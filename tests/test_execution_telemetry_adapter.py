"""MEGB-03H.2C.1: tests for the reference-side execution-telemetry adapter
(src.reference.execution_telemetry_adapter). Synthetic fixtures only, via
tests/_calibration_fixtures.py -- no real privileged corpus access, no
Docker.
"""

import dataclasses

import pytest

from src.execution.protocol import CandidateExecutionResult, ExecutionStatus
from src.execution.telemetry import (
    CollectorFailureStage,
    TelemetryObservation,
    TelemetryQuality,
    TelemetryUnavailableReason,
    build_execution_telemetry,
    collector_failure_observation,
)
from src.execution.telemetry_methods import (
    CollectorMethod,
    CollectorMethodIdentity,
    MetricCollectionDisposition,
    TerminalCoverageState,
)
from src.reference.calibration_schema import MeasurementQuality
from src.reference.calibration_schema import TelemetryUnavailableReason as CalibReason
from src.reference.calibration_summary import (
    CalibrationRecordNotReleaseReadyError,
    require_release_ready_stage,
)
from src.reference.execution_telemetry_adapter import (
    CalibrationTelemetryFields,
    adapt_execution_telemetry,
    adapt_quality,
    adapt_unavailable_reason,
)
from tests._calibration_fixtures import make_invocation
from tests._h2c1_telemetry_fixtures import make_candidate_execution_result

# ---------------------------------------------------------------------------
# Exhaustive quality/reason mapping
# ---------------------------------------------------------------------------


def test_every_telemetry_quality_maps_to_the_identically_named_measurement_quality() -> None:
    """Every TelemetryQuality member maps to its same-named MeasurementQuality."""
    for quality in TelemetryQuality:
        mapped = adapt_quality(quality)
        assert isinstance(mapped, MeasurementQuality)
        assert mapped.value == quality.value


def test_every_telemetry_unavailable_reason_maps_to_the_identically_named_calib_reason() -> None:
    """Every TelemetryUnavailableReason member maps to its same-named calibration reason."""
    for reason in TelemetryUnavailableReason:
        mapped = adapt_unavailable_reason(reason)
        assert isinstance(mapped, CalibReason)
        assert mapped.value == reason.value


def test_quality_mapping_is_exhaustive_over_every_real_enum_member() -> None:
    """Every member of both enums is covered -- not just a fixed count."""
    for quality in TelemetryQuality:
        adapt_quality(quality)  # must not raise KeyError
    assert len(list(TelemetryQuality)) == 4


def test_reason_mapping_is_exhaustive_over_every_real_enum_member() -> None:
    """Every member of both enums is covered -- not just a fixed count."""
    for reason in TelemetryUnavailableReason:
        adapt_unavailable_reason(reason)  # must not raise KeyError
    assert len(list(TelemetryUnavailableReason)) == 8


# ---------------------------------------------------------------------------
# adapt_execution_telemetry: full field mapping
# ---------------------------------------------------------------------------


def _result(
    *, candidate_wall_time_sec: float | None, observed_response_bytes: int | None
) -> CandidateExecutionResult:
    status = (
        ExecutionStatus.COMPLETED
        if candidate_wall_time_sec is not None
        else ExecutionStatus.TIMEOUT
    )
    return make_candidate_execution_result(
        status=status,
        candidate_wall_time_sec=candidate_wall_time_sec,
        observed_response_bytes=observed_response_bytes,
        wall_time_sec=0.75,
        request_bytes=321,
    )


def _exact_method_identity() -> CollectorMethodIdentity:
    return CollectorMethodIdentity(
        method=CollectorMethod.CGROUP_V2_MEMORY_PEAK,
        method_version="cgroup_peak_file_collector/v1",
        interface="cgroupfs:/fake/memory.peak",
        sampling_interval_sec=None,
        selection_disposition=MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
    )


def _exact(value: float) -> TelemetryObservation:
    return TelemetryObservation(
        value=value,
        quality=TelemetryQuality.EXACT,
        unavailable_reason=None,
        method_identity=_exact_method_identity(),
        terminal_coverage=TerminalCoverageState.TERMINAL_READ_CONFIRMED,
    )


def test_adapt_execution_telemetry_maps_exact_observations() -> None:
    """Every EXACT observation maps straight through to its calibration counterpart."""
    result = _result(candidate_wall_time_sec=0.12, observed_response_bytes=64)
    telemetry = build_execution_telemetry(
        result, peak_memory=_exact(1024), peak_process_count=_exact(2)
    )
    fields = adapt_execution_telemetry(telemetry)

    assert fields.controller_wall_time_sec == 0.75
    assert fields.request_bytes == 321
    assert fields.candidate_wall_time_sec == 0.12
    assert fields.candidate_wall_time_quality == MeasurementQuality.EXACT
    assert fields.candidate_wall_time_unavailable_reason is None
    assert fields.observed_response_bytes == 64
    assert fields.observed_response_quality == MeasurementQuality.EXACT
    assert fields.peak_memory_bytes == 1024
    assert fields.peak_memory_quality == MeasurementQuality.EXACT
    assert fields.peak_process_count == 2
    assert fields.peak_process_quality == MeasurementQuality.EXACT


def test_adapt_execution_telemetry_maps_unavailable_observations() -> None:
    """Every unavailable observation maps to the matching calibration reason."""
    result = _result(candidate_wall_time_sec=None, observed_response_bytes=None)
    peak_memory = TelemetryObservation(
        value=None, quality=None, unavailable_reason=TelemetryUnavailableReason.NOT_APPLICABLE
    )
    peak_process = TelemetryObservation(
        value=None,
        quality=None,
        unavailable_reason=TelemetryUnavailableReason.HOST_TELEMETRY_UNAVAILABLE,
    )
    telemetry = build_execution_telemetry(
        result, peak_memory=peak_memory, peak_process_count=peak_process
    )
    fields = adapt_execution_telemetry(telemetry)

    assert fields.candidate_wall_time_sec is None
    assert fields.candidate_wall_time_quality is None
    assert fields.candidate_wall_time_unavailable_reason == CalibReason.KILLED_BEFORE_COMPLETION
    assert fields.peak_memory_bytes is None
    assert fields.peak_memory_unavailable_reason == CalibReason.NOT_APPLICABLE
    assert fields.peak_process_count is None
    assert fields.peak_process_unavailable_reason == CalibReason.HOST_TELEMETRY_UNAVAILABLE


def test_adapt_execution_telemetry_maps_collector_failure_to_sampler_failure() -> None:
    """A collector failure loses its stage-level detail (no schema slot
    for it) but is never silently dropped -- it always lands on
    SAMPLER_FAILURE, H.2A's own slot for exactly this situation."""
    result = _result(candidate_wall_time_sec=0.1, observed_response_bytes=1)
    telemetry = build_execution_telemetry(
        result,
        peak_memory=collector_failure_observation(CollectorFailureStage.FINALIZE),
        peak_process_count=_exact(1),
    )
    fields = adapt_execution_telemetry(telemetry)
    assert fields.peak_memory_bytes is None
    assert fields.peak_memory_unavailable_reason == CalibReason.SAMPLER_FAILURE


# ---------------------------------------------------------------------------
# Real CalibrationInvocationRecord integration
# ---------------------------------------------------------------------------


def _splat_fields(fields: CalibrationTelemetryFields) -> dict[str, object]:
    """Shallow field-by-field conversion -- deliberately not
    dataclasses.asdict(), which would recursively flatten the nested
    CollectorMethodProvenance fields (MEGB-03H.2C.2A provenance/schema
    correction) into plain dicts, breaking CalibrationInvocationRecord's
    own isinstance(..., CollectorMethodProvenance) validation."""
    return {field.name: getattr(fields, field.name) for field in dataclasses.fields(fields)}


def test_adapted_fields_build_a_real_valid_calibration_invocation_record() -> None:
    """The adapter's output is directly accepted by H.2A's own,
    unmodified CalibrationInvocationRecord constructor."""
    result = _result(candidate_wall_time_sec=0.05, observed_response_bytes=77)
    telemetry = build_execution_telemetry(
        result, peak_memory=_exact(2048), peak_process_count=_exact(4)
    )
    fields = adapt_execution_telemetry(telemetry)
    record = make_invocation(**_splat_fields(fields))
    assert record.peak_memory_bytes == 2048
    assert record.peak_memory_quality == MeasurementQuality.EXACT
    assert record.observed_response_bytes == 77


def test_not_yet_instrumented_reason_fails_release_readiness() -> None:
    """NOT_YET_INSTRUMENTED is allowed only in synthetic H.2 development
    fixtures and must fail the existing release-readiness gate -- proven
    here by actually calling it, not merely asserting on the enum."""
    result = _result(candidate_wall_time_sec=0.05, observed_response_bytes=77)
    placeholder = TelemetryObservation(
        value=None,
        quality=None,
        unavailable_reason=TelemetryUnavailableReason.NOT_YET_INSTRUMENTED,
    )
    telemetry = build_execution_telemetry(
        result, peak_memory=placeholder, peak_process_count=placeholder
    )
    fields = adapt_execution_telemetry(telemetry)
    assert fields.peak_memory_unavailable_reason == CalibReason.NOT_YET_INSTRUMENTED

    record = make_invocation(**_splat_fields(fields))
    with pytest.raises(CalibrationRecordNotReleaseReadyError):
        require_release_ready_stage([record])


def test_real_telemetry_never_fails_release_readiness() -> None:
    """A genuinely real (non-placeholder) telemetry mapping passes the
    release-readiness gate cleanly."""
    result = _result(candidate_wall_time_sec=0.05, observed_response_bytes=77)
    telemetry = build_execution_telemetry(
        result, peak_memory=_exact(1), peak_process_count=_exact(1)
    )
    fields = adapt_execution_telemetry(telemetry)
    record = make_invocation(**_splat_fields(fields))
    require_release_ready_stage([record])  # must not raise


# ---------------------------------------------------------------------------
# No raw content leakage
# ---------------------------------------------------------------------------


def test_calibration_telemetry_fields_never_carries_raw_content() -> None:
    """Structural check: no field name on CalibrationTelemetryFields is
    capable of carrying candidate source, stdout/stderr, or expected
    output -- only counts, durations, and typed classifications."""
    field_names = {f.name for f in dataclasses.fields(CalibrationTelemetryFields)}
    for forbidden in ("stdout", "stderr", "candidate_code", "return_value", "expected_output"):
        assert forbidden not in field_names
