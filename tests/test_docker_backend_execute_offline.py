"""MEGB-03H.2C.1 conformance audit: full DockerPerInvocationBackend.execute()
integration tests against a fake subprocess/Docker CLI
(tests/_docker_backend_fake_fixtures.py) -- no real Docker.

Proves, at the integration level (not just the pure-function level):

* request_bytes equals the exact bytes actually passed to communicate()
  -- the same bytes object, not a reserialization -- including for
  non-ASCII candidate source;
* observed_response_bytes equals the exact raw stdout bytes actually
  returned by communicate(), including multibyte UTF-8 response content
  and trailing framing bytes -- never a decoded/reserialized length;
* wire payloads (what's sent, what's parsed) are unaffected by whether
  telemetry fields are read afterward;
* request_bytes is populated on every terminal path, including
  TIMEOUT/OOM/container-never-created/malformed-response;
* the container is always removed exactly once, on every terminal path.
"""

# This module's RunnerResponse/_response_payload-style construction
# intentionally mirrors patterns already present in test_execution_wire.py
# and (for the ten backend-outcome scenarios) test_collector_lifecycle_coverage.py
# -- all three exercise the exact same real wire-protocol shapes.
# Expected and accepted, not a defect (same precedent as this codebase's
# other shared-vocabulary duplicate-code notes).
# pylint: disable=duplicate-code

import pytest

from src.execution.docker_backend import (
    DockerPerInvocationBackend,
    _ContainerInspectInfo,
    observed_response_byte_count,
)
from src.execution.protocol import CandidateExecutionRequest, ExecutionLimits, ExecutionStatus
from src.execution.wire import (
    ProtocolError,
    RunnerResponse,
    parse_response_message,
    serialize_request,
    serialize_response,
)
from tests._docker_backend_fake_fixtures import install_fake_docker


def _request(
    *, candidate_code: str = "def f():\n    return 1\n", args: tuple[object, ...] = ()
) -> CandidateExecutionRequest:
    return CandidateExecutionRequest(
        candidate_code=candidate_code,
        entry_point="f",
        args=args,
        kwargs={},
        limits=ExecutionLimits(),
        protocol_version="reference-evaluator-execution-protocol-v1",
    )


def _response_payload(status: ExecutionStatus, **kwargs: object) -> bytes:
    fields: dict[str, object] = {
        "status": status,
        "return_value": None,
        "exception_type": None,
        "exception_message": None,
        "stdout": "",
        "stderr": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "candidate_wall_time_sec": 0.01,
    }
    fields.update(kwargs)
    response = RunnerResponse(**fields)  # type: ignore[arg-type]
    return serialize_response(response, max_response_bytes=10_000_000)


# ---------------------------------------------------------------------------
# request_bytes: exact bytes actually transmitted, non-ASCII candidate source
# ---------------------------------------------------------------------------


def test_request_bytes_equals_the_exact_bytes_passed_to_communicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """request_bytes is not a reserialization -- it is len() of the very
    same bytes object handed to communicate(input=...)."""
    request = _request(candidate_code="def f():\n    return '日本語のコメント'\n")
    payload = _response_payload(ExecutionStatus.COMPLETED, return_value=1)
    harness = install_fake_docker(monkeypatch, stdout_bytes=payload + b"\n")

    result = DockerPerInvocationBackend().execute(request)

    assert len(harness.popens) == 1
    transmitted_input = harness.popens[0].communicate_calls[0]["input"]
    assert isinstance(transmitted_input, bytes)
    assert result.request_bytes == len(transmitted_input)
    # And that transmitted payload is itself exactly what wire.serialize_request
    # independently produces for this same request -- proving no drift.
    assert transmitted_input == serialize_request(request)


def test_request_bytes_counts_real_utf8_bytes_not_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-ASCII candidate source: request_bytes must reflect UTF-8
    encoded byte length, not Python character count (which would
    undercount multibyte characters)."""
    non_ascii_code = "def f():\n    x = '日本語'\n    return x\n"
    request = _request(candidate_code=non_ascii_code)
    payload = _response_payload(ExecutionStatus.COMPLETED, return_value="ok")
    harness = install_fake_docker(monkeypatch, stdout_bytes=payload + b"\n")

    result = DockerPerInvocationBackend().execute(request)

    transmitted_input = harness.popens[0].communicate_calls[0]["input"]
    assert result.request_bytes == len(transmitted_input)
    # The Japanese characters are each 3 bytes in UTF-8 -- byte length
    # must exceed the raw character count of the source string.
    assert len(transmitted_input) > len(non_ascii_code)


# ---------------------------------------------------------------------------
# observed_response_bytes: exact raw stdout bytes, multibyte UTF-8, framing
# ---------------------------------------------------------------------------


def test_observed_response_bytes_equals_raw_stdout_bytes_with_multibyte_utf8(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A response whose return_value contains multibyte UTF-8 content:
    observed_response_bytes must equal the exact raw stdout byte count,
    never a decoded-string length."""
    payload = _response_payload(ExecutionStatus.COMPLETED, return_value="日本語のレスポンス")
    stdout_bytes = payload + b"\n"
    harness = install_fake_docker(monkeypatch, stdout_bytes=stdout_bytes)

    result = DockerPerInvocationBackend().execute(_request())

    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value == "日本語のレスポンス"
    assert result.observed_response_bytes == len(stdout_bytes)
    assert result.observed_response_bytes == len(harness.popens[0].stdout_bytes)
    # Framing newline is counted, never stripped.
    assert result.observed_response_bytes == len(payload) + 1


def test_observed_response_bytes_counts_the_framing_newline() -> None:
    """Direct proof the framing byte is included, isolated from any Popen
    plumbing: two payloads differing only by the trailing newline count
    as different byte counts."""
    payload = _response_payload(ExecutionStatus.COMPLETED, return_value=1)
    assert observed_response_byte_count(
        status=ExecutionStatus.COMPLETED, stdout_bytes=payload
    ) == len(payload)
    assert observed_response_byte_count(
        status=ExecutionStatus.COMPLETED, stdout_bytes=payload + b"\n"
    ) == len(payload) + 1


# ---------------------------------------------------------------------------
# Wire payloads unaffected by telemetry: what's sent/parsed matches exactly
# ---------------------------------------------------------------------------


def test_wire_payload_and_parsed_status_are_unaffected_by_telemetry_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Independently recomputing the parsed response from the exact same
    raw bytes the fake backend returned yields the identical
    status/return_value the result carries -- telemetry never alters what
    the wire protocol itself determines."""
    payload = _response_payload(ExecutionStatus.COMPLETED, return_value=[1, 2, 3])
    stdout_bytes = payload + b"\n"
    harness = install_fake_docker(monkeypatch, stdout_bytes=stdout_bytes)

    request = _request()
    result = DockerPerInvocationBackend().execute(request)

    independently_parsed = parse_response_message(
        stdout_bytes.rstrip(b"\n"), max_response_bytes=request.limits.max_response_bytes
    )
    assert result.status == independently_parsed.status
    assert result.return_value == independently_parsed.return_value
    assert harness.popens[0].communicate_calls[0]["input"] == serialize_request(request)


# ---------------------------------------------------------------------------
# request_bytes populated on every terminal path; container always removed
# ---------------------------------------------------------------------------


def test_timeout_path_populates_request_bytes_and_leaves_response_bytes_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """request_bytes is populated even when the container is killed
    before ever producing a response."""
    harness = install_fake_docker(
        monkeypatch,
        stdout_bytes=b"",
        raise_timeout_first=True,
        inspect_info=_ContainerInspectInfo(found=True, oom_killed=False, exit_code=137),
    )
    request = _request()

    result = DockerPerInvocationBackend().execute(request)

    assert result.status == ExecutionStatus.TIMEOUT
    assert result.request_bytes == len(serialize_request(request))
    assert result.observed_response_bytes is None
    assert harness.remove_calls  # container still cleaned up


def test_container_never_created_populates_request_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """request_bytes is populated even when the container never started."""
    harness = install_fake_docker(
        monkeypatch,
        stdout_bytes=b"",
        raise_timeout_first=True,
        inspect_info=_ContainerInspectInfo(found=False, oom_killed=False, exit_code=None),
    )
    request = _request()

    result = DockerPerInvocationBackend().execute(request)

    assert result.status == ExecutionStatus.INFRASTRUCTURE_ERROR
    assert result.request_bytes == len(serialize_request(request))
    assert result.observed_response_bytes is None
    assert harness.remove_calls


def test_oom_populates_request_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """request_bytes is populated even when the container is OOM-killed."""
    harness = install_fake_docker(
        monkeypatch,
        stdout_bytes=b"",
        inspect_info=_ContainerInspectInfo(found=True, oom_killed=True, exit_code=137),
    )
    request = _request()

    result = DockerPerInvocationBackend().execute(request)

    assert result.status == ExecutionStatus.OUT_OF_MEMORY
    assert result.request_bytes == len(serialize_request(request))
    assert result.observed_response_bytes is None
    assert harness.remove_calls


def test_malformed_response_populates_request_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """request_bytes is populated even when the response fails to parse."""
    harness = install_fake_docker(monkeypatch, stdout_bytes=b"not valid json at all")
    request = _request()

    result = DockerPerInvocationBackend().execute(request)

    assert result.status == ExecutionStatus.INFRASTRUCTURE_ERROR
    assert result.request_bytes == len(serialize_request(request))
    assert result.observed_response_bytes is None
    assert harness.remove_calls


def test_container_is_removed_exactly_once_on_every_terminal_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pre-existing finally: _docker_remove(container_name) cleanup
    contract is unaffected by the new telemetry fields."""
    scenarios: list[tuple[bytes, bool, _ContainerInspectInfo]] = [
        (
            _response_payload(ExecutionStatus.COMPLETED, return_value=1) + b"\n",
            False,
            _ContainerInspectInfo(found=True, oom_killed=False, exit_code=0),
        ),
        (b"", True, _ContainerInspectInfo(found=True, oom_killed=False, exit_code=137)),
        (b"", False, _ContainerInspectInfo(found=True, oom_killed=True, exit_code=137)),
        (b"garbage", False, _ContainerInspectInfo(found=True, oom_killed=False, exit_code=1)),
    ]
    for stdout_bytes, raise_timeout_first, inspect_info in scenarios:
        harness = install_fake_docker(
            monkeypatch,
            stdout_bytes=stdout_bytes,
            raise_timeout_first=raise_timeout_first,
            inspect_info=inspect_info,
        )
        DockerPerInvocationBackend().execute(_request())
        assert len(harness.remove_calls) == 1


# ---------------------------------------------------------------------------
# Serialization-failure boundary: no invented telemetry for untransmitted bytes
# ---------------------------------------------------------------------------


def test_request_serialization_failure_terminates_before_any_container_or_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When wire.serialize_request itself raises (an unsupported argument
    type, here), execute() propagates that ProtocolError uncaught -- no
    container is ever created (Popen is never called, since serialization
    happens first), no cleanup is attempted (nothing to clean up), and no
    CandidateExecutionResult is ever constructed. request_bytes is never
    fabricated for bytes that were never transmitted."""
    harness = install_fake_docker(monkeypatch, stdout_bytes=b"")
    request = CandidateExecutionRequest(
        candidate_code="def f():\n    return 1\n",
        entry_point="f",
        args=(),
        kwargs={"bad": object()},  # unsupported wire type -> encode_value raises
        limits=ExecutionLimits(),
        protocol_version="reference-evaluator-execution-protocol-v1",
    )

    with pytest.raises(ProtocolError):
        DockerPerInvocationBackend().execute(request)

    assert not harness.popens  # no container was ever started
    assert not harness.remove_calls  # nothing to clean up, none attempted


def test_oversized_request_serialization_failure_terminates_before_any_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same boundary, triggered by exceeding max_request_bytes instead of
    an unsupported type."""
    harness = install_fake_docker(monkeypatch, stdout_bytes=b"")
    tiny_limits = ExecutionLimits(max_request_bytes=10)
    request = CandidateExecutionRequest(
        candidate_code="def f():\n    return 'much too long for the tiny limit'\n",
        entry_point="f",
        args=(),
        kwargs={},
        limits=tiny_limits,
        protocol_version="reference-evaluator-execution-protocol-v1",
    )

    with pytest.raises(ProtocolError):
        DockerPerInvocationBackend().execute(request)

    assert not harness.popens
    assert not harness.remove_calls
