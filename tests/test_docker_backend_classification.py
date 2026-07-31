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


def test_valid_runner_response_is_passed_through_with_candidate_wall_time() -> None:
    """A well-formed runner response's status and candidate duration pass through untouched."""
    response = RunnerResponse(
        status=ExecutionStatus.COMPLETED,
        return_value=7,
        exception_type=None,
        exception_message=None,
        stdout="hi",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        candidate_wall_time_sec=0.0123,
    )
    payload = serialize_response(response, max_response_bytes=1_000_000)

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


def test_derive_terminating_signal_from_exit_code() -> None:
    """Exit codes >= 128 map back to the conventional signal number; others don't."""
    assert _derive_terminating_signal(137) == 9  # SIGKILL
    assert _derive_terminating_signal(139) == 11  # SIGSEGV
    assert _derive_terminating_signal(0) is None
    assert _derive_terminating_signal(1) is None
    assert _derive_terminating_signal(None) is None
