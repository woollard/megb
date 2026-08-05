"""MEGB-03H.2C.3B.2B.3: shared recorder for the fault-injection/recovery
conformance suite. Not a test module itself -- imported by
``test_fault_conformance.py``.

``ConformanceRecorder`` accumulates one :class:`~src.distributed.fault_conformance.ConformanceEntry`
per (fault point, invariant) actually exercised by a test function --
nothing else is ever recorded (no exception text, no candidate content, no
participant identifier)."""

from src.distributed.fault_conformance import ConformanceEntry, FaultPointId, InvariantId


class ConformanceRecorder:
    """Accumulates :class:`ConformanceEntry` objects across the whole
    conformance test module, in the order tests record them. Read once, at
    the end of the module, to build the safe, committed report."""

    def __init__(self) -> None:
        self._entries: list[ConformanceEntry] = []

    def record(
        self,
        fault_point: FaultPointId,
        invariant: InvariantId,
        passed: bool,
        *,
        attempt_count: int = 1,
    ) -> None:
        """Record one exercised (fault point, invariant) pair."""
        self._entries.append(
            ConformanceEntry(
                fault_point=fault_point,
                invariant=invariant,
                passed=passed,
                attempt_count=attempt_count,
            )
        )

    @property
    def entries(self) -> list[ConformanceEntry]:
        """Every entry recorded so far, in recording order."""
        return list(self._entries)


RECORDER = ConformanceRecorder()
