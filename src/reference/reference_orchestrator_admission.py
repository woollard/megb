"""MEGB-03G.3/H.2B.1: cache-key derivation, admission-group bookkeeping,
and result-equivalence helpers for
:class:`~src.reference.reference_orchestrator.ReferenceOrchestrator`.

Split out from ``src.reference.reference_orchestrator`` (whose
``ReferenceOrchestrator`` is these helpers' only real caller) purely to
keep each module under a manageable size -- there is no behavioral reason
for the split.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.reference.cache_key import CACHE_KEY_SCHEMA_VERSION, ReferenceResultCacheKey
from src.reference.reference_evaluator import ReferenceTaskEvidence
from src.reference.result_schema import ReferenceTaskResult

if TYPE_CHECKING:
    # Import-cycle-safe: reference_orchestrator.py imports this module, so
    # WorkItem/WorkItemDisposition are only ever used here as (quoted, for
    # WorkItemDisposition) type annotations -- dataclasses do not evaluate
    # string annotations, so no runtime import of either is required.
    from concurrent.futures import Future

    from src.reference.reference_orchestrator import WorkItem, WorkItemDisposition


def prospective_cache_key(
    item: "WorkItem", evidence: ReferenceTaskEvidence
) -> ReferenceResultCacheKey:
    """Construct the cache key a fresh evaluation of ``item`` against
    ``evidence`` would produce, *before* any execution happens -- every
    field is already knowable from ``item.run_context``/``evidence`` alone
    (``evaluate_reference`` always copies them onto the result verbatim),
    so this key is guaranteed to equal the real result's later hash,
    letting the orchestrator consult the cache before running candidate
    code. A pure additive read of ``src.reference.cache_key``'s already-
    public constructor -- no change to that module's schema or behavior.
    """

    context = item.run_context
    return ReferenceResultCacheKey(
        cache_key_schema_version=CACHE_KEY_SCHEMA_VERSION,
        task_id=item.task_id,
        candidate_sha256=item.candidate_sha256,
        reference_case_checksum=evidence.reference_case_checksum,
        dataset_version=context.dataset_version,
        dataset_checksum=context.dataset_checksum,
        partition_version=context.partition_version,
        task_manifest_checksum=context.task_manifest_checksum,
        oracle_version=evidence.oracle_version,
        comparison_profile_version=context.comparison_profile_version,
        evaluator_version=context.evaluator_version,
        execution_profile_id=context.execution_profile_id,
        execution_protocol_version=context.execution_protocol_version,
    )


@dataclass
class KeyGroup:
    """One admission group: every :class:`~src.reference.reference_orchestrator.WorkItem`
    sharing both a cache key and a ``task_evaluation_replicate_id``."""

    key: ReferenceResultCacheKey
    evidence: ReferenceTaskEvidence
    representative: "WorkItem"
    members: "list[WorkItem]"
    task_evaluation_replicate_id: int


def logically_equivalent(first: ReferenceTaskResult, second: ReferenceTaskResult) -> bool:
    """True when two results are *semantically* the same measurement for
    the same task/candidate/evidence, differing (if at all) only in
    *observational* invocation metadata. The single, centralized
    definition of "equivalent enough to reconcile as a cache hit" (one call
    site: :meth:`~src.reference.reference_orchestrator.ReferenceOrchestrator._accept_valid_result`),
    deciding whether a :attr:`~src.reference.reference_cache.CacheDisposition.CONFLICTING_WRITE`
    may be accepted as a hit rather than blocked.

    Semantic fields (must match exactly): ``task_id``, ``candidate_sha256``,
    ``context``, ``status``, ``q_ref_task``, ``reference_case_total``,
    ``reference_case_pass_count``, ``first_failure_category``,
    ``oracle_version``, ``reference_case_checksum``,
    ``execution_failure_counts`` -- these fully determine *what was
    measured*. Observational fields, deliberately excluded:
    ``evaluated_at``/``duration_seconds`` -- two independent correct
    executions of the same deterministic candidate will almost never agree
    on either, so an exact ``==`` would reject every genuine concurrent
    race as a conflict.
    """
    return (
        first.task_id == second.task_id
        and first.candidate_sha256 == second.candidate_sha256
        and first.context == second.context
        and first.status == second.status
        and first.q_ref_task == second.q_ref_task
        and first.reference_case_total == second.reference_case_total
        and first.reference_case_pass_count == second.reference_case_pass_count
        and first.first_failure_category == second.first_failure_category
        and first.oracle_version == second.oracle_version
        and first.reference_case_checksum == second.reference_case_checksum
        and dict(first.execution_failure_counts) == dict(second.execution_failure_counts)
    )


@dataclass(frozen=True)
class KeyExecutionResult:
    """The terminal (or in-flight) execution outcome for one admission group."""

    disposition: "WorkItemDisposition"
    task_result: ReferenceTaskResult | None
    attempts: int
    detail: str


@dataclass
class AdmissionState:
    """Mutable bookkeeping for one
    :meth:`~src.reference.reference_orchestrator.ReferenceOrchestrator._execute_key_groups`
    call -- bundled into one object purely to keep that method's own local
    variable count small; not used anywhere else."""

    pending: "list[str]"
    key_results: "dict[str, KeyExecutionResult]" = field(default_factory=dict)
    in_flight: "dict[Future[KeyExecutionResult], str]" = field(default_factory=dict)
    unstarted: "set[str]" = field(default_factory=set)
    interrupted: bool = False
