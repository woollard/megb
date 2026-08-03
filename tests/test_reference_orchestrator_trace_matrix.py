"""Tests for MEGB-03H.2B.1's post-provisional-acceptance trace-coverage and
audit-schema review: NOT_STARTED/cancellation representation in the
calibration trace, and the outcome-path trace-content matrix.

Split out from ``test_reference_orchestrator_cache_policy.py`` purely to
keep each test module under pylint's per-module line-count limit -- both
files share the same synthetic fixtures (``tests/_reference_orchestrator_cache_policy_fixtures.py``)
and cover the same H.2B.1 checkpoint; there is no behavioral reason for the
split. No real privileged corpus access, no Docker.

Required-coverage for this correction: cancellation/not-started
coordinates are represented in the calibration trace at task-evaluation
level under a fresh policy (even with no invocation record), and are a
no-op under CACHE_FIRST; every evaluator-attempt outcome path (valid
correct/incorrect/resource-limit, invalid protocol/oracle, infrastructure
retry-then-success, infrastructure retry-exhaustion, unexpected-exception
exhaustion) is traced with the correct disposition/attempts/result
presence, under both fresh policies where applicable.
"""

# See _reference_orchestrator_cache_policy_fixtures.py's own note: these
# fixtures intentionally mirror patterns already present in
# test_reference_evaluator.py -- suppressing here rather than coupling this
# module's fixtures to that other, unrelated test module's internals.
# pylint: disable=duplicate-code

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from src.execution.backend import ExecutionBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionStatus,
)
from src.reference.orchestration_trace import CachePolicy
from src.reference.reference_cache import ReferenceResultCache
from src.reference.reference_orchestrator import WorkItemDisposition
from tests._reference_orchestrator_cache_policy_fixtures import (
    FakeTraceRecorder,
    OverrideSequenceBackend,
    RaisingBackend,
    RecordingBackend,
    WrongAnswerBackend,
)
from tests._reference_orchestrator_cache_policy_fixtures import (
    execution_result as _execution_result,
)
from tests._reference_orchestrator_cache_policy_fixtures import orchestrator as _orchestrator
from tests._reference_orchestrator_cache_policy_fixtures import work_item as _work_item

# ---------------------------------------------------------------------------
# NOT_STARTED / cancellation trace representation (post-acceptance-review
# correction): cancellation/not-started coordinates must be represented at
# task-evaluation level even when no invocation record exists.
# ---------------------------------------------------------------------------


def test_cancellation_traces_not_started_coordinates_at_task_evaluation_level(
    tmp_path: Path,
) -> None:
    """A replicate cancelled before its cache key was ever admitted is still
    represented in the calibration trace under a fresh policy -- a
    NOT_STARTED task-evaluation-level record, even though no invocation ever
    ran for it. CACHE_FIRST is unaffected (asserted separately below)."""
    cancelled = threading.Event()

    class _OneShotThenCancelBackend(ExecutionBackend):
        def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
            cancelled.set()
            n = request.args[0]
            return _execution_result(ExecutionStatus.COMPLETED, n * 2, f"inv-{n}")

    recorder = FakeTraceRecorder()
    replicate_count = 4
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
    not_started_outcomes = [
        o for o in summary.outcomes if o.disposition == WorkItemDisposition.NOT_STARTED
    ]
    assert len(not_started_outcomes) == replicate_count - 1

    started_calls = [
        call for call in recorder.calls if call.disposition != WorkItemDisposition.NOT_STARTED
    ]
    not_started_calls = [
        call for call in recorder.calls if call.disposition == WorkItemDisposition.NOT_STARTED
    ]
    assert len(started_calls) == 1
    assert len(not_started_calls) == replicate_count - 1
    assert all(call.attempts == 0 for call in not_started_calls)
    assert all(call.has_result is False for call in not_started_calls)
    # Every cancelled replicate is individually represented -- none were
    # collapsed into a single shared NOT_STARTED trace record.
    assert len({call.task_evaluation_replicate_id for call in not_started_calls}) == (
        replicate_count - 1
    )


def test_cache_first_cancellation_never_touches_trace_recorder(tmp_path: Path) -> None:
    """Under CACHE_FIRST (no trace_recorder configured), cancelled/
    not-started items still resolve to NOT_STARTED without error -- the new
    NOT_STARTED trace call is a strict no-op there, per requirement 8.
    Items differ only by candidate source (distinct cache keys, same task)
    so cancellation-before-admission has more than one coordinate to leave
    NOT_STARTED, without needing CACHE_FIRST's own replicate-id restriction
    (which requires every replicate id to stay 0)."""
    cancelled = threading.Event()

    class _OneShotThenCancelBackend(ExecutionBackend):
        def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
            cancelled.set()
            n = request.args[0]
            return _execution_result(ExecutionStatus.COMPLETED, n * 2, f"inv-{n}")

    orchestrator, _, _ = _orchestrator(
        tmp_path, backend_factory=_OneShotThenCancelBackend, max_workers=1, max_in_flight=1
    )
    items = [
        _work_item(f"wi-{i}", i, candidate_code=f"def double(n):\n    return n * 2  # v{i}\n")
        for i in range(4)
    ]

    summary = orchestrator.run(items, run_id="run-1", cancellation_event=cancelled)

    assert summary.interrupted is True
    assert any(o.disposition == WorkItemDisposition.NOT_STARTED for o in summary.outcomes)


# ---------------------------------------------------------------------------
# Outcome-path trace-content matrix: every evaluator attempt and final
# work-item state must be represented in the calibration trace under a
# fresh policy, not only accepted valid results. Verifies trace *contents*
# (disposition/attempts/has_result), not merely evaluator call counts or
# cache state.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutcomePathCase:
    """One outcome-path scenario for the trace-content matrix below."""

    backend_factory: Callable[[], ExecutionBackend]
    max_attempts: int
    expected_disposition: WorkItemDisposition
    expected_attempts: int
    expects_result: bool
    expects_cache_write: bool


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            OutcomePathCase(
                RecordingBackend, 3, WorkItemDisposition.EXECUTED_VALID, 1, True, True
            ),
            id="valid_correct_result",
        ),
        pytest.param(
            OutcomePathCase(
                WrongAnswerBackend, 3, WorkItemDisposition.EXECUTED_VALID, 1, True, True
            ),
            id="valid_incorrect_candidate_result",
        ),
        pytest.param(
            OutcomePathCase(
                lambda: OverrideSequenceBackend([ExecutionStatus.TIMEOUT]),
                3, WorkItemDisposition.EXECUTED_VALID, 1, True, True,
            ),
            id="valid_resource_limit_candidate_failure",
        ),
        pytest.param(
            OutcomePathCase(
                lambda: OverrideSequenceBackend([ExecutionStatus.PROTOCOL_ERROR]),
                3, WorkItemDisposition.EXECUTED_INVALID, 1, True, False,
            ),
            id="invalid_protocol_result",
        ),
        pytest.param(
            OutcomePathCase(
                lambda: OverrideSequenceBackend(
                    [ExecutionStatus.INFRASTRUCTURE_ERROR, ExecutionStatus.COMPLETED]
                ),
                3, WorkItemDisposition.EXECUTED_VALID, 2, True, True,
            ),
            id="invalid_infrastructure_then_successful_retry",
        ),
        pytest.param(
            OutcomePathCase(
                lambda: OverrideSequenceBackend([ExecutionStatus.INFRASTRUCTURE_ERROR] * 3),
                3, WorkItemDisposition.RETRY_EXHAUSTED, 3, True, False,
            ),
            id="invalid_infrastructure_retries_exhausted",
        ),
        pytest.param(
            OutcomePathCase(
                RaisingBackend, 2, WorkItemDisposition.RETRY_EXHAUSTED, 2, False, False
            ),
            id="evaluator_raises_unexpectedly_retries_exhausted",
        ),
    ],
)
def test_outcome_path_trace_content_matrix(tmp_path: Path, case: OutcomePathCase) -> None:
    """For each outcome path, under FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
    the calibration trace is written exactly once per key-group with the
    correct disposition/attempts/result-presence, and the production cache
    is written only for the paths where that is actually expected."""
    cache = ReferenceResultCache(tmp_path / "cache")
    recorder = FakeTraceRecorder()
    orchestrator, _, _ = _orchestrator(
        tmp_path,
        cache=cache,
        backend_factory=case.backend_factory,
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=recorder,
        max_attempts=case.max_attempts,
        max_workers=1,
        max_in_flight=1,
    )
    item = _work_item("wi-0", 0)

    summary = orchestrator.run([item], run_id="run-1")
    expected_disposition = case.expected_disposition
    expected_attempts = case.expected_attempts
    expects_result = case.expects_result
    expects_cache_write = case.expects_cache_write

    assert summary.outcomes[0].disposition == expected_disposition
    assert summary.outcomes[0].attempts == expected_attempts
    assert len(list(cache.cache_dir.glob("*.json"))) == (1 if expects_cache_write else 0)

    assert len(recorder.calls) == 1, "exactly one trace record per key-group, win or lose"
    call = recorder.calls[0]
    assert call.disposition == expected_disposition
    assert call.attempts == expected_attempts
    assert call.has_result is expects_result
    assert call.task_evaluation_replicate_id == 0


def test_outcome_path_matrix_covers_no_cache_write_policy_for_valid_and_invalid(
    tmp_path: Path,
) -> None:
    """The same trace-content guarantee holds under
    FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE for both a valid and a
    non-retryable-invalid path -- not only for
    FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID.

    For the valid path, the *traced* disposition is ``EXECUTED_VALID`` (what
    was measured) even though the *outcome*-level disposition is
    ``EXECUTED_VALID_UNCACHED`` (the outcome additionally encodes the cache-
    write policy) -- an intentional divergence, not a bug: the trace call in
    ``_accept_valid_result`` always fires with ``EXECUTED_VALID`` before the
    method decides whether this policy bypasses the cache write."""
    cases = (
        (
            RecordingBackend,
            WorkItemDisposition.EXECUTED_VALID_UNCACHED,
            WorkItemDisposition.EXECUTED_VALID,
            True,
        ),
        (
            lambda: OverrideSequenceBackend([ExecutionStatus.PROTOCOL_ERROR]),
            WorkItemDisposition.EXECUTED_INVALID,
            WorkItemDisposition.EXECUTED_INVALID,
            True,
        ),
    )
    for case in cases:
        backend_factory = case[0]
        expected_outcome_disposition = case[1]
        expected_trace_disposition = case[2]
        expects_result = case[3]
        cache = ReferenceResultCache(tmp_path / f"cache-{expected_outcome_disposition.value}")
        recorder = FakeTraceRecorder()
        orchestrator, _, _ = _orchestrator(
            tmp_path,
            cache=cache,
            backend_factory=backend_factory,
            cache_policy=CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
            trace_recorder=recorder,
            max_workers=1,
            max_in_flight=1,
        )
        item = _work_item("wi-0", 0)

        summary = orchestrator.run([item], run_id="run-1")

        assert summary.outcomes[0].disposition == expected_outcome_disposition
        assert not list(cache.cache_dir.glob("*.json"))
        assert len(recorder.calls) == 1
        assert recorder.calls[0].disposition == expected_trace_disposition
        assert recorder.calls[0].has_result is expects_result
