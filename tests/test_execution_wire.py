"""Unit tests for the tagged-JSON wire serialization protocol (MEGB-02)."""

import json

import pytest

from src.execution.protocol import CandidateExecutionRequest, ExecutionLimits, ExecutionStatus
from src.execution.wire import (
    ProtocolError,
    RunnerResponse,
    decode_value,
    encode_value,
    parse_request_message,
    parse_response_message,
    serialize_request,
    serialize_response,
)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        -7,
        3.5,
        "",
        "hello",
        [1, 2.0, "three", None, True],
        (1, 2.0, "three"),
        {"a": 1, "b": [1, 2], "c": {"nested": True}},
        [(1, 2), [3, 4]],
    ],
)
def test_value_round_trips(value: object) -> None:
    """Every supported value round trips through encode/decode unchanged."""
    assert decode_value(encode_value(value)) == value


def test_tuple_and_list_are_distinguishable_on_the_wire() -> None:
    """Tuple and list must not collapse to the same wire representation."""
    tuple_wire = encode_value((1, 2))
    list_wire = encode_value([1, 2])

    assert tuple_wire["type"] == "tuple"
    assert list_wire["type"] == "list"
    assert isinstance(decode_value(tuple_wire), tuple)
    assert isinstance(decode_value(list_wire), list)


@pytest.mark.parametrize(
    "unsupported",
    [
        {1, 2, 3},
        b"bytes",
        object(),
        (lambda: None),
    ],
)
def test_unsupported_types_are_rejected(unsupported: object) -> None:
    """Types outside the supported set are rejected explicitly, not silently coerced."""
    with pytest.raises(ProtocolError):
        encode_value(unsupported)


def test_non_string_dict_keys_are_rejected() -> None:
    """Dict keys must be strings; non-string keys are rejected explicitly."""
    with pytest.raises(ProtocolError, match="dict keys must be strings"):
        encode_value({1: "a"})


def test_decode_rejects_malformed_tagged_value() -> None:
    """A tagged value missing 'type' or naming an unknown type is rejected."""
    with pytest.raises(ProtocolError, match="'type' field"):
        decode_value({"value": 1})
    with pytest.raises(ProtocolError, match="unsupported tagged type"):
        decode_value({"type": "function", "value": 1})


def _make_request(**overrides: object) -> CandidateExecutionRequest:
    fields: dict[str, object] = {
        "candidate_code": "def f(x):\n    return x\n",
        "entry_point": "f",
        "args": (1,),
        "kwargs": {},
        "limits": ExecutionLimits(),
        "protocol_version": "1",
    }
    fields.update(overrides)
    return CandidateExecutionRequest(**fields)  # type: ignore[arg-type]


def test_request_round_trips_through_serialize_and_parse() -> None:
    """A request serializes and parses back to an equivalent invocation."""
    request = _make_request(args=(1, [2, 3], (4, 5)), kwargs={"flag": True})

    payload = serialize_request(request)
    invocation = parse_request_message(payload, request.limits.max_request_bytes)

    assert invocation.entry_point == "f"
    assert invocation.candidate_code == request.candidate_code
    assert invocation.args == (1, [2, 3], (4, 5))
    assert invocation.kwargs == {"flag": True}
    assert invocation.max_stdout_bytes == request.limits.max_stdout_bytes
    assert invocation.max_stderr_bytes == request.limits.max_stderr_bytes
    assert invocation.max_response_bytes == request.limits.max_response_bytes


def test_serialize_request_enforces_max_request_bytes() -> None:
    """An oversized request is rejected before it ever reaches the worker."""
    request = _make_request(
        candidate_code="x" * 100,
        limits=ExecutionLimits(max_request_bytes=10),
    )

    with pytest.raises(ProtocolError, match="exceeds limit"):
        serialize_request(request)


def test_parse_request_message_enforces_max_request_bytes() -> None:
    """The worker-side parser also enforces the size limit independently."""
    oversized_payload = b"{}" * 1000

    with pytest.raises(ProtocolError, match="exceeds limit"):
        parse_request_message(oversized_payload, max_request_bytes=10)


def test_parse_request_message_rejects_malformed_json() -> None:
    """Non-JSON or truncated payloads are rejected as protocol errors."""
    with pytest.raises(ProtocolError, match="malformed request payload"):
        parse_request_message(b"{not json", max_request_bytes=1_000_000)


def _request_message(**overrides: object) -> dict[str, object]:
    message: dict[str, object] = {
        "protocol_version": "1",
        "operation": "invoke",
        "entry_point": "f",
        "candidate_code": "def f(): pass",
        "args": [],
        "kwargs": {},
        "max_stdout_bytes": 65_536,
        "max_stderr_bytes": 65_536,
        "max_response_bytes": 1_048_576,
    }
    message.update(overrides)
    return message


@pytest.mark.parametrize(
    "missing_field",
    [
        "protocol_version",
        "operation",
        "entry_point",
        "candidate_code",
        "args",
        "kwargs",
        "max_stdout_bytes",
        "max_stderr_bytes",
        "max_response_bytes",
    ],
)
def test_parse_request_message_rejects_missing_fields(missing_field: str) -> None:
    """Any missing required field is rejected explicitly."""
    message = _request_message()
    del message[missing_field]
    payload = json.dumps(message).encode("utf-8")

    with pytest.raises(ProtocolError, match="missing required fields"):
        parse_request_message(payload, max_request_bytes=1_000_000)


def test_parse_request_message_rejects_unsupported_operation() -> None:
    """A request naming an operation other than 'invoke' is rejected."""
    payload = json.dumps(_request_message(operation="delete_everything")).encode("utf-8")

    with pytest.raises(ProtocolError, match="unsupported operation"):
        parse_request_message(payload, max_request_bytes=1_000_000)


def _make_response(**overrides: object) -> RunnerResponse:
    fields: dict[str, object] = {
        "status": ExecutionStatus.COMPLETED,
        "return_value": 42,
        "exception_type": None,
        "exception_message": None,
        "stdout": "",
        "stderr": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "candidate_wall_time_sec": 0.001,
    }
    fields.update(overrides)
    return RunnerResponse(**fields)  # type: ignore[arg-type]


def test_response_round_trips_through_serialize_and_parse() -> None:
    """A COMPLETED response serializes and parses back with its return value intact."""
    response = _make_response(return_value=[1, "two", (3,)])

    payload = serialize_response(response, max_response_bytes=1_000_000)
    parsed = parse_response_message(payload, max_response_bytes=1_000_000)

    assert parsed.status == ExecutionStatus.COMPLETED
    assert parsed.return_value == [1, "two", (3,)]


def test_completed_response_distinguishes_none_return_from_no_return_value() -> None:
    """A candidate that returns None must round-trip differently from a failed invocation."""
    completed_none = _make_response(status=ExecutionStatus.COMPLETED, return_value=None)
    failed = _make_response(
        status=ExecutionStatus.CANDIDATE_EXCEPTION,
        return_value=None,
        exception_type="ValueError",
        exception_message="boom",
    )

    completed_payload = serialize_response(completed_none, max_response_bytes=1_000_000)
    failed_payload = serialize_response(failed, max_response_bytes=1_000_000)

    completed_message = json.loads(completed_payload)
    failed_message = json.loads(failed_payload)

    # COMPLETED + None is tagged; failure statuses carry a bare null.
    assert completed_message["return_value"] == {"type": "none", "value": None}
    assert failed_message["return_value"] is None

    assert parse_response_message(completed_payload, 1_000_000).return_value is None
    assert parse_response_message(failed_payload, 1_000_000).return_value is None


def test_serialize_response_enforces_max_response_bytes() -> None:
    """An oversized response is rejected before it leaves the worker."""
    response = _make_response(stdout="x" * 1000)

    with pytest.raises(ProtocolError, match="exceeds limit"):
        serialize_response(response, max_response_bytes=10)


def test_parse_response_message_rejects_unknown_status() -> None:
    """A response naming a status outside the taxonomy is rejected."""
    message = {
        "status": "PASSED",  # deliberately excluded from ExecutionStatus
        "return_value": None,
        "exception_type": None,
        "exception_message": None,
        "stdout": "",
        "stderr": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "candidate_wall_time_sec": 0.0,
    }
    payload = json.dumps(message).encode("utf-8")

    with pytest.raises(ProtocolError, match="unsupported status"):
        parse_response_message(payload, max_response_bytes=1_000_000)
