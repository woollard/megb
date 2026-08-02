"""Tests for src.reference.g4_benchmark (MEGB-03G.4).

Everything here is offline: a fake execution backend, temp cache/audit
directories, and an injected leftover-container check -- no real Docker
access, matching the frozen MEGB-03G.4 Benchmark Plan's requirement that
the synthetic workload itself never touch the real corpus. The plan's
*actual* real-Docker execution (calibration, throughput sweep, cross-tier
equivalence, warm-cache, interruption/resumption against a real
``DockerPerInvocationBackend``) is run separately and is not part of this
offline suite, matching the plan's own "not on every push" requirement.

Covers: the scaling-decision pure function (no scaling needed, scaling
down while preserving proportions, throughput-blocked), the workload
builders (correct case counts, cold-cache namespacing), the
measurement-only equivalence comparator, readiness determination, and a
full offline end-to-end smoke test of ``run_g4_benchmark`` itself against a
fake backend.
"""

# See tests/test_reference_cache_key.py's note: this file intentionally
# builds its own local fixtures (a fake CandidateExecutionResult, a fake
# ReferenceTaskResult) independent of test_reference_evaluator.py's/
# test_result_schema.py's own copies, rather than importing or subclassing
# them.
# pylint: disable=duplicate-code

import hashlib
import threading
from pathlib import Path

import pytest

from src.evaluators.schema import FailureCategory
from src.execution.backend import ExecutionBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionLimits,
    ExecutionStatus,
)
from src.reference.g4_benchmark import (
    _TIER_CASE_COUNTS,
    _UNSCALED_CROSS_TIER_N,
    _UNSCALED_INTERRUPTION_N,
    _UNSCALED_THROUGHPUT_N,
    CalibrationMeasurement,
    EquivalenceCheckResult,
    InterruptionResumptionResult,
    InvalidG4ReportError,
    ReadinessState,
    ScaledRunCounts,
    ScalingDecision,
    ThroughputSweepResult,
    WarmCacheCheckResult,
    _best_speedup,
    _determine_readiness,
    _evidence_for,
    _measurement_matches,
    _run_context,
    _run_interruption_resumption,
    _work_items,
    compute_scaling_decision,
    run_g4_benchmark,
)
from src.reference.reference_audit import ReferenceAuditLog
from src.reference.reference_cache import ReferenceResultCache
from src.reference.result_schema import MeasurementStatus, ReferenceTaskResult

# --- CalibrationMeasurement ----------------------------------------------------


def test_calibration_measurement_computes_mean() -> None:
    """Calibration measurement computes mean."""
    measurement = CalibrationMeasurement(sample_seconds=(1.0, 2.0, 3.0))
    assert measurement.mean_seconds == pytest.approx(2.0)


def test_calibration_measurement_rejects_mismatched_mean() -> None:
    """Calibration measurement rejects mismatched mean."""
    with pytest.raises(InvalidG4ReportError):
        CalibrationMeasurement(sample_seconds=(1.0, 2.0, 3.0), mean_seconds=999.0)


def test_calibration_measurement_rejects_empty_samples() -> None:
    """Calibration measurement rejects empty samples."""
    with pytest.raises(InvalidG4ReportError):
        CalibrationMeasurement(sample_seconds=())


def test_calibration_measurement_rejects_negative_sample() -> None:
    """Calibration measurement rejects negative sample."""
    with pytest.raises(InvalidG4ReportError):
        CalibrationMeasurement(sample_seconds=(1.0, -0.5))


# --- Scaling decision ----------------------------------------------------------


def test_compute_scaling_decision_no_scaling_needed_for_fast_calibration() -> None:
    """A fast per-invocation measurement needs no scaling."""
    calibration = CalibrationMeasurement(sample_seconds=(0.01, 0.01, 0.01))
    decision = compute_scaling_decision(calibration)
    assert decision.scale_factor == 1.0
    assert decision.scaled_counts == ScaledRunCounts(
        throughput_sweep_n=_UNSCALED_THROUGHPUT_N,
        cross_tier_n=_UNSCALED_CROSS_TIER_N,
        interruption_n=_UNSCALED_INTERRUPTION_N,
    )
    assert decision.scaled_projected_seconds <= decision.ceiling_seconds
    assert not decision.throughput_blocked


def test_compute_scaling_decision_scales_down_preserving_proportions() -> None:
    """A slow per-invocation measurement scales every run's N down by the
    same factor, keeping their relative proportions."""
    # Chosen so the unscaled projection comfortably exceeds the ceiling.
    calibration = CalibrationMeasurement(sample_seconds=(10.0, 10.0, 10.0))
    decision = compute_scaling_decision(calibration)
    assert decision.scale_factor < 1.0
    assert decision.scaled_projected_seconds <= decision.ceiling_seconds + 1e-6

    unscaled_ratio_throughput = _UNSCALED_THROUGHPUT_N / _UNSCALED_CROSS_TIER_N
    scaled_ratio_throughput = (
        decision.scaled_counts.throughput_sweep_n / decision.scaled_counts.cross_tier_n
    )
    # Integer rounding means this is approximate, not exact.
    assert scaled_ratio_throughput == pytest.approx(unscaled_ratio_throughput, rel=0.5)
    assert decision.scaled_counts.throughput_sweep_n >= 1
    assert decision.scaled_counts.cross_tier_n >= 1
    assert decision.scaled_counts.interruption_n >= 1


def test_compute_scaling_decision_never_scales_up() -> None:
    """A near-zero calibration never inflates counts beyond the frozen plan's own."""
    calibration = CalibrationMeasurement(sample_seconds=(0.0001,))
    decision = compute_scaling_decision(calibration)
    assert decision.scaled_counts.throughput_sweep_n == _UNSCALED_THROUGHPUT_N
    assert decision.scaled_counts.cross_tier_n == _UNSCALED_CROSS_TIER_N
    assert decision.scaled_counts.interruption_n == _UNSCALED_INTERRUPTION_N


def test_compute_scaling_decision_blocks_throughput_when_extremely_slow() -> None:
    """An extreme per-invocation cost blocks the throughput-measurement
    portion specifically, even after scaling to N=1."""
    calibration = CalibrationMeasurement(sample_seconds=(10_000.0,))
    decision = compute_scaling_decision(calibration)
    assert decision.throughput_blocked is True


def test_scaling_decision_is_reproducible_from_its_own_fields() -> None:
    """The same calibration always yields the same scaling decision."""
    calibration = CalibrationMeasurement(sample_seconds=(2.5, 3.5))
    first = compute_scaling_decision(calibration)
    second = compute_scaling_decision(calibration)
    assert first == second


# --- Workload builders ----------------------------------------------------------


@pytest.mark.parametrize("tier", ["LOW", "MEDIAN", "HIGH"])
def test_evidence_for_produces_correct_case_count(tier: str) -> None:
    """Evidence for produces correct case count."""
    case_count = _TIER_CASE_COUNTS[tier]
    evidence = _evidence_for(f"G4Bench/{tier}/0", case_count)
    assert len(evidence.cases) == case_count
    assert [case.args[0] for case in evidence.cases] == list(range(1, case_count + 1))


def test_work_items_are_namespaced_for_cold_cache() -> None:
    """Work items are namespaced for cold cache."""
    run_context = _run_context()
    items_a = _work_items("MEDIAN-C1", 3, run_context)
    items_b = _work_items("MEDIAN-C4", 3, run_context)
    task_ids_a = {item.task_id for item in items_a}
    task_ids_b = {item.task_id for item in items_b}
    assert task_ids_a.isdisjoint(task_ids_b)


def test_work_items_share_one_fixed_candidate() -> None:
    """Work items share one fixed candidate."""
    items = _work_items("MEDIAN-C1", 4, _run_context())
    sha256_values = {item.candidate_sha256 for item in items}
    assert len(sha256_values) == 1
    assert all(
        hashlib.sha256(item.candidate_code.encode("utf-8")).hexdigest() == item.candidate_sha256
        for item in items
    )


def test_wired_evidence_and_context_never_carry_real_identity() -> None:
    """The wired g4_benchmark evidence/run_context never carry any real
    MEGB-03B/C/E/F identity (MEGB-03G.4 correction: no forced-real labels)."""
    from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION  # pylint: disable=import-outside-toplevel

    from src.reference.oracle import (  # pylint: disable=import-outside-toplevel
        COMPARISON_PROFILE_VERSION,
        ORACLE_ALGORITHM_VERSION,
    )
    from src.reference.partition import (  # pylint: disable=import-outside-toplevel
        PARTITION_ALGORITHM_VERSION,
    )
    from src.reference.reference_evaluator import (  # pylint: disable=import-outside-toplevel
        EVALUATOR_VERSION_FULL,
        EXECUTION_PROFILE_ID_FULL,
        EXECUTION_PROTOCOL_VERSION,
    )

    context = _run_context()
    evidence = _evidence_for("G4Bench/MEDIAN/0", 1)

    assert context.dataset_version != HUMANEVAL_PLUS_VERSION
    assert context.partition_version != PARTITION_ALGORITHM_VERSION
    assert context.evaluator_version != EVALUATOR_VERSION_FULL
    assert context.execution_profile_id != EXECUTION_PROFILE_ID_FULL
    assert context.comparison_profile_version != COMPARISON_PROFILE_VERSION
    assert context.execution_protocol_version != EXECUTION_PROTOCOL_VERSION
    assert evidence.oracle_version != ORACLE_ALGORITHM_VERSION
    assert evidence.partition_version != PARTITION_ALGORITHM_VERSION
    assert evidence.comparison_profile.profile_version != COMPARISON_PROFILE_VERSION


# --- Measurement comparator ------------------------------------------------------


def _fake_task_result(**overrides: object) -> ReferenceTaskResult:
    fields: dict[str, object] = {
        "task_id": "G4Bench/MEDIAN-C1/0",
        "candidate_id": "g4-cand-a",
        "candidate_sha256": "a" * 64,
        "context": _run_context(),
        "status": MeasurementStatus.VALID,
        "q_ref_task": 1.0,
        "reference_case_total": 5,
        "reference_case_pass_count": 5,
        "first_failure_category": FailureCategory.NONE,
        "oracle_version": "oracle-v1",
        "reference_case_checksum": "b" * 64,
        "evaluated_at": "2026-08-01T00:00:00Z",
        "duration_seconds": 0.2,
    }
    fields.update(overrides)
    return ReferenceTaskResult(**fields)  # type: ignore[arg-type]


def test_measurement_matches_ignores_identity_fields() -> None:
    """Measurement matches ignores identity fields."""
    first = _fake_task_result(task_id="G4Bench/MEDIAN-C1/0", candidate_sha256="a" * 64)
    second = _fake_task_result(task_id="G4Bench/MEDIAN-C4/0", candidate_sha256="c" * 64)
    assert _measurement_matches(first, second)


def test_measurement_matches_detects_a_real_content_difference() -> None:
    """Measurement matches detects a real content difference."""
    first = _fake_task_result(q_ref_task=1.0, reference_case_pass_count=5)
    second = _fake_task_result(
        q_ref_task=0.0,
        reference_case_pass_count=4,
        first_failure_category=FailureCategory.WRONG_OUTPUT,
    )
    assert not _measurement_matches(first, second)


# --- Readiness determination -----------------------------------------------------


def _passing_components() -> tuple[
    ScalingDecision,
    tuple[EquivalenceCheckResult, ...],
    WarmCacheCheckResult,
    InterruptionResumptionResult,
]:
    scaling = compute_scaling_decision(CalibrationMeasurement(sample_seconds=(0.01,)))
    equivalence = tuple(
        EquivalenceCheckResult(
            tier=tier,
            n_items=4,
            sequential_wall_seconds=1.0,
            concurrent_wall_seconds=0.5,
            equivalent=True,
            mismatched_work_item_ids=(),
        )
        for tier in _TIER_CASE_COUNTS
    )
    warm = WarmCacheCheckResult(n_items=8, all_cache_hits=True, fresh_execution_keys=0)
    interruption = InterruptionResumptionResult(
        n_items=6,
        first_run_interrupted=True,
        first_run_accepted=1,
        first_run_unstarted=5,
        resumed_run_accepted=6,
        resumed_run_unstarted=0,
        fully_completed_without_gaps=True,
    )
    return scaling, equivalence, warm, interruption


def test_determine_readiness_ready_when_everything_passes() -> None:
    """Determine readiness ready when everything passes."""
    scaling, equivalence, warm, interruption = _passing_components()
    readiness = _determine_readiness(scaling, equivalence, warm, interruption, (), 2.0, 100.0)
    assert readiness == ReadinessState.ORCHESTRATION_READY_FOR_MEGB_03H


def test_determine_readiness_blocked_on_equivalence_mismatch() -> None:
    """Determine readiness blocked on equivalence mismatch."""
    scaling, equivalence, warm, interruption = _passing_components()
    broken = equivalence[:-1] + (
        EquivalenceCheckResult(
            tier="HIGH",
            n_items=4,
            sequential_wall_seconds=1.0,
            concurrent_wall_seconds=0.5,
            equivalent=False,
            mismatched_work_item_ids=("HIGH-C1-0",),
        ),
    )
    readiness = _determine_readiness(scaling, broken, warm, interruption, (), 2.0, 100.0)
    assert readiness == ReadinessState.ORCHESTRATION_BLOCKED


def test_determine_readiness_blocked_on_leftover_containers() -> None:
    """Determine readiness blocked on leftover containers."""
    scaling, equivalence, warm, interruption = _passing_components()
    readiness = _determine_readiness(
        scaling, equivalence, warm, interruption, ("megb-runner-leaked",), 2.0, 100.0
    )
    assert readiness == ReadinessState.ORCHESTRATION_BLOCKED


def test_determine_readiness_blocked_on_low_speedup() -> None:
    """Determine readiness blocked on low speedup."""
    scaling, equivalence, warm, interruption = _passing_components()
    readiness = _determine_readiness(scaling, equivalence, warm, interruption, (), 1.1, 100.0)
    assert readiness == ReadinessState.ORCHESTRATION_BLOCKED


def test_determine_readiness_blocked_when_nothing_was_actually_interrupted() -> None:
    """Determine readiness blocked when nothing was actually interrupted."""
    scaling, equivalence, warm, _ = _passing_components()
    non_interrupted = InterruptionResumptionResult(
        n_items=6,
        first_run_interrupted=False,
        first_run_accepted=6,
        first_run_unstarted=0,
        resumed_run_accepted=6,
        resumed_run_unstarted=0,
        fully_completed_without_gaps=True,
    )
    readiness = _determine_readiness(scaling, equivalence, warm, non_interrupted, (), 2.0, 100.0)
    assert readiness == ReadinessState.ORCHESTRATION_BLOCKED


def test_best_speedup_computes_ratio_against_sequential_baseline() -> None:
    """Best speedup computes ratio against sequential baseline."""
    results = (
        ThroughputSweepResult(concurrency=1, n_items=8, wall_seconds=10.0, accepted_work_items=8),
        ThroughputSweepResult(concurrency=2, n_items=8, wall_seconds=6.0, accepted_work_items=8),
        ThroughputSweepResult(concurrency=4, n_items=8, wall_seconds=4.0, accepted_work_items=8),
    )
    assert _best_speedup(results) == pytest.approx(2.5)


# --- Full offline end-to-end smoke test -------------------------------------------


class _FakeCorrectBackend(ExecutionBackend):
    """Deterministically correct, instantaneous fake backend -- proves
    run_g4_benchmark's own wiring end-to-end without any real Docker
    container ever being launched."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.call_count = 0

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        with self._lock:
            self.call_count += 1
        n = request.args[0]
        return CandidateExecutionResult(
            invocation_id=f"inv-{self.call_count}",
            status=ExecutionStatus.COMPLETED,
            return_value=(n * 2) + 1,
            exception_type=None,
            exception_message=None,
            wall_time_sec=0.001,
            candidate_wall_time_sec=0.0005,
            exit_code=0,
            terminating_signal=None,
            stdout="",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            backend_id="fake",
            backend_version="1",
            runner_image_digest="sha256:fake",
            protocol_version=request.protocol_version,
            limits=ExecutionLimits(),
            started_at="2026-08-01T00:00:00Z",
        )


def test_run_g4_benchmark_end_to_end_offline(tmp_path: Path) -> None:
    """The full plan wiring runs correctly offline against a fake backend:
    calibration, scaling, throughput sweep, cross-tier equivalence,
    warm-cache, and interruption/resumption all execute and reconcile."""
    report = run_g4_benchmark(
        cache_dir=tmp_path / "cache",
        audit_path=tmp_path / "audit.jsonl",
        backend_factory=_FakeCorrectBackend,
        leftover_container_check=lambda: (),
    )

    assert report.scaling.scale_factor == 1.0  # the fake backend is effectively instantaneous
    assert len(report.throughput_results) == 3
    assert len(report.equivalence_results) == 3
    assert all(result.equivalent for result in report.equivalence_results)
    assert report.warm_cache_result.all_cache_hits
    assert report.warm_cache_result.fresh_execution_keys == 0
    assert report.interruption_result.first_run_interrupted
    assert report.interruption_result.fully_completed_without_gaps
    assert not report.leftover_containers
    # A fake, near-instant backend naturally does not demonstrate a real
    # concurrency speedup, so readiness itself is not asserted here -- only
    # that every *correctness* component of the wiring behaves as designed.
    assert report.best_speedup >= 0.0


def test_run_g4_benchmark_uses_the_injected_leftover_check(tmp_path: Path) -> None:
    """The injected leftover-container check is actually used, not the real one."""
    calls = {"n": 0}

    def fake_check() -> tuple[str, ...]:
        calls["n"] += 1
        return ()

    run_g4_benchmark(
        cache_dir=tmp_path / "cache",
        audit_path=tmp_path / "audit.jsonl",
        backend_factory=_FakeCorrectBackend,
        leftover_container_check=fake_check,
    )
    assert calls["n"] == 1


def test_interruption_run_actually_produces_not_started_items(tmp_path: Path) -> None:
    """Confirms the interruption step's own outcomes include at least one
    NOT_STARTED item on the first pass -- i.e. the interruption is real,
    not a no-op."""
    cache = ReferenceResultCache(tmp_path / "cache")
    audit_log = ReferenceAuditLog(tmp_path / "audit.jsonl")
    result = _run_interruption_resumption(cache, audit_log, _FakeCorrectBackend, 6, _run_context())
    assert result.first_run_interrupted
    assert result.first_run_unstarted > 0
    assert result.resumed_run_unstarted == 0
