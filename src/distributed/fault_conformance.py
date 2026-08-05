"""MEGB-03H.2C.3B.2B.3: the safe, committed in-process fault-injection,
recovery, and resumption conformance report.

Mirrors ``src/reference/h2c2b_qualification_report.py``'s own
self-checksummed, versioned, explicitly-allowlisted pattern, applied to
conformance testing rather than telemetry measurement. Every field is a
closed-enum identifier, a count, a boolean, or a checksum -- never
candidate/result content, a raw exception message, a worker/participant
identifier, or an infrastructure identifier, and never free-form execution
log text. This report proves **in-process recovery only**; it makes no
durable-process, cross-host, or cloud-recovery claim of any kind -- see
this checkpoint's own frozen plan
(``docs/reference/megb-03h2c3b2b3-fault-injection-plan.md``), which this
report's ``plan_sha256``/``plan_git_blob_sha1`` fields reference by
checksum rather than embedding.

Deliberately independent of ``DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION``
(a different schema family, mirroring how
``DISTRIBUTED_PROVENANCE_SCHEMA_VERSION`` and
``DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`` are themselves two
independent, separately-versioned families) -- this report's own schema
evolves on its own counter."""

# This module's error class, nonempty-string validator, and self-checksum
# construction/rejection pattern intentionally mirror
# h2c2b_qualification_report.py's own already-established shape -- both are
# the same safe-report pattern applied to a different measurement/proof.
# Expected and accepted, not a defect.
# pylint: disable=duplicate-code

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from enum import Enum

FAULT_CONFORMANCE_REPORT_SCHEMA_VERSION = "megb-03h2c3b2b3-fault-conformance-v1"


class InvalidFaultConformanceReportError(ValueError):
    """Raised when a :class:`FaultConformanceReport`'s fields are
    internally inconsistent, or its self-checksum does not match its own
    recomputed contents."""


def _require_nonempty_str(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or value == "":
        raise InvalidFaultConformanceReportError(
            f"{field_name!r} must be a nonempty string, got {value!r}"
        )


class FaultPointId(str, Enum):
    """Closed set of fault-point identifiers -- exactly the fault matrix
    frozen in this checkpoint's own plan document. No free-form fault
    description is ever recorded; only one of these labels."""

    # Admission boundaries (A1-A5)
    A1_BEFORE_BUDGET_RESERVATION = "A1_BEFORE_BUDGET_RESERVATION"
    A2_AFTER_RESERVATION_BEFORE_WORK_CREATION = "A2_AFTER_RESERVATION_BEFORE_WORK_CREATION"
    A3_AFTER_WORK_CREATION_BEFORE_AUDIT_INTENT = "A3_AFTER_WORK_CREATION_BEFORE_AUDIT_INTENT"
    A4_AFTER_AUDIT_INTENT_BEFORE_PUBLICATION = "A4_AFTER_AUDIT_INTENT_BEFORE_PUBLICATION"
    A5_AFTER_PUBLICATION_BEFORE_RETURN = "A5_AFTER_PUBLICATION_BEFORE_RETURN"
    # Worker boundaries (W1-W9)
    W1_AFTER_DELIVERY_BEFORE_LEASE = "W1_AFTER_DELIVERY_BEFORE_LEASE"
    W2_AFTER_LEASE_BEFORE_EXECUTOR = "W2_AFTER_LEASE_BEFORE_EXECUTOR"
    W3_EXECUTOR_RETRYABLE_FAILURE = "W3_EXECUTOR_RETRYABLE_FAILURE"
    W4_EXECUTOR_NON_RETRYABLE_FAILURE = "W4_EXECUTOR_NON_RETRYABLE_FAILURE"
    W5_AFTER_ARTIFACT_WRITE_BEFORE_OUTBOX_INTENT = "W5_AFTER_ARTIFACT_WRITE_BEFORE_OUTBOX_INTENT"
    W6_AFTER_OUTBOX_INTENT_BEFORE_COMMIT = "W6_AFTER_OUTBOX_INTENT_BEFORE_COMMIT"
    W7_AFTER_COMMIT_BEFORE_FINALIZATION = "W7_AFTER_COMMIT_BEFORE_FINALIZATION"
    W8_AFTER_FINALIZATION_BEFORE_ACK = "W8_AFTER_FINALIZATION_BEFORE_ACK"
    W9_AFTER_ACK_BEFORE_RETURN = "W9_AFTER_ACK_BEFORE_RETURN"
    # Additional fault categories (C1-C13)
    C1_AUDIT_SINK_FAILURE = "C1_AUDIT_SINK_FAILURE"
    C2_OUTBOX_FULL = "C2_OUTBOX_FULL"
    C3_ORPHAN_INTENT_ABANDONED = "C3_ORPHAN_INTENT_ABANDONED"
    C4_QUEUE_DUPLICATE_REDELIVERY = "C4_QUEUE_DUPLICATE_REDELIVERY"
    C5_QUEUE_ACK_FAILURE = "C5_QUEUE_ACK_FAILURE"
    C6_LEASE_EXPIRY_REASSIGNMENT = "C6_LEASE_EXPIRY_REASSIGNMENT"
    C7_STALE_FUTURE_FENCING = "C7_STALE_FUTURE_FENCING"
    C8_CANCELLATION_AT_EACH_PHASE = "C8_CANCELLATION_AT_EACH_PHASE"
    C9_RETRY_SUCCESS_AND_EXHAUSTION = "C9_RETRY_SUCCESS_AND_EXHAUSTION"
    C10_CONFLICTING_RESULT_AND_COST = "C10_CONFLICTING_RESULT_AND_COST"
    C11_COORDINATOR_RECREATION = "C11_COORDINATOR_RECREATION"
    C12_RESERVATION_WITHOUT_WORK = "C12_RESERVATION_WITHOUT_WORK"
    C13_BUDGET_EXHAUSTION_ORPHAN_RECOVERY = "C13_BUDGET_EXHAUSTION_ORPHAN_RECOVERY"
    # Concurrency/race validation (R1-R10)
    R1_CONCURRENCY_ONE = "R1_CONCURRENCY_ONE"
    R2_CONCURRENCY_TWO = "R2_CONCURRENCY_TWO"
    R3_CONCURRENCY_FOUR = "R3_CONCURRENCY_FOUR"
    R4_PERSONAL_POLICY_REJECTS_ABOVE_TWO = "R4_PERSONAL_POLICY_REJECTS_ABOVE_TWO"
    R5_REVERSED_COMPLETION_ORDER = "R5_REVERSED_COMPLETION_ORDER"
    R6_DUPLICATE_DELIVERIES_RACING = "R6_DUPLICATE_DELIVERIES_RACING"
    R7_CANCELLATION_RACING_COMMIT = "R7_CANCELLATION_RACING_COMMIT"
    R8_LEASE_EXPIRY_RACING_COMMIT = "R8_LEASE_EXPIRY_RACING_COMMIT"
    R9_OUTBOX_DISPATCH_RACING_RECONCILIATION = "R9_OUTBOX_DISPATCH_RACING_RECONCILIATION"
    R10_CONCURRENT_RESERVATIONS_AT_CEILING = "R10_CONCURRENT_RESERVATIONS_AT_CEILING"


class InvariantId(str, Enum):
    """Closed set of invariant identifiers -- exactly the 13 invariants
    frozen in this checkpoint's own plan document, before any test result
    was observed."""

    I1_AT_MOST_ONE_COMMITTED_RESULT = "I1_AT_MOST_ONE_COMMITTED_RESULT"
    I2_NO_EXECUTION_AFTER_COMMIT = "I2_NO_EXECUTION_AFTER_COMMIT"
    I3_NO_STALE_LEASE_COMMIT = "I3_NO_STALE_LEASE_COMMIT"
    I4_NO_ACK_BEFORE_COMMIT = "I4_NO_ACK_BEFORE_COMMIT"
    I5_NO_DOUBLE_BUDGET_FINALIZATION = "I5_NO_DOUBLE_BUDGET_FINALIZATION"
    I6_NO_SILENT_BUDGET_LEAK = "I6_NO_SILENT_BUDGET_LEAK"
    I7_NO_LOST_QUEUE_VISIBLE_WORK = "I7_NO_LOST_QUEUE_VISIBLE_WORK"
    I8_NO_UNAUDITED_AUTHORITATIVE_TRANSITION = "I8_NO_UNAUDITED_AUTHORITATIVE_TRANSITION"
    I9_NO_PERMANENT_IMPOSSIBLE_INTENT_CAPACITY = "I9_NO_PERMANENT_IMPOSSIBLE_INTENT_CAPACITY"
    I10_NO_TERMINAL_EVIDENCE_ERASED = "I10_NO_TERMINAL_EVIDENCE_ERASED"
    I11_EVERY_ITEM_ENDS_DEFINED_DISPOSITION = "I11_EVERY_ITEM_ENDS_DEFINED_DISPOSITION"
    I12_DETERMINISTIC_RESULT_ORDERING = "I12_DETERMINISTIC_RESULT_ORDERING"
    I13_NO_UNSAFE_LEAKAGE = "I13_NO_UNSAFE_LEAKAGE"


class ReadinessClassification(str, Enum):
    """The only two legal readiness values this report may carry. Neither
    ever implies a durable-process, cross-host, or cloud-recovery
    claim -- both are scoped entirely to in-process recovery."""

    IN_PROCESS_RECOVERY_READY_FOR_B2C = "IN_PROCESS_RECOVERY_READY_FOR_B2C"
    BLOCKED_IN_PROCESS_RECOVERY = "BLOCKED_IN_PROCESS_RECOVERY"


@dataclass(frozen=True)
class ConformanceEntry:
    """One exercised (fault point, invariant) pair. ``attempt_count`` is
    the number of trials/repetitions this entry aggregates (a
    barrier-synchronized race repeated N times counts as N, a
    single-shot scenario counts as 1) -- never a free-form count of
    unrelated things."""

    fault_point: FaultPointId
    invariant: InvariantId
    passed: bool
    attempt_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.fault_point, FaultPointId):
            raise InvalidFaultConformanceReportError(
                f"fault_point must be a FaultPointId, got {self.fault_point!r}"
            )
        if not isinstance(self.invariant, InvariantId):
            raise InvalidFaultConformanceReportError(
                f"invariant must be an InvariantId, got {self.invariant!r}"
            )
        if not isinstance(self.passed, bool):
            raise InvalidFaultConformanceReportError(
                f"passed must be a bool, got {self.passed!r}"
            )
        if not isinstance(self.attempt_count, int) or isinstance(self.attempt_count, bool) or (
            self.attempt_count < 1
        ):
            raise InvalidFaultConformanceReportError(
                f"attempt_count must be a positive int, got {self.attempt_count!r}"
            )


def _conformance_entry_to_dict(entry: ConformanceEntry) -> dict[str, object]:
    return {
        "fault_point": entry.fault_point.value,
        "invariant": entry.invariant.value,
        "passed": entry.passed,
        "attempt_count": entry.attempt_count,
    }


def _conformance_entry_from_dict(data: dict[str, object]) -> ConformanceEntry:
    return ConformanceEntry(
        fault_point=FaultPointId(data["fault_point"]),
        invariant=InvariantId(data["invariant"]),
        passed=bool(data["passed"]),
        attempt_count=int(data["attempt_count"]),  # type: ignore[call-overload]
    )


@dataclass(frozen=True)
class FaultConformanceReport:  # pylint: disable=too-many-instance-attributes
    """The full, typed, versioned, self-checksummed MEGB-03H.2C.3B.2B.3
    fault-conformance report. ``report_checksum`` is always recomputed
    from every other field at construction time -- the same
    auto-compute-or-reject pattern already established throughout this
    project."""

    schema_version: str
    plan_sha256: str
    plan_git_blob_sha1: str
    entries: tuple[ConformanceEntry, ...]
    total_attempts: int
    passed_count: int
    failed_count: int
    readiness: ReadinessClassification
    report_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        for field_name in ("schema_version", "plan_sha256", "plan_git_blob_sha1"):
            _require_nonempty_str(self, field_name)
        if self.schema_version != FAULT_CONFORMANCE_REPORT_SCHEMA_VERSION:
            raise InvalidFaultConformanceReportError(
                f"schema_version {self.schema_version!r} does not match the version this "
                f"module implements ({FAULT_CONFORMANCE_REPORT_SCHEMA_VERSION!r})"
            )
        if not isinstance(self.entries, tuple) or not self.entries or not all(
            isinstance(entry, ConformanceEntry) for entry in self.entries
        ):
            raise InvalidFaultConformanceReportError(
                "entries must be a nonempty tuple of ConformanceEntry"
            )
        expected_total_attempts = sum(entry.attempt_count for entry in self.entries)
        if self.total_attempts != expected_total_attempts:
            raise InvalidFaultConformanceReportError(
                f"total_attempts {self.total_attempts!r} does not match the sum of each "
                f"entry's own attempt_count ({expected_total_attempts!r})"
            )
        expected_passed = sum(1 for entry in self.entries if entry.passed)
        expected_failed = len(self.entries) - expected_passed
        if self.passed_count != expected_passed or self.failed_count != expected_failed:
            raise InvalidFaultConformanceReportError(
                f"passed_count/failed_count ({self.passed_count}/{self.failed_count}) do not "
                f"match the entries' own pass/fail tally ({expected_passed}/{expected_failed})"
            )
        if not isinstance(self.readiness, ReadinessClassification):
            raise InvalidFaultConformanceReportError(
                f"readiness must be a ReadinessClassification, got {self.readiness!r}"
            )
        expected_readiness = (
            ReadinessClassification.IN_PROCESS_RECOVERY_READY_FOR_B2C
            if self.failed_count == 0
            else ReadinessClassification.BLOCKED_IN_PROCESS_RECOVERY
        )
        if self.readiness != expected_readiness:
            raise InvalidFaultConformanceReportError(
                f"readiness {self.readiness!r} is inconsistent with failed_count "
                f"{self.failed_count!r} (expected {expected_readiness!r}) -- readiness may "
                "never be reported independently of whether every entry passed"
            )
        expected_checksum = _compute_report_checksum(self)
        if self.report_checksum and self.report_checksum != expected_checksum:
            raise InvalidFaultConformanceReportError(
                f"report_checksum {self.report_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                "corrupted conformance report"
            )
        object.__setattr__(self, "report_checksum", expected_checksum)


FAULT_CONFORMANCE_REPORT_FIELD_NAMES = frozenset(
    field.name for field in dataclasses.fields(FaultConformanceReport)
)


def _report_payload(report: FaultConformanceReport) -> dict[str, object]:
    payload: dict[str, object] = {}
    for name in FAULT_CONFORMANCE_REPORT_FIELD_NAMES:
        if name == "report_checksum":
            continue
        value = getattr(report, name)
        if name == "entries":
            payload[name] = [_conformance_entry_to_dict(entry) for entry in value]
        elif name == "readiness":
            payload[name] = value.value
        else:
            payload[name] = value
    return payload


def _compute_report_checksum(report: FaultConformanceReport) -> str:
    canonical = json.dumps(_report_payload(report), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_fault_conformance_report(
    entries: list[ConformanceEntry], *, plan_sha256: str, plan_git_blob_sha1: str
) -> FaultConformanceReport:
    """Build a :class:`FaultConformanceReport` from every
    :class:`ConformanceEntry` the conformance suite recorded, deriving
    every aggregate field (and the readiness classification itself)
    purely from the entries -- never set independently, so a report can
    never claim readiness inconsistent with its own recorded matrix."""
    ordered = tuple(
        sorted(entries, key=lambda entry: (entry.fault_point.value, entry.invariant.value))
    )
    total_attempts = sum(entry.attempt_count for entry in ordered)
    passed_count = sum(1 for entry in ordered if entry.passed)
    failed_count = len(ordered) - passed_count
    readiness = (
        ReadinessClassification.IN_PROCESS_RECOVERY_READY_FOR_B2C
        if failed_count == 0
        else ReadinessClassification.BLOCKED_IN_PROCESS_RECOVERY
    )
    return FaultConformanceReport(
        schema_version=FAULT_CONFORMANCE_REPORT_SCHEMA_VERSION,
        plan_sha256=plan_sha256,
        plan_git_blob_sha1=plan_git_blob_sha1,
        entries=ordered,
        total_attempts=total_attempts,
        passed_count=passed_count,
        failed_count=failed_count,
        readiness=readiness,
    )


def fault_conformance_report_to_dict(report: FaultConformanceReport) -> dict[str, object]:
    """Serialize a conformance report. Output keys are exactly
    :data:`FAULT_CONFORMANCE_REPORT_FIELD_NAMES` -- nothing more, nothing
    less."""
    payload = _report_payload(report)
    payload["report_checksum"] = report.report_checksum
    return payload


def fault_conformance_report_from_dict(data: dict[str, object]) -> FaultConformanceReport:
    """Inverse of :func:`fault_conformance_report_to_dict`."""
    fields = {name: data[name] for name in FAULT_CONFORMANCE_REPORT_FIELD_NAMES}
    raw_entries: list[dict[str, object]] = data["entries"]  # type: ignore[assignment]
    fields["entries"] = tuple(_conformance_entry_from_dict(entry) for entry in raw_entries)
    fields["readiness"] = ReadinessClassification(fields["readiness"])
    return FaultConformanceReport(**fields)  # type: ignore[arg-type]


def render_markdown(report: FaultConformanceReport) -> str:
    """A concise, human-readable Markdown rendering of the same safe
    fields the JSON report carries -- nothing else."""
    lines = [
        "# MEGB-03H.2C.3B.2B.3 In-Process Fault-Injection, Recovery, and "
        "Resumption Conformance Report",
        "",
        f"- **Readiness:** `{report.readiness.value}`",
        "- **Scope:** in-process recovery only -- no durable-process, "
        "cross-host, or cloud-recovery claim is made.",
        f"- **Schema version:** `{report.schema_version}`",
        f"- **Report checksum:** `{report.report_checksum}`",
        (
            f"- **Frozen plan:** sha256 `{report.plan_sha256}`, git blob "
            f"`{report.plan_git_blob_sha1}`"
        ),
        f"- **Entries:** {len(report.entries)}, total attempts "
        f"{report.total_attempts}, passed {report.passed_count}, failed "
        f"{report.failed_count}",
        "",
        "## Fault/invariant matrix",
        "",
        "| Fault point | Invariant | Passed | Attempts |",
        "|---|---|---|---|",
    ]
    for entry in report.entries:
        lines.append(
            f"| `{entry.fault_point.value}` | `{entry.invariant.value}` | "
            f"{entry.passed} | {entry.attempt_count} |"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "FAULT_CONFORMANCE_REPORT_SCHEMA_VERSION",
    "InvalidFaultConformanceReportError",
    "FaultPointId",
    "InvariantId",
    "ReadinessClassification",
    "ConformanceEntry",
    "FaultConformanceReport",
    "FAULT_CONFORMANCE_REPORT_FIELD_NAMES",
    "build_fault_conformance_report",
    "fault_conformance_report_to_dict",
    "fault_conformance_report_from_dict",
    "render_markdown",
]
