"""Dedicated provenance-chain proof for MEGB-03G.4 correction v2.

Proves, offline, for **both** the benchmark-only synthetic evaluator and
the real reference evaluator, that:

    ReferenceTaskResult.context.execution_protocol_version
    == CandidateExecutionRequest.protocol_version
    == EXECUTION_PROTOCOL_VERSION

i.e. the execution-protocol identity a produced result claims always
matches what was actually sent over the MEGB-02 wire transport, and both
always match the one real constant -- for the synthetic evaluator despite
every other identity field being deliberately distinct, and for the real
evaluator as an unchanged regression check.
"""

import hashlib

from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION

from src.execution.backend import ExecutionBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionLimits,
    ExecutionStatus,
)
from src.execution.wire import encode_value
from src.reference.g4_benchmark_evaluator import (
    G4_COMPARISON_PROFILE_VERSION,
    G4_DATASET_CHECKSUM,
    G4_DATASET_VERSION,
    G4_EVALUATOR_VERSION,
    G4_EXECUTION_PROFILE_ID,
    G4_ORACLE_VERSION,
    G4_PARTITION_VERSION,
    G4_TASK_MANIFEST_CHECKSUM,
    evaluate_g4_benchmark_candidate,
)
from src.reference.oracle import (
    COMPARISON_PROFILE_VERSION,
    ORACLE_ALGORITHM_VERSION,
    POOL_REFERENCE_ONLY,
    ComparisonProfile,
    OracleRecord,
    comparison_profile_for_task,
    generate_oracle_record,
)
from src.reference.partition import PARTITION_ALGORITHM_VERSION
from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EXECUTION_PROFILE_ID_FULL,
    EXECUTION_PROTOCOL_VERSION,
    FULL_EXECUTION_PROFILE,
    ExecutionProfile,
    ReferenceCase,
    ReferenceTaskEvidence,
    evaluate_reference,
)
from src.reference.result_schema import ReferenceRunContext


class _RecordingBackend(ExecutionBackend):
    """A fake backend recording every outbound request's protocol_version."""

    def __init__(self) -> None:
        self.protocol_versions: list[str] = []

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        self.protocol_versions.append(request.protocol_version)
        return CandidateExecutionResult(
            invocation_id="inv-0", status=ExecutionStatus.COMPLETED,
            return_value=request.args[0] * 2,
            exception_type=None, exception_message=None,
            wall_time_sec=0.01, candidate_wall_time_sec=0.005,
            exit_code=0, terminating_signal=None,
            stdout="", stderr="", stdout_truncated=False, stderr_truncated=False,
            backend_id="fake", backend_version="1", runner_image_digest="sha256:fake",
            protocol_version=request.protocol_version,
            limits=ExecutionLimits(), started_at="2026-08-01T00:00:00Z",
        )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_CANDIDATE_CODE = "def double(n):\n    return n * 2\n"
_CANDIDATE_SHA256 = _sha256(_CANDIDATE_CODE)


def test_g4_synthetic_evaluator_protocol_provenance_chain_holds() -> None:
    """For the G4 synthetic evaluator: context, outbound request, and the
    real constant all agree on execution_protocol_version, even though
    every other identity field is deliberately synthetic."""
    task_id = "G4ProtocolProvenance/0"
    record = OracleRecord(
        task_id=task_id,
        case_id="c0",
        pool="megb-03g4-synthetic",
        provenance="megb-03g4-synthetic",
        comparison_profile_kind="default_exact_or_tolerance",
        status="success",
        expected_output=encode_value(6),
        failure_reason=None,
    )
    case = ReferenceCase(case_id="c0", args=(3,), oracle_record=record)
    evidence = ReferenceTaskEvidence(
        task_id=task_id,
        entry_point="double",
        comparison_profile=ComparisonProfile(
            kind="default_exact_or_tolerance",
            atol=0.0,
            profile_version=G4_COMPARISON_PROFILE_VERSION,
        ),
        cases=(case,),
        oracle_version=G4_ORACLE_VERSION,
        partition_version=G4_PARTITION_VERSION,
        dataset_version=G4_DATASET_VERSION,
        protocol_version=EXECUTION_PROTOCOL_VERSION,
        dataset_checksum=G4_DATASET_CHECKSUM,
        task_manifest_checksum=G4_TASK_MANIFEST_CHECKSUM,
    )
    run_context = ReferenceRunContext(
        experiment_run_id="g4-protocol-provenance",
        optimization_run_id="g4-protocol-provenance",
        optimization_config_sha256="0" * 64,
        portfolio_frozen_at="2026-01-01T00:00:00Z",
        portfolio_selection_rule="g4-protocol-provenance-fixed",
        evaluator_version=G4_EVALUATOR_VERSION,
        dataset_version=G4_DATASET_VERSION,
        partition_version=G4_PARTITION_VERSION,
        execution_profile_id=G4_EXECUTION_PROFILE_ID,
        comparison_profile_version=G4_COMPARISON_PROFILE_VERSION,
        execution_protocol_version=EXECUTION_PROTOCOL_VERSION,
        dataset_checksum=G4_DATASET_CHECKSUM,
        task_manifest_checksum=G4_TASK_MANIFEST_CHECKSUM,
    )
    profile = ExecutionProfile(
        profile_id=G4_EXECUTION_PROFILE_ID,
        evaluator_version=G4_EVALUATOR_VERSION,
        limits=ExecutionLimits(),
    )
    backend = _RecordingBackend()

    result, _ = evaluate_g4_benchmark_candidate(
        evidence, _CANDIDATE_CODE, "cand-0", _CANDIDATE_SHA256, run_context,
        backend=backend, profile=profile,
    )

    assert len(backend.protocol_versions) == 1
    assert (
        result.context.execution_protocol_version
        == backend.protocol_versions[0]
        == EXECUTION_PROTOCOL_VERSION
    )
    # Every other identity remains deliberately distinct from the real one.
    assert result.context.evaluator_version != EVALUATOR_VERSION_FULL
    assert result.context.execution_profile_id != EXECUTION_PROFILE_ID_FULL


def test_real_evaluator_protocol_provenance_chain_holds() -> None:
    """Unchanged-regression check: the real evaluate_reference's own
    provenance chain holds exactly the same way."""
    task_id = "Test/ProtocolProvenance"
    prompt = "def double(n):\n"
    canonical_solution = "    return n * 2\n"
    namespace: dict[str, object] = {}
    exec(prompt + canonical_solution, namespace)  # pylint: disable=exec-used
    canonical_fn = namespace["double"]

    profile = comparison_profile_for_task("double", atol=0.0)
    record = generate_oracle_record(
        task_id=task_id,
        case_id="c0",
        args=(3,),
        provenance="original",
        pool=POOL_REFERENCE_ONLY,
        canonical_fn=canonical_fn,  # type: ignore[arg-type]
        profile=profile,
    )
    case = ReferenceCase(case_id="c0", args=(3,), oracle_record=record)
    evidence = ReferenceTaskEvidence(
        task_id=task_id,
        entry_point="double",
        comparison_profile=profile,
        cases=(case,),
        oracle_version=ORACLE_ALGORITHM_VERSION,
        partition_version=PARTITION_ALGORITHM_VERSION,
        dataset_version=HUMANEVAL_PLUS_VERSION,
        protocol_version=EXECUTION_PROTOCOL_VERSION,
        dataset_checksum="fe585eb4df8c88d844eeb463ea4d0302",
        task_manifest_checksum="d" * 64,
    )
    run_context = ReferenceRunContext(
        experiment_run_id="exp-1",
        optimization_run_id="opt-1",
        optimization_config_sha256="b" * 64,
        portfolio_frozen_at="2026-08-01T00:00:00Z",
        portfolio_selection_rule="best_of_run",
        evaluator_version=EVALUATOR_VERSION_FULL,
        dataset_version=HUMANEVAL_PLUS_VERSION,
        partition_version=PARTITION_ALGORITHM_VERSION,
        execution_profile_id=EXECUTION_PROFILE_ID_FULL,
        comparison_profile_version=COMPARISON_PROFILE_VERSION,
        execution_protocol_version=EXECUTION_PROTOCOL_VERSION,
        dataset_checksum="fe585eb4df8c88d844eeb463ea4d0302",
        task_manifest_checksum="d" * 64,
    )
    candidate_code = "def double(n):\n    return n * 2\n"
    candidate_sha256 = _sha256(candidate_code)
    backend = _RecordingBackend()

    result, _ = evaluate_reference(
        evidence, candidate_code, "cand-real", candidate_sha256, run_context,
        backend=backend, profile=FULL_EXECUTION_PROFILE,
    )

    assert len(backend.protocol_versions) == 1
    assert (
        result.context.execution_protocol_version
        == backend.protocol_versions[0]
        == EXECUTION_PROTOCOL_VERSION
    )
