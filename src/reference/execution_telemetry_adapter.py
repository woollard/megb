"""MEGB-03H.2C.1: reference-side adapter converting execution-layer
telemetry (``src.execution.telemetry``) into H.2A's accepted
``CalibrationInvocationRecord`` telemetry fields.

Reference-side code may adapt execution telemetry into calibration
records; the reverse (``src/execution/`` importing ``src/reference/`` or
any calibration schema) is architecturally forbidden -- this module is
where that one-way adaptation lives, importing both
``src.execution.telemetry`` and ``src.reference.calibration_schema``.

Produces only the subset of :class:`~src.reference.calibration_schema.CalibrationInvocationRecord`'s
own fields derivable from telemetry alone (the two plain values plus the
four orthogonal quality/reason triples) -- every other field on that
record (task/candidate identity, ``measurement_status``,
``first_failure_category``, ...) comes from the evaluator/orchestrator
layer, not from telemetry, and is supplied by the caller separately.
"""

from dataclasses import dataclass

from src.execution.telemetry import ExecutionTelemetry, TelemetryObservation
from src.execution.telemetry import TelemetryQuality as ExecQuality
from src.execution.telemetry import TelemetryUnavailableReason as ExecReason
from src.reference.calibration_schema import MeasurementQuality
from src.reference.calibration_schema import TelemetryUnavailableReason as CalibReason

# Exhaustive, order-independent 1:1 correspondence between the execution
# layer's own taxonomy and H.2A's accepted one -- both enums share the
# same member names by design (see telemetry.py's own module docstring),
# so these maps are a straight rename, verified exhaustive by
# tests/test_execution_telemetry_adapter.py (one entry per real member of
# each source enum, checked by iterating the enum itself rather than by a
# fixed count -- any future member added to either enum without a
# corresponding map entry fails immediately, on the map's own construction
# below rather than silently at first use).
_QUALITY_MAP: dict[ExecQuality, MeasurementQuality] = {
    ExecQuality.EXACT: MeasurementQuality.EXACT,
    ExecQuality.SAMPLED_WITH_KNOWN_ERROR: MeasurementQuality.SAMPLED_WITH_KNOWN_ERROR,
    ExecQuality.BOUNDARY_ONLY: MeasurementQuality.BOUNDARY_ONLY,
    ExecQuality.UNAVAILABLE_WITHOUT_CONTAMINATION: (
        MeasurementQuality.UNAVAILABLE_WITHOUT_CONTAMINATION
    ),
}

_REASON_MAP: dict[ExecReason, CalibReason] = {
    ExecReason.NEVER_STARTED: CalibReason.NEVER_STARTED,
    ExecReason.KILLED_BEFORE_COMPLETION: CalibReason.KILLED_BEFORE_COMPLETION,
    ExecReason.NO_RESPONSE_PRODUCED: CalibReason.NO_RESPONSE_PRODUCED,
    ExecReason.HOST_TELEMETRY_UNAVAILABLE: CalibReason.HOST_TELEMETRY_UNAVAILABLE,
    ExecReason.UNAVAILABLE_WITHOUT_CONTAMINATION: CalibReason.UNAVAILABLE_WITHOUT_CONTAMINATION,
    ExecReason.SAMPLER_FAILURE: CalibReason.SAMPLER_FAILURE,
    ExecReason.NOT_APPLICABLE: CalibReason.NOT_APPLICABLE,
    ExecReason.NOT_YET_INSTRUMENTED: CalibReason.NOT_YET_INSTRUMENTED,
}

if _QUALITY_MAP.keys() != set(ExecQuality):
    raise AssertionError("_QUALITY_MAP is not exhaustive over ExecQuality")
if _REASON_MAP.keys() != set(ExecReason):
    raise AssertionError("_REASON_MAP is not exhaustive over ExecReason")


def adapt_quality(quality: ExecQuality) -> MeasurementQuality:
    """Map one execution-layer quality value onto H.2A's own."""
    return _QUALITY_MAP[quality]


def adapt_unavailable_reason(reason: ExecReason) -> CalibReason:
    """Map one execution-layer unavailable reason onto H.2A's own."""
    return _REASON_MAP[reason]


def _adapt_observation(
    observation: TelemetryObservation,
) -> tuple[float | int | None, MeasurementQuality | None, CalibReason | None]:
    """Return ``(value, quality, unavailable_reason)`` in
    ``CalibrationInvocationRecord``'s own field shape for one observation.

    A ``collector_failure`` is intentionally *not* separately represented
    here -- H.2A's accepted schema has no field for which lifecycle stage
    failed; ``TelemetryUnavailableReason.SAMPLER_FAILURE`` (the reason
    every collector failure already carries, enforced by
    ``TelemetryObservation.__post_init__``) is exactly the schema's own
    slot for "a sampler that ran but failed" and is not lost -- only the
    additional stage-level detail is, which is outside this schema's
    scope.

    ``cleanup_failed`` (MEGB-03H.2C.1 conformance-audit correction) is
    handled conservatively: whenever the collector's own ``cleanup()``
    also failed, this maps to unavailable/``SAMPLER_FAILURE`` for
    calibration-release purposes *regardless* of what ``value``/
    ``quality`` the observation otherwise carried -- an observation whose
    collector could not confirm its resources were released is never
    treated as trustworthy here, even if the reading itself looked valid.
    This never touches candidate correctness or cacheability:
    :class:`CalibrationTelemetryFields` has no field capable of
    representing either.
    """
    if observation.cleanup_failed:
        return None, None, adapt_unavailable_reason(ExecReason.SAMPLER_FAILURE)
    if observation.value is not None:
        assert observation.quality is not None
        return observation.value, adapt_quality(observation.quality), None
    assert observation.unavailable_reason is not None
    return None, None, adapt_unavailable_reason(observation.unavailable_reason)


def _adapt_int_observation(
    observation: TelemetryObservation,
) -> tuple[int | None, MeasurementQuality | None, CalibReason | None]:
    """Same as :func:`_adapt_observation`, narrowed to ``int | None`` for
    the three byte-count/process-count fields (never ``float``)."""
    value, quality, reason = _adapt_observation(observation)
    if value is not None:
        assert isinstance(value, int)
    return value, quality, reason


@dataclass(frozen=True)
class CalibrationTelemetryFields:
    """The subset of :class:`~src.reference.calibration_schema.CalibrationInvocationRecord`'s
    own fields this adapter populates from an :class:`ExecutionTelemetry`
    -- splat directly (``**dataclasses.asdict(...)``, or field-by-field)
    into that record's constructor alongside every other field the caller
    already has from elsewhere."""

    controller_wall_time_sec: float
    request_bytes: int
    candidate_wall_time_sec: float | None
    candidate_wall_time_quality: MeasurementQuality | None
    candidate_wall_time_unavailable_reason: CalibReason | None
    observed_response_bytes: int | None
    observed_response_quality: MeasurementQuality | None
    observed_response_unavailable_reason: CalibReason | None
    peak_memory_bytes: int | None
    peak_memory_quality: MeasurementQuality | None
    peak_memory_unavailable_reason: CalibReason | None
    peak_process_count: int | None
    peak_process_quality: MeasurementQuality | None
    peak_process_unavailable_reason: CalibReason | None


def adapt_execution_telemetry(telemetry: ExecutionTelemetry) -> CalibrationTelemetryFields:
    """Convert one invocation's :class:`ExecutionTelemetry` into the
    telemetry-shaped subset of :class:`CalibrationInvocationRecord`'s own
    fields. Exhaustive and total over every real ``ExecutionTelemetry``:
    every :class:`TelemetryQuality`/:class:`TelemetryUnavailableReason`
    member maps to exactly one H.2A counterpart (see the module-level
    exhaustiveness assertions above), so this function never raises for a
    well-formed ``ExecutionTelemetry``.
    """
    candidate_wall_time_value, candidate_wall_time_quality, candidate_wall_time_reason = (
        _adapt_observation(telemetry.candidate_wall_time)
    )
    observed_response_value, observed_response_quality, observed_response_reason = (
        _adapt_int_observation(telemetry.observed_response_bytes)
    )
    peak_memory_value, peak_memory_quality, peak_memory_reason = _adapt_int_observation(
        telemetry.peak_memory
    )
    peak_process_value, peak_process_quality, peak_process_reason = _adapt_int_observation(
        telemetry.peak_process_count
    )
    return CalibrationTelemetryFields(
        controller_wall_time_sec=telemetry.controller_wall_time_sec,
        request_bytes=telemetry.request_bytes,
        candidate_wall_time_sec=candidate_wall_time_value,
        candidate_wall_time_quality=candidate_wall_time_quality,
        candidate_wall_time_unavailable_reason=candidate_wall_time_reason,
        observed_response_bytes=observed_response_value,
        observed_response_quality=observed_response_quality,
        observed_response_unavailable_reason=observed_response_reason,
        peak_memory_bytes=peak_memory_value,
        peak_memory_quality=peak_memory_quality,
        peak_memory_unavailable_reason=peak_memory_reason,
        peak_process_count=peak_process_value,
        peak_process_quality=peak_process_quality,
        peak_process_unavailable_reason=peak_process_reason,
    )


__all__ = [
    "CalibrationTelemetryFields",
    "adapt_execution_telemetry",
    "adapt_quality",
    "adapt_unavailable_reason",
]
