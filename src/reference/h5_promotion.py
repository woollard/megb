"""MEGB-03H.2B.2: production-cache preflight and incremental, resumable
promotion, plus the safe, allowlisted promotion summary.

Neither function here ever reruns the complete-run gate
(:func:`~src.reference.h5_staging.evaluate_complete_run_gate`) -- both
operate purely from an already-``GATE_PASSED``/``PREFLIGHT_PASSED``
:class:`~src.reference.h5_promotion_manifest.H5PromotionManifest`'s own
frozen, gate-approved ``entry_states``, so resuming an interrupted
preflight or promotion never re-derives approval from a different staged
set. Manifest updates are always durably persisted (atomic write + flush +
fsync, via :func:`~src.reference.h5_promotion_manifest.save_promotion_manifest`)
immediately after each individual state change, so an interruption at any
point leaves the manifest an exact record of real progress.
"""

# PromotionSummary intentionally repeats several of H5StagingIdentity's own
# field names (calibration_run_id, execution_profile_id, evaluator_version,
# dataset/partition/oracle/comparison identities) -- the same recurring
# identity vocabulary, projected here into a safe, allowlisted summary
# shape rather than composing the identity object directly. Expected and
# accepted, not a defect (see h5_staging.py's own equivalent note).
# pylint: disable=duplicate-code

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from src.reference.cache_key import cache_key_for
from src.reference.h5_promotion_manifest import (
    EntryPromotionState,
    H5PromotionManifest,
    PreflightClassification,
    PreflightEntryResult,
    PreflightOutcome,
    PromotionState,
    advance_manifest,
    save_promotion_manifest,
)
from src.reference.reference_cache import CacheDisposition, CacheLookupResult, ReferenceResultCache
from src.reference.reference_orchestrator_admission import logically_equivalent
from src.reference.result_schema import ReferenceTaskResult


class PromotionPreconditionError(ValueError):
    """Raised when :func:`run_preflight`/:func:`promote` is called against a
    manifest whose ``state`` cannot legally reach the requested next state
    -- see :func:`~src.reference.h5_promotion_manifest.advance_manifest`."""


def run_preflight(  # pylint: disable=too-many-locals
    manifest: H5PromotionManifest,
    production_cache: ReferenceResultCache,
    staged_results_by_task_id: Mapping[str, ReferenceTaskResult],
    manifest_path: Path,
) -> H5PromotionManifest:
    """Classify every approved entry against the production cache
    (read-only -- never writes) before the first production write.

    Blocks (``PromotionState.BLOCKED``) on any ``CONFLICTING``,
    ``CORRUPT_OR_STALE``, or ``STORAGE_FAILURE`` classification; an
    ``IDENTICAL_VALID`` entry is marked ``ALREADY_SATISFIED`` (never
    relabeled as if freshly executed) and never written again. Persists
    the result durably and returns the new manifest generation.
    """
    entry_states = dict(manifest.entry_states)
    entries: list[PreflightEntryResult] = []
    all_ok = True
    for task_id in manifest.expected_task_ids:
        staged_result = staged_results_by_task_id[task_id]
        lookup = production_cache.get(cache_key_for(staged_result))
        entry, entry_state, ok = _classify_preflight_lookup(task_id, lookup, staged_result)
        entry_states[task_id] = entry_state
        all_ok = all_ok and ok
        entries.append(entry)

    reason = (
        "every entry is absent-or-identical; safe to promote into the production cache"
        if all_ok
        else "at least one entry is conflicting, corrupt/stale, or unreadable; promotion blocked"
    )
    preflight_outcome = PreflightOutcome(passed=all_ok, reason=reason, entries=tuple(entries))
    new_state = PromotionState.PREFLIGHT_PASSED if all_ok else PromotionState.BLOCKED
    updated = advance_manifest(
        manifest, state=new_state, preflight_outcome=preflight_outcome, entry_states=entry_states
    )
    save_promotion_manifest(manifest_path, updated)
    return updated


def _classify_preflight_lookup(
    task_id: str, lookup: CacheLookupResult, staged_result: ReferenceTaskResult
) -> tuple[PreflightEntryResult, EntryPromotionState, bool]:
    """Return ``(entry_result, entry_state, ok)`` for one prospective
    entry's read-only production-cache lookup."""
    disposition = lookup.disposition
    if disposition == CacheDisposition.MISS:
        classification = PreflightClassification.ABSENT
        detail = "no existing production entry"
        entry_state, ok = EntryPromotionState.PENDING, True
    elif disposition == CacheDisposition.VALID_HIT:
        assert lookup.task_result is not None
        if logically_equivalent(lookup.task_result, staged_result):
            classification = PreflightClassification.IDENTICAL_VALID
            detail = "identical valid production entry already present"
            entry_state, ok = EntryPromotionState.ALREADY_SATISFIED, True
        else:
            classification = PreflightClassification.CONFLICTING
            detail = "a different valid production entry already exists under this cache key"
            entry_state, ok = EntryPromotionState.PENDING, False
    elif disposition in (CacheDisposition.STALE_INCOMPATIBLE, CacheDisposition.CORRUPT):
        classification = PreflightClassification.CORRUPT_OR_STALE
        detail = f"{disposition.value}: {lookup.detail}"
        entry_state, ok = EntryPromotionState.PENDING, False
    else:
        classification = PreflightClassification.STORAGE_FAILURE
        detail = f"{disposition.value}: {lookup.detail}"
        entry_state, ok = EntryPromotionState.PENDING, False
    return PreflightEntryResult(task_id, classification, detail), entry_state, ok


def promote(
    manifest: H5PromotionManifest,
    production_cache: ReferenceResultCache,
    staged_results_by_task_id: Mapping[str, ReferenceTaskResult],
    manifest_path: Path,
) -> H5PromotionManifest:
    """Incrementally, resumably promote every still-``PENDING`` entry into
    ``production_cache``. Idempotent: an already-``PROMOTED``/
    ``ALREADY_SATISFIED`` entry is skipped without touching the cache
    again. Persists the manifest durably after every individual promoted
    entry, so an interruption at any point leaves only that safe subset
    durably recorded and present. A conflict discovered mid-promotion (only
    possible if the production cache changed out-of-band since preflight)
    stops promotion entirely -- never skips past it or overwrites existing
    data -- and transitions the manifest to ``BLOCKED``.

    Calling ``promote()`` again on an already-``COMPLETED`` manifest is a
    true no-op (returns it unchanged, writes nothing) -- repeated
    finalization is idempotent.

    Raises :class:`PromotionPreconditionError` if ``manifest.state`` is not
    ``PREFLIGHT_PASSED``, ``PROMOTING``, or ``COMPLETED``.
    """
    if manifest.state == PromotionState.COMPLETED:
        return manifest
    if manifest.state not in (PromotionState.PREFLIGHT_PASSED, PromotionState.PROMOTING):
        raise PromotionPreconditionError(
            f"promote() requires a manifest in PREFLIGHT_PASSED or PROMOTING state, "
            f"got {manifest.state.value}"
        )
    current = manifest
    if current.state == PromotionState.PREFLIGHT_PASSED:
        current = advance_manifest(current, state=PromotionState.PROMOTING)
        save_promotion_manifest(manifest_path, current)

    for task_id in current.expected_task_ids:
        if current.entry_states[task_id] != EntryPromotionState.PENDING:
            continue  # already ALREADY_SATISFIED or PROMOTED -- idempotent skip
        staged_result = staged_results_by_task_id[task_id]
        write = production_cache.put(staged_result)
        if write.disposition == CacheDisposition.WRITE_ACCEPTED:
            new_entry_states = dict(current.entry_states)
            new_entry_states[task_id] = EntryPromotionState.PROMOTED
            current = advance_manifest(current, entry_states=new_entry_states)
            save_promotion_manifest(manifest_path, current)
            continue
        current = _block_on_mid_promotion_conflict(
            current, task_id, write.disposition, write.detail
        )
        save_promotion_manifest(manifest_path, current)
        return current

    current = advance_manifest(current, state=PromotionState.COMPLETED)
    save_promotion_manifest(manifest_path, current)
    return current


def _block_on_mid_promotion_conflict(
    manifest: H5PromotionManifest,
    task_id: str,
    disposition: CacheDisposition,
    detail: str,
) -> H5PromotionManifest:
    prior_entries = manifest.preflight_outcome.entries if manifest.preflight_outcome else ()
    blocked_preflight = PreflightOutcome(
        passed=False,
        reason=f"conflict discovered mid-promotion for task {task_id!r}: {disposition.value}",
        entries=prior_entries,
    )
    del detail  # not included in the (safe, allowlisted-only) preflight reason
    return advance_manifest(
        manifest, state=PromotionState.BLOCKED, preflight_outcome=blocked_preflight
    )


@dataclass(frozen=True)
class PromotionSummary:
    """Safe, allowlisted promotion summary suitable for committed output.

    Contains only run/checksum identities, counts, states, and
    dispositions -- structurally excludes candidate source, expected
    output, case identity, raw diagnostics, and privileged paths: no field
    here is capable of carrying any of those, and free-form ``reason``/
    ``detail`` strings (which could embed a filesystem path in a storage-
    failure message) are deliberately never included.
    """

    manifest_schema_version: str
    calibration_run_id: str
    execution_profile_id: str
    evaluator_version: str
    execution_protocol_version: str
    dataset_version: str
    partition_version: str
    oracle_version: str
    comparison_profile_version: str
    task_manifest_checksum: str
    candidate_set_manifest_checksum: str
    expected_task_count: int
    state: str
    generation: int
    interrupted: bool
    gate_passed: bool | None
    preflight_passed: bool | None
    preflight_classification_counts: Mapping[str, int]
    entry_state_counts: Mapping[str, int]


def build_promotion_summary(manifest: H5PromotionManifest) -> PromotionSummary:
    """Build the safe :class:`PromotionSummary` for ``manifest``."""
    entry_state_counts: dict[str, int] = {}
    for entry_state in manifest.entry_states.values():
        entry_state_counts[entry_state.value] = entry_state_counts.get(entry_state.value, 0) + 1

    preflight_classification_counts: dict[str, int] = {}
    if manifest.preflight_outcome is not None:
        for entry in manifest.preflight_outcome.entries:
            key = entry.classification.value
            preflight_classification_counts[key] = preflight_classification_counts.get(key, 0) + 1

    identity = manifest.identity
    return PromotionSummary(
        manifest_schema_version=manifest.manifest_schema_version,
        calibration_run_id=identity.calibration_run_id,
        execution_profile_id=identity.execution_profile_id,
        evaluator_version=identity.evaluator_version,
        execution_protocol_version=identity.execution_protocol_version,
        dataset_version=identity.dataset_version,
        partition_version=identity.partition_version,
        oracle_version=identity.oracle_version,
        comparison_profile_version=identity.comparison_profile_version,
        task_manifest_checksum=identity.task_manifest_checksum,
        candidate_set_manifest_checksum=identity.candidate_set_manifest_checksum,
        expected_task_count=identity.expected_task_count,
        state=manifest.state.value,
        generation=manifest.generation,
        interrupted=manifest.interrupted,
        gate_passed=manifest.gate_outcome.passed if manifest.gate_outcome is not None else None,
        preflight_passed=(
            manifest.preflight_outcome.passed if manifest.preflight_outcome is not None else None
        ),
        preflight_classification_counts=preflight_classification_counts,
        entry_state_counts=entry_state_counts,
    )
