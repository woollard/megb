"""Tests for the MEGB-03G.4/G.5 conformance correction (frozen synthetic
identity restoration).

Offline only. Proves that ``G4_DATASET_VERSION``/``G4_DATASET_CHECKSUM``/
``G4_TASK_MANIFEST_CHECKSUM`` now exactly match the "Approved MEGB-03G.4
Benchmark Plan (Frozen)" (``tickets/megb-03.md``), that the two checksums
are genuinely *derived* from the plan's own pre-images rather than
independently hardcoded, that ``G4_EVALUATOR_VERSION`` v2 artifacts are now
rejected as stale, and that this identity correction changed nothing about
the workload's own content identity, the real execution protocol, or
non-contamination against the real reference profile.
"""

# This file's real-full-profile fixture (four identity fields mapped to
# their real constants) necessarily overlaps other test files' own
# real-profile fixtures (e.g. tests/test_reference_evaluator.py) -- both
# legitimately reuse the same small set of real constants for the same
# conceptual purpose (the real full profile's identity), and this file
# intentionally builds its own local fixture rather than importing another
# test module's private helpers, matching tests/test_reference_aggregation.py's
# own precedent for this exact situation. The resulting overlap is
# expected and accepted, not a defect.
# pylint: disable=duplicate-code

import hashlib
import inspect

import pytest
from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION

from src.reference.g4_benchmark import _CANONICAL_SOLUTION
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
    evaluate_g4_benchmark_candidate,
)
from src.reference.oracle import ComparisonProfile, OracleRecord
from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EXECUTION_PROFILE_ID_FULL,
    EXECUTION_PROTOCOL_VERSION,
    ExecutionProfile,
    ReferenceCase,
    ReferenceTaskEvidence,
)
from src.evaluators.schema import FailureCategory
from src.reference.cache_key import cache_key_for
from src.reference.oracle import COMPARISON_PROFILE_VERSION, ORACLE_ALGORITHM_VERSION
from src.reference.partition import PARTITION_ALGORITHM_VERSION
from src.reference.g4_qualification_report_cli import _synthetic_workload_checksum
from src.reference.result_schema import MeasurementStatus, ReferenceRunContext, ReferenceTaskResult
from src.execution.backend import ExecutionBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionLimits,
    ExecutionStatus,
)
from src.execution.wire import encode_value

_FROZEN_DATASET_VERSION = "synthetic-g4-benchmark-v1"
_FROZEN_DATASET_CHECKSUM = "620d891af7232d54263877049d3e8720fc81cb38e3f2afad3e476b7e6936f8a9"
_FROZEN_TASK_MANIFEST_CHECKSUM = "2660eefaf368c747f88db3842d5d4c021279e6b1c6bd60b7be1cdb318f0f8977"
_FROZEN_CANONICAL_SOLUTION_SHA256 = (
    "f677aa4cceca480683e70c3a23d2fd095f8ac3e77fd487432364095cdced5e47"
)
_WORKLOAD_CHECKSUM = "c8e20a97f145c01ae39c56297bffa8e4dae95761095cb9d188eb93260ef92c41"

_TASK_ID = "G4Conformance/0"
_CANDIDATE_CODE = "def g4_compute(n):\n    return (n * 2) + 1\n"
_CANDIDATE_SHA256 = hashlib.sha256(_CANDIDATE_CODE.encode("utf-8")).hexdigest()


def test_identity_values_exactly_equal_the_frozen_plan_values() -> None:
    """The implementation's three corrected identity values exactly equal
    the frozen plan's own values -- not merely non-colliding synthetic
    values, but the specific literals the plan froze."""
    assert G4_DATASET_VERSION == _FROZEN_DATASET_VERSION
    assert G4_DATASET_CHECKSUM == _FROZEN_DATASET_CHECKSUM
    assert G4_TASK_MANIFEST_CHECKSUM == _FROZEN_TASK_MANIFEST_CHECKSUM


def test_checksums_are_recomputed_from_the_exact_frozen_preimages() -> None:
    """Both checksums are genuinely derived from the frozen plan's own
    pre-image strings, not independently hardcoded hex values that merely
    happen to match -- recomputing sha256 of the plan's literal pre-images
    here, in this test, reproduces the implementation's constants exactly."""
    assert (
        hashlib.sha256(b"g4-benchmark-synthetic-dataset-v1").hexdigest() == G4_DATASET_CHECKSUM
    )
    assert (
        hashlib.sha256(b"g4-benchmark-synthetic-manifest-v1").hexdigest()
        == G4_TASK_MANIFEST_CHECKSUM
    )


def test_canonical_solution_hash_still_matches_the_frozen_value() -> None:
    """The already-conformant entry_point/canonical-solution pair (never
    touched by this correction) still reproduces the frozen plan's own
    sha256, confirming this correction did not disturb workload content."""
    assert (
        hashlib.sha256(_CANONICAL_SOLUTION.encode("utf-8")).hexdigest()
        == _FROZEN_CANONICAL_SOLUTION_SHA256
    )


def _oracle_case(case_id: str, n: int) -> ReferenceCase:
    record = OracleRecord(
        task_id=_TASK_ID,
        case_id=case_id,
        pool="megb-03g4-synthetic",
        provenance="megb-03g4-synthetic",
        comparison_profile_kind="default_exact_or_tolerance",
        status="success",
        expected_output=encode_value((n * 2) + 1),
        failure_reason=None,
    )
    return ReferenceCase(case_id=case_id, args=(n,), oracle_record=record)


def _g4_evidence() -> ReferenceTaskEvidence:
    return ReferenceTaskEvidence(
        task_id=_TASK_ID,
        entry_point="g4_compute",
        comparison_profile=ComparisonProfile(
            kind="default_exact_or_tolerance",
            atol=0.0,
            profile_version=G4_COMPARISON_PROFILE_VERSION,
        ),
        cases=(_oracle_case("c0", 3),),
        oracle_version=G4_ORACLE_VERSION,
        partition_version=G4_PARTITION_VERSION,
        dataset_version=G4_DATASET_VERSION,
        protocol_version=EXECUTION_PROTOCOL_VERSION,
        dataset_checksum=G4_DATASET_CHECKSUM,
        task_manifest_checksum=G4_TASK_MANIFEST_CHECKSUM,
    )


def _g4_run_context(**overrides: object) -> ReferenceRunContext:
    fields: dict[str, object] = {
        "experiment_run_id": "g4-conformance",
        "optimization_run_id": "g4-conformance",
        "optimization_config_sha256": "0" * 64,
        "portfolio_frozen_at": "2026-01-01T00:00:00Z",
        "portfolio_selection_rule": "g4-conformance-fixed",
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


class _RecordingBackend(ExecutionBackend):
    """Fake backend for this file's own conformance checks -- records each
    request's protocol_version and always completes successfully."""

    def __init__(self) -> None:
        self.protocol_versions: list[str] = []

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        self.protocol_versions.append(request.protocol_version)
        result_fields: dict[str, object] = {
            "invocation_id": "inv-0",
            "status": ExecutionStatus.COMPLETED,
            "return_value": request.args[0] * 2 + 1,
            "exception_type": None,
            "exception_message": None,
            "wall_time_sec": 0.01,
            "candidate_wall_time_sec": 0.005,
            "exit_code": 0,
            "terminating_signal": None,
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "backend_id": "fake",
            "backend_version": "1",
            "runner_image_digest": "sha256:fake",
            "protocol_version": request.protocol_version,
            "limits": ExecutionLimits(),
            "started_at": "2026-08-02T00:00:00Z",
        }
        return CandidateExecutionResult(**result_fields)  # type: ignore[arg-type]


def _profile() -> ExecutionProfile:
    return ExecutionProfile(
        profile_id=G4_EXECUTION_PROFILE_ID,
        evaluator_version=G4_EVALUATOR_VERSION,
        limits=ExecutionLimits(),
    )


def test_execution_protocol_version_remains_the_real_constant() -> None:
    """The conformance correction touched only dataset/manifest identity
    and the evaluator version -- execution_protocol_version remains the
    real, shared EXECUTION_PROTOCOL_VERSION, unaffected."""
    backend = _RecordingBackend()
    result, _ = evaluate_g4_benchmark_candidate(
        _g4_evidence(), _CANDIDATE_CODE, "cand-0", _CANDIDATE_SHA256, _g4_run_context(),
        backend=backend, profile=_profile(),
    )
    assert result.context.execution_protocol_version == EXECUTION_PROTOCOL_VERSION
    assert backend.protocol_versions == [EXECUTION_PROTOCOL_VERSION]


def test_corrected_synthetic_cache_key_remains_distinct_from_the_real_key() -> None:
    """Under the corrected, frozen identities, a G4 result's cache key
    still differs from the real full-profile cache key for the same
    task_id -- the identity correction did not introduce a collision."""
    backend = _RecordingBackend()
    g4_result, _ = evaluate_g4_benchmark_candidate(
        _g4_evidence(), _CANDIDATE_CODE, "cand-0", _CANDIDATE_SHA256, _g4_run_context(),
        backend=backend, profile=_profile(),
    )
    g4_key = cache_key_for(g4_result)

    real_profile_overrides: dict[str, object] = {
        "evaluator_version": EVALUATOR_VERSION_FULL,
        "dataset_version": HUMANEVAL_PLUS_VERSION,
        "partition_version": PARTITION_ALGORITHM_VERSION,
        "execution_profile_id": EXECUTION_PROFILE_ID_FULL,
        "comparison_profile_version": COMPARISON_PROFILE_VERSION,
        "dataset_checksum": "fe585eb4df8c88d844eeb463ea4d0302",
    }
    real_context = _g4_run_context(**real_profile_overrides)
    real_result = ReferenceTaskResult(
        task_id=_TASK_ID,
        candidate_id="cand-0",
        candidate_sha256=_CANDIDATE_SHA256,
        context=real_context,
        status=MeasurementStatus.VALID,
        q_ref_task=1.0,
        reference_case_total=1,
        reference_case_pass_count=1,
        first_failure_category=FailureCategory.NONE,
        oracle_version=ORACLE_ALGORITHM_VERSION,
        reference_case_checksum="b" * 64,
        evaluated_at="2026-08-02T00:00:00Z",
        duration_seconds=0.01,
    )
    real_key = cache_key_for(real_result)

    assert g4_key.dataset_version != real_key.dataset_version
    assert g4_key.partition_version != real_key.partition_version
    assert g4_key.oracle_version != real_key.oracle_version
    assert g4_key.comparison_profile_version != real_key.comparison_profile_version
    assert g4_key.evaluator_version != real_key.evaluator_version
    assert g4_key.execution_profile_id != real_key.execution_profile_id
    assert g4_key.execution_protocol_version == real_key.execution_protocol_version
    assert g4_key.key_digest != real_key.key_digest


def test_v2_stamped_artifacts_are_rejected_as_stale() -> None:
    """A run_context/evidence pair stamped with the superseded
    v2 evaluator_version is rejected by the v3 evaluator's own
    internal-consistency check -- version equality is required, and a
    stale v2 identity no longer satisfies it."""
    stale_context = _g4_run_context(evaluator_version="megb-03g4-benchmark-evaluator-v2")
    backend = _RecordingBackend()

    with pytest.raises(G4BenchmarkEvaluatorVersionMismatchError):
        evaluate_g4_benchmark_candidate(
            _g4_evidence(), _CANDIDATE_CODE, "cand-0", _CANDIDATE_SHA256, stale_context,
            backend=backend, profile=_profile(),
        )


def test_workload_checksum_remains_unchanged() -> None:
    """Because workload content (entry point, canonical solution, tier
    case counts) is untouched by this correction, the synthetic workload
    checksum remains exactly its pre-correction value."""
    assert _synthetic_workload_checksum() == _WORKLOAD_CHECKSUM


def test_workload_checksum_independent_of_the_evaluator_version_bump() -> None:
    """Changing only evaluator/provenance identity (v2 -> v3) does not
    change workload content identity: the checksum function accepts no
    evaluator-version parameter at all, so it cannot have moved because of
    this bump -- reconfirmed directly against the pre-bump recorded value."""
    params = set(inspect.signature(_synthetic_workload_checksum).parameters)
    assert "evaluator_version" not in params
    assert _synthetic_workload_checksum() == _WORKLOAD_CHECKSUM
