"""MEGB-03H.2C.3B.3: offline tests for the safe, committed
CalibrationProvenanceReport (``src.distributed.calibration_provenance_report``).

Synthetic only -- no candidate code, HumanEval cases, oracle values,
Docker, or cloud resources anywhere in this file.
"""

import dataclasses

import pytest

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.calibration_provenance_report import (
    CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION,
    CalibrationProvenanceBlockerReason,
    CalibrationProvenanceReadiness,
    CalibrationProvenanceReport,
    InvalidCalibrationProvenanceReportError,
    build_calibration_provenance_report,
    calibration_provenance_report_from_dict,
    calibration_provenance_report_to_dict,
    compute_calibration_evidence_checksum,
)
from src.distributed.personal_policy import PERSONAL_BOOTSTRAP_MAX_WORKERS
from src.distributed.provenance import DISTRIBUTED_PROVENANCE_SCHEMA_VERSION, EnvironmentClass
from src.distributed.qualification_gate import ProvenanceGateFailureReason, ProvenanceGateReadiness

_MANIFEST_CHECKSUM = "1" * 64
_CALIBRATION_RUN_CONTEXT_CHECKSUM = "2" * 64
_WORKER_CHECKSUMS = ("3" * 64, "4" * 64)
_EVIDENCE_CHECKSUM = compute_calibration_evidence_checksum(("5" * 64,), ("6" * 64,))


def _build(**overrides: object) -> CalibrationProvenanceReport:
    fields: dict[str, object] = {
        "provenance_manifest_checksum": _MANIFEST_CHECKSUM,
        "calibration_run_context_checksum": _CALIBRATION_RUN_CONTEXT_CHECKSUM,
        "participating_worker_context_checksums": _WORKER_CHECKSUMS,
        "environment_class": EnvironmentClass.PERSONAL_BOOTSTRAP.value,
        "topology_region_counts": (("us-central1", 2),),
        "topology_machine_type_counts": (("n2-standard-4", 2),),
        "topology_provisioning_class_counts": (("ON_DEMAND", 2),),
        "intended_concurrency": 2,
        "measured_peak_concurrency": 2,
        "admitted_invocation_count": 2,
        "completed_invocation_count": 2,
        "invalid_invocation_count": 0,
        "incomplete_invocation_count": 0,
        "invocation_provenance_resolved": True,
        "task_reconciliation_passed": True,
        "qualification_gate_readiness": ProvenanceGateReadiness.READY.value,
        "qualification_gate_missing_dimensions": (),
        "calibration_evidence_checksum": _EVIDENCE_CHECKSUM,
    }
    fields.update(overrides)
    return build_calibration_provenance_report(**fields)  # type: ignore[arg-type]


def test_build_report_healthy_is_ready_for_3c() -> None:
    """A report built from fully-consistent, fully-reconciled facts
    reports readiness CALIBRATION_PROVENANCE_READY_FOR_3C."""
    report = _build()
    assert report.readiness == CalibrationProvenanceReadiness.CALIBRATION_PROVENANCE_READY_FOR_3C
    assert not report.blocker_reasons
    assert len(report.report_checksum) == 64


def test_report_round_trips() -> None:
    """Full-fidelity serialization round trips exactly."""
    report = _build()
    data = calibration_provenance_report_to_dict(report)
    rebuilt = calibration_provenance_report_from_dict(data)
    assert rebuilt == report


def test_current_schema_version() -> None:
    """Confirms the exact, intentional new schema-family identity. Bumped
    v1->v2 by the qualification-failure-semantics correction: v1 treated
    an excessive-but-valid measured_peak_concurrency as a construction
    error; v2 folds it into blocker_reasons like every other criterion."""
    assert (
        CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION
        == "megb-03h2c3b3-calibration-provenance-report-v2"
    )


@pytest.mark.parametrize(
    "overrides,expected_reason",
    [
        (
            {
                "qualification_gate_readiness": ProvenanceGateReadiness.BLOCKED.value,
                "qualification_gate_missing_dimensions": (
                    ProvenanceGateFailureReason.NOT_QUALIFICATION_INTENT.value,
                ),
            },
            ProvenanceGateFailureReason.NOT_QUALIFICATION_INTENT.value,
        ),
        (
            {"invocation_provenance_resolved": False},
            CalibrationProvenanceBlockerReason.INVOCATION_PROVENANCE_UNRESOLVED.value,
        ),
        (
            {"task_reconciliation_passed": False},
            CalibrationProvenanceBlockerReason.TASK_RECONCILIATION_FAILED.value,
        ),
        (
            {"incomplete_invocation_count": 1, "completed_invocation_count": 1},
            CalibrationProvenanceBlockerReason.INCOMPLETE_INVOCATION_EVIDENCE.value,
        ),
        (
            {"invalid_invocation_count": 1, "completed_invocation_count": 1},
            CalibrationProvenanceBlockerReason.INCOMPLETE_INVOCATION_EVIDENCE.value,
        ),
        (
            {"completed_invocation_count": 1, "incomplete_invocation_count": 1},
            CalibrationProvenanceBlockerReason.INCOMPLETE_INVOCATION_EVIDENCE.value,
        ),
    ],
)
def test_build_report_blocks_on_any_single_deviation(
    overrides: dict[str, object], expected_reason: str
) -> None:
    """Test that deviating from any single healthy fact yields
    BLOCKED_CALIBRATION_PROVENANCE with the exact expected blocker
    reason, never a silently-still-ready report."""
    report = _build(**overrides)
    assert report.readiness == CalibrationProvenanceReadiness.BLOCKED_CALIBRATION_PROVENANCE
    assert expected_reason in report.blocker_reasons


def test_smoke_intent_gate_blocked_cannot_qualify() -> None:
    """A manifest whose gate blocked on smoke intent (NOT_QUALIFICATION_INTENT)
    can never yield CALIBRATION_PROVENANCE_READY_FOR_3C here either."""
    report = _build(
        qualification_gate_readiness=ProvenanceGateReadiness.BLOCKED.value,
        qualification_gate_missing_dimensions=(
            ProvenanceGateFailureReason.NOT_QUALIFICATION_INTENT.value,
        ),
    )
    assert report.readiness == CalibrationProvenanceReadiness.BLOCKED_CALIBRATION_PROVENANCE
    assert (
        ProvenanceGateFailureReason.NOT_QUALIFICATION_INTENT.value in report.blocker_reasons
    )


def test_measured_peak_concurrency_exceeding_intended_blocks_not_raises() -> None:
    """A structurally valid measurement exceeding intended_concurrency is
    a failed qualification result, not malformed data: it must yield a
    valid, self-checksummed BLOCKED_CALIBRATION_PROVENANCE report --
    never a raised constructor error -- with the measured counts
    preserved as negative evidence."""
    three_workers = _WORKER_CHECKSUMS + ("7" * 64,)
    report = _build(
        participating_worker_context_checksums=three_workers,
        intended_concurrency=2,
        measured_peak_concurrency=3,
    )
    assert report.readiness == CalibrationProvenanceReadiness.BLOCKED_CALIBRATION_PROVENANCE
    assert (
        CalibrationProvenanceBlockerReason.MEASURED_CONCURRENCY_EXCEEDS_INTENDED.value
        in report.blocker_reasons
    )
    assert (
        CalibrationProvenanceBlockerReason.MEASURED_CONCURRENCY_EXCEEDS_ADMITTED_TOPOLOGY.value
        not in report.blocker_reasons
    )
    assert report.measured_peak_concurrency == 3
    assert report.intended_concurrency == 2
    assert len(report.report_checksum) == 64


def test_measured_peak_concurrency_exceeding_admitted_topology_blocks() -> None:
    """A measurement exceeding the admitted worker-topology size (the
    count of participating_worker_context_checksums, i.e. two workers by
    the default fixture) is likewise a failed qualification result, not
    a construction error -- distinct from exceeding intended_concurrency."""
    report = _build(intended_concurrency=10, measured_peak_concurrency=3)
    assert report.readiness == CalibrationProvenanceReadiness.BLOCKED_CALIBRATION_PROVENANCE
    assert (
        CalibrationProvenanceBlockerReason.MEASURED_CONCURRENCY_EXCEEDS_ADMITTED_TOPOLOGY.value
        in report.blocker_reasons
    )
    assert (
        CalibrationProvenanceBlockerReason.MEASURED_CONCURRENCY_EXCEEDS_INTENDED.value
        not in report.blocker_reasons
    )
    assert report.measured_peak_concurrency == 3


def test_measured_peak_concurrency_exceeding_personal_ceiling_blocks() -> None:
    """Personal qualification concurrency exceeding the
    PERSONAL_BOOTSTRAP_MAX_WORKERS ceiling (2) blocks rather than raises,
    even when intended concurrency itself is (incorrectly) claimed
    higher -- isolated from the other two concurrency checks by keeping
    the admitted worker-topology size equal to the measured value."""
    three_workers = _WORKER_CHECKSUMS + ("7" * 64,)
    report = _build(
        environment_class=EnvironmentClass.PERSONAL_BOOTSTRAP.value,
        participating_worker_context_checksums=three_workers,
        intended_concurrency=PERSONAL_BOOTSTRAP_MAX_WORKERS + 1,
        measured_peak_concurrency=PERSONAL_BOOTSTRAP_MAX_WORKERS + 1,
    )
    assert report.readiness == CalibrationProvenanceReadiness.BLOCKED_CALIBRATION_PROVENANCE
    assert (
        CalibrationProvenanceBlockerReason.PERSONAL_CONCURRENCY_CEILING_EXCEEDED.value
        in report.blocker_reasons
    )
    assert (
        CalibrationProvenanceBlockerReason.MEASURED_CONCURRENCY_EXCEEDS_INTENDED.value
        not in report.blocker_reasons
    )
    assert (
        CalibrationProvenanceBlockerReason.MEASURED_CONCURRENCY_EXCEEDS_ADMITTED_TOPOLOGY.value
        not in report.blocker_reasons
    )
    assert report.measured_peak_concurrency == PERSONAL_BOOTSTRAP_MAX_WORKERS + 1


def test_measured_peak_concurrency_above_personal_ceiling_allowed_non_personal() -> None:
    """The personal ceiling check is scoped to PERSONAL_BOOTSTRAP only --
    a non-personal (COMPANY_PLAYGROUND) environment may exceed it."""
    report = _build(
        environment_class=EnvironmentClass.COMPANY_PLAYGROUND.value,
        intended_concurrency=4,
        measured_peak_concurrency=4,
        admitted_invocation_count=4,
        completed_invocation_count=4,
    )
    assert report.measured_peak_concurrency == 4


def test_admitted_count_must_partition_exactly() -> None:
    """admitted_invocation_count must exactly equal
    completed+invalid+incomplete -- an inconsistent count set is a
    construction error, not merely a blocked readiness."""
    with pytest.raises(InvalidCalibrationProvenanceReportError):
        _build(admitted_invocation_count=5)


def test_report_rejects_tampered_checksum() -> None:
    """A report_checksum that does not match the recomputed value is
    rejected -- tampered or corrupted evidence."""
    report = _build()
    data = calibration_provenance_report_to_dict(report)
    data["report_checksum"] = "0" * 64
    with pytest.raises(InvalidCalibrationProvenanceReportError):
        calibration_provenance_report_from_dict(data)


def test_report_rejects_readiness_manually_altered() -> None:
    """readiness can never be forced to a value inconsistent with the
    recorded counts/flags/gate-state -- always derived, never
    independently caller-settable. Constructed directly (bypassing the
    build_ helper) to attempt exactly this."""
    with pytest.raises(InvalidCalibrationProvenanceReportError):
        CalibrationProvenanceReport(
            calibration_provenance_report_schema_version=(
                CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION
            ),
            checksum_algorithm_version="sha256-canonical-json-v1",
            distributed_provenance_schema_version=DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
            provenance_manifest_checksum=_MANIFEST_CHECKSUM,
            calibration_run_context_checksum=_CALIBRATION_RUN_CONTEXT_CHECKSUM,
            participating_worker_context_checksums=_WORKER_CHECKSUMS,
            environment_class=EnvironmentClass.PERSONAL_BOOTSTRAP.value,
            topology_region_counts=(("us-central1", 2),),
            topology_machine_type_counts=(("n2-standard-4", 2),),
            topology_provisioning_class_counts=(("ON_DEMAND", 2),),
            intended_concurrency=2,
            measured_peak_concurrency=2,
            admitted_invocation_count=2,
            completed_invocation_count=1,
            invalid_invocation_count=0,
            incomplete_invocation_count=1,
            invocation_provenance_resolved=True,
            task_reconciliation_passed=True,
            qualification_gate_readiness=ProvenanceGateReadiness.READY.value,
            qualification_gate_missing_dimensions=(),
            calibration_evidence_checksum=_EVIDENCE_CHECKSUM,
            # Manually forced READY despite incomplete evidence -- rejected.
            readiness=CalibrationProvenanceReadiness.CALIBRATION_PROVENANCE_READY_FOR_3C,
            blocker_reasons=(),
        )


def test_report_rejects_blocker_reasons_manually_altered() -> None:
    """blocker_reasons can never be forced to a value inconsistent with
    what the recorded facts imply."""
    with pytest.raises(InvalidCalibrationProvenanceReportError):
        CalibrationProvenanceReport(
            calibration_provenance_report_schema_version=(
                CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION
            ),
            checksum_algorithm_version="sha256-canonical-json-v1",
            distributed_provenance_schema_version=DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
            provenance_manifest_checksum=_MANIFEST_CHECKSUM,
            calibration_run_context_checksum=_CALIBRATION_RUN_CONTEXT_CHECKSUM,
            participating_worker_context_checksums=_WORKER_CHECKSUMS,
            environment_class=EnvironmentClass.PERSONAL_BOOTSTRAP.value,
            topology_region_counts=(("us-central1", 2),),
            topology_machine_type_counts=(("n2-standard-4", 2),),
            topology_provisioning_class_counts=(("ON_DEMAND", 2),),
            intended_concurrency=2,
            measured_peak_concurrency=2,
            admitted_invocation_count=2,
            completed_invocation_count=2,
            invalid_invocation_count=0,
            incomplete_invocation_count=0,
            invocation_provenance_resolved=True,
            task_reconciliation_passed=True,
            qualification_gate_readiness=ProvenanceGateReadiness.READY.value,
            qualification_gate_missing_dimensions=(),
            calibration_evidence_checksum=_EVIDENCE_CHECKSUM,
            readiness=CalibrationProvenanceReadiness.BLOCKED_CALIBRATION_PROVENANCE,
            # Fabricated blocker reason despite otherwise-healthy facts.
            blocker_reasons=(
                CalibrationProvenanceBlockerReason.TASK_RECONCILIATION_FAILED.value,
            ),
        )


def test_report_rejects_stale_schema_version() -> None:
    """A report stamped with an unknown schema version is rejected."""
    report = _build()
    data = calibration_provenance_report_to_dict(report)
    data["calibration_provenance_report_schema_version"] = (
        "megb-03h2c3b3-calibration-provenance-report-v0"
    )
    with pytest.raises(InvalidDistributedProvenanceError):
        calibration_provenance_report_from_dict(data)


def test_report_rejects_stale_v1_schema_version() -> None:
    """A report stamped with the superseded v1 schema version -- which
    predates the qualification-failure-semantics correction and could
    have hidden a failed concurrency criterion behind a raised
    constructor error -- is rejected outright, never silently accepted
    as current."""
    report = _build()
    data = calibration_provenance_report_to_dict(report)
    data["calibration_provenance_report_schema_version"] = (
        "megb-03h2c3b3-calibration-provenance-report-v1"
    )
    with pytest.raises(InvalidDistributedProvenanceError):
        calibration_provenance_report_from_dict(data)


def test_v2_round_trip_preserves_blocked_report_as_negative_evidence() -> None:
    """A BLOCKED_CALIBRATION_PROVENANCE report arising from valid
    evidence that simply failed a qualification criterion round-trips
    exactly under schema v2, proving it can be safely retained as
    negative evidence rather than discarded or hidden."""
    report = _build(intended_concurrency=10, measured_peak_concurrency=3)
    assert report.readiness == CalibrationProvenanceReadiness.BLOCKED_CALIBRATION_PROVENANCE
    data = calibration_provenance_report_to_dict(report)
    rebuilt = calibration_provenance_report_from_dict(data)
    assert rebuilt == report
    assert rebuilt.blocker_reasons == report.blocker_reasons
    assert rebuilt.measured_peak_concurrency == 3


def test_report_rejects_unsorted_topology_histogram() -> None:
    """Topology histograms must be sorted by key for deterministic
    serialization."""
    with pytest.raises(InvalidCalibrationProvenanceReportError):
        _build(topology_region_counts=(("us-east1", 1), ("us-central1", 1)))


def test_report_rejects_malformed_worker_checksum() -> None:
    """Every participating_worker_context_checksums entry must be
    sha256-hex shaped."""
    with pytest.raises(InvalidCalibrationProvenanceReportError):
        _build(participating_worker_context_checksums=("not-a-checksum",))


def test_compute_calibration_evidence_checksum_is_order_independent() -> None:
    """The evidence checksum is stable regardless of input ordering, but
    changes if the underlying evidence set changes."""
    checksum_a = compute_calibration_evidence_checksum(("1" * 64, "2" * 64), ("3" * 64,))
    checksum_b = compute_calibration_evidence_checksum(("2" * 64, "1" * 64), ("3" * 64,))
    checksum_c = compute_calibration_evidence_checksum(("1" * 64, "9" * 64), ("3" * 64,))
    assert checksum_a == checksum_b
    assert checksum_a != checksum_c


def test_report_has_no_unsafe_field() -> None:
    """Structurally excludes every forbidden concept -- no candidate
    content, protected identifier, generation command, or code
    revision (both exist only on the protected manifest, never here)."""
    forbidden_substrings = (
        "candidate",
        "credential",
        "password",
        "secret",
        "hostname",
        "instance_id",
        "container_id",
        "project_id",
        "path",
        "exception",
        "stdout",
        "stderr",
        "traceback",
        "message",
        "participant",
        "worker_id",
        "prompt",
        "source",
        "zone",
        "generation_command",
        "code_revision",
    )
    field_names = {field.name for field in dataclasses.fields(CalibrationProvenanceReport)}
    for name in field_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"field {name!r} matches forbidden {forbidden!r}"
