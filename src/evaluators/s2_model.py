"""System 2: weak Measurement Model (M).

Evaluates candidates with exhaustive test evidence but a coarse scoring
rule (binary pass/fail execution only, no AST static checks or complexity
bounds), per ARCHITECTURE.md Section 2. Observation and Process are held at
their most robust setting so any gaming divergence can be attributed to the
coarse measurement model alone.
"""

from src.evaluators.base import BaseMeasurementSystem
from src.evaluators.schema import TaskMeasurementResult


class S2WeakModel(BaseMeasurementSystem):
    """Coarse-specification measurement system: binary pass/fail scoring only."""

    @property
    def system_id(self) -> str:
        return "S2_WeakModel"

    def evaluate(self, task_id: str, candidate_code: str) -> TaskMeasurementResult:
        raise NotImplementedError("S2 coarse-model evaluation not yet implemented.")
