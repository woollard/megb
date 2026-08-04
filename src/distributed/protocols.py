"""MEGB-03H.2C.3B.2A: provider-neutral structural interfaces for the
storage/queue/registry/audit boundaries a future coordinator/worker engine
(MEGB-03H.2C.3B.2B, not this checkpoint) will implement.

Every interface here is a :class:`typing.Protocol` -- a structural
signature only, never a concrete implementation, never in-memory state,
never a thread/process pool. This checkpoint's own explicit non-goal is
"a working coordinator loop... queue polling... cloud adapters" -- these
Protocols exist so B.2B can implement (and this checkpoint's own tests can
exercise via a minimal synthetic fake, never a real backing store) against
a frozen, typed contract, without this module itself providing any
runtime behavior."""

from typing import Protocol

from src.distributed.state_machine import WorkItemState
from src.distributed.work_contracts import (
    Acknowledgement,
    ArtifactReference,
    CancellationRequest,
    QueueWorkMessage,
    ResultCommit,
    TerminalDisposition,
    WorkDescriptor,
)
from src.distributed.worker_contracts import Lease, LeaseRenewal, WorkerRegistration


class WorkQueueProtocol(Protocol):
    """The work-admission and delivery boundary. Mirrors the "Work
    admission and leasing" abstraction named in
    ``docs/architecture/gcp-distributed-reference-execution.md`` §3."""

    def publish(self, descriptor: WorkDescriptor) -> QueueWorkMessage:
        """Admit ``descriptor`` and return its initial, unleased
        :class:`QueueWorkMessage`."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def lease(self, message: QueueWorkMessage, lease: Lease) -> QueueWorkMessage:
        """Return the :class:`QueueWorkMessage` reflecting ``lease``
        having been issued against it."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def cancel(self, request: CancellationRequest) -> None:
        """Cancel the work item ``request`` names."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class ArtifactStoreProtocol(Protocol):
    """The immutable-artifact persistence boundary. Mirrors the
    "Object/artifact persistence" abstraction named in
    ``docs/architecture/gcp-distributed-reference-execution.md`` §3."""

    def resolve(self, reference: ArtifactReference) -> bool:
        """``True`` if ``reference`` names content this store actually
        holds -- never returns or transports the content itself through
        this interface."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class ResultStoreProtocol(Protocol):
    """The durable result-commit persistence boundary."""

    def get_result(self, scientific_work_id: str) -> ResultCommit | None:
        """The currently durable :class:`ResultCommit` for
        ``scientific_work_id``, or ``None`` if none exists yet."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def commit_result(self, commit: ResultCommit) -> ResultCommit:
        """Durably persist ``commit``, reconciling against any existing
        commit for the same work item (see
        :func:`~src.distributed.work_contracts.reconcile_result_commit`),
        and return the durable commit of record."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def acknowledge(self, ack: Acknowledgement) -> None:
        """Durably record ``ack`` against its already-committed result."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class LeaseStateStoreProtocol(Protocol):
    """The lease/state-machine persistence boundary."""

    def get_state(self, scientific_work_id: str) -> WorkItemState:
        """The current :class:`~src.distributed.state_machine.WorkItemState`
        for ``scientific_work_id``."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def transition(self, scientific_work_id: str, next_state: WorkItemState) -> None:
        """Durably transition ``scientific_work_id`` to ``next_state``,
        validated against
        :func:`~src.distributed.state_machine.validate_transition`."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def current_lease(self, scientific_work_id: str) -> Lease | None:
        """The currently valid :class:`Lease` for ``scientific_work_id``,
        or ``None`` if unleased."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def renew_lease(self, renewal: LeaseRenewal) -> Lease:
        """Apply ``renewal`` to the currently valid lease and return the
        renewed :class:`Lease`."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def record_terminal_disposition(self, disposition: TerminalDisposition) -> None:
        """Durably record ``disposition`` as this work item's final,
        closed outcome."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class WorkerRegistryProtocol(Protocol):
    """The worker-fleet membership boundary. Mirrors the
    "Worker-fleet control" abstraction named in
    ``docs/architecture/gcp-distributed-reference-execution.md`` §3."""

    def register(self, registration: WorkerRegistration) -> WorkerRegistration:
        """Admit ``registration`` and return the registry's own record of
        it."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def active_worker_participant_ids(self) -> tuple[str, ...]:
        """Every currently active worker's ``worker_participant_id``,
        deterministically ordered."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class AuditSinkProtocol(Protocol):
    """The safe-audit-event emission boundary."""

    def emit(self, event) -> None:  # type: ignore[no-untyped-def]
        """Durably emit a
        :class:`~src.distributed.safe_audit.SafeAuditEvent`. Typed as a
        bare parameter (rather than importing
        :mod:`~src.distributed.safe_audit`) to avoid a needless import
        cycle risk between this module and every other contract module
        it already depends on; callers pass a real ``SafeAuditEvent``."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


__all__ = [
    "WorkQueueProtocol",
    "ArtifactStoreProtocol",
    "ResultStoreProtocol",
    "LeaseStateStoreProtocol",
    "WorkerRegistryProtocol",
    "AuditSinkProtocol",
]
