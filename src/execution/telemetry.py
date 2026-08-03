"""MEGB-03H.2C.1: the execution-layer telemetry model.

Defines this layer's own, independent measurement-quality and
unavailable-reason taxonomies (mirroring H.2A's accepted
``src.reference.calibration_schema`` vocabulary in shape and member names,
since it is the same real-world concept recurring at a lower layer) rather
than importing them from ``src.reference`` -- ``src/execution/`` must never
import ``src/reference/`` or any calibration schema (see the module
docstring's own architectural constraint, echoed in
``src/reference/execution_telemetry_adapter.py``, which performs the
reverse-direction adaptation these two independent enums exist to support).
Duplicating this small, stable taxonomy is the accepted, established
pattern in this codebase for two types that share vocabulary across a
one-way dependency boundary (see ``h5_staging.py``'s own equivalent note
about ``H5StagingIdentity`` repeating ``CalibrationRunContext`` field
names) -- the alternative would require moving H.2A's already-accepted
``MeasurementQuality``/``TelemetryUnavailableReason`` out of
``calibration_schema.py``, which is out of scope for this checkpoint.

Never carries raw request/response content, candidate source, or
expected-output data -- only counts, durations, and typed classifications.
"""

# TelemetryQuality/TelemetryUnavailableReason intentionally repeat
# calibration_schema.py's own MeasurementQuality/TelemetryUnavailableReason
# member names verbatim -- see the module docstring above. Expected and
# accepted, not a defect (mirrors h5_staging.py's own documented
# precedent for the same situation).
# pylint: disable=duplicate-code

from dataclasses import dataclass
from enum import Enum

from src.execution.protocol import CandidateExecutionResult, ExecutionStatus
from src.execution.response_overflow import (
    ResponseOverflowClassification,
    classify_response_overflow,
)


class TelemetryQuality(str, Enum):
    """The execution layer's own copy of the accepted, exactly-four-value
    telemetry measurement-quality taxonomy. No fifth value exists."""

    EXACT = "EXACT"
    SAMPLED_WITH_KNOWN_ERROR = "SAMPLED_WITH_KNOWN_ERROR"
    BOUNDARY_ONLY = "BOUNDARY_ONLY"
    UNAVAILABLE_WITHOUT_CONTAMINATION = "UNAVAILABLE_WITHOUT_CONTAMINATION"


class TelemetryUnavailableReason(str, Enum):
    """The execution layer's own copy of H.2A's eight-value unavailable-
    reason taxonomy -- see ``TelemetryQuality``'s own docstring for why
    this is independently defined here rather than imported."""

    NEVER_STARTED = "NEVER_STARTED"
    KILLED_BEFORE_COMPLETION = "KILLED_BEFORE_COMPLETION"
    NO_RESPONSE_PRODUCED = "NO_RESPONSE_PRODUCED"
    HOST_TELEMETRY_UNAVAILABLE = "HOST_TELEMETRY_UNAVAILABLE"
    UNAVAILABLE_WITHOUT_CONTAMINATION = "UNAVAILABLE_WITHOUT_CONTAMINATION"
    SAMPLER_FAILURE = "SAMPLER_FAILURE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_YET_INSTRUMENTED = "NOT_YET_INSTRUMENTED"


class CollectorFailureStage(str, Enum):
    """Which lifecycle stage of a :class:`~src.execution.telemetry_collectors.TelemetryCollector`
    raised, when one did. Distinct from ``TelemetryUnavailableReason`` --
    a collector failure additionally pins *where* in the lifecycle the
    failure happened, for diagnostics; the observation's own
    ``unavailable_reason`` is always ``SAMPLER_FAILURE`` whenever this is
    set (see :class:`TelemetryObservation`)."""

    START = "START"
    SAMPLE = "SAMPLE"
    FINALIZE = "FINALIZE"


class InvalidTelemetryObservationError(ValueError):
    """Raised when a :class:`TelemetryObservation`'s fields are internally
    inconsistent."""


@dataclass(frozen=True)
class TelemetryObservation:
    """One raw, optional telemetry observation, orthogonal availability
    modeled exactly as H.2A's own contract: ``value`` present iff
    ``quality`` is a :class:`TelemetryQuality` and ``unavailable_reason``
    is ``None``; ``value`` absent iff ``quality`` is ``None`` and
    ``unavailable_reason`` is a :class:`TelemetryUnavailableReason`.

    ``collector_failure``, when set, always implies ``value is None`` and
    ``unavailable_reason is SAMPLER_FAILURE`` -- it is strictly additional
    diagnostic detail (which lifecycle stage failed), never an independent
    axis of unavailability.
    """

    value: float | int | None
    quality: TelemetryQuality | None
    unavailable_reason: TelemetryUnavailableReason | None
    collector_failure: CollectorFailureStage | None = None

    def __post_init__(self) -> None:
        if self.value is None:
            if self.quality is not None:
                raise InvalidTelemetryObservationError(
                    f"quality must be None when value is None, got {self.quality!r}"
                )
            if not isinstance(self.unavailable_reason, TelemetryUnavailableReason):
                raise InvalidTelemetryObservationError(
                    "unavailable_reason must be a TelemetryUnavailableReason when value is "
                    f"None, got {self.unavailable_reason!r}"
                )
        else:
            if self.unavailable_reason is not None:
                raise InvalidTelemetryObservationError(
                    f"unavailable_reason must be None when value is present, got "
                    f"{self.unavailable_reason!r}"
                )
            if not isinstance(self.quality, TelemetryQuality):
                raise InvalidTelemetryObservationError(
                    f"quality must be a TelemetryQuality when value is present, got "
                    f"{self.quality!r}"
                )
        if self.collector_failure is not None:
            if self.value is not None:
                raise InvalidTelemetryObservationError(
                    "collector_failure requires value to be None, got a present value"
                )
            if self.unavailable_reason != TelemetryUnavailableReason.SAMPLER_FAILURE:
                raise InvalidTelemetryObservationError(
                    "collector_failure requires unavailable_reason to be SAMPLER_FAILURE, got "
                    f"{self.unavailable_reason!r}"
                )


def collector_failure_observation(stage: CollectorFailureStage) -> TelemetryObservation:
    """Build the :class:`TelemetryObservation` for a collector that raised
    during ``stage`` of its lifecycle."""
    return TelemetryObservation(
        value=None,
        quality=None,
        unavailable_reason=TelemetryUnavailableReason.SAMPLER_FAILURE,
        collector_failure=stage,
    )


def _no_response_reason(status: ExecutionStatus) -> TelemetryUnavailableReason:
    """Reason for TIMEOUT/OUT_OF_MEMORY/INFRASTRUCTURE_ERROR -- the only
    three statuses under which the runner never produced a completed
    response (killed before writing one, or never started)."""
    if status in (ExecutionStatus.TIMEOUT, ExecutionStatus.OUT_OF_MEMORY):
        return TelemetryUnavailableReason.KILLED_BEFORE_COMPLETION
    return TelemetryUnavailableReason.NO_RESPONSE_PRODUCED


def candidate_wall_time_observation(result: CandidateExecutionResult) -> TelemetryObservation:
    """EXACT when the runner reported a real duration (every status except
    the three where the runner never got to run to completion or failure
    on its own); unavailable otherwise, matching
    ``CandidateExecutionResult.candidate_wall_time_sec``'s own contract."""
    if result.candidate_wall_time_sec is not None:
        return TelemetryObservation(
            value=result.candidate_wall_time_sec, quality=TelemetryQuality.EXACT,
            unavailable_reason=None,
        )
    return TelemetryObservation(
        value=None, quality=None, unavailable_reason=_no_response_reason(result.status)
    )


def observed_response_bytes_observation(result: CandidateExecutionResult) -> TelemetryObservation:
    """EXACT when the controller actually received a completed response
    (every status except the three where none ever existed); unavailable
    otherwise."""
    if result.observed_response_bytes is not None:
        return TelemetryObservation(
            value=result.observed_response_bytes,
            quality=TelemetryQuality.EXACT,
            unavailable_reason=None,
        )
    return TelemetryObservation(
        value=None, quality=None, unavailable_reason=_no_response_reason(result.status)
    )


@dataclass(frozen=True)
class ExecutionTelemetry:  # pylint: disable=too-many-instance-attributes
    """The full set of raw execution-layer telemetry observations for one
    invocation. Structurally cannot carry candidate source, expected
    outputs, or raw request/response content -- every field here is a
    duration, a byte count, or a typed classification.

    ``controller_wall_time_sec``/``request_bytes`` reuse
    ``CandidateExecutionResult``'s own existing (non-nullable) fields
    rather than duplicating their meaning under a new orthogonal-quality
    wrapper -- matching ``CalibrationInvocationRecord``'s own precedent of
    treating exactly these two fields as always-present, un-tagged values.
    """

    controller_wall_time_sec: float
    request_bytes: int
    candidate_wall_time: TelemetryObservation
    observed_response_bytes: TelemetryObservation
    response_overflow: ResponseOverflowClassification
    peak_memory: TelemetryObservation
    peak_process_count: TelemetryObservation


def build_execution_telemetry(
    result: CandidateExecutionResult,
    *,
    peak_memory: TelemetryObservation,
    peak_process_count: TelemetryObservation,
) -> ExecutionTelemetry:
    """Build the full :class:`ExecutionTelemetry` for one invocation's
    :class:`CandidateExecutionResult`, plus its two collector-derived
    observations (peak memory/process count are produced by the separate
    collector-lifecycle machinery in
    ``src.execution.telemetry_collectors``, run alongside the invocation,
    not derivable from the result alone).

    Raises :class:`ValueError` if ``result.request_bytes`` is ``None`` --
    every real invocation attempt has one (serialization always succeeds
    before any container is started), so a missing value here means
    ``result`` does not represent a genuine invocation.
    """
    if result.request_bytes is None:
        raise ValueError(
            "result.request_bytes is None -- a genuine invocation attempt always has one"
        )
    return ExecutionTelemetry(
        controller_wall_time_sec=result.wall_time_sec,
        request_bytes=result.request_bytes,
        candidate_wall_time=candidate_wall_time_observation(result),
        observed_response_bytes=observed_response_bytes_observation(result),
        response_overflow=classify_response_overflow(result),
        peak_memory=peak_memory,
        peak_process_count=peak_process_count,
    )
