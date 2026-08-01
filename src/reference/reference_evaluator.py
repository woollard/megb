"""MEGB-03F: trusted-side task-level reference evaluator (S*).

Orchestrates evaluating one frozen candidate against one task's frozen
reference-only evidence through the MEGB-02 execution boundary, producing a
MEGB-03E-typed :class:`~src.reference.result_schema.ReferenceTaskResult`.

Candidate code is never executed in this (trusted controller) process — every
case invocation goes through an injected :class:`~src.execution.backend.ExecutionBackend`
(normally :class:`~src.execution.docker_backend.DockerPerInvocationBackend`,
which launches one fresh, isolated container per invocation). Expected
outputs and comparison rules never leave this module: only candidate source,
entry point, arguments, resource limits, and protocol version are sent
through the execution boundary (:class:`~src.execution.protocol.CandidateExecutionRequest`);
comparison against the oracle's expected output happens only after the
result comes back.

Two output channels, matching MEGB-03E's privileged/redacted split: the
returned :class:`~src.reference.result_schema.ReferenceTaskResult` is the
authorized projection; the accompanying tuple of :class:`PrivilegedCaseDiagnostic`
carries case-level detail (comparison outcome, raw execution metadata) that
must never be handed to a development-facing consumer. Persisting those
diagnostics to durable storage is explicitly out of scope here — see
Non-Goals below and MEGB-03G's "Audit" responsibility.

Non-goals (per the ticket): benchmark aggregation, candidate generation/
revision/selection, adaptive querying of S*, and performance batching unless
separately approved and versioned — every case is one independent
``backend.execute()`` call, sequentially, matching MEGB-02's one-container-
per-invocation isolation model exactly.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION

from src.evaluators.schema import FailureCategory
from src.execution.backend import ExecutionBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionLimits,
    ExecutionStatus,
)
from src.execution.wire import decode_value
from src.reference.oracle import (
    COMPARISON_PROFILE_VERSION,
    ORACLE_ALGORITHM_VERSION,
    ORACLE_STATUS_SUCCESS,
    ComparisonProfile,
    OracleRecord,
    compare_outputs,
)
from src.reference.partition import PARTITION_ALGORITHM_VERSION
from src.reference.result_schema import (
    MeasurementStatus,
    ReferenceEvaluationContext,
    ReferenceTaskResult,
)

EXECUTION_PROTOCOL_VERSION = "reference-evaluator-execution-protocol-v1"

EXECUTION_PROFILE_ID_FULL = "docker-megb02-full-v1"
EXECUTION_PROFILE_ID_REDUCED_DEV = "docker-megb02-reduced-dev-v1"

EVALUATOR_VERSION_FULL = "reference-evaluator-v1"
EVALUATOR_VERSION_REDUCED_DEV = "reference-evaluator-reduced-dev-v1"

# ExecutionStatus values whose case-level outcome is attributable to the
# candidate itself (the case ran to completion or a candidate-caused
# failure) — mapped to a MeasurementStatus.VALID case outcome and a
# FailureCategory drawn from _CANDIDATE_FAILURE_CATEGORY_BY_STATUS below.
_CANDIDATE_FAILURE_CATEGORY_BY_STATUS: Mapping[ExecutionStatus, FailureCategory] = {
    ExecutionStatus.SYNTAX_ERROR: FailureCategory.SYNTAX_ERROR,
    ExecutionStatus.CANDIDATE_EXCEPTION: FailureCategory.RUNTIME_EXCEPTION,
    ExecutionStatus.TIMEOUT: FailureCategory.TIMEOUT,
    ExecutionStatus.OUT_OF_MEMORY: FailureCategory.RESOURCE_LIMIT,
    ExecutionStatus.PROCESS_LIMIT: FailureCategory.RESOURCE_LIMIT,
    ExecutionStatus.OUTPUT_LIMIT: FailureCategory.OUTPUT_LIMIT,
}

# ExecutionStatus values that mean the measurement apparatus itself failed —
# never attributable to the candidate. Any case hitting one of these
# invalidates the whole task's measurement (MeasurementStatus.INVALID_*).
_INVALID_MEASUREMENT_STATUS_BY_EXECUTION_STATUS: Mapping[ExecutionStatus, MeasurementStatus] = {
    ExecutionStatus.PROTOCOL_ERROR: MeasurementStatus.INVALID_PROTOCOL,
    ExecutionStatus.INFRASTRUCTURE_ERROR: MeasurementStatus.INVALID_INFRASTRUCTURE,
}

# MEGB-03E's accepted ReferenceTaskResult schema requires a measurement-
# apparatus FailureCategory (never NONE) whenever status is a non-VALID,
# non-INCOMPLETE MeasurementStatus. INVALID_ORACLE has no dedicated
# FailureCategory of its own in that already-accepted taxonomy, so it is
# mapped to INFRASTRUCTURE_ERROR — a broken/missing oracle record reflects
# a defect in the trusted evaluation infrastructure, not a candidate/
# sandbox communication protocol failure.
_MEASUREMENT_FAILURE_CATEGORY_BY_INVALID_STATUS: Mapping[MeasurementStatus, FailureCategory] = {
    MeasurementStatus.INVALID_PROTOCOL: FailureCategory.PROTOCOL_ERROR,
    MeasurementStatus.INVALID_INFRASTRUCTURE: FailureCategory.INFRASTRUCTURE_ERROR,
    MeasurementStatus.INVALID_ORACLE: FailureCategory.INFRASTRUCTURE_ERROR,
}


class CandidateIdentityMismatchError(ValueError):
    """The candidate source's SHA-256 does not match ``context.candidate_sha256``.

    Blocks execution outright (acceptance criterion: "Candidate hash
    mismatch blocks execution") — this is a caller-contract violation, not
    a normal invalid-measurement outcome, so it is raised rather than
    encoded as a ``ReferenceTaskResult``.
    """


class ReferenceEvaluatorVersionMismatchError(ValueError):
    """A version/checksum ``evaluate_reference`` depends on does not match
    what ``context`` or ``evidence`` declares.

    Raised before any candidate code executes — refuses to silently
    evaluate against a stale or inconsistent dataset/partition/oracle/
    comparison/protocol/execution-profile combination.
    """


class UnclassifiedExecutionStatusError(RuntimeError):
    """An ``ExecutionStatus`` value has no known mapping to a candidate
    failure or invalid-measurement outcome.

    Guards requirement 11 ("Prevent unclassified failures from becoming
    valid zero scores"): rather than defaulting an unrecognized status to
    a pass or a candidate failure, construction fails loudly so a new
    ``ExecutionStatus`` value can never silently produce a wrong score.
    """


@dataclass(frozen=True)
class ReferenceCase:
    """One authorized reference-only case: its input and trusted expected output."""

    case_id: str
    args: tuple[Any, ...]
    oracle_record: OracleRecord

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("case_id must be nonempty")
        if self.oracle_record.case_id != self.case_id:
            raise ValueError(
                f"oracle_record.case_id {self.oracle_record.case_id!r} does not match "
                f"case_id {self.case_id!r}"
            )


def _reference_case_checksum(task_id: str, cases: tuple[ReferenceCase, ...]) -> str:
    hasher = hashlib.sha256()
    hasher.update(task_id.encode("utf-8"))
    for case in cases:
        hasher.update(b"\x00")
        hasher.update(case.case_id.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(case.oracle_record.status.encode("utf-8"))
    return hasher.hexdigest()


@dataclass(frozen=True)
class ReferenceTaskEvidence:
    """Trusted-side bundle of everything needed to evaluate one task.

    Never passed to candidate code, never returned from ``evaluate_reference``
    — only ``args`` (never expected outputs) cross the execution boundary,
    one case at a time, inside a freshly constructed
    ``CandidateExecutionRequest``.

    ``cases`` must already be sorted by ``case_id`` — construction enforces
    this (requirement 7: deterministic test ordering) rather than sorting
    silently, so a caller that assembled cases out of order fails loudly
    instead of getting a silently reordered evaluation.
    """

    task_id: str
    entry_point: str
    comparison_profile: ComparisonProfile
    cases: tuple[ReferenceCase, ...]
    oracle_version: str
    partition_version: str
    dataset_version: str
    protocol_version: str
    reference_case_checksum: str = ""

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError("task_id must be nonempty")
        if not self.entry_point:
            raise ValueError("entry_point must be nonempty")
        if not self.cases:
            raise ValueError(f"task {self.task_id!r}: evidence must contain at least one case")
        case_ids = [case.case_id for case in self.cases]
        if case_ids != sorted(case_ids):
            raise ValueError(
                f"task {self.task_id!r}: cases must be sorted by case_id for deterministic "
                f"ordering, got {case_ids!r}"
            )
        if len(case_ids) != len(set(case_ids)):
            raise ValueError(f"task {self.task_id!r}: cases contains duplicate case_id entries")
        expected_checksum = _reference_case_checksum(self.task_id, self.cases)
        if self.reference_case_checksum and self.reference_case_checksum != expected_checksum:
            raise ValueError(
                f"task {self.task_id!r}: reference_case_checksum {self.reference_case_checksum!r} "
                f"does not match the recomputed checksum {expected_checksum!r} over its own "
                f"cases — evidence bundle is inconsistent"
            )
        object.__setattr__(self, "reference_case_checksum", expected_checksum)


@dataclass(frozen=True)
class ExecutionProfile:
    """A named, versioned execution configuration for ``evaluate_reference``.

    Both the full and reduced-development profiles route every invocation
    through the same ``ExecutionBackend`` (normally
    ``DockerPerInvocationBackend``) — "reduced" only ever means a smaller,
    deterministic case subset and a distinct evaluator identifier, never a
    less-isolated execution mechanism (requirement 5 applies to both).
    """

    profile_id: str
    evaluator_version: str
    limits: ExecutionLimits
    max_cases_per_task: int | None = None

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("profile_id must be nonempty")
        if not self.evaluator_version:
            raise ValueError("evaluator_version must be nonempty")
        if self.max_cases_per_task is not None and self.max_cases_per_task < 1:
            raise ValueError("max_cases_per_task must be at least 1 when set")


FULL_EXECUTION_PROFILE = ExecutionProfile(
    profile_id=EXECUTION_PROFILE_ID_FULL,
    evaluator_version=EVALUATOR_VERSION_FULL,
    limits=ExecutionLimits(),
)

REDUCED_DEV_EXECUTION_PROFILE = ExecutionProfile(
    profile_id=EXECUTION_PROFILE_ID_REDUCED_DEV,
    evaluator_version=EVALUATOR_VERSION_REDUCED_DEV,
    limits=ExecutionLimits(wall_time_sec=1.0),
    max_cases_per_task=3,
)


@dataclass(frozen=True)
class PrivilegedCaseDiagnostic:
    """Privileged, case-level detail for one candidate invocation.

    Never returned to a development-facing consumer: ``expected_output`` on
    the underlying oracle record and ``matched`` together would let a
    caller reconstruct which specific inputs the candidate got right or
    wrong. Persisting this to durable storage is out of scope for MEGB-03F
    (MEGB-03G's "Audit" responsibility) — callers receive it in-memory only.
    """

    case_id: str
    execution_status: ExecutionStatus
    matched: bool | None
    first_failure_category: FailureCategory
    invocation_id: str
    wall_time_sec: float
    candidate_wall_time_sec: float | None
    backend_id: str
    backend_version: str
    runner_image_digest: str


def _verify_candidate_identity(candidate_code: str, context: ReferenceEvaluationContext) -> None:
    actual_sha256 = hashlib.sha256(candidate_code.encode("utf-8")).hexdigest()
    if actual_sha256 != context.candidate_sha256:
        raise CandidateIdentityMismatchError(
            f"candidate source sha256 {actual_sha256!r} does not match "
            f"context.candidate_sha256 {context.candidate_sha256!r}"
        )


def _verify_versions(
    context: ReferenceEvaluationContext, evidence: ReferenceTaskEvidence, profile: ExecutionProfile
) -> None:
    checks = (
        ("dataset_version", context.dataset_version, evidence.dataset_version),
        ("dataset_version", evidence.dataset_version, HUMANEVAL_PLUS_VERSION),
        ("partition_version", context.partition_version, evidence.partition_version),
        ("partition_version", evidence.partition_version, PARTITION_ALGORITHM_VERSION),
        ("execution_profile_id", context.execution_profile_id, profile.profile_id),
        ("evaluator_version", context.evaluator_version, profile.evaluator_version),
        ("oracle_version", evidence.oracle_version, ORACLE_ALGORITHM_VERSION),
        (
            "comparison_profile_version",
            evidence.comparison_profile.profile_version,
            COMPARISON_PROFILE_VERSION,
        ),
        ("protocol_version", evidence.protocol_version, EXECUTION_PROTOCOL_VERSION),
    )
    for label, actual, expected in checks:
        if actual != expected:
            raise ReferenceEvaluatorVersionMismatchError(
                f"{label} mismatch: got {actual!r}, expected {expected!r}"
            )


def _select_cases(
    evidence: ReferenceTaskEvidence, profile: ExecutionProfile
) -> tuple[ReferenceCase, ...]:
    if profile.max_cases_per_task is None:
        return evidence.cases
    return evidence.cases[: profile.max_cases_per_task]


def _build_request(
    candidate_code: str, entry_point: str, args: tuple[Any, ...], profile: ExecutionProfile
) -> CandidateExecutionRequest:
    return CandidateExecutionRequest(
        candidate_code=candidate_code,
        entry_point=entry_point,
        args=args,
        kwargs={},
        limits=profile.limits,
        protocol_version=EXECUTION_PROTOCOL_VERSION,
    )


def _classify_execution_result(
    case: ReferenceCase,
    execution_result: CandidateExecutionResult,
    comparison_profile: ComparisonProfile,
) -> tuple[bool | None, FailureCategory, MeasurementStatus | None]:
    """Returns (matched, first_failure_category, invalid_measurement_status_or_none).

    For an invalid-measurement outcome, ``first_failure_category`` is always
    a measurement-apparatus category (``PROTOCOL_ERROR``/``INFRASTRUCTURE_ERROR``)
    per MEGB-03E's accepted schema, which requires exactly this for any
    non-VALID, non-INCOMPLETE ``ReferenceTaskResult`` — never ``NONE``.
    """
    status = execution_result.status

    if status in _INVALID_MEASUREMENT_STATUS_BY_EXECUTION_STATUS:
        invalid_status = _INVALID_MEASUREMENT_STATUS_BY_EXECUTION_STATUS[status]
        return None, _MEASUREMENT_FAILURE_CATEGORY_BY_INVALID_STATUS[invalid_status], invalid_status

    if status in _CANDIDATE_FAILURE_CATEGORY_BY_STATUS:
        return False, _CANDIDATE_FAILURE_CATEGORY_BY_STATUS[status], None

    if status == ExecutionStatus.COMPLETED:
        if case.oracle_record.status != ORACLE_STATUS_SUCCESS:
            category = _MEASUREMENT_FAILURE_CATEGORY_BY_INVALID_STATUS[
                MeasurementStatus.INVALID_ORACLE
            ]
            return None, category, MeasurementStatus.INVALID_ORACLE
        expected = decode_value(case.oracle_record.expected_output)
        matched = compare_outputs(
            comparison_profile,
            case.args,
            execution_result.return_value,
            expected,
        )
        if matched:
            return True, FailureCategory.NONE, None
        return False, FailureCategory.WRONG_OUTPUT, None

    raise UnclassifiedExecutionStatusError(f"no known mapping for ExecutionStatus {status!r}")


def evaluate_reference(  # pylint: disable=too-many-locals
    evidence: ReferenceTaskEvidence,
    candidate_code: str,
    context: ReferenceEvaluationContext,
    *,
    backend: ExecutionBackend,
    profile: ExecutionProfile = FULL_EXECUTION_PROFILE,
) -> tuple[ReferenceTaskResult, tuple[PrivilegedCaseDiagnostic, ...]]:
    """Evaluate one frozen candidate against one task's frozen reference-only evidence.

    Deviates from the ticket's minimal illustrative signature
    (``evaluate_reference(task_id, candidate_code, context)``) by taking the
    trusted evidence bundle, execution backend, and execution profile as
    explicit parameters rather than discovering them internally — the
    ticket itself invites "an interface similar to" this signature, and a
    pure 3-argument function cannot function without knowing where to load
    privileged oracle evidence from or which backend/profile to use.

    Every case is sent through ``backend.execute()`` exactly once,
    sequentially, in ``evidence.cases`` order (already validated as sorted
    by ``case_id``) — never batched, never in the trusted controller
    process, never carrying the oracle's expected output.
    """
    _verify_candidate_identity(candidate_code, context)
    _verify_versions(context, evidence, profile)

    selected_cases = _select_cases(evidence, profile)
    reference_case_total = len(selected_cases)
    reference_case_pass_count = 0
    first_failure_category = FailureCategory.NONE
    execution_failure_counts: dict[str, int] = {}
    diagnostics: list[PrivilegedCaseDiagnostic] = []
    invalid_status: MeasurementStatus | None = None
    invalid_category = FailureCategory.NONE
    total_duration = 0.0

    for case in selected_cases:
        request = _build_request(candidate_code, evidence.entry_point, case.args, profile)
        execution_result = backend.execute(request)
        total_duration += execution_result.wall_time_sec

        matched, category, case_invalid_status = _classify_execution_result(
            case, execution_result, evidence.comparison_profile
        )

        diagnostics.append(
            PrivilegedCaseDiagnostic(
                case_id=case.case_id,
                execution_status=execution_result.status,
                matched=matched,
                first_failure_category=category,
                invocation_id=execution_result.invocation_id,
                wall_time_sec=execution_result.wall_time_sec,
                candidate_wall_time_sec=execution_result.candidate_wall_time_sec,
                backend_id=execution_result.backend_id,
                backend_version=execution_result.backend_version,
                runner_image_digest=execution_result.runner_image_digest,
            )
        )

        if case_invalid_status is not None:
            invalid_status = case_invalid_status
            invalid_category = category
            break

        if matched:
            reference_case_pass_count += 1
        else:
            if first_failure_category == FailureCategory.NONE:
                first_failure_category = category
            execution_failure_counts[category.value] = (
                execution_failure_counts.get(category.value, 0) + 1
            )

    evaluated_at = datetime.now(timezone.utc).isoformat()

    if invalid_status is not None:
        result = ReferenceTaskResult(
            task_id=evidence.task_id,
            context=context,
            status=invalid_status,
            q_ref_task=None,
            reference_case_total=len(diagnostics),
            reference_case_pass_count=reference_case_pass_count,
            first_failure_category=invalid_category,
            oracle_version=evidence.oracle_version,
            reference_case_checksum=evidence.reference_case_checksum,
            evaluated_at=evaluated_at,
            duration_seconds=total_duration,
            execution_failure_counts={},
        )
        return result, tuple(diagnostics)

    q_ref_task = 1.0 if reference_case_pass_count == reference_case_total else 0.0
    result = ReferenceTaskResult(
        task_id=evidence.task_id,
        context=context,
        status=MeasurementStatus.VALID,
        q_ref_task=q_ref_task,
        reference_case_total=reference_case_total,
        reference_case_pass_count=reference_case_pass_count,
        first_failure_category=first_failure_category,
        oracle_version=evidence.oracle_version,
        reference_case_checksum=evidence.reference_case_checksum,
        evaluated_at=evaluated_at,
        duration_seconds=total_duration,
        execution_failure_counts=execution_failure_counts,
    )
    return result, tuple(diagnostics)
