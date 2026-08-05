"""MEGB-03H.2C.3B.2B.2: admission-flow tests for
:mod:`src.distributed.coordinator` -- ordering, trusted metadata
verification, policy refusal before publication, exact budget
reservation, conflicting/duplicate admission, and crash-window
diagnostics."""

from src.distributed.budget_store import (
    OrphanReservationDisposition,
    ReservationStatus,
    diagnose_reservation_work_binding,
)
from src.distributed.coordinator import (
    WorkPublicationDisposition,
    diagnose_work_publication_binding,
)
from src.distributed.personal_policy import (
    AdmissionRefusalReason,
    DataClassification,
    WorkloadClass,
)
from src.distributed.work_outcome import WorkOutcomeKind
from tests._coordinator_fixtures import (
    ScriptedExecutor,
    build_environment,
    make_synthetic_content,
    make_work_descriptor,
    make_worker_registration,
    publish_candidate,
)


def test_successful_admission_returns_none_and_publishes_to_queue() -> None:
    """Test successful admission returns None (admitted) and publishes
    to the queue exactly once."""
    env = build_environment()
    content = make_synthetic_content("a")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())

    outcome = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
    )
    assert outcome is None
    assert env.queue.in_flight_count() == 1
    record = env.work_store.read("work-1")
    assert record.reservation_id == "res-1"


def test_admission_verifies_metadata_from_the_trusted_store_not_a_claim() -> None:
    """Test admission reads classification from the trusted artifact
    store directly -- never from any caller-supplied claim (this
    Coordinator API accepts no such claim parameter at all)."""
    env = build_environment()
    content = make_synthetic_content("b")
    reference = publish_candidate(
        env.artifact_store, content, data_classification=DataClassification.SYNTHETIC
    )
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    outcome = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
    )
    assert outcome is None  # SYNTHETIC is allowlisted -- admitted


def test_policy_refusal_occurs_before_queue_publication() -> None:
    """Test policy refusal occurs before queue publication -- a
    disallowed workload class never reaches the queue."""
    env = build_environment()
    content = make_synthetic_content("c")
    reference = publish_candidate(
        env.artifact_store, content, workload_class=WorkloadClass.CALIBRATION
    )
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    outcome = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
    )
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.POLICY_BLOCKED
    assert AdmissionRefusalReason.WORKLOAD_CLASS_NOT_ALLOWLISTED in outcome.policy_refusal_reasons
    assert env.queue.in_flight_count() == 0
    assert env.queue.receive() is None


def test_protected_data_classification_cannot_enter_a_personal_run() -> None:
    """Test protected/incorrectly classified artifacts cannot enter a
    personal run."""
    env = build_environment()
    content = make_synthetic_content("d")
    reference = publish_candidate(
        env.artifact_store,
        content,
        data_classification=DataClassification.PRIVILEGED_REFERENCE,
    )
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    outcome = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
    )
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.POLICY_BLOCKED
    assert AdmissionRefusalReason.DATA_CLASSIFICATION_REFUSED in outcome.policy_refusal_reasons
    assert env.queue.in_flight_count() == 0


def test_budget_ceiling_exceeded_blocks_admission() -> None:
    """Test budget ceiling exceeded blocks admission, and no work record
    or queue entry is ever created."""
    env = build_environment(budget_ceiling_cents=100)
    content = make_synthetic_content("e")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    outcome = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=1000, requested_worker_count=1
    )
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.BUDGET_BLOCKED
    assert env.queue.in_flight_count() == 0
    assert diagnose_work_publication_binding(
        env.work_store, env.queue, "work-1"
    ) == WorkPublicationDisposition.NOT_YET_ADMITTED


def test_exact_budget_reservation_is_created_at_the_requested_amount() -> None:
    """Test exact budget reservation is created at the requested
    amount -- integer cents, exactly."""
    env = build_environment()
    content = make_synthetic_content("f")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=1234, requested_worker_count=1
    )
    reservation = env.budget_store.get("res-1")
    assert reservation.requested_cost_cents == 1234
    assert reservation.status == ReservationStatus.RESERVED


def test_admission_replay_with_the_same_reservation_id_is_idempotent() -> None:
    """Test admission replay with the same reservation_id is idempotent
    -- duplicate admission never double-reserves or double-publishes."""
    env = build_environment()
    content = make_synthetic_content("g")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    first = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
    )
    second = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
    )
    assert first is None
    assert second is None
    assert env.queue.in_flight_count() == 1


def test_admission_with_a_conflicting_reservation_id_blocks_and_releases() -> None:
    """Test that admitting the same scientific_work_id a second time
    with a *different* reservation_id blocks -- conflicting reservation
    binding -- and the second, unused reservation is released rather
    than leaked."""
    env = build_environment()
    content = make_synthetic_content("h")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    first = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
    )
    second = coordinator.admit(
        descriptor, reservation_id="res-2", requested_cost_cents=100, requested_worker_count=1
    )
    assert first is None
    assert second is not None
    assert second.outcome_kind == WorkOutcomeKind.CONFLICTING_RESULT
    assert env.budget_store.get("res-2").status == ReservationStatus.RELEASED
    # the original binding is untouched
    assert env.work_store.read("work-1").reservation_id == "res-1"


def test_reservation_before_work_creation_crash_window_is_diagnosable() -> None:
    """Test reservation-before-work-creation crash window is
    diagnosable/resumable via
    :func:`~src.distributed.budget_store.diagnose_reservation_work_binding`
    -- exercised directly at the store layer, since this window is
    strictly between two store calls the coordinator itself makes
    sequentially."""
    env = build_environment()
    env.budget_store.reserve("res-crash", 100, 1)
    disposition = diagnose_reservation_work_binding(
        env.budget_store, env.work_store, "work-crash", "res-crash"
    )
    assert disposition == OrphanReservationDisposition.RESUMABLE


def test_work_creation_before_publication_crash_window_is_diagnosable() -> None:
    """Test work-creation-before-publication crash window is
    diagnosable/resumable -- a work record created but never published
    is ADMITTED_NOT_PUBLISHED, and re-publishing is safe (idempotent)."""
    env = build_environment()
    content = make_synthetic_content("i")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)

    env.budget_store.reserve("res-1", 100, 1)
    env.work_store.create_if_absent(
        "work-1", descriptor.distributed_run_context_checksum, "res-1", lambda _rid: True
    )
    # Simulated crash: queue.publish was never called.
    assert (
        diagnose_work_publication_binding(env.work_store, env.queue, "work-1")
        == WorkPublicationDisposition.ADMITTED_NOT_PUBLISHED
    )
    env.queue.publish(descriptor)
    assert (
        diagnose_work_publication_binding(env.work_store, env.queue, "work-1")
        == WorkPublicationDisposition.PUBLISHED
    )
    # Resuming (re-publish) is safe/idempotent.
    env.queue.publish(descriptor)
    assert env.queue.in_flight_count() == 1


def test_diagnose_work_publication_binding_reports_not_yet_admitted() -> None:
    """Test diagnose_work_publication_binding reports NOT_YET_ADMITTED
    when no work record exists at all."""
    env = build_environment()
    assert (
        diagnose_work_publication_binding(env.work_store, env.queue, "never-admitted")
        == WorkPublicationDisposition.NOT_YET_ADMITTED
    )


def test_cancellation_before_admission_is_observed() -> None:
    """Test cancellation before admission is observed -- no reservation,
    work record, or queue entry is ever created."""
    env = build_environment()
    content = make_synthetic_content("j")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.request_cancellation("work-1")
    outcome = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
    )
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.CANCELLED_NOT_STARTED
    assert env.queue.in_flight_count() == 0


def test_worker_registration_is_independent_of_admission() -> None:
    """Test that admission does not require any worker to be registered
    yet -- registration/admission are independent phases."""
    env = build_environment()
    content = make_synthetic_content("k")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    outcome = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
    )
    assert outcome is None
    env.worker_registry.register(make_worker_registration("worker-a"))
    result = coordinator.invoke_worker("worker-a")
    assert result is not None
    assert result.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
