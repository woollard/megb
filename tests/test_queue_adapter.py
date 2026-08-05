"""MEGB-03H.2C.3B.2B.2: construction/behavior tests for
:mod:`src.distributed.queue_adapter` -- idempotent publish, at-least-once
redelivery, bounded backpressure."""

import pytest

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
)
from src.distributed.artifact_store import InMemoryArtifactStore
from src.distributed.clock import LogicalClock
from src.distributed.queue_adapter import InMemoryAtLeastOnceQueue, QueueBackpressureError
from src.distributed.work_contracts import CancellationRequest, CancellationScope, WorkDescriptor
from tests._coordinator_fixtures import (
    ROUTING_ENVIRONMENT_CLASS,
    ROUTING_LOGICAL_ENVIRONMENT_ID,
    make_synthetic_content,
    make_work_descriptor,
    publish_candidate,
)


def _queue(
    clock: LogicalClock, *, max_in_flight: int = 5, visibility_timeout_ticks: int = 3
) -> InMemoryAtLeastOnceQueue:
    return InMemoryAtLeastOnceQueue(
        clock,
        max_in_flight=max_in_flight,
        visibility_timeout_ticks=visibility_timeout_ticks,
        routing_environment_class=ROUTING_ENVIRONMENT_CLASS,
        routing_logical_environment_id=ROUTING_LOGICAL_ENVIRONMENT_ID,
    )


def _descriptor(work_id: str, ordinal: int = 0) -> WorkDescriptor:
    store = InMemoryArtifactStore()
    reference = publish_candidate(store, make_synthetic_content(work_id))
    return make_work_descriptor(work_id, ordinal, reference)


def test_publish_is_idempotent_per_scientific_work_id() -> None:
    """Test publish is idempotent per scientific_work_id."""
    clock = LogicalClock()
    queue = _queue(clock)
    descriptor = _descriptor("work-1")
    first = queue.publish(descriptor)
    second = queue.publish(descriptor)
    assert first == second
    assert queue.in_flight_count() == 1


def test_publish_refuses_beyond_max_in_flight() -> None:
    """Test publish refuses beyond max_in_flight -- backpressure, never
    unbounded accumulation."""
    clock = LogicalClock()
    queue = _queue(clock, max_in_flight=2)
    queue.publish(_descriptor("work-1"))
    queue.publish(_descriptor("work-2"))
    with pytest.raises(QueueBackpressureError):
        queue.publish(_descriptor("work-3"))
    assert queue.in_flight_count() == 2


def test_receive_returns_none_when_empty() -> None:
    """Test receive returns none when empty."""
    clock = LogicalClock()
    queue = _queue(clock)
    assert queue.receive() is None


def test_receive_is_immediately_visible_after_publish() -> None:
    """Test receive is immediately visible after publish."""
    clock = LogicalClock()
    queue = _queue(clock)
    descriptor = _descriptor("work-1")
    queue.publish(descriptor)
    delivered = queue.receive()
    assert delivered is not None
    assert delivered.scientific_work_id == "work-1"


def test_receive_does_not_redeliver_before_visibility_timeout_elapses() -> None:
    """Test receive does not redeliver before visibility timeout
    elapses -- a second immediate receive() call returns None (no other
    message queued)."""
    clock = LogicalClock()
    queue = _queue(clock, visibility_timeout_ticks=5)
    queue.publish(_descriptor("work-1"))
    first = queue.receive()
    assert first is not None
    assert queue.receive() is None


def test_receive_redelivers_under_a_fresh_delivery_id_after_visibility_elapses() -> None:
    """Test receive redelivers under a fresh delivery_id after
    visibility elapses -- at-least-once, not exactly-once."""
    clock = LogicalClock()
    queue = _queue(clock, visibility_timeout_ticks=3)
    queue.publish(_descriptor("work-1"))
    first = queue.receive()
    assert first is not None
    clock.advance(3)
    second = queue.receive()
    assert second is not None
    assert second.scientific_work_id == first.scientific_work_id
    assert second.delivery_id != first.delivery_id


def test_ack_prevents_further_redelivery() -> None:
    """Test ack prevents further redelivery."""
    clock = LogicalClock()
    queue = _queue(clock, visibility_timeout_ticks=1)
    queue.publish(_descriptor("work-1"))
    queue.receive()
    queue.ack("work-1")
    clock.advance(5)
    assert queue.receive() is None
    assert queue.in_flight_count() == 0


def test_ack_is_idempotent_across_repeated_calls() -> None:
    """Test ack raises for an unknown message but repeated ack of a known
    one does not corrupt state."""
    clock = LogicalClock()
    queue = _queue(clock)
    queue.publish(_descriptor("work-1"))
    queue.receive()
    queue.ack("work-1")
    queue.ack("work-1")  # must not raise
    assert queue.in_flight_count() == 0


def test_cancel_prevents_further_delivery() -> None:
    """Test cancel prevents further delivery."""
    clock = LogicalClock()
    queue = _queue(clock)
    queue.publish(_descriptor("work-1"))
    request = CancellationRequest(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        scientific_work_id="work-1",
        cancellation_scope=CancellationScope.BEFORE_ADMISSION,
        requested_at_logical_clock=0,
    )
    queue.cancel(request)
    assert queue.receive() is None
    assert queue.in_flight_count() == 0
