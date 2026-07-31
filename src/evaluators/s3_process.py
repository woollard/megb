"""System 3: weak Measurement Process (P).

Evaluates candidates using exhaustive test evidence and a granular scoring
rule, but an unstable process: an LLM-as-judge at T=0.7 with no sandboxed
execution, per ARCHITECTURE.md Section 2. Observation and Model are held at
their most robust setting so any gaming divergence can be attributed to
process instability alone.
"""

from src.evaluators.base import BaseMeasurementSystem
from src.evaluators.schema import TaskMeasurementResult


class S3WeakProcess(BaseMeasurementSystem):
    """Unstable-reader measurement system: stochastic LLM judge, no sandbox execution."""

    @property
    def system_id(self) -> str:
        return "S3_WeakProcess"

    def evaluate(self, task_id: str, candidate_code: str) -> TaskMeasurementResult:
        raise NotImplementedError("S3 LLM-judge evaluation not yet implemented.")
