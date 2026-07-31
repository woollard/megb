"""Interface for optimization-pressure search algorithms (e.g., Best-of-N)."""

from abc import ABC, abstractmethod
from typing import Any

from src.evaluators.base import BaseMeasurementSystem


class BaseOptimizer(ABC):
    """Common interface for search algorithms that apply optimization pressure.

    Implementations must only be given access to a measurement system under
    test (S1..S4); the gold evaluator (S*) must never be passed in, per
    CLAUDE.md's non-negotiable repository rules.
    """

    @abstractmethod
    def search(
        self,
        task_id: str,
        prompt: str,
        measurement_system: BaseMeasurementSystem,
        budget_n: int,
        seed: int,
    ) -> dict[str, Any]:
        """Run search under a fixed optimization budget and return the selected candidate.

        Args:
            task_id: HumanEval task identifier.
            prompt: Task prompt supplied to the generator.
            measurement_system: The measurement system under test (S1..S4), used to
                select among generated candidates.
            budget_n: Number of candidate generations allowed in this run.
            seed: Seed governing all randomness in this search run, for reproducibility.

        Returns:
            A dict containing at minimum the selected candidate code, its q_meas
            score, and the full set of generated candidates for auditability.
        """
