"""MEGB-03H.2C.3B.2C: the safe, committed offline end-to-end synthetic
distributed qualification report.

Mirrors :mod:`~src.distributed.fault_conformance`'s own self-checksummed,
versioned, explicitly-allowlisted, anti-gaming pattern: every count here
is checked in ``__post_init__`` against the exact frozen expectation from
``docs/reference/megb-03h2c3b2c-offline-e2e-qualification-plan.md``'s own
8-item path-coverage workload, and ``readiness`` is always derived from
those checks -- never independently settable, so a report can never claim
readiness for a run that silently dropped, skipped, or fabricated an
outcome. This report proves the **offline, provider-neutral, in-process**
path only; it makes no H.2C.3D, GCP, durable-process, cross-host,
Docker/native-Linux-equivalence, calibration-provenance-completeness, or
real-scientific-result-validity claim of any kind."""

# This module's error class, checksum-tamper pattern, and derived-readiness
# discipline intentionally mirror fault_conformance.py's own already-
# established shape -- the same safe-report pattern applied to a different
# proof. Expected and accepted, not a defect.
# pylint: disable=duplicate-code

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from src.distributed.personal_policy import WorkloadClass
from src.distributed.provenance import DistributedRunIntent

# MEGB-03H.2C.3B.2C correction (v1->v2): v1 (never accepted -- superseded,
# preserved only in git history at commit edbda37) recorded only the
# qualification gate's own output checksums (run_context_checksum,
# qualification_identity_checksum) with no field ever checking that the
# *workload class actually used* was the qualification-candidate class,
# not the smoke class -- so a report could in principle claim readiness
# for a run whose run_intent satisfied the gate while its actual
# candidate metadata was WorkloadClass.SYNTHETIC_SMOKE (which must never
# qualify). v2 adds distributed_run_intent/qualifying_workload_class/
# qualification_gate_ready as explicit, safe (closed-enum-valued) fields,
# and qualification_workload_consistent as a fourth, wholly-derived
# field -- never caller-settable -- folded into readiness derivation.
OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION = "megb-03h2c3b2c-offline-e2e-qualification-v2"

_QUALIFYING_RUN_INTENT = DistributedRunIntent.QUALIFICATION_CANDIDATE.value
_QUALIFYING_WORKLOAD_CLASS = WorkloadClass.SYNTHETIC_QUALIFICATION_CANDIDATE.value
_VALID_RUN_INTENTS = frozenset(member.value for member in DistributedRunIntent)
_VALID_WORKLOAD_CLASSES = frozenset(member.value for member in WorkloadClass)

# Frozen expectations from this checkpoint's own plan (8-item path-coverage
# workload: e2e-01..e2e-08). See the plan document for the full mapping.
EXPECTED_ADMITTED_COUNT = 7
EXPECTED_COMPLETED_COUNT = 6
EXPECTED_FAILED_COUNT = 1
EXPECTED_RETRIED_COUNT = 1
EXPECTED_CANCELLED_COUNT = 1
EXPECTED_MINIMUM_DUPLICATE_DELIVERY_COUNT = 1
EXPECTED_MINIMUM_REDELIVERY_COUNT = 1
EXPECTED_AUDIT_ABANDONED_COUNT = 1


class InvalidOfflineE2EQualificationReportError(ValueError):
    """Raised when a :class:`OfflineE2EQualificationReport`'s fields are
    internally inconsistent, inconsistent with this checkpoint's own
    frozen workload expectations, or its self-checksum does not match its
    own recomputed contents."""


class ReadinessClassification(str, Enum):
    """The only two legal readiness values this report may carry. Neither
    ever implies H.2C.3D readiness, GCP readiness, durable-process
    recovery, cross-host recovery, Docker/native-Linux equivalence,
    calibration-provenance completeness, or real-scientific-result
    validity -- both are scoped entirely to the offline, in-process
    coordinator/worker path."""

    OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3 = "OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3"
    BLOCKED_OFFLINE_DISTRIBUTED_PATH = "BLOCKED_OFFLINE_DISTRIBUTED_PATH"


def _require_nonempty_str(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or value == "":
        raise InvalidOfflineE2EQualificationReportError(
            f"{field_name!r} must be a nonempty string, got {value!r}"
        )


def _require_non_negative_int(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvalidOfflineE2EQualificationReportError(
            f"{field_name!r} must be a non-negative int, got {value!r}"
        )


def _require_bool(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, bool):
        raise InvalidOfflineE2EQualificationReportError(
            f"{field_name!r} must be a bool, got {value!r}"
        )


def _require_count_histogram(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, tuple) or not all(
        isinstance(pair, tuple)
        and len(pair) == 2
        and isinstance(pair[0], str)
        and isinstance(pair[1], int)
        and not isinstance(pair[1], bool)
        and pair[1] > 0
        for pair in value
    ):
        raise InvalidOfflineE2EQualificationReportError(
            f"{field_name!r} must be a tuple of (str, positive int) pairs, got {value!r}"
        )
    labels = [pair[0] for pair in value]
    if labels != sorted(labels):
        raise InvalidOfflineE2EQualificationReportError(f"{field_name!r} must be sorted by label")


@dataclass(frozen=True)
class OfflineE2EQualificationReport:  # pylint: disable=too-many-instance-attributes
    """The full, typed, versioned, self-checksummed MEGB-03H.2C.3B.2C
    offline end-to-end qualification report. ``report_checksum`` is
    always recomputed from every other field at construction time; every
    count is checked against this checkpoint's own frozen workload
    expectations; ``readiness`` is always derived, never independently
    settable."""

    schema_version: str
    plan_sha256: str
    plan_git_blob_sha1: str
    workload_sha256: str
    distributed_provenance_schema_version: str
    distributed_orchestration_schema_version: str
    fault_conformance_report_checksum: str
    run_context_checksum: str
    qualification_identity_checksum: str
    distributed_run_intent: str
    qualifying_workload_class: str
    qualification_gate_ready: bool
    worker_topology_provisioning_class_counts: tuple[tuple[str, int], ...]
    worker_topology_region_counts: tuple[tuple[str, int], ...]
    worker_topology_machine_type_counts: tuple[tuple[str, int], ...]
    admitted_count: int
    completed_count: int
    failed_count: int
    retried_count: int
    cancelled_count: int
    duplicate_delivery_count: int
    redelivery_count: int
    budget_requested_cents_total: int
    budget_finalized_cents_total: int
    budget_released_cents_total: int
    measured_peak_concurrency_personal: int
    measured_peak_concurrency_generic: int
    audit_delivered_count: int
    audit_abandoned_count: int
    audit_still_pending_count: int
    queue_unacknowledged_count: int
    serial_vs_distributed_equivalent: bool
    generic_concurrency4_equivalent: bool
    readiness: ReadinessClassification
    qualification_workload_consistent: bool | None = None
    report_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        for field_name in (
            "schema_version",
            "plan_sha256",
            "plan_git_blob_sha1",
            "workload_sha256",
            "distributed_provenance_schema_version",
            "distributed_orchestration_schema_version",
            "fault_conformance_report_checksum",
            "run_context_checksum",
            "qualification_identity_checksum",
            "distributed_run_intent",
            "qualifying_workload_class",
        ):
            _require_nonempty_str(self, field_name)
        if self.schema_version != OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION:
            raise InvalidOfflineE2EQualificationReportError(
                f"schema_version {self.schema_version!r} does not match the version this "
                f"module implements ({OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION!r})"
            )
        if self.distributed_run_intent not in _VALID_RUN_INTENTS:
            raise InvalidOfflineE2EQualificationReportError(
                f"distributed_run_intent {self.distributed_run_intent!r} is not one of "
                f"{sorted(_VALID_RUN_INTENTS)!r}"
            )
        if self.qualifying_workload_class not in _VALID_WORKLOAD_CLASSES:
            raise InvalidOfflineE2EQualificationReportError(
                f"qualifying_workload_class {self.qualifying_workload_class!r} is not one of "
                f"{sorted(_VALID_WORKLOAD_CLASSES)!r}"
            )
        _require_bool(self, "qualification_gate_ready")
        for field_name in (
            "worker_topology_provisioning_class_counts",
            "worker_topology_region_counts",
            "worker_topology_machine_type_counts",
        ):
            _require_count_histogram(self, field_name)
        for field_name in (
            "admitted_count",
            "completed_count",
            "failed_count",
            "retried_count",
            "cancelled_count",
            "duplicate_delivery_count",
            "redelivery_count",
            "budget_requested_cents_total",
            "budget_finalized_cents_total",
            "budget_released_cents_total",
            "measured_peak_concurrency_personal",
            "measured_peak_concurrency_generic",
            "audit_delivered_count",
            "audit_abandoned_count",
            "audit_still_pending_count",
            "queue_unacknowledged_count",
        ):
            _require_non_negative_int(self, field_name)
        for field_name in ("serial_vs_distributed_equivalent", "generic_concurrency4_equivalent"):
            _require_bool(self, field_name)

        frozen_workload_satisfied = (
            self.admitted_count == EXPECTED_ADMITTED_COUNT
            and self.completed_count == EXPECTED_COMPLETED_COUNT
            and self.failed_count == EXPECTED_FAILED_COUNT
            and self.retried_count == EXPECTED_RETRIED_COUNT
            and self.cancelled_count == EXPECTED_CANCELLED_COUNT
            and self.duplicate_delivery_count >= EXPECTED_MINIMUM_DUPLICATE_DELIVERY_COUNT
            and self.redelivery_count >= EXPECTED_MINIMUM_REDELIVERY_COUNT
            and self.audit_abandoned_count == EXPECTED_AUDIT_ABANDONED_COUNT
        )
        reconciliation_clean = (
            self.audit_still_pending_count == 0
            and self.queue_unacknowledged_count == 0
            and self.budget_requested_cents_total
            == self.budget_finalized_cents_total + self.budget_released_cents_total
        )
        # MEGB-03H.2C.3B.2C correction (v2): qualification_workload_consistent
        # is wholly derived here -- never caller-settable -- from the run's
        # own intent, the workload class its candidate metadata actually
        # used, and the qualification gate's own readiness. A run whose
        # gate READY determination is real but whose candidate metadata
        # was WorkloadClass.SYNTHETIC_SMOKE (or any run_intent other than
        # QUALIFICATION_CANDIDATE) can never be consistent, and this
        # report's own overall readiness can then never claim
        # OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3 regardless of every other
        # count reconciling.
        expected_workload_consistent = (
            self.qualification_gate_ready
            and self.distributed_run_intent == _QUALIFYING_RUN_INTENT
            and self.qualifying_workload_class == _QUALIFYING_WORKLOAD_CLASS
        )
        if (
            self.qualification_workload_consistent is not None
            and self.qualification_workload_consistent != expected_workload_consistent
        ):
            raise InvalidOfflineE2EQualificationReportError(
                f"qualification_workload_consistent {self.qualification_workload_consistent!r} "
                f"is inconsistent with the recorded run_intent/workload_class/gate-readiness "
                f"(expected {expected_workload_consistent!r}) -- never independently settable"
            )
        object.__setattr__(self, "qualification_workload_consistent", expected_workload_consistent)

        expected_ready = (
            frozen_workload_satisfied
            and reconciliation_clean
            and self.serial_vs_distributed_equivalent
            and self.generic_concurrency4_equivalent
            and expected_workload_consistent
        )
        if not isinstance(self.readiness, ReadinessClassification):
            raise InvalidOfflineE2EQualificationReportError(
                f"readiness must be a ReadinessClassification, got {self.readiness!r}"
            )
        expected_readiness = (
            ReadinessClassification.OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3
            if expected_ready
            else ReadinessClassification.BLOCKED_OFFLINE_DISTRIBUTED_PATH
        )
        if self.readiness != expected_readiness:
            raise InvalidOfflineE2EQualificationReportError(
                f"readiness {self.readiness!r} is inconsistent with the reconciled counts, "
                f"equivalence results, and run-intent/workload-class/gate consistency (expected "
                f"{expected_readiness!r}) -- readiness may never be reported independently of "
                "the frozen workload's own outcome"
            )

        expected_checksum = _compute_report_checksum(self)
        if self.report_checksum and self.report_checksum != expected_checksum:
            raise InvalidOfflineE2EQualificationReportError(
                f"report_checksum {self.report_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                "corrupted qualification report"
            )
        object.__setattr__(self, "report_checksum", expected_checksum)


OFFLINE_E2E_QUALIFICATION_REPORT_FIELD_NAMES = frozenset(
    field.name for field in dataclasses.fields(OfflineE2EQualificationReport)
)


def _report_payload(report: OfflineE2EQualificationReport) -> dict[str, object]:
    payload: dict[str, object] = {}
    for name in OFFLINE_E2E_QUALIFICATION_REPORT_FIELD_NAMES:
        if name == "report_checksum":
            continue
        value = getattr(report, name)
        payload[name] = value.value if name == "readiness" else value
    return payload


def _compute_report_checksum(report: OfflineE2EQualificationReport) -> str:
    canonical = json.dumps(_report_payload(report), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_offline_e2e_qualification_report(  # pylint: disable=too-many-arguments,too-many-locals
    *,
    plan_sha256: str,
    plan_git_blob_sha1: str,
    workload_sha256: str,
    distributed_provenance_schema_version: str,
    distributed_orchestration_schema_version: str,
    fault_conformance_report_checksum: str,
    accumulator: object,
) -> OfflineE2EQualificationReport:
    """Build a :class:`OfflineE2EQualificationReport` from every count the
    calling suite's own tests accumulated, deriving ``readiness`` purely
    from those counts -- never set independently. ``accumulator`` is any
    object exposing the report's own count/checksum/bool attributes by
    name (deliberately untyped here so this production module never
    imports a test-only type; the caller's own test-harness accumulator
    dataclass satisfies this structurally)."""
    field_names = (
        "run_context_checksum",
        "qualification_identity_checksum",
        "distributed_run_intent",
        "qualifying_workload_class",
        "qualification_gate_ready",
        "worker_topology_provisioning_class_counts",
        "worker_topology_region_counts",
        "worker_topology_machine_type_counts",
        "admitted_count",
        "completed_count",
        "failed_count",
        "retried_count",
        "cancelled_count",
        "duplicate_delivery_count",
        "redelivery_count",
        "budget_requested_cents_total",
        "budget_finalized_cents_total",
        "budget_released_cents_total",
        "measured_peak_concurrency_personal",
        "measured_peak_concurrency_generic",
        "audit_delivered_count",
        "audit_abandoned_count",
        "audit_still_pending_count",
        "queue_unacknowledged_count",
        "serial_vs_distributed_equivalent",
        "generic_concurrency4_equivalent",
    )
    accumulated = {name: getattr(accumulator, name) for name in field_names}

    frozen_workload_satisfied = (
        accumulated["admitted_count"] == EXPECTED_ADMITTED_COUNT
        and accumulated["completed_count"] == EXPECTED_COMPLETED_COUNT
        and accumulated["failed_count"] == EXPECTED_FAILED_COUNT
        and accumulated["retried_count"] == EXPECTED_RETRIED_COUNT
        and accumulated["cancelled_count"] == EXPECTED_CANCELLED_COUNT
        and accumulated["duplicate_delivery_count"] >= EXPECTED_MINIMUM_DUPLICATE_DELIVERY_COUNT
        and accumulated["redelivery_count"] >= EXPECTED_MINIMUM_REDELIVERY_COUNT
        and accumulated["audit_abandoned_count"] == EXPECTED_AUDIT_ABANDONED_COUNT
    )
    reconciliation_clean = (
        accumulated["audit_still_pending_count"] == 0
        and accumulated["queue_unacknowledged_count"] == 0
        and accumulated["budget_requested_cents_total"]
        == accumulated["budget_finalized_cents_total"] + accumulated["budget_released_cents_total"]
    )
    workload_consistent = (
        bool(accumulated["qualification_gate_ready"])
        and accumulated["distributed_run_intent"] == _QUALIFYING_RUN_INTENT
        and accumulated["qualifying_workload_class"] == _QUALIFYING_WORKLOAD_CLASS
    )
    expected_ready = (
        frozen_workload_satisfied
        and reconciliation_clean
        and bool(accumulated["serial_vs_distributed_equivalent"])
        and bool(accumulated["generic_concurrency4_equivalent"])
        and workload_consistent
    )
    readiness = (
        ReadinessClassification.OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3
        if expected_ready
        else ReadinessClassification.BLOCKED_OFFLINE_DISTRIBUTED_PATH
    )
    return OfflineE2EQualificationReport(
        schema_version=OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION,
        plan_sha256=plan_sha256,
        plan_git_blob_sha1=plan_git_blob_sha1,
        workload_sha256=workload_sha256,
        distributed_provenance_schema_version=distributed_provenance_schema_version,
        distributed_orchestration_schema_version=distributed_orchestration_schema_version,
        fault_conformance_report_checksum=fault_conformance_report_checksum,
        readiness=readiness,
        **accumulated,
    )


def offline_e2e_qualification_report_to_dict(
    report: OfflineE2EQualificationReport,
) -> dict[str, object]:
    """Serialize a qualification report. Output keys are exactly
    :data:`OFFLINE_E2E_QUALIFICATION_REPORT_FIELD_NAMES` -- nothing more,
    nothing less."""
    payload = _report_payload(report)
    payload["report_checksum"] = report.report_checksum
    return payload


def offline_e2e_qualification_report_from_dict(
    data: dict[str, object],
) -> OfflineE2EQualificationReport:
    """Inverse of :func:`offline_e2e_qualification_report_to_dict`."""
    fields = {name: data[name] for name in OFFLINE_E2E_QUALIFICATION_REPORT_FIELD_NAMES}
    for name in (
        "worker_topology_provisioning_class_counts",
        "worker_topology_region_counts",
        "worker_topology_machine_type_counts",
    ):
        raw = fields[name]
        if not isinstance(raw, (list, tuple)):
            raise InvalidOfflineE2EQualificationReportError(f"{name!r} must be a list of pairs")
        fields[name] = tuple((str(pair[0]), int(pair[1])) for pair in raw)
    readiness_value = fields["readiness"]
    try:
        fields["readiness"] = ReadinessClassification(readiness_value)
    except ValueError as exc:
        raise InvalidOfflineE2EQualificationReportError(
            f"unknown readiness identifier: {exc}"
        ) from exc
    for name in (
        "admitted_count",
        "completed_count",
        "failed_count",
        "retried_count",
        "cancelled_count",
        "duplicate_delivery_count",
        "redelivery_count",
        "budget_requested_cents_total",
        "budget_finalized_cents_total",
        "budget_released_cents_total",
        "measured_peak_concurrency_personal",
        "measured_peak_concurrency_generic",
        "audit_delivered_count",
        "audit_abandoned_count",
        "audit_still_pending_count",
        "queue_unacknowledged_count",
    ):
        value = fields[name]
        if not isinstance(value, int) or isinstance(value, bool):
            raise InvalidOfflineE2EQualificationReportError(f"{name!r} must be an int")
    for name in (
        "serial_vs_distributed_equivalent",
        "generic_concurrency4_equivalent",
        "qualification_gate_ready",
    ):
        if not isinstance(fields[name], bool):
            raise InvalidOfflineE2EQualificationReportError(f"{name!r} must be a bool")
    consistent = fields["qualification_workload_consistent"]
    if consistent is not None and not isinstance(consistent, bool):
        raise InvalidOfflineE2EQualificationReportError(
            "'qualification_workload_consistent' must be a bool or null"
        )
    return OfflineE2EQualificationReport(**fields)  # type: ignore[arg-type]


def render_markdown(report: OfflineE2EQualificationReport) -> str:
    """A concise, human-readable Markdown rendering of the same safe
    fields the JSON report carries -- nothing else."""
    lines = [
        "# MEGB-03H.2C.3B.2C Offline End-to-End Synthetic Distributed "
        "Qualification Report",
        "",
        f"- **Readiness:** `{report.readiness.value}`",
        "- **Scope:** offline, provider-neutral, in-process coordinator/"
        "worker path only -- no H.2C.3D, GCP, durable-process, "
        "cross-host, Docker/native-Linux-equivalence, calibration-"
        "provenance-completeness, or real-scientific-result-validity "
        "claim is made.",
        f"- **Schema version:** `{report.schema_version}`",
        f"- **Report checksum:** `{report.report_checksum}`",
        f"- **Frozen plan:** sha256 `{report.plan_sha256}`, git blob "
        f"`{report.plan_git_blob_sha1}`",
        f"- **Frozen workload:** sha256 `{report.workload_sha256}`",
        f"- **Fault-conformance report referenced:** checksum "
        f"`{report.fault_conformance_report_checksum}`",
        "",
        "## Run-intent / workload-class / gate consistency",
        "",
        f"- distributed_run_intent: `{report.distributed_run_intent}`",
        f"- qualifying_workload_class: `{report.qualifying_workload_class}`",
        f"- qualification_gate_ready: {report.qualification_gate_ready}",
        f"- qualification_workload_consistent: {report.qualification_workload_consistent}",
        "",
        "## Path-coverage counts",
        "",
        f"- admitted: {report.admitted_count}, completed: {report.completed_count}, "
        f"failed: {report.failed_count}, retried: {report.retried_count}, "
        f"cancelled: {report.cancelled_count}",
        f"- duplicate deliveries: {report.duplicate_delivery_count}, "
        f"redeliveries: {report.redelivery_count}",
        "",
        "## Budget reconciliation (integer cents)",
        "",
        f"- requested: {report.budget_requested_cents_total}, finalized: "
        f"{report.budget_finalized_cents_total}, released: "
        f"{report.budget_released_cents_total}",
        "",
        "## Concurrency and equivalence",
        "",
        f"- measured peak concurrency (personal): "
        f"{report.measured_peak_concurrency_personal}",
        f"- measured peak concurrency (generic, non-personal): "
        f"{report.measured_peak_concurrency_generic}",
        f"- serial-vs-distributed equivalence: "
        f"{report.serial_vs_distributed_equivalent}",
        f"- generic concurrency-4 equivalence: "
        f"{report.generic_concurrency4_equivalent}",
        "",
        "## Audit and queue reconciliation",
        "",
        f"- audit delivered: {report.audit_delivered_count}, abandoned: "
        f"{report.audit_abandoned_count}, still pending: "
        f"{report.audit_still_pending_count}",
        f"- queue unacknowledged: {report.queue_unacknowledged_count}",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION",
    "EXPECTED_ADMITTED_COUNT",
    "EXPECTED_COMPLETED_COUNT",
    "EXPECTED_FAILED_COUNT",
    "EXPECTED_RETRIED_COUNT",
    "EXPECTED_CANCELLED_COUNT",
    "EXPECTED_MINIMUM_DUPLICATE_DELIVERY_COUNT",
    "EXPECTED_MINIMUM_REDELIVERY_COUNT",
    "EXPECTED_AUDIT_ABANDONED_COUNT",
    "InvalidOfflineE2EQualificationReportError",
    "ReadinessClassification",
    "OfflineE2EQualificationReport",
    "OFFLINE_E2E_QUALIFICATION_REPORT_FIELD_NAMES",
    "build_offline_e2e_qualification_report",
    "offline_e2e_qualification_report_to_dict",
    "offline_e2e_qualification_report_from_dict",
    "render_markdown",
]
