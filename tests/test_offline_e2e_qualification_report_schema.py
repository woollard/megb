"""MEGB-03H.2C.3B.2C: offline tests for the safe offline end-to-end
qualification report schema. Synthetic fixtures only."""

import pytest

from src.distributed.offline_e2e_qualification_report import (
    EXPECTED_ADMITTED_COUNT,
    EXPECTED_AUDIT_ABANDONED_COUNT,
    EXPECTED_CANCELLED_COUNT,
    EXPECTED_COMPLETED_COUNT,
    EXPECTED_FAILED_COUNT,
    EXPECTED_MINIMUM_DUPLICATE_DELIVERY_COUNT,
    EXPECTED_MINIMUM_REDELIVERY_COUNT,
    EXPECTED_RETRIED_COUNT,
    OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION,
    InvalidOfflineE2EQualificationReportError,
    OfflineE2EQualificationReport,
    ReadinessClassification,
    build_offline_e2e_qualification_report,
    offline_e2e_qualification_report_from_dict,
    offline_e2e_qualification_report_to_dict,
    render_markdown,
)

_PLAN_SHA256 = "a" * 64
_PLAN_BLOB = "b" * 40
_WORKLOAD_SHA256 = "c" * 64
_FAULT_CONFORMANCE_CHECKSUM = "d" * 64


class _Accumulator:  # pylint: disable=too-many-instance-attributes
    """A minimal stand-in for the real test-harness accumulator --
    proves build_offline_e2e_qualification_report never needs the real
    dataclass type, only these attributes by name."""

    def __init__(self, **overrides: object) -> None:
        fields: dict[str, object] = {
            "run_context_checksum": "e" * 64,
            "qualification_identity_checksum": "f" * 64,
            "worker_topology_provisioning_class_counts": (("ON_DEMAND", 2),),
            "worker_topology_region_counts": (("us-central1", 1), ("us-east1", 1)),
            "worker_topology_machine_type_counts": (("n2-standard-4", 2),),
            "admitted_count": EXPECTED_ADMITTED_COUNT,
            "completed_count": EXPECTED_COMPLETED_COUNT,
            "failed_count": EXPECTED_FAILED_COUNT,
            "retried_count": EXPECTED_RETRIED_COUNT,
            "cancelled_count": EXPECTED_CANCELLED_COUNT,
            "duplicate_delivery_count": EXPECTED_MINIMUM_DUPLICATE_DELIVERY_COUNT,
            "redelivery_count": EXPECTED_MINIMUM_REDELIVERY_COUNT,
            "budget_requested_cents_total": 1100,
            "budget_finalized_cents_total": 1000,
            "budget_released_cents_total": 100,
            "measured_peak_concurrency_personal": 2,
            "measured_peak_concurrency_generic": 4,
            "audit_delivered_count": 20,
            "audit_abandoned_count": EXPECTED_AUDIT_ABANDONED_COUNT,
            "audit_still_pending_count": 0,
            "queue_unacknowledged_count": 0,
            "serial_vs_distributed_equivalent": True,
            "generic_concurrency4_equivalent": True,
        }
        fields.update(overrides)
        for name, value in fields.items():
            setattr(self, name, value)


def _build(**overrides: object) -> OfflineE2EQualificationReport:
    return build_offline_e2e_qualification_report(
        plan_sha256=_PLAN_SHA256,
        plan_git_blob_sha1=_PLAN_BLOB,
        workload_sha256=_WORKLOAD_SHA256,
        distributed_provenance_schema_version="megb-03h2c3b1-distributed-provenance-v1",
        distributed_orchestration_schema_version="megb-03h2c3b2b2-distributed-orchestration-v3",
        fault_conformance_report_checksum=_FAULT_CONFORMANCE_CHECKSUM,
        accumulator=_Accumulator(**overrides),
    )


def test_build_report_with_healthy_accumulator_is_ready() -> None:
    """Test a report built from a fully-reconciled, frozen-count-matching
    accumulator reports readiness OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3,
    never independently settable."""
    report = _build()
    assert report.readiness == ReadinessClassification.OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3
    assert len(report.report_checksum) == 64


@pytest.mark.parametrize(
    "overrides",
    [
        {"admitted_count": EXPECTED_ADMITTED_COUNT + 1},
        {"completed_count": EXPECTED_COMPLETED_COUNT - 1},
        {"failed_count": 0},
        {"retried_count": 0},
        {"cancelled_count": 0},
        {"duplicate_delivery_count": 0},
        {"redelivery_count": 0},
        {"audit_abandoned_count": 0},
        {"audit_still_pending_count": 1},
        {"queue_unacknowledged_count": 1},
        {"budget_requested_cents_total": 999},
        {"serial_vs_distributed_equivalent": False},
        {"generic_concurrency4_equivalent": False},
    ],
)
def test_build_report_blocks_on_any_deviation_from_frozen_expectations(
    overrides: dict[str, object],
) -> None:
    """Test that deviating from any single frozen expectation --
    including budget reconciliation -- yields BLOCKED_OFFLINE_DISTRIBUTED_PATH,
    never a silently-still-ready report."""
    report = _build(**overrides)
    assert report.readiness == ReadinessClassification.BLOCKED_OFFLINE_DISTRIBUTED_PATH


def test_report_rejects_readiness_inconsistent_with_reconciled_counts() -> None:
    """Test that readiness can never be constructed inconsistently with
    the accumulator's own reconciled counts -- readiness is always
    derived, never independently asserted."""
    with pytest.raises(InvalidOfflineE2EQualificationReportError):
        OfflineE2EQualificationReport(
            schema_version=OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION,
            plan_sha256=_PLAN_SHA256,
            plan_git_blob_sha1=_PLAN_BLOB,
            workload_sha256=_WORKLOAD_SHA256,
            distributed_provenance_schema_version="megb-03h2c3b1-distributed-provenance-v1",
            distributed_orchestration_schema_version="megb-03h2c3b2b2-distributed-orchestration-v3",
            fault_conformance_report_checksum=_FAULT_CONFORMANCE_CHECKSUM,
            run_context_checksum="e" * 64,
            qualification_identity_checksum="f" * 64,
            worker_topology_provisioning_class_counts=(("ON_DEMAND", 2),),
            worker_topology_region_counts=(("us-central1", 2),),
            worker_topology_machine_type_counts=(("n2-standard-4", 2),),
            admitted_count=0,
            completed_count=0,
            failed_count=0,
            retried_count=0,
            cancelled_count=0,
            duplicate_delivery_count=0,
            redelivery_count=0,
            budget_requested_cents_total=0,
            budget_finalized_cents_total=0,
            budget_released_cents_total=0,
            measured_peak_concurrency_personal=0,
            measured_peak_concurrency_generic=0,
            audit_delivered_count=0,
            audit_abandoned_count=0,
            audit_still_pending_count=0,
            queue_unacknowledged_count=0,
            serial_vs_distributed_equivalent=False,
            generic_concurrency4_equivalent=False,
            readiness=ReadinessClassification.OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3,
        )


def test_report_rejects_checksum_tampering() -> None:
    """Test report rejects checksum tampering."""
    report = _build()
    data = offline_e2e_qualification_report_to_dict(report)
    data["report_checksum"] = "0" * 64
    with pytest.raises(InvalidOfflineE2EQualificationReportError):
        offline_e2e_qualification_report_from_dict(data)


def test_report_rejects_stale_schema_version() -> None:
    """Test report rejects a stale/unknown schema_version."""
    report = _build()
    data = offline_e2e_qualification_report_to_dict(report)
    data["schema_version"] = "megb-03h2c3b2c-offline-e2e-qualification-v0"
    with pytest.raises(InvalidOfflineE2EQualificationReportError):
        offline_e2e_qualification_report_from_dict(data)


def test_report_rejects_unknown_readiness_identifier() -> None:
    """Test report rejects an unknown readiness string."""
    report = _build()
    data = offline_e2e_qualification_report_to_dict(report)
    data["readiness"] = "NOT_A_REAL_READINESS_VALUE"
    with pytest.raises(InvalidOfflineE2EQualificationReportError):
        offline_e2e_qualification_report_from_dict(data)


def test_report_rejects_unsorted_topology_histogram() -> None:
    """Test report rejects a topology histogram not sorted by label."""
    with pytest.raises(InvalidOfflineE2EQualificationReportError):
        _build(worker_topology_region_counts=(("us-east1", 1), ("us-central1", 1)))


def test_report_round_trips() -> None:
    """Test report round trips through to_dict/from_dict."""
    report = _build()
    data = offline_e2e_qualification_report_to_dict(report)
    rebuilt = offline_e2e_qualification_report_from_dict(data)
    assert rebuilt == report


def test_render_markdown_contains_readiness_and_key_fields() -> None:
    """Test render_markdown contains readiness and key safe fields."""
    report = _build()
    rendered = render_markdown(report)
    assert "OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3" in rendered
    assert "no H.2C.3D" in rendered
    assert str(report.admitted_count) in rendered
