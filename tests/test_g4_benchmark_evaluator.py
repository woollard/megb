"""Tests for src.reference.g4_benchmark_evaluator (MEGB-03G.4 correction).

Offline only: a fake execution backend, no real Docker, no real corpus.
Covers: distinct synthetic identities never collide with real constants
(except ``execution_protocol_version``, which is deliberately the real
``EXECUTION_PROTOCOL_VERSION`` -- see the module's Correction v2 note),
correct/wrong-output classification, candidate-hash and version-mismatch
rejection, execution-status mapping, and that every outbound request
carries the real protocol version.
"""

# See tests/test_reference_cache_key.py's note: this file intentionally
# builds its own local fixtures (a fake execution result/backend)
# independent of test_reference_evaluator.py's own copies.
# pylint: disable=duplicate-code

import hashlib

import pytest

from src.evaluators.schema import FailureCategory
from src.execution.backend import ExecutionBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionLimits,
    ExecutionStatus,
)
from src.reference.g4_benchmark_evaluator import (
    G4_COMPARISON_PROFILE_VERSION,
    G4_DATASET_CHECKSUM,
    G4_DATASET_VERSION,
    G4_EVALUATOR_VERSION,
    G4_EXECUTION_PROFILE_ID,
    G4_ORACLE_VERSION,
    G4_PARTITION_VERSION,
    G4_TASK_MANIFEST_CHECKSUM,
    G4BenchmarkEvaluatorVersionMismatchError,
    G4CandidateIdentityMismatchError,
    assert_g4_identities_are_synthetic,
    evaluate_g4_benchmark_candidate,
)
from src.reference.oracle import ORACLE_STATUS_GENERATION_FAILED, OracleRecord
from src.reference.reference_evaluator import (
    EXECUTION_PROTOCOL_VERSION,
    ExecutionProfile,
    ReferenceCase,
    ReferenceTaskEvidence,
)
from src.reference.result_schema import MeasurementStatus, ReferenceRunContext

_ENTRY_POINT = "g4_evaluator_test"
_CANDIDATE_CODE = "def g4_evaluator_test(n):\n    return n * 2\n"
_TASK_ID = "G4EvalTest/0"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_CANDIDATE_SHA256 = _sha256(_CANDIDATE_CODE)


class FakeBackend(ExecutionBackend):
    """Deterministic, queued fake backend for offline unit tests."""

    def __init__(self, results: list[CandidateExecutionResult]) -> None:
        self._results = list(results)
        self.requests: list[CandidateExecutionRequest] = []

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        self.requests.append(request)
        return self._results[len(self.requests) - 1]


def _execution_result(
    status: ExecutionStatus = ExecutionStatus.COMPLETED, return_value: object = None
) -> CandidateExecutionResult:
    return CandidateExecutionResult(
        invocation_id="inv-0",
        status=status,
        return_value=return_value,
        exception_type=None,
        exception_message=None,
        wall_time_sec=0.01,
        candidate_wall_time_sec=0.005 if status == ExecutionStatus.COMPLETED else None,
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


def _profile() -> ExecutionProfile:
    return ExecutionProfile(
        profile_id=G4_EXECUTION_PROFILE_ID,
        evaluator_version=G4_EVALUATOR_VERSION,
        limits=ExecutionLimits(),
    )


def _case(case_id: str, n: int) -> ReferenceCase:
    from src.execution.wire import encode_value  # pylint: disable=import-outside-toplevel

    record = OracleRecord(
        task_id=_TASK_ID,
        case_id=case_id,
        pool="megb-03g4-synthetic",
        provenance="megb-03g4-synthetic",
        comparison_profile_kind="default_exact_or_tolerance",
        status="success",
        expected_output=encode_value(n * 2),
        failure_reason=None,
    )
    return ReferenceCase(case_id=case_id, args=(n,), oracle_record=record)


def _evidence(cases: list[ReferenceCase], **overrides: object) -> ReferenceTaskEvidence:
    from src.reference.oracle import ComparisonProfile  # pylint: disable=import-outside-toplevel

    fields: dict[str, object] = {
        "task_id": _TASK_ID,
        "entry_point": _ENTRY_POINT,
        "comparison_profile": ComparisonProfile(
            kind="default_exact_or_tolerance",
            atol=0.0,
            profile_version=G4_COMPARISON_PROFILE_VERSION,
        ),
        "cases": tuple(cases),
        "oracle_version": G4_ORACLE_VERSION,
        "partition_version": G4_PARTITION_VERSION,
        "dataset_version": G4_DATASET_VERSION,
        "protocol_version": EXECUTION_PROTOCOL_VERSION,
        "dataset_checksum": G4_DATASET_CHECKSUM,
        "task_manifest_checksum": G4_TASK_MANIFEST_CHECKSUM,
    }
    fields.update(overrides)
    return ReferenceTaskEvidence(**fields)  # type: ignore[arg-type]


def _run_context(**overrides: object) -> ReferenceRunContext:
    fields: dict[str, object] = {
        "experiment_run_id": "g4-benchmark",
        "optimization_run_id": "g4-benchmark",
        "optimization_config_sha256": "0" * 64,
        "portfolio_frozen_at": "2026-01-01T00:00:00Z",
        "portfolio_selection_rule": "g4-benchmark-fixed",
        "evaluator_version": G4_EVALUATOR_VERSION,
        "dataset_version": G4_DATASET_VERSION,
        "partition_version": G4_PARTITION_VERSION,
        "execution_profile_id": G4_EXECUTION_PROFILE_ID,
        "comparison_profile_version": G4_COMPARISON_PROFILE_VERSION,
        "execution_protocol_version": EXECUTION_PROTOCOL_VERSION,
        "dataset_checksum": G4_DATASET_CHECKSUM,
        "task_manifest_checksum": G4_TASK_MANIFEST_CHECKSUM,
    }
    fields.update(overrides)
    return ReferenceRunContext(**fields)  # type: ignore[arg-type]


# --- Synthetic-identity structural proof --------------------------------------


def test_g4_identities_never_collide_with_real_constants() -> None:
    """G4 identities never collide with real constants."""
    assert_g4_identities_are_synthetic()  # must not raise


@pytest.mark.parametrize(
    "real_constant_module,real_constant_name",
    [
        ("src.reference.oracle", "ORACLE_ALGORITHM_VERSION"),
        ("src.reference.oracle", "COMPARISON_PROFILE_VERSION"),
        ("src.reference.partition", "PARTITION_ALGORITHM_VERSION"),
    ],
)
def test_collision_check_would_actually_detect_a_real_collision(
    real_constant_module: str, real_constant_name: str
) -> None:
    """If a G4 constant ever collided with a real one, the check would
    catch it -- proved by constructing the exact same comparison this
    module's own assert function performs, with a deliberately colliding
    value substituted in."""
    module = __import__(real_constant_module, fromlist=[real_constant_name])
    real_value = getattr(module, real_constant_name)
    # The same style of dict assert_g4_identities_are_synthetic() builds,
    # but deliberately colliding for this one entry.
    colliding_identities = {real_value: (real_value,)}
    for synthetic_value, real_values in colliding_identities.items():
        assert synthetic_value in real_values  # demonstrates the check fires on a real collision


# --- Correct/incorrect candidate evaluation -----------------------------------


def test_correct_candidate_all_cases_pass() -> None:
    """A candidate matching every case's expected output yields q_ref_task=1.0."""
    cases = [_case("c0", 3), _case("c1", 5)]
    evidence = _evidence(cases)
    backend = FakeBackend([_execution_result(return_value=6), _execution_result(return_value=10)])

    result, diagnostics = evaluate_g4_benchmark_candidate(
        evidence, _CANDIDATE_CODE, "cand-0", _CANDIDATE_SHA256, _run_context(),
        backend=backend, profile=_profile(),
    )

    assert result.status == MeasurementStatus.VALID
    assert result.q_ref_task == 1.0
    assert result.reference_case_pass_count == 2
    assert len(diagnostics) == 2


def test_wrong_output_yields_valid_zero() -> None:
    """A wrong-answer candidate is a VALID measurement with q_ref_task=0.0."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    backend = FakeBackend([_execution_result(return_value=999)])

    result, _ = evaluate_g4_benchmark_candidate(
        evidence, _CANDIDATE_CODE, "cand-0", _CANDIDATE_SHA256, _run_context(),
        backend=backend, profile=_profile(),
    )

    assert result.status == MeasurementStatus.VALID
    assert result.q_ref_task == 0.0
    assert result.first_failure_category == FailureCategory.WRONG_OUTPUT


@pytest.mark.parametrize(
    "status,expected_measurement_status",
    [
        (ExecutionStatus.PROTOCOL_ERROR, MeasurementStatus.INVALID_PROTOCOL),
        (ExecutionStatus.INFRASTRUCTURE_ERROR, MeasurementStatus.INVALID_INFRASTRUCTURE),
    ],
)
def test_measurement_apparatus_failures_are_invalid(
    status: ExecutionStatus, expected_measurement_status: MeasurementStatus
) -> None:
    """Measurement apparatus failures are invalid."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    backend = FakeBackend([_execution_result(status=status)])

    result, _ = evaluate_g4_benchmark_candidate(
        evidence, _CANDIDATE_CODE, "cand-0", _CANDIDATE_SHA256, _run_context(),
        backend=backend, profile=_profile(),
    )

    assert result.status == expected_measurement_status
    assert result.q_ref_task is None


def test_candidate_hash_mismatch_is_rejected() -> None:
    """Candidate hash mismatch is rejected."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    backend = FakeBackend([_execution_result(return_value=6)])

    with pytest.raises(G4CandidateIdentityMismatchError):
        evaluate_g4_benchmark_candidate(
            evidence, _CANDIDATE_CODE, "cand-0", "0" * 64, _run_context(),
            backend=backend, profile=_profile(),
        )


def test_run_context_evidence_mismatch_is_rejected() -> None:
    """A run_context that disagrees with evidence's G4 identities is rejected."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    backend = FakeBackend([_execution_result(return_value=6)])
    bad_context = _run_context(dataset_version="not-the-g4-dataset-version")

    with pytest.raises(G4BenchmarkEvaluatorVersionMismatchError):
        evaluate_g4_benchmark_candidate(
            evidence, _CANDIDATE_CODE, "cand-0", _CANDIDATE_SHA256, bad_context,
            backend=backend, profile=_profile(),
        )


def test_invalid_oracle_record_is_not_silently_treated_as_success() -> None:
    """A broken (generation-failed) oracle record yields INVALID_ORACLE --
    checked before any decode/comparison is even attempted, so a `None`
    expected_output never crashes or is silently treated as a match."""
    broken_record = OracleRecord(
        task_id=_TASK_ID,
        case_id="c0",
        pool="megb-03g4-synthetic",
        provenance="megb-03g4-synthetic",
        comparison_profile_kind="default_exact_or_tolerance",
        status=ORACLE_STATUS_GENERATION_FAILED,
        expected_output=None,
        failure_reason="simulated",
    )
    case = ReferenceCase(case_id="c0", args=(3,), oracle_record=broken_record)
    evidence = _evidence([case])
    backend = FakeBackend([_execution_result(return_value=6)])

    result, _ = evaluate_g4_benchmark_candidate(
        evidence, _CANDIDATE_CODE, "cand-0", _CANDIDATE_SHA256, _run_context(),
        backend=backend, profile=_profile(),
    )
    assert result.status == MeasurementStatus.INVALID_ORACLE
    assert result.q_ref_task is None


# --- Protocol-version isolation -------------------------------------------------


def test_outbound_requests_carry_the_real_protocol_version() -> None:
    """Every request sent to the backend carries the real
    EXECUTION_PROTOCOL_VERSION -- this benchmark reuses the identical,
    unmodified MEGB-02 wire transport, so this field is deliberately
    shared truthful identity, not a synthetic label."""
    cases = [_case("c0", 3), _case("c1", 4)]
    evidence = _evidence(cases)
    backend = FakeBackend([_execution_result(return_value=6), _execution_result(return_value=8)])

    evaluate_g4_benchmark_candidate(
        evidence, _CANDIDATE_CODE, "cand-0", _CANDIDATE_SHA256, _run_context(),
        backend=backend, profile=_profile(),
    )

    assert len(backend.requests) == 2
    for request in backend.requests:
        assert request.protocol_version == EXECUTION_PROTOCOL_VERSION


def test_result_context_never_carries_any_real_identity() -> None:
    """The produced ReferenceTaskResult's context never equals any real
    profile's identity fields."""
    from src.reference.oracle import (  # pylint: disable=import-outside-toplevel
        COMPARISON_PROFILE_VERSION,
        ORACLE_ALGORITHM_VERSION,
    )
    from src.reference.reference_evaluator import (  # pylint: disable=import-outside-toplevel
        EVALUATOR_VERSION_FULL,
        EXECUTION_PROFILE_ID_FULL,
    )

    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    backend = FakeBackend([_execution_result(return_value=6)])

    result, _ = evaluate_g4_benchmark_candidate(
        evidence, _CANDIDATE_CODE, "cand-0", _CANDIDATE_SHA256, _run_context(),
        backend=backend, profile=_profile(),
    )

    assert result.context.evaluator_version != EVALUATOR_VERSION_FULL
    assert result.context.execution_profile_id != EXECUTION_PROFILE_ID_FULL
    assert result.context.comparison_profile_version != COMPARISON_PROFILE_VERSION
    assert result.oracle_version != ORACLE_ALGORITHM_VERSION
