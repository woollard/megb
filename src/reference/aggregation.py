"""MEGB-03G.1: benchmark-level aggregation for the primary 164-task
reference-validation portfolio.

Implements the corrected interface from the ticket's "Approved MEGB-03G
Compatibility Amendment" (section 1): ``aggregate_reference_results`` takes
the task results and the frozen :class:`ReferenceValidationCandidateSetManifest`
only — it never accepts an independently suppliable
:class:`~src.reference.result_schema.ReferenceRunContext`, and never
synthesizes one. The shared run context is derived from the task results
themselves and is then verified, not assumed, to be identical across all of
them.

This module also enforces the amendment's profile-separation requirement
(section 2): only task results produced under the full reference-only
evaluator/execution profile may enter this aggregate. Reduced-development
results, mixed-profile result sets, and non-164-task input are all rejected
before a :class:`~src.reference.result_schema.ReferenceBenchmarkResult` is
ever constructed.

Everything this module cannot itself re-derive from the supplied inputs
(missing/duplicate task ids, candidate-identity mismatches against the
manifest, task-manifest-checksum consistency) is left to
``ReferenceBenchmarkResult.__post_init__``, which already enforces it —
this module adds only the checks that constructor does not perform: exact
count, canonical ordering, and profile identity.

**Schema-completeness note (resolved by the v3 correction):** an earlier
version of this module could not independently re-verify comparison-profile
consistency across task results, because ``COMPARISON_PROFILE_VERSION`` was
not itself a field on ``ReferenceRunContext``. ``ReferenceRunContext`` now
carries ``comparison_profile_version`` (schema v3), so
``_require_shared_run_context``'s existing run-context-equality check
already catches a comparison-profile inconsistency across task results —
no separate, dedicated check is needed here, since (unlike
``execution_profile_id``/``evaluator_version``) comparison-profile identity
does not itself vary between the full and reduced-development profiles.
"""

from typing import Sequence

from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EXECUTION_PROFILE_ID_FULL,
)
from src.reference.result_schema import (
    REQUIRED_TASK_COUNT,
    InvalidReferenceResultError,
    ReferenceBenchmarkResult,
    ReferenceRunContext,
    ReferenceTaskResult,
    ReferenceValidationCandidateSetManifest,
)


class ReferenceAggregationError(InvalidReferenceResultError):
    """Raised when ``task_results``/``candidate_set_manifest`` cannot be
    aggregated into a valid primary 164-task reference-validation result.

    A subclass of :class:`InvalidReferenceResultError` so existing callers
    that catch the base type continue to catch this too. Distinguishes
    aggregation-input-shape defects this module checks directly (wrong
    count, wrong ordering, wrong profile, inconsistent oracle version) from
    the per-field invariants ``ReferenceBenchmarkResult`` itself enforces,
    which this function relies on and lets propagate unchanged.
    """


def aggregate_reference_results(
    task_results: Sequence[ReferenceTaskResult],
    candidate_set_manifest: ReferenceValidationCandidateSetManifest,
) -> ReferenceBenchmarkResult:
    """Aggregate exactly 164 task-specific S* results into the primary
    164-task reference-validation :class:`ReferenceBenchmarkResult`.

    Requires:

    - exactly ``REQUIRED_TASK_COUNT`` (164) task results, one per
      ``candidate_set_manifest`` entry, supplied in the manifest's own
      canonical (task-id-sorted) order — a reordered, missing, duplicated,
      or substituted task id is rejected rather than silently corrected;
    - a single shared :class:`ReferenceRunContext`, derived from
      ``task_results[0].context`` and verified identical across every
      result — never accepted as a second, independently suppliable
      argument;
    - that shared run context's ``execution_profile_id``/``evaluator_version``
      equal the full reference-only profile's identifiers exactly, rejecting
      reduced-development or any other non-full profile;
    - a single shared ``oracle_version`` across every result.

    Every other v2-schema invariant (candidate identity matching its
    manifest entry, task-manifest-checksum consistency, no duplicate task
    ids) is enforced by ``ReferenceBenchmarkResult.__post_init__`` itself,
    which this function delegates to rather than re-implementing.

    Full-suite compatibility diagnostics (``ReferenceTaskResult.
    full_suite_diagnostic``) may remain attached to any task result: this
    function does not inspect, strip, or otherwise treat their presence as
    disqualifying. They play no part in ``q_ref``/``q_ref_task`` (see
    ``ReferenceBenchmarkResult.q_ref``, which sums only ``q_ref_task``) and
    this module makes no attempt to fold them in.

    Raises :class:`ReferenceAggregationError` for every rejection this
    function itself performs, and lets
    :class:`~src.reference.result_schema.InvalidReferenceResultError` (or a
    subclass) propagate unchanged from the underlying
    ``ReferenceBenchmarkResult`` construction.
    """
    _require_valid_types(task_results, candidate_set_manifest)
    _require_exact_count(task_results)
    _require_canonical_order(task_results, candidate_set_manifest)

    run_context = _require_shared_run_context(task_results)
    _require_full_reference_profile(run_context)
    oracle_version = _require_shared_oracle_version(task_results)

    evaluated_at = max(result.evaluated_at for result in task_results)
    duration_seconds = sum(result.duration_seconds for result in task_results)

    return ReferenceBenchmarkResult(
        run_context=run_context,
        candidate_set_manifest=candidate_set_manifest,
        task_results=tuple(task_results),
        task_manifest_checksum=candidate_set_manifest.task_manifest_checksum,
        oracle_version=oracle_version,
        evaluated_at=evaluated_at,
        duration_seconds=duration_seconds,
        expected_task_count=REQUIRED_TASK_COUNT,
    )


def _require_valid_types(
    task_results: Sequence[ReferenceTaskResult],
    candidate_set_manifest: ReferenceValidationCandidateSetManifest,
) -> None:
    if not isinstance(candidate_set_manifest, ReferenceValidationCandidateSetManifest):
        raise ReferenceAggregationError(
            f"candidate_set_manifest must be a ReferenceValidationCandidateSetManifest, "
            f"got {type(candidate_set_manifest).__name__}"
        )
    for index, result in enumerate(task_results):
        if not isinstance(result, ReferenceTaskResult):
            raise ReferenceAggregationError(
                f"task_results[{index}] must be a ReferenceTaskResult, "
                f"got {type(result).__name__}"
            )


def _require_exact_count(task_results: Sequence[ReferenceTaskResult]) -> None:
    if len(task_results) != REQUIRED_TASK_COUNT:
        raise ReferenceAggregationError(
            f"aggregate_reference_results requires exactly {REQUIRED_TASK_COUNT} task "
            f"results (the reference-validation denominator), got {len(task_results)}"
        )
    task_ids = [result.task_id for result in task_results]
    if len(set(task_ids)) != len(task_ids):
        raise ReferenceAggregationError("task_results contains duplicate task_id entries")


def _require_canonical_order(
    task_results: Sequence[ReferenceTaskResult],
    candidate_set_manifest: ReferenceValidationCandidateSetManifest,
) -> None:
    task_ids = [result.task_id for result in task_results]
    manifest_task_ids = [entry.task_id for entry in candidate_set_manifest.entries]
    if set(task_ids) != set(manifest_task_ids):
        missing = sorted(set(manifest_task_ids) - set(task_ids))
        extra = sorted(set(task_ids) - set(manifest_task_ids))
        raise ReferenceAggregationError(
            "task_results task_id set does not match candidate_set_manifest's "
            f"{REQUIRED_TASK_COUNT} entries (missing={missing!r}, extra/substituted={extra!r})"
        )
    if task_ids != manifest_task_ids:
        raise ReferenceAggregationError(
            "task_results is not in candidate_set_manifest's canonical task_id order "
            "-- reordered input is rejected rather than silently re-sorted"
        )


def _require_shared_run_context(
    task_results: Sequence[ReferenceTaskResult],
) -> ReferenceRunContext:
    run_context = task_results[0].context
    for result in task_results:
        if result.context != run_context:
            raise ReferenceAggregationError(
                f"task_result for {result.task_id!r} was evaluated under a different "
                f"run_context than task_results[0] (task {task_results[0].task_id!r}) "
                f"-- a benchmark run must share exactly one run_context across all "
                f"{REQUIRED_TASK_COUNT} tasks"
            )
    return run_context


def _require_full_reference_profile(run_context: ReferenceRunContext) -> None:
    if run_context.execution_profile_id != EXECUTION_PROFILE_ID_FULL:
        raise ReferenceAggregationError(
            f"the primary {REQUIRED_TASK_COUNT}-task reference-validation aggregate accepts "
            f"only the full reference-only execution profile ({EXECUTION_PROFILE_ID_FULL!r}); "
            f"got execution_profile_id={run_context.execution_profile_id!r} (rejecting "
            f"reduced-development or any other non-full profile)"
        )
    if run_context.evaluator_version != EVALUATOR_VERSION_FULL:
        raise ReferenceAggregationError(
            f"the primary {REQUIRED_TASK_COUNT}-task reference-validation aggregate accepts "
            f"only the full reference-only evaluator version ({EVALUATOR_VERSION_FULL!r}); "
            f"got evaluator_version={run_context.evaluator_version!r}"
        )


def _require_shared_oracle_version(task_results: Sequence[ReferenceTaskResult]) -> str:
    oracle_versions = {result.oracle_version for result in task_results}
    if len(oracle_versions) != 1:
        raise ReferenceAggregationError(
            f"task_results have inconsistent oracle_version values: {sorted(oracle_versions)!r}"
        )
    return next(iter(oracle_versions))
