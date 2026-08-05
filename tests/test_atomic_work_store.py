"""MEGB-03H.2C.3B.2B.1: construction/validation and single-threaded
lifecycle/CAS/fencing/reconciliation tests for
:mod:`src.distributed.atomic_work_store`. Concurrency/race tests live in
``tests/test_atomic_stores_races.py``."""

# pylint: disable=duplicate-code
# This file's own direct AuthoritativeWorkRecord constructions inherently
# mirror src/distributed/atomic_work_store.py's own _new_record field
# list (both build the same dataclass) -- shared boilerplate, not shared
# logic.

import dataclasses

import pytest

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
)
from src.distributed.atomic_work_store import (
    AtomicWorkStore,
    AuthoritativeWorkRecord,
    IdentityMismatchError,
    InvalidReservationError,
    MissingArtifactReferenceError,
    RevisionConflictError,
    WorkRecordNotFoundError,
)
from src.distributed.state_machine import IllegalStateTransitionError, WorkItemState
from src.distributed.work_contracts import (
    Acknowledgement,
    CancellationRequest,
    CancellationScope,
    ConflictingResultCommitError,
    TerminalDisposition,
    TerminalDispositionKind,
    TerminalDispositionReason,
)
from src.distributed.worker_contracts import LeaseRenewal, StaleLeaseGenerationError
from tests._atomic_stores_fixtures import make_result_commit, make_synthetic_content
from tests._distributed_orchestration_fixtures import (
    make_execution_attempt,
    make_lease,
    make_sha256,
)

RUN_CTX = make_sha256("synthetic-run-context")
RESERVATION_ID = "reservation-0001"


def _always_present(_reference: object) -> bool:
    return True


def _never_present(_reference: object) -> bool:
    return False


def _always_valid_reservation(_reservation_id: str) -> bool:
    return True


def _never_valid_reservation(_reservation_id: str) -> bool:
    return False


# ---------------------------------------------------------------------------
# AuthoritativeWorkRecord construction/validation
# ---------------------------------------------------------------------------


def test_create_if_absent_starts_at_pending_available_revision_zero() -> None:
    """Test create if absent starts at pending available revision zero."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    assert record.state == WorkItemState.PENDING_AVAILABLE
    assert record.revision == 0
    assert record.current_lease_generation == 0
    assert record.worker_participant_id is None
    assert record.result_commit is None
    assert record.acknowledged is False
    assert record.terminal_disposition is None


def test_create_if_absent_is_idempotent() -> None:
    """Test create if absent is idempotent."""
    store = AtomicWorkStore()
    first = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    second = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    assert first == second


def test_read_raises_for_unknown_work_id() -> None:
    """Test read raises for unknown work id."""
    store = AtomicWorkStore()
    with pytest.raises(WorkRecordNotFoundError):
        store.read("no-such-work")


def test_authoritative_work_record_is_immutable() -> None:
    """Test authoritative work record is immutable."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.revision = 99  # type: ignore[misc]


def test_authoritative_work_record_rejects_acknowledged_without_result_commit() -> None:
    """Test authoritative work record rejects acknowledged without
    result commit."""
    with pytest.raises(InvalidDistributedProvenanceError):
        AuthoritativeWorkRecord(
            scientific_work_id="work-1",
            distributed_run_context_checksum=RUN_CTX,
            reservation_id=RESERVATION_ID,
            state=WorkItemState.ACKNOWLEDGED_COMPLETED,
            revision=1,
            current_lease_generation=1,
            worker_participant_id="worker-a",
            worker_context_checksum=None,
            cancellation_scope=None,
            result_commit=None,
            acknowledged=True,
            terminal_disposition=None,
            retry_count=0,
            retry_limit=3,
        )


def test_authoritative_work_record_rejects_result_commit_in_wrong_state() -> None:
    """Test authoritative work record rejects result commit in wrong
    state."""
    attempt = make_execution_attempt()
    content = make_synthetic_content("x")
    commit = make_result_commit(attempt, content)
    with pytest.raises(InvalidDistributedProvenanceError):
        AuthoritativeWorkRecord(
            scientific_work_id="work-1",
            distributed_run_context_checksum=RUN_CTX,
            reservation_id=RESERVATION_ID,
            state=WorkItemState.EXECUTING,
            revision=1,
            current_lease_generation=1,
            worker_participant_id="worker-a",
            worker_context_checksum=None,
            cancellation_scope=None,
            result_commit=commit,
            acknowledged=False,
            terminal_disposition=None,
            retry_count=0,
            retry_limit=3,
        )


def test_authoritative_work_record_rejects_terminal_state_without_disposition() -> None:
    """Test authoritative work record rejects terminal state without
    disposition."""
    with pytest.raises(InvalidDistributedProvenanceError):
        AuthoritativeWorkRecord(
            scientific_work_id="work-1",
            distributed_run_context_checksum=RUN_CTX,
            reservation_id=RESERVATION_ID,
            state=WorkItemState.CANCELLED,
            revision=1,
            current_lease_generation=0,
            worker_participant_id=None,
            worker_context_checksum=None,
            cancellation_scope=CancellationScope.BEFORE_ADMISSION,
            result_commit=None,
            acknowledged=False,
            terminal_disposition=None,
            retry_count=0,
            retry_limit=3,
        )


def test_authoritative_work_record_rejects_retry_count_above_limit() -> None:
    """Test authoritative work record rejects retry count above limit."""
    with pytest.raises(InvalidDistributedProvenanceError):
        AuthoritativeWorkRecord(
            scientific_work_id="work-1",
            distributed_run_context_checksum=RUN_CTX,
            reservation_id=RESERVATION_ID,
            state=WorkItemState.PENDING_AVAILABLE,
            revision=0,
            current_lease_generation=0,
            worker_participant_id=None,
            worker_context_checksum=None,
            cancellation_scope=None,
            result_commit=None,
            acknowledged=False,
            terminal_disposition=None,
            retry_count=5,
            retry_limit=3,
        )


def test_acknowledgement_eligible_false_before_commit_true_after_false_after_ack() -> None:
    """Test acknowledgement_eligible property tracks the full lifecycle."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    assert record.acknowledgement_eligible is False

    lease = make_lease(scientific_work_id="work-1")
    record = store.acquire_lease(
        "work-1",
        record.revision,
        lease,
        reservation_validator=_always_valid_reservation,
    )
    record = store.transition_to_executing("work-1", record.revision)
    assert record.acknowledgement_eligible is False

    attempt = make_execution_attempt(scientific_work_id="work-1")
    content = make_synthetic_content("a")
    commit = make_result_commit(attempt, content)
    record = store.commit_result("work-1", record.revision, attempt, commit, _always_present)
    assert record.acknowledgement_eligible is True

    ack = Acknowledgement(
        distributed_orchestration_schema_version=commit.distributed_orchestration_schema_version,
        checksum_algorithm_version=commit.checksum_algorithm_version,
        scientific_work_id="work-1",
        attempt_checksum=attempt.attempt_checksum,
        result_content_checksum=commit.result_content_checksum,
    )
    record = store.acknowledge("work-1", record.revision, ack)
    assert record.acknowledgement_eligible is False
    assert record.acknowledged is True


# ---------------------------------------------------------------------------
# CAS / revision-conflict rejection
# ---------------------------------------------------------------------------


def test_acquire_lease_rejects_stale_expected_revision() -> None:
    """Test acquire lease rejects stale expected revision."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    lease = make_lease(scientific_work_id="work-1")
    store.acquire_lease(
        "work-1",
        record.revision,
        lease,
        reservation_validator=_always_valid_reservation,
    )  # succeeds, revision now 1
    with pytest.raises(RevisionConflictError):
        store.acquire_lease(
            "work-1",
            record.revision,
            lease,
            reservation_validator=_always_valid_reservation,
        )  # stale (0), current is 1


def test_operations_on_unknown_work_id_raise_not_found() -> None:
    """Test operations on unknown work id raise not found."""
    store = AtomicWorkStore()
    lease = make_lease(scientific_work_id="ghost-work")
    with pytest.raises(WorkRecordNotFoundError):
        store.acquire_lease("ghost-work", 0, lease, reservation_validator=_always_valid_reservation)


def test_illegal_transition_leaves_record_unchanged() -> None:
    """Test a rejected operation (illegal transition) leaves the record's
    revision and state completely unchanged -- no partial write."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    # PENDING_AVAILABLE -> EXECUTING is illegal (must go through LEASED)
    with pytest.raises(IllegalStateTransitionError):
        store.transition_to_executing("work-1", record.revision)
    unchanged = store.read("work-1")
    assert unchanged == record


# ---------------------------------------------------------------------------
# Lease acquire / renew / expire / reassign / fencing
# ---------------------------------------------------------------------------


def test_acquire_lease_requires_next_generation() -> None:
    """Test acquire lease requires next generation."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    bad_lease = make_lease(scientific_work_id="work-1", lease_generation=2)
    with pytest.raises(IdentityMismatchError):
        store.acquire_lease(
            "work-1",
            record.revision,
            bad_lease,
            reservation_validator=_always_valid_reservation,
        )


def test_renew_lease_keeps_generation_and_state() -> None:
    """Test renew lease keeps generation and state."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    lease = make_lease(scientific_work_id="work-1")
    record = store.acquire_lease(
        "work-1",
        record.revision,
        lease,
        reservation_validator=_always_valid_reservation,
    )
    renewal = LeaseRenewal(
        distributed_orchestration_schema_version=lease.distributed_orchestration_schema_version,
        checksum_algorithm_version=lease.checksum_algorithm_version,
        scientific_work_id="work-1",
        worker_participant_id="worker-participant-a",
        lease_generation=1,
        renewed_at_logical_clock=5,
    )
    renewed = store.renew_lease("work-1", record.revision, renewal)
    assert renewed.state == WorkItemState.LEASED
    assert renewed.current_lease_generation == 1
    assert renewed.revision == record.revision + 1


def test_renew_lease_rejects_stale_generation() -> None:
    """Test renew lease rejects stale generation (fencing) -- a delayed
    renewal for a generation that has since been reassigned away."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    lease1 = make_lease(
        scientific_work_id="work-1", worker_participant_id="worker-a", lease_generation=1
    )
    record = store.acquire_lease(
        "work-1",
        record.revision,
        lease1,
        reservation_validator=_always_valid_reservation,
    )
    record = store.mark_retryable("work-1", record.revision)
    lease2 = make_lease(
        scientific_work_id="work-1", worker_participant_id="worker-b", lease_generation=2
    )
    record = store.reassign_lease(
        "work-1",
        record.revision,
        lease2,
        reservation_validator=_always_valid_reservation,
    )
    stale_renewal = LeaseRenewal(
        distributed_orchestration_schema_version=lease1.distributed_orchestration_schema_version,
        checksum_algorithm_version=lease1.checksum_algorithm_version,
        scientific_work_id="work-1",
        worker_participant_id="worker-b",
        lease_generation=1,
        renewed_at_logical_clock=5,
    )
    with pytest.raises(StaleLeaseGenerationError):
        store.renew_lease("work-1", record.revision, stale_renewal)


def test_mark_retryable_then_reassign_lease_increments_generation() -> None:
    """Test mark retryable then reassign lease increments generation."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    lease = make_lease(scientific_work_id="work-1")
    record = store.acquire_lease(
        "work-1",
        record.revision,
        lease,
        reservation_validator=_always_valid_reservation,
    )
    record = store.mark_retryable("work-1", record.revision)
    assert record.state == WorkItemState.RETRYABLE
    assert record.retry_count == 1
    new_lease = make_lease(
        scientific_work_id="work-1",
        worker_participant_id="worker-participant-b",
        lease_generation=2,
    )
    record = store.reassign_lease(
        "work-1",
        record.revision,
        new_lease,
        reservation_validator=_always_valid_reservation,
    )
    assert record.state == WorkItemState.LEASED
    assert record.current_lease_generation == 2
    assert record.worker_participant_id == "worker-participant-b"


def test_reassign_lease_rejects_non_incrementing_generation() -> None:
    """Test reassign lease rejects non incrementing generation."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    lease = make_lease(scientific_work_id="work-1")
    record = store.acquire_lease(
        "work-1",
        record.revision,
        lease,
        reservation_validator=_always_valid_reservation,
    )
    record = store.mark_retryable("work-1", record.revision)
    bad_lease = make_lease(scientific_work_id="work-1", lease_generation=1)  # not incremented
    with pytest.raises(IdentityMismatchError):
        store.reassign_lease(
            "work-1",
            record.revision,
            bad_lease,
            reservation_validator=_always_valid_reservation,
        )


def test_dead_letter_from_retryable() -> None:
    """Test dead letter from retryable."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    lease = make_lease(scientific_work_id="work-1")
    record = store.acquire_lease(
        "work-1",
        record.revision,
        lease,
        reservation_validator=_always_valid_reservation,
    )
    record = store.mark_retryable("work-1", record.revision)
    disposition = TerminalDisposition(
        distributed_orchestration_schema_version=lease.distributed_orchestration_schema_version,
        checksum_algorithm_version=lease.checksum_algorithm_version,
        scientific_work_id="work-1",
        disposition=TerminalDispositionKind.DEAD_LETTERED,
        disposition_reason=TerminalDispositionReason.RETRY_CEILING_EXCEEDED,
        attempt_count=record.retry_count,
    )
    record = store.dead_letter("work-1", record.revision, disposition)
    assert record.state == WorkItemState.DEAD_LETTERED
    assert record.terminal_disposition == disposition


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_cancellation_before_admission() -> None:
    """Test cancellation before admission."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    request = CancellationRequest(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        scientific_work_id="work-1",
        cancellation_scope=CancellationScope.BEFORE_ADMISSION,
        requested_at_logical_clock=0,
    )
    record = store.request_cancellation("work-1", record.revision, request)
    assert record.state == WorkItemState.CANCELLED
    assert record.cancellation_scope == CancellationScope.BEFORE_ADMISSION


def test_cancellation_after_lease() -> None:
    """Test cancellation after lease."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    lease = make_lease(scientific_work_id="work-1")
    record = store.acquire_lease(
        "work-1",
        record.revision,
        lease,
        reservation_validator=_always_valid_reservation,
    )
    request = CancellationRequest(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        scientific_work_id="work-1",
        cancellation_scope=CancellationScope.AFTER_LEASE,
        requested_at_logical_clock=1,
    )
    record = store.request_cancellation("work-1", record.revision, request)
    assert record.state == WorkItemState.CANCELLED
    assert record.cancellation_scope == CancellationScope.AFTER_LEASE


def test_cancellation_wrong_scope_rejected() -> None:
    """Test cancellation wrong scope rejected."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    request = CancellationRequest(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        scientific_work_id="work-1",
        cancellation_scope=CancellationScope.AFTER_LEASE,
        requested_at_logical_clock=0,
    )
    with pytest.raises(IdentityMismatchError):
        store.request_cancellation("work-1", record.revision, request)


def test_terminal_evidence_cannot_be_erased_by_cancellation() -> None:
    """Test terminal evidence (a committed result) cannot be erased by a
    later cancellation attempt."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    lease = make_lease(scientific_work_id="work-1")
    record = store.acquire_lease(
        "work-1",
        record.revision,
        lease,
        reservation_validator=_always_valid_reservation,
    )
    record = store.transition_to_executing("work-1", record.revision)
    attempt = make_execution_attempt(scientific_work_id="work-1")
    content = make_synthetic_content("z")
    commit = make_result_commit(attempt, content)
    record = store.commit_result("work-1", record.revision, attempt, commit, _always_present)
    request = CancellationRequest(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        scientific_work_id="work-1",
        cancellation_scope=CancellationScope.AFTER_LEASE,
        requested_at_logical_clock=2,
    )
    with pytest.raises(IllegalStateTransitionError):
        store.request_cancellation("work-1", record.revision, request)
    unchanged = store.read("work-1")
    assert unchanged.state == WorkItemState.RESULT_COMMITTED
    assert unchanged.result_commit == commit


# ---------------------------------------------------------------------------
# commit_result -- the atomic 8-step decision
# ---------------------------------------------------------------------------


def _leased_and_executing(
    store: AtomicWorkStore, scientific_work_id: str
) -> AuthoritativeWorkRecord:
    record = store.create_if_absent(
        scientific_work_id,
        RUN_CTX,
        RESERVATION_ID,
        _always_valid_reservation,
    )
    lease = make_lease(scientific_work_id=scientific_work_id)
    record = store.acquire_lease(
        scientific_work_id,
        record.revision,
        lease,
        reservation_validator=_always_valid_reservation,
    )
    return store.transition_to_executing(scientific_work_id, record.revision)


def test_commit_result_rejects_missing_artifact() -> None:
    """Test commit_result rejects missing artifact -- crash-before-
    artifact-write case: the artifact must be durably present first."""
    store = AtomicWorkStore()
    record = _leased_and_executing(store, "work-1")
    attempt = make_execution_attempt(scientific_work_id="work-1")
    content = make_synthetic_content("m")
    commit = make_result_commit(attempt, content)
    with pytest.raises(MissingArtifactReferenceError):
        store.commit_result("work-1", record.revision, attempt, commit, _never_present)
    unchanged = store.read("work-1")
    assert unchanged.state == WorkItemState.EXECUTING


def test_commit_result_identical_duplicate_is_idempotent() -> None:
    """Test commit_result identical duplicate is idempotent (crash after
    commit, before ack -- safe redelivery recovers, does not re-execute)."""
    store = AtomicWorkStore()
    record = _leased_and_executing(store, "work-1")
    attempt = make_execution_attempt(scientific_work_id="work-1")
    content = make_synthetic_content("dup")
    commit = make_result_commit(attempt, content)
    record = store.commit_result("work-1", record.revision, attempt, commit, _always_present)
    # duplicate delivery of the identical commit against the new revision
    duplicate = store.commit_result("work-1", record.revision, attempt, commit, _always_present)
    assert duplicate.state == WorkItemState.RESULT_COMMITTED
    assert duplicate.result_commit == commit


def test_commit_result_conflicting_duplicate_blocks() -> None:
    """Test commit_result conflicting duplicate blocks without
    overwriting the durable result."""
    store = AtomicWorkStore()
    record = _leased_and_executing(store, "work-1")
    attempt = make_execution_attempt(scientific_work_id="work-1")
    content = make_synthetic_content("first")
    commit = make_result_commit(attempt, content)
    record = store.commit_result("work-1", record.revision, attempt, commit, _always_present)

    conflicting_content = make_synthetic_content("conflicting")
    conflicting_commit = make_result_commit(attempt, conflicting_content)
    with pytest.raises(ConflictingResultCommitError):
        store.commit_result(
            "work-1", record.revision, attempt, conflicting_commit, _always_present
        )
    unchanged = store.read("work-1")
    assert unchanged.result_commit == commit  # original preserved, not overwritten


def test_commit_result_rejects_stale_lease_generation() -> None:
    """Test commit_result rejects stale lease generation -- a worker
    whose lease was reassigned away cannot commit."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    lease1 = make_lease(
        scientific_work_id="work-1", worker_participant_id="worker-a", lease_generation=1
    )
    record = store.acquire_lease(
        "work-1",
        record.revision,
        lease1,
        reservation_validator=_always_valid_reservation,
    )
    record = store.mark_retryable("work-1", record.revision)
    lease2 = make_lease(
        scientific_work_id="work-1", worker_participant_id="worker-b", lease_generation=2
    )
    record = store.reassign_lease(
        "work-1",
        record.revision,
        lease2,
        reservation_validator=_always_valid_reservation,
    )
    record = store.transition_to_executing("work-1", record.revision)

    stale_attempt = make_execution_attempt(
        scientific_work_id="work-1", worker_participant_id="worker-a", lease_generation=1
    )
    content = make_synthetic_content("stale")
    stale_commit = make_result_commit(stale_attempt, content)
    with pytest.raises((IdentityMismatchError, StaleLeaseGenerationError)):
        store.commit_result(
            "work-1", record.revision, stale_attempt, stale_commit, _always_present
        )


def test_commit_result_rejects_forged_future_generation() -> None:
    """Test commit_result rejects a forged/future lease generation that
    was never actually issued."""
    store = AtomicWorkStore()
    record = _leased_and_executing(store, "work-1")
    forged_attempt = make_execution_attempt(scientific_work_id="work-1", lease_generation=99)
    content = make_synthetic_content("forged")
    forged_commit = make_result_commit(forged_attempt, content)
    with pytest.raises((IdentityMismatchError, StaleLeaseGenerationError)):
        store.commit_result(
            "work-1", record.revision, forged_attempt, forged_commit, _always_present
        )


def test_commit_result_rejects_mixed_run_context() -> None:
    """Test commit_result rejects an attempt bound to a different
    distributed run context than the record's own."""
    store = AtomicWorkStore()
    record = _leased_and_executing(store, "work-1")
    mismatched_attempt = make_execution_attempt(
        scientific_work_id="work-1", distributed_run_context_checksum=make_sha256("other-run")
    )
    content = make_synthetic_content("mixed")
    commit = make_result_commit(mismatched_attempt, content)
    with pytest.raises(IdentityMismatchError):
        store.commit_result(
            "work-1", record.revision, mismatched_attempt, commit, _always_present
        )


def test_commit_result_rejects_mismatched_worker_context() -> None:
    """Test commit_result rejects an attempt from a worker other than
    the currently leased one."""
    store = AtomicWorkStore()
    record = _leased_and_executing(store, "work-1")
    other_worker_attempt = make_execution_attempt(
        scientific_work_id="work-1", worker_participant_id="worker-imposter"
    )
    content = make_synthetic_content("imposter")
    commit = make_result_commit(other_worker_attempt, content)
    with pytest.raises(IdentityMismatchError):
        store.commit_result(
            "work-1", record.revision, other_worker_attempt, commit, _always_present
        )


def test_commit_result_rejects_commit_not_matching_attempt() -> None:
    """Test commit_result rejects a commit whose attempt_checksum does
    not match the supplied attempt."""
    store = AtomicWorkStore()
    record = _leased_and_executing(store, "work-1")
    attempt = make_execution_attempt(scientific_work_id="work-1")
    other_attempt = make_execution_attempt(
        scientific_work_id="work-1", worker_participant_id="worker-b"
    )
    content = make_synthetic_content("mismatch")
    commit = make_result_commit(other_attempt, content)  # attempt_checksum from other_attempt
    with pytest.raises(IdentityMismatchError):
        store.commit_result("work-1", record.revision, attempt, commit, _always_present)


def test_commit_result_illegal_from_pending_available() -> None:
    """Test commit_result illegal from pending available (never leased)."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    attempt = make_execution_attempt(scientific_work_id="work-1", lease_generation=1)
    content = make_synthetic_content("never-leased")
    commit = make_result_commit(attempt, content)
    with pytest.raises(IllegalStateTransitionError):
        store.commit_result("work-1", record.revision, attempt, commit, _always_present)


# ---------------------------------------------------------------------------
# Acknowledgement
# ---------------------------------------------------------------------------


def test_acknowledge_requires_result_committed_state() -> None:
    """Test acknowledge requires result committed state (cannot precede
    durable commit)."""
    store = AtomicWorkStore()
    record = _leased_and_executing(store, "work-1")
    attempt = make_execution_attempt(scientific_work_id="work-1")
    content = make_synthetic_content("ack-test")
    commit = make_result_commit(attempt, content)
    ack = Acknowledgement(
        distributed_orchestration_schema_version=commit.distributed_orchestration_schema_version,
        checksum_algorithm_version=commit.checksum_algorithm_version,
        scientific_work_id="work-1",
        attempt_checksum=attempt.attempt_checksum,
        result_content_checksum=commit.result_content_checksum,
    )
    with pytest.raises(IllegalStateTransitionError):
        store.acknowledge("work-1", record.revision, ack)


def test_acknowledge_rejects_ack_naming_different_result() -> None:
    """Test acknowledge rejects ack naming different result."""
    store = AtomicWorkStore()
    record = _leased_and_executing(store, "work-1")
    attempt = make_execution_attempt(scientific_work_id="work-1")
    content = make_synthetic_content("real")
    commit = make_result_commit(attempt, content)
    record = store.commit_result("work-1", record.revision, attempt, commit, _always_present)
    wrong_ack = Acknowledgement(
        distributed_orchestration_schema_version=commit.distributed_orchestration_schema_version,
        checksum_algorithm_version=commit.checksum_algorithm_version,
        scientific_work_id="work-1",
        attempt_checksum=attempt.attempt_checksum,
        result_content_checksum=make_sha256("different-result"),
    )
    with pytest.raises(InvalidDistributedProvenanceError):
        store.acknowledge("work-1", record.revision, wrong_ack)


def test_acknowledge_cannot_be_repeated() -> None:
    """Test acknowledge cannot be repeated -- ACKNOWLEDGED_COMPLETED is
    terminal with no self-loop."""
    store = AtomicWorkStore()
    record = _leased_and_executing(store, "work-1")
    attempt = make_execution_attempt(scientific_work_id="work-1")
    content = make_synthetic_content("once")
    commit = make_result_commit(attempt, content)
    record = store.commit_result("work-1", record.revision, attempt, commit, _always_present)
    ack = Acknowledgement(
        distributed_orchestration_schema_version=commit.distributed_orchestration_schema_version,
        checksum_algorithm_version=commit.checksum_algorithm_version,
        scientific_work_id="work-1",
        attempt_checksum=attempt.attempt_checksum,
        result_content_checksum=commit.result_content_checksum,
    )
    record = store.acknowledge("work-1", record.revision, ack)
    with pytest.raises(IllegalStateTransitionError):
        store.acknowledge("work-1", record.revision, ack)


# ---------------------------------------------------------------------------
# MEGB-03H.2C.3B.2B.1 correction: reservation binding -- "reservation
# before admission" and "no leaseability without a currently valid
# reservation" enforced structurally, not by convention.
# ---------------------------------------------------------------------------


def test_create_if_absent_binds_the_supplied_reservation_id() -> None:
    """Test create_if_absent binds the supplied reservation_id onto the
    new record."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    assert record.reservation_id == RESERVATION_ID


def test_create_if_absent_rejects_an_invalid_reservation() -> None:
    """Test create_if_absent refuses to create a new record when the
    reservation does not validate -- "reservation before admission" is a
    structural precondition, not a convention. No record is created."""
    store = AtomicWorkStore()
    with pytest.raises(InvalidReservationError):
        store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _never_valid_reservation)
    with pytest.raises(WorkRecordNotFoundError):
        store.read("work-1")


def test_create_if_absent_idempotent_replay_does_not_revalidate_reservation() -> None:
    """Test that once a record exists, a replayed create_if_absent call
    returns the existing record without re-validating the reservation --
    the reservation was already validated at first creation; the
    idempotent-return path is not a second admission decision."""
    store = AtomicWorkStore()
    first = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    second = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _never_valid_reservation)
    assert first == second


def test_acquire_lease_rejects_when_reservation_no_longer_valid() -> None:
    """Test acquire_lease refuses the LEASED transition when the bound
    reservation is no longer valid, even though it was valid at record
    creation -- a work item must never become leaseable without a
    currently valid reservation. No state change is applied."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    lease = make_lease(scientific_work_id="work-1")
    with pytest.raises(InvalidReservationError):
        store.acquire_lease(
            "work-1", record.revision, lease, reservation_validator=_never_valid_reservation
        )
    unchanged = store.read("work-1")
    assert unchanged.state == WorkItemState.PENDING_AVAILABLE
    assert unchanged.revision == record.revision


def test_reassign_lease_rejects_when_reservation_no_longer_valid() -> None:
    """Test reassign_lease refuses reassignment when the bound
    reservation is no longer valid -- a redelivered/reassigned work item
    is no more leaseable without a valid reservation than a first lease
    is."""
    store = AtomicWorkStore()
    record = store.create_if_absent("work-1", RUN_CTX, RESERVATION_ID, _always_valid_reservation)
    lease1 = make_lease(scientific_work_id="work-1", lease_generation=1)
    record = store.acquire_lease(
        "work-1", record.revision, lease1, reservation_validator=_always_valid_reservation
    )
    record = store.mark_retryable("work-1", record.revision)
    lease2 = make_lease(scientific_work_id="work-1", lease_generation=2)
    with pytest.raises(InvalidReservationError):
        store.reassign_lease(
            "work-1", record.revision, lease2, reservation_validator=_never_valid_reservation
        )
    unchanged = store.read("work-1")
    assert unchanged.state == WorkItemState.RETRYABLE
    assert unchanged.revision == record.revision
