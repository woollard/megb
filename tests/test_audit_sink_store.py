"""MEGB-03H.2C.3B.2B.1: construction/validation and behavior tests for
:mod:`src.distributed.audit_sink_store` -- especially that failure
behavior is explicit and can never falsely report successful
completion."""

import pytest

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.audit_sink_store import AuditSinkFailureError, InMemoryAuditSink
from src.distributed.safe_audit import SafeAuditEvent, SafeAuditEventType, build_safe_audit_event
from src.distributed.state_machine import WorkItemState


def _event(**overrides: object) -> SafeAuditEvent:
    fields: dict[str, object] = {
        "event_type": SafeAuditEventType.WORK_ADMITTED,
        "work_reference": "work-0000000000000001",
        "safe_run_identity": "env-logical-0000000000000001",
        "state_after": WorkItemState.PENDING_AVAILABLE,
        "logical_timestamp": 0,
    }
    fields.update(overrides)
    return build_safe_audit_event(**fields)  # type: ignore[arg-type]


def test_emit_appends_event() -> None:
    """Test emit appends event."""
    sink = InMemoryAuditSink()
    event = _event()
    sink.emit(event)
    assert sink.events() == (event,)


def test_emit_is_append_only_and_ordered() -> None:
    """Test emit is append only and ordered."""
    sink = InMemoryAuditSink()
    first = _event(logical_timestamp=0)
    second = _event(logical_timestamp=1)
    sink.emit(first)
    sink.emit(second)
    assert sink.events() == (first, second)


def test_emit_rejects_non_safe_audit_event() -> None:
    """Test emit rejects non safe audit event."""
    sink = InMemoryAuditSink()
    with pytest.raises(InvalidDistributedProvenanceError):
        sink.emit("not-an-event")  # type: ignore[arg-type]


def test_emit_failure_is_explicit_never_falsely_successful() -> None:
    """Test emit failure is explicit and the failed event is never
    silently recorded as if it had succeeded."""
    sink = InMemoryAuditSink(fail_after=1)
    sink.emit(_event(logical_timestamp=0))
    with pytest.raises(AuditSinkFailureError):
        sink.emit(_event(logical_timestamp=1))
    # exactly the one successful event is present -- the failed one never
    # silently landed
    assert len(sink.events()) == 1


def test_fail_after_zero_fails_the_very_first_emit() -> None:
    """Test fail after zero fails the very first emit."""
    sink = InMemoryAuditSink(fail_after=0)
    with pytest.raises(AuditSinkFailureError):
        sink.emit(_event())
    assert not sink.events()


def test_audit_sink_rejects_negative_fail_after() -> None:
    """Test audit sink rejects negative fail after."""
    with pytest.raises(InvalidDistributedProvenanceError):
        InMemoryAuditSink(fail_after=-1)


def test_events_returns_a_copy_not_the_live_internal_list() -> None:
    """Test events() returns an immutable snapshot -- callers cannot
    mutate the sink's own internal state through the returned tuple."""
    sink = InMemoryAuditSink()
    sink.emit(_event())
    events = sink.events()
    assert isinstance(events, tuple)
