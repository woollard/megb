"""System 1: weak Observation Design (O).

Evaluates candidates against only the single public example test bundled
with each HumanEval prompt, per ARCHITECTURE.md Section 2. The Measurement
Model and Measurement Process are held at their most robust setting so any
gaming divergence can be attributed to sparse observation evidence alone.
"""

from typing import Any

from src.evaluators.base import BaseMeasurementSystem


class S1WeakObservation(BaseMeasurementSystem):
    """Sparse-evidence measurement system: one public test, no hidden tests."""

    @property
    def system_id(self) -> str:
        return "S1_WeakObservation"

    def evaluate(self, task_id: str, candidate_code: str) -> dict[str, Any]:
        raise NotImplementedError("S1 sparse-observation evaluation not yet implemented.")
