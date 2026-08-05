"""MEGB-03H.2C.3B.2B.2: construction/validation tests for
:mod:`src.distributed.executor`."""

import pytest

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.executor import (
    ExecutorFailureReason,
    ExecutorInvocationResult,
    ExecutorOutcomeKind,
    executor_failure,
    executor_success,
    is_retryable_failure,
)


def test_executor_success_carries_result_content() -> None:
    """Test executor success carries result content."""
    result = executor_success(b"content")
    assert result.outcome_kind == ExecutorOutcomeKind.SUCCESS
    assert result.result_content == b"content"
    assert result.failure_reason is None


def test_executor_failure_carries_reason_only() -> None:
    """Test executor failure carries reason only."""
    result = executor_failure(ExecutorFailureReason.TERMINAL_INVALID_OUTPUT)
    assert result.outcome_kind == ExecutorOutcomeKind.FAILURE
    assert result.result_content is None
    assert result.failure_reason == ExecutorFailureReason.TERMINAL_INVALID_OUTPUT


def test_success_rejects_missing_result_content() -> None:
    """Test success rejects missing result content."""
    with pytest.raises(InvalidDistributedProvenanceError):
        ExecutorInvocationResult(
            outcome_kind=ExecutorOutcomeKind.SUCCESS, result_content=None, failure_reason=None
        )


def test_success_rejects_a_failure_reason_alongside_result() -> None:
    """Test success rejects a failure reason alongside result."""
    with pytest.raises(InvalidDistributedProvenanceError):
        ExecutorInvocationResult(
            outcome_kind=ExecutorOutcomeKind.SUCCESS,
            result_content=b"x",
            failure_reason=ExecutorFailureReason.TERMINAL_INVALID_OUTPUT,
        )


def test_failure_rejects_missing_reason() -> None:
    """Test failure rejects missing reason."""
    with pytest.raises(InvalidDistributedProvenanceError):
        ExecutorInvocationResult(
            outcome_kind=ExecutorOutcomeKind.FAILURE, result_content=None, failure_reason=None
        )


def test_failure_rejects_result_content_alongside_reason() -> None:
    """Test failure rejects result content alongside reason."""
    with pytest.raises(InvalidDistributedProvenanceError):
        ExecutorInvocationResult(
            outcome_kind=ExecutorOutcomeKind.FAILURE,
            result_content=b"x",
            failure_reason=ExecutorFailureReason.TERMINAL_INVALID_OUTPUT,
        )


@pytest.mark.parametrize(
    "reason,expected",
    [
        (ExecutorFailureReason.RETRYABLE_EXECUTION_ERROR, True),
        (ExecutorFailureReason.RETRYABLE_RESOURCE_EXHAUSTED, True),
        (ExecutorFailureReason.TERMINAL_INVALID_OUTPUT, False),
        (ExecutorFailureReason.TERMINAL_EXECUTION_ERROR, False),
    ],
)
def test_is_retryable_failure_matches_the_closed_taxonomy(
    reason: ExecutorFailureReason, expected: bool
) -> None:
    """Test is_retryable_failure matches the closed taxonomy."""
    assert is_retryable_failure(reason) is expected
