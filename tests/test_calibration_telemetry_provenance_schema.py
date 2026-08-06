"""MEGB-03H.2C.2A provenance/schema correction: tests for the persisted
telemetry-provenance model -- HostRuntimeContext, TelemetryCollectionPolicy
(both embedded in CalibrationRunContext), and CollectorMethodProvenance
(embedded per-metric in CalibrationInvocationRecord).

Synthetic fixtures only, via tests/_calibration_fixtures.py -- no real
privileged corpus access, no Docker. Distinct from
test_calibration_provenance.py, which covers the earlier schema-
provenance-audit correction (task-manifest/reference-case identity,
content-bound contributor checksums) -- a different provenance concern.
"""

# The safe-summary-leakage test below intentionally re-lists the same six
# field-name literals that src/reference/calibration_summary.py itself
# declares, so that a rename of one without the other is caught. Expected
# and accepted, not a defect.
# pylint: disable=duplicate-code

import pytest

from src.execution.telemetry_methods import (
    CollectorMethod,
    MetricCollectionDisposition,
    TerminalCoverageState,
)
from src.reference.calibration_schema import (
    CALIBRATION_SCHEMA_VERSION,
    CalibrationReconciliationError,
    InvalidCalibrationRecordError,
    MeasurementQuality,
    TelemetryUnavailableReason,
    UnsupportedCalibrationSchemaVersionError,
    calibration_run_context_from_dict,
    calibration_run_context_to_dict,
    collector_method_provenance_from_dict,
    collector_method_provenance_to_dict,
    host_runtime_context_from_dict,
    host_runtime_context_to_dict,
    reconcile_task_evaluation,
    telemetry_collection_policy_from_dict,
    telemetry_collection_policy_to_dict,
)
from src.reference.calibration_summary import (
    CALIBRATION_SUMMARY_REPORT_FIELD_NAMES,
    build_calibration_summary_report,
)
from tests._calibration_fixtures import (
    make_collector_method_provenance,
    make_context,
    make_host_runtime_context,
    make_invocation,
    make_task_evaluation_for,
    make_telemetry_collection_policy,
)

# ---------------------------------------------------------------------------
# Construction and round trip
# ---------------------------------------------------------------------------


def test_host_runtime_context_round_trip_is_deterministic() -> None:
    """Host runtime context round trip is deterministic."""
    context = make_host_runtime_context()
    restored = host_runtime_context_from_dict(host_runtime_context_to_dict(context))
    assert restored == context


def test_telemetry_collection_policy_round_trip_is_deterministic() -> None:
    """Telemetry collection policy round trip is deterministic."""
    policy = make_telemetry_collection_policy()
    restored = telemetry_collection_policy_from_dict(telemetry_collection_policy_to_dict(policy))
    assert restored == policy


def test_collector_method_provenance_round_trip_is_deterministic() -> None:
    """Collector method provenance round trip is deterministic."""
    provenance = make_collector_method_provenance()
    restored = collector_method_provenance_from_dict(
        collector_method_provenance_to_dict(provenance)
    )
    assert restored == provenance


def test_context_round_trip_carries_the_new_nested_provenance() -> None:
    """CalibrationRunContext's own round trip carries the new nested
    telemetry-policy/host-context objects, not just the pre-existing
    scalar fields."""
    context = make_context()
    restored = calibration_run_context_from_dict(calibration_run_context_to_dict(context))
    assert restored == context
    assert restored.telemetry_collection_policy == context.telemetry_collection_policy
    assert restored.host_runtime_context == context.host_runtime_context


def test_invocation_round_trip_carries_the_new_per_metric_provenance() -> None:
    """CalibrationInvocationRecord's own round trip carries both
    per-metric CollectorMethodProvenance objects."""
    from src.reference.calibration_schema import (  # pylint: disable=import-outside-toplevel
        calibration_invocation_record_from_dict,
        calibration_invocation_record_to_dict,
    )

    invocation = make_invocation()
    restored = calibration_invocation_record_from_dict(
        calibration_invocation_record_to_dict(invocation)
    )
    assert restored == invocation
    assert restored.peak_memory_provenance == invocation.peak_memory_provenance
    assert restored.peak_process_provenance == invocation.peak_process_provenance


# ---------------------------------------------------------------------------
# Old-version rejection
# ---------------------------------------------------------------------------


def test_calibration_schema_v1_is_rejected() -> None:
    """A record stamped with the pre-correction v1 schema version is
    rejected outright -- the version bump is real, not cosmetic."""
    with pytest.raises(UnsupportedCalibrationSchemaVersionError):
        make_context(calibration_schema_version="megb-03h-calibration-record-v1")


def test_calibration_schema_v2_is_rejected() -> None:
    """A record stamped with the pre-MEGB-03H.2C.3B.3 v2 schema version
    (this file's own "current" version at the time it was written) is
    rejected outright now that the schema has moved to v3 -- the v2->v3
    bump is real, not cosmetic."""
    with pytest.raises(UnsupportedCalibrationSchemaVersionError):
        make_context(calibration_schema_version="megb-03h-calibration-record-v2")


def test_current_schema_version_is_v3() -> None:
    """Confirms the exact, intentional version string this module
    currently implements (bumped v2->v3 by MEGB-03H.2C.3B.3 -- see
    tests/test_distributed_calibration_provenance.py for that
    correction's own dedicated test coverage)."""
    assert CALIBRATION_SCHEMA_VERSION == "megb-03h-calibration-record-v3"


# ---------------------------------------------------------------------------
# Checksum tampering
# ---------------------------------------------------------------------------


def test_host_runtime_context_checksum_tampering_detected() -> None:
    """Host runtime context checksum tampering detected."""
    context = make_host_runtime_context()
    payload = host_runtime_context_to_dict(context)
    payload["kernel_release"] = "tampered"
    with pytest.raises(InvalidCalibrationRecordError, match="host_context_checksum"):
        host_runtime_context_from_dict(payload)


def test_telemetry_collection_policy_checksum_tampering_detected() -> None:
    """Telemetry collection policy checksum tampering detected."""
    policy = make_telemetry_collection_policy()
    payload = telemetry_collection_policy_to_dict(policy)
    payload["telemetry_collection_profile_version"] = "tampered"
    with pytest.raises(InvalidCalibrationRecordError, match="policy_checksum"):
        telemetry_collection_policy_from_dict(payload)


def test_collector_method_provenance_checksum_tampering_detected() -> None:
    """Collector method provenance checksum tampering detected."""
    provenance = make_collector_method_provenance()
    payload = collector_method_provenance_to_dict(provenance)
    payload["actual_sample_count"] = 999
    with pytest.raises(InvalidCalibrationRecordError, match="provenance_checksum"):
        collector_method_provenance_from_dict(payload)


# ---------------------------------------------------------------------------
# Identity/checksum sensitivity: policy, host context, per-metric method
# ---------------------------------------------------------------------------


def test_different_telemetry_collection_policy_changes_context_checksum() -> None:
    """Changing the requested telemetry policy changes context identity."""
    base = make_context()
    other = make_context(
        telemetry_collection_policy=make_telemetry_collection_policy(
            telemetry_collection_profile_version="v2"
        )
    )
    assert base.context_checksum != other.context_checksum


def test_different_host_runtime_context_changes_context_checksum() -> None:
    """Changing the host/runtime description changes context identity."""
    base = make_context()
    other = make_context(host_runtime_context=make_host_runtime_context(kernel_release="6.9.0"))
    assert base.context_checksum != other.context_checksum


def test_different_collector_method_provenance_changes_record_checksum() -> None:
    """Changing a metric's actual selected method changes invocation
    record identity -- a run-level policy alone could never capture
    this, since different metrics/hosts may fall back differently."""
    base = make_invocation()
    other_provenance = make_collector_method_provenance(
        metric_id="peak_memory_bytes",
        collector_implementation_id=CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY.value,
        selected_method=CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY,
        selection_disposition=MetricCollectionDisposition.FALLBACK_METHOD_SELECTED,
        terminal_coverage=TerminalCoverageState.TERMINAL_READ_NOT_APPLICABLE,
    )
    other = make_invocation(peak_memory_provenance=other_provenance)
    assert base.record_checksum != other.record_checksum


def test_identical_display_labels_but_different_telemetry_provenance_are_distinct() -> None:
    """Two contexts sharing every pre-existing label but differing only
    in telemetry policy or host context must never collapse to the same
    identity -- the exact scenario this correction exists to prevent."""
    same_labels_different_policy = make_context(
        telemetry_collection_policy=make_telemetry_collection_policy(
            collector_selection_policy_version="v9"
        )
    )
    assert make_context().context_checksum != same_labels_different_policy.context_checksum


# ---------------------------------------------------------------------------
# Sampling-interval / sample-count validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_interval", [0.0, -1.0, True])
def test_provenance_configured_sampling_interval_must_be_positive_or_none(
    bad_interval: object,
) -> None:
    """A sampled method's configured interval must be a real positive
    number -- zero, negative, or a bool are all rejected."""
    with pytest.raises(InvalidCalibrationRecordError):
        make_collector_method_provenance(configured_sampling_interval_sec=bad_interval)


def test_provenance_configured_sampling_interval_none_is_valid_for_exact_methods() -> None:
    """An exact (non-sampled) method legitimately has no sampling
    interval at all."""
    make_collector_method_provenance(
        selected_method=CollectorMethod.CGROUP_V2_MEMORY_PEAK,
        selection_disposition=MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
        measurement_quality=MeasurementQuality.EXACT,
        unavailability_or_failure_reason=None,
        terminal_coverage=TerminalCoverageState.TERMINAL_READ_CONFIRMED,
        configured_sampling_interval_sec=None,
    )  # does not raise


@pytest.mark.parametrize("bad_count", [-1, True])
def test_provenance_actual_sample_count_must_be_a_non_negative_int(bad_count: object) -> None:
    """actual_sample_count rejects negative values and bools."""
    with pytest.raises(InvalidCalibrationRecordError):
        make_collector_method_provenance(actual_sample_count=bad_count)


@pytest.mark.parametrize(
    "bad_pair",
    [
        ("", 0.05),
        ("peak_memory_bytes", 0.0),
        ("peak_memory_bytes", -1.0),
        ("peak_memory_bytes", True),
        (1, 0.05),
    ],
)
def test_telemetry_collection_policy_sampling_interval_pairs_are_validated(
    bad_pair: tuple[object, object],
) -> None:
    """Every (metric id, interval) pair in the policy is validated the
    same way -- empty metric id, non-positive interval, or a bool
    interval are all rejected."""
    with pytest.raises(InvalidCalibrationRecordError):
        make_telemetry_collection_policy(configured_sampling_intervals_sec=(bad_pair,))


# ---------------------------------------------------------------------------
# Fallback disposition
# ---------------------------------------------------------------------------


def test_fallback_disposition_is_representable_and_persisted() -> None:
    """A fallback (non-primary) method selection round-trips faithfully."""
    provenance = make_collector_method_provenance(
        selected_method=CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY,
        selection_disposition=MetricCollectionDisposition.FALLBACK_METHOD_SELECTED,
        measurement_quality=MeasurementQuality.BOUNDARY_ONLY,
        unavailability_or_failure_reason=None,
        terminal_coverage=TerminalCoverageState.TERMINAL_READ_NOT_APPLICABLE,
        actual_sample_count=5,
    )
    restored = collector_method_provenance_from_dict(
        collector_method_provenance_to_dict(provenance)
    )
    assert restored.selection_disposition == MetricCollectionDisposition.FALLBACK_METHOD_SELECTED


def test_no_method_available_disposition_requires_the_matching_method() -> None:
    """selection_disposition=NO_METHOD_AVAILABLE if and only if
    selected_method=UNAVAILABLE_WITHOUT_CONTAMINATION -- the two must
    never disagree."""
    make_collector_method_provenance(
        selected_method=CollectorMethod.UNAVAILABLE_WITHOUT_CONTAMINATION,
        selection_disposition=MetricCollectionDisposition.NO_METHOD_AVAILABLE,
        measurement_quality=None,
        unavailability_or_failure_reason=(
            TelemetryUnavailableReason.UNAVAILABLE_WITHOUT_CONTAMINATION
        ),
    )  # does not raise
    with pytest.raises(InvalidCalibrationRecordError):
        make_collector_method_provenance(
            selected_method=CollectorMethod.UNAVAILABLE_WITHOUT_CONTAMINATION,
            selection_disposition=MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
        )
    with pytest.raises(InvalidCalibrationRecordError):
        make_collector_method_provenance(
            selected_method=CollectorMethod.CGROUP_V2_MEMORY_PEAK,
            selection_disposition=MetricCollectionDisposition.NO_METHOD_AVAILABLE,
            measurement_quality=MeasurementQuality.EXACT,
            unavailability_or_failure_reason=None,
            terminal_coverage=TerminalCoverageState.TERMINAL_READ_CONFIRMED,
        )


# ---------------------------------------------------------------------------
# Terminal-read success / race / exactness invariants
# ---------------------------------------------------------------------------


def test_exact_with_terminal_read_confirmed_is_accepted() -> None:
    """A genuinely confirmed terminal read may legitimately claim EXACT."""
    make_collector_method_provenance(
        selected_method=CollectorMethod.CGROUP_V2_MEMORY_PEAK,
        selection_disposition=MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
        measurement_quality=MeasurementQuality.EXACT,
        unavailability_or_failure_reason=None,
        terminal_coverage=TerminalCoverageState.TERMINAL_READ_CONFIRMED,
    )  # does not raise


def test_exact_rejected_when_terminal_read_missed() -> None:
    """A lifecycle race (the terminal read could not be confirmed) must
    never be paired with EXACT -- the whole point of this correction."""
    with pytest.raises(InvalidCalibrationRecordError, match="TERMINAL_READ_CONFIRMED"):
        make_collector_method_provenance(
            selected_method=CollectorMethod.CGROUP_V2_MEMORY_PEAK,
            selection_disposition=MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
            measurement_quality=MeasurementQuality.EXACT,
            unavailability_or_failure_reason=None,
            terminal_coverage=TerminalCoverageState.TERMINAL_READ_MISSED,
        )


def test_exact_rejected_when_terminal_read_not_applicable() -> None:
    """EXACT with NOT_APPLICABLE terminal coverage (the placeholder/
    sampled default) is equally rejected -- file existence or a
    mid-execution read alone is not proof."""
    with pytest.raises(InvalidCalibrationRecordError, match="TERMINAL_READ_CONFIRMED"):
        make_collector_method_provenance(
            selected_method=CollectorMethod.CGROUP_V2_MEMORY_PEAK,
            selection_disposition=MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
            measurement_quality=MeasurementQuality.EXACT,
            unavailability_or_failure_reason=None,
            terminal_coverage=TerminalCoverageState.TERMINAL_READ_NOT_APPLICABLE,
        )


def test_sampled_method_rejected_as_exact_even_with_confirmed_terminal_read() -> None:
    """A sampled method can never claim EXACT, even if (implausibly) a
    terminal-read confirmation were supplied -- exactness requires an
    exact *method*, not merely confirmed coverage."""
    with pytest.raises(InvalidCalibrationRecordError, match="sampled method"):
        make_collector_method_provenance(
            selected_method=CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY,
            selection_disposition=MetricCollectionDisposition.FALLBACK_METHOD_SELECTED,
            measurement_quality=MeasurementQuality.EXACT,
            unavailability_or_failure_reason=None,
            terminal_coverage=TerminalCoverageState.TERMINAL_READ_CONFIRMED,
        )


def test_sampled_with_known_error_is_rejected_outright() -> None:
    """No implemented collector method has a defensible quantitative
    error model yet -- SAMPLED_WITH_KNOWN_ERROR is provisionally
    forbidden entirely, not just for sampled methods."""
    with pytest.raises(InvalidCalibrationRecordError, match="SAMPLED_WITH_KNOWN_ERROR"):
        make_collector_method_provenance(
            selected_method=CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY,
            selection_disposition=MetricCollectionDisposition.FALLBACK_METHOD_SELECTED,
            measurement_quality=MeasurementQuality.SAMPLED_WITH_KNOWN_ERROR,
            unavailability_or_failure_reason=None,
            terminal_coverage=TerminalCoverageState.TERMINAL_READ_NOT_APPLICABLE,
        )


def test_boundary_only_is_a_lower_bound_never_upgraded_implicitly() -> None:
    """A BOUNDARY_ONLY sampled reading is accepted as-is -- nothing here
    ever silently upgrades it to a stronger quality tier."""
    provenance = make_collector_method_provenance(
        selected_method=CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY,
        selection_disposition=MetricCollectionDisposition.FALLBACK_METHOD_SELECTED,
        measurement_quality=MeasurementQuality.BOUNDARY_ONLY,
        unavailability_or_failure_reason=None,
        terminal_coverage=TerminalCoverageState.TERMINAL_READ_NOT_APPLICABLE,
        actual_sample_count=3,
    )
    assert provenance.measurement_quality == MeasurementQuality.BOUNDARY_ONLY


# ---------------------------------------------------------------------------
# Metric-id / cross-field consistency
# ---------------------------------------------------------------------------


def test_provenance_metric_id_must_be_one_of_the_two_collector_metrics() -> None:
    """metric_id is a closed set -- not an arbitrary string."""
    with pytest.raises(InvalidCalibrationRecordError, match="metric_id"):
        make_collector_method_provenance(metric_id="observed_response_bytes")


def test_invocation_rejects_provenance_bound_to_the_wrong_metric_slot() -> None:
    """A CollectorMethodProvenance built for the wrong metric (e.g. one
    tagged peak_process_count placed in the peak_memory_provenance slot)
    is rejected, never silently accepted."""
    wrong_slot_provenance = make_collector_method_provenance(metric_id="peak_process_count")
    with pytest.raises(InvalidCalibrationRecordError, match="metric_id"):
        make_invocation(peak_memory_provenance=wrong_slot_provenance)


def test_invocation_rejects_provenance_quality_disagreeing_with_the_record_own_field() -> None:
    """peak_memory_provenance.measurement_quality must agree exactly with
    peak_memory_quality on the same record."""
    disagreeing_provenance = make_collector_method_provenance(
        metric_id="peak_memory_bytes",
        selected_method=CollectorMethod.CGROUP_V2_MEMORY_PEAK,
        selection_disposition=MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
        measurement_quality=MeasurementQuality.EXACT,
        unavailability_or_failure_reason=None,
        terminal_coverage=TerminalCoverageState.TERMINAL_READ_CONFIRMED,
    )
    with pytest.raises(InvalidCalibrationRecordError, match="measurement_quality"):
        make_invocation(
            peak_memory_bytes=None,
            peak_memory_quality=None,
            peak_memory_unavailable_reason=TelemetryUnavailableReason.NOT_YET_INSTRUMENTED,
            peak_memory_provenance=disagreeing_provenance,
        )


def test_invocation_rejects_provenance_reason_disagreeing_with_the_record_own_field() -> None:
    """peak_memory_provenance.unavailability_or_failure_reason must agree
    exactly with peak_memory_unavailable_reason on the same record."""
    disagreeing_provenance = make_collector_method_provenance(
        metric_id="peak_memory_bytes",
        unavailability_or_failure_reason=TelemetryUnavailableReason.HOST_TELEMETRY_UNAVAILABLE,
    )
    with pytest.raises(InvalidCalibrationRecordError, match="unavailability_or_failure_reason"):
        make_invocation(
            peak_memory_unavailable_reason=TelemetryUnavailableReason.NOT_YET_INSTRUMENTED,
            peak_memory_provenance=disagreeing_provenance,
        )


# ---------------------------------------------------------------------------
# Contributor reconciliation
# ---------------------------------------------------------------------------


def test_reconcile_rejects_contributors_with_incompatible_telemetry_policy() -> None:
    """Two invocations sharing every other identity field but differing
    in telemetry_collection_policy have different context_checksum
    values and therefore fail reconciliation against a shared task
    evaluation -- satisfied automatically by context embedding, no
    additional reconciliation code required."""
    context_a = make_context()
    context_b = make_context(
        telemetry_collection_policy=make_telemetry_collection_policy(
            telemetry_collection_profile_version="v2"
        )
    )
    invocation_a = make_invocation(invocation_id="inv-a", context=context_a, case_ordinal=0)
    invocation_b = make_invocation(invocation_id="inv-b", context=context_b, case_ordinal=1)
    task_evaluation = make_task_evaluation_for([invocation_a, invocation_b])
    with pytest.raises(CalibrationReconciliationError, match="different calibration context"):
        reconcile_task_evaluation(
            task_evaluation, {"inv-a": invocation_a, "inv-b": invocation_b}
        )


def test_reconcile_rejects_contributors_with_incompatible_host_runtime_context() -> None:
    """Same as above, for host_runtime_context -- a run spanning
    incompatible host descriptions is never silently reconciled."""
    context_a = make_context()
    context_b = make_context(host_runtime_context=make_host_runtime_context(cgroup_version="v1"))
    invocation_a = make_invocation(invocation_id="inv-a", context=context_a, case_ordinal=0)
    invocation_b = make_invocation(invocation_id="inv-b", context=context_b, case_ordinal=1)
    task_evaluation = make_task_evaluation_for([invocation_a, invocation_b])
    with pytest.raises(CalibrationReconciliationError, match="different calibration context"):
        reconcile_task_evaluation(
            task_evaluation, {"inv-a": invocation_a, "inv-b": invocation_b}
        )


# ---------------------------------------------------------------------------
# Safe-summary leakage (method/quality aggregates only)
# ---------------------------------------------------------------------------


def test_summary_field_names_include_the_new_safe_method_aggregates() -> None:
    """The new aggregate fields exist and are part of the same allowlist
    the leakage test in test_calibration_schema.py already enforces
    (forbidding case_id/candidate_code/path/etc. substrings)."""
    for expected in (
        "peak_memory_selected_method_counts",
        "peak_process_selected_method_counts",
        "peak_memory_selection_disposition_counts",
        "peak_process_selection_disposition_counts",
        "peak_memory_terminal_coverage_counts",
        "peak_process_terminal_coverage_counts",
    ):
        assert expected in CALIBRATION_SUMMARY_REPORT_FIELD_NAMES


def test_summary_report_aggregates_method_and_disposition_counts_correctly() -> None:
    """build_calibration_summary_report() actually populates the new
    fields from real invocation records, never leaving them empty when
    real data exists."""
    exact_provenance = make_collector_method_provenance(
        metric_id="peak_memory_bytes",
        selected_method=CollectorMethod.CGROUP_V2_MEMORY_PEAK,
        selection_disposition=MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
        measurement_quality=MeasurementQuality.EXACT,
        unavailability_or_failure_reason=None,
        terminal_coverage=TerminalCoverageState.TERMINAL_READ_CONFIRMED,
    )
    invocation = make_invocation(
        peak_memory_bytes=4096,
        peak_memory_quality=MeasurementQuality.EXACT,
        peak_memory_unavailable_reason=None,
        peak_memory_provenance=exact_provenance,
    )
    report = build_calibration_summary_report(
        stage=invocation.context.stage,
        calibration_run_id=invocation.context.calibration_run_id,
        generated_at="2026-08-03T00:00:05Z",
        invocation_records=[invocation],
        task_evaluation_records=[],
    )
    assert report.peak_memory_selected_method_counts == {"CGROUP_V2_MEMORY_PEAK": 1}
    assert report.peak_memory_selection_disposition_counts == {"PRIMARY_METHOD_SELECTED": 1}
    assert report.peak_memory_terminal_coverage_counts == {"TERMINAL_READ_CONFIRMED": 1}


def test_summary_report_never_carries_interface_family_or_raw_content() -> None:
    """Structural check: no summary field is capable of carrying
    interface_family, a host path, or any other per-record detail --
    only method/quality/disposition enum-value counts."""
    for forbidden in ("interface_family", "interface", "path", "collector_implementation_id"):
        assert forbidden not in CALIBRATION_SUMMARY_REPORT_FIELD_NAMES
