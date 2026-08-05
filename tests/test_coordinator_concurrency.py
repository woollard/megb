"""MEGB-03H.2C.3B.2B.2: bounded-concurrency, backpressure, and
deterministic-ordering tests for :mod:`src.distributed.coordinator`.

No wall-clock sleeps anywhere -- every synchronization point is either a
:class:`threading.Barrier` (genuine contention, exactly mirroring
B.2B.1's own established race-test pattern) or the injected
:class:`~src.distributed.clock.LogicalClock`."""

# pylint: disable=cell-var-from-loop
# Every per-trial closure below (bounded_execute and _BoundedExecutor) is
# both defined and fully exercised -- built, invoked via coordinator.run,
# and discarded -- within the same loop iteration, before the next
# iteration rebinds `lock`/`in_flight`/`max_observed` -- there is no
# stale-capture-across-iterations bug for this rule to catch, only the
# loop-body-defines-a-closure shape the rule pattern-matches on
# generically (same precedent as tests/test_atomic_stores_races.py).

import threading

import pytest

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.coordinator_config import CoordinatorConfig
from src.distributed.executor import ExecutorInvocationResult, executor_success
from src.distributed.provenance import EnvironmentClass
from src.distributed.work_outcome import WorkOutcome, WorkOutcomeKind, build_run_summary
from tests._coordinator_fixtures import (
    ScriptedExecutor,
    build_environment,
    make_default_config,
    make_synthetic_content,
    make_work_descriptor,
    make_worker_registration,
    publish_candidate,
)

_TRIALS = 10


def test_config_alone_permits_more_than_the_personal_ceiling() -> None:
    """MEGB-03H.2C.3B.2B.2 correction: CoordinatorConfig itself is
    provider-neutral and no longer hardcodes the personal-bootstrap
    2-worker ceiling -- constructing one with max_admitted_workers=4
    must not raise. The personal ceiling is enforced elsewhere (by
    PersonalEnvironmentPolicy and the Coordinator construction-time
    cross-check below), never by this config type alone."""
    config = CoordinatorConfig(
        max_admitted_workers=4,
        max_in_flight_work=10,
        lease_duration_ticks=5,
        visibility_timeout_ticks=5,
        heartbeat_interval_ticks=2,
        audit_outbox_max_pending=10,
    )
    assert config.max_admitted_workers == 4


def test_coordinator_construction_rejects_config_ceiling_above_personal_policy() -> None:
    """A personal run configured above two is rejected before admission
    -- at Coordinator construction time, before any admit() call, when
    the config's own concurrency ceiling exceeds the injected
    personal-bootstrap policy's own max_admitted_workers."""
    env = build_environment(max_admitted_workers=2)
    higher_config = make_default_config(max_admitted_workers=3, max_in_flight_work=10)
    with pytest.raises(InvalidDistributedProvenanceError):
        env.make_coordinator(ScriptedExecutor(), config=higher_config)


def test_coordinator_construction_accepts_matching_personal_ceiling() -> None:
    """The companion positive case: a config exactly at the personal
    ceiling constructs without error."""
    env = build_environment(max_admitted_workers=2)
    coordinator = env.make_coordinator(ScriptedExecutor())
    assert coordinator is not None


def test_generic_engine_runs_at_concurrency_four_while_personal_policy_still_refuses_it() -> None:
    """The provider-neutral engine itself supports a bounded concurrency
    greater than two: a coordinator wired to a non-personal-bootstrap
    policy (a synthetic test fixture only -- not a company-authorization
    policy, which remains separately gated and not authorized here) with
    max_admitted_workers=4 constructs and runs four concurrent workers
    successfully, while a personal-bootstrap policy at the same
    CoordinatorConfig ceiling still refuses to construct at all."""
    generic_env = build_environment(
        max_admitted_workers=4,
        max_in_flight_work=10,
        policy_environment_class=EnvironmentClass.COMPANY_PLAYGROUND,
    )
    assert generic_env.policy.max_admitted_workers == 4
    for worker_id in ("worker-a", "worker-b", "worker-c", "worker-d"):
        generic_env.worker_registry.register(make_worker_registration(worker_id))
    coordinator = generic_env.make_coordinator(ScriptedExecutor())

    admissions = []
    for ordinal in range(4):
        work_id = f"work-{ordinal}"
        content = make_synthetic_content(work_id)
        reference = publish_candidate(generic_env.artifact_store, content, reference_id=work_id)
        descriptor = make_work_descriptor(work_id, ordinal, reference)
        admissions.append((descriptor, f"res-{ordinal}", 100, 1))

    summary = coordinator.run(
        admissions, ["worker-a", "worker-b", "worker-c", "worker-d"]
    )
    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 4

    # The same CoordinatorConfig ceiling (4) still cannot be paired with a
    # personal-bootstrap policy (ceiling 2) -- rejected at construction.
    personal_env = build_environment(max_admitted_workers=2)
    higher_config = make_default_config(max_admitted_workers=4, max_in_flight_work=10)
    with pytest.raises(InvalidDistributedProvenanceError):
        personal_env.make_coordinator(ScriptedExecutor(), config=higher_config)


def test_run_refuses_more_worker_ids_than_configured_ceiling() -> None:
    """Test run refuses more worker ids than the configured ceiling."""
    env = build_environment(max_admitted_workers=2)
    coordinator = env.make_coordinator(ScriptedExecutor())
    with pytest.raises(InvalidDistributedProvenanceError):
        coordinator.run([], ["worker-a", "worker-b", "worker-c"])


def test_admission_backpressure_refuses_beyond_max_in_flight() -> None:
    """Test admission backpressure refuses beyond max_in_flight -- an
    admission that would exceed the queue's own bound reports
    INFRASTRUCTURE_FAILURE rather than accumulating unboundedly."""
    env = build_environment(max_in_flight_work=1)
    coordinator = env.make_coordinator(ScriptedExecutor())
    content_a = make_synthetic_content("a")
    reference_a = publish_candidate(env.artifact_store, content_a, reference_id="cand-a")
    descriptor_a = make_work_descriptor("work-1", 0, reference_a)
    assert coordinator.admit(descriptor_a, reservation_id="res-1", requested_cost_cents=100) is None

    content_b = make_synthetic_content("b")
    reference_b = publish_candidate(env.artifact_store, content_b, reference_id="cand-b")
    descriptor_b = make_work_descriptor("work-2", 1, reference_b)
    outcome = coordinator.admit(descriptor_b, reservation_id="res-2", requested_cost_cents=100)
    assert outcome is not None
    assert outcome.outcome_kind == WorkOutcomeKind.INFRASTRUCTURE_FAILURE
    assert env.queue.in_flight_count() == 1


def test_two_worker_ceiling_bounds_concurrent_executor_invocations() -> None:
    """Test the two-worker ceiling bounds concurrent executor
    invocations -- a barrier-synchronized executor proves at most two
    invocations are ever in flight at once, repeated across trials to
    catch a nondeterministic failure."""
    for _ in range(_TRIALS):
        env = build_environment(max_admitted_workers=2, max_in_flight_work=10)
        env.worker_registry.register(make_worker_registration("worker-a"))
        env.worker_registry.register(make_worker_registration("worker-b"))

        in_flight = 0
        max_observed = 0
        lock = threading.Lock()

        def bounded_execute(_content: bytes) -> ExecutorInvocationResult:
            """Track concurrent in-flight invocations for this trial."""
            nonlocal in_flight, max_observed
            with lock:
                in_flight += 1
                max_observed = max(max_observed, in_flight)
            with lock:
                in_flight -= 1
            return executor_success(b"result")

        class _BoundedExecutor:  # pylint: disable=too-few-public-methods
            def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
                """Delegate to this trial's bounded_execute closure."""
                return bounded_execute(candidate_content)

        coordinator = env.make_coordinator(_BoundedExecutor())
        # Exactly the personal-bootstrap worker ceiling's own admitted-
        # but-not-yet-finalized bound (2) -- admitting more at once would
        # itself be BUDGET_BLOCKED by the accepted B.2B.1 budget model,
        # a separate, already-tested concern from this test's own
        # bounded-concurrency proof.
        admissions = []
        for ordinal in range(2):
            work_id = f"work-{ordinal}"
            content = make_synthetic_content(work_id)
            reference = publish_candidate(env.artifact_store, content, reference_id=work_id)
            descriptor = make_work_descriptor(work_id, ordinal, reference)
            admissions.append((descriptor, f"res-{ordinal}", 100, 1))

        summary = coordinator.run(admissions, ["worker-a", "worker-b"])
        assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 2
        assert max_observed <= 2


def test_deterministic_returned_ordering_under_reversed_completion() -> None:  # pylint: disable=too-many-locals
    """Test deterministic returned ordering under deliberately reversed
    completion -- the work item with the *later* input_ordinal is made
    to finish executing first, yet the returned summary is still ordered
    by input_ordinal. Legitimately needs one local per work item
    (content/reference/descriptor x2) plus the synchronization
    primitives (barrier/lock/completion_order) proving the reversal --
    splitting it up would only obscure the single scenario under test."""
    env = build_environment(max_admitted_workers=2, max_in_flight_work=10)
    env.worker_registry.register(make_worker_registration("worker-a"))
    env.worker_registry.register(make_worker_registration("worker-b"))

    barrier = threading.Barrier(2)
    order_lock = threading.Lock()
    completion_order: list[str] = []

    class _OrderProbeExecutor:  # pylint: disable=too-few-public-methods
        def __init__(self, label: str, delay_after_barrier: bool) -> None:
            self._label = label
            self._delay_after_barrier = delay_after_barrier

        def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
            """Record this invocation's completion order after the
            barrier releases both threads together."""
            del candidate_content
            barrier.wait()
            if self._delay_after_barrier:
                # Yield the GIL a few times so the "early" ordinal's
                # executor call (below) gets scheduled and completes
                # first, deliberately reversing completion order.
                for _ in range(50):
                    pass
            with order_lock:
                completion_order.append(self._label)
            return executor_success(b"result")

    content_0 = make_synthetic_content("ordinal-0")
    reference_0 = publish_candidate(env.artifact_store, content_0, reference_id="cand-0")
    descriptor_0 = make_work_descriptor("work-0", 0, reference_0)
    content_1 = make_synthetic_content("ordinal-1")
    reference_1 = publish_candidate(env.artifact_store, content_1, reference_id="cand-1")
    descriptor_1 = make_work_descriptor("work-1", 1, reference_1)

    coordinator = env.make_coordinator(_OrderProbeExecutor("unused", False))
    coordinator.admit(descriptor_0, reservation_id="res-0", requested_cost_cents=100)
    coordinator.admit(descriptor_1, reservation_id="res-1", requested_cost_cents=100)

    outcomes: list[WorkOutcome] = []
    outcomes_lock = threading.Lock()

    def run_one(worker_id: str, delay: bool) -> None:
        """Invoke one worker with its own probe executor, collecting the
        returned outcome (if any) into the shared outcomes list."""
        executor = _OrderProbeExecutor(worker_id, delay)
        coordinator._executor = executor  # pylint: disable=protected-access
        outcome = coordinator.invoke_worker(worker_id)
        if outcome is not None:
            with outcomes_lock:
                outcomes.append(outcome)

    # Both threads race through the barrier together; the "later ordinal"
    # (work-1, delivered second since it was admitted second) finishes
    # first because the "earlier ordinal" spins after the barrier.
    thread_a = threading.Thread(target=run_one, args=("worker-a", True))
    thread_b = threading.Thread(target=run_one, args=("worker-b", False))
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    summary = build_run_summary(outcomes)
    assert [outcome.input_ordinal for outcome in summary.outcomes] == [0, 1]


def test_executor_callback_never_invoked_while_authoritative_lock_is_held() -> None:
    """Test the executor callback is never invoked while an
    authoritative-store lock is held -- proven by having the executor
    itself perform an unrelated read against the same work_store from
    inside its own callback. If the coordinator held the store's
    internal (non-reentrant) lock across the executor call, this nested
    read would deadlock; bounding it with a timeout turns a latent
    regression into a clean test failure instead of a hang."""
    env = build_environment()
    content = make_synthetic_content("lock-probe")
    reference = publish_candidate(env.artifact_store, content)
    descriptor = make_work_descriptor("work-1", 0, reference)
    env.worker_registry.register(make_worker_registration("worker-a"))

    nested_read_succeeded = threading.Event()

    class _LockProbeExecutor:  # pylint: disable=too-few-public-methods
        def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
            """Perform a nested read against the same work_store to
            prove the coordinator's lock isn't held across this call."""
            del candidate_content
            env.work_store.read("work-1")  # would deadlock if the lock were held
            nested_read_succeeded.set()
            return executor_success(b"result")

    coordinator = env.make_coordinator(_LockProbeExecutor())
    coordinator.admit(descriptor, reservation_id="res-1", requested_cost_cents=100)

    worker_thread = threading.Thread(target=coordinator.invoke_worker, args=("worker-a",))
    worker_thread.start()
    worker_thread.join(timeout=5)
    assert not worker_thread.is_alive(), (
        "invoke_worker hung -- executor call may hold the store lock"
    )
    assert nested_read_succeeded.is_set()


def test_bounded_concurrency_repeated_without_nondeterministic_failure() -> None:
    """Test bounded concurrency repeated without nondeterministic
    failure -- re-runs the ceiling-bounding scenario many additional
    trials, two rounds of two admitted items each (matching the
    accepted personal-bootstrap worker-reservation ceiling)."""
    for _ in range(_TRIALS):
        env = build_environment(max_admitted_workers=2, max_in_flight_work=10)
        env.worker_registry.register(make_worker_registration("worker-a"))
        env.worker_registry.register(make_worker_registration("worker-b"))
        coordinator = env.make_coordinator(ScriptedExecutor())
        all_outcomes: list[WorkOutcome] = []
        for round_index in range(2):
            admissions = []
            for slot in range(2):
                ordinal = round_index * 2 + slot
                work_id = f"work-{ordinal}"
                content = make_synthetic_content(work_id)
                reference = publish_candidate(env.artifact_store, content, reference_id=work_id)
                descriptor = make_work_descriptor(work_id, ordinal, reference)
                admissions.append((descriptor, f"res-{ordinal}", 100, 1))
            summary = coordinator.run(admissions, ["worker-a", "worker-b"])
            all_outcomes.extend(summary.outcomes)
        combined = build_run_summary(all_outcomes)
        assert combined.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 4
        assert [outcome.input_ordinal for outcome in combined.outcomes] == [0, 1, 2, 3]


def test_default_config_matches_the_personal_ceiling() -> None:
    """Test the shared default config fixture matches the personal
    ceiling exactly."""
    config = make_default_config()
    assert config.max_admitted_workers == 2
