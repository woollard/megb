"""MEGB-03G.4 correction: the benchmark-only synthetic evaluator.

``evaluate_g4_benchmark_candidate`` mirrors ``evaluate_reference``'s exact
call shape and the same real, unmodified execution boundary (an injected
``ExecutionBackend``, ``CandidateExecutionRequest``/``CandidateExecutionResult``,
and EvalPlus's own ``compare_outputs`` comparison algorithm) so it can be
dropped into :class:`~src.reference.reference_orchestrator.OrchestrationConfig`'s
additive ``evaluator`` extension point. It never calls, is called by, or
modifies ``evaluate_reference`` itself: the real evaluator's hardcoded
real-corpus cross-check (``evidence.dataset_version == HUMANEVAL_PLUS_VERSION``,
and the equivalent checks for partition/oracle/comparison-profile/evaluator/
execution-profile/protocol identity) never applies here, because this
function performs its *own*, separate internal-consistency check against
this module's own ``G4_*`` constants only.

Every one of the six version/identity fields ``evaluate_reference``
cross-checks against a real MEGB-03B/C/E/F constant has a distinct,
synthetic counterpart here -- none equal to any real constant (enforced
by :func:`assert_g4_identities_are_synthetic`, and covered by a dedicated
equality-negation test). This function never claims, and cannot be
mistaken for, HumanEval, EvalPlus, the frozen reference partition, or S*.

Reuses ``ReferenceTaskEvidence``/``ReferenceCase``/``OracleRecord``/
``ComparisonProfile``/``ReferenceTaskResult`` as *containers only* --
already-accepted, generic, content-agnostic schemas -- never any function
that itself performs real-corpus validation.
"""

# This module deliberately mirrors evaluate_reference's control flow
# (case-by-case backend invocation, classification, ReferenceTaskResult
# construction) without importing or calling it -- see the module
# docstring for why. The resulting structural similarity is intentional,
# not a refactor target: importing evaluate_reference's own private
# helpers would couple this benchmark-only evaluator to the real
# evaluator's internals and its hardcoded real-corpus constants.
# pylint: disable=duplicate-code

import hashlib
from datetime import datetime, timezone
from typing import Any

from src.evaluators.schema import FailureCategory
from src.execution.backend import ExecutionBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionStatus,
)
from src.execution.wire import decode_value
from src.reference.oracle import ComparisonProfile, compare_outputs
from src.reference.reference_evaluator import (
    ExecutionProfile,
    PrivilegedCaseDiagnostic,
    ReferenceCase,
    ReferenceTaskEvidence,
)
from src.reference.result_schema import MeasurementStatus, ReferenceRunContext, ReferenceTaskResult

# --- Fully synthetic identity constants ---------------------------------------
# None of these equal any real MEGB-03B/C/E/F constant -- see
# assert_g4_identities_are_synthetic() and its dedicated test.

G4_EVALUATOR_VERSION = "megb-03g4-benchmark-evaluator-v1"
G4_EXECUTION_PROFILE_ID = "megb-03g4-benchmark-profile-v1"
G4_EXECUTION_PROTOCOL_VERSION = "megb-03g4-benchmark-protocol-v1"
G4_DATASET_VERSION = "megb-03g4-synthetic-dataset-v1"
G4_PARTITION_VERSION = "megb-03g4-synthetic-partition-v1"
G4_ORACLE_VERSION = "megb-03g4-synthetic-oracle-v1"
G4_COMPARISON_PROFILE_VERSION = "megb-03g4-synthetic-comparison-v1"
G4_DATASET_CHECKSUM = hashlib.sha256(b"megb-03g4-synthetic-dataset-content-v1").hexdigest()
G4_TASK_MANIFEST_CHECKSUM = hashlib.sha256(b"megb-03g4-synthetic-manifest-content-v1").hexdigest()


class G4BenchmarkEvaluatorVersionMismatchError(ValueError):
    """A ``run_context``/``evidence`` field this benchmark evaluator checks
    does not match this module's own ``G4_*`` synthetic identity constants.

    Distinct from ``ReferenceEvaluatorVersionMismatchError`` (the real
    evaluator's own exception): this evaluator never raises that type and
    never shares an exception hierarchy with the real evaluator, keeping
    the two fully independent."""


class G4CandidateIdentityMismatchError(ValueError):
    """``candidate_sha256`` does not match ``sha256(candidate_code)``."""


def assert_g4_identities_are_synthetic() -> None:
    """Fail loudly (at import time, via a dedicated test) if any ``G4_*``
    identity constant here ever collided with a real MEGB-03B/C/E/F
    constant -- structural proof, not just convention, that this module
    never claims real-corpus identity."""
    from src.reference.oracle import (  # pylint: disable=import-outside-toplevel
        COMPARISON_PROFILE_VERSION,
        ORACLE_ALGORITHM_VERSION,
    )
    from src.reference.partition import (  # pylint: disable=import-outside-toplevel
        PARTITION_ALGORITHM_VERSION,
    )
    from src.reference.reference_evaluator import (  # pylint: disable=import-outside-toplevel
        EVALUATOR_VERSION_FULL,
        EVALUATOR_VERSION_REDUCED_DEV,
        EXECUTION_PROFILE_ID_FULL,
        EXECUTION_PROFILE_ID_REDUCED_DEV,
        EXECUTION_PROTOCOL_VERSION,
    )

    real_identities = {
        G4_EVALUATOR_VERSION: (EVALUATOR_VERSION_FULL, EVALUATOR_VERSION_REDUCED_DEV),
        G4_EXECUTION_PROFILE_ID: (EXECUTION_PROFILE_ID_FULL, EXECUTION_PROFILE_ID_REDUCED_DEV),
        G4_EXECUTION_PROTOCOL_VERSION: (EXECUTION_PROTOCOL_VERSION,),
        G4_ORACLE_VERSION: (ORACLE_ALGORITHM_VERSION,),
        G4_PARTITION_VERSION: (PARTITION_ALGORITHM_VERSION,),
        G4_COMPARISON_PROFILE_VERSION: (COMPARISON_PROFILE_VERSION,),
    }
    for synthetic_value, real_values in real_identities.items():
        if synthetic_value in real_values:
            raise G4BenchmarkEvaluatorVersionMismatchError(
                f"G4 benchmark identity {synthetic_value!r} collides with a real constant"
            )


def _verify_g4_candidate_identity(candidate_code: str, candidate_sha256: str) -> None:
    actual_sha256 = hashlib.sha256(candidate_code.encode("utf-8")).hexdigest()
    if actual_sha256 != candidate_sha256:
        raise G4CandidateIdentityMismatchError(
            f"candidate source sha256 {actual_sha256!r} does not match the expected "
            f"candidate_sha256 {candidate_sha256!r}"
        )


def _verify_g4_versions(run_context: ReferenceRunContext, evidence: ReferenceTaskEvidence) -> None:
    """This benchmark's own internal-consistency check -- run_context must
    agree with evidence, and both must agree with this module's own G4_*
    constants. Never compares against any real MEGB-03B/C/E/F constant."""
    checks = (
        ("dataset_version", run_context.dataset_version, evidence.dataset_version),
        ("dataset_version", evidence.dataset_version, G4_DATASET_VERSION),
        ("dataset_checksum", run_context.dataset_checksum, evidence.dataset_checksum),
        ("partition_version", run_context.partition_version, evidence.partition_version),
        ("partition_version", evidence.partition_version, G4_PARTITION_VERSION),
        (
            "task_manifest_checksum",
            run_context.task_manifest_checksum,
            evidence.task_manifest_checksum,
        ),
        ("execution_profile_id", run_context.execution_profile_id, G4_EXECUTION_PROFILE_ID),
        ("evaluator_version", run_context.evaluator_version, G4_EVALUATOR_VERSION),
        ("oracle_version", evidence.oracle_version, G4_ORACLE_VERSION),
        (
            "comparison_profile_version",
            run_context.comparison_profile_version,
            evidence.comparison_profile.profile_version,
        ),
        (
            "comparison_profile_version",
            evidence.comparison_profile.profile_version,
            G4_COMPARISON_PROFILE_VERSION,
        ),
        (
            "execution_protocol_version",
            run_context.execution_protocol_version,
            evidence.protocol_version,
        ),
        ("protocol_version", evidence.protocol_version, G4_EXECUTION_PROTOCOL_VERSION),
    )
    for label, actual, expected in checks:
        if actual != expected:
            raise G4BenchmarkEvaluatorVersionMismatchError(
                f"{label} mismatch: got {actual!r}, expected {expected!r}"
            )


def _build_g4_request(
    candidate_code: str, entry_point: str, args: tuple[Any, ...], profile: ExecutionProfile
) -> CandidateExecutionRequest:
    """A local, fully independent request builder -- never reuses
    ``reference_evaluator._build_request``, which hardcodes the real
    ``EXECUTION_PROTOCOL_VERSION``. This benchmark's requests always carry
    ``G4_EXECUTION_PROTOCOL_VERSION`` instead."""
    return CandidateExecutionRequest(
        candidate_code=candidate_code,
        entry_point=entry_point,
        args=args,
        kwargs={},
        limits=profile.limits,
        protocol_version=G4_EXECUTION_PROTOCOL_VERSION,
    )


_CANDIDATE_FAILURE_CATEGORIES = {
    ExecutionStatus.SYNTAX_ERROR: FailureCategory.SYNTAX_ERROR,
    ExecutionStatus.CANDIDATE_EXCEPTION: FailureCategory.RUNTIME_EXCEPTION,
    ExecutionStatus.TIMEOUT: FailureCategory.TIMEOUT,
    ExecutionStatus.OUT_OF_MEMORY: FailureCategory.RESOURCE_LIMIT,
    ExecutionStatus.PROCESS_LIMIT: FailureCategory.RESOURCE_LIMIT,
    ExecutionStatus.OUTPUT_LIMIT: FailureCategory.OUTPUT_LIMIT,
}


def _classify_g4_case(
    case: ReferenceCase, result: CandidateExecutionResult, comparison_profile: ComparisonProfile
) -> tuple[bool | None, FailureCategory, MeasurementStatus | None]:
    """Mirrors ``evaluate_reference``'s own classification order exactly:
    measurement-apparatus failures (protocol/infrastructure/oracle) are
    checked before ever attempting to decode or compare an output, so a
    failed oracle record is never silently treated as a match (or crashes
    on a ``None`` expected_output)."""
    status = result.status
    if status == ExecutionStatus.PROTOCOL_ERROR:
        return None, FailureCategory.PROTOCOL_ERROR, MeasurementStatus.INVALID_PROTOCOL
    if status == ExecutionStatus.INFRASTRUCTURE_ERROR:
        return None, FailureCategory.INFRASTRUCTURE_ERROR, MeasurementStatus.INVALID_INFRASTRUCTURE
    if status in _CANDIDATE_FAILURE_CATEGORIES:
        return False, _CANDIDATE_FAILURE_CATEGORIES[status], None
    if status == ExecutionStatus.COMPLETED:
        if case.oracle_record.status != "success":
            return None, FailureCategory.INFRASTRUCTURE_ERROR, MeasurementStatus.INVALID_ORACLE
        expected = decode_value(case.oracle_record.expected_output)
        matched = compare_outputs(comparison_profile, case.args, result.return_value, expected)
        if matched:
            return True, FailureCategory.NONE, None
        return False, FailureCategory.WRONG_OUTPUT, None
    raise ValueError(f"no known classification for ExecutionStatus {status!r}")


def evaluate_g4_benchmark_candidate(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    evidence: ReferenceTaskEvidence,
    candidate_code: str,
    candidate_id: str,
    candidate_sha256: str,
    run_context: ReferenceRunContext,
    *,
    backend: ExecutionBackend,
    profile: ExecutionProfile,
) -> tuple[ReferenceTaskResult, tuple[PrivilegedCaseDiagnostic, ...]]:
    """Benchmark-only evaluator: same real-backend, same-shape evaluation as
    ``evaluate_reference``, against fully synthetic, non-privileged
    evidence, verified only against this module's own ``G4_*`` constants."""
    _verify_g4_candidate_identity(candidate_code, candidate_sha256)
    _verify_g4_versions(run_context, evidence)

    if profile.max_cases_per_task:
        cases = evidence.cases[: profile.max_cases_per_task]
    else:
        cases = evidence.cases
    pass_count = 0
    first_failure_category = FailureCategory.NONE
    execution_failure_counts: dict[str, int] = {}
    diagnostics: list[PrivilegedCaseDiagnostic] = []
    invalid_status: MeasurementStatus | None = None
    invalid_category = FailureCategory.NONE
    total_duration = 0.0

    for case in cases:
        request = _build_g4_request(candidate_code, evidence.entry_point, case.args, profile)
        result = backend.execute(request)
        total_duration += result.wall_time_sec

        matched, category, case_invalid_status = _classify_g4_case(
            case, result, evidence.comparison_profile
        )
        diagnostics.append(
            PrivilegedCaseDiagnostic(
                case_id=case.case_id,
                execution_status=result.status,
                matched=matched,
                first_failure_category=category,
                invocation_id=result.invocation_id,
                wall_time_sec=result.wall_time_sec,
                candidate_wall_time_sec=result.candidate_wall_time_sec,
                backend_id=result.backend_id,
                backend_version=result.backend_version,
                runner_image_digest=result.runner_image_digest,
            )
        )
        if case_invalid_status is not None:
            invalid_status, invalid_category = case_invalid_status, category
            break
        if matched:
            pass_count += 1
        else:
            if first_failure_category == FailureCategory.NONE:
                first_failure_category = category
            execution_failure_counts[category.value] = (
                execution_failure_counts.get(category.value, 0) + 1
            )

    evaluated_at = datetime.now(timezone.utc).isoformat()

    if invalid_status is not None:
        return (
            ReferenceTaskResult(
                task_id=evidence.task_id,
                candidate_id=candidate_id,
                candidate_sha256=candidate_sha256,
                context=run_context,
                status=invalid_status,
                q_ref_task=None,
                reference_case_total=len(diagnostics),
                reference_case_pass_count=pass_count,
                first_failure_category=invalid_category,
                oracle_version=evidence.oracle_version,
                reference_case_checksum=evidence.reference_case_checksum,
                evaluated_at=evaluated_at,
                duration_seconds=total_duration,
                execution_failure_counts={},
            ),
            tuple(diagnostics),
        )

    q_ref_task = 1.0 if pass_count == len(cases) else 0.0
    return (
        ReferenceTaskResult(
            task_id=evidence.task_id,
            candidate_id=candidate_id,
            candidate_sha256=candidate_sha256,
            context=run_context,
            status=MeasurementStatus.VALID,
            q_ref_task=q_ref_task,
            reference_case_total=len(cases),
            reference_case_pass_count=pass_count,
            first_failure_category=first_failure_category,
            oracle_version=evidence.oracle_version,
            reference_case_checksum=evidence.reference_case_checksum,
            evaluated_at=evaluated_at,
            duration_seconds=total_duration,
            execution_failure_counts=execution_failure_counts,
        ),
        tuple(diagnostics),
    )
