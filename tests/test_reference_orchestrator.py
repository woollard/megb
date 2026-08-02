"""Tests for src.reference.reference_orchestrator (MEGB-03G.3).

Synthetic evidence, temp cache/audit directories, and controllable fake
execution backends only -- no real privileged corpus access, no Docker.
Organized to map onto the authorizing scope's "Required tests" list:
cache-first execution, deduplication, candidate-hash verification,
deterministic ordering, bounded concurrency/backpressure, retry policy,
interruption/resumption, cache-disposition handling, and leakage/
non-goal checks.
"""

# The authorizing scope's own required-tests list runs to ~20 items; this
# file covers ~30 to give each disposition/reconciliation/leakage case its
# own focused test rather than folding several concerns into one -- long by
# count of small, single-purpose tests, not by any one test's complexity.
# pylint: disable=too-many-lines
#
# See tests/test_reference_cache_key.py's/test_reference_audit.py's note:
# this file intentionally builds its own local fixtures (evidence/context/
# work-item builders, a fake execution backend) independent of
# test_reference_evaluator.py's own copies, rather than importing or
# subclassing them -- keeping each test module's fixtures self-contained is
# preferred here over coupling test files to each other's internals.
# pylint: disable=duplicate-code

import dataclasses
import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pytest
from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION

from src.execution.backend import ExecutionBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionLimits,
    ExecutionStatus,
)
from src.reference.oracle import (
    COMPARISON_PROFILE_VERSION,
    ORACLE_ALGORITHM_VERSION,
    ORACLE_STATUS_GENERATION_FAILED,
    POOL_REFERENCE_ONLY,
    OracleRecord,
    comparison_profile_for_task,
    generate_oracle_record,
)
from src.reference.partition import PARTITION_ALGORITHM_VERSION
from src.reference.reference_audit import ReferenceAuditLog
from src.reference.reference_cache import (
    CacheDisposition,
    CacheLookupResult,
    CacheWriteResult,
    ReferenceResultCache,
)
from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EXECUTION_PROFILE_ID_FULL,
    EXECUTION_PROTOCOL_VERSION,
    FULL_EXECUTION_PROFILE,
    ReferenceCase,
    ReferenceTaskEvidence,
)
from src.reference.reference_orchestrator import (
    DuplicateWorkItemIdError,
    InvalidWorkItemError,
    MappingEvidenceResolver,
    OrchestrationConfig,
    ReferenceOrchestrator,
    RetryPolicy,
    WorkItem,
    WorkItemDisposition,
)
from src.reference.result_schema import MeasurementStatus, ReferenceRunContext

_ENTRY_POINT = "double"
_PROMPT = f"def {_ENTRY_POINT}(n):\n"
_CANONICAL_SOLUTION = "    return n * 2\n"
_TASK_ID = "Test/0"
_CORRECT_CANDIDATE_CODE = "def double(n):\n    return n * 2\n"
_WRONG_CANDIDATE_CODE = "def double(n):\n    return n * 3\n"

_DATASET_CHECKSUM = "fe585eb4df8c88d844eeb463ea4d0302"
_TASK_MANIFEST_CHECKSUM = "d" * 64


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _oracle_record(task_id: str, case_id: str, n: int) -> OracleRecord:
    profile = comparison_profile_for_task(_ENTRY_POINT, atol=0.0)
    namespace: dict[str, Any] = {}
    exec(_PROMPT + _CANONICAL_SOLUTION, namespace)  # pylint: disable=exec-used
    canonical_fn = namespace[_ENTRY_POINT]
    return generate_oracle_record(
        task_id=task_id,
        case_id=case_id,
        args=(n,),
        provenance="original",
        pool=POOL_REFERENCE_ONLY,
        canonical_fn=canonical_fn,
        profile=profile,
    )


def _case(task_id: str, case_id: str, n: int) -> ReferenceCase:
    return ReferenceCase(
        case_id=case_id, args=(n,), oracle_record=_oracle_record(task_id, case_id, n)
    )


def _evidence(
    task_id: str = _TASK_ID, num_cases: int = 1, **overrides: object
) -> ReferenceTaskEvidence:
    cases = tuple(_case(task_id, f"c{i}", i + 1) for i in range(num_cases))
    fields: dict[str, object] = {
        "task_id": task_id,
        "entry_point": _ENTRY_POINT,
        "comparison_profile": comparison_profile_for_task(_ENTRY_POINT, atol=0.0),
        "cases": cases,
        "oracle_version": ORACLE_ALGORITHM_VERSION,
        "partition_version": PARTITION_ALGORITHM_VERSION,
        "dataset_version": HUMANEVAL_PLUS_VERSION,
        "protocol_version": EXECUTION_PROTOCOL_VERSION,
        "dataset_checksum": _DATASET_CHECKSUM,
        "task_manifest_checksum": _TASK_MANIFEST_CHECKSUM,
    }
    fields.update(overrides)
    return ReferenceTaskEvidence(**fields)  # type: ignore[arg-type]


def _run_context(**overrides: object) -> ReferenceRunContext:
    fields: dict[str, object] = {
        "experiment_run_id": "exp-1",
        "optimization_run_id": "opt-1",
        "optimization_config_sha256": "b" * 64,
        "portfolio_frozen_at": "2026-08-01T00:00:00Z",
        "portfolio_selection_rule": "best_of_run",
        "evaluator_version": EVALUATOR_VERSION_FULL,
        "dataset_version": HUMANEVAL_PLUS_VERSION,
        "partition_version": PARTITION_ALGORITHM_VERSION,
        "execution_profile_id": EXECUTION_PROFILE_ID_FULL,
        "comparison_profile_version": COMPARISON_PROFILE_VERSION,
        "execution_protocol_version": EXECUTION_PROTOCOL_VERSION,
        "dataset_checksum": _DATASET_CHECKSUM,
        "task_manifest_checksum": _TASK_MANIFEST_CHECKSUM,
    }
    fields.update(overrides)
    return ReferenceRunContext(**fields)  # type: ignore[arg-type]


def _work_item(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    work_item_id: str,
    input_ordinal: int,
    *,
    task_id: str = _TASK_ID,
    candidate_code: str = _CORRECT_CANDIDATE_CODE,
    candidate_id: str | None = None,
    candidate_sha256: str | None = None,
    run_context: ReferenceRunContext | None = None,
) -> WorkItem:
    resolved_sha256 = candidate_sha256 if candidate_sha256 is not None else _sha256(candidate_code)
    return WorkItem(
        work_item_id=work_item_id,
        input_ordinal=input_ordinal,
        task_id=task_id,
        candidate_id=candidate_id if candidate_id is not None else f"cand-{work_item_id}",
        candidate_sha256=resolved_sha256,
        candidate_code=candidate_code,
        run_context=run_context if run_context is not None else _run_context(),
    )


def _execution_result(
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    return_value: object = None,
    invocation_id: str = "inv-0",
) -> CandidateExecutionResult:
    return CandidateExecutionResult(
        invocation_id=invocation_id,
        status=status,
        return_value=return_value,
        exception_type=None,
        exception_message=None,
        wall_time_sec=0.001,
        candidate_wall_time_sec=0.0005 if status == ExecutionStatus.COMPLETED else None,
        exit_code=0,
        terminating_signal=None,
        stdout="",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        backend_id="fake",
        backend_version="1",
        runner_image_digest="sha256:fake",
        protocol_version=EXECUTION_PROTOCOL_VERSION,
        limits=ExecutionLimits(),
        started_at="2026-08-01T00:00:00Z",
    )


class ConcurrencyTracker:
    """Records how many backend calls are simultaneously in progress."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current = 0
        self.max_observed = 0

    def enter(self) -> None:
        """Record one more concurrently-in-progress call."""
        with self._lock:
            self._current += 1
            self.max_observed = max(self.max_observed, self._current)

    def exit(self) -> None:
        """Record that one in-progress call has finished."""
        with self._lock:
            self._current -= 1


class RecordingBackend(ExecutionBackend):
    """One fresh instance per key-execution (per the factory pattern):
    always returns the *correct* doubled value for ``COMPLETED`` calls,
    unless ``overrides`` supplies a different status for that call index.
    """

    def __init__(
        self,
        overrides: list[ExecutionStatus] | None = None,
        delay: float = 0.0,
        tracker: ConcurrencyTracker | None = None,
    ) -> None:
        self._overrides = list(overrides) if overrides else []
        self._delay = delay
        self._tracker = tracker
        self._lock = threading.Lock()
        self.call_count = 0

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        with self._lock:
            call_index = self.call_count
            self.call_count += 1
        if self._tracker is not None:
            self._tracker.enter()
        try:
            if self._delay:
                time.sleep(self._delay)
            status = (
                self._overrides[call_index]
                if call_index < len(self._overrides)
                else ExecutionStatus.COMPLETED
            )
            n = request.args[0]
            return_value = n * 2 if status == ExecutionStatus.COMPLETED else None
            return _execution_result(status=status, return_value=return_value)
        finally:
            if self._tracker is not None:
                self._tracker.exit()


class RaisingBackend(ExecutionBackend):
    """Always raises -- simulates a genuine backend-setup failure that
    ``ExecutionBackend.execute()``'s own interface contract permits."""

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        raise RuntimeError("simulated backend-setup failure")


def _factory(make: Callable[[], ExecutionBackend]) -> Callable[[], ExecutionBackend]:
    return make


def _orchestrator(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    tmp_path: Path,
    *,
    evidence_by_task: dict[str, ReferenceTaskEvidence] | None = None,
    backend_factory: Callable[[], ExecutionBackend] | None = None,
    max_workers: int = 2,
    max_in_flight: int = 2,
    max_attempts: int = 3,
    on_in_flight_change: Callable[[int], None] | None = None,
    cache: ReferenceResultCache | None = None,
    audit_log: ReferenceAuditLog | None = None,
) -> tuple[ReferenceOrchestrator, ReferenceResultCache, ReferenceAuditLog]:
    resolved_cache = cache if cache is not None else ReferenceResultCache(tmp_path / "cache")
    resolved_audit = (
        audit_log if audit_log is not None else ReferenceAuditLog(tmp_path / "audit.jsonl")
    )
    evidence_map = evidence_by_task if evidence_by_task is not None else {_TASK_ID: _evidence()}
    factory = backend_factory if backend_factory is not None else _factory(RecordingBackend)
    orchestrator = ReferenceOrchestrator(
        cache=resolved_cache,
        audit_log=resolved_audit,
        evidence_resolver=MappingEvidenceResolver(evidence_map),
        backend_factory=factory,
        config=OrchestrationConfig(
            max_workers=max_workers,
            max_in_flight=max_in_flight,
            retry_policy=RetryPolicy(max_attempts=max_attempts),
            profile=FULL_EXECUTION_PROFILE,
        ),
        on_in_flight_change=on_in_flight_change,
    )
    return orchestrator, resolved_cache, resolved_audit


# --- Cache-first execution and deduplication --------------------------------


def test_cache_hit_invokes_no_backend_call(tmp_path: Path) -> None:
    """A valid cache hit never invokes the backend."""
    call_counter = {"n": 0}

    def make_backend() -> ExecutionBackend:
        call_counter["n"] += 1
        return RecordingBackend()

    orchestrator, _, _ = _orchestrator(tmp_path, backend_factory=make_backend)
    item = _work_item("wi-0", 0)

    first = orchestrator.run([item], run_id="run-1")
    assert first.outcomes[0].disposition == WorkItemDisposition.EXECUTED_VALID
    assert call_counter["n"] == 1

    second = orchestrator.run([item], run_id="run-2")
    assert second.outcomes[0].disposition == WorkItemDisposition.CACHE_HIT
    assert call_counter["n"] == 1, "cache hit must not construct a fresh backend"


def test_cache_miss_executes_once_and_caches(tmp_path: Path) -> None:
    """A miss executes exactly once and the result becomes retrievable."""
    orchestrator, cache, _ = _orchestrator(tmp_path)
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    assert summary.fresh_execution_keys == 1
    assert summary.cache_hit_keys == 0
    outcome = summary.outcomes[0]
    assert outcome.disposition == WorkItemDisposition.EXECUTED_VALID
    assert outcome.task_result is not None
    assert outcome.task_result.status == MeasurementStatus.VALID
    assert cache.cache_dir.exists()
    assert len(list(cache.cache_dir.glob("*.json"))) == 1


def test_duplicate_work_items_same_key_coalesced_and_executed_once(tmp_path: Path) -> None:
    """Two work items sharing the same task/candidate/context execute once."""
    call_counter = {"n": 0}

    def make_backend() -> ExecutionBackend:
        call_counter["n"] += 1
        return RecordingBackend()

    orchestrator, _, _ = _orchestrator(tmp_path, backend_factory=make_backend)
    items = [_work_item("wi-0", 0), _work_item("wi-1", 1)]

    summary = orchestrator.run(items, run_id="run-1")

    assert summary.unique_cache_keys == 1
    assert summary.duplicate_work_items == 1
    assert call_counter["n"] == 1
    assert all(o.disposition == WorkItemDisposition.EXECUTED_VALID for o in summary.outcomes)
    assert summary.outcomes[0].cache_key_digest == summary.outcomes[1].cache_key_digest


def test_same_candidate_hash_different_tasks_remains_distinct_work(tmp_path: Path) -> None:
    """The same candidate_sha256 against two different tasks is distinct work."""
    evidence_map = {_TASK_ID: _evidence(_TASK_ID), "Test/1": _evidence("Test/1")}
    orchestrator, _, _ = _orchestrator(tmp_path, evidence_by_task=evidence_map)
    items = [
        _work_item("wi-0", 0, task_id=_TASK_ID),
        _work_item("wi-1", 1, task_id="Test/1", candidate_sha256=_sha256(_CORRECT_CANDIDATE_CODE)),
    ]

    summary = orchestrator.run(items, run_id="run-1")

    assert summary.unique_cache_keys == 2
    assert summary.duplicate_work_items == 0
    assert summary.outcomes[0].cache_key_digest != summary.outcomes[1].cache_key_digest


# --- Candidate identity verification -----------------------------------------


def test_candidate_hash_mismatch_rejected_before_lookup_or_execution(tmp_path: Path) -> None:
    """A mismatched candidate_sha256 never reaches the cache or the backend."""
    call_counter = {"n": 0}

    def make_backend() -> ExecutionBackend:
        call_counter["n"] += 1
        return RecordingBackend()

    orchestrator, cache, _ = _orchestrator(tmp_path, backend_factory=make_backend)
    item = _work_item("wi-0", 0, candidate_sha256="0" * 64)

    summary = orchestrator.run([item], run_id="run-1")

    outcome = summary.outcomes[0]
    assert outcome.disposition == WorkItemDisposition.CANDIDATE_HASH_MISMATCH
    assert outcome.cache_key_digest is None
    assert outcome.task_result is None
    assert call_counter["n"] == 0
    assert not list(cache.cache_dir.glob("*.json"))
    assert summary.invalid_work_items == 1
    assert summary.candidate_hash_mismatches == 1


def test_work_item_rejects_malformed_fields() -> None:
    """WorkItem construction validates its own required fields."""
    with pytest.raises(InvalidWorkItemError):
        _work_item("", 0)
    with pytest.raises(InvalidWorkItemError):
        WorkItem(
            work_item_id="wi-0",
            input_ordinal=-1,
            task_id=_TASK_ID,
            candidate_id="cand",
            candidate_sha256=_sha256(_CORRECT_CANDIDATE_CODE),
            candidate_code=_CORRECT_CANDIDATE_CODE,
            run_context=_run_context(),
        )


def test_duplicate_work_item_id_rejected(tmp_path: Path) -> None:
    """Two work items sharing a work_item_id in one run() call is a caller error."""
    orchestrator, _, _ = _orchestrator(tmp_path)
    items = [_work_item("wi-0", 0), _work_item("wi-0", 1)]
    with pytest.raises(DuplicateWorkItemIdError):
        orchestrator.run(items, run_id="run-1")


# --- Deterministic ordering ---------------------------------------------------


def test_deterministic_ordering_independent_of_completion_order(tmp_path: Path) -> None:
    """Outcomes are ordered by input_ordinal even when later items finish first."""
    tracker = ConcurrencyTracker()

    def make_backend() -> ExecutionBackend:
        # Earlier-ordinal items get a longer delay so they finish *after*
        # later-ordinal items, deliberately reversing completion order.
        return RecordingBackend(tracker=tracker)

    evidence_map = {f"Test/{i}": _evidence(f"Test/{i}") for i in range(5)}
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        evidence_by_task=evidence_map,
        max_workers=5,
        max_in_flight=5,
        backend_factory=make_backend,
    )
    items = [_work_item(f"wi-{i}", i, task_id=f"Test/{4 - i}") for i in range(5)]

    summary = orchestrator.run(items, run_id="run-1")

    assert [o.input_ordinal for o in summary.outcomes] == [0, 1, 2, 3, 4]
    assert [o.work_item_id for o in summary.outcomes] == [f"wi-{i}" for i in range(5)]


# --- Bounded concurrency / backpressure ---------------------------------------


def test_max_workers_bounds_concurrent_backend_calls(tmp_path: Path) -> None:
    """No more than max_workers backend calls run at the same instant."""
    tracker = ConcurrencyTracker()
    evidence_map = {f"Test/{i}": _evidence(f"Test/{i}", num_cases=1) for i in range(8)}
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        evidence_by_task=evidence_map,
        max_workers=2,
        max_in_flight=8,
        backend_factory=lambda: RecordingBackend(delay=0.05, tracker=tracker),
    )
    items = [_work_item(f"wi-{i}", i, task_id=f"Test/{i}") for i in range(8)]

    orchestrator.run(items, run_id="run-1")

    assert tracker.max_observed <= 2


def test_max_in_flight_bounds_admitted_but_unfinished_work(tmp_path: Path) -> None:
    """Admitted-but-unfinished work never exceeds max_in_flight, even when
    max_in_flight exceeds max_workers."""
    observed: dict[str, int] = {"max": 0}

    def on_change(count: int) -> None:
        observed["max"] = max(observed["max"], count)

    evidence_map = {f"Test/{i}": _evidence(f"Test/{i}", num_cases=1) for i in range(10)}
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        evidence_by_task=evidence_map,
        max_workers=2,
        max_in_flight=4,
        on_in_flight_change=on_change,
        backend_factory=lambda: RecordingBackend(delay=0.03),
    )
    items = [_work_item(f"wi-{i}", i, task_id=f"Test/{i}") for i in range(10)]

    summary = orchestrator.run(items, run_id="run-1")

    assert observed["max"] <= 4
    assert summary.accepted_work_items == 10


def test_cache_and_audit_safe_under_concurrency(tmp_path: Path) -> None:
    """Concurrent unique-key executions never corrupt the cache or audit log."""
    evidence_map = {f"Test/{i}": _evidence(f"Test/{i}", num_cases=1) for i in range(12)}
    orchestrator, cache, audit_log = _orchestrator(
        tmp_path,
        evidence_by_task=evidence_map,
        max_workers=4,
        max_in_flight=6,
        backend_factory=lambda: RecordingBackend(delay=0.01),
    )
    items = [_work_item(f"wi-{i}", i, task_id=f"Test/{i}") for i in range(12)]

    summary = orchestrator.run(items, run_id="run-1")

    assert summary.accepted_work_items == 12
    assert len(list(cache.cache_dir.glob("*.json"))) == 12
    assert len(audit_log.read_all()) == 12


# --- Retry policy --------------------------------------------------------------


def test_infrastructure_failure_retried_and_eventually_succeeds(tmp_path: Path) -> None:
    """A transient infrastructure failure is retried and can still succeed."""
    orchestrator, cache, audit_log = _orchestrator(
        tmp_path,
        max_attempts=3,
        backend_factory=lambda: RecordingBackend(
            overrides=[ExecutionStatus.INFRASTRUCTURE_ERROR, ExecutionStatus.COMPLETED]
        ),
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    outcome = summary.outcomes[0]
    assert outcome.disposition == WorkItemDisposition.EXECUTED_VALID
    assert outcome.attempts == 2
    assert summary.total_attempts == 2
    assert len(list(cache.cache_dir.glob("*.json"))) == 1
    records = audit_log.read_all()
    assert len(records) == 2
    assert records[0].status == "INVALID_INFRASTRUCTURE"
    assert records[1].status == "VALID"


def test_retry_exhaustion_produces_typed_incomplete_outcome_not_cached(tmp_path: Path) -> None:
    """Exhausted retries yield RETRY_EXHAUSTED and nothing is cached."""
    orchestrator, cache, audit_log = _orchestrator(
        tmp_path,
        max_attempts=2,
        backend_factory=lambda: RecordingBackend(
            overrides=[ExecutionStatus.INFRASTRUCTURE_ERROR, ExecutionStatus.INFRASTRUCTURE_ERROR]
        ),
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    outcome = summary.outcomes[0]
    assert outcome.disposition == WorkItemDisposition.RETRY_EXHAUSTED
    assert outcome.attempts == 2
    assert summary.accepted_work_items == 0
    assert summary.invalid_work_items == 1
    assert not list(cache.cache_dir.glob("*.json"))
    assert len(audit_log.read_all()) == 2


def test_raised_backend_exception_is_retried_like_infrastructure_failure(tmp_path: Path) -> None:
    """A raised backend-setup exception is treated like INVALID_INFRASTRUCTURE."""
    orchestrator, _, _ = _orchestrator(tmp_path, max_attempts=2, backend_factory=RaisingBackend)
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    outcome = summary.outcomes[0]
    assert outcome.disposition == WorkItemDisposition.RETRY_EXHAUSTED
    assert outcome.attempts == 2
    assert outcome.task_result is None


class _WrongAnswerBackend(ExecutionBackend):
    """Always returns a value that is wrong for double(n) -- used to prove
    a candidate failure is a VALID measurement (q_ref_task=0.0), never
    retried."""

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        n = request.args[0]
        return _execution_result(status=ExecutionStatus.COMPLETED, return_value=n * 2 + 1)


def test_wrong_output_is_valid_not_retried(tmp_path: Path) -> None:
    """A candidate producing a wrong answer is VALID (q_ref_task=0.0), never retried."""
    orchestrator, _, _ = _orchestrator(
        tmp_path, max_attempts=3, backend_factory=_WrongAnswerBackend
    )
    item = _work_item("wi-0", 0, candidate_code=_WRONG_CANDIDATE_CODE)

    summary = orchestrator.run([item], run_id="run-1")

    outcome = summary.outcomes[0]
    assert outcome.disposition == WorkItemDisposition.EXECUTED_VALID
    assert outcome.attempts == 1
    assert outcome.task_result is not None
    assert outcome.task_result.q_ref_task == 0.0


def test_protocol_error_is_non_retryable(tmp_path: Path) -> None:
    """INVALID_PROTOCOL is never retried, even with attempts remaining."""
    orchestrator, cache, _ = _orchestrator(
        tmp_path,
        max_attempts=5,
        backend_factory=lambda: RecordingBackend(overrides=[ExecutionStatus.PROTOCOL_ERROR]),
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    outcome = summary.outcomes[0]
    assert outcome.disposition == WorkItemDisposition.EXECUTED_INVALID
    assert outcome.attempts == 1
    assert not list(cache.cache_dir.glob("*.json"))


def test_invalid_oracle_is_non_retryable(tmp_path: Path) -> None:
    """A case with a failed oracle record yields INVALID_ORACLE, never retried."""
    profile = comparison_profile_for_task(_ENTRY_POINT, atol=0.0)
    broken_record = OracleRecord(
        task_id=_TASK_ID,
        case_id="c0",
        pool=POOL_REFERENCE_ONLY,
        provenance="original",
        comparison_profile_kind=profile.kind,
        status=ORACLE_STATUS_GENERATION_FAILED,
        expected_output=None,
        failure_reason="simulated oracle generation failure",
    )
    broken_case = ReferenceCase(case_id="c0", args=(1,), oracle_record=broken_record)
    evidence = _evidence(num_cases=0, cases=(broken_case,))
    orchestrator, cache, _ = _orchestrator(
        tmp_path, evidence_by_task={_TASK_ID: evidence}, max_attempts=5
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    outcome = summary.outcomes[0]
    assert outcome.disposition == WorkItemDisposition.EXECUTED_INVALID
    assert outcome.attempts == 1
    assert not list(cache.cache_dir.glob("*.json"))


# --- Interruption and resumption ----------------------------------------------


def test_interruption_before_admission_marks_items_not_started(tmp_path: Path) -> None:
    """A pre-set cancellation event stops admission before anything runs."""
    call_counter = {"n": 0}

    def make_backend() -> ExecutionBackend:
        call_counter["n"] += 1
        return RecordingBackend()

    evidence_map = {_TASK_ID: _evidence(_TASK_ID), "Test/1": _evidence("Test/1")}
    orchestrator, _, _ = _orchestrator(
        tmp_path, evidence_by_task=evidence_map, backend_factory=make_backend
    )
    cancelled = threading.Event()
    cancelled.set()
    items = [_work_item("wi-0", 0), _work_item("wi-1", 1, task_id="Test/1")]

    summary = orchestrator.run(items, run_id="run-1", cancellation_event=cancelled)

    assert summary.interrupted is True
    assert summary.unstarted_work_items == len(items)
    assert call_counter["n"] == 0
    assert all(o.disposition == WorkItemDisposition.NOT_STARTED for o in summary.outcomes)


def test_interruption_with_work_in_flight_preserves_completed_results(tmp_path: Path) -> None:
    """Cancellation mid-run preserves already-admitted results and marks the rest unstarted."""
    cancelled = threading.Event()

    def make_backend() -> ExecutionBackend:
        # The first admitted item's execution triggers cancellation partway
        # through, simulating a cooperative cancel signal arriving mid-run.
        time.sleep(0.02)
        cancelled.set()
        return RecordingBackend()

    evidence_map = {f"Test/{i}": _evidence(f"Test/{i}") for i in range(4)}
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        evidence_by_task=evidence_map,
        max_workers=1,
        max_in_flight=1,
        backend_factory=make_backend,
    )
    items = [_work_item(f"wi-{i}", i, task_id=f"Test/{i}") for i in range(4)]

    summary = orchestrator.run(items, run_id="run-1", cancellation_event=cancelled)

    assert summary.interrupted is True
    started = [o for o in summary.outcomes if o.disposition != WorkItemDisposition.NOT_STARTED]
    unstarted = [o for o in summary.outcomes if o.disposition == WorkItemDisposition.NOT_STARTED]
    assert len(started) >= 1
    assert len(unstarted) >= 1
    assert all(o.disposition == WorkItemDisposition.EXECUTED_VALID for o in started)


def test_restart_after_interruption_executes_only_unfinished_keys(tmp_path: Path) -> None:
    """A second run() over the same items resumes via cache hits and only
    executes what was left unstarted."""
    call_counter = {"n": 0}

    def make_backend() -> ExecutionBackend:
        call_counter["n"] += 1
        return RecordingBackend()

    cache = ReferenceResultCache(tmp_path / "cache")
    audit_log = ReferenceAuditLog(tmp_path / "audit.jsonl")
    evidence_map = {f"Test/{i}": _evidence(f"Test/{i}") for i in range(4)}
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        evidence_by_task=evidence_map,
        cache=cache,
        audit_log=audit_log,
        max_workers=1,
        max_in_flight=1,
        backend_factory=make_backend,
    )
    items = [_work_item(f"wi-{i}", i, task_id=f"Test/{i}") for i in range(4)]

    cancelled = threading.Event()
    cancelled.set()
    # Nothing admitted at all on the first (fully pre-cancelled) call --
    # simulates a process that was interrupted before doing any work.
    first = orchestrator.run(items, run_id="run-1", cancellation_event=cancelled)
    assert first.unstarted_work_items == 4
    assert call_counter["n"] == 0

    second = orchestrator.run(items, run_id="run-2")
    assert second.unstarted_work_items == 0
    assert second.accepted_work_items == 4
    assert call_counter["n"] == 4


def test_no_duplicate_accepted_results_after_resume(tmp_path: Path) -> None:
    """Re-running fully-completed work items produces only cache hits, no re-execution."""
    call_counter = {"n": 0}

    def make_backend() -> ExecutionBackend:
        call_counter["n"] += 1
        return RecordingBackend()

    orchestrator, _, _ = _orchestrator(tmp_path, backend_factory=make_backend)
    items = [_work_item("wi-0", 0)]

    orchestrator.run(items, run_id="run-1")
    assert call_counter["n"] == 1

    second = orchestrator.run(items, run_id="run-2")
    assert call_counter["n"] == 1
    assert second.outcomes[0].disposition == WorkItemDisposition.CACHE_HIT

    third = orchestrator.run(items, run_id="run-3")
    assert call_counter["n"] == 1
    assert third.outcomes[0].disposition == WorkItemDisposition.CACHE_HIT


def test_run_id_does_not_affect_cache_identity(tmp_path: Path) -> None:
    """Different run IDs over the same work item still hit the same cache entry."""
    call_counter = {"n": 0}

    def make_backend() -> ExecutionBackend:
        call_counter["n"] += 1
        return RecordingBackend()

    orchestrator, _, _ = _orchestrator(tmp_path, backend_factory=make_backend)
    item = _work_item("wi-0", 0)

    orchestrator.run([item], run_id="alpha")
    orchestrator.run([item], run_id="completely-different-run-id")

    assert call_counter["n"] == 1


# --- Cache-disposition handling: corrupt / stale / conflicting / storage -----


def test_corrupt_cache_entry_blocks_the_item(tmp_path: Path) -> None:
    """A corrupt on-disk entry is never silently trusted, overwritten, or repaired."""
    orchestrator, cache, audit_log = _orchestrator(tmp_path)
    item = _work_item("wi-0", 0)

    # Discover the real key digest by running once normally, then corrupt
    # the file it produced, using a *different* cache instance so the
    # orchestrator's own in-memory state is untouched.
    orchestrator.run([item], run_id="run-1")
    entry_path = next(cache.cache_dir.glob("*.json"))
    entry_path.write_text("not valid json {{{", encoding="utf-8")

    fresh_orchestrator, _, _ = _orchestrator(tmp_path, cache=cache, audit_log=audit_log)
    summary = fresh_orchestrator.run([item], run_id="run-2")

    outcome = summary.outcomes[0]
    assert outcome.disposition == WorkItemDisposition.CACHE_CONFLICT_BLOCKED
    assert "could not be reconciled" in outcome.detail
    # The corrupt bytes are still there -- never silently overwritten.
    assert entry_path.read_text(encoding="utf-8") == "not valid json {{{"


def test_stale_incompatible_cache_entry_blocks_the_item(tmp_path: Path) -> None:
    """A schema-incompatible on-disk entry is treated the same way: blocked, not repaired."""
    orchestrator, cache, audit_log = _orchestrator(tmp_path)
    item = _work_item("wi-0", 0)

    orchestrator.run([item], run_id="run-1")
    entry_path = next(cache.cache_dir.glob("*.json"))
    payload = json.loads(entry_path.read_text(encoding="utf-8"))
    payload["cache_entry_schema_version"] = "reference-result-cache-entry-v0"
    entry_path.write_text(json.dumps(payload), encoding="utf-8")

    fresh_orchestrator, _, _ = _orchestrator(tmp_path, cache=cache, audit_log=audit_log)
    summary = fresh_orchestrator.run([item], run_id="run-2")

    assert summary.outcomes[0].disposition == WorkItemDisposition.CACHE_CONFLICT_BLOCKED


class _InjectingCache:
    """Wraps a real cache: the first ``get()`` for any key pretends MISS
    (simulating "no entry visible yet from this caller's perspective"), and
    ``put()`` injects a concurrently-written, logically equivalent entry
    just before delegating -- used only to deterministically exercise the
    CONFLICTING_WRITE-reconciled-as-hit path without a real race."""

    def __init__(self, real: ReferenceResultCache) -> None:
        self._real = real
        self._get_calls = 0

    @property
    def cache_dir(self) -> Path:
        """Delegate to the wrapped real cache's directory."""
        return self._real.cache_dir

    def get(self, key: object) -> Any:
        """Return MISS on the first call for any key, then delegate."""
        self._get_calls += 1
        if self._get_calls == 1:
            return CacheLookupResult(CacheDisposition.MISS, None, "simulated miss")
        return self._real.get(key)  # type: ignore[arg-type]

    def put(self, task_result: Any) -> Any:
        """Inject a concurrent equivalent write, then delegate the real one."""
        # A "concurrent" writer lands its own re-derived copy first --
        # logically equivalent (same outcome fields) but not byte-identical
        # (different evaluated_at/duration_seconds), exactly as two
        # independent real executions of the same deterministic candidate
        # would differ.
        injected = dataclasses.replace(
            task_result, evaluated_at="2026-08-01T00:00:00Z", duration_seconds=999.0
        )
        self._real.put(injected)
        return self._real.put(task_result)


def test_conflicting_write_with_equivalent_content_reconciled_as_hit(tmp_path: Path) -> None:
    """A CONFLICTING_WRITE whose existing entry is logically equivalent is
    accepted as a cache hit, not blocked."""
    real_cache = ReferenceResultCache(tmp_path / "cache")
    injecting_cache = _InjectingCache(real_cache)
    orchestrator, _, _ = _orchestrator(tmp_path, cache=injecting_cache)  # type: ignore[arg-type]
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    outcome = summary.outcomes[0]
    assert outcome.disposition == WorkItemDisposition.CACHE_HIT
    assert outcome.detail == "concurrent equivalent write reconciled as a cache hit"


class _ReadOnlyPutCache:
    """Wraps a real cache; ``get`` passes through, ``put`` always reports a
    storage-infrastructure failure -- simulates a disk/permission failure
    without depending on OS-specific chmod behavior."""

    def __init__(self, real: ReferenceResultCache) -> None:
        self._real = real

    @property
    def cache_dir(self) -> Path:
        """Delegate to the wrapped real cache's directory."""
        return self._real.cache_dir

    def get(self, key: object) -> Any:
        """Delegate straight through to the wrapped real cache."""
        return self._real.get(key)  # type: ignore[arg-type]

    def put(self, task_result: Any) -> Any:
        """Always simulate a storage-infrastructure failure."""
        del task_result
        return CacheWriteResult(
            CacheDisposition.STORAGE_INFRASTRUCTURE_FAILURE, "simulated disk failure"
        )


def test_storage_infrastructure_failure_on_put_reported(tmp_path: Path) -> None:
    """A cache write failure produces a typed CACHE_STORAGE_FAILURE outcome,
    carrying the valid (but unpersisted) result."""
    real_cache = ReferenceResultCache(tmp_path / "cache")
    broken_cache = _ReadOnlyPutCache(real_cache)
    orchestrator, _, audit_log = _orchestrator(
        tmp_path, cache=broken_cache  # type: ignore[arg-type]
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    outcome = summary.outcomes[0]
    assert outcome.disposition == WorkItemDisposition.CACHE_STORAGE_FAILURE
    assert outcome.task_result is not None
    assert outcome.task_result.status == MeasurementStatus.VALID
    records = audit_log.read_all()
    assert records[-1].cache_disposition == "STORAGE_INFRASTRUCTURE_FAILURE"


# --- Reconciliation and non-goal checks ---------------------------------------


def test_summary_reconciles_counts(tmp_path: Path) -> None:
    """accepted + invalid + unstarted always equals total_work_items."""
    evidence_map = {f"Test/{i}": _evidence(f"Test/{i}") for i in range(3)}
    orchestrator, _, _ = _orchestrator(tmp_path, evidence_by_task=evidence_map)
    items = [
        _work_item("wi-0", 0, task_id="Test/0"),
        _work_item("wi-1", 1, task_id="Test/1", candidate_sha256="0" * 64),  # mismatch
        _work_item("wi-2", 2, task_id="Test/2"),
    ]

    summary = orchestrator.run(items, run_id="run-1")

    assert (
        summary.accepted_work_items + summary.invalid_work_items + summary.unstarted_work_items
        == summary.total_work_items
    )
    assert summary.total_work_items == 3
    assert summary.candidate_hash_mismatches == 1


def test_workload_sizes_other_than_163_or_164_are_accepted(tmp_path: Path) -> None:
    """Nothing about this orchestrator requires a 163 or 164 count."""
    for size in (1, 3, 7):
        evidence_map = {f"Sz{size}/{i}": _evidence(f"Sz{size}/{i}") for i in range(size)}
        orchestrator, _, _ = _orchestrator(
            tmp_path, evidence_by_task=evidence_map, max_workers=1, max_in_flight=1
        )
        items = [_work_item(f"wi-{size}-{i}", i, task_id=f"Sz{size}/{i}") for i in range(size)]
        summary = orchestrator.run(items, run_id=f"run-{size}")
        assert summary.total_work_items == size
        assert summary.accepted_work_items == size


def test_no_aggregation_function_is_referenced() -> None:
    """The orchestrator module never imports aggregate_reference_results
    or any manifest-specific type -- only its docstring may *mention* them
    (as an explicit non-goal), never import or call them."""
    import src.reference.reference_orchestrator as orchestrator_module  # pylint: disable=import-outside-toplevel

    assert not hasattr(orchestrator_module, "aggregate_reference_results")
    assert not hasattr(orchestrator_module, "ReferenceValidationCandidateSetManifest")
    source = Path(orchestrator_module.__file__).read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    joined_imports = "\n".join(import_lines)
    assert "aggregate_reference_results" not in joined_imports
    assert "ReferenceValidationCandidateSetManifest" not in joined_imports
    assert "primary_experiment_task_manifest" not in joined_imports
    assert "src.reference.aggregation" not in joined_imports


# --- Leakage checks ------------------------------------------------------------


def test_no_candidate_code_or_privileged_content_in_outcomes_or_audit(tmp_path: Path) -> None:
    """Candidate code, case IDs, and expected outputs never leak into the
    run summary or the audit log."""
    canary_code = "def double(n):\n    return n * 2  # CANDIDATE-CODE-CANARY\n"
    orchestrator, _, audit_log = _orchestrator(tmp_path)
    item = _work_item("wi-0", 0, candidate_code=canary_code)

    summary = orchestrator.run([item], run_id="run-1")

    summary_repr = repr(summary)
    assert "CANDIDATE-CODE-CANARY" not in summary_repr
    assert canary_code not in summary_repr

    audit_repr = repr(audit_log.read_all())
    assert "CANDIDATE-CODE-CANARY" not in audit_repr
    assert canary_code not in audit_repr


def test_candidate_hash_mismatch_detail_never_contains_candidate_code(tmp_path: Path) -> None:
    """Even the rejection detail message never echoes candidate source."""
    canary_code = "def double(n):\n    return n * 2  # SHOULD-NEVER-APPEAR\n"
    orchestrator, _, _ = _orchestrator(tmp_path)
    item = _work_item("wi-0", 0, candidate_code=canary_code, candidate_sha256="1" * 64)

    summary = orchestrator.run([item], run_id="run-1")

    assert "SHOULD-NEVER-APPEAR" not in summary.outcomes[0].detail
