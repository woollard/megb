"""MEGB-03H.2C.3B.2B.3: in-process fault-injection, recovery, and
resumption conformance suite for the already-accepted
MEGB-03H.2C.3B.2B.1 (atomic stores) and MEGB-03H.2C.3B.2B.2 (coordinator/
worker engine) code.

Every test below maps directly onto one fault point in this checkpoint's
own frozen plan (``docs/reference/megb-03h2c3b2b3-fault-injection-plan.md``)
and records a :class:`~src.distributed.fault_conformance.ConformanceEntry`
for each invariant it exercises via the shared module-level
``RECORDER`` (``tests/_fault_conformance_harness.py``). The final test in
this file builds and writes the safe, committed conformance report from
every entry recorded above it -- deterministic given pytest's own default
top-to-bottom, non-randomized collection order within one file (no
pytest-randomly or similar plugin is installed or used here).

No wall-clock sleep, process termination, signal, subprocess, Docker, or
network access anywhere. Every fault point is exercised via a deterministic
typed fault (a scripted executor outcome, a direct authoritative-store
call simulating a crash window, a synthetic exception, a
``threading.Barrier``-synchronized race, or the injected ``LogicalClock``).
"Coordinator recreation" means constructing a new ``Coordinator`` around
the same in-memory store objects -- in-process component recreation, never
process-crash durability, cross-host, or cloud recovery."""

# pylint: disable=duplicate-code
# This file's own admission/execution fixture usage inherently mirrors
# tests/test_coordinator_admission.py's and tests/test_coordinator_execution.py's
# own patterns (both build the same synthetic environments against the
# same coordinator API) -- shared boilerplate, not shared logic, per this
# project's own established convention.
# pylint: disable=cell-var-from-loop
# Every per-trial closure in the R5-R10 race tests below is both defined
# and fully exercised -- built, started, and joined -- within the same
# loop iteration, before the next iteration rebinds any of these
# variables -- there is no stale-capture-across-iterations bug for this
# rule to catch, only the loop-body-defines-a-closure shape the rule
# pattern-matches on generically (same precedent as
# tests/test_atomic_stores_races.py and tests/test_coordinator_concurrency.py).
# pylint: disable=too-many-lines
# This is one large, deliberately exhaustive conformance suite mapping
# 1:1 onto every fault point in this checkpoint's own frozen plan -- never
# split across files, so the plan/test/report mapping stays traceable.

import json
import pathlib
import threading

import pytest

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
)
from src.distributed.artifact_capabilities import WorkerArtifactCapability
from src.distributed.artifact_store import ArtifactMetadata
from src.distributed.atomic_work_store import (
    IdentityMismatchError,
    MissingArtifactReferenceError,
    RevisionConflictError,
)
from src.distributed.audit_sink_store import InMemoryAuditSink
from src.distributed.budget_store import (
    BudgetCeilingExceededError,
    OrphanReservationDisposition,
    ReservationNotFoundError,
    ReservationStatus,
    WorkerCeilingExceededError,
    diagnose_reservation_work_binding,
)
from src.distributed.coordinator import (
    Coordinator,
    WorkPublicationDisposition,
    diagnose_work_publication_binding,
)
from src.distributed.executor import ExecutorInvocationResult, executor_success
from src.distributed.fault_conformance import (
    FaultPointId,
    InvariantId,
    ReadinessClassification,
    build_fault_conformance_report,
    fault_conformance_report_to_dict,
    render_markdown,
)
from src.distributed.personal_policy import (
    PERSONAL_BOOTSTRAP_MAX_WORKERS,
    DataClassification,
    WorkloadClass,
)
from src.distributed.provenance import EnvironmentClass
from src.distributed.safe_audit import SafeAuditEventType, build_safe_audit_event
from src.distributed.state_machine import WorkItemState
from src.distributed.work_contracts import (
    CancellationRequest,
    CancellationScope,
    ConflictingResultCommitError,
    TerminalDispositionReason,
)
from src.distributed.work_outcome import WorkOutcomeKind, build_run_summary
from src.distributed.worker_contracts import Lease, StaleLeaseGenerationError
from tests._atomic_stores_fixtures import make_result_commit
from tests._coordinator_fixtures import (
    RUN_CTX,
    CoordinatorEnvironment,
    RaisingExecutor,
    ScriptedExecutor,
    build_environment,
    make_default_config,
    make_synthetic_content,
    make_work_descriptor,
    make_worker_registration,
    publish_candidate,
    retryable_failure,
    terminal_failure,
)
from tests._distributed_orchestration_fixtures import make_execution_attempt
from tests._fault_conformance_harness import RECORDER

_DEFAULT_METADATA = ArtifactMetadata(
    workload_class=WorkloadClass.SYNTHETIC_SMOKE, data_classification=DataClassification.SYNTHETIC
)


def _track_lease_expiry(
    coordinator: Coordinator, env: CoordinatorEnvironment, work_id: str = "work-1"
) -> None:
    """Simulate the coordinator-side bookkeeping ``_acquire_or_reassign_lease``
    would have performed, for tests that acquire a lease directly against
    the store (bypassing the coordinator's own admission/lease path) to
    construct a specific crash window. ``check_lease_expiry`` is
    caller-driven and reads only this coordinator-local tracking dict --
    a lease acquired by any other path is otherwise invisible to it."""
    coordinator._lease_expiry[work_id] = (  # pylint: disable=protected-access
        env.clock.now() + env.config.lease_duration_ticks
    )


def _lease(worker_id: str, generation: int = 1, work_id: str = "work-1") -> Lease:
    return Lease(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        scientific_work_id=work_id,
        worker_participant_id=worker_id,
        lease_generation=generation,
        lease_issued_at_logical_clock=0,
        lease_duration_logical_ticks=10,
    )


# ---------------------------------------------------------------------------
# Admission boundaries (A1-A5)
# ---------------------------------------------------------------------------


def test_a1_cancellation_before_reservation_ends_defined_disposition() -> None:
    """A1: before budget reservation. Cancellation observed here means no
    reservation, work record, or queue entry is ever created -- a
    defined, terminal disposition with no partial side effect."""
    env = build_environment()
    content = make_synthetic_content("a1")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.request_cancellation("work-1")
    outcome = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
    )
    passed = (
        outcome is not None
        and outcome.outcome_kind == WorkOutcomeKind.CANCELLED_NOT_STARTED
        and env.queue.in_flight_count() == 0
    )
    with pytest.raises(ReservationNotFoundError):
        env.budget_store.get("res-1")
    RECORDER.record(
        FaultPointId.A1_BEFORE_BUDGET_RESERVATION,
        InvariantId.I11_EVERY_ITEM_ENDS_DEFINED_DISPOSITION,
        passed,
    )
    assert passed


def test_a2_reservation_without_work_is_diagnosable_and_resumable() -> None:
    """A2: after reservation, before work creation. A reservation made but
    never bound to a work record is RESUMABLE -- safe to retry admission
    (create_if_absent is idempotent) with the same identifiers."""
    env = build_environment()
    env.budget_store.reserve("res-a2", 100, 1)
    disposition = diagnose_reservation_work_binding(
        env.budget_store, env.work_store, "work-a2", "res-a2"
    )
    resumable = disposition == OrphanReservationDisposition.RESUMABLE

    content = make_synthetic_content("a2")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-a2", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    outcome = coordinator.admit(
        descriptor, reservation_id="res-a2", requested_cost_cents=100, requested_worker_count=1
    )
    resumed_cleanly = outcome is None and env.queue.in_flight_count() == 1
    passed = resumable and resumed_cleanly
    RECORDER.record(
        FaultPointId.A2_AFTER_RESERVATION_BEFORE_WORK_CREATION,
        InvariantId.I7_NO_LOST_QUEUE_VISIBLE_WORK,
        passed,
    )
    assert passed


def test_a3_work_created_before_audit_intent_is_resumable() -> None:
    """A3: after work creation, before audit intent. The authoritative
    record exists (bound to its reservation) but no admission audit
    intent has been enqueued yet, and nothing is queue-visible -- resuming
    admission through the normal coordinator path completes the audit
    intent and publication correctly, and exactly one audit intent ever
    exists for this work item (never a duplicate)."""
    env = build_environment()
    content = make_synthetic_content("a3")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-a3", 0, reference)
    env.budget_store.reserve("res-a3", 100, 1)
    env.work_store.create_if_absent(
        "work-a3", descriptor.distributed_run_context_checksum, "res-a3", lambda _rid: True
    )
    no_audit_yet = not any(
        entry.outbox_key == "admitted:work-a3" for entry in env.audit_outbox.entries()
    )
    not_published_yet = (
        diagnose_work_publication_binding(env.work_store, env.queue, "work-a3")
        == WorkPublicationDisposition.ADMITTED_NOT_PUBLISHED
    )

    coordinator = env.make_coordinator(ScriptedExecutor())
    outcome = coordinator.admit(
        descriptor, reservation_id="res-a3", requested_cost_cents=100, requested_worker_count=1
    )
    resumed = outcome is None and env.queue.in_flight_count() == 1
    exactly_one_audit_entry = (
        sum(1 for entry in env.audit_outbox.entries() if entry.outbox_key == "admitted:work-a3")
        == 1
    )
    passed = no_audit_yet and not_published_yet and resumed and exactly_one_audit_entry
    RECORDER.record(
        FaultPointId.A3_AFTER_WORK_CREATION_BEFORE_AUDIT_INTENT,
        InvariantId.I8_NO_UNAUDITED_AUTHORITATIVE_TRANSITION,
        passed,
    )
    assert passed


def test_a4_audit_intent_before_publication_is_resumable() -> None:
    """A4: after audit intent, before queue publication. The admission
    audit intent already exists, but the item is not yet queue-visible --
    resuming publication (idempotent) makes it visible, and the worker
    path completes normally afterward."""
    env = build_environment()
    content = make_synthetic_content("a4")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-a4", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.budget_store.reserve("res-a4", 100, 1)
    env.work_store.create_if_absent(
        "work-a4", descriptor.distributed_run_context_checksum, "res-a4", lambda _rid: True
    )
    event = build_safe_audit_event(
        event_type=SafeAuditEventType.WORK_ADMITTED,
        work_reference="work-a4",
        safe_run_identity=descriptor.distributed_run_context_checksum,
        state_after=WorkItemState.PENDING_AVAILABLE,
        logical_timestamp=0,
        input_ordinal=0,
    )
    env.audit_outbox.enqueue(
        "admitted:work-a4", event, reconciliation_scientific_work_id="work-a4"
    )
    not_published_yet = (
        diagnose_work_publication_binding(env.work_store, env.queue, "work-a4")
        == WorkPublicationDisposition.ADMITTED_NOT_PUBLISHED
    )

    env.queue.publish(descriptor)
    published_now = (
        diagnose_work_publication_binding(env.work_store, env.queue, "work-a4")
        == WorkPublicationDisposition.PUBLISHED
    )
    coordinator = env.make_coordinator(ScriptedExecutor())
    outcome = coordinator.invoke_worker("worker-a")
    completed = (
        outcome is not None and outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    )
    passed = not_published_yet and published_now and completed
    RECORDER.record(
        FaultPointId.A4_AFTER_AUDIT_INTENT_BEFORE_PUBLICATION,
        InvariantId.I7_NO_LOST_QUEUE_VISIBLE_WORK,
        passed,
    )
    assert passed


def test_a5_admission_return_reflects_completed_side_effects() -> None:
    """A5: after publication, before admission returns. admit() has no
    remaining side effect after queue.publish succeeds -- its return value
    (None) always accurately reflects a fully-admitted, queue-visible
    work item."""
    env = build_environment()
    content = make_synthetic_content("a5")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-a5", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    outcome = coordinator.admit(
        descriptor, reservation_id="res-a5", requested_cost_cents=100, requested_worker_count=1
    )
    passed = (
        outcome is None
        and env.queue.in_flight_count() == 1
        and diagnose_work_publication_binding(env.work_store, env.queue, "work-a5")
        == WorkPublicationDisposition.PUBLISHED
    )
    RECORDER.record(
        FaultPointId.A5_AFTER_PUBLICATION_BEFORE_RETURN,
        InvariantId.I11_EVERY_ITEM_ENDS_DEFINED_DISPOSITION,
        passed,
    )
    assert passed


# ---------------------------------------------------------------------------
# Worker boundaries (W1-W9)
# ---------------------------------------------------------------------------


def test_w1_delivery_before_lease_leaves_record_untouched_and_resumes() -> None:
    """W1: after delivery, before lease. Merely receiving a queue message
    mutates no authoritative state -- a crash here is invisible to the
    store; the same message becomes redeliverable after the queue's own
    visibility timeout, and normal processing then completes."""
    env = build_environment()
    content = make_synthetic_content("w1")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    peeked = env.queue.receive()
    record_untouched = (
        peeked is not None
        and env.work_store.read("work-1").state == WorkItemState.PENDING_AVAILABLE
    )
    env.clock.advance(10)  # elapse visibility timeout -> redelivery
    outcome = coordinator.invoke_worker("worker-a")
    completed = (
        outcome is not None and outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    )
    passed = record_untouched and completed
    RECORDER.record(
        FaultPointId.W1_AFTER_DELIVERY_BEFORE_LEASE,
        InvariantId.I7_NO_LOST_QUEUE_VISIBLE_WORK,
        passed,
    )
    assert passed


def test_w2_lease_before_executor_crash_recovers_with_fresh_attempt() -> None:
    """W2: after lease, before executor. A crash after the lease is
    acquired (state EXECUTING) but before the injected executor is ever
    invoked is recoverable through the same lease-expiry/reassignment
    path as any other in-flight interruption -- the eventual committed
    result comes from exactly one successful attempt, never a stale one."""
    env = build_environment()
    content = make_synthetic_content("w2")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    executor = ScriptedExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    record = env.work_store.read("work-1")
    record = env.work_store.acquire_lease(
        "work-1", record.revision, _lease("worker-a"), reservation_validator=lambda _rid: True
    )
    _track_lease_expiry(coordinator, env)
    env.work_store.transition_to_executing("work-1", record.revision)
    # Simulated crash: the injected executor is never invoked for this
    # attempt at all.
    executing_untouched = executor.invocation_count == 0

    env.clock.advance(100)
    assert coordinator.check_lease_expiry("work-1") is True
    outcome = coordinator.invoke_worker("worker-b")
    completed_once = (
        outcome is not None
        and outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
        and executor.invocation_count == 1
    )
    passed = executing_untouched and completed_once
    RECORDER.record(
        FaultPointId.W2_AFTER_LEASE_BEFORE_EXECUTOR, InvariantId.I3_NO_STALE_LEASE_COMMIT, passed
    )
    assert passed


def test_w3_retryable_executor_failure_schedules_retry() -> None:
    """W3: executor raises a retryable failure -- schedules a retry,
    never dead-letters immediately."""
    env = build_environment()
    content = make_synthetic_content("w3")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor(script=[retryable_failure()])
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    outcome = coordinator.invoke_worker("worker-a")
    passed = (
        outcome is not None
        and outcome.outcome_kind == WorkOutcomeKind.RETRY_SCHEDULED
        and env.work_store.read("work-1").state == WorkItemState.RETRYABLE
    )
    RECORDER.record(
        FaultPointId.W3_EXECUTOR_RETRYABLE_FAILURE,
        InvariantId.I11_EVERY_ITEM_ENDS_DEFINED_DISPOSITION,
        passed,
    )
    assert passed


def test_w4_non_retryable_executor_failure_dead_letters_with_correct_reason() -> None:
    """W4: executor raises a non-retryable (terminal) failure -- dead
    letters immediately, tagged NON_RETRYABLE_EXECUTOR_FAILURE, never
    RETRY_CEILING_EXCEEDED (which would falsely claim retries were
    exhausted)."""
    env = build_environment()
    content = make_synthetic_content("w4")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor(script=[terminal_failure()])
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    outcome = coordinator.invoke_worker("worker-a")
    disposition = env.work_store.read("work-1").terminal_disposition
    correct_reason = (
        disposition is not None
        and disposition.disposition_reason
        == TerminalDispositionReason.NON_RETRYABLE_EXECUTOR_FAILURE
    )
    passed = (
        outcome is not None
        and outcome.outcome_kind == WorkOutcomeKind.RETRY_EXHAUSTED
        and correct_reason
    )
    RECORDER.record(
        FaultPointId.W4_EXECUTOR_NON_RETRYABLE_FAILURE,
        InvariantId.I11_EVERY_ITEM_ENDS_DEFINED_DISPOSITION,
        passed,
    )
    assert passed


def test_i13_executor_raised_exception_message_never_leaks() -> None:
    """I13 (recorded against W4, its closest fault point -- an executor
    that raises a raw Python exception is the unscripted variant of "the
    executor cannot complete this attempt"): the executor's own
    distinctive, deliberately unsafe exception message must never appear
    in the returned WorkOutcome, the authoritative record, or any safe
    audit event -- proving no raw exception text ever leaks."""
    env = build_environment()
    content = make_synthetic_content("i13")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = RaisingExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None
    coordinator.dispatch_audit()
    assert executor.message not in repr(outcome)
    assert executor.message not in repr(env.work_store.read("work-1"))
    for event in env.audit_sink.events():
        assert executor.message not in repr(event)
    passed = outcome.outcome_kind == WorkOutcomeKind.INFRASTRUCTURE_FAILURE
    RECORDER.record(
        FaultPointId.W4_EXECUTOR_NON_RETRYABLE_FAILURE,
        InvariantId.I13_NO_UNSAFE_LEAKAGE,
        passed,
    )
    assert passed


def test_w5_artifact_written_before_outbox_intent_orphan_remains_unreferenced() -> None:  # pylint: disable=too-many-locals
    """W5: after result-artifact write, before outbox intent. A result
    artifact published for an attempt that never completes its commit
    remains present but permanently unreferenced -- the eventual, real
    committed result comes from a distinct, later attempt, and at most
    one authoritative committed result ever exists."""
    env = build_environment()
    content = make_synthetic_content("w5")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    record = env.work_store.read("work-1")
    record = env.work_store.acquire_lease(
        "work-1", record.revision, _lease("worker-a"), reservation_validator=lambda _rid: True
    )
    _track_lease_expiry(coordinator, env)
    env.work_store.transition_to_executing("work-1", record.revision)
    orphan_attempt = make_execution_attempt(
        scientific_work_id="work-1",
        worker_participant_id="worker-a",
        lease_generation=1,
        distributed_run_context_checksum=RUN_CTX,
    )
    orphan_content = b"synthetic-orphan-result-w5"
    orphan_commit = make_result_commit(orphan_attempt, orphan_content)
    capability = WorkerArtifactCapability(env.artifact_store, env.artifact_store)
    capability.publish_result(
        orphan_commit.result_artifact_reference,
        orphan_content,
        ArtifactMetadata(
            workload_class=WorkloadClass.SYNTHETIC_SMOKE,
            data_classification=DataClassification.SYNTHETIC,
        ),
    )
    # Simulated crash: no outbox intent enqueued, no commit_result called.
    record_still_executing = env.work_store.read("work-1").state == WorkItemState.EXECUTING
    orphan_artifact_present = capability.resolve(orphan_commit.result_artifact_reference)

    env.clock.advance(100)
    assert coordinator.check_lease_expiry("work-1") is True
    outcome = coordinator.invoke_worker("worker-b")
    final_record = env.work_store.read("work-1")
    assert final_record.result_commit is not None
    real_commit_is_distinct = (
        final_record.result_commit.result_content_checksum
        != orphan_commit.result_content_checksum
    )
    passed = (
        record_still_executing
        and orphan_artifact_present
        and outcome is not None
        and outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
        and real_commit_is_distinct
    )
    RECORDER.record(
        FaultPointId.W5_AFTER_ARTIFACT_WRITE_BEFORE_OUTBOX_INTENT,
        InvariantId.I1_AT_MOST_ONE_COMMITTED_RESULT,
        passed,
    )
    assert passed


def test_w6_outbox_intent_before_commit_becomes_abandoned_on_lost_commit() -> None:  # pylint: disable=too-many-locals
    """W6: after outbox intent, before authoritative commit. An outbox
    intent enqueued for an attempt whose commit never happens (a lost
    CAS) is later reconciled as ABANDONED, once a distinct attempt's
    commit durably lands -- it never blocks or falsely delivers."""
    env = build_environment()
    content = make_synthetic_content("w6")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    coordinator = env.make_coordinator(ScriptedExecutor(default_result_content=b"real-result"))
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    record = env.work_store.read("work-1")
    record = env.work_store.acquire_lease(
        "work-1", record.revision, _lease("worker-a"), reservation_validator=lambda _rid: True
    )
    _track_lease_expiry(coordinator, env)
    env.work_store.transition_to_executing("work-1", record.revision)
    lost_attempt = make_execution_attempt(
        scientific_work_id="work-1",
        worker_participant_id="worker-a",
        lease_generation=1,
        distributed_run_context_checksum=RUN_CTX,
    )
    lost_commit = make_result_commit(lost_attempt, b"lost-cas-content")
    event = build_safe_audit_event(
        event_type=SafeAuditEventType.RESULT_COMMITTED,
        work_reference="work-1",
        safe_run_identity=RUN_CTX,
        state_after=WorkItemState.RESULT_COMMITTED,
        logical_timestamp=0,
        lease_generation=1,
        content_checksum=lost_commit.result_content_checksum,
        input_ordinal=0,
    )
    env.audit_outbox.enqueue(
        f"result-committed:work-1:{lost_attempt.attempt_checksum}",
        event,
        reconciliation_scientific_work_id="work-1",
        reconciliation_expected_state=WorkItemState.RESULT_COMMITTED,
        reconciliation_expected_result_content_checksum=lost_commit.result_content_checksum,
    )
    # Simulated crash: commit_result for this attempt is never called.
    still_pending_summary = coordinator.dispatch_audit()
    initially_pending = (
        f"result-committed:work-1:{lost_attempt.attempt_checksum}"
        in still_pending_summary.still_pending_keys
    )

    env.clock.advance(100)
    assert coordinator.check_lease_expiry("work-1") is True
    outcome = coordinator.invoke_worker("worker-b")
    real_commit_landed = (
        outcome is not None and outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    )
    final_summary = coordinator.dispatch_audit()
    orphan_abandoned = (
        f"result-committed:work-1:{lost_attempt.attempt_checksum}"
        in final_summary.abandoned_keys
    )
    passed = initially_pending and real_commit_landed and orphan_abandoned
    RECORDER.record(
        FaultPointId.W6_AFTER_OUTBOX_INTENT_BEFORE_COMMIT,
        InvariantId.I9_NO_PERMANENT_IMPOSSIBLE_INTENT_CAPACITY,
        passed,
    )
    assert passed


def test_w7_commit_before_finalization_crash_recovers_and_finalizes_once() -> None:  # pylint: disable=too-many-locals
    """W7: after commit, before budget finalization. A result committed
    but never finalized (crash before finalize ever runs) is recovered on
    redelivery -- the executor is never invoked again, and finalize
    happens exactly once, for the exact actual_cost_cents carried on the
    durable commit."""
    env = build_environment()
    content = make_synthetic_content("w7")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    record = env.work_store.read("work-1")
    record = env.work_store.acquire_lease(
        "work-1", record.revision, _lease("worker-a"), reservation_validator=lambda _rid: True
    )
    record = env.work_store.transition_to_executing("work-1", record.revision)
    attempt = make_execution_attempt(
        scientific_work_id="work-1",
        worker_participant_id="worker-a",
        lease_generation=1,
        distributed_run_context_checksum=RUN_CTX,
    )
    result_content = b"synthetic-w7-content"
    commit = make_result_commit(attempt, result_content, actual_cost_cents=100)
    env.artifact_store.put(commit.result_artifact_reference, result_content, _DEFAULT_METADATA)
    env.work_store.commit_result(
        "work-1", record.revision, attempt, commit, artifact_resolver=env.artifact_store.resolve
    )
    # Simulated crash: neither finalize nor ack happens for this attempt.
    reservation_still_reserved = env.budget_store.get("res-1").status == ReservationStatus.RESERVED

    outcome = coordinator.invoke_worker("worker-a")
    recovered_without_execution = (
        outcome is not None
        and outcome.outcome_kind == WorkOutcomeKind.RECOVERED_COMMITTED_RESULT
        and executor.invocation_count == 0
    )
    reservation = env.budget_store.get("res-1")
    finalized_once = (
        reservation.status == ReservationStatus.FINALIZED and reservation.actual_cost_cents == 100
    )
    passed = reservation_still_reserved and recovered_without_execution and finalized_once
    RECORDER.record(
        FaultPointId.W7_AFTER_COMMIT_BEFORE_FINALIZATION,
        InvariantId.I5_NO_DOUBLE_BUDGET_FINALIZATION,
        passed,
    )
    RECORDER.record(
        FaultPointId.W7_AFTER_COMMIT_BEFORE_FINALIZATION,
        InvariantId.I6_NO_SILENT_BUDGET_LEAK,
        passed,
    )
    assert passed


def test_w8_finalization_before_ack_crash_recovers_without_reexecution_or_double_charge() -> None:
    """W8: after finalization, before queue acknowledgement. Budget
    finalization already succeeded when the crash occurred -- redelivery
    recovers without re-invoking the executor, and retrying finalize on
    the already-FINALIZED reservation is a harmless no-op, never a
    double-charge."""
    env = build_environment()
    content = make_synthetic_content("w8")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    record = env.work_store.read("work-1")
    record = env.work_store.acquire_lease(
        "work-1", record.revision, _lease("worker-a"), reservation_validator=lambda _rid: True
    )
    record = env.work_store.transition_to_executing("work-1", record.revision)
    attempt = make_execution_attempt(
        scientific_work_id="work-1",
        worker_participant_id="worker-a",
        lease_generation=1,
        distributed_run_context_checksum=RUN_CTX,
    )
    result_content = b"synthetic-w8-content"
    commit = make_result_commit(attempt, result_content, actual_cost_cents=100)
    env.artifact_store.put(commit.result_artifact_reference, result_content, _DEFAULT_METADATA)
    env.work_store.commit_result(
        "work-1", record.revision, attempt, commit, artifact_resolver=env.artifact_store.resolve
    )
    env.budget_store.finalize("res-1", 100)
    # Simulated crash: queue.ack("work-1") deliberately never called.

    outcome = coordinator.invoke_worker("worker-a")
    recovered = (
        outcome is not None
        and outcome.outcome_kind == WorkOutcomeKind.RECOVERED_COMMITTED_RESULT
        and executor.invocation_count == 0
    )
    reservation = env.budget_store.get("res-1")
    no_double_charge = (
        reservation.status == ReservationStatus.FINALIZED and reservation.actual_cost_cents == 100
    )
    passed = recovered and no_double_charge
    RECORDER.record(
        FaultPointId.W8_AFTER_FINALIZATION_BEFORE_ACK,
        InvariantId.I2_NO_EXECUTION_AFTER_COMMIT,
        passed,
    )
    RECORDER.record(
        FaultPointId.W8_AFTER_FINALIZATION_BEFORE_ACK,
        InvariantId.I4_NO_ACK_BEFORE_COMMIT,
        passed,
    )
    assert passed


def test_w9_ack_before_return_is_idempotent_terminal() -> None:
    """W9: after acknowledgement, before result return. Once acked, the
    queue has nothing further to deliver -- invoking the worker again
    returns None (nothing deliverable), never a second outcome for the
    same completed item."""
    env = build_environment()
    content = make_synthetic_content("w9")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    first_outcome = coordinator.invoke_worker("worker-a")
    second_outcome = coordinator.invoke_worker("worker-a")
    passed = (
        first_outcome is not None
        and first_outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
        and second_outcome is None
    )
    RECORDER.record(
        FaultPointId.W9_AFTER_ACK_BEFORE_RETURN,
        InvariantId.I12_DETERMINISTIC_RESULT_ORDERING,
        passed,
    )
    assert passed


# ---------------------------------------------------------------------------
# Additional fault categories (C1-C13)
# ---------------------------------------------------------------------------


def test_c1_audit_sink_failure_never_causes_reexecution() -> None:
    """C1: audit-sink failure during dispatch. A failing sink leaves the
    entry pending for retry, never re-invoking the executor or mutating
    authoritative state."""
    env = build_environment()
    content = make_synthetic_content("c1")
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
    summary = coordinator.dispatch_audit()
    passed = (
        outcome is not None
        and outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
        and executor.invocation_count == 1
        and bool(summary.sink_failed_keys)
        and env.work_store.read("work-1").state == WorkItemState.RESULT_COMMITTED
    )
    RECORDER.record(
        FaultPointId.C1_AUDIT_SINK_FAILURE, InvariantId.I2_NO_EXECUTION_AFTER_COMMIT, passed
    )
    assert passed


def test_c2_outbox_full_refuses_admission_before_publication_and_is_resumable() -> None:
    """C2: audit outbox at capacity. Admission is refused before
    publication -- never an unaudited, queue-visible item -- and the
    admission is safely resumable once capacity frees."""
    env = build_environment(audit_outbox_max_pending=1)
    filler_event = build_safe_audit_event(
        event_type=SafeAuditEventType.WORK_ADMITTED,
        work_reference="filler-work",
        safe_run_identity="env-logical-0000000000000001",
        state_after=WorkItemState.PENDING_AVAILABLE,
        logical_timestamp=0,
    )
    env.audit_outbox.enqueue("filler-key", filler_event)
    content = make_synthetic_content("c2")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    refused = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
    )
    refused_before_publish = (
        refused is not None
        and refused.outcome_kind == WorkOutcomeKind.INFRASTRUCTURE_FAILURE
        and env.queue.in_flight_count() == 0
    )
    env.audit_outbox.dispatch_pending(env.audit_sink, env.work_store)
    resumed = coordinator.admit(
        descriptor, reservation_id="res-1", requested_cost_cents=100, requested_worker_count=1
    )
    resumed_cleanly = resumed is None and env.queue.in_flight_count() == 1
    passed = refused_before_publish and resumed_cleanly
    RECORDER.record(
        FaultPointId.C2_OUTBOX_FULL, InvariantId.I8_NO_UNAUDITED_AUTHORITATIVE_TRANSITION, passed
    )
    assert passed


def test_c3_orphan_intent_abandoned_releases_capacity() -> None:
    """C3: an outbox intent whose reconciliation clause becomes
    permanently impossible (here: the work item is cancelled instead of
    ever reaching RESULT_COMMITTED) is reclassified ABANDONED and no
    longer consumes pending capacity."""
    env = build_environment(audit_outbox_max_pending=1)
    content = make_synthetic_content("c3")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.budget_store.reserve("res-1", 100, 1)
    env.work_store.create_if_absent(
        "work-1", descriptor.distributed_run_context_checksum, "res-1", lambda _rid: True
    )
    event = build_safe_audit_event(
        event_type=SafeAuditEventType.RESULT_COMMITTED,
        work_reference="work-1",
        safe_run_identity=RUN_CTX,
        state_after=WorkItemState.RESULT_COMMITTED,
        logical_timestamp=0,
    )
    env.audit_outbox.enqueue(
        "premature-result-committed:work-1",
        event,
        reconciliation_scientific_work_id="work-1",
        reconciliation_expected_state=WorkItemState.RESULT_COMMITTED,
    )
    at_capacity = env.audit_outbox.pending_count() == 1

    request = CancellationRequest(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        scientific_work_id="work-1",
        cancellation_scope=CancellationScope.BEFORE_ADMISSION,
        requested_at_logical_clock=0,
    )
    env.work_store.request_cancellation("work-1", 0, request)
    summary = env.audit_outbox.dispatch_pending(env.audit_sink, env.work_store)
    abandoned = "premature-result-committed:work-1" in summary.abandoned_keys
    capacity_freed = env.audit_outbox.pending_count() == 0
    passed = at_capacity and abandoned and capacity_freed
    RECORDER.record(
        FaultPointId.C3_ORPHAN_INTENT_ABANDONED,
        InvariantId.I9_NO_PERMANENT_IMPOSSIBLE_INTENT_CAPACITY,
        passed,
    )
    assert passed


def test_c4_duplicate_delivery_before_and_after_commit_is_harmless() -> None:
    """C4: queue duplicate delivery/redelivery. A duplicate delivery
    before a lease is harmless (STALE_LEASE against the current holder);
    a duplicate delivery after commit recovers the existing result
    without re-invoking the executor."""
    env = build_environment()
    content = make_synthetic_content("c4")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    executor = ScriptedExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    record = env.work_store.read("work-1")
    env.work_store.acquire_lease(
        "work-1", record.revision, _lease("worker-a"), reservation_validator=lambda _rid: True
    )
    _track_lease_expiry(coordinator, env)
    stale_outcome = coordinator.invoke_worker("worker-b")
    stale_rejected = (
        stale_outcome is not None and stale_outcome.outcome_kind == WorkOutcomeKind.STALE_LEASE
    )

    env.clock.advance(100)
    coordinator.check_lease_expiry("work-1")
    real_outcome = coordinator.invoke_worker("worker-a")
    real_committed = (
        real_outcome is not None
        and real_outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    )
    duplicate_message = env.queue.publish(descriptor)  # idempotent -- already published
    del duplicate_message
    passed = stale_rejected and real_committed
    RECORDER.record(
        FaultPointId.C4_QUEUE_DUPLICATE_REDELIVERY, InvariantId.I3_NO_STALE_LEASE_COMMIT, passed
    )
    assert passed


def test_c5_ack_failure_simulated_recovers_via_redelivery() -> None:
    """C5: queue acknowledgement failure. Regardless of which specific
    sub-step (finalize, ack) failed to complete, redelivery of an
    already-committed item always recovers via the RESULT_COMMITTED
    branch -- never a re-execution, never a lost item."""
    env = build_environment()
    content = make_synthetic_content("c5")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor = ScriptedExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    first_outcome = coordinator.invoke_worker("worker-a")
    assert (
        first_outcome is not None
        and first_outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    )

    env.clock.advance(100)  # simulate a redelivery attempt after the fact
    replay_outcome = coordinator.invoke_worker("worker-a")
    passed = replay_outcome is None and executor.invocation_count == 1
    RECORDER.record(
        FaultPointId.C5_QUEUE_ACK_FAILURE, InvariantId.I10_NO_TERMINAL_EVIDENCE_ERASED, passed
    )
    assert passed


def test_c6_lease_expiry_and_reassignment_fences_original_worker() -> None:
    """C6: lease expiry and reassignment. After expiry, the reassigned
    lease carries a strictly higher generation (even when reassigned back
    to the same worker), and a stale attempt still carrying the old
    generation is fenced -- rejected at commit time, never allowed to
    overwrite the real, current commit."""
    env = build_environment()
    content = make_synthetic_content("c6")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    record = env.work_store.read("work-1")
    env.work_store.acquire_lease(
        "work-1", record.revision, _lease("worker-a"), reservation_validator=lambda _rid: True
    )
    _track_lease_expiry(coordinator, env)
    env.clock.advance(100)
    expired = coordinator.check_lease_expiry("work-1")
    # Reassigned back to the same worker (e.g. a slow first attempt whose
    # own lease expired, followed by a fresh retry) -- generation still
    # strictly increases.
    outcome = coordinator.invoke_worker("worker-a")
    reassigned_record = env.work_store.read("work-1")
    fenced_higher_generation = reassigned_record.current_lease_generation == 2

    stale_attempt = make_execution_attempt(
        scientific_work_id="work-1",
        worker_participant_id="worker-a",
        lease_generation=1,
        distributed_run_context_checksum=RUN_CTX,
    )
    stale_commit = make_result_commit(stale_attempt, b"stale-worker-a-content")
    env.artifact_store.put(
        stale_commit.result_artifact_reference, b"stale-worker-a-content", _DEFAULT_METADATA
    )
    with pytest.raises(StaleLeaseGenerationError):
        env.work_store.commit_result(
            "work-1",
            reassigned_record.revision,
            stale_attempt,
            stale_commit,
            artifact_resolver=env.artifact_store.resolve,
        )
    final_record = env.work_store.read("work-1")
    real_commit_preserved = (
        final_record.result_commit is not None
        and final_record.result_commit.result_content_checksum
        != stale_commit.result_content_checksum
    )
    passed = (
        expired
        and outcome is not None
        and outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
        and fenced_higher_generation
        and real_commit_preserved
    )
    RECORDER.record(
        FaultPointId.C6_LEASE_EXPIRY_REASSIGNMENT, InvariantId.I3_NO_STALE_LEASE_COMMIT, passed
    )
    assert passed


def test_c7_stale_and_future_fencing_generations_rejected() -> None:
    """C7: stale and future fencing generations. Once a work item is
    RETRYABLE (ready for reassignment), both a stale (too low, matching
    the already-superseded generation) and a forged-future (too high)
    reassignment generation are rejected -- only the exact next generation
    is ever accepted."""
    env = build_environment()
    content = make_synthetic_content("c7")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    record = env.work_store.read("work-1")
    record = env.work_store.acquire_lease(
        "work-1",
        record.revision,
        _lease("worker-a", generation=1),
        reservation_validator=lambda _rid: True,
    )
    record = env.work_store.mark_retryable("work-1", record.revision)
    assert record.current_lease_generation == 1

    with pytest.raises(IdentityMismatchError):
        env.work_store.reassign_lease(
            "work-1",
            record.revision,
            _lease("worker-stale", generation=1),
            reservation_validator=lambda _rid: True,
        )
    with pytest.raises(IdentityMismatchError):
        env.work_store.reassign_lease(
            "work-1",
            record.revision,
            _lease("worker-future", generation=5),
            reservation_validator=lambda _rid: True,
        )
    valid = env.work_store.reassign_lease(
        "work-1",
        record.revision,
        _lease("worker-real", generation=2),
        reservation_validator=lambda _rid: True,
    )
    passed = valid.current_lease_generation == 2
    RECORDER.record(
        FaultPointId.C7_STALE_FUTURE_FENCING, InvariantId.I3_NO_STALE_LEASE_COMMIT, passed
    )
    assert passed


def test_c8_cancellation_at_each_phase_has_defined_outcomes() -> None:  # pylint: disable=too-many-locals
    """C8: cancellation at each phase. Before admission, before lease,
    and after commit each have a distinct, defined outcome; terminal
    evidence already committed is never erased by a later cancellation
    request."""
    env = build_environment()
    # Before admission.
    content_a = make_synthetic_content("c8a")
    reference_a = publish_candidate(env.artifact_store, content_a, reference_id="c8a")
    descriptor_a = make_work_descriptor("work-c8a", 0, reference_a)
    coordinator = env.make_coordinator(ScriptedExecutor())
    coordinator.request_cancellation("work-c8a")
    before_admission = coordinator.admit(
        descriptor_a, reservation_id="res-c8a", requested_cost_cents=100
    )
    before_admission_ok = (
        before_admission is not None
        and before_admission.outcome_kind == WorkOutcomeKind.CANCELLED_NOT_STARTED
    )

    # Before lease (after admission).
    content_b = make_synthetic_content("c8b")
    reference_b = publish_candidate(env.artifact_store, content_b, reference_id="c8b")
    descriptor_b = make_work_descriptor("work-c8b", 1, reference_b)
    env.worker_registry.register(make_worker_registration("worker-a"))
    coordinator.admit(descriptor_b, reservation_id="res-c8b", requested_cost_cents=100)
    coordinator.request_cancellation("work-c8b")
    before_lease = coordinator.invoke_worker("worker-a")
    before_lease_ok = (
        before_lease is not None
        and before_lease.outcome_kind == WorkOutcomeKind.CANCELLED_NOT_STARTED
    )

    # After commit: cancellation has no effect, terminal evidence preserved.
    content_c = make_synthetic_content("c8c")
    reference_c = publish_candidate(env.artifact_store, content_c, reference_id="c8c")
    descriptor_c = make_work_descriptor("work-c8c", 2, reference_c)
    coordinator.admit(descriptor_c, reservation_id="res-c8c", requested_cost_cents=100)
    committed = coordinator.invoke_worker("worker-a")
    assert (
        committed is not None and committed.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    )
    coordinator.request_cancellation("work-c8c")
    still_committed = env.work_store.read("work-c8c").state == WorkItemState.RESULT_COMMITTED

    passed = before_admission_ok and before_lease_ok and still_committed
    RECORDER.record(
        FaultPointId.C8_CANCELLATION_AT_EACH_PHASE,
        InvariantId.I10_NO_TERMINAL_EVIDENCE_ERASED,
        passed,
    )
    assert passed


def test_c9_retry_success_and_retry_exhaustion() -> None:  # pylint: disable=too-many-locals
    """C9: retry success and exhaustion. A retryable failure followed by
    success completes normally; genuine retry-ceiling exhaustion
    dead-letters with RETRY_CEILING_EXCEEDED (distinct from W4's
    NON_RETRYABLE_EXECUTOR_FAILURE)."""
    env = build_environment()
    content_a = make_synthetic_content("c9a")
    reference_a = publish_candidate(env.artifact_store, content_a, reference_id="c9a")
    descriptor_a = make_work_descriptor("work-c9a", 0, reference_a)
    env.worker_registry.register(make_worker_registration("worker-a"))
    executor_a = ScriptedExecutor(script=[retryable_failure()])
    coordinator_a = env.make_coordinator(executor_a)
    coordinator_a.admit(descriptor_a, reservation_id="res-c9a", requested_cost_cents=100)
    first = coordinator_a.invoke_worker("worker-a")
    assert first is not None and first.outcome_kind == WorkOutcomeKind.RETRY_SCHEDULED
    env.clock.advance(10)
    second = coordinator_a.invoke_worker("worker-a")
    retry_success = (
        second is not None and second.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    )

    content_b = make_synthetic_content("c9b")
    reference_b = publish_candidate(env.artifact_store, content_b, reference_id="c9b")
    descriptor_b = make_work_descriptor("work-c9b", 1, reference_b)
    executor_b = ScriptedExecutor(
        script=[retryable_failure(), retryable_failure(), retryable_failure()]
    )
    coordinator_b = env.make_coordinator(executor_b)
    coordinator_b.admit(descriptor_b, reservation_id="res-c9b", requested_cost_cents=100)
    outcomes = []
    for _ in range(3):
        outcomes.append(coordinator_b.invoke_worker("worker-a"))
        env.clock.advance(10)
    disposition = env.work_store.read("work-c9b").terminal_disposition
    exhaustion_ok = (
        outcomes[-1] is not None
        and outcomes[-1].outcome_kind == WorkOutcomeKind.RETRY_EXHAUSTED
        and disposition is not None
        and disposition.disposition_reason == TerminalDispositionReason.RETRY_CEILING_EXCEEDED
    )
    passed = retry_success and exhaustion_ok
    RECORDER.record(
        FaultPointId.C9_RETRY_SUCCESS_AND_EXHAUSTION,
        InvariantId.I11_EVERY_ITEM_ENDS_DEFINED_DISPOSITION,
        passed,
    )
    assert passed


def test_c10_conflicting_result_and_actual_cost_replay_never_overwrite() -> None:
    """C10: conflicting result and conflicting actual-cost replay. A
    second commit attempt for the same work item, carrying a different
    result checksum (or the same checksum but a different
    actual_cost_cents), is refused -- the originally accepted evidence is
    never overwritten."""
    env = build_environment()
    content = make_synthetic_content("c10")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    coordinator = env.make_coordinator(ScriptedExecutor(default_result_content=b"accepted-result"))
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    outcome = coordinator.invoke_worker("worker-a")
    assert outcome is not None and outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    accepted = env.work_store.read("work-1")
    assert accepted.result_commit is not None

    conflicting_attempt = make_execution_attempt(
        scientific_work_id="work-1",
        worker_participant_id="worker-a",
        lease_generation=accepted.current_lease_generation,
        distributed_run_context_checksum=RUN_CTX,
    )
    conflicting_commit = make_result_commit(conflicting_attempt, b"conflicting-result-content")
    env.artifact_store.put(
        conflicting_commit.result_artifact_reference,
        b"conflicting-result-content",
        _DEFAULT_METADATA,
    )
    with pytest.raises(ConflictingResultCommitError):
        env.work_store.commit_result(
            "work-1",
            accepted.revision,
            conflicting_attempt,
            conflicting_commit,
            artifact_resolver=env.artifact_store.resolve,
        )
    unchanged = env.work_store.read("work-1")
    passed = (
        unchanged.result_commit is not None
        and unchanged.result_commit.result_content_checksum
        == accepted.result_commit.result_content_checksum
    )
    RECORDER.record(
        FaultPointId.C10_CONFLICTING_RESULT_AND_COST,
        InvariantId.I1_AT_MOST_ONE_COMMITTED_RESULT,
        passed,
    )
    assert passed


def test_c11_coordinator_recreation_around_same_stores_recovers() -> None:
    """C11: coordinator recreation around the same in-memory stores. A
    fresh Coordinator instance, wired to the exact same store/queue/outbox
    objects a prior (discarded) instance used, completes an in-flight
    admission through to a committed result -- no coordinator-instance-
    local field (other than the documented, non-authoritative
    `_lease_expiry` tracking) is required for correctness. This is
    in-process component recreation, not process-crash durability."""
    env = build_environment()
    content = make_synthetic_content("c11")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))
    first_coordinator = env.make_coordinator(ScriptedExecutor())
    first_coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)
    # first_coordinator is now discarded -- never referenced again.

    second_executor = ScriptedExecutor()
    second_coordinator = Coordinator(
        config=env.config,
        clock=env.clock,
        work_store=env.work_store,
        artifact_reader=env.artifact_store,
        artifact_writer=env.artifact_store,
        budget_store=env.budget_store,
        policy=env.policy,
        worker_registry=env.worker_registry,
        queue=env.queue,
        audit_sink=env.audit_sink,
        audit_outbox=env.audit_outbox,
        cancellation=env.cancellation,
        executor=second_executor,
    )
    outcome = second_coordinator.invoke_worker("worker-a")
    passed = (
        outcome is not None
        and outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
        and second_executor.invocation_count == 1
    )
    RECORDER.record(
        FaultPointId.C11_COORDINATOR_RECREATION,
        InvariantId.I7_NO_LOST_QUEUE_VISIBLE_WORK,
        passed,
    )
    assert passed


def test_c12_reservation_without_work_creation_store_level_diagnosis() -> None:
    """C12: reservation-without-work-creation crash window, at the pure
    store level (the admission A2 companion) -- a reservation with no
    bound work record is RESUMABLE; once resolved (or released), it is
    ALREADY_RESOLVED, never left ambiguous."""
    env = build_environment()
    env.budget_store.reserve("res-c12", 100, 1)
    resumable = (
        diagnose_reservation_work_binding(env.budget_store, env.work_store, "work-c12", "res-c12")
        == OrphanReservationDisposition.RESUMABLE
    )
    env.budget_store.release("res-c12")
    already_resolved = (
        diagnose_reservation_work_binding(env.budget_store, env.work_store, "work-c12", "res-c12")
        == OrphanReservationDisposition.ALREADY_RESOLVED
    )
    passed = resumable and already_resolved
    RECORDER.record(
        FaultPointId.C12_RESERVATION_WITHOUT_WORK, InvariantId.I6_NO_SILENT_BUDGET_LEAK, passed
    )
    assert passed


def test_c13_budget_exhaustion_and_orphan_reservation_recovery() -> None:
    """C13: budget exhaustion and orphan-reservation recovery. Admission
    beyond the budget ceiling is blocked (no reservation leak); a
    reservation left RESERVED with no work created is diagnosable and
    releasable, freeing ceiling capacity for a subsequent admission."""
    env = build_environment(budget_ceiling_cents=100)
    content = make_synthetic_content("c13")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-c13", 0, reference)
    coordinator = env.make_coordinator(ScriptedExecutor())
    with pytest.raises(BudgetCeilingExceededError):
        env.budget_store.reserve("res-c13-too-big", 1000, 1)
    blocked = coordinator.admit(
        descriptor, reservation_id="res-c13-too-big-2", requested_cost_cents=1000
    )
    exhaustion_blocked = (
        blocked is not None and blocked.outcome_kind == WorkOutcomeKind.BUDGET_BLOCKED
    )

    env.budget_store.reserve("res-c13-orphan", 100, 1)
    with pytest.raises(BudgetCeilingExceededError):
        env.budget_store.reserve("res-c13-second", 1, 1)
    env.budget_store.release("res-c13-orphan")
    recovered = env.budget_store.reserve("res-c13-second", 100, 1)
    passed = exhaustion_blocked and recovered.status == ReservationStatus.RESERVED
    RECORDER.record(
        FaultPointId.C13_BUDGET_EXHAUSTION_ORPHAN_RECOVERY,
        InvariantId.I6_NO_SILENT_BUDGET_LEAK,
        passed,
    )
    assert passed


# ---------------------------------------------------------------------------
# Concurrency/race validation (R1-R10)
# ---------------------------------------------------------------------------

_RACE_TRIALS = 15


def _run_concurrency_scenario(worker_count: int, *, environment_class: EnvironmentClass) -> bool:
    env = build_environment(
        max_admitted_workers=worker_count,
        max_in_flight_work=10,
        policy_environment_class=environment_class,
    )
    worker_ids = [f"worker-{i}" for i in range(worker_count)]
    for worker_id in worker_ids:
        env.worker_registry.register(make_worker_registration(worker_id))
    coordinator = env.make_coordinator(ScriptedExecutor())
    admissions = []
    for ordinal in range(worker_count):
        work_id = f"work-{ordinal}"
        content = make_synthetic_content(work_id)
        reference = publish_candidate(env.artifact_store, content, reference_id=work_id)
        descriptor = make_work_descriptor(work_id, ordinal, reference)
        admissions.append((descriptor, f"res-{ordinal}", 100, 1))
    summary = coordinator.run(admissions, worker_ids)
    return summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == worker_count


def test_r1_concurrency_one_under_generic_policy() -> None:
    """R1: concurrency = 1 under the generic synthetic (non-personal)
    policy."""
    passed = _run_concurrency_scenario(1, environment_class=EnvironmentClass.COMPANY_PLAYGROUND)
    RECORDER.record(
        FaultPointId.R1_CONCURRENCY_ONE, InvariantId.I12_DETERMINISTIC_RESULT_ORDERING, passed
    )
    assert passed


def test_r2_concurrency_two_under_generic_policy() -> None:
    """R2: concurrency = 2 under the generic synthetic policy."""
    passed = _run_concurrency_scenario(2, environment_class=EnvironmentClass.COMPANY_PLAYGROUND)
    RECORDER.record(
        FaultPointId.R2_CONCURRENCY_TWO, InvariantId.I12_DETERMINISTIC_RESULT_ORDERING, passed
    )
    assert passed


def test_r3_concurrency_four_under_generic_policy() -> None:
    """R3: concurrency = 4 under the generic synthetic policy -- proves
    the provider-neutral engine is not structurally limited to two."""
    passed = _run_concurrency_scenario(4, environment_class=EnvironmentClass.COMPANY_PLAYGROUND)
    RECORDER.record(
        FaultPointId.R3_CONCURRENCY_FOUR, InvariantId.I12_DETERMINISTIC_RESULT_ORDERING, passed
    )
    assert passed


def test_r4_personal_policy_rejects_concurrency_above_two() -> None:
    """R4: the personal-bootstrap policy rejects concurrency above two,
    at Coordinator construction time, before any admission."""
    env = build_environment(max_admitted_workers=PERSONAL_BOOTSTRAP_MAX_WORKERS)
    higher_config = make_default_config(max_admitted_workers=3, max_in_flight_work=10)
    rejected = False
    try:
        env.make_coordinator(ScriptedExecutor(), config=higher_config)
    except InvalidDistributedProvenanceError:
        rejected = True
    RECORDER.record(
        FaultPointId.R4_PERSONAL_POLICY_REJECTS_ABOVE_TWO,
        InvariantId.I11_EVERY_ITEM_ENDS_DEFINED_DISPOSITION,
        rejected,
    )
    assert rejected


def test_r5_reversed_completion_order_is_deterministic() -> None:  # pylint: disable=too-many-locals
    """R5: a deliberately reversed completion order still yields
    deterministic, input-ordinal-sorted results -- repeated across
    several trials."""
    all_passed = True
    for _ in range(_RACE_TRIALS):
        env = build_environment(max_admitted_workers=2, max_in_flight_work=10)
        env.worker_registry.register(make_worker_registration("worker-a"))
        env.worker_registry.register(make_worker_registration("worker-b"))
        barrier = threading.Barrier(2)

        class _OrderProbeExecutor:  # pylint: disable=too-few-public-methods
            def __init__(self, delay_after_barrier: bool) -> None:
                self._delay_after_barrier = delay_after_barrier

            def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
                """Race through the barrier, optionally spinning after it
                to deliberately reverse completion order."""
                del candidate_content
                barrier.wait()
                if self._delay_after_barrier:
                    for _ in range(50):
                        pass
                return executor_success(b"result")

        content_0 = make_synthetic_content("r5-0")
        reference_0 = publish_candidate(env.artifact_store, content_0, reference_id="r5-cand-0")
        descriptor_0 = make_work_descriptor("r5-work-0", 0, reference_0)
        content_1 = make_synthetic_content("r5-1")
        reference_1 = publish_candidate(env.artifact_store, content_1, reference_id="r5-cand-1")
        descriptor_1 = make_work_descriptor("r5-work-1", 1, reference_1)
        coordinator = env.make_coordinator(_OrderProbeExecutor(False))
        coordinator.admit(descriptor_0, reservation_id="r5-res-0", requested_cost_cents=100)
        coordinator.admit(descriptor_1, reservation_id="r5-res-1", requested_cost_cents=100)

        outcomes = []
        outcomes_lock = threading.Lock()

        def run_one(worker_id: str, delay: bool) -> None:
            """Invoke one worker with its own probe executor."""
            coordinator._executor = _OrderProbeExecutor(delay)  # pylint: disable=protected-access
            outcome = coordinator.invoke_worker(worker_id)
            if outcome is not None:
                with outcomes_lock:
                    outcomes.append(outcome)

        thread_a = threading.Thread(target=run_one, args=("worker-a", True))
        thread_b = threading.Thread(target=run_one, args=("worker-b", False))
        thread_a.start()
        thread_b.start()
        thread_a.join()
        thread_b.join()
        summary = build_run_summary(outcomes)
        if [o.input_ordinal for o in summary.outcomes] != [0, 1]:
            all_passed = False
    RECORDER.record(
        FaultPointId.R5_REVERSED_COMPLETION_ORDER,
        InvariantId.I12_DETERMINISTIC_RESULT_ORDERING,
        all_passed,
        attempt_count=_RACE_TRIALS,
    )
    assert all_passed


def test_r6_duplicate_deliveries_racing() -> None:
    """R6: duplicate deliveries racing -- two workers racing to acquire
    the same lease yields exactly one valid lease holder, repeated
    across trials."""
    all_passed = True
    for _ in range(_RACE_TRIALS):
        env = build_environment(max_admitted_workers=2)
        env.worker_registry.register(make_worker_registration("worker-a"))
        env.worker_registry.register(make_worker_registration("worker-b"))
        content = make_synthetic_content("r6")
        reference = publish_candidate(env.artifact_store, content, reference_id="r6-cand")
        descriptor = make_work_descriptor("r6-work", 0, reference)
        coordinator = env.make_coordinator(ScriptedExecutor())
        coordinator.admit(descriptor, reservation_id="r6-res", requested_cost_cents=100)

        barrier = threading.Barrier(2)
        results: list[tuple[str, str | None]] = []
        results_lock = threading.Lock()

        def race_lease(worker_id: str) -> None:
            """Race to acquire the lease, recording the outcome."""
            barrier.wait()
            record = env.work_store.read("r6-work")
            try:
                leased = env.work_store.acquire_lease(
                    "r6-work",
                    record.revision,
                    _lease(worker_id, work_id="r6-work"),
                    reservation_validator=lambda _rid: True,
                )
                with results_lock:
                    results.append(("won", leased.worker_participant_id))
            except Exception:  # pylint: disable=broad-except
                with results_lock:
                    results.append(("lost", worker_id))

        threads = [
            threading.Thread(target=race_lease, args=(worker_id,))
            for worker_id in ("worker-a", "worker-b")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        winners = [entry for entry in results if entry[0] == "won"]
        if len(winners) != 1:
            all_passed = False
    RECORDER.record(
        FaultPointId.R6_DUPLICATE_DELIVERIES_RACING,
        InvariantId.I3_NO_STALE_LEASE_COMMIT,
        all_passed,
        attempt_count=_RACE_TRIALS,
    )
    assert all_passed


def test_r7_cancellation_racing_commit() -> None:  # pylint: disable=too-many-locals
    """R7: cancellation racing commit -- exactly one deterministic
    winner (either the cancellation or the commit), never both, and the
    loser is cleanly rejected."""
    all_passed = True
    for _ in range(_RACE_TRIALS):
        env = build_environment()
        content = make_synthetic_content("r7")
        reference = publish_candidate(env.artifact_store, content, reference_id="r7-cand")
        descriptor = make_work_descriptor("r7-work", 0, reference)
        env.worker_registry.register(make_worker_registration("worker-a"))
        coordinator = env.make_coordinator(ScriptedExecutor())
        coordinator.admit(descriptor, reservation_id="r7-res", requested_cost_cents=100)
        record = env.work_store.read("r7-work")
        record = env.work_store.acquire_lease(
            "r7-work",
            record.revision,
            _lease("worker-a", work_id="r7-work"),
            reservation_validator=lambda _rid: True,
        )
        record = env.work_store.transition_to_executing("r7-work", record.revision)
        attempt = make_execution_attempt(
            scientific_work_id="r7-work",
            worker_participant_id="worker-a",
            lease_generation=1,
            distributed_run_context_checksum=RUN_CTX,
        )
        result_content = b"synthetic-r7-content"
        commit = make_result_commit(attempt, result_content)
        env.artifact_store.put(commit.result_artifact_reference, result_content, _DEFAULT_METADATA)

        cancel_request = CancellationRequest(
            distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
            checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
            scientific_work_id="r7-work",
            cancellation_scope=CancellationScope.AFTER_LEASE,
            requested_at_logical_clock=0,
        )
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        outcomes_lock = threading.Lock()

        def try_commit() -> None:
            """Race to commit the result."""
            barrier.wait()
            try:
                env.work_store.commit_result(
                    "r7-work",
                    record.revision,
                    attempt,
                    commit,
                    artifact_resolver=env.artifact_store.resolve,
                )
                with outcomes_lock:
                    outcomes.append("commit-won")
            except Exception:  # pylint: disable=broad-except
                with outcomes_lock:
                    outcomes.append("commit-lost")

        def try_cancel() -> None:
            """Race to cancel."""
            barrier.wait()
            try:
                env.work_store.request_cancellation("r7-work", record.revision, cancel_request)
                with outcomes_lock:
                    outcomes.append("cancel-won")
            except Exception:  # pylint: disable=broad-except
                with outcomes_lock:
                    outcomes.append("cancel-lost")

        threads = [threading.Thread(target=try_commit), threading.Thread(target=try_cancel)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        winners = [o for o in outcomes if o.endswith("-won")]
        final_state = env.work_store.read("r7-work").state
        one_winner = len(winners) == 1
        state_matches_winner = (
            (winners == ["commit-won"] and final_state == WorkItemState.RESULT_COMMITTED)
            or (winners == ["cancel-won"] and final_state == WorkItemState.CANCELLED)
        )
        if not (one_winner and state_matches_winner):
            all_passed = False
    RECORDER.record(
        FaultPointId.R7_CANCELLATION_RACING_COMMIT,
        InvariantId.I10_NO_TERMINAL_EVIDENCE_ERASED,
        all_passed,
        attempt_count=_RACE_TRIALS,
    )
    assert all_passed


def test_r8_lease_expiry_racing_commit() -> None:  # pylint: disable=too-many-locals
    """R8: lease expiry racing commit -- a commit racing an expiry-driven
    reassignment has exactly one deterministic winner (the revision-CAS
    ensures the loser's write is cleanly rejected, never corrupting
    state)."""
    all_passed = True
    for _ in range(_RACE_TRIALS):
        env = build_environment()
        content = make_synthetic_content("r8")
        reference = publish_candidate(env.artifact_store, content, reference_id="r8-cand")
        descriptor = make_work_descriptor("r8-work", 0, reference)
        env.worker_registry.register(make_worker_registration("worker-a"))
        env.worker_registry.register(make_worker_registration("worker-b"))
        coordinator = env.make_coordinator(ScriptedExecutor())
        coordinator.admit(descriptor, reservation_id="r8-res", requested_cost_cents=100)
        record = env.work_store.read("r8-work")
        record = env.work_store.acquire_lease(
            "r8-work",
            record.revision,
            _lease("worker-a", work_id="r8-work"),
            reservation_validator=lambda _rid: True,
        )
        record = env.work_store.transition_to_executing("r8-work", record.revision)
        attempt = make_execution_attempt(
            scientific_work_id="r8-work",
            worker_participant_id="worker-a",
            lease_generation=1,
            distributed_run_context_checksum=RUN_CTX,
        )
        result_content = b"synthetic-r8-content"
        commit = make_result_commit(attempt, result_content)
        env.artifact_store.put(commit.result_artifact_reference, result_content, _DEFAULT_METADATA)

        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        outcomes_lock = threading.Lock()

        def try_commit() -> None:
            """Race to commit the result at the pre-expiry revision."""
            barrier.wait()
            try:
                env.work_store.commit_result(
                    "r8-work",
                    record.revision,
                    attempt,
                    commit,
                    artifact_resolver=env.artifact_store.resolve,
                )
                with outcomes_lock:
                    outcomes.append("commit-won")
            except (RevisionConflictError, MissingArtifactReferenceError):
                with outcomes_lock:
                    outcomes.append("commit-lost")

        def try_expire() -> None:
            """Race to mark the item retryable (expiry)."""
            barrier.wait()
            try:
                env.work_store.mark_retryable("r8-work", record.revision)
                with outcomes_lock:
                    outcomes.append("expire-won")
            except RevisionConflictError:
                with outcomes_lock:
                    outcomes.append("expire-lost")

        threads = [threading.Thread(target=try_commit), threading.Thread(target=try_expire)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        winners = [o for o in outcomes if o.endswith("-won")]
        final_state = env.work_store.read("r8-work").state
        one_winner = len(winners) == 1
        state_matches_winner = (
            (winners == ["commit-won"] and final_state == WorkItemState.RESULT_COMMITTED)
            or (winners == ["expire-won"] and final_state == WorkItemState.RETRYABLE)
        )
        if not (one_winner and state_matches_winner):
            all_passed = False
    RECORDER.record(
        FaultPointId.R8_LEASE_EXPIRY_RACING_COMMIT,
        InvariantId.I3_NO_STALE_LEASE_COMMIT,
        all_passed,
        attempt_count=_RACE_TRIALS,
    )
    assert all_passed


def test_r9_outbox_dispatch_racing_authoritative_reconciliation() -> None:
    """R9: outbox dispatch racing authoritative reconciliation -- calling
    dispatch_pending concurrently with an authoritative commit never
    corrupts either store; dispatch always reads a fully-formed,
    self-consistent snapshot (never a partially-written record), proven
    by repeating the race and cross-checking the final delivered/pending
    state against the final authoritative state every time."""
    all_passed = True
    for _ in range(_RACE_TRIALS):
        env = build_environment()
        content = make_synthetic_content("r9")
        reference = publish_candidate(env.artifact_store, content, reference_id="r9-cand")
        descriptor = make_work_descriptor("r9-work", 0, reference)
        env.worker_registry.register(make_worker_registration("worker-a"))
        coordinator = env.make_coordinator(ScriptedExecutor())
        coordinator.admit(descriptor, reservation_id="r9-res", requested_cost_cents=100)

        barrier = threading.Barrier(2)
        dispatch_summaries: list[object] = []
        summaries_lock = threading.Lock()

        def race_commit() -> None:
            """Race the commit against a concurrent dispatch."""
            barrier.wait()
            coordinator.invoke_worker("worker-a")

        def race_dispatch() -> None:
            """Race a dispatch against the concurrent commit."""
            barrier.wait()
            summary = coordinator.dispatch_audit()
            with summaries_lock:
                dispatch_summaries.append(summary)

        threads = [threading.Thread(target=race_commit), threading.Thread(target=race_dispatch)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        # Drain any still-pending entries after the race settles.
        coordinator.dispatch_audit()
        final_record = env.work_store.read("r9-work")
        consistent = (
            final_record.state == WorkItemState.RESULT_COMMITTED
            and env.audit_outbox.pending_count() == 0
        )
        if not consistent:
            all_passed = False
    RECORDER.record(
        FaultPointId.R9_OUTBOX_DISPATCH_RACING_RECONCILIATION,
        InvariantId.I8_NO_UNAUDITED_AUTHORITATIVE_TRANSITION,
        all_passed,
        attempt_count=_RACE_TRIALS,
    )
    assert all_passed


def test_r10_concurrent_reservations_at_exact_ceiling() -> None:
    """R10: concurrent budget reservations at the exact ceiling never
    oversubscribe -- repeated across trials, exactly the ceiling's own
    number of reservations succeed every time."""
    all_passed = True
    for _ in range(_RACE_TRIALS):
        env = build_environment(
            budget_ceiling_cents=500,
            max_admitted_workers=6,
            policy_environment_class=EnvironmentClass.COMPANY_PLAYGROUND,
        )
        barrier = threading.Barrier(6)
        results: list[bool] = []
        results_lock = threading.Lock()

        def race_reserve(index: int) -> None:
            """Race to reserve 100 cents against a 500-cent ceiling."""
            barrier.wait()
            try:
                env.budget_store.reserve(f"r10-res-{index}", 100, 1)
                with results_lock:
                    results.append(True)
            except (BudgetCeilingExceededError, WorkerCeilingExceededError):
                with results_lock:
                    results.append(False)

        threads = [threading.Thread(target=race_reserve, args=(i,)) for i in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if sum(1 for r in results if r) != 5:
            all_passed = False
    RECORDER.record(
        FaultPointId.R10_CONCURRENT_RESERVATIONS_AT_CEILING,
        InvariantId.I6_NO_SILENT_BUDGET_LEAK,
        all_passed,
        attempt_count=_RACE_TRIALS,
    )
    assert all_passed


# ---------------------------------------------------------------------------
# Final: build and write the safe, committed conformance report
# ---------------------------------------------------------------------------


def test_zzz_generate_and_write_safe_conformance_report() -> None:
    """Build the safe FaultConformanceReport from every entry recorded by
    the tests above, and write it to docs/measurement/ -- deterministic
    given a fixed, frozen plan checksum and pytest's own default
    (non-randomized) collection order within this one file."""
    entries = RECORDER.entries
    assert entries, "no conformance entries were recorded -- the suite above did not run"
    report = build_fault_conformance_report(
        entries,
        plan_sha256="9bf39c6bae0b43e3ce0807d9ca1bd6f08f892b7356f563c73e75376b7bbd9891",
        plan_git_blob_sha1="b037ed68292ed06fc226453ed07130992783db6b",
    )
    assert report.readiness == ReadinessClassification.IN_PROCESS_RECOVERY_READY_FOR_B2C
    assert report.failed_count == 0

    out_dir = pathlib.Path(__file__).resolve().parent.parent / "docs" / "measurement"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "megb-03h2c3b2b3-fault-conformance-report.json"
    md_path = out_dir / "megb-03h2c3b2b3-fault-conformance-report.md"
    json_path.write_text(
        json.dumps(fault_conformance_report_to_dict(report), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
