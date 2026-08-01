"""Tests for MEGB-03D's privileged parity-artifact lock (write/verify of the
full parity results kept outside git, anchored by a committed parity.lock.json).

Deliberately mirrors test_reference_partition_lock.py's assertion patterns
(same verification-result shape, same synthetic-fixture test style) rather
than sharing a base with it — see parity_lock.py's module docstring for why.
"""

# pylint: disable=duplicate-code

import dataclasses
import json
from pathlib import Path

import pytest

from src.dataset import load_provenance
from src.reference.parity import ParityOutcome, ParityResult, SideClassification
from src.reference.parity_lock import (
    EnvironmentRecord,
    FrozenArtifactConflictError,
    ParityArtifact,
    finalize_parity_artifact,
    load_parity_lock_file,
    redact_parity_artifact,
    verify_parity_against_lock,
    write_parity_lock_file,
    write_privileged_parity_artifact,
)


def _environment() -> EnvironmentRecord:
    return EnvironmentRecord(
        evalplus_version="0.3.1",
        human_eval_version="1.0.3",
        python_version="3.14.6",
        numpy_version="2.5.1",
        evalplus_internal_apis=("evalplus.eval.untrusted_check",),
        docker_backend_id="docker",
        runner_image_digest="sha256:deadbeef",
    )


def _result(candidate_id: str = "test-1", agree: bool = True) -> ParityResult:
    side = SideClassification(passed=True, sample_size=7, detail="0/7 mismatched")
    outcome = ParityOutcome(base=side, plus=side, outcome="PASS_BASE_PASS_PLUS")
    return ParityResult(
        candidate_id=candidate_id,
        task_id="HumanEval/0",
        category="corrected_canonical_solution",
        candidate_source_sha256="abc123",
        upstream=outcome,
        megb=outcome,
        agree=agree,
        mismatch_detail=None,
    )


def _build_artifact(results: tuple[ParityResult, ...] = (_result(),)) -> ParityArtifact:
    return finalize_parity_artifact("parity-corpus-v1", load_provenance(), results, _environment())


def test_finalize_parity_artifact_is_deterministic_across_rebuilds() -> None:
    """Rebuilding from identical inputs reproduces the identical checksum."""
    artifact_a = _build_artifact()
    artifact_b = _build_artifact()
    assert artifact_a.artifact_checksum == artifact_b.artifact_checksum


def test_write_and_verify_privileged_parity_artifact_passes_cleanly(tmp_path: Path) -> None:
    """A lock built and immediately verified against its own artifact passes cleanly."""
    artifact = _build_artifact()
    lock = write_privileged_parity_artifact(artifact, privileged_dir=tmp_path)

    results = verify_parity_against_lock(lock, artifact)
    assert len(results) == 1
    assert all(r.passed for r in results)
    assert all(r.logical_checksum_match for r in results)
    assert all(r.size_match for r in results)
    assert all(r.on_disk_present for r in results)
    assert all(r.on_disk_checksum_match for r in results)
    assert all(r.on_disk_bytes_match_rebuild for r in results)
    assert all(r.dataset_checksum_match for r in results)


def test_verify_parity_against_lock_detects_checksum_mismatch(tmp_path: Path) -> None:
    """A tampered logical_sha256 in the lock is caught, not silently accepted."""
    artifact = _build_artifact()
    lock = write_privileged_parity_artifact(artifact, privileged_dir=tmp_path)
    tampered_entries = tuple(
        dataclasses.replace(entry, logical_sha256="0" * 64) for entry in lock.entries
    )
    tampered_lock = dataclasses.replace(lock, entries=tampered_entries)

    results = verify_parity_against_lock(tampered_lock, artifact)
    assert not results[0].logical_checksum_match
    assert not results[0].passed


def test_verify_parity_against_lock_detects_environment_version_drift(tmp_path: Path) -> None:
    """A rebuild under a different pinned-dependency version changes the
    artifact checksum, so verification against the old lock fails — this is
    the environment/version-mismatch refusal MEGB-03D requires, achieved
    because EnvironmentRecord is part of the hashed artifact content."""
    artifact = _build_artifact()
    lock = write_privileged_parity_artifact(artifact, privileged_dir=tmp_path)

    drifted_environment = dataclasses.replace(_environment(), evalplus_version="9.9.9")
    drifted_artifact = finalize_parity_artifact(
        "parity-corpus-v1", load_provenance(), (_result(),), drifted_environment
    )

    results = verify_parity_against_lock(lock, drifted_artifact)
    assert not results[0].logical_checksum_match
    assert not results[0].passed


def test_verify_parity_against_lock_detects_source_dataset_mismatch(tmp_path: Path) -> None:
    """A dataset checksum recorded in the lock that no longer matches the
    freshly-built artifact's provenance is flagged, never silently accepted."""
    artifact = _build_artifact()
    lock = write_privileged_parity_artifact(artifact, privileged_dir=tmp_path)
    tampered_entries = tuple(
        dataclasses.replace(entry, dataset_checksum="deadbeef-different-dataset")
        for entry in lock.entries
    )
    tampered_lock = dataclasses.replace(lock, entries=tampered_entries)

    results = verify_parity_against_lock(tampered_lock, artifact)
    assert not results[0].dataset_checksum_match
    assert not results[0].passed


def test_verify_parity_against_lock_regenerates_successfully_when_artifact_missing(
    tmp_path: Path,
) -> None:
    """A missing on-disk privileged file doesn't block verification: deterministic
    regeneration alone is sufficient to confirm content identity."""
    artifact = _build_artifact()
    lock = write_privileged_parity_artifact(artifact, privileged_dir=tmp_path)
    for entry in lock.entries:
        Path(entry.privileged_path).unlink()

    results = verify_parity_against_lock(lock, artifact)
    assert not results[0].on_disk_present
    assert results[0].on_disk_checksum_match is None
    assert results[0].on_disk_bytes_match_rebuild is None
    assert results[0].logical_checksum_match
    assert results[0].size_match
    assert results[0].passed


def test_write_privileged_parity_artifact_refuses_silent_overwrite_of_differing_artifact(
    tmp_path: Path,
) -> None:
    """A second build with different content must not silently clobber the
    first build's frozen artifact unless force=True is passed explicitly."""
    artifact_a = _build_artifact()
    write_privileged_parity_artifact(artifact_a, privileged_dir=tmp_path)

    artifact_b = _build_artifact(results=(_result(candidate_id="test-2"),))
    assert artifact_a.artifact_checksum != artifact_b.artifact_checksum

    with pytest.raises(FrozenArtifactConflictError):
        write_privileged_parity_artifact(artifact_b, privileged_dir=tmp_path)

    lock_b = write_privileged_parity_artifact(artifact_b, privileged_dir=tmp_path, force=True)
    assert lock_b.entries[0].logical_sha256 == artifact_b.artifact_checksum


def test_redact_parity_artifact_never_contains_mismatch_detail_or_per_side_detail() -> None:
    """The committed, public view carries classifications/counts only — never
    the free-text mismatch-detail or per-side detail strings."""
    artifact = _build_artifact()
    redacted = redact_parity_artifact(artifact)
    serialized = json.dumps(redacted, default=str)
    assert "mismatch_detail" not in serialized
    assert "0/7 mismatched" not in serialized
    candidates = redacted["candidates"]
    assert isinstance(candidates, list)
    first_candidate = candidates[0]
    assert isinstance(first_candidate, dict)
    assert first_candidate["agree"] is True
    assert first_candidate["candidate_source_sha256"] == "abc123"


def test_write_privileged_parity_artifact_round_trips_through_lock_file(tmp_path: Path) -> None:
    """A lock written to disk and reloaded verifies identically to the in-memory one."""
    artifact = _build_artifact()
    lock = write_privileged_parity_artifact(artifact, privileged_dir=tmp_path)
    lock_path = tmp_path / "parity.lock.json"
    write_parity_lock_file(lock, lock_path=lock_path)

    loaded = load_parity_lock_file(lock_path=lock_path)
    results = verify_parity_against_lock(loaded, artifact)
    assert all(r.passed for r in results)
