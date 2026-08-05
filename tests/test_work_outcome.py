"""MEGB-03H.2C.3B.2B.2: construction/validation/ordering tests for
:mod:`src.distributed.work_outcome`."""

import pytest

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.executor import ExecutorFailureReason
from src.distributed.personal_policy import AdmissionRefusalReason
from src.distributed.work_outcome import (
    WorkOutcome,
    WorkOutcomeKind,
    build_run_summary,
    make_work_outcome,
)


def test_committed_outcome_requires_a_result_content_checksum() -> None:
    """Test committed outcome requires a result content checksum."""
    with pytest.raises(InvalidDistributedProvenanceError):
        WorkOutcome(
            scientific_work_id="work-1",
            input_ordinal=0,
            outcome_kind=WorkOutcomeKind.EXECUTED_AND_COMMITTED,
            result_content_checksum=None,
            policy_refusal_reasons=(),
            executor_failure_reason=None,
        )


def test_non_committed_outcome_rejects_a_result_content_checksum() -> None:
    """Test non committed outcome rejects a result content checksum."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_work_outcome(
            "work-1",
            0,
            WorkOutcomeKind.STALE_LEASE,
            result_content_checksum="9" * 64,
        )


def test_policy_blocked_requires_at_least_one_refusal_reason() -> None:
    """Test policy blocked requires at least one refusal reason."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_work_outcome("work-1", 0, WorkOutcomeKind.POLICY_BLOCKED)


def test_non_policy_blocked_rejects_refusal_reasons() -> None:
    """Test non policy blocked rejects refusal reasons."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_work_outcome(
            "work-1",
            0,
            WorkOutcomeKind.BUDGET_BLOCKED,
            policy_refusal_reasons=(AdmissionRefusalReason.COST_CEILING_EXCEEDED,),
        )


def test_executor_failure_reason_only_allowed_for_retry_outcomes() -> None:
    """Test executor_failure_reason only allowed for retry outcomes."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_work_outcome(
            "work-1",
            0,
            WorkOutcomeKind.STALE_LEASE,
            executor_failure_reason=ExecutorFailureReason.RETRYABLE_EXECUTION_ERROR,
        )


def test_make_work_outcome_builds_a_valid_policy_blocked_outcome() -> None:
    """Test make_work_outcome builds a valid policy blocked outcome."""
    outcome = make_work_outcome(
        "work-1",
        0,
        WorkOutcomeKind.POLICY_BLOCKED,
        policy_refusal_reasons=(AdmissionRefusalReason.WORKLOAD_CLASS_NOT_ALLOWLISTED,),
    )
    assert outcome.outcome_kind == WorkOutcomeKind.POLICY_BLOCKED


def test_build_run_summary_orders_by_input_ordinal_regardless_of_list_order() -> None:
    """Test build_run_summary orders by input_ordinal regardless of list
    order -- the deterministic-ordering requirement, independent of
    completion order."""
    out_2 = make_work_outcome("work-3", 2, WorkOutcomeKind.CANCELLED_NOT_STARTED)
    out_0 = make_work_outcome("work-1", 0, WorkOutcomeKind.CANCELLED_NOT_STARTED)
    out_1 = make_work_outcome("work-2", 1, WorkOutcomeKind.CANCELLED_NOT_STARTED)
    summary = build_run_summary([out_2, out_0, out_1])
    assert [outcome.input_ordinal for outcome in summary.outcomes] == [0, 1, 2]
    assert [outcome.scientific_work_id for outcome in summary.outcomes] == [
        "work-1",
        "work-2",
        "work-3",
    ]


def test_coordinator_run_summary_count() -> None:
    """Test CoordinatorRunSummary.count tallies exactly one kind."""
    summary = build_run_summary(
        [
            make_work_outcome("work-1", 0, WorkOutcomeKind.CANCELLED_NOT_STARTED),
            make_work_outcome("work-2", 1, WorkOutcomeKind.CANCELLED_NOT_STARTED),
            make_work_outcome("work-3", 2, WorkOutcomeKind.STALE_LEASE),
        ]
    )
    assert summary.count(WorkOutcomeKind.CANCELLED_NOT_STARTED) == 2
    assert summary.count(WorkOutcomeKind.STALE_LEASE) == 1
    assert summary.count(WorkOutcomeKind.EXECUTED_AND_COMMITTED) == 0
