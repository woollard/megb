"""Abstract measurement-system interface shared by S1..S4 and the gold evaluator (S*)."""

from abc import ABC, abstractmethod
from typing import Any


class BaseMeasurementSystem(ABC):
    """Common interface for engineered measurement systems and the gold evaluator.

    Implementations must isolate their behavior to the Observation (O),
    Measurement Model (M), and Measurement Process (P) layers they are
    designed to manipulate, per ARCHITECTURE.md Section 2. Candidate code
    passed to ``evaluate`` is untrusted and must only be executed by isolated
    subprocess workers, never in the controlling experiment process.
    """

    @property
    @abstractmethod
    def system_id(self) -> str:
        """Stable identifier for this measurement system, e.g. ``S1_WeakObservation``."""

    @abstractmethod
    def evaluate(self, task_id: str, candidate_code: str) -> dict[str, Any]:
        """Evaluate untrusted candidate code against this system's operational definition.

        Args:
            task_id: HumanEval task identifier, e.g. ``HumanEval/0``.
            candidate_code: Untrusted, LLM-generated candidate solution source.

        Returns:
            A dict containing at minimum:
                - ``task_id`` (str)
                - ``q_meas`` (float): normalized score in [0.0, 1.0]
                - ``execution_details`` (dict[str, Any]): structured diagnostic payload
        """
