"""Typed execution request/result models and the execution-status taxonomy.

This is execution infrastructure only. It does not determine candidate
correctness and does not compute any measurement score — see
``src/evaluators/`` for that. ``ExecutionStatus`` deliberately excludes
``WRONG_ANSWER`` / ``PASSED``: those are evaluator-level judgments.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ExecutionStatus(str, Enum):
    """Outcome of one candidate invocation, at the execution-infrastructure layer."""

    COMPLETED = "COMPLETED"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    CANDIDATE_EXCEPTION = "CANDIDATE_EXCEPTION"
    TIMEOUT = "TIMEOUT"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    PROCESS_LIMIT = "PROCESS_LIMIT"
    OUTPUT_LIMIT = "OUTPUT_LIMIT"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"


@dataclass(frozen=True)
class ExecutionLimits:
    """Centralized, configurable resource-safety defaults for one invocation.

    These are initial process-safety defaults, not claims about acceptable
    algorithmic complexity (a universal timeout is an execution policy, not
    evidence of a particular complexity class).
    """

    wall_time_sec: float = 2.0
    memory_mb: int = 256
    cpu_count: float = 1.0
    max_processes: int = 32
    max_open_files: int = 64
    max_stdout_bytes: int = 65_536
    max_stderr_bytes: int = 65_536
    max_request_bytes: int = 1_048_576
    max_response_bytes: int = 1_048_576
    temp_storage_mb: int = 16


@dataclass(frozen=True)
class CandidateExecutionRequest:
    """One invocation of untrusted candidate code.

    Must never carry hidden tests, expected outputs, canonical solutions, or
    any other privileged evidence — only what is needed to invoke the
    candidate's entry point once.
    """

    candidate_code: str
    entry_point: str
    args: tuple[Any, ...]
    kwargs: Mapping[str, Any]
    limits: ExecutionLimits
    protocol_version: str


@dataclass(frozen=True)
class CandidateExecutionResult:
    """Result of one candidate invocation.

    Distinguishes execution completion (this dataclass) from semantic
    correctness (a later evaluator's concern). Carries enough structured
    metadata to reproduce and diagnose the invocation without logging
    candidate source, arguments, or return values by default (see
    ``docs/security/execution-threat-model.md``).

    ``wall_time_sec`` and ``candidate_wall_time_sec`` are deliberately
    distinct: the former is the total duration the backend observed for
    this invocation (container start + candidate execution + teardown).
    The latter is measured by the runner itself, from immediately before
    compiling the candidate's source through the entry-point call
    returning or failing — it covers compilation and module-level code,
    not just the final function call — and is ``None`` whenever the
    candidate never got to run to completion or failure on its own
    (``TIMEOUT``, ``OUT_OF_MEMORY``, ``INFRASTRUCTURE_ERROR`` — the runner
    was killed externally or never started, so it never measured or
    reported its own duration).
    """

    invocation_id: str
    status: ExecutionStatus
    return_value: Any | None
    exception_type: str | None
    exception_message: str | None
    wall_time_sec: float
    candidate_wall_time_sec: float | None
    exit_code: int | None
    terminating_signal: int | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    backend_id: str
    backend_version: str
    runner_image_digest: str
    protocol_version: str
    limits: ExecutionLimits
    started_at: str
    infrastructure_error_detail: str | None = field(default=None)
