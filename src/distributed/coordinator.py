"""MEGB-03H.2C.3B.2B.2: the provider-neutral, in-memory coordinator/worker
scheduling engine.

## Mandatory dependency and transaction-boundary audit (recorded here, per
this checkpoint's own instruction, mirroring
:mod:`~src.distributed.atomic_work_store`'s own precedent)

Every coordinator/worker operation below is mapped to the provider-neutral
protocol it calls, never a concrete store:

* authoritative state mutation (``create_if_absent``/``acquire_lease``/
  ``reassign_lease``/``transition_to_executing``/``mark_retryable``/
  ``dead_letter``/``request_cancellation``/``commit_result``/
  ``acknowledge``/``renew_lease``) -- exclusively
  :class:`~src.distributed.protocols.AtomicWorkStoreProtocol`, injected as
  ``work_store``. This module never imports
  :class:`~src.distributed.atomic_work_store.AtomicWorkStore` for
  anything other than its exception types (``WorkRecordNotFoundError``,
  ``RevisionConflictError``, ``IdentityMismatchError``,
  ``InvalidReservationError``, ``MissingArtifactReferenceError``) --
  typed conditions this module must catch, not a concrete dependency.
* :class:`~src.distributed.protocols.LeaseStateStoreProtocol` and
  :class:`~src.distributed.protocols.ResultStoreProtocol` are never
  imported here at all -- absent from this module entirely, not merely
  unused.
* artifact reads depend on
  :class:`~src.distributed.protocols.ArtifactReaderProtocol` (checksum-
  verified content/metadata, classification verification) --
  ``resolve``/``get``/``verify_artifact_classification`` only.
* worker-side artifact access is further narrowed through
  :class:`~src.distributed.artifact_capabilities.WorkerArtifactCapability`
  -- read-only plus result-only publication, never the raw writer.
* policy/admission evaluates
  :func:`~src.distributed.personal_policy.evaluate_admission` against
  metadata read fresh from the artifact reader -- never a queue-supplied
  claim.
* budget operations depend on
  :class:`~src.distributed.protocols.BudgetReservationProtocol` -- exact
  integer cents only.
* worker registration, work queue, audit sink, clock, and the executor
  callback are all injected as their respective Protocols
  (:class:`~src.distributed.protocols.WorkerRegistryProtocol`,
  the queue adapter's own structural shape,
  :class:`~src.distributed.protocols.AuditSinkProtocol`,
  :class:`~src.distributed.clock.Clock`,
  :class:`~src.distributed.executor.WorkExecutorProtocol`).
* the only concrete in-memory type this module imports for anything other
  than exception classes or structural composition is
  :class:`~src.distributed.queue_adapter.InMemoryAtLeastOnceQueue` itself
  (for its ``receive``/``ack`` at-least-once methods, beyond the minimal
  :class:`~src.distributed.protocols.WorkQueueProtocol`) and
  :class:`~src.distributed.audit_outbox.InMemoryAuditOutbox` -- both are
  this checkpoint's own new synthetic adapters, not a pre-existing
  concrete store this module is supposed to depend on abstractly instead.

See :mod:`~src.distributed.audit_outbox`'s own module docstring for the
audit/outbox recoverability sub-audit (its finding: expressible via a
write-intent-before-CAS-plus-reconciliation-at-dispatch pattern, no
contract correction needed).

**One narrow, additive change to two already-accepted B.2B.1 modules**
(documented, not silently made): ``InMemoryWorkerRegistry.get_registration``
and the matching addition to ``WorkerRegistryProtocol`` -- a read-only
getter, purely additive, so this module can validate a delivered queue
message's ``distributed_run_context_checksum`` against the worker's own
registered one, never trusting the queue message alone for that binding.
No existing method's behavior changed.

## MEGB-03H.2C.3B.2B.2 correction (four semantic issues, addressed before
acceptance -- see ``docs/reference/version-registry.md``'s own
"MEGB-03H.2C.3B.2B.2 correction addendum" for the full schema-version
account)

1. **Concurrency ceiling.** ``CoordinatorConfig.max_admitted_workers`` no
   longer hardcodes :data:`~src.distributed.personal_policy.PERSONAL_BOOTSTRAP_MAX_WORKERS`
   -- see ``coordinator_config.py``'s own docstring. This module's
   ``__init__`` now structurally refuses to construct a
   :class:`Coordinator` whose ``config.max_admitted_workers`` exceeds the
   *injected policy's own* ``max_admitted_workers``, so a personal-
   bootstrap-policy coordinator can never be configured above two, while a
   coordinator wired to a policy with a higher ceiling (test-only; no
   company-authorization policy is created by this correction) may run at
   a genuinely higher bounded concurrency.
2. **Terminal-failure taxonomy.** The reuse of ``RETRY_CEILING_EXCEEDED``
   for a *terminal* (non-retryable) executor failure, previously recorded
   just above this section, was withdrawn as semantically false -- a work
   item dead-lettered on its first attempt never exhausted a retry
   ceiling. :meth:`Coordinator._handle_executor_failure` now selects
   between the new ``NON_RETRYABLE_EXECUTOR_FAILURE`` reason and
   ``RETRY_CEILING_EXCEEDED`` based on *why* dead-lettering occurred. This
   is a legal-value-set expansion of an already-versioned,
   self-checksummed type (``TerminalDispositionReason``, embedded in
   ``TerminalDisposition``), so ``DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION``
   bumps v2->v3.
3. **Admission-audit ordering plus outbox lifecycle.**
   :meth:`Coordinator.admit` now enqueues the admission audit intent
   *before* ``queue.publish`` (previously after) -- a queue-visible work
   item can no longer exist without either a matching audit intent already
   enqueued or a typed, recoverable ``ADMITTED_NOT_PUBLISHED`` diagnosis;
   an audit-enqueue failure (outbox at capacity) now refuses admission
   before publication rather than leaving an unaudited, already-published
   item. See :mod:`~src.distributed.audit_outbox`'s own module docstring
   for the paired ``ABANDONED`` entry-lifecycle state, which prevents
   permanently-unreconciled entries from consuming outbox capacity
   forever.
4. **Committed-result/budget/ack recovery.** ``ResultCommit`` now carries
   ``actual_cost_cents`` (part of the same v2->v3 bump), so the exact
   amount to finalize is authoritative, checksum-bound state, not a
   separate lookup against the independently-mutable budget store.
   :meth:`Coordinator._finalize_from_commit` is called both on the
   fresh-commit path (:meth:`Coordinator._commit_success`, now finalizing
   *before* acking, not after) and on the ``RESULT_COMMITTED``/
   ``ACKNOWLEDGED_COMPLETED`` recovery branch at the top of
   :meth:`Coordinator.invoke_worker` -- so a redelivery after a commit
   whose finalize did not complete (crash, or finalize failure) retries
   finalize idempotently, recovers the existing result without invoking
   the executor again, and only then acks."""

# pylint: disable=too-many-lines

import hashlib
import threading
from enum import Enum
from typing import Callable

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
)
from src.distributed.artifact_capabilities import WorkerArtifactCapability
from src.distributed.artifact_store import (
    ArtifactContentMismatchError,
    ArtifactMetadata,
    ArtifactMetadataMismatchError,
    ArtifactNotFoundError,
)
from src.distributed.atomic_work_store import (
    AuthoritativeWorkRecord,
    IdentityMismatchError,
    InvalidReservationError,
    MissingArtifactReferenceError,
    RevisionConflictError,
    WorkRecordNotFoundError,
)
from src.distributed.audit_outbox import (
    AuditDispatchSummary,
    AuditOutboxFullError,
    InMemoryAuditOutbox,
)
from src.distributed.budget_store import (
    BudgetCeilingExceededError,
    ReservationConflictError,
    ReservationNotActiveError,
    ReservationNotFoundError,
    ReservationStatus,
    WorkerCeilingExceededError,
)
from src.distributed.cancellation import CancellationController
from src.distributed.clock import Clock
from src.distributed.coordinator_config import CoordinatorConfig
from src.distributed.executor import (
    ExecutorFailureReason,
    ExecutorOutcomeKind,
    WorkExecutorProtocol,
    is_retryable_failure,
)
from src.distributed.personal_policy import PersonalEnvironmentPolicy, evaluate_admission
from src.distributed.protocols import (
    ArtifactReaderProtocol,
    ArtifactWriterProtocol,
    AtomicWorkStoreProtocol,
    AuditSinkProtocol,
    BudgetReservationProtocol,
    WorkerRegistryProtocol,
)
from src.distributed.queue_adapter import InMemoryAtLeastOnceQueue, QueueBackpressureError
from src.distributed.safe_audit import SafeAuditEventType, build_safe_audit_event
from src.distributed.state_machine import IllegalStateTransitionError, WorkItemState
from src.distributed.work_contracts import (
    ArtifactKind,
    ArtifactReference,
    CancellationRequest,
    CancellationScope,
    ConflictingResultCommitError,
    ExecutionAttempt,
    QueueWorkMessage,
    ResultCommit,
    TerminalDisposition,
    TerminalDispositionKind,
    TerminalDispositionReason,
    WorkDescriptor,
    queue_work_message_to_dict,
)
from src.distributed.work_outcome import (
    CoordinatorRunSummary,
    WorkOutcome,
    WorkOutcomeKind,
    build_run_summary,
    make_work_outcome,
)
from src.distributed.worker_contracts import Lease, LeaseRenewal, StaleLeaseGenerationError
from src.distributed.worker_registry_store import WorkerNotRegisteredError, WorkerRegistrationStatus

_V = DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION
_C = CHECKSUM_ALGORITHM_VERSION


class QueueMessageIntegrityError(InvalidDistributedProvenanceError):
    """Raised when a received queue message fails a fresh checksum
    reconstruction -- in this synthetic, never-actually-serialized engine
    this can only occur from a genuine internal defect, but the check is
    performed explicitly rather than assumed."""


def _validate_queue_message_integrity(message: QueueWorkMessage) -> None:
    """Recompute ``message``'s own checksum from its current field values
    and confirm it still matches -- the explicit "validate the queue
    message checksum" step this checkpoint's own worker-execution
    sequence requires."""
    data = queue_work_message_to_dict(message)
    try:
        rebuilt = type(message)(
            distributed_orchestration_schema_version=data[
                "distributed_orchestration_schema_version"
            ],
            checksum_algorithm_version=data["checksum_algorithm_version"],
            scientific_work_id=data["scientific_work_id"],
            delivery_id=data["delivery_id"],
            input_ordinal=data["input_ordinal"],
            distributed_run_context_checksum=data["distributed_run_context_checksum"],
            candidate_artifact_reference=message.candidate_artifact_reference,
            lease_generation=data["lease_generation"],
            attempt_checksum=data["attempt_checksum"],
            routing_environment_class=data["routing_environment_class"],
            routing_logical_environment_id=data["routing_logical_environment_id"],
            message_checksum=data["message_checksum"],
        )
    except InvalidDistributedProvenanceError as exc:
        raise QueueMessageIntegrityError(
            f"queue message failed integrity reconstruction: {exc}"
        ) from exc
    if rebuilt != message:
        raise QueueMessageIntegrityError(
            "queue message does not match its own freshly reconstructed checksum"
        )


def make_reservation_validator(budget_store: BudgetReservationProtocol) -> Callable[[str], bool]:
    """The one ``reservation_validator`` callback every
    :class:`~src.distributed.protocols.AtomicWorkStoreProtocol` call in
    this module uses -- ``True`` iff ``reservation_id`` is currently
    ``RESERVED``."""

    def _validate(reservation_id: str) -> bool:
        try:
            return budget_store.get(reservation_id).status == ReservationStatus.RESERVED
        except ReservationNotFoundError:
            return False

    return _validate


class WorkPublicationDisposition(str, Enum):
    """The outcome of :func:`diagnose_work_publication_binding` -- a
    pure, single-item diagnostic (never a scanning coordinator loop, out
    of this checkpoint's scope) proving the crash window between
    authoritative work-record creation (admission step 6) and queue
    publication (admission step 7) is diagnosable and resumable, exactly
    mirroring :func:`~src.distributed.budget_store.diagnose_reservation_work_binding`'s
    own established pattern for the reservation/work-creation window."""

    NOT_YET_ADMITTED = "NOT_YET_ADMITTED"
    ADMITTED_NOT_PUBLISHED = "ADMITTED_NOT_PUBLISHED"
    PUBLISHED = "PUBLISHED"


def diagnose_work_publication_binding(
    work_store: AtomicWorkStoreProtocol,
    queue: InMemoryAtLeastOnceQueue,
    scientific_work_id: str,
) -> WorkPublicationDisposition:
    """Diagnose whether ``scientific_work_id`` has an authoritative
    record, and whether it has been published to ``queue`` -- the
    recovery diagnostic for a crash between
    :meth:`~src.distributed.protocols.AtomicWorkStoreProtocol.create_if_absent`
    succeeding and :meth:`~src.distributed.queue_adapter.InMemoryAtLeastOnceQueue.publish`
    ever being called. A caller observing ``ADMITTED_NOT_PUBLISHED`` may
    safely resume by calling ``queue.publish`` again with the same
    descriptor -- ``publish`` is itself idempotent per
    ``scientific_work_id``."""
    try:
        work_store.read(scientific_work_id)
    except WorkRecordNotFoundError:
        return WorkPublicationDisposition.NOT_YET_ADMITTED
    if queue.is_published(scientific_work_id):
        return WorkPublicationDisposition.PUBLISHED
    return WorkPublicationDisposition.ADMITTED_NOT_PUBLISHED


class Coordinator:  # pylint: disable=too-many-instance-attributes
    """The provider-neutral, in-memory coordinator/worker engine. Every
    dependency is injected as a Protocol (or, for the two synthetic
    adapters this checkpoint itself introduces, the concrete adapter
    type) -- see this module's own audit above."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        config: CoordinatorConfig,
        clock: Clock,
        work_store: AtomicWorkStoreProtocol,
        artifact_reader: ArtifactReaderProtocol,
        artifact_writer: ArtifactWriterProtocol,
        budget_store: BudgetReservationProtocol,
        policy: PersonalEnvironmentPolicy,
        worker_registry: WorkerRegistryProtocol,
        queue: InMemoryAtLeastOnceQueue,
        audit_sink: AuditSinkProtocol,
        audit_outbox: InMemoryAuditOutbox,
        cancellation: CancellationController,
        executor: WorkExecutorProtocol,
    ) -> None:
        if config.max_admitted_workers > policy.max_admitted_workers:
            raise InvalidDistributedProvenanceError(
                f"coordinator config.max_admitted_workers ({config.max_admitted_workers}) "
                f"exceeds the injected policy's own max_admitted_workers "
                f"({policy.max_admitted_workers}) -- a coordinator's technical concurrency "
                "ceiling must never exceed what its own environment policy permits, rejected "
                "before any admission"
            )
        self._config = config
        self._clock = clock
        self._work_store = work_store
        self._artifact_reader = artifact_reader
        self._artifact_writer = artifact_writer
        self._budget_store = budget_store
        self._policy = policy
        self._worker_registry = worker_registry
        self._queue = queue
        self._audit_sink = audit_sink
        self._audit_outbox = audit_outbox
        self._cancellation = cancellation
        self._executor = executor
        self._lease_expiry: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Admission
    # ------------------------------------------------------------------

    def admit(  # pylint: disable=too-many-return-statements
        self,
        descriptor: WorkDescriptor,
        *,
        reservation_id: str,
        requested_cost_cents: int,
        requested_worker_count: int = 1,
    ) -> WorkOutcome | None:
        """The full admission sequence. Returns ``None`` on successful
        admission (the work is now queued; its eventual outcome is
        reported later by :meth:`invoke_worker`), or a terminal
        :class:`~src.distributed.work_outcome.WorkOutcome` if admission
        itself is refused/blocked/cancelled/conflicting."""
        work_id = descriptor.scientific_work_id
        ordinal = descriptor.input_ordinal
        token = self._cancellation.token_for(work_id)
        if token.is_cancelled():
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.CANCELLED_NOT_STARTED)

        try:
            _, metadata = self._artifact_reader.get(descriptor.candidate_artifact_reference)
        except (ArtifactContentMismatchError, ArtifactMetadataMismatchError, ArtifactNotFoundError):
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.INFRASTRUCTURE_FAILURE)

        decision = evaluate_admission(
            self._policy,
            metadata.workload_class,
            metadata.data_classification,
            requested_worker_count,
            requested_cost_cents,
        )
        if not decision.admitted:
            self._enqueue_admission_refused_audit(descriptor)
            return make_work_outcome(
                work_id,
                ordinal,
                WorkOutcomeKind.POLICY_BLOCKED,
                policy_refusal_reasons=decision.refusal_reasons,
            )

        try:
            self._budget_store.reserve(reservation_id, requested_cost_cents, requested_worker_count)
        except (BudgetCeilingExceededError, WorkerCeilingExceededError, ReservationConflictError):
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.BUDGET_BLOCKED)

        record = self._work_store.create_if_absent(
            work_id,
            descriptor.distributed_run_context_checksum,
            reservation_id,
            make_reservation_validator(self._budget_store),
        )
        if record.reservation_id != reservation_id:
            try:
                self._budget_store.release(reservation_id)
            except (ReservationNotFoundError, ReservationNotActiveError):
                pass
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.CONFLICTING_RESULT)

        # MEGB-03H.2C.3B.2B.2 correction: the audit intent is enqueued
        # BEFORE the work item becomes queue-visible, never after -- a
        # queue-visible work item must never exist without either a
        # matching audit intent already durably enqueued, or a typed,
        # recoverable reconciliation state. An admission audit-enqueue
        # failure (outbox at capacity) now refuses admission before
        # publication rather than leaving an unaudited, already-published
        # work item; the authoritative record it refers to already exists
        # and is idempotently re-creatable (create_if_absent), so this
        # admission is safely retriable once outbox capacity frees up --
        # diagnosable via diagnose_work_publication_binding, which reports
        # ADMITTED_NOT_PUBLISHED for exactly this state.
        try:
            self._enqueue_admission_audit(descriptor)
        except AuditOutboxFullError:
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.INFRASTRUCTURE_FAILURE)

        try:
            self._queue.publish(descriptor)
        except QueueBackpressureError:
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.INFRASTRUCTURE_FAILURE)

        return None

    def _enqueue_admission_refused_audit(self, descriptor: WorkDescriptor) -> None:
        event = build_safe_audit_event(
            event_type=SafeAuditEventType.WORK_ADMISSION_REFUSED,
            work_reference=descriptor.scientific_work_id,
            safe_run_identity=descriptor.distributed_run_context_checksum,
            state_after=WorkItemState.PENDING_AVAILABLE,
            logical_timestamp=self._clock.now(),
            input_ordinal=descriptor.input_ordinal,
        )
        self._audit_outbox.enqueue(
            f"refused:{descriptor.scientific_work_id}:{self._clock.now()}", event
        )

    def _enqueue_admission_audit(self, descriptor: WorkDescriptor) -> None:
        event = build_safe_audit_event(
            event_type=SafeAuditEventType.WORK_ADMITTED,
            work_reference=descriptor.scientific_work_id,
            safe_run_identity=descriptor.distributed_run_context_checksum,
            state_after=WorkItemState.PENDING_AVAILABLE,
            logical_timestamp=self._clock.now(),
            input_ordinal=descriptor.input_ordinal,
        )
        self._audit_outbox.enqueue(
            f"admitted:{descriptor.scientific_work_id}",
            event,
            reconciliation_scientific_work_id=descriptor.scientific_work_id,
        )

    # ------------------------------------------------------------------
    # Worker execution
    # ------------------------------------------------------------------

    def invoke_worker(  # pylint: disable=too-many-return-statements,too-many-branches,too-many-statements,too-many-locals
        self, worker_participant_id: str
    ) -> WorkOutcome | None:
        """Receive one at-least-once delivery and process it fully.
        Returns ``None`` if nothing is currently deliverable."""
        message = self._queue.receive()
        if message is None:
            return None
        work_id = message.scientific_work_id
        ordinal = message.input_ordinal
        _validate_queue_message_integrity(message)

        try:
            registration = self._worker_registry.get_registration(worker_participant_id)
            status = self._worker_registry.registration_status(worker_participant_id)
        except WorkerNotRegisteredError:
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.INFRASTRUCTURE_FAILURE)
        if status != WorkerRegistrationStatus.ACTIVE:
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.INFRASTRUCTURE_FAILURE)
        if (
            registration.distributed_run_context_checksum
            != message.distributed_run_context_checksum
        ):
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.INFRASTRUCTURE_FAILURE)

        token = self._cancellation.token_for(work_id)
        try:
            record = self._work_store.read(work_id)
        except WorkRecordNotFoundError:
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.INFRASTRUCTURE_FAILURE)

        if record.state in (WorkItemState.RESULT_COMMITTED, WorkItemState.ACKNOWLEDGED_COMPLETED):
            assert record.result_commit is not None
            # MEGB-03H.2C.3B.2B.2 correction: retry budget finalization
            # (idempotently -- see _finalize_from_commit) before ack, not
            # just on the fresh-commit path. Covers the crash window where
            # a result was durably committed but the process was
            # interrupted (or finalize itself failed) before either
            # finalize or ack completed: redelivery lands here, recovers
            # the existing result without invoking the executor again, and
            # this call is exactly what makes finalize (and ack) actually
            # retried rather than silently skipped forever.
            self._finalize_from_commit(record)
            self._queue.ack(work_id)
            return make_work_outcome(
                work_id,
                ordinal,
                WorkOutcomeKind.RECOVERED_COMMITTED_RESULT,
                result_content_checksum=record.result_commit.result_content_checksum,
            )
        if record.state == WorkItemState.CANCELLED:
            self._queue.ack(work_id)
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.CANCELLED_NOT_STARTED)
        if record.state == WorkItemState.DEAD_LETTERED:
            self._queue.ack(work_id)
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.RETRY_EXHAUSTED)

        if token.is_cancelled() and record.state in (
            WorkItemState.PENDING_AVAILABLE,
            WorkItemState.RETRYABLE,
        ):
            outcome = self._try_cancel_before_lease(record, work_id, ordinal)
            if outcome is not None:
                return outcome
            record = self._work_store.read(work_id)

        lease_outcome = self._acquire_or_reassign_lease(
            record, work_id, ordinal, worker_participant_id
        )
        if isinstance(lease_outcome, WorkOutcome):
            return lease_outcome
        record = lease_outcome
        self._queue.lease(message, Lease(
            distributed_orchestration_schema_version=_V,
            checksum_algorithm_version=_C,
            scientific_work_id=work_id,
            worker_participant_id=worker_participant_id,
            lease_generation=record.current_lease_generation,
            lease_issued_at_logical_clock=self._clock.now(),
            lease_duration_logical_ticks=self._config.lease_duration_ticks,
        ))

        attempt = ExecutionAttempt(
            distributed_orchestration_schema_version=_V,
            checksum_algorithm_version=_C,
            scientific_work_id=work_id,
            worker_participant_id=worker_participant_id,
            lease_generation=record.current_lease_generation,
            distributed_run_context_checksum=message.distributed_run_context_checksum,
        )
        record = self._work_store.transition_to_executing(work_id, record.revision)

        capability = WorkerArtifactCapability(self._artifact_reader, self._artifact_writer)
        try:
            candidate_content, candidate_metadata = capability.get(
                message.candidate_artifact_reference
            )
        except (ArtifactContentMismatchError, ArtifactMetadataMismatchError, ArtifactNotFoundError):
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.INFRASTRUCTURE_FAILURE)

        if token.is_cancelled():
            cancel_outcome = self._try_cancel_after_lease(record, work_id, ordinal)
            if cancel_outcome is not None:
                return cancel_outcome
            record = self._work_store.read(work_id)

        try:
            invocation = self._executor.execute(candidate_content)
        except Exception:  # pylint: disable=broad-except
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.INFRASTRUCTURE_FAILURE)

        if invocation.outcome_kind == ExecutorOutcomeKind.FAILURE:
            assert invocation.failure_reason is not None
            return self._handle_executor_failure(
                record, work_id, ordinal, invocation.failure_reason
            )

        assert invocation.result_content is not None
        return self._commit_success(
            record,
            message,
            attempt,
            work_id,
            ordinal,
            candidate_metadata,
            invocation.result_content,
        )

    def _try_cancel_before_lease(
        self, record: AuthoritativeWorkRecord, work_id: str, ordinal: int
    ) -> WorkOutcome | None:
        scope = (
            CancellationScope.BEFORE_ADMISSION
            if record.state == WorkItemState.PENDING_AVAILABLE
            else CancellationScope.AFTER_LEASE
        )
        request = CancellationRequest(
            distributed_orchestration_schema_version=_V,
            checksum_algorithm_version=_C,
            scientific_work_id=work_id,
            cancellation_scope=scope,
            requested_at_logical_clock=self._clock.now(),
        )
        try:
            self._work_store.request_cancellation(work_id, record.revision, request)
        except (RevisionConflictError, IllegalStateTransitionError):
            return None
        self._queue.ack(work_id)
        return make_work_outcome(work_id, ordinal, WorkOutcomeKind.CANCELLED_NOT_STARTED)

    def _try_cancel_after_lease(
        self, record: AuthoritativeWorkRecord, work_id: str, ordinal: int
    ) -> WorkOutcome | None:
        request = CancellationRequest(
            distributed_orchestration_schema_version=_V,
            checksum_algorithm_version=_C,
            scientific_work_id=work_id,
            cancellation_scope=CancellationScope.AFTER_LEASE,
            requested_at_logical_clock=self._clock.now(),
        )
        try:
            self._work_store.request_cancellation(work_id, record.revision, request)
        except (RevisionConflictError, IllegalStateTransitionError):
            return None
        self._queue.ack(work_id)
        return make_work_outcome(work_id, ordinal, WorkOutcomeKind.CANCELLED_NOT_STARTED)

    def _acquire_or_reassign_lease(
        self,
        record: AuthoritativeWorkRecord,
        work_id: str,
        ordinal: int,
        worker_participant_id: str,
    ) -> AuthoritativeWorkRecord | WorkOutcome:
        next_generation = record.current_lease_generation + 1
        lease = Lease(
            distributed_orchestration_schema_version=_V,
            checksum_algorithm_version=_C,
            scientific_work_id=work_id,
            worker_participant_id=worker_participant_id,
            lease_generation=next_generation,
            lease_issued_at_logical_clock=self._clock.now(),
            lease_duration_logical_ticks=self._config.lease_duration_ticks,
        )
        reservation_validator = make_reservation_validator(self._budget_store)
        try:
            if record.state == WorkItemState.PENDING_AVAILABLE:
                leased_record = self._work_store.acquire_lease(
                    work_id, record.revision, lease, reservation_validator=reservation_validator
                )
            elif record.state == WorkItemState.RETRYABLE:
                leased_record = self._work_store.reassign_lease(
                    work_id, record.revision, lease, reservation_validator=reservation_validator
                )
            else:
                return make_work_outcome(work_id, ordinal, WorkOutcomeKind.STALE_LEASE)
        except (
            RevisionConflictError,
            InvalidReservationError,
            IdentityMismatchError,
            IllegalStateTransitionError,
        ):
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.STALE_LEASE)
        self._lease_expiry[work_id] = self._clock.now() + self._config.lease_duration_ticks
        return leased_record

    def _handle_executor_failure(
        self,
        record: AuthoritativeWorkRecord,
        work_id: str,
        ordinal: int,
        failure_reason: ExecutorFailureReason,
    ) -> WorkOutcome:
        try:
            new_record = self._work_store.mark_retryable(work_id, record.revision)
        except RevisionConflictError:
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.STALE_LEASE)

        is_terminal_failure = not is_retryable_failure(failure_reason)
        retry_ceiling_exceeded = new_record.retry_count >= new_record.retry_limit
        should_dead_letter = is_terminal_failure or retry_ceiling_exceeded
        if should_dead_letter:
            # MEGB-03H.2C.3B.2B.2 correction: a terminal (non-retryable)
            # executor failure is never RETRY_CEILING_EXCEEDED -- that
            # reason means retries were genuinely attempted and exhausted
            # (retry_count >= retry_limit), which is false for a work item
            # dead-lettered on its very first attempt. NON_RETRYABLE_EXECUTOR_FAILURE
            # is the distinct, correct reason for the former; a terminal
            # failure takes priority in the (unreachable in practice, but
            # not structurally impossible) case where both conditions hold.
            disposition_reason = (
                TerminalDispositionReason.NON_RETRYABLE_EXECUTOR_FAILURE
                if is_terminal_failure
                else TerminalDispositionReason.RETRY_CEILING_EXCEEDED
            )
            disposition = TerminalDisposition(
                distributed_orchestration_schema_version=_V,
                checksum_algorithm_version=_C,
                scientific_work_id=work_id,
                disposition=TerminalDispositionKind.DEAD_LETTERED,
                disposition_reason=disposition_reason,
                attempt_count=new_record.retry_count,
            )
            try:
                self._work_store.dead_letter(work_id, new_record.revision, disposition)
                self._queue.ack(work_id)
            except RevisionConflictError:
                pass
            return make_work_outcome(
                work_id,
                ordinal,
                WorkOutcomeKind.RETRY_EXHAUSTED,
                executor_failure_reason=failure_reason,
            )
        return make_work_outcome(
            work_id,
            ordinal,
            WorkOutcomeKind.RETRY_SCHEDULED,
            executor_failure_reason=failure_reason,
        )

    def _commit_success(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        self,
        record: AuthoritativeWorkRecord,
        message: QueueWorkMessage,
        attempt: ExecutionAttempt,
        work_id: str,
        ordinal: int,
        candidate_metadata: ArtifactMetadata,
        result_content: bytes,
    ) -> WorkOutcome:
        result_content_checksum = hashlib.sha256(result_content).hexdigest()
        result_metadata = ArtifactMetadata(
            workload_class=candidate_metadata.workload_class,
            data_classification=candidate_metadata.data_classification,
        )
        result_reference = ArtifactReference(
            distributed_orchestration_schema_version=_V,
            checksum_algorithm_version=_C,
            artifact_kind=ArtifactKind.RESULT_ARTIFACT,
            artifact_reference_id=f"result-{attempt.attempt_checksum}",
            content_checksum=result_content_checksum,
            metadata_checksum=result_metadata.metadata_checksum,
        )
        capability = WorkerArtifactCapability(self._artifact_reader, self._artifact_writer)
        try:
            capability.publish_result(result_reference, result_content, result_metadata)
        except (ArtifactContentMismatchError, ArtifactMetadataMismatchError):
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.CONFLICTING_RESULT)

        # MEGB-03H.2C.3B.2B.2 correction: read the exact amount to finalize
        # once, before the commit, and carry it durably on the commit
        # itself (ResultCommit.actual_cost_cents) -- so it is recoverable
        # from authoritative, checksum-bound state alone after a crash,
        # never re-derived from the separately-locked budget store (whose
        # own reservation may have already moved to FINALIZED/RELEASED by
        # the time a recovering caller looks). This synthetic engine has
        # no real cost-metering mechanism, so the exact amount finalized
        # is the reservation's own requested_cost_cents -- a deterministic,
        # already-known value at commit time.
        try:
            actual_cost_cents = self._budget_store.get(record.reservation_id).requested_cost_cents
        except ReservationNotFoundError:
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.INFRASTRUCTURE_FAILURE)

        commit = ResultCommit(
            distributed_orchestration_schema_version=_V,
            checksum_algorithm_version=_C,
            scientific_work_id=work_id,
            attempt_checksum=attempt.attempt_checksum,
            lease_generation=attempt.lease_generation,
            result_content_checksum=result_content_checksum,
            result_artifact_reference=result_reference,
            actual_cost_cents=actual_cost_cents,
        )

        event = build_safe_audit_event(
            event_type=SafeAuditEventType.RESULT_COMMITTED,
            work_reference=work_id,
            safe_run_identity=message.distributed_run_context_checksum,
            state_after=WorkItemState.RESULT_COMMITTED,
            logical_timestamp=self._clock.now(),
            lease_generation=attempt.lease_generation,
            content_checksum=result_content_checksum,
            input_ordinal=ordinal,
        )
        self._audit_outbox.enqueue(
            f"result-committed:{work_id}:{attempt.attempt_checksum}",
            event,
            reconciliation_scientific_work_id=work_id,
            reconciliation_expected_state=WorkItemState.RESULT_COMMITTED,
            reconciliation_expected_result_content_checksum=result_content_checksum,
        )

        try:
            new_record = self._work_store.commit_result(
                work_id, record.revision, attempt, commit, artifact_resolver=capability.resolve
            )
        except (RevisionConflictError, IdentityMismatchError, StaleLeaseGenerationError):
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.STALE_LEASE)
        except ConflictingResultCommitError:
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.CONFLICTING_RESULT)
        except MissingArtifactReferenceError:
            return make_work_outcome(work_id, ordinal, WorkOutcomeKind.INFRASTRUCTURE_FAILURE)

        # MEGB-03H.2C.3B.2B.2 correction: finalize (idempotently) BEFORE
        # ack, not after -- queue acknowledgement must happen only once
        # the committed-state and accounting invariants both hold. If the
        # process is interrupted here (after commit_result, before or
        # during finalize/ack), no ack has occurred, so at-least-once
        # redelivery lands back in the RESULT_COMMITTED recovery branch
        # above, which retries this same finalize step idempotently
        # before acking.
        self._finalize_from_commit(new_record)
        self._queue.ack(work_id)

        return make_work_outcome(
            work_id,
            ordinal,
            WorkOutcomeKind.EXECUTED_AND_COMMITTED,
            result_content_checksum=result_content_checksum,
        )

    def _finalize_from_commit(self, record: AuthoritativeWorkRecord) -> None:
        """Idempotently finalize ``record``'s bound budget reservation
        using the exact ``actual_cost_cents`` already durably carried on
        its own ``result_commit`` -- never re-derived from a separate
        lookup. Safe to call more than once for the same record: a second
        finalize on an already-``FINALIZED``/``RELEASED`` reservation
        raises :class:`ReservationNotActiveError`
        (:class:`~src.distributed.budget_store.AtomicBudgetStore.finalize`'s
        own existing guarantee), swallowed here as an idempotent no-op --
        double-finalization is structurally impossible, never merely
        avoided by convention."""
        assert record.result_commit is not None
        try:
            self._budget_store.finalize(
                record.reservation_id, record.result_commit.actual_cost_cents
            )
        except (ReservationNotFoundError, ReservationNotActiveError):
            pass

    # ------------------------------------------------------------------
    # Lease heartbeat/renewal
    # ------------------------------------------------------------------

    def renew_lease(self, scientific_work_id: str, worker_participant_id: str) -> None:
        """Explicit heartbeat: renew the current lease without changing
        its generation or state, and extend this coordinator's own
        tracked expiry for it."""
        record = self._work_store.read(scientific_work_id)
        renewal = LeaseRenewal(
            distributed_orchestration_schema_version=_V,
            checksum_algorithm_version=_C,
            scientific_work_id=scientific_work_id,
            worker_participant_id=worker_participant_id,
            lease_generation=record.current_lease_generation,
            renewed_at_logical_clock=self._clock.now(),
        )
        self._work_store.renew_lease(scientific_work_id, record.revision, renewal)
        self._lease_expiry[scientific_work_id] = (
            self._clock.now() + self._config.lease_duration_ticks
        )

    def check_lease_expiry(self, scientific_work_id: str) -> bool:
        """Explicit expiry check: if this coordinator's own tracked
        expiry for ``scientific_work_id``'s current lease has elapsed
        (per the injected logical clock) and the record is still
        ``LEASED``/``EXECUTING`` (no heartbeat renewed it, no result was
        committed), mark it ``RETRYABLE`` so a future
        :meth:`invoke_worker` call may reassign it. Returns ``True`` iff
        it actually transitioned the record. This is an explicit,
        caller-driven check -- never an autonomous timer/polling loop,
        which is out of this checkpoint's own scope."""
        expiry = self._lease_expiry.get(scientific_work_id)
        if expiry is None or self._clock.now() < expiry:
            return False
        try:
            record = self._work_store.read(scientific_work_id)
        except WorkRecordNotFoundError:
            return False
        if record.state not in (WorkItemState.LEASED, WorkItemState.EXECUTING):
            return False
        try:
            self._work_store.mark_retryable(scientific_work_id, record.revision)
        except RevisionConflictError:
            return False
        return True

    # ------------------------------------------------------------------
    # Coordinator-level cancellation
    # ------------------------------------------------------------------

    def request_cancellation(self, scientific_work_id: str) -> None:
        """Request cancellation of ``scientific_work_id`` -- observed at
        the next defined checkpoint (admission, pre-lease, or
        post-lease-pre-commit); never erases already-committed terminal
        evidence."""
        self._cancellation.request_cancellation(scientific_work_id)

    # ------------------------------------------------------------------
    # Audit dispatch
    # ------------------------------------------------------------------

    def dispatch_audit(self) -> AuditDispatchSummary:
        """Attempt to deliver every currently pending, reconciling audit
        outbox entry."""
        return self._audit_outbox.dispatch_pending(self._audit_sink, self._work_store)

    # ------------------------------------------------------------------
    # Bounded scheduler
    # ------------------------------------------------------------------

    def run(
        self,
        admissions: list[tuple[WorkDescriptor, str, int, int]],
        worker_participant_ids: list[str],
    ) -> CoordinatorRunSummary:
        """Admit every descriptor in ``admissions``
        (``(descriptor, reservation_id, requested_cost_cents,
        requested_worker_count)`` tuples), then drain the queue using at
        most ``config.max_admitted_workers`` concurrently-running worker
        invocations -- never more, and never holding any authoritative-
        store lock while the injected executor callback runs (the
        executor is only ever called from inside :meth:`invoke_worker`,
        strictly between two separate, already-returned store calls).
        Outcomes are collected then returned ordered by
        ``input_ordinal``, regardless of completion order."""
        if len(worker_participant_ids) > self._config.max_admitted_workers:
            raise InvalidDistributedProvenanceError(
                f"cannot run with {len(worker_participant_ids)} workers, exceeding "
                f"max_admitted_workers={self._config.max_admitted_workers}"
            )
        outcomes: list[WorkOutcome] = []
        outcomes_lock = threading.Lock()

        for descriptor, reservation_id, requested_cost_cents, requested_worker_count in admissions:
            outcome = self.admit(
                descriptor,
                reservation_id=reservation_id,
                requested_cost_cents=requested_cost_cents,
                requested_worker_count=requested_worker_count,
            )
            if outcome is not None:
                with outcomes_lock:
                    outcomes.append(outcome)

        semaphore = threading.Semaphore(self._config.max_admitted_workers)

        def worker_loop(worker_participant_id: str) -> None:
            while True:
                with semaphore:
                    outcome = self.invoke_worker(worker_participant_id)
                if outcome is None:
                    return
                with outcomes_lock:
                    outcomes.append(outcome)

        threads = [
            threading.Thread(target=worker_loop, args=(worker_participant_id,))
            for worker_participant_id in worker_participant_ids
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        return build_run_summary(outcomes)


__all__ = [
    "QueueMessageIntegrityError",
    "make_reservation_validator",
    "WorkPublicationDisposition",
    "diagnose_work_publication_binding",
    "Coordinator",
]
