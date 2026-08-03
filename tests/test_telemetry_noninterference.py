"""MEGB-03H.2C.1 conformance audit: telemetry noninterference.

Proves, using offline fakes only:

* collector start/sample/finalize failure never changes an otherwise
  valid CandidateExecutionResult's status or return_value;
* a telemetry failure is represented only in its own telemetry
  observation, never leaking into or corrupting sibling telemetry fields;
* collector failure cannot cause a cacheable candidate result to be
  misclassified -- CalibrationTelemetryFields carries no field capable of
  influencing MeasurementStatus/cacheability at all.
"""

# This module's failing-collector-loop construction intentionally mirrors
# a pattern already present in test_telemetry_collectors.py -- both
# exercise the same three lifecycle-failure fakes. Expected and accepted,
# not a defect.
# pylint: disable=duplicate-code

import dataclasses
import inspect

from src.execution.protocol import ExecutionStatus
from src.execution.telemetry import (
    CollectorFailureStage,
    TelemetryObservation,
    TelemetryQuality,
    TelemetryUnavailableReason,
    build_execution_telemetry,
    collector_failure_observation,
)
from src.execution.telemetry_collectors import FakeTelemetryCollector, run_collector
from src.execution.telemetry_methods import (
    CollectorMethod,
    CollectorMethodIdentity,
    MetricCollectionDisposition,
    TerminalCoverageState,
)
from src.reference.execution_telemetry_adapter import (
    CalibrationTelemetryFields,
    adapt_execution_telemetry,
)
from tests._h2c1_telemetry_fixtures import make_candidate_execution_result


def test_collector_failure_does_not_change_the_candidate_result_status_or_value() -> None:
    """A valid candidate result's status/return_value are computed and
    frozen before any collector ever runs -- proven here by running a
    failing collector after the fact and confirming the result object is
    completely unaffected."""
    result = make_candidate_execution_result(status=ExecutionStatus.COMPLETED)
    assert result.status == ExecutionStatus.COMPLETED

    for collector in (
        FakeTelemetryCollector(start_raises=True),
        FakeTelemetryCollector(sample_raises=True),
        FakeTelemetryCollector(finalize_raises=True),
    ):
        run_collector(collector, sample_count=1)
        # The result is a frozen dataclass built independently of any
        # collector; nothing a collector does can reach it.
        assert result.status == ExecutionStatus.COMPLETED
        assert result.return_value is None


def test_candidate_execution_result_is_frozen_and_structurally_unreachable_by_collectors() -> None:
    """Structural proof: CandidateExecutionResult is an immutable
    (frozen) dataclass, and TelemetryCollector's own interface
    (start/sample/finalize/cleanup) never receives a reference to it --
    a collector has no mechanism by which it could even attempt to
    mutate a candidate result."""
    result = make_candidate_execution_result(status=ExecutionStatus.COMPLETED)
    assert dataclasses.is_dataclass(result)
    try:
        result.status = ExecutionStatus.TIMEOUT  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("CandidateExecutionResult is not actually frozen")

    for method_name in ("start", "sample", "finalize", "cleanup"):
        signature = inspect.signature(getattr(FakeTelemetryCollector, method_name))
        assert "result" not in signature.parameters
        assert "candidate_execution_result" not in signature.parameters


def test_one_collector_failure_does_not_corrupt_sibling_telemetry_fields() -> None:
    """peak_memory failing must not affect peak_process_count,
    candidate_wall_time, observed_response_bytes, request_bytes, or
    controller_wall_time_sec -- each field is independently derived."""
    result = make_candidate_execution_result(
        status=ExecutionStatus.COMPLETED,
        candidate_wall_time_sec=0.5,
        observed_response_bytes=77,
        request_bytes=321,
        wall_time_sec=1.5,
    )
    peak_memory = run_collector(FakeTelemetryCollector(finalize_raises=True))
    peak_process_count = TelemetryObservation(
        value=4, quality=TelemetryQuality.EXACT, unavailable_reason=None
    )

    telemetry = build_execution_telemetry(
        result, peak_memory=peak_memory, peak_process_count=peak_process_count
    )

    assert telemetry.peak_memory.collector_failure == CollectorFailureStage.FINALIZE
    assert telemetry.peak_memory.unavailable_reason == TelemetryUnavailableReason.SAMPLER_FAILURE
    # Every sibling field is unaffected by peak_memory's failure.
    assert telemetry.peak_process_count.value == 4
    assert telemetry.peak_process_count.collector_failure is None
    assert telemetry.candidate_wall_time.value == 0.5
    assert telemetry.observed_response_bytes.value == 77
    assert telemetry.request_bytes == 321
    assert telemetry.controller_wall_time_sec == 1.5


def test_collector_failure_cannot_cause_a_cacheable_result_to_be_misclassified() -> None:
    """CalibrationTelemetryFields (the adapter's entire output surface)
    has no field capable of describing measurement validity, correctness,
    or cacheability -- a collector failure is structurally incapable of
    influencing that determination, which is made entirely elsewhere from
    fields telemetry never touches."""
    result = make_candidate_execution_result(status=ExecutionStatus.COMPLETED)
    telemetry = build_execution_telemetry(
        result,
        peak_memory=collector_failure_observation(CollectorFailureStage.START),
        peak_process_count=collector_failure_observation(CollectorFailureStage.SAMPLE),
    )
    fields = adapt_execution_telemetry(telemetry)

    field_names = {f.name for f in dataclasses.fields(CalibrationTelemetryFields)}
    for forbidden in (
        "measurement_status",
        "q_ref_task",
        "status",
        "cacheable",
        "first_failure_category",
    ):
        assert forbidden not in field_names

    # The two collector failures land exactly where H.2A's own schema
    # expects them (SAMPLER_FAILURE), and nowhere else.
    assert fields.peak_memory_unavailable_reason is not None
    assert fields.peak_memory_unavailable_reason.value == "SAMPLER_FAILURE"
    assert fields.peak_process_unavailable_reason is not None
    assert fields.peak_process_unavailable_reason.value == "SAMPLER_FAILURE"


# ---------------------------------------------------------------------------
# cleanup_failed noninterference (MEGB-03H.2C.1 conformance-audit correction)
# ---------------------------------------------------------------------------


def test_cleanup_failure_does_not_change_the_candidate_result() -> None:
    """A collector whose cleanup() ALSO fails (on top of a successful
    observation) still cannot touch the candidate result -- same
    structural guarantee as any other collector behavior."""
    result = make_candidate_execution_result(status=ExecutionStatus.COMPLETED)
    peak_memory = run_collector(
        FakeTelemetryCollector(
            observation=TelemetryObservation(
                value=1, quality=TelemetryQuality.EXACT, unavailable_reason=None
            ),
            cleanup_raises=True,
        )
    )
    assert peak_memory.cleanup_failed is True
    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value is None


def test_cleanup_failure_on_one_collector_does_not_corrupt_sibling_telemetry_fields() -> None:
    """A cleanup() failure on peak_memory must not affect
    peak_process_count or any other sibling field."""
    result = make_candidate_execution_result(
        status=ExecutionStatus.COMPLETED,
        candidate_wall_time_sec=0.5,
        observed_response_bytes=77,
        request_bytes=321,
        wall_time_sec=1.5,
    )
    peak_memory = run_collector(
        FakeTelemetryCollector(
            observation=TelemetryObservation(
                value=2048, quality=TelemetryQuality.EXACT, unavailable_reason=None
            ),
            cleanup_raises=True,
        )
    )
    peak_process_count = TelemetryObservation(
        value=4, quality=TelemetryQuality.EXACT, unavailable_reason=None
    )
    telemetry = build_execution_telemetry(
        result, peak_memory=peak_memory, peak_process_count=peak_process_count
    )

    assert telemetry.peak_memory.value == 2048  # observation itself preserved
    assert telemetry.peak_memory.cleanup_failed is True
    assert telemetry.peak_process_count.value == 4
    assert telemetry.peak_process_count.cleanup_failed is False
    assert telemetry.candidate_wall_time.value == 0.5
    assert telemetry.observed_response_bytes.value == 77


def _confirmed_exact_method_identity() -> CollectorMethodIdentity:
    return CollectorMethodIdentity(
        method=CollectorMethod.CGROUP_V2_MEMORY_PEAK,
        method_version="cgroup_peak_file_collector/v1",
        interface="cgroupfs:/fake/memory.peak",
        sampling_interval_sec=None,
        selection_disposition=MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
    )


def test_cleanup_failure_is_conservatively_mapped_to_sampler_failure_for_calibration() -> None:
    """Per invariant 4: even though the raw observation was a valid EXACT
    reading, the adapter conservatively reports it as unavailable/
    SAMPLER_FAILURE for calibration-release purposes once cleanup_failed
    is set -- and this still cannot touch candidate correctness/
    cacheability (no such field exists on CalibrationTelemetryFields)."""
    result = make_candidate_execution_result(status=ExecutionStatus.COMPLETED)
    peak_memory = run_collector(
        FakeTelemetryCollector(
            observation=TelemetryObservation(
                value=999,
                quality=TelemetryQuality.EXACT,
                unavailable_reason=None,
                method_identity=_confirmed_exact_method_identity(),
                terminal_coverage=TerminalCoverageState.TERMINAL_READ_CONFIRMED,
            ),
            cleanup_raises=True,
        )
    )
    assert peak_memory.value == 999  # the raw observation is untouched
    assert peak_memory.cleanup_failed is True

    telemetry = build_execution_telemetry(
        result,
        peak_memory=peak_memory,
        peak_process_count=TelemetryObservation(
            value=1,
            quality=TelemetryQuality.EXACT,
            unavailable_reason=None,
            method_identity=_confirmed_exact_method_identity(),
            terminal_coverage=TerminalCoverageState.TERMINAL_READ_CONFIRMED,
        ),
    )
    fields = adapt_execution_telemetry(telemetry)

    assert fields.peak_memory_bytes is None
    assert fields.peak_memory_quality is None
    assert fields.peak_memory_unavailable_reason is not None
    assert fields.peak_memory_unavailable_reason.value == "SAMPLER_FAILURE"
    # Candidate correctness/cacheability remain entirely outside this
    # adapter's output surface.
    field_names = {f.name for f in dataclasses.fields(CalibrationTelemetryFields)}
    assert "measurement_status" not in field_names
    assert "cacheable" not in field_names
