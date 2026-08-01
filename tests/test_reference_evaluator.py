"""Tests for src.reference.reference_evaluator (MEGB-03F).

Organized to map onto the ticket's "Required Tests" list: correct/wrong-
output, execution-status mapping, candidate-hash verification, missing/
corrupt oracle, sandbox-backend/malformed-response injection, deterministic
ordering, cross-case state isolation, privileged-evidence exfiltration
attempts, and full-versus-mini identifiers. A real Docker-backed vertical
slice (correct/incorrect/malicious) lives in
``tests/test_reference_evaluator_docker.py``.
"""

import dataclasses
import hashlib
from typing import Any, Callable

import pytest
from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION

from src.evaluators.schema import FailureCategory
from src.execution.backend import ExecutionBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionLimits,
    ExecutionStatus,
)
from src.reference.oracle import (
    ORACLE_ALGORITHM_VERSION,
    ORACLE_STATUS_GENERATION_FAILED,
    POOL_REFERENCE_ONLY,
    OracleRecord,
    comparison_profile_for_task,
    generate_oracle_record,
)
from src.reference.partition import PARTITION_ALGORITHM_VERSION
from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EVALUATOR_VERSION_REDUCED_DEV,
    EXECUTION_PROFILE_ID_FULL,
    EXECUTION_PROFILE_ID_REDUCED_DEV,
    EXECUTION_PROTOCOL_VERSION,
    FULL_EXECUTION_PROFILE,
    REDUCED_DEV_EXECUTION_PROFILE,
    CandidateIdentityMismatchError,
    ExecutionProfile,
    ReferenceCase,
    ReferenceEvaluatorVersionMismatchError,
    ReferenceTaskEvidence,
    _CANDIDATE_FAILURE_CATEGORY_BY_STATUS,
    _INVALID_MEASUREMENT_STATUS_BY_EXECUTION_STATUS,
    evaluate_reference,
)
from src.reference.result_schema import MeasurementStatus, ReferenceEvaluationContext

_ENTRY_POINT = "double"
_PROMPT = f"def {_ENTRY_POINT}(n):\n"
_CANONICAL_SOLUTION = "    return n * 2\n"
_TASK_ID = "Test/0"


class FakeExecutionBackend(ExecutionBackend):
    """Deterministic, queued fake backend for offline unit tests."""

    def __init__(self, results: list[CandidateExecutionResult]) -> None:
        self._results = list(results)
        self.requests: list[CandidateExecutionRequest] = []

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        self.requests.append(request)
        return self._results[len(self.requests) - 1]


def _execution_result(
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    return_value: object = None,
    invocation_id: str = "inv-0",
    wall_time_sec: float = 0.01,
) -> CandidateExecutionResult:
    return CandidateExecutionResult(
        invocation_id=invocation_id,
        status=status,
        return_value=return_value,
        exception_type=None,
        exception_message=None,
        wall_time_sec=wall_time_sec,
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


def _canonical_fn() -> Callable[..., Any]:
    namespace: dict[str, Any] = {}
    exec(_PROMPT + _CANONICAL_SOLUTION, namespace)  # pylint: disable=exec-used
    return namespace[_ENTRY_POINT]  # type: ignore[no-any-return]


def _oracle_record(case_id: str, n: int) -> OracleRecord:
    profile = comparison_profile_for_task(_ENTRY_POINT, atol=0.0)
    return generate_oracle_record(
        task_id=_TASK_ID,
        case_id=case_id,
        args=(n,),
        provenance="original",
        pool=POOL_REFERENCE_ONLY,
        canonical_fn=_canonical_fn(),
        profile=profile,
    )


def _case(case_id: str, n: int) -> ReferenceCase:
    return ReferenceCase(case_id=case_id, args=(n,), oracle_record=_oracle_record(case_id, n))


def _evidence(cases: list[ReferenceCase], **overrides: object) -> ReferenceTaskEvidence:
    fields: dict[str, object] = {
        "task_id": _TASK_ID,
        "entry_point": _ENTRY_POINT,
        "comparison_profile": comparison_profile_for_task(_ENTRY_POINT, atol=0.0),
        "cases": tuple(cases),
        "oracle_version": ORACLE_ALGORITHM_VERSION,
        "partition_version": PARTITION_ALGORITHM_VERSION,
        "dataset_version": HUMANEVAL_PLUS_VERSION,
        "protocol_version": EXECUTION_PROTOCOL_VERSION,
    }
    fields.update(overrides)
    return ReferenceTaskEvidence(**fields)  # type: ignore[arg-type]


def _context(candidate_sha256: str, **overrides: object) -> ReferenceEvaluationContext:
    fields: dict[str, object] = {
        "experiment_run_id": "exp-1",
        "optimization_run_id": "opt-1",
        "candidate_id": "cand-1",
        "candidate_sha256": candidate_sha256,
        "candidate_frozen_at": "2026-08-01T00:00:00Z",
        "candidate_selection_rule": "best_of_run",
        "optimization_config_sha256": "b" * 64,
        "evaluator_version": EVALUATOR_VERSION_FULL,
        "dataset_version": HUMANEVAL_PLUS_VERSION,
        "partition_version": PARTITION_ALGORITHM_VERSION,
        "execution_profile_id": EXECUTION_PROFILE_ID_FULL,
    }
    fields.update(overrides)
    return ReferenceEvaluationContext(**fields)  # type: ignore[arg-type]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_CANDIDATE_CODE = "def double(n):\n    return n * 2\n"


# --- Correct candidate and wrong-output tests --------------------------


def test_correct_candidate_all_cases_pass() -> None:
    """A candidate matching every case's expected output yields q_ref_task=1.0."""
    cases = [_case("c0", 3), _case("c1", 5)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend(
        [_execution_result(return_value=6), _execution_result(return_value=10)]
    )

    result, diagnostics = evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert result.status == MeasurementStatus.VALID
    assert result.q_ref_task == 1.0
    assert result.reference_case_total == 2
    assert result.reference_case_pass_count == 2
    assert result.first_failure_category == FailureCategory.NONE
    assert len(diagnostics) == 2
    assert all(d.matched is True for d in diagnostics)


def test_wrong_output_candidate_produces_valid_zero() -> None:
    """A candidate returning a wrong value yields q_ref_task=0.0, category WRONG_OUTPUT."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend([_execution_result(return_value=999)])

    result, diagnostics = evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert result.status == MeasurementStatus.VALID
    assert result.q_ref_task == 0.0
    assert result.first_failure_category == FailureCategory.WRONG_OUTPUT
    assert diagnostics[0].matched is False


# --- Execution-status mapping tests --------------------------------------


@pytest.mark.parametrize(
    "status,expected_category",
    [
        (ExecutionStatus.SYNTAX_ERROR, FailureCategory.SYNTAX_ERROR),
        (ExecutionStatus.CANDIDATE_EXCEPTION, FailureCategory.RUNTIME_EXCEPTION),
        (ExecutionStatus.TIMEOUT, FailureCategory.TIMEOUT),
        (ExecutionStatus.OUT_OF_MEMORY, FailureCategory.RESOURCE_LIMIT),
        (ExecutionStatus.PROCESS_LIMIT, FailureCategory.RESOURCE_LIMIT),
        (ExecutionStatus.OUTPUT_LIMIT, FailureCategory.OUTPUT_LIMIT),
    ],
)
def test_candidate_failure_status_maps_to_valid_zero_with_category(
    status: ExecutionStatus, expected_category: FailureCategory
) -> None:
    """Every candidate-attributable ExecutionStatus maps to a valid zero score."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend([_execution_result(status=status, return_value=None)])

    result, _diagnostics = evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert result.status == MeasurementStatus.VALID
    assert result.q_ref_task == 0.0
    assert result.first_failure_category == expected_category


def test_every_execution_status_value_is_mapped() -> None:
    """Guards requirement 11: no ExecutionStatus value can fall through unmapped."""
    mapped = (
        set(_CANDIDATE_FAILURE_CATEGORY_BY_STATUS)
        | set(_INVALID_MEASUREMENT_STATUS_BY_EXECUTION_STATUS)
        | {ExecutionStatus.COMPLETED}
    )
    assert mapped == set(ExecutionStatus)


# --- Candidate-hash verification ------------------------------------------


def test_candidate_hash_mismatch_blocks_execution() -> None:
    """A candidate/context sha256 mismatch raises before any case executes."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256="0" * 64)
    backend = FakeExecutionBackend([])

    with pytest.raises(CandidateIdentityMismatchError):
        evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert not backend.requests


# --- Missing/corrupt oracle tests -----------------------------------------


def test_corrupt_oracle_record_produces_invalid_oracle_measurement() -> None:
    """A case whose oracle record failed generation invalidates the whole task."""
    good_record = _oracle_record("c0", 3)
    corrupt_record = dataclasses.replace(
        good_record,
        status=ORACLE_STATUS_GENERATION_FAILED,
        expected_output=None,
        failure_reason="simulated corrupt oracle record",
    )
    corrupt_case = ReferenceCase(case_id="c0", args=(3,), oracle_record=corrupt_record)
    evidence = _evidence([corrupt_case])
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend([_execution_result(return_value=6)])

    result, diagnostics = evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert result.status == MeasurementStatus.INVALID_ORACLE
    assert result.q_ref_task is None
    assert len(diagnostics) == 1


# --- Sandbox-backend and malformed-response injection ---------------------


def test_protocol_error_invalidates_measurement_and_stops_early() -> None:
    """A PROTOCOL_ERROR (e.g. malformed runner response) invalidates the task
    and never proceeds to remaining cases."""
    cases = [_case("c0", 3), _case("c1", 5)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend(
        [
            _execution_result(status=ExecutionStatus.PROTOCOL_ERROR),
            _execution_result(return_value=10),
        ]
    )

    result, diagnostics = evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert result.status == MeasurementStatus.INVALID_PROTOCOL
    assert result.q_ref_task is None
    assert len(backend.requests) == 1
    assert len(diagnostics) == 1


def test_infrastructure_error_invalidates_measurement_and_stops_early() -> None:
    """An INFRASTRUCTURE_ERROR (backend/sandbox failure) invalidates the task."""
    cases = [_case("c0", 3), _case("c1", 5)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend(
        [
            _execution_result(status=ExecutionStatus.INFRASTRUCTURE_ERROR),
            _execution_result(return_value=10),
        ]
    )

    result, _diagnostics = evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert result.status == MeasurementStatus.INVALID_INFRASTRUCTURE
    assert result.q_ref_task is None
    assert len(backend.requests) == 1


# --- Deterministic ordering tests ------------------------------------------


def test_evidence_rejects_unsorted_cases() -> None:
    """ReferenceTaskEvidence enforces case_id-sorted ordering at construction."""
    cases = [_case("c1", 5), _case("c0", 3)]
    with pytest.raises(ValueError):
        _evidence(cases)


def test_evidence_rejects_duplicate_case_ids() -> None:
    """ReferenceTaskEvidence rejects duplicate case_id entries."""
    cases = [_case("c0", 3), _case("c0", 3)]
    with pytest.raises(ValueError):
        _evidence(cases)


def test_cases_sent_to_backend_in_case_id_order() -> None:
    """Requests are sent to the backend in evidence.cases order, deterministically."""
    cases = [_case("c0", 1), _case("c1", 2), _case("c2", 3)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend(
        [
            _execution_result(return_value=2),
            _execution_result(return_value=4),
            _execution_result(return_value=6),
        ]
    )

    evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert [request.args for request in backend.requests] == [(1,), (2,), (3,)]


# --- Cross-case state-isolation tests ---------------------------------------


def test_each_case_gets_independent_request_with_only_its_own_args() -> None:
    """No request's args ever contains another case's input (no state/data leakage)."""
    cases = [_case("c0", 1), _case("c1", 2), _case("c2", 3)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend(
        [
            _execution_result(return_value=2),
            _execution_result(return_value=4),
            _execution_result(return_value=6),
        ]
    )

    evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    for index, request in enumerate(backend.requests):
        assert request.args == cases[index].args
        for other_index, other_case in enumerate(cases):
            if other_index != index:
                assert request.args != other_case.args or cases[index].args == other_case.args


def test_backend_called_exactly_once_per_case() -> None:
    """Each case results in exactly one backend.execute() call, never reused/batched."""
    cases = [_case("c0", 1), _case("c1", 2)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend(
        [_execution_result(return_value=2), _execution_result(return_value=4)]
    )

    evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert len(backend.requests) == len(cases)
    assert len({id(r) for r in backend.requests}) == len(cases)


# --- Privileged-evidence exfiltration attempts ------------------------------


def test_candidate_execution_request_has_no_room_for_oracle_content() -> None:
    """CandidateExecutionRequest's fixed field set structurally excludes any
    expected-output, oracle, or dataset-provenance field."""
    field_names = {f.name for f in dataclasses.fields(CandidateExecutionRequest)}
    assert field_names == {
        "candidate_code",
        "entry_point",
        "args",
        "kwargs",
        "limits",
        "protocol_version",
    }


def test_request_candidate_code_passed_through_unmodified() -> None:
    """The candidate source sent to the backend is exactly what was given, never augmented."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend([_execution_result(return_value=6)])

    evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert backend.requests[0].candidate_code == _CANDIDATE_CODE


def test_request_never_carries_evaluation_context_fields() -> None:
    """None of the trusted-side context's privileged identifiers ever appear in a request."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend([_execution_result(return_value=6)])

    evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    request = backend.requests[0]
    sensitive_values = [
        context.experiment_run_id,
        context.optimization_run_id,
        context.candidate_frozen_at,
        context.optimization_config_sha256,
    ]
    request_text = f"{request.candidate_code}{request.entry_point}{request.args}{request.kwargs}"
    for value in sensitive_values:
        assert value not in request_text


def test_request_kwargs_are_always_empty() -> None:
    """evaluate_reference never injects hidden kwargs alongside a case's positional args."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend([_execution_result(return_value=6)])

    evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert backend.requests[0].kwargs == {}


# --- Full-versus-mini identifier tests --------------------------------------


def test_full_and_reduced_profiles_have_distinct_identifiers() -> None:
    """The full and reduced-development profiles never share an identifier."""
    assert FULL_EXECUTION_PROFILE.profile_id != REDUCED_DEV_EXECUTION_PROFILE.profile_id
    assert (
        FULL_EXECUTION_PROFILE.evaluator_version != REDUCED_DEV_EXECUTION_PROFILE.evaluator_version
    )


def test_reduced_profile_evaluates_fewer_cases() -> None:
    """A reduced profile with max_cases_per_task=2 evaluates only the first 2 cases."""
    cases = [_case("c0", 1), _case("c1", 2), _case("c2", 3)]
    evidence = _evidence(cases)
    reduced_profile = ExecutionProfile(
        profile_id=EXECUTION_PROFILE_ID_REDUCED_DEV,
        evaluator_version=EVALUATOR_VERSION_REDUCED_DEV,
        limits=ExecutionLimits(),
        max_cases_per_task=2,
    )
    context = _context(
        candidate_sha256=_sha256(_CANDIDATE_CODE),
        evaluator_version=EVALUATOR_VERSION_REDUCED_DEV,
        execution_profile_id=EXECUTION_PROFILE_ID_REDUCED_DEV,
    )
    backend = FakeExecutionBackend(
        [_execution_result(return_value=2), _execution_result(return_value=4)]
    )

    result, diagnostics = evaluate_reference(
        evidence, _CANDIDATE_CODE, context, backend=backend, profile=reduced_profile
    )

    assert result.reference_case_total == 2
    assert len(backend.requests) == 2
    assert len(diagnostics) == 2


def test_reduced_result_never_carries_full_evaluator_version() -> None:
    """A reduced-profile result's context always declares the reduced evaluator_version."""
    cases = [_case("c0", 1)]
    evidence = _evidence(cases)
    context = _context(
        candidate_sha256=_sha256(_CANDIDATE_CODE),
        evaluator_version=EVALUATOR_VERSION_REDUCED_DEV,
        execution_profile_id=EXECUTION_PROFILE_ID_REDUCED_DEV,
    )
    backend = FakeExecutionBackend([_execution_result(return_value=2)])

    result, _diagnostics = evaluate_reference(
        evidence, _CANDIDATE_CODE, context, backend=backend, profile=REDUCED_DEV_EXECUTION_PROFILE
    )

    assert result.context.evaluator_version == EVALUATOR_VERSION_REDUCED_DEV
    assert result.context.evaluator_version != EVALUATOR_VERSION_FULL


# --- Configuration/version validation ----------------------------------------


def test_dataset_version_mismatch_on_context_rejected() -> None:
    """context.dataset_version must match the live pinned HumanEval+ version."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    context = _context(
        candidate_sha256=_sha256(_CANDIDATE_CODE), dataset_version="stale-version"
    )
    backend = FakeExecutionBackend([])

    with pytest.raises(ReferenceEvaluatorVersionMismatchError):
        evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)
    assert not backend.requests


def test_partition_version_mismatch_on_context_rejected() -> None:
    """context.partition_version must match the live PARTITION_ALGORITHM_VERSION."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    context = _context(
        candidate_sha256=_sha256(_CANDIDATE_CODE), partition_version="stale-partition"
    )
    backend = FakeExecutionBackend([])

    with pytest.raises(ReferenceEvaluatorVersionMismatchError):
        evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)
    assert not backend.requests


def test_execution_profile_id_mismatch_on_context_rejected() -> None:
    """context.execution_profile_id must match the profile actually being used."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    context = _context(
        candidate_sha256=_sha256(_CANDIDATE_CODE), execution_profile_id="wrong-profile"
    )
    backend = FakeExecutionBackend([])

    with pytest.raises(ReferenceEvaluatorVersionMismatchError):
        evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)
    assert not backend.requests


def test_evaluator_version_mismatch_on_context_rejected() -> None:
    """context.evaluator_version must match the profile actually being used."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases)
    context = _context(
        candidate_sha256=_sha256(_CANDIDATE_CODE), evaluator_version="wrong-evaluator"
    )
    backend = FakeExecutionBackend([])

    with pytest.raises(ReferenceEvaluatorVersionMismatchError):
        evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)
    assert not backend.requests


def test_evidence_oracle_version_mismatch_rejected() -> None:
    """evidence.oracle_version must match the live ORACLE_ALGORITHM_VERSION."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases, oracle_version="stale-oracle")
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend([])

    with pytest.raises(ReferenceEvaluatorVersionMismatchError):
        evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)
    assert not backend.requests


def test_evidence_protocol_version_mismatch_rejected() -> None:
    """evidence.protocol_version must match the live EXECUTION_PROTOCOL_VERSION."""
    cases = [_case("c0", 3)]
    evidence = _evidence(cases, protocol_version="stale-protocol")
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend([])

    with pytest.raises(ReferenceEvaluatorVersionMismatchError):
        evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)
    assert not backend.requests


def test_evidence_comparison_profile_version_mismatch_rejected() -> None:
    """evidence.comparison_profile.profile_version must match the live
    COMPARISON_PROFILE_VERSION."""
    cases = [_case("c0", 3)]
    stale_profile = dataclasses.replace(
        comparison_profile_for_task(_ENTRY_POINT, atol=0.0), profile_version="stale-comparison"
    )
    evidence = _evidence(cases, comparison_profile=stale_profile)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend([])

    with pytest.raises(ReferenceEvaluatorVersionMismatchError):
        evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)
    assert not backend.requests


# --- ReferenceCase / ReferenceTaskEvidence / ExecutionProfile construction ----


def test_reference_case_empty_case_id_rejected() -> None:
    """ReferenceCase requires a nonempty case_id."""
    with pytest.raises(ValueError):
        ReferenceCase(case_id="", args=(3,), oracle_record=_oracle_record("c0", 3))


def test_reference_case_id_mismatch_with_oracle_record_rejected() -> None:
    """ReferenceCase.case_id must match its own oracle_record.case_id."""
    record = _oracle_record("c0", 3)
    with pytest.raises(ValueError):
        ReferenceCase(case_id="different", args=(3,), oracle_record=record)


def test_evidence_requires_at_least_one_case() -> None:
    """ReferenceTaskEvidence must contain at least one case."""
    with pytest.raises(ValueError):
        _evidence([])


def test_evidence_checksum_mismatch_rejected() -> None:
    """An explicitly wrong reference_case_checksum is rejected, not silently overwritten."""
    with pytest.raises(ValueError):
        _evidence([_case("c0", 3)], reference_case_checksum="0" * 64)


def test_evidence_auto_computes_checksum_when_omitted() -> None:
    """Omitting reference_case_checksum causes it to be computed automatically."""
    evidence = _evidence([_case("c0", 3)])
    assert len(evidence.reference_case_checksum) == 64


def test_evidence_checksum_is_deterministic() -> None:
    """The same case set always produces the same checksum."""
    evidence_a = _evidence([_case("c0", 3), _case("c1", 5)])
    evidence_b = _evidence([_case("c0", 3), _case("c1", 5)])
    assert evidence_a.reference_case_checksum == evidence_b.reference_case_checksum


def test_execution_profile_empty_profile_id_rejected() -> None:
    """ExecutionProfile requires a nonempty profile_id."""
    with pytest.raises(ValueError):
        ExecutionProfile(profile_id="", evaluator_version="v1", limits=ExecutionLimits())


def test_execution_profile_empty_evaluator_version_rejected() -> None:
    """ExecutionProfile requires a nonempty evaluator_version."""
    with pytest.raises(ValueError):
        ExecutionProfile(profile_id="p1", evaluator_version="", limits=ExecutionLimits())


def test_execution_profile_max_cases_per_task_zero_rejected() -> None:
    """max_cases_per_task, if set, must be at least 1."""
    with pytest.raises(ValueError):
        ExecutionProfile(
            profile_id="p1", evaluator_version="v1", limits=ExecutionLimits(), max_cases_per_task=0
        )


# --- Diagnostics and duration ------------------------------------------------


def test_duration_seconds_sums_every_case_wall_time() -> None:
    """result.duration_seconds is the sum of every case's execution wall time."""
    cases = [_case("c0", 1), _case("c1", 2)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend(
        [
            _execution_result(return_value=2, wall_time_sec=0.3),
            _execution_result(return_value=4, wall_time_sec=0.7),
        ]
    )

    result, _diagnostics = evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert result.duration_seconds == pytest.approx(1.0)


def test_privileged_diagnostics_capture_per_case_detail() -> None:
    """PrivilegedCaseDiagnostic entries record execution status/match/timing per case."""
    cases = [_case("c0", 1), _case("c1", 2)]
    evidence = _evidence(cases)
    context = _context(candidate_sha256=_sha256(_CANDIDATE_CODE))
    backend = FakeExecutionBackend(
        [
            _execution_result(return_value=2, invocation_id="inv-a"),
            _execution_result(return_value=999, invocation_id="inv-b"),
        ]
    )

    _result, diagnostics = evaluate_reference(evidence, _CANDIDATE_CODE, context, backend=backend)

    assert diagnostics[0].invocation_id == "inv-a"
    assert diagnostics[0].matched is True
    assert diagnostics[1].invocation_id == "inv-b"
    assert diagnostics[1].matched is False
    assert diagnostics[1].first_failure_category == FailureCategory.WRONG_OUTPUT
