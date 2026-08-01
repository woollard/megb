"""Tests for src.reference.result_schema (MEGB-03E).

Organized to map directly onto the ticket's "Required Tests" list:
task-result construction/schema validation, all-pass scoring,
pass-base/fail-plus diagnostic scoring, candidate execution-failure
scoring, invalid-measurement propagation, denominator preservation,
serialization round trips (see test_result_redaction.py),
configuration/version validation, and redaction (see
test_result_redaction.py).
"""

import pytest

from src.evaluators.schema import FailureCategory
from src.reference.result_schema import (
    REQUIRED_TASK_COUNT,
    FullSuiteDiagnostic,
    InvalidReferenceResultError,
    MeasurementStatus,
    ReferenceBenchmarkResult,
    ReferenceEvaluationContext,
    ReferenceOutcome,
    ReferenceTaskResult,
)

_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_CASE = "c" * 64
_ORACLE_VERSION = "oracle-v1"

_NON_VALID_STATUSES = [
    MeasurementStatus.INVALID_ORACLE,
    MeasurementStatus.INVALID_INFRASTRUCTURE,
    MeasurementStatus.INVALID_PROTOCOL,
]


def _context(**overrides: str) -> ReferenceEvaluationContext:
    fields = {
        "experiment_run_id": "exp-1",
        "optimization_run_id": "opt-1",
        "candidate_id": "cand-1",
        "candidate_sha256": _SHA_A,
        "candidate_frozen_at": "2026-07-01T00:00:00Z",
        "candidate_selection_rule": "best_of_run",
        "optimization_config_sha256": _SHA_B,
        "evaluator_version": "reference-evaluator-v1",
        "dataset_version": "humaneval-plus-v0.1.10",
        "partition_version": "partition-v1",
        "execution_profile_id": "docker-megb02-v1",
    }
    fields.update(overrides)
    return ReferenceEvaluationContext(**fields)


def _task_result(task_id: str = "HumanEval/0", **overrides: object) -> ReferenceTaskResult:
    fields: dict[str, object] = {
        "task_id": task_id,
        "context": _context(),
        "status": MeasurementStatus.VALID,
        "q_ref_task": 1.0,
        "reference_case_total": 5,
        "reference_case_pass_count": 5,
        "first_failure_category": FailureCategory.NONE,
        "oracle_version": _ORACLE_VERSION,
        "reference_case_checksum": _SHA_CASE,
        "evaluated_at": "2026-07-01T00:00:01Z",
        "duration_seconds": 0.25,
    }
    fields.update(overrides)
    return ReferenceTaskResult(**fields)  # type: ignore[arg-type]


def _valid_results(
    count: int = REQUIRED_TASK_COUNT, context: ReferenceEvaluationContext | None = None
) -> tuple[ReferenceTaskResult, ...]:
    ctx = context or _context()
    return tuple(
        ReferenceTaskResult(
            task_id=f"HumanEval/{i}",
            context=ctx,
            status=MeasurementStatus.VALID,
            q_ref_task=1.0,
            reference_case_total=5,
            reference_case_pass_count=5,
            first_failure_category=FailureCategory.NONE,
            oracle_version=_ORACLE_VERSION,
            reference_case_checksum=_SHA_CASE,
            evaluated_at="2026-07-01T00:00:01Z",
            duration_seconds=0.25,
        )
        for i in range(count)
    )


def _benchmark(
    task_results: tuple[ReferenceTaskResult, ...], **overrides: object
) -> ReferenceBenchmarkResult:
    fields: dict[str, object] = {
        "candidate_context": _context(),
        "task_results": task_results,
        "task_manifest_checksum": "d" * 64,
        "oracle_version": _ORACLE_VERSION,
        "evaluated_at": "2026-07-01T00:00:02Z",
        "duration_seconds": 12.5,
    }
    fields.update(overrides)
    return ReferenceBenchmarkResult(**fields)  # type: ignore[arg-type]


# --- Task-result construction and schema validation -------------------------


def test_valid_context_constructs() -> None:
    """A context with well-formed fields constructs without error."""
    _context()


@pytest.mark.parametrize(
    "field_name",
    [
        "experiment_run_id",
        "optimization_run_id",
        "candidate_id",
        "candidate_frozen_at",
        "candidate_selection_rule",
        "evaluator_version",
        "dataset_version",
        "partition_version",
        "execution_profile_id",
    ],
)
def test_context_empty_string_field_rejected(field_name: str) -> None:
    """Every identity/provenance string field must be nonempty."""
    with pytest.raises(InvalidReferenceResultError):
        _context(**{field_name: ""})


def test_context_non_hex_candidate_sha256_rejected() -> None:
    """candidate_sha256 must be a hex sha256 digest."""
    with pytest.raises(InvalidReferenceResultError):
        _context(candidate_sha256="not-a-sha256")


def test_context_is_frozen() -> None:
    """ReferenceEvaluationContext instances must be immutable."""
    context = _context()
    with pytest.raises(AttributeError):
        context.candidate_id = "other"  # type: ignore[misc]


def test_task_result_constructs_with_well_formed_fields() -> None:
    """A well-formed task result constructs without error."""
    result = _task_result()
    assert result.task_id == "HumanEval/0"


def test_empty_task_id_rejected() -> None:
    """task_id must be nonempty."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(task_id="")


def test_empty_oracle_version_rejected() -> None:
    """oracle_version must be nonempty."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(oracle_version="")


def test_non_hex_reference_case_checksum_rejected() -> None:
    """reference_case_checksum must be a hex sha256 digest."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(reference_case_checksum="not-a-checksum")


def test_negative_duration_rejected() -> None:
    """duration_seconds must be non-negative."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(duration_seconds=-0.1)


def test_reference_case_pass_count_exceeding_total_rejected() -> None:
    """reference_case_pass_count can never exceed reference_case_total."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(reference_case_total=3, reference_case_pass_count=4)


def test_execution_failure_counts_unknown_category_key_rejected() -> None:
    """execution_failure_counts keys must be real FailureCategory values."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(execution_failure_counts={"NOT_A_CATEGORY": 1})


def test_execution_failure_counts_negative_value_rejected() -> None:
    """execution_failure_counts values must be non-negative."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(execution_failure_counts={FailureCategory.TIMEOUT.value: -1})


def test_execution_failure_counts_accepts_valid_categories() -> None:
    """A well-formed execution_failure_counts mapping is accepted."""
    result = _task_result(
        q_ref_task=0.0,
        reference_case_pass_count=3,
        first_failure_category=FailureCategory.TIMEOUT,
        execution_failure_counts={FailureCategory.TIMEOUT.value: 2},
    )
    assert result.execution_failure_counts[FailureCategory.TIMEOUT.value] == 2


def test_task_result_is_frozen() -> None:
    """ReferenceTaskResult instances must be immutable."""
    result = _task_result()
    with pytest.raises(AttributeError):
        result.q_ref_task = 0.0  # type: ignore[misc]


# --- All-pass scoring ---------------------------------------------------


def test_all_cases_pass_yields_q_ref_task_one() -> None:
    """q_ref_task=1.0 requires every required reference-only case to pass."""
    result = _task_result(
        q_ref_task=1.0,
        reference_case_total=5,
        reference_case_pass_count=5,
        first_failure_category=FailureCategory.NONE,
    )
    assert result.q_ref_task == 1.0


def test_q_ref_task_one_with_incomplete_case_pass_count_rejected() -> None:
    """q_ref_task cannot be 1.0 unless all required cases actually passed."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(
            q_ref_task=1.0,
            reference_case_total=5,
            reference_case_pass_count=4,
            first_failure_category=FailureCategory.NONE,
        )


def test_pass_with_nonnone_category_rejected() -> None:
    """A pass (q_ref_task=1.0) must not carry a nonzero failure category."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(q_ref_task=1.0, first_failure_category=FailureCategory.WRONG_OUTPUT)


def test_full_valid_benchmark_computes_q_ref_one() -> None:
    """A benchmark with all 164 tasks VALID and passing computes q_ref=1.0."""
    benchmark = _benchmark(_valid_results())
    assert benchmark.q_ref == 1.0
    assert benchmark.valid_task_count == REQUIRED_TASK_COUNT
    assert benchmark.primary_pass_count == REQUIRED_TASK_COUNT
    assert benchmark.missing_task_count == 0
    assert benchmark.aggregate_status == MeasurementStatus.VALID


# --- Pass-base/fail-plus diagnostic scoring ------------------------------


def test_full_suite_diagnostic_pass_base_fail_plus() -> None:
    """A candidate passing base but failing plus is PASS_BASE_FAIL_PLUS, never gaming-proof."""
    diagnostic = FullSuiteDiagnostic(
        outcome=ReferenceOutcome.PASS_BASE_FAIL_PLUS,
        base_total=1,
        base_pass_count=1,
        plus_total=10,
        plus_pass_count=7,
    )
    result = _task_result(full_suite_diagnostic=diagnostic)
    assert result.full_suite_diagnostic is not None
    assert result.full_suite_diagnostic.outcome == ReferenceOutcome.PASS_BASE_FAIL_PLUS


def test_full_suite_diagnostic_outcome_inconsistent_with_counts_rejected() -> None:
    """The outcome label must agree with the base/plus pass counts it accompanies."""
    with pytest.raises(InvalidReferenceResultError):
        FullSuiteDiagnostic(
            outcome=ReferenceOutcome.PASS_BASE_PASS_PLUS,
            base_total=1,
            base_pass_count=1,
            plus_total=10,
            plus_pass_count=7,
        )


def test_full_suite_diagnostic_fail_base_pass_plus_is_a_representable_anomaly() -> None:
    """FAIL_BASE_PASS_PLUS is representable — it must be surfaced, never suppressed."""
    diagnostic = FullSuiteDiagnostic(
        outcome=ReferenceOutcome.FAIL_BASE_PASS_PLUS,
        base_total=1,
        base_pass_count=0,
        plus_total=10,
        plus_pass_count=10,
    )
    assert diagnostic.outcome == ReferenceOutcome.FAIL_BASE_PASS_PLUS


def test_full_suite_diagnostic_pass_count_exceeding_total_rejected() -> None:
    """base_pass_count/plus_pass_count can never exceed their totals."""
    with pytest.raises(InvalidReferenceResultError):
        FullSuiteDiagnostic(
            outcome=ReferenceOutcome.PASS_BASE_PASS_PLUS,
            base_total=1,
            base_pass_count=2,
            plus_total=10,
            plus_pass_count=10,
        )


def test_full_suite_diagnostic_invalid_measurement_allows_zero_totals() -> None:
    """INVALID_MEASUREMENT does not require nonzero totals (the comparison itself failed)."""
    diagnostic = FullSuiteDiagnostic(
        outcome=ReferenceOutcome.INVALID_MEASUREMENT,
        base_total=0,
        base_pass_count=0,
        plus_total=0,
        plus_pass_count=0,
    )
    assert diagnostic.outcome == ReferenceOutcome.INVALID_MEASUREMENT


def test_full_suite_diagnostic_rejected_when_task_status_not_valid() -> None:
    """full_suite_diagnostic must be None whenever status is not VALID."""
    diagnostic = FullSuiteDiagnostic(
        outcome=ReferenceOutcome.PASS_BASE_PASS_PLUS,
        base_total=1,
        base_pass_count=1,
        plus_total=10,
        plus_pass_count=10,
    )
    with pytest.raises(InvalidReferenceResultError):
        _task_result(
            status=MeasurementStatus.INVALID_ORACLE,
            q_ref_task=None,
            first_failure_category=FailureCategory.INFRASTRUCTURE_ERROR,
            full_suite_diagnostic=diagnostic,
        )


def test_benchmark_full_suite_outcome_counts_aggregate_across_tasks() -> None:
    """full_suite_outcome_counts tallies diagnostics across every task result."""
    ctx = _context()
    diagnostic = FullSuiteDiagnostic(
        outcome=ReferenceOutcome.PASS_BASE_FAIL_PLUS,
        base_total=1,
        base_pass_count=1,
        plus_total=10,
        plus_pass_count=5,
    )
    results = list(_valid_results(REQUIRED_TASK_COUNT - 1, context=ctx))
    results.append(
        ReferenceTaskResult(
            task_id=f"HumanEval/{REQUIRED_TASK_COUNT - 1}",
            context=ctx,
            status=MeasurementStatus.VALID,
            q_ref_task=1.0,
            reference_case_total=5,
            reference_case_pass_count=5,
            first_failure_category=FailureCategory.NONE,
            oracle_version=_ORACLE_VERSION,
            reference_case_checksum=_SHA_CASE,
            evaluated_at="2026-07-01T00:00:01Z",
            duration_seconds=0.25,
            full_suite_diagnostic=diagnostic,
        )
    )
    benchmark = _benchmark(tuple(results), candidate_context=ctx)
    assert benchmark.full_suite_outcome_counts[ReferenceOutcome.PASS_BASE_FAIL_PLUS] == 1
    assert benchmark.full_suite_outcome_counts[ReferenceOutcome.PASS_BASE_PASS_PLUS] == 0


# --- Candidate execution-failure scoring ---------------------------------


def test_fail_with_candidate_category_is_valid() -> None:
    """q_ref_task=0.0 with a candidate-attributable category is valid."""
    result = _task_result(
        q_ref_task=0.0,
        reference_case_pass_count=2,
        first_failure_category=FailureCategory.WRONG_OUTPUT,
    )
    assert result.q_ref_task == 0.0


def test_fail_with_none_category_rejected() -> None:
    """A fail (q_ref_task=0.0) must name a real failure category."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(
            q_ref_task=0.0, reference_case_pass_count=2, first_failure_category=FailureCategory.NONE
        )


def test_fail_with_measurement_only_category_rejected() -> None:
    """A VALID fail must not be attributed to a measurement-apparatus-only category."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(
            q_ref_task=0.0,
            reference_case_pass_count=2,
            first_failure_category=FailureCategory.INFRASTRUCTURE_ERROR,
        )


def test_q_ref_task_zero_with_all_cases_passing_rejected() -> None:
    """q_ref_task cannot be 0.0 if every required case actually passed."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(
            q_ref_task=0.0,
            reference_case_total=5,
            reference_case_pass_count=5,
            first_failure_category=FailureCategory.WRONG_OUTPUT,
        )


@pytest.mark.parametrize("fractional", [0.5, 0.99, -0.0001, 1.5])
def test_fractional_q_ref_task_rejected(fractional: float) -> None:
    """q_ref_task must never be a fraction when status is VALID (requirement 7)."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(
            q_ref_task=fractional,
            reference_case_pass_count=2,
            first_failure_category=FailureCategory.WRONG_OUTPUT,
        )


def test_bool_q_ref_task_rejected_even_though_true_equals_one() -> None:
    """bool must be rejected even though True == 1 in Python."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(q_ref_task=True, first_failure_category=FailureCategory.NONE)


def test_case_level_fraction_never_substitutes_for_binary_score() -> None:
    """4/5 cases passing is diagnostic only — q_ref_task is still binary 0.0, not 0.8."""
    result = _task_result(
        q_ref_task=0.0,
        reference_case_total=5,
        reference_case_pass_count=4,
        first_failure_category=FailureCategory.WRONG_OUTPUT,
    )
    assert result.q_ref_task == 0.0
    assert result.reference_case_pass_count == 4


def test_mixed_pass_fail_benchmark_computes_fraction() -> None:
    """q_ref is the mean of q_ref_task across all 164 VALID results."""
    ctx = _context()
    results = list(_valid_results(REQUIRED_TASK_COUNT - 1, context=ctx))
    results.append(
        ReferenceTaskResult(
            task_id=f"HumanEval/{REQUIRED_TASK_COUNT - 1}",
            context=ctx,
            status=MeasurementStatus.VALID,
            q_ref_task=0.0,
            reference_case_total=5,
            reference_case_pass_count=2,
            first_failure_category=FailureCategory.WRONG_OUTPUT,
            oracle_version=_ORACLE_VERSION,
            reference_case_checksum=_SHA_CASE,
            evaluated_at="2026-07-01T00:00:02Z",
            duration_seconds=0.25,
        )
    )
    benchmark = _benchmark(tuple(results), candidate_context=ctx)
    assert benchmark.q_ref == (REQUIRED_TASK_COUNT - 1) / REQUIRED_TASK_COUNT


# --- Invalid-measurement propagation --------------------------------------


def test_none_q_ref_task_rejected_when_status_valid() -> None:
    """A VALID measurement must always produce a concrete q_ref_task."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(q_ref_task=None, first_failure_category=FailureCategory.NONE)


@pytest.mark.parametrize("status", _NON_VALID_STATUSES)
def test_non_valid_status_requires_none_q_ref_task(status: MeasurementStatus) -> None:
    """A non-VALID measurement must never carry a q_ref_task value."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(
            status=status,
            q_ref_task=1.0,
            first_failure_category=FailureCategory.INFRASTRUCTURE_ERROR,
        )


@pytest.mark.parametrize("status", _NON_VALID_STATUSES)
def test_non_valid_status_with_measurement_category_is_valid(status: MeasurementStatus) -> None:
    """A non-VALID measurement paired with a measurement-apparatus category is valid."""
    result = _task_result(
        status=status,
        q_ref_task=None,
        first_failure_category=FailureCategory.INFRASTRUCTURE_ERROR,
    )
    assert result.q_ref_task is None


@pytest.mark.parametrize("status", _NON_VALID_STATUSES)
def test_non_valid_status_with_none_category_rejected(status: MeasurementStatus) -> None:
    """A non-VALID (non-INCOMPLETE) measurement must name why it's invalid."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(status=status, q_ref_task=None, first_failure_category=FailureCategory.NONE)


@pytest.mark.parametrize("status", _NON_VALID_STATUSES)
def test_non_valid_status_with_candidate_only_category_rejected(status: MeasurementStatus) -> None:
    """A measurement-apparatus failure must not be blamed on the candidate."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(
            status=status, q_ref_task=None, first_failure_category=FailureCategory.WRONG_OUTPUT
        )


def test_incomplete_status_requires_none_category() -> None:
    """INCOMPLETE with NONE category is valid: nothing was categorized yet."""
    result = _task_result(
        status=MeasurementStatus.INCOMPLETE,
        q_ref_task=None,
        first_failure_category=FailureCategory.NONE,
    )
    assert result.status == MeasurementStatus.INCOMPLETE


def test_incomplete_status_with_nonnone_category_rejected() -> None:
    """INCOMPLETE must not carry a failure category it never determined."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(
            status=MeasurementStatus.INCOMPLETE,
            q_ref_task=None,
            first_failure_category=FailureCategory.INFRASTRUCTURE_ERROR,
        )


def test_incomplete_task_among_full_set_yields_none_q_ref() -> None:
    """One INCOMPLETE task among an otherwise-full set blocks q_ref."""
    ctx = _context()
    results = list(_valid_results(REQUIRED_TASK_COUNT - 1, context=ctx))
    results.append(
        ReferenceTaskResult(
            task_id=f"HumanEval/{REQUIRED_TASK_COUNT - 1}",
            context=ctx,
            status=MeasurementStatus.INCOMPLETE,
            q_ref_task=None,
            reference_case_total=0,
            reference_case_pass_count=0,
            first_failure_category=FailureCategory.NONE,
            oracle_version=_ORACLE_VERSION,
            reference_case_checksum=_SHA_CASE,
            evaluated_at="2026-07-01T00:00:02Z",
            duration_seconds=0.0,
        )
    )
    benchmark = _benchmark(tuple(results), candidate_context=ctx)
    assert benchmark.q_ref is None
    assert benchmark.valid_task_count == REQUIRED_TASK_COUNT - 1
    assert benchmark.incomplete_task_count == 1
    assert benchmark.status_counts[MeasurementStatus.INCOMPLETE] == 1
    assert benchmark.aggregate_status == MeasurementStatus.INCOMPLETE


def test_invalid_oracle_task_sets_aggregate_status() -> None:
    """A single INVALID_ORACLE task result propagates to the aggregate status."""
    ctx = _context()
    results = list(_valid_results(REQUIRED_TASK_COUNT - 1, context=ctx))
    results.append(
        ReferenceTaskResult(
            task_id=f"HumanEval/{REQUIRED_TASK_COUNT - 1}",
            context=ctx,
            status=MeasurementStatus.INVALID_ORACLE,
            q_ref_task=None,
            reference_case_total=0,
            reference_case_pass_count=0,
            first_failure_category=FailureCategory.INFRASTRUCTURE_ERROR,
            oracle_version=_ORACLE_VERSION,
            reference_case_checksum=_SHA_CASE,
            evaluated_at="2026-07-01T00:00:02Z",
            duration_seconds=0.0,
        )
    )
    benchmark = _benchmark(tuple(results), candidate_context=ctx)
    assert benchmark.aggregate_status == MeasurementStatus.INVALID_ORACLE
    assert benchmark.invalid_task_count == 1
    assert benchmark.q_ref is None


# --- Denominator preservation ---------------------------------------------


def test_missing_tasks_yields_none_q_ref_never_a_smaller_denominator() -> None:
    """q_ref must never be computed over fewer than expected_task_count tasks."""
    benchmark = _benchmark(_valid_results(REQUIRED_TASK_COUNT - 1))
    assert benchmark.q_ref is None
    assert benchmark.missing_task_count == 1
    assert benchmark.aggregate_status == MeasurementStatus.INCOMPLETE


def test_wrong_expected_task_count_rejected() -> None:
    """expected_task_count must always be exactly REQUIRED_TASK_COUNT."""
    with pytest.raises(InvalidReferenceResultError):
        _benchmark(_valid_results(10), expected_task_count=10)


def test_duplicate_task_id_rejected() -> None:
    """task_results must not contain duplicate task_id entries."""
    dup = _task_result(task_id="HumanEval/0")
    with pytest.raises(InvalidReferenceResultError):
        _benchmark((dup, dup))


def test_too_many_task_results_rejected() -> None:
    """task_results must not exceed expected_task_count entries."""
    with pytest.raises(InvalidReferenceResultError):
        _benchmark(_valid_results(REQUIRED_TASK_COUNT + 1))


def test_benchmark_result_is_frozen() -> None:
    """ReferenceBenchmarkResult instances must be immutable."""
    benchmark = _benchmark(_valid_results(0))
    with pytest.raises(AttributeError):
        benchmark.evaluated_at = "later"  # type: ignore[misc]


# --- Configuration/version validation --------------------------------------


def test_mismatched_candidate_identity_rejected() -> None:
    """Every task_result must belong to the same candidate/run as candidate_context."""
    other_candidate_result = _task_result(context=_context(candidate_id="different-candidate"))
    with pytest.raises(InvalidReferenceResultError):
        _benchmark((other_candidate_result,))


def test_mismatched_evaluator_version_rejected() -> None:
    """A task result evaluated under a different evaluator_version is rejected."""
    other_version_result = _task_result(
        context=_context(evaluator_version="reference-evaluator-v2")
    )
    with pytest.raises(InvalidReferenceResultError):
        _benchmark((other_version_result,))


def test_mismatched_oracle_version_on_task_result_rejected() -> None:
    """Every task_result.oracle_version must match the benchmark's oracle_version."""
    other_oracle_result = _task_result(oracle_version="oracle-v2")
    with pytest.raises(InvalidReferenceResultError):
        _benchmark((other_oracle_result,))


def test_non_hex_task_manifest_checksum_rejected() -> None:
    """task_manifest_checksum must be a hex sha256 digest."""
    with pytest.raises(InvalidReferenceResultError):
        _benchmark(_valid_results(0), task_manifest_checksum="not-a-checksum")


def test_negative_benchmark_duration_rejected() -> None:
    """duration_seconds must be non-negative at the benchmark level too."""
    with pytest.raises(InvalidReferenceResultError):
        _benchmark(_valid_results(0), duration_seconds=-1.0)
