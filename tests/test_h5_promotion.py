"""Tests for MEGB-03H.2B.2's production-cache preflight, incremental
promotion, and safe promotion summary (src.reference.h5_promotion).
Synthetic 164-task fixtures only, via tests/_h5_fixtures.py -- no real
privileged corpus access, no Docker.

Required coverage for this checkpoint: full 164/164 staging-gate-preflight-
promotion; production conflict/corrupt/stale/storage-failure discovered
during preflight leaves the cache unchanged; identical existing entries are
accepted without being relabeled as fresh execution or a cache hit;
interruption before the gate completes and after exactly k promotions each
leave only the expected subset; resumption promotes only the remainder;
repeated finalization is idempotent; the safe summary never leaks free-text
reasons/details or privileged paths; trace-before-stage ordering still holds
when the staging cache is plugged into the real H.2B.1 orchestrator; and no
real privileged directory is ever touched.
"""

# See _h5_fixtures.py's own note: shared fixtures across the H.2B.2 test
# modules, and this module also reuses the H.2B.1 orchestrator fixtures
# module for the trace-before-stage-ordering test.
# pylint: disable=duplicate-code

import dataclasses
from pathlib import Path
from typing import Mapping

import pytest

from src.evaluators.schema import FailureCategory
from src.reference.cache_key import cache_key_for
from src.reference.h5_promotion import (
    PromotionPreconditionError,
    PromotionSummary,
    build_promotion_summary,
    promote,
    run_preflight,
)
from src.reference.h5_promotion_manifest import (
    EntryPromotionState,
    GateOutcome,
    H5PromotionManifest,
    PreflightClassification,
    PromotionState,
    advance_manifest,
    build_initial_manifest,
    build_staged_entries,
    load_promotion_manifest,
)
from src.reference.h5_staging import (
    DEFAULT_H5_STAGING_ROOT,
    H5StagingIdentity,
    build_staging_cache,
    evaluate_complete_run_gate,
)
from src.reference.orchestration_trace import CachePolicy
from src.reference.reference_cache import CacheDisposition, CacheWriteResult, ReferenceResultCache
from src.reference.reference_orchestrator import WorkItemDisposition
from src.reference.result_schema import (
    REQUIRED_TASK_COUNT,
    ReferenceTaskResult,
    ReferenceValidationCandidateSetManifest,
)
from tests import _h5_fixtures as fx
from tests import _reference_orchestrator_cache_policy_fixtures as orch_fx


_StagedRun = tuple[
    H5StagingIdentity,
    ReferenceValidationCandidateSetManifest,
    tuple[ReferenceTaskResult, ...],
    ReferenceResultCache,
]


def _stage_and_gate(tmp_path: Path) -> _StagedRun:
    """Stage a full, valid 164-task run and pass the complete-run gate."""
    results = fx.valid_task_results(fx.full_run_context())
    manifest = fx.candidate_set_manifest()
    identity = fx.staging_identity(manifest)
    staging_cache = build_staging_cache(identity, root=tmp_path)
    for result in results:
        assert staging_cache.put(result).disposition == CacheDisposition.WRITE_ACCEPTED
    invocations, task_evaluations = fx.full_trace_for_results(
        fx.calibration_context(), results
    )
    gate_result = evaluate_complete_run_gate(
        identity=identity,
        candidate_set_manifest=manifest,
        task_results=results,
        staging_cache=staging_cache,
        invocations=invocations,
        task_evaluations=task_evaluations,
    )
    assert gate_result.passed is True
    return identity, manifest, results, staging_cache


def _staged_results_and_gated_manifest(
    tmp_path: Path,
) -> tuple[H5PromotionManifest, Mapping[str, ReferenceTaskResult], Path]:
    """Build a real, gate-approved 164-task run: stage every result into a
    staging cache, pass the complete-run gate, and advance a fresh
    promotion manifest to ``GATE_PASSED``."""
    identity, _manifest, results, _staging_cache = _stage_and_gate(tmp_path)
    results_by_task_id = {result.task_id: result for result in results}
    expected_task_ids = tuple(sorted(results_by_task_id))
    promotion_manifest = advance_manifest(
        build_initial_manifest(identity, expected_task_ids),
        state=PromotionState.GATE_PASSED,
        gate_outcome=GateOutcome(True, "complete-run gate passed"),
        staged_entries=build_staged_entries(results),
    )
    return promotion_manifest, results_by_task_id, tmp_path / "promotion_manifest.json"


class _CountingCache(ReferenceResultCache):
    """A real ``ReferenceResultCache`` that counts ``put`` calls -- used to
    assert exactly how many (and which) production writes actually
    happened."""

    def __init__(self, cache_dir: Path) -> None:
        super().__init__(cache_dir)
        self.put_calls: list[str] = []

    def put(self, task_result: ReferenceTaskResult) -> CacheWriteResult:
        self.put_calls.append(task_result.task_id)
        return super().put(task_result)


class _InterruptingCache(ReferenceResultCache):
    """A real ``ReferenceResultCache`` whose ``put`` raises once a fixed
    number of successful writes have already happened -- simulates an
    interruption partway through promotion."""

    def __init__(self, cache_dir: Path, interrupt_after: int) -> None:
        super().__init__(cache_dir)
        self._interrupt_after = interrupt_after
        self._count = 0

    def put(self, task_result: ReferenceTaskResult) -> CacheWriteResult:
        if self._count == self._interrupt_after:
            raise RuntimeError("simulated interruption")
        self._count += 1
        return super().put(task_result)


class _RefusingCache(ReferenceResultCache):
    """A real ``ReferenceResultCache`` whose ``put`` always fails the test
    if ever called -- used to prove a no-op path never touches production."""

    def put(self, task_result: ReferenceTaskResult) -> CacheWriteResult:
        raise AssertionError(f"put() must never be called, but was for {task_result.task_id!r}")


# ---------------------------------------------------------------------------
# Full successful 164/164 staging -> gate -> preflight -> promotion -> summary
# ---------------------------------------------------------------------------


def test_full_164_run_stages_gates_preflights_and_promotes(tmp_path: Path) -> None:
    """A gate-approved 164/164 run preflights all-ABSENT and promotes every
    entry into an empty production cache, reaching COMPLETED."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_cache = ReferenceResultCache(tmp_path / "production")

    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.PREFLIGHT_PASSED
    assert manifest.preflight_outcome is not None
    assert manifest.preflight_outcome.passed is True
    assert all(
        entry.classification == PreflightClassification.ABSENT
        for entry in manifest.preflight_outcome.entries
    )

    manifest = promote(manifest, production_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.COMPLETED
    assert all(
        state == EntryPromotionState.PROMOTED for state in manifest.entry_states.values()
    )
    assert len(manifest.entry_states) == REQUIRED_TASK_COUNT

    for result in results_by_task_id.values():
        lookup = production_cache.get(cache_key_for(result))
        assert lookup.disposition == CacheDisposition.VALID_HIT
        assert lookup.task_result == result

    reloaded = load_promotion_manifest(manifest_path)
    assert reloaded == manifest

    summary = build_promotion_summary(manifest, generated_at="2026-08-03T00:00:00Z")
    assert summary.state == "COMPLETED"
    assert summary.expected_task_count == REQUIRED_TASK_COUNT
    assert summary.entry_state_counts == {"PROMOTED": REQUIRED_TASK_COUNT}


# ---------------------------------------------------------------------------
# Identical existing entries: ALREADY_SATISFIED, never relabeled
# ---------------------------------------------------------------------------


def test_identical_existing_entries_are_accepted_without_relabeling(tmp_path: Path) -> None:
    """Entries already identically present in production are classified
    ALREADY_SATISFIED at preflight and stay that way through promotion --
    never relabeled as PROMOTED (as if freshly written)."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_cache = ReferenceResultCache(tmp_path / "production")
    for result in results_by_task_id.values():
        write = production_cache.put(result)
        assert write.disposition == CacheDisposition.WRITE_ACCEPTED

    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.PREFLIGHT_PASSED
    assert all(
        entry.classification == PreflightClassification.IDENTICAL_VALID
        for entry in manifest.preflight_outcome.entries  # type: ignore[union-attr]
    )
    assert all(
        state == EntryPromotionState.ALREADY_SATISFIED
        for state in manifest.entry_states.values()
    )

    refusing_cache = _RefusingCache(production_cache.cache_dir)
    manifest = promote(manifest, refusing_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.COMPLETED
    # Never relabeled as PROMOTED (i.e. as if freshly written) -- still ALREADY_SATISFIED.
    assert all(
        state == EntryPromotionState.ALREADY_SATISFIED
        for state in manifest.entry_states.values()
    )


# ---------------------------------------------------------------------------
# Production conflict / corrupt / stale / storage failure during preflight
# ---------------------------------------------------------------------------


def test_production_conflict_discovered_during_preflight_leaves_cache_unchanged(
    tmp_path: Path,
) -> None:
    """A different valid production entry under the same cache key blocks
    promotion at preflight and is never overwritten or removed."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_dir = tmp_path / "production"
    production_cache = ReferenceResultCache(production_dir)

    conflicting = fx.task_result(
        "HumanEval/0",
        fx.full_run_context(),
        q_ref_task=0.0,
        reference_case_pass_count=4,
        first_failure_category=FailureCategory.WRONG_OUTPUT,
    )
    write = production_cache.put(conflicting)
    assert write.disposition == CacheDisposition.WRITE_ACCEPTED
    before = sorted(p.name for p in production_dir.iterdir())

    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.BLOCKED
    assert manifest.preflight_outcome is not None
    assert manifest.preflight_outcome.passed is False
    conflict_entries = [
        entry
        for entry in manifest.preflight_outcome.entries
        if entry.classification == PreflightClassification.CONFLICTING
    ]
    assert len(conflict_entries) == 1
    assert conflict_entries[0].task_id == "HumanEval/0"

    after = sorted(p.name for p in production_dir.iterdir())
    assert before == after
    # The conflicting entry itself is untouched.
    lookup = production_cache.get(cache_key_for(conflicting))
    assert lookup.disposition == CacheDisposition.VALID_HIT
    assert lookup.task_result == conflicting

    with pytest.raises(PromotionPreconditionError):
        promote(manifest, production_cache, results_by_task_id, manifest_path)


def test_corrupt_production_entry_leaves_cache_unchanged_and_blocks(tmp_path: Path) -> None:
    """A malformed production entry blocks promotion at preflight and is
    left byte-for-byte untouched."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_dir = tmp_path / "production"
    production_cache = ReferenceResultCache(production_dir)

    key = cache_key_for(results_by_task_id["HumanEval/0"])
    corrupt_path = production_dir / f"{key.key_digest}.json"
    corrupt_path.write_text("{not even valid json", encoding="utf-8")
    before = corrupt_path.read_bytes()

    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.BLOCKED
    corrupt_entries = [
        entry
        for entry in manifest.preflight_outcome.entries  # type: ignore[union-attr]
        if entry.classification == PreflightClassification.CORRUPT_OR_STALE
    ]
    assert len(corrupt_entries) == 1
    assert corrupt_entries[0].task_id == "HumanEval/0"
    assert corrupt_path.read_bytes() == before


def test_storage_failure_during_preflight_blocks_and_leaves_cache_unchanged(
    tmp_path: Path,
) -> None:
    """An unreadable production entry (a directory occupying the expected
    file path) blocks promotion at preflight without being touched."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_dir = tmp_path / "production"
    production_cache = ReferenceResultCache(production_dir)

    key = cache_key_for(results_by_task_id["HumanEval/0"])
    unreadable_path = production_dir / f"{key.key_digest}.json"
    # A directory in place of the expected entry file: get() will raise
    # IsADirectoryError (an OSError) attempting to read_text() it.
    unreadable_path.mkdir()

    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.BLOCKED
    storage_failure_entries = [
        entry
        for entry in manifest.preflight_outcome.entries  # type: ignore[union-attr]
        if entry.classification == PreflightClassification.STORAGE_FAILURE
    ]
    assert len(storage_failure_entries) == 1
    assert unreadable_path.is_dir()
    assert not list(unreadable_path.iterdir())


# ---------------------------------------------------------------------------
# Interruption before the gate completes
# ---------------------------------------------------------------------------


def test_interruption_before_gate_leaves_production_cache_unchanged(tmp_path: Path) -> None:
    """A manifest that never reached GATE_PASSED can never legally reach
    PREFLIGHT_PASSED, so the production cache stays empty."""
    manifest = fx.candidate_set_manifest()
    identity = fx.staging_identity(manifest)
    expected_task_ids = tuple(entry.task_id for entry in manifest.entries)
    prepared = build_initial_manifest(identity, expected_task_ids)
    assert prepared.state == PromotionState.PREPARED

    production_dir = tmp_path / "production"
    production_cache = ReferenceResultCache(production_dir)
    results_by_task_id = {
        result.task_id: result for result in fx.valid_task_results(fx.full_run_context())
    }
    manifest_path = tmp_path / "promotion_manifest.json"

    # A manifest that never reached GATE_PASSED can never legally reach
    # PREFLIGHT_PASSED -- attempting to preflight it raises rather than
    # silently promoting an ungated run.
    with pytest.raises(Exception):  # PromotionStateTransitionError
        run_preflight(prepared, production_cache, results_by_task_id, manifest_path)

    assert not list(production_dir.iterdir())
    assert not manifest_path.exists()


# ---------------------------------------------------------------------------
# Interruption after exactly k promotions; resumption; idempotent finalization
# ---------------------------------------------------------------------------


def test_interruption_after_exactly_k_promotions_leaves_exactly_those_k(tmp_path: Path) -> None:
    """An interruption after exactly k successful production writes leaves
    exactly those k entries PROMOTED and durably persisted; no more."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_dir = tmp_path / "production"
    production_cache = ReferenceResultCache(production_dir)
    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.PREFLIGHT_PASSED

    k = 7
    interrupting_cache = _InterruptingCache(production_dir, interrupt_after=k)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        promote(manifest, interrupting_cache, results_by_task_id, manifest_path)

    persisted = load_promotion_manifest(manifest_path)
    assert persisted is not None
    assert persisted.state == PromotionState.PROMOTING
    promoted_ids = sorted(
        task_id
        for task_id, state in persisted.entry_states.items()
        if state == EntryPromotionState.PROMOTED
    )
    assert len(promoted_ids) == k
    assert promoted_ids == sorted(persisted.expected_task_ids)[:k]
    for task_id in promoted_ids:
        lookup = production_cache.get(cache_key_for(results_by_task_id[task_id]))
        assert lookup.disposition == CacheDisposition.VALID_HIT
    for task_id in sorted(persisted.expected_task_ids)[k:]:
        lookup = production_cache.get(cache_key_for(results_by_task_id[task_id]))
        assert lookup.disposition == CacheDisposition.MISS


def test_resumption_promotes_only_the_remaining_entries(tmp_path: Path) -> None:
    """Resuming an interrupted promotion writes only the still-PENDING
    entries -- never re-derives approval or reruns the gate."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_dir = tmp_path / "production"
    production_cache = ReferenceResultCache(production_dir)
    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)

    k = 5
    interrupting_cache = _InterruptingCache(production_dir, interrupt_after=k)
    with pytest.raises(RuntimeError):
        promote(manifest, interrupting_cache, results_by_task_id, manifest_path)

    resumed_manifest = load_promotion_manifest(manifest_path)
    assert resumed_manifest is not None
    counting_cache = _CountingCache(production_dir)
    finished = promote(resumed_manifest, counting_cache, results_by_task_id, manifest_path)
    assert finished.state == PromotionState.COMPLETED
    assert len(counting_cache.put_calls) == REQUIRED_TASK_COUNT - k
    assert all(
        state == EntryPromotionState.PROMOTED for state in finished.entry_states.values()
    )
    for result in results_by_task_id.values():
        lookup = production_cache.get(cache_key_for(result))
        assert lookup.disposition == CacheDisposition.VALID_HIT
        assert lookup.task_result == result


def test_repeated_finalization_is_idempotent(tmp_path: Path) -> None:
    """Calling promote() again on an already-COMPLETED manifest is a true
    no-op: unchanged manifest, and production is never touched again."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_dir = tmp_path / "production"
    production_cache = ReferenceResultCache(production_dir)
    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)
    manifest = promote(manifest, production_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.COMPLETED

    refusing_cache = _RefusingCache(production_dir)
    again = promote(manifest, refusing_cache, results_by_task_id, manifest_path)
    assert again == manifest
    assert again.generation == manifest.generation


# ---------------------------------------------------------------------------
# Safe-summary leakage checks
# ---------------------------------------------------------------------------


def test_safe_summary_never_leaks_free_text_or_privileged_paths(tmp_path: Path) -> None:
    """PromotionSummary carries no free-text reason/detail field, and none
    of its string values embed a privileged tmp_path or corrupt content."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_dir = tmp_path / "production"
    production_cache = ReferenceResultCache(production_dir)

    key = cache_key_for(results_by_task_id["HumanEval/0"])
    corrupt_path = production_dir / f"{key.key_digest}.json"
    production_dir.mkdir(parents=True, exist_ok=True)
    corrupt_path.write_text("{not even valid json", encoding="utf-8")

    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.BLOCKED

    summary = build_promotion_summary(manifest, generated_at="2026-08-03T00:00:00Z")
    field_names = {f.name for f in dataclasses.fields(PromotionSummary)}
    assert "reason" not in field_names
    assert "detail" not in field_names
    for value in dataclasses.asdict(summary).values():
        if isinstance(value, str):
            assert str(tmp_path) not in value
            assert "not even valid json" not in value


# ---------------------------------------------------------------------------
# Trace-before-stage ordering, reusing the real H.2B.1 orchestrator
# ---------------------------------------------------------------------------


def test_trace_before_stage_ordering_holds_for_the_staging_cache(tmp_path: Path) -> None:
    """Plugging an H.5 staging cache into the real H.2B.1 orchestrator under
    a fresh CachePolicy still traces before writing to that cache."""
    manifest = fx.candidate_set_manifest()
    identity = fx.staging_identity(manifest, calibration_run_id="h5-trace-order-run")
    staging_cache = build_staging_cache(identity, root=tmp_path / "staging_root")
    trace_recorder = orch_fx.FakeTraceRecorder()

    orch, cache, _audit = orch_fx.orchestrator(
        tmp_path,
        cache=staging_cache,
        cache_policy=CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        trace_recorder=trace_recorder,
    )
    item = orch_fx.work_item("wi-0", 0)
    summary = orch.run([item], run_id="h5-trace-order-run")

    assert summary.outcomes[0].disposition == WorkItemDisposition.EXECUTED_VALID
    assert len(trace_recorder.calls) == 1
    assert trace_recorder.calls[0].disposition == WorkItemDisposition.EXECUTED_VALID

    result = summary.outcomes[0].task_result
    assert result is not None
    lookup = cache.get(cache_key_for(result))
    assert lookup.disposition == CacheDisposition.VALID_HIT
    assert cache is staging_cache


# ---------------------------------------------------------------------------
# No real privileged directory is ever touched
# ---------------------------------------------------------------------------


def test_no_real_privileged_directory_is_touched() -> None:
    """None of this module's tests ever create a real privileged directory
    -- every test roots its caches/manifests under tmp_path."""
    assert not DEFAULT_H5_STAGING_ROOT.exists()
    assert not Path("artifacts/privileged/reference/calibration").exists()
    assert not Path("artifacts/privileged/reference/cache").exists()
