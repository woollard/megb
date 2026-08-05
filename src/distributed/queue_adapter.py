"""MEGB-03H.2C.3B.2B.2: a bounded, in-memory, at-least-once work-queue
adapter structurally implementing
:class:`~src.distributed.protocols.WorkQueueProtocol`.

**At-least-once, not exactly-once:** :meth:`InMemoryAtLeastOnceQueue.receive`
may redeliver the same ``scientific_work_id`` under a fresh ``delivery_id``
if the previous delivery's visibility window elapses (per the injected
:class:`~src.distributed.clock.Clock`) before :meth:`ack` is called --
this is deliberate, matching the accepted authorization's own "no
exactly-once claim." Duplicate delivery is made harmless downstream by
:mod:`~src.distributed.coordinator`'s own idempotent commit-recovery path,
never by this queue pretending to deduplicate.

**Idempotent duplicate publish:** :meth:`publish` returns the existing
message for an already-published ``scientific_work_id`` rather than
creating a second one -- "duplicate queue publication remains harmless."

**Bounded:** construction takes ``max_in_flight`` -- :meth:`publish`
refuses (never blocks; no wall-clock wait) once that many
not-yet-acknowledged, not-cancelled messages exist, so this queue can
never accumulate unboundedly."""

import threading

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.clock import Clock
from src.distributed.work_contracts import (
    CancellationRequest,
    QueueWorkMessage,
    WorkDescriptor,
    work_descriptor_to_queue_message,
)
from src.distributed.worker_contracts import Lease


class QueueBackpressureError(InvalidDistributedProvenanceError):
    """Raised by :meth:`InMemoryAtLeastOnceQueue.publish` when admitting
    a new message would exceed ``max_in_flight`` -- backpressure, not an
    unbounded queue."""


class QueueMessageNotFoundError(InvalidDistributedProvenanceError):
    """Raised when an operation names a ``scientific_work_id`` this queue
    has no message for."""


class InMemoryAtLeastOnceQueue:
    """Synthetic, single-process, lock-protected, bounded at-least-once
    queue. Structurally implements
    :class:`~src.distributed.protocols.WorkQueueProtocol`
    (``publish``/``lease``/``cancel``), plus ``receive``/``ack`` for
    at-least-once worker-side delivery."""

    def __init__(
        self,
        clock: Clock,
        *,
        max_in_flight: int,
        visibility_timeout_ticks: int,
        routing_environment_class: str,
        routing_logical_environment_id: str,
    ) -> None:
        if not isinstance(max_in_flight, int) or isinstance(max_in_flight, bool) or (
            max_in_flight < 1
        ):
            raise InvalidDistributedProvenanceError(
                f"max_in_flight must be a positive int, got {max_in_flight!r}"
            )
        if (
            not isinstance(visibility_timeout_ticks, int)
            or isinstance(visibility_timeout_ticks, bool)
            or visibility_timeout_ticks < 1
        ):
            raise InvalidDistributedProvenanceError(
                f"visibility_timeout_ticks must be a positive int, got "
                f"{visibility_timeout_ticks!r}"
            )
        self._clock = clock
        self._max_in_flight = max_in_flight
        self._visibility_timeout_ticks = visibility_timeout_ticks
        self._routing_environment_class = routing_environment_class
        self._routing_logical_environment_id = routing_logical_environment_id
        self._lock = threading.Lock()
        self._messages: dict[str, QueueWorkMessage] = {}
        self._visible_at: dict[str, int] = {}
        self._acked: set[str] = set()
        self._cancelled: set[str] = set()
        self._delivery_counter = 0

    def _active_count_locked(self) -> int:
        return sum(
            1
            for work_id in self._messages
            if work_id not in self._acked and work_id not in self._cancelled
        )

    def publish(self, descriptor: WorkDescriptor) -> QueueWorkMessage:
        """Idempotent per ``scientific_work_id``; refuses (raises
        :class:`QueueBackpressureError`) rather than exceeding
        ``max_in_flight``."""
        with self._lock:
            existing = self._messages.get(descriptor.scientific_work_id)
            if existing is not None:
                return existing
            if self._active_count_locked() >= self._max_in_flight:
                raise QueueBackpressureError(
                    f"queue at capacity ({self._max_in_flight} in-flight); refusing to publish "
                    f"{descriptor.scientific_work_id!r}"
                )
            self._delivery_counter += 1
            message = work_descriptor_to_queue_message(
                descriptor,
                delivery_id=f"delivery-{descriptor.scientific_work_id}-{self._delivery_counter}",
                routing_environment_class=self._routing_environment_class,
                routing_logical_environment_id=self._routing_logical_environment_id,
            )
            self._messages[descriptor.scientific_work_id] = message
            self._visible_at[descriptor.scientific_work_id] = self._clock.now()
            return message

    def receive(self) -> QueueWorkMessage | None:
        """Return the oldest (by publish order) currently-visible,
        not-yet-acknowledged, not-cancelled message, redelivering under a
        fresh ``delivery_id`` if its previous visibility window has
        elapsed -- or ``None`` if nothing is currently deliverable."""
        with self._lock:
            now = self._clock.now()
            for work_id, message in self._messages.items():
                if work_id in self._acked or work_id in self._cancelled:
                    continue
                if self._visible_at[work_id] <= now:
                    self._delivery_counter += 1
                    redelivered = work_descriptor_to_queue_message(
                        WorkDescriptor(
                            distributed_orchestration_schema_version=(
                                message.distributed_orchestration_schema_version
                            ),
                            checksum_algorithm_version=message.checksum_algorithm_version,
                            scientific_work_id=message.scientific_work_id,
                            input_ordinal=message.input_ordinal,
                            distributed_run_context_checksum=(
                                message.distributed_run_context_checksum
                            ),
                            candidate_artifact_reference=message.candidate_artifact_reference,
                        ),
                        delivery_id=f"delivery-{work_id}-{self._delivery_counter}",
                        routing_environment_class=self._routing_environment_class,
                        routing_logical_environment_id=self._routing_logical_environment_id,
                        lease_generation=message.lease_generation,
                        attempt_checksum=message.attempt_checksum,
                    )
                    self._messages[work_id] = redelivered
                    self._visible_at[work_id] = now + self._visibility_timeout_ticks
                    return redelivered
            return None

    def ack(self, scientific_work_id: str) -> None:
        """Acknowledge delivery of ``scientific_work_id`` -- idempotent;
        after this, :meth:`receive` will never return it again."""
        with self._lock:
            if scientific_work_id not in self._messages:
                raise QueueMessageNotFoundError(
                    f"no queue message for {scientific_work_id!r}"
                )
            self._acked.add(scientific_work_id)

    def lease(self, message: QueueWorkMessage, lease: Lease) -> QueueWorkMessage:
        """Record ``lease``'s generation/attempt against this queue's own
        projection of ``message`` and extend its visibility window --
        this is queue-side bookkeeping only, never the authoritative
        lease decision (that is
        :meth:`~src.distributed.protocols.AtomicWorkStoreProtocol.acquire_lease`'s
        role alone)."""
        with self._lock:
            if message.scientific_work_id not in self._messages:
                raise QueueMessageNotFoundError(
                    f"no queue message for {message.scientific_work_id!r}"
                )
            leased = work_descriptor_to_queue_message(
                WorkDescriptor(
                    distributed_orchestration_schema_version=(
                        message.distributed_orchestration_schema_version
                    ),
                    checksum_algorithm_version=message.checksum_algorithm_version,
                    scientific_work_id=message.scientific_work_id,
                    input_ordinal=message.input_ordinal,
                    distributed_run_context_checksum=message.distributed_run_context_checksum,
                    candidate_artifact_reference=message.candidate_artifact_reference,
                ),
                delivery_id=message.delivery_id,
                routing_environment_class=self._routing_environment_class,
                routing_logical_environment_id=self._routing_logical_environment_id,
                lease_generation=lease.lease_generation,
                attempt_checksum=None,
            )
            self._messages[message.scientific_work_id] = leased
            self._visible_at[message.scientific_work_id] = (
                self._clock.now() + self._visibility_timeout_ticks
            )
            return leased

    def cancel(self, request: CancellationRequest) -> None:
        """Mark ``request.scientific_work_id`` cancelled at the queue
        level -- idempotent; :meth:`receive` will never return it again."""
        with self._lock:
            self._cancelled.add(request.scientific_work_id)

    def in_flight_count(self) -> int:
        """The current number of not-yet-acknowledged, not-cancelled
        messages -- for backpressure assertions in tests."""
        with self._lock:
            return self._active_count_locked()

    def is_published(self, scientific_work_id: str) -> bool:
        """``True`` iff a message for ``scientific_work_id`` currently
        exists in this queue (published, whether or not yet delivered,
        acknowledged, or cancelled) -- a read-only existence check used
        by :func:`~src.distributed.coordinator.diagnose_work_publication_binding`
        to detect the crash window between authoritative work-record
        creation and queue publication."""
        with self._lock:
            return scientific_work_id in self._messages


__all__ = [
    "QueueBackpressureError",
    "QueueMessageNotFoundError",
    "InMemoryAtLeastOnceQueue",
]
