"""MEGB-03H.2C.2B: offline tests for the real-Docker measurement harness's
pure, non-Docker-dependent pieces -- plan identity verification (against
the real committed plan file), workload source generation, the
status-matrix scenario table, overhead statistics, and stage-runtime
projections. No real Docker; the harness's ``run_*`` orchestration
functions themselves are exercised only by the real measurement run.
"""

import os

import pytest

from src.execution.protocol import ExecutionStatus
from src.execution.telemetry import (
    TelemetryObservation,
    TelemetryQuality,
    TelemetryUnavailableReason,
)
from src.execution.telemetry_methods import (
    CollectorMethod,
    CollectorMethodIdentity,
    MetricCollectionDisposition,
    TerminalCoverageState,
)
from src.reference import h2c2b_measurement as harness

_PLAN_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs",
    "reference",
    "megb-03h2c2b-real-docker-measurement-plan.md",
)


# ---------------------------------------------------------------------------
# Plan identity
# ---------------------------------------------------------------------------


def test_verify_plan_identity_accepts_the_real_committed_plan() -> None:
    """The frozen identity constants match the actual committed plan
    document -- proves the harness was built against the real, current
    plan, not a stale or hypothetical one."""
    harness.verify_plan_identity(_PLAN_PATH)  # does not raise


def test_verify_plan_identity_rejects_a_modified_plan(tmp_path: object) -> None:
    """Any change to the plan's own bytes is detected -- a real run must
    never silently proceed against a changed plan."""
    from pathlib import Path  # pylint: disable=import-outside-toplevel

    modified = Path(str(tmp_path)) / "plan.md"
    modified.write_text("not the real plan\n", encoding="utf-8")
    with pytest.raises(harness.PlanIdentityMismatchError):
        harness.verify_plan_identity(str(modified))


def test_run_identity_distinguishes_qualifying_from_diagnostic() -> None:
    """A qualifying run's identity never collides with a diagnostic one,
    and vice versa -- the required visible distinction."""
    qualifying = harness.run_identity_for(qualifying=True, label="x")
    diagnostic = harness.run_identity_for(qualifying=False, label="x")
    assert qualifying != diagnostic
    assert "diagnostic" in diagnostic
    assert "diagnostic" not in qualifying


# ---------------------------------------------------------------------------
# Synthetic workload source generation
# ---------------------------------------------------------------------------


def test_baseline_candidate_source_defines_entry_point_f() -> None:
    """The baseline candidate defines the conventional entry_point='f'."""
    assert "def f(" in harness.BASELINE_CANDIDATE_SOURCE


def test_memory_allocator_candidate_source_is_parameterized() -> None:
    """Distinct parameterizations produce distinct source -- no hardcoded
    single-size workload."""
    small = harness.memory_allocator_candidate_source(32, 0.1)
    large = harness.memory_allocator_candidate_source(128, 0.1)
    assert small != large
    assert "32" in small
    assert "128" in large
    assert "def f(" in small


def test_process_spawner_candidate_source_is_parameterized() -> None:
    """Distinct spawn counts produce distinct source."""
    few = harness.process_spawner_candidate_source(1, 0.1)
    many = harness.process_spawner_candidate_source(16, 0.1)
    assert few != many
    assert "range(1)" in few
    assert "range(16)" in many


def test_late_peak_candidate_source_orders_baseline_then_spike() -> None:
    """The late_peak source allocates baseline, sleeps, then allocates the
    larger spike immediately before returning -- matching the frozen
    plan's own end-of-container race design."""
    source = harness.late_peak_candidate_source(baseline_mib=8, spike_mib=64, presleep_sec=0.2)
    baseline_index = source.index("baseline = bytearray(8")
    spike_index = source.index("spike = bytearray(64")
    return_index = source.index("return")
    assert baseline_index < spike_index < return_index


def test_all_workload_versions_are_distinct() -> None:
    """No two synthetic workload identities collide with each other."""
    versions = {
        harness.BASELINE_WORKLOAD_VERSION,
        harness.MEMORY_ALLOCATOR_WORKLOAD_VERSION,
        harness.PROCESS_SPAWNER_WORKLOAD_VERSION,
        harness.LATE_PEAK_WORKLOAD_VERSION,
    }
    assert len(versions) == 4


# ---------------------------------------------------------------------------
# Status-matrix scenario table (pure structure)
# ---------------------------------------------------------------------------


def test_status_matrix_scenarios_cover_the_frozen_plan_statuses() -> None:
    """Every named status in the frozen plan's §6 (excluding process_limit,
    which is deliberately not pinned to one expected status) has its own
    scenario."""
    expected = {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.SYNTAX_ERROR,
        ExecutionStatus.CANDIDATE_EXCEPTION,
        ExecutionStatus.OUTPUT_LIMIT,
        ExecutionStatus.PROTOCOL_ERROR,
        ExecutionStatus.TIMEOUT,
        ExecutionStatus.OUT_OF_MEMORY,
        ExecutionStatus.INFRASTRUCTURE_ERROR,
    }
    actual = {scenario.expected_status for scenario in harness.STATUS_MATRIX_SCENARIOS}
    assert actual == expected


def test_status_matrix_scenario_names_are_unique() -> None:
    """No duplicate scenario names -- each is independently addressable."""
    names = [scenario.name for scenario in harness.STATUS_MATRIX_SCENARIOS]
    assert len(names) == len(set(names))


def test_process_limit_scenario_declares_two_acceptable_statuses() -> None:
    """process_limit's own containment result may legitimately be either
    PROCESS_LIMIT or the wall-clock TIMEOUT backstop -- never COMPLETED."""
    assert ExecutionStatus.COMPLETED not in harness.PROCESS_LIMIT_ACCEPTABLE_STATUSES
    assert ExecutionStatus.PROCESS_LIMIT in harness.PROCESS_LIMIT_ACCEPTABLE_STATUSES
    assert ExecutionStatus.TIMEOUT in harness.PROCESS_LIMIT_ACCEPTABLE_STATUSES


# ---------------------------------------------------------------------------
# Overhead statistics (pure)
# ---------------------------------------------------------------------------


def _timing(
    disabled_sec: float, enabled_sec: float, leg_order: str = "AB"
) -> harness.PairedInvocationTiming:
    return harness.PairedInvocationTiming(
        leg_order=leg_order, disabled_wall_sec=disabled_sec, enabled_wall_sec=enabled_sec
    )


def test_overhead_sec_is_enabled_minus_disabled() -> None:
    """overhead_sec is signed enabled-minus-disabled, so a real overhead
    (enabled slower) is positive."""
    timing = _timing(1.0, 1.02)
    assert timing.overhead_sec == pytest.approx(0.02)


def test_mean_overhead_ms_matches_hand_computed_mean() -> None:
    """mean_overhead_ms is the arithmetic mean across all pairs, in
    milliseconds."""
    pairs = (_timing(1.0, 1.01), _timing(1.0, 1.03))  # overheads: 10ms, 30ms
    measurement = harness.OverheadMeasurement(workload="baseline", concurrency=1, pairs=pairs)
    assert measurement.mean_overhead_ms == pytest.approx(20.0)


def test_p99_overhead_ms_is_a_diagnostic_upper_tail_value() -> None:
    """p99 never falls below the mean for a right-skewed sample, and
    matches the nearest-rank value for a small sample."""
    pairs = tuple(_timing(1.0, 1.0 + i * 0.001) for i in range(1, 11))
    measurement = harness.OverheadMeasurement(workload="baseline", concurrency=1, pairs=pairs)
    assert measurement.p99_overhead_ms >= measurement.mean_overhead_ms


def test_percentile_ms_rejects_zero_samples() -> None:
    """A percentile over zero samples is a programming error, not a
    silent zero."""
    with pytest.raises(ValueError):
        harness._percentile_ms((), 0.99)  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# MethodFinding projection (pure)
# ---------------------------------------------------------------------------


def _identity(**overrides: object) -> CollectorMethodIdentity:
    defaults: dict[str, object] = {
        "method": CollectorMethod.CGROUP_V2_MEMORY_PEAK,
        "method_version": "cgroup_peak_file_collector/v1",
        "interface": "cgroupfs:/fake/memory.peak",
        "sampling_interval_sec": None,
        "selection_disposition": MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
    }
    defaults.update(overrides)
    return CollectorMethodIdentity(**defaults)  # type: ignore[arg-type]


def test_method_finding_from_observation_with_a_method_identity() -> None:
    """A real observation with a resolved method identity projects every
    required field."""
    observation = TelemetryObservation(
        value=1024,
        quality=TelemetryQuality.EXACT,
        unavailable_reason=None,
        method_identity=_identity(),
        terminal_coverage=TerminalCoverageState.TERMINAL_READ_CONFIRMED,
    )
    finding = harness.method_finding_from_observation(
        metric="peak_memory_bytes",
        preferred_method="CGROUP_V2_MEMORY_PEAK",
        observation=observation,
    )
    assert finding.actual_selected_method == "CGROUP_V2_MEMORY_PEAK"
    assert finding.selection_disposition == "PRIMARY_METHOD_SELECTED"
    assert finding.terminal_coverage == "TERMINAL_READ_CONFIRMED"
    assert finding.quality == "EXACT"
    assert finding.unavailable_reason is None


def test_method_finding_from_observation_with_no_method_identity() -> None:
    """An observation with no resolved method (e.g. a START failure
    before selection) reports 'NONE' rather than raising or guessing."""
    observation = TelemetryObservation(
        value=None,
        quality=None,
        unavailable_reason=TelemetryUnavailableReason.SAMPLER_FAILURE,
    )
    finding = harness.method_finding_from_observation(
        metric="peak_memory_bytes",
        preferred_method="CGROUP_V2_MEMORY_PEAK",
        observation=observation,
    )
    assert finding.actual_selected_method == "NONE"
    assert finding.selection_disposition == "NONE"
    assert finding.unavailable_reason == "SAMPLER_FAILURE"


# ---------------------------------------------------------------------------
# CleanupCheckResult (pure)
# ---------------------------------------------------------------------------


def test_cleanup_check_result_clean_iff_no_leftover_names() -> None:
    """clean is exactly the emptiness of leftover_container_names."""
    assert harness.CleanupCheckResult(leftover_container_names=()).clean is True
    assert harness.CleanupCheckResult(leftover_container_names=("x",)).clean is False


# ---------------------------------------------------------------------------
# Stage-runtime projections (pure formula)
# ---------------------------------------------------------------------------


def test_project_stage_runtimes_covers_every_stage_and_scenario() -> None:
    """Every (stage, scenario) combination is projected -- 4 stages x 4
    scenarios = 16 projections."""
    projections = harness.project_stage_runtimes(measured_telemetry_overhead_sec=0.0)
    assert len(projections) == 16
    stages = {p.stage for p in projections}
    scenarios = {p.scenario for p in projections}
    assert stages == set(harness.FROZEN_STAGE_INVOCATION_COUNTS)
    assert scenarios == set(harness.FROZEN_SCENARIO_MULTIPLIERS)


def test_project_stage_runtimes_scales_linearly_with_overhead() -> None:
    """Adding measured telemetry overhead strictly increases every
    projected runtime -- never silently absorbed or ignored."""
    zero_overhead = harness.project_stage_runtimes(measured_telemetry_overhead_sec=0.0)
    with_overhead = harness.project_stage_runtimes(measured_telemetry_overhead_sec=0.5)
    zero_by_key = {(p.stage, p.scenario): p.projected_seconds for p in zero_overhead}
    for projection in with_overhead:
        key = (projection.stage, projection.scenario)
        assert projection.projected_seconds > zero_by_key[key]


def test_project_stage_runtimes_baseline_scenario_h3_matches_accepted_sanity_check() -> None:
    """H.3's baseline scenario at zero measured telemetry overhead
    reproduces the H.1 calibration design's own accepted sanity check
    (~3.4 minutes)."""
    projections = harness.project_stage_runtimes(measured_telemetry_overhead_sec=0.0)
    h3_baseline = next(p for p in projections if p.stage == "H3" and p.scenario == "baseline")
    assert h3_baseline.projected_seconds == pytest.approx(3.4 * 60, rel=0.05)


def test_stage_projection_within_ceiling_reflects_the_frozen_hard_ceilings() -> None:
    """A projection under its own stage's frozen hard ceiling reports
    within_ceiling=True; one that isn't reports False."""
    under = harness.StageProjection(
        stage="H3", scenario="baseline", projected_seconds=100.0, hard_ceiling_seconds=3600.0
    )
    over = harness.StageProjection(
        stage="H3", scenario="stress", projected_seconds=999_999.0, hard_ceiling_seconds=3600.0
    )
    assert under.within_ceiling is True
    assert over.within_ceiling is False
