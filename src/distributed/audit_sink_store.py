"""MEGB-03H.2C.3B.2B.1: synthetic in-memory append-only safe-audit sink.

**Failure behavior is explicit and can never falsely report successful
completion**: :meth:`InMemoryAuditSink.emit` either durably appends the
event and returns, or raises :class:`AuditSinkFailureError` -- there is
no third outcome where a caller is told the emit succeeded while the
event was silently dropped."""

import threading

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.safe_audit import SafeAuditEvent


class AuditSinkFailureError(InvalidDistributedProvenanceError):
    """Raised when the sink cannot durably record an event. Always
    raised, never swallowed -- a caller that does not see this exception
    is guaranteed the event was actually appended."""


class InMemoryAuditSink:
    """Synthetic, single-process, lock-protected append-only audit
    event log. ``fail_after`` (test-only) simulates a durable-write
    failure starting at the Nth ``emit`` call, to prove failure is
    explicit rather than silently absorbed."""

    def __init__(self, *, fail_after: int | None = None) -> None:
        if fail_after is not None and (
            not isinstance(fail_after, int) or isinstance(fail_after, bool) or fail_after < 0
        ):
            raise InvalidDistributedProvenanceError(
                f"fail_after must be a non-negative int or None, got {fail_after!r}"
            )
        self._lock = threading.Lock()
        self._events: list[SafeAuditEvent] = []
        self._fail_after = fail_after

    def emit(self, event: SafeAuditEvent) -> None:
        """Durably append ``event``, or raise
        :class:`AuditSinkFailureError` -- never both silently and
        never neither."""
        if not isinstance(event, SafeAuditEvent):
            raise InvalidDistributedProvenanceError(
                f"event must be a SafeAuditEvent, got {event!r}"
            )
        with self._lock:
            if self._fail_after is not None and len(self._events) >= self._fail_after:
                raise AuditSinkFailureError(
                    "simulated durable-write failure -- audit event NOT recorded"
                )
            self._events.append(event)

    def events(self) -> tuple[SafeAuditEvent, ...]:
        """Every durably-appended event, in append order."""
        with self._lock:
            return tuple(self._events)


__all__ = [
    "AuditSinkFailureError",
    "InMemoryAuditSink",
]
