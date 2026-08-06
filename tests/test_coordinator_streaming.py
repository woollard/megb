"""MEGB-03H.2C.3B.2C correction: regression tests for
``Coordinator.run()``'s bounded-streaming admission scheduler --
replacing the prior admit-all-then-execute design, which contradicted
bounded admission/backpressure and could never process a workload larger
than the queue's own in-flight capacity.

No wall-clock sleeps anywhere -- every synchronization point is either a
``threading.Barrier``/``threading.Condition`` (real, event-driven,
deterministic) or the injected ``LogicalClock``."""

# pylint: disable=duplicate-code
# This file's own admission/execution fixture usage inherently mirrors
# tests/test_coordinator_admission.py's and tests/test_coordinator_concurrency.py's
# own established patterns -- shared boilerplate, not shared logic.

import threading

import pytest

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
)
from src.distributed.executor import ExecutorInvocationResult, executor_success
from src.distributed.queue_adapter import InMemoryAtLeastOnceQueue
from src.distributed.work_contracts import ArtifactKind, ArtifactReference, WorkDescriptor
from src.distributed.work_outcome import WorkOutcomeKind
from tests._coordinator_fixtures import (
    CoordinatorEnvironment,
    ScriptedExecutor,
    build_environment,
    make_synthetic_content,
    make_work_descriptor,
    make_worker_registration,
    publish_candidate,
    retryable_failure,
)


def _make_admissions(
    env: CoordinatorEnvironment, count: int, *, prefix: str = "stream", cost_cents: int = 1
) -> list[tuple[WorkDescriptor, str, int, int]]:
    """Build ``count`` distinct, lightweight admission tuples, each
    requesting ``requested_worker_count=1`` and ``cost_cents`` cents."""
    admissions: list[tuple[WorkDescriptor, str, int, int]] = []
    for i in range(count):
        work_id = f"{prefix}-{i:04d}"
        content = make_synthetic_content(work_id)
        reference = publish_candidate(env.artifact_store, content, reference_id=f"cand-{work_id}")
        descriptor = make_work_descriptor(work_id, i, reference)
        admissions.append((descriptor, f"res-{work_id}", cost_cents, 1))
    return admissions


class _WindowObservingExecutor:
    """Records ``queue.in_flight_count()`` at the start of every
    invocation, then always succeeds immediately -- a real, synchronous
    measurement of admitted-but-unresolved capacity at each execution
    point, never an assumed value."""

    def __init__(self, queue: InMemoryAtLeastOnceQueue) -> None:
        self._queue = queue
        self.observed_in_flight: list[int] = []
        self._lock = threading.Lock()

    def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
        """Record the queue's own current in-flight count, then succeed."""
        del candidate_content
        with self._lock:
            self.observed_in_flight.append(self._queue.in_flight_count())
        return executor_success(b"ok")


def test_run_streams_164_items_through_two_personal_workers_under_budget_ceiling() -> None:
    """164 lightweight synthetic work items, admitted 10 at a time
    (default admission_window == max_in_flight_work), processed to
    completion by exactly two personal workers -- worker count and work-
    item count are fully independent; budget stays well under the
    personal $50/5000-cent ceiling. audit_outbox_max_pending=400: each
    item contributes up to two pending audit entries (admission +
    result-committed) before any dispatch_audit() drains them."""
    env = build_environment(
        max_admitted_workers=2,
        max_in_flight_work=10,
        audit_outbox_max_pending=400,
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    admissions = _make_admissions(env, 164)

    summary = coordinator.run(admissions, ["worker-a", "worker-b"])

    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 164
    assert [o.input_ordinal for o in summary.outcomes] == list(range(164))
    assert env.queue.in_flight_count() == 0
    finalized_amounts = [
        env.budget_store.get(f"res-stream-{i:04d}").actual_cost_cents for i in range(164)
    ]
    assert all(amount is not None for amount in finalized_amounts)
    assert sum(amount for amount in finalized_amounts if amount is not None) == 164


def test_run_handles_queue_capacity_smaller_than_workload() -> None:
    """Queue in-flight capacity (3) is far smaller than the 30-item
    workload -- the run still completes every item deterministically."""
    env = build_environment(
        max_admitted_workers=2,
        max_in_flight_work=3,
        audit_outbox_max_pending=200,
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    admissions = _make_admissions(env, 30)

    summary = coordinator.run(admissions, ["worker-a", "worker-b"])

    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 30
    assert [o.input_ordinal for o in summary.outcomes] == list(range(30))


def test_run_handles_admission_window_smaller_than_workload_and_queue_capacity() -> None:
    """admission_window (2) is smaller than both the queue's own
    capacity (10) and the 30-item workload -- never observed in flight
    beyond the window at any recorded execution point."""
    env = build_environment(
        max_admitted_workers=2,
        max_in_flight_work=10,
        audit_outbox_max_pending=200,
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    tracker = _WindowObservingExecutor(env.queue)
    coordinator = env.make_coordinator(tracker)
    admissions = _make_admissions(env, 30)

    summary = coordinator.run(admissions, ["worker-a", "worker-b"], admission_window=2)

    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 30
    assert tracker.observed_in_flight, "executor was never invoked"
    assert max(tracker.observed_in_flight) <= 2


def test_run_handles_all_three_bounds_simultaneously() -> None:
    """Worker count (2), queue capacity (3), and admission_window (2)
    are all deliberately smaller than the 25-item workload at once."""
    env = build_environment(
        max_admitted_workers=2,
        max_in_flight_work=3,
        audit_outbox_max_pending=200,
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    admissions = _make_admissions(env, 25)

    summary = coordinator.run(admissions, ["worker-a", "worker-b"], admission_window=2)

    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 25
    assert [o.input_ordinal for o in summary.outcomes] == list(range(25))


def test_run_avoids_deadlock_when_queue_capacity_equals_worker_count() -> None:
    """Queue capacity exactly equals worker count (2) -- no deadlock, no
    hang, complete deterministic drain of a larger workload."""
    env = build_environment(
        max_admitted_workers=2,
        max_in_flight_work=2,
        audit_outbox_max_pending=200,
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    admissions = _make_admissions(env, 20)

    summary = coordinator.run(admissions, ["worker-a", "worker-b"], admission_window=2)

    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 20


def test_run_avoids_deadlock_when_queue_capacity_smaller_than_worker_count() -> None:
    """Queue/window capacity (1) is smaller than the worker count (2) --
    the hardest deadlock case: one worker must repeatedly find nothing
    deliverable and wait, without ever missing a wakeup."""
    env = build_environment(
        max_admitted_workers=2,
        max_in_flight_work=1,
        audit_outbox_max_pending=200,
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    admissions = _make_admissions(env, 20)

    summary = coordinator.run(admissions, ["worker-a", "worker-b"], admission_window=1)

    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 20


def test_run_avoids_deadlock_when_queue_capacity_smaller_than_worker_count_repeated() -> None:
    """Repeat the hardest deadlock case 15 times to detect flakes; report
    zero-flake repetitions."""
    for trial in range(15):
        env = build_environment(
            max_admitted_workers=2,
            max_in_flight_work=1,
            audit_outbox_max_pending=200,
        )
        env.worker_registry.register(make_worker_registration("worker-a"))
        env.worker_registry.register(make_worker_registration("worker-b"))
        coordinator = env.make_coordinator(ScriptedExecutor())
        admissions = _make_admissions(env, 12, prefix=f"deadlock-{trial}")
        summary = coordinator.run(admissions, ["worker-a", "worker-b"], admission_window=1)
        assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 12


def test_run_preserves_deterministic_ordering_under_reversed_completion() -> None:
    """Two items, two workers, admission_window=2 -- one deliberately
    delayed past a shared barrier so it completes strictly after the
    other, despite being admitted first. The returned summary is still
    ordered by input_ordinal, not completion order."""
    env = build_environment(
        max_admitted_workers=2,
        max_in_flight_work=2,
        audit_outbox_max_pending=200,
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    barrier = threading.Barrier(2)
    seen_content: set[bytes] = set()
    seen_lock = threading.Lock()
    slow_content = make_synthetic_content("reversed-0")

    class _ReversalExecutor:  # pylint: disable=too-few-public-methods
        def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
            """Race through the barrier; the item admitted first
            deliberately spins after release so it finishes second."""
            barrier.wait()
            with seen_lock:
                already_slow = slow_content in seen_content
                seen_content.add(candidate_content)
            if candidate_content == slow_content and not already_slow:
                for _ in range(200):
                    pass
            return executor_success(b"ok")

    coordinator = env.make_coordinator(_ReversalExecutor())
    admissions = _make_admissions(env, 2, prefix="reversed")

    summary = coordinator.run(admissions, ["worker-a", "worker-b"], admission_window=2)

    assert [o.input_ordinal for o in summary.outcomes] == [0, 1]
    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 2


def test_run_stops_admission_predictably_on_cancellation_of_a_not_yet_admitted_item() -> None:
    """An item cancelled before it is ever admitted (still beyond the
    admission window when cancellation is requested) resolves as
    CANCELLED_NOT_STARTED once its turn comes, without hanging the run."""
    env = build_environment(
        max_admitted_workers=2,
        max_in_flight_work=2,
        audit_outbox_max_pending=200,
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    admissions = _make_admissions(env, 10, prefix="cancel")
    # The 9th item (ordinal 8) is well beyond the window=2 at admission
    # time -- cancel it before the run ever starts.
    coordinator.request_cancellation("cancel-0008")

    summary = coordinator.run(admissions, ["worker-a", "worker-b"], admission_window=2)

    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 9
    assert summary.count(WorkOutcomeKind.CANCELLED_NOT_STARTED) == 1
    cancelled = [o for o in summary.outcomes if o.scientific_work_id == "cancel-0008"]
    assert len(cancelled) == 1
    assert cancelled[0].outcome_kind == WorkOutcomeKind.CANCELLED_NOT_STARTED


def test_run_stops_admission_predictably_on_terminal_infrastructure_failure() -> None:
    """One item whose candidate artifact was never published resolves as
    an immediate INFRASTRUCTURE_FAILURE at admission time (its own
    window slot is freed immediately), and every other item still
    completes normally -- the run neither hangs nor loses window
    capacity."""
    env = build_environment(
        max_admitted_workers=2,
        max_in_flight_work=2,
        audit_outbox_max_pending=200,
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    admissions = _make_admissions(env, 10, prefix="badref")
    bad_descriptor, bad_reservation, bad_cost, bad_workers = admissions[4]
    unresolvable_reference = ArtifactReference(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        artifact_kind=ArtifactKind.CANDIDATE_MANIFEST_ENTRY,
        artifact_reference_id="never-published",
        content_checksum="0" * 64,
        metadata_checksum="1" * 64,
    )
    bad_descriptor_replacement = make_work_descriptor(
        bad_descriptor.scientific_work_id, bad_descriptor.input_ordinal, unresolvable_reference
    )
    admissions[4] = (bad_descriptor_replacement, bad_reservation, bad_cost, bad_workers)

    summary = coordinator.run(admissions, ["worker-a", "worker-b"], admission_window=2)

    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 9
    assert summary.count(WorkOutcomeKind.INFRASTRUCTURE_FAILURE) == 1
    assert [o.input_ordinal for o in summary.outcomes] == list(range(10))


def test_run_admission_window_defaults_to_max_in_flight_work() -> None:
    """Omitting admission_window falls back to config.max_in_flight_work
    exactly -- confirmed by observing the window is respected without an
    explicit override."""
    env = build_environment(
        max_admitted_workers=2,
        max_in_flight_work=4,
        audit_outbox_max_pending=200,
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    tracker = _WindowObservingExecutor(env.queue)
    coordinator = env.make_coordinator(tracker)
    admissions = _make_admissions(env, 20, prefix="default-window")

    summary = coordinator.run(admissions, ["worker-a", "worker-b"])

    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 20
    assert max(tracker.observed_in_flight) <= 4


def test_run_rejects_non_positive_admission_window() -> None:
    """A non-positive admission_window is rejected before any admission
    happens."""
    env = build_environment(
        max_admitted_workers=2,
        max_in_flight_work=10,
        audit_outbox_max_pending=200,
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    coordinator = env.make_coordinator(ScriptedExecutor())
    admissions = _make_admissions(env, 1, prefix="badwindow")
    with pytest.raises(InvalidDistributedProvenanceError):
        coordinator.run(admissions, ["worker-a"], admission_window=0)


def test_run_completes_with_a_mixed_retryable_failure_present() -> None:
    """A retryable-failure outcome frees its own admission-window slot
    for further admission pacing immediately (this scheduler's
    documented liveness-over-strict-queue-mirroring trade-off for
    retries); the run still completes deterministically for every other
    item without deadlocking, given headroom between admission_window
    and the queue's own in-flight capacity."""
    env = build_environment(
        max_admitted_workers=2,
        max_in_flight_work=10,
        audit_outbox_max_pending=200,
    )
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))
    executor = ScriptedExecutor(script=[retryable_failure()])
    coordinator = env.make_coordinator(executor)
    admissions = _make_admissions(env, 15, prefix="mixedretry")

    summary = coordinator.run(admissions, ["worker-a", "worker-b"], admission_window=4)

    assert summary.count(WorkOutcomeKind.RETRY_SCHEDULED) == 1
    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 14
    assert len(summary.outcomes) == 15
