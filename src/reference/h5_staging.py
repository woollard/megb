"""MEGB-03H.2B.2: H.5 run-scoped staging identity and the complete-run gate.

Implements the already-accepted "Approved MEGB-03H Planning Amendment" §4
(H.5 production-cache promotion guarantee) and the H.1 design doc's §6
("Frozen decision 4 -- H.5 full-run design"): the production cache stays
byte-for-byte unchanged through fresh execution, staging, and the full
164-task gate evaluation -- nothing here ever writes to a production
:class:`~src.reference.reference_cache.ReferenceResultCache`.

**Staging execution itself is not reimplemented here** -- H.2B.1's own
``ReferenceOrchestrator``, configured with a staging
``ReferenceResultCache`` (rooted under this module's identity-scoped
directory) and ``CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID``,
already provides fresh execution with durable trace-before-cache-write
ordering -- exactly the "stage only after the calibration trace has been
durably persisted" requirement. This module supplies only what H.2B.1
does not: the frozen staging identity, and the post-hoc, read-only
complete-run gate evaluated once staging finishes.

The gate reuses :func:`~src.reference.aggregation.aggregate_reference_results`
and :class:`~src.reference.result_schema.ReferenceBenchmarkResult` for every
check they already perform (exact 164-count, no missing/duplicate/extra/
reordered task identities, one shared full-profile ``ReferenceRunContext``,
one shared ``oracle_version``, per-task candidate-identity/manifest
agreement, ``Q_ref``) rather than duplicating that scoring logic, per the
authorizing scope.
"""

# H5StagingIdentity intentionally repeats several of CalibrationRunContext's/
# ReferenceResultCacheKey's own field declarations verbatim (calibration_run_id,
# execution_profile_id, evaluator_version, dataset/partition/oracle/comparison
# identities): the same real-world identity vocabulary genuinely recurs
# across these types by design, and composing one into another would
# either pull in fields this identity must not carry or require modifying
# an already-accepted schema -- out of scope here. The resulting overlap is
# expected and accepted, not a defect (mirrors reference_audit.py's own
# documented precedent for the same situation).
# pylint: disable=duplicate-code

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from src.evaluators.schema import FailureCategory
from src.reference.aggregation import ReferenceAggregationError, aggregate_reference_results
from src.reference.cache_key import cache_key_for
from src.reference.calibration_schema import (
    CalibrationInvocationRecord,
    CalibrationReconciliationError,
    CalibrationRunContext,
    CalibrationStage,
    CalibrationTaskEvaluationRecord,
    reconcile_all,
)
from src.reference.calibration_summary import (
    CalibrationRecordNotReleaseReadyError,
    incomplete_task_evaluations,
    require_release_ready_stage,
)
from src.reference.reference_cache import CacheDisposition, ReferenceResultCache
from src.reference.result_schema import (
    REQUIRED_TASK_COUNT,
    InvalidReferenceResultError,
    MeasurementStatus,
    ReferenceBenchmarkResult,
    ReferenceRunContext,
    ReferenceTaskResult,
    ReferenceValidationCandidateSetManifest,
)

DEFAULT_H5_STAGING_ROOT = Path("artifacts/privileged/reference/h5_staging_cache")

_LIMIT_ATTRIBUTABLE_CATEGORIES = frozenset(
    {FailureCategory.TIMEOUT, FailureCategory.RESOURCE_LIMIT, FailureCategory.OUTPUT_LIMIT}
)


def _require_nonempty_str(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{field_name!r} must be a nonempty string, got {value!r}")


def _require_sha256_hex(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(
            f"{field_name!r} must be a 64-character hex sha256 digest, got {value!r}"
        )


@dataclass(frozen=True)
class H5StagingIdentity:
    """The frozen run-identity tuple an H.5 staging area and its promotion
    manifest are scoped to. Staging from one run, execution profile,
    evidence identity, or candidate-set manifest must never satisfy
    another -- every field here is compared, not merely the directory name
    a staging cache happens to be rooted under.

    ``dataset_checksum`` is deliberately not required to be sha256-hex
    (its authoritative source, ``DatasetProvenance.evalplus_dataset_hash``,
    is not in that format -- mirroring
    :mod:`~src.reference.cache_key`'s own same exclusion).
    """

    calibration_run_id: str
    execution_profile_id: str
    evaluator_version: str
    execution_protocol_version: str
    dataset_version: str
    dataset_checksum: str
    partition_version: str
    task_manifest_checksum: str
    oracle_version: str
    comparison_profile_version: str
    candidate_set_manifest_checksum: str
    expected_task_count: int = REQUIRED_TASK_COUNT

    def __post_init__(self) -> None:
        for field_name in (
            "calibration_run_id",
            "execution_profile_id",
            "evaluator_version",
            "execution_protocol_version",
            "dataset_version",
            "dataset_checksum",
            "partition_version",
            "oracle_version",
            "comparison_profile_version",
        ):
            _require_nonempty_str(self, field_name)
        _require_sha256_hex(self, "task_manifest_checksum")
        _require_sha256_hex(self, "candidate_set_manifest_checksum")
        if not isinstance(self.expected_task_count, int) or isinstance(
            self.expected_task_count, bool
        ):
            raise ValueError(
                f"expected_task_count must be an int, got {self.expected_task_count!r}"
            )
        if self.expected_task_count != REQUIRED_TASK_COUNT:
            raise ValueError(
                f"expected_task_count must be exactly {REQUIRED_TASK_COUNT} "
                f"(never a silently different denominator), got {self.expected_task_count}"
            )

    def identity_checksum(self) -> str:
        """A content-addressed sha256-hex digest over every field of this
        identity -- the sole component ever used to name this identity's
        staging directory (see :meth:`staging_dir`'s own path-safety note).
        Two identities differing in *any* field (even if they share the
        same human-readable ``calibration_run_id``) never collide."""
        canonical = json.dumps(dataclasses.asdict(self), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def staging_dir(self, root: Path | None = None) -> Path:
        """The privileged directory this identity's staging area is rooted
        at: ``<root>/<identity_checksum>/``.

        Deliberately named from :meth:`identity_checksum` rather than the
        raw, operator-supplied ``calibration_run_id`` -- a free-form string
        that may contain path separators, ``..`` traversal components, an
        absolute-path prefix, control characters, or other platform-
        specific path escapes. A 64-character lowercase hex digest can
        never contain any of those, so this directory (and everything
        derived from it: the staging cache, the promotion manifest) is
        always a direct child of ``root`` for *every* identity, regardless
        of what ``calibration_run_id`` happens to contain. The
        human-readable ``calibration_run_id`` remains available -- inside
        the promotion manifest's own ``identity`` field -- for operators;
        it is simply never interpolated into a filesystem path. Manifest-
        level identity comparison (not directory naming alone) is what
        actually prevents one identity's staging area from satisfying
        another's gate/promotion -- see
        :func:`~src.reference.h5_promotion_manifest.load_promotion_manifest`.
        """
        base = root if root is not None else DEFAULT_H5_STAGING_ROOT
        return base / self.identity_checksum()


def build_staging_cache(
    identity: H5StagingIdentity, root: Path | None = None
) -> ReferenceResultCache:
    """Construct the run-scoped staging :class:`ReferenceResultCache` for
    ``identity`` -- the same, unmodified cache class the production cache
    uses, rooted at a different, identity-scoped directory. No new caching
    code: staging execution reuses H.2B.1's orchestrator against this
    instance."""
    return ReferenceResultCache(identity.staging_dir(root) / "cache")


def manifest_path_for(identity: H5StagingIdentity, root: Path | None = None) -> Path:
    """The canonical promotion-manifest path for ``identity``: a sibling of
    the staging cache under :meth:`H5StagingIdentity.staging_dir`. Deriving
    both from the same checksum-named directory is what makes it provable
    that every staging/cache/manifest write for a given identity is a
    descendant of ``root`` -- see :meth:`H5StagingIdentity.staging_dir`."""
    return identity.staging_dir(root) / "promotion_manifest.json"


@dataclass(frozen=True)
class GateResult:
    """Outcome of :func:`evaluate_complete_run_gate`.

    ``benchmark_result`` is populated only when ``passed`` is ``True`` --
    the single, reconciled :class:`~src.reference.result_schema.ReferenceBenchmarkResult`
    the gate itself derived and validated, available for a caller that
    wants it (e.g. a future committed report) without recomputing it.
    """

    passed: bool
    reason: str
    benchmark_result: ReferenceBenchmarkResult | None = None

    def __post_init__(self) -> None:
        if self.passed and self.benchmark_result is None:
            raise ValueError("a passed GateResult must carry its benchmark_result")
        if not self.passed and self.benchmark_result is not None:
            raise ValueError("a failed GateResult must not carry a benchmark_result")


def evaluate_complete_run_gate(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-return-statements
    *,
    identity: H5StagingIdentity,
    candidate_set_manifest: ReferenceValidationCandidateSetManifest,
    task_results: Sequence[ReferenceTaskResult],
    staging_cache: ReferenceResultCache,
    invocations: Sequence[CalibrationInvocationRecord],
    task_evaluations: Sequence[CalibrationTaskEvaluationRecord],
) -> GateResult:
    """Evaluate the H.5 complete-run promotion gate. Read-only: never
    touches the production cache, never mutates the staging cache or the
    calibration trace. A 163/164 run, a canonical timeout represented as a
    valid zero, an invalid measurement, a trace gap, or any identity
    mismatch fails the gate -- see the module docstring for which checks
    are delegated to :func:`~src.reference.aggregation.aggregate_reference_results`
    rather than re-implemented here.
    """
    if candidate_set_manifest.manifest_checksum != identity.candidate_set_manifest_checksum:
        return GateResult(
            False,
            "candidate_set_manifest.manifest_checksum "
            f"({candidate_set_manifest.manifest_checksum!r}) does not match the frozen staging "
            f"identity's candidate_set_manifest_checksum "
            f"({identity.candidate_set_manifest_checksum!r})",
        )

    try:
        benchmark_result = aggregate_reference_results(task_results, candidate_set_manifest)
    except (ReferenceAggregationError, InvalidReferenceResultError) as exc:
        return GateResult(False, f"aggregation failed: {exc}")

    identity_mismatch = _check_run_context_agrees_with_identity(
        benchmark_result.run_context, identity
    )
    if identity_mismatch is not None:
        return GateResult(False, identity_mismatch)

    content_mismatch = _check_staged_entries_validate(benchmark_result.task_results, staging_cache)
    if content_mismatch is not None:
        return GateResult(False, content_mismatch)

    if benchmark_result.q_ref != 1.0:
        return GateResult(
            False,
            f"Q_ref must be exactly 1.0 for promotion, got {benchmark_result.q_ref!r}",
        )

    limit_failure = _check_no_limit_attributable_failures(benchmark_result.task_results)
    if limit_failure is not None:
        return GateResult(False, limit_failure)

    trace_failure = _check_trace(identity, task_results, invocations, task_evaluations)
    if trace_failure is not None:
        return GateResult(False, trace_failure)

    return GateResult(True, "complete-run gate passed", benchmark_result)


def _check_run_context_agrees_with_identity(
    run_context: ReferenceRunContext, identity: H5StagingIdentity
) -> str | None:
    field_pairs = (
        ("execution_profile_id", run_context.execution_profile_id),
        ("evaluator_version", run_context.evaluator_version),
        ("execution_protocol_version", run_context.execution_protocol_version),
        ("dataset_version", run_context.dataset_version),
        ("dataset_checksum", run_context.dataset_checksum),
        ("partition_version", run_context.partition_version),
        ("task_manifest_checksum", run_context.task_manifest_checksum),
        ("comparison_profile_version", run_context.comparison_profile_version),
    )
    for field_name, actual in field_pairs:
        expected = getattr(identity, field_name)
        if actual != expected:
            return (
                f"run_context.{field_name} ({actual!r}) does not match the frozen staging "
                f"identity's {field_name} ({expected!r})"
            )
    return None


def _check_staged_entries_validate(
    task_results: Sequence[ReferenceTaskResult], staging_cache: ReferenceResultCache
) -> str | None:
    for result in task_results:
        key = cache_key_for(result)
        lookup = staging_cache.get(key)
        if lookup.disposition != CacheDisposition.VALID_HIT:
            return (
                f"task {result.task_id!r}: staged entry does not validate against its own "
                f"cache key ({lookup.disposition.value}: {lookup.detail})"
            )
        if lookup.task_result != result:
            return (
                f"task {result.task_id!r}: staging cache content does not match the "
                f"supplied task result"
            )
    return None


def _check_no_limit_attributable_failures(
    task_results: Sequence[ReferenceTaskResult],
) -> str | None:
    for result in task_results:
        if result.first_failure_category in _LIMIT_ATTRIBUTABLE_CATEGORIES:
            return (
                f"task {result.task_id!r}: first_failure_category "
                f"{result.first_failure_category!r} is limit-attributable -- a valid "
                f"canonical result must never carry TIMEOUT/RESOURCE_LIMIT/OUTPUT_LIMIT"
            )
    return None


def _check_trace(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-return-statements
    identity: H5StagingIdentity,
    task_results: Sequence[ReferenceTaskResult],
    invocations: Sequence[CalibrationInvocationRecord],
    task_evaluations: Sequence[CalibrationTaskEvaluationRecord],
) -> str | None:
    try:
        require_release_ready_stage(invocations)
    except CalibrationRecordNotReleaseReadyError as exc:
        return f"calibration trace is not release-ready: {exc}"

    try:
        reconcile_all(invocations, task_evaluations)
    except CalibrationReconciliationError as exc:
        return f"calibration trace reconciliation failed: {exc}"

    if incomplete_task_evaluations(task_evaluations):
        return "calibration trace has at least one incomplete (non-superseded) task evaluation"

    active = [record for record in task_evaluations if not record.superseded]
    expected_task_ids = {result.task_id for result in task_results}
    active_by_task_id: dict[str, CalibrationTaskEvaluationRecord] = {}
    for record in active:
        if record.task_id in active_by_task_id:
            return (
                f"task {record.task_id!r} has more than one active (non-superseded) "
                f"task evaluation"
            )
        active_by_task_id[record.task_id] = record
    if set(active_by_task_id) != expected_task_ids:
        missing = sorted(expected_task_ids - set(active_by_task_id))
        extra = sorted(set(active_by_task_id) - expected_task_ids)
        return (
            f"active calibration task evaluations do not match the expected task set "
            f"(missing={missing!r}, extra={extra!r})"
        )
    for record in active:
        mismatch = _check_task_evaluation_identity(identity, record)
        if mismatch is not None:
            return mismatch
    return None


def _check_task_evaluation_identity(
    identity: H5StagingIdentity, record: CalibrationTaskEvaluationRecord
) -> str | None:
    context: CalibrationRunContext = record.context
    if context.stage != CalibrationStage.H5:
        return (
            f"task {record.task_id!r}: calibration context stage is {context.stage!r}, "
            f"expected H5"
        )
    if context.calibration_run_id != identity.calibration_run_id:
        return (
            f"task {record.task_id!r}: calibration context calibration_run_id "
            f"{context.calibration_run_id!r} does not match staging identity "
            f"{identity.calibration_run_id!r}"
        )
    if record.task_evaluation_replicate_id != 0:
        return (
            f"task {record.task_id!r}: task_evaluation_replicate_id "
            f"{record.task_evaluation_replicate_id} must be 0 for an H.5 canonical run"
        )
    if record.measurement_status != MeasurementStatus.VALID or record.q_ref_task != 1.0:
        return (
            f"task {record.task_id!r}: calibration trace records "
            f"measurement_status={record.measurement_status!r}, q_ref_task="
            f"{record.q_ref_task!r} -- both must be VALID/1.0"
        )
    return _check_task_evaluation_field_agreement(identity, record)


def _check_task_evaluation_field_agreement(
    identity: H5StagingIdentity, record: CalibrationTaskEvaluationRecord
) -> str | None:
    context = record.context
    field_pairs = (
        ("evaluator_version", context.evaluator_version),
        ("execution_protocol_version", context.execution_protocol_version),
        ("dataset_version", context.dataset_version),
        ("dataset_checksum", context.dataset_checksum),
        ("partition_version", context.partition_version),
        ("oracle_version", context.oracle_version),
        ("comparison_profile_version", context.comparison_profile_version),
        ("task_manifest_checksum", context.task_manifest_checksum),
    )
    for field_name, actual in field_pairs:
        expected = getattr(identity, field_name)
        if actual != expected:
            return (
                f"task {record.task_id!r}: calibration context.{field_name} ({actual!r}) does "
                f"not match the frozen staging identity's {field_name} ({expected!r})"
            )
    if record.first_failure_category in _LIMIT_ATTRIBUTABLE_CATEGORIES:
        return (
            f"task {record.task_id!r}: calibration trace records a limit-attributable "
            f"first_failure_category {record.first_failure_category!r}"
        )
    return None
