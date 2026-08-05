"""MEGB-03H.2C.3B.2B.2: a recoverable, in-memory, reconciliation-aware
safe-audit outbox.

## Mandatory audit/outbox transaction-boundary audit (recorded here, per
this checkpoint's own authorization, mirroring
:mod:`~src.distributed.atomic_work_store`'s own precedent of recording its
audit inline rather than in a separate document)

**Question audited:** can the accepted protocols express "the
authoritative state transition that installs a result must also install a
safe audit intent" without an unsafe check-then-write or an
implementation-specific cast?

**Finding: yes, via the same write-before-CAS pattern this project
already established for immutable result artifacts** (see
:mod:`~src.distributed.atomic_work_store`'s own module docstring: "immutable,
content-addressed result artifacts may be durably written *before* that
CAS"). This module's :meth:`InMemoryAuditOutbox.enqueue` is called
**before** the corresponding
:meth:`~src.distributed.protocols.AtomicWorkStoreProtocol.commit_result`
(or ``request_cancellation``, or ``create_if_absent``) call, carrying an
optional *reconciliation clause* -- the exact ``expected_state``/
``expected_result_content_checksum`` the underlying authoritative mutation
was attempting to produce. :meth:`InMemoryAuditOutbox.dispatch_pending`
never delivers an entry whose reconciliation clause does not match the
authoritative record's *actual current* state, read fresh via
:meth:`~src.distributed.protocols.AtomicWorkStoreProtocol.read` at dispatch
time -- exactly mirroring how a losing, already-written result artifact
remains present but unreferenced and harmless after a lost CAS. This is
**not** literal single-transaction atomicity (this module and
``AtomicWorkStore`` are two independent, separately-locked stores, and no
claim of cross-store atomicity is made); it is the same deterministic,
recoverable two-step protocol this project's own reservation/work-creation
correction already established, applied to audit intent instead of budget
reservation.

**Consequence:** a crash between ``enqueue`` and the authoritative
mutation leaves a permanently PENDING, never-reconciling, harmless orphan
entry (analogous to an orphaned, unreferenced result artifact) -- it is
never delivered, and its presence never implies the mutation happened.
Audit-sink failure after a real, successful mutation leaves the entry
PENDING for retry, without altering authoritative state or re-invoking any
executor -- dispatch never calls any state-mutating method, only
``read()``. No change to any accepted B.2A/B.2B.1 contract was needed."""

import threading
from dataclasses import dataclass
from enum import Enum

from src.distributed._checksums import (
    InvalidDistributedProvenanceError,
    require_nonempty_str as _require_nonempty_str,
)
from src.distributed.atomic_work_store import WorkRecordNotFoundError
from src.distributed.audit_sink_store import AuditSinkFailureError
from src.distributed.protocols import AtomicWorkStoreProtocol, AuditSinkProtocol
from src.distributed.safe_audit import SafeAuditEvent
from src.distributed.state_machine import WorkItemState


class AuditOutboxFullError(InvalidDistributedProvenanceError):
    """Raised when enqueueing a new entry would exceed the outbox's own
    bound on pending entries -- backpressure, never unbounded
    accumulation."""


class AuditOutboxEntryStatus(str, Enum):
    """Closed set of outbox entry states."""

    PENDING = "PENDING"
    DELIVERED = "DELIVERED"


@dataclass(frozen=True)
class AuditOutboxEntry:
    """One outbox entry. ``outbox_key`` is the idempotency key --
    re-enqueueing the same key is a harmless no-op, never a duplicate.
    The three ``reconciliation_*`` fields are the optional clause
    :meth:`InMemoryAuditOutbox.dispatch_pending` checks against the
    authoritative store before ever delivering this entry; all ``None``
    means "deliver unconditionally" (used for events with no
    corresponding authoritative mutation that could fail, e.g. a policy
    refusal recorded before any work record exists)."""

    outbox_key: str
    event: SafeAuditEvent
    status: AuditOutboxEntryStatus
    reconciliation_scientific_work_id: str | None
    reconciliation_expected_state: WorkItemState | None
    reconciliation_expected_result_content_checksum: str | None

    def __post_init__(self) -> None:
        _require_nonempty_str(self, "outbox_key")
        if not isinstance(self.event, SafeAuditEvent):
            raise InvalidDistributedProvenanceError(
                f"event must be a SafeAuditEvent, got {self.event!r}"
            )
        if not isinstance(self.status, AuditOutboxEntryStatus):
            raise InvalidDistributedProvenanceError(
                f"status must be an AuditOutboxEntryStatus, got {self.status!r}"
            )
        if self.reconciliation_expected_state is not None and not isinstance(
            self.reconciliation_expected_state, WorkItemState
        ):
            raise InvalidDistributedProvenanceError(
                "reconciliation_expected_state must be a WorkItemState or None"
            )
        has_reconciliation = self.reconciliation_scientific_work_id is not None
        has_state_or_checksum = (
            self.reconciliation_expected_state is not None
            or self.reconciliation_expected_result_content_checksum is not None
        )
        if has_state_or_checksum and not has_reconciliation:
            raise InvalidDistributedProvenanceError(
                "reconciliation_expected_state/result_content_checksum require "
                "reconciliation_scientific_work_id to also be present"
            )


@dataclass(frozen=True)
class AuditDispatchSummary:
    """The outcome of one :meth:`InMemoryAuditOutbox.dispatch_pending`
    call."""

    delivered_keys: tuple[str, ...]
    still_pending_keys: tuple[str, ...]
    sink_failed_keys: tuple[str, ...]


class InMemoryAuditOutbox:
    """Synthetic, single-process, lock-protected, bounded, idempotent,
    reconciliation-aware audit outbox."""

    def __init__(self, *, max_pending: int) -> None:
        if not isinstance(max_pending, int) or isinstance(max_pending, bool) or max_pending < 1:
            raise InvalidDistributedProvenanceError(
                f"max_pending must be a positive int, got {max_pending!r}"
            )
        self._max_pending = max_pending
        self._lock = threading.Lock()
        self._entries: dict[str, AuditOutboxEntry] = {}

    def enqueue(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        outbox_key: str,
        event: SafeAuditEvent,
        *,
        reconciliation_scientific_work_id: str | None = None,
        reconciliation_expected_state: WorkItemState | None = None,
        reconciliation_expected_result_content_checksum: str | None = None,
    ) -> AuditOutboxEntry:
        """Idempotently enqueue ``event`` under ``outbox_key``. Raises
        :class:`AuditOutboxFullError` if this would exceed
        ``max_pending`` pending entries -- backpressure applied before
        the corresponding authoritative mutation is even attempted."""
        with self._lock:
            existing = self._entries.get(outbox_key)
            if existing is not None:
                return existing
            pending_count = sum(
                1
                for entry in self._entries.values()
                if entry.status == AuditOutboxEntryStatus.PENDING
            )
            if pending_count >= self._max_pending:
                raise AuditOutboxFullError(
                    f"audit outbox at capacity ({self._max_pending} pending); refusing to "
                    f"enqueue {outbox_key!r}"
                )
            entry = AuditOutboxEntry(
                outbox_key=outbox_key,
                event=event,
                status=AuditOutboxEntryStatus.PENDING,
                reconciliation_scientific_work_id=reconciliation_scientific_work_id,
                reconciliation_expected_state=reconciliation_expected_state,
                reconciliation_expected_result_content_checksum=(
                    reconciliation_expected_result_content_checksum
                ),
            )
            self._entries[outbox_key] = entry
            return entry

    def _reconciles_locked(
        self, entry: AuditOutboxEntry, work_store: AtomicWorkStoreProtocol
    ) -> bool:
        if entry.reconciliation_scientific_work_id is None:
            return True
        try:
            record = work_store.read(entry.reconciliation_scientific_work_id)
        except WorkRecordNotFoundError:
            return False
        if (
            entry.reconciliation_expected_state is not None
            and record.state != entry.reconciliation_expected_state
        ):
            return False
        if entry.reconciliation_expected_result_content_checksum is not None:
            if (
                record.result_commit is None
                or record.result_commit.result_content_checksum
                != entry.reconciliation_expected_result_content_checksum
            ):
                return False
        return True

    def dispatch_pending(
        self, sink: AuditSinkProtocol, work_store: AtomicWorkStoreProtocol
    ) -> AuditDispatchSummary:
        """Attempt to deliver every currently PENDING, reconciling entry
        to ``sink``. Never mutates ``work_store`` -- only ``read()``.
        A sink failure leaves that entry PENDING (retryable later);
        an entry whose reconciliation clause does not (yet, or ever)
        match ``work_store``'s current state is left PENDING without
        even attempting delivery."""
        delivered: list[str] = []
        still_pending: list[str] = []
        sink_failed: list[str] = []
        with self._lock:
            pending_keys = [
                key
                for key, entry in self._entries.items()
                if entry.status == AuditOutboxEntryStatus.PENDING
            ]
            for key in pending_keys:
                entry = self._entries[key]
                if not self._reconciles_locked(entry, work_store):
                    still_pending.append(key)
                    continue
                try:
                    sink.emit(entry.event)
                except AuditSinkFailureError:
                    sink_failed.append(key)
                    continue
                self._entries[key] = AuditOutboxEntry(
                    outbox_key=entry.outbox_key,
                    event=entry.event,
                    status=AuditOutboxEntryStatus.DELIVERED,
                    reconciliation_scientific_work_id=entry.reconciliation_scientific_work_id,
                    reconciliation_expected_state=entry.reconciliation_expected_state,
                    reconciliation_expected_result_content_checksum=(
                        entry.reconciliation_expected_result_content_checksum
                    ),
                )
                delivered.append(key)
        return AuditDispatchSummary(
            delivered_keys=tuple(delivered),
            still_pending_keys=tuple(still_pending),
            sink_failed_keys=tuple(sink_failed),
        )

    def entries(self) -> tuple[AuditOutboxEntry, ...]:
        """Every entry, delivered or pending, for reconciliation/
        inspection."""
        with self._lock:
            return tuple(self._entries.values())

    def pending_count(self) -> int:
        """The current number of PENDING entries."""
        with self._lock:
            return sum(
                1
                for entry in self._entries.values()
                if entry.status == AuditOutboxEntryStatus.PENDING
            )


__all__ = [
    "AuditOutboxFullError",
    "AuditOutboxEntryStatus",
    "AuditOutboxEntry",
    "AuditDispatchSummary",
    "InMemoryAuditOutbox",
]
