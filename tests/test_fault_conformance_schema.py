"""MEGB-03H.2C.3B.2B.3: offline tests for the safe fault-conformance
report schema. Synthetic fixtures only."""

import pytest

from src.distributed.fault_conformance import (
    FAULT_CONFORMANCE_REPORT_SCHEMA_VERSION,
    ConformanceEntry,
    FaultConformanceReport,
    FaultPointId,
    InvalidFaultConformanceReportError,
    InvariantId,
    ReadinessClassification,
    build_fault_conformance_report,
    fault_conformance_report_from_dict,
    fault_conformance_report_to_dict,
    render_markdown,
)

_PLAN_SHA256 = "9bf39c6bae0b43e3ce0807d9ca1bd6f08f892b7356f563c73e75376b7bbd9891"
_PLAN_BLOB = "b037ed68292ed06fc226453ed07130992783db6b"


def _entry(**overrides: object) -> ConformanceEntry:
    fields: dict[str, object] = {
        "fault_point": FaultPointId.A1_BEFORE_BUDGET_RESERVATION,
        "invariant": InvariantId.I11_EVERY_ITEM_ENDS_DEFINED_DISPOSITION,
        "passed": True,
        "attempt_count": 1,
    }
    fields.update(overrides)
    return ConformanceEntry(**fields)  # type: ignore[arg-type]


def test_conformance_entry_rejects_non_positive_attempt_count() -> None:
    """Test conformance entry rejects non positive attempt count."""
    with pytest.raises(InvalidFaultConformanceReportError):
        _entry(attempt_count=0)


def test_conformance_entry_rejects_wrong_enum_types() -> None:
    """Test conformance entry rejects wrong enum types."""
    with pytest.raises(InvalidFaultConformanceReportError):
        ConformanceEntry(
            fault_point="not-a-fault-point",  # type: ignore[arg-type]
            invariant=InvariantId.I1_AT_MOST_ONE_COMMITTED_RESULT,
            passed=True,
            attempt_count=1,
        )


def test_build_report_all_passed_is_ready() -> None:
    """Test a report built from all-passed entries reports readiness
    IN_PROCESS_RECOVERY_READY_FOR_B2C, never independently settable."""
    report = build_fault_conformance_report(
        [_entry(), _entry(fault_point=FaultPointId.W1_AFTER_DELIVERY_BEFORE_LEASE)],
        plan_sha256=_PLAN_SHA256,
        plan_git_blob_sha1=_PLAN_BLOB,
    )
    assert report.readiness == ReadinessClassification.IN_PROCESS_RECOVERY_READY_FOR_B2C
    assert report.passed_count == 2
    assert report.failed_count == 0
    assert report.total_attempts == 2
    assert len(report.report_checksum) == 64


def test_build_report_any_failure_is_blocked() -> None:
    """Test a report built with any failing entry reports
    BLOCKED_IN_PROCESS_RECOVERY."""
    failing_entry = _entry(
        fault_point=FaultPointId.W4_EXECUTOR_NON_RETRYABLE_FAILURE, passed=False
    )
    report = build_fault_conformance_report(
        [_entry(), failing_entry],
        plan_sha256=_PLAN_SHA256,
        plan_git_blob_sha1=_PLAN_BLOB,
    )
    assert report.readiness == ReadinessClassification.BLOCKED_IN_PROCESS_RECOVERY
    assert report.failed_count == 1


def test_report_rejects_readiness_inconsistent_with_failed_count() -> None:
    """Test that readiness can never be constructed inconsistently with
    the entries' own pass/fail tally -- readiness is always derived, never
    independently asserted."""
    with pytest.raises(InvalidFaultConformanceReportError):
        FaultConformanceReport(
            schema_version=FAULT_CONFORMANCE_REPORT_SCHEMA_VERSION,
            plan_sha256=_PLAN_SHA256,
            plan_git_blob_sha1=_PLAN_BLOB,
            entries=(_entry(passed=False),),
            total_attempts=1,
            passed_count=0,
            failed_count=1,
            readiness=ReadinessClassification.IN_PROCESS_RECOVERY_READY_FOR_B2C,
        )


def test_report_rejects_checksum_tampering() -> None:
    """Test report rejects checksum tampering."""
    report = build_fault_conformance_report(
        [_entry()], plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
    )
    data = fault_conformance_report_to_dict(report)
    data["report_checksum"] = "0" * 64
    with pytest.raises(InvalidFaultConformanceReportError):
        fault_conformance_report_from_dict(data)


def test_report_round_trips() -> None:
    """Test report round trips through to_dict/from_dict."""
    report = build_fault_conformance_report(
        [_entry(), _entry(fault_point=FaultPointId.R1_CONCURRENCY_ONE, attempt_count=15)],
        plan_sha256=_PLAN_SHA256,
        plan_git_blob_sha1=_PLAN_BLOB,
    )
    data = fault_conformance_report_to_dict(report)
    rebuilt = fault_conformance_report_from_dict(data)
    assert rebuilt == report


def test_render_markdown_contains_readiness_and_matrix_rows() -> None:
    """Test render_markdown contains readiness and one row per entry."""
    report = build_fault_conformance_report(
        [_entry(), _entry(fault_point=FaultPointId.C1_AUDIT_SINK_FAILURE)],
        plan_sha256=_PLAN_SHA256,
        plan_git_blob_sha1=_PLAN_BLOB,
    )
    rendered = render_markdown(report)
    assert "IN_PROCESS_RECOVERY_READY_FOR_B2C" in rendered
    assert "A1_BEFORE_BUDGET_RESERVATION" in rendered
    assert "C1_AUDIT_SINK_FAILURE" in rendered
    assert "no durable-process" in rendered


def test_report_entries_are_sorted_deterministically() -> None:
    """Test build_fault_conformance_report sorts entries deterministically
    by (fault_point, invariant) regardless of input order -- required for
    byte-for-byte deterministic report regeneration."""
    first = build_fault_conformance_report(
        [
            _entry(fault_point=FaultPointId.W9_AFTER_ACK_BEFORE_RETURN),
            _entry(fault_point=FaultPointId.A1_BEFORE_BUDGET_RESERVATION),
        ],
        plan_sha256=_PLAN_SHA256,
        plan_git_blob_sha1=_PLAN_BLOB,
    )
    second = build_fault_conformance_report(
        [
            _entry(fault_point=FaultPointId.A1_BEFORE_BUDGET_RESERVATION),
            _entry(fault_point=FaultPointId.W9_AFTER_ACK_BEFORE_RETURN),
        ],
        plan_sha256=_PLAN_SHA256,
        plan_git_blob_sha1=_PLAN_BLOB,
    )
    assert first == second
    assert first.report_checksum == second.report_checksum
