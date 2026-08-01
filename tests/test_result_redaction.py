"""Tests for src.reference.result_redaction (MEGB-03E).

Covers the ticket's "serialization round trips" and "public-result
redaction and feedback-leakage" required-test categories.
"""

# This file's minimal-task-result fixture necessarily mirrors
# test_result_schema.py's own fixture helper (both build a well-formed
# ReferenceTaskResult from the same required fields); introducing a shared
# conftest fixture for eight lines isn't warranted in this narrowly scoped
# subtask.
# pylint: disable=duplicate-code

from src.evaluators.schema import FailureCategory
from src.reference.result_redaction import (
    benchmark_result_from_dict,
    benchmark_result_to_dict,
    context_from_dict,
    context_to_dict,
    full_suite_diagnostic_from_dict,
    full_suite_diagnostic_to_dict,
    redact_benchmark_result,
    redact_task_result,
    task_result_from_dict,
    task_result_to_dict,
)
from src.reference.result_schema import (
    FullSuiteDiagnostic,
    MeasurementStatus,
    ReferenceBenchmarkResult,
    ReferenceEvaluationContext,
    ReferenceOutcome,
    ReferenceTaskResult,
)

_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_CASE = "c" * 64
_SHA_MANIFEST = "d" * 64
_ORACLE_VERSION = "oracle-v1"


def _context() -> ReferenceEvaluationContext:
    return ReferenceEvaluationContext(
        experiment_run_id="exp-1",
        optimization_run_id="opt-1",
        candidate_id="cand-1",
        candidate_sha256=_SHA_A,
        candidate_frozen_at="2026-07-01T00:00:00Z",
        candidate_selection_rule="best_of_run",
        optimization_config_sha256=_SHA_B,
        evaluator_version="reference-evaluator-v1",
        dataset_version="humaneval-plus-v0.1.10",
        partition_version="partition-v1",
        execution_profile_id="docker-megb02-v1",
    )


def _task_result_with_diagnostics() -> ReferenceTaskResult:
    return ReferenceTaskResult(
        task_id="HumanEval/39",
        context=_context(),
        status=MeasurementStatus.VALID,
        q_ref_task=0.0,
        reference_case_total=12,
        reference_case_pass_count=9,
        first_failure_category=FailureCategory.WRONG_OUTPUT,
        oracle_version=_ORACLE_VERSION,
        reference_case_checksum=_SHA_CASE,
        evaluated_at="2026-07-01T00:00:01Z",
        duration_seconds=0.42,
        execution_failure_counts={FailureCategory.WRONG_OUTPUT.value: 3},
        full_suite_diagnostic=FullSuiteDiagnostic(
            outcome=ReferenceOutcome.PASS_BASE_FAIL_PLUS,
            base_total=1,
            base_pass_count=1,
            plus_total=10,
            plus_pass_count=6,
        ),
        diagnostics={
            "expected_output": "this must never be redacted-exposed",
            "canonical_solution": "def prime_fib(n): ...",
            "raw_stderr": "Traceback ...",
        },
    )


def _minimal_pass_task_result() -> ReferenceTaskResult:
    return ReferenceTaskResult(
        task_id="HumanEval/0",
        context=_context(),
        status=MeasurementStatus.VALID,
        q_ref_task=1.0,
        reference_case_total=5,
        reference_case_pass_count=5,
        first_failure_category=FailureCategory.NONE,
        oracle_version=_ORACLE_VERSION,
        reference_case_checksum=_SHA_CASE,
        evaluated_at="2026-07-01T00:00:01Z",
        duration_seconds=0.1,
    )


def test_context_round_trip_preserves_all_fields() -> None:
    """context_from_dict(context_to_dict(x)) == x."""
    context = _context()
    assert context_from_dict(context_to_dict(context)) == context


def test_full_suite_diagnostic_round_trip() -> None:
    """full_suite_diagnostic_from_dict(full_suite_diagnostic_to_dict(x)) == x."""
    diagnostic = FullSuiteDiagnostic(
        outcome=ReferenceOutcome.PASS_BASE_FAIL_PLUS,
        base_total=1,
        base_pass_count=1,
        plus_total=10,
        plus_pass_count=6,
    )
    assert full_suite_diagnostic_from_dict(full_suite_diagnostic_to_dict(diagnostic)) == diagnostic


def test_task_result_round_trip_preserves_diagnostics() -> None:
    """Privileged serialization round-trips diagnostics content exactly."""
    result = _task_result_with_diagnostics()
    restored = task_result_from_dict(task_result_to_dict(result))
    assert restored == result
    assert restored.diagnostics["expected_output"] == "this must never be redacted-exposed"


def test_task_result_round_trip_with_none_full_suite_diagnostic() -> None:
    """A None full_suite_diagnostic round-trips as None, not a placeholder."""
    result = _minimal_pass_task_result()
    restored = task_result_from_dict(task_result_to_dict(result))
    assert restored.full_suite_diagnostic is None


def test_benchmark_result_round_trip_preserves_task_results() -> None:
    """Privileged benchmark serialization round-trips every nested task result."""
    result = _task_result_with_diagnostics()
    benchmark = ReferenceBenchmarkResult(
        candidate_context=_context(),
        task_results=(result,),
        task_manifest_checksum=_SHA_MANIFEST,
        oracle_version=_ORACLE_VERSION,
        evaluated_at="2026-07-01T00:00:02Z",
        duration_seconds=1.5,
    )
    restored = benchmark_result_from_dict(benchmark_result_to_dict(benchmark))
    assert restored == benchmark


def test_redact_task_result_default_excludes_diagnostics_entirely() -> None:
    """The redacted view never includes the diagnostics mapping or its contents."""
    redacted = redact_task_result(_task_result_with_diagnostics())
    assert "diagnostics" not in redacted
    assert "expected_output" not in redacted
    assert "canonical_solution" not in redacted
    assert "raw_stderr" not in redacted


def test_redact_task_result_default_excludes_reference_case_counts() -> None:
    """The unapproved reference-test counts (requirement 13) are excluded by default."""
    redacted = redact_task_result(_task_result_with_diagnostics())
    assert "reference_case_total" not in redacted
    assert "reference_case_pass_count" not in redacted


def test_redact_task_result_default_excludes_full_context() -> None:
    """The redacted view never includes the full evaluation context."""
    redacted = redact_task_result(_task_result_with_diagnostics())
    assert "context" not in redacted
    assert "candidate_sha256" not in redacted


def test_redact_task_result_includes_task_level_classification_fields() -> None:
    """The redacted view includes task-level classifications and safe aggregate counts."""
    redacted = redact_task_result(_task_result_with_diagnostics())
    assert redacted["task_id"] == "HumanEval/39"
    assert redacted["status"] == "VALID"
    assert redacted["q_ref_task"] == 0.0
    assert redacted["first_failure_category"] == "WRONG_OUTPUT"
    assert redacted["full_suite_diagnostic"]["outcome"] == "PASS_BASE_FAIL_PLUS"
    assert redacted["execution_failure_counts"][FailureCategory.WRONG_OUTPUT.value] == 3


def test_redact_task_result_opt_in_exposes_reference_case_counts() -> None:
    """include_reference_case_counts=True exposes only the totals, nothing else."""
    redacted = redact_task_result(
        _task_result_with_diagnostics(), include_reference_case_counts=True
    )
    assert redacted["reference_case_total"] == 12
    assert redacted["reference_case_pass_count"] == 9
    assert "expected_output" not in redacted
    assert "canonical_solution" not in redacted
    assert "raw_stderr" not in redacted


def test_redact_benchmark_result_excludes_candidate_sha256_and_diagnostics() -> None:
    """The redacted benchmark view never exposes candidate_sha256 or diagnostics."""
    result = _task_result_with_diagnostics()
    benchmark = ReferenceBenchmarkResult(
        candidate_context=_context(),
        task_results=(result,),
        task_manifest_checksum=_SHA_MANIFEST,
        oracle_version=_ORACLE_VERSION,
        evaluated_at="2026-07-01T00:00:02Z",
        duration_seconds=1.5,
    )
    redacted = redact_benchmark_result(benchmark)
    assert "candidate_sha256" not in redacted
    assert redacted["candidate_id"] == "cand-1"
    assert redacted["q_ref"] is None
    assert redacted["evaluated_task_count"] == 1
    assert redacted["valid_task_count"] == 1
    assert redacted["missing_task_count"] == 163
    assert redacted["task_manifest_checksum"] == _SHA_MANIFEST
    for task_redaction in redacted["task_results"]:
        assert "diagnostics" not in task_redaction
        assert "expected_output" not in task_redaction
        assert "reference_case_total" not in task_redaction
        assert "reference_case_pass_count" not in task_redaction


def test_redact_benchmark_result_status_counts_are_json_safe_string_keys() -> None:
    """status_counts and full_suite_outcome_counts keys must be plain strings."""
    result = _task_result_with_diagnostics()
    benchmark = ReferenceBenchmarkResult(
        candidate_context=_context(),
        task_results=(result,),
        task_manifest_checksum=_SHA_MANIFEST,
        oracle_version=_ORACLE_VERSION,
        evaluated_at="2026-07-01T00:00:02Z",
        duration_seconds=1.5,
    )
    redacted = redact_benchmark_result(benchmark)
    assert redacted["status_counts"]["VALID"] == 1
    assert redacted["status_counts"]["INCOMPLETE"] == 0
    assert redacted["full_suite_outcome_counts"]["PASS_BASE_FAIL_PLUS"] == 1
    assert redacted["aggregate_status"] == "INCOMPLETE"


def test_redact_benchmark_result_opt_in_propagates_to_nested_task_results() -> None:
    """include_reference_case_counts propagates down to every nested task redaction."""
    result = _task_result_with_diagnostics()
    benchmark = ReferenceBenchmarkResult(
        candidate_context=_context(),
        task_results=(result,),
        task_manifest_checksum=_SHA_MANIFEST,
        oracle_version=_ORACLE_VERSION,
        evaluated_at="2026-07-01T00:00:02Z",
        duration_seconds=1.5,
    )
    redacted = redact_benchmark_result(benchmark, include_reference_case_counts=True)
    assert redacted["task_results"][0]["reference_case_total"] == 12
    assert redacted["task_results"][0]["reference_case_pass_count"] == 9
