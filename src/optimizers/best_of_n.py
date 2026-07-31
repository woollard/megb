"""Best-of-N rejection sampling optimizer."""

from typing import Any

from src.evaluators.base import BaseMeasurementSystem
from src.optimizers.base_optimizer import BaseOptimizer


class BestOfNOptimizer(BaseOptimizer):
    """Generates N candidates and selects the highest-q_meas candidate."""

    def search(
        self,
        task_id: str,
        prompt: str,
        measurement_system: BaseMeasurementSystem,
        budget_n: int,
        seed: int,
    ) -> dict[str, Any]:
        raise NotImplementedError("Best-of-N generation loop not yet implemented.")
