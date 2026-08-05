"""MEGB-03H.2C.3B.2B.1: deterministic concurrency/race tests proving the
atomic stores' own compare-and-swap guarantees hold under real thread
contention -- no wall-clock sleeps anywhere; every synchronization point
is a :class:`threading.Barrier` (blocks until all parties arrive, then
releases them together) so the race is genuinely contended rather than
merely sequential-with-a-delay. Each race is repeated many trials
(``_TRIALS``) to catch a nondeterministic failure that a single run could
miss, since which thread wins any individual trial is not itself
required to be deterministic -- only the *invariant* (exactly one legal
winner, no corruption, no silent double-apply) must hold on every trial."""

# pylint: disable=cell-var-from-loop
# Every per-trial closure below is both started and joined (via
# _run_concurrently, which starts then immediately joins every thread)
# within the same loop iteration, before the next iteration rebinds any
# of these variables -- there is no stale-capture-across-iterations bug
# for this rule to catch, only the loop-body-defines-a-closure shape the
# rule pattern-matches on generically.
# pylint: disable=too-many-locals
# Each race scenario legitimately needs its own store/lease/attempt/
# commit/artifact-store/barrier/lock/outcomes setup per trial -- no
# extraction would reduce this without splitting one coherent race
# scenario across multiple functions purely to satisfy a line count.

import threading
from typing import Callable

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION as C,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION as V,
)
from src.distributed.artifact_store import ArtifactMetadata, InMemoryArtifactStore
from src.distributed.atomic_work_store import (
    AtomicWorkStore,
    IdentityMismatchError,
    RevisionConflictError,
)
from src.distributed.budget_store import AtomicBudgetStore, BudgetCeilingExceededError
from src.distributed.personal_policy import DataClassification, WorkloadClass
from src.distributed.state_machine import WorkItemState
from src.distributed.work_contracts import (
    CancellationRequest,
    CancellationScope,
    ExecutionAttempt,
    ResultCommit,
)
from src.distributed.worker_contracts import StaleLeaseGenerationError
from tests._atomic_stores_fixtures import make_result_commit, make_synthetic_content
from tests._distributed_orchestration_fixtures import (
    make_execution_attempt,
    make_lease,
    make_sha256,
)

RUN_CTX = make_sha256("synthetic-run-context")
RESERVATION_ID = "reservation-0001"
_TRIALS = 25


def _always_valid_reservation(_reservation_id: str) -> bool:
    return True


def _run_concurrently(*targets: Callable[[], None]) -> None:
    threads = [threading.Thread(target=target) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_two_workers_racing_for_one_lease_yields_exactly_one_valid_lease() -> None:
    """Test two workers racing for one lease yields exactly one valid
    lease -- the loser is always cleanly rejected, never partially
    applied."""
    for trial in range(_TRIALS):
        work_id = f"work-lease-race-{trial}"
        store = AtomicWorkStore()
        record = store.create_if_absent(work_id, RUN_CTX, RESERVATION_ID, _always_valid_reservation)
        barrier = threading.Barrier(2)
        outcomes: list[tuple[str, str]] = []
        lock = threading.Lock()

        def attempt(worker_id: str) -> None:
            lease = make_lease(
                scientific_work_id=work_id, worker_participant_id=worker_id, lease_generation=1
            )
            barrier.wait()
            status: str
            try:
                store.acquire_lease(
                    work_id,
                    record.revision,
                    lease,
                    reservation_validator=_always_valid_reservation,
                )
                status = "success"
            except RevisionConflictError:
                status = "conflict"
            with lock:
                outcomes.append((worker_id, status))

        _run_concurrently(
            lambda: attempt("worker-a"),
            lambda: attempt("worker-b"),
        )

        successes = [entry for entry in outcomes if entry[1] == "success"]
        conflicts = [entry for entry in outcomes if entry[1] == "conflict"]
        assert len(successes) == 1, f"trial {trial}: expected exactly one winner, got {outcomes!r}"
        assert len(conflicts) == 1
        final = store.read(work_id)
        assert final.state == WorkItemState.LEASED
        assert final.worker_participant_id == successes[0][0]
        assert final.revision == 1


def test_stale_worker_never_commits_despite_racing_against_the_reassigned_worker() -> None:
    """Test that under real thread contention, a worker whose lease was
    reassigned away can never commit -- regardless of which thread's
    call happens to acquire the store's internal lock first, the fencing
    check (fixed generation values, independent of scheduling order)
    always rejects the stale attempt and always admits the current one."""
    for trial in range(_TRIALS):
        work_id = f"work-stale-race-{trial}"
        store = AtomicWorkStore()
        record = store.create_if_absent(
            work_id, RUN_CTX, RESERVATION_ID, _always_valid_reservation
        )
        lease1 = make_lease(
            scientific_work_id=work_id, worker_participant_id="worker-a", lease_generation=1
        )
        record = store.acquire_lease(
            work_id, record.revision, lease1, reservation_validator=_always_valid_reservation
        )
        record = store.mark_retryable(work_id, record.revision)
        lease2 = make_lease(
            scientific_work_id=work_id, worker_participant_id="worker-b", lease_generation=2
        )
        record = store.reassign_lease(
            work_id, record.revision, lease2, reservation_validator=_always_valid_reservation
        )
        record = store.transition_to_executing(work_id, record.revision)

        stale_attempt = make_execution_attempt(
            scientific_work_id=work_id, worker_participant_id="worker-a", lease_generation=1
        )
        current_attempt = make_execution_attempt(
            scientific_work_id=work_id, worker_participant_id="worker-b", lease_generation=2
        )
        stale_content = make_synthetic_content(f"stale-{trial}")
        current_content = make_synthetic_content(f"current-{trial}")
        stale_commit = make_result_commit(stale_attempt, stale_content)
        current_commit = make_result_commit(current_attempt, current_content)

        astore = InMemoryArtifactStore()
        metadata = ArtifactMetadata(
            workload_class=WorkloadClass.SYNTHETIC_SMOKE,
            data_classification=DataClassification.SYNTHETIC,
        )
        astore.put(stale_commit.result_artifact_reference, stale_content, metadata)
        astore.put(current_commit.result_artifact_reference, current_content, metadata)

        barrier = threading.Barrier(2)
        outcomes: list[tuple[str, str]] = []
        lock = threading.Lock()

        def attempt_commit(label: str, attempt: ExecutionAttempt, commit: ResultCommit) -> None:
            barrier.wait()
            try:
                store.commit_result(work_id, record.revision, attempt, commit, astore.resolve)
                outcome = "success"
            except (IdentityMismatchError, StaleLeaseGenerationError, RevisionConflictError):
                outcome = "rejected"
            with lock:
                outcomes.append((label, outcome))

        _run_concurrently(
            lambda: attempt_commit("stale", stale_attempt, stale_commit),
            lambda: attempt_commit("current", current_attempt, current_commit),
        )

        outcome_by_label = dict(outcomes)
        assert outcome_by_label["stale"] == "rejected", (
            f"trial {trial}: stale worker must never commit"
        )
        assert outcome_by_label["current"] == "success", (
            f"trial {trial}: current worker must commit"
        )
        final = store.read(work_id)
        assert final.result_commit == current_commit


def test_losing_competing_artifact_remains_unreferenced_after_cas_race() -> None:
    """Test that when two already-durably-written competing result
    artifacts race to be committed, exactly one wins the CAS and the
    loser's artifact remains present in the artifact store but never
    referenced by the authoritative record -- an orphaned, harmless,
    immutable artifact."""
    for trial in range(_TRIALS):
        work_id = f"work-artifact-race-{trial}"
        store = AtomicWorkStore()
        record = store.create_if_absent(work_id, RUN_CTX, RESERVATION_ID, _always_valid_reservation)
        lease = make_lease(
            scientific_work_id=work_id, worker_participant_id="worker-a", lease_generation=1
        )
        record = store.acquire_lease(
            work_id, record.revision, lease, reservation_validator=_always_valid_reservation
        )
        record = store.transition_to_executing(work_id, record.revision)

        attempt = make_execution_attempt(
            scientific_work_id=work_id, worker_participant_id="worker-a"
        )
        content_a = make_synthetic_content(f"race-a-{trial}")
        content_b = make_synthetic_content(f"race-b-{trial}")
        commit_a = make_result_commit(attempt, content_a)
        commit_b = make_result_commit(attempt, content_b)

        astore = InMemoryArtifactStore()
        metadata = ArtifactMetadata(
            workload_class=WorkloadClass.SYNTHETIC_SMOKE,
            data_classification=DataClassification.SYNTHETIC,
        )
        # Both artifacts are durably written BEFORE either CAS attempt --
        # the design this checkpoint's own audit requires.
        astore.put(commit_a.result_artifact_reference, content_a, metadata)
        astore.put(commit_b.result_artifact_reference, content_b, metadata)

        barrier = threading.Barrier(2)
        outcomes: list[tuple[ResultCommit, str]] = []
        lock = threading.Lock()

        def attempt_commit(commit: ResultCommit) -> None:
            barrier.wait()
            try:
                store.commit_result(work_id, record.revision, attempt, commit, astore.resolve)
                outcome = "success"
            except RevisionConflictError:
                outcome = "conflict"
            with lock:
                outcomes.append((commit, outcome))

        _run_concurrently(
            lambda: attempt_commit(commit_a),
            lambda: attempt_commit(commit_b),
        )

        successes = [entry for entry in outcomes if entry[1] == "success"]
        conflicts = [entry for entry in outcomes if entry[1] == "conflict"]
        assert len(successes) == 1, f"trial {trial}: exactly one commit must win the CAS"
        assert len(conflicts) == 1

        winning_commit = successes[0][0]
        losing_commit = commit_b if winning_commit is commit_a else commit_a
        final = store.read(work_id)
        assert final.result_commit == winning_commit
        # the losing artifact is still present (harmless) but unreferenced
        assert astore.resolve(losing_commit.result_artifact_reference) is True
        assert final.result_commit is not None
        assert final.result_commit.result_artifact_reference != (
            losing_commit.result_artifact_reference
        )


def test_cancellation_and_result_commit_race_has_exactly_one_deterministic_winner() -> None:
    """Test cancellation and result commit race has exactly one
    deterministic winner -- whichever operation wins the CAS determines
    the final, closed, typed outcome; the loser is cleanly rejected,
    never partially applied, and terminal evidence (if the commit won)
    can never subsequently be erased."""
    for trial in range(_TRIALS):
        work_id = f"work-cancel-race-{trial}"
        store = AtomicWorkStore()
        record = store.create_if_absent(work_id, RUN_CTX, RESERVATION_ID, _always_valid_reservation)
        lease = make_lease(
            scientific_work_id=work_id, worker_participant_id="worker-a", lease_generation=1
        )
        record = store.acquire_lease(
            work_id, record.revision, lease, reservation_validator=_always_valid_reservation
        )
        record = store.transition_to_executing(work_id, record.revision)

        attempt = make_execution_attempt(
            scientific_work_id=work_id, worker_participant_id="worker-a"
        )
        content = make_synthetic_content(f"cancel-race-{trial}")
        commit = make_result_commit(attempt, content)
        astore = InMemoryArtifactStore()
        metadata = ArtifactMetadata(
            workload_class=WorkloadClass.SYNTHETIC_SMOKE,
            data_classification=DataClassification.SYNTHETIC,
        )
        astore.put(commit.result_artifact_reference, content, metadata)

        cancellation = CancellationRequest(
            distributed_orchestration_schema_version=V,
            checksum_algorithm_version=C,
            scientific_work_id=work_id,
            cancellation_scope=CancellationScope.AFTER_LEASE,
            requested_at_logical_clock=1,
        )

        barrier = threading.Barrier(2)
        outcomes: list[tuple[str, str]] = []
        lock = threading.Lock()

        def try_commit() -> None:
            barrier.wait()
            try:
                store.commit_result(work_id, record.revision, attempt, commit, astore.resolve)
                outcome = "success"
            except RevisionConflictError:
                outcome = "conflict"
            with lock:
                outcomes.append(("commit", outcome))

        def try_cancel() -> None:
            barrier.wait()
            try:
                store.request_cancellation(work_id, record.revision, cancellation)
                outcome = "success"
            except RevisionConflictError:
                outcome = "conflict"
            with lock:
                outcomes.append(("cancel", outcome))

        _run_concurrently(try_commit, try_cancel)

        successes = [entry for entry in outcomes if entry[1] == "success"]
        assert len(successes) == 1, f"trial {trial}: exactly one of commit/cancel must win"
        winner = successes[0][0]
        final = store.read(work_id)
        if winner == "commit":
            assert final.state == WorkItemState.RESULT_COMMITTED
            assert final.result_commit == commit
        else:
            assert final.state == WorkItemState.CANCELLED
            assert final.result_commit is None


def test_concurrent_budget_reservations_never_oversubscribe_the_ceiling() -> None:
    """Test concurrent budget reservations never oversubscribe the
    ceiling -- budget reservation and work admission cannot diverge
    silently under real contention: with a 5000-cent ceiling and six
    threads each requesting 1000 cents, exactly five can ever be
    admitted, deterministically, regardless of thread interleaving."""
    for trial in range(_TRIALS):
        store = AtomicBudgetStore(budget_ceiling_cents=5000, max_admitted_workers=10)
        barrier = threading.Barrier(6)
        successes: list[int] = []
        lock = threading.Lock()

        def attempt(worker_index: int) -> None:
            barrier.wait()
            try:
                store.reserve(f"res-{trial}-{worker_index}", 1000, 1)
                with lock:
                    successes.append(worker_index)
            except BudgetCeilingExceededError:
                pass

        _run_concurrently(*(lambda i=i: attempt(i) for i in range(6)))

        assert len(successes) == 5, (
            f"trial {trial}: expected exactly 5 admissions, got {successes!r}"
        )
