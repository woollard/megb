"""Real-Docker ordering and concurrent-isolation validation for MEGB-03G.4
(correction, sections 4-5 of the "Approved MEGB-03G.4 Correction" in
tickets/megb-03.md).

Requires a running Docker daemon and the ``megb-runner:local`` image.
These are bounded correctness checks (not MEGB-03G.4's own expensive
throughput benchmark), so -- like the rest of the adversarial sandbox
suite -- they join the existing Docker-marked test suite
(``pytest -m docker``) rather than the benchmark's own "not on every push"
manual/scheduled path. Uses only synthetic, non-privileged evidence
against the real MEGB-02 execution boundary through the real,
already-accepted MEGB-03G.3 orchestrator.
"""

# This file intentionally builds its own local orchestrator-construction
# helper and leftover-container check (mirroring
# tests/test_execution_sandbox.py's own _list_megb_runner_containers and
# src.reference.g4_benchmark's _make_orchestrator) rather than importing
# either -- see tests/test_reference_cache_key.py's note on why test files
# keep their own local fixtures independent of each other.
# pylint: disable=duplicate-code

import hashlib
import subprocess
import threading
from pathlib import Path
from typing import Callable

import pytest

from src.execution.backend import ExecutionBackend
from src.execution.docker_backend import DockerPerInvocationBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionLimits,
)
from src.execution.wire import encode_value
from src.reference.g4_benchmark_evaluator import (
    G4_COMPARISON_PROFILE_VERSION,
    G4_DATASET_CHECKSUM,
    G4_DATASET_VERSION,
    G4_EVALUATOR_VERSION,
    G4_EXECUTION_PROFILE_ID,
    G4_EXECUTION_PROTOCOL_VERSION,
    G4_ORACLE_VERSION,
    G4_PARTITION_VERSION,
    G4_TASK_MANIFEST_CHECKSUM,
    evaluate_g4_benchmark_candidate,
)
from src.reference.oracle import ComparisonProfile, OracleRecord
from src.reference.reference_audit import ReferenceAuditLog
from src.reference.reference_cache import ReferenceResultCache
from src.reference.reference_evaluator import ExecutionProfile, ReferenceCase, ReferenceTaskEvidence
from src.reference.reference_orchestrator import (
    MappingEvidenceResolver,
    OrchestrationConfig,
    OrchestrationRunSummary,
    ReferenceOrchestrator,
    RetryPolicy,
    WorkItem,
    WorkItemDisposition,
)
from src.reference.result_schema import ReferenceRunContext

pytestmark = pytest.mark.docker

_PROFILE = ExecutionProfile(
    profile_id=G4_EXECUTION_PROFILE_ID,
    evaluator_version=G4_EVALUATOR_VERSION,
    limits=ExecutionLimits(wall_time_sec=5.0),
)
_COMPARISON_PROFILE = ComparisonProfile(
    kind="default_exact_or_tolerance", atol=0.0, profile_version=G4_COMPARISON_PROFILE_VERSION
)


def _run_context() -> ReferenceRunContext:
    return ReferenceRunContext(
        experiment_run_id="g4-ordering-isolation",
        optimization_run_id="g4-ordering-isolation",
        optimization_config_sha256="0" * 64,
        portfolio_frozen_at="2026-01-01T00:00:00Z",
        portfolio_selection_rule="g4-ordering-isolation-fixed",
        evaluator_version=G4_EVALUATOR_VERSION,
        dataset_version=G4_DATASET_VERSION,
        partition_version=G4_PARTITION_VERSION,
        execution_profile_id=G4_EXECUTION_PROFILE_ID,
        comparison_profile_version=G4_COMPARISON_PROFILE_VERSION,
        execution_protocol_version=G4_EXECUTION_PROTOCOL_VERSION,
        dataset_checksum=G4_DATASET_CHECKSUM,
        task_manifest_checksum=G4_TASK_MANIFEST_CHECKSUM,
    )


def _evidence(
    task_id: str, entry_point: str, args: tuple[object, ...], expected_output: object
) -> ReferenceTaskEvidence:
    record = OracleRecord(
        task_id=task_id,
        case_id="c0",
        pool="megb-03g4-synthetic",
        provenance="megb-03g4-synthetic",
        comparison_profile_kind="default_exact_or_tolerance",
        status="success",
        expected_output=encode_value(expected_output),
        failure_reason=None,
    )
    case = ReferenceCase(case_id="c0", args=args, oracle_record=record)
    return ReferenceTaskEvidence(
        task_id=task_id,
        entry_point=entry_point,
        comparison_profile=_COMPARISON_PROFILE,
        cases=(case,),
        oracle_version=G4_ORACLE_VERSION,
        partition_version=G4_PARTITION_VERSION,
        dataset_version=G4_DATASET_VERSION,
        protocol_version=G4_EXECUTION_PROTOCOL_VERSION,
        dataset_checksum=G4_DATASET_CHECKSUM,
        task_manifest_checksum=G4_TASK_MANIFEST_CHECKSUM,
    )


def _work_item(
    work_item_id: str,
    ordinal: int,
    task_id: str,
    candidate_code: str,
    run_context: ReferenceRunContext,
) -> WorkItem:
    return WorkItem(
        work_item_id=work_item_id,
        input_ordinal=ordinal,
        task_id=task_id,
        candidate_id=f"cand-{work_item_id}",
        candidate_sha256=hashlib.sha256(candidate_code.encode("utf-8")).hexdigest(),
        candidate_code=candidate_code,
        run_context=run_context,
    )


def _orchestrator(
    cache_dir: Path,
    audit_path: Path,
    evidence_map: dict[str, ReferenceTaskEvidence],
    backend_factory: Callable[[], ExecutionBackend],
    max_workers: int,
) -> ReferenceOrchestrator:
    cache = ReferenceResultCache(cache_dir)
    audit_log = ReferenceAuditLog(audit_path)
    return ReferenceOrchestrator(
        cache=cache,
        audit_log=audit_log,
        evidence_resolver=MappingEvidenceResolver(evidence_map),
        backend_factory=backend_factory,
        config=OrchestrationConfig(
            max_workers=max_workers,
            max_in_flight=max_workers,
            retry_policy=RetryPolicy(max_attempts=1),
            profile=_PROFILE,
            evaluator=evaluate_g4_benchmark_candidate,
        ),
    )


def _leftover_containers() -> list[str]:
    proc = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=megb-runner-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return [name for name in proc.stdout.splitlines() if name]


# --- Deterministic ordering under real Docker, deliberately reversed completion ---

_ORDER_ENTRY_POINT = "g4_order_test"
_ORDER_CANDIDATE = (
    "def g4_order_test(sleep_seconds):\n"
    "    import time\n"
    "    time.sleep(sleep_seconds)\n"
    "    return sleep_seconds\n"
)
_ORDER_SLEEPS = (1.2, 0.8, 0.4, 0.1)  # ordinal 0 sleeps longest, ordinal 3 shortest


class _CompletionOrderRecordingBackend(ExecutionBackend):
    """Wraps a real DockerPerInvocationBackend, recording the order in
    which invocations actually complete (identified by their own
    sleep_seconds argument, which is unique per work item here)."""

    def __init__(self, completion_order: list[float], lock: threading.Lock) -> None:
        self._real = DockerPerInvocationBackend()
        self._completion_order = completion_order
        self._lock = lock

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        result = self._real.execute(request)
        with self._lock:
            self._completion_order.append(request.args[0])
        return result


def _order_evidence_map() -> dict[str, ReferenceTaskEvidence]:
    return {
        f"G4Order/{ordinal}": _evidence(
            f"G4Order/{ordinal}", _ORDER_ENTRY_POINT, (sleep_seconds,), sleep_seconds
        )
        for ordinal, sleep_seconds in enumerate(_ORDER_SLEEPS)
    }


def _order_items(run_context: ReferenceRunContext) -> tuple[WorkItem, ...]:
    return tuple(
        _work_item(f"wi-{ordinal}", ordinal, f"G4Order/{ordinal}", _ORDER_CANDIDATE, run_context)
        for ordinal in range(len(_ORDER_SLEEPS))
    )


def test_real_docker_deterministic_ordering_under_reversed_completion(tmp_path: Path) -> None:
    """Real completion order is reversed relative to input order at
    concurrency=4, but returned outcomes still exactly match input_ordinal,
    with every result correctly associated with its own task/candidate."""
    run_context = _run_context()
    evidence_map = _order_evidence_map()
    items = _order_items(run_context)

    completion_order: list[float] = []
    lock = threading.Lock()
    orchestrator = _orchestrator(
        tmp_path / "cache",
        tmp_path / "audit.jsonl",
        evidence_map,
        lambda: _CompletionOrderRecordingBackend(completion_order, lock),
        max_workers=4,
    )

    summary = orchestrator.run(items, run_id="g4-order-1")

    assert summary.accepted_work_items == len(_ORDER_SLEEPS)
    assert completion_order != list(_ORDER_SLEEPS), "completion order must differ from input order"
    assert completion_order[0] == min(_ORDER_SLEEPS), "the shortest-sleep item must finish first"

    ordinals = [outcome.input_ordinal for outcome in summary.outcomes]
    assert ordinals == list(range(len(_ORDER_SLEEPS)))
    assert [outcome.work_item_id for outcome in summary.outcomes] == [
        f"wi-{i}" for i in range(len(_ORDER_SLEEPS))
    ]
    for ordinal, outcome in enumerate(summary.outcomes):
        assert outcome.task_id == f"G4Order/{ordinal}"
        assert outcome.task_result is not None
        assert outcome.task_result.q_ref_task == 1.0


def test_real_docker_ordering_is_reproducible_on_a_second_independent_run(tmp_path: Path) -> None:
    """A second, independent run (fresh cache) over the same items
    reproduces identical ordering and task/candidate associations, with no
    duplicate or missing accepted results."""
    run_context = _run_context()
    evidence_map = _order_evidence_map()
    items = _order_items(run_context)

    first = _orchestrator(
        tmp_path / "run1-cache", tmp_path / "run1-audit.jsonl", evidence_map,
        DockerPerInvocationBackend, max_workers=4,
    )
    first_summary = first.run(items, run_id="g4-order-repro-1")

    second = _orchestrator(
        tmp_path / "run2-cache", tmp_path / "run2-audit.jsonl", evidence_map,
        DockerPerInvocationBackend, max_workers=4,
    )
    second_summary = second.run(items, run_id="g4-order-repro-2")

    def _associations(summary: OrchestrationRunSummary) -> list[tuple[str, int, str]]:
        return [(o.work_item_id, o.input_ordinal, o.task_id) for o in summary.outcomes]

    assert _associations(first_summary) == _associations(second_summary)
    assert first_summary.accepted_work_items == len(items)
    assert second_summary.accepted_work_items == len(items)


# --- Concurrent isolation: writer/reader canary --------------------------------

_WRITER_ENTRY_POINT = "g4_isolation_writer"
_READER_ENTRY_POINT = "g4_isolation_reader"
_CANARY_PATH = "/tmp/g4_isolation_canary.txt"
_WRITER_CANDIDATE = (
    f"def {_WRITER_ENTRY_POINT}(secret):\n"
    f"    with open({_CANARY_PATH!r}, 'w', encoding='utf-8') as fh:\n"
    "        fh.write(secret)\n"
    "    import time\n"
    "    time.sleep(0.4)\n"
    "    return 'written:' + secret\n"
)
_READER_CANDIDATE = (
    f"def {_READER_ENTRY_POINT}(_marker):\n"
    "    try:\n"
    f"        with open({_CANARY_PATH!r}, encoding='utf-8') as fh:\n"
    "            return fh.read()\n"
    "    except OSError:\n"
    "        return 'NOT_FOUND'\n"
)
_ISOLATION_SECRETS = ("secret-alpha", "secret-beta", "secret-gamma")


def test_real_docker_concurrent_isolation_writer_reader_canary(tmp_path: Path) -> None:
    """Multiple writer/reader pairs run concurrently, each writer using the
    same in-container filename with a distinct secret. Every reader must
    see NOT_FOUND -- proving no writable-state sharing between
    concurrently-running (or any other) containers, including within the
    same pair -- and every writer's own result must reflect its own
    secret, with no cross-item result attribution."""
    run_context = _run_context()
    evidence_map: dict[str, ReferenceTaskEvidence] = {}
    items = []
    ordinal = 0
    for index, secret in enumerate(_ISOLATION_SECRETS):
        writer_task = f"G4IsolationWriter/{index}"
        evidence_map[writer_task] = _evidence(
            writer_task, _WRITER_ENTRY_POINT, (secret,), f"written:{secret}"
        )
        writer_item = _work_item(
            f"writer-{index}", ordinal, writer_task, _WRITER_CANDIDATE, run_context
        )
        items.append(writer_item)
        ordinal += 1

        reader_task = f"G4IsolationReader/{index}"
        evidence_map[reader_task] = _evidence(reader_task, _READER_ENTRY_POINT, (0,), "NOT_FOUND")
        reader_item = _work_item(
            f"reader-{index}", ordinal, reader_task, _READER_CANDIDATE, run_context
        )
        items.append(reader_item)
        ordinal += 1

    orchestrator = _orchestrator(
        tmp_path / "cache", tmp_path / "audit.jsonl", evidence_map,
        DockerPerInvocationBackend, max_workers=4,
    )
    summary = orchestrator.run(items, run_id="g4-isolation-1")

    assert summary.accepted_work_items == len(items)
    for outcome in summary.outcomes:
        assert outcome.disposition == WorkItemDisposition.EXECUTED_VALID
        assert outcome.task_result is not None
        assert outcome.task_result.q_ref_task == 1.0, (
            f"{outcome.work_item_id} ({outcome.task_id}) did not match its own expected "
            "output -- either a writer failed, or a reader observed another container's state"
        )
        if outcome.work_item_id.startswith("writer-"):
            assert outcome.task_id.startswith("G4IsolationWriter/")
        else:
            assert outcome.task_id.startswith("G4IsolationReader/")


# --- Cleanup --------------------------------------------------------------------


def test_no_leftover_containers_after_ordering_and_isolation_tests() -> None:
    """No megb-runner-* containers remain after every test above, including
    on any earlier failure path."""
    leftover = _leftover_containers()
    assert not leftover, f"leftover megb-runner-* containers found: {leftover}"
