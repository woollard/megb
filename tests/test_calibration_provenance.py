"""MEGB-03H.2A schema-provenance-audit correction: regression tests proving
rejection of identical-label/different-content-identity scenarios, content-
unbound contributor tampering, mixed evidence sets, and non-release-ready
traces.

Synthetic fixtures only -- no privileged artifact, no Docker, no
canonical/candidate execution anywhere in this module.
"""

import dataclasses

import pytest

from src.reference.calibration_schema import (
    CalibrationReconciliationError,
    MeasurementQuality,
    TelemetryUnavailableReason,
    reconcile_task_evaluation,
    require_consistent_case_scope,
)
from src.reference.calibration_summary import (
    CalibrationRecordNotReleaseReadyError,
    require_release_ready_stage,
)
from tests._calibration_fixtures import (
    OTHER_REFERENCE_CASE_CHECKSUM,
    REFERENCE_CASE_CHECKSUM,
    make_collector_method_provenance,
    make_context,
    make_invocation,
    make_task_evaluation_for,
)


# ---------------------------------------------------------------------------
# Identical labels, different task-manifest checksum
# ---------------------------------------------------------------------------


def test_different_task_manifest_checksum_changes_context_checksum() -> None:
    """Different task manifest checksum changes context checksum."""
    context_a = make_context()
    context_b = make_context(task_manifest_checksum="8" * 64)
    assert context_a.context_checksum != context_b.context_checksum


def test_identical_labels_different_task_manifest_checksum_rejected_on_reconcile() -> None:
    """Identical labels, different task manifest checksum, rejected on reconcile."""
    context_a = make_context()
    context_b = make_context(task_manifest_checksum="8" * 64)
    invocation = make_invocation(context=context_b)
    task_evaluation = make_task_evaluation_for([make_invocation(context=context_a)])
    with pytest.raises(CalibrationReconciliationError, match="different calibration context"):
        reconcile_task_evaluation(task_evaluation, {"inv-1": invocation})


# ---------------------------------------------------------------------------
# Identical task/case ordinal, different reference-case checksum
# ---------------------------------------------------------------------------


def test_require_consistent_case_scope_rejects_differing_reference_case_checksum() -> None:
    """Require consistent case scope rejects differing reference case checksum."""
    invocation_a = make_invocation(
        invocation_id="inv-1", case_ordinal=5, reference_case_checksum=REFERENCE_CASE_CHECKSUM
    )
    invocation_b = make_invocation(
        invocation_id="inv-2",
        case_ordinal=5,
        reference_case_checksum=OTHER_REFERENCE_CASE_CHECKSUM,
    )
    with pytest.raises(CalibrationReconciliationError, match="reference_case_checksum"):
        require_consistent_case_scope([invocation_a, invocation_b])


def test_identical_case_ordinal_different_reference_case_checksum_rejected() -> None:
    """Identical task/case ordinal, different reference case checksum, rejected on reconcile."""
    invocation_a = make_invocation(
        invocation_id="inv-1", case_ordinal=5, reference_case_checksum=REFERENCE_CASE_CHECKSUM
    )
    invocation_b = make_invocation(
        invocation_id="inv-2",
        case_ordinal=5,
        reference_case_checksum=OTHER_REFERENCE_CASE_CHECKSUM,
    )
    task_evaluation = make_task_evaluation_for([invocation_a, invocation_b])
    with pytest.raises(CalibrationReconciliationError, match="reference_case_checksum"):
        reconcile_task_evaluation(
            task_evaluation, {"inv-1": invocation_a, "inv-2": invocation_b}
        )


# ---------------------------------------------------------------------------
# Contributor content changed while contributor IDs remain unchanged
# ---------------------------------------------------------------------------


def test_contributor_content_changed_while_id_unchanged_rejected() -> None:
    """Contributor content changed while id unchanged, rejected."""
    invocation = make_invocation()
    task_evaluation = make_task_evaluation_for([invocation])
    tampered_invocation = dataclasses.replace(
        invocation, controller_wall_time_sec=999.0, record_checksum=""
    )
    assert tampered_invocation.invocation_id == invocation.invocation_id
    assert tampered_invocation.record_checksum != invocation.record_checksum
    with pytest.raises(CalibrationReconciliationError, match="content changed after binding"):
        reconcile_task_evaluation(task_evaluation, {"inv-1": tampered_invocation})


def test_reordered_contributors_normalize_to_the_same_checksum() -> None:
    """Reordered contributors normalize to the same checksum (sanity check
    that reordering is normalized, per the correction's own requirement,
    distinct from a real content change)."""
    invocation_a = make_invocation(invocation_id="inv-1")
    invocation_b = make_invocation(invocation_id="inv-2")
    forward = make_task_evaluation_for([invocation_a, invocation_b])
    reversed_order = make_task_evaluation_for([invocation_b, invocation_a])
    assert (
        forward.contributing_invocations_checksum
        == reversed_order.contributing_invocations_checksum
    )


# ---------------------------------------------------------------------------
# Contributors from mixed evidence sets
# ---------------------------------------------------------------------------


def test_contributors_from_mixed_evidence_sets_rejected() -> None:
    """Contributors from mixed evidence sets rejected."""
    invocation_a = make_invocation(
        invocation_id="inv-1", reference_case_checksum=REFERENCE_CASE_CHECKSUM
    )
    invocation_b = make_invocation(
        invocation_id="inv-2", reference_case_checksum=OTHER_REFERENCE_CASE_CHECKSUM
    )
    task_evaluation = make_task_evaluation_for([invocation_a, invocation_b])
    with pytest.raises(CalibrationReconciliationError):
        reconcile_task_evaluation(
            task_evaluation, {"inv-1": invocation_a, "inv-2": invocation_b}
        )


# ---------------------------------------------------------------------------
# Release-readiness: NOT_YET_INSTRUMENTED must never appear in a real trace
# ---------------------------------------------------------------------------


def test_release_ready_rejects_not_yet_instrumented() -> None:
    """Release ready rejects not yet instrumented."""
    invocation = make_invocation()  # default fixture uses NOT_YET_INSTRUMENTED
    with pytest.raises(CalibrationRecordNotReleaseReadyError, match="NOT_YET_INSTRUMENTED"):
        require_release_ready_stage([invocation])


def test_release_ready_accepts_fully_instrumented_invocation() -> None:
    """Release ready accepts fully instrumented invocation."""
    invocation = make_invocation(
        peak_memory_unavailable_reason=TelemetryUnavailableReason.HOST_TELEMETRY_UNAVAILABLE,
        peak_memory_provenance=make_collector_method_provenance(
            metric_id="peak_memory_bytes",
            unavailability_or_failure_reason=TelemetryUnavailableReason.HOST_TELEMETRY_UNAVAILABLE,
        ),
        peak_process_unavailable_reason=TelemetryUnavailableReason.HOST_TELEMETRY_UNAVAILABLE,
        peak_process_provenance=make_collector_method_provenance(
            metric_id="peak_process_count",
            unavailability_or_failure_reason=TelemetryUnavailableReason.HOST_TELEMETRY_UNAVAILABLE,
        ),
    )
    require_release_ready_stage([invocation])  # must not raise


def test_release_ready_checks_superseded_records_too() -> None:
    """Release ready checks superseded records too."""
    invocation = make_invocation(superseded=True)  # still NOT_YET_INSTRUMENTED by default
    with pytest.raises(CalibrationRecordNotReleaseReadyError):
        require_release_ready_stage([invocation])


# ---------------------------------------------------------------------------
# Taxonomy audit
# ---------------------------------------------------------------------------


def test_measurement_quality_still_has_exactly_four_values() -> None:
    """Measurement quality still has exactly four values (preserved unchanged)."""
    assert {member.value for member in MeasurementQuality} == {
        "EXACT",
        "SAMPLED_WITH_KNOWN_ERROR",
        "BOUNDARY_ONLY",
        "UNAVAILABLE_WITHOUT_CONTAMINATION",
    }


def test_telemetry_unavailable_reason_covers_required_categories() -> None:
    """Telemetry unavailable reason covers required categories."""
    values = {member.value for member in TelemetryUnavailableReason}
    assert values == {
        "NEVER_STARTED",
        "KILLED_BEFORE_COMPLETION",
        "NO_RESPONSE_PRODUCED",
        "HOST_TELEMETRY_UNAVAILABLE",
        "UNAVAILABLE_WITHOUT_CONTAMINATION",
        "SAMPLER_FAILURE",
        "NOT_APPLICABLE",
        "NOT_YET_INSTRUMENTED",
    }
