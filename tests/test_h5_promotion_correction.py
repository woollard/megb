"""MEGB-03H.2B.2 recovery/safe-report correction: regression tests for the
narrow correction requested before acceptance --

1. crash-window recovery (a production ``cache.put()`` that succeeded just
   before a crash, with the manifest entry still ``PENDING``, must resume
   as ``ALREADY_SATISFIED`` -- never a conflict, never a duplicate write);
2. manifest progress is never trusted without cache re-verification
   (``verify_completed_promotion``) -- covering deletion, corruption,
   replacement, post-``COMPLETED`` drift, and concurrent mutation between
   preflight and an individual write;
3. the promotion summary is versioned and self-checksummed, and its field
   set stays within the required allowlist.

Synthetic 164-task fixtures only, via tests/_h5_fixtures.py -- no real
privileged corpus access, no Docker.
"""

# See _h5_fixtures.py's own note: shared fixtures across the H.2B.2 test
# modules.
# pylint: disable=duplicate-code

import dataclasses
from pathlib import Path
from typing import Mapping

import pytest

from src.evaluators.schema import FailureCategory
from src.reference.cache_key import cache_key_for
from src.reference.h5_promotion import (
    PROMOTION_SUMMARY_SCHEMA_VERSION,
    InvalidPromotionSummaryError,
    PromotionSummary,
    PromotionVerificationError,
    build_promotion_summary,
    promote,
    run_preflight,
    verify_completed_promotion,
)
from src.reference.h5_promotion_manifest import (
    EntryPromotionState,
    GateOutcome,
    H5PromotionManifest,
    PromotionState,
    advance_manifest,
    build_initial_manifest,
    build_staged_entries,
    load_promotion_manifest,
)
from src.reference.h5_staging import build_staging_cache, evaluate_complete_run_gate
from src.reference.reference_cache import CacheDisposition, CacheWriteResult, ReferenceResultCache
from src.reference.result_schema import ReferenceTaskResult
from tests import _h5_fixtures as fx


def _staged_results_and_gated_manifest(
    tmp_path: Path,
) -> tuple[H5PromotionManifest, Mapping[str, ReferenceTaskResult], Path]:
    """Build a real, gate-approved 164-task run advanced to GATE_PASSED."""
    results = fx.valid_task_results(fx.full_run_context())
    manifest = fx.candidate_set_manifest()
    identity = fx.staging_identity(manifest)
    staging_cache = build_staging_cache(identity, root=tmp_path)
    for result in results:
        assert staging_cache.put(result).disposition == CacheDisposition.WRITE_ACCEPTED
    invocations, task_evaluations = fx.full_trace_for_results(fx.calibration_context(), results)
    gate_result = evaluate_complete_run_gate(
        identity=identity,
        candidate_set_manifest=manifest,
        task_results=results,
        staging_cache=staging_cache,
        invocations=invocations,
        task_evaluations=task_evaluations,
    )
    assert gate_result.passed is True
    results_by_task_id = {result.task_id: result for result in results}
    expected_task_ids = tuple(sorted(results_by_task_id))
    promotion_manifest = advance_manifest(
        build_initial_manifest(identity, expected_task_ids),
        state=PromotionState.GATE_PASSED,
        gate_outcome=GateOutcome(True, "complete-run gate passed"),
        staged_entries=build_staged_entries(results),
    )
    return promotion_manifest, results_by_task_id, tmp_path / "promotion_manifest.json"


def _conflicting_result(task_id: str) -> ReferenceTaskResult:
    """A different, but still valid and same-cache-key, result for
    ``task_id`` -- differs only in fields the cache key does not cover."""
    return fx.task_result(
        task_id,
        fx.full_run_context(),
        q_ref_task=0.0,
        reference_case_pass_count=4,
        first_failure_category=FailureCategory.WRONG_OUTPUT,
    )


_FullyPromotedRun = tuple[
    H5PromotionManifest, Mapping[str, ReferenceTaskResult], Path, ReferenceResultCache, Path
]


def _fully_promoted(tmp_path: Path) -> _FullyPromotedRun:
    """Stage, gate, preflight, and promote a full 164-task run to
    COMPLETED against a real, on-disk production cache."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_dir = tmp_path / "production"
    production_cache = ReferenceResultCache(production_dir)
    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)
    manifest = promote(manifest, production_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.COMPLETED
    return manifest, results_by_task_id, manifest_path, production_cache, production_dir


class _CountingCache(ReferenceResultCache):
    """A real cache that records every task_id it was asked to ``put()``."""

    def __init__(self, cache_dir: Path) -> None:
        super().__init__(cache_dir)
        self.put_calls: list[str] = []

    def put(self, task_result: ReferenceTaskResult) -> CacheWriteResult:
        self.put_calls.append(task_result.task_id)
        return super().put(task_result)


# ---------------------------------------------------------------------------
# Crash-window recovery
# ---------------------------------------------------------------------------


def test_crash_after_cache_put_before_manifest_update_resumes_as_already_satisfied(
    tmp_path: Path,
) -> None:
    """A production put() that already succeeded before a crash (manifest
    entry still PENDING) resumes as ALREADY_SATISFIED -- no duplicate
    write, no conflict reported."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_dir = tmp_path / "production"
    production_cache = ReferenceResultCache(production_dir)
    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.PREFLIGHT_PASSED

    crashed_task_id = manifest.expected_task_ids[0]
    write = production_cache.put(results_by_task_id[crashed_task_id])
    assert write.disposition == CacheDisposition.WRITE_ACCEPTED
    assert manifest.entry_states[crashed_task_id] == EntryPromotionState.PENDING

    counting_cache = _CountingCache(production_dir)
    finished = promote(manifest, counting_cache, results_by_task_id, manifest_path)
    assert finished.state == PromotionState.COMPLETED
    assert finished.entry_states[crashed_task_id] == EntryPromotionState.ALREADY_SATISFIED
    assert crashed_task_id not in counting_cache.put_calls


def test_crash_window_with_a_genuinely_different_entry_blocks_promotion(tmp_path: Path) -> None:
    """If the entry present at resume is genuinely different (not the
    frozen approved staged entry), promotion blocks instead of trusting
    it -- and the differing entry is never overwritten."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_dir = tmp_path / "production"
    production_cache = ReferenceResultCache(production_dir)
    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)

    task_id = manifest.expected_task_ids[0]
    conflicting = _conflicting_result(task_id)
    assert production_cache.put(conflicting).disposition == CacheDisposition.WRITE_ACCEPTED

    finished = promote(manifest, production_cache, results_by_task_id, manifest_path)
    assert finished.state == PromotionState.BLOCKED
    assert finished.entry_states[task_id] == EntryPromotionState.PENDING
    lookup = production_cache.get(cache_key_for(conflicting))
    assert lookup.task_result == conflicting


# ---------------------------------------------------------------------------
# verify_completed_promotion: do not trust manifest progress
# ---------------------------------------------------------------------------


def test_verify_completed_promotion_detects_a_deleted_entry(tmp_path: Path) -> None:
    """A promoted production entry deleted before verification is caught."""
    manifest, results_by_task_id, _path, production_cache, production_dir = _fully_promoted(
        tmp_path
    )
    task_id = manifest.expected_task_ids[0]
    key = cache_key_for(results_by_task_id[task_id])
    (production_dir / f"{key.key_digest}.json").unlink()

    result = verify_completed_promotion(manifest, production_cache, results_by_task_id)
    assert result.verified is False
    assert any(f.task_id == task_id and f.reason == "missing" for f in result.failures)


def test_verify_completed_promotion_detects_a_corrupted_entry(tmp_path: Path) -> None:
    """A promoted production entry corrupted before verification is caught."""
    manifest, results_by_task_id, _path, production_cache, production_dir = _fully_promoted(
        tmp_path
    )
    task_id = manifest.expected_task_ids[0]
    key = cache_key_for(results_by_task_id[task_id])
    (production_dir / f"{key.key_digest}.json").write_text(
        "{not even valid json", encoding="utf-8"
    )

    result = verify_completed_promotion(manifest, production_cache, results_by_task_id)
    assert result.verified is False
    failure = next(f for f in result.failures if f.task_id == task_id)
    assert failure.reason.startswith("unreadable")


def test_verify_completed_promotion_detects_a_replaced_entry(tmp_path: Path) -> None:
    """A promoted production entry replaced by a different valid result
    (same cache key, different content) is caught as content_mismatch."""
    manifest, results_by_task_id, _path, production_cache, production_dir = _fully_promoted(
        tmp_path
    )
    task_id = manifest.expected_task_ids[0]
    original = results_by_task_id[task_id]
    key = cache_key_for(original)
    (production_dir / f"{key.key_digest}.json").unlink()

    replacement = _conflicting_result(task_id)
    assert cache_key_for(replacement) == key
    assert production_cache.put(replacement).disposition == CacheDisposition.WRITE_ACCEPTED

    result = verify_completed_promotion(manifest, production_cache, results_by_task_id)
    assert result.verified is False
    failure = next(f for f in result.failures if f.task_id == task_id)
    assert failure.reason == "content_mismatch"


def test_verify_completed_promotion_passes_when_nothing_has_drifted(tmp_path: Path) -> None:
    """A freshly completed promotion re-verifies cleanly."""
    manifest, results_by_task_id, _path, production_cache, _dir = _fully_promoted(tmp_path)
    result = verify_completed_promotion(manifest, production_cache, results_by_task_id)
    assert result.verified is True
    assert not result.failures
    assert result.checked_count == len(manifest.expected_task_ids)


def test_completed_manifest_with_subsequently_altered_production_raises_on_promote(
    tmp_path: Path,
) -> None:
    """promote() called again on an already-COMPLETED manifest whose
    production cache was altered afterward raises loudly -- it never
    silently retains COMPLETED, and never illegally rewrites the
    (already-accepted) terminal state."""
    manifest, results_by_task_id, manifest_path, production_cache, production_dir = (
        _fully_promoted(tmp_path)
    )
    task_id = manifest.expected_task_ids[0]
    key = cache_key_for(results_by_task_id[task_id])
    (production_dir / f"{key.key_digest}.json").unlink()

    with pytest.raises(PromotionVerificationError):
        promote(manifest, production_cache, results_by_task_id, manifest_path)

    # COMPLETED is never silently rewritten -- the persisted manifest is
    # byte-for-byte the same as before the failed re-verification attempt.
    reloaded = load_promotion_manifest(manifest_path)
    assert reloaded == manifest
    assert reloaded.state == PromotionState.COMPLETED


def test_completed_manifest_with_unaltered_production_is_a_true_noop(tmp_path: Path) -> None:
    """Repeated finalization is still idempotent when nothing has drifted."""
    manifest, results_by_task_id, manifest_path, production_cache, _dir = _fully_promoted(
        tmp_path
    )
    again = promote(manifest, production_cache, results_by_task_id, manifest_path)
    assert again == manifest


def test_concurrent_mutation_after_preflight_before_an_individual_write_blocks(
    tmp_path: Path,
) -> None:
    """An out-of-band write landing between preflight and this specific
    entry's own write is caught by the reread-before-write step inside
    promote(), not just by the (now-stale) preflight snapshot."""
    manifest, results_by_task_id, manifest_path = _staged_results_and_gated_manifest(tmp_path)
    production_dir = tmp_path / "production"
    production_cache = ReferenceResultCache(production_dir)
    manifest = run_preflight(manifest, production_cache, results_by_task_id, manifest_path)
    assert manifest.state == PromotionState.PREFLIGHT_PASSED

    task_id = manifest.expected_task_ids[5]
    conflicting = _conflicting_result(task_id)
    assert production_cache.put(conflicting).disposition == CacheDisposition.WRITE_ACCEPTED

    finished = promote(manifest, production_cache, results_by_task_id, manifest_path)
    assert finished.state == PromotionState.BLOCKED
    assert finished.entry_states[task_id] == EntryPromotionState.PENDING
    lookup = production_cache.get(cache_key_for(conflicting))
    assert lookup.task_result == conflicting


# ---------------------------------------------------------------------------
# Safe promotion summary: versioned, self-checksummed, allowlisted
# ---------------------------------------------------------------------------


def test_promotion_summary_is_self_checksummed(tmp_path: Path) -> None:
    """PromotionSummary auto-computes its own summary_checksum, and a
    reconstructed summary with an intentionally wrong checksum is rejected."""
    manifest, _results, _path, _cache, _dir = _fully_promoted(tmp_path)
    summary = build_promotion_summary(manifest, generated_at="2026-08-03T00:00:00Z")
    assert summary.summary_checksum
    payload = dataclasses.asdict(summary)
    payload["summary_checksum"] = "0" * 64
    with pytest.raises(InvalidPromotionSummaryError):
        PromotionSummary(**payload)


def test_promotion_summary_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    """A PromotionSummary stamped with an unrecognized schema version is rejected."""
    manifest, _results, _path, _cache, _dir = _fully_promoted(tmp_path)
    summary = build_promotion_summary(manifest, generated_at="2026-08-03T00:00:00Z")
    payload = dataclasses.asdict(summary)
    payload["summary_schema_version"] = "some-other-version"
    payload["summary_checksum"] = ""
    with pytest.raises(InvalidPromotionSummaryError):
        PromotionSummary(**payload)


def test_promotion_summary_schema_version_constant_is_stable() -> None:
    """The promotion-summary schema-version constant has not silently changed."""
    assert PROMOTION_SUMMARY_SCHEMA_VERSION == "megb-03h5-promotion-summary-v1"


def test_promotion_summary_includes_required_counts_and_timestamp(tmp_path: Path) -> None:
    """The summary carries expected/staged/promoted counts, gate/preflight/
    final states, a generation timestamp, and its own report checksum."""
    manifest, _results, _path, _cache, _dir = _fully_promoted(tmp_path)
    summary = build_promotion_summary(manifest, generated_at="2026-08-03T00:00:00Z")
    assert summary.expected_task_count == len(manifest.expected_task_ids)
    assert summary.staged_entry_count == len(manifest.staged_entries)
    assert summary.entry_state_counts["PROMOTED"] == len(manifest.expected_task_ids)
    assert summary.state == "COMPLETED"
    assert summary.gate_passed is True
    assert summary.preflight_passed is True
    assert summary.generated_at == "2026-08-03T00:00:00Z"
    assert summary.summary_checksum


def test_promotion_summary_field_allowlist_excludes_forbidden_content() -> None:
    """The summary's own field set structurally excludes task/case
    identities, candidate identities/source, cache keys, per-entry
    (task-linked) states, raw diagnostics, and privileged paths.

    ``candidate_set_manifest_checksum`` is deliberately exempted from the
    ``candidate`` substring check: it is a manifest-level artifact
    checksum (explicitly allowlisted -- "safe run and artifact
    checksums"), not a candidate identity or candidate source.
    """
    field_names = {f.name for f in dataclasses.fields(PromotionSummary)}
    exempt = {"candidate_set_manifest_checksum"}
    forbidden_substrings = (
        "task_id",
        "candidate_id",
        "candidate_sha256",
        "candidate_source",
        "cache_key",
        "reason",
        "detail",
        "path",
        "expected_output",
        "case_id",
    )
    for field_name in field_names - exempt:
        for forbidden in forbidden_substrings:
            assert forbidden not in field_name, f"{field_name!r} contains forbidden {forbidden!r}"
