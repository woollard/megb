"""MEGB-03H.2C.3B.2A: the injected, deterministic clock abstraction every
orchestration-contract type in this package uses instead of wall-clock
time.

Every timestamp field in :mod:`~src.distributed.work_contracts`,
:mod:`~src.distributed.worker_contracts`, and
:mod:`~src.distributed.safe_audit` is a *logical* tick from a
:class:`Clock`, never ``time.time()``/``datetime.now()`` -- so every test
in this package (and, eventually, H.2C.3B.2B's own coordinator/worker
engine) can drive lease expiry, renewal, and ordering deterministically,
with no wall-clock sleep anywhere. This mirrors this project's own
established preference for deterministic, injectable time sources over
ambient wall-clock reads at a trust boundary (e.g.
``CalibrationRunContext``'s own checksum-bound, never-wall-clock-derived
identity fields).

``Clock`` is a :class:`typing.Protocol` -- a structural interface, not a
base class -- so any deterministic clock implementation satisfies it
without inheriting from this module. :class:`LogicalClock` is the one
concrete, synthetic implementation this checkpoint provides, for tests
and for a future in-memory coordinator (MEGB-03H.2C.3B.2B) to reuse; it
holds no wall-clock state at all.
"""

from typing import Protocol


class Clock(Protocol):
    """Structural interface for a monotonic, logical tick source.

    ``now()`` must never decrease between calls on the same instance --
    every state-machine/lease-fencing invariant in this package assumes
    non-decreasing logical time."""

    def now(self) -> int:
        """The current logical tick. Non-decreasing across calls."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class NonMonotonicClockAdvanceError(ValueError):
    """Raised when :meth:`LogicalClock.advance` is asked to move the
    clock backward or by zero ticks -- a logical clock that could go
    backward would violate every lease-expiry/ordering invariant this
    package's tests rely on."""


class LogicalClock:
    """A synthetic, deterministic, injectable :class:`Clock` -- an
    explicit integer tick counter with no relationship to wall-clock
    time whatsoever. Starts at ``0`` (or a caller-supplied
    ``start_tick``) and only ever advances by an explicit,
    caller-driven :meth:`advance` call -- never on its own, and never by
    sleeping. This is the concrete clock every test in this package (and
    a future in-memory coordinator) uses in place of wall-clock time."""

    def __init__(self, start_tick: int = 0) -> None:
        if not isinstance(start_tick, int) or isinstance(start_tick, bool) or start_tick < 0:
            raise ValueError(f"start_tick must be a non-negative int, got {start_tick!r}")
        self._tick = start_tick

    def now(self) -> int:
        """The current logical tick."""
        return self._tick

    def advance(self, ticks: int) -> int:
        """Move the clock forward by ``ticks`` (a positive int) and
        return the new ``now()``. Raises
        :class:`NonMonotonicClockAdvanceError` for a non-positive value
        -- a logical clock in this package only ever moves forward, and
        only by an explicit amount a test or caller controls."""
        if not isinstance(ticks, int) or isinstance(ticks, bool) or ticks <= 0:
            raise NonMonotonicClockAdvanceError(
                f"ticks must be a positive int, got {ticks!r}"
            )
        self._tick += ticks
        return self._tick


__all__ = [
    "Clock",
    "LogicalClock",
    "NonMonotonicClockAdvanceError",
]
