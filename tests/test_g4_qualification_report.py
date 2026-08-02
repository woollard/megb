"""Tests for src.reference.g4_qualification_report (MEGB-03G.4 correction,
section 6).

Offline only. Covers: construction from a synthetic G4BenchmarkReport,
the explicit field allowlist (exhaustive and safe -- no candidate code,
individual synthetic inputs/outputs, real task/case identifiers,
privileged paths, or free-form diagnostics), round-trip serialization,
self-checksum tamper detection, and the Markdown rendering.

Also covers the report-schema-v2 correction: independence of
``synthetic_workload_version``/``synthetic_workload_checksum`` from
``G4_EVALUATOR_VERSION`` and the qualification-report's own schema
version, distinctness of all five identities, content-sensitivity of the
workload checksum, and consistency of the actual committed JSON/Markdown
qualification reports.
"""

import copy
import inspect
import json
from pathlib import Path

import pytest

from src.reference.g4_benchmark import (
    CalibrationMeasurement,
    EquivalenceCheckResult,
    G4BenchmarkReport,
    InterruptionResumptionResult,
    ReadinessState,
    ScaledRunCounts,
    ScalingDecision,
    ThroughputSweepResult,
    WarmCacheCheckResult,
)
from src.reference.g4_benchmark_evaluator import G4_EVALUATOR_VERSION
from src.reference.g4_qualification_report import (
    BENCHMARK_PLAN_VERSION,
    G4_QUALIFICATION_REPORT_SCHEMA_VERSION,
    QUALIFICATION_REPORT_FIELD_NAMES,
    SYNTHETIC_WORKLOAD_CHECKSUM_ALGORITHM_VERSION,
    SYNTHETIC_WORKLOAD_VERSION,
    G4QualificationReport,
    InvalidQualificationReportError,
    build_qualification_report,
    qualification_report_from_dict,
    qualification_report_to_dict,
    render_markdown,
)
from src.reference.g4_qualification_report_cli import _synthetic_workload_checksum

_COMMITTED_JSON_PATH = Path("docs/measurement/megb-03g4-qualification-report.json")
_COMMITTED_MARKDOWN_PATH = Path("docs/measurement/megb-03g4-qualification-report.md")

_FORBIDDEN_NAME_FRAGMENTS = (
    "candidate_code",
    "candidate_source",
    "case_input",
    "case_id",
    "expected_output",
    "canonical_solution",
    "diagnostic",
    "traceback",
    "exception",
    "task_id",
)

_FORBIDDEN_CONTENT = {
    "candidate_code": "def solve(): return 'CANDIDATE-CODE-CANARY'",
    "case_input": "CASE-INPUT-CANARY",
    "task_id": "G4Bench/CANARY-TASK-ID",
    "traceback": "Traceback (most recent call last): TRACEBACK-CANARY",
}


def _benchmark_report(**overrides: object) -> G4BenchmarkReport:
    calibration = CalibrationMeasurement(sample_seconds=(0.3, 0.4, 0.5))
    scaling = ScalingDecision(
        calibration=calibration,
        unscaled_total_case_invocations=358,
        unscaled_projected_seconds=143.2,
        ceiling_seconds=3300.0,
        scale_factor=1.0,
        scaled_counts=ScaledRunCounts(throughput_sweep_n=8, cross_tier_n=4, interruption_n=6),
        scaled_total_case_invocations=358,
        scaled_projected_seconds=143.2,
        throughput_blocked=False,
    )
    throughput_results = (
        ThroughputSweepResult(concurrency=1, n_items=8, wall_seconds=10.0, accepted_work_items=8),
        ThroughputSweepResult(concurrency=2, n_items=8, wall_seconds=6.0, accepted_work_items=8),
        ThroughputSweepResult(concurrency=4, n_items=8, wall_seconds=4.0, accepted_work_items=8),
    )
    equivalence_results = tuple(
        EquivalenceCheckResult(
            tier=tier,
            n_items=4,
            sequential_wall_seconds=1.0,
            concurrent_wall_seconds=0.5,
            equivalent=True,
            mismatched_work_item_ids=(),
        )
        for tier in ("LOW", "MEDIAN", "HIGH")
    )
    warm_cache_result = WarmCacheCheckResult(n_items=8, all_cache_hits=True, fresh_execution_keys=0)
    interruption_result = InterruptionResumptionResult(
        n_items=6,
        first_run_interrupted=True,
        first_run_accepted=1,
        first_run_unstarted=5,
        resumed_run_accepted=6,
        resumed_run_unstarted=0,
        fully_completed_without_gaps=True,
    )
    fields: dict[str, object] = {
        "schema_version": "megb-03g4-throughput-report-v1",
        "generated_at": "2026-08-02T00:00:00Z",
        "readiness": ReadinessState.ORCHESTRATION_READY_FOR_MEGB_03H,
        "scaling": scaling,
        "throughput_results": throughput_results,
        "best_speedup": 2.5,
        "equivalence_results": equivalence_results,
        "warm_cache_result": warm_cache_result,
        "interruption_result": interruption_result,
        "leftover_containers": (),
        "total_wall_seconds": 66.5,
    }
    fields.update(overrides)
    return G4BenchmarkReport(**fields)  # type: ignore[arg-type]


def _qualification_report(**overrides: object) -> G4QualificationReport:
    benchmark_report = overrides.pop("benchmark_report", None) or _benchmark_report()
    kwargs: dict[str, object] = {
        "generated_at": "2026-08-02T00:00:00Z",
        "benchmark_plan_checksum": "a" * 64,
        "synthetic_workload_checksum": "b" * 64,
        "implementation_commit_sha": "c" * 40,
        "implementation_dirty": False,
        "docker_image_id": "sha256:deadbeef",
        "docker_image_provenance_checksum": "d" * 64,
        "host_platform_summary": "macOS-arm64",
        "ordering_deterministic": True,
        "isolation_all_matched": True,
    }
    kwargs.update(overrides)
    return build_qualification_report(benchmark_report, **kwargs)  # type: ignore[arg-type]


# --- Construction and derived fields --------------------------------------------


def test_build_qualification_report_derives_expected_fields() -> None:
    """Build qualification report derives expected fields."""
    report = _qualification_report()
    assert report.readiness == "ORCHESTRATION_READY_FOR_MEGB_03H"
    assert report.concurrency_levels == (1, 2, 4)
    assert report.throughput_sweep_n == 8
    assert report.cross_tier_n == 4
    assert report.interruption_n == 6
    assert report.calibration_sample_count == 3
    assert report.calibration_mean_seconds == pytest.approx(0.4)
    assert report.scale_factor == 1.0
    assert report.best_speedup == 2.5
    assert report.equivalence_all_matched is True
    assert report.equivalence_mismatch_count == 0
    assert report.cache_all_hits_on_warm_run is True
    assert report.resumption_no_gaps is True
    assert report.leftover_containers_found is False


def test_equivalence_mismatch_count_is_derived_correctly() -> None:
    """Equivalence mismatch count is derived correctly."""
    benchmark_report = _benchmark_report(
        equivalence_results=(
            EquivalenceCheckResult(
                tier="HIGH", n_items=4, sequential_wall_seconds=1.0, concurrent_wall_seconds=0.5,
                equivalent=False, mismatched_work_item_ids=("a", "b"),
            ),
        )
    )
    report = _qualification_report(benchmark_report=benchmark_report)
    assert report.equivalence_all_matched is False
    assert report.equivalence_mismatch_count == 2


def test_leftover_containers_found_reflects_the_benchmark_report() -> None:
    """Leftover containers found reflects the benchmark report."""
    benchmark_report = _benchmark_report(leftover_containers=("megb-runner-leaked",))
    report = _qualification_report(benchmark_report=benchmark_report)
    assert report.leftover_containers_found is True


# --- Field allowlist -------------------------------------------------------------


def test_field_allowlist_is_exhaustive_and_safe() -> None:
    """The allowlist contains only safe identity/version/count/boolean/
    timing fields -- nothing named after case content or candidate source."""
    for field_name in QUALIFICATION_REPORT_FIELD_NAMES:
        for fragment in _FORBIDDEN_NAME_FRAGMENTS:
            assert fragment not in field_name, f"{field_name!r} looks unsafe for this report"


def test_to_dict_keys_are_exactly_the_allowlist() -> None:
    """To dict keys are exactly the allowlist."""
    report = _qualification_report()
    assert set(qualification_report_to_dict(report).keys()) == QUALIFICATION_REPORT_FIELD_NAMES


def test_report_never_contains_forbidden_content_in_values() -> None:
    """Even if a caller tried to smuggle forbidden content through one of
    this report's own free-text-shaped fields (host_platform_summary), the
    *other* forbidden categories can never appear -- no field exists to
    carry candidate code, case content, or real task identifiers at all."""
    report = _qualification_report(host_platform_summary="macOS-arm64 CANARY-HOST")
    serialized = str(qualification_report_to_dict(report))
    for label, canary in _FORBIDDEN_CONTENT.items():
        assert canary not in serialized, f"{label} leaked into the qualification report"


# --- Round trip and self-checksum ------------------------------------------------


def test_round_trip_preserves_all_fields() -> None:
    """Round trip preserves all fields."""
    report = _qualification_report()
    restored = qualification_report_from_dict(qualification_report_to_dict(report))
    assert restored == report


def test_tampered_checksum_is_rejected() -> None:
    """Tampered checksum is rejected."""
    report = _qualification_report()
    data = qualification_report_to_dict(report)
    data["best_speedup"] = 999.0  # tamper with content, keep the old checksum
    with pytest.raises(InvalidQualificationReportError):
        qualification_report_from_dict(data)


def test_tampered_report_checksum_field_itself_is_rejected() -> None:
    """Tampered report checksum field itself is rejected."""
    report = _qualification_report()
    data = qualification_report_to_dict(report)
    data["report_checksum"] = "0" * 64
    with pytest.raises(InvalidQualificationReportError):
        qualification_report_from_dict(data)


def test_report_is_frozen_and_immutable() -> None:
    """Report is frozen and immutable."""
    report = _qualification_report()
    with pytest.raises(AttributeError):
        report.best_speedup = 0.0  # type: ignore[misc]


def test_unknown_readiness_value_is_rejected() -> None:
    """Unknown readiness value is rejected."""
    report = _qualification_report()
    data = copy.deepcopy(qualification_report_to_dict(report))
    data["readiness"] = "NOT_A_REAL_READINESS_STATE"
    del data["report_checksum"]
    with pytest.raises(InvalidQualificationReportError):
        qualification_report_from_dict({**data, "report_checksum": ""})


# --- Markdown rendering -----------------------------------------------------------


def test_render_markdown_contains_key_fields() -> None:
    """Render markdown contains key fields."""
    report = _qualification_report()
    markdown = render_markdown(report)
    assert "ORCHESTRATION_READY_FOR_MEGB_03H" in markdown
    assert report.report_checksum in markdown
    assert "2.500" in markdown or "2.5" in markdown


def test_render_markdown_never_contains_forbidden_content() -> None:
    """Render markdown never contains forbidden content."""
    report = _qualification_report()
    markdown = render_markdown(report)
    for label, canary in _FORBIDDEN_CONTENT.items():
        assert canary not in markdown, f"{label} leaked into the Markdown rendering"


# --- Report-schema v2 correction: independent identities --------------------------


def test_synthetic_workload_version_does_not_equal_evaluator_version() -> None:
    """Synthetic workload version does not equal evaluator version."""
    assert SYNTHETIC_WORKLOAD_VERSION != G4_EVALUATOR_VERSION


def test_report_synthetic_workload_version_is_always_the_fixed_constant() -> None:
    """A built report's synthetic_workload_version is always the module's
    own fixed constant -- never the benchmark evaluator's version, and
    never derived from the benchmark report's own schema_version."""
    report = _qualification_report(
        benchmark_report=_benchmark_report(schema_version="some-other-benchmark-schema-v99")
    )
    assert report.synthetic_workload_version == SYNTHETIC_WORKLOAD_VERSION
    assert report.synthetic_workload_version != G4_EVALUATOR_VERSION
    assert report.synthetic_workload_version != "some-other-benchmark-schema-v99"


def test_all_five_identities_are_pairwise_distinct() -> None:
    """Benchmark-plan, synthetic-workload, checksum-algorithm, evaluator,
    and qualification-report-schema identities are pairwise distinct."""
    identities = {
        "benchmark_plan_version": BENCHMARK_PLAN_VERSION,
        "synthetic_workload_version": SYNTHETIC_WORKLOAD_VERSION,
        "synthetic_workload_checksum_algorithm_version": (
            SYNTHETIC_WORKLOAD_CHECKSUM_ALGORITHM_VERSION
        ),
        "evaluator_version": G4_EVALUATOR_VERSION,
        "report_schema_version": G4_QUALIFICATION_REPORT_SCHEMA_VERSION,
    }
    values = list(identities.values())
    assert len(values) == len(set(values)), f"identities collide: {identities}"


def test_workload_checksum_function_has_no_evaluator_or_schema_parameter() -> None:
    """_synthetic_workload_checksum only accepts workload-content
    parameters -- it structurally cannot depend on evaluator version,
    report-schema version, execution-protocol version, benchmark-plan
    version, code revision, timestamps, or measured outcomes, because
    none of those is even an accepted input."""
    params = set(inspect.signature(_synthetic_workload_checksum).parameters)
    assert params == {"entry_point", "canonical_solution", "tier_case_counts"}


def test_workload_checksum_is_deterministic_for_the_same_content() -> None:
    """Workload checksum is deterministic for the same content."""
    assert _synthetic_workload_checksum() == _synthetic_workload_checksum()


def test_workload_checksum_changes_when_any_canonical_item_changes() -> None:
    """Changing any canonical workload item changes the workload checksum."""
    base = _synthetic_workload_checksum()
    assert _synthetic_workload_checksum(entry_point="different_entry_point") != base
    assert _synthetic_workload_checksum(canonical_solution="def f(): pass\n") != base
    assert _synthetic_workload_checksum(tier_case_counts={"LOW": 999}) != base


def test_report_synthetic_workload_checksum_is_a_pure_passthrough() -> None:
    """The report's synthetic_workload_checksum is exactly whatever value
    was supplied -- unaffected by the benchmark report's own schema
    version, i.e. by a change in report-schema-adjacent metadata."""
    checksum = _synthetic_workload_checksum()
    report_a = _qualification_report(
        synthetic_workload_checksum=checksum,
        benchmark_report=_benchmark_report(schema_version="megb-03g4-throughput-report-v1"),
    )
    report_b = _qualification_report(
        synthetic_workload_checksum=checksum,
        benchmark_report=_benchmark_report(schema_version="megb-03g4-throughput-report-v2"),
    )
    assert report_a.synthetic_workload_checksum == checksum
    assert report_b.synthetic_workload_checksum == checksum


# --- Consistency of the actual committed qualification report ---------------------


def test_committed_json_report_verifies_against_its_own_self_checksum() -> None:
    """The committed JSON qualification report round-trips through
    qualification_report_from_dict without raising -- i.e. it verifies
    against its own self-checksum (the same check every reader gets)."""
    data = json.loads(_COMMITTED_JSON_PATH.read_text(encoding="utf-8"))
    report = qualification_report_from_dict(data)
    assert report.report_checksum == data["report_checksum"]


def test_committed_json_and_markdown_reports_describe_the_same_frozen_run() -> None:
    """The committed JSON and Markdown qualification reports describe the
    same frozen run -- same readiness, schema version, workload identity,
    and self-checksum appear in both."""
    data = json.loads(_COMMITTED_JSON_PATH.read_text(encoding="utf-8"))
    markdown = _COMMITTED_MARKDOWN_PATH.read_text(encoding="utf-8")
    for field in (
        "readiness",
        "schema_version",
        "report_checksum",
        "synthetic_workload_version",
        "synthetic_workload_checksum",
        "synthetic_workload_checksum_algorithm_version",
        "benchmark_plan_version",
    ):
        assert str(data[field]) in markdown, f"{field}={data[field]!r} missing from Markdown"
