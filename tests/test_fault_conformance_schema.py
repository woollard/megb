"""MEGB-03H.2C.3B.2B.3 report-integrity correction: offline tests for the
safe fault-conformance report schema. Synthetic fixtures only.

A valid :class:`FaultConformanceReport` must now cover every one of the
37 frozen ``FaultPointId`` members and all 13 ``InvariantId`` members
with no duplicate (fault_point, invariant) pair -- enforced by the
report's own constructor, not merely by test-writing discipline. Tests
below therefore build a full, synthetic 37-entry baseline via
``_complete_entries()`` (one entry per fault point, invariants assigned
round-robin so all 13 also appear, since 37 > 13) and mutate exactly one
axis at a time to exercise each rejection path."""

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

_ALL_FAULT_POINTS = list(FaultPointId)
_ALL_INVARIANTS = list(InvariantId)


def _entry(**overrides: object) -> ConformanceEntry:
    fields: dict[str, object] = {
        "fault_point": FaultPointId.A1_BEFORE_BUDGET_RESERVATION,
        "invariant": InvariantId.I11_EVERY_ITEM_ENDS_DEFINED_DISPOSITION,
        "passed": True,
        "attempt_count": 1,
    }
    fields.update(overrides)
    return ConformanceEntry(**fields)  # type: ignore[arg-type]


def _complete_entries(*, failing: FaultPointId | None = None) -> list[ConformanceEntry]:
    """One entry per every frozen fault point (all 37), with invariants
    assigned round-robin so all 13 invariants are also covered -- the
    minimal entry set the report's own constructor now accepts. If
    ``failing`` is given, that one fault point's entry is recorded as
    failed; every other entry passes."""
    return [
        ConformanceEntry(
            fault_point=fault_point,
            invariant=_ALL_INVARIANTS[index % len(_ALL_INVARIANTS)],
            passed=fault_point != failing,
            attempt_count=1,
        )
        for index, fault_point in enumerate(_ALL_FAULT_POINTS)
    ]


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
    """Test a report built from a complete, all-passed entry set reports
    readiness IN_PROCESS_RECOVERY_READY_FOR_B2C, never independently
    settable."""
    entries = _complete_entries()
    report = build_fault_conformance_report(
        entries, plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
    )
    assert report.readiness == ReadinessClassification.IN_PROCESS_RECOVERY_READY_FOR_B2C
    assert report.passed_count == len(_ALL_FAULT_POINTS)
    assert report.failed_count == 0
    assert report.total_attempts == len(_ALL_FAULT_POINTS)
    assert len(report.report_checksum) == 64


def test_build_report_any_failure_is_blocked() -> None:
    """Test a report built with any failing entry reports
    BLOCKED_IN_PROCESS_RECOVERY -- entries remain otherwise complete, only
    one fault point's own result is flipped to failed."""
    entries = _complete_entries(failing=FaultPointId.W4_EXECUTOR_NON_RETRYABLE_FAILURE)
    report = build_fault_conformance_report(
        entries, plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
    )
    assert report.readiness == ReadinessClassification.BLOCKED_IN_PROCESS_RECOVERY
    assert report.failed_count == 1


def test_report_rejects_readiness_inconsistent_with_failed_count() -> None:
    """Test that readiness can never be constructed inconsistently with
    the entries' own pass/fail tally -- readiness is always derived, never
    independently asserted."""
    entries = tuple(_complete_entries(failing=FaultPointId.W4_EXECUTOR_NON_RETRYABLE_FAILURE))
    with pytest.raises(InvalidFaultConformanceReportError):
        FaultConformanceReport(
            schema_version=FAULT_CONFORMANCE_REPORT_SCHEMA_VERSION,
            plan_sha256=_PLAN_SHA256,
            plan_git_blob_sha1=_PLAN_BLOB,
            entries=entries,
            total_attempts=len(entries),
            passed_count=len(entries) - 1,
            failed_count=1,
            readiness=ReadinessClassification.IN_PROCESS_RECOVERY_READY_FOR_B2C,
        )


def test_report_rejects_missing_fault_point() -> None:
    """Test that a report missing even one of the 37 frozen fault points
    fails to construct -- removing a scenario can never silently produce
    a smaller-but-still-READY report; it must instead abort construction
    entirely."""
    incomplete = tuple(_complete_entries())[:-1]  # drop the last fault point's entry
    with pytest.raises(InvalidFaultConformanceReportError):
        build_fault_conformance_report(
            list(incomplete), plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
        )


def test_report_rejects_missing_invariant() -> None:
    """Test that a report whose entries collectively skip one of the 13
    frozen invariants fails to construct, even if every fault point is
    still present (by recording every entry against the same single
    invariant)."""
    skewed = [
        ConformanceEntry(
            fault_point=fault_point,
            invariant=InvariantId.I1_AT_MOST_ONE_COMMITTED_RESULT,
            passed=True,
            attempt_count=1,
        )
        for fault_point in _ALL_FAULT_POINTS
    ]
    with pytest.raises(InvalidFaultConformanceReportError):
        build_fault_conformance_report(
            skewed, plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
        )


def test_report_rejects_duplicate_fault_point_invariant_pair() -> None:
    """Test that recording the exact same (fault_point, invariant) pair
    twice -- rather than exercising the one missing pair -- fails to
    construct, so a duplicate can never stand in for a distinct,
    unexercised fault point."""
    entries = _complete_entries()
    duplicated = entries[:-1] + [entries[0]]  # replace the last entry with a repeat of the first
    with pytest.raises(InvalidFaultConformanceReportError):
        build_fault_conformance_report(
            duplicated, plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
        )


def test_report_from_dict_rejects_unknown_fault_point() -> None:
    """Test that deserializing a report whose JSON carries a fault_point
    string outside the closed FaultPointId enum raises the module's own
    typed error, not a bare ValueError/KeyError."""
    report = build_fault_conformance_report(
        _complete_entries(), plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
    )
    data = fault_conformance_report_to_dict(report)
    entries: list[dict[str, object]] = data["entries"]  # type: ignore[assignment]
    entries[0]["fault_point"] = "NOT_A_REAL_FAULT_POINT"
    with pytest.raises(InvalidFaultConformanceReportError):
        fault_conformance_report_from_dict(data)


def test_report_from_dict_rejects_non_bool_passed_field() -> None:
    """Test that a tampered JSON carrying a truthy non-bool string for
    'passed' (e.g. the string "false", which Python's own bool() would
    silently coerce to True) is rejected rather than silently flipping
    polarity."""
    report = build_fault_conformance_report(
        _complete_entries(), plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
    )
    data = fault_conformance_report_to_dict(report)
    entries: list[dict[str, object]] = data["entries"]  # type: ignore[assignment]
    entries[0]["passed"] = "false"
    with pytest.raises(InvalidFaultConformanceReportError):
        fault_conformance_report_from_dict(data)


def test_report_rejects_checksum_tampering() -> None:
    """Test report rejects checksum tampering."""
    report = build_fault_conformance_report(
        _complete_entries(), plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
    )
    data = fault_conformance_report_to_dict(report)
    data["report_checksum"] = "0" * 64
    with pytest.raises(InvalidFaultConformanceReportError):
        fault_conformance_report_from_dict(data)


def test_report_round_trips() -> None:
    """Test report round trips through to_dict/from_dict."""
    entries = _complete_entries()
    entries[0] = ConformanceEntry(
        fault_point=entries[0].fault_point,
        invariant=entries[0].invariant,
        passed=entries[0].passed,
        attempt_count=15,
    )
    report = build_fault_conformance_report(
        entries, plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
    )
    data = fault_conformance_report_to_dict(report)
    rebuilt = fault_conformance_report_from_dict(data)
    assert rebuilt == report


def test_render_markdown_contains_readiness_and_matrix_rows() -> None:
    """Test render_markdown contains readiness and one row per entry."""
    report = build_fault_conformance_report(
        _complete_entries(), plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
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
    entries = _complete_entries()
    reversed_entries = list(reversed(entries))
    first = build_fault_conformance_report(
        entries, plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
    )
    second = build_fault_conformance_report(
        reversed_entries, plan_sha256=_PLAN_SHA256, plan_git_blob_sha1=_PLAN_BLOB
    )
    assert first == second
    assert first.report_checksum == second.report_checksum
