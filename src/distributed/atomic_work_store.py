"""MEGB-03H.2C.3B.2B.1: the atomic authoritative work-state store.

## Mandatory pre-implementation atomicity audit (recorded here, per this
checkpoint's own instruction, rather than in a separate document)

**Question audited:** can the accepted MEGB-03H.2C.3B.2A protocols
(``src.distributed.protocols``) express the indivisible 8-step commit
decision -- verify work record/revision, verify state, verify lease
fencing, verify identities, reconcile any existing result, install the
result reference, transition to result-committed, and establish
acknowledgement eligibility -- as one atomic operation, without relying
on a process-local lock spanning independent services, a check-then-write
race, best-effort compensation, queue ordering, exactly-once delivery, or
caller discipline?

**Finding: no, not as literally composed.** B.2A split this decision
across two independent :class:`typing.Protocol` interfaces --
:class:`~src.distributed.protocols.LeaseStateStoreProtocol` (owns
``transition``/``current_lease``) and
:class:`~src.distributed.protocols.ResultStoreProtocol` (owns
``commit_result``/``acknowledge``) -- with **no shared revision or
compare-and-swap parameter connecting them**. A caller composing them
naively (read state, decide, call ``result_store.commit_result(...)``,
then separately call ``lease_state_store.transition(...)``) performs
exactly the check-then-write race across independent services this
checkpoint's own audit instruction forbids relying on: between the two
calls, a concurrent competitor could reassign the lease, and neither
Protocol's own signature would detect it, because neither carries the
other's notion of "current revision."

**This is not a MEGB-03H.2C.3B.2A defect requiring a correction.** B.2A's
own acceptance record (``tickets/megb-03.md``) already states explicitly
that B.2A "establishes contracts only... does not yet prove race-free
composed behavior," and lists "one atomic transaction or equivalent
compare-and-swap operation" as B.2B's own **downstream obligation to
build** -- never a promise B.2A's four Protocols were meant to keep by
mere composition. No accepted B.2A dataclass's field *shape* needs to
change to close this gap: :class:`~src.distributed.work_contracts.ExecutionAttempt`,
:class:`~src.distributed.work_contracts.ResultCommit`,
:class:`~src.distributed.worker_contracts.Lease`,
:class:`~src.distributed.work_contracts.TerminalDisposition`, and
:class:`~src.distributed.state_machine.WorkItemState` are reused here
completely unchanged, as the *data* a new, additive, unified record
carries -- what was missing is the record and the transaction engine
around it, not a correction to any accepted value type.

**Conclusion: ``DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`` does not
bump.** No existing type's shape changes. :class:`AuthoritativeWorkRecord`
is a genuinely new type, introduced by this checkpoint, joining the same
family of ``src/distributed/`` orchestration types this project's own
version registry already documents as able to grow by addition without a
version bump (the same "a brand-new type joining an unchanged schema
family" pattern already established there) -- **but see the deliberate
exception below**: this module's own new types intentionally do **not**
carry ``distributed_orchestration_schema_version``/
``checksum_algorithm_version`` fields at all, for a reason distinct from
"forgot to bump a version": every B.1/B.2A self-checksummed type exists
to cross a trust or process boundary (a queue message, a persisted
provenance record) where tamper detection via a content checksum is the
right tool. :class:`AuthoritativeWorkRecord` is the opposite kind of
object -- **the single, in-process, mutable-by-replacement authoritative
state** a coordinator consults *right now*; the property it needs is a
monotonically-increasing ``revision`` integer for compare-and-swap
concurrency control, not a content checksum, and it is never serialized
across a process boundary in this checkpoint's own scope (no coordinator
loop, no real persistence, no GCP adapter exists yet to transmit one).
A future checkpoint that *does* persist or transmit this record across a
boundary should reconsider this decision at that time, exactly as this
project's own established discipline already does for other "not yet
persisted, revisit later" gaps (e.g. ``H5StagingIdentity.identity_checksum()``'s
own recorded, not-yet-closed gap in the version registry).

**Provider-neutral shape of the guarantee going forward:** a single
authoritative, revisioned per-work state record, updated only by
compare-and-swap (or an equivalent real-backend transaction -- a GCP
Firestore transaction, a DynamoDB conditional write, a Spanner mutation;
none accessed or implemented here). Immutable, content-addressed result
artifacts may be durably written *before* that CAS (see
:mod:`~src.distributed.artifact_store`); queue acknowledgement remains
strictly *after* it. :class:`AtomicWorkStore` below is the synthetic,
single-process, ``threading.Lock``-protected realization of this shape --
a real distributed backend would replace the internal lock with its own
atomic primitive, but the *contract* (one revisioned record, one
indivisible read-validate-write) is what this module fixes. This module
structurally implements
:class:`~src.distributed.protocols.AtomicWorkStoreProtocol` (see that
module for the full method contract and linearizability requirement).

**MEGB-03H.2C.3B.2B.1 correction: reservation binding.** The checkpoint
correction's admission/reservation crash-window audit found that an
authoritative work record and a budget reservation
(:mod:`~src.distributed.budget_store`) are necessarily created in two
separate, non-atomic steps (this module does not claim cross-store
atomicity with an independent, separately-locked budget store). To keep
that two-step protocol deterministic and recoverable rather than merely
best-effort, :class:`AuthoritativeWorkRecord` now binds an immutable
``reservation_id`` at creation, :meth:`AtomicWorkStore.create_if_absent`
requires it to validate as currently reserved before a *new* record is
ever created, and :meth:`AtomicWorkStore.acquire_lease`/
:meth:`AtomicWorkStore.reassign_lease` re-validate the same bound
reservation, inside the same atomic ``mutate`` step as the ``LEASED``
transition itself (never as a separate check-then-write), before either
may proceed -- "work cannot become leaseable without a valid reservation"
is enforced at the one indivisible step where leaseability actually takes
effect, not by convention. See
:func:`~src.distributed.budget_store.diagnose_reservation_work_binding`
for the crash-recovery diagnostic this binding makes possible.
"""

# pylint: disable=duplicate-code
# _new_record's field list inherently mirrors
# tests/test_atomic_work_store.py's own direct AuthoritativeWorkRecord
# constructions (both build the same dataclass) -- shared boilerplate,
# not shared logic.

import dataclasses
import threading
from dataclasses import dataclass
from typing import Callable

from src.distributed._checksums import (
    InvalidDistributedProvenanceError,
    require_non_negative_int as _require_non_negative_int,
    require_nonempty_str as _require_nonempty_str,
    require_positive_int as _require_positive_int,
    require_sha256_hex as _require_sha256_hex,
)
from src.distributed.state_machine import (
    IllegalStateTransitionError,
    WorkItemState,
    is_terminal,
    validate_transition,
)
from src.distributed.work_contracts import (
    Acknowledgement,
    ArtifactReference,
    CancellationRequest,
    CancellationScope,
    ExecutionAttempt,
    ResultCommit,
    TerminalDisposition,
    TerminalDispositionKind,
    TerminalDispositionReason,
    reconcile_result_commit,
    require_commit_before_ack,
)
from src.distributed.worker_contracts import Lease, LeaseRenewal, validate_fencing

DEFAULT_RETRY_LIMIT = 3


class WorkRecordNotFoundError(InvalidDistributedProvenanceError):
    """Raised when an operation names a ``scientific_work_id`` with no
    authoritative record yet (or no longer, though records are never
    deleted in this store)."""


class RevisionConflictError(InvalidDistributedProvenanceError):
    """Raised when a caller's ``expected_revision`` does not match the
    record's current revision -- the compare-and-swap rejection every
    concurrent competitor must be prepared to retry against. No data is
    corrupted or partially written when this is raised; the record is
    left exactly as it was before the call."""


class MissingArtifactReferenceError(InvalidDistributedProvenanceError):
    """Raised by :meth:`AtomicWorkStore.commit_result` when the referenced
    result artifact is not yet durably present in the artifact store --
    the artifact must be written before the CAS, never after."""


class IdentityMismatchError(InvalidDistributedProvenanceError):
    """Raised when an incoming attempt/commit's own identity fields
    (scientific work id, distributed-run-context checksum, worker
    participant id, attempt checksum) do not match the authoritative
    record they are being applied against."""


class InvalidReservationError(InvalidDistributedProvenanceError):
    """Raised when a caller-supplied ``reservation_id`` does not validate
    as currently reserved (per an injected ``reservation_validator``) --
    either at authoritative work creation (reservation before admission)
    or at lease acquisition/reassignment (a work item must never become
    leaseable without a currently valid reservation, even if the
    reservation was released after the work record was created). See
    :mod:`~src.distributed.budget_store`'s own module docstring for the
    full reservation/work-creation crash-window recovery protocol this
    validation is part of."""


@dataclass(frozen=True)
class AuthoritativeWorkRecord:  # pylint: disable=too-many-instance-attributes
    """The single authoritative, revisioned state for one unit of
    scientific work. Every field here is either an opaque logical
    identity, a closed-enum value, a sha256 checksum, a non-negative
    integer, a boolean, or an already-leakage-tested B.2A value type
    (:class:`~src.distributed.work_contracts.ResultCommit`,
    :class:`~src.distributed.work_contracts.TerminalDisposition`) --
    there is structurally no field capable of carrying raw candidate
    content, privileged evidence, a credential, an infrastructure
    resource name, or free-form exception text.

    Deliberately carries no ``distributed_orchestration_schema_version``/
    ``checksum_algorithm_version``/self-checksum field -- see this
    module's own docstring for why: this is in-process authoritative
    state, never (in this checkpoint's scope) serialized across a
    process boundary, and its concurrency-control property is
    ``revision`` (a compare-and-swap sequence number), not a content
    checksum."""

    scientific_work_id: str
    distributed_run_context_checksum: str
    reservation_id: str
    state: WorkItemState
    revision: int
    current_lease_generation: int
    worker_participant_id: str | None
    worker_context_checksum: str | None
    cancellation_scope: CancellationScope | None
    result_commit: ResultCommit | None
    acknowledged: bool
    terminal_disposition: TerminalDisposition | None
    retry_count: int
    retry_limit: int

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _require_nonempty_str(self, "scientific_work_id")
        _require_sha256_hex(self, "distributed_run_context_checksum")
        _require_nonempty_str(self, "reservation_id")
        if not isinstance(self.state, WorkItemState):
            raise InvalidDistributedProvenanceError(
                f"state must be a WorkItemState, got {self.state!r}"
            )
        _require_non_negative_int(self, "revision")
        _require_non_negative_int(self, "current_lease_generation")
        if self.worker_participant_id is not None and (
            not isinstance(self.worker_participant_id, str) or self.worker_participant_id == ""
        ):
            raise InvalidDistributedProvenanceError(
                f"worker_participant_id must be a nonempty string or None, got "
                f"{self.worker_participant_id!r}"
            )
        if self.worker_context_checksum is not None:
            _require_sha256_hex(self, "worker_context_checksum")
        if self.cancellation_scope is not None and not isinstance(
            self.cancellation_scope, CancellationScope
        ):
            raise InvalidDistributedProvenanceError(
                f"cancellation_scope must be a CancellationScope or None, got "
                f"{self.cancellation_scope!r}"
            )
        if self.result_commit is not None and not isinstance(self.result_commit, ResultCommit):
            raise InvalidDistributedProvenanceError(
                f"result_commit must be a ResultCommit or None, got {self.result_commit!r}"
            )
        if not isinstance(self.acknowledged, bool):
            raise InvalidDistributedProvenanceError(
                f"acknowledged must be a bool, got {self.acknowledged!r}"
            )
        if self.terminal_disposition is not None and not isinstance(
            self.terminal_disposition, TerminalDisposition
        ):
            raise InvalidDistributedProvenanceError(
                f"terminal_disposition must be a TerminalDisposition or None, got "
                f"{self.terminal_disposition!r}"
            )
        _require_non_negative_int(self, "retry_count")
        _require_positive_int(self, "retry_limit")
        if self.retry_count > self.retry_limit:
            raise InvalidDistributedProvenanceError(
                f"retry_count ({self.retry_count}) must not exceed retry_limit "
                f"({self.retry_limit})"
            )
        # Cross-field invariants -- the state machine's own topology plus
        # these checks together make an inconsistent record unconstructable.
        if self.acknowledged and (
            self.state != WorkItemState.ACKNOWLEDGED_COMPLETED or self.result_commit is None
        ):
            raise InvalidDistributedProvenanceError(
                "acknowledged=True requires state=ACKNOWLEDGED_COMPLETED and a present "
                "result_commit"
            )
        if self.result_commit is not None and self.state not in (
            WorkItemState.RESULT_COMMITTED,
            WorkItemState.ACKNOWLEDGED_COMPLETED,
        ):
            raise InvalidDistributedProvenanceError(
                "result_commit may only be present when state is RESULT_COMMITTED or "
                "ACKNOWLEDGED_COMPLETED"
            )
        if is_terminal(self.state) and self.terminal_disposition is None:
            raise InvalidDistributedProvenanceError(
                f"state {self.state.value!r} is terminal and requires a terminal_disposition"
            )
        if not is_terminal(self.state) and self.terminal_disposition is not None:
            raise InvalidDistributedProvenanceError(
                f"state {self.state.value!r} is not terminal but carries a terminal_disposition"
            )
        if self.cancellation_scope is not None and self.state != WorkItemState.CANCELLED:
            raise InvalidDistributedProvenanceError(
                "cancellation_scope may only be present when state is CANCELLED"
            )

    @property
    def acknowledgement_eligible(self) -> bool:
        """``True`` iff a durable, checksum-verified result commit is
        present and not yet acknowledged -- "acknowledgement occurs only
        after durable, checksum-verified result commit," expressed as a
        derived property rather than a separate mutable flag, so it can
        never drift out of sync with ``state``/``result_commit``."""
        return (
            self.state == WorkItemState.RESULT_COMMITTED
            and self.result_commit is not None
            and not self.acknowledged
        )


def _new_record(
    scientific_work_id: str, distributed_run_context_checksum: str, reservation_id: str
) -> AuthoritativeWorkRecord:
    return AuthoritativeWorkRecord(
        scientific_work_id=scientific_work_id,
        distributed_run_context_checksum=distributed_run_context_checksum,
        reservation_id=reservation_id,
        state=WorkItemState.PENDING_AVAILABLE,
        revision=0,
        current_lease_generation=0,
        worker_participant_id=None,
        worker_context_checksum=None,
        cancellation_scope=None,
        result_commit=None,
        acknowledged=False,
        terminal_disposition=None,
        retry_count=0,
        retry_limit=DEFAULT_RETRY_LIMIT,
    )


class AtomicWorkStore:
    """Synthetic, single-process, lock-protected realization of the
    single-authoritative-revisioned-record contract this module's own
    docstring establishes. Every public method here performs its entire
    read-validate-write sequence while holding one internal lock -- from
    the perspective of competing callers, each method call is
    indivisible."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, AuthoritativeWorkRecord] = {}

    def create_if_absent(
        self,
        scientific_work_id: str,
        distributed_run_context_checksum: str,
        reservation_id: str,
        reservation_validator: Callable[[str], bool],
    ) -> AuthoritativeWorkRecord:
        """Create a fresh, ``PENDING_AVAILABLE``, revision-0 record bound
        to ``reservation_id`` if none exists yet; idempotently return the
        existing record otherwise (never overwrites, and does not
        re-validate the reservation on the idempotent-return path -- it
        was already validated when the record was first created).

        ``reservation_validator(reservation_id)`` must return ``True`` for
        a *new* record to be created -- "reservation before admission" is
        enforced here structurally, not merely by calling-convention.
        Raises :class:`InvalidReservationError` if it returns ``False``:
        no record is created, and the reservation itself is left
        untouched (the caller may retry once the reservation is valid, or
        may instead release it)."""
        with self._lock:
            existing = self._records.get(scientific_work_id)
            if existing is not None:
                return existing
            if not reservation_validator(reservation_id):
                raise InvalidReservationError(
                    f"reservation_id {reservation_id!r} is not currently valid -- an "
                    "authoritative work record cannot be created without a currently reserved "
                    "budget/worker-capacity reservation"
                )
            record = _new_record(
                scientific_work_id, distributed_run_context_checksum, reservation_id
            )
            self._records[scientific_work_id] = record
            return record

    def read(self, scientific_work_id: str) -> AuthoritativeWorkRecord:
        """The current authoritative record and its revision."""
        with self._lock:
            record = self._records.get(scientific_work_id)
        if record is None:
            raise WorkRecordNotFoundError(f"no work record for {scientific_work_id!r}")
        return record

    def _atomic_update(
        self,
        scientific_work_id: str,
        expected_revision: int,
        mutate: Callable[[AuthoritativeWorkRecord], AuthoritativeWorkRecord],
    ) -> AuthoritativeWorkRecord:
        """The one compare-and-swap primitive every public mutating
        method below is built from: read the current record under the
        lock, reject on a revision mismatch, apply ``mutate`` (which may
        itself raise -- in which case nothing is written), and swap in
        the result with ``revision`` incremented by exactly one. The
        entire sequence holds the lock throughout, so no other call can
        observe or act on an intermediate state."""
        with self._lock:
            current = self._records.get(scientific_work_id)
            if current is None:
                raise WorkRecordNotFoundError(f"no work record for {scientific_work_id!r}")
            if current.revision != expected_revision:
                raise RevisionConflictError(
                    f"expected revision {expected_revision} for {scientific_work_id!r}, current "
                    f"revision is {current.revision}"
                )
            updated = mutate(current)
            new_record = dataclasses.replace(updated, revision=current.revision + 1)
            self._records[scientific_work_id] = new_record
            return new_record

    def acquire_lease(
        self,
        scientific_work_id: str,
        expected_revision: int,
        lease: Lease,
        *,
        reservation_validator: Callable[[str], bool],
    ) -> AuthoritativeWorkRecord:
        """Atomically transition ``PENDING_AVAILABLE`` (or ``RETRYABLE``,
        for reassignment) to ``LEASED``, binding ``lease``'s worker
        participant and requiring ``lease.lease_generation`` to be
        exactly one more than the record's current generation -- the
        coordinator-issued, monotonically-increasing fencing token.

        ``reservation_validator(current.reservation_id)`` is checked
        inside this same atomic step, before the ``LEASED`` transition is
        applied -- a work item can never become leaseable without a
        currently valid reservation, even if the reservation bound at
        creation time was released in the interim. Raises
        :class:`InvalidReservationError` if it returns ``False``; no
        state change is applied."""
        if lease.scientific_work_id != scientific_work_id:
            raise IdentityMismatchError(
                f"lease.scientific_work_id {lease.scientific_work_id!r} does not match "
                f"{scientific_work_id!r}"
            )

        def mutate(current: AuthoritativeWorkRecord) -> AuthoritativeWorkRecord:
            validate_transition(current.state, WorkItemState.LEASED)
            if not reservation_validator(current.reservation_id):
                raise InvalidReservationError(
                    f"reservation_id {current.reservation_id!r} bound to {scientific_work_id!r} "
                    "is no longer valid -- a work item cannot become leaseable without a "
                    "currently valid reservation"
                )
            if lease.lease_generation != current.current_lease_generation + 1:
                raise IdentityMismatchError(
                    f"lease_generation {lease.lease_generation} is not the next expected "
                    f"generation ({current.current_lease_generation + 1})"
                )
            return dataclasses.replace(
                current,
                state=WorkItemState.LEASED,
                current_lease_generation=lease.lease_generation,
                worker_participant_id=lease.worker_participant_id,
            )

        return self._atomic_update(scientific_work_id, expected_revision, mutate)

    def transition_to_executing(
        self, scientific_work_id: str, expected_revision: int
    ) -> AuthoritativeWorkRecord:
        """Atomically transition ``LEASED`` to ``EXECUTING``."""

        def mutate(current: AuthoritativeWorkRecord) -> AuthoritativeWorkRecord:
            validate_transition(current.state, WorkItemState.EXECUTING)
            return dataclasses.replace(current, state=WorkItemState.EXECUTING)

        return self._atomic_update(scientific_work_id, expected_revision, mutate)

    def renew_lease(
        self, scientific_work_id: str, expected_revision: int, renewal: LeaseRenewal
    ) -> AuthoritativeWorkRecord:
        """Atomically validate ``renewal`` against the record's current
        lease generation and worker participant (fencing) without
        changing ``state`` -- a heartbeat, never a state transition, so
        it is not governed by :func:`~src.distributed.state_machine.validate_transition`."""
        if renewal.scientific_work_id != scientific_work_id:
            raise IdentityMismatchError(
                f"renewal.scientific_work_id {renewal.scientific_work_id!r} does not match "
                f"{scientific_work_id!r}"
            )

        def mutate(current: AuthoritativeWorkRecord) -> AuthoritativeWorkRecord:
            if current.state not in (WorkItemState.LEASED, WorkItemState.EXECUTING):
                raise IllegalStateTransitionError(
                    f"cannot renew a lease while state is {current.state.value!r}"
                )
            if renewal.worker_participant_id != current.worker_participant_id:
                raise IdentityMismatchError(
                    f"renewal.worker_participant_id {renewal.worker_participant_id!r} does not "
                    f"match the currently leased worker {current.worker_participant_id!r}"
                )
            validate_fencing(current.current_lease_generation, renewal.lease_generation)
            return current

        return self._atomic_update(scientific_work_id, expected_revision, mutate)

    def mark_retryable(
        self, scientific_work_id: str, expected_revision: int
    ) -> AuthoritativeWorkRecord:
        """Atomically transition ``LEASED``/``EXECUTING`` to
        ``RETRYABLE`` (lease expiry or execution crash detected),
        incrementing ``retry_count``."""

        def mutate(current: AuthoritativeWorkRecord) -> AuthoritativeWorkRecord:
            validate_transition(current.state, WorkItemState.RETRYABLE)
            return dataclasses.replace(
                current,
                state=WorkItemState.RETRYABLE,
                retry_count=current.retry_count + 1,
            )

        return self._atomic_update(scientific_work_id, expected_revision, mutate)

    def reassign_lease(
        self,
        scientific_work_id: str,
        expected_revision: int,
        new_lease: Lease,
        *,
        reservation_validator: Callable[[str], bool],
    ) -> AuthoritativeWorkRecord:
        """Atomically transition ``RETRYABLE`` to ``LEASED`` under a
        fresh, strictly higher lease generation -- reassignment after
        expiry, never a renewal. Re-validates the record's bound
        reservation in the same atomic step, exactly as
        :meth:`acquire_lease` does -- a redelivered/reassigned work item
        is no more leaseable without a valid reservation than a
        first-time lease is."""
        if new_lease.scientific_work_id != scientific_work_id:
            raise IdentityMismatchError(
                f"new_lease.scientific_work_id {new_lease.scientific_work_id!r} does not match "
                f"{scientific_work_id!r}"
            )

        def mutate(current: AuthoritativeWorkRecord) -> AuthoritativeWorkRecord:
            validate_transition(current.state, WorkItemState.LEASED)
            if not reservation_validator(current.reservation_id):
                raise InvalidReservationError(
                    f"reservation_id {current.reservation_id!r} bound to {scientific_work_id!r} "
                    "is no longer valid -- a work item cannot become leaseable without a "
                    "currently valid reservation"
                )
            if new_lease.lease_generation != current.current_lease_generation + 1:
                raise IdentityMismatchError(
                    f"reassignment lease_generation {new_lease.lease_generation} is not the "
                    f"next expected generation ({current.current_lease_generation + 1})"
                )
            return dataclasses.replace(
                current,
                state=WorkItemState.LEASED,
                current_lease_generation=new_lease.lease_generation,
                worker_participant_id=new_lease.worker_participant_id,
            )

        return self._atomic_update(scientific_work_id, expected_revision, mutate)

    def dead_letter(
        self, scientific_work_id: str, expected_revision: int, disposition: TerminalDisposition
    ) -> AuthoritativeWorkRecord:
        """Atomically transition ``RETRYABLE`` to ``DEAD_LETTERED``,
        recording ``disposition`` as the closed, typed terminal outcome."""
        if disposition.scientific_work_id != scientific_work_id:
            raise IdentityMismatchError(
                f"disposition.scientific_work_id {disposition.scientific_work_id!r} does not "
                f"match {scientific_work_id!r}"
            )

        def mutate(current: AuthoritativeWorkRecord) -> AuthoritativeWorkRecord:
            validate_transition(current.state, WorkItemState.DEAD_LETTERED)
            return dataclasses.replace(
                current, state=WorkItemState.DEAD_LETTERED, terminal_disposition=disposition
            )

        return self._atomic_update(scientific_work_id, expected_revision, mutate)

    def request_cancellation(
        self, scientific_work_id: str, expected_revision: int, request: CancellationRequest
    ) -> AuthoritativeWorkRecord:
        """Atomically cancel the work item -- legal only from
        ``PENDING_AVAILABLE`` (``BEFORE_ADMISSION``) or ``LEASED``/
        ``EXECUTING``/``RETRYABLE`` (``AFTER_LEASE``); illegal, and
        rejected by :func:`~src.distributed.state_machine.validate_transition`
        itself, from ``RESULT_COMMITTED``/``ACKNOWLEDGED_COMPLETED`` --
        terminal evidence cannot be erased by a cancellation race."""
        if request.scientific_work_id != scientific_work_id:
            raise IdentityMismatchError(
                f"request.scientific_work_id {request.scientific_work_id!r} does not match "
                f"{scientific_work_id!r}"
            )

        def mutate(current: AuthoritativeWorkRecord) -> AuthoritativeWorkRecord:
            expected_scope = (
                CancellationScope.BEFORE_ADMISSION
                if current.state == WorkItemState.PENDING_AVAILABLE
                else CancellationScope.AFTER_LEASE
            )
            if request.cancellation_scope != expected_scope:
                raise IdentityMismatchError(
                    f"cancellation_scope {request.cancellation_scope!r} does not match the "
                    f"expected {expected_scope!r} for state {current.state.value!r}"
                )
            validate_transition(current.state, WorkItemState.CANCELLED)
            disposition_kind = (
                TerminalDispositionKind.CANCELLED_BEFORE_ADMISSION
                if expected_scope == CancellationScope.BEFORE_ADMISSION
                else TerminalDispositionKind.CANCELLED_AFTER_LEASE
            )
            disposition = TerminalDisposition(
                distributed_orchestration_schema_version=(
                    request.distributed_orchestration_schema_version
                ),
                checksum_algorithm_version=request.checksum_algorithm_version,
                scientific_work_id=scientific_work_id,
                disposition=disposition_kind,
                disposition_reason=TerminalDispositionReason.USER_REQUESTED_CANCELLATION,
                attempt_count=current.retry_count,
            )
            return dataclasses.replace(
                current,
                state=WorkItemState.CANCELLED,
                cancellation_scope=request.cancellation_scope,
                terminal_disposition=disposition,
            )

        return self._atomic_update(scientific_work_id, expected_revision, mutate)

    def acknowledge(
        self, scientific_work_id: str, expected_revision: int, ack: Acknowledgement
    ) -> AuthoritativeWorkRecord:
        """Atomically transition ``RESULT_COMMITTED`` to
        ``ACKNOWLEDGED_COMPLETED`` -- only reachable when
        ``acknowledgement_eligible`` already held, and only when ``ack``
        names exactly the durable commit of record
        (:func:`~src.distributed.work_contracts.require_commit_before_ack`)."""
        if ack.scientific_work_id != scientific_work_id:
            raise IdentityMismatchError(
                f"ack.scientific_work_id {ack.scientific_work_id!r} does not match "
                f"{scientific_work_id!r}"
            )

        def mutate(current: AuthoritativeWorkRecord) -> AuthoritativeWorkRecord:
            validate_transition(current.state, WorkItemState.ACKNOWLEDGED_COMPLETED)
            if current.result_commit is None:
                raise IdentityMismatchError(
                    "cannot acknowledge: no durable result_commit present on the record"
                )
            require_commit_before_ack(current.result_commit, ack)
            disposition = TerminalDisposition(
                distributed_orchestration_schema_version=(
                    current.result_commit.distributed_orchestration_schema_version
                ),
                checksum_algorithm_version=current.result_commit.checksum_algorithm_version,
                scientific_work_id=scientific_work_id,
                disposition=TerminalDispositionKind.COMPLETED_ACKNOWLEDGED,
                disposition_reason=TerminalDispositionReason.NORMAL_COMPLETION,
                attempt_count=current.retry_count + 1,
            )
            return dataclasses.replace(
                current,
                state=WorkItemState.ACKNOWLEDGED_COMPLETED,
                acknowledged=True,
                terminal_disposition=disposition,
            )

        return self._atomic_update(scientific_work_id, expected_revision, mutate)

    def commit_result(
        self,
        scientific_work_id: str,
        expected_revision: int,
        attempt: ExecutionAttempt,
        commit: ResultCommit,
        artifact_resolver: Callable[[ArtifactReference], bool],
    ) -> AuthoritativeWorkRecord:
        """The atomic 8-step commit decision: verifies the work record
        and its revision (via the CAS this method is built on), the
        current state (``EXECUTING`` for a first commit, or
        ``RESULT_COMMITTED`` for an idempotent duplicate re-commit),
        the current lease generation/fencing token
        (:func:`~src.distributed.worker_contracts.validate_fencing`),
        scientific-work/distributed-run/worker-context/attempt identities,
        reconciles any existing result commit
        (:func:`~src.distributed.work_contracts.reconcile_result_commit`
        -- idempotent duplicates accepted, conflicting duplicates raise
        and abort with no state change), confirms the immutable result
        artifact is already durably present via ``artifact_resolver``
        (never returns/transports content itself), transitions state to
        ``RESULT_COMMITTED``, and establishes ``acknowledgement_eligible``
        -- all within one indivisible call."""
        if (
            attempt.scientific_work_id != scientific_work_id
            or commit.scientific_work_id != scientific_work_id
        ):
            raise IdentityMismatchError(
                "attempt/commit scientific_work_id does not match the record being committed to"
            )
        if commit.attempt_checksum != attempt.attempt_checksum:
            raise IdentityMismatchError(
                "commit.attempt_checksum does not match the supplied attempt's own checksum"
            )

        def mutate(current: AuthoritativeWorkRecord) -> AuthoritativeWorkRecord:
            if current.state not in (WorkItemState.EXECUTING, WorkItemState.RESULT_COMMITTED):
                raise IllegalStateTransitionError(
                    f"cannot commit a result while state is {current.state.value!r}"
                )
            if attempt.distributed_run_context_checksum != current.distributed_run_context_checksum:
                raise IdentityMismatchError(
                    "attempt.distributed_run_context_checksum does not match the record's own "
                    "distributed_run_context_checksum -- mixed-run attempt rejected"
                )
            if current.worker_participant_id is not None and (
                attempt.worker_participant_id != current.worker_participant_id
            ):
                raise IdentityMismatchError(
                    f"attempt.worker_participant_id {attempt.worker_participant_id!r} does not "
                    f"match the currently leased worker {current.worker_participant_id!r}"
                )
            validate_fencing(current.current_lease_generation, attempt.lease_generation)
            reconciliation = reconcile_result_commit(current.result_commit, commit)
            if not artifact_resolver(commit.result_artifact_reference):
                raise MissingArtifactReferenceError(
                    "commit.result_artifact_reference is not yet durably present in the "
                    "artifact store -- the artifact must be written before this commit"
                )
            validate_transition(current.state, WorkItemState.RESULT_COMMITTED)
            del reconciliation  # ACCEPTED_NEW vs IDEMPOTENT_DUPLICATE both proceed identically
            return dataclasses.replace(
                current,
                state=WorkItemState.RESULT_COMMITTED,
                result_commit=commit,
            )

        return self._atomic_update(scientific_work_id, expected_revision, mutate)


__all__ = [
    "DEFAULT_RETRY_LIMIT",
    "WorkRecordNotFoundError",
    "RevisionConflictError",
    "MissingArtifactReferenceError",
    "IdentityMismatchError",
    "InvalidReservationError",
    "AuthoritativeWorkRecord",
    "AtomicWorkStore",
]
