"""Synthetic calibration-record factories shared between
``test_calibration_schema.py`` and ``test_calibration_trace.py``.

Every factory builds a structurally valid record by default, with any
field overridable via keyword arguments -- kept in one place so both test
modules exercise the exact same baseline fixture rather than two copies
drifting apart. No privileged content, no real task/candidate data.
"""

from typing import Sequence

from src.evaluators.schema import FailureCategory
from src.execution.protocol import ExecutionStatus
from src.reference.calibration_schema import (
    CALIBRATION_SCHEMA_VERSION,
    CalibrationInvocationRecord,
    CalibrationRunContext,
    CalibrationStage,
    CalibrationTaskEvaluationRecord,
    MeasurementQuality,
    TelemetryUnavailableReason,
)
from src.reference.reference_orchestrator import WorkItemDisposition
from src.reference.result_schema import MeasurementStatus

CANDIDATE_SHA256 = "b" * 64
OTHER_CANDIDATE_SHA256 = "d" * 64
DATASET_CHECKSUM = "a" * 64
TASK_MANIFEST_CHECKSUM = "9" * 64
REFERENCE_CASE_CHECKSUM = "e" * 64
OTHER_REFERENCE_CASE_CHECKSUM = "f" * 64
RUNNER_IMAGE_DIGEST = "sha256:" + "c" * 64


def make_context(**overrides: object) -> CalibrationRunContext:
    """Build a structurally valid CalibrationRunContext, fields overridable."""
    fields: dict[str, object] = {
        "calibration_schema_version": CALIBRATION_SCHEMA_VERSION,
        "stage": CalibrationStage.H3,
        "calibration_run_id": "run-1",
        "execution_profile_id": "docker-megb03h-diagnostic-v1",
        "evaluator_version": "megb-03h-diagnostic-evaluator-v1",
        "execution_protocol_version": "reference-evaluator-execution-protocol-v1",
        "dataset_version": "humaneval-plus-1.0",
        "dataset_checksum": DATASET_CHECKSUM,
        "partition_version": "partition-v1",
        "oracle_version": "oracle-v1",
        "comparison_profile_version": "comparison-v1",
        "task_manifest_checksum": TASK_MANIFEST_CHECKSUM,
    }
    fields.update(overrides)
    return CalibrationRunContext(**fields)  # type: ignore[arg-type]


def make_invocation(
    invocation_id: object = "inv-1", **overrides: object
) -> CalibrationInvocationRecord:
    """Build a structurally valid CalibrationInvocationRecord, fields overridable."""
    fields: dict[str, object] = {
        "calibration_schema_version": CALIBRATION_SCHEMA_VERSION,
        "context": make_context(),
        "task_id": "HumanEval/41",
        "candidate_sha256": CANDIDATE_SHA256,
        "reference_case_checksum": REFERENCE_CASE_CHECKSUM,
        "case_ordinal": 0,
        "task_evaluation_replicate_id": 0,
        "attempt_id": 1,
        "invocation_id": invocation_id,
        "invoked_at": "2026-08-03T00:00:00Z",
        "execution_status": ExecutionStatus.COMPLETED,
        "measurement_status": MeasurementStatus.VALID,
        "first_failure_category": FailureCategory.NONE,
        "candidate_wall_time_sec": 0.01,
        "candidate_wall_time_quality": MeasurementQuality.EXACT,
        "candidate_wall_time_unavailable_reason": None,
        "controller_wall_time_sec": 0.02,
        "request_bytes": 100,
        "observed_response_bytes": 50,
        "observed_response_quality": MeasurementQuality.EXACT,
        "observed_response_unavailable_reason": None,
        "peak_memory_bytes": None,
        "peak_memory_quality": None,
        "peak_memory_unavailable_reason": TelemetryUnavailableReason.NOT_YET_INSTRUMENTED,
        "peak_process_count": None,
        "peak_process_quality": None,
        "peak_process_unavailable_reason": TelemetryUnavailableReason.NOT_YET_INSTRUMENTED,
        "exit_code": 0,
        "terminating_signal": None,
        "backend_id": "docker",
        "backend_version": "1.0",
        "runner_image_digest": RUNNER_IMAGE_DIGEST,
    }
    fields.update(overrides)
    return CalibrationInvocationRecord(**fields)  # type: ignore[arg-type]


def make_task_evaluation(**overrides: object) -> CalibrationTaskEvaluationRecord:
    """Build a structurally valid CalibrationTaskEvaluationRecord, fields
    overridable. The default single contributor ("inv-1") and its
    contributing_invocation_content_checksums entry are kept consistent
    with make_invocation()'s own default record_checksum -- callers that
    override contributing_invocation_ids to a different arity must also
    override contributing_invocation_content_checksums to match (see
    make_task_evaluation_for for a helper that derives both from real
    invocation records instead)."""
    default_contributor_checksum = make_invocation().record_checksum
    fields: dict[str, object] = {
        "calibration_schema_version": CALIBRATION_SCHEMA_VERSION,
        "context": make_context(),
        "task_id": "HumanEval/41",
        "candidate_sha256": CANDIDATE_SHA256,
        "reference_case_checksum": REFERENCE_CASE_CHECKSUM,
        "task_evaluation_replicate_id": 0,
        "measurement_status": MeasurementStatus.VALID,
        "q_ref_task": 1.0,
        "first_failure_category": FailureCategory.NONE,
        "reference_case_total": 1,
        "reference_case_pass_count": 1,
        "work_item_disposition": WorkItemDisposition.EXECUTED_VALID,
        "contributing_invocation_ids": ("inv-1",),
        "contributing_invocation_content_checksums": (default_contributor_checksum,),
        "evaluated_at": "2026-08-03T00:00:01Z",
    }
    fields.update(overrides)
    return CalibrationTaskEvaluationRecord(**fields)  # type: ignore[arg-type]


def make_task_evaluation_for(
    invocations: Sequence[CalibrationInvocationRecord], **overrides: object
) -> CalibrationTaskEvaluationRecord:
    """Build a CalibrationTaskEvaluationRecord whose contributing_invocation_ids
    and contributing_invocation_content_checksums are correctly derived
    from the given (already-constructed) invocation records' own current
    identity/content -- the realistic way to build a task-evaluation record
    that will actually reconcile against those exact invocations."""
    first = invocations[0]
    fields: dict[str, object] = {
        "calibration_schema_version": CALIBRATION_SCHEMA_VERSION,
        "context": first.context,
        "task_id": first.task_id,
        "candidate_sha256": first.candidate_sha256,
        "reference_case_checksum": first.reference_case_checksum,
        "task_evaluation_replicate_id": first.task_evaluation_replicate_id,
        "measurement_status": MeasurementStatus.VALID,
        "q_ref_task": 1.0,
        "first_failure_category": FailureCategory.NONE,
        "reference_case_total": len(invocations),
        "reference_case_pass_count": len(invocations),
        "work_item_disposition": WorkItemDisposition.EXECUTED_VALID,
        "contributing_invocation_ids": tuple(inv.invocation_id for inv in invocations),
        "contributing_invocation_content_checksums": tuple(
            inv.record_checksum for inv in invocations
        ),
        "evaluated_at": "2026-08-03T00:00:01Z",
    }
    fields.update(overrides)
    return CalibrationTaskEvaluationRecord(**fields)  # type: ignore[arg-type]
