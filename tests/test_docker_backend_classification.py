"""Offline unit tests for docker_backend's pure outcome-classification logic.

``_classify_outcome`` and ``_derive_terminating_signal`` take already-
captured bytes/inspection results as plain arguments, so their branching
logic (TIMEOUT vs. INFRASTRUCTURE_ERROR vs. OUT_OF_MEMORY vs. runner-
reported status) can be verified without a real Docker daemon. Real
end-to-end behavior against actual containers is covered separately in
``tests/test_execution_sandbox.py`` (requires Docker).
"""

from src.execution.docker_backend import (
    _ContainerInspectInfo,
    _classify_outcome,
    _derive_terminating_signal,
    observed_response_byte_count,
)
from src.execution.protocol import ExecutionStatus
from src.execution.wire import RunnerResponse, serialize_response


def _not_found() -> _ContainerInspectInfo:
    return _ContainerInspectInfo(found=False, oom_killed=False, exit_code=None)


def _found(*, oom_killed: bool = False, exit_code: int | None = 0) -> _ContainerInspectInfo:
    return _ContainerInspectInfo(found=True, oom_killed=oom_killed, exit_code=exit_code)


def test_timeout_with_container_found_is_candidate_timeout() -> None:
    """A controller timeout after the container actually started is TIMEOUT."""
    outcome = _classify_outcome(
        timed_out=True,
        inspect_info=_found(exit_code=137),
        stdout_bytes=b"",
        stderr_bytes=b"",
        max_response_bytes=1_000_000,
    )

    assert outcome.status == ExecutionStatus.TIMEOUT
    assert outcome.candidate_wall_time_sec is None
    assert outcome.infrastructure_error_detail is None
    assert outcome.observed_response_bytes is None


def test_timeout_with_container_never_created_is_infrastructure_error() -> None:
    """A controller timeout where the container never even started is not the candidate's fault."""
    outcome = _classify_outcome(
        timed_out=True,
        inspect_info=_not_found(),
        stdout_bytes=b"",
        stderr_bytes=b"some docker error",
        max_response_bytes=1_000_000,
    )

    assert outcome.status == ExecutionStatus.INFRASTRUCTURE_ERROR
    assert outcome.infrastructure_error_detail is not None
    assert "never started" in outcome.infrastructure_error_detail
    assert outcome.observed_response_bytes is None


def test_oom_killed_takes_precedence_over_stdout_parsing() -> None:
    """An OOM-killed container is reported as OUT_OF_MEMORY even with no stdout."""
    outcome = _classify_outcome(
        timed_out=False,
        inspect_info=_found(oom_killed=True, exit_code=137),
        stdout_bytes=b"",
        stderr_bytes=b"",
        max_response_bytes=1_000_000,
    )

    assert outcome.status == ExecutionStatus.OUT_OF_MEMORY
    assert outcome.candidate_wall_time_sec is None
    assert outcome.observed_response_bytes is None


def _response_payload(
    status: ExecutionStatus,
    *,
    return_value: object = None,
    exception_type: str | None = None,
    exception_message: str | None = None,
) -> bytes:
    response = RunnerResponse(
        status=status,
        return_value=return_value,
        exception_type=exception_type,
        exception_message=exception_message,
        stdout="hi",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        candidate_wall_time_sec=0.0123,
    )
    return serialize_response(response, max_response_bytes=1_000_000)


def test_valid_runner_response_is_passed_through_with_candidate_wall_time() -> None:
    """A well-formed runner response's status and candidate duration pass through untouched."""
    payload = _response_payload(ExecutionStatus.COMPLETED, return_value=7)

    outcome = _classify_outcome(
        timed_out=False,
        inspect_info=_found(exit_code=0),
        stdout_bytes=payload + b"\n",
        stderr_bytes=b"",
        max_response_bytes=1_000_000,
    )

    assert outcome.status == ExecutionStatus.COMPLETED
    assert outcome.return_value == 7
    assert outcome.candidate_wall_time_sec == 0.0123
    assert outcome.infrastructure_error_detail is None
    # Raw, untrimmed byte count -- includes the framing newline main() appends.
    assert outcome.observed_response_bytes == len(payload) + 1


def test_unparseable_stdout_is_infrastructure_error() -> None:
    """Garbage on stdout (no valid runner response at all) is an infrastructure error."""
    outcome = _classify_outcome(
        timed_out=False,
        inspect_info=_found(exit_code=1),
        stdout_bytes=b"not json at all",
        stderr_bytes=b"",
        max_response_bytes=1_000_000,
    )

    assert outcome.status == ExecutionStatus.INFRASTRUCTURE_ERROR
    assert outcome.infrastructure_error_detail is not None
    assert outcome.observed_response_bytes is None


# ---------------------------------------------------------------------------
# Controller-side byte accounting (MEGB-03H.2C.1): observed_response_bytes
# ---------------------------------------------------------------------------


def test_observed_response_byte_count_is_none_for_timeout_oom_and_infrastructure_error() -> None:
    """No completed response ever existed for these three statuses."""
    for status in (
        ExecutionStatus.TIMEOUT,
        ExecutionStatus.OUT_OF_MEMORY,
        ExecutionStatus.INFRASTRUCTURE_ERROR,
    ):
        assert observed_response_byte_count(status=status, stdout_bytes=b"anything") is None


def test_observed_response_byte_count_is_exact_for_every_completed_response_status() -> None:
    """A real, parseable response yields an exact, RAW (untrimmed) byte
    count for every status the runner can terminally report on its own --
    syntax error, candidate exception, output/process limit, protocol
    error, and ordinary completion."""
    for status in (
        ExecutionStatus.COMPLETED,
        ExecutionStatus.SYNTAX_ERROR,
        ExecutionStatus.CANDIDATE_EXCEPTION,
        ExecutionStatus.OUTPUT_LIMIT,
        ExecutionStatus.PROCESS_LIMIT,
        ExecutionStatus.PROTOCOL_ERROR,
    ):
        stdout_bytes = f"some {status.value} payload".encode() + b"\n"
        assert observed_response_byte_count(status=status, stdout_bytes=stdout_bytes) == len(
            stdout_bytes
        )


def test_observed_response_byte_count_never_strips_a_trailing_newline() -> None:
    """Deliberately does NOT mirror parse_response_message's own
    rstrip(b"\\n") -- that trim exists only to keep the parser's size
    check consistent with the runner's own (newline-exclusive)
    max_response_bytes check, and must never leak into this raw
    byte-accounting count."""
    assert observed_response_byte_count(
        status=ExecutionStatus.COMPLETED, stdout_bytes=b"abc\n"
    ) == 4
    assert observed_response_byte_count(
        status=ExecutionStatus.COMPLETED, stdout_bytes=b"abc"
    ) == 3
    # Even multiple/unusual trailing bytes are counted raw, never trimmed.
    assert observed_response_byte_count(
        status=ExecutionStatus.COMPLETED, stdout_bytes=b"abc\n\n"
    ) == 5


def test_syntax_error_and_candidate_exception_report_exact_observed_response_bytes() -> None:
    """Real runner responses for a syntax error and a candidate exception
    both parse successfully and report an exact byte count."""
    for status, exc_type, exc_message in (
        (ExecutionStatus.SYNTAX_ERROR, "SyntaxError", "invalid syntax"),
        (ExecutionStatus.CANDIDATE_EXCEPTION, "ValueError", "boom"),
        (ExecutionStatus.OUTPUT_LIMIT, None, None),
        (ExecutionStatus.PROCESS_LIMIT, "BlockingIOError", "no threads"),
    ):
        payload = _response_payload(status, exception_type=exc_type, exception_message=exc_message)
        outcome = _classify_outcome(
            timed_out=False,
            inspect_info=_found(exit_code=1),
            stdout_bytes=payload + b"\n",
            stderr_bytes=b"",
            max_response_bytes=1_000_000,
        )
        assert outcome.status == status
        assert outcome.observed_response_bytes == len(payload) + 1


def test_protocol_error_response_reports_exact_observed_response_bytes() -> None:
    """The runner's own oversized-response fallback (PROTOCOL_ERROR) still
    parses successfully -- it is a real, completed response describing a
    protocol failure, not a missing one."""
    payload = _response_payload(
        ExecutionStatus.PROTOCOL_ERROR,
        exception_type="ProtocolError",
        exception_message="serialized response (2000000 bytes) exceeds limit (1048576 bytes)",
    )
    outcome = _classify_outcome(
        timed_out=False,
        inspect_info=_found(exit_code=0),
        stdout_bytes=payload + b"\n",
        stderr_bytes=b"",
        max_response_bytes=1_000_000,
    )
    assert outcome.status == ExecutionStatus.PROTOCOL_ERROR
    assert outcome.observed_response_bytes == len(payload) + 1


def test_derive_terminating_signal_from_exit_code() -> None:
    """Exit codes >= 128 map back to the conventional signal number; others don't."""
    assert _derive_terminating_signal(137) == 9  # SIGKILL
    assert _derive_terminating_signal(139) == 11  # SIGSEGV
    assert _derive_terminating_signal(0) is None
    assert _derive_terminating_signal(1) is None
    assert _derive_terminating_signal(None) is None
