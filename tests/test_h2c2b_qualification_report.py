"""MEGB-03H.2C.2B: offline tests for the safe qualification report schema.

Synthetic fixtures only -- no real Docker, no real run.
"""

import dataclasses

import pytest

from src.reference.h2c2b_qualification_report import (
    H2C2B_QUALIFICATION_REPORT_SCHEMA_VERSION,
    QUALIFICATION_REPORT_FIELD_NAMES,
    ConcurrencyOverheadStat,
    H2C2BQualificationReport,
    InvalidQualificationReportError,
    StageProjectionSummary,
    qualification_report_from_dict,
    qualification_report_to_dict,
    render_markdown,
)


def _stat(**overrides: object) -> ConcurrencyOverheadStat:
    defaults: dict[str, object] = {
        "concurrency": 1,
        "pair_count": 8,
        "mean_overhead_ms": 5.0,
        "p99_overhead_ms": 12.0,
    }
    defaults.update(overrides)
    return ConcurrencyOverheadStat(**defaults)  # type: ignore[arg-type]


def _projection(**overrides: object) -> StageProjectionSummary:
    defaults: dict[str, object] = {
        "stage": "H3",
        "scenario": "baseline",
        "projected_seconds": 200.0,
        "hard_ceiling_seconds": 3600.0,
        "within_ceiling": True,
    }
    defaults.update(overrides)
    return StageProjectionSummary(**defaults)  # type: ignore[arg-type]


def make_report(**overrides: object) -> H2C2BQualificationReport:
    """A structurally valid report, fields overridable."""
    fields: dict[str, object] = {
        "schema_version": H2C2B_QUALIFICATION_REPORT_SCHEMA_VERSION,
        "generated_at": "2026-08-03T00:00:00Z",
        "run_identity": "h2c2b-diagnostic-run-1",
        "qualifying": False,
        "plan_sha256": "a" * 64,
        "plan_git_blob_sha1": "b" * 40,
        "harness_version": "megb-03h2c2b-measurement-harness-v1",
        "implementation_commit_sha": "e8d40a2acc8dd33f62ac7a7ce2bb3ec4fe8077e2",
        "implementation_dirty": False,
        "docker_image_id": "sha256:" + "c" * 64,
        "docker_image_provenance_checksum": "d" * 64,
        "host_os_family": "linux",
        "host_architecture": "arm64",
        "host_kernel_release": "25.5.0",
        "host_docker_server_version": "29.1.3",
        "host_cgroup_driver": "cgroupfs",
        "memory_preferred_method": "CGROUP_V2_MEMORY_PEAK",
        "memory_actual_selected_method": "SAMPLED_DOCKER_STATS_MEMORY",
        "memory_selection_disposition": "FALLBACK_METHOD_SELECTED",
        "memory_quality": "BOUNDARY_ONLY",
        "memory_unavailable_reason": "NONE",
        "process_count_preferred_method": "CGROUP_V2_PIDS_PEAK",
        "process_count_actual_selected_method": "SAMPLED_DOCKER_TOP_PROCESS_COUNT",
        "process_count_selection_disposition": "FALLBACK_METHOD_SELECTED",
        "process_count_quality": "NONE",
        "process_count_unavailable_reason": "HOST_TELEMETRY_UNAVAILABLE",
        "late_peak_quality": "BOUNDARY_ONLY",
        "late_peak_terminal_coverage": "TERMINAL_READ_NOT_APPLICABLE",
        "late_peak_value_matches_expected_minimum": True,
        "overhead_by_concurrency": (_stat(),),
        "primary_overhead_gate_ms": 20.9,
        "primary_overhead_gate_passed": True,
        "status_matrix_scenarios_tested": 8,
        "status_matrix_all_statuses_agree": True,
        "status_matrix_all_return_values_agree": True,
        "leftover_containers_found": False,
        "stage_projections": (_projection(),),
        "readiness": "NOT_QUALIFYING_DIAGNOSTIC_PILOT_ONLY",
        "blocking_reasons": (),
    }
    fields.update(overrides)
    return H2C2BQualificationReport(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Construction / round trip
# ---------------------------------------------------------------------------


def test_report_round_trip_is_deterministic() -> None:
    """to_dict/from_dict round trip preserves the report exactly."""
    report = make_report()
    restored = qualification_report_from_dict(qualification_report_to_dict(report))
    assert restored == report


def test_report_self_computes_checksum() -> None:
    """A report constructed with no checksum supplied computes one."""
    report = make_report()
    assert report.report_checksum != ""


# ---------------------------------------------------------------------------
# Checksum tampering
# ---------------------------------------------------------------------------


def test_checksum_tampering_is_detected() -> None:
    """Any field change after serialization is caught on reconstruction."""
    report = make_report()
    payload = qualification_report_to_dict(report)
    payload["primary_overhead_gate_passed"] = not payload["primary_overhead_gate_passed"]
    with pytest.raises(InvalidQualificationReportError, match="report_checksum"):
        qualification_report_from_dict(payload)


def test_nested_overhead_stat_change_alters_the_report_checksum() -> None:
    """A change inside a nested ConcurrencyOverheadStat is not silently
    ignored by the report's own top-level checksum."""
    base = make_report()
    changed = make_report(overhead_by_concurrency=(_stat(mean_overhead_ms=999.0),))
    assert base.report_checksum != changed.report_checksum


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_unknown_schema_version_is_rejected() -> None:
    """A schema_version this module doesn't implement is rejected."""
    with pytest.raises(InvalidQualificationReportError, match="schema_version"):
        make_report(schema_version="megb-03h2c2b-qualification-report-v0")


def test_unknown_readiness_value_is_rejected() -> None:
    """An unrecognized readiness classification is rejected -- never a
    free-text string."""
    with pytest.raises(InvalidQualificationReportError, match="readiness"):
        make_report(readiness="SOMETHING_MADE_UP")


@pytest.mark.parametrize(
    "readiness",
    [
        "TELEMETRY_READY_FOR_MEGB_03H3",
        "BLOCKED_TELEMETRY_OVERHEAD",
        "BLOCKED_NONINTERFERENCE_OR_CLEANUP",
        "BLOCKED_MEASUREMENT_VALIDITY",
        "BLOCKED_EXACT_TELEMETRY_UNAVAILABLE_NATIVE_LINUX_OR_AWS_REQUIRED",
        "BLOCKED_H5_PROJECTION_CEILING",
        "NOT_QUALIFYING_DIAGNOSTIC_PILOT_ONLY",
    ],
)
def test_every_pre_registered_readiness_value_is_accepted(readiness: str) -> None:
    """Every readiness classification named in the frozen plan's §13
    (plus the diagnostic-pilot label) constructs without error."""
    make_report(readiness=readiness)  # does not raise


def test_empty_overhead_by_concurrency_is_rejected() -> None:
    """A report with zero overhead measurements is structurally invalid --
    the primary gate cannot be evaluated without at least one."""
    with pytest.raises(InvalidQualificationReportError, match="overhead_by_concurrency"):
        make_report(overhead_by_concurrency=())


def test_empty_stage_projections_is_rejected() -> None:
    """A report with zero stage projections is structurally invalid."""
    with pytest.raises(InvalidQualificationReportError, match="stage_projections"):
        make_report(stage_projections=())


def test_zero_status_matrix_scenarios_tested_is_rejected() -> None:
    """status_matrix_scenarios_tested must be a real, positive count."""
    with pytest.raises(InvalidQualificationReportError, match="status_matrix_scenarios_tested"):
        make_report(status_matrix_scenarios_tested=0)


def test_concurrency_overhead_stat_rejects_nonpositive_concurrency() -> None:
    """A concurrency level of 0 or negative is structurally invalid."""
    with pytest.raises(InvalidQualificationReportError, match="concurrency"):
        _stat(concurrency=0)


def test_concurrency_overhead_stat_rejects_zero_pair_count() -> None:
    """A configuration with zero measured pairs carries no real evidence."""
    with pytest.raises(InvalidQualificationReportError, match="pair_count"):
        _stat(pair_count=0)


# ---------------------------------------------------------------------------
# Safe-summary leakage (structural, allowlist-based)
# ---------------------------------------------------------------------------


def test_field_names_contain_no_forbidden_substrings() -> None:
    """No field name itself hints at candidate source, raw I/O, container
    identity, filesystem paths, or credentials -- the same allowlist
    discipline as every other safe report in this project."""
    forbidden_substrings = (
        "candidate_source",
        "candidate_code",
        "stdout",
        "stderr",
        "container_id",
        "container_name",
        "cgroup_path",
        "hostname",
        "username",
        "socket",
        "exception_message",
        "traceback",
        "raw_log",
        "privileged_path",
    )
    for name in QUALIFICATION_REPORT_FIELD_NAMES:
        for forbidden in forbidden_substrings:
            assert forbidden not in name, (
                f"field {name!r} contains forbidden substring {forbidden!r}"
            )


def test_dataclass_fields_match_the_allowlist_exactly() -> None:
    """QUALIFICATION_REPORT_FIELD_NAMES is derived from, and stays in
    lockstep with, the dataclass's own real field set."""
    actual = {f.name for f in dataclasses.fields(H2C2BQualificationReport)}
    assert actual == QUALIFICATION_REPORT_FIELD_NAMES


def test_render_markdown_does_not_raise_and_contains_readiness() -> None:
    """The Markdown rendering succeeds and surfaces the readiness
    classification prominently."""
    report = make_report()
    markdown = render_markdown(report)
    assert report.readiness in markdown
    assert report.report_checksum in markdown
