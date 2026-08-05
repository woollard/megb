"""MEGB-03H.2C.3B.2B.2: construction/behavior tests for
:mod:`src.distributed.cancellation`."""

import pytest

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.cancellation import CancellationController


def test_is_cancelled_false_before_any_request() -> None:
    """Test is_cancelled false before any request."""
    controller = CancellationController()
    assert controller.is_cancelled("work-1") is False


def test_request_cancellation_is_observed() -> None:
    """Test request_cancellation is observed."""
    controller = CancellationController()
    controller.request_cancellation("work-1")
    assert controller.is_cancelled("work-1") is True


def test_cancellation_is_scoped_to_its_own_work_id() -> None:
    """Test cancellation is scoped to its own work id -- cancelling one
    work item never cancels an unrelated one."""
    controller = CancellationController()
    controller.request_cancellation("work-1")
    assert controller.is_cancelled("work-2") is False


def test_request_cancellation_is_idempotent() -> None:
    """Test request_cancellation is idempotent."""
    controller = CancellationController()
    controller.request_cancellation("work-1")
    controller.request_cancellation("work-1")  # must not raise
    assert controller.is_cancelled("work-1") is True


def test_token_for_reflects_the_controllers_own_state() -> None:
    """Test token_for reflects the controller's own state."""
    controller = CancellationController()
    token = controller.token_for("work-1")
    assert token.is_cancelled() is False
    controller.request_cancellation("work-1")
    assert token.is_cancelled() is True


def test_token_for_rejects_an_empty_work_id() -> None:
    """Test token_for rejects an empty work id."""
    controller = CancellationController()
    with pytest.raises(InvalidDistributedProvenanceError):
        controller.token_for("")
