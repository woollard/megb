"""MEGB-03H.2C.3B.3: the safe, committed calibration-provenance
qualification-evidence report.

Binds (all by checksum/plain-safe-value only -- this module never
imports ``src.reference``, per this package's own layering rule; the
caller, which does import both ``src.reference`` and ``src.distributed``,
is responsible for computing every boolean/count field from a real
reconciliation pass and passing the results in):

* the distributed-provenance manifest checksum;
* the calibration run-context checksum;
* the participating worker-context checksums;
* a safe, coarse topology histogram;
* intended vs. actual measured peak concurrency;
* admitted/completed/invalid/incomplete invocation counts;
* whether every invocation's worker provenance resolved, and whether
  calibration task-evaluation reconciliation passed;
* the manifest's own qualification-gate readiness/missing-dimensions;
* a calibration-evidence ("trace") checksum and this report's own
  self-checksum.

Mirrors ``src.distributed.offline_e2e_qualification_report``'s own
established safe-report pattern exactly: ``readiness`` and
``blocker_reasons`` are always derived by
:func:`build_calibration_provenance_report`, never independently
caller-settable -- direct dataclass construction validates a caller-
supplied value against the recomputed one and rejects any mismatch.

Readiness this report may claim is exactly one of
:class:`CalibrationProvenanceReadiness`'s two values. Neither implies
GCP readiness, H.2C.3C credential-boundary readiness, or real
scientific-result validity -- both are scoped entirely to the offline
calibration-provenance evidence chain proven by this checkpoint.

**Measured peak concurrency is genuine evidence, never a caller-supplied
provenance label -- but a valid measurement that simply exceeds a
criterion is a failed qualification result, not malformed data.**
A structurally valid ``measured_peak_concurrency`` that exceeds
``intended_concurrency``, exceeds the admitted worker-topology size (the
count of ``participating_worker_context_checksums``), or -- under
``EnvironmentClass.PERSONAL_BOOTSTRAP`` -- exceeds
:data:`~src.distributed.personal_policy.PERSONAL_BOOTSTRAP_MAX_WORKERS`,
never raises a construction error. Each instead folds into
``blocker_reasons``/``readiness`` exactly like every other qualification
criterion, producing a valid, self-checksummed
``BLOCKED_CALIBRATION_PROVENANCE`` report that safely retains the
measured counts as negative evidence. Only genuine structural/integrity
defects (unsupported schema version, checksum tampering, a malformed or
out-of-range count, an inconsistent count partition, an unsafe field) are
construction errors.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    InvalidDistributedProvenanceError,
    require_non_negative_int as _require_non_negative_int,
    require_nonempty_str_fields as _require_nonempty_str_fields,
    require_sha256_hex as _require_sha256_hex,
    sha256_of as _sha256_of,
)
from src.distributed.personal_policy import PERSONAL_BOOTSTRAP_MAX_WORKERS
from src.distributed.provenance import DISTRIBUTED_PROVENANCE_SCHEMA_VERSION, EnvironmentClass
from src.distributed.qualification_gate import ProvenanceGateFailureReason, ProvenanceGateReadiness

CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION = "megb-03h2c3b3-calibration-provenance-report-v2"


class InvalidCalibrationProvenanceReportError(InvalidDistributedProvenanceError):
    """Raised when a :class:`CalibrationProvenanceReport`'s fields are
    structurally invalid -- an unsupported schema version, a tampered or
    corrupted self-checksum, a malformed or out-of-range count, an
    inconsistent invocation-count partition, or a ``blocker_reasons``/
    ``readiness`` value inconsistent with the recomputed derivation.
    Never raised for a merely-failed qualification criterion (e.g. an
    excessive but structurally valid measured peak concurrency) -- those
    instead produce a valid ``BLOCKED_CALIBRATION_PROVENANCE`` report."""


class CalibrationProvenanceReadiness(str, Enum):
    """The only two legal readiness values this report may carry.
    Neither ever implies GCP readiness, H.2C.3C credential-boundary
    readiness, or real scientific-result validity."""

    CALIBRATION_PROVENANCE_READY_FOR_3C = "CALIBRATION_PROVENANCE_READY_FOR_3C"
    BLOCKED_CALIBRATION_PROVENANCE = "BLOCKED_CALIBRATION_PROVENANCE"


class CalibrationProvenanceBlockerReason(str, Enum):
    """Closed, safe, non-sensitive reason codes for the calibration-
    specific ways readiness can block, distinct from
    :class:`~src.distributed.qualification_gate.ProvenanceGateFailureReason`
    (which this report also folds in when the manifest's own gate is not
    READY).

    The three ``*_CONCURRENCY_*`` members below were added in schema v2:
    each covers a structurally valid measurement that simply fails a
    qualification criterion -- never a construction-time error (see
    :class:`InvalidCalibrationProvenanceReportError`)."""

    INVOCATION_PROVENANCE_UNRESOLVED = "INVOCATION_PROVENANCE_UNRESOLVED"
    TASK_RECONCILIATION_FAILED = "TASK_RECONCILIATION_FAILED"
    INCOMPLETE_INVOCATION_EVIDENCE = "INCOMPLETE_INVOCATION_EVIDENCE"
    MEASURED_CONCURRENCY_EXCEEDS_INTENDED = "MEASURED_CONCURRENCY_EXCEEDS_INTENDED"
    MEASURED_CONCURRENCY_EXCEEDS_ADMITTED_TOPOLOGY = (
        "MEASURED_CONCURRENCY_EXCEEDS_ADMITTED_TOPOLOGY"
    )
    PERSONAL_CONCURRENCY_CEILING_EXCEEDED = "PERSONAL_CONCURRENCY_CEILING_EXCEEDED"


_VALID_GATE_READINESS = frozenset(member.value for member in ProvenanceGateReadiness)
_VALID_GATE_FAILURE_REASONS = frozenset(member.value for member in ProvenanceGateFailureReason)
_VALID_BLOCKER_REASONS = frozenset(
    member.value for member in ProvenanceGateFailureReason
) | frozenset(member.value for member in CalibrationProvenanceBlockerReason)


_SHA256_HEX_LENGTH = 64
_SHA256_HEX_ALPHABET = frozenset("0123456789abcdef")


def _require_sha256_hex_value(value: str, label: str) -> None:
    """Validate a bare string value (not read via getattr) is a
    64-character lowercase hex sha256 digest -- used for each entry of
    ``participating_worker_context_checksums``, where
    :func:`~src.distributed._checksums.require_sha256_hex`'s own
    getattr-based field-name contract does not fit a tuple element."""
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_HEX_LENGTH
        or not set(value) <= _SHA256_HEX_ALPHABET
    ):
        raise InvalidCalibrationProvenanceReportError(
            f"{label} must be a 64-character lowercase hex sha256 digest, got {value!r}"
        )


def _require_histogram(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, tuple) or not all(
        isinstance(pair, tuple)
        and len(pair) == 2
        and isinstance(pair[0], str)
        and pair[0]
        and isinstance(pair[1], int)
        and not isinstance(pair[1], bool)
        and pair[1] > 0
        for pair in value
    ):
        raise InvalidCalibrationProvenanceReportError(
            f"{field_name!r} must be a tuple of (nonempty str, positive int) pairs, got {value!r}"
        )
    keys = [pair[0] for pair in value]
    if keys != sorted(keys):
        raise InvalidCalibrationProvenanceReportError(f"{field_name!r} must be sorted by key")


@dataclass(frozen=True)
class CalibrationProvenanceReport:  # pylint: disable=too-many-instance-attributes
    """The full, typed, versioned, self-checksummed MEGB-03H.2C.3B.3
    calibration-provenance qualification-evidence report. Every field is
    either a closed-enum value, a content-bound checksum, a coarse safe
    histogram, or a plain non-negative count -- never candidate content,
    raw exception text, or a protected identifier."""

    calibration_provenance_report_schema_version: str
    checksum_algorithm_version: str
    distributed_provenance_schema_version: str
    provenance_manifest_checksum: str
    calibration_run_context_checksum: str
    participating_worker_context_checksums: tuple[str, ...]
    environment_class: str
    topology_region_counts: tuple[tuple[str, int], ...]
    topology_machine_type_counts: tuple[tuple[str, int], ...]
    topology_provisioning_class_counts: tuple[tuple[str, int], ...]
    intended_concurrency: int
    measured_peak_concurrency: int
    admitted_invocation_count: int
    completed_invocation_count: int
    invalid_invocation_count: int
    incomplete_invocation_count: int
    invocation_provenance_resolved: bool
    task_reconciliation_passed: bool
    qualification_gate_readiness: str
    qualification_gate_missing_dimensions: tuple[str, ...]
    calibration_evidence_checksum: str
    readiness: CalibrationProvenanceReadiness
    blocker_reasons: tuple[str, ...]
    report_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        if (
            self.calibration_provenance_report_schema_version
            != CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION
        ):
            raise InvalidCalibrationProvenanceReportError(
                f"calibration_provenance_report_schema_version "
                f"{self.calibration_provenance_report_schema_version!r} does not match the "
                f"version this module implements "
                f"({CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION!r})"
            )
        if self.checksum_algorithm_version != CHECKSUM_ALGORITHM_VERSION:
            raise InvalidCalibrationProvenanceReportError(
                f"checksum_algorithm_version {self.checksum_algorithm_version!r} does not "
                f"match the version this package implements ({CHECKSUM_ALGORITHM_VERSION!r})"
            )
        if self.distributed_provenance_schema_version != DISTRIBUTED_PROVENANCE_SCHEMA_VERSION:
            raise InvalidCalibrationProvenanceReportError(
                f"distributed_provenance_schema_version "
                f"{self.distributed_provenance_schema_version!r} does not match the version "
                f"this package implements ({DISTRIBUTED_PROVENANCE_SCHEMA_VERSION!r})"
            )
        _require_sha256_hex(self, "provenance_manifest_checksum")
        _require_sha256_hex(self, "calibration_run_context_checksum")
        _require_sha256_hex(self, "calibration_evidence_checksum")
        if not isinstance(self.participating_worker_context_checksums, tuple) or not (
            self.participating_worker_context_checksums
        ):
            raise InvalidCalibrationProvenanceReportError(
                "participating_worker_context_checksums must be a nonempty tuple, got "
                f"{self.participating_worker_context_checksums!r}"
            )
        for checksum in self.participating_worker_context_checksums:
            _require_sha256_hex_value(checksum, "participating_worker_context_checksums entry")
        try:
            EnvironmentClass(self.environment_class)
        except ValueError as exc:
            raise InvalidCalibrationProvenanceReportError(
                f"environment_class {self.environment_class!r} is not a valid EnvironmentClass "
                "value"
            ) from exc
        for field_name in (
            "topology_region_counts",
            "topology_machine_type_counts",
            "topology_provisioning_class_counts",
        ):
            _require_histogram(self, field_name)
        for field_name in (
            "intended_concurrency",
            "measured_peak_concurrency",
            "admitted_invocation_count",
            "completed_invocation_count",
            "invalid_invocation_count",
            "incomplete_invocation_count",
        ):
            _require_non_negative_int(self, field_name)
        for field_name in ("invocation_provenance_resolved", "task_reconciliation_passed"):
            if not isinstance(getattr(self, field_name), bool):
                raise InvalidCalibrationProvenanceReportError(
                    f"{field_name!r} must be a bool, got {getattr(self, field_name)!r}"
                )
        if self.qualification_gate_readiness not in _VALID_GATE_READINESS:
            raise InvalidCalibrationProvenanceReportError(
                f"qualification_gate_readiness {self.qualification_gate_readiness!r} is not a "
                f"valid ProvenanceGateReadiness value"
            )
        if not isinstance(self.qualification_gate_missing_dimensions, tuple):
            raise InvalidCalibrationProvenanceReportError(
                "qualification_gate_missing_dimensions must be a tuple, got "
                f"{type(self.qualification_gate_missing_dimensions).__name__}"
            )
        for reason in self.qualification_gate_missing_dimensions:
            if reason not in _VALID_GATE_FAILURE_REASONS:
                raise InvalidCalibrationProvenanceReportError(
                    f"qualification_gate_missing_dimensions entry {reason!r} is not a valid "
                    "ProvenanceGateFailureReason value"
                )

        # Hard invariant: the four invocation counts must exactly
        # partition admitted_invocation_count -- a tampered or
        # inconsistent count set is a construction error, never merely a
        # readiness input.
        if self.admitted_invocation_count != (
            self.completed_invocation_count
            + self.invalid_invocation_count
            + self.incomplete_invocation_count
        ):
            raise InvalidCalibrationProvenanceReportError(
                f"admitted_invocation_count ({self.admitted_invocation_count}) does not equal "
                f"completed ({self.completed_invocation_count}) + invalid "
                f"({self.invalid_invocation_count}) + incomplete "
                f"({self.incomplete_invocation_count})"
            )

        # Measured peak concurrency exceeding intended_concurrency, the
        # admitted worker-topology size, or (under PERSONAL_BOOTSTRAP) the
        # personal-bootstrap ceiling is a *failed qualification result*,
        # not malformed data -- it is folded into
        # expected_blocker_reasons below, never raised here.

        expected_blocker_reasons = _expected_blocker_reasons(self)
        if not isinstance(self.blocker_reasons, tuple) or not all(
            isinstance(reason, str) for reason in self.blocker_reasons
        ):
            raise InvalidCalibrationProvenanceReportError(
                f"blocker_reasons must be a tuple of str, got {self.blocker_reasons!r}"
            )
        for reason in self.blocker_reasons:
            if reason not in _VALID_BLOCKER_REASONS:
                raise InvalidCalibrationProvenanceReportError(
                    f"blocker_reasons entry {reason!r} is not a valid blocker reason"
                )
        if tuple(self.blocker_reasons) != expected_blocker_reasons:
            raise InvalidCalibrationProvenanceReportError(
                f"blocker_reasons {self.blocker_reasons!r} is inconsistent with the recorded "
                f"counts/flags (expected {expected_blocker_reasons!r}) -- never independently "
                "settable"
            )

        expected_readiness = (
            CalibrationProvenanceReadiness.BLOCKED_CALIBRATION_PROVENANCE
            if expected_blocker_reasons
            else CalibrationProvenanceReadiness.CALIBRATION_PROVENANCE_READY_FOR_3C
        )
        if not isinstance(self.readiness, CalibrationProvenanceReadiness):
            raise InvalidCalibrationProvenanceReportError(
                f"readiness must be a CalibrationProvenanceReadiness, got {self.readiness!r}"
            )
        if self.readiness != expected_readiness:
            raise InvalidCalibrationProvenanceReportError(
                f"readiness {self.readiness!r} is inconsistent with the reconciled counts/flags "
                f"(expected {expected_readiness!r}) -- readiness may never be reported "
                "independently of the evidence it derives from"
            )

        payload = _report_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.report_checksum and self.report_checksum != expected_checksum:
            raise InvalidCalibrationProvenanceReportError(
                f"report_checksum {self.report_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or corrupted "
                f"calibration-provenance report"
            )
        object.__setattr__(self, "report_checksum", expected_checksum)


def _compute_blocker_reasons(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    qualification_gate_readiness: str,
    qualification_gate_missing_dimensions: tuple[str, ...],
    invocation_provenance_resolved: bool,
    task_reconciliation_passed: bool,
    admitted_invocation_count: int,
    completed_invocation_count: int,
    invalid_invocation_count: int,
    incomplete_invocation_count: int,
    measured_peak_concurrency: int,
    intended_concurrency: int,
    admitted_worker_count: int,
    environment_class: str,
) -> tuple[str, ...]:
    """Compute the exact, sorted set of blocker reasons these raw facts
    imply -- the single source of truth both
    :func:`build_calibration_provenance_report` (before construction) and
    ``CalibrationProvenanceReport.__post_init__`` (validating an already-
    constructed instance) call, so the two can never drift apart. Empty
    if and only if every requirement for
    ``CALIBRATION_PROVENANCE_READY_FOR_3C`` holds.

    A structurally valid ``measured_peak_concurrency`` that exceeds
    ``intended_concurrency``, exceeds ``admitted_worker_count`` (the
    admitted worker-topology size), or -- under
    ``EnvironmentClass.PERSONAL_BOOTSTRAP`` -- exceeds
    :data:`~src.distributed.personal_policy.PERSONAL_BOOTSTRAP_MAX_WORKERS`,
    is a failed qualification criterion, not malformed data: each folds
    in here as an ordinary blocker reason, never a construction error."""
    reasons: set[str] = set()
    if qualification_gate_readiness != ProvenanceGateReadiness.READY.value:
        reasons.update(qualification_gate_missing_dimensions)
    if not invocation_provenance_resolved:
        reasons.add(CalibrationProvenanceBlockerReason.INVOCATION_PROVENANCE_UNRESOLVED.value)
    if not task_reconciliation_passed:
        reasons.add(CalibrationProvenanceBlockerReason.TASK_RECONCILIATION_FAILED.value)
    if (
        incomplete_invocation_count > 0
        or invalid_invocation_count > 0
        or completed_invocation_count != admitted_invocation_count
    ):
        reasons.add(CalibrationProvenanceBlockerReason.INCOMPLETE_INVOCATION_EVIDENCE.value)
    if measured_peak_concurrency > intended_concurrency:
        reasons.add(CalibrationProvenanceBlockerReason.MEASURED_CONCURRENCY_EXCEEDS_INTENDED.value)
    if measured_peak_concurrency > admitted_worker_count:
        reasons.add(
            CalibrationProvenanceBlockerReason.MEASURED_CONCURRENCY_EXCEEDS_ADMITTED_TOPOLOGY.value
        )
    if (
        environment_class == EnvironmentClass.PERSONAL_BOOTSTRAP.value
        and measured_peak_concurrency > PERSONAL_BOOTSTRAP_MAX_WORKERS
    ):
        reasons.add(CalibrationProvenanceBlockerReason.PERSONAL_CONCURRENCY_CEILING_EXCEEDED.value)
    return tuple(sorted(reasons))


def _expected_blocker_reasons(report: "CalibrationProvenanceReport") -> tuple[str, ...]:
    """:func:`_compute_blocker_reasons` applied to an already-constructed
    report's own fields -- used by ``__post_init__`` to validate a
    caller-supplied ``blocker_reasons``/``readiness`` pair."""
    return _compute_blocker_reasons(
        qualification_gate_readiness=report.qualification_gate_readiness,
        qualification_gate_missing_dimensions=report.qualification_gate_missing_dimensions,
        invocation_provenance_resolved=report.invocation_provenance_resolved,
        task_reconciliation_passed=report.task_reconciliation_passed,
        admitted_invocation_count=report.admitted_invocation_count,
        completed_invocation_count=report.completed_invocation_count,
        invalid_invocation_count=report.invalid_invocation_count,
        incomplete_invocation_count=report.incomplete_invocation_count,
        measured_peak_concurrency=report.measured_peak_concurrency,
        intended_concurrency=report.intended_concurrency,
        admitted_worker_count=len(report.participating_worker_context_checksums),
        environment_class=report.environment_class,
    )


def _report_payload(report: "CalibrationProvenanceReport") -> dict[str, Any]:
    return {
        "calibration_provenance_report_schema_version": (
            report.calibration_provenance_report_schema_version
        ),
        "checksum_algorithm_version": report.checksum_algorithm_version,
        "distributed_provenance_schema_version": report.distributed_provenance_schema_version,
        "provenance_manifest_checksum": report.provenance_manifest_checksum,
        "calibration_run_context_checksum": report.calibration_run_context_checksum,
        "participating_worker_context_checksums": list(
            report.participating_worker_context_checksums
        ),
        "environment_class": report.environment_class,
        "topology_region_counts": [list(pair) for pair in report.topology_region_counts],
        "topology_machine_type_counts": [
            list(pair) for pair in report.topology_machine_type_counts
        ],
        "topology_provisioning_class_counts": [
            list(pair) for pair in report.topology_provisioning_class_counts
        ],
        "intended_concurrency": report.intended_concurrency,
        "measured_peak_concurrency": report.measured_peak_concurrency,
        "admitted_invocation_count": report.admitted_invocation_count,
        "completed_invocation_count": report.completed_invocation_count,
        "invalid_invocation_count": report.invalid_invocation_count,
        "incomplete_invocation_count": report.incomplete_invocation_count,
        "invocation_provenance_resolved": report.invocation_provenance_resolved,
        "task_reconciliation_passed": report.task_reconciliation_passed,
        "qualification_gate_readiness": report.qualification_gate_readiness,
        "qualification_gate_missing_dimensions": list(
            report.qualification_gate_missing_dimensions
        ),
        "calibration_evidence_checksum": report.calibration_evidence_checksum,
        "readiness": report.readiness.value,
        "blocker_reasons": list(report.blocker_reasons),
    }


def calibration_provenance_report_to_dict(report: CalibrationProvenanceReport) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`CalibrationProvenanceReport`
    -- safe, committed-report-suitable in its entirety."""
    return {**_report_payload(report), "report_checksum": report.report_checksum}


def calibration_provenance_report_from_dict(
    data: Mapping[str, Any]
) -> CalibrationProvenanceReport:
    """Inverse of :func:`calibration_provenance_report_to_dict`."""
    try:
        return CalibrationProvenanceReport(
            calibration_provenance_report_schema_version=data[
                "calibration_provenance_report_schema_version"
            ],
            checksum_algorithm_version=data["checksum_algorithm_version"],
            distributed_provenance_schema_version=data["distributed_provenance_schema_version"],
            provenance_manifest_checksum=data["provenance_manifest_checksum"],
            calibration_run_context_checksum=data["calibration_run_context_checksum"],
            participating_worker_context_checksums=tuple(
                data["participating_worker_context_checksums"]
            ),
            environment_class=data["environment_class"],
            topology_region_counts=tuple(
                tuple(pair) for pair in data["topology_region_counts"]
            ),
            topology_machine_type_counts=tuple(
                tuple(pair) for pair in data["topology_machine_type_counts"]
            ),
            topology_provisioning_class_counts=tuple(
                tuple(pair) for pair in data["topology_provisioning_class_counts"]
            ),
            intended_concurrency=data["intended_concurrency"],
            measured_peak_concurrency=data["measured_peak_concurrency"],
            admitted_invocation_count=data["admitted_invocation_count"],
            completed_invocation_count=data["completed_invocation_count"],
            invalid_invocation_count=data["invalid_invocation_count"],
            incomplete_invocation_count=data["incomplete_invocation_count"],
            invocation_provenance_resolved=data["invocation_provenance_resolved"],
            task_reconciliation_passed=data["task_reconciliation_passed"],
            qualification_gate_readiness=data["qualification_gate_readiness"],
            qualification_gate_missing_dimensions=tuple(
                data["qualification_gate_missing_dimensions"]
            ),
            calibration_evidence_checksum=data["calibration_evidence_checksum"],
            readiness=CalibrationProvenanceReadiness(data["readiness"]),
            blocker_reasons=tuple(data["blocker_reasons"]),
            report_checksum=data["report_checksum"],
        )
    except KeyError as exc:
        raise InvalidCalibrationProvenanceReportError(
            f"missing required calibration-provenance report field: {exc}"
        ) from exc
    except ValueError as exc:
        raise InvalidCalibrationProvenanceReportError(
            f"malformed calibration-provenance report: {exc}"
        ) from exc


def compute_calibration_evidence_checksum(
    invocation_record_checksums: tuple[str, ...], task_evaluation_record_checksums: tuple[str, ...]
) -> str:
    """The "trace" checksum this report binds: sha256 over the sorted
    set of every contributing invocation's and task-evaluation's own
    ``record_checksum`` -- changes if and only if the underlying
    calibration evidence set changes, without embedding any of that
    (protected) evidence content directly in this safe report."""
    payload = {
        "invocation_record_checksums": sorted(invocation_record_checksums),
        "task_evaluation_record_checksums": sorted(task_evaluation_record_checksums),
    }
    return _sha256_of(payload)


def build_calibration_provenance_report(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    *,
    provenance_manifest_checksum: str,
    calibration_run_context_checksum: str,
    participating_worker_context_checksums: tuple[str, ...],
    environment_class: str,
    topology_region_counts: tuple[tuple[str, int], ...],
    topology_machine_type_counts: tuple[tuple[str, int], ...],
    topology_provisioning_class_counts: tuple[tuple[str, int], ...],
    intended_concurrency: int,
    measured_peak_concurrency: int,
    admitted_invocation_count: int,
    completed_invocation_count: int,
    invalid_invocation_count: int,
    incomplete_invocation_count: int,
    invocation_provenance_resolved: bool,
    task_reconciliation_passed: bool,
    qualification_gate_readiness: str,
    qualification_gate_missing_dimensions: tuple[str, ...],
    calibration_evidence_checksum: str,
) -> CalibrationProvenanceReport:
    """Build a :class:`CalibrationProvenanceReport` from every fact the
    calling harness itself measured/reconciled, deriving
    ``readiness``/``blocker_reasons`` purely from those facts -- never
    set independently. This is the only supported construction path for
    ordinary callers; direct dataclass construction is reserved for
    tests proving the derivation itself. Blocker reasons/readiness are
    computed from the raw arguments *before* constructing the dataclass
    (which validates eagerly in ``__post_init__`` and would otherwise
    raise on any placeholder value inconsistent with what these facts
    actually imply)."""
    blocker_reasons = _compute_blocker_reasons(
        qualification_gate_readiness=qualification_gate_readiness,
        qualification_gate_missing_dimensions=qualification_gate_missing_dimensions,
        invocation_provenance_resolved=invocation_provenance_resolved,
        task_reconciliation_passed=task_reconciliation_passed,
        admitted_invocation_count=admitted_invocation_count,
        completed_invocation_count=completed_invocation_count,
        invalid_invocation_count=invalid_invocation_count,
        incomplete_invocation_count=incomplete_invocation_count,
        measured_peak_concurrency=measured_peak_concurrency,
        intended_concurrency=intended_concurrency,
        admitted_worker_count=len(participating_worker_context_checksums),
        environment_class=environment_class,
    )
    readiness = (
        CalibrationProvenanceReadiness.BLOCKED_CALIBRATION_PROVENANCE
        if blocker_reasons
        else CalibrationProvenanceReadiness.CALIBRATION_PROVENANCE_READY_FOR_3C
    )
    return CalibrationProvenanceReport(
        calibration_provenance_report_schema_version=(
            CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION
        ),
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        distributed_provenance_schema_version=DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
        provenance_manifest_checksum=provenance_manifest_checksum,
        calibration_run_context_checksum=calibration_run_context_checksum,
        participating_worker_context_checksums=participating_worker_context_checksums,
        environment_class=environment_class,
        topology_region_counts=topology_region_counts,
        topology_machine_type_counts=topology_machine_type_counts,
        topology_provisioning_class_counts=topology_provisioning_class_counts,
        intended_concurrency=intended_concurrency,
        measured_peak_concurrency=measured_peak_concurrency,
        admitted_invocation_count=admitted_invocation_count,
        completed_invocation_count=completed_invocation_count,
        invalid_invocation_count=invalid_invocation_count,
        incomplete_invocation_count=incomplete_invocation_count,
        invocation_provenance_resolved=invocation_provenance_resolved,
        task_reconciliation_passed=task_reconciliation_passed,
        qualification_gate_readiness=qualification_gate_readiness,
        qualification_gate_missing_dimensions=qualification_gate_missing_dimensions,
        calibration_evidence_checksum=calibration_evidence_checksum,
        readiness=readiness,
        blocker_reasons=blocker_reasons,
    )


def render_markdown(report: CalibrationProvenanceReport) -> str:
    """A concise, human-readable Markdown rendering of the same safe
    fields the JSON report carries -- nothing else."""
    lines = [
        "# MEGB-03H.2C.3B.3 Calibration-Provenance Qualification-Evidence Report",
        "",
        f"- **Readiness:** `{report.readiness.value}`",
        "- **Scope:** offline, provider-neutral calibration-provenance evidence chain "
        "only -- no GCP, H.2C.3C credential-boundary, or real scientific-result-validity "
        "claim is made.",
        f"- **Schema version:** `{report.calibration_provenance_report_schema_version}`",
        f"- **Report checksum:** `{report.report_checksum}`",
        f"- **Provenance manifest checksum:** `{report.provenance_manifest_checksum}`",
        f"- **Calibration run-context checksum:** `{report.calibration_run_context_checksum}`",
        f"- **Calibration evidence checksum:** `{report.calibration_evidence_checksum}`",
        "",
        "## Qualification gate",
        "",
        f"- qualification_gate_readiness: `{report.qualification_gate_readiness}`",
        f"- qualification_gate_missing_dimensions: "
        f"{list(report.qualification_gate_missing_dimensions)}",
        "",
        "## Concurrency",
        "",
        f"- intended_concurrency: {report.intended_concurrency}",
        f"- measured_peak_concurrency: {report.measured_peak_concurrency}",
        "",
        "## Invocation counts",
        "",
        f"- admitted: {report.admitted_invocation_count}, completed: "
        f"{report.completed_invocation_count}, invalid: {report.invalid_invocation_count}, "
        f"incomplete: {report.incomplete_invocation_count}",
        f"- invocation_provenance_resolved: {report.invocation_provenance_resolved}",
        f"- task_reconciliation_passed: {report.task_reconciliation_passed}",
        "",
        "## Topology (safe, coarse)",
        "",
        f"- region_counts: {list(report.topology_region_counts)}",
        f"- machine_type_counts: {list(report.topology_machine_type_counts)}",
        f"- provisioning_class_counts: {list(report.topology_provisioning_class_counts)}",
        "",
        "## Blocker reasons",
        "",
        f"{list(report.blocker_reasons) if report.blocker_reasons else 'none'}",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION",
    "InvalidCalibrationProvenanceReportError",
    "CalibrationProvenanceReadiness",
    "CalibrationProvenanceBlockerReason",
    "CalibrationProvenanceReport",
    "calibration_provenance_report_to_dict",
    "calibration_provenance_report_from_dict",
    "render_markdown",
    "compute_calibration_evidence_checksum",
    "build_calibration_provenance_report",
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_PROVENANCE_SCHEMA_VERSION",
]
