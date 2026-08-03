"""MEGB-03G.3: manifest-independent production orchestration, backpressure,
and resumption for the reference evaluator (S*).

Evaluates a bounded collection of task-candidate :class:`WorkItem`\\ s
through :func:`~src.reference.reference_evaluator.evaluate_reference`,
consulting and populating the accepted MEGB-03G.2
:class:`~src.reference.reference_cache.ReferenceResultCache` and
:class:`~src.reference.reference_audit.ReferenceAuditLog` around every
invocation. Reusable, unmodified, by both the 164-task reference-validation
workflow and MEGB-06H's 163-task experimental workflow: nothing here
imports or requires ``ReferenceValidationCandidateSetManifest``,
``primary_experiment_task_manifest``, an expected 163/164 count, or
``aggregate_reference_results`` -- manifest-specific assembly is strictly a
separate adapter's job, not this module's.

Non-goals (explicit, per the authorizing scope): 164-task or 163-task
benchmark aggregation; Q_ref/Q_meas/gaming-delta computation; candidate
selection; MEGB-06 stream evaluation; throughput benchmarking/resource
calibration; scientific-determinism qualification; the MEGB-03I
user-facing CLI; distributed/multi-controller orchestration. Docker
equivalence, isolation, and interruption/resumption validation against a
*real* backend, and throughput benchmarking, are MEGB-03G.4's job -- this
module proves its own behavior with deterministic synthetic/offline tests
only (fake backends/evaluators, temp cache/audit directories, synthetic
evidence).

**Evidence-resolver production-readiness (Requirement 3):** :class:`EvidenceResolver`
is a typed, minimal boundary (``resolve(task_id) -> ReferenceTaskEvidence``)
so orchestration policy never depends on where evidence comes from. A
resolver reading directly from the committed MEGB-03B/MEGB-03C privileged
lock artifacts is *not* implemented here (deliberate scope decision, not a
schema/access-policy blocker -- every field it would need already exists in
those modules' accepted schemas). :class:`MappingEvidenceResolver` is the
production-usable adapter in the meantime: a caller resolves evidence
through its own process and hands this orchestrator a plain mapping.

**KeyboardInterrupt handling:** :meth:`ReferenceOrchestrator.run` catches
``KeyboardInterrupt`` internally, performs the same safe reconciliation as
cooperative cancellation, and *returns* a typed, ``interrupted=True``
:class:`OrchestrationRunSummary` instead of raising. A caller that wants
the process to actually exit on Ctrl-C must check ``summary.interrupted``
itself; nothing here imposes ``sys.exit`` on the caller's behalf.
"""

import hashlib
import re
import threading
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Mapping, Protocol, Sequence

from src.execution.backend import ExecutionBackend
from src.reference.cache_key import ReferenceResultCacheKey, cache_key_for
from src.reference.orchestration_trace import (
    FRESH_CACHE_POLICIES,
    CachePolicy,
    CalibrationTraceRequiredError,
    ReplicateRequiresFreshPolicyError,
    TraceRecorder,
)
from src.reference.reference_audit import ReferenceAuditLog, build_audit_record
from src.reference.reference_orchestrator_admission import (
    AdmissionState,
    KeyExecutionResult,
    KeyGroup,
    logically_equivalent,
    prospective_cache_key,
)
from src.reference.reference_cache import CacheDisposition, ReferenceResultCache
from src.reference.reference_evaluator import (
    FULL_EXECUTION_PROFILE,
    CandidateIdentityMismatchError,
    ExecutionProfile,
    PrivilegedCaseDiagnostic,
    ReferenceEvaluatorVersionMismatchError,
    ReferenceTaskEvidence,
    evaluate_reference,
)
from src.reference.result_schema import MeasurementStatus, ReferenceRunContext, ReferenceTaskResult

ORCHESTRATION_MODEL_SCHEMA_VERSION = "reference-orchestration-v1"

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# The only MeasurementStatus this orchestrator ever retries: a typed,
# transient infrastructure failure. Deliberately not caller-configurable --
# a configurable retryable-status set would let a caller accidentally make
# candidate failures (WRONG_OUTPUT, syntax errors, timeouts...), invalid
# oracle, or invalid protocol/configuration outcomes retryable, all of
# which requirement 7 explicitly forbids.
_RETRYABLE_STATUSES = frozenset({MeasurementStatus.INVALID_INFRASTRUCTURE})


class InvalidWorkItemError(ValueError):
    """Raised when a :class:`WorkItem`'s own fields are internally invalid."""


class DuplicateWorkItemIdError(ValueError):
    """Raised by :meth:`ReferenceOrchestrator.run` when two work items in the
    same call share a ``work_item_id`` -- a caller-contract violation, since
    ``work_item_id`` is the stable key used to map every outcome back to its
    originating request."""


class UnknownTaskIdError(KeyError):
    """Raised by :class:`MappingEvidenceResolver` when asked to resolve a
    ``task_id`` it was not supplied evidence for."""


def _require_nonempty(value: object, field_name: str) -> None:
    if not isinstance(value, str) or value == "":
        raise InvalidWorkItemError(f"{field_name!r} must be a nonempty string, got {value!r}")


@dataclass(frozen=True)
class WorkItem:
    """One task-candidate work item submitted for orchestrated evaluation.

    ``candidate_code`` lives here only in trusted, in-process memory: never
    written to the cache, audit log, run summary, exception message, or any
    committed artifact -- only ``candidate_sha256``/``candidate_id`` ever
    leave the orchestrator's in-process boundary.

    ``candidate_sha256`` is *not* verified against ``candidate_code`` at
    construction time -- that check happens explicitly in
    :meth:`ReferenceOrchestrator.run`, before cache lookup or execution, so
    a malformed item in a batch gets a typed ``CANDIDATE_HASH_MISMATCH``
    outcome rather than failing the whole batch's construction.

    ``task_evaluation_replicate_id`` (H.2B.1, default ``0``): an admission-
    layer-only identity letting ``N`` identical (task, candidate, context)
    items admit as ``N`` distinct fresh measurements. Never enters
    :class:`~src.reference.cache_key.ReferenceResultCacheKey`; a nonzero
    value is rejected under :attr:`CachePolicy.CACHE_FIRST` (see
    :exc:`ReplicateRequiresFreshPolicyError`).
    """

    work_item_id: str
    input_ordinal: int
    task_id: str
    candidate_id: str
    candidate_sha256: str
    candidate_code: str
    run_context: ReferenceRunContext
    task_evaluation_replicate_id: int = 0

    def __post_init__(self) -> None:
        _require_nonempty(self.work_item_id, "work_item_id")
        _require_nonempty(self.task_id, "task_id")
        _require_nonempty(self.candidate_id, "candidate_id")
        _require_nonempty(self.candidate_code, "candidate_code")
        if not isinstance(self.input_ordinal, int) or isinstance(self.input_ordinal, bool):
            raise InvalidWorkItemError(
                f"input_ordinal must be an int, got {self.input_ordinal!r}"
            )
        if self.input_ordinal < 0:
            raise InvalidWorkItemError(
                f"input_ordinal must be non-negative, got {self.input_ordinal!r}"
            )
        if not isinstance(self.candidate_sha256, str) or not _SHA256_HEX_PATTERN.match(
            self.candidate_sha256
        ):
            raise InvalidWorkItemError(
                f"candidate_sha256 must be a 64-character lowercase hex sha256 digest, "
                f"got {self.candidate_sha256!r}"
            )
        if not isinstance(self.run_context, ReferenceRunContext):
            raise InvalidWorkItemError(
                f"run_context must be a ReferenceRunContext, got {self.run_context!r}"
            )
        if not isinstance(self.task_evaluation_replicate_id, int) or isinstance(
            self.task_evaluation_replicate_id, bool
        ):
            raise InvalidWorkItemError(
                f"task_evaluation_replicate_id must be an int, got "
                f"{self.task_evaluation_replicate_id!r}"
            )
        if self.task_evaluation_replicate_id < 0:
            raise InvalidWorkItemError(
                f"task_evaluation_replicate_id must be non-negative, got "
                f"{self.task_evaluation_replicate_id!r}"
            )


@dataclass(frozen=True)
class RetryPolicy:
    """Bounds how many total attempts (including the first) a work item's
    unique cache key may consume when each attempt yields a typed,
    transient ``INVALID_INFRASTRUCTURE`` measurement. ``max_attempts=1``
    means "no retry": one attempt only."""

    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.max_attempts, int) or isinstance(self.max_attempts, bool):
            raise ValueError(f"max_attempts must be an int, got {self.max_attempts!r}")
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be at least 1, got {self.max_attempts!r}")


class Evaluator(Protocol):
    """The exact call shape of :func:`~src.reference.reference_evaluator.evaluate_reference`,
    factored out so a caller may substitute a different evaluation function
    entirely (e.g. MEGB-03G.4's benchmark-only synthetic evaluator, against
    fully synthetic, non-privileged evidence). Purely additive:
    :class:`OrchestrationConfig`'s ``evaluator`` field defaults to the real
    ``evaluate_reference``, so every existing call site is unaffected
    unless it explicitly supplies a different one.
    """

    def __call__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        evidence: ReferenceTaskEvidence,
        candidate_code: str,
        candidate_id: str,
        candidate_sha256: str,
        run_context: ReferenceRunContext,
        *,
        backend: ExecutionBackend,
        profile: ExecutionProfile,
    ) -> tuple[ReferenceTaskResult, tuple[PrivilegedCaseDiagnostic, ...]]:
        """Evaluate one candidate against one task's evidence, exactly like
        ``evaluate_reference``."""


@dataclass(frozen=True)
class OrchestrationConfig:
    """Run-level orchestration policy: concurrency bounds, retry policy,
    execution profile, the audit ``caller`` label, the ``evaluator``
    function invoked per attempt, and the ``cache_policy``/``trace_recorder``
    pair governing the production cache and calibration trace.

    ``evaluator``/``cache_policy`` default to the real ``evaluate_reference``/
    :attr:`CachePolicy.CACHE_FIRST` -- every existing call site that omits
    them is completely unaffected (a purely additive H.2B.1 extension)."""

    max_workers: int
    max_in_flight: int
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    profile: ExecutionProfile = FULL_EXECUTION_PROFILE
    caller: str = "MEGB-03G.3-orchestrator"
    evaluator: Evaluator = evaluate_reference
    cache_policy: CachePolicy = CachePolicy.CACHE_FIRST
    trace_recorder: TraceRecorder | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.max_workers, int) or isinstance(self.max_workers, bool):
            raise ValueError(f"max_workers must be an int, got {self.max_workers!r}")
        if self.max_workers < 1:
            raise ValueError(f"max_workers must be at least 1, got {self.max_workers!r}")
        if not isinstance(self.max_in_flight, int) or isinstance(self.max_in_flight, bool):
            raise ValueError(f"max_in_flight must be an int, got {self.max_in_flight!r}")
        if self.max_in_flight < self.max_workers:
            raise ValueError(
                f"max_in_flight ({self.max_in_flight}) must be >= max_workers "
                f"({self.max_workers})"
            )
        _require_nonempty(self.caller, "caller")
        if not isinstance(self.cache_policy, CachePolicy):
            raise ValueError(f"cache_policy must be a CachePolicy, got {self.cache_policy!r}")
        if self.cache_policy in FRESH_CACHE_POLICIES and self.trace_recorder is None:
            raise CalibrationTraceRequiredError(
                f"cache_policy={self.cache_policy.value!r} requires a trace_recorder -- a "
                f"fresh policy's entire purpose is to produce a durable calibration trace, "
                f"so it can never be configured without one"
            )


class WorkItemDisposition(str, Enum):
    """Typed terminal (or not-yet-started) outcome for one original work item."""

    # A valid result, served without a fresh backend invocation.
    CACHE_HIT = "CACHE_HIT"
    # A valid result, produced by a fresh evaluate_reference() call and cached.
    EXECUTED_VALID = "EXECUTED_VALID"
    # A fresh, non-retryable invalid measurement (INVALID_ORACLE/INVALID_PROTOCOL).
    EXECUTED_INVALID = "EXECUTED_INVALID"
    # INVALID_INFRASTRUCTURE persisted across every authorized retry attempt.
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    # candidate_sha256 mismatched sha256(candidate_code); rejected pre-cache.
    CANDIDATE_HASH_MISMATCH = "CANDIDATE_HASH_MISMATCH"
    # evaluate_reference()'s own version/checksum cross-check failed first.
    EVIDENCE_VERSION_MISMATCH = "EVIDENCE_VERSION_MISMATCH"
    # A valid result, but a conflicting cache entry could not be reconciled.
    CACHE_CONFLICT_BLOCKED = "CACHE_CONFLICT_BLOCKED"
    # A valid result, but the cache layer itself failed to store it.
    CACHE_STORAGE_FAILURE = "CACHE_STORAGE_FAILURE"
    # A valid, fresh result under FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE --
    # deliberately never written to the production cache.
    EXECUTED_VALID_UNCACHED = "EXECUTED_VALID_UNCACHED"
    # Orchestration was interrupted before this item's unique key was ever admitted.
    NOT_STARTED = "NOT_STARTED"


_ACCEPTED_DISPOSITIONS = frozenset(
    {
        WorkItemDisposition.CACHE_HIT,
        WorkItemDisposition.EXECUTED_VALID,
        WorkItemDisposition.EXECUTED_VALID_UNCACHED,
    }
)


@dataclass(frozen=True)
class WorkItemOutcome:
    """The final (or not-yet-started) outcome for one original work item.

    ``task_result``, when present, is a real, already-validated
    :class:`~src.reference.result_schema.ReferenceTaskResult` -- never
    candidate source, never a raw exception, never a privileged
    case-level diagnostic."""

    work_item_id: str
    input_ordinal: int
    task_id: str
    cache_key_digest: str | None
    disposition: WorkItemDisposition
    task_result: ReferenceTaskResult | None
    attempts: int
    detail: str


@dataclass(frozen=True)
class OrchestrationRunSummary:
    """Deterministic, fully reconciled summary of one orchestration run.

    ``accepted_work_items + invalid_work_items + unstarted_work_items ==
    total_work_items`` always holds -- an exhaustive, non-overlapping
    partition over the original work items, regardless of how many unique
    cache keys or retries were involved. ``outcomes`` is ordered by
    ``input_ordinal``, independent of completion order.
    """

    run_id: str
    total_work_items: int
    unique_cache_keys: int
    duplicate_work_items: int
    candidate_hash_mismatches: int
    cache_hit_keys: int
    fresh_execution_keys: int
    total_attempts: int
    accepted_work_items: int
    invalid_work_items: int
    unstarted_work_items: int
    interrupted: bool
    outcomes: tuple[WorkItemOutcome, ...]


class EvidenceResolver(Protocol):
    """Trusted-side boundary resolving the exact
    :class:`~src.reference.reference_evaluator.ReferenceTaskEvidence` for a
    task, kept strictly separate from orchestration policy. Reference-only
    case membership and oracle expected outputs live only inside whatever
    ``ReferenceTaskEvidence`` this returns -- never in this protocol's own
    surface, never logged, never handed back to a caller."""

    def resolve(self, task_id: str) -> ReferenceTaskEvidence:
        """Return the trusted evidence bundle for ``task_id``."""


@dataclass(frozen=True)
class MappingEvidenceResolver:
    """Production-usable :class:`EvidenceResolver` wrapping a pre-resolved
    ``{task_id: ReferenceTaskEvidence}`` mapping -- suitable for tests and
    for real callers that resolve evidence through their own trusted-side
    process and hand this orchestrator the result (see the module
    docstring's Requirement 3 note).
    """

    evidence_by_task_id: Mapping[str, ReferenceTaskEvidence]

    def resolve(self, task_id: str) -> ReferenceTaskEvidence:
        """Return the evidence supplied for ``task_id`` at construction time."""
        try:
            return self.evidence_by_task_id[task_id]
        except KeyError as exc:
            raise UnknownTaskIdError(f"no evidence supplied for task_id {task_id!r}") from exc


class ReferenceOrchestrator:  # pylint: disable=too-few-public-methods
    """Manifest-independent, cache-first, bounded-concurrency orchestrator.

    Never calls ``aggregate_reference_results``, never requires a
    ``ReferenceValidationCandidateSetManifest`` or a 163/164-task count --
    operates purely over the ``work_items`` sequence it is given.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        cache: ReferenceResultCache,
        audit_log: ReferenceAuditLog,
        evidence_resolver: EvidenceResolver,
        backend_factory: Callable[[], ExecutionBackend],
        config: OrchestrationConfig,
        on_in_flight_change: Callable[[int], None] | None = None,
    ) -> None:
        # backend_factory is called once per unique-key execution (never
        # shared across threads): ExecutionBackend's interface does not
        # document thread safety, so a fresh instance per key-execution
        # avoids relying on an undocumented guarantee (requirement 6).
        self._cache = cache
        self._audit_log = audit_log
        self._evidence_resolver = evidence_resolver
        self._backend_factory = backend_factory
        self._config = config
        self._on_in_flight_change = on_in_flight_change
        self._io_lock = threading.Lock()

    def run(
        self,
        work_items: Sequence[WorkItem],
        *,
        run_id: str,
        cancellation_event: threading.Event | None = None,
    ) -> OrchestrationRunSummary:
        """Evaluate ``work_items``, returning a fully reconciled summary.

        Deterministically ordered by ``input_ordinal`` regardless of
        completion order. Catches cooperative cancellation
        (``cancellation_event.is_set()``) and ``KeyboardInterrupt`` alike:
        both stop admission of new unique keys, wait for already-admitted
        keys to finish (their results are never discarded), and mark every
        not-yet-admitted item ``NOT_STARTED`` rather than raising.

        **Contract: never raises or propagates ``KeyboardInterrupt``** --
        returns a normal, fully-formed ``OrchestrationRunSummary`` with
        ``interrupted=True`` instead (see the module docstring's
        KeyboardInterrupt note for the full rationale).
        """
        _require_nonempty(run_id, "run_id")
        work_item_ids = [item.work_item_id for item in work_items]
        if len(work_item_ids) != len(set(work_item_ids)):
            raise DuplicateWorkItemIdError("work_items contains a duplicate work_item_id")

        outcomes_by_id: dict[str, WorkItemOutcome] = {}
        valid_items = self._reject_hash_mismatches(work_items, outcomes_by_id)

        key_groups, ordered_key_digests = self._group_by_cache_key(valid_items)
        unique_cache_keys = len(key_groups)
        duplicate_work_items = len(valid_items) - unique_cache_keys

        key_results, unstarted_digests, interrupted = self._execute_key_groups(
            key_groups, ordered_key_digests, run_id, cancellation_event
        )
        self._fill_outcomes_from_keys(
            key_groups, ordered_key_digests, key_results, unstarted_digests, outcomes_by_id
        )

        ordered_outcomes = tuple(
            sorted(outcomes_by_id.values(), key=lambda outcome: outcome.input_ordinal)
        )
        return self._build_summary(
            run_id=run_id,
            total_work_items=len(work_items),
            unique_cache_keys=unique_cache_keys,
            duplicate_work_items=duplicate_work_items,
            key_results=key_results,
            interrupted=interrupted,
            outcomes=ordered_outcomes,
        )

    @staticmethod
    def _reject_hash_mismatches(
        work_items: Sequence[WorkItem], outcomes_by_id: dict[str, WorkItemOutcome]
    ) -> list[WorkItem]:
        """Verify every item's ``candidate_sha256`` against its
        ``candidate_code`` before any cache lookup, evidence resolution, or
        execution (requirement 1). Mismatches get a terminal
        ``CANDIDATE_HASH_MISMATCH`` outcome directly; everything else is
        returned for further processing."""
        valid_items: list[WorkItem] = []
        for item in work_items:
            actual_sha256 = hashlib.sha256(item.candidate_code.encode("utf-8")).hexdigest()
            if actual_sha256 != item.candidate_sha256:
                outcomes_by_id[item.work_item_id] = WorkItemOutcome(
                    work_item_id=item.work_item_id,
                    input_ordinal=item.input_ordinal,
                    task_id=item.task_id,
                    cache_key_digest=None,
                    disposition=WorkItemDisposition.CANDIDATE_HASH_MISMATCH,
                    task_result=None,
                    attempts=0,
                    detail="candidate_sha256 does not match sha256(candidate_code)",
                )
            else:
                valid_items.append(item)
        return valid_items

    @staticmethod
    def _fill_outcomes_from_keys(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        key_groups: dict[str, KeyGroup],
        ordered_admission_keys: list[str],
        key_results: dict[str, KeyExecutionResult],
        unstarted_admission_keys: set[str],
        outcomes_by_id: dict[str, WorkItemOutcome],
    ) -> None:
        for admission_key in ordered_admission_keys:
            group = key_groups[admission_key]
            # The real cache digest, never the admission_key itself (which
            # also folds in the replicate id for bookkeeping only).
            cache_key_digest = group.key.key_digest
            if admission_key in unstarted_admission_keys:
                for item in group.members:
                    outcomes_by_id[item.work_item_id] = WorkItemOutcome(
                        work_item_id=item.work_item_id,
                        input_ordinal=item.input_ordinal,
                        task_id=item.task_id,
                        cache_key_digest=cache_key_digest,
                        disposition=WorkItemDisposition.NOT_STARTED,
                        task_result=None,
                        attempts=0,
                        detail="orchestration interrupted before this cache key was admitted",
                    )
                continue
            exec_result = key_results[admission_key]
            for item in group.members:
                outcomes_by_id[item.work_item_id] = WorkItemOutcome(
                    work_item_id=item.work_item_id,
                    input_ordinal=item.input_ordinal,
                    task_id=item.task_id,
                    cache_key_digest=cache_key_digest,
                    disposition=exec_result.disposition,
                    task_result=exec_result.task_result,
                    attempts=exec_result.attempts,
                    detail=exec_result.detail,
                )

    def _group_by_cache_key(
        self, valid_items: list[WorkItem]
    ) -> tuple[dict[str, KeyGroup], list[str]]:
        """Group ``valid_items`` for admission, keyed by
        ``f"{cache_key_digest}#{replicate_id}"``. Under ``CACHE_FIRST``
        every replicate id is guaranteed ``0`` (validated below), so this
        degenerates to the original cache-key-only grouping -- byte-for-
        byte unchanged. Under a fresh policy, ``N`` items sharing a cache
        key but carrying ``N`` distinct replicate ids form ``N`` distinct
        groups; ``KeyGroup.key`` is always the plain, replicate-free key.
        """
        evidence_by_task: dict[str, ReferenceTaskEvidence] = {}
        key_groups: dict[str, KeyGroup] = {}
        ordered_admission_keys: list[str] = []
        for item in valid_items:
            if (
                self._config.cache_policy == CachePolicy.CACHE_FIRST
                and item.task_evaluation_replicate_id != 0
            ):
                raise ReplicateRequiresFreshPolicyError(
                    f"work_item {item.work_item_id!r} has explicit replicate semantics "
                    f"(task_evaluation_replicate_id={item.task_evaluation_replicate_id}) but "
                    f"cache_policy is CACHE_FIRST -- configure a fresh CachePolicy instead"
                )
            if item.task_id not in evidence_by_task:
                evidence_by_task[item.task_id] = self._evidence_resolver.resolve(item.task_id)
            evidence = evidence_by_task[item.task_id]
            key = prospective_cache_key(item, evidence)
            admission_key = f"{key.key_digest}#{item.task_evaluation_replicate_id}"
            if admission_key not in key_groups:
                key_groups[admission_key] = KeyGroup(
                    key=key,
                    evidence=evidence,
                    representative=item,
                    members=[],
                    task_evaluation_replicate_id=item.task_evaluation_replicate_id,
                )
                ordered_admission_keys.append(admission_key)
            key_groups[admission_key].members.append(item)
        return key_groups, ordered_admission_keys

    def _build_summary(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        run_id: str,
        total_work_items: int,
        unique_cache_keys: int,
        duplicate_work_items: int,
        key_results: dict[str, KeyExecutionResult],
        interrupted: bool,
        outcomes: tuple[WorkItemOutcome, ...],
    ) -> OrchestrationRunSummary:
        accepted = sum(1 for o in outcomes if o.disposition in _ACCEPTED_DISPOSITIONS)
        unstarted = sum(
            1 for o in outcomes if o.disposition == WorkItemDisposition.NOT_STARTED
        )
        candidate_hash_mismatches = sum(
            1 for o in outcomes if o.disposition == WorkItemDisposition.CANDIDATE_HASH_MISMATCH
        )
        cache_hit_keys = sum(
            1
            for result in key_results.values()
            if result.disposition == WorkItemDisposition.CACHE_HIT
        )
        return OrchestrationRunSummary(
            run_id=run_id,
            total_work_items=total_work_items,
            unique_cache_keys=unique_cache_keys,
            duplicate_work_items=duplicate_work_items,
            candidate_hash_mismatches=candidate_hash_mismatches,
            cache_hit_keys=cache_hit_keys,
            fresh_execution_keys=len(key_results) - cache_hit_keys,
            total_attempts=sum(result.attempts for result in key_results.values()),
            accepted_work_items=accepted,
            invalid_work_items=total_work_items - accepted - unstarted,
            unstarted_work_items=unstarted,
            interrupted=interrupted,
            outcomes=outcomes,
        )

    def _report_in_flight(self, state: AdmissionState) -> None:
        if self._on_in_flight_change is not None:
            self._on_in_flight_change(len(state.in_flight))

    def _drain_in_flight(self, state: AdmissionState) -> None:
        for future, digest in list(state.in_flight.items()):
            state.key_results[digest] = future.result()
        state.in_flight.clear()
        self._report_in_flight(state)

    def _interrupt(self, state: AdmissionState) -> None:
        state.interrupted = True
        self._drain_in_flight(state)
        state.unstarted.update(state.pending)
        state.pending.clear()

    def _admit_ready(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        state: AdmissionState,
        key_groups: dict[str, KeyGroup],
        run_id: str,
        cancelled: threading.Event,
        executor: ThreadPoolExecutor,
    ) -> None:
        while (
            state.pending
            and len(state.in_flight) < self._config.max_in_flight
            and not cancelled.is_set()
        ):
            digest = state.pending.pop(0)
            future = executor.submit(self._execute_key_group, key_groups[digest], run_id)
            state.in_flight[future] = digest
            self._report_in_flight(state)

    def _execute_key_groups(
        self,
        key_groups: dict[str, KeyGroup],
        ordered_key_digests: list[str],
        run_id: str,
        cancellation_event: threading.Event | None,
    ) -> tuple[dict[str, KeyExecutionResult], set[str], bool]:
        cancelled = cancellation_event if cancellation_event is not None else threading.Event()
        state = AdmissionState(pending=list(ordered_key_digests))

        executor = ThreadPoolExecutor(max_workers=self._config.max_workers)
        try:
            try:
                while state.pending or state.in_flight:
                    self._admit_ready(state, key_groups, run_id, cancelled, executor)
                    if cancelled.is_set() or not state.in_flight:
                        break
                    done, _ = wait(list(state.in_flight), return_when=FIRST_COMPLETED)
                    for future in done:
                        digest = state.in_flight.pop(future)
                        state.key_results[digest] = future.result()
                    self._report_in_flight(state)
                if cancelled.is_set():
                    self._interrupt(state)
            except KeyboardInterrupt:
                self._interrupt(state)
        finally:
            executor.shutdown(wait=True)

        return state.key_results, state.unstarted, state.interrupted

    def _execute_key_group(self, group: KeyGroup, run_id: str) -> KeyExecutionResult:
        key = group.key
        representative = group.representative
        evidence = group.evidence
        replicate_id = group.task_evaluation_replicate_id

        # Fresh policies bypass cache.get() completely (requirement 3);
        # CACHE_FIRST's own lookup path below is byte-for-byte unchanged.
        if self._config.cache_policy != CachePolicy.CACHE_FIRST:
            return self._execute_with_retries(
                evidence, representative, key, run_id, "", replicate_id
            )

        with self._io_lock:
            lookup = self._cache.get(key)

        if lookup.disposition == CacheDisposition.VALID_HIT:
            assert lookup.task_result is not None
            with self._io_lock:
                self._append_audit(
                    run_id, representative, lookup.task_result, CacheDisposition.VALID_HIT, 1
                )
            return KeyExecutionResult(
                WorkItemDisposition.CACHE_HIT, lookup.task_result, 0, "served from cache"
            )

        prior_note = ""
        if lookup.disposition in (
            CacheDisposition.STALE_INCOMPATIBLE,
            CacheDisposition.CORRUPT,
            CacheDisposition.STORAGE_INFRASTRUCTURE_FAILURE,
        ):
            prior_note = (
                f" (initial cache lookup returned {lookup.disposition.value}: "
                f"{lookup.detail}; treated as a miss and re-executed)"
            )

        return self._execute_with_retries(
            evidence, representative, key, run_id, prior_note, replicate_id
        )

    def _execute_with_retries(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        self,
        evidence: ReferenceTaskEvidence,
        representative: WorkItem,
        key: ReferenceResultCacheKey,
        run_id: str,
        prior_note: str,
        task_evaluation_replicate_id: int,
    ) -> KeyExecutionResult:
        backend = self._backend_factory()
        max_attempts = self._config.retry_policy.max_attempts
        attempts = 0
        while True:
            attempts += 1
            try:
                result, _diagnostics = self._config.evaluator(
                    evidence,
                    representative.candidate_code,
                    representative.candidate_id,
                    representative.candidate_sha256,
                    representative.run_context,
                    backend=backend,
                    profile=self._config.profile,
                )
            except ReferenceEvaluatorVersionMismatchError as exc:
                return self._finalize(
                    evidence, representative, task_evaluation_replicate_id,
                    WorkItemDisposition.EVIDENCE_VERSION_MISMATCH, None, attempts,
                    f"evidence/run_context version mismatch: {exc}",
                )
            except CandidateIdentityMismatchError as exc:
                # Unreachable in practice (run() already verifies this) --
                # handled defensively so this cannot crash the pool.
                return self._finalize(
                    evidence, representative, task_evaluation_replicate_id,
                    WorkItemDisposition.CANDIDATE_HASH_MISMATCH, None, attempts, str(exc),
                )
            except Exception as exc:  # pylint: disable=broad-except
                # Backend setup failure -- treated as transient infrastructure
                # failure; only the type name is kept, never the raw message.
                if attempts < max_attempts:
                    continue
                return self._finalize(
                    evidence, representative, task_evaluation_replicate_id,
                    WorkItemDisposition.RETRY_EXHAUSTED, None, attempts,
                    f"infrastructure retries exhausted after {attempts} attempts "
                    f"(backend raised {type(exc).__name__})",
                )

            if result.status == MeasurementStatus.VALID:
                return self._accept_valid_result(
                    result,
                    key,
                    representative,
                    evidence,
                    run_id,
                    attempts,
                    prior_note,
                    task_evaluation_replicate_id,
                )

            with self._io_lock:
                self._append_audit(run_id, representative, result, CacheDisposition.MISS, attempts)

            if result.status not in _RETRYABLE_STATUSES:
                return self._finalize(
                    evidence, representative, task_evaluation_replicate_id,
                    WorkItemDisposition.EXECUTED_INVALID, result, attempts,
                    f"non-retryable status {result.status.value}",
                )
            if attempts < max_attempts:
                continue
            return self._finalize(
                evidence, representative, task_evaluation_replicate_id,
                WorkItemDisposition.RETRY_EXHAUSTED, result, attempts,
                f"infrastructure retries exhausted after {attempts} attempts",
            )

    def _finalize(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        evidence: ReferenceTaskEvidence,
        representative: WorkItem,
        task_evaluation_replicate_id: int,
        disposition: WorkItemDisposition,
        result: ReferenceTaskResult | None,
        attempts: int,
        detail: str,
    ) -> KeyExecutionResult:
        """Build the terminal result for a non-cache-writing code path,
        durably tracing it first under a fresh :class:`CachePolicy` (a
        no-op under ``CACHE_FIRST`` -- never touches ``trace_recorder``
        there, per requirement 8)."""
        if self._config.cache_policy != CachePolicy.CACHE_FIRST:
            assert (trace_recorder := self._config.trace_recorder) is not None
            trace_recorder.record_fresh_attempt(
                work_item=representative,
                evidence=evidence,
                task_evaluation_replicate_id=task_evaluation_replicate_id,
                attempts=attempts,
                disposition=disposition,
                task_result=result,
            )
        return KeyExecutionResult(disposition, result, attempts, detail)

    def _accept_valid_result(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        result: ReferenceTaskResult,
        key: ReferenceResultCacheKey,
        representative: WorkItem,
        evidence: ReferenceTaskEvidence,
        run_id: str,
        attempts: int,
        prior_note: str,
        task_evaluation_replicate_id: int,
    ) -> KeyExecutionResult:
        if self._config.cache_policy != CachePolicy.CACHE_FIRST:
            # Fresh policies: trace first (requirement 4/5); a raised
            # failure propagates before cache.put() is ever reached.
            assert (trace_recorder := self._config.trace_recorder) is not None
            trace_recorder.record_fresh_attempt(
                work_item=representative,
                evidence=evidence,
                task_evaluation_replicate_id=task_evaluation_replicate_id,
                attempts=attempts,
                disposition=WorkItemDisposition.EXECUTED_VALID,
                task_result=result,
            )
        if self._config.cache_policy == CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE:
            # Bypass cache reads and writes completely (requirement 5).
            with self._io_lock:
                self._append_audit(run_id, representative, result, CacheDisposition.MISS, attempts)
            return KeyExecutionResult(
                WorkItemDisposition.EXECUTED_VALID_UNCACHED,
                result,
                attempts,
                "fresh valid execution, not written to the production cache "
                "(FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE)" + prior_note,
            )

        with self._io_lock:
            write = self._cache.put(result)
            if write.disposition == CacheDisposition.WRITE_ACCEPTED:
                self._append_audit(
                    run_id, representative, result, CacheDisposition.WRITE_ACCEPTED, attempts
                )
                return KeyExecutionResult(
                    WorkItemDisposition.EXECUTED_VALID,
                    result,
                    attempts,
                    "fresh valid execution cached" + prior_note,
                )
            if write.disposition == CacheDisposition.CONFLICTING_WRITE:
                reread = self._cache.get(key)
                reread_valid = reread.disposition == CacheDisposition.VALID_HIT
                reread_matches = (
                    reread_valid
                    and reread.task_result is not None
                    and logically_equivalent(reread.task_result, result)
                )
                if reread_matches:
                    assert reread.task_result is not None
                    self._append_audit(
                        run_id,
                        representative,
                        reread.task_result,
                        CacheDisposition.VALID_HIT,
                        attempts,
                    )
                    return KeyExecutionResult(
                        WorkItemDisposition.CACHE_HIT,
                        reread.task_result,
                        attempts,
                        "concurrent equivalent write reconciled as a cache hit",
                    )
                self._append_audit(
                    run_id, representative, result, CacheDisposition.CONFLICTING_WRITE, attempts
                )
                return KeyExecutionResult(
                    WorkItemDisposition.CACHE_CONFLICT_BLOCKED,
                    result,
                    attempts,
                    f"conflicting cache entry could not be reconciled as equivalent: "
                    f"{write.detail}",
                )
            # STORAGE_INFRASTRUCTURE_FAILURE
            self._append_audit(
                run_id,
                representative,
                result,
                CacheDisposition.STORAGE_INFRASTRUCTURE_FAILURE,
                attempts,
            )
            return KeyExecutionResult(
                WorkItemDisposition.CACHE_STORAGE_FAILURE,
                result,
                attempts,
                f"cache storage failure while writing a valid result: {write.detail}",
            )

    def _append_audit(
        self,
        run_id: str,
        representative: WorkItem,
        task_result: ReferenceTaskResult,
        cache_disposition: CacheDisposition,
        attempt: int,
    ) -> None:
        """Build and append one safe audit record. Always called while
        holding ``self._io_lock`` -- serializes cache/audit I/O across
        concurrently executing key groups without holding that lock during
        the (potentially slow) backend execution itself."""
        digest = cache_key_for(task_result).key_digest
        location = str(self._cache.cache_dir / f"{digest}.json")
        record = build_audit_record(
            caller=f"{self._config.caller}:{run_id}",
            run_context=representative.run_context,
            task_result=task_result,
            cache_disposition=cache_disposition,
            invocation_id=f"{uuid.uuid4().hex}-attempt-{attempt}",
            invoked_at=datetime.now(timezone.utc).isoformat(),
            result_artifact_location=location,
        )
        self._audit_log.append(record)
