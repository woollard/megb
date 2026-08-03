"""MEGB-03H.2C.1: tests for the execution-layer telemetry model
(src.execution.telemetry). Synthetic CandidateExecutionResult construction
only -- no real Docker.
"""

# The backward-compatibility test below deliberately constructs a
# CandidateExecutionResult the old way (no request_bytes/
# observed_response_bytes kwargs at all) rather than through
# tests/_h2c1_telemetry_fixtures.py's shared builder -- the whole point is
# to prove the pre-H.2C.1 construction style still works unmodified,
# independent of any new fixture. Expected overlap with that fixture's own
# body, not a defect.
# pylint: disable=duplicate-code

import dataclasses

import pytest

from src.execution.protocol import CandidateExecutionResult, ExecutionLimits, ExecutionStatus
from src.execution.telemetry import (
    CollectorFailureStage,
    InvalidTelemetryObservationError,
    TelemetryObservation,
    TelemetryQuality,
    TelemetryUnavailableReason,
    build_execution_telemetry,
    candidate_wall_time_observation,
    collector_failure_observation,
    observed_response_bytes_observation,
)
from tests._h2c1_telemetry_fixtures import make_candidate_execution_result as _result


# ---------------------------------------------------------------------------
# Backward compatibility: existing constructors are unaffected
# ---------------------------------------------------------------------------


def test_candidate_execution_result_still_constructs_without_the_new_fields() -> None:
    """Every existing caller/test that builds a CandidateExecutionResult
    without request_bytes/observed_response_bytes is unaffected -- both
    default to None."""
    result = CandidateExecutionResult(
        invocation_id="inv-1",
        status=ExecutionStatus.COMPLETED,
        return_value=1,
        exception_type=None,
        exception_message=None,
        wall_time_sec=0.1,
        candidate_wall_time_sec=0.05,
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
    )
    assert result.request_bytes is None
    assert result.observed_response_bytes is None


# ---------------------------------------------------------------------------
# TelemetryObservation invariants
# ---------------------------------------------------------------------------


def test_present_value_requires_quality_and_forbids_reason() -> None:
    """A present value must carry a quality and no unavailable_reason."""
    TelemetryObservation(value=1.0, quality=TelemetryQuality.EXACT, unavailable_reason=None)
    with pytest.raises(InvalidTelemetryObservationError):
        TelemetryObservation(value=1.0, quality=None, unavailable_reason=None)
    with pytest.raises(InvalidTelemetryObservationError):
        TelemetryObservation(
            value=1.0,
            quality=TelemetryQuality.EXACT,
            unavailable_reason=TelemetryUnavailableReason.NOT_APPLICABLE,
        )


def test_absent_value_requires_reason_and_forbids_quality() -> None:
    """An absent value must carry an unavailable_reason and no quality."""
    TelemetryObservation(
        value=None, quality=None, unavailable_reason=TelemetryUnavailableReason.NOT_APPLICABLE
    )
    with pytest.raises(InvalidTelemetryObservationError):
        TelemetryObservation(value=None, quality=None, unavailable_reason=None)
    with pytest.raises(InvalidTelemetryObservationError):
        TelemetryObservation(
            value=None, quality=TelemetryQuality.EXACT, unavailable_reason=None
        )


def test_collector_failure_requires_absent_value_and_sampler_failure_reason() -> None:
    """collector_failure always implies value=None and reason=SAMPLER_FAILURE."""
    collector_failure_observation(CollectorFailureStage.START)  # does not raise
    with pytest.raises(InvalidTelemetryObservationError):
        TelemetryObservation(
            value=1.0,
            quality=TelemetryQuality.EXACT,
            unavailable_reason=None,
            collector_failure=CollectorFailureStage.START,
        )
    with pytest.raises(InvalidTelemetryObservationError):
        TelemetryObservation(
            value=None,
            quality=None,
            unavailable_reason=TelemetryUnavailableReason.NOT_APPLICABLE,
            collector_failure=CollectorFailureStage.SAMPLE,
        )


def test_collector_failure_observation_builds_a_consistent_observation() -> None:
    """collector_failure_observation() itself always builds a valid instance."""
    for stage in CollectorFailureStage:
        observation = collector_failure_observation(stage)
        assert observation.value is None
        assert observation.quality is None
        assert observation.unavailable_reason == TelemetryUnavailableReason.SAMPLER_FAILURE
        assert observation.collector_failure == stage
        assert observation.cleanup_failed is False


def test_cleanup_failed_defaults_to_false_and_never_appears_uninvited() -> None:
    """Every existing construction path (no cleanup_failed kwarg at all)
    is unaffected -- it defaults to False."""
    observation = TelemetryObservation(
        value=1.0, quality=TelemetryQuality.EXACT, unavailable_reason=None
    )
    assert observation.cleanup_failed is False


def test_cleanup_failed_is_orthogonal_to_a_present_value() -> None:
    """cleanup_failed=True can coexist with a genuinely present, valid
    observation -- it is purely additive, never forcing value to None by
    itself (that conservative remapping happens only in the reference
    adapter, for calibration-release purposes -- not at this layer)."""
    observation = TelemetryObservation(
        value=1024, quality=TelemetryQuality.EXACT, unavailable_reason=None, cleanup_failed=True
    )
    assert observation.value == 1024
    assert observation.cleanup_failed is True


def test_cleanup_failed_can_coexist_with_a_collector_failure_stage() -> None:
    """cleanup_failed and collector_failure are independent axes -- both
    can be set at once, one never overwriting the other."""
    observation = collector_failure_observation(
        CollectorFailureStage.FINALIZE, cleanup_failed=True
    )
    assert observation.collector_failure == CollectorFailureStage.FINALIZE
    assert observation.unavailable_reason == TelemetryUnavailableReason.SAMPLER_FAILURE
    assert observation.cleanup_failed is True


# ---------------------------------------------------------------------------
# candidate_wall_time_observation / observed_response_bytes_observation:
# exhaustive ExecutionStatus coverage
# ---------------------------------------------------------------------------


_NO_RESPONSE_STATUSES = (
    ExecutionStatus.TIMEOUT,
    ExecutionStatus.OUT_OF_MEMORY,
    ExecutionStatus.INFRASTRUCTURE_ERROR,
)

_COMPLETED_RESPONSE_STATUSES = (
    ExecutionStatus.COMPLETED,
    ExecutionStatus.SYNTAX_ERROR,
    ExecutionStatus.CANDIDATE_EXCEPTION,
    ExecutionStatus.OUTPUT_LIMIT,
    ExecutionStatus.PROCESS_LIMIT,
    ExecutionStatus.PROTOCOL_ERROR,
)


def test_every_execution_status_is_covered_by_the_two_status_buckets() -> None:
    """Sanity check: every ExecutionStatus member falls into exactly one
    of the two buckets this module's status-driven logic relies on."""
    assert set(_NO_RESPONSE_STATUSES) | set(_COMPLETED_RESPONSE_STATUSES) == set(ExecutionStatus)
    assert not set(_NO_RESPONSE_STATUSES) & set(_COMPLETED_RESPONSE_STATUSES)


@pytest.mark.parametrize("status", _NO_RESPONSE_STATUSES)
def test_candidate_wall_time_is_unavailable_for_no_response_statuses(
    status: ExecutionStatus,
) -> None:
    """No completed response ever existed for TIMEOUT/OOM/INFRASTRUCTURE_ERROR."""
    result = _result(status=status, candidate_wall_time_sec=None, observed_response_bytes=None)
    observation = candidate_wall_time_observation(result)
    assert observation.value is None
    expected_reason = (
        TelemetryUnavailableReason.KILLED_BEFORE_COMPLETION
        if status in (ExecutionStatus.TIMEOUT, ExecutionStatus.OUT_OF_MEMORY)
        else TelemetryUnavailableReason.NO_RESPONSE_PRODUCED
    )
    assert observation.unavailable_reason == expected_reason


@pytest.mark.parametrize("status", _COMPLETED_RESPONSE_STATUSES)
def test_candidate_wall_time_is_exact_for_completed_response_statuses(
    status: ExecutionStatus,
) -> None:
    """A real, completed response always yields an EXACT observation."""
    result = _result(status=status, candidate_wall_time_sec=0.25, observed_response_bytes=42)
    observation = candidate_wall_time_observation(result)
    assert observation.value == 0.25
    assert observation.quality == TelemetryQuality.EXACT


@pytest.mark.parametrize("status", _NO_RESPONSE_STATUSES)
def test_observed_response_bytes_is_unavailable_for_no_response_statuses(
    status: ExecutionStatus,
) -> None:
    """No completed response ever existed for TIMEOUT/OOM/INFRASTRUCTURE_ERROR."""
    result = _result(status=status, candidate_wall_time_sec=None, observed_response_bytes=None)
    observation = observed_response_bytes_observation(result)
    assert observation.value is None
    expected_reason = (
        TelemetryUnavailableReason.KILLED_BEFORE_COMPLETION
        if status in (ExecutionStatus.TIMEOUT, ExecutionStatus.OUT_OF_MEMORY)
        else TelemetryUnavailableReason.NO_RESPONSE_PRODUCED
    )
    assert observation.unavailable_reason == expected_reason


@pytest.mark.parametrize("status", _COMPLETED_RESPONSE_STATUSES)
def test_observed_response_bytes_is_exact_for_completed_response_statuses(
    status: ExecutionStatus,
) -> None:
    """A real, completed response always yields an EXACT byte count."""
    result = _result(status=status, candidate_wall_time_sec=0.1, observed_response_bytes=99)
    observation = observed_response_bytes_observation(result)
    assert observation.value == 99
    assert observation.quality == TelemetryQuality.EXACT


# ---------------------------------------------------------------------------
# build_execution_telemetry
# ---------------------------------------------------------------------------


def _exact_observation(value: float) -> TelemetryObservation:
    return TelemetryObservation(
        value=value, quality=TelemetryQuality.EXACT, unavailable_reason=None
    )


def test_build_execution_telemetry_reuses_wall_time_and_request_bytes() -> None:
    """controller_wall_time_sec/request_bytes are reused directly from the
    result, never recomputed or duplicated under a new quality wrapper."""
    result = _result(
        status=ExecutionStatus.COMPLETED,
        candidate_wall_time_sec=0.2,
        observed_response_bytes=10,
        request_bytes=555,
    )
    telemetry = build_execution_telemetry(
        result, peak_memory=_exact_observation(1024), peak_process_count=_exact_observation(3)
    )
    assert telemetry.controller_wall_time_sec == 0.5
    assert telemetry.request_bytes == 555
    assert telemetry.candidate_wall_time.value == 0.2
    assert telemetry.observed_response_bytes.value == 10
    assert telemetry.peak_memory.value == 1024
    assert telemetry.peak_process_count.value == 3


def test_build_execution_telemetry_raises_when_request_bytes_is_none() -> None:
    """A result with no request_bytes does not represent a genuine
    invocation attempt -- raises rather than silently fabricating a value."""
    result = _result(
        status=ExecutionStatus.COMPLETED,
        candidate_wall_time_sec=0.2,
        observed_response_bytes=10,
        request_bytes=None,
    )
    with pytest.raises(ValueError):
        build_execution_telemetry(
            result, peak_memory=_exact_observation(1), peak_process_count=_exact_observation(1)
        )


def test_build_execution_telemetry_never_carries_raw_request_or_response_content() -> None:
    """Structural check: ExecutionTelemetry has no field capable of
    carrying candidate source, stdout/stderr text, or any other raw
    content -- only durations, counts, and typed classifications."""
    result = _result(
        status=ExecutionStatus.COMPLETED, candidate_wall_time_sec=0.1, observed_response_bytes=1
    )
    telemetry = build_execution_telemetry(
        result, peak_memory=_exact_observation(1), peak_process_count=_exact_observation(1)
    )
    for field in dataclasses.fields(telemetry):
        assert field.name not in ("stdout", "stderr", "candidate_code", "return_value")
