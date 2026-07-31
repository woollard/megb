"""Versioned, safe tagged-JSON serialization protocol.

Never uses ``pickle``, ``marshal``, ``eval``, or another unsafe
deserialization mechanism across the trust boundary between the trusted
controller and the isolated candidate worker. All messages are plain JSON
with an explicit type tag on every scalar/collection, so unsupported types
(functions, classes, sets, custom objects, bytes, ...) are rejected
explicitly rather than silently coerced.
"""

import json
from dataclasses import dataclass
from typing import Any, Mapping

from src.execution.protocol import CandidateExecutionRequest, ExecutionStatus

REQUEST_OPERATION = "invoke"

_SUPPORTED_TAGS = frozenset(
    {"none", "bool", "int", "float", "str", "list", "tuple", "dict"}
)


class ProtocolError(ValueError):
    """Raised when a wire message is malformed, oversized, or type-unsafe."""


@dataclass(frozen=True)
class RunnerInvocation:
    """A decoded invocation ready to execute inside the candidate worker.

    Carries only the output/response bounds the runner itself must enforce
    live (stdout/stderr buffering, response size). Other ``ExecutionLimits``
    fields (wall clock, memory, process count, ...) are enforced by the
    trusted controller via the container runtime, not by the runner.
    """

    entry_point: str
    candidate_code: str
    args: tuple[Any, ...]
    kwargs: Mapping[str, Any]
    max_stdout_bytes: int
    max_stderr_bytes: int
    max_response_bytes: int


@dataclass(frozen=True)
class RunnerResponse:
    """The runner's own report of one invocation, before controller enrichment.

    The controller merges this with metadata it alone can observe (exit
    code, signal, total backend duration, backend/image identity) to build
    the final ``CandidateExecutionResult``. ``candidate_wall_time_sec`` is
    measured by the runner itself around just the candidate's own
    execution, distinct from the controller's total backend duration (which
    also includes container start/stop overhead).
    """

    status: ExecutionStatus
    return_value: Any | None
    exception_type: str | None
    exception_message: str | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    candidate_wall_time_sec: float


def encode_value(value: Any) -> dict[str, Any]:  # pylint: disable=too-many-return-statements
    """Encode a Python value into a tagged wire representation.

    Supports ``None``, ``bool``, ``int``, ``float``, ``str``, ``list``,
    ``tuple``, and ``dict`` (string keys only), recursively. All other
    types are rejected explicitly. The early-return type dispatch below
    (rather than a lookup table) is deliberate: ``bool`` must be checked
    before ``int`` since ``bool`` is an ``int`` subclass, and a flat
    sequence of checks makes that ordering requirement visible.
    """
    if value is None:
        return {"type": "none", "value": None}
    if isinstance(value, bool):  # must precede int: bool is an int subclass
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": value}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, str):
        return {"type": "str", "value": value}
    if isinstance(value, list):
        return {"type": "list", "items": [encode_value(item) for item in value]}
    if isinstance(value, tuple):
        return {"type": "tuple", "items": [encode_value(item) for item in value]}
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise ProtocolError(f"dict keys must be strings, got {type(key).__name__}")
        return {
            "type": "dict",
            "entries": [{"key": k, "value": encode_value(v)} for k, v in value.items()],
        }
    raise ProtocolError(f"unsupported value type for wire encoding: {type(value).__name__}")


def decode_value(tagged: Any) -> Any:  # pylint: disable=too-many-return-statements
    """Decode a tagged wire representation back into a Python value.

    See ``encode_value`` for why this uses a flat type-tag dispatch.
    """
    if not isinstance(tagged, Mapping) or "type" not in tagged:
        raise ProtocolError("malformed tagged value: expected an object with a 'type' field")
    tag = tagged["type"]
    if tag not in _SUPPORTED_TAGS:
        raise ProtocolError(f"unsupported tagged type: {tag!r}")
    if tag == "none":
        return None
    if tag == "bool":
        return bool(tagged["value"])
    if tag == "int":
        return int(tagged["value"])
    if tag == "float":
        return float(tagged["value"])
    if tag == "str":
        return str(tagged["value"])
    if tag == "list":
        return [decode_value(item) for item in tagged["items"]]
    if tag == "tuple":
        return tuple(decode_value(item) for item in tagged["items"])
    return {entry["key"]: decode_value(entry["value"]) for entry in tagged["entries"]}


def _encode_kwargs(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    return {key: encode_value(value) for key, value in kwargs.items()}


def _decode_kwargs(tagged_kwargs: Mapping[str, Any]) -> dict[str, Any]:
    return {key: decode_value(value) for key, value in tagged_kwargs.items()}


def _dumps_and_check_size(message: Mapping[str, Any], max_bytes: int, label: str) -> bytes:
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if len(payload) > max_bytes:
        raise ProtocolError(
            f"serialized {label} ({len(payload)} bytes) exceeds limit ({max_bytes} bytes)"
        )
    return payload


def serialize_request(request: CandidateExecutionRequest) -> bytes:
    """Serialize a request to a size-bounded, tagged-JSON wire payload."""
    message = {
        "protocol_version": request.protocol_version,
        "operation": REQUEST_OPERATION,
        "entry_point": request.entry_point,
        "candidate_code": request.candidate_code,
        "args": [encode_value(v) for v in request.args],
        "kwargs": _encode_kwargs(request.kwargs),
        "max_stdout_bytes": request.limits.max_stdout_bytes,
        "max_stderr_bytes": request.limits.max_stderr_bytes,
        "max_response_bytes": request.limits.max_response_bytes,
    }
    return _dumps_and_check_size(message, request.limits.max_request_bytes, "request")


def parse_request_message(payload: bytes, max_request_bytes: int) -> RunnerInvocation:
    """Parse and validate a request payload inside the candidate worker."""
    if len(payload) > max_request_bytes:
        raise ProtocolError(
            f"request payload ({len(payload)} bytes) exceeds limit ({max_request_bytes} bytes)"
        )
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"malformed request payload: {exc}") from exc

    if not isinstance(message, dict):
        raise ProtocolError("malformed request payload: expected a JSON object")
    required = {
        "protocol_version",
        "operation",
        "entry_point",
        "candidate_code",
        "args",
        "kwargs",
        "max_stdout_bytes",
        "max_stderr_bytes",
        "max_response_bytes",
    }
    missing = required - message.keys()
    if missing:
        raise ProtocolError(f"request payload missing required fields: {sorted(missing)}")
    if message["operation"] != REQUEST_OPERATION:
        raise ProtocolError(f"unsupported operation: {message['operation']!r}")

    return RunnerInvocation(
        entry_point=message["entry_point"],
        candidate_code=message["candidate_code"],
        args=tuple(decode_value(item) for item in message["args"]),
        kwargs=_decode_kwargs(message["kwargs"]),
        max_stdout_bytes=message["max_stdout_bytes"],
        max_stderr_bytes=message["max_stderr_bytes"],
        max_response_bytes=message["max_response_bytes"],
    )


def serialize_response(response: RunnerResponse, max_response_bytes: int) -> bytes:
    """Serialize a runner response to a size-bounded, tagged-JSON wire payload.

    ``return_value`` is only meaningful when ``status`` is ``COMPLETED``: a
    candidate that genuinely returns ``None`` must be distinguishable from a
    failed invocation that has no return value at all. That distinction is
    carried by ``status`` alone, not by the wire shape of ``return_value``:
    only the ``COMPLETED`` case is tagged (so a real ``None`` still round
    trips as ``{"type": "none", ...}``); every other status is encoded as a
    bare JSON ``null`` and must be treated as inapplicable on decode.
    """
    message = {
        "status": response.status.value,
        "return_value": (
            encode_value(response.return_value)
            if response.status is ExecutionStatus.COMPLETED
            else None
        ),
        "exception_type": response.exception_type,
        "exception_message": response.exception_message,
        "stdout": response.stdout,
        "stderr": response.stderr,
        "stdout_truncated": response.stdout_truncated,
        "stderr_truncated": response.stderr_truncated,
        "candidate_wall_time_sec": response.candidate_wall_time_sec,
    }
    return _dumps_and_check_size(message, max_response_bytes, "response")


def parse_response_message(payload: bytes, max_response_bytes: int) -> RunnerResponse:
    """Parse and validate a response payload on the trusted controller side."""
    if len(payload) > max_response_bytes:
        raise ProtocolError(
            f"response payload ({len(payload)} bytes) exceeds limit ({max_response_bytes} bytes)"
        )
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"malformed response payload: {exc}") from exc

    if not isinstance(message, dict):
        raise ProtocolError("malformed response payload: expected a JSON object")
    required = {
        "status",
        "return_value",
        "exception_type",
        "exception_message",
        "stdout",
        "stderr",
        "stdout_truncated",
        "stderr_truncated",
        "candidate_wall_time_sec",
    }
    missing = required - message.keys()
    if missing:
        raise ProtocolError(f"response payload missing required fields: {sorted(missing)}")
    try:
        status = ExecutionStatus(message["status"])
    except ValueError as exc:
        raise ProtocolError(f"unsupported status in response: {message['status']!r}") from exc

    return RunnerResponse(
        status=status,
        return_value=(
            None if message["return_value"] is None else decode_value(message["return_value"])
        ),
        exception_type=message["exception_type"],
        exception_message=message["exception_message"],
        stdout=message["stdout"],
        stderr=message["stderr"],
        stdout_truncated=message["stdout_truncated"],
        stderr_truncated=message["stderr_truncated"],
        candidate_wall_time_sec=message["candidate_wall_time_sec"],
    )
