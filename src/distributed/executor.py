"""MEGB-03H.2C.3B.2B.2: the injected work-executor boundary and its closed,
typed outcome/failure taxonomy.

:class:`WorkExecutorProtocol` is the one point where the coordinator/worker
engine calls out to caller-supplied logic that actually "does" the
scientific work -- in this checkpoint, always a harmless synthetic
callback (see ``tests/_coordinator_fixtures.py``). This module has no
HumanEval, oracle, cache, model-provider, or Docker-execution logic of any
kind; it is a pure, provider-neutral seam.

:class:`ExecutorInvocationResult` is deliberately closed and safe: a
raised exception's own message never appears in it (only a typed
:class:`ExecutorFailureReason`), mirroring
:class:`~src.distributed.work_contracts.TerminalDispositionReason`'s own
"typed and closed, no free-form diagnostic" discipline."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from src.distributed._checksums import InvalidDistributedProvenanceError


class ExecutorOutcomeKind(str, Enum):
    """Closed set of outcomes a single executor invocation can report."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class ExecutorFailureReason(str, Enum):
    """Closed, safe failure taxonomy -- never a raw exception message.
    ``RETRYABLE_*`` members are eligible for retry; ``TERMINAL_*`` members
    are not."""

    RETRYABLE_EXECUTION_ERROR = "RETRYABLE_EXECUTION_ERROR"
    RETRYABLE_RESOURCE_EXHAUSTED = "RETRYABLE_RESOURCE_EXHAUSTED"
    TERMINAL_INVALID_OUTPUT = "TERMINAL_INVALID_OUTPUT"
    TERMINAL_EXECUTION_ERROR = "TERMINAL_EXECUTION_ERROR"


_RETRYABLE_REASONS = frozenset(
    {
        ExecutorFailureReason.RETRYABLE_EXECUTION_ERROR,
        ExecutorFailureReason.RETRYABLE_RESOURCE_EXHAUSTED,
    }
)


def is_retryable_failure(reason: ExecutorFailureReason) -> bool:
    """``True`` iff ``reason`` is one of the retryable members."""
    return reason in _RETRYABLE_REASONS


@dataclass(frozen=True)
class ExecutorInvocationResult:
    """The typed, safe result of one executor invocation. Exactly one of
    ``result_content``/``failure_reason`` is present, matching
    ``outcome_kind`` -- never a partially-computed result alongside a
    failure, mirroring
    :class:`~src.distributed.personal_policy.AdmissionDecision`'s own
    "never both" discipline. ``result_content`` is harmless synthetic
    bytes in every test in this checkpoint -- never real candidate/
    oracle/benchmark content."""

    outcome_kind: ExecutorOutcomeKind
    result_content: bytes | None
    failure_reason: ExecutorFailureReason | None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome_kind, ExecutorOutcomeKind):
            raise InvalidDistributedProvenanceError(
                f"outcome_kind must be an ExecutorOutcomeKind, got {self.outcome_kind!r}"
            )
        if self.outcome_kind == ExecutorOutcomeKind.SUCCESS:
            if not isinstance(self.result_content, bytes) or self.failure_reason is not None:
                raise InvalidDistributedProvenanceError(
                    "SUCCESS requires a bytes result_content and no failure_reason"
                )
        else:
            if self.result_content is not None or not isinstance(
                self.failure_reason, ExecutorFailureReason
            ):
                raise InvalidDistributedProvenanceError(
                    "FAILURE requires a failure_reason and no result_content"
                )


def executor_success(result_content: bytes) -> ExecutorInvocationResult:
    """Build a :class:`ExecutorInvocationResult` for a successful
    invocation."""
    return ExecutorInvocationResult(
        outcome_kind=ExecutorOutcomeKind.SUCCESS,
        result_content=result_content,
        failure_reason=None,
    )


def executor_failure(reason: ExecutorFailureReason) -> ExecutorInvocationResult:
    """Build a :class:`ExecutorInvocationResult` for a failed invocation."""
    return ExecutorInvocationResult(
        outcome_kind=ExecutorOutcomeKind.FAILURE,
        result_content=None,
        failure_reason=reason,
    )


class WorkExecutorProtocol(Protocol):
    """The injected work-executor boundary. Structural only -- no
    implementation, no Docker, no HumanEval/oracle/cache logic. A real
    adapter (not implemented here) would invoke the accepted MEGB-02
    execution protocol; every test in this checkpoint injects a harmless
    synthetic callback instead."""

    def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
        """Execute against ``candidate_content`` (already checksum-
        verified by the caller) and return a typed, safe result. Must
        never raise for an ordinary execution failure -- report it via
        :class:`ExecutorInvocationResult` instead; the engine treats an
        actual raised exception here as an infrastructure/internal
        failure, never as scientific-work data."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


__all__ = [
    "ExecutorOutcomeKind",
    "ExecutorFailureReason",
    "is_retryable_failure",
    "ExecutorInvocationResult",
    "executor_success",
    "executor_failure",
    "WorkExecutorProtocol",
]
