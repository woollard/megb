"""MEGB-03H.2C.3B.2B.1: synthetic in-memory run-scoped worker-registration
store.

Reuses :class:`~src.distributed.worker_contracts.WorkerRegistration`
completely unchanged as the value type; this module adds only the
concrete, in-memory, duplicate-rejecting, retirable registry around it.
Raw infrastructure mappings (real instance IDs, hostnames) remain
entirely outside this store -- ``WorkerRegistration`` itself has no such
field, the same structural-absence guarantee established throughout
``src/distributed/``.

**MEGB-03H.2C.3B.2B.2 addition:** :meth:`InMemoryWorkerRegistry.get_registration`
-- a read-only getter for the full registration record, added purely
additively (no existing method's behavior changes) so the coordinator/
worker engine can validate a delivered queue message's
``distributed_run_context_checksum`` against the worker's own registered
one, never trusting the queue message alone for that binding."""

import threading
from enum import Enum

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.worker_contracts import WorkerRegistration


class WorkerRegistrationStatus(str, Enum):
    """Closed set of registry membership states."""

    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class DuplicateWorkerParticipantError(InvalidDistributedProvenanceError):
    """Raised when the same ``worker_participant_id`` is registered a
    second time with different registration content -- a duplicate
    *observation* of the same participant identity, rejected rather than
    silently overwritten, mirroring
    :class:`~src.distributed.identity.DuplicateWorkerProvenanceError`'s
    own established judgment-by-participant-id-only rule (not by
    configuration similarity)."""


class WorkerContextMismatchError(InvalidDistributedProvenanceError):
    """Raised when the same ``worker_participant_id`` re-registers under
    a different ``distributed_run_context_checksum`` -- a worker-context/
    run-context consistency violation."""


class WorkerNotRegisteredError(InvalidDistributedProvenanceError):
    """Raised when ``retire`` names a ``worker_participant_id`` this
    registry has never seen."""


class InMemoryWorkerRegistry:
    """Synthetic, single-process, lock-protected worker-fleet membership
    store for one distributed run."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._registrations: dict[str, WorkerRegistration] = {}
        self._status: dict[str, WorkerRegistrationStatus] = {}

    def register(self, registration: WorkerRegistration) -> WorkerRegistration:
        """Admit ``registration``. An exact-match repeat registration
        (identical content, same ``registration_checksum``) is an
        idempotent no-op. A different ``distributed_run_context_checksum``
        under the same participant id is rejected as a context
        mismatch; different content under the same participant id and
        run context is rejected as a duplicate-participant conflict --
        never silently overwritten."""
        if not isinstance(registration, WorkerRegistration):
            raise InvalidDistributedProvenanceError(
                f"registration must be a WorkerRegistration, got {registration!r}"
            )
        with self._lock:
            existing = self._registrations.get(registration.worker_participant_id)
            if existing is not None:
                if (
                    existing.distributed_run_context_checksum
                    != registration.distributed_run_context_checksum
                ):
                    raise WorkerContextMismatchError(
                        f"worker_participant_id {registration.worker_participant_id!r} is "
                        f"already registered under a different distributed_run_context_checksum"
                    )
                if existing.registration_checksum != registration.registration_checksum:
                    raise DuplicateWorkerParticipantError(
                        f"worker_participant_id {registration.worker_participant_id!r} is "
                        f"already registered with different content -- duplicate participant "
                        f"observation rejected"
                    )
                return existing
            self._registrations[registration.worker_participant_id] = registration
            self._status[registration.worker_participant_id] = WorkerRegistrationStatus.ACTIVE
            return registration

    def active_worker_participant_ids(self) -> tuple[str, ...]:
        """Every currently ``ACTIVE`` worker's ``worker_participant_id``,
        deterministically sorted."""
        with self._lock:
            return tuple(
                sorted(
                    participant_id
                    for participant_id, status in self._status.items()
                    if status == WorkerRegistrationStatus.ACTIVE
                )
            )

    def get_registration(self, worker_participant_id: str) -> WorkerRegistration:
        """The full, currently-registered :class:`WorkerRegistration` for
        ``worker_participant_id`` (whether ``ACTIVE`` or ``RETIRED``)."""
        with self._lock:
            registration = self._registrations.get(worker_participant_id)
        if registration is None:
            raise WorkerNotRegisteredError(f"no registration for {worker_participant_id!r}")
        return registration

    def registration_status(self, worker_participant_id: str) -> WorkerRegistrationStatus:
        """The current :class:`WorkerRegistrationStatus` for
        ``worker_participant_id``."""
        with self._lock:
            status = self._status.get(worker_participant_id)
        if status is None:
            raise WorkerNotRegisteredError(f"no registration for {worker_participant_id!r}")
        return status

    def retire(self, worker_participant_id: str) -> None:
        """Safely retire an already-registered worker -- idempotent if
        already retired."""
        with self._lock:
            if worker_participant_id not in self._registrations:
                raise WorkerNotRegisteredError(f"no registration for {worker_participant_id!r}")
            self._status[worker_participant_id] = WorkerRegistrationStatus.RETIRED


__all__ = [
    "WorkerRegistrationStatus",
    "DuplicateWorkerParticipantError",
    "WorkerContextMismatchError",
    "WorkerNotRegisteredError",
    "InMemoryWorkerRegistry",
]
