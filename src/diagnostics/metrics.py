"""Gaming-delta metric computations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GamingDelta:
    """Comparison of measured vs. held-out performance for a single run."""

    task_id: str
    system_id: str
    q_meas: float
    q_true: float

    @property
    def gaming_delta(self) -> float:
        """Q_meas - Q_true, the primary comparison metric from CLAUDE.md."""
        return self.q_meas - self.q_true
