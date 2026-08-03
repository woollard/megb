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

import hashlib
import json
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


class PromotionVerificationError(RuntimeError):
    """Raised when :func:`promote` is called again on an already-
    ``COMPLETED`` manifest and :func:`verify_completed_promotion` finds
    that production no longer matches it (deleted, corrupted, or replaced
    since promotion). ``COMPLETED`` is an already-accepted terminal state
    -- :func:`~src.reference.h5_promotion_manifest.advance_manifest` never
    rewrites it -- so drift discovered this late is surfaced loudly rather
    than silently trusted or silently discarded."""


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


def promote(  # pylint: disable=too-many-locals
    manifest: H5PromotionManifest,
    production_cache: ReferenceResultCache,
    staged_results_by_task_id: Mapping[str, ReferenceTaskResult],
    manifest_path: Path,
) -> H5PromotionManifest:
    """Incrementally, resumably promote every still-``PENDING`` entry into
    ``production_cache``.

    Before writing any ``PENDING`` entry, rereads its production entry
    (never trusts the manifest's own bookkeeping alone) -- this closes the
    crash window between a successful ``cache.put()`` and the manifest
    entry actually advancing past ``PENDING``: on resumption, an identical
    entry already present is marked ``ALREADY_SATISFIED`` without a
    redundant write or a false conflict; a genuinely different entry blocks
    promotion outright, without overwriting it. Persists the manifest
    durably after every individual entry, so an interruption at any point
    leaves only that safe subset durably recorded and present.

    Before declaring ``COMPLETED`` (whether reached for the first time this
    call, or already recorded as such by an earlier call), independently
    re-verifies every entry the manifest records as ``PROMOTED``/
    ``ALREADY_SATISFIED`` is still present and content-equivalent via
    :func:`verify_completed_promotion` -- manifest progress is never
    trusted without cache verification. A first-time completion that fails
    this check is instead ``BLOCKED``. Calling ``promote()`` again on a
    manifest already recorded as ``COMPLETED`` never rewrites that
    (already-accepted, terminal) state: if verification then finds
    production has since drifted, it raises
    :class:`PromotionVerificationError` rather than silently trusting or
    silently discarding the drift; otherwise it is a true read-only no-op.

    Raises :class:`PromotionPreconditionError` if ``manifest.state`` is not
    ``PREFLIGHT_PASSED``, ``PROMOTING``, or ``COMPLETED``.
    """
    if manifest.state == PromotionState.COMPLETED:
        verification = verify_completed_promotion(
            manifest, production_cache, staged_results_by_task_id
        )
        if not verification.verified:
            raise PromotionVerificationError(_completed_drift_message(manifest, verification))
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
        lookup = production_cache.get(cache_key_for(staged_result))
        entry, entry_state, ok = _classify_preflight_lookup(task_id, lookup, staged_result)
        if entry_state == EntryPromotionState.ALREADY_SATISFIED:
            # Crash-window recovery: an earlier put() already succeeded for
            # this identical entry before a prior crash -- no redundant
            # write, no false conflict.
            current = _advance_entry_state(current, task_id, entry_state)
            save_promotion_manifest(manifest_path, current)
            continue
        if not ok:
            current = _block(
                current,
                f"conflict discovered while re-reading task {task_id!r} before promotion: "
                f"{entry.classification.value}",
            )
            save_promotion_manifest(manifest_path, current)
            return current
        write = production_cache.put(staged_result)
        if write.disposition == CacheDisposition.WRITE_ACCEPTED:
            current = _advance_entry_state(current, task_id, EntryPromotionState.PROMOTED)
            save_promotion_manifest(manifest_path, current)
            continue
        # A race: the entry became conflicting between our get() and put().
        current = _block(
            current,
            f"conflict discovered mid-promotion for task {task_id!r}: {write.disposition.value}",
        )
        save_promotion_manifest(manifest_path, current)
        return current

    verification = verify_completed_promotion(current, production_cache, staged_results_by_task_id)
    if not verification.verified:
        failed_ids = ", ".join(failure.task_id for failure in verification.failures)
        current = _block(
            current,
            f"post-promotion verification failed for {len(verification.failures)} of "
            f"{verification.checked_count} entries before declaring COMPLETED ({failed_ids})",
        )
        save_promotion_manifest(manifest_path, current)
        return current

    current = advance_manifest(current, state=PromotionState.COMPLETED)
    save_promotion_manifest(manifest_path, current)
    return current


def _advance_entry_state(
    manifest: H5PromotionManifest, task_id: str, new_state: EntryPromotionState
) -> H5PromotionManifest:
    new_entry_states = dict(manifest.entry_states)
    new_entry_states[task_id] = new_state
    return advance_manifest(manifest, entry_states=new_entry_states)


def _block(manifest: H5PromotionManifest, reason: str) -> H5PromotionManifest:
    prior_entries = manifest.preflight_outcome.entries if manifest.preflight_outcome else ()
    blocked_preflight = PreflightOutcome(passed=False, reason=reason, entries=prior_entries)
    return advance_manifest(
        manifest, state=PromotionState.BLOCKED, preflight_outcome=blocked_preflight
    )


@dataclass(frozen=True)
class VerificationFailure:
    """One entry that failed :func:`verify_completed_promotion` -- ``reason``
    is always a short, typed, allowlisted label (``missing``,
    ``content_mismatch``, or ``unreadable: <CacheDisposition value>``),
    never a free-text detail string that could embed a privileged path."""

    task_id: str
    reason: str

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError("task_id must be nonempty")
        if not self.reason:
            raise ValueError("reason must be nonempty")


@dataclass(frozen=True)
class PromotionVerificationResult:
    """Outcome of :func:`verify_completed_promotion`."""

    verified: bool
    checked_count: int
    failures: tuple[VerificationFailure, ...]

    def __post_init__(self) -> None:
        if self.verified and self.failures:
            raise ValueError("a verified result must not carry any failures")
        if not self.verified and not self.failures:
            raise ValueError("an unverified result must carry at least one failure")
        if self.checked_count < len(self.failures):
            raise ValueError("checked_count cannot be smaller than the number of failures")


def verify_completed_promotion(
    manifest: H5PromotionManifest,
    production_cache: ReferenceResultCache,
    staged_results_by_task_id: Mapping[str, ReferenceTaskResult],
) -> PromotionVerificationResult:
    """Read-only operator check: never writes to ``production_cache`` or to
    any manifest file. Confirms every entry ``manifest`` currently records
    as ``PROMOTED``/``ALREADY_SATISFIED`` is still present in
    ``production_cache`` and content-equivalent to its frozen, gate-
    approved staged entry -- manifest bookkeeping is never trusted on its
    own. Callable at any time, including against an already-``COMPLETED``
    manifest, to detect silent drift (deletion, corruption, or replacement
    with a different valid result) that happened after promotion."""
    failures: list[VerificationFailure] = []
    checked = 0
    for task_id in manifest.expected_task_ids:
        entry_state = manifest.entry_states[task_id]
        if entry_state not in (EntryPromotionState.PROMOTED, EntryPromotionState.ALREADY_SATISFIED):
            continue
        checked += 1
        staged_result = staged_results_by_task_id[task_id]
        lookup = production_cache.get(cache_key_for(staged_result))
        reason = _verification_failure_reason(lookup, staged_result)
        if reason is not None:
            failures.append(VerificationFailure(task_id, reason))
    return PromotionVerificationResult(
        verified=not failures, checked_count=checked, failures=tuple(failures)
    )


def _verification_failure_reason(
    lookup: CacheLookupResult, staged_result: ReferenceTaskResult
) -> str | None:
    if lookup.disposition == CacheDisposition.MISS:
        return "missing"
    if lookup.disposition == CacheDisposition.VALID_HIT:
        assert lookup.task_result is not None
        if logically_equivalent(lookup.task_result, staged_result):
            return None
        return "content_mismatch"
    return f"unreadable: {lookup.disposition.value}"


def _completed_drift_message(
    manifest: H5PromotionManifest, verification: PromotionVerificationResult
) -> str:
    failed_ids = ", ".join(failure.task_id for failure in verification.failures)
    return (
        f"manifest already COMPLETED at generation {manifest.generation} no longer matches "
        f"production: {len(verification.failures)} of {verification.checked_count} previously-"
        f"promoted/already-satisfied entries failed re-verification ({failed_ids})"
    )


PROMOTION_SUMMARY_SCHEMA_VERSION = "megb-03h5-promotion-summary-v1"


class InvalidPromotionSummaryError(ValueError):
    """Raised when a :class:`PromotionSummary`'s ``summary_schema_version``
    is unrecognized, or its ``summary_checksum`` does not match its own
    recomputed contents (tampered or corrupted summary)."""


def _summary_checksum_of(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PromotionSummary:  # pylint: disable=too-many-instance-attributes
    """Safe, allowlisted, versioned, self-checksummed promotion summary
    suitable for committed output.

    Contains only a schema/report version, safe run and artifact
    checksums, expected/staged/promoted/already-satisfied counts, gate/
    preflight/final states, a generation timestamp, and its own
    ``summary_checksum`` -- structurally excludes task or case identities,
    candidate identities or source, expected outputs, cache keys, per-entry
    (task-linked) states, raw diagnostics, and privileged filesystem paths:
    no field here is capable of carrying any of those. ``entry_state_counts``/
    ``preflight_classification_counts`` are aggregate counts across all 164
    entries, never keyed by task id, so they carry no per-entry identity.
    Free-form ``reason``/``detail`` strings (which could embed a filesystem
    path in a storage-failure message) are deliberately never included.
    """

    summary_schema_version: str
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
    staged_entry_count: int
    state: str
    generation: int
    interrupted: bool
    gate_passed: bool | None
    preflight_passed: bool | None
    preflight_classification_counts: Mapping[str, int]
    entry_state_counts: Mapping[str, int]
    generated_at: str
    summary_checksum: str = ""

    def __post_init__(self) -> None:
        if self.summary_schema_version != PROMOTION_SUMMARY_SCHEMA_VERSION:
            raise InvalidPromotionSummaryError(
                f"summary_schema_version {self.summary_schema_version!r} does not match the "
                f"version this module implements ({PROMOTION_SUMMARY_SCHEMA_VERSION!r})"
            )
        if not self.generated_at:
            raise InvalidPromotionSummaryError("generated_at must be a nonempty string")
        payload = _promotion_summary_payload(self)
        expected_checksum = _summary_checksum_of(payload)
        if self.summary_checksum and self.summary_checksum != expected_checksum:
            raise InvalidPromotionSummaryError(
                f"summary_checksum {self.summary_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted promotion summary"
            )
        object.__setattr__(self, "summary_checksum", expected_checksum)


def _promotion_summary_payload(summary: PromotionSummary) -> dict[str, object]:
    return {
        "summary_schema_version": summary.summary_schema_version,
        "manifest_schema_version": summary.manifest_schema_version,
        "calibration_run_id": summary.calibration_run_id,
        "execution_profile_id": summary.execution_profile_id,
        "evaluator_version": summary.evaluator_version,
        "execution_protocol_version": summary.execution_protocol_version,
        "dataset_version": summary.dataset_version,
        "partition_version": summary.partition_version,
        "oracle_version": summary.oracle_version,
        "comparison_profile_version": summary.comparison_profile_version,
        "task_manifest_checksum": summary.task_manifest_checksum,
        "candidate_set_manifest_checksum": summary.candidate_set_manifest_checksum,
        "expected_task_count": summary.expected_task_count,
        "staged_entry_count": summary.staged_entry_count,
        "state": summary.state,
        "generation": summary.generation,
        "interrupted": summary.interrupted,
        "gate_passed": summary.gate_passed,
        "preflight_passed": summary.preflight_passed,
        "preflight_classification_counts": dict(summary.preflight_classification_counts),
        "entry_state_counts": dict(summary.entry_state_counts),
        "generated_at": summary.generated_at,
    }


def build_promotion_summary(
    manifest: H5PromotionManifest, *, generated_at: str
) -> PromotionSummary:
    """Build the safe, self-checksummed :class:`PromotionSummary` for
    ``manifest``. ``generated_at`` is caller-supplied (an ISO-8601
    timestamp) rather than sourced internally, matching this codebase's
    existing safe-report convention (e.g.
    :func:`~src.reference.calibration_summary.build_calibration_summary_report`)."""
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
        summary_schema_version=PROMOTION_SUMMARY_SCHEMA_VERSION,
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
        staged_entry_count=len(manifest.staged_entries),
        state=manifest.state.value,
        generation=manifest.generation,
        interrupted=manifest.interrupted,
        gate_passed=manifest.gate_outcome.passed if manifest.gate_outcome is not None else None,
        preflight_passed=(
            manifest.preflight_outcome.passed if manifest.preflight_outcome is not None else None
        ),
        preflight_classification_counts=preflight_classification_counts,
        entry_state_counts=entry_state_counts,
        generated_at=generated_at,
    )
