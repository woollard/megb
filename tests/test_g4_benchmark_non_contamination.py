"""Structural non-contamination proof for MEGB-03G.4's benchmark-only
synthetic evaluator (MEGB-03G.4 correction, section 3 of the correction
plan in tickets/megb-03.md).

Proves, directly against the already-accepted MEGB-03G.1 aggregation
module and MEGB-03G.2 cache-key module, that a G4 benchmark result:

- cannot be accepted by ``aggregate_reference_results`` (wrong count, and
  independently, profile mismatch);
- cannot be silently mixed with real reference-validation results in the
  same aggregation call (run-context equality already rejects it);
- cannot contribute to ``q_ref``/``Q_ref`` (a direct consequence of the
  previous two);
- cannot collide with a real-corpus cache entry (every discriminating
  cache-key field differs from the real profile's own).

Offline only -- no real Docker, no real privileged corpus, no changes to
any already-accepted module.
"""

# This file intentionally builds its own local fixtures (a fake real-profile
# run_context/manifest/results, mirroring tests/test_reference_aggregation.py's
# own pattern) rather than importing that file's private helpers -- see its
# own note on why cross-coupling test layers is undesirable.
# pylint: disable=duplicate-code

import hashlib

import pytest

from src.evaluators.schema import FailureCategory
from src.reference.aggregation import ReferenceAggregationError, aggregate_reference_results
from src.reference.cache_key import cache_key_for
from src.reference.g4_benchmark_evaluator import (
    G4_COMPARISON_PROFILE_VERSION,
    G4_DATASET_CHECKSUM,
    G4_EVALUATOR_VERSION,
    G4_EXECUTION_PROFILE_ID,
    G4_EXECUTION_PROTOCOL_VERSION,
    G4_ORACLE_VERSION,
    G4_PARTITION_VERSION,
)
from src.reference.oracle import COMPARISON_PROFILE_VERSION, ORACLE_ALGORITHM_VERSION
from src.reference.partition import PARTITION_ALGORITHM_VERSION
from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EXECUTION_PROFILE_ID_FULL,
    EXECUTION_PROTOCOL_VERSION,
)
from src.reference.result_schema import (
    REFERENCE_VALIDATION_CANDIDATE_SET_ALGORITHM_VERSION,
    REFERENCE_VALIDATION_CANDIDATE_SET_MANIFEST_SCHEMA_VERSION,
    REQUIRED_TASK_COUNT,
    CandidateSetEntry,
    MeasurementStatus,
    ReferenceRunContext,
    ReferenceTaskResult,
    ReferenceValidationCandidateSetManifest,
)

_SHA_SELECTION_PROVENANCE = "e" * 64
_SHA_CONFIG = "b" * 64
_HUMANEVAL_PLUS_VERSION = "humaneval-plus-v0.1.10"


def _real_full_run_context(**overrides: str) -> ReferenceRunContext:
    fields = {
        "experiment_run_id": "exp-1",
        "optimization_run_id": "opt-1",
        "optimization_config_sha256": _SHA_CONFIG,
        "portfolio_frozen_at": "2026-07-01T00:00:00Z",
        "portfolio_selection_rule": "best_of_run",
        "evaluator_version": EVALUATOR_VERSION_FULL,
        "dataset_version": _HUMANEVAL_PLUS_VERSION,
        "partition_version": "partition-v1",
        "execution_profile_id": EXECUTION_PROFILE_ID_FULL,
        "comparison_profile_version": COMPARISON_PROFILE_VERSION,
        "execution_protocol_version": EXECUTION_PROTOCOL_VERSION,
        "dataset_checksum": "fe585eb4df8c88d844eeb463ea4d0302",
        "task_manifest_checksum": "d" * 64,
    }
    fields.update(overrides)
    return ReferenceRunContext(**fields)


def _g4_style_run_context(**overrides: str) -> ReferenceRunContext:
    fields = {
        "experiment_run_id": "g4-benchmark",
        "optimization_run_id": "g4-benchmark",
        "optimization_config_sha256": _SHA_CONFIG,
        "portfolio_frozen_at": "2026-07-01T00:00:00Z",
        "portfolio_selection_rule": "g4-benchmark-fixed",
        "evaluator_version": G4_EVALUATOR_VERSION,
        "dataset_version": "g4-doesnt-matter-here-v1",
        "partition_version": G4_PARTITION_VERSION,
        "execution_profile_id": G4_EXECUTION_PROFILE_ID,
        "comparison_profile_version": G4_COMPARISON_PROFILE_VERSION,
        "execution_protocol_version": G4_EXECUTION_PROTOCOL_VERSION,
        "dataset_checksum": G4_DATASET_CHECKSUM,
        "task_manifest_checksum": "d" * 64,
    }
    fields.update(overrides)
    return ReferenceRunContext(**fields)


def _candidate_identity(task_id: str) -> tuple[str, str]:
    candidate_id = f"cand-{task_id}"
    candidate_sha256 = hashlib.sha256(f"candidate-source-for-{task_id}".encode()).hexdigest()
    return candidate_id, candidate_sha256


def _task_result(
    task_id: str, context: ReferenceRunContext, *, oracle_version: str, **overrides: object
) -> ReferenceTaskResult:
    candidate_id, candidate_sha256 = _candidate_identity(task_id)
    fields: dict[str, object] = {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "candidate_sha256": candidate_sha256,
        "context": context,
        "status": MeasurementStatus.VALID,
        "q_ref_task": 1.0,
        "reference_case_total": 1,
        "reference_case_pass_count": 1,
        "first_failure_category": FailureCategory.NONE,
        "oracle_version": oracle_version,
        "reference_case_checksum": hashlib.sha256(f"cases-{task_id}".encode()).hexdigest(),
        "evaluated_at": "2026-07-01T00:00:01Z",
        "duration_seconds": 0.01,
    }
    fields.update(overrides)
    return ReferenceTaskResult(**fields)  # type: ignore[arg-type]


def _manifest_for(
    task_ids: list[str], task_manifest_checksum: str
) -> ReferenceValidationCandidateSetManifest:
    entries = []
    for task_id in task_ids:
        candidate_id, candidate_sha256 = _candidate_identity(task_id)
        entries.append(
            CandidateSetEntry(
                task_id=task_id, candidate_id=candidate_id, candidate_sha256=candidate_sha256
            )
        )
    return ReferenceValidationCandidateSetManifest(
        manifest_schema_version=REFERENCE_VALIDATION_CANDIDATE_SET_MANIFEST_SCHEMA_VERSION,
        algorithm_version=REFERENCE_VALIDATION_CANDIDATE_SET_ALGORITHM_VERSION,
        task_manifest_id="g4-fake-manifest",
        task_manifest_checksum=task_manifest_checksum,
        selection_provenance_sha256=_SHA_SELECTION_PROVENANCE,
        entries=tuple(sorted(entries, key=lambda entry: entry.task_id)),
    )


def _padded_g4_style_results_and_manifest() -> tuple[
    tuple[ReferenceTaskResult, ...], ReferenceValidationCandidateSetManifest
]:
    """164 results carrying G4 benchmark identities (never real ones) --
    proves the *profile* check rejects G4 results independently of the
    count check (which alone would already reject any real G4 batch,
    since those are never 164 items)."""
    task_manifest_checksum = "f" * 64
    context = _g4_style_run_context(task_manifest_checksum=task_manifest_checksum)
    task_ids = [f"G4Fake/{i:03d}" for i in range(REQUIRED_TASK_COUNT)]
    unsorted = (
        _task_result(task_id, context, oracle_version=G4_ORACLE_VERSION) for task_id in task_ids
    )
    results = tuple(sorted(unsorted, key=lambda result: result.task_id))
    manifest = _manifest_for(task_ids, task_manifest_checksum)
    return results, manifest


# --- Cannot be accepted by aggregate_reference_results ------------------------


def test_g4_batch_rejected_by_wrong_count() -> None:
    """A real G4 benchmark batch (never 164 items, and never presented
    with a matching 164-entry manifest, since a benchmark run never
    constructs one) is rejected on count alone. A
    ReferenceValidationCandidateSetManifest itself cannot even be
    constructed with fewer than 164 entries, so this uses a valid
    164-entry manifest paired with a short results sequence -- exactly
    the shape a real G4 caller could produce if it mistakenly tried."""
    all_results, manifest = _padded_g4_style_results_and_manifest()
    short_results = all_results[:1]

    with pytest.raises(ReferenceAggregationError, match="exactly 164"):
        aggregate_reference_results(short_results, manifest)


def test_g4_batch_rejected_by_profile_even_at_164_items() -> None:
    """Even a G4 batch artificially padded to exactly 164 items is
    independently rejected by the full-reference-profile check."""
    results, manifest = _padded_g4_style_results_and_manifest()

    with pytest.raises(ReferenceAggregationError, match="full reference-only"):
        aggregate_reference_results(results, manifest)


# --- Cannot be mixed with real reference-validation results -------------------


def test_g4_result_cannot_be_mixed_into_a_real_aggregation() -> None:
    """One G4-context result among 163 real-context results is rejected by
    the shared-run-context equality check before any profile check runs."""
    real_context = _real_full_run_context()
    g4_context = _g4_style_run_context(task_manifest_checksum=real_context.task_manifest_checksum)
    task_ids = [f"HumanEval/{i}" for i in range(REQUIRED_TASK_COUNT)]

    unsorted_results = [
        _task_result(
            task_id,
            g4_context if index == 5 else real_context,
            oracle_version=ORACLE_ALGORITHM_VERSION,
        )
        for index, task_id in enumerate(task_ids)
    ]
    results = tuple(sorted(unsorted_results, key=lambda result: result.task_id))
    manifest = _manifest_for(task_ids, real_context.task_manifest_checksum)

    with pytest.raises(ReferenceAggregationError, match="different"):
        aggregate_reference_results(results, manifest)


# --- Cannot contribute to q_ref/Q_ref ------------------------------------------


def test_g4_results_can_never_produce_a_benchmark_result_at_all() -> None:
    """Since a G4 result set is always rejected before a ReferenceBenchmarkResult
    is ever constructed, no q_ref/Q_ref value can ever be derived from one."""
    results, manifest = _padded_g4_style_results_and_manifest()
    with pytest.raises(ReferenceAggregationError):
        aggregate_reference_results(results, manifest)
    # No ReferenceBenchmarkResult (and therefore no .q_ref) was ever returned.


# --- Cannot collide with a real-corpus cache entry ----------------------------


def test_g4_cache_key_differs_from_real_profile_in_every_discriminating_field() -> None:
    """Every version/checksum field ReferenceResultCacheKey binds on differs
    between a G4 result and what a real full-profile result would carry --
    proved by direct field inequality, not probabilistic digest non-collision."""
    g4_context = _g4_style_run_context()
    g4_result = _task_result("G4Bench/MEDIAN/0", g4_context, oracle_version=G4_ORACLE_VERSION)
    g4_key = cache_key_for(g4_result)

    assert g4_key.partition_version != PARTITION_ALGORITHM_VERSION
    assert g4_key.oracle_version != ORACLE_ALGORITHM_VERSION
    assert g4_key.comparison_profile_version != COMPARISON_PROFILE_VERSION
    assert g4_key.evaluator_version != EVALUATOR_VERSION_FULL
    assert g4_key.execution_profile_id != EXECUTION_PROFILE_ID_FULL
    assert g4_key.execution_protocol_version != EXECUTION_PROTOCOL_VERSION


def test_g4_benchmark_never_uses_the_production_cache_directory() -> None:
    """The primary, structural collision guarantee: a dedicated cache
    directory, never artifacts/privileged/reference/cache/."""
    from src.reference.g4_benchmark import (  # pylint: disable=import-outside-toplevel
        DEFAULT_BENCHMARK_CACHE_DIR,
    )
    from src.reference.reference_cache import (  # pylint: disable=import-outside-toplevel
        DEFAULT_CACHE_DIR,
    )

    assert DEFAULT_BENCHMARK_CACHE_DIR != DEFAULT_CACHE_DIR
    assert "g4_benchmark" in str(DEFAULT_BENCHMARK_CACHE_DIR)


# --- Manifest independence remains unchanged ----------------------------------


def test_g4_benchmark_evaluator_module_has_no_manifest_coupling() -> None:
    """The new evaluator module never imports any manifest type."""
    from pathlib import Path  # pylint: disable=import-outside-toplevel

    import src.reference.g4_benchmark_evaluator as module  # pylint: disable=import-outside-toplevel

    source = Path(module.__file__).read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    joined_imports = "\n".join(import_lines)
    assert "ReferenceValidationCandidateSetManifest" not in joined_imports
    assert "primary_experiment_task_manifest" not in joined_imports
    assert "aggregate_reference_results" not in joined_imports
