"""MEGB-03H.2A: the safe, allowlisted calibration summary-report projection.

Split out from ``src.reference.calibration_schema`` (which defines the two
underlying record types this module aggregates) purely to keep each module
under a manageable size -- there is no behavioral reason for the split, and
both modules are part of the same H.2A checkpoint.

:class:`CalibrationSummaryReport` and :func:`build_calibration_summary_report`
implement the design doc's (§9) "Safe-summary projection" requirement:
per-task (public identifiers) aggregate case counts, resource-stat
aggregates, pass/fail/disposition counts, and measurement-quality
classification counts; self-checksummed; excludes every ``superseded``
record; never includes ``case_ordinal``-level detail, raw telemetry values
beyond aggregates, or any candidate/expected-output content -- structurally
impossible here, since no field on this schema is capable of carrying any
of that.
"""

import dataclasses
from dataclasses import dataclass
from typing import Mapping, Sequence

from src.reference.calibration_schema import (
    CalibrationInvocationRecord,
    CalibrationStage,
    CalibrationTaskEvaluationRecord,
    InvalidCalibrationRecordError,
    UnsupportedCalibrationSchemaVersionError,
    checksum_of,
)
# Reuses calibration_schema's own field validators rather than duplicating
# them: this module is a sibling half of the same H.2A checkpoint (see the
# module docstring), not an independent, decoupled consumer.
from src.reference.calibration_schema import (  # pylint: disable=protected-access
    _require_non_negative_int,
    _require_nonempty_str,
)
from src.reference.result_schema import MeasurementStatus

CALIBRATION_SUMMARY_REPORT_SCHEMA_VERSION = "megb-03h-calibration-summary-report-v1"


@dataclass(frozen=True)
class CalibrationSummaryReport:  # pylint: disable=too-many-instance-attributes
    """Safe, allowlisted aggregate summary of a calibration trace.

    Structurally cannot carry case identities, candidate source, expected
    outputs, input arguments, raw output, environment data, unrestricted
    diagnostics, or privileged paths -- there is no field here capable of
    holding any of those; every field is either an identifier already
    public (``task_id``, a HumanEval identifier), a count, or a checksum.
    Excludes every ``superseded`` record from all counts.
    """

    summary_schema_version: str
    stage: CalibrationStage
    calibration_run_id: str
    generated_at: str
    total_invocation_records: int
    total_task_evaluation_records: int
    execution_status_counts: Mapping[str, int]
    measurement_status_counts: Mapping[str, int]
    work_item_disposition_counts: Mapping[str, int]
    candidate_wall_time_quality_counts: Mapping[str, int]
    observed_response_quality_counts: Mapping[str, int]
    peak_memory_quality_counts: Mapping[str, int]
    peak_process_quality_counts: Mapping[str, int]
    per_task_case_counts: Mapping[str, int]
    report_checksum: str = ""

    def __post_init__(self) -> None:
        if self.summary_schema_version != CALIBRATION_SUMMARY_REPORT_SCHEMA_VERSION:
            raise UnsupportedCalibrationSchemaVersionError(
                f"summary_schema_version {self.summary_schema_version!r} does not match the "
                f"version this module implements "
                f"({CALIBRATION_SUMMARY_REPORT_SCHEMA_VERSION!r})"
            )
        if not isinstance(self.stage, CalibrationStage):
            raise InvalidCalibrationRecordError(
                f"stage must be a CalibrationStage, got {self.stage!r}"
            )
        _require_nonempty_str(self, "calibration_run_id")
        _require_nonempty_str(self, "generated_at")
        _require_non_negative_int(self, "total_invocation_records")
        _require_non_negative_int(self, "total_task_evaluation_records")
        for mapping_field in (
            "execution_status_counts",
            "measurement_status_counts",
            "work_item_disposition_counts",
            "candidate_wall_time_quality_counts",
            "observed_response_quality_counts",
            "peak_memory_quality_counts",
            "peak_process_quality_counts",
            "per_task_case_counts",
        ):
            self._validate_count_mapping(mapping_field)

        payload = _calibration_summary_report_payload(self)
        expected_checksum = checksum_of(payload)
        if self.report_checksum and self.report_checksum != expected_checksum:
            raise InvalidCalibrationRecordError(
                f"report_checksum {self.report_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted summary report"
            )
        object.__setattr__(self, "report_checksum", expected_checksum)

    def _validate_count_mapping(self, field_name: str) -> None:
        mapping = getattr(self, field_name)
        if not isinstance(mapping, Mapping):
            raise InvalidCalibrationRecordError(
                f"{field_name!r} must be a mapping, got {mapping!r}"
            )
        for key, count in mapping.items():
            if not isinstance(key, str) or key == "":
                raise InvalidCalibrationRecordError(
                    f"{field_name!r} has a non-string or empty key: {key!r}"
                )
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise InvalidCalibrationRecordError(
                    f"{field_name!r}[{key!r}] must be a non-negative int, got {count!r}"
                )


def _calibration_summary_report_payload(report: CalibrationSummaryReport) -> dict[str, object]:
    return {
        "summary_schema_version": report.summary_schema_version,
        "stage": report.stage.value,
        "calibration_run_id": report.calibration_run_id,
        "generated_at": report.generated_at,
        "total_invocation_records": report.total_invocation_records,
        "total_task_evaluation_records": report.total_task_evaluation_records,
        "execution_status_counts": dict(report.execution_status_counts),
        "measurement_status_counts": dict(report.measurement_status_counts),
        "work_item_disposition_counts": dict(report.work_item_disposition_counts),
        "candidate_wall_time_quality_counts": dict(report.candidate_wall_time_quality_counts),
        "observed_response_quality_counts": dict(report.observed_response_quality_counts),
        "peak_memory_quality_counts": dict(report.peak_memory_quality_counts),
        "peak_process_quality_counts": dict(report.peak_process_quality_counts),
        "per_task_case_counts": dict(report.per_task_case_counts),
    }


CALIBRATION_SUMMARY_REPORT_FIELD_NAMES = frozenset(
    field.name for field in dataclasses.fields(CalibrationSummaryReport)
)


def _count_by(values: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_calibration_summary_report(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    stage: CalibrationStage,
    calibration_run_id: str,
    generated_at: str,
    invocation_records: Sequence[CalibrationInvocationRecord],
    task_evaluation_records: Sequence[CalibrationTaskEvaluationRecord],
) -> CalibrationSummaryReport:
    """Build the safe :class:`CalibrationSummaryReport` for one stage/run,
    excluding every ``superseded`` record from all aggregates. Reads only
    public task identifiers, typed status/quality enums, and counts --
    never case content, candidate source, or expected-output data (none of
    which any input record here is even capable of carrying)."""
    active_invocations = [record for record in invocation_records if not record.superseded]
    active_task_evaluations = [
        record for record in task_evaluation_records if not record.superseded
    ]
    return CalibrationSummaryReport(
        summary_schema_version=CALIBRATION_SUMMARY_REPORT_SCHEMA_VERSION,
        stage=stage,
        calibration_run_id=calibration_run_id,
        generated_at=generated_at,
        total_invocation_records=len(active_invocations),
        total_task_evaluation_records=len(active_task_evaluations),
        execution_status_counts=_count_by(
            [record.execution_status.value for record in active_invocations]
        ),
        measurement_status_counts=_count_by(
            [record.measurement_status.value for record in active_invocations]
        ),
        work_item_disposition_counts=_count_by(
            [record.work_item_disposition.value for record in active_task_evaluations]
        ),
        candidate_wall_time_quality_counts=_count_by(
            [
                record.candidate_wall_time_quality.value
                for record in active_invocations
                if record.candidate_wall_time_quality is not None
            ]
        ),
        observed_response_quality_counts=_count_by(
            [
                record.observed_response_quality.value
                for record in active_invocations
                if record.observed_response_quality is not None
            ]
        ),
        peak_memory_quality_counts=_count_by(
            [
                record.peak_memory_quality.value
                for record in active_invocations
                if record.peak_memory_quality is not None
            ]
        ),
        peak_process_quality_counts=_count_by(
            [
                record.peak_process_quality.value
                for record in active_invocations
                if record.peak_process_quality is not None
            ]
        ),
        per_task_case_counts=_count_by([record.task_id for record in active_invocations]),
    )


def incomplete_task_evaluations(
    task_evaluations: Sequence[CalibrationTaskEvaluationRecord],
) -> tuple[CalibrationTaskEvaluationRecord, ...]:
    """Non-superseded task-evaluation records whose ``measurement_status``
    is :attr:`~src.reference.result_schema.MeasurementStatus.INCOMPLETE` --
    i.e. an interrupted evaluation that has not yet been superseded by a
    completed re-execution."""
    return tuple(
        record
        for record in task_evaluations
        if not record.superseded and record.measurement_status == MeasurementStatus.INCOMPLETE
    )
