"""MEGB-03H.2C.3B.2A: provider-neutral worker-registration and lease
contracts, plus the fencing check that keeps a stale lease generation
from ever committing.

``worker_participant_id`` here is the same run-scoped, coordinator-issued,
opaque pseudonym established by
:class:`~src.distributed.provenance.WorkerExecutionContext` (MEGB-03H.2C.3B.1
conformance audit) -- never a raw instance ID, hostname, or resource name.

``lease_generation`` is the fencing token: a monotonically increasing,
coordinator-issued integer, unique per work item across its entire
lifetime (never reused, even after a lease expires and is reassigned). A
:class:`Lease` is issued once per admission-or-reassignment event; a
:class:`LeaseRenewal` extends an *existing* lease's expiry without
changing its generation (a heartbeat, not a reassignment) -- reassignment
after expiry is modeled by issuing a brand-new :class:`Lease` with a
higher ``lease_generation`` for the same work item, which
:func:`validate_fencing` then uses to reject any commit attempt still
carrying the old, now-stale generation."""

# pylint: disable=duplicate-code
# Lease's leading fields intentionally mirror
# src.distributed.work_contracts.ExecutionAttempt's own leading fields
# (both identify one work item/worker/generation) -- shared boilerplate,
# not shared logic, per this project's own established convention.

from dataclasses import dataclass
from typing import Any

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
    require_checksum_algorithm_version as _require_checksum_algorithm_version,
    require_non_negative_int as _require_non_negative_int,
    require_nonempty_str as _require_nonempty_str,
    require_nonempty_str_fields as _require_nonempty_str_fields,
    require_orchestration_schema_version as _require_orchestration_schema_version,
    require_positive_int as _require_positive_int,
    require_sha256_hex as _require_sha256_hex,
    sha256_of as _sha256_of,
)


@dataclass(frozen=True)
class WorkerRegistration:
    """A worker's registration with the coordinator for one distributed
    run. ``worker_participant_id`` is the same opaque, run-scoped
    pseudonym :class:`~src.distributed.provenance.WorkerExecutionContext`
    carries -- this type does not re-derive or duplicate that identity,
    it simply names it as the registrant."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    worker_participant_id: str
    distributed_run_context_checksum: str
    registered_at_logical_clock: int
    registration_checksum: str = ""

    def __post_init__(self) -> None:
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str(self, "worker_participant_id")
        _require_non_negative_int(self, "registered_at_logical_clock")
        _require_sha256_hex(self, "distributed_run_context_checksum")
        payload = _worker_registration_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.registration_checksum and self.registration_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"registration_checksum {self.registration_checksum!r} does not match the "
                f"recomputed checksum {expected_checksum!r} over its own contents -- tampered "
                f"or corrupted worker registration"
            )
        object.__setattr__(self, "registration_checksum", expected_checksum)


def _worker_registration_payload(registration: WorkerRegistration) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": (
            registration.distributed_orchestration_schema_version
        ),
        "checksum_algorithm_version": registration.checksum_algorithm_version,
        "worker_participant_id": registration.worker_participant_id,
        "distributed_run_context_checksum": registration.distributed_run_context_checksum,
        "registered_at_logical_clock": registration.registered_at_logical_clock,
    }


def worker_registration_to_dict(registration: WorkerRegistration) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`WorkerRegistration`."""
    return {
        **_worker_registration_payload(registration),
        "registration_checksum": registration.registration_checksum,
    }


@dataclass(frozen=True)
class Lease:
    """A fencing-token-bearing lease over one unit of scientific work.
    ``lease_generation`` is coordinator-issued and monotonically
    increasing per ``scientific_work_id`` across its entire lifetime --
    a fresh :class:`Lease` (not a :class:`LeaseRenewal`) with a higher
    generation models reassignment after expiry."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    scientific_work_id: str
    worker_participant_id: str
    lease_generation: int
    lease_issued_at_logical_clock: int
    lease_duration_logical_ticks: int
    lease_checksum: str = ""

    def __post_init__(self) -> None:
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str_fields(self, ("scientific_work_id", "worker_participant_id"))
        _require_positive_int(self, "lease_generation")
        _require_non_negative_int(self, "lease_issued_at_logical_clock")
        _require_positive_int(self, "lease_duration_logical_ticks")
        payload = _lease_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.lease_checksum and self.lease_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"lease_checksum {self.lease_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted lease"
            )
        object.__setattr__(self, "lease_checksum", expected_checksum)

    @property
    def expires_at_logical_clock(self) -> int:
        """The logical tick at which this lease becomes eligible for
        expiry-triggered redelivery, absent a renewal."""
        return self.lease_issued_at_logical_clock + self.lease_duration_logical_ticks

    def is_expired(self, now: int) -> bool:
        """``True`` once ``now`` has reached or passed
        :attr:`expires_at_logical_clock`."""
        return now >= self.expires_at_logical_clock


def _lease_payload(lease: Lease) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": (
            lease.distributed_orchestration_schema_version
        ),
        "checksum_algorithm_version": lease.checksum_algorithm_version,
        "scientific_work_id": lease.scientific_work_id,
        "worker_participant_id": lease.worker_participant_id,
        "lease_generation": lease.lease_generation,
        "lease_issued_at_logical_clock": lease.lease_issued_at_logical_clock,
        "lease_duration_logical_ticks": lease.lease_duration_logical_ticks,
    }


def lease_to_dict(lease: Lease) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`Lease`."""
    return {**_lease_payload(lease), "lease_checksum": lease.lease_checksum}


@dataclass(frozen=True)
class LeaseRenewal:
    """A heartbeat extending an *existing* lease's expiry without
    changing its ``lease_generation`` -- the same worker still holds the
    same lease, it simply has more time. A generation change is never
    expressed as a :class:`LeaseRenewal`; it always requires a fresh
    :class:`Lease` (reassignment)."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    scientific_work_id: str
    worker_participant_id: str
    lease_generation: int
    renewed_at_logical_clock: int
    renewal_checksum: str = ""

    def __post_init__(self) -> None:
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str_fields(self, ("scientific_work_id", "worker_participant_id"))
        _require_positive_int(self, "lease_generation")
        _require_non_negative_int(self, "renewed_at_logical_clock")
        payload = _lease_renewal_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.renewal_checksum and self.renewal_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"renewal_checksum {self.renewal_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted lease renewal"
            )
        object.__setattr__(self, "renewal_checksum", expected_checksum)


def _lease_renewal_payload(renewal: LeaseRenewal) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": (
            renewal.distributed_orchestration_schema_version
        ),
        "checksum_algorithm_version": renewal.checksum_algorithm_version,
        "scientific_work_id": renewal.scientific_work_id,
        "worker_participant_id": renewal.worker_participant_id,
        "lease_generation": renewal.lease_generation,
        "renewed_at_logical_clock": renewal.renewed_at_logical_clock,
    }


def lease_renewal_to_dict(renewal: LeaseRenewal) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`LeaseRenewal`."""
    return {**_lease_renewal_payload(renewal), "renewal_checksum": renewal.renewal_checksum}


def apply_lease_renewal(lease: Lease, renewal: LeaseRenewal, *, extend_by_ticks: int) -> Lease:
    """Return a new :class:`Lease` with the same ``lease_generation`` and
    a later ``lease_issued_at_logical_clock``/expiry, reflecting
    ``renewal``. Raises if ``renewal`` does not name the same
    ``scientific_work_id``/``worker_participant_id``/``lease_generation``
    as ``lease`` -- a renewal can only ever extend the exact lease it
    names, never a different one."""
    if (
        renewal.scientific_work_id != lease.scientific_work_id
        or renewal.worker_participant_id != lease.worker_participant_id
        or renewal.lease_generation != lease.lease_generation
    ):
        raise InvalidDistributedProvenanceError(
            "lease renewal does not match the lease it claims to renew -- "
            f"lease=({lease.scientific_work_id!r}, {lease.worker_participant_id!r}, "
            f"{lease.lease_generation}) renewal=({renewal.scientific_work_id!r}, "
            f"{renewal.worker_participant_id!r}, {renewal.lease_generation})"
        )
    if (
        not isinstance(extend_by_ticks, int)
        or isinstance(extend_by_ticks, bool)
        or extend_by_ticks <= 0
    ):
        raise InvalidDistributedProvenanceError(
            f"extend_by_ticks must be a positive int, got {extend_by_ticks!r}"
        )
    return Lease(
        distributed_orchestration_schema_version=lease.distributed_orchestration_schema_version,
        checksum_algorithm_version=lease.checksum_algorithm_version,
        scientific_work_id=lease.scientific_work_id,
        worker_participant_id=lease.worker_participant_id,
        lease_generation=lease.lease_generation,
        lease_issued_at_logical_clock=renewal.renewed_at_logical_clock,
        lease_duration_logical_ticks=extend_by_ticks,
    )


class StaleLeaseGenerationError(InvalidDistributedProvenanceError):
    """Raised by :func:`validate_fencing` when an attempt's
    ``lease_generation`` does not match the work item's currently valid
    generation -- a stale worker (holding an old, since-reassigned
    lease) must never be allowed to commit."""


def validate_fencing(current_generation: int, attempt_generation: int) -> None:
    """Raise :class:`StaleLeaseGenerationError` unless
    ``attempt_generation == current_generation`` -- the fencing check
    every result commit must pass before it is accepted. A generation
    below current means a stale, reassigned-away worker; a generation
    above current is an internal-consistency violation (the coordinator
    is always the sole issuer of generations), so both directions are
    rejected identically."""
    if attempt_generation != current_generation:
        raise StaleLeaseGenerationError(
            f"attempt lease_generation {attempt_generation} does not match the currently valid "
            f"lease_generation {current_generation} -- stale or invalid lease, commit rejected"
        )


__all__ = [
    "WorkerRegistration",
    "worker_registration_to_dict",
    "Lease",
    "lease_to_dict",
    "LeaseRenewal",
    "lease_renewal_to_dict",
    "apply_lease_renewal",
    "StaleLeaseGenerationError",
    "validate_fencing",
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION",
]
