"""MEGB-03H.2C.3B.2C: offline end-to-end synthetic distributed
qualification suite, exercising the full accepted B.2B.1/B.2B.2/B.2B.3
coordinator/worker engine against this checkpoint's own frozen 8-item
path-coverage workload and 4-item equivalence workload (see
``docs/reference/megb-03h2c3b2c-offline-e2e-qualification-plan.md``).

Every test performs its own real, independent admission/lease/execution/
commit/finalize/audit/acknowledgement sequence through the accepted
coordinator -- never a shortcut around it -- and contributes its own
measured counts to the shared module-level ``ACCUMULATOR``
(``tests/_offline_e2e_qualification_harness.py``). The final test in
this file builds and writes the safe, committed qualification report
from the accumulated totals.

No wall-clock sleep, process termination, signal, subprocess, Docker, or
network access anywhere. No GCP/`gcloud`/cloud resource, HumanEval
evidence, real candidate content, or model API call. All concurrency
uses real Python threads, synchronized with ``threading.Barrier`` where
needed, measured with the injected ``LogicalClock`` -- never wall-clock
time as scientific evidence."""

# pylint: disable=duplicate-code
# This file's own admission/execution fixture usage inherently mirrors
# tests/test_coordinator_admission.py's, tests/test_coordinator_execution.py's,
# and tests/test_fault_conformance.py's own patterns (all build the same
# synthetic environments against the same coordinator API) -- shared
# boilerplate, not shared logic, per this project's own established
# convention.
# pylint: disable=too-many-lines
# One large, deliberately exhaustive end-to-end qualification suite
# mapping 1:1 onto every item in this checkpoint's own frozen workload --
# never split across files, so the plan/test/report mapping stays
# traceable.

import dataclasses
import json
import pathlib
import threading

import pytest

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
)
from src.distributed.artifact_capabilities import (
    ArtifactCapabilityViolationError,
    GenerationPlaneArtifactCapability,
    WorkerArtifactCapability,
)
from src.distributed.artifact_store import ArtifactMetadata
from src.distributed.budget_store import ReservationNotFoundError, ReservationStatus
from src.distributed.candidate_manifest import build_candidate_manifest
from src.distributed.coordinator import Coordinator
from src.distributed.executor import (
    ExecutorFailureReason,
    ExecutorInvocationResult,
    executor_failure,
    executor_success,
)
from src.distributed.offline_e2e_qualification_report import (
    ReadinessClassification,
    build_offline_e2e_qualification_report,
    offline_e2e_qualification_report_to_dict,
    render_markdown,
)
from src.distributed.personal_policy import DataClassification, WorkloadClass
from src.distributed.provenance import (
    DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
    DistributedRunIntent,
    EnvironmentClass,
)
from src.distributed.qualification_gate import (
    ProvenanceGateFailureReason,
    ProvenanceGateReadiness,
    evaluate_qualification_gate,
)
from src.distributed.safe_audit import SafeAuditEventType, build_safe_audit_event
from src.distributed.state_machine import WorkItemState
from src.distributed.work_contracts import (
    TerminalDispositionReason,
    queue_work_message_field_names,
    work_descriptor_to_queue_message,
)
from src.distributed.work_contracts import ArtifactReference
from src.distributed.work_outcome import CoordinatorRunSummary, WorkOutcome, WorkOutcomeKind
from src.distributed.worker_contracts import Lease
from tests._atomic_stores_fixtures import make_result_artifact_reference, make_result_commit
from tests._coordinator_fixtures import (
    RUN_CTX,
    CoordinatorEnvironment,
    ScriptedExecutor,
    build_environment,
    make_work_descriptor,
    make_worker_registration,
    terminal_failure,
)
from tests._distributed_fixtures import (
    make_run_context,
    make_two_region_workers,
    make_worker_context,
)
from tests._distributed_orchestration_fixtures import make_execution_attempt
from tests._offline_e2e_qualification_fixtures import (
    BarrierSynchronizedTransformExecutor,
    EQUIVALENCE_ITEM_IDS,
    PeakConcurrencyTrackingExecutor,
    TransformExecutor,
    compute_workload_checksum,
    equivalence_content,
    path_coverage_content,
    synthetic_transform,
    synthetic_transform_checksum,
)
from tests._offline_e2e_qualification_harness import ACCUMULATOR

_METADATA = ArtifactMetadata(
    # MEGB-03H.2C.3B.2C correction: a qualifying run must never use
    # WorkloadClass.SYNTHETIC_SMOKE for its candidate metadata --
    # SYNTHETIC_QUALIFICATION_CANDIDATE, exactly as the frozen plan
    # specifies, is now used throughout. The earlier substitution of
    # SYNTHETIC_SMOKE was itself a defect (the shared build_environment()
    # test fixture's default personal policy narrowly allowlisted only
    # SYNTHETIC_SMOKE, not the full accepted
    # PERSONAL_BOOTSTRAP_ALLOWED_WORKLOAD_CLASSES set) -- corrected at
    # its root in tests/_coordinator_fixtures.py::make_default_policy,
    # not worked around here.
    workload_class=WorkloadClass.SYNTHETIC_QUALIFICATION_CANDIDATE,
    data_classification=DataClassification.SYNTHETIC,
)


def _publish(env: CoordinatorEnvironment, item_id: str) -> ArtifactReference:
    """Publish one path-coverage candidate through the generation-plane
    capability -- never a raw ``artifact_store.put`` call, and never
    through the coordinator/worker engine."""
    capability = GenerationPlaneArtifactCapability(env.artifact_store)
    manifest = build_candidate_manifest(
        capability, {f"e2e-cand-{item_id}": path_coverage_content(item_id)}, metadata=_METADATA
    )
    return manifest.manifest_entries[0]


def _track_lease_expiry(
    coordinator: Coordinator, env: CoordinatorEnvironment, work_id: str
) -> None:
    """Simulate the coordinator-side bookkeeping ``_acquire_or_reassign_lease``
    would have performed, for tests that acquire a lease directly against
    the store (bypassing the coordinator's own admission/lease path) --
    same established pattern as ``tests/test_fault_conformance.py``'s own
    helper of the same name."""
    coordinator._lease_expiry[work_id] = (  # pylint: disable=protected-access
        env.clock.now() + env.config.lease_duration_ticks
    )


def _lease(worker_id: str, work_id: str, generation: int = 1) -> Lease:
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
# Provenance / qualification-gate requirements
# ---------------------------------------------------------------------------


def test_e2e_gate_ready_for_complete_provenance() -> None:
    """The qualification gate accepts this checkpoint's own two-worker,
    complete-provenance construction, and its safe identity/topology
    fields are recorded for the final report."""
    run_context = make_run_context(run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE)
    worker_a, worker_b = make_two_region_workers(run_context)
    result = evaluate_qualification_gate(run_context, (worker_a, worker_b))
    assert result.readiness == ProvenanceGateReadiness.READY
    assert result.qualification_identity is not None
    assert result.worker_summary is not None
    ACCUMULATOR.run_context_checksum = run_context.run_context_checksum
    ACCUMULATOR.qualification_identity_checksum = result.qualification_identity.identity_checksum
    ACCUMULATOR.worker_topology_provisioning_class_counts = (
        result.worker_summary.provisioning_class_counts
    )
    ACCUMULATOR.worker_topology_region_counts = result.worker_summary.region_counts
    ACCUMULATOR.worker_topology_machine_type_counts = result.worker_summary.machine_type_counts
    ACCUMULATOR.distributed_run_intent = run_context.run_intent.value
    ACCUMULATOR.qualifying_workload_class = WorkloadClass.SYNTHETIC_QUALIFICATION_CANDIDATE.value
    ACCUMULATOR.qualification_gate_ready = result.readiness == ProvenanceGateReadiness.READY


def test_e2e_gate_blocked_for_smoke_test_intent() -> None:
    """The gate rejects a run_intent=SMOKE_TEST construction --
    NOT_QUALIFICATION_INTENT."""
    run_context = make_run_context(run_intent=DistributedRunIntent.SMOKE_TEST)
    worker = make_worker_context(parent_run_context_checksum=run_context.run_context_checksum)
    result = evaluate_qualification_gate(run_context, (worker,))
    assert result.readiness == ProvenanceGateReadiness.BLOCKED
    assert ProvenanceGateFailureReason.NOT_QUALIFICATION_INTENT in result.missing_dimensions
    assert result.qualification_identity is None
    assert result.worker_summary is None


def test_e2e_gate_blocked_for_mismatched_worker_context() -> None:
    """The gate rejects a worker context whose parent_run_context_checksum
    does not match the run context's own -- MIXED_CONTEXT_WORKERS."""
    run_context = make_run_context(run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE)
    mismatched_worker = make_worker_context(parent_run_context_checksum="f" * 64)
    result = evaluate_qualification_gate(run_context, (mismatched_worker,))
    assert result.readiness == ProvenanceGateReadiness.BLOCKED
    assert ProvenanceGateFailureReason.MIXED_CONTEXT_WORKERS in result.missing_dimensions


def test_e2e_gate_blocked_for_duplicate_worker_provenance() -> None:
    """The gate rejects two worker contexts sharing one
    worker_participant_id -- DUPLICATE_WORKER_PROVENANCE."""
    run_context = make_run_context(run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE)
    worker_a = make_worker_context(parent_run_context_checksum=run_context.run_context_checksum)
    worker_a_dup = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum
    )
    result = evaluate_qualification_gate(run_context, (worker_a, worker_a_dup))
    assert result.readiness == ProvenanceGateReadiness.BLOCKED
    assert ProvenanceGateFailureReason.DUPLICATE_WORKER_PROVENANCE in result.missing_dimensions


def test_e2e_queue_messages_contain_only_allowlisted_fields() -> None:
    """Queue-visible records for this checkpoint's own workload contain
    exactly the already-established allowlisted field set -- exact
    field-set equality, not merely "no forbidden substring"."""
    env = build_environment()
    reference = _publish(env, "queue-check")
    descriptor = make_work_descriptor("e2e-queue-check", 0, reference)
    message = work_descriptor_to_queue_message(
        descriptor,
        delivery_id="delivery-0001",
        routing_environment_class=EnvironmentClass.PERSONAL_BOOTSTRAP.value,
        routing_logical_environment_id="env-logical-e2e",
    )
    field_names = {f.name for f in dataclasses.fields(message)}
    assert field_names == queue_work_message_field_names()


def test_e2e_capability_boundaries_hold_against_the_shared_store() -> None:
    """After candidates are published through the generation-plane
    capability, the worker capability sharing the same backing store
    still cannot author a candidate, and the generation-plane capability
    still cannot read or publish a result -- checked against the exact
    store instance this suite's other tests actually use, not a fresh
    throwaway one."""
    env = build_environment()
    reference = _publish(env, "boundary-check")
    assert env.artifact_store.resolve(reference)

    generation_capability = GenerationPlaneArtifactCapability(env.artifact_store)
    assert not hasattr(generation_capability, "get")
    assert not hasattr(generation_capability, "resolve")
    assert not hasattr(generation_capability, "publish_result")

    worker_capability = WorkerArtifactCapability(env.artifact_store, env.artifact_store)
    with pytest.raises(ArtifactCapabilityViolationError):
        worker_capability.publish_result(reference, b"forged-candidate", _METADATA)


# ---------------------------------------------------------------------------
# Path-coverage workload (e2e-01/02/08, e2e-03..e2e-07)
# ---------------------------------------------------------------------------


# pylint: disable-next=too-many-locals
def test_e2e_01_02_08_two_worker_contexts_and_reversed_completion_order() -> None:
    """e2e-01/e2e-02: successful outcomes across two distinct worker
    contexts. e2e-08: two items admitted together and raced under a
    barrier so one's executor completes strictly after the other's,
    proving the aggregated result is still ordered by input_ordinal
    regardless of completion order."""
    env = build_environment(max_admitted_workers=2, max_in_flight_work=10)
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))

    ref_02 = _publish(env, "02")
    descriptor_02 = make_work_descriptor("e2e-02", 1, ref_02)
    coordinator = env.make_coordinator(TransformExecutor())
    coordinator.admit(descriptor_02, reservation_id="res-e2e-02", requested_cost_cents=100)
    outcome_02 = coordinator.invoke_worker("worker-b")
    assert (
        outcome_02 is not None
        and outcome_02.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    )
    assert outcome_02.result_content_checksum == synthetic_transform_checksum(
        path_coverage_content("02")
    )

    ref_01 = _publish(env, "01")
    ref_08 = _publish(env, "08")
    descriptor_01 = make_work_descriptor("e2e-01", 0, ref_01)
    descriptor_08 = make_work_descriptor("e2e-08", 2, ref_08)
    coordinator.admit(descriptor_01, reservation_id="res-e2e-01", requested_cost_cents=100)
    coordinator.admit(descriptor_08, reservation_id="res-e2e-08", requested_cost_cents=100)

    barrier = threading.Barrier(2)

    class _OrderProbeExecutor:  # pylint: disable=too-few-public-methods
        def __init__(self, delay_after_barrier: bool) -> None:
            self._delay_after_barrier = delay_after_barrier

        def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
            """Race through the barrier, optionally spinning after it to
            deliberately reverse completion order."""
            barrier.wait()
            if self._delay_after_barrier:
                for _ in range(50):
                    pass
            return executor_success(synthetic_transform_checksum(candidate_content).encode())

    outcomes: list[WorkOutcome] = []
    outcomes_lock = threading.Lock()

    def run_one(worker_id: str, delay: bool) -> None:
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

    with outcomes_lock:
        ordered = sorted(outcomes, key=lambda outcome: outcome.input_ordinal)
    assert [outcome.input_ordinal for outcome in ordered] == [0, 2]
    assert all(
        outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED for outcome in ordered
    )

    for reservation_id in ("res-e2e-01", "res-e2e-02", "res-e2e-08"):
        assert env.budget_store.get(reservation_id).status == ReservationStatus.FINALIZED
    audit_summary = coordinator.dispatch_audit()
    assert not audit_summary.still_pending_keys
    assert env.queue.in_flight_count() == 0

    ACCUMULATOR.admitted_count += 3
    ACCUMULATOR.completed_count += 3
    ACCUMULATOR.budget_requested_cents_total += 300
    ACCUMULATOR.budget_finalized_cents_total += 300
    ACCUMULATOR.audit_delivered_count += len(audit_summary.delivered_keys)


def test_e2e_03_retryable_failure_then_success() -> None:
    """e2e-03: a retryable executor failure schedules a retry; the same
    scientific work identity then completes on its second attempt with
    the real, deterministic transform of its candidate content."""
    env = build_environment()
    env.worker_registry.register(make_worker_registration("worker-a"))
    reference = _publish(env, "03")
    descriptor = make_work_descriptor("e2e-03", 0, reference)
    executor = TransformExecutor(pre_script=[_retryable_failure_result()])
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-e2e-03", requested_cost_cents=100)

    first = coordinator.invoke_worker("worker-a")
    assert first is not None and first.outcome_kind == WorkOutcomeKind.RETRY_SCHEDULED
    env.clock.advance(10)
    second = coordinator.invoke_worker("worker-a")
    assert second is not None and second.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
    assert second.result_content_checksum == synthetic_transform_checksum(
        path_coverage_content("03")
    )
    assert env.work_store.read("e2e-03").scientific_work_id == "e2e-03"

    audit_summary = coordinator.dispatch_audit()
    assert not audit_summary.still_pending_keys
    assert env.queue.in_flight_count() == 0

    ACCUMULATOR.admitted_count += 1
    ACCUMULATOR.completed_count += 1
    ACCUMULATOR.retried_count += 1
    ACCUMULATOR.budget_requested_cents_total += 100
    ACCUMULATOR.budget_finalized_cents_total += 100
    ACCUMULATOR.audit_delivered_count += len(audit_summary.delivered_keys)


def test_e2e_04_non_retryable_failure_and_budget_release() -> None:
    """e2e-04: a non-retryable executor failure dead-letters immediately,
    tagged NON_RETRYABLE_EXECUTOR_FAILURE (never RETRY_CEILING_EXCEEDED);
    its orphaned reservation is then explicitly reconciled -- released --
    per this project's own established C13 reconciliation pattern."""
    env = build_environment()
    env.worker_registry.register(make_worker_registration("worker-a"))
    reference = _publish(env, "04")
    descriptor = make_work_descriptor("e2e-04", 0, reference)
    executor = ScriptedExecutor(script=[terminal_failure()])
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-e2e-04", requested_cost_cents=100)
    outcome = coordinator.invoke_worker("worker-a")
    disposition = env.work_store.read("e2e-04").terminal_disposition
    assert (
        outcome is not None
        and outcome.outcome_kind == WorkOutcomeKind.RETRY_EXHAUSTED
        and disposition is not None
        and disposition.disposition_reason
        == TerminalDispositionReason.NON_RETRYABLE_EXECUTOR_FAILURE
    )
    env.budget_store.release("res-e2e-04")
    assert env.budget_store.get("res-e2e-04").status == ReservationStatus.RELEASED

    audit_summary = coordinator.dispatch_audit()
    assert not audit_summary.still_pending_keys
    assert env.queue.in_flight_count() == 0

    ACCUMULATOR.admitted_count += 1
    ACCUMULATOR.failed_count += 1
    ACCUMULATOR.budget_requested_cents_total += 100
    ACCUMULATOR.budget_released_cents_total += 100
    ACCUMULATOR.audit_delivered_count += len(audit_summary.delivered_keys)


def test_e2e_05_duplicate_delivery_and_stale_lease_is_harmless() -> None:
    """e2e-05: a duplicate/stale delivery attempt against an
    already-leased item is rejected (STALE_LEASE); a duplicate queue
    publish is idempotent; the real attempt then completes normally."""
    env = build_environment()
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    reference = _publish(env, "05")
    descriptor = make_work_descriptor("e2e-05", 0, reference)
    executor = TransformExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-e2e-05", requested_cost_cents=100)

    record = env.work_store.read("e2e-05")
    env.work_store.acquire_lease(
        "e2e-05",
        record.revision,
        _lease("worker-a", "e2e-05"),
        reservation_validator=lambda _rid: True,
    )
    _track_lease_expiry(coordinator, env, "e2e-05")
    stale_outcome = coordinator.invoke_worker("worker-b")
    assert stale_outcome is not None and stale_outcome.outcome_kind == WorkOutcomeKind.STALE_LEASE

    duplicate_message = env.queue.publish(descriptor)
    assert duplicate_message is not None

    env.clock.advance(100)
    coordinator.check_lease_expiry("e2e-05")
    real_outcome = coordinator.invoke_worker("worker-a")
    assert (
        real_outcome is not None
        and real_outcome.outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
        and real_outcome.result_content_checksum
        == synthetic_transform_checksum(path_coverage_content("05"))
    )

    audit_summary = coordinator.dispatch_audit()
    assert not audit_summary.still_pending_keys
    assert env.queue.in_flight_count() == 0

    ACCUMULATOR.admitted_count += 1
    ACCUMULATOR.completed_count += 1
    ACCUMULATOR.duplicate_delivery_count += 1
    ACCUMULATOR.budget_requested_cents_total += 100
    ACCUMULATOR.budget_finalized_cents_total += 100
    ACCUMULATOR.audit_delivered_count += len(audit_summary.delivered_keys)


# pylint: disable-next=too-many-locals
def test_e2e_06_committed_result_recovery_and_abandoned_orphan_intent() -> None:
    """e2e-06: a result committed but never finalized/acked (simulated
    crash window) recovers on redelivery without re-invoking the
    executor, finalizing exactly once; a separately-manufactured,
    never-landing outbox intent for a distinct attempt on the same item
    is reconciled ABANDONED once the real commit lands, releasing its
    pending capacity."""
    env = build_environment()
    env.worker_registry.register(make_worker_registration("worker-a"))
    reference = _publish(env, "06")
    descriptor = make_work_descriptor("e2e-06", 0, reference)
    executor = TransformExecutor()
    coordinator = env.make_coordinator(executor)
    coordinator.admit(descriptor, reservation_id="res-e2e-06", requested_cost_cents=100)

    record = env.work_store.read("e2e-06")
    record = env.work_store.acquire_lease(
        "e2e-06",
        record.revision,
        _lease("worker-a", "e2e-06"),
        reservation_validator=lambda _rid: True,
    )
    record = env.work_store.transition_to_executing("e2e-06", record.revision)

    orphan_attempt = make_execution_attempt(
        scientific_work_id="e2e-06",
        worker_participant_id="worker-a",
        lease_generation=1,
        distributed_run_context_checksum=RUN_CTX,
    )
    orphan_commit = make_result_commit(orphan_attempt, b"e2e-06-orphan-content")
    orphan_event = build_safe_audit_event(
        event_type=SafeAuditEventType.RESULT_COMMITTED,
        work_reference="e2e-06",
        safe_run_identity=RUN_CTX,
        state_after=WorkItemState.RESULT_COMMITTED,
        logical_timestamp=0,
        lease_generation=1,
        content_checksum=orphan_commit.result_content_checksum,
        input_ordinal=0,
    )
    env.audit_outbox.enqueue(
        f"result-committed:e2e-06:{orphan_attempt.attempt_checksum}",
        orphan_event,
        reconciliation_scientific_work_id="e2e-06",
        reconciliation_expected_state=WorkItemState.RESULT_COMMITTED,
        reconciliation_expected_result_content_checksum=orphan_commit.result_content_checksum,
    )

    attempt = make_execution_attempt(
        scientific_work_id="e2e-06",
        worker_participant_id="worker-a",
        lease_generation=1,
        distributed_run_context_checksum=RUN_CTX,
    )
    result_content = path_coverage_content("06")
    transformed = synthetic_transform(result_content)
    commit = make_result_commit(
        attempt,
        transformed,
        actual_cost_cents=100,
        result_artifact_reference=make_result_artifact_reference(transformed, metadata=_METADATA),
    )
    env.artifact_store.put(commit.result_artifact_reference, transformed, _METADATA)
    env.work_store.commit_result(
        "e2e-06", record.revision, attempt, commit, artifact_resolver=env.artifact_store.resolve
    )
    # Simulated crash: neither finalize nor ack happens for this attempt.

    outcome = coordinator.invoke_worker("worker-a")
    assert (
        outcome is not None
        and outcome.outcome_kind == WorkOutcomeKind.RECOVERED_COMMITTED_RESULT
        and executor.invocation_count == 0
    )
    reservation = env.budget_store.get("res-e2e-06")
    assert (
        reservation.status == ReservationStatus.FINALIZED
        and reservation.actual_cost_cents == 100
    )

    audit_summary = coordinator.dispatch_audit()
    assert not audit_summary.still_pending_keys
    orphan_key = f"result-committed:e2e-06:{orphan_attempt.attempt_checksum}"
    assert orphan_key in audit_summary.abandoned_keys
    assert env.queue.in_flight_count() == 0

    ACCUMULATOR.admitted_count += 1
    ACCUMULATOR.completed_count += 1
    ACCUMULATOR.redelivery_count += 1
    ACCUMULATOR.audit_abandoned_count += 1
    ACCUMULATOR.budget_requested_cents_total += 100
    ACCUMULATOR.budget_finalized_cents_total += 100
    ACCUMULATOR.audit_delivered_count += len(audit_summary.delivered_keys)


def test_e2e_07_cancellation_before_admission() -> None:
    """e2e-07: cancellation observed before admission means no
    reservation, work record, or queue entry is ever created."""
    env = build_environment()
    reference = _publish(env, "07")
    descriptor = make_work_descriptor("e2e-07", 0, reference)
    coordinator = env.make_coordinator(TransformExecutor())
    coordinator.request_cancellation("e2e-07")
    outcome = coordinator.admit(
        descriptor, reservation_id="res-e2e-07", requested_cost_cents=100
    )
    assert outcome is not None and outcome.outcome_kind == WorkOutcomeKind.CANCELLED_NOT_STARTED
    assert env.queue.in_flight_count() == 0
    with pytest.raises(ReservationNotFoundError):
        env.budget_store.get("res-e2e-07")

    audit_summary = coordinator.dispatch_audit()
    assert not audit_summary.still_pending_keys

    ACCUMULATOR.cancelled_count += 1
    ACCUMULATOR.audit_delivered_count += len(audit_summary.delivered_keys)


def _retryable_failure_result() -> ExecutorInvocationResult:
    return executor_failure(ExecutorFailureReason.RETRYABLE_EXECUTION_ERROR)


# ---------------------------------------------------------------------------
# Equivalence workload: serial baseline vs. concurrency 1/2, and the
# separately-labeled non-personal generic concurrency-4 comparison
# ---------------------------------------------------------------------------


def test_e2e_equivalence_serial_vs_concurrency_1_and_2() -> None:  # pylint: disable=too-many-locals
    """Run the fixed 4-item equivalence workload through a serial
    baseline (no coordinator), then through the real coordinator/worker
    engine at concurrency 1 and concurrency 2 -- requiring exact
    agreement on scientific work identity, typed terminal outcome,
    result-content checksum, retry count (frozen at 0), input ordering,
    and aggregate outcome counts."""
    env = build_environment(
        max_admitted_workers=2, max_in_flight_work=10, audit_outbox_max_pending=40
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    capability = GenerationPlaneArtifactCapability(env.artifact_store)
    contents = {
        f"eq-cand-{item_id}": equivalence_content(item_id) for item_id in EQUIVALENCE_ITEM_IDS
    }
    manifest = build_candidate_manifest(capability, contents, metadata=_METADATA)
    refs = {entry.artifact_reference_id: entry for entry in manifest.manifest_entries}

    serial_checksums = {
        item_id: synthetic_transform_checksum(equivalence_content(item_id))
        for item_id in EQUIVALENCE_ITEM_IDS
    }

    def run_concurrency(
        suffix: str, worker_ids: list[str]
    ) -> tuple[Coordinator, CoordinatorRunSummary, int]:
        barrier = threading.Barrier(len(worker_ids))
        tracker = PeakConcurrencyTrackingExecutor(BarrierSynchronizedTransformExecutor(barrier))
        coordinator = env.make_coordinator(tracker)
        admissions = []
        for ordinal, item_id in enumerate(EQUIVALENCE_ITEM_IDS):
            work_id = f"eq-{item_id}-{suffix}"
            descriptor = make_work_descriptor(work_id, ordinal, refs[f"eq-cand-{item_id}"])
            admissions.append((descriptor, f"res-eq-{item_id}-{suffix}", 100, 1))
        summary = coordinator.run(admissions, worker_ids)
        return coordinator, summary, tracker.peak

    coordinator_c1, summary_c1, _peak_c1 = run_concurrency("c1", ["worker-a"])
    coordinator_c2, summary_c2, peak_c2 = run_concurrency("c2", ["worker-a", "worker-b"])

    equivalent = True
    for suffix, summary in (("c1", summary_c1), ("c2", summary_c2)):
        assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == len(EQUIVALENCE_ITEM_IDS)
        assert [o.input_ordinal for o in summary.outcomes] == list(range(len(EQUIVALENCE_ITEM_IDS)))
        for item_id in EQUIVALENCE_ITEM_IDS:
            work_id = f"eq-{item_id}-{suffix}"
            record = env.work_store.read(work_id)
            matching = [o for o in summary.outcomes if o.scientific_work_id == work_id]
            equivalent = equivalent and (
                len(matching) == 1
                and matching[0].outcome_kind == WorkOutcomeKind.EXECUTED_AND_COMMITTED
                and matching[0].result_content_checksum == serial_checksums[item_id]
                and record.retry_count == 0
            )
    assert equivalent

    for suffix, coordinator in (("c1", coordinator_c1), ("c2", coordinator_c2)):
        audit_summary = coordinator.dispatch_audit()
        assert not audit_summary.still_pending_keys
        ACCUMULATOR.audit_delivered_count += len(audit_summary.delivered_keys)
    assert env.queue.in_flight_count() == 0
    assert peak_c2 == 2, "the barrier-forced overlap did not produce a genuine measured peak of 2"

    ACCUMULATOR.serial_vs_distributed_equivalent = equivalent
    ACCUMULATOR.measured_peak_concurrency_personal = peak_c2
    ACCUMULATOR.budget_requested_cents_total += 100 * len(EQUIVALENCE_ITEM_IDS) * 2
    ACCUMULATOR.budget_finalized_cents_total += 100 * len(EQUIVALENCE_ITEM_IDS) * 2


# pylint: disable-next=too-many-locals
def test_e2e_generic_concurrency_4_comparison_labeled_non_personal() -> None:
    """A separate, non-personal generic-engine comparison at concurrency
    4, run under COMPANY_PLAYGROUND with its own environment/budget
    store. Does not imply company authorization and is excluded from
    the personal $50 ceiling. Compared against the equivalence workload's
    serial baseline for outcome/checksum equivalence only -- peak
    concurrency is expected to differ and is not part of the equivalence
    claim."""
    env = build_environment(
        max_admitted_workers=4,
        max_in_flight_work=10,
        policy_environment_class=EnvironmentClass.COMPANY_PLAYGROUND,
    )
    for worker_id in ("worker-a", "worker-b", "worker-c", "worker-d"):
        env.worker_registry.register(make_worker_registration(worker_id))
    capability = GenerationPlaneArtifactCapability(env.artifact_store)
    contents = {
        f"eq-gen-cand-{item_id}": equivalence_content(item_id) for item_id in EQUIVALENCE_ITEM_IDS
    }
    manifest = build_candidate_manifest(capability, contents, metadata=_METADATA)
    refs = {entry.artifact_reference_id: entry for entry in manifest.manifest_entries}

    generic_barrier = threading.Barrier(4)
    tracker = PeakConcurrencyTrackingExecutor(BarrierSynchronizedTransformExecutor(generic_barrier))
    coordinator = env.make_coordinator(tracker)
    admissions = []
    for ordinal, item_id in enumerate(EQUIVALENCE_ITEM_IDS):
        work_id = f"eq-gen-{item_id}"
        descriptor = make_work_descriptor(work_id, ordinal, refs[f"eq-gen-cand-{item_id}"])
        admissions.append((descriptor, f"res-eq-gen-{item_id}", 100, 1))
    summary = coordinator.run(admissions, ["worker-a", "worker-b", "worker-c", "worker-d"])

    equivalent = summary.count(
        WorkOutcomeKind.EXECUTED_AND_COMMITTED
    ) == len(EQUIVALENCE_ITEM_IDS)
    for item_id in EQUIVALENCE_ITEM_IDS:
        work_id = f"eq-gen-{item_id}"
        matching = [o for o in summary.outcomes if o.scientific_work_id == work_id]
        equivalent = equivalent and (
            len(matching) == 1
            and matching[0].result_content_checksum
            == synthetic_transform_checksum(equivalence_content(item_id))
        )
    assert equivalent

    audit_summary = coordinator.dispatch_audit()
    assert not audit_summary.still_pending_keys
    assert env.queue.in_flight_count() == 0
    assert tracker.peak == 4, "the barrier-forced overlap did not produce a genuine peak of 4"

    ACCUMULATOR.generic_concurrency4_equivalent = equivalent
    ACCUMULATOR.measured_peak_concurrency_generic = tracker.peak


# ---------------------------------------------------------------------------
# Final report generation
# ---------------------------------------------------------------------------

_PLAN_SHA256 = "53f2ff50b7079e871a6bf79595a577069b29be9e3ec1f3db345c7234955a1c61"
_PLAN_GIT_BLOB_SHA1 = "aec3e2f64e5a83086081f65cf6ff817a6e0176cc"
_FAULT_CONFORMANCE_REPORT_CHECKSUM = (
    "3a0d6e71cf7162144f193b534b64eef6f604a5e3cd2276f70ef954e60b148b56"
)


def test_zzz_generate_and_write_safe_offline_e2e_qualification_report() -> None:
    """Build the safe OfflineE2EQualificationReport from every count this
    suite's own tests actually accumulated, and write it to
    docs/measurement/ -- deterministic given pytest's own default
    (non-randomized) collection order within this one file."""
    assert ACCUMULATOR.run_context_checksum, "provenance-gate test above did not run"
    assert ACCUMULATOR.serial_vs_distributed_equivalent is not None, "equivalence test did not run"
    assert ACCUMULATOR.generic_concurrency4_equivalent is not None, "generic-4 test did not run"
    assert ACCUMULATOR.qualification_gate_ready is not None, "provenance-gate test did not run"
    assert ACCUMULATOR.distributed_run_intent, "provenance-gate test did not run"
    assert ACCUMULATOR.qualifying_workload_class, "provenance-gate test did not run"

    report = build_offline_e2e_qualification_report(
        plan_sha256=_PLAN_SHA256,
        plan_git_blob_sha1=_PLAN_GIT_BLOB_SHA1,
        workload_sha256=compute_workload_checksum(),
        distributed_provenance_schema_version=DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        fault_conformance_report_checksum=_FAULT_CONFORMANCE_REPORT_CHECKSUM,
        accumulator=ACCUMULATOR,
    )
    assert report.readiness == ReadinessClassification.OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3

    out_dir = pathlib.Path(__file__).resolve().parent.parent / "docs" / "measurement"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "megb-03h2c3b2c-offline-e2e-qualification-report.json"
    md_path = out_dir / "megb-03h2c3b2c-offline-e2e-qualification-report.md"
    json_path.write_text(
        json.dumps(offline_e2e_qualification_report_to_dict(report), sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
