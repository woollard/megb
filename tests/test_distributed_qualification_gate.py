"""MEGB-03H.2C.3B.1: tests for ``src.distributed.qualification_gate`` --
the H.2C.3D READY/BLOCKED decision function."""

import dataclasses

import pytest

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.provenance import DistributedRunIntent, EnvironmentClass
from src.distributed.qualification_gate import (
    ProvenanceGateFailureReason,
    ProvenanceGateReadiness,
    QualificationGateResult,
    evaluate_qualification_gate,
)
from tests._distributed_fixtures import (
    make_run_context,
    make_two_region_workers,
    make_worker_context,
)


def test_gate_ready_for_valid_single_worker() -> None:
    """Test gate ready for valid single worker."""
    run_context = make_run_context(run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE)
    worker = make_worker_context(parent_run_context_checksum=run_context.run_context_checksum)
    result = evaluate_qualification_gate(run_context, (worker,))
    assert result.readiness == ProvenanceGateReadiness.READY
    assert not result.missing_dimensions
    assert result.qualification_identity is not None
    assert result.worker_summary is not None


def test_gate_ready_for_multiple_workers_different_regions() -> None:
    """Test gate ready for multiple workers different regions."""
    run_context = make_run_context(run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE)
    worker_a, worker_b = make_two_region_workers(run_context)
    result = evaluate_qualification_gate(run_context, (worker_a, worker_b))
    assert result.readiness == ProvenanceGateReadiness.READY
    assert result.worker_summary is not None
    assert result.worker_summary.distinct_region_count == 2


def test_gate_blocked_for_smoke_test_intent() -> None:
    """A personal-bootstrap/connectivity smoke-test record must never be
    mislabeled as qualifying evidence -- Ambiguity 3."""
    run_context = make_run_context(
        run_intent=DistributedRunIntent.SMOKE_TEST,
        environment_class=EnvironmentClass.PERSONAL_BOOTSTRAP,
    )
    worker = make_worker_context(parent_run_context_checksum=run_context.run_context_checksum)
    result = evaluate_qualification_gate(run_context, (worker,))
    assert result.readiness == ProvenanceGateReadiness.BLOCKED
    assert ProvenanceGateFailureReason.NOT_QUALIFICATION_INTENT in result.missing_dimensions
    assert result.qualification_identity is None
    assert result.worker_summary is None


def test_gate_ready_for_company_playground_qualification_candidate() -> None:
    """environment_class alone is never the readiness signal -- a
    company-playground run with QUALIFICATION_CANDIDATE intent is also
    READY, same as a personal-bootstrap one."""
    run_context = make_run_context(
        run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE,
        environment_class=EnvironmentClass.COMPANY_PLAYGROUND,
    )
    worker = make_worker_context(parent_run_context_checksum=run_context.run_context_checksum)
    result = evaluate_qualification_gate(run_context, (worker,))
    assert result.readiness == ProvenanceGateReadiness.READY


def test_gate_blocked_for_no_worker_contexts() -> None:
    """Test gate blocked for no worker contexts."""
    run_context = make_run_context(run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE)
    result = evaluate_qualification_gate(run_context, ())
    assert result.readiness == ProvenanceGateReadiness.BLOCKED
    assert ProvenanceGateFailureReason.NO_WORKER_CONTEXTS in result.missing_dimensions
    assert result.qualification_identity is None
    assert result.worker_summary is None


def test_gate_blocked_for_mixed_context_workers() -> None:
    """Test gate blocked for mixed context workers."""
    run_a = make_run_context(
        distributed_run_id="run-a", run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE
    )
    run_b = make_run_context(
        distributed_run_id="run-b", run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE
    )
    worker_from_b = make_worker_context(parent_run_context_checksum=run_b.run_context_checksum)
    result = evaluate_qualification_gate(run_a, (worker_from_b,))
    assert result.readiness == ProvenanceGateReadiness.BLOCKED
    assert ProvenanceGateFailureReason.MIXED_CONTEXT_WORKERS in result.missing_dimensions


def test_gate_blocked_for_duplicate_worker_provenance() -> None:
    """Test gate blocked for duplicate worker provenance."""
    run_context = make_run_context(run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE)
    worker = make_worker_context(parent_run_context_checksum=run_context.run_context_checksum)
    duplicate = make_worker_context(parent_run_context_checksum=run_context.run_context_checksum)
    assert worker.worker_context_checksum == duplicate.worker_context_checksum
    result = evaluate_qualification_gate(run_context, (worker, duplicate))
    assert result.readiness == ProvenanceGateReadiness.BLOCKED
    assert ProvenanceGateFailureReason.DUPLICATE_WORKER_PROVENANCE in result.missing_dimensions


def test_gate_enumerates_multiple_simultaneous_reasons() -> None:
    """The gate collects every applicable reason in one evaluation rather
    than stopping at the first."""
    run_context = make_run_context(run_intent=DistributedRunIntent.SMOKE_TEST)
    result = evaluate_qualification_gate(run_context, ())
    assert result.readiness == ProvenanceGateReadiness.BLOCKED
    assert ProvenanceGateFailureReason.NOT_QUALIFICATION_INTENT in result.missing_dimensions
    assert ProvenanceGateFailureReason.NO_WORKER_CONTEXTS in result.missing_dimensions
    assert len(result.missing_dimensions) == 2


def test_gate_reasons_are_closed_enum_values_not_free_text() -> None:
    """Requirement: enumerate missing/incompatible dimensions without
    free-form sensitive detail."""
    run_context = make_run_context(run_intent=DistributedRunIntent.SMOKE_TEST)
    result = evaluate_qualification_gate(run_context, ())
    for reason in result.missing_dimensions:
        assert isinstance(reason, ProvenanceGateFailureReason)


# ---------------------------------------------------------------------------
# QualificationGateResult's own internal consistency invariants
# ---------------------------------------------------------------------------


def test_result_is_frozen() -> None:
    """Test result is frozen."""
    run_context = make_run_context(run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE)
    worker = make_worker_context(parent_run_context_checksum=run_context.run_context_checksum)
    result = evaluate_qualification_gate(run_context, (worker,))
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.readiness = ProvenanceGateReadiness.BLOCKED  # type: ignore[misc]


def test_ready_result_cannot_have_missing_dimensions() -> None:
    """Test ready result cannot have missing dimensions."""
    with pytest.raises(InvalidDistributedProvenanceError):
        QualificationGateResult(
            readiness=ProvenanceGateReadiness.READY,
            missing_dimensions=(ProvenanceGateFailureReason.NO_WORKER_CONTEXTS,),
            qualification_identity=None,
            worker_summary=None,
        )


def test_ready_result_requires_identity_and_summary() -> None:
    """Test ready result requires identity and summary."""
    with pytest.raises(InvalidDistributedProvenanceError):
        QualificationGateResult(
            readiness=ProvenanceGateReadiness.READY,
            missing_dimensions=(),
            qualification_identity=None,
            worker_summary=None,
        )


def test_blocked_result_requires_nonempty_missing_dimensions() -> None:
    """Test blocked result requires nonempty missing dimensions."""
    with pytest.raises(InvalidDistributedProvenanceError):
        QualificationGateResult(
            readiness=ProvenanceGateReadiness.BLOCKED,
            missing_dimensions=(),
            qualification_identity=None,
            worker_summary=None,
        )


def test_blocked_result_cannot_carry_an_identity() -> None:
    """Test blocked result cannot carry an identity."""
    run_context = make_run_context(run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE)
    worker = make_worker_context(parent_run_context_checksum=run_context.run_context_checksum)
    ready_result = evaluate_qualification_gate(run_context, (worker,))
    with pytest.raises(InvalidDistributedProvenanceError):
        QualificationGateResult(
            readiness=ProvenanceGateReadiness.BLOCKED,
            missing_dimensions=(ProvenanceGateFailureReason.NO_WORKER_CONTEXTS,),
            qualification_identity=ready_result.qualification_identity,
            worker_summary=None,
        )
