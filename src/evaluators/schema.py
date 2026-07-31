"""Shared measurement-result schema and failure taxonomy for S1..S4 evaluators.

This is the general result contract used by ``BaseMeasurementSystem``
implementations. The privileged gold-standard evaluator (S*) uses a separate,
more detailed schema defined alongside its own ticket, because it must
additionally distinguish candidate failures from measurement-system failures
under audit; that distinction is out of scope for the general S1..S4 result
schema defined here.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class FailureCategory(str, Enum):
    """General failure taxonomy for a single task measurement."""

    NONE = "NONE"
    WRONG_OUTPUT = "WRONG_OUTPUT"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    RUNTIME_EXCEPTION = "RUNTIME_EXCEPTION"
    TIMEOUT = "TIMEOUT"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    OUTPUT_LIMIT = "OUTPUT_LIMIT"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"


@dataclass(frozen=True)
class TaskMeasurementResult:
    """Result of evaluating one candidate solution against one measurement system.

    Attributes:
        task_id: HumanEval task identifier, e.g. ``HumanEval/0``.
        system_id: Identifier of the measurement system that produced this result.
        q_meas: Normalized score in [0.0, 1.0], or ``None`` if the measurement
            itself was invalid (see ``failure_category``).
        failure_category: The general failure taxonomy classification.
        diagnostics: Structured, system-specific diagnostic payload.
    """

    task_id: str
    system_id: str
    q_meas: float | None
    failure_category: FailureCategory
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
