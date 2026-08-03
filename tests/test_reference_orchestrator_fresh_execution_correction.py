"""Tests for the MEGB-03H.2B.1 fresh-execution-semantics correction
(post-second-review): cache-bypass must never be recorded as MISS, a fresh
execution must never become CACHE_HIT, every retry attempt must retain a
distinct typed identity that can propagate into
:class:`~src.reference.calibration_schema.CalibrationInvocationRecord.attempt_id`,
and a trace-persistence failure must be a typed, chained exception rather
than an arbitrary one.

Shares fixtures with the sibling H.2B.1 test modules via
``tests/_reference_orchestrator_cache_policy_fixtures.py``, kept in its own
file purely for pylint's per-module line-count limit. No real privileged
corpus access, no Docker.
"""

# See _reference_orchestrator_cache_policy_fixtures.py's own note: these
# fixtures intentionally mirror patterns already present in
# test_reference_evaluator.py -- suppressing here rather than coupling this
# module's fixtures to that other, unrelated test module's internals.
# pylint: disable=duplicate-code

from pathlib import Path

from src.evaluators.schema import FailureCategory
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionStatus,
)
from src.reference.calibration_schema import (
    CALIBRATION_SCHEMA_VERSION,
    CalibrationInvocationRecord,
    CalibrationRunContext,
    CalibrationStage,
    CalibrationTaskEvaluationRecord,
    TelemetryUnavailableReason,
    reconcile_task_evaluation,
)
from src.reference.calibration_trace import CalibrationTraceStore
from src.reference.oracle import COMPARISON_PROFILE_VERSION, ORACLE_ALGORITHM_VERSION
from src.reference.orchestration_trace import (
    CachePolicy,
    CalibrationTracePersistenceError,
    FreshExecutionAttempt,
)
from src.reference.partition import PARTITION_ALGORITHM_VERSION
from src.reference.reference_cache import CacheDisposition, ReferenceResultCache
from src.reference.reference_evaluator import EXECUTION_PROTOCOL_VERSION, ReferenceTaskEvidence
from src.reference.reference_orchestrator import WorkItem, WorkItemDisposition
from src.reference.result_schema import MeasurementStatus, ReferenceTaskResult
from tests._calibration_fixtures import (
    make_collector_method_provenance,
    make_host_runtime_context,
    make_telemetry_collection_policy,
)
from tests._reference_orchestrator_cache_policy_fixtures import (
    FakeTraceRecorder,
    OverrideSequenceBackend,
    RaisingBackend,
    RecordingBackend,
    WrongAnswerBackend,
)
from tests._reference_orchestrator_cache_policy_fixtures import (
    DATASET_CHECKSUM as _DATASET_CHECKSUM,
)
from tests._reference_orchestrator_cache_policy_fixtures import (
    TASK_MANIFEST_CHECKSUM as _TASK_MANIFEST_CHECKSUM,
)
from tests._reference_orchestrator_cache_policy_fixtures import orchestrator as _orchestrator
from tests._reference_orchestrator_cache_policy_fixtures import work_item as _work_item

_FRESH_POLICIES = (
    CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
    CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
)

# ---------------------------------------------------------------------------
# 1. Never represent cache bypass as a miss
# ---------------------------------------------------------------------------


def test_bypassed_by_policy_added_to_cache_disposition() -> None:
    """A dedicated CacheDisposition value exists for a deliberate bypass,
    distinct from MISS (a real, attempted, empty lookup)."""
    assert CacheDisposition.BYPASSED_BY_POLICY.value == "BYPASSED_BY_POLICY"
    assert CacheDisposition.MISS.value == "MISS"


def test_audit_records_bypassed_by_policy_for_uncached_valid_result(tmp_path: Path) -> None:
    """A valid fresh result under FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE is
    audited as BYPASSED_BY_POLICY, never MISS."""
    recorder = FakeTraceRecorder()
    orchestrator, _, audit_log = _orchestrator(
        tmp_path,
        cache_policy=CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
        trace_recorder=recorder,
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    assert summary.outcomes[0].disposition == WorkItemDisposition.EXECUTED_VALID_UNCACHED
    assert summary.outcomes[0].cache_write_disposition == CacheDisposition.BYPASSED_BY_POLICY
    records = audit_log.read_all()
    assert len(records) == 1
    assert records[0].cache_disposition == "BYPASSED_BY_POLICY"


def test_audit_records_bypassed_by_policy_for_non_valid_fresh_attempt(tmp_path: Path) -> None:
    """A non-VALID result under a fresh policy is audited as
    BYPASSED_BY_POLICY (the cache was never consulted for it), not MISS --
    CACHE_FIRST's own MISS labeling for the analogous case is unchanged."""
    for cache_policy in _FRESH_POLICIES:
        policy_tmp = tmp_path / cache_policy.value
        policy_tmp.mkdir()
        recorder = FakeTraceRecorder()
        orchestrator, _, audit_log = _orchestrator(
            policy_tmp,
            backend_factory=lambda: OverrideSequenceBackend([ExecutionStatus.PROTOCOL_ERROR]),
            cache_policy=cache_policy,
            trace_recorder=recorder,
        )
        item = _work_item("wi-0", 0)

        orchestrator.run([item], run_id=f"run-{cache_policy.value}")

        records = audit_log.read_all()
        assert len(records) == 1
        assert records[0].cache_disposition == "BYPASSED_BY_POLICY"


def test_cache_first_non_valid_attempt_still_audited_as_miss(tmp_path: Path) -> None:
    """CACHE_FIRST's own MISS labeling is unchanged -- a real cache.get()
    genuinely preceded this attempt and genuinely found nothing."""
    orchestrator, _, audit_log = _orchestrator(
        tmp_path,
        backend_factory=lambda: OverrideSequenceBackend([ExecutionStatus.PROTOCOL_ERROR]),
    )
    item = _work_item("wi-0", 0)

    orchestrator.run([item], run_id="run-1")

    records = audit_log.read_all()
    assert len(records) == 1
    assert records[0].cache_disposition == "MISS"


# ---------------------------------------------------------------------------
# 2. Fresh execution must never become CACHE_HIT
# ---------------------------------------------------------------------------


def test_no_fresh_policy_path_produces_cache_hit(tmp_path: Path) -> None:
    """Across cold-cache, reconciled-equivalent, and genuinely-conflicting
    scenarios, neither fresh policy ever produces WorkItemDisposition.CACHE_HIT."""
    # Cold cache: nothing pre-exists.
    def _cold(cache_policy: CachePolicy, tmp: Path) -> WorkItemDisposition:
        recorder = FakeTraceRecorder()
        orchestrator, _, _ = _orchestrator(
            tmp, cache_policy=cache_policy, trace_recorder=recorder
        )
        item = _work_item("wi-0", 0)
        return orchestrator.run([item], run_id="run").outcomes[0].disposition

    # Reconciled-equivalent: an identical valid entry already exists.
    def _reconciled(cache_policy: CachePolicy, tmp: Path) -> WorkItemDisposition:
        cache = ReferenceResultCache(tmp / "cache")
        seed_orchestrator, _, _ = _orchestrator(tmp, cache=cache)
        seed_item = _work_item("seed", 0)
        seed_orchestrator.run([seed_item], run_id="seed")

        recorder = FakeTraceRecorder()
        orchestrator, _, _ = _orchestrator(
            tmp, cache=cache, cache_policy=cache_policy, trace_recorder=recorder
        )
        item = _work_item("wi-0", 0)
        return orchestrator.run([item], run_id="fresh").outcomes[0].disposition

    # Genuinely conflicting: a different valid entry already exists.
    def _conflicting(cache_policy: CachePolicy, tmp: Path) -> WorkItemDisposition:
        cache = ReferenceResultCache(tmp / "cache")
        seed_orchestrator, _, _ = _orchestrator(
            tmp, cache=cache, backend_factory=WrongAnswerBackend
        )
        seed_item = _work_item("seed", 0)
        seed_orchestrator.run([seed_item], run_id="seed")

        recorder = FakeTraceRecorder()
        orchestrator, _, _ = _orchestrator(
            tmp,
            cache=cache,
            backend_factory=RecordingBackend,
            cache_policy=cache_policy,
            trace_recorder=recorder,
        )
        item = _work_item("wi-0", 0)
        return orchestrator.run([item], run_id="fresh").outcomes[0].disposition

    for index, scenario in enumerate((_cold, _reconciled, _conflicting)):
        for policy in _FRESH_POLICIES:
            never_writes = policy == CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE
            if scenario is _conflicting and never_writes:
                continue  # this policy never writes, so no conflict is ever possible
            scenario_tmp = tmp_path / f"scenario-{index}-{policy.value}"
            scenario_tmp.mkdir()
            disposition = scenario(policy, scenario_tmp)
            assert disposition != WorkItemDisposition.CACHE_HIT, (
                f"{scenario.__name__} under {policy.value} must never be CACHE_HIT, got "
                f"{disposition.value}"
            )


# ---------------------------------------------------------------------------
# 3. Preserve distinct retry attempts
# ---------------------------------------------------------------------------


def test_infrastructure_failure_then_success_produces_two_distinct_attempt_ids(
    tmp_path: Path,
) -> None:
    """An infrastructure-failure attempt followed by a successful retry
    produces exactly two FreshExecutionAttempt records, attempt_id 1 and 2,
    neither overwriting the other."""
    recorder = FakeTraceRecorder()
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        backend_factory=lambda: OverrideSequenceBackend(
            [ExecutionStatus.INFRASTRUCTURE_ERROR, ExecutionStatus.COMPLETED]
        ),
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    assert summary.outcomes[0].disposition == WorkItemDisposition.EXECUTED_VALID
    assert len(recorder.calls) == 1
    attempt_records = recorder.calls[0].attempt_records
    assert [record.attempt_id for record in attempt_records] == [1, 2]
    assert attempt_records[0].task_result is not None
    assert attempt_records[0].task_result.status == MeasurementStatus.INVALID_INFRASTRUCTURE
    assert attempt_records[0].exception_type_name is None
    assert attempt_records[1].task_result is not None
    assert attempt_records[1].task_result.status == MeasurementStatus.VALID
    assert attempt_records[1].exception_type_name is None


def test_retry_exhaustion_preserves_all_attempts(tmp_path: Path) -> None:
    """Retry exhaustion (every attempt INVALID_INFRASTRUCTURE) preserves
    every one of the N attempts distinctly -- none are erased by the final
    RETRY_EXHAUSTED outcome."""
    n_attempts = 3
    recorder = FakeTraceRecorder()
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        backend_factory=lambda: OverrideSequenceBackend(
            [ExecutionStatus.INFRASTRUCTURE_ERROR] * n_attempts
        ),
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
        max_attempts=n_attempts,
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    assert summary.outcomes[0].disposition == WorkItemDisposition.RETRY_EXHAUSTED
    attempt_records = recorder.calls[0].attempt_records
    assert len(attempt_records) == n_attempts
    assert [record.attempt_id for record in attempt_records] == list(range(1, n_attempts + 1))
    assert all(
        record.task_result is not None
        and record.task_result.status == MeasurementStatus.INVALID_INFRASTRUCTURE
        for record in attempt_records
    )


def test_evaluator_exception_preserves_typed_attempt_evidence_without_raw_message(
    tmp_path: Path,
) -> None:
    """A raised backend exception preserves a typed, allowlisted
    exception_type_name per attempt -- never the raw exception message."""

    class _SensitiveRaisingBackend(RaisingBackend):
        def execute(
            self, request: CandidateExecutionRequest
        ) -> CandidateExecutionResult:
            raise RuntimeError("SENSITIVE-MARKER-should-never-be-persisted")

    recorder = FakeTraceRecorder()
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        backend_factory=_SensitiveRaisingBackend,
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
        max_attempts=2,
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    assert summary.outcomes[0].disposition == WorkItemDisposition.RETRY_EXHAUSTED
    attempt_records = recorder.calls[0].attempt_records
    assert len(attempt_records) == 2
    assert all(record.exception_type_name == "RuntimeError" for record in attempt_records)
    assert all(record.task_result is None for record in attempt_records)
    for record in attempt_records:
        assert "SENSITIVE-MARKER" not in repr(record)
    assert "SENSITIVE-MARKER" not in summary.outcomes[0].detail


def test_fresh_execution_attempt_requires_exactly_one_of_result_or_exception() -> None:
    """FreshExecutionAttempt itself refuses to represent an attempt with
    both a result and an exception, or neither."""
    try:
        FreshExecutionAttempt(1, None, None)
    except ValueError:
        pass
    else:
        raise AssertionError("expected a ValueError for neither field set")


def _build_invocation_record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    attempt: FreshExecutionAttempt,
    *,
    work_item: WorkItem,
    evidence: ReferenceTaskEvidence,
    context: CalibrationRunContext,
    task_evaluation_replicate_id: int,
) -> CalibrationInvocationRecord:
    """Synthetic H.2C-style mapping of one FreshExecutionAttempt into a
    real CalibrationInvocationRecord, proving attempt_id propagates through
    the trace-recorder boundary into this H.2A-accepted schema field."""
    if attempt.task_result is not None:
        measurement_status = attempt.task_result.status
        execution_status = (
            ExecutionStatus.COMPLETED
            if measurement_status == MeasurementStatus.VALID
            else ExecutionStatus.INFRASTRUCTURE_ERROR
        )
        first_failure_category = attempt.task_result.first_failure_category
    else:
        measurement_status = MeasurementStatus.INVALID_INFRASTRUCTURE
        execution_status = ExecutionStatus.INFRASTRUCTURE_ERROR
        first_failure_category = FailureCategory.INFRASTRUCTURE_ERROR
    return CalibrationInvocationRecord(
        calibration_schema_version=CALIBRATION_SCHEMA_VERSION,
        context=context,
        task_id=work_item.task_id,
        candidate_sha256=work_item.candidate_sha256,
        reference_case_checksum=evidence.reference_case_checksum,
        case_ordinal=0,
        task_evaluation_replicate_id=task_evaluation_replicate_id,
        attempt_id=attempt.attempt_id,
        invocation_id=f"{work_item.work_item_id}-attempt-{attempt.attempt_id}",
        invoked_at="2026-08-03T00:00:00Z",
        execution_status=execution_status,
        measurement_status=measurement_status,
        first_failure_category=first_failure_category,
        candidate_wall_time_sec=None,
        candidate_wall_time_quality=None,
        candidate_wall_time_unavailable_reason=TelemetryUnavailableReason.NOT_YET_INSTRUMENTED,
        controller_wall_time_sec=0.001,
        request_bytes=0,
        observed_response_bytes=None,
        observed_response_quality=None,
        observed_response_unavailable_reason=TelemetryUnavailableReason.NOT_YET_INSTRUMENTED,
        peak_memory_bytes=None,
        peak_memory_quality=None,
        peak_memory_unavailable_reason=TelemetryUnavailableReason.NOT_YET_INSTRUMENTED,
        peak_memory_provenance=make_collector_method_provenance(metric_id="peak_memory_bytes"),
        peak_process_count=None,
        peak_process_quality=None,
        peak_process_unavailable_reason=TelemetryUnavailableReason.NOT_YET_INSTRUMENTED,
        peak_process_provenance=make_collector_method_provenance(
            metric_id="peak_process_count"
        ),
        exit_code=None,
        terminating_signal=None,
        backend_id="fake",
        backend_version="1",
        runner_image_digest="sha256:fake",
    )


def _calibration_context() -> CalibrationRunContext:
    return CalibrationRunContext(
        calibration_schema_version=CALIBRATION_SCHEMA_VERSION,
        stage=CalibrationStage.H3,
        calibration_run_id="calib-run-1",
        execution_profile_id="docker-megb03h-diagnostic-v1",
        evaluator_version="megb-03h-diagnostic-evaluator-v1",
        execution_protocol_version=EXECUTION_PROTOCOL_VERSION,
        dataset_version="synthetic-v1",
        dataset_checksum=_DATASET_CHECKSUM,
        partition_version=PARTITION_ALGORITHM_VERSION,
        oracle_version=ORACLE_ALGORITHM_VERSION,
        comparison_profile_version=COMPARISON_PROFILE_VERSION,
        task_manifest_checksum=_TASK_MANIFEST_CHECKSUM,
        telemetry_collection_policy=make_telemetry_collection_policy(),
        host_runtime_context=make_host_runtime_context(),
    )


class _FullReconcilingTraceRecorder:
    """A TraceRecorder that builds one CalibrationInvocationRecord per
    FreshExecutionAttempt plus one terminal CalibrationTaskEvaluationRecord
    referencing all of them, appending both to a real CalibrationTraceStore
    -- proving the H.2B.1 boundary can carry attempt identity all the way
    into the already-accepted H.2A schema without any schema change."""

    def __init__(self, trace_store: CalibrationTraceStore) -> None:
        self._trace_store = trace_store
        self.built_task_evaluations: list[CalibrationTaskEvaluationRecord] = []

    def record_fresh_attempt(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        work_item: WorkItem,
        evidence: ReferenceTaskEvidence,
        task_evaluation_replicate_id: int,
        attempt_records: tuple[FreshExecutionAttempt, ...],
        disposition: WorkItemDisposition,
        task_result: ReferenceTaskResult | None,
    ) -> None:
        """Build and append one invocation record per attempt, plus one
        reconciling task-evaluation record."""
        context = _calibration_context()
        invocations = [
            _build_invocation_record(
                attempt,
                work_item=work_item,
                evidence=evidence,
                context=context,
                task_evaluation_replicate_id=task_evaluation_replicate_id,
            )
            for attempt in attempt_records
        ]
        for invocation in invocations:
            self._trace_store.append_invocation_record(invocation)

        # Only the terminal/eligible attempt (the final measured result)
        # contributes to the task's own measurement_status/q_ref_task --
        # earlier, non-contributing attempts are still referenced (so they
        # are never silently lost) but never double-counted as their own
        # scored task evaluation.
        assert task_result is not None
        ids = tuple(inv.invocation_id for inv in invocations)
        checksums = tuple(inv.record_checksum for inv in invocations)
        record = CalibrationTaskEvaluationRecord(
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
            contributing_invocation_ids=ids,
            contributing_invocation_content_checksums=checksums,
            evaluated_at="2026-08-03T00:00:00Z",
        )
        self._trace_store.append_task_evaluation_record(record)
        self.built_task_evaluations.append(record)


def test_attempt_ids_propagate_through_trace_recorder_into_invocation_records(
    tmp_path: Path,
) -> None:
    """attempt_id propagates from FreshExecutionAttempt all the way into
    real CalibrationInvocationRecord.attempt_id values, reconciled against
    one CalibrationTaskEvaluationRecord -- no H.2A schema change needed."""
    trace_store = CalibrationTraceStore(tmp_path / "trace.jsonl")
    recorder = _FullReconcilingTraceRecorder(trace_store)
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        backend_factory=lambda: OverrideSequenceBackend(
            [ExecutionStatus.INFRASTRUCTURE_ERROR, ExecutionStatus.COMPLETED]
        ),
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")

    assert summary.outcomes[0].disposition == WorkItemDisposition.EXECUTED_VALID
    invocations, task_evaluations = trace_store.read_all()
    assert [inv.attempt_id for inv in invocations] == [1, 2]
    assert len(task_evaluations) == 1
    assert task_evaluations[0].contributing_invocation_ids == tuple(
        inv.invocation_id for inv in invocations
    )
    # Reconciliation succeeds using only the already-accepted H.2A helper.
    invocations_by_id = {inv.invocation_id: inv for inv in invocations}
    reconcile_task_evaluation(task_evaluations[0], invocations_by_id)


def test_only_terminal_eligible_attempt_contributes_to_task_result(tmp_path: Path) -> None:
    """The task-evaluation record's own measurement_status/q_ref_task
    reflect only the terminal (successful) attempt, never the earlier
    infrastructure-failed one -- no double counting."""
    trace_store = CalibrationTraceStore(tmp_path / "trace.jsonl")
    recorder = _FullReconcilingTraceRecorder(trace_store)
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        backend_factory=lambda: OverrideSequenceBackend(
            [ExecutionStatus.INFRASTRUCTURE_ERROR, ExecutionStatus.COMPLETED]
        ),
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
    )
    item = _work_item("wi-0", 0)

    orchestrator.run([item], run_id="run-1")

    assert len(recorder.built_task_evaluations) == 1
    task_evaluation = recorder.built_task_evaluations[0]
    assert task_evaluation.measurement_status == MeasurementStatus.VALID
    assert task_evaluation.q_ref_task == 1.0
    # Both attempts are referenced (never silently dropped)...
    assert len(task_evaluation.contributing_invocation_ids) == 2
    # ...but exactly one CalibrationTaskEvaluationRecord exists for this
    # coordinate -- the failed attempt never produces its own, separately
    # scored task evaluation.
    _invocations, task_evaluations = trace_store.read_all()
    assert len(task_evaluations) == 1


# ---------------------------------------------------------------------------
# 4. Typed trace-storage failure
# ---------------------------------------------------------------------------


def test_trace_persistence_error_chains_the_original_cause(tmp_path: Path) -> None:
    """CalibrationTracePersistenceError preserves the original exception via
    __cause__ (exception chaining), never swallowing or replacing it."""
    recorder = FakeTraceRecorder(fail=True)
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
    )
    item = _work_item("wi-0", 0)

    try:
        orchestrator.run([item], run_id="run-1")
    except CalibrationTracePersistenceError as exc:
        assert isinstance(exc.__cause__, RuntimeError)
        assert "simulated trace-write failure" in str(exc.__cause__)
    else:
        raise AssertionError("expected CalibrationTracePersistenceError")


def test_trace_failure_run_never_returns_an_apparently_complete_summary(tmp_path: Path) -> None:
    """A trace-persistence failure makes the whole run() call explicitly
    fail (a typed exception) rather than silently returning a summary that
    looks complete but is missing the failed coordinate."""
    recorder = FakeTraceRecorder(fail=True)
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
        max_workers=1,
        max_in_flight=1,
    )
    items = [_work_item(f"wi-{i}", i, task_evaluation_replicate_id=i) for i in range(3)]

    try:
        summary = orchestrator.run(items, run_id="run-1")
    except CalibrationTracePersistenceError:
        pass
    else:
        raise AssertionError(
            f"expected CalibrationTracePersistenceError, got a summary: {summary!r}"
        )


def test_trace_failure_preserves_already_durable_trace_records(tmp_path: Path) -> None:
    """A trace-persistence failure on a later coordinate does not retract
    or corrupt trace records already durably appended for an earlier one."""
    trace_store = CalibrationTraceStore(tmp_path / "trace.jsonl")

    class _FailOnSecondCallRecorder:
        def __init__(self) -> None:
            self.call_count = 0

        def record_fresh_attempt(  # pylint: disable=too-many-arguments
            self,
            *,
            work_item: WorkItem,
            evidence: ReferenceTaskEvidence,
            task_evaluation_replicate_id: int,
            attempt_records: tuple[FreshExecutionAttempt, ...],
            disposition: WorkItemDisposition,
            task_result: ReferenceTaskResult | None,
        ) -> None:
            """Append a real trace record, or raise on the second call."""
            del attempt_records
            self.call_count += 1
            if self.call_count == 2:
                raise RuntimeError("simulated failure on the second coordinate")
            context = _calibration_context()
            assert task_result is not None
            record = CalibrationTaskEvaluationRecord(
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
            trace_store.append_task_evaluation_record(record)

    recorder = _FailOnSecondCallRecorder()
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
        max_workers=1,
        max_in_flight=1,
    )
    items = [_work_item(f"wi-{i}", i, task_evaluation_replicate_id=i) for i in range(3)]

    try:
        orchestrator.run(items, run_id="run-1")
    except CalibrationTracePersistenceError:
        pass
    else:
        raise AssertionError("expected CalibrationTracePersistenceError")

    _invocations, task_evaluations = trace_store.read_all()
    assert len(task_evaluations) == 1, (
        "the first coordinate's trace record, durably appended before the "
        "second coordinate's failure, must survive untouched"
    )
