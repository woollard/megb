"""Synthetic fixtures shared across the MEGB-03H.2B.2 (H.5 staging/gate/
promotion) test modules: a real 164-task candidate-set manifest, run
context, task results, staging identity, and a matching, reconciling
calibration trace. No real privileged corpus access, no Docker.
"""

# This module's candidate-set-manifest/task-result builders intentionally
# mirror patterns already present in test_result_schema.py (both build a
# real, self-checksummed 164-entry manifest and valid task results) --
# suppressing here rather than coupling this shared H.2B.2 fixtures module
# to that other, unrelated test module's internals (same precedent as
# _reference_orchestrator_cache_policy_fixtures.py's own header note).
# pylint: disable=duplicate-code

import hashlib

from src.evaluators.schema import FailureCategory
from src.execution.protocol import ExecutionStatus
from src.execution.telemetry_methods import (
    CollectorMethod,
    MetricCollectionDisposition,
    TerminalCoverageState,
)
from src.reference.calibration_schema import (
    CALIBRATION_SCHEMA_VERSION,
    CalibrationInvocationRecord,
    CalibrationRunContext,
    CalibrationStage,
    CalibrationTaskEvaluationRecord,
    CollectorMethodProvenance,
    HostRuntimeContext,
    TelemetryCollectionPolicy,
    TelemetryUnavailableReason,
)
from src.reference.h5_staging import H5StagingIdentity
from src.reference.oracle import COMPARISON_PROFILE_VERSION
from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EXECUTION_PROFILE_ID_FULL,
    EXECUTION_PROTOCOL_VERSION,
)
from src.reference.reference_orchestrator import WorkItemDisposition
from src.reference.result_schema import (
    REFERENCE_VALIDATION_CANDIDATE_SET_ALGORITHM_VERSION,
    REFERENCE_VALIDATION_CANDIDATE_SET_MANIFEST_SCHEMA_VERSION,
    REQUIRED_TASK_COUNT,
    CandidateSetEntry,
    MeasurementStatus,
    ReferenceRunContext,
    ReferenceTaskResult,
    ReferenceValidationCandidateSetManifest,
)

TASK_MANIFEST_CHECKSUM = "d" * 64
SELECTION_PROVENANCE_SHA256 = "e" * 64
CONFIG_SHA256 = "b" * 64
ORACLE_VERSION = "oracle-v1"
DATASET_VERSION = "humaneval-plus-v0.1.10"
DATASET_CHECKSUM = "fe585eb4df8c88d844eeb463ea4d0302"
PARTITION_VERSION = "partition-v1"
CALIBRATION_RUN_ID = "h5-run-1"


def candidate_identity(task_id: str) -> tuple[str, str]:
    """A deterministic (candidate_id, candidate_sha256) pair for ``task_id``."""
    candidate_id = f"cand-{task_id}"
    candidate_sha256 = hashlib.sha256(f"candidate-source-for-{task_id}".encode()).hexdigest()
    return candidate_id, candidate_sha256


def reference_case_checksum(task_id: str) -> str:
    """A deterministic reference-case checksum for ``task_id``."""
    return hashlib.sha256(f"reference-cases-for-{task_id}".encode()).hexdigest()


def full_run_context(**overrides: object) -> ReferenceRunContext:
    """A synthetic full-profile ReferenceRunContext, any field overridable."""
    fields: dict[str, object] = {
        "experiment_run_id": "exp-1",
        "optimization_run_id": "opt-1",
        "optimization_config_sha256": CONFIG_SHA256,
        "portfolio_frozen_at": "2026-07-01T00:00:00Z",
        "portfolio_selection_rule": "best_of_run",
        "evaluator_version": EVALUATOR_VERSION_FULL,
        "dataset_version": DATASET_VERSION,
        "partition_version": PARTITION_VERSION,
        "execution_profile_id": EXECUTION_PROFILE_ID_FULL,
        "comparison_profile_version": COMPARISON_PROFILE_VERSION,
        "execution_protocol_version": EXECUTION_PROTOCOL_VERSION,
        "dataset_checksum": DATASET_CHECKSUM,
        "task_manifest_checksum": TASK_MANIFEST_CHECKSUM,
    }
    fields.update(overrides)
    return ReferenceRunContext(**fields)  # type: ignore[arg-type]


def candidate_set_entries(count: int = REQUIRED_TASK_COUNT) -> tuple[CandidateSetEntry, ...]:
    """``count`` synthetic candidate-set entries, sorted by task_id."""
    entries = []
    for i in range(count):
        task_id = f"HumanEval/{i}"
        candidate_id, candidate_sha256 = candidate_identity(task_id)
        entries.append(
            CandidateSetEntry(
                task_id=task_id, candidate_id=candidate_id, candidate_sha256=candidate_sha256
            )
        )
    return tuple(sorted(entries, key=lambda entry: entry.task_id))


def candidate_set_manifest(
    entries: tuple[CandidateSetEntry, ...] | None = None, **overrides: object
) -> ReferenceValidationCandidateSetManifest:
    """A real, self-checksummed 164-entry candidate-set manifest."""
    fields: dict[str, object] = {
        "manifest_schema_version": REFERENCE_VALIDATION_CANDIDATE_SET_MANIFEST_SCHEMA_VERSION,
        "algorithm_version": REFERENCE_VALIDATION_CANDIDATE_SET_ALGORITHM_VERSION,
        "task_manifest_id": "reference-validation-composite-manifest",
        "task_manifest_checksum": TASK_MANIFEST_CHECKSUM,
        "selection_provenance_sha256": SELECTION_PROVENANCE_SHA256,
        "entries": entries if entries is not None else candidate_set_entries(),
    }
    fields.update(overrides)
    return ReferenceValidationCandidateSetManifest(**fields)  # type: ignore[arg-type]


def task_result(
    task_id: str,
    context: ReferenceRunContext,
    **overrides: object,
) -> ReferenceTaskResult:
    """A single, valid (q_ref_task=1.0) synthetic task result, any field
    overridable."""
    candidate_id, candidate_sha256 = candidate_identity(task_id)
    fields: dict[str, object] = {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "candidate_sha256": candidate_sha256,
        "context": context,
        "status": MeasurementStatus.VALID,
        "q_ref_task": 1.0,
        "reference_case_total": 5,
        "reference_case_pass_count": 5,
        "first_failure_category": FailureCategory.NONE,
        "oracle_version": ORACLE_VERSION,
        "reference_case_checksum": reference_case_checksum(task_id),
        "evaluated_at": "2026-07-01T00:00:01Z",
        "duration_seconds": 0.25,
    }
    fields.update(overrides)
    return ReferenceTaskResult(**fields)  # type: ignore[arg-type]


def valid_task_results(
    context: ReferenceRunContext | None = None,
    count: int = REQUIRED_TASK_COUNT,
) -> tuple[ReferenceTaskResult, ...]:
    """``count`` valid task results, sorted by task_id (canonical order)."""
    ctx = context or full_run_context()
    results = [task_result(f"HumanEval/{i}", ctx) for i in range(count)]
    return tuple(sorted(results, key=lambda result: result.task_id))


def replace_result(
    results: tuple[ReferenceTaskResult, ...],
    task_id: str,
    context: ReferenceRunContext,
    **overrides: object,
) -> tuple[ReferenceTaskResult, ...]:
    """Replace the result for ``task_id`` in place, by identity rather than
    position (task_id string order does not match numeric order)."""
    index = next(i for i, result in enumerate(results) if result.task_id == task_id)
    replacement = task_result(task_id, context, **overrides)
    return results[:index] + (replacement,) + results[index + 1 :]


def staging_identity(
    manifest: ReferenceValidationCandidateSetManifest, **overrides: object
) -> H5StagingIdentity:
    """The frozen staging identity matching ``manifest`` and the default
    full-profile run identity."""
    fields: dict[str, object] = {
        "calibration_run_id": CALIBRATION_RUN_ID,
        "execution_profile_id": EXECUTION_PROFILE_ID_FULL,
        "evaluator_version": EVALUATOR_VERSION_FULL,
        "execution_protocol_version": EXECUTION_PROTOCOL_VERSION,
        "dataset_version": DATASET_VERSION,
        "dataset_checksum": DATASET_CHECKSUM,
        "partition_version": PARTITION_VERSION,
        "task_manifest_checksum": TASK_MANIFEST_CHECKSUM,
        "oracle_version": ORACLE_VERSION,
        "comparison_profile_version": COMPARISON_PROFILE_VERSION,
        "candidate_set_manifest_checksum": manifest.manifest_checksum,
    }
    fields.update(overrides)
    return H5StagingIdentity(**fields)  # type: ignore[arg-type]


def _telemetry_collection_policy(**overrides: object) -> TelemetryCollectionPolicy:
    fields: dict[str, object] = {
        "telemetry_collection_profile_id": "megb-03h5-telemetry-profile",
        "telemetry_collection_profile_version": "v1",
        "collector_selection_policy_id": "megb-03h5-collector-selection-policy",
        "collector_selection_policy_version": "v1",
        "requested_metrics": ("peak_memory_bytes", "peak_process_count"),
        "preferred_method_order": (
            CollectorMethod.CGROUP_V2_MEMORY_PEAK,
            CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY,
        ),
        "configured_sampling_intervals_sec": (("peak_memory_bytes", 0.05),),
    }
    fields.update(overrides)
    return TelemetryCollectionPolicy(**fields)  # type: ignore[arg-type]


def _host_runtime_context(**overrides: object) -> HostRuntimeContext:
    fields: dict[str, object] = {
        "os_family": "Linux",
        "architecture": "x86_64",
        "kernel_release": "6.8.0-fake",
        "docker_server_version": "27.0.0",
        "docker_server_os": "linux",
        "docker_server_architecture": "x86_64",
        "cgroup_version": "v2",
        "cgroup_mode": "systemd",
        "docker_desktop": False,
        "rootless": False,
    }
    fields.update(overrides)
    return HostRuntimeContext(**fields)  # type: ignore[arg-type]


def _not_applicable_provenance(metric_id: str) -> CollectorMethodProvenance:
    """A metric that simply does not apply to this invocation -- distinct
    from NOT_YET_INSTRUMENTED, and release-ready (see
    require_release_ready_stage)."""
    return CollectorMethodProvenance(
        metric_id=metric_id,
        collector_implementation_id="not_applicable",
        collector_implementation_version="not_applicable/v1",
        selected_method=CollectorMethod.UNAVAILABLE_WITHOUT_CONTAMINATION,
        selected_method_version="not_applicable/v1",
        interface_family="not_applicable",
        configured_sampling_interval_sec=None,
        actual_sample_count=0,
        measurement_quality=None,
        selection_disposition=MetricCollectionDisposition.NO_METHOD_AVAILABLE,
        terminal_coverage=TerminalCoverageState.TERMINAL_READ_NOT_APPLICABLE,
        unavailability_or_failure_reason=TelemetryUnavailableReason.NOT_APPLICABLE,
    )


def calibration_context(**overrides: object) -> CalibrationRunContext:
    """The H.5-stage CalibrationRunContext matching the default identity."""
    fields: dict[str, object] = {
        "calibration_schema_version": CALIBRATION_SCHEMA_VERSION,
        "stage": CalibrationStage.H5,
        "calibration_run_id": CALIBRATION_RUN_ID,
        "execution_profile_id": EXECUTION_PROFILE_ID_FULL,
        "evaluator_version": EVALUATOR_VERSION_FULL,
        "execution_protocol_version": EXECUTION_PROTOCOL_VERSION,
        "dataset_version": DATASET_VERSION,
        "dataset_checksum": DATASET_CHECKSUM,
        "partition_version": PARTITION_VERSION,
        "oracle_version": ORACLE_VERSION,
        "comparison_profile_version": COMPARISON_PROFILE_VERSION,
        "task_manifest_checksum": TASK_MANIFEST_CHECKSUM,
        "telemetry_collection_policy": _telemetry_collection_policy(),
        "host_runtime_context": _host_runtime_context(),
    }
    fields.update(overrides)
    return CalibrationRunContext(**fields)  # type: ignore[arg-type]


def invocation_record(
    result: ReferenceTaskResult,
    context: CalibrationRunContext,
    attempt_id: int = 1,
    replicate_id: int = 0,
) -> CalibrationInvocationRecord:
    """One synthetic, release-ready (never NOT_YET_INSTRUMENTED) invocation
    record contributing to ``result``."""
    return CalibrationInvocationRecord(
        calibration_schema_version=CALIBRATION_SCHEMA_VERSION,
        context=context,
        task_id=result.task_id,
        candidate_sha256=result.candidate_sha256,
        reference_case_checksum=result.reference_case_checksum,
        case_ordinal=0,
        task_evaluation_replicate_id=replicate_id,
        attempt_id=attempt_id,
        invocation_id=f"{result.task_id}-attempt-{attempt_id}",
        invoked_at="2026-07-01T00:00:00Z",
        execution_status=ExecutionStatus.COMPLETED,
        measurement_status=result.status,
        first_failure_category=result.first_failure_category,
        candidate_wall_time_sec=None,
        candidate_wall_time_quality=None,
        candidate_wall_time_unavailable_reason=TelemetryUnavailableReason.NOT_APPLICABLE,
        controller_wall_time_sec=0.01,
        request_bytes=64,
        observed_response_bytes=None,
        observed_response_quality=None,
        observed_response_unavailable_reason=TelemetryUnavailableReason.NOT_APPLICABLE,
        peak_memory_bytes=None,
        peak_memory_quality=None,
        peak_memory_unavailable_reason=TelemetryUnavailableReason.NOT_APPLICABLE,
        peak_memory_provenance=_not_applicable_provenance("peak_memory_bytes"),
        peak_process_count=None,
        peak_process_quality=None,
        peak_process_unavailable_reason=TelemetryUnavailableReason.NOT_APPLICABLE,
        peak_process_provenance=_not_applicable_provenance("peak_process_count"),
        exit_code=0,
        terminating_signal=None,
        backend_id="fake",
        backend_version="1",
        runner_image_digest="sha256:fake",
    )


def task_evaluation_record(
    result: ReferenceTaskResult,
    context: CalibrationRunContext,
    invocations: tuple[CalibrationInvocationRecord, ...],
    replicate_id: int = 0,
    superseded: bool = False,
) -> CalibrationTaskEvaluationRecord:
    """One reconciling CalibrationTaskEvaluationRecord for ``result``,
    referencing ``invocations`` as its contributing invocation records."""
    return CalibrationTaskEvaluationRecord(
        calibration_schema_version=CALIBRATION_SCHEMA_VERSION,
        context=context,
        task_id=result.task_id,
        candidate_sha256=result.candidate_sha256,
        reference_case_checksum=result.reference_case_checksum,
        task_evaluation_replicate_id=replicate_id,
        measurement_status=result.status,
        q_ref_task=result.q_ref_task,
        first_failure_category=result.first_failure_category,
        reference_case_total=result.reference_case_total,
        reference_case_pass_count=result.reference_case_pass_count,
        work_item_disposition=_disposition_for(result),
        contributing_invocation_ids=tuple(inv.invocation_id for inv in invocations),
        contributing_invocation_content_checksums=tuple(
            inv.record_checksum for inv in invocations
        ),
        evaluated_at=result.evaluated_at,
        superseded=superseded,
    )


def _disposition_for(result: ReferenceTaskResult) -> WorkItemDisposition:
    return (
        WorkItemDisposition.EXECUTED_VALID
        if result.status == MeasurementStatus.VALID
        else WorkItemDisposition.EXECUTED_INVALID
    )


def full_trace_for_results(
    context: CalibrationRunContext,
    task_results: tuple[ReferenceTaskResult, ...],
) -> tuple[tuple[CalibrationInvocationRecord, ...], tuple[CalibrationTaskEvaluationRecord, ...]]:
    """Build one contributing invocation record plus one reconciling
    task-evaluation record per ``task_results`` entry -- a complete,
    release-ready, reconciling H.5 calibration trace."""
    invocations: list[CalibrationInvocationRecord] = []
    task_evaluations: list[CalibrationTaskEvaluationRecord] = []
    for result in task_results:
        inv = invocation_record(result, context)
        invocations.append(inv)
        task_evaluations.append(task_evaluation_record(result, context, (inv,)))
    return tuple(invocations), tuple(task_evaluations)
