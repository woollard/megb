"""MEGB-03H.2A tests: calibration record schemas, taxonomy, checksums,
supersession, and the safe summary-report projection.

Synthetic fixtures only -- no privileged artifact, no Docker, no
canonical/candidate execution anywhere in this module.
"""

import dataclasses

import pytest

from src.evaluators.schema import FailureCategory
from src.reference.calibration_schema import (
    CalibrationReconciliationError,
    CalibrationStage,
    InvalidCalibrationRecordError,
    MeasurementQuality,
    TelemetryUnavailableReason,
    UnsupportedCalibrationSchemaVersionError,
    calibration_invocation_record_from_dict,
    calibration_invocation_record_to_dict,
    calibration_run_context_from_dict,
    calibration_run_context_to_dict,
    calibration_task_evaluation_record_from_dict,
    calibration_task_evaluation_record_to_dict,
    reconcile_all,
    reconcile_task_evaluation,
)
from src.reference.calibration_summary import (
    CALIBRATION_SUMMARY_REPORT_FIELD_NAMES,
    CALIBRATION_SUMMARY_REPORT_SCHEMA_VERSION,
    CalibrationSummaryReport,
    build_calibration_summary_report,
    incomplete_task_evaluations,
)
from src.reference.result_schema import MeasurementStatus
from tests._calibration_fixtures import (
    OTHER_CANDIDATE_SHA256,
    make_context,
    make_invocation,
    make_task_evaluation,
)


# ---------------------------------------------------------------------------
# 1. Record construction and validation
# ---------------------------------------------------------------------------


def test_valid_context_invocation_and_task_evaluation_construct() -> None:
    """Valid context invocation and task evaluation construct."""
    context = make_context()
    invocation = make_invocation(context=context)
    task_evaluation = make_task_evaluation(context=context)
    assert context.stage == CalibrationStage.H3
    assert invocation.task_id == "HumanEval/41"
    assert task_evaluation.q_ref_task == 1.0


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"task_id": ""}, "nonempty string"),
        ({"candidate_sha256": "not-hex"}, "sha256"),
        ({"case_ordinal": -1}, "non-negative int"),
        ({"attempt_id": 0}, "attempt_id"),
        ({"execution_status": "COMPLETED"}, "ExecutionStatus"),
        ({"measurement_status": "VALID"}, "MeasurementStatus"),
        ({"first_failure_category": "NONE"}, "FailureCategory"),
        ({"controller_wall_time_sec": -1.0}, "non-negative number"),
        ({"request_bytes": -1}, "non-negative int"),
        ({"terminating_signal": -1}, "terminating_signal"),
    ],
)
def test_invalid_invocation_fields_rejected(overrides: dict[str, object], match: str) -> None:
    """Invalid invocation fields rejected."""
    with pytest.raises(InvalidCalibrationRecordError, match=match):
        make_invocation(**overrides)


def test_invalid_task_evaluation_pass_count_exceeds_total_rejected() -> None:
    """Invalid task evaluation pass count exceeds total rejected."""
    with pytest.raises(InvalidCalibrationRecordError, match="exceeds"):
        make_task_evaluation(reference_case_total=1, reference_case_pass_count=2)


def test_quality_present_requires_no_unavailable_reason() -> None:
    """Quality present requires no unavailable reason."""
    with pytest.raises(InvalidCalibrationRecordError, match="unavailable_reason"):
        make_invocation(
            candidate_wall_time_sec=0.5,
            candidate_wall_time_quality=MeasurementQuality.EXACT,
            candidate_wall_time_unavailable_reason=TelemetryUnavailableReason.NEVER_STARTED,
        )


def test_quality_none_requires_unavailable_reason() -> None:
    """Quality none requires unavailable reason."""
    with pytest.raises(InvalidCalibrationRecordError, match="TelemetryUnavailableReason"):
        make_invocation(
            candidate_wall_time_sec=None,
            candidate_wall_time_quality=None,
            candidate_wall_time_unavailable_reason=None,
        )


def test_value_present_requires_quality() -> None:
    """Value present requires quality."""
    with pytest.raises(InvalidCalibrationRecordError, match="MeasurementQuality"):
        make_invocation(
            observed_response_bytes=10,
            observed_response_quality=None,
            observed_response_unavailable_reason=None,
        )


def test_valid_measurement_requires_binary_q_ref_task() -> None:
    """Valid measurement requires binary q ref task."""
    with pytest.raises(InvalidCalibrationRecordError, match="q_ref_task"):
        make_task_evaluation(measurement_status=MeasurementStatus.VALID, q_ref_task=0.5)


def test_non_valid_measurement_requires_none_q_ref_task() -> None:
    """Non valid measurement requires none q ref task."""
    with pytest.raises(InvalidCalibrationRecordError, match="q_ref_task"):
        make_task_evaluation(measurement_status=MeasurementStatus.INCOMPLETE, q_ref_task=1.0)


# ---------------------------------------------------------------------------
# 2. Schema-version rejection
# ---------------------------------------------------------------------------


def test_context_schema_version_rejection() -> None:
    """Context schema version rejection."""
    with pytest.raises(UnsupportedCalibrationSchemaVersionError):
        make_context(calibration_schema_version="megb-03h-calibration-record-v0")


def test_invocation_schema_version_rejection() -> None:
    """Invocation schema version rejection."""
    with pytest.raises(UnsupportedCalibrationSchemaVersionError):
        make_invocation(calibration_schema_version="megb-03h-calibration-record-v0")


def test_task_evaluation_schema_version_rejection() -> None:
    """Task evaluation schema version rejection."""
    with pytest.raises(UnsupportedCalibrationSchemaVersionError):
        make_task_evaluation(calibration_schema_version="megb-03h-calibration-record-v0")


def test_summary_report_schema_version_rejection() -> None:
    """Summary report schema version rejection."""
    with pytest.raises(UnsupportedCalibrationSchemaVersionError):
        CalibrationSummaryReport(
            summary_schema_version="megb-03h-calibration-summary-report-v0",
            stage=CalibrationStage.H3,
            calibration_run_id="run-1",
            generated_at="2026-08-03T00:00:00Z",
            total_invocation_records=0,
            total_task_evaluation_records=0,
            execution_status_counts={},
            measurement_status_counts={},
            work_item_disposition_counts={},
            candidate_wall_time_quality_counts={},
            observed_response_quality_counts={},
            peak_memory_quality_counts={},
            peak_process_quality_counts={},
            per_task_case_counts={},
        )


# ---------------------------------------------------------------------------
# 3. Checksum tampering
# ---------------------------------------------------------------------------


def test_context_checksum_tampering_detected() -> None:
    """Context checksum tampering detected."""
    context = make_context()
    payload = calibration_run_context_to_dict(context)
    payload["context_checksum"] = "0" * 64
    with pytest.raises(InvalidCalibrationRecordError, match="context_checksum"):
        calibration_run_context_from_dict(payload)


def test_invocation_record_checksum_tampering_detected() -> None:
    """Invocation record checksum tampering detected."""
    invocation = make_invocation()
    payload = calibration_invocation_record_to_dict(invocation)
    payload["task_id"] = "HumanEval/999"  # mutate content without recomputing checksum
    with pytest.raises(InvalidCalibrationRecordError, match="record_checksum"):
        calibration_invocation_record_from_dict(payload)


def test_task_evaluation_record_checksum_tampering_detected() -> None:
    """Task evaluation record checksum tampering detected."""
    task_evaluation = make_task_evaluation()
    payload = calibration_task_evaluation_record_to_dict(task_evaluation)
    payload["q_ref_task"] = 0.0
    payload["first_failure_category"] = FailureCategory.WRONG_OUTPUT.value
    payload["reference_case_pass_count"] = 0
    with pytest.raises(InvalidCalibrationRecordError, match="record_checksum"):
        calibration_task_evaluation_record_from_dict(payload)


def test_contributing_invocations_checksum_tampering_detected() -> None:
    """Contributing invocations checksum tampering detected."""
    task_evaluation = make_task_evaluation()
    payload = calibration_task_evaluation_record_to_dict(task_evaluation)
    payload["contributing_invocations_checksum"] = "0" * 64
    with pytest.raises(InvalidCalibrationRecordError, match="contributing_invocations_checksum"):
        calibration_task_evaluation_record_from_dict(payload)


# ---------------------------------------------------------------------------
# 4. Contributor-set mismatch / 6. task/invocation context mismatch
# ---------------------------------------------------------------------------


def test_reconcile_missing_contributor_raises() -> None:
    """Reconcile missing contributor raises."""
    task_evaluation = make_task_evaluation(
        contributing_invocation_ids=("inv-1", "inv-missing"),
        contributing_invocation_content_checksums=("0" * 64, "1" * 64),
    )
    invocation = make_invocation()
    with pytest.raises(CalibrationReconciliationError, match="inv-missing"):
        reconcile_task_evaluation(task_evaluation, {"inv-1": invocation})


def test_reconcile_context_mismatch_raises() -> None:
    """Reconcile context mismatch raises."""
    task_evaluation = make_task_evaluation()
    other_context = make_context(calibration_run_id="run-2")
    invocation = make_invocation(context=other_context)
    with pytest.raises(CalibrationReconciliationError, match="different calibration context"):
        reconcile_task_evaluation(task_evaluation, {"inv-1": invocation})


def test_reconcile_task_id_mismatch_raises() -> None:
    """Reconcile task id mismatch raises."""
    task_evaluation = make_task_evaluation()
    invocation = make_invocation(task_id="HumanEval/999")
    with pytest.raises(CalibrationReconciliationError, match="task_id"):
        reconcile_task_evaluation(task_evaluation, {"inv-1": invocation})


def test_reconcile_candidate_mismatch_raises() -> None:
    """Reconcile candidate mismatch raises."""
    task_evaluation = make_task_evaluation()
    invocation = make_invocation(candidate_sha256=OTHER_CANDIDATE_SHA256)
    with pytest.raises(CalibrationReconciliationError, match="candidate_sha256"):
        reconcile_task_evaluation(task_evaluation, {"inv-1": invocation})


def test_reconcile_replicate_mismatch_raises() -> None:
    """Reconcile replicate mismatch raises."""
    task_evaluation = make_task_evaluation(task_evaluation_replicate_id=0)
    invocation = make_invocation(task_evaluation_replicate_id=1)
    with pytest.raises(CalibrationReconciliationError, match="task_evaluation_replicate_id"):
        reconcile_task_evaluation(task_evaluation, {"inv-1": invocation})


def test_reconcile_all_succeeds_for_consistent_records() -> None:
    """Reconcile all succeeds for consistent records."""
    invocation = make_invocation()
    task_evaluation = make_task_evaluation()
    reconcile_all([invocation], [task_evaluation])


# ---------------------------------------------------------------------------
# 5. Duplicate identities
# ---------------------------------------------------------------------------


def test_duplicate_contributing_invocation_ids_rejected() -> None:
    """Duplicate contributing invocation ids rejected."""
    with pytest.raises(InvalidCalibrationRecordError, match="duplicate"):
        make_task_evaluation(
            contributing_invocation_ids=("inv-1", "inv-1"),
            contributing_invocation_content_checksums=("0" * 64, "1" * 64),
        )


# ---------------------------------------------------------------------------
# 7. Superseded-record exclusion / 8. incomplete task-evaluation detection
# ---------------------------------------------------------------------------


def test_superseded_records_excluded_from_summary() -> None:
    """Superseded records excluded from summary."""
    context = make_context()
    active = make_invocation(context=context, invocation_id="inv-active")
    superseded = make_invocation(
        context=context, invocation_id="inv-superseded", superseded=True
    )
    report = build_calibration_summary_report(
        stage=CalibrationStage.H3,
        calibration_run_id="run-1",
        generated_at="2026-08-03T00:00:02Z",
        invocation_records=[active, superseded],
        task_evaluation_records=[],
    )
    assert report.total_invocation_records == 1
    assert report.per_task_case_counts == {"HumanEval/41": 1}


def test_incomplete_task_evaluations_detected_and_superseded_excluded() -> None:
    """Incomplete task evaluations detected and superseded excluded."""
    incomplete = make_task_evaluation(
        measurement_status=MeasurementStatus.INCOMPLETE,
        q_ref_task=None,
        contributing_invocation_ids=(),
        contributing_invocation_content_checksums=(),
    )
    superseded_incomplete = make_task_evaluation(
        measurement_status=MeasurementStatus.INCOMPLETE,
        q_ref_task=None,
        contributing_invocation_ids=(),
        contributing_invocation_content_checksums=(),
        superseded=True,
    )
    complete = make_task_evaluation()
    result = incomplete_task_evaluations([incomplete, superseded_incomplete, complete])
    assert result == (incomplete,)


# ---------------------------------------------------------------------------
# 9. Deterministic round trips
# ---------------------------------------------------------------------------


def test_context_round_trip_is_deterministic() -> None:
    """Context round trip is deterministic."""
    context = make_context()
    restored = calibration_run_context_from_dict(calibration_run_context_to_dict(context))
    assert restored == context


def test_invocation_round_trip_is_deterministic() -> None:
    """Invocation round trip is deterministic."""
    invocation = make_invocation()
    restored = calibration_invocation_record_from_dict(
        calibration_invocation_record_to_dict(invocation)
    )
    assert restored == invocation


def test_task_evaluation_round_trip_is_deterministic() -> None:
    """Task evaluation round trip is deterministic."""
    task_evaluation = make_task_evaluation()
    restored = calibration_task_evaluation_record_from_dict(
        calibration_task_evaluation_record_to_dict(task_evaluation)
    )
    assert restored == task_evaluation


def test_repeated_serialization_is_byte_identical() -> None:
    """Repeated serialization is byte identical."""
    invocation = make_invocation()
    first = calibration_invocation_record_to_dict(invocation)
    second = calibration_invocation_record_to_dict(invocation)
    assert first == second


# ---------------------------------------------------------------------------
# 15. Safe-summary leakage checks
# ---------------------------------------------------------------------------

_FORBIDDEN_SUBSTRINGS = (
    "case_id",
    "case_ordinal",
    "candidate_code",
    "candidate_source",
    "expected_output",
    "args",
    "kwargs",
    "stdout",
    "stderr",
    "env",
    "path",
    "input",
)


def test_summary_report_field_names_allowlist_has_no_forbidden_content() -> None:
    """Summary report field names allowlist has no forbidden content."""
    for field_name in CALIBRATION_SUMMARY_REPORT_FIELD_NAMES:
        lowered = field_name.lower()
        for forbidden in _FORBIDDEN_SUBSTRINGS:
            assert forbidden not in lowered, (
                f"summary report field {field_name!r} appears to carry forbidden "
                f"content ({forbidden!r})"
            )


def test_summary_report_fields_match_dataclass_definition() -> None:
    """Summary report fields match dataclass definition."""
    declared = frozenset(f.name for f in dataclasses.fields(CalibrationSummaryReport))
    assert declared == CALIBRATION_SUMMARY_REPORT_FIELD_NAMES


def test_build_summary_report_never_carries_case_level_detail() -> None:
    """Build summary report never carries case level detail."""
    invocation = make_invocation()
    task_evaluation = make_task_evaluation()
    report = build_calibration_summary_report(
        stage=CalibrationStage.H3,
        calibration_run_id="run-1",
        generated_at="2026-08-03T00:00:03Z",
        invocation_records=[invocation],
        task_evaluation_records=[task_evaluation],
    )
    serialized = repr(report)
    assert invocation.invocation_id not in serialized
    assert invocation.candidate_sha256 not in serialized
    assert "case_ordinal" not in serialized
    assert CALIBRATION_SUMMARY_REPORT_SCHEMA_VERSION in serialized
