"""MEGB-03H.2C.1: tests for the typed, centralized response-overflow
classifier (src.execution.response_overflow). Synthetic
CandidateExecutionResult construction only -- no real Docker.
"""

from src.execution.protocol import ExecutionStatus
from src.execution.response_overflow import (
    ResponseOverflowClassification,
    classify_response_overflow,
)
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
