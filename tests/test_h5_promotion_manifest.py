"""Tests for MEGB-03H.2B.2's promotion-manifest schema
(src.reference.h5_promotion_manifest): construction invariants, state
transitions, checksum tampering, and crash-safe durable I/O. Synthetic
fixtures only, via tests/_h5_fixtures.py -- no real privileged corpus
access, no Docker.
"""

# See _h5_fixtures.py's own note: self-contained fixtures, shared across
# the H.2B.2 test modules.
# pylint: disable=duplicate-code

import dataclasses
import json
from pathlib import Path

import pytest

from src.reference.h5_promotion_manifest import (
    EntryPromotionState,
    GateOutcome,
    H5PromotionManifest,
    H5_PROMOTION_MANIFEST_SCHEMA_VERSION,
    InvalidPromotionManifestError,
    PreflightEntryResult,
    PreflightOutcome,
    PromotionState,
    PromotionStateTransitionError,
    advance_manifest,
    build_initial_manifest,
    build_staged_entries,
    load_or_create_manifest,
    load_promotion_manifest,
    manifest_from_dict,
    manifest_to_dict,
    save_promotion_manifest,
)
from src.reference.h5_staging import H5StagingIdentity
from tests import _h5_fixtures as fx


def _identity() -> H5StagingIdentity:
    return fx.staging_identity(fx.candidate_set_manifest())


def _expected_task_ids() -> tuple[str, ...]:
    return tuple(entry.task_id for entry in fx.candidate_set_entries())


def _initial_manifest() -> H5PromotionManifest:
    return build_initial_manifest(_identity(), _expected_task_ids())


# ---------------------------------------------------------------------------
# Construction invariants
# ---------------------------------------------------------------------------


def test_build_initial_manifest_is_prepared_with_every_entry_pending() -> None:
    """A freshly built initial manifest is PREPARED with every entry PENDING."""
    manifest = _initial_manifest()
    assert manifest.state == PromotionState.PREPARED
    assert manifest.generation == 0
    assert all(state == EntryPromotionState.PENDING for state in manifest.entry_states.values())
    assert manifest.gate_outcome is None
    assert manifest.preflight_outcome is None


def test_prepared_with_a_gate_outcome_is_rejected() -> None:
    """A PREPARED manifest may never carry a gate_outcome."""
    manifest = _initial_manifest()
    with pytest.raises(InvalidPromotionManifestError):
        dataclasses.replace(
            manifest, gate_outcome=GateOutcome(True, "ok"), manifest_checksum=""
        )


def test_gate_passed_without_a_passed_gate_outcome_is_rejected() -> None:
    """GATE_PASSED requires a passed gate_outcome to be present."""
    manifest = _initial_manifest()
    with pytest.raises(InvalidPromotionManifestError):
        dataclasses.replace(manifest, state=PromotionState.GATE_PASSED, manifest_checksum="")


def test_completed_with_a_pending_entry_is_rejected() -> None:
    """COMPLETED requires every entry_state to be non-PENDING."""
    manifest = _initial_manifest()
    entry_states = dict(manifest.entry_states)
    task_ids = list(entry_states)
    for task_id in task_ids[:-1]:
        entry_states[task_id] = EntryPromotionState.PROMOTED
    with pytest.raises(InvalidPromotionManifestError):
        dataclasses.replace(
            manifest,
            state=PromotionState.COMPLETED,
            gate_outcome=GateOutcome(True, "ok"),
            preflight_outcome=PreflightOutcome(True, "ok", ()),
            entry_states=entry_states,
            manifest_checksum="",
        )


def test_blocked_requires_a_failed_gate_or_preflight_outcome() -> None:
    """BLOCKED requires a failed gate_outcome or preflight_outcome."""
    manifest = _initial_manifest()
    with pytest.raises(InvalidPromotionManifestError):
        dataclasses.replace(
            manifest,
            state=PromotionState.BLOCKED,
            gate_outcome=GateOutcome(True, "ok"),
            manifest_checksum="",
        )


def test_expected_task_ids_must_be_sorted() -> None:
    """expected_task_ids must be sorted (canonical order), not merely unique."""
    manifest = _initial_manifest()
    reversed_ids = tuple(reversed(manifest.expected_task_ids))
    with pytest.raises(InvalidPromotionManifestError):
        dataclasses.replace(manifest, expected_task_ids=reversed_ids, manifest_checksum="")


def test_entry_states_keys_must_match_expected_task_ids() -> None:
    """entry_states' key set must exactly equal expected_task_ids."""
    manifest = _initial_manifest()
    entry_states = dict(manifest.entry_states)
    del entry_states[manifest.expected_task_ids[0]]
    with pytest.raises(InvalidPromotionManifestError):
        dataclasses.replace(manifest, entry_states=entry_states, manifest_checksum="")


def test_unsupported_schema_version_is_rejected() -> None:
    """An unrecognized manifest_schema_version is rejected."""
    manifest = _initial_manifest()
    with pytest.raises(InvalidPromotionManifestError):
        dataclasses.replace(
            manifest, manifest_schema_version="some-other-version", manifest_checksum=""
        )


# ---------------------------------------------------------------------------
# State-transition violations
# ---------------------------------------------------------------------------


def test_prepared_to_promoting_is_an_illegal_transition() -> None:
    """PREPARED may only legally advance to GATE_PASSED or BLOCKED."""
    manifest = _initial_manifest()
    with pytest.raises(PromotionStateTransitionError):
        advance_manifest(manifest, state=PromotionState.PROMOTING)


def _fully_promoted_manifest() -> H5PromotionManifest:
    manifest = _initial_manifest()
    context = fx.full_run_context()
    staged_entries = build_staged_entries(fx.valid_task_results(context))
    manifest = advance_manifest(
        manifest,
        state=PromotionState.GATE_PASSED,
        gate_outcome=GateOutcome(True, "ok"),
        staged_entries=staged_entries,
    )
    manifest = advance_manifest(
        manifest,
        state=PromotionState.PREFLIGHT_PASSED,
        preflight_outcome=PreflightOutcome(True, "ok", ()),
    )
    manifest = advance_manifest(manifest, state=PromotionState.PROMOTING)
    entry_states = {
        task_id: EntryPromotionState.PROMOTED for task_id in manifest.expected_task_ids
    }
    manifest = advance_manifest(manifest, entry_states=entry_states)
    return advance_manifest(manifest, state=PromotionState.COMPLETED)


def test_completed_is_a_terminal_state() -> None:
    """COMPLETED never legally transitions to any other state."""
    completed = _fully_promoted_manifest()
    assert completed.state == PromotionState.COMPLETED
    with pytest.raises(PromotionStateTransitionError):
        advance_manifest(completed, state=PromotionState.PROMOTING)


# ---------------------------------------------------------------------------
# Checksum tampering
# ---------------------------------------------------------------------------


def test_tampered_manifest_checksum_is_rejected() -> None:
    """A manifest_checksum that doesn't match its own recomputed contents is rejected."""
    manifest = _initial_manifest()
    data = manifest_to_dict(manifest)
    data["manifest_checksum"] = "0" * 64
    with pytest.raises(InvalidPromotionManifestError):
        manifest_from_dict(data)


def test_tampered_entry_state_after_checksum_stamped_is_detected() -> None:
    """Tampering with entry_states after the checksum was stamped is detected."""
    manifest = _initial_manifest()
    data = manifest_to_dict(manifest)
    task_id = manifest.expected_task_ids[0]
    data["entry_states"][task_id] = EntryPromotionState.PROMOTED.value
    with pytest.raises(InvalidPromotionManifestError):
        manifest_from_dict(data)


# ---------------------------------------------------------------------------
# Durable save/load, crash-safe recovery
# ---------------------------------------------------------------------------


def test_save_and_load_round_trips(tmp_path: Path) -> None:
    """A saved manifest round-trips byte-for-byte through load."""
    manifest = _initial_manifest()
    path = tmp_path / "promotion_manifest.json"
    save_promotion_manifest(path, manifest)
    loaded = load_promotion_manifest(path)
    assert loaded == manifest


def test_load_promotion_manifest_returns_none_when_absent(tmp_path: Path) -> None:
    """Loading a manifest path that doesn't exist returns None."""
    assert load_promotion_manifest(tmp_path / "does_not_exist.json") is None


def test_save_promotion_manifest_uses_atomic_temp_file_replace(tmp_path: Path) -> None:
    """A normal save leaves no leftover temp file behind."""
    manifest = _initial_manifest()
    path = tmp_path / "promotion_manifest.json"
    save_promotion_manifest(path, manifest)
    # No leftover temp file after a normal, successful save.
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".tmp-")]
    assert not leftovers


def test_crash_safe_recovery_ignores_a_stray_temp_file(tmp_path: Path) -> None:
    """A stray, malformed temp file alongside a real manifest is ignored on load."""
    manifest = _initial_manifest()
    path = tmp_path / "promotion_manifest.json"
    save_promotion_manifest(path, manifest)
    # Simulate a crash between writing the temp file and the atomic
    # replace: a stray, possibly-incomplete temp file is left behind, but
    # the real manifest file itself was never touched by the crash.
    stray = tmp_path / ".tmp-deadbeef-promotion_manifest.json"
    stray.write_text("{not even valid json", encoding="utf-8")
    loaded = load_promotion_manifest(path)
    assert loaded == manifest


def test_load_or_create_returns_fresh_manifest_when_absent(tmp_path: Path) -> None:
    """load_or_create_manifest builds (but never persists) a fresh PREPARED manifest."""
    path = tmp_path / "promotion_manifest.json"
    identity = _identity()
    manifest = load_or_create_manifest(path, identity, _expected_task_ids())
    assert manifest.state == PromotionState.PREPARED
    assert not path.exists()  # load_or_create never persists by itself


def test_load_or_create_resumes_an_existing_compatible_manifest(tmp_path: Path) -> None:
    """load_or_create_manifest resumes an existing, identity-compatible manifest."""
    path = tmp_path / "promotion_manifest.json"
    identity = _identity()
    original = build_initial_manifest(identity, _expected_task_ids())
    save_promotion_manifest(path, original)
    resumed = load_or_create_manifest(path, identity, _expected_task_ids())
    assert resumed == original


def test_load_or_create_rejects_a_different_identity(tmp_path: Path) -> None:
    """load_or_create_manifest rejects an existing manifest with a different identity."""
    path = tmp_path / "promotion_manifest.json"
    identity = _identity()
    original = build_initial_manifest(identity, _expected_task_ids())
    save_promotion_manifest(path, original)
    other_identity = fx.staging_identity(
        fx.candidate_set_manifest(), calibration_run_id="a-different-run"
    )
    with pytest.raises(Exception):  # PromotionManifestIdentityMismatchError
        load_or_create_manifest(path, other_identity, _expected_task_ids())


# ---------------------------------------------------------------------------
# build_staged_entries
# ---------------------------------------------------------------------------


def test_build_staged_entries_matches_task_ids() -> None:
    """build_staged_entries produces one sorted entry per task result."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context, count=5)
    entries = build_staged_entries(results)
    assert [entry.task_id for entry in entries] == sorted(result.task_id for result in results)


def test_preflight_entry_result_requires_known_classification() -> None:
    """PreflightEntryResult rejects an unknown classification string."""
    with pytest.raises(InvalidPromotionManifestError):
        PreflightEntryResult(
            "HumanEval/0", "NOT_A_REAL_CLASSIFICATION", "detail"  # type: ignore[arg-type]
        )


def test_manifest_schema_version_constant_is_stable() -> None:
    """The promotion-manifest schema-version constant has not silently changed."""
    assert H5_PROMOTION_MANIFEST_SCHEMA_VERSION == "megb-03h5-promotion-manifest-v1"


def test_manifest_serializes_to_plain_json(tmp_path: Path) -> None:
    """A saved manifest is plain, committed-output-suitable JSON."""
    manifest = _initial_manifest()
    path = tmp_path / "m.json"
    save_promotion_manifest(path, manifest)
    # Confirm the on-disk file really is plain JSON (not pickled or
    # otherwise opaque) -- required for a "committed output"-suitable
    # artifact family.
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["manifest_schema_version"] == H5_PROMOTION_MANIFEST_SCHEMA_VERSION
