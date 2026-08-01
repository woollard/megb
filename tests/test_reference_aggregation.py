"""Tests for src.reference.aggregation (MEGB-03G.1: Aggregation and Profile
Enforcement).

Covers the "Approved MEGB-03G Compatibility Amendment"'s sections 1 and 2:
the corrected ``aggregate_reference_results(task_results, candidate_set_manifest)``
interface (exact-164 enforcement, canonical ordering, run-context derivation
and equality, delegation of per-field invariants to
``ReferenceBenchmarkResult`` itself) and explicit profile separation (only
the full reference-only evaluator/execution profile is accepted; reduced-
development and mixed-profile input is rejected). Also proves requirement 8:
an attached full-suite compatibility diagnostic never contributes to
``q_ref``/``q_ref_task``.

Uses synthetic fixtures only -- no privileged artifacts, no Docker.
"""

import hashlib

import pytest

from src.evaluators.schema import FailureCategory
from src.reference.aggregation import ReferenceAggregationError, aggregate_reference_results
from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EVALUATOR_VERSION_REDUCED_DEV,
    EXECUTION_PROFILE_ID_FULL,
    EXECUTION_PROFILE_ID_REDUCED_DEV,
)
from src.reference.result_schema import (
    REFERENCE_VALIDATION_CANDIDATE_SET_ALGORITHM_VERSION,
    REFERENCE_VALIDATION_CANDIDATE_SET_MANIFEST_SCHEMA_VERSION,
    REQUIRED_TASK_COUNT,
    CandidateSetEntry,
    FullSuiteDiagnostic,
    InvalidReferenceResultError,
    MeasurementStatus,
    ReferenceOutcome,
    ReferenceRunContext,
    ReferenceTaskResult,
    ReferenceValidationCandidateSetManifest,
)

_SHA_TASK_MANIFEST = "d" * 64
_SHA_SELECTION_PROVENANCE = "e" * 64
_SHA_CONFIG = "b" * 64
_ORACLE_VERSION = "oracle-v1"


def _candidate_identity(task_id: str) -> tuple[str, str]:
    candidate_id = f"cand-{task_id}"
    candidate_sha256 = hashlib.sha256(f"candidate-source-for-{task_id}".encode()).hexdigest()
    return candidate_id, candidate_sha256


def _reference_case_checksum(task_id: str) -> str:
    return hashlib.sha256(f"reference-cases-for-{task_id}".encode()).hexdigest()


def _full_run_context(**overrides: str) -> ReferenceRunContext:
    fields = {
        "experiment_run_id": "exp-1",
        "optimization_run_id": "opt-1",
        "optimization_config_sha256": _SHA_CONFIG,
        "portfolio_frozen_at": "2026-07-01T00:00:00Z",
        "portfolio_selection_rule": "best_of_run",
        "evaluator_version": EVALUATOR_VERSION_FULL,
        "dataset_version": "humaneval-plus-v0.1.10",
        "partition_version": "partition-v1",
        "execution_profile_id": EXECUTION_PROFILE_ID_FULL,
    }
    fields.update(overrides)
    return ReferenceRunContext(**fields)


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


def _task_result(
    task_id: str,
    context: ReferenceRunContext,
    **overrides: object,
) -> ReferenceTaskResult:
    candidate_id, candidate_sha256 = _candidate_identity(task_id)
    fields: dict[str, object] = {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "candidate_sha256": candidate_sha256,
        "context": context,
        "status": MeasurementStatus.VALID,
        "q_ref_task": 1.0,
        "reference_case_total": 5,
        "reference_case_pass_count": 5,
        "first_failure_category": FailureCategory.NONE,
        "oracle_version": _ORACLE_VERSION,
        "reference_case_checksum": _reference_case_checksum(task_id),
        "evaluated_at": "2026-07-01T00:00:01Z",
        "duration_seconds": 0.25,
    }
    fields.update(overrides)
    return ReferenceTaskResult(**fields)  # type: ignore[arg-type]


def _valid_task_results(
    context: ReferenceRunContext | None = None,
    count: int = REQUIRED_TASK_COUNT,
) -> tuple[ReferenceTaskResult, ...]:
    ctx = context or _full_run_context()
    results = [_task_result(f"HumanEval/{i}", ctx) for i in range(count)]
    # Sorted by task_id (string order, not numeric) to match
    # ReferenceValidationCandidateSetManifest's own canonical entry order --
    # "HumanEval/10" sorts before "HumanEval/2" lexically, so plain i=0..163
    # iteration order does *not* match the manifest's sorted entries.
    return tuple(sorted(results, key=lambda result: result.task_id))


def _manifest_and_results(
    context: ReferenceRunContext | None = None,
) -> tuple[ReferenceValidationCandidateSetManifest, tuple[ReferenceTaskResult, ...]]:
    manifest = _candidate_set_manifest()
    results = _valid_task_results(context)
    return manifest, results


def _replace_result(
    results: tuple[ReferenceTaskResult, ...],
    task_id: str,
    context: ReferenceRunContext,
    **overrides: object,
) -> tuple[ReferenceTaskResult, ...]:
    """Replace the result for ``task_id`` in place, by identity rather than
    position -- task_id string order ("HumanEval/10" < "HumanEval/2") does
    not match numeric order, so index-based mutation silently targets the
    wrong task and corrupts the fixture instead of the field under test."""
    index = next(i for i, result in enumerate(results) if result.task_id == task_id)
    replacement = _task_result(task_id, context, **overrides)
    return results[:index] + (replacement,) + results[index + 1 :]


# --- Happy path ---------------------------------------------------------


def test_aggregate_valid_164_task_results() -> None:
    """A valid 164-entry manifest and matching task results aggregate cleanly."""
    manifest, results = _manifest_and_results()
    benchmark = aggregate_reference_results(results, manifest)
    assert benchmark.expected_task_count == REQUIRED_TASK_COUNT
    assert benchmark.evaluated_task_count == REQUIRED_TASK_COUNT
    assert benchmark.q_ref == 1.0
    assert benchmark.candidate_set_manifest is manifest


def test_aggregate_derives_run_context_from_task_results() -> None:
    """The benchmark's run_context is derived from the task results, never
    accepted as a separate, independently suppliable argument."""
    context = _full_run_context(experiment_run_id="exp-derived")
    manifest, results = _manifest_and_results(context)
    benchmark = aggregate_reference_results(results, manifest)
    assert benchmark.run_context == context


def test_aggregate_repeated_candidate_sha256_across_different_tasks_is_valid() -> None:
    """Regression guard for the MEGB-03E/F Approved Correction (v2):
    candidate_sha256 is never required to be globally unique across tasks."""
    context = _full_run_context()
    shared_sha = hashlib.sha256(b"shared-helper-snippet").hexdigest()
    entries = []
    results = []
    for i in range(REQUIRED_TASK_COUNT):
        task_id = f"HumanEval/{i}"
        candidate_id = f"cand-{task_id}"
        entries.append(
            CandidateSetEntry(
                task_id=task_id, candidate_id=candidate_id, candidate_sha256=shared_sha
            )
        )
        results.append(
            _task_result(task_id, context, candidate_id=candidate_id, candidate_sha256=shared_sha)
        )
    manifest = _candidate_set_manifest(
        entries=tuple(sorted(entries, key=lambda entry: entry.task_id))
    )
    ordered_results = tuple(sorted(results, key=lambda result: result.task_id))
    benchmark = aggregate_reference_results(ordered_results, manifest)
    assert benchmark.q_ref == 1.0


def test_full_suite_diagnostic_never_affects_q_ref() -> None:
    """Proves amendment requirement 8: an attached, internally-valid
    full-suite diagnostic cannot replace, modify, or contribute to primary
    q_ref_task/Q_ref."""
    context = _full_run_context()
    manifest = _candidate_set_manifest()
    diagnostic = FullSuiteDiagnostic(
        outcome=ReferenceOutcome.PASS_BASE_FAIL_PLUS,
        base_total=1,
        base_pass_count=1,
        plus_total=5,
        plus_pass_count=3,
    )
    without_diagnostic = aggregate_reference_results(_valid_task_results(context), manifest)

    with_diagnostic_results = list(_valid_task_results(context))
    with_diagnostic_results[0] = _task_result(
        "HumanEval/0", context, full_suite_diagnostic=diagnostic
    )
    with_diagnostic = aggregate_reference_results(tuple(with_diagnostic_results), manifest)

    assert with_diagnostic.q_ref == without_diagnostic.q_ref == 1.0
    assert with_diagnostic.primary_pass_count == without_diagnostic.primary_pass_count
    assert with_diagnostic.full_suite_outcome_counts[ReferenceOutcome.PASS_BASE_FAIL_PLUS] == 1


# --- Count / ordering / identity rejection -------------------------------


def test_rejects_fewer_than_164_task_results() -> None:
    """163 task results (one short) is rejected, not silently aggregated
    over a smaller denominator."""
    manifest, results = _manifest_and_results()
    with pytest.raises(ReferenceAggregationError, match="requires exactly 164"):
        aggregate_reference_results(results[:-1], manifest)


def test_rejects_more_than_164_task_results() -> None:
    """165 task results (one extra) is rejected outright."""
    context = _full_run_context()
    manifest, results = _manifest_and_results(context)
    extra = _task_result("HumanEval/9999", context)
    with pytest.raises(ReferenceAggregationError, match="requires exactly 164"):
        aggregate_reference_results(results + (extra,), manifest)


def test_rejects_duplicate_task_id() -> None:
    """Two results for the same task_id are rejected even at exactly 164 total."""
    context = _full_run_context()
    manifest, results = _manifest_and_results(context)
    tampered = results[:-1] + (results[0],)
    with pytest.raises(ReferenceAggregationError, match="duplicate task_id"):
        aggregate_reference_results(tampered, manifest)


def test_rejects_substituted_task_id() -> None:
    """A task id absent from the manifest is rejected even when the total
    count is still exactly 164."""
    context = _full_run_context()
    manifest, results = _manifest_and_results(context)
    substituted = _task_result("HumanEval/9999", context)
    tampered = results[:-1] + (substituted,)
    with pytest.raises(ReferenceAggregationError, match="does not match candidate_set_manifest"):
        aggregate_reference_results(tampered, manifest)


def test_rejects_reordered_task_results() -> None:
    """Task results out of the manifest's canonical task_id order are
    rejected rather than silently re-sorted."""
    context = _full_run_context()
    manifest, results = _manifest_and_results(context)
    reordered = (results[1], results[0]) + results[2:]
    with pytest.raises(ReferenceAggregationError, match="canonical task_id order"):
        aggregate_reference_results(reordered, manifest)


def test_rejects_candidate_identity_mismatch_against_manifest() -> None:
    """A task result whose candidate_sha256 disagrees with its manifest
    entry is rejected by the underlying ReferenceBenchmarkResult invariant."""
    context = _full_run_context()
    manifest, results = _manifest_and_results(context)
    tampered_result = _task_result(
        "HumanEval/0",
        context,
        candidate_sha256=hashlib.sha256(b"wrong-candidate").hexdigest(),
    )
    tampered = (tampered_result,) + results[1:]
    with pytest.raises(InvalidReferenceResultError, match="candidate identity"):
        aggregate_reference_results(tampered, manifest)


# --- Run-context / version consistency -----------------------------------


def test_rejects_run_context_mismatch_across_results() -> None:
    """Every task result must share exactly one run_context; one task
    evaluated under a different context is rejected."""
    context_a = _full_run_context()
    context_b = _full_run_context(experiment_run_id="exp-2")
    manifest, results = _manifest_and_results(context_a)
    tampered = _replace_result(results, "HumanEval/163", context_b)
    with pytest.raises(ReferenceAggregationError, match="different run_context"):
        aggregate_reference_results(tampered, manifest)


def test_rejects_inconsistent_oracle_version() -> None:
    """oracle_version must be identical across every task result."""
    context = _full_run_context()
    manifest, results = _manifest_and_results(context)
    tampered = _replace_result(results, "HumanEval/163", context, oracle_version="oracle-v2")
    with pytest.raises(ReferenceAggregationError, match="inconsistent oracle_version"):
        aggregate_reference_results(tampered, manifest)


# --- Profile enforcement --------------------------------------------------


def test_rejects_reduced_development_profile() -> None:
    """A uniformly reduced-development-profile result set is rejected from
    the primary 164-task aggregate."""
    context = _full_run_context(
        execution_profile_id=EXECUTION_PROFILE_ID_REDUCED_DEV,
        evaluator_version=EVALUATOR_VERSION_REDUCED_DEV,
    )
    manifest, results = _manifest_and_results(context)
    with pytest.raises(ReferenceAggregationError, match="full reference-only execution profile"):
        aggregate_reference_results(results, manifest)


def test_rejects_mixed_execution_profile_across_results() -> None:
    """A single reduced-development-profile result mixed into an otherwise
    full-profile set is rejected via the run-context-equality check."""
    full_context = _full_run_context()
    reduced_context = _full_run_context(
        execution_profile_id=EXECUTION_PROFILE_ID_REDUCED_DEV,
        evaluator_version=EVALUATOR_VERSION_REDUCED_DEV,
    )
    manifest, results = _manifest_and_results(full_context)
    tampered = _replace_result(results, "HumanEval/163", reduced_context)
    with pytest.raises(ReferenceAggregationError, match="different run_context"):
        aggregate_reference_results(tampered, manifest)


def test_rejects_evaluator_version_mismatch_with_full_profile_id() -> None:
    """execution_profile_id alone looks correct; evaluator_version must
    independently match the full profile's identifier too."""
    context = _full_run_context(evaluator_version="some-other-evaluator-v1")
    manifest, results = _manifest_and_results(context)
    with pytest.raises(
        ReferenceAggregationError, match="full reference-only evaluator version"
    ):
        aggregate_reference_results(results, manifest)


# --- Type defense ----------------------------------------------------------


def test_rejects_wrong_type_for_candidate_set_manifest() -> None:
    """A non-manifest object passed as candidate_set_manifest is rejected
    defensively, independent of static type checking."""
    _, results = _manifest_and_results()
    with pytest.raises(
        ReferenceAggregationError, match="ReferenceValidationCandidateSetManifest"
    ):
        aggregate_reference_results(results, object())  # type: ignore[arg-type]


def test_rejects_wrong_type_in_task_results() -> None:
    """A non-ReferenceTaskResult object among task_results is rejected
    defensively, independent of static type checking."""
    manifest, results = _manifest_and_results()
    tampered = results[:-1] + (object(),)
    with pytest.raises(ReferenceAggregationError, match="must be a ReferenceTaskResult"):
        aggregate_reference_results(tampered, manifest)  # type: ignore[arg-type]


# --- Aggregate-field derivation ---------------------------------------------


def test_evaluated_at_is_the_latest_task_timestamp() -> None:
    """The aggregate's evaluated_at is the latest of its task results'
    evaluated_at timestamps."""
    context = _full_run_context()
    manifest, results = _manifest_and_results(context)
    tampered = _replace_result(
        results, "HumanEval/163", context, evaluated_at="2026-07-01T00:00:05Z"
    )
    benchmark = aggregate_reference_results(tampered, manifest)
    assert benchmark.evaluated_at == "2026-07-01T00:00:05Z"


def test_duration_seconds_is_the_sum_of_task_durations() -> None:
    """The aggregate's duration_seconds is the sum of every task result's
    own duration_seconds."""
    manifest, results = _manifest_and_results()
    benchmark = aggregate_reference_results(results, manifest)
    assert benchmark.duration_seconds == pytest.approx(0.25 * REQUIRED_TASK_COUNT)
