"""MEGB-03H.2C.3B.2B.2: worker-execution-flow tests for
:mod:`src.distributed.coordinator` -- fencing, retry, cancellation at
every phase, duplicate delivery, ack-failure recovery, artifact conflict,
and safe executor-failure handling."""

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
)
from src.distributed.artifact_store import ArtifactMetadata
from src.distributed.audit_sink_store import InMemoryAuditSink
from src.distributed.budget_store import ReservationStatus
from src.distributed.coordinator import Coordinator
from src.distributed.personal_policy import DataClassification, WorkloadClass
from src.distributed.state_machine import WorkItemState
from src.distributed.work_contracts import TerminalDispositionReason
from src.distributed.work_outcome import WorkOutcomeKind
from src.distributed.worker_contracts import Lease
from tests._atomic_stores_fixtures import make_result_commit
from tests._coordinator_fixtures import (
    RUN_CTX,
    RaisingExecutor,
    ScriptedExecutor,
    build_environment,
    make_synthetic_content,
    make_work_descriptor,
    make_worker_registration,
    publish_candidate,
    retryable_failure,
    terminal_failure,
)
from tests._distributed_orchestration_fixtures import make_execution_attempt

_DEFAULT_METADATA = ArtifactMetadata(
    workload_class=WorkloadClass.SYNTHETIC_SMOKE, data_classification=DataClassification.SYNTHETIC
)


def _make_lease(worker_participant_id: str, lease_generation: int = 1) -> Lease:
    return Lease(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        scientific_work_id="work-1",
        worker_participant_id=worker_participant_id,
        lease_generation=lease_generation,
        lease_issued_at_logical_clock=0,
        lease_duration_logical_ticks=5,
    )


def test_happy_path_commits_and_finalizes_budget() -> None:
    """Test happy path commits and finalizes budget."""
    env = build_environment()
    content = make_synthetic_content("a")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor()
    coordinator = env.make_coordinator(executor)

    assert (
        coordinator.admit(
            descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
        )
        is None
    )
    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    assert executor.invocation_count == 1
    reservation = env.budget_store.get("res-1")
    assert reservation.status == ReservationStatus.FINALIZED
    assert reservation.actual_cost_cents == 100


def test_unregistered_worker_is_rejected() -> None:
    """Test unregistered worker is rejected."""
    env = build_environment()
    content = make_synthetic_content("b")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    outcome = coordinator.invoke_worker("worker-unregistered")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.INFRASTRUCTURE_FAILURE


def test_worker_registered_under_a_different_run_context_is_rejected() -> None:
    """Test worker registered under a different run context is
    rejected -- wrong-run fencing."""
    env = build_environment()
    content = make_synthetic_content("c")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(
        make_worker_registration("worker-a", run_context_checksum="f" * 64)
    )
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.INFRASTRUCTURE_FAILURE


def test_a_stale_worker_racing_against_an_already_leased_item_gets_stale_lease() -> None:
    """Test a stale/duplicate delivery for an already-leased work item
    yields STALE_LEASE, never a second commit."""
    env = build_environment()
    content = make_synthetic_content("d")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    # Directly force the record into LEASED-by-worker-b, simulating a
    # lease already held by another worker before worker-a's (redelivered)
    # message is processed.
    record = env.work_store.read("work-1")
    env.work_store.acquire_lease(
        "work-1", record.revision, _make_lease("worker-b"), reservation_validator=lambda _rid: True
    )

    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.STALE_LEASE
    final = env.work_store.read("work-1")
    assert final.worker_participant_id == "worker-b"


def test_recovery_path_when_result_committed_but_never_acked() -> None:
    """Test the recovery path when a result was durably committed but
    the queue message was never acknowledged (simulating a crash between
    commit and ack) -- redelivery must recover the existing result
    without invoking the executor again. This is the same mechanism that
    proves duplicate delivery after commit is harmless."""
    env = build_environment()
    content = make_synthetic_content("f")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    message = env.queue.receive()
    assert message is not None
    record = env.work_store.read("work-1")
    record = env.work_store.acquire_lease(
        "work-1", record.revision, _make_lease("worker-a"), reservation_validator=lambda _rid: True
    )
    record = env.work_store.transition_to_executing("work-1", record.revision)

    attempt = make_execution_attempt(
        scientific_work_id="work-1",
        worker_participant_id="worker-a",
        lease_generation=1,
        distributed_run_context_checksum=RUN_CTX,
    )
    result_content = b"synthetic-manually-committed-result"
    commit = make_result_commit(attempt, result_content)
    env.artifact_store.put(commit.result_artifact_reference, result_content, _DEFAULT_METADATA)
    env.work_store.commit_result(
        "work-1", record.revision, attempt, commit, artifact_resolver=env.artifact_store.resolve
    )
    # queue.ack("work-1") deliberately NOT called -- simulating a crash
    # between durable commit and acknowledgement.

    env.clock.advance(10)  # elapse visibility timeout -> redelivery
    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.RECOVERED_COMMITTED_RESULT
    assert executor.invocation_count == 0  # never invoked


def test_heartbeat_renews_the_lease() -> None:
    """Test heartbeat renews the lease -- extends this coordinator's own
    tracked expiry without changing state or generation."""
    env = build_environment()
    content = make_synthetic_content("g")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    record = env.work_store.read("work-1")
    env.work_store.acquire_lease(
        "work-1", record.revision, _make_lease("worker-a"), reservation_validator=lambda _rid: True
    )
    coordinator.renew_lease("work-1", "worker-a")  # must not raise
    final = env.work_store.read("work-1")
    assert final.current_lease_generation == 1
    assert final.state == WorkItemState.LEASED


def test_lease_expiry_and_reassignment_through_the_logical_clock() -> None:
    """Test lease expiry and reassignment through the logical clock --
    an explicit, caller-driven check (never an autonomous timer)."""
    env = build_environment()
    content = make_synthetic_content("h")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    executor = ScriptedExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    message = env.queue.receive()
    assert message is not None
    record = env.work_store.read("work-1")
    env.work_store.acquire_lease(
        "work-1", record.revision, _make_lease("worker-a"), reservation_validator=lambda _rid: True
    )
    # Acquired directly via the store, bypassing the coordinator's own
    # bookkeeping -- simulate tracking the expiry as the coordinator
    # would have, then advance past it.
    coordinator._lease_expiry["work-1"] = 5  # pylint: disable=protected-access
    env.clock.advance(10)
    assert coordinator.check_lease_expiry("work-1") is True
    expired = env.work_store.read("work-1")
    assert expired.state == WorkItemState.RETRYABLE

    env.clock.advance(10)  # elapse queue visibility too
    outcome = coordinator.invoke_worker("worker-b")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    final = env.work_store.read("work-1")
    assert final.worker_participant_id == "worker-b"
    assert final.current_lease_generation == 2


def test_retryable_failure_then_success_on_retry() -> None:
    """Test retryable failure then success on retry."""
    env = build_environment()
    content = make_synthetic_content("i")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor(script=[retryable_failure()])
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    first = coordinator.invoke_worker("worker-a")
    assert first is not None
    assert first.outcome_kind == WorkOutcomeKind.RETRY_SCHEDULED
    assert env.work_store.read("work-1").state == WorkItemState.RETRYABLE

    env.clock.advance(10)  # elapse visibility -> redelivery
    second = coordinator.invoke_worker("worker-a")
    assert second is not None
    assert second.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    assert executor.invocation_count == 2


def test_retry_exhaustion_dead_letters() -> None:
    """Test retry exhaustion dead letters -- the retry ceiling
    (DEFAULT_RETRY_LIMIT=3) is reached and the item terminally
    dead-letters."""
    env = build_environment()
    content = make_synthetic_content("j")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor(
        script=[retryable_failure(), retryable_failure(), retryable_failure()]
    )
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    outcomes = []
    for _ in range(3):
        outcomes.append(coordinator.invoke_worker("worker-a"))
        env.clock.advance(10)

    assert [outcome.outcome_kind for outcome in outcomes if outcome is not None] == [
        WorkOutcomeKind.RETRY_SCHEDULED,
        WorkOutcomeKind.RETRY_SCHEDULED,
        WorkOutcomeKind.RETRY_EXHAUSTED,
    ]
    assert env.work_store.read("work-1").state == WorkItemState.DEAD_LETTERED
    assert env.queue.receive() is None  # acked on dead-letter -- no redelivery
    # MEGB-03H.2C.3B.2B.2 correction: genuine retry-ceiling exhaustion is
    # tagged RETRY_CEILING_EXCEEDED -- retries really were attempted and
    # really were exhausted here.
    terminal_disposition = env.work_store.read("work-1").terminal_disposition
    assert terminal_disposition is not None
    assert (
        terminal_disposition.disposition_reason
        == TerminalDispositionReason.RETRY_CEILING_EXCEEDED
    )


def test_terminal_executor_failure_dead_letters_immediately() -> None:
    """Test a terminal (non-retryable) executor failure dead-letters
    immediately, without waiting for the retry ceiling."""
    env = build_environment()
    content = make_synthetic_content("k")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor(script=[terminal_failure()])
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.RETRY_EXHAUSTED
    # MEGB-03H.2C.3B.2B.2 correction: a terminal (non-retryable) failure on
    # the very first attempt must never be tagged RETRY_CEILING_EXCEEDED --
    # no retry ceiling was ever exceeded, since no retry was ever attempted.
    terminal_disposition = env.work_store.read("work-1").terminal_disposition
    assert terminal_disposition is not None
    assert (
        terminal_disposition.disposition_reason
        == TerminalDispositionReason.NON_RETRYABLE_EXECUTOR_FAILURE
    )
    assert terminal_disposition.attempt_count == 1
    assert env.work_store.read("work-1").state == WorkItemState.DEAD_LETTERED


def test_cancellation_before_lease() -> None:
    """Test cancellation before lease -- requested after admission but
    before any worker receives the delivery."""
    env = build_environment()
    content = make_synthetic_content("l")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    coordinator.request_cancellation("work-1")

    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.CANCELLED_NOT_STARTED
    assert executor.invocation_count == 0
    assert env.work_store.read("work-1").state == WorkItemState.CANCELLED


def test_cancellation_after_commit_has_no_effect_terminal_evidence_preserved() -> None:
    """Test cancellation after commit has no effect -- terminal evidence
    (an already-committed result) is never erased by a later
    cancellation request."""
    env = build_environment()
    content = make_synthetic_content("n")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED

    coordinator.request_cancellation("work-1")  # too late -- must have no effect
    final = env.work_store.read("work-1")
    assert final.state == WorkItemState.RESULT_COMMITTED
    assert final.result_commit is not None


def test_executor_raises_without_leaking_its_message() -> None:
    """Test executor raises without leaking its message -- an
    infrastructure/internal failure outcome carries no raw exception
    text anywhere."""
    env = build_environment()
    content = make_synthetic_content("o")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = RaisingExecutor("unsafe-diagnostic-should-never-leak-12345")
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.INFRASTRUCTURE_FAILURE
    assert executor.message not in repr(outcome)
    for event in env.audit_sink.events():
        assert executor.message not in repr(event)


def test_committed_result_content_checksum_is_present_and_stable() -> None:
    """Test the committed result's content checksum is present and
    stable -- the durable identity a conflicting duplicate commit would
    be checked against (see B.2B.1's own exhaustive
    reconcile_result_commit coverage for the conflict/idempotent matrix
    itself; this test proves the coordinator's own commit path produces
    a well-formed, checkable commit record)."""
    env = build_environment()
    content = make_synthetic_content("p")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor(default_result_content=b"first-result")
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED

    final = env.work_store.read("work-1")
    assert final.result_commit is not None
    assert final.result_commit.result_content_checksum == outcome.result_content_checksum


# ---------------------------------------------------------------------------
# MEGB-03H.2C.3B.2B.2 correction: committed-result/budget/ack recovery --
# actual_cost_cents is carried on the durable ResultCommit itself, budget
# finalization is retried idempotently on redelivery, and queue
# acknowledgement happens only once finalize has been (re)attempted.
# ---------------------------------------------------------------------------


def test_actual_cost_cents_is_carried_on_the_durable_commit() -> None:
    """The committed result's own ResultCommit carries the exact
    actual_cost_cents that was (or will be) finalized -- recoverable from
    authoritative, checksum-bound state alone, never a separate lookup."""
    env = build_environment()
    content = make_synthetic_content("q")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=250)
    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None and outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED

    record = env.work_store.read("work-1")
    assert record.result_commit is not None
    assert record.result_commit.actual_cost_cents == 250
    reservation = env.budget_store.get("res-1")
    assert reservation.actual_cost_cents == 250


def test_budget_finalization_succeeds_but_ack_never_happens_then_redelivery_recovers() -> None:
    """Simulates a crash exactly between budget finalization succeeding
    and queue acknowledgement completing: redelivery recovers the
    existing committed result without invoking the executor again, and
    retrying finalize on an already-FINALIZED reservation is a harmless,
    idempotent no-op -- never a double-finalization error."""
    env = build_environment()
    content = make_synthetic_content("r")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    message = env.queue.receive()
    assert message is not None
    record = env.work_store.read("work-1")
    record = env.work_store.acquire_lease(
        "work-1", record.revision, _make_lease("worker-a"), reservation_validator=lambda _rid: True
    )
    record = env.work_store.transition_to_executing("work-1", record.revision)

    attempt = make_execution_attempt(
        scientific_work_id="work-1",
        worker_participant_id="worker-a",
        lease_generation=1,
        distributed_run_context_checksum=RUN_CTX,
    )
    result_content = b"synthetic-manually-committed-result"
    commit = make_result_commit(attempt, result_content, actual_cost_cents=100)
    env.artifact_store.put(commit.result_artifact_reference, result_content, _DEFAULT_METADATA)
    env.work_store.commit_result(
        "work-1", record.revision, attempt, commit, artifact_resolver=env.artifact_store.resolve
    )
    # Budget finalization succeeds here (simulating it completed before
    # the crash)...
    env.budget_store.finalize("res-1", 100)
    # ...but queue.ack("work-1") deliberately NOT called -- the crash
    # window this test targets.

    env.clock.advance(10)  # elapse visibility timeout -> redelivery
    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.RECOVERED_COMMITTED_RESULT
    assert executor.invocation_count == 0  # never invoked -- no re-execution

    reservation = env.budget_store.get("res-1")
    assert reservation.status == ReservationStatus.FINALIZED
    assert reservation.actual_cost_cents == 100  # unchanged -- no double-charge


def test_audit_sink_failure_during_dispatch_never_causes_re_execution() -> None:
    """A failing audit sink at dispatch time leaves the result-committed
    audit entry pending for retry, without altering authoritative state
    or ever re-invoking the executor -- dispatch_pending never mutates
    work_store."""
    env = build_environment()
    content = make_synthetic_content("s")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    failing_sink = InMemoryAuditSink(fail_after=0)
    executor = ScriptedExecutor()
    coordinator = Coordinator(
        config=env.config,
        clock=env.clock,
        work_store=env.work_store,
        artifact_reader=env.artifact_store,
        artifact_writer=env.artifact_store,
        budget_store=env.budget_store,
        policy=env.policy,
        worker_registry=env.worker_registry,
        queue=env.queue,
        audit_sink=failing_sink,
        audit_outbox=env.audit_outbox,
        cancellation=env.cancellation,
        executor=executor,
    )
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    assert executor.invocation_count == 1

    summary = coordinator.dispatch_audit()
    committed_record = env.work_store.read("work-1")
    assert committed_record.result_commit is not None
    expected_key = f"result-committed:work-1:{committed_record.result_commit.attempt_checksum}"
    assert expected_key in summary.sink_failed_keys
    assert executor.invocation_count == 1  # unchanged
    assert env.work_store.read("work-1").state == WorkItemState.RESULT_COMMITTED
    assert not failing_sink.events()
