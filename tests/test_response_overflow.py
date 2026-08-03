"""MEGB-03H.2C.1: tests for the typed, centralized response-overflow
classifier (src.execution.response_overflow). Synthetic
CandidateExecutionResult construction only -- no real Docker.
"""

import pytest

from src.execution.protocol import ExecutionStatus
from src.execution.response_overflow import (
    ResponseOverflowClassification,
    classify_response_overflow,
)
from src.execution.runner import _protocol_error_response
from src.execution.wire import ProtocolError, RunnerResponse, serialize_response
from tests._h2c1_telemetry_fixtures import make_candidate_execution_result as _result


def test_the_runners_exact_response_overflow_message_is_classified_as_overflowed() -> None:
    """The exact format wire._dumps_and_check_size produces for a
    too-large response, label='response'."""
    result = _result(
        status=ExecutionStatus.PROTOCOL_ERROR,
        exception_type="ProtocolError",
        exception_message="serialized response (2000000 bytes) exceeds limit (1048576 bytes)",
    )
    assert classify_response_overflow(result) == ResponseOverflowClassification.OVERFLOWED


def test_boundary_sized_counts_still_match() -> None:
    """The regex matches regardless of the specific digit counts."""
    result = _result(
        status=ExecutionStatus.PROTOCOL_ERROR,
        exception_type="ProtocolError",
        exception_message="serialized response (0 bytes) exceeds limit (1 bytes)",
    )
    assert classify_response_overflow(result) == ResponseOverflowClassification.OVERFLOWED


def test_completed_status_is_never_overflowed() -> None:
    """A normal completion is never misclassified, regardless of content."""
    result = _result(status=ExecutionStatus.COMPLETED)
    assert classify_response_overflow(result) == ResponseOverflowClassification.NOT_OVERFLOWED


def test_candidate_exception_with_lookalike_text_is_not_misclassified() -> None:
    """A candidate that defines its own exception class named
    'ProtocolError' and raises it with text that exactly matches the
    overflow message format must not be misclassified -- status is
    CANDIDATE_EXCEPTION, never PROTOCOL_ERROR, for any candidate-raised
    exception, regardless of its class name or message."""
    result = _result(
        status=ExecutionStatus.CANDIDATE_EXCEPTION,
        exception_type="ProtocolError",
        exception_message="serialized response (500 bytes) exceeds limit (1000 bytes)",
    )
    assert classify_response_overflow(result) == ResponseOverflowClassification.NOT_OVERFLOWED


def test_malformed_request_protocol_error_is_not_misclassified_as_overflow() -> None:
    """A malformed/oversized *request* is also PROTOCOL_ERROR + exception_type
    'ProtocolError', but the message format says 'request', not
    'response' -- never misclassified as a response overflow."""
    result = _result(
        status=ExecutionStatus.PROTOCOL_ERROR,
        exception_type="ProtocolError",
        exception_message="request payload (9999999 bytes) exceeds limit (8388608 bytes)",
    )
    assert classify_response_overflow(result) == ResponseOverflowClassification.NOT_OVERFLOWED


def test_unsupported_return_value_type_protocol_error_is_not_misclassified() -> None:
    """A return value of an unsupported wire type is also a ProtocolError
    under PROTOCOL_ERROR status, but a completely different message
    format -- never misclassified as a response overflow."""
    result = _result(
        status=ExecutionStatus.PROTOCOL_ERROR,
        exception_type="ProtocolError",
        exception_message="unsupported value type for wire encoding: MyCustomClass",
    )
    assert classify_response_overflow(result) == ResponseOverflowClassification.NOT_OVERFLOWED


def test_protocol_error_with_no_exception_message_is_not_misclassified() -> None:
    """A PROTOCOL_ERROR result missing exception_message entirely (should
    never happen in practice, but must not crash or false-positive)."""
    result = _result(status=ExecutionStatus.PROTOCOL_ERROR, exception_type="ProtocolError")
    assert classify_response_overflow(result) == ResponseOverflowClassification.NOT_OVERFLOWED


def test_protocol_error_with_a_different_exception_type_is_not_misclassified() -> None:
    """PROTOCOL_ERROR status with an exception_type other than 'ProtocolError'
    (should not occur from the real runner, but must not false-positive)."""
    result = _result(
        status=ExecutionStatus.PROTOCOL_ERROR,
        exception_type="SomeOtherError",
        exception_message="serialized response (1 bytes) exceeds limit (1 bytes)",
    )
    assert classify_response_overflow(result) == ResponseOverflowClassification.NOT_OVERFLOWED


# ---------------------------------------------------------------------------
# Producer/consumer contract: the runner's REAL formatter, not a copied literal
# ---------------------------------------------------------------------------


def test_producer_consumer_contract_via_the_real_runner_fallback_path() -> None:
    """Drives the runner's actual, unmodified oversized-response code path
    end to end -- wire.serialize_response's real size check raising a
    real ProtocolError, fed through runner._protocol_error_response's real
    fallback construction -- and confirms classify_response_overflow()
    recognizes the resulting real message. Unlike the tests above (which
    assert against a message the audit specified literally), this test
    derives the message from the runner's own current formatter, so it
    fails immediately if that formatter's wording or field order ever
    drifts without response_overflow.py's regex being updated to match --
    exactly the "message drift cannot silently break it" guarantee this
    contract exists to enforce.
    """
    oversized_response = RunnerResponse(
        status=ExecutionStatus.COMPLETED,
        return_value="x" * 10_000,
        exception_type=None,
        exception_message=None,
        stdout="",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        candidate_wall_time_sec=0.01,
    )
    tiny_max_response_bytes = 10  # deliberately far smaller than the real payload

    with pytest.raises(ProtocolError) as exc_info:
        serialize_response(oversized_response, tiny_max_response_bytes)

    # Exactly what runner.main() does on this exact exception.
    fallback_response = _protocol_error_response(exc_info.value)
    assert fallback_response.status == ExecutionStatus.PROTOCOL_ERROR
    assert fallback_response.exception_type == "ProtocolError"
    assert fallback_response.exception_message is not None
    assert "serialized response" in fallback_response.exception_message

    result = _result(
        status=fallback_response.status,
        exception_type=fallback_response.exception_type,
        exception_message=fallback_response.exception_message,
    )
    assert classify_response_overflow(result) == ResponseOverflowClassification.OVERFLOWED


def test_producer_contract_for_a_genuinely_different_protocol_error_stays_not_overflowed() -> None:
    """The same real runner fallback path, but for an UNSUPPORTED VALUE
    TYPE failure (a completely different ProtocolError message) -- proves
    the contract test harness itself can distinguish message shapes, not
    just rubber-stamp any ProtocolError as an overflow."""

    class _Unsupported:  # pylint: disable=too-few-public-methods
        """A type wire.encode_value cannot serialize."""

    oversized_response = RunnerResponse(
        status=ExecutionStatus.COMPLETED,
        return_value=_Unsupported(),
        exception_type=None,
        exception_message=None,
        stdout="",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        candidate_wall_time_sec=0.01,
    )

    with pytest.raises(ProtocolError) as exc_info:
        serialize_response(oversized_response, max_response_bytes=10_000_000)

    fallback_response = _protocol_error_response(exc_info.value)
    assert fallback_response.exception_message is not None
    assert "serialized response" not in fallback_response.exception_message

    result = _result(
        status=fallback_response.status,
        exception_type=fallback_response.exception_type,
        exception_message=fallback_response.exception_message,
    )
    assert classify_response_overflow(result) == ResponseOverflowClassification.NOT_OVERFLOWED


def test_timeout_and_infrastructure_error_are_never_overflowed() -> None:
    """No other status is ever classified as an overflow."""
    for status in (
        ExecutionStatus.TIMEOUT,
        ExecutionStatus.OUT_OF_MEMORY,
        ExecutionStatus.INFRASTRUCTURE_ERROR,
        ExecutionStatus.SYNTAX_ERROR,
        ExecutionStatus.PROCESS_LIMIT,
        ExecutionStatus.OUTPUT_LIMIT,
    ):
        result = _result(status=status)
        assert classify_response_overflow(result) == ResponseOverflowClassification.NOT_OVERFLOWED
