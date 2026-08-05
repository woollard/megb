"""MEGB-03H.2C.3B.2B.1: construction/validation and behavior tests for
:mod:`src.distributed.worker_registry_store`."""

import pytest

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
)
from src.distributed.worker_contracts import WorkerRegistration
from src.distributed.worker_registry_store import (
    DuplicateWorkerParticipantError,
    InMemoryWorkerRegistry,
    WorkerContextMismatchError,
    WorkerNotRegisteredError,
    WorkerRegistrationStatus,
)
from tests._distributed_orchestration_fixtures import make_sha256


def _registration(**overrides: object) -> WorkerRegistration:
    fields: dict[str, object] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "worker_participant_id": "worker-participant-a",
        "distributed_run_context_checksum": make_sha256("run-ctx"),
        "registered_at_logical_clock": 0,
    }
    fields.update(overrides)
    return WorkerRegistration(**fields)  # type: ignore[arg-type]


def test_register_adds_to_active_participant_ids() -> None:
    """Test register adds to active participant ids."""
    registry = InMemoryWorkerRegistry()
    registry.register(_registration())
    assert registry.active_worker_participant_ids() == ("worker-participant-a",)


def test_register_is_idempotent_for_identical_content() -> None:
    """Test register is idempotent for identical content."""
    registry = InMemoryWorkerRegistry()
    reg = _registration()
    first = registry.register(reg)
    second = registry.register(reg)
    assert first == second
    assert registry.active_worker_participant_ids() == ("worker-participant-a",)


def test_register_rejects_duplicate_participant_with_different_content() -> None:
    """Test register rejects duplicate participant with different
    content -- same participant id, different registration content is a
    duplicate observation, not an update."""
    registry = InMemoryWorkerRegistry()
    registry.register(_registration())
    with pytest.raises(DuplicateWorkerParticipantError):
        registry.register(_registration(registered_at_logical_clock=99))


def test_register_rejects_context_mismatch_under_same_participant_id() -> None:
    """Test register rejects context mismatch under same participant
    id."""
    registry = InMemoryWorkerRegistry()
    registry.register(_registration())
    with pytest.raises(WorkerContextMismatchError):
        registry.register(
            _registration(distributed_run_context_checksum=make_sha256("different-run"))
        )


def test_register_two_distinct_participants_are_both_active() -> None:
    """Test register two distinct participants are both active -- a
    homogeneous fleet of distinct participants must not be rejected as
    duplicates."""
    registry = InMemoryWorkerRegistry()
    registry.register(_registration(worker_participant_id="worker-participant-a"))
    registry.register(_registration(worker_participant_id="worker-participant-b"))
    assert registry.active_worker_participant_ids() == (
        "worker-participant-a",
        "worker-participant-b",
    )


def test_active_worker_participant_ids_is_deterministically_sorted() -> None:
    """Test active worker participant ids is deterministically sorted."""
    registry = InMemoryWorkerRegistry()
    registry.register(_registration(worker_participant_id="worker-participant-z"))
    registry.register(_registration(worker_participant_id="worker-participant-a"))
    assert registry.active_worker_participant_ids() == (
        "worker-participant-a",
        "worker-participant-z",
    )


def test_registration_status_starts_active() -> None:
    """Test registration status starts active."""
    registry = InMemoryWorkerRegistry()
    registry.register(_registration())
    assert registry.registration_status("worker-participant-a") == WorkerRegistrationStatus.ACTIVE


def test_registration_status_raises_for_unregistered_worker() -> None:
    """Test registration status raises for unregistered worker."""
    registry = InMemoryWorkerRegistry()
    with pytest.raises(WorkerNotRegisteredError):
        registry.registration_status("ghost-worker")


def test_retire_moves_worker_out_of_active_list() -> None:
    """Test retire moves worker out of active list."""
    registry = InMemoryWorkerRegistry()
    registry.register(_registration())
    registry.retire("worker-participant-a")
    assert not registry.active_worker_participant_ids()
    assert registry.registration_status("worker-participant-a") == WorkerRegistrationStatus.RETIRED


def test_retire_is_idempotent() -> None:
    """Test retire is idempotent."""
    registry = InMemoryWorkerRegistry()
    registry.register(_registration())
    registry.retire("worker-participant-a")
    registry.retire("worker-participant-a")  # must not raise
    assert registry.registration_status("worker-participant-a") == WorkerRegistrationStatus.RETIRED


def test_retire_unregistered_worker_raises_not_registered() -> None:
    """Test retire unregistered worker raises not registered."""
    registry = InMemoryWorkerRegistry()
    with pytest.raises(WorkerNotRegisteredError):
        registry.retire("ghost-worker")


def test_register_rejects_non_worker_registration() -> None:
    """Test register rejects non worker registration."""
    registry = InMemoryWorkerRegistry()
    with pytest.raises(InvalidDistributedProvenanceError):
        registry.register("not-a-registration")  # type: ignore[arg-type]
