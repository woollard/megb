"""MEGB-03H.2C.3B.2A: construction/validation/immutability/round-trip,
lease issue/renewal/expiry/reassignment, and fencing tests for
:mod:`src.distributed.worker_contracts`. No wall-clock sleep anywhere --
every "time" concept here is the injected
:class:`~src.distributed.clock.LogicalClock`."""

# pylint: disable=duplicate-code
# Lease's round-trip test intentionally mirrors
# tests/test_distributed_work_contracts.py's own ExecutionAttempt
# round-trip test (both rebuild an object sharing the same leading field
# names) -- shared boilerplate, not shared logic.

import dataclasses

import pytest

from src.distributed._checksums import (
    InvalidDistributedProvenanceError,
    UnsupportedDistributedOrchestrationSchemaVersionError,
)
from src.distributed.clock import LogicalClock
from src.distributed.worker_contracts import (
    Lease,
    LeaseRenewal,
    StaleLeaseGenerationError,
    WorkerRegistration,
    apply_lease_renewal,
    lease_renewal_to_dict,
    lease_to_dict,
    validate_fencing,
    worker_registration_to_dict,
)
from tests._distributed_orchestration_fixtures import (
    make_lease,
    make_lease_renewal,
    make_worker_registration,
)


# ---------------------------------------------------------------------------
# WorkerRegistration
# ---------------------------------------------------------------------------


def test_worker_registration_constructs_and_computes_checksum() -> None:
    """Test worker registration constructs and computes checksum."""
    registration = make_worker_registration()
    assert len(registration.registration_checksum) == 64


def test_worker_registration_is_immutable() -> None:
    """Test worker registration is immutable."""
    registration = make_worker_registration()
    with pytest.raises(dataclasses.FrozenInstanceError):
        registration.worker_participant_id = "changed"  # type: ignore[misc]


def test_worker_registration_round_trips() -> None:
    """Test worker registration round trips."""
    registration = make_worker_registration()
    data = worker_registration_to_dict(registration)
    rebuilt = WorkerRegistration(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        worker_participant_id=data["worker_participant_id"],
        distributed_run_context_checksum=data["distributed_run_context_checksum"],
        registered_at_logical_clock=data["registered_at_logical_clock"],
        registration_checksum=data["registration_checksum"],
    )
    assert rebuilt == registration


def test_worker_registration_rejects_empty_participant_id() -> None:
    """Test worker registration rejects empty participant id."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_worker_registration(worker_participant_id="")


def test_worker_registration_rejects_negative_logical_clock() -> None:
    """Test worker registration rejects negative logical clock."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_worker_registration(registered_at_logical_clock=-1)


# ---------------------------------------------------------------------------
# Lease
# ---------------------------------------------------------------------------


def test_lease_constructs_and_computes_checksum() -> None:
    """Test lease constructs and computes checksum."""
    lease = make_lease()
    assert len(lease.lease_checksum) == 64


def test_lease_is_immutable() -> None:
    """Test lease is immutable."""
    lease = make_lease()
    with pytest.raises(dataclasses.FrozenInstanceError):
        lease.lease_generation = 99  # type: ignore[misc]


def test_lease_round_trips() -> None:
    """Test lease round trips."""
    lease = make_lease()
    data = lease_to_dict(lease)
    rebuilt = Lease(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        scientific_work_id=data["scientific_work_id"],
        worker_participant_id=data["worker_participant_id"],
        lease_generation=data["lease_generation"],
        lease_issued_at_logical_clock=data["lease_issued_at_logical_clock"],
        lease_duration_logical_ticks=data["lease_duration_logical_ticks"],
        lease_checksum=data["lease_checksum"],
    )
    assert rebuilt == lease


def test_lease_rejects_unsupported_schema_version() -> None:
    """Test lease rejects unsupported schema version."""
    with pytest.raises(UnsupportedDistributedOrchestrationSchemaVersionError):
        make_lease(distributed_orchestration_schema_version="stale-version")


def test_lease_rejects_non_positive_generation() -> None:
    """Test lease rejects non positive generation."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_lease(lease_generation=0)


def test_lease_rejects_non_positive_duration() -> None:
    """Test lease rejects non positive duration."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_lease(lease_duration_logical_ticks=0)


def test_lease_expires_at_is_issued_plus_duration() -> None:
    """Test lease expires at is issued plus duration."""
    lease = make_lease(lease_issued_at_logical_clock=5, lease_duration_logical_ticks=10)
    assert lease.expires_at_logical_clock == 15


def test_lease_is_expired_true_at_and_after_expiry() -> None:
    """Test lease issue/expiry: is_expired is False before expiry, True
    at and after -- driven entirely by the injected LogicalClock, no
    wall-clock sleep."""
    lease = make_lease(lease_issued_at_logical_clock=0, lease_duration_logical_ticks=10)
    clock = LogicalClock()
    assert not lease.is_expired(clock.now())
    clock.advance(9)
    assert not lease.is_expired(clock.now())
    clock.advance(1)  # now == 10, exactly at expiry
    assert lease.is_expired(clock.now())
    clock.advance(5)
    assert lease.is_expired(clock.now())


# ---------------------------------------------------------------------------
# LeaseRenewal / apply_lease_renewal -- renewal vs. reassignment
# ---------------------------------------------------------------------------


def test_lease_renewal_constructs_and_computes_checksum() -> None:
    """Test lease renewal constructs and computes checksum."""
    lease = make_lease()
    renewal = make_lease_renewal(lease)
    assert len(renewal.renewal_checksum) == 64


def test_lease_renewal_round_trips() -> None:
    """Test lease renewal round trips."""
    lease = make_lease()
    renewal = make_lease_renewal(lease)
    data = lease_renewal_to_dict(renewal)
    rebuilt = LeaseRenewal(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        scientific_work_id=data["scientific_work_id"],
        worker_participant_id=data["worker_participant_id"],
        lease_generation=data["lease_generation"],
        renewed_at_logical_clock=data["renewed_at_logical_clock"],
        renewal_checksum=data["renewal_checksum"],
    )
    assert rebuilt == renewal


def test_apply_lease_renewal_keeps_same_generation_extends_expiry() -> None:
    """Test a renewal (heartbeat) keeps the same lease_generation and
    only extends expiry -- never a reassignment."""
    lease = make_lease(lease_issued_at_logical_clock=0, lease_duration_logical_ticks=10)
    clock = LogicalClock()
    clock.advance(5)
    renewal = make_lease_renewal(lease, renewed_at_logical_clock=clock.now())
    renewed_lease = apply_lease_renewal(lease, renewal, extend_by_ticks=10)
    assert renewed_lease.lease_generation == lease.lease_generation
    assert renewed_lease.expires_at_logical_clock == clock.now() + 10
    assert not renewed_lease.is_expired(clock.now())


def test_apply_lease_renewal_rejects_mismatched_lease() -> None:
    """Test apply_lease_renewal rejects a renewal naming a different
    scientific_work_id/worker/generation than the lease it is applied
    to."""
    lease = make_lease()
    mismatched_renewal = make_lease_renewal(lease, scientific_work_id="different-work")
    with pytest.raises(InvalidDistributedProvenanceError):
        apply_lease_renewal(lease, mismatched_renewal, extend_by_ticks=10)


def test_apply_lease_renewal_rejects_non_positive_extension() -> None:
    """Test apply lease renewal rejects non positive extension."""
    lease = make_lease()
    renewal = make_lease_renewal(lease)
    with pytest.raises(InvalidDistributedProvenanceError):
        apply_lease_renewal(lease, renewal, extend_by_ticks=0)


def test_lease_reassignment_after_expiry_uses_a_new_higher_generation() -> None:
    """Test lease reassignment after expiry is modeled as a brand-new
    Lease with a strictly higher lease_generation for the same work item
    -- never a LeaseRenewal."""
    original_lease = make_lease(
        lease_generation=1, lease_issued_at_logical_clock=0, lease_duration_logical_ticks=10
    )
    clock = LogicalClock()
    clock.advance(11)  # past expiry
    assert original_lease.is_expired(clock.now())

    reassigned_lease = make_lease(
        lease_generation=2,
        worker_participant_id="worker-b",
        lease_issued_at_logical_clock=clock.now(),
        lease_duration_logical_ticks=10,
    )
    assert reassigned_lease.lease_generation > original_lease.lease_generation
    assert reassigned_lease.scientific_work_id == original_lease.scientific_work_id
    assert reassigned_lease.worker_participant_id != original_lease.worker_participant_id


# ---------------------------------------------------------------------------
# Fencing -- stale-worker commit rejection
# ---------------------------------------------------------------------------


def test_validate_fencing_accepts_matching_generation() -> None:
    """Test validate fencing accepts matching generation."""
    validate_fencing(current_generation=3, attempt_generation=3)  # must not raise


def test_validate_fencing_rejects_stale_lower_generation() -> None:
    """Test a stale worker (holding an old, since-reassigned lease
    generation) cannot commit -- fencing rejects a lower generation."""
    with pytest.raises(StaleLeaseGenerationError):
        validate_fencing(current_generation=3, attempt_generation=2)


def test_validate_fencing_rejects_higher_generation_as_internal_inconsistency() -> None:
    """Test validate_fencing also rejects an attempt generation higher
    than the coordinator's own currently valid generation -- an internal-
    consistency violation, since the coordinator is the sole issuer."""
    with pytest.raises(StaleLeaseGenerationError):
        validate_fencing(current_generation=3, attempt_generation=4)
