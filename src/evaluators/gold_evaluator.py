"""Held-out gold-standard evaluator (S*).

S* must never be exposed to the optimization loop; per CLAUDE.md's
non-negotiable repository rules, it is used only to compute ``q_true`` for
offline gaming-delta analysis after a search run has completed.
"""

from typing import Any

from src.evaluators.base import BaseMeasurementSystem


class GoldEvaluator(BaseMeasurementSystem):
    """Exhaustive hidden-test and property-fuzzing evaluator used only for q_true."""

    @property
    def system_id(self) -> str:
        return "S_star_Gold"

    def evaluate(self, task_id: str, candidate_code: str) -> dict[str, Any]:
        raise NotImplementedError(
            "Gold evaluator sandboxed execution and hypothesis-based property "
            "fuzzing are not yet implemented."
        )
