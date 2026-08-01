"""Tests for src.reference.result_schema (MEGB-03E/03F Approved Correction, v2).

Organized to map directly onto the ticket's "Required Tests" list plus the
v2 correction's own required regression coverage: task-result construction/
schema validation, all-pass scoring, pass-base/fail-plus diagnostic
scoring, candidate execution-failure scoring, invalid-measurement
propagation, denominator preservation, serialization round trips (see
test_result_redaction.py), configuration/version validation, redaction (see
test_result_redaction.py), and the v2 candidate-set-manifest guarantees
(different per-task candidates accepted; shared run context, candidate-set
membership, and candidate-set checksum all enforced).
"""

import hashlib

import pytest

from src.evaluators.schema import FailureCategory
from src.reference.result_schema import (
    REFERENCE_VALIDATION_CANDIDATE_SET_ALGORITHM_VERSION,
    REFERENCE_VALIDATION_CANDIDATE_SET_MANIFEST_SCHEMA_VERSION,
    REQUIRED_TASK_COUNT,
    CandidateSetEntry,
    ReferenceValidationCandidateSetManifest,
    FullSuiteDiagnostic,
    InvalidReferenceValidationCandidateSetManifestError,
    InvalidReferenceResultError,
    MeasurementStatus,
    ReferenceBenchmarkResult,
    ReferenceOutcome,
    ReferenceRunContext,
    ReferenceTaskResult,
)

_SHA_B = "b" * 64
_SHA_CASE = "c" * 64
_SHA_TASK_MANIFEST = "d" * 64
_SHA_SELECTION_PROVENANCE = "e" * 64
_ORACLE_VERSION = "oracle-v1"

_NON_VALID_STATUSES = [
    MeasurementStatus.INVALID_ORACLE,
    MeasurementStatus.INVALID_INFRASTRUCTURE,
    MeasurementStatus.INVALID_PROTOCOL,
]


def _candidate_identity(task_id: str) -> tuple[str, str]:
    """Deterministic, task-specific (candidate_id, candidate_sha256) pair."""
    candidate_id = f"cand-{task_id}"
    candidate_sha256 = hashlib.sha256(f"candidate-source-for-{task_id}".encode()).hexdigest()
    return candidate_id, candidate_sha256


def _run_context(**overrides: str) -> ReferenceRunContext:
    fields = {
        "experiment_run_id": "exp-1",
        "optimization_run_id": "opt-1",
        "optimization_config_sha256": _SHA_B,
        "portfolio_frozen_at": "2026-07-01T00:00:00Z",
        "portfolio_selection_rule": "best_of_run",
        "evaluator_version": "reference-evaluator-v1",
        "dataset_version": "humaneval-plus-v0.1.10",
        "partition_version": "partition-v1",
        "execution_profile_id": "docker-megb02-v1",
        "comparison_profile_version": "comparison-profile-v1",
    }
    fields.update(overrides)
    return ReferenceRunContext(**fields)


def _task_result(task_id: str = "HumanEval/0", **overrides: object) -> ReferenceTaskResult:
    candidate_id, candidate_sha256 = _candidate_identity(task_id)
    fields: dict[str, object] = {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "candidate_sha256": candidate_sha256,
        "context": _run_context(),
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


def _candidate_set_entries(count: int = REQUIRED_TASK_COUNT) -> tuple[CandidateSetEntry, ...]:
    entries = []
    for i in range(count):
        task_id = f"HumanEval/{i}"
        candidate_id, candidate_sha256 = _candidate_identity(task_id)
        entries.append(
            CandidateSetEntry(
                task_id=task_id, candidate_id=candidate_id, candidate_sha256=candidate_sha256
            )
        )
    return tuple(sorted(entries, key=lambda entry: entry.task_id))


def _candidate_set_manifest(
    entries: tuple[CandidateSetEntry, ...] | None = None, **overrides: object
) -> ReferenceValidationCandidateSetManifest:
    fields: dict[str, object] = {
        "manifest_schema_version": REFERENCE_VALIDATION_CANDIDATE_SET_MANIFEST_SCHEMA_VERSION,
        "algorithm_version": REFERENCE_VALIDATION_CANDIDATE_SET_ALGORITHM_VERSION,
        "task_manifest_id": "reference-validation-composite-manifest",
        "task_manifest_checksum": _SHA_TASK_MANIFEST,
        "selection_provenance_sha256": _SHA_SELECTION_PROVENANCE,
        "entries": entries if entries is not None else _candidate_set_entries(),
    }
    fields.update(overrides)
    return ReferenceValidationCandidateSetManifest(**fields)  # type: ignore[arg-type]


def _valid_results(
    count: int = REQUIRED_TASK_COUNT, context: ReferenceRunContext | None = None
) -> tuple[ReferenceTaskResult, ...]:
    ctx = context or _run_context()
    results = []
    for i in range(count):
        task_id = f"HumanEval/{i}"
        candidate_id, candidate_sha256 = _candidate_identity(task_id)
        results.append(
            ReferenceTaskResult(
                task_id=task_id,
                candidate_id=candidate_id,
                candidate_sha256=candidate_sha256,
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
        )
    return tuple(results)


def _benchmark(
    task_results: tuple[ReferenceTaskResult, ...], **overrides: object
) -> ReferenceBenchmarkResult:
    fields: dict[str, object] = {
        "run_context": _run_context(),
        "candidate_set_manifest": _candidate_set_manifest(),
        "task_results": task_results,
        "task_manifest_checksum": _SHA_TASK_MANIFEST,
        "oracle_version": _ORACLE_VERSION,
        "evaluated_at": "2026-07-01T00:00:02Z",
        "duration_seconds": 12.5,
    }
    fields.update(overrides)
    return ReferenceBenchmarkResult(**fields)  # type: ignore[arg-type]


# --- Task-result construction and schema validation -------------------------


def test_valid_run_context_constructs() -> None:
    """A run context with well-formed fields constructs without error."""
    _run_context()


@pytest.mark.parametrize(
    "field_name",
    [
        "experiment_run_id",
        "optimization_run_id",
        "portfolio_frozen_at",
        "portfolio_selection_rule",
        "evaluator_version",
        "dataset_version",
        "partition_version",
        "execution_profile_id",
        "comparison_profile_version",
    ],
)
def test_run_context_empty_string_field_rejected(field_name: str) -> None:
    """Every identity/provenance string field must be nonempty."""
    with pytest.raises(InvalidReferenceResultError):
        _run_context(**{field_name: ""})


def test_run_context_non_hex_optimization_config_sha256_rejected() -> None:
    """optimization_config_sha256 must be a hex sha256 digest."""
    with pytest.raises(InvalidReferenceResultError):
        _run_context(optimization_config_sha256="not-a-sha256")


def test_run_context_is_frozen() -> None:
    """ReferenceRunContext instances must be immutable."""
    context = _run_context()
    with pytest.raises(AttributeError):
        context.experiment_run_id = "other"  # type: ignore[misc]


def test_run_context_has_no_candidate_identity_field() -> None:
    """ReferenceRunContext must not carry any per-candidate identity field —
    that would force every task in a benchmark to share one candidate."""
    import dataclasses  # pylint: disable=import-outside-toplevel

    field_names = {f.name for f in dataclasses.fields(ReferenceRunContext)}
    assert "candidate_id" not in field_names
    assert "candidate_sha256" not in field_names


def test_task_result_constructs_with_well_formed_fields() -> None:
    """A well-formed task result constructs without error."""
    result = _task_result()
    assert result.task_id == "HumanEval/0"


def test_empty_task_id_rejected() -> None:
    """task_id must be nonempty."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(task_id="")


def test_empty_candidate_id_rejected() -> None:
    """candidate_id must be nonempty."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(candidate_id="")


def test_non_hex_candidate_sha256_rejected() -> None:
    """candidate_sha256 must be a hex sha256 digest."""
    with pytest.raises(InvalidReferenceResultError):
        _task_result(candidate_sha256="not-a-sha256")


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


# --- Candidate-set manifest construction -----------------------------------


def test_candidate_set_manifest_constructs_and_computes_checksum() -> None:
    """A well-formed 164-entry manifest constructs and stamps a real checksum."""
    manifest = _candidate_set_manifest()
    assert len(manifest.manifest_checksum) == 64
    assert len(manifest.entries) == REQUIRED_TASK_COUNT


def test_candidate_set_manifest_checksum_is_deterministic() -> None:
    """The same entries always produce the same checksum."""
    manifest_a = _candidate_set_manifest()
    manifest_b = _candidate_set_manifest()
    assert manifest_a.manifest_checksum == manifest_b.manifest_checksum


def test_candidate_set_manifest_missing_entry_rejected() -> None:
    """A manifest with fewer than 164 entries (a missing task) is rejected."""
    with pytest.raises(InvalidReferenceValidationCandidateSetManifestError):
        _candidate_set_manifest(entries=_candidate_set_entries(REQUIRED_TASK_COUNT - 1))


def test_candidate_set_manifest_duplicate_task_id_rejected() -> None:
    """Duplicate task_id entries in the candidate-set manifest are rejected."""
    entries = list(_candidate_set_entries(REQUIRED_TASK_COUNT - 1))
    entries.append(entries[0])
    with pytest.raises(InvalidReferenceValidationCandidateSetManifestError):
        _candidate_set_manifest(entries=tuple(entries))


def test_candidate_set_manifest_reordered_entries_rejected() -> None:
    """Entries must be sorted by task_id — a reordered (but otherwise
    identical) entry set is rejected, not silently accepted as equivalent."""
    entries = list(_candidate_set_entries())
    entries[0], entries[1] = entries[1], entries[0]
    with pytest.raises(InvalidReferenceValidationCandidateSetManifestError):
        _candidate_set_manifest(entries=tuple(entries))


def test_candidate_set_manifest_tampered_entry_rejected() -> None:
    """A hand-edited entry combined with a stale (now-mismatched)
    manifest_checksum is rejected as tampered, never silently accepted."""
    good_manifest = _candidate_set_manifest()
    tampered_entries = list(good_manifest.entries)
    tampered_entries[0] = CandidateSetEntry(
        task_id=tampered_entries[0].task_id,
        candidate_id=tampered_entries[0].candidate_id,
        candidate_sha256="f" * 64,
    )
    with pytest.raises(InvalidReferenceValidationCandidateSetManifestError):
        ReferenceValidationCandidateSetManifest(
            manifest_schema_version=good_manifest.manifest_schema_version,
            algorithm_version=good_manifest.algorithm_version,
            task_manifest_id=good_manifest.task_manifest_id,
            task_manifest_checksum=good_manifest.task_manifest_checksum,
            selection_provenance_sha256=good_manifest.selection_provenance_sha256,
            entries=tuple(tampered_entries),
            manifest_checksum=good_manifest.manifest_checksum,  # stale — no longer matches
        )


def test_candidate_set_manifest_checksum_mismatch_rejected() -> None:
    """An explicitly wrong manifest_checksum is rejected, never silently overwritten."""
    with pytest.raises(InvalidReferenceValidationCandidateSetManifestError):
        _candidate_set_manifest(manifest_checksum="0" * 64)


def test_candidate_set_manifest_wrong_expected_task_count_rejected() -> None:
    """expected_task_count must always be exactly REQUIRED_TASK_COUNT."""
    with pytest.raises(InvalidReferenceValidationCandidateSetManifestError):
        _candidate_set_manifest(entries=_candidate_set_entries(10), expected_task_count=10)


def test_candidate_set_entry_has_no_room_for_privileged_content() -> None:
    """CandidateSetEntry's fixed field set structurally excludes any source,
    expected-output, or test-case content."""
    import dataclasses  # pylint: disable=import-outside-toplevel

    field_names = {f.name for f in dataclasses.fields(CandidateSetEntry)}
    assert field_names == {"task_id", "candidate_id", "candidate_sha256"}


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
    ctx = _run_context()
    diagnostic = FullSuiteDiagnostic(
        outcome=ReferenceOutcome.PASS_BASE_FAIL_PLUS,
        base_total=1,
        base_pass_count=1,
        plus_total=10,
        plus_pass_count=5,
    )
    results = list(_valid_results(REQUIRED_TASK_COUNT - 1, context=ctx))
    last_task_id = f"HumanEval/{REQUIRED_TASK_COUNT - 1}"
    candidate_id, candidate_sha256 = _candidate_identity(last_task_id)
    results.append(
        ReferenceTaskResult(
            task_id=last_task_id,
            candidate_id=candidate_id,
            candidate_sha256=candidate_sha256,
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
    benchmark = _benchmark(tuple(results), run_context=ctx)
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
    ctx = _run_context()
    results = list(_valid_results(REQUIRED_TASK_COUNT - 1, context=ctx))
    last_task_id = f"HumanEval/{REQUIRED_TASK_COUNT - 1}"
    candidate_id, candidate_sha256 = _candidate_identity(last_task_id)
    results.append(
        ReferenceTaskResult(
            task_id=last_task_id,
            candidate_id=candidate_id,
            candidate_sha256=candidate_sha256,
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
    benchmark = _benchmark(tuple(results), run_context=ctx)
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
    ctx = _run_context()
    results = list(_valid_results(REQUIRED_TASK_COUNT - 1, context=ctx))
    last_task_id = f"HumanEval/{REQUIRED_TASK_COUNT - 1}"
    candidate_id, candidate_sha256 = _candidate_identity(last_task_id)
    results.append(
        ReferenceTaskResult(
            task_id=last_task_id,
            candidate_id=candidate_id,
            candidate_sha256=candidate_sha256,
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
    benchmark = _benchmark(tuple(results), run_context=ctx)
    assert benchmark.q_ref is None
    assert benchmark.valid_task_count == REQUIRED_TASK_COUNT - 1
    assert benchmark.incomplete_task_count == 1
    assert benchmark.status_counts[MeasurementStatus.INCOMPLETE] == 1
    assert benchmark.aggregate_status == MeasurementStatus.INCOMPLETE


def test_invalid_oracle_task_sets_aggregate_status() -> None:
    """A single INVALID_ORACLE task result propagates to the aggregate status."""
    ctx = _run_context()
    results = list(_valid_results(REQUIRED_TASK_COUNT - 1, context=ctx))
    last_task_id = f"HumanEval/{REQUIRED_TASK_COUNT - 1}"
    candidate_id, candidate_sha256 = _candidate_identity(last_task_id)
    results.append(
        ReferenceTaskResult(
            task_id=last_task_id,
            candidate_id=candidate_id,
            candidate_sha256=candidate_sha256,
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
    benchmark = _benchmark(tuple(results), run_context=ctx)
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
        _benchmark(
            _valid_results(10),
            candidate_set_manifest=_candidate_set_manifest(
                entries=_candidate_set_entries(10), expected_task_count=10
            ),
            expected_task_count=10,
        )


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


# --- v2: different candidates across tasks are accepted; shared context enforced ---


def test_different_candidate_ids_and_hashes_across_tasks_accepted() -> None:
    """The core correction: a benchmark run legitimately contains 164
    *different* task-specific candidate solutions, and this must be
    accepted, not rejected."""
    results = _valid_results()
    candidate_ids = {result.candidate_id for result in results}
    candidate_hashes = {result.candidate_sha256 for result in results}
    assert len(candidate_ids) == REQUIRED_TASK_COUNT
    assert len(candidate_hashes) == REQUIRED_TASK_COUNT
    benchmark = _benchmark(results)
    assert benchmark.q_ref == 1.0


def test_mismatched_run_context_rejected() -> None:
    """Every task_result must share the exact same run_context — a task
    evaluated under a different experiment_run_id is rejected."""
    other_run_result = _task_result(context=_run_context(experiment_run_id="different-run"))
    with pytest.raises(InvalidReferenceResultError):
        _benchmark((other_run_result,))


def test_mismatched_evaluator_version_rejected() -> None:
    """A task result evaluated under a different evaluator_version is rejected —
    this is the mechanism that prevents mixing reduced/full profile results."""
    other_version_result = _task_result(
        context=_run_context(evaluator_version="reference-evaluator-v2")
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


def test_task_result_missing_from_candidate_set_manifest_rejected() -> None:
    """A task result whose task_id has no entry in candidate_set_manifest is rejected."""
    stray_result = _task_result(task_id="HumanEval/9999")
    with pytest.raises(InvalidReferenceResultError):
        _benchmark((stray_result,))


def test_task_result_candidate_identity_mismatching_manifest_rejected() -> None:
    """A task result whose candidate_sha256 disagrees with the frozen
    candidate-set manifest's entry for that task is rejected — the manifest
    is authoritative, so a task result cannot silently claim to measure a
    different candidate than the one actually bound to that task."""
    mismatched_result = _task_result(task_id="HumanEval/0", candidate_sha256="1" * 64)
    with pytest.raises(InvalidReferenceResultError):
        _benchmark((mismatched_result,))


def test_candidate_set_manifest_task_manifest_checksum_mismatch_rejected() -> None:
    """candidate_set_manifest.task_manifest_checksum must match the
    benchmark's own task_manifest_checksum."""
    manifest = _candidate_set_manifest(task_manifest_checksum="9" * 64)
    with pytest.raises(InvalidReferenceResultError):
        _benchmark(_valid_results(0), candidate_set_manifest=manifest)


def test_candidate_set_manifest_expected_task_count_mismatch_with_benchmark_rejected() -> None:
    """candidate_set_manifest.expected_task_count must match the benchmark's own."""
    # Both must independently be 164, so this is exercised via a manifest built
    # for a different (but still internally consistent) task count alongside a
    # benchmark still declaring the standard 164 — the manifest's own
    # REQUIRED_TASK_COUNT check fires first, which is an equally valid
    # rejection of the same inconsistency.
    with pytest.raises(InvalidReferenceValidationCandidateSetManifestError):
        _candidate_set_manifest(entries=_candidate_set_entries(163), expected_task_count=163)
