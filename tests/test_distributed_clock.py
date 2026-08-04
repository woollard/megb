"""MEGB-03H.2C.3B.2A: tests for the injected, deterministic clock
abstraction -- no wall-clock sleep anywhere in this file or any test that
depends on it."""

import pytest

from src.distributed.clock import LogicalClock, NonMonotonicClockAdvanceError


def test_logical_clock_starts_at_zero_by_default() -> None:
    """Test logical clock starts at zero by default."""
    clock = LogicalClock()
    assert clock.now() == 0


def test_logical_clock_starts_at_explicit_tick() -> None:
    """Test logical clock starts at explicit tick."""
    clock = LogicalClock(start_tick=42)
    assert clock.now() == 42


def test_logical_clock_advance_moves_forward_and_returns_new_now() -> None:
    """Test logical clock advance moves forward and returns new now."""
    clock = LogicalClock()
    assert clock.advance(5) == 5
    assert clock.now() == 5
    assert clock.advance(3) == 8
    assert clock.now() == 8


def test_logical_clock_rejects_zero_advance() -> None:
    """Test logical clock rejects zero advance."""
    clock = LogicalClock()
    with pytest.raises(NonMonotonicClockAdvanceError):
        clock.advance(0)


def test_logical_clock_rejects_negative_advance() -> None:
    """Test logical clock rejects negative advance."""
    clock = LogicalClock()
    with pytest.raises(NonMonotonicClockAdvanceError):
        clock.advance(-1)


def test_logical_clock_rejects_non_int_advance() -> None:
    """Test logical clock rejects non-int advance."""
    clock = LogicalClock()
    with pytest.raises(NonMonotonicClockAdvanceError):
        clock.advance(1.5)  # type: ignore[arg-type]


def test_logical_clock_rejects_negative_start_tick() -> None:
    """Test logical clock rejects negative start tick."""
    with pytest.raises(ValueError):
        LogicalClock(start_tick=-1)


def test_logical_clock_satisfies_clock_protocol() -> None:
    """Test logical clock satisfies clock protocol structurally (has a
    callable now())."""
    clock = LogicalClock()
    assert callable(clock.now)
    assert isinstance(clock.now(), int)
