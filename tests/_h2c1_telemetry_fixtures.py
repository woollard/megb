"""Synthetic CandidateExecutionResult factory shared across the
MEGB-03H.2C.1 test modules (test_response_overflow.py,
test_execution_telemetry.py, test_execution_telemetry_adapter.py,
test_docker_backend_classification.py) -- kept in one place so they all
exercise the exact same baseline fixture rather than several drifting
copies. No real Docker, no privileged content.
"""

# This factory's field-by-field construction intentionally mirrors
# test_reference_evaluator.py's own pre-existing (unmodified, per H.2C.1's
# backward-compatibility requirement) CandidateExecutionResult fixture --
# both build the same real MEGB-02 dataclass shape. Expected and accepted,
# not a defect.
# pylint: disable=duplicate-code

from src.execution.protocol import CandidateExecutionResult, ExecutionLimits, ExecutionStatus


def make_candidate_execution_result(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    candidate_wall_time_sec: float | None = 0.05,
    request_bytes: int | None = 100,
    observed_response_bytes: int | None = 50,
    exception_type: str | None = None,
    exception_message: str | None = None,
    wall_time_sec: float = 0.5,
    invocation_id: str = "inv-1",
) -> CandidateExecutionResult:
    """A structurally valid CandidateExecutionResult, fields overridable."""
    return CandidateExecutionResult(
        invocation_id=invocation_id,
        status=status,
        return_value=None,
        exception_type=exception_type,
        exception_message=exception_message,
        wall_time_sec=wall_time_sec,
        candidate_wall_time_sec=candidate_wall_time_sec,
        exit_code=0,
        terminating_signal=None,
        stdout="",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        backend_id="fake",
        backend_version="1",
        runner_image_digest="sha256:fake",
        protocol_version="v1",
        limits=ExecutionLimits(),
        started_at="2026-08-03T00:00:00Z",
        request_bytes=request_bytes,
        observed_response_bytes=observed_response_bytes,
    )
