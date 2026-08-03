"""MEGB-03H.2A: typed, immutable, versioned calibration record schemas.

Implements the approved MEGB-03H.1 design's frozen decisions 7 (calibration-
record schemas), 9 (telemetry-quality taxonomy), and the H.1 Correction's
per-task/circuit-breaker structure's own record-level grounding, per
``docs/reference/megb-03h1-calibration-design.md`` §§9/11 and the ticket's
"Approved MEGB-03H Planning Amendment" §§3/5.

Two distinct record granularities, matching the design doc exactly:

* :class:`CalibrationInvocationRecord` -- one case-level backend
  invocation/attempt.
* :class:`CalibrationTaskEvaluationRecord` -- one complete
  task/candidate/profile/replicate evaluation, referencing the
  :class:`CalibrationInvocationRecord`\\ s that contributed to it.

Both embed a shared, self-checksummed :class:`CalibrationRunContext`
directly (mirroring the established
:class:`~src.reference.result_schema.ReferenceTaskResult`/
:class:`~src.reference.result_schema.ReferenceRunContext` embedding
convention in this codebase, rather than storing only an opaque checksum)
so that either record type is independently self-describing: reading one
record alone is enough to know exactly which stage/run/profile/evaluator/
protocol/dataset/partition/oracle/comparison identity produced it, without
a side lookup table. ``CalibrationRunContext.context_checksum`` still gives
the compact "context-identity checksum" concept the design doc's §9
describes for :class:`CalibrationTaskEvaluationRecord`.

Exactly four telemetry measurement-quality values exist
(:class:`MeasurementQuality`) -- ``EXACT``, ``SAMPLED_WITH_KNOWN_ERROR``,
``BOUNDARY_ONLY``, ``UNAVAILABLE_WITHOUT_CONTAMINATION`` -- per the
already-installed Amendment §5. There is deliberately no fifth value (e.g.
no ``EXACT_WHEN_AVAILABLE``): availability is instead modeled orthogonally,
via a separate typed :class:`TelemetryUnavailableReason` populated only
when the corresponding nullable telemetry field is ``None``. A single
shared reason enum (rather than one bespoke enum per nullable field, as the
design doc's own prose loosely suggested with
"``TimingUnavailableReason``/``ResponseUnavailableReason``") is used here:
every nullable telemetry field in this schema shares the same three
possible causes for absence, so one enum avoids duplicating an identical
member set under different names for no behavioral difference.

Supersession (design doc §9's "Supersession rule") applies at *both*
record levels: an interrupted, incomplete task-replicate's records --
every contributing :class:`CalibrationInvocationRecord` and its
:class:`CalibrationTaskEvaluationRecord` -- are marked ``superseded=True``,
never deleted, and excluded from
:class:`~src.reference.calibration_summary.CalibrationSummaryReport`
aggregation. The full re-execution that later completes it is a wholly
new, distinct set of records; nothing is ever merged with a superseded
record.

This module implements schema, validation, checksums, and cross-record
reconciliation only. The safe summary-report projection lives in the
sibling ``src.reference.calibration_summary`` module (split out purely to
keep each module's line count manageable); trace persistence is in
``src.reference.calibration_trace``. Neither telemetry collection (H.2C),
fresh-execution/cache/staging policy (H.2B), nor any canonical or
candidate execution is implemented anywhere in this module.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from src.evaluators.schema import FailureCategory
from src.execution.protocol import ExecutionStatus
from src.reference.reference_orchestrator import WorkItemDisposition
from src.reference.result_schema import MeasurementStatus

CALIBRATION_SCHEMA_VERSION = "megb-03h-calibration-record-v1"

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class InvalidCalibrationRecordError(ValueError):
    """Raised when a calibration record's fields are internally
    inconsistent, or a stamped checksum does not match its own recomputed
    contents (tampered or corrupted record)."""


class UnsupportedCalibrationSchemaVersionError(InvalidCalibrationRecordError):
    """Raised when deserializing a payload stamped with a different
    ``CALIBRATION_SCHEMA_VERSION`` (or, for
    :class:`~src.reference.calibration_summary.CalibrationSummaryReport`,
    ``CALIBRATION_SUMMARY_REPORT_SCHEMA_VERSION``) than the version
    currently implemented."""


class CalibrationReconciliationError(InvalidCalibrationRecordError):
    """Raised when a :class:`CalibrationTaskEvaluationRecord` does not
    reconcile against its own claimed contributing
    :class:`CalibrationInvocationRecord`\\ s (missing contributor, context/
    task/candidate/replicate mismatch, or a tampered contributor-set
    checksum)."""


class CalibrationStage(str, Enum):
    """The four calibration stages this schema's records may belong to."""

    H3 = "H.3"
    H4 = "H.4"
    H5 = "H.5"
    H6 = "H.6"


class MeasurementQuality(str, Enum):
    """The accepted, exactly-four-value telemetry measurement-quality
    taxonomy. No fifth value exists anywhere in this schema."""

    EXACT = "EXACT"
    SAMPLED_WITH_KNOWN_ERROR = "SAMPLED_WITH_KNOWN_ERROR"
    BOUNDARY_ONLY = "BOUNDARY_ONLY"
    UNAVAILABLE_WITHOUT_CONTAMINATION = "UNAVAILABLE_WITHOUT_CONTAMINATION"


class TelemetryUnavailableReason(str, Enum):
    """Why a nullable telemetry field is ``None``, populated only in that
    case (see the module docstring for why one shared enum is used).

    Audited against the H.2C measurement design
    (``docs/reference/megb-03h1-calibration-design.md`` §§11-12): covers
    execution never starting, being killed before measurement completed,
    producing no completed response, the host telemetry interface itself
    being unavailable or unsupported on the current host/kernel, a metric
    being deliberately uncollected because collecting it would contaminate
    the very execution being measured, a sampler that ran but failed, and a
    metric that simply does not apply to a given invocation.
    ``NOT_YET_INSTRUMENTED`` is a placeholder for records produced before
    H.2C's own telemetry collection exists (i.e. by H.2A/H.2B) -- see
    :func:`require_release_ready_stage`, which rejects it in any trace
    claimed release-ready for real H.3-H.6 execution."""

    NEVER_STARTED = "NEVER_STARTED"
    KILLED_BEFORE_COMPLETION = "KILLED_BEFORE_COMPLETION"
    NO_RESPONSE_PRODUCED = "NO_RESPONSE_PRODUCED"
    HOST_TELEMETRY_UNAVAILABLE = "HOST_TELEMETRY_UNAVAILABLE"
    UNAVAILABLE_WITHOUT_CONTAMINATION = "UNAVAILABLE_WITHOUT_CONTAMINATION"
    SAMPLER_FAILURE = "SAMPLER_FAILURE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_YET_INSTRUMENTED = "NOT_YET_INSTRUMENTED"


def _require_nonempty_str(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or value == "":
        raise InvalidCalibrationRecordError(
            f"{field_name!r} must be a nonempty string, got {value!r}"
        )


def _require_sha256_hex(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or not _SHA256_HEX_PATTERN.match(value):
        raise InvalidCalibrationRecordError(
            f"{field_name!r} must be a 64-character lowercase hex sha256 digest, got {value!r}"
        )


def _require_non_negative_int(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvalidCalibrationRecordError(
            f"{field_name!r} must be a non-negative int, got {value!r}"
        )


def _require_non_negative_float(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise InvalidCalibrationRecordError(
            f"{field_name!r} must be a non-negative number, got {value!r}"
        )


def _require_bool(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, bool):
        raise InvalidCalibrationRecordError(f"{field_name!r} must be a bool, got {value!r}")


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True)


def _sha256_of(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def checksum_of(payload: Mapping[str, Any]) -> str:
    """Public canonical-JSON sha256 checksum helper, shared with
    ``src.reference.calibration_trace`` so its trace-envelope checksums use
    the exact same canonicalization as every record checksum in this
    module."""
    return _sha256_of(payload)


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


# ---------------------------------------------------------------------------
# CalibrationRunContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationRunContext:
    """Immutable identity shared across every calibration record produced
    within one stage/run: the exact profile, evaluator, protocol, dataset,
    partition, oracle, comparison, and task-manifest identities in force,
    plus the stage and calibration-run identifiers themselves.

    ``task_manifest_checksum`` (schema-provenance-audit correction) pins
    exactly which frozen task manifest's content this run was evaluated
    against -- mirroring
    :class:`~src.reference.result_schema.ReferenceRunContext`'s own
    ``task_manifest_checksum`` field -- so two contexts that share every
    other label but differ in *which manifest instance* they were bound to
    are never treated as the same context (``context_checksum`` differs).

    ``context_checksum`` is always recomputed from this object's own
    canonical contents at construction time -- never accepted as an
    unverified caller-provided value (same auto-compute-or-reject pattern
    as :class:`~src.reference.result_schema.ReferenceValidationCandidateSetManifest`).
    """

    calibration_schema_version: str
    stage: CalibrationStage
    calibration_run_id: str
    execution_profile_id: str
    evaluator_version: str
    execution_protocol_version: str
    dataset_version: str
    dataset_checksum: str
    partition_version: str
    oracle_version: str
    comparison_profile_version: str
    task_manifest_checksum: str
    context_checksum: str = ""

    def __post_init__(self) -> None:
        if self.calibration_schema_version != CALIBRATION_SCHEMA_VERSION:
            raise UnsupportedCalibrationSchemaVersionError(
                f"calibration_schema_version {self.calibration_schema_version!r} does not "
                f"match the version this module implements ({CALIBRATION_SCHEMA_VERSION!r})"
            )
        if not isinstance(self.stage, CalibrationStage):
            raise InvalidCalibrationRecordError(
                f"stage must be a CalibrationStage, got {self.stage!r}"
            )
        for field_name in (
            "calibration_run_id",
            "execution_profile_id",
            "evaluator_version",
            "execution_protocol_version",
            "dataset_version",
            "dataset_checksum",
            "partition_version",
            "oracle_version",
            "comparison_profile_version",
        ):
            _require_nonempty_str(self, field_name)
        _require_sha256_hex(self, "task_manifest_checksum")

        payload = _calibration_run_context_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.context_checksum and self.context_checksum != expected_checksum:
            raise InvalidCalibrationRecordError(
                f"context_checksum {self.context_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted calibration run context"
            )
        object.__setattr__(self, "context_checksum", expected_checksum)


def _calibration_run_context_payload(context: CalibrationRunContext) -> dict[str, Any]:
    return {
        "calibration_schema_version": context.calibration_schema_version,
        "stage": context.stage.value,
        "calibration_run_id": context.calibration_run_id,
        "execution_profile_id": context.execution_profile_id,
        "evaluator_version": context.evaluator_version,
        "execution_protocol_version": context.execution_protocol_version,
        "dataset_version": context.dataset_version,
        "dataset_checksum": context.dataset_checksum,
        "partition_version": context.partition_version,
        "oracle_version": context.oracle_version,
        "comparison_profile_version": context.comparison_profile_version,
        "task_manifest_checksum": context.task_manifest_checksum,
    }


def calibration_run_context_to_dict(context: CalibrationRunContext) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`CalibrationRunContext`."""
    return {
        **_calibration_run_context_payload(context),
        "context_checksum": context.context_checksum,
    }


def calibration_run_context_from_dict(data: Mapping[str, Any]) -> CalibrationRunContext:
    """Inverse of :func:`calibration_run_context_to_dict`."""
    try:
        return CalibrationRunContext(
            calibration_schema_version=data["calibration_schema_version"],
            stage=CalibrationStage(data["stage"]),
            calibration_run_id=data["calibration_run_id"],
            execution_profile_id=data["execution_profile_id"],
            evaluator_version=data["evaluator_version"],
            execution_protocol_version=data["execution_protocol_version"],
            dataset_version=data["dataset_version"],
            dataset_checksum=data["dataset_checksum"],
            partition_version=data["partition_version"],
            oracle_version=data["oracle_version"],
            comparison_profile_version=data["comparison_profile_version"],
            task_manifest_checksum=data["task_manifest_checksum"],
            context_checksum=data["context_checksum"],
        )
    except KeyError as exc:
        raise InvalidCalibrationRecordError(f"missing required context field: {exc}") from exc
    except ValueError as exc:
        raise InvalidCalibrationRecordError(f"malformed calibration run context: {exc}") from exc


# ---------------------------------------------------------------------------
# Nullable-telemetry-triple validation (value / quality / unavailable_reason)
# ---------------------------------------------------------------------------


def _validate_telemetry_triple(
    obj: object, value_field: str, quality_field: str, reason_field: str
) -> None:
    value = getattr(obj, value_field)
    quality = getattr(obj, quality_field)
    reason = getattr(obj, reason_field)
    if value is None:
        if quality is not None:
            raise InvalidCalibrationRecordError(
                f"{quality_field!r} must be None when {value_field!r} is None, got {quality!r}"
            )
        if not isinstance(reason, TelemetryUnavailableReason):
            raise InvalidCalibrationRecordError(
                f"{reason_field!r} must be a TelemetryUnavailableReason when "
                f"{value_field!r} is None, got {reason!r}"
            )
    else:
        if reason is not None:
            raise InvalidCalibrationRecordError(
                f"{reason_field!r} must be None when {value_field!r} is present, got {reason!r}"
            )
        if not isinstance(quality, MeasurementQuality):
            raise InvalidCalibrationRecordError(
                f"{quality_field!r} must be a MeasurementQuality when {value_field!r} is "
                f"present, got {quality!r}"
            )


# ---------------------------------------------------------------------------
# CalibrationInvocationRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationInvocationRecord:  # pylint: disable=too-many-instance-attributes
    """One case-level backend execution attempt during calibration.

    ``case_ordinal`` (an integer position within the task's case list, not
    the true ``case_id``) and ``task_evaluation_replicate_id`` (an integer
    replicate index) deliberately carry no case-content signal, per the
    Amendment's own default. ``candidate_wall_time_sec``,
    ``observed_response_bytes``, ``peak_memory_bytes``, and
    ``peak_process_count`` are each paired with a quality tag (describing
    quality *when present*) and, when ``None``, a typed
    :class:`TelemetryUnavailableReason` -- see
    :func:`_validate_telemetry_triple`. ``peak_memory_bytes``/
    ``peak_process_count`` are always ``None``/``NOT_YET_INSTRUMENTED``
    until H.2C's own telemetry collection exists; this module only defines
    the schema they will eventually populate.

    ``reference_case_checksum`` (schema-provenance-audit correction) pins
    exactly which frozen reference-case set (the same concept as
    :class:`~src.reference.result_schema.ReferenceTaskResult`'s own
    ``reference_case_checksum``) ``case_ordinal`` is a position *within* --
    ``case_ordinal`` alone is never meaningful without this pin; see
    :func:`require_consistent_case_scope`.
    """

    calibration_schema_version: str
    context: CalibrationRunContext
    task_id: str
    candidate_sha256: str
    reference_case_checksum: str
    case_ordinal: int
    task_evaluation_replicate_id: int
    attempt_id: int
    invocation_id: str
    invoked_at: str
    execution_status: ExecutionStatus
    measurement_status: MeasurementStatus
    first_failure_category: FailureCategory
    candidate_wall_time_sec: float | None
    candidate_wall_time_quality: MeasurementQuality | None
    candidate_wall_time_unavailable_reason: TelemetryUnavailableReason | None
    controller_wall_time_sec: float
    request_bytes: int
    observed_response_bytes: int | None
    observed_response_quality: MeasurementQuality | None
    observed_response_unavailable_reason: TelemetryUnavailableReason | None
    peak_memory_bytes: int | None
    peak_memory_quality: MeasurementQuality | None
    peak_memory_unavailable_reason: TelemetryUnavailableReason | None
    peak_process_count: int | None
    peak_process_quality: MeasurementQuality | None
    peak_process_unavailable_reason: TelemetryUnavailableReason | None
    exit_code: int | None
    terminating_signal: int | None
    backend_id: str
    backend_version: str
    runner_image_digest: str
    superseded: bool = False
    record_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        if self.calibration_schema_version != CALIBRATION_SCHEMA_VERSION:
            raise UnsupportedCalibrationSchemaVersionError(
                f"calibration_schema_version {self.calibration_schema_version!r} does not "
                f"match the version this module implements ({CALIBRATION_SCHEMA_VERSION!r})"
            )
        if not isinstance(self.context, CalibrationRunContext):
            raise InvalidCalibrationRecordError(
                f"context must be a CalibrationRunContext, got {self.context!r}"
            )
        for field_name in (
            "task_id",
            "invocation_id",
            "invoked_at",
            "backend_id",
            "backend_version",
            "runner_image_digest",
        ):
            _require_nonempty_str(self, field_name)
        _require_sha256_hex(self, "candidate_sha256")
        _require_sha256_hex(self, "reference_case_checksum")
        _require_non_negative_int(self, "case_ordinal")
        _require_non_negative_int(self, "task_evaluation_replicate_id")
        if (
            not isinstance(self.attempt_id, int)
            or isinstance(self.attempt_id, bool)
            or self.attempt_id < 1
        ):
            raise InvalidCalibrationRecordError(
                f"attempt_id must be an int >= 1 (first attempt is 1), got {self.attempt_id!r}"
            )
        if not isinstance(self.execution_status, ExecutionStatus):
            raise InvalidCalibrationRecordError(
                f"execution_status must be an ExecutionStatus, got {self.execution_status!r}"
            )
        if not isinstance(self.measurement_status, MeasurementStatus):
            raise InvalidCalibrationRecordError(
                f"measurement_status must be a MeasurementStatus, got {self.measurement_status!r}"
            )
        if not isinstance(self.first_failure_category, FailureCategory):
            raise InvalidCalibrationRecordError(
                f"first_failure_category must be a FailureCategory, got "
                f"{self.first_failure_category!r}"
            )
        _require_non_negative_float(self, "controller_wall_time_sec")
        _require_non_negative_int(self, "request_bytes")
        _validate_telemetry_triple(
            self,
            "candidate_wall_time_sec",
            "candidate_wall_time_quality",
            "candidate_wall_time_unavailable_reason",
        )
        _validate_telemetry_triple(
            self,
            "observed_response_bytes",
            "observed_response_quality",
            "observed_response_unavailable_reason",
        )
        _validate_telemetry_triple(
            self, "peak_memory_bytes", "peak_memory_quality", "peak_memory_unavailable_reason"
        )
        _validate_telemetry_triple(
            self, "peak_process_count", "peak_process_quality", "peak_process_unavailable_reason"
        )
        if self.exit_code is not None and (
            not isinstance(self.exit_code, int) or isinstance(self.exit_code, bool)
        ):
            raise InvalidCalibrationRecordError(
                f"exit_code must be an int or None, got {self.exit_code!r}"
            )
        if self.terminating_signal is not None and (
            not isinstance(self.terminating_signal, int)
            or isinstance(self.terminating_signal, bool)
            or self.terminating_signal < 0
        ):
            raise InvalidCalibrationRecordError(
                f"terminating_signal must be a non-negative int or None, got "
                f"{self.terminating_signal!r}"
            )
        _require_bool(self, "superseded")

        payload = _calibration_invocation_record_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.record_checksum and self.record_checksum != expected_checksum:
            raise InvalidCalibrationRecordError(
                f"record_checksum {self.record_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted invocation record"
            )
        object.__setattr__(self, "record_checksum", expected_checksum)


def _calibration_invocation_record_payload(record: CalibrationInvocationRecord) -> dict[str, Any]:
    return {
        "calibration_schema_version": record.calibration_schema_version,
        "context": calibration_run_context_to_dict(record.context),
        "task_id": record.task_id,
        "candidate_sha256": record.candidate_sha256,
        "reference_case_checksum": record.reference_case_checksum,
        "case_ordinal": record.case_ordinal,
        "task_evaluation_replicate_id": record.task_evaluation_replicate_id,
        "attempt_id": record.attempt_id,
        "invocation_id": record.invocation_id,
        "invoked_at": record.invoked_at,
        "execution_status": record.execution_status.value,
        "measurement_status": record.measurement_status.value,
        "first_failure_category": record.first_failure_category.value,
        "candidate_wall_time_sec": record.candidate_wall_time_sec,
        "candidate_wall_time_quality": _enum_value(record.candidate_wall_time_quality),
        "candidate_wall_time_unavailable_reason": _enum_value(
            record.candidate_wall_time_unavailable_reason
        ),
        "controller_wall_time_sec": record.controller_wall_time_sec,
        "request_bytes": record.request_bytes,
        "observed_response_bytes": record.observed_response_bytes,
        "observed_response_quality": _enum_value(record.observed_response_quality),
        "observed_response_unavailable_reason": _enum_value(
            record.observed_response_unavailable_reason
        ),
        "peak_memory_bytes": record.peak_memory_bytes,
        "peak_memory_quality": _enum_value(record.peak_memory_quality),
        "peak_memory_unavailable_reason": _enum_value(record.peak_memory_unavailable_reason),
        "peak_process_count": record.peak_process_count,
        "peak_process_quality": _enum_value(record.peak_process_quality),
        "peak_process_unavailable_reason": _enum_value(record.peak_process_unavailable_reason),
        "exit_code": record.exit_code,
        "terminating_signal": record.terminating_signal,
        "backend_id": record.backend_id,
        "backend_version": record.backend_version,
        "runner_image_digest": record.runner_image_digest,
        "superseded": record.superseded,
    }


def calibration_invocation_record_to_dict(record: CalibrationInvocationRecord) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`CalibrationInvocationRecord`."""
    return {
        **_calibration_invocation_record_payload(record),
        "record_checksum": record.record_checksum,
    }


def _optional_enum(value: Any, enum_cls: type[Enum]) -> Any:
    return None if value is None else enum_cls(value)


def calibration_invocation_record_from_dict(data: Mapping[str, Any]) -> CalibrationInvocationRecord:
    """Inverse of :func:`calibration_invocation_record_to_dict`."""
    try:
        return CalibrationInvocationRecord(
            calibration_schema_version=data["calibration_schema_version"],
            context=calibration_run_context_from_dict(data["context"]),
            task_id=data["task_id"],
            candidate_sha256=data["candidate_sha256"],
            reference_case_checksum=data["reference_case_checksum"],
            case_ordinal=data["case_ordinal"],
            task_evaluation_replicate_id=data["task_evaluation_replicate_id"],
            attempt_id=data["attempt_id"],
            invocation_id=data["invocation_id"],
            invoked_at=data["invoked_at"],
            execution_status=ExecutionStatus(data["execution_status"]),
            measurement_status=MeasurementStatus(data["measurement_status"]),
            first_failure_category=FailureCategory(data["first_failure_category"]),
            candidate_wall_time_sec=data["candidate_wall_time_sec"],
            candidate_wall_time_quality=_optional_enum(
                data["candidate_wall_time_quality"], MeasurementQuality
            ),
            candidate_wall_time_unavailable_reason=_optional_enum(
                data["candidate_wall_time_unavailable_reason"], TelemetryUnavailableReason
            ),
            controller_wall_time_sec=data["controller_wall_time_sec"],
            request_bytes=data["request_bytes"],
            observed_response_bytes=data["observed_response_bytes"],
            observed_response_quality=_optional_enum(
                data["observed_response_quality"], MeasurementQuality
            ),
            observed_response_unavailable_reason=_optional_enum(
                data["observed_response_unavailable_reason"], TelemetryUnavailableReason
            ),
            peak_memory_bytes=data["peak_memory_bytes"],
            peak_memory_quality=_optional_enum(data["peak_memory_quality"], MeasurementQuality),
            peak_memory_unavailable_reason=_optional_enum(
                data["peak_memory_unavailable_reason"], TelemetryUnavailableReason
            ),
            peak_process_count=data["peak_process_count"],
            peak_process_quality=_optional_enum(data["peak_process_quality"], MeasurementQuality),
            peak_process_unavailable_reason=_optional_enum(
                data["peak_process_unavailable_reason"], TelemetryUnavailableReason
            ),
            exit_code=data["exit_code"],
            terminating_signal=data["terminating_signal"],
            backend_id=data["backend_id"],
            backend_version=data["backend_version"],
            runner_image_digest=data["runner_image_digest"],
            superseded=data["superseded"],
            record_checksum=data["record_checksum"],
        )
    except KeyError as exc:
        raise InvalidCalibrationRecordError(
            f"missing required invocation record field: {exc}"
        ) from exc
    except ValueError as exc:
        raise InvalidCalibrationRecordError(f"malformed invocation record: {exc}") from exc


# ---------------------------------------------------------------------------
# CalibrationTaskEvaluationRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationTaskEvaluationRecord:  # pylint: disable=too-many-instance-attributes
    """One complete task/candidate/profile/replicate evaluation, aggregating
    a set of contributing :class:`CalibrationInvocationRecord`\\ s.

    Uniquely identified (design doc §9's "Identity relationships") by
    ``(context.stage, context.calibration_run_id, task_id, candidate_sha256,
    context.execution_profile_id, context.evaluator_version,
    task_evaluation_replicate_id)`` -- every field of that tuple is present
    directly on this record via the embedded ``context`` plus its own
    fields, so identity can be read off one record with no external lookup.

    ``reference_case_checksum`` (schema-provenance-audit correction) pins
    the same frozen reference-case set every contributing invocation must
    share -- checked by :func:`reconcile_task_evaluation`.
    ``contributing_invocation_content_checksums`` (schema-provenance-audit
    correction) is the parallel tuple of each contributor's own
    ``record_checksum`` at binding time, so
    ``contributing_invocations_checksum`` below binds contributor *content*,
    not merely their display ``invocation_id``\\ s: reordering is
    normalized (both tuples are zipped and sorted by id before hashing),
    but changing any contributing record's own content changes its
    ``record_checksum`` and therefore invalidates this checksum.
    """

    calibration_schema_version: str
    context: CalibrationRunContext
    task_id: str
    candidate_sha256: str
    reference_case_checksum: str
    task_evaluation_replicate_id: int
    measurement_status: MeasurementStatus
    q_ref_task: float | None
    first_failure_category: FailureCategory
    reference_case_total: int
    reference_case_pass_count: int
    work_item_disposition: WorkItemDisposition
    contributing_invocation_ids: tuple[str, ...]
    contributing_invocation_content_checksums: tuple[str, ...]
    evaluated_at: str
    superseded: bool = False
    contributing_invocations_checksum: str = ""
    record_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        if self.calibration_schema_version != CALIBRATION_SCHEMA_VERSION:
            raise UnsupportedCalibrationSchemaVersionError(
                f"calibration_schema_version {self.calibration_schema_version!r} does not "
                f"match the version this module implements ({CALIBRATION_SCHEMA_VERSION!r})"
            )
        if not isinstance(self.context, CalibrationRunContext):
            raise InvalidCalibrationRecordError(
                f"context must be a CalibrationRunContext, got {self.context!r}"
            )
        _require_nonempty_str(self, "task_id")
        _require_sha256_hex(self, "candidate_sha256")
        _require_sha256_hex(self, "reference_case_checksum")
        _require_non_negative_int(self, "task_evaluation_replicate_id")
        if not isinstance(self.measurement_status, MeasurementStatus):
            raise InvalidCalibrationRecordError(
                f"measurement_status must be a MeasurementStatus, got {self.measurement_status!r}"
            )
        if not isinstance(self.first_failure_category, FailureCategory):
            raise InvalidCalibrationRecordError(
                f"first_failure_category must be a FailureCategory, got "
                f"{self.first_failure_category!r}"
            )
        if not isinstance(self.work_item_disposition, WorkItemDisposition):
            raise InvalidCalibrationRecordError(
                f"work_item_disposition must be a WorkItemDisposition, got "
                f"{self.work_item_disposition!r}"
            )
        _require_non_negative_int(self, "reference_case_total")
        _require_non_negative_int(self, "reference_case_pass_count")
        if self.reference_case_pass_count > self.reference_case_total:
            raise InvalidCalibrationRecordError(
                f"reference_case_pass_count ({self.reference_case_pass_count}) exceeds "
                f"reference_case_total ({self.reference_case_total})"
            )
        _require_nonempty_str(self, "evaluated_at")
        _require_bool(self, "superseded")
        self._validate_q_ref_task()
        self._validate_contributing_invocation_ids()

        contributing_checksum = _contributing_invocations_checksum(
            self.contributing_invocation_ids, self.contributing_invocation_content_checksums
        )
        if (
            self.contributing_invocations_checksum
            and self.contributing_invocations_checksum != contributing_checksum
        ):
            raise InvalidCalibrationRecordError(
                f"contributing_invocations_checksum {self.contributing_invocations_checksum!r} "
                f"does not match the recomputed checksum {contributing_checksum!r} over its "
                f"own (sorted) contributing (id, content-checksum) pairs -- tampered "
                f"contributor set"
            )
        object.__setattr__(self, "contributing_invocations_checksum", contributing_checksum)

        payload = _calibration_task_evaluation_record_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.record_checksum and self.record_checksum != expected_checksum:
            raise InvalidCalibrationRecordError(
                f"record_checksum {self.record_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted task-evaluation record"
            )
        object.__setattr__(self, "record_checksum", expected_checksum)

    def _validate_q_ref_task(self) -> None:
        if self.measurement_status == MeasurementStatus.VALID:
            # pylint: disable=unidiomatic-typecheck
            if type(self.q_ref_task) is not float or self.q_ref_task not in (0.0, 1.0):
                raise InvalidCalibrationRecordError(
                    f"task {self.task_id!r}: q_ref_task must be exactly 0.0 or 1.0 when "
                    f"measurement_status is VALID, got {self.q_ref_task!r}"
                )
        elif self.q_ref_task is not None:
            raise InvalidCalibrationRecordError(
                f"task {self.task_id!r}: q_ref_task must be None when measurement_status is "
                f"{self.measurement_status.value}, got {self.q_ref_task!r}"
            )

    def _validate_contributing_invocation_ids(self) -> None:
        if not isinstance(self.contributing_invocation_ids, tuple):
            raise InvalidCalibrationRecordError(
                f"contributing_invocation_ids must be a tuple, got "
                f"{type(self.contributing_invocation_ids).__name__}"
            )
        for invocation_id in self.contributing_invocation_ids:
            if not isinstance(invocation_id, str) or invocation_id == "":
                raise InvalidCalibrationRecordError(
                    f"contributing_invocation_ids entries must be nonempty strings, got "
                    f"{invocation_id!r}"
                )
        if len(set(self.contributing_invocation_ids)) != len(self.contributing_invocation_ids):
            raise InvalidCalibrationRecordError(
                "contributing_invocation_ids contains duplicate invocation ids"
            )
        if not isinstance(self.contributing_invocation_content_checksums, tuple):
            raise InvalidCalibrationRecordError(
                f"contributing_invocation_content_checksums must be a tuple, got "
                f"{type(self.contributing_invocation_content_checksums).__name__}"
            )
        if len(self.contributing_invocation_content_checksums) != len(
            self.contributing_invocation_ids
        ):
            raise InvalidCalibrationRecordError(
                f"contributing_invocation_content_checksums must have exactly one entry per "
                f"contributing_invocation_ids entry (got "
                f"{len(self.contributing_invocation_content_checksums)} checksums for "
                f"{len(self.contributing_invocation_ids)} ids)"
            )
        for content_checksum in self.contributing_invocation_content_checksums:
            if not isinstance(content_checksum, str) or not _SHA256_HEX_PATTERN.match(
                content_checksum
            ):
                raise InvalidCalibrationRecordError(
                    f"contributing_invocation_content_checksums entries must each be a "
                    f"64-character lowercase hex sha256 digest, got {content_checksum!r}"
                )


def _contributing_invocations_checksum(
    invocation_ids: Sequence[str], content_checksums: Sequence[str]
) -> str:
    """Hash the *content-bound* contributor set: sorted ``(id,
    content_checksum)`` pairs, so reordering is normalized but changing any
    contributor's own content (which changes its ``record_checksum``)
    changes this checksum too -- see the schema-provenance-audit
    correction in :class:`CalibrationTaskEvaluationRecord`'s docstring."""
    pairs = sorted(zip(invocation_ids, content_checksums))
    return _sha256_of({"contributing_invocation_pairs": [list(pair) for pair in pairs]})


def _calibration_task_evaluation_record_payload(
    record: CalibrationTaskEvaluationRecord,
) -> dict[str, Any]:
    return {
        "calibration_schema_version": record.calibration_schema_version,
        "context": calibration_run_context_to_dict(record.context),
        "task_id": record.task_id,
        "candidate_sha256": record.candidate_sha256,
        "reference_case_checksum": record.reference_case_checksum,
        "task_evaluation_replicate_id": record.task_evaluation_replicate_id,
        "measurement_status": record.measurement_status.value,
        "q_ref_task": record.q_ref_task,
        "first_failure_category": record.first_failure_category.value,
        "reference_case_total": record.reference_case_total,
        "reference_case_pass_count": record.reference_case_pass_count,
        "work_item_disposition": record.work_item_disposition.value,
        "contributing_invocation_ids": list(record.contributing_invocation_ids),
        "contributing_invocation_content_checksums": list(
            record.contributing_invocation_content_checksums
        ),
        "contributing_invocations_checksum": record.contributing_invocations_checksum,
        "evaluated_at": record.evaluated_at,
        "superseded": record.superseded,
    }


def calibration_task_evaluation_record_to_dict(
    record: CalibrationTaskEvaluationRecord,
) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`CalibrationTaskEvaluationRecord`."""
    return {
        **_calibration_task_evaluation_record_payload(record),
        "record_checksum": record.record_checksum,
    }


def calibration_task_evaluation_record_from_dict(
    data: Mapping[str, Any],
) -> CalibrationTaskEvaluationRecord:
    """Inverse of :func:`calibration_task_evaluation_record_to_dict`."""
    try:
        return CalibrationTaskEvaluationRecord(
            calibration_schema_version=data["calibration_schema_version"],
            context=calibration_run_context_from_dict(data["context"]),
            task_id=data["task_id"],
            candidate_sha256=data["candidate_sha256"],
            reference_case_checksum=data["reference_case_checksum"],
            task_evaluation_replicate_id=data["task_evaluation_replicate_id"],
            measurement_status=MeasurementStatus(data["measurement_status"]),
            q_ref_task=data["q_ref_task"],
            first_failure_category=FailureCategory(data["first_failure_category"]),
            reference_case_total=data["reference_case_total"],
            reference_case_pass_count=data["reference_case_pass_count"],
            work_item_disposition=WorkItemDisposition(data["work_item_disposition"]),
            contributing_invocation_ids=tuple(data["contributing_invocation_ids"]),
            contributing_invocation_content_checksums=tuple(
                data["contributing_invocation_content_checksums"]
            ),
            evaluated_at=data["evaluated_at"],
            superseded=data["superseded"],
            contributing_invocations_checksum=data["contributing_invocations_checksum"],
            record_checksum=data["record_checksum"],
        )
    except KeyError as exc:
        raise InvalidCalibrationRecordError(
            f"missing required task-evaluation record field: {exc}"
        ) from exc
    except ValueError as exc:
        raise InvalidCalibrationRecordError(f"malformed task-evaluation record: {exc}") from exc


# ---------------------------------------------------------------------------
# Cross-record reconciliation
# ---------------------------------------------------------------------------


def require_consistent_case_scope(invocations: Sequence[CalibrationInvocationRecord]) -> None:
    """Raise :class:`CalibrationReconciliationError` unless every invocation
    shares the same ``(task_id, reference_case_checksum)`` pair --
    ``case_ordinal`` is only ever meaningful relative to that identical
    pair (schema-provenance-audit correction), never in isolation."""
    scopes = {
        (invocation.task_id, invocation.reference_case_checksum) for invocation in invocations
    }
    if len(scopes) > 1:
        raise CalibrationReconciliationError(
            f"invocations do not share a single (task_id, reference_case_checksum) scope -- "
            f"case_ordinal is meaningless without an identical pair; found scopes: "
            f"{sorted(scopes)!r}"
        )


def reconcile_task_evaluation(
    task_evaluation: CalibrationTaskEvaluationRecord,
    invocations_by_id: Mapping[str, CalibrationInvocationRecord],
) -> None:
    """Raise :class:`CalibrationReconciliationError` unless every one of
    ``task_evaluation``'s ``contributing_invocation_ids`` is present in
    ``invocations_by_id``, shares its exact context/task/candidate/
    reference-case/replicate identity with ``task_evaluation`` and with
    each other, and its *current* ``record_checksum`` still matches the
    content checksum ``task_evaluation`` bound it under -- and unless
    ``contributing_invocations_checksum`` still matches a fresh
    recomputation over those bound (id, content-checksum) pairs. Never
    mutates either input."""
    missing = [
        invocation_id
        for invocation_id in task_evaluation.contributing_invocation_ids
        if invocation_id not in invocations_by_id
    ]
    if missing:
        raise CalibrationReconciliationError(
            f"task-evaluation record for {task_evaluation.task_id!r} references contributing "
            f"invocation id(s) not present in the supplied set: {missing!r}"
        )
    contributors = [
        invocations_by_id[invocation_id]
        for invocation_id in task_evaluation.contributing_invocation_ids
    ]
    for invocation_id, invocation in zip(task_evaluation.contributing_invocation_ids, contributors):
        if invocation.context.context_checksum != task_evaluation.context.context_checksum:
            raise CalibrationReconciliationError(
                f"invocation {invocation_id!r} was recorded under a different calibration "
                f"context than task-evaluation record for {task_evaluation.task_id!r} "
                f"(this also catches identical labels bound to a different "
                f"task_manifest_checksum, since that checksum is part of the context)"
            )
        if invocation.task_id != task_evaluation.task_id:
            raise CalibrationReconciliationError(
                f"invocation {invocation_id!r} has task_id {invocation.task_id!r}, expected "
                f"{task_evaluation.task_id!r}"
            )
        if invocation.candidate_sha256 != task_evaluation.candidate_sha256:
            raise CalibrationReconciliationError(
                f"invocation {invocation_id!r} has candidate_sha256 "
                f"{invocation.candidate_sha256!r}, expected {task_evaluation.candidate_sha256!r}"
            )
        if invocation.reference_case_checksum != task_evaluation.reference_case_checksum:
            raise CalibrationReconciliationError(
                f"invocation {invocation_id!r} has reference_case_checksum "
                f"{invocation.reference_case_checksum!r}, expected "
                f"{task_evaluation.reference_case_checksum!r} -- mixed evidence sets cannot "
                f"contribute to the same task evaluation"
            )
        if invocation.task_evaluation_replicate_id != task_evaluation.task_evaluation_replicate_id:
            raise CalibrationReconciliationError(
                f"invocation {invocation_id!r} has task_evaluation_replicate_id "
                f"{invocation.task_evaluation_replicate_id!r}, expected "
                f"{task_evaluation.task_evaluation_replicate_id!r}"
            )
    require_consistent_case_scope(contributors)
    for invocation_id, invocation, bound_content_checksum in zip(
        task_evaluation.contributing_invocation_ids,
        contributors,
        task_evaluation.contributing_invocation_content_checksums,
    ):
        if invocation.record_checksum != bound_content_checksum:
            raise CalibrationReconciliationError(
                f"invocation {invocation_id!r} has current record_checksum "
                f"{invocation.record_checksum!r}, but task-evaluation record for "
                f"{task_evaluation.task_id!r} bound it under {bound_content_checksum!r} -- "
                f"contributor content changed after binding"
            )
    recomputed = _contributing_invocations_checksum(
        task_evaluation.contributing_invocation_ids,
        task_evaluation.contributing_invocation_content_checksums,
    )
    if recomputed != task_evaluation.contributing_invocations_checksum:
        raise CalibrationReconciliationError(
            f"task-evaluation record for {task_evaluation.task_id!r} has a "
            f"contributing_invocations_checksum inconsistent with its own contributing "
            f"(id, content-checksum) pairs -- tampered contributor set"
        )


def reconcile_all(
    invocations: Sequence[CalibrationInvocationRecord],
    task_evaluations: Sequence[CalibrationTaskEvaluationRecord],
) -> None:
    """Reconcile every task-evaluation record against ``invocations``, in
    the given (deterministic, e.g. trace-append) order. Raises on the first
    reconciliation failure encountered."""
    invocations_by_id = {invocation.invocation_id: invocation for invocation in invocations}
    for task_evaluation in task_evaluations:
        reconcile_task_evaluation(task_evaluation, invocations_by_id)
