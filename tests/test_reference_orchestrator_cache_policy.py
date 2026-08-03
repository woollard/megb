"""Tests for MEGB-03H.2B.1: CachePolicy, task-evaluation replicate
admission, and durable trace-before-cache ordering, layered onto the
existing MEGB-03G.3 orchestrator.

Synthetic evidence, temp cache/audit/trace directories, and controllable
fake execution backends only -- no real privileged corpus access, no
Docker. Builds its own local fixtures (evidence/context/work-item
builders, a fake execution backend, a fake trace recorder), independent of
test_reference_orchestrator.py's own copies, per this test suite's own
established convention of keeping test modules self-contained.

Required-tests coverage (per the H.2B.1 authorization):
prepopulated-cache bypass under both fresh policies; N replicates -> N
evaluator calls; replicate ids never alter cache keys; H.6-style execution
leaves the production cache byte-for-byte unchanged; trace-before-cache
ordering; trace-write failure blocks cache mutation; conflicting/non-
cacheable classifications preserved under a fresh policy; deterministic
ordering/association for concurrent replicates; cancellation/resumption
never deduplicates distinct replicates; CACHE_FIRST is the default; fresh
policies refuse to run without a trace_recorder.
"""

# See test_reference_orchestrator.py's/test_reference_evaluator.py's own
# note: this file intentionally builds its own local fixtures (evidence/
# context/work-item/execution-result builders) independent of those other
# modules' copies, rather than importing or subclassing them -- keeping
# each test module's fixtures self-contained is preferred here over
# coupling test files to each other's internals.
# pylint: disable=duplicate-code

import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION

from src.execution.backend import ExecutionBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionLimits,
    ExecutionStatus,
)
from src.reference.calibration_schema import (
    CALIBRATION_SCHEMA_VERSION,
    CalibrationRunContext,
    CalibrationStage,
    CalibrationTaskEvaluationRecord,
)
from src.reference.calibration_trace import CalibrationTraceStore
from src.reference.oracle import (
    COMPARISON_PROFILE_VERSION,
    ORACLE_ALGORITHM_VERSION,
    POOL_REFERENCE_ONLY,
    comparison_profile_for_task,
    generate_oracle_record,
)
from src.reference.orchestration_trace import (
    CachePolicy,
    CalibrationTraceRecorder,
    CalibrationTraceRequiredError,
    ReplicateRequiresFreshPolicyError,
)
from src.reference.partition import PARTITION_ALGORITHM_VERSION
from src.reference.reference_audit import ReferenceAuditLog
from src.reference.reference_cache import ReferenceResultCache
from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EXECUTION_PROFILE_ID_FULL,
    EXECUTION_PROTOCOL_VERSION,
    FULL_EXECUTION_PROFILE,
    ReferenceCase,
    ReferenceTaskEvidence,
)
from src.reference.reference_orchestrator import (
    MappingEvidenceResolver,
    OrchestrationConfig,
    ReferenceOrchestrator,
    RetryPolicy,
    WorkItem,
    WorkItemDisposition,
)
from src.reference.result_schema import ReferenceRunContext, ReferenceTaskResult

_ENTRY_POINT = "double"
_PROMPT = f"def {_ENTRY_POINT}(n):\n"
_CANONICAL_SOLUTION = "    return n * 2\n"
_TASK_ID = "Test/0"
_CORRECT_CANDIDATE_CODE = "def double(n):\n    return n * 2\n"

_DATASET_CHECKSUM = "fe585eb4df8c88d844eeb463ea4d0302"
_TASK_MANIFEST_CHECKSUM = "d" * 64


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _oracle_record(task_id: str, case_id: str, n: int) -> Any:
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


def _evidence(task_id: str = _TASK_ID, num_cases: int = 1) -> ReferenceTaskEvidence:
    cases = tuple(
        ReferenceCase(
            case_id=f"c{i}", args=(i + 1,), oracle_record=_oracle_record(task_id, f"c{i}", i + 1)
        )
        for i in range(num_cases)
    )
    return ReferenceTaskEvidence(
        task_id=task_id,
        entry_point=_ENTRY_POINT,
        comparison_profile=comparison_profile_for_task(_ENTRY_POINT, atol=0.0),
        cases=cases,
        oracle_version=ORACLE_ALGORITHM_VERSION,
        partition_version=PARTITION_ALGORITHM_VERSION,
        dataset_version=HUMANEVAL_PLUS_VERSION,
        protocol_version=EXECUTION_PROTOCOL_VERSION,
        dataset_checksum=_DATASET_CHECKSUM,
        task_manifest_checksum=_TASK_MANIFEST_CHECKSUM,
    )


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
    task_evaluation_replicate_id: int = 0,
) -> WorkItem:
    return WorkItem(
        work_item_id=work_item_id,
        input_ordinal=input_ordinal,
        task_id=task_id,
        candidate_id=f"cand-{work_item_id}",
        candidate_sha256=_sha256(candidate_code),
        candidate_code=candidate_code,
        run_context=_run_context(),
        task_evaluation_replicate_id=task_evaluation_replicate_id,
    )


def _execution_result(
    status: ExecutionStatus, return_value: object, invocation_id: str
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


class RecordingBackend(ExecutionBackend):
    """Always returns the correct doubled value for COMPLETED calls."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.call_count = 0

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        with self._lock:
            invocation_id = f"inv-{self.call_count}"
            self.call_count += 1
        n = request.args[0]
        return _execution_result(ExecutionStatus.COMPLETED, n * 2, invocation_id)


class WrongAnswerBackend(ExecutionBackend):
    """Always returns a wrong value -- a VALID but q_ref_task=0.0 measurement."""

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        n = request.args[0]
        return _execution_result(ExecutionStatus.COMPLETED, n * 2 + 1, "inv-wrong")


@dataclass
class RecordedTraceCall:
    """One captured call to a FakeTraceRecorder."""

    work_item_id: str
    task_evaluation_replicate_id: int
    attempts: int
    disposition: WorkItemDisposition
    has_result: bool


@dataclass
class FakeTraceRecorder:
    """In-memory TraceRecorder: records every call, optionally raising to
    simulate a durable-write failure."""

    fail: bool = False
    calls: list[RecordedTraceCall] = field(default_factory=list)

    def record_fresh_attempt(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        work_item: WorkItem,
        evidence: ReferenceTaskEvidence,
        task_evaluation_replicate_id: int,
        attempts: int,
        disposition: WorkItemDisposition,
        task_result: ReferenceTaskResult | None,
    ) -> None:
        """Record the call, or raise if configured to simulate failure."""
        del evidence
        if self.fail:
            raise RuntimeError("simulated trace-write failure")
        self.calls.append(
            RecordedTraceCall(
                work_item.work_item_id,
                task_evaluation_replicate_id,
                attempts,
                disposition,
                task_result is not None,
            )
        )


def _orchestrator(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    tmp_path: Path,
    *,
    cache_policy: CachePolicy = CachePolicy.CACHE_FIRST,
    trace_recorder: Any = None,
    backend_factory: Callable[[], ExecutionBackend] | None = None,
    evidence_by_task: dict[str, ReferenceTaskEvidence] | None = None,
    max_workers: int = 2,
    max_in_flight: int = 2,
    cache: ReferenceResultCache | None = None,
) -> tuple[ReferenceOrchestrator, ReferenceResultCache, ReferenceAuditLog]:
    resolved_cache = cache if cache is not None else ReferenceResultCache(tmp_path / "cache")
    audit_log = ReferenceAuditLog(tmp_path / "audit.jsonl")
    evidence_map = evidence_by_task if evidence_by_task is not None else {_TASK_ID: _evidence()}
    orchestrator = ReferenceOrchestrator(
        cache=resolved_cache,
        audit_log=audit_log,
        evidence_resolver=MappingEvidenceResolver(evidence_map),
        backend_factory=backend_factory if backend_factory is not None else RecordingBackend,
        config=OrchestrationConfig(
            max_workers=max_workers,
            max_in_flight=max_in_flight,
            retry_policy=RetryPolicy(max_attempts=3),
            profile=FULL_EXECUTION_PROFILE,
            cache_policy=cache_policy,
            trace_recorder=trace_recorder,
        ),
    )
    return orchestrator, resolved_cache, audit_log


# ---------------------------------------------------------------------------
# CachePolicy defaults and configuration validation
# ---------------------------------------------------------------------------


def test_cache_first_remains_the_default() -> None:
    """OrchestrationConfig.cache_policy defaults to CACHE_FIRST."""
    config = OrchestrationConfig(max_workers=1, max_in_flight=1)
    assert config.cache_policy == CachePolicy.CACHE_FIRST
    assert config.trace_recorder is None


def test_fresh_policy_requires_trace_recorder() -> None:
    """Both fresh policies refuse construction without a trace_recorder."""
    for policy in (
        CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
    ):
        try:
            OrchestrationConfig(max_workers=1, max_in_flight=1, cache_policy=policy)
        except CalibrationTraceRequiredError:
            pass
        else:
            raise AssertionError(f"{policy} did not require a trace_recorder")


def test_fresh_policy_with_trace_recorder_constructs_fine() -> None:
    """Supplying a trace_recorder satisfies the fresh-policy requirement."""
    OrchestrationConfig(
        max_workers=1,
        max_in_flight=1,
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=FakeTraceRecorder(),
    )


def test_replicate_under_cache_first_is_rejected(tmp_path: Path) -> None:
    """A nonzero task_evaluation_replicate_id under CACHE_FIRST is rejected
    outright -- a repeated calibration coordinate must never silently run
    under production cache-first semantics."""
    orchestrator, _, _ = _orchestrator(tmp_path)
    item = _work_item("wi-0", 0, task_evaluation_replicate_id=1)
    try:
        orchestrator.run([item], run_id="run-1")
    except ReplicateRequiresFreshPolicyError:
        pass
    else:
        raise AssertionError("expected ReplicateRequiresFreshPolicyError")


def test_zero_replicate_under_cache_first_is_unaffected(tmp_path: Path) -> None:
    """The default task_evaluation_replicate_id=0 never triggers rejection
    under CACHE_FIRST -- existing callers are completely unaffected."""
    orchestrator, _, _ = _orchestrator(tmp_path)
    item = _work_item("wi-0", 0)
    summary = orchestrator.run([item], run_id="run-1")
    assert summary.outcomes[0].disposition == WorkItemDisposition.EXECUTED_VALID


# ---------------------------------------------------------------------------
# Prepopulated cache cannot suppress evaluator execution under fresh policies
# ---------------------------------------------------------------------------


def test_fresh_measure_and_optionally_cache_bypasses_existing_valid_entry(tmp_path: Path) -> None:
    """FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID still invokes the evaluator
    even when an identical valid cache entry already exists. Because this
    deterministic candidate's fresh result is *logically equivalent* to the
    already-cached entry (same content, different evaluated_at/duration),
    the existing, unmodified equivalent-write-reconciliation logic folds it
    into CACHE_HIT -- exactly the accepted "preserve existing cache
    conflict behavior" requirement, not a suppressed execution."""
    cache = ReferenceResultCache(tmp_path / "cache")
    seed_backend = RecordingBackend()
    seed_orchestrator, _, _ = _orchestrator(
        tmp_path, cache=cache, backend_factory=lambda: seed_backend
    )
    item = _work_item("wi-0", 0)
    seed_orchestrator.run([item], run_id="seed")
    assert seed_backend.call_count == 1

    fresh_backend = RecordingBackend()
    recorder = FakeTraceRecorder()
    fresh_orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache=cache,
        backend_factory=lambda: fresh_backend,
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
    )
    summary = fresh_orchestrator.run([item], run_id="fresh")

    assert fresh_backend.call_count == 1, (
        "a prepopulated valid cache entry must not suppress execution"
    )
    assert summary.outcomes[0].disposition == WorkItemDisposition.CACHE_HIT
    assert summary.outcomes[0].detail == "concurrent equivalent write reconciled as a cache hit"
    assert len(recorder.calls) == 1, "the trace is recorded for the fresh attempt regardless"


def test_fresh_measure_no_cache_write_bypasses_existing_valid_entry(tmp_path: Path) -> None:
    """FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE also invokes the evaluator
    even when an identical valid cache entry already exists."""
    cache = ReferenceResultCache(tmp_path / "cache")
    seed_backend = RecordingBackend()
    seed_orchestrator, _, _ = _orchestrator(
        tmp_path, cache=cache, backend_factory=lambda: seed_backend
    )
    item = _work_item("wi-0", 0)
    seed_orchestrator.run([item], run_id="seed")
    assert seed_backend.call_count == 1

    fresh_backend = RecordingBackend()
    recorder = FakeTraceRecorder()
    fresh_orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache=cache,
        backend_factory=lambda: fresh_backend,
        cache_policy=CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
        trace_recorder=recorder,
    )
    summary = fresh_orchestrator.run([item], run_id="fresh")

    assert fresh_backend.call_count == 1
    assert summary.outcomes[0].disposition == WorkItemDisposition.EXECUTED_VALID_UNCACHED
    assert len(recorder.calls) == 1


# ---------------------------------------------------------------------------
# Replicate admission: N replicates -> N evaluator calls; cache keys unaffected
# ---------------------------------------------------------------------------


def test_n_replicates_cause_exactly_n_evaluator_calls(tmp_path: Path) -> None:
    """N task-level replicates of the same task/candidate/context cause
    exactly N evaluator calls, not 1 (deduplicated) and not 0 (suppressed)."""
    backend = RecordingBackend()
    recorder = FakeTraceRecorder()
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        backend_factory=lambda: backend,
        cache_policy=CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
        trace_recorder=recorder,
        max_workers=1,
        max_in_flight=1,
    )
    replicate_count = 5
    items = [
        _work_item(f"wi-{i}", i, task_evaluation_replicate_id=i) for i in range(replicate_count)
    ]

    summary = orchestrator.run(items, run_id="run-1")

    assert backend.call_count == replicate_count
    assert summary.unique_cache_keys == replicate_count
    assert len(recorder.calls) == replicate_count
    assert all(
        o.disposition == WorkItemDisposition.EXECUTED_VALID_UNCACHED for o in summary.outcomes
    )


def test_replicate_ids_do_not_alter_cache_key_digest(tmp_path: Path) -> None:
    """Two work items differing only in task_evaluation_replicate_id
    produce the exact same production cache-key digest."""
    recorder = FakeTraceRecorder()
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache_policy=CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
        trace_recorder=recorder,
        max_workers=1,
        max_in_flight=1,
    )
    items = [
        _work_item("wi-0", 0, task_evaluation_replicate_id=0),
        _work_item("wi-1", 1, task_evaluation_replicate_id=7),
    ]

    summary = orchestrator.run(items, run_id="run-1")

    digests = {o.cache_key_digest for o in summary.outcomes}
    assert len(digests) == 1, "replicate id must never enter the production cache key"


def test_h6_style_execution_leaves_production_cache_byte_for_byte_unchanged(tmp_path: Path) -> None:
    """A full repeated-measurement (H.6-style) run under
    FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE leaves the production cache
    directory byte-for-byte unchanged."""
    cache = ReferenceResultCache(tmp_path / "cache")
    seed_orchestrator, _, _ = _orchestrator(tmp_path, cache=cache)
    seed_item = _work_item("seed", 0)
    seed_orchestrator.run([seed_item], run_id="seed")

    before = {
        path.name: path.read_bytes() for path in cache.cache_dir.iterdir()
    }
    assert before, "seed run should have written exactly one cache entry"

    recorder = FakeTraceRecorder()
    n_replicates = 20
    h6_orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache=cache,
        cache_policy=CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
        trace_recorder=recorder,
        max_workers=1,
        max_in_flight=1,
    )
    items = [_work_item(f"rep-{i}", i, task_evaluation_replicate_id=i) for i in range(n_replicates)]
    h6_orchestrator.run(items, run_id="h6-run")

    after = {path.name: path.read_bytes() for path in cache.cache_dir.iterdir()}
    assert after == before
    assert len(recorder.calls) == n_replicates


# ---------------------------------------------------------------------------
# Trace-before-cache ordering and durability
# ---------------------------------------------------------------------------


class _OrderCheckingTraceRecorder:
    """Confirms the production cache is still empty at the moment the
    trace is recorded -- direct evidence of trace-before-cache-write
    ordering, not merely a side effect."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self.observed_cache_dir_empty_at_trace_time: bool | None = None

    def record_fresh_attempt(self, **_kwargs: Any) -> None:
        """Record whether the cache directory is empty right now."""
        self.observed_cache_dir_empty_at_trace_time = not any(self._cache_dir.iterdir())


def test_trace_persistence_occurs_before_any_optional_cache_write(tmp_path: Path) -> None:
    """The calibration trace is durably recorded before cache.put() is ever
    attempted under FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID."""
    cache = ReferenceResultCache(tmp_path / "cache")
    recorder = _OrderCheckingTraceRecorder(cache.cache_dir)
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache=cache,
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    assert recorder.observed_cache_dir_empty_at_trace_time is True
    assert summary.outcomes[0].disposition == WorkItemDisposition.EXECUTED_VALID
    assert len(list(cache.cache_dir.glob("*.json"))) == 1


def test_trace_write_failure_prevents_cache_mutation(tmp_path: Path) -> None:
    """A raised trace-recorder failure propagates and the production cache
    is never mutated for that attempt."""
    cache = ReferenceResultCache(tmp_path / "cache")
    recorder = FakeTraceRecorder(fail=True)
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache=cache,
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
    )
    item = _work_item("wi-0", 0)

    try:
        orchestrator.run([item], run_id="run-1")
    except RuntimeError as exc:
        assert "simulated trace-write failure" in str(exc)
    else:
        raise AssertionError("expected the trace-recorder failure to propagate")

    assert not list(cache.cache_dir.glob("*.json")), (
        "cache must never be mutated after a trace-write failure"
    )


def test_trace_write_failure_prevents_cache_mutation_under_no_cache_write_policy(
    tmp_path: Path,
) -> None:
    """Same guarantee under FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE, whose
    own cache bypass must not be reached before the (failed) trace call."""
    cache = ReferenceResultCache(tmp_path / "cache")
    recorder = FakeTraceRecorder(fail=True)
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache=cache,
        cache_policy=CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
        trace_recorder=recorder,
    )
    item = _work_item("wi-0", 0)

    try:
        orchestrator.run([item], run_id="run-1")
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the trace-recorder failure to propagate")

    assert not list(cache.cache_dir.glob("*.json"))


def test_calibration_trace_recorder_with_real_trace_store_end_to_end(tmp_path: Path) -> None:
    """The production-usable CalibrationTraceRecorder, wired to a real
    (temporary) CalibrationTraceStore and a synthetic record builder,
    durably appends one CalibrationTaskEvaluationRecord per fresh attempt
    before any cache write."""
    trace_store = CalibrationTraceStore(tmp_path / "trace.jsonl")

    def build_record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        *,
        work_item: WorkItem,
        evidence: ReferenceTaskEvidence,
        task_evaluation_replicate_id: int,
        attempts: int,
        disposition: WorkItemDisposition,
        task_result: ReferenceTaskResult | None,
    ) -> CalibrationTaskEvaluationRecord:
        del attempts
        context = CalibrationRunContext(
            calibration_schema_version=CALIBRATION_SCHEMA_VERSION,
            stage=CalibrationStage.H3,
            calibration_run_id="calib-run-1",
            execution_profile_id="docker-megb03h-diagnostic-v1",
            evaluator_version="megb-03h-diagnostic-evaluator-v1",
            execution_protocol_version=EXECUTION_PROTOCOL_VERSION,
            dataset_version=HUMANEVAL_PLUS_VERSION,
            dataset_checksum=_DATASET_CHECKSUM,
            partition_version=PARTITION_ALGORITHM_VERSION,
            oracle_version=ORACLE_ALGORITHM_VERSION,
            comparison_profile_version=COMPARISON_PROFILE_VERSION,
            task_manifest_checksum=_TASK_MANIFEST_CHECKSUM,
        )
        assert task_result is not None
        return CalibrationTaskEvaluationRecord(
            calibration_schema_version=CALIBRATION_SCHEMA_VERSION,
            context=context,
            task_id=work_item.task_id,
            candidate_sha256=work_item.candidate_sha256,
            reference_case_checksum=evidence.reference_case_checksum,
            task_evaluation_replicate_id=task_evaluation_replicate_id,
            measurement_status=task_result.status,
            q_ref_task=task_result.q_ref_task,
            first_failure_category=task_result.first_failure_category,
            reference_case_total=task_result.reference_case_total,
            reference_case_pass_count=task_result.reference_case_pass_count,
            work_item_disposition=disposition,
            contributing_invocation_ids=(),
            contributing_invocation_content_checksums=(),
            evaluated_at="2026-08-03T00:00:00Z",
        )

    recorder = CalibrationTraceRecorder(build_record=build_record, sink=trace_store)
    orchestrator, cache, _ = _orchestrator(
        tmp_path,
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    assert summary.outcomes[0].disposition == WorkItemDisposition.EXECUTED_VALID
    _invocations, task_evaluations = trace_store.read_all()
    assert len(task_evaluations) == 1
    assert task_evaluations[0].task_id == _TASK_ID
    assert len(list(cache.cache_dir.glob("*.json"))) == 1


# ---------------------------------------------------------------------------
# Accepted classifications preserved under a fresh policy
# ---------------------------------------------------------------------------


def test_non_cacheable_invalid_result_never_touches_cache_under_fresh_policy(
    tmp_path: Path,
) -> None:
    """A non-VALID (candidate-failure-free but oracle-invalid-style)
    measurement never reaches cache.put() under a fresh policy, and its
    disposition classification is unaffected by the policy."""
    from src.reference.oracle import ORACLE_STATUS_GENERATION_FAILED, OracleRecord  # pylint: disable=import-outside-toplevel

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
    evidence = ReferenceTaskEvidence(
        task_id=_TASK_ID,
        entry_point=_ENTRY_POINT,
        comparison_profile=profile,
        cases=(broken_case,),
        oracle_version=ORACLE_ALGORITHM_VERSION,
        partition_version=PARTITION_ALGORITHM_VERSION,
        dataset_version=HUMANEVAL_PLUS_VERSION,
        protocol_version=EXECUTION_PROTOCOL_VERSION,
        dataset_checksum=_DATASET_CHECKSUM,
        task_manifest_checksum=_TASK_MANIFEST_CHECKSUM,
    )
    recorder = FakeTraceRecorder()
    orchestrator, cache, _ = _orchestrator(
        tmp_path,
        evidence_by_task={_TASK_ID: evidence},
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    assert summary.outcomes[0].disposition == WorkItemDisposition.EXECUTED_INVALID
    assert not list(cache.cache_dir.glob("*.json"))


def test_conflicting_write_classification_preserved_under_fresh_policy(tmp_path: Path) -> None:
    """A genuinely conflicting (non-equivalent) cache entry still yields
    CACHE_CONFLICT_BLOCKED under FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
    exactly as it would under CACHE_FIRST."""
    cache = ReferenceResultCache(tmp_path / "cache")
    seed_orchestrator, _, _ = _orchestrator(
        tmp_path, cache=cache, backend_factory=WrongAnswerBackend
    )
    seed_item = _work_item("seed", 0)
    seed_orchestrator.run([seed_item], run_id="seed")
    assert len(list(cache.cache_dir.glob("*.json"))) == 1

    recorder = FakeTraceRecorder()
    fresh_orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache=cache,
        backend_factory=RecordingBackend,
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
    )
    fresh_item = _work_item("wi-0", 0)

    summary = fresh_orchestrator.run([fresh_item], run_id="run-1")

    assert summary.outcomes[0].disposition == WorkItemDisposition.CACHE_CONFLICT_BLOCKED
    assert len(recorder.calls) == 1, "the trace is still recorded even though caching is blocked"


# ---------------------------------------------------------------------------
# Deterministic ordering, association, and cancellation for replicates
# ---------------------------------------------------------------------------


def test_concurrent_replicates_return_in_deterministic_input_order(tmp_path: Path) -> None:
    """Replicates submitted out of input_ordinal order, executed
    concurrently, still return sorted by input_ordinal with correct
    work_item_id associations."""
    recorder = FakeTraceRecorder()
    replicate_count = 6
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache_policy=CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
        trace_recorder=recorder,
        max_workers=replicate_count,
        max_in_flight=replicate_count,
    )
    # Submitted with replicate_id deliberately reversed relative to
    # input_ordinal, to prove the final order depends on input_ordinal
    # alone, never on replicate id or completion order.
    items = [
        _work_item(f"wi-{i}", i, task_evaluation_replicate_id=replicate_count - 1 - i)
        for i in range(replicate_count)
    ]

    summary = orchestrator.run(items, run_id="run-1")

    assert [o.input_ordinal for o in summary.outcomes] == list(range(replicate_count))
    assert [o.work_item_id for o in summary.outcomes] == [f"wi-{i}" for i in range(replicate_count)]
    assert all(
        o.disposition == WorkItemDisposition.EXECUTED_VALID_UNCACHED for o in summary.outcomes
    )


def test_cancellation_does_not_deduplicate_distinct_replicates(  # pylint: disable=too-many-locals
    tmp_path: Path,
) -> None:
    """Cancelling mid-run over N replicates never merges or drops distinct
    replicate identities: each admitted replicate gets its own outcome, and
    every not-yet-admitted replicate is NOT_STARTED, never silently
    treated as equivalent to one that did run."""
    cancelled = threading.Event()
    call_log: list[int] = []

    class _OneShotThenCancelBackend(ExecutionBackend):
        def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
            call_log.append(request.args[0])
            cancelled.set()
            n = request.args[0]
            return _execution_result(ExecutionStatus.COMPLETED, n * 2, f"inv-{n}")

    recorder = FakeTraceRecorder()
    replicate_count = 5
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        backend_factory=_OneShotThenCancelBackend,
        cache_policy=CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
        trace_recorder=recorder,
        max_workers=1,
        max_in_flight=1,
    )
    items = [
        _work_item(f"wi-{i}", i, task_evaluation_replicate_id=i) for i in range(replicate_count)
    ]

    summary = orchestrator.run(items, run_id="run-1", cancellation_event=cancelled)

    assert summary.interrupted is True
    started = [o for o in summary.outcomes if o.disposition != WorkItemDisposition.NOT_STARTED]
    unstarted = [o for o in summary.outcomes if o.disposition == WorkItemDisposition.NOT_STARTED]
    assert len(started) == 1
    assert len(unstarted) == replicate_count - 1
    # Every started/unstarted outcome maps back to its own distinct
    # work_item_id -- no two replicates were coalesced into one outcome.
    assert len({o.work_item_id for o in summary.outcomes}) == replicate_count

    # Resuming must execute exactly the remaining, still-distinct replicates
    # -- never silently skip them as if already satisfied by the one that
    # did complete (they share a cache key but not a replicate id).
    resumed_recorder = FakeTraceRecorder()
    resumed_orchestrator, _, _ = _orchestrator(
        tmp_path,
        backend_factory=RecordingBackend,
        cache_policy=CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
        trace_recorder=resumed_recorder,
        max_workers=1,
        max_in_flight=1,
    )
    started_ids = {o.work_item_id for o in started}
    remaining_items = [item for item in items if item.work_item_id not in started_ids]
    resumed_summary = resumed_orchestrator.run(remaining_items, run_id="run-2")

    assert resumed_summary.unstarted_work_items == 0
    assert len(resumed_recorder.calls) == replicate_count - 1
