"""MEGB-03H.2C.3B.2A: the work-item state machine -- the typed transition
table every legal lifecycle a reference-execution work item can pass
through, and every illegal one this package refuses.

Eight states, matching the authorization's own required equivalents:
``PENDING_AVAILABLE`` (pending/available), ``LEASED``, ``EXECUTING``,
``RESULT_COMMITTED`` (result durably committed), ``ACKNOWLEDGED_COMPLETED``
(acknowledged/completed), ``RETRYABLE``, ``CANCELLED``, ``DEAD_LETTERED``
(terminally blocked/dead-lettered).

The transition table alone encodes several required invariants directly,
by the simple absence of an edge:

* **Lease expiry does not erase already durable evidence** -- there is no
  edge from ``RESULT_COMMITTED``/``ACKNOWLEDGED_COMPLETED`` back to
  ``LEASED``/``EXECUTING``/``PENDING_AVAILABLE``; once a result is
  durably committed, redelivery or lease expiry can never regress the
  work item's state.
* **Acknowledgement occurs only after durable, checksum-verified result
  commit** -- ``ACKNOWLEDGED_COMPLETED`` is reachable only from
  ``RESULT_COMMITTED``.
* **Cancellation before admission differs from cancellation after lease**
  -- ``PENDING_AVAILABLE -> CANCELLED`` and ``{LEASED, EXECUTING,
  RETRYABLE} -> CANCELLED`` are both legal, distinct edges; a caller can
  tell which one occurred from the *source* state alone.
* **Terminal states are closed** -- ``ACKNOWLEDGED_COMPLETED``,
  ``CANCELLED``, and ``DEAD_LETTERED`` have no outgoing edges at all.

What the table alone cannot express -- fencing (a stale lease generation
must not be allowed to commit) and idempotent-vs-conflicting result-commit
reconciliation -- are implemented as separate pure functions in
:mod:`~src.distributed.work_contracts`/:mod:`~src.distributed.worker_contracts`,
since those require comparing *values* (lease generations, result-content
checksums), not merely state labels.
"""

from enum import Enum


class WorkItemState(str, Enum):
    """The eight states a reference-execution work item's lifecycle can
    occupy. Closed by design -- no state outside this set is legal."""

    PENDING_AVAILABLE = "PENDING_AVAILABLE"
    LEASED = "LEASED"
    EXECUTING = "EXECUTING"
    RESULT_COMMITTED = "RESULT_COMMITTED"
    ACKNOWLEDGED_COMPLETED = "ACKNOWLEDGED_COMPLETED"
    RETRYABLE = "RETRYABLE"
    CANCELLED = "CANCELLED"
    DEAD_LETTERED = "DEAD_LETTERED"


class IllegalStateTransitionError(ValueError):
    """Raised by :func:`validate_transition` when the requested
    ``(current, next_state)`` pair is not a legal edge in
    :data:`ALLOWED_TRANSITIONS`."""


# Every legal (current, next) edge. Read top-to-bottom as: admission,
# leasing/execution, durable commit and acknowledgement, retry/redelivery,
# and the three terminal sinks.
ALLOWED_TRANSITIONS: frozenset[tuple[WorkItemState, WorkItemState]] = frozenset(
    {
        # Admission and cancellation-before-admission.
        (WorkItemState.PENDING_AVAILABLE, WorkItemState.LEASED),
        (WorkItemState.PENDING_AVAILABLE, WorkItemState.CANCELLED),
        # Leasing and execution.
        (WorkItemState.LEASED, WorkItemState.EXECUTING),
        (WorkItemState.LEASED, WorkItemState.RETRYABLE),
        (WorkItemState.LEASED, WorkItemState.CANCELLED),
        (WorkItemState.EXECUTING, WorkItemState.RESULT_COMMITTED),
        (WorkItemState.EXECUTING, WorkItemState.RETRYABLE),
        (WorkItemState.EXECUTING, WorkItemState.CANCELLED),
        # Durable commit is idempotent (an identical duplicate re-commit is
        # a self-loop, never a regression) and leads to acknowledgement.
        (WorkItemState.RESULT_COMMITTED, WorkItemState.RESULT_COMMITTED),
        (WorkItemState.RESULT_COMMITTED, WorkItemState.ACKNOWLEDGED_COMPLETED),
        # Retry/redelivery: reassigned to a new lease, cancelled, or
        # exhausted into dead-lettering.
        (WorkItemState.RETRYABLE, WorkItemState.LEASED),
        (WorkItemState.RETRYABLE, WorkItemState.CANCELLED),
        (WorkItemState.RETRYABLE, WorkItemState.DEAD_LETTERED),
    }
)

_TERMINAL_STATES: frozenset[WorkItemState] = frozenset(
    {
        WorkItemState.ACKNOWLEDGED_COMPLETED,
        WorkItemState.CANCELLED,
        WorkItemState.DEAD_LETTERED,
    }
)


def is_terminal(state: WorkItemState) -> bool:
    """``True`` for the three closed sink states with no outgoing edge."""
    return state in _TERMINAL_STATES


def validate_transition(current: WorkItemState, next_state: WorkItemState) -> None:
    """Raise :class:`IllegalStateTransitionError` unless
    ``(current, next_state)`` is a member of :data:`ALLOWED_TRANSITIONS`."""
    if (current, next_state) not in ALLOWED_TRANSITIONS:
        raise IllegalStateTransitionError(
            f"illegal work-item state transition {current.value!r} -> {next_state.value!r}"
        )


__all__ = [
    "WorkItemState",
    "IllegalStateTransitionError",
    "ALLOWED_TRANSITIONS",
    "is_terminal",
    "validate_transition",
]
