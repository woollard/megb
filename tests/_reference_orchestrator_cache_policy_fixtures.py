"""Synthetic fixtures shared between ``test_reference_orchestrator_cache_policy.py``
and ``test_reference_orchestrator_trace_matrix.py`` (MEGB-03H.2B.1): evidence/
context/work-item builders, controllable fake execution backends, and an
in-memory ``TraceRecorder`` -- kept in one place so both test modules
exercise the exact same baseline fixtures rather than two drifting copies.
No real privileged corpus access, no Docker.
"""

# Intentionally mirrors patterns already present in test_reference_evaluator.py
# and test_reference_orchestrator.py (evidence/context/work-item/execution-
# result construction) -- suppressing here rather than coupling this shared
# fixtures module to those other, unrelated test modules' internals.
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
from src.reference.oracle import (
    COMPARISON_PROFILE_VERSION,
    ORACLE_ALGORITHM_VERSION,
    POOL_REFERENCE_ONLY,
    comparison_profile_for_task,
    generate_oracle_record,
)
from src.reference.orchestration_trace import CachePolicy, FreshExecutionAttempt
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

ENTRY_POINT = "double"
_PROMPT = f"def {ENTRY_POINT}(n):\n"
_CANONICAL_SOLUTION = "    return n * 2\n"
TASK_ID = "Test/0"
CORRECT_CANDIDATE_CODE = "def double(n):\n    return n * 2\n"

DATASET_CHECKSUM = "fe585eb4df8c88d844eeb463ea4d0302"
TASK_MANIFEST_CHECKSUM = "d" * 64


def sha256(text: str) -> str:
    """Hex sha256 digest of ``text``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def oracle_record(task_id: str, case_id: str, n: int) -> Any:
    """A real, generated oracle record for ``double(n)``."""
    profile = comparison_profile_for_task(ENTRY_POINT, atol=0.0)
    namespace: dict[str, Any] = {}
    exec(_PROMPT + _CANONICAL_SOLUTION, namespace)  # pylint: disable=exec-used
    canonical_fn = namespace[ENTRY_POINT]
    return generate_oracle_record(
        task_id=task_id,
        case_id=case_id,
        args=(n,),
        provenance="original",
        pool=POOL_REFERENCE_ONLY,
        canonical_fn=canonical_fn,
        profile=profile,
    )


def evidence(task_id: str = TASK_ID, num_cases: int = 1) -> ReferenceTaskEvidence:
    """Synthetic single/multi-case evidence for ``task_id``."""
    cases = tuple(
        ReferenceCase(
            case_id=f"c{i}", args=(i + 1,), oracle_record=oracle_record(task_id, f"c{i}", i + 1)
        )
        for i in range(num_cases)
    )
    return ReferenceTaskEvidence(
        task_id=task_id,
        entry_point=ENTRY_POINT,
        comparison_profile=comparison_profile_for_task(ENTRY_POINT, atol=0.0),
        cases=cases,
        oracle_version=ORACLE_ALGORITHM_VERSION,
        partition_version=PARTITION_ALGORITHM_VERSION,
        dataset_version=HUMANEVAL_PLUS_VERSION,
        protocol_version=EXECUTION_PROTOCOL_VERSION,
        dataset_checksum=DATASET_CHECKSUM,
        task_manifest_checksum=TASK_MANIFEST_CHECKSUM,
    )


def run_context(**overrides: object) -> ReferenceRunContext:
    """A synthetic run context, with any field overridable."""
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
        "dataset_checksum": DATASET_CHECKSUM,
        "task_manifest_checksum": TASK_MANIFEST_CHECKSUM,
    }
    fields.update(overrides)
    return ReferenceRunContext(**fields)  # type: ignore[arg-type]


def work_item(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    work_item_id: str,
    input_ordinal: int,
    *,
    task_id: str = TASK_ID,
    candidate_code: str = CORRECT_CANDIDATE_CODE,
    task_evaluation_replicate_id: int = 0,
) -> WorkItem:
    """A synthetic WorkItem for ``task_id``/``candidate_code``."""
    return WorkItem(
        work_item_id=work_item_id,
        input_ordinal=input_ordinal,
        task_id=task_id,
        candidate_id=f"cand-{work_item_id}",
        candidate_sha256=sha256(candidate_code),
        candidate_code=candidate_code,
        run_context=run_context(),
        task_evaluation_replicate_id=task_evaluation_replicate_id,
    )


def execution_result(
    status: ExecutionStatus, return_value: object, invocation_id: str
) -> CandidateExecutionResult:
    """A synthetic CandidateExecutionResult carrying ``status``."""
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
        return execution_result(ExecutionStatus.COMPLETED, n * 2, invocation_id)


class WrongAnswerBackend(ExecutionBackend):
    """Always returns a wrong value -- a VALID but q_ref_task=0.0 measurement."""

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        n = request.args[0]
        return execution_result(ExecutionStatus.COMPLETED, n * 2 + 1, "inv-wrong")


class OverrideSequenceBackend(ExecutionBackend):
    """Returns the correct doubled value tagged with ``overrides[call_index]``
    (or ``COMPLETED`` once ``overrides`` is exhausted) -- lets a test script
    an exact attempt-by-attempt execution-status sequence, e.g. one or more
    transient infrastructure failures followed by success or exhaustion."""

    def __init__(self, overrides: list[ExecutionStatus]) -> None:
        self._overrides = list(overrides)
        self._lock = threading.Lock()
        self.call_count = 0

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        with self._lock:
            call_index = self.call_count
            self.call_count += 1
        status = (
            self._overrides[call_index]
            if call_index < len(self._overrides)
            else ExecutionStatus.COMPLETED
        )
        n = request.args[0]
        return execution_result(status, n * 2, f"inv-{call_index}")


class RaisingBackend(ExecutionBackend):
    """Always raises -- simulates a genuine backend-setup failure."""

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        raise RuntimeError("simulated backend-setup failure")


@dataclass
class RecordedTraceCall:
    """One captured call to a FakeTraceRecorder.

    ``attempt_records`` is the full per-attempt history handed to this
    call; ``attempts`` (a convenience property, not its own field) is
    simply ``len(attempt_records)``, matching the pre-existing tests that
    only cared about the count.
    """

    work_item_id: str
    task_evaluation_replicate_id: int
    attempt_records: tuple[FreshExecutionAttempt, ...]
    disposition: WorkItemDisposition
    has_result: bool

    @property
    def attempts(self) -> int:
        """Number of attempts this call's ``attempt_records`` carries."""
        return len(self.attempt_records)


@dataclass
class FakeTraceRecorder:
    """In-memory TraceRecorder: records every call, optionally raising to
    simulate a durable-write failure."""

    fail: bool = False
    calls: list[RecordedTraceCall] = field(default_factory=list)

    def record_fresh_attempt(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        work_item: WorkItem,  # pylint: disable=redefined-outer-name
        evidence: ReferenceTaskEvidence,  # pylint: disable=redefined-outer-name
        task_evaluation_replicate_id: int,
        attempt_records: tuple[FreshExecutionAttempt, ...],
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
                attempt_records,
                disposition,
                task_result is not None,
            )
        )


def orchestrator(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    tmp_path: Path,
    *,
    cache_policy: CachePolicy = CachePolicy.CACHE_FIRST,
    trace_recorder: Any = None,
    backend_factory: Callable[[], ExecutionBackend] | None = None,
    evidence_by_task: dict[str, ReferenceTaskEvidence] | None = None,
    max_workers: int = 2,
    max_in_flight: int = 2,
    max_attempts: int = 3,
    cache: ReferenceResultCache | None = None,
) -> tuple[ReferenceOrchestrator, ReferenceResultCache, ReferenceAuditLog]:
    """Build a ReferenceOrchestrator wired to temp cache/audit directories."""
    resolved_cache = cache if cache is not None else ReferenceResultCache(tmp_path / "cache")
    audit_log = ReferenceAuditLog(tmp_path / "audit.jsonl")
    evidence_map = evidence_by_task if evidence_by_task is not None else {TASK_ID: evidence()}
    built = ReferenceOrchestrator(
        cache=resolved_cache,
        audit_log=audit_log,
        evidence_resolver=MappingEvidenceResolver(evidence_map),
        backend_factory=backend_factory if backend_factory is not None else RecordingBackend,
        config=OrchestrationConfig(
            max_workers=max_workers,
            max_in_flight=max_in_flight,
            retry_policy=RetryPolicy(max_attempts=max_attempts),
            profile=FULL_EXECUTION_PROFILE,
            cache_policy=cache_policy,
            trace_recorder=trace_recorder,
        ),
    )
    return built, resolved_cache, audit_log
