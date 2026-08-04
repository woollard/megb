"""MEGB-03H.2C.3B.2A: complete legal/illegal state-transition matrix
tests for :mod:`src.distributed.state_machine`."""

import itertools

import pytest

from src.distributed.state_machine import (
    ALLOWED_TRANSITIONS,
    IllegalStateTransitionError,
    WorkItemState,
    is_terminal,
    validate_transition,
)

_ALL_LEGAL_EDGES = sorted(ALLOWED_TRANSITIONS, key=lambda pair: (pair[0].value, pair[1].value))


@pytest.mark.parametrize("current,next_state", _ALL_LEGAL_EDGES)
def test_every_legal_edge_is_accepted(
    current: WorkItemState, next_state: WorkItemState
) -> None:
    """Test every legal edge is accepted."""
    validate_transition(current, next_state)  # must not raise


@pytest.mark.parametrize(
    "current,next_state",
    [
        (current, next_state)
        for current, next_state in itertools.product(WorkItemState, WorkItemState)
        if (current, next_state) not in ALLOWED_TRANSITIONS
    ],
)
def test_every_illegal_edge_is_rejected(
    current: WorkItemState, next_state: WorkItemState
) -> None:
    """Test every illegal edge -- the full complement of the legal set
    over all 8x8 state pairs -- is rejected."""
    with pytest.raises(IllegalStateTransitionError):
        validate_transition(current, next_state)


def test_terminal_states_have_no_outgoing_edges() -> None:
    """Test terminal states have no outgoing edges."""
    for state in WorkItemState:
        if is_terminal(state):
            outgoing = [edge for edge in ALLOWED_TRANSITIONS if edge[0] == state]
            assert outgoing == [], f"{state} is terminal but has outgoing edges {outgoing}"


def test_non_terminal_states_have_at_least_one_outgoing_edge() -> None:
    """Test non-terminal states have at least one outgoing edge."""
    for state in WorkItemState:
        if not is_terminal(state):
            outgoing = [edge for edge in ALLOWED_TRANSITIONS if edge[0] == state]
            assert outgoing, f"{state} is non-terminal but has no outgoing edge"


def test_result_committed_has_no_edge_back_to_pending_leased_or_executing() -> None:
    """Test lease expiry/redelivery can never erase already-durable
    evidence: RESULT_COMMITTED has no edge back to PENDING_AVAILABLE,
    LEASED, or EXECUTING."""
    forbidden_targets = {
        WorkItemState.PENDING_AVAILABLE,
        WorkItemState.LEASED,
        WorkItemState.EXECUTING,
    }
    for current, next_state in ALLOWED_TRANSITIONS:
        if current == WorkItemState.RESULT_COMMITTED:
            assert next_state not in forbidden_targets


def test_acknowledged_completed_is_reachable_only_from_result_committed() -> None:
    """Test acknowledgement occurs only after durable result commit."""
    sources = {
        current
        for current, next_state in ALLOWED_TRANSITIONS
        if next_state == WorkItemState.ACKNOWLEDGED_COMPLETED
    }
    assert sources == {WorkItemState.RESULT_COMMITTED}


def test_cancellation_before_admission_and_after_lease_are_distinct_edges() -> None:
    """Test cancellation-before-admission (from PENDING_AVAILABLE) and
    cancellation-after-lease (from LEASED/EXECUTING/RETRYABLE) are both
    legal, and a caller can distinguish which occurred from the source
    state alone."""
    cancellation_sources = {
        current
        for current, next_state in ALLOWED_TRANSITIONS
        if next_state == WorkItemState.CANCELLED
    }
    assert WorkItemState.PENDING_AVAILABLE in cancellation_sources
    assert cancellation_sources - {WorkItemState.PENDING_AVAILABLE} == {
        WorkItemState.LEASED,
        WorkItemState.EXECUTING,
        WorkItemState.RETRYABLE,
    }


def test_result_committed_self_loop_is_the_only_self_loop() -> None:
    """Test result committed self loop is the only self loop (idempotent
    duplicate commit)."""
    self_loops = {current for current, next_state in ALLOWED_TRANSITIONS if current == next_state}
    assert self_loops == {WorkItemState.RESULT_COMMITTED}
