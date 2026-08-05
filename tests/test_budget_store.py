"""MEGB-03H.2C.3B.2B.1: construction/validation and behavior tests for
:mod:`src.distributed.budget_store` -- personal two-worker/$50 ceilings,
idempotent/conflicting reservation replay, and the composed
:func:`~src.distributed.budget_store.evaluate_and_reserve` decision."""

from typing import Callable

import pytest

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
)
from src.distributed.artifact_store import (
    ArtifactMetadata,
    ArtifactMetadataMismatchError,
    InMemoryArtifactStore,
)
from src.distributed.atomic_work_store import AtomicWorkStore, InvalidReservationError
from src.distributed.budget_store import (
    AtomicBudgetStore,
    BudgetCeilingExceededError,
    OrphanReservationDisposition,
    ReservationConflictError,
    ReservationNotActiveError,
    ReservationNotFoundError,
    ReservationStatus,
    WorkerCeilingExceededError,
    diagnose_reservation_work_binding,
    evaluate_and_reserve,
)
from src.distributed.personal_policy import (
    DataClassification,
    PersonalEnvironmentPolicy,
    WorkloadClass,
)
from src.distributed.provenance import EnvironmentClass
from tests._atomic_stores_fixtures import make_result_artifact_reference, make_synthetic_content
from tests._distributed_orchestration_fixtures import make_sha256

PERSONAL_BOOTSTRAP_MAX_WORKERS = 2
PERSONAL_BOOTSTRAP_CEILING_CENTS = 5000


def _policy() -> PersonalEnvironmentPolicy:
    return PersonalEnvironmentPolicy(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        environment_class=EnvironmentClass.PERSONAL_BOOTSTRAP,
        allowed_workload_classes=(WorkloadClass.SYNTHETIC_SMOKE,),
        max_admitted_workers=PERSONAL_BOOTSTRAP_MAX_WORKERS,
        spending_ceiling_cents=PERSONAL_BOOTSTRAP_CEILING_CENTS,
    )


def _budget_store() -> AtomicBudgetStore:
    return AtomicBudgetStore(
        budget_ceiling_cents=PERSONAL_BOOTSTRAP_CEILING_CENTS,
        max_admitted_workers=PERSONAL_BOOTSTRAP_MAX_WORKERS,
    )


# ---------------------------------------------------------------------------
# BudgetReservation / AtomicBudgetStore construction and validation
# ---------------------------------------------------------------------------


def test_reserve_admits_within_ceilings() -> None:
    """Test reserve admits within ceilings."""
    store = _budget_store()
    reservation = store.reserve("res-1", 1000, 1)
    assert reservation.status == ReservationStatus.RESERVED
    assert reservation.requested_cost_cents == 1000
    assert reservation.actual_cost_cents is None


def test_reserve_accepts_exactly_the_ceiling_value() -> None:
    """Test reserve accepts exactly the ceiling value (both cost and
    worker count)."""
    store = _budget_store()
    reservation = store.reserve(
        "res-1", PERSONAL_BOOTSTRAP_CEILING_CENTS, PERSONAL_BOOTSTRAP_MAX_WORKERS
    )
    assert reservation.requested_cost_cents == PERSONAL_BOOTSTRAP_CEILING_CENTS
    assert reservation.requested_worker_count == PERSONAL_BOOTSTRAP_MAX_WORKERS


def test_reserve_rejects_cost_one_cent_above_ceiling() -> None:
    """Test reserve rejects cost one cent above ceiling."""
    store = _budget_store()
    with pytest.raises(BudgetCeilingExceededError):
        store.reserve("res-1", PERSONAL_BOOTSTRAP_CEILING_CENTS + 1, 1)


def test_reserve_rejects_worker_count_one_above_ceiling() -> None:
    """Test reserve rejects worker count one above ceiling."""
    store = _budget_store()
    with pytest.raises(WorkerCeilingExceededError):
        store.reserve("res-1", 1000, PERSONAL_BOOTSTRAP_MAX_WORKERS + 1)


def test_concurrent_reservations_cannot_together_oversubscribe_the_ceiling() -> None:
    """Test two separate, individually-valid reservations that together
    would exceed the ceiling -- the second is refused."""
    store = _budget_store()
    store.reserve("res-1", 3000, 1)
    with pytest.raises(BudgetCeilingExceededError):
        store.reserve("res-2", 3000, 1)  # 3000+3000=6000 > 5000


def test_reserve_idempotent_replay_of_same_reservation() -> None:
    """Test reserve idempotent replay of same reservation."""
    store = _budget_store()
    first = store.reserve("res-1", 1000, 1)
    second = store.reserve("res-1", 1000, 1)
    assert first == second


def test_reserve_rejects_conflicting_replay_different_cost() -> None:
    """Test reserve rejects conflicting replay different cost."""
    store = _budget_store()
    store.reserve("res-1", 1000, 1)
    with pytest.raises(ReservationConflictError):
        store.reserve("res-1", 2000, 1)


def test_reserve_rejects_conflicting_replay_different_worker_count() -> None:
    """Test reserve rejects conflicting replay different worker count."""
    store = _budget_store()
    store.reserve("res-1", 1000, 1)
    with pytest.raises(ReservationConflictError):
        store.reserve("res-1", 1000, 2)


def test_reserve_rejects_negative_cost() -> None:
    """Test reserve rejects negative cost."""
    store = _budget_store()
    with pytest.raises(InvalidDistributedProvenanceError):
        store.reserve("res-1", -1, 1)


def test_reserve_rejects_non_positive_worker_count() -> None:
    """Test reserve rejects non positive worker count."""
    store = _budget_store()
    with pytest.raises(InvalidDistributedProvenanceError):
        store.reserve("res-1", 1000, 0)


def test_budget_store_rejects_non_positive_ceiling() -> None:
    """Test budget store rejects non positive ceiling."""
    with pytest.raises(InvalidDistributedProvenanceError):
        AtomicBudgetStore(budget_ceiling_cents=0, max_admitted_workers=2)


def test_budget_store_rejects_non_positive_max_workers() -> None:
    """Test budget store rejects non positive max workers."""
    with pytest.raises(InvalidDistributedProvenanceError):
        AtomicBudgetStore(budget_ceiling_cents=5000, max_admitted_workers=0)


# ---------------------------------------------------------------------------
# release / finalize -- explicit semantics, distinct from reserved amount
# ---------------------------------------------------------------------------


def test_release_frees_the_reserved_slot() -> None:
    """Test release frees the reserved slot -- a subsequent reservation
    that would otherwise oversubscribe now succeeds."""
    store = _budget_store()
    store.reserve("res-1", 3000, 1)
    store.release("res-1")
    store.reserve("res-2", 3000, 1)  # would have failed had res-1 stayed active
    released = store.get("res-1")
    assert released.status == ReservationStatus.RELEASED


def test_release_unknown_reservation_raises_not_found() -> None:
    """Test release unknown reservation raises not found."""
    store = _budget_store()
    with pytest.raises(ReservationNotFoundError):
        store.release("no-such-reservation")


def test_release_already_released_raises_not_active() -> None:
    """Test release already released raises not active."""
    store = _budget_store()
    store.reserve("res-1", 1000, 1)
    store.release("res-1")
    with pytest.raises(ReservationNotActiveError):
        store.release("res-1")


def test_finalize_records_actual_cost_distinct_from_requested() -> None:
    """Test finalize records actual cost distinct from requested --
    actual-versus-reserved accounting is typed and independently
    observable."""
    store = _budget_store()
    store.reserve("res-1", 3000, 1)
    finalized = store.finalize("res-1", 1234)
    assert finalized.status == ReservationStatus.FINALIZED
    assert finalized.requested_cost_cents == 3000
    assert finalized.actual_cost_cents == 1234


def test_finalize_already_finalized_raises_not_active() -> None:
    """Test finalize already finalized raises not active."""
    store = _budget_store()
    store.reserve("res-1", 1000, 1)
    store.finalize("res-1", 900)
    with pytest.raises(ReservationNotActiveError):
        store.finalize("res-1", 900)


def test_finalize_rejects_negative_actual_cost() -> None:
    """Test finalize rejects negative actual cost."""
    store = _budget_store()
    store.reserve("res-1", 1000, 1)
    with pytest.raises(InvalidDistributedProvenanceError):
        store.finalize("res-1", -1)


# ---------------------------------------------------------------------------
# evaluate_and_reserve -- the composed classification+policy+budget decision
# ---------------------------------------------------------------------------


def test_evaluate_and_reserve_admits_valid_synthetic_workload() -> None:
    """Test evaluate and reserve admits valid synthetic workload."""
    astore = InMemoryArtifactStore()
    content = make_synthetic_content("budget-1")
    reference = make_result_artifact_reference(content)
    astore.put(
        reference,
        content,
        ArtifactMetadata(
            workload_class=WorkloadClass.SYNTHETIC_SMOKE,
            data_classification=DataClassification.SYNTHETIC,
        ),
    )
    bstore = _budget_store()
    decision = evaluate_and_reserve(
        _policy(), bstore, astore, reference, WorkloadClass.SYNTHETIC_SMOKE,
        DataClassification.SYNTHETIC, "res-1", 1000, 1,
    )
    assert decision.admitted is True
    assert bstore.get("res-1").status == ReservationStatus.RESERVED


def test_evaluate_and_reserve_raises_on_classification_mismatch() -> None:
    """Test evaluate_and_reserve never trusts a claimed classification
    that does not match the artifact store's own immutably-bound
    metadata -- raises rather than silently proceeding."""
    astore = InMemoryArtifactStore()
    content = make_synthetic_content("budget-2")
    reference = make_result_artifact_reference(content)
    astore.put(
        reference,
        content,
        ArtifactMetadata(
            workload_class=WorkloadClass.SYNTHETIC_SMOKE,
            data_classification=DataClassification.SYNTHETIC,
        ),
    )
    bstore = _budget_store()
    with pytest.raises(ArtifactMetadataMismatchError):
        evaluate_and_reserve(
            _policy(), bstore, astore, reference, WorkloadClass.PRODUCTION,
            DataClassification.SYNTHETIC, "res-1", 1000, 1,
        )
    with pytest.raises(ReservationNotFoundError):
        bstore.get("res-1")  # never reserved -- rejected before the ledger


def test_evaluate_and_reserve_refuses_disallowed_workload_class_without_raising() -> None:
    """Test evaluate_and_reserve returns a refusing AdmissionDecision
    (not an exception) for a policy-level refusal, and never reserves
    budget for it."""
    astore = InMemoryArtifactStore()
    content = make_synthetic_content("budget-3")
    metadata = ArtifactMetadata(
        workload_class=WorkloadClass.PRODUCTION,
        data_classification=DataClassification.SYNTHETIC,
    )
    reference = make_result_artifact_reference(content, metadata=metadata)
    astore.put(reference, content, metadata)
    bstore = _budget_store()
    decision = evaluate_and_reserve(
        _policy(), bstore, astore, reference, WorkloadClass.PRODUCTION,
        DataClassification.SYNTHETIC, "res-1", 1000, 1,
    )
    assert decision.admitted is False
    with pytest.raises(ReservationNotFoundError):
        bstore.get("res-1")


# ---------------------------------------------------------------------------
# MEGB-03H.2C.3B.2B.1 correction: reservation/work-creation crash-window
# recovery -- a deterministic, recoverable two-step protocol with
# explicit, non-leaseable intermediate states, never a claim of genuine
# cross-store atomicity.
# ---------------------------------------------------------------------------

RUN_CTX = make_sha256("budget-reservation-run-context")


def _reservation_validator(bstore: AtomicBudgetStore) -> Callable[[str], bool]:
    def _validate(reservation_id: str) -> bool:
        try:
            return bstore.get(reservation_id).status == ReservationStatus.RESERVED
        except ReservationNotFoundError:
            return False

    return _validate


def test_reservation_before_work_creation_then_resume_after_simulated_crash() -> None:
    """Test the crash window between a successful reservation and work
    creation: the reservation succeeds, work creation is never reached
    (simulated crash), and a recovering caller diagnoses RESUMABLE and
    safely retries create_if_absent."""
    bstore = _budget_store()
    wstore = AtomicWorkStore()
    bstore.reserve("res-crash-1", 1000, 1)
    # Simulated crash: create_if_absent was never called.

    disposition = diagnose_reservation_work_binding(bstore, wstore, "work-crash-1", "res-crash-1")
    assert disposition == OrphanReservationDisposition.RESUMABLE

    record = wstore.create_if_absent(
        "work-crash-1", RUN_CTX, "res-crash-1", _reservation_validator(bstore)
    )
    assert record.reservation_id == "res-crash-1"
    assert (
        diagnose_reservation_work_binding(bstore, wstore, "work-crash-1", "res-crash-1")
        == OrphanReservationDisposition.NO_ACTION_NEEDED
    )


def test_reservation_before_work_creation_then_release_after_simulated_crash() -> None:
    """Test the same crash window, but the recovering caller instead
    chooses to release the orphaned reservation rather than resume --
    both are valid, deterministic recovery actions from a RESUMABLE
    diagnosis."""
    bstore = _budget_store()
    wstore = AtomicWorkStore()
    bstore.reserve("res-crash-2", 1000, 1)

    assert (
        diagnose_reservation_work_binding(bstore, wstore, "work-crash-2", "res-crash-2")
        == OrphanReservationDisposition.RESUMABLE
    )
    bstore.release("res-crash-2")
    assert (
        diagnose_reservation_work_binding(bstore, wstore, "work-crash-2", "res-crash-2")
        == OrphanReservationDisposition.ALREADY_RESOLVED
    )
    # A subsequent create_if_absent attempt against the now-released
    # reservation is correctly refused -- work cannot be admitted without
    # a currently valid reservation.
    with pytest.raises(InvalidReservationError):
        wstore.create_if_absent(
            "work-crash-2", RUN_CTX, "res-crash-2", _reservation_validator(bstore)
        )


def test_diagnose_reservation_work_binding_raises_for_unknown_reservation() -> None:
    """Test diagnose_reservation_work_binding raises for a reservation
    that was never made -- there is nothing to diagnose."""
    bstore = _budget_store()
    wstore = AtomicWorkStore()
    with pytest.raises(ReservationNotFoundError):
        diagnose_reservation_work_binding(bstore, wstore, "work-x", "no-such-reservation")


def test_diagnose_reservation_work_binding_detects_conflicting_binding() -> None:
    """Test diagnose_reservation_work_binding reports CONFLICTING_BINDING
    when a work record already exists bound to a different
    reservation_id than the one supplied -- a protocol violation that
    must never occur under correct reserve-before-admission usage, but
    must be surfaced rather than silently ignored if it does."""
    bstore = _budget_store()
    wstore = AtomicWorkStore()
    bstore.reserve("res-a", 1000, 1)
    bstore.reserve("res-b", 1000, 1)
    wstore.create_if_absent("work-conflict", RUN_CTX, "res-a", _reservation_validator(bstore))
    disposition = diagnose_reservation_work_binding(bstore, wstore, "work-conflict", "res-b")
    assert disposition == OrphanReservationDisposition.CONFLICTING_BINDING


def test_work_creation_without_a_valid_reservation_is_refused() -> None:
    """Test that work creation naming a reservation_id that was never
    reserved is refused outright -- work cannot be admitted without
    reservation."""
    bstore = _budget_store()
    wstore = AtomicWorkStore()
    with pytest.raises(InvalidReservationError):
        wstore.create_if_absent(
            "work-no-reservation", RUN_CTX, "never-reserved", _reservation_validator(bstore)
        )


def test_release_then_release_again_raises_not_active_never_double_credits() -> None:
    """Test that releasing an already-released reservation raises rather
    than silently double-crediting the budget ledger."""
    store = _budget_store()
    store.reserve("res-1", 1000, 1)
    store.release("res-1")
    with pytest.raises(ReservationNotActiveError):
        store.release("res-1")


def test_finalize_then_release_raises_not_active_never_double_credits() -> None:
    """Test that finalizing then attempting to release the same
    reservation raises -- finalize and release are mutually exclusive
    terminal outcomes, never both applied to the same reservation."""
    store = _budget_store()
    store.reserve("res-1", 1000, 1)
    store.finalize("res-1", 900)
    with pytest.raises(ReservationNotActiveError):
        store.release("res-1")
