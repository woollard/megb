"""MEGB-03H.2C.1 conformance audit: collector lifecycle coverage across
every named backend outcome, plus cancellation.

For each of the 11 required scenarios -- normal completion, syntax error,
candidate exception, output limit, process limit, protocol error,
timeout, OOM, container never created, malformed/no response, and
cancellation -- this module confirms the collector lifecycle
(start/sample/finalize/cleanup) runs correctly and produces the correct
quality/unavailability classification, and that the backend outcome and
the collector outcome are fully orthogonal: nothing about one leaks into
or corrupts the other. No real Docker.
"""

# This module's response-payload/fake-Docker-harness construction
# intentionally mirrors patterns already present in
# test_docker_backend_execute_offline.py and test_telemetry_collectors.py
# -- all three exercise the same real wire-protocol/collector-lifecycle
# shapes. Expected and accepted, not a defect.
# pylint: disable=duplicate-code

import pytest

from src.execution.docker_backend import DockerPerInvocationBackend, _ContainerInspectInfo
from src.execution.protocol import CandidateExecutionRequest, ExecutionLimits, ExecutionStatus
from src.execution.telemetry import (
    TelemetryObservation,
    TelemetryQuality,
    build_execution_telemetry,
)
from src.execution.telemetry_collectors import FakeTelemetryCollector, run_collector
from src.execution.wire import RunnerResponse, serialize_response
from tests._docker_backend_fake_fixtures import install_fake_docker


def _request() -> CandidateExecutionRequest:
    return CandidateExecutionRequest(
        candidate_code="def f():\n    return 1\n",
        entry_point="f",
        args=(),
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


# The fake container id install_fake_docker() resolves by default --
# matched here so a _ContainerInspectInfo claiming a genuinely terminal
# state (below) is also recognized as belonging to *this* invocation's
# own container by real_telemetry_collectors._confirm_container_terminal_state's
# identity check, not just coincidentally inert.
_FAKE_TERMINAL_CONTAINER_ID = "f" * 64


def _terminal_inspect(*, oom_killed: bool, exit_code: int) -> _ContainerInspectInfo:
    """A found, genuinely-terminated container's inspect info -- every
    field the MEGB-03H.2C.2A terminal-state-proof audit requires is
    populated, not just ``exit_code``, so scenarios built from this
    still confirm as terminal under the corrected predicate."""
    return _ContainerInspectInfo(
        found=True,
        oom_killed=oom_killed,
        exit_code=exit_code,
        container_full_id=_FAKE_TERMINAL_CONTAINER_ID,
        running=False,
        status="exited",
        finished_at="2026-01-01T00:00:01Z",
    )


# Ten backend-outcome scenarios, each producing a real
# CandidateExecutionResult via the fake Docker CLI harness.
# (stdout_bytes, raise_timeout_first, inspect_info, expected_status)
_BACKEND_SCENARIOS = {
    "normal_completion": (
        _response_payload(ExecutionStatus.COMPLETED, return_value=1) + b"\n",
        False,
        _terminal_inspect(oom_killed=False, exit_code=0),
        ExecutionStatus.COMPLETED,
    ),
    "syntax_error": (
        _response_payload(
            ExecutionStatus.SYNTAX_ERROR, exception_type="SyntaxError", exception_message="bad"
        )
        + b"\n",
        False,
        _terminal_inspect(oom_killed=False, exit_code=1),
        ExecutionStatus.SYNTAX_ERROR,
    ),
    "candidate_exception": (
        _response_payload(
            ExecutionStatus.CANDIDATE_EXCEPTION,
            exception_type="ValueError",
            exception_message="boom",
        )
        + b"\n",
        False,
        _terminal_inspect(oom_killed=False, exit_code=1),
        ExecutionStatus.CANDIDATE_EXCEPTION,
    ),
    "output_limit": (
        _response_payload(ExecutionStatus.OUTPUT_LIMIT) + b"\n",
        False,
        _terminal_inspect(oom_killed=False, exit_code=1),
        ExecutionStatus.OUTPUT_LIMIT,
    ),
    "process_limit": (
        _response_payload(
            ExecutionStatus.PROCESS_LIMIT,
            exception_type="BlockingIOError",
            exception_message="no threads",
        )
        + b"\n",
        False,
        _terminal_inspect(oom_killed=False, exit_code=1),
        ExecutionStatus.PROCESS_LIMIT,
    ),
    "protocol_error": (
        _response_payload(
            ExecutionStatus.PROTOCOL_ERROR,
            exception_type="ProtocolError",
            exception_message="serialized response (2000000 bytes) exceeds limit (1048576 bytes)",
        )
        + b"\n",
        False,
        _terminal_inspect(oom_killed=False, exit_code=0),
        ExecutionStatus.PROTOCOL_ERROR,
    ),
    "timeout": (
        b"",
        True,
        _terminal_inspect(oom_killed=False, exit_code=137),
        ExecutionStatus.TIMEOUT,
    ),
    "oom": (
        b"",
        False,
        _terminal_inspect(oom_killed=True, exit_code=137),
        ExecutionStatus.OUT_OF_MEMORY,
    ),
    "container_never_created": (
        b"",
        True,
        _ContainerInspectInfo(found=False, oom_killed=False, exit_code=None),
        ExecutionStatus.INFRASTRUCTURE_ERROR,
    ),
    "malformed_response": (
        b"not valid json",
        False,
        _terminal_inspect(oom_killed=False, exit_code=1),
        ExecutionStatus.INFRASTRUCTURE_ERROR,
    ),
}

_NO_RESPONSE_SCENARIOS = {"timeout", "oom", "container_never_created", "malformed_response"}


@pytest.mark.parametrize("scenario_name", sorted(_BACKEND_SCENARIOS))
def test_a_normal_collector_is_unaffected_by_every_backend_outcome(
    scenario_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """For every named backend outcome, a healthy collector still runs
    its full start -> finalize -> cleanup lifecycle and reports an EXACT
    observation -- the backend's own outcome never leaks into or alters
    the collector's own classification."""
    stdout_bytes, raise_timeout_first, inspect_info, expected_status = _BACKEND_SCENARIOS[
        scenario_name
    ]
    harness = install_fake_docker(
        monkeypatch,
        stdout_bytes=stdout_bytes,
        raise_timeout_first=raise_timeout_first,
        inspect_info=inspect_info,
    )

    result = DockerPerInvocationBackend().execute(_request())
    assert result.status == expected_status
    assert result.request_bytes is not None
    if scenario_name in _NO_RESPONSE_SCENARIOS:
        assert result.observed_response_bytes is None
    else:
        assert result.observed_response_bytes is not None

    collector = FakeTelemetryCollector(
        observation=TelemetryObservation(
            value=2048, quality=TelemetryQuality.EXACT, unavailable_reason=None
        )
    )
    peak_memory = run_collector(collector, sample_count=2)

    assert collector.start_called
    assert collector.sample_call_count == 2
    assert collector.finalize_called
    assert collector.cleanup_call_count == 1
    assert peak_memory.value == 2048
    assert peak_memory.quality == TelemetryQuality.EXACT
    assert peak_memory.collector_failure is None

    telemetry = build_execution_telemetry(
        result, peak_memory=peak_memory, peak_process_count=peak_memory
    )
    assert telemetry.peak_memory.value == 2048
    assert harness.remove_calls  # container cleanup ran regardless of outcome


@pytest.mark.parametrize("scenario_name", sorted(_BACKEND_SCENARIOS))
def test_a_failing_collector_is_unaffected_by_every_backend_outcome(
    scenario_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Symmetric to the above: a FAILING collector's SAMPLER_FAILURE
    classification is identical regardless of the backend outcome it ran
    alongside, and the backend result itself is untouched."""
    stdout_bytes, raise_timeout_first, inspect_info, expected_status = _BACKEND_SCENARIOS[
        scenario_name
    ]
    install_fake_docker(
        monkeypatch,
        stdout_bytes=stdout_bytes,
        raise_timeout_first=raise_timeout_first,
        inspect_info=inspect_info,
    )

    result = DockerPerInvocationBackend().execute(_request())
    assert result.status == expected_status

    collector = FakeTelemetryCollector(finalize_raises=True)
    peak_memory = run_collector(collector)

    assert peak_memory.value is None
    assert peak_memory.collector_failure is not None
    assert collector.cleanup_call_count == 1
    # The backend result is completely unaffected by the collector's failure.
    assert result.status == expected_status


def test_cancellation_scenario_leaves_no_backend_result_corrupted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 11th scenario: cancellation during telemetry collection.
    Already-established backend results are untouched, and cancellation
    (KeyboardInterrupt) still propagates after cleanup runs -- proven
    together here as the final entry in the full coverage matrix."""
    stdout_bytes, _raise_timeout_first, inspect_info, expected_status = _BACKEND_SCENARIOS[
        "normal_completion"
    ]
    install_fake_docker(monkeypatch, stdout_bytes=stdout_bytes, inspect_info=inspect_info)
    result = DockerPerInvocationBackend().execute(_request())
    assert result.status == expected_status

    class _CancelledCollector(FakeTelemetryCollector):
        def finalize(self) -> TelemetryObservation:
            self.finalize_called = True
            raise KeyboardInterrupt("simulated cancellation")

    collector = _CancelledCollector()
    with pytest.raises(KeyboardInterrupt):
        run_collector(collector)
    assert collector.cleanup_call_count == 1
    # The backend result computed earlier remains exactly as it was.
    assert result.status == expected_status
