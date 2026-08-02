"""MEGB-03G.4: orchestration qualification benchmark.

Validates, against the real MEGB-02 execution boundary (a real
``DockerPerInvocationBackend``, real containers), the properties MEGB-03G.3
already proved with synthetic fake backends: sequential/concurrent
semantic equivalence, isolation preservation, cache correctness,
deterministic output ordering, bounded concurrency/backpressure,
interruption/resumption correctness, and infrastructure-level throughput.
Uses only the synthetic, non-privileged workload frozen in the "Approved
MEGB-03G.4 Benchmark Plan" (``tickets/megb-03.md``) -- no real reference-only
inputs, expected outputs, canonical solutions, or privileged manifests.

Explicitly **not** MEGB-03H's job: real-corpus resource calibration, the
frozen high-assurance execution profile, repeated-run/environmental
determinism, or the definitive runtime/compute projection MEGB-06A
consumes (see the "MEGB-03G.4 versus MEGB-03H" boundary in the ticket).
This module's ``ReadinessState`` is deliberately one of
``ORCHESTRATION_READY_FOR_MEGB_03H`` / ``ORCHESTRATION_BLOCKED`` -- never a
claim of final MEGB-06A readiness.

This module's own throughput measurements are host-dependent and
expensive; per the frozen plan's section 5, ``run_g4_benchmark`` must be
invoked through a designated manual/scheduled workflow (e.g.
``python -m src.reference.g4_benchmark``), never automatically on every
push. Everything in this module short of :func:`run_g4_benchmark` itself
(workload construction, the scaling-decision math, the report schema, and
the cross-tier measurement comparator) is pure/offline and covered by
``tests/test_g4_benchmark.py`` without touching Docker; only
:func:`run_g4_benchmark` and its private ``_run_*`` helpers below actually
invoke a backend.
"""

import dataclasses
import hashlib
import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION

from src.execution.backend import ExecutionBackend
from src.reference.oracle import (
    COMPARISON_PROFILE_VERSION,
    ORACLE_ALGORITHM_VERSION,
    POOL_REFERENCE_ONLY,
    comparison_profile_for_task,
    generate_oracle_record,
)
from src.reference.partition import PARTITION_ALGORITHM_VERSION
from src.reference.reference_audit import ReferenceAuditLog
from src.reference.reference_cache import ReferenceResultCache
from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EXECUTION_PROFILE_ID_FULL,
    EXECUTION_PROTOCOL_VERSION,
    FULL_EXECUTION_PROFILE,
    ReferenceCase,
    ReferenceTaskEvidence,
)
from src.reference.reference_orchestrator import (
    MappingEvidenceResolver,
    OrchestrationConfig,
    OrchestrationRunSummary,
    ReferenceOrchestrator,
    RetryPolicy,
    WorkItem,
)
from src.reference.result_schema import ReferenceRunContext, ReferenceTaskResult

G4_REPORT_SCHEMA_VERSION = "megb-03g4-throughput-report-v1"

DEFAULT_BENCHMARK_CACHE_DIR = Path("artifacts/privileged/reference/g4_benchmark_cache")
DEFAULT_BENCHMARK_AUDIT_PATH = Path(
    "artifacts/reference/g4_benchmark_audit/g4_benchmark_audit_log.jsonl"
)

_ENTRY_POINT = "g4_compute"
_CANONICAL_SOLUTION = "def g4_compute(n):\n    return (n * 2) + 1\n"
# `dataset_version` must be the real HUMANEVAL_PLUS_VERSION: evaluate_reference
# (already-accepted MEGB-03F code) hardcodes evidence.dataset_version ==
# HUMANEVAL_PLUS_VERSION as a version-consistency check unrelated to this
# benchmark, so a synthetic label here would always raise
# ReferenceEvaluatorVersionMismatchError. This is only a shared *version
# label* for project-controlled code (like oracle_version/partition_version
# below) -- it does not mean any real dataset content is loaded or used;
# dataset_checksum/task_manifest_checksum (the actual content-identity
# fields) and every task_id (always under the G4Bench/ namespace) remain
# fully synthetic and never collide with the real corpus.
_DATASET_VERSION = HUMANEVAL_PLUS_VERSION
_DATASET_CHECKSUM = hashlib.sha256(b"g4-benchmark-synthetic-dataset-v1").hexdigest()
_TASK_MANIFEST_CHECKSUM = hashlib.sha256(b"g4-benchmark-synthetic-manifest-v1").hexdigest()

_TIER_CASE_COUNTS = {"LOW": 1, "MEDIAN": 5, "HIGH": 20}

_UNSCALED_THROUGHPUT_N = 8
_THROUGHPUT_CONCURRENCIES = (1, 2, 4)

_UNSCALED_CROSS_TIER_N = 4
_CROSS_TIER_CONCURRENCIES = (1, 4)

_UNSCALED_INTERRUPTION_N = 6
_INTERRUPTION_CONCURRENCY = 2

_CALIBRATION_SAMPLES = 3
_CEILING_SECONDS = 55.0 * 60.0


class ReadinessState(str, Enum):
    """MEGB-03G.4's own readiness verdict -- an orchestration-qualification
    claim only, never a claim of final MEGB-06A readiness (that remains
    MEGB-03H's and MEGB-06A's, per the ticket's own boundary)."""

    ORCHESTRATION_READY_FOR_MEGB_03H = "ORCHESTRATION_READY_FOR_MEGB_03H"
    ORCHESTRATION_BLOCKED = "ORCHESTRATION_BLOCKED"


class InvalidG4ReportError(ValueError):
    """Raised when a benchmark report's fields are internally inconsistent."""


@dataclass(frozen=True)
class CalibrationMeasurement:
    """Raw per-invocation timings from the frozen plan's calibration step,
    plus their recomputed-and-verified mean (the same auto-compute-or-reject
    pattern used elsewhere in this project: a caller-supplied ``mean_seconds``
    that disagrees with the recomputation is rejected, not silently trusted).
    """

    sample_seconds: tuple[float, ...]
    mean_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not self.sample_seconds:
            raise InvalidG4ReportError("sample_seconds must be nonempty")
        if any(value < 0 for value in self.sample_seconds):
            raise InvalidG4ReportError("sample_seconds must all be non-negative")
        expected_mean = sum(self.sample_seconds) / len(self.sample_seconds)
        if self.mean_seconds and abs(self.mean_seconds - expected_mean) > 1e-9:
            raise InvalidG4ReportError(
                f"mean_seconds {self.mean_seconds!r} does not match the recomputed "
                f"mean {expected_mean!r} over its own sample_seconds"
            )
        object.__setattr__(self, "mean_seconds", expected_mean)


@dataclass(frozen=True)
class ScaledRunCounts:
    """Per-run work-item counts (``N``) actually used, after scaling."""

    throughput_sweep_n: int
    cross_tier_n: int
    interruption_n: int


_UNSCALED_COUNTS = ScaledRunCounts(
    throughput_sweep_n=_UNSCALED_THROUGHPUT_N,
    cross_tier_n=_UNSCALED_CROSS_TIER_N,
    interruption_n=_UNSCALED_INTERRUPTION_N,
)


def _throughput_case_invocations(n: int) -> int:
    return n * _TIER_CASE_COUNTS["MEDIAN"] * len(_THROUGHPUT_CONCURRENCIES)


def _cross_tier_case_invocations(n: int) -> int:
    return sum(_TIER_CASE_COUNTS.values()) * n * len(_CROSS_TIER_CONCURRENCIES)


def _interruption_case_invocations(n: int) -> int:
    return n * _TIER_CASE_COUNTS["MEDIAN"]


def _total_case_invocations(counts: ScaledRunCounts) -> int:
    return (
        _throughput_case_invocations(counts.throughput_sweep_n)
        + _cross_tier_case_invocations(counts.cross_tier_n)
        + _interruption_case_invocations(counts.interruption_n)
    )


@dataclass(frozen=True)
class ScalingDecision:
    """The frozen plan's section-3 scaling rule, applied to one real
    calibration measurement. Reproducible from its own recorded fields
    alone: ``scaled_counts``/``scaled_total_case_invocations``/
    ``scaled_projected_seconds`` are all deterministic functions of
    ``calibration.mean_seconds`` and the module's own frozen constants."""

    calibration: CalibrationMeasurement
    unscaled_total_case_invocations: int
    unscaled_projected_seconds: float
    ceiling_seconds: float
    scale_factor: float
    scaled_counts: ScaledRunCounts
    scaled_total_case_invocations: int
    scaled_projected_seconds: float
    throughput_blocked: bool


def compute_scaling_decision(calibration: CalibrationMeasurement) -> ScalingDecision:
    """Pure function implementing the frozen plan's section-3 scaling rule.

    Scales every run's item count down by the same factor (preserving
    relative proportions) if the unscaled projection exceeds the 55-minute
    ceiling; never scales up beyond the plan's own frozen counts.
    """
    unscaled_total = _total_case_invocations(_UNSCALED_COUNTS)
    unscaled_projected = calibration.mean_seconds * unscaled_total

    if unscaled_projected <= _CEILING_SECONDS:
        scale_factor = 1.0
        scaled_counts = _UNSCALED_COUNTS
    else:
        scale_factor = _CEILING_SECONDS / unscaled_projected
        scaled_counts = ScaledRunCounts(
            throughput_sweep_n=max(1, int(_UNSCALED_THROUGHPUT_N * scale_factor)),
            cross_tier_n=max(1, int(_UNSCALED_CROSS_TIER_N * scale_factor)),
            interruption_n=max(1, int(_UNSCALED_INTERRUPTION_N * scale_factor)),
        )

    scaled_total = _total_case_invocations(scaled_counts)
    scaled_projected = calibration.mean_seconds * scaled_total
    throughput_blocked = (
        calibration.mean_seconds * _throughput_case_invocations(scaled_counts.throughput_sweep_n)
        > _CEILING_SECONDS
    )
    return ScalingDecision(
        calibration=calibration,
        unscaled_total_case_invocations=unscaled_total,
        unscaled_projected_seconds=unscaled_projected,
        ceiling_seconds=_CEILING_SECONDS,
        scale_factor=scale_factor,
        scaled_counts=scaled_counts,
        scaled_total_case_invocations=scaled_total,
        scaled_projected_seconds=scaled_projected,
        throughput_blocked=throughput_blocked,
    )


# --- Synthetic, non-privileged workload construction -------------------------


def _canonical_fn() -> Callable[[int], int]:
    namespace: dict[str, object] = {}
    exec(_CANONICAL_SOLUTION, namespace)  # pylint: disable=exec-used
    return namespace[_ENTRY_POINT]  # type: ignore[return-value]


def _case_id(index: int, case_count: int) -> str:
    # Zero-padded so lexical case_id ordering (required by
    # ReferenceTaskEvidence) agrees with numeric ordering even at the HIGH
    # tier's 20 cases -- "c1" < "c10" < "c2" lexically would otherwise
    # violate the evidence's own sorted-by-case_id invariant.
    width = max(1, len(str(case_count - 1)))
    return f"c{index:0{width}d}"


def _evidence_for(task_id: str, case_count: int) -> ReferenceTaskEvidence:
    profile = comparison_profile_for_task(_ENTRY_POINT, atol=0.0)
    canonical_fn = _canonical_fn()
    cases = tuple(
        ReferenceCase(
            case_id=_case_id(i, case_count),
            args=(i + 1,),
            oracle_record=generate_oracle_record(
                task_id=task_id,
                case_id=_case_id(i, case_count),
                args=(i + 1,),
                provenance="original",
                pool=POOL_REFERENCE_ONLY,
                canonical_fn=canonical_fn,
                profile=profile,
            ),
        )
        for i in range(case_count)
    )
    return ReferenceTaskEvidence(
        task_id=task_id,
        entry_point=_ENTRY_POINT,
        comparison_profile=profile,
        cases=cases,
        oracle_version=ORACLE_ALGORITHM_VERSION,
        partition_version=PARTITION_ALGORITHM_VERSION,
        dataset_version=_DATASET_VERSION,
        protocol_version=EXECUTION_PROTOCOL_VERSION,
        dataset_checksum=_DATASET_CHECKSUM,
        task_manifest_checksum=_TASK_MANIFEST_CHECKSUM,
    )


def _run_context() -> ReferenceRunContext:
    return ReferenceRunContext(
        experiment_run_id="megb-03g4-benchmark",
        optimization_run_id="megb-03g4-benchmark",
        optimization_config_sha256="0" * 64,
        portfolio_frozen_at="2026-01-01T00:00:00Z",
        portfolio_selection_rule="g4-benchmark-fixed-candidate",
        evaluator_version=EVALUATOR_VERSION_FULL,
        dataset_version=_DATASET_VERSION,
        partition_version=PARTITION_ALGORITHM_VERSION,
        execution_profile_id=EXECUTION_PROFILE_ID_FULL,
        comparison_profile_version=COMPARISON_PROFILE_VERSION,
        execution_protocol_version=EXECUTION_PROTOCOL_VERSION,
        dataset_checksum=_DATASET_CHECKSUM,
        task_manifest_checksum=_TASK_MANIFEST_CHECKSUM,
    )


def _work_items(namespace: str, n: int, run_context: ReferenceRunContext) -> tuple[WorkItem, ...]:
    """Every item in ``namespace`` shares one fixed correct candidate; the
    namespace itself (not the candidate) guarantees a cold cache for a
    fresh run, since it is embedded in every item's ``task_id``."""
    candidate_sha256 = hashlib.sha256(_CANONICAL_SOLUTION.encode("utf-8")).hexdigest()
    return tuple(
        WorkItem(
            work_item_id=f"{namespace}-{i}",
            input_ordinal=i,
            task_id=f"G4Bench/{namespace}/{i}",
            candidate_id=f"g4-cand-{namespace}",
            candidate_sha256=candidate_sha256,
            candidate_code=_CANONICAL_SOLUTION,
            run_context=run_context,
        )
        for i in range(n)
    )


def _evidence_map(items: tuple[WorkItem, ...], case_count: int) -> dict[str, ReferenceTaskEvidence]:
    return {item.task_id: _evidence_for(item.task_id, case_count) for item in items}


def _make_orchestrator(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    cache: ReferenceResultCache,
    audit_log: ReferenceAuditLog,
    evidence_map: dict[str, ReferenceTaskEvidence],
    backend_factory: Callable[[], ExecutionBackend],
    max_workers: int,
    on_in_flight_change: Callable[[int], None] | None = None,
) -> ReferenceOrchestrator:
    return ReferenceOrchestrator(
        cache=cache,
        audit_log=audit_log,
        evidence_resolver=MappingEvidenceResolver(evidence_map),
        backend_factory=backend_factory,
        config=OrchestrationConfig(
            max_workers=max_workers,
            max_in_flight=max_workers,
            retry_policy=RetryPolicy(max_attempts=2),
            profile=FULL_EXECUTION_PROFILE,
        ),
        on_in_flight_change=on_in_flight_change,
    )


# --- Result comparison --------------------------------------------------------


def _measurement_matches(first: ReferenceTaskResult, second: ReferenceTaskResult) -> bool:
    """Compares only the candidate-correctness measurement fields -- not
    identity (``task_id``/``candidate_sha256``/``context``), which
    legitimately differ between the sequential and concurrent legs of the
    cross-tier equivalence check (each leg uses its own task-ID namespace
    to force a cold cache, per the frozen plan)."""
    return (
        first.status == second.status
        and first.q_ref_task == second.q_ref_task
        and first.reference_case_total == second.reference_case_total
        and first.reference_case_pass_count == second.reference_case_pass_count
        and first.first_failure_category == second.first_failure_category
    )


# --- Report schema -------------------------------------------------------------


@dataclass(frozen=True)
class ThroughputSweepResult:
    """One concurrency level's cold-cache wall-clock timing, MEDIAN tier."""

    concurrency: int
    n_items: int
    wall_seconds: float
    accepted_work_items: int


@dataclass(frozen=True)
class EquivalenceCheckResult:
    """One tier's sequential-vs-concurrent measurement-equivalence check."""

    tier: str
    n_items: int
    sequential_wall_seconds: float
    concurrent_wall_seconds: float
    equivalent: bool
    mismatched_work_item_ids: tuple[str, ...]


@dataclass(frozen=True)
class WarmCacheCheckResult:
    """Result of immediately re-running an already-completed run: every
    item must be a cache hit, with zero fresh backend executions."""

    n_items: int
    all_cache_hits: bool
    fresh_execution_keys: int


@dataclass(frozen=True)
class InterruptionResumptionResult:
    """Result of cooperatively cancelling a run partway through, then
    resuming it in a second, fresh orchestrator over the same work items."""

    n_items: int
    first_run_interrupted: bool
    first_run_accepted: int
    first_run_unstarted: int
    resumed_run_accepted: int
    resumed_run_unstarted: int
    fully_completed_without_gaps: bool


@dataclass(frozen=True)
class G4BenchmarkReport:  # pylint: disable=too-many-instance-attributes
    """The full, typed, versioned MEGB-03G.4 benchmark report.

    Reproducible from its own recorded fields: ``scaling`` alone pins the
    calibration measurement and the deterministic scaling math that
    derived every other section's item counts.
    """

    schema_version: str
    generated_at: str
    readiness: ReadinessState
    scaling: ScalingDecision
    throughput_results: tuple[ThroughputSweepResult, ...]
    best_speedup: float
    equivalence_results: tuple[EquivalenceCheckResult, ...]
    warm_cache_result: WarmCacheCheckResult
    interruption_result: InterruptionResumptionResult
    leftover_containers: tuple[str, ...]
    total_wall_seconds: float


def _best_speedup(results: tuple[ThroughputSweepResult, ...]) -> float:
    by_concurrency = {result.concurrency: result.wall_seconds for result in results}
    baseline = by_concurrency.get(1)
    if not baseline:
        return 0.0
    return max(
        (
            baseline / wall_seconds
            for concurrency, wall_seconds in by_concurrency.items()
            if concurrency > 1
        ),
        default=0.0,
    )


def _determine_readiness(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    scaling: ScalingDecision,
    equivalence_results: tuple[EquivalenceCheckResult, ...],
    warm_cache_result: WarmCacheCheckResult,
    interruption_result: InterruptionResumptionResult,
    leftover_containers: tuple[str, ...],
    best_speedup: float,
    total_wall_seconds: float,
) -> ReadinessState:
    blocked = (
        scaling.throughput_blocked
        or not all(result.equivalent for result in equivalence_results)
        or not warm_cache_result.all_cache_hits
        or warm_cache_result.fresh_execution_keys != 0
        or not interruption_result.first_run_interrupted
        or interruption_result.first_run_unstarted == 0
        or not interruption_result.fully_completed_without_gaps
        or bool(leftover_containers)
        or best_speedup < 1.5
        or total_wall_seconds > 3600.0
    )
    if blocked:
        return ReadinessState.ORCHESTRATION_BLOCKED
    return ReadinessState.ORCHESTRATION_READY_FOR_MEGB_03H


def _check_leftover_containers() -> tuple[str, ...]:
    # Mirrors tests/test_execution_sandbox.py's _list_megb_runner_containers
    # (the same docker-ps-based leftover check the CI workflow itself
    # already runs) -- duplicated deliberately rather than shared, since
    # production code must not import test helpers and this one function is
    # too small to justify a new shared module just to avoid repeating it.
    # pylint: disable=duplicate-code
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=megb-runner-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return tuple(name for name in result.stdout.splitlines() if name.strip())


# --- Real-Docker execution steps ----------------------------------------------


def _run_calibration(
    cache: ReferenceResultCache,
    audit_log: ReferenceAuditLog,
    backend_factory: Callable[[], ExecutionBackend],
) -> CalibrationMeasurement:
    run_context = _run_context()
    items = _work_items("CALIBRATION", _CALIBRATION_SAMPLES, run_context)
    evidence_map = _evidence_map(items, _TIER_CASE_COUNTS["LOW"])
    samples = []
    for item in items:
        orchestrator = _make_orchestrator(
            cache, audit_log, evidence_map, backend_factory, max_workers=1
        )
        start = time.monotonic()
        orchestrator.run([item], run_id=f"g4-calibration-{item.work_item_id}")
        samples.append(time.monotonic() - start)
    return CalibrationMeasurement(sample_seconds=tuple(samples))


def _run_throughput_sweep(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    cache: ReferenceResultCache,
    audit_log: ReferenceAuditLog,
    backend_factory: Callable[[], ExecutionBackend],
    n: int,
    run_context: ReferenceRunContext,
) -> tuple[ThroughputSweepResult, ...]:
    results = []
    for concurrency in _THROUGHPUT_CONCURRENCIES:
        namespace = f"MEDIAN-C{concurrency}"
        items = _work_items(namespace, n, run_context)
        evidence_map = _evidence_map(items, _TIER_CASE_COUNTS["MEDIAN"])
        orchestrator = _make_orchestrator(
            cache, audit_log, evidence_map, backend_factory, concurrency
        )
        start = time.monotonic()
        summary = orchestrator.run(items, run_id=f"g4-throughput-{namespace}")
        wall_seconds = time.monotonic() - start
        results.append(
            ThroughputSweepResult(
                concurrency=concurrency,
                n_items=n,
                wall_seconds=wall_seconds,
                accepted_work_items=summary.accepted_work_items,
            )
        )
    return tuple(results)


def _run_one_equivalence_leg(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    cache: ReferenceResultCache,
    audit_log: ReferenceAuditLog,
    backend_factory: Callable[[], ExecutionBackend],
    n: int,
    run_context: ReferenceRunContext,
    tier: str,
    case_count: int,
    concurrency: int,
) -> tuple[OrchestrationRunSummary, float]:
    namespace = f"{tier}-C{concurrency}"
    items = _work_items(namespace, n, run_context)
    evidence_map = _evidence_map(items, case_count)
    orchestrator = _make_orchestrator(cache, audit_log, evidence_map, backend_factory, concurrency)
    start = time.monotonic()
    summary = orchestrator.run(items, run_id=f"g4-equivalence-{namespace}")
    return summary, time.monotonic() - start


def _run_one_tier_equivalence(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    cache: ReferenceResultCache,
    audit_log: ReferenceAuditLog,
    backend_factory: Callable[[], ExecutionBackend],
    n: int,
    run_context: ReferenceRunContext,
    tier: str,
    case_count: int,
) -> EquivalenceCheckResult:
    legs = {
        concurrency: _run_one_equivalence_leg(
            cache, audit_log, backend_factory, n, run_context, tier, case_count, concurrency
        )
        for concurrency in _CROSS_TIER_CONCURRENCIES
    }
    sequential_summary, sequential_wall = legs[1]
    concurrent_summary, concurrent_wall = legs[4]
    paired_outcomes = zip(sequential_summary.outcomes, concurrent_summary.outcomes)
    mismatches = [
        seq_outcome.work_item_id
        for seq_outcome, conc_outcome in paired_outcomes
        if seq_outcome.task_result is None
        or conc_outcome.task_result is None
        or not _measurement_matches(seq_outcome.task_result, conc_outcome.task_result)
    ]
    return EquivalenceCheckResult(
        tier=tier,
        n_items=n,
        sequential_wall_seconds=sequential_wall,
        concurrent_wall_seconds=concurrent_wall,
        equivalent=not mismatches,
        mismatched_work_item_ids=tuple(mismatches),
    )


def _run_cross_tier_equivalence(
    cache: ReferenceResultCache,
    audit_log: ReferenceAuditLog,
    backend_factory: Callable[[], ExecutionBackend],
    n: int,
    run_context: ReferenceRunContext,
) -> tuple[EquivalenceCheckResult, ...]:
    return tuple(
        _run_one_tier_equivalence(
            cache, audit_log, backend_factory, n, run_context, tier, case_count
        )
        for tier, case_count in _TIER_CASE_COUNTS.items()
    )


def _run_warm_cache_check(
    cache: ReferenceResultCache,
    audit_log: ReferenceAuditLog,
    backend_factory: Callable[[], ExecutionBackend],
    n: int,
    run_context: ReferenceRunContext,
) -> WarmCacheCheckResult:
    namespace = f"MEDIAN-C{_THROUGHPUT_CONCURRENCIES[-1]}"
    items = _work_items(namespace, n, run_context)
    evidence_map = _evidence_map(items, _TIER_CASE_COUNTS["MEDIAN"])
    orchestrator = _make_orchestrator(
        cache, audit_log, evidence_map, backend_factory, max_workers=4
    )
    summary = orchestrator.run(items, run_id="g4-warm-cache")
    return WarmCacheCheckResult(
        n_items=n,
        all_cache_hits=summary.cache_hit_keys == summary.unique_cache_keys,
        fresh_execution_keys=summary.fresh_execution_keys,
    )


def _run_interruption_resumption(
    cache: ReferenceResultCache,
    audit_log: ReferenceAuditLog,
    backend_factory: Callable[[], ExecutionBackend],
    n: int,
    run_context: ReferenceRunContext,
) -> InterruptionResumptionResult:
    namespace = "INTERRUPT"
    items = _work_items(namespace, n, run_context)
    evidence_map = _evidence_map(items, _TIER_CASE_COUNTS["MEDIAN"])

    cancelled = threading.Event()
    triggered = {"done": False}

    def _on_in_flight_change(count: int) -> None:
        if count == 0 and not triggered["done"]:
            triggered["done"] = True
            cancelled.set()

    first_orchestrator = _make_orchestrator(
        cache,
        audit_log,
        evidence_map,
        backend_factory,
        max_workers=1,
        on_in_flight_change=_on_in_flight_change,
    )
    first_summary = first_orchestrator.run(
        items, run_id="g4-interrupt-1", cancellation_event=cancelled
    )

    resumed_orchestrator = _make_orchestrator(
        cache, audit_log, evidence_map, backend_factory, max_workers=_INTERRUPTION_CONCURRENCY
    )
    resumed_summary = resumed_orchestrator.run(items, run_id="g4-interrupt-2")

    return InterruptionResumptionResult(
        n_items=n,
        first_run_interrupted=first_summary.interrupted,
        first_run_accepted=first_summary.accepted_work_items,
        first_run_unstarted=first_summary.unstarted_work_items,
        resumed_run_accepted=resumed_summary.accepted_work_items,
        resumed_run_unstarted=resumed_summary.unstarted_work_items,
        fully_completed_without_gaps=(
            resumed_summary.accepted_work_items == n and resumed_summary.unstarted_work_items == 0
        ),
    )


@dataclass(frozen=True)
class _G4RunResults:
    """Bundles the four post-scaling check results purely to keep
    :func:`run_g4_benchmark`'s own local variable count small."""

    throughput_results: tuple[ThroughputSweepResult, ...]
    best_speedup: float
    equivalence_results: tuple[EquivalenceCheckResult, ...]
    warm_cache_result: WarmCacheCheckResult
    interruption_result: InterruptionResumptionResult


def _run_all_checks(
    cache: ReferenceResultCache,
    audit_log: ReferenceAuditLog,
    backend_factory: Callable[[], ExecutionBackend],
    counts: ScaledRunCounts,
    run_context: ReferenceRunContext,
) -> _G4RunResults:
    throughput_results = _run_throughput_sweep(
        cache, audit_log, backend_factory, counts.throughput_sweep_n, run_context
    )
    equivalence_results = _run_cross_tier_equivalence(
        cache, audit_log, backend_factory, counts.cross_tier_n, run_context
    )
    warm_cache_result = _run_warm_cache_check(
        cache, audit_log, backend_factory, counts.throughput_sweep_n, run_context
    )
    interruption_result = _run_interruption_resumption(
        cache, audit_log, backend_factory, counts.interruption_n, run_context
    )
    return _G4RunResults(
        throughput_results=throughput_results,
        best_speedup=_best_speedup(throughput_results),
        equivalence_results=equivalence_results,
        warm_cache_result=warm_cache_result,
        interruption_result=interruption_result,
    )


def run_g4_benchmark(
    *,
    cache_dir: Path | None = None,
    audit_path: Path | None = None,
    backend_factory: Callable[[], ExecutionBackend],
    leftover_container_check: Callable[[], tuple[str, ...]] = _check_leftover_containers,
) -> G4BenchmarkReport:
    """Execute the full frozen MEGB-03G.4 benchmark plan and return a typed report.

    Calibrates first, applies the section-3 scaling rule, then runs the
    throughput sweep, cross-tier equivalence check, warm-cache check, and
    interruption/resumption check in that order -- all against
    ``backend_factory`` (a real ``DockerPerInvocationBackend`` in normal
    use; a fake backend in ``tests/test_g4_benchmark.py``, where none of
    this touches real Docker). ``leftover_container_check`` defaults to the
    real ``docker ps`` inspection but is injectable so an offline,
    fake-backend end-to-end test never needs a real ``docker`` binary
    installed at all.
    """
    cache = ReferenceResultCache(
        cache_dir if cache_dir is not None else DEFAULT_BENCHMARK_CACHE_DIR
    )
    audit_log = ReferenceAuditLog(
        audit_path if audit_path is not None else DEFAULT_BENCHMARK_AUDIT_PATH
    )
    run_context = _run_context()

    overall_start = time.monotonic()
    calibration = _run_calibration(cache, audit_log, backend_factory)
    scaling = compute_scaling_decision(calibration)
    checks = _run_all_checks(cache, audit_log, backend_factory, scaling.scaled_counts, run_context)
    leftover_containers = leftover_container_check()
    total_wall_seconds = time.monotonic() - overall_start

    readiness = _determine_readiness(
        scaling,
        checks.equivalence_results,
        checks.warm_cache_result,
        checks.interruption_result,
        leftover_containers,
        checks.best_speedup,
        total_wall_seconds,
    )
    return G4BenchmarkReport(
        schema_version=G4_REPORT_SCHEMA_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        readiness=readiness,
        scaling=scaling,
        throughput_results=checks.throughput_results,
        best_speedup=checks.best_speedup,
        equivalence_results=checks.equivalence_results,
        warm_cache_result=checks.warm_cache_result,
        interruption_result=checks.interruption_result,
        leftover_containers=leftover_containers,
        total_wall_seconds=total_wall_seconds,
    )


def report_to_dict(report: G4BenchmarkReport) -> dict[str, object]:
    """Full-fidelity, JSON-serializable projection of a report -- every
    field the checkpoint report needs for reproducibility, nothing
    privileged (this benchmark never touches real reference-only evidence)."""

    def _default(value: object) -> object:
        if isinstance(value, ReadinessState):
            return value.value
        raise TypeError(f"object of type {type(value)!r} is not JSON serializable")

    result: dict[str, object] = json.loads(json.dumps(dataclasses.asdict(report), default=_default))
    return result


def main() -> None:
    """Manual/scheduled-workflow entry point: ``python -m src.reference.g4_benchmark``.

    Runs the full frozen plan against a real ``DockerPerInvocationBackend``
    and writes the typed report as JSON next to the benchmark's own cache/
    audit directories, per the plan's "not on every push" requirement.
    """
    from src.execution.docker_backend import (  # pylint: disable=import-outside-toplevel
        DockerPerInvocationBackend,
    )

    report = run_g4_benchmark(backend_factory=DockerPerInvocationBackend)
    output_path = Path("artifacts/reference/g4_benchmark_audit/g4_benchmark_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report_to_dict(report), indent=2, sort_keys=True)
    output_path.write_text(serialized, encoding="utf-8")
    print(f"MEGB-03G.4 readiness: {report.readiness.value}")
    print(f"Report written to {output_path}")
    if report.readiness == ReadinessState.ORCHESTRATION_BLOCKED:
        sys.exit(1)


if __name__ == "__main__":
    main()
