"""Pluggable candidate-execution backend interface.

Evaluator code (measurement systems, the reference evaluator, optimizers)
must depend only on ``ExecutionBackend``, never on a concrete strategy such
as ``DockerPerInvocationBackend``. The initial strategy launches one fresh
container per invocation, favoring isolation and simplicity per MEGB-02; a
future batched or pooled backend can implement this same interface for
performance without any evaluator-side changes, per MEGB-02's own
requirement that performance optimizations "must not silently change the
evaluator's measurement process" without being versioned and compared.
"""

from abc import ABC, abstractmethod

from src.execution.protocol import CandidateExecutionRequest, CandidateExecutionResult


class ExecutionBackend(ABC):
    """Interface for executing one untrusted candidate invocation in isolation."""

    @abstractmethod
    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        """Execute one candidate invocation and return a structured result.

        Never raises for candidate-caused failures (syntax errors,
        exceptions, timeouts, resource exhaustion, malformed output): those
        are all reported via ``CandidateExecutionResult.status``. May raise
        for genuine backend-setup failures the caller cannot recover from
        (e.g. the container runtime itself being unavailable).
        """
