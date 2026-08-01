"""Tests for MEGB-03B's privileged-artifact lock (write/verify of the two full
manifests kept outside git, anchored by a committed partition.lock.json)."""

# This test intentionally reconstructs production lock/provenance fields
# independently to verify the serialized contract. Sharing the production
# implementation would weaken the test by allowing implementation and
# verification to fail identically.
# pylint: disable=duplicate-code

import dataclasses
import json
from pathlib import Path

import pytest

from src.dataset import DatasetProvenance, load_provenance
from src.reference.augmentation import TaskAugmentationResult
from src.reference.partition import (
    CaseWithProvenance,
    PrimaryExperimentManifest,
    ReferenceValidationManifest,
    build_primary_experiment_manifest,
    build_reference_validation_manifest,
)
from src.reference.partition_lock import (
    FrozenArtifactConflictError,
    ManifestKindMismatchError,
    verify_against_lock,
    write_privileged_artifacts,
)


def _cases(count: int, provenance: str = "evalplus-original-v1") -> list[CaseWithProvenance]:
    return [CaseWithProvenance(case_id=f"case-{i}", provenance=provenance) for i in range(count)]


def _small_cases_by_task() -> dict[str, list[CaseWithProvenance]]:
    return {"T/0": _cases(100), "T/1": _cases(100)}


def _build_manifests(
    cases_by_task: dict[str, list[CaseWithProvenance]], provenance: DatasetProvenance
) -> tuple[PrimaryExperimentManifest, ReferenceValidationManifest]:
    experiment_manifest = build_primary_experiment_manifest(
        cases_by_task, provenance, excluded_task_id="none"
    )
    validation_manifest = build_reference_validation_manifest(cases_by_task, provenance)
    return experiment_manifest, validation_manifest


def test_verify_against_lock_passes_for_freshly_written_artifacts(tmp_path: Path) -> None:
    """A lock built and immediately verified against its own artifacts passes cleanly."""
    cases_by_task = _small_cases_by_task()
    provenance = load_provenance()
    augmentation_results: dict[str, TaskAugmentationResult] = {}
    experiment_manifest, validation_manifest = _build_manifests(cases_by_task, provenance)

    lock = write_privileged_artifacts(
        experiment_manifest,
        validation_manifest,
        augmentation_results,
        provenance,
        privileged_dir=tmp_path / "privileged",
    )

    results = verify_against_lock(lock, cases_by_task, provenance, augmentation_results)
    assert len(results) == 2
    assert all(r.passed for r in results)
    assert all(r.logical_checksum_match for r in results)
    assert all(r.size_match for r in results)
    assert all(r.on_disk_present for r in results)
    assert all(r.on_disk_checksum_match for r in results)
    assert all(r.on_disk_bytes_match_rebuild for r in results)
    assert all(r.dataset_checksum_match for r in results)
    assert all(r.augmentation_checksum_match for r in results)


def test_verify_against_lock_detects_checksum_mismatch(tmp_path: Path) -> None:
    """A tampered logical_sha256 in the lock is caught, not silently accepted."""
    cases_by_task = _small_cases_by_task()
    provenance = load_provenance()
    augmentation_results: dict[str, TaskAugmentationResult] = {}
    experiment_manifest, validation_manifest = _build_manifests(cases_by_task, provenance)

    lock = write_privileged_artifacts(
        experiment_manifest,
        validation_manifest,
        augmentation_results,
        provenance,
        privileged_dir=tmp_path / "privileged",
    )
    tampered_entries = tuple(
        dataclasses.replace(entry, logical_sha256="0" * 64) if i == 0 else entry
        for i, entry in enumerate(lock.entries)
    )
    tampered_lock = dataclasses.replace(lock, entries=tampered_entries)

    results = verify_against_lock(tampered_lock, cases_by_task, provenance, augmentation_results)
    tampered_result = next(r for r in results if r.artifact_id == tampered_entries[0].artifact_id)
    assert not tampered_result.logical_checksum_match
    assert not tampered_result.passed


def test_verify_against_lock_detects_byte_size_mismatch(tmp_path: Path) -> None:
    """A tampered size_bytes in the lock is caught, not silently accepted."""
    cases_by_task = _small_cases_by_task()
    provenance = load_provenance()
    augmentation_results: dict[str, TaskAugmentationResult] = {}
    experiment_manifest, validation_manifest = _build_manifests(cases_by_task, provenance)

    lock = write_privileged_artifacts(
        experiment_manifest,
        validation_manifest,
        augmentation_results,
        provenance,
        privileged_dir=tmp_path / "privileged",
    )
    tampered_entries = tuple(
        dataclasses.replace(entry, size_bytes=entry.size_bytes + 1) if i == 0 else entry
        for i, entry in enumerate(lock.entries)
    )
    tampered_lock = dataclasses.replace(lock, entries=tampered_entries)

    results = verify_against_lock(tampered_lock, cases_by_task, provenance, augmentation_results)
    tampered_result = next(r for r in results if r.artifact_id == tampered_entries[0].artifact_id)
    assert not tampered_result.size_match
    assert not tampered_result.passed


def test_verify_against_lock_detects_source_dataset_mismatch(tmp_path: Path) -> None:
    """A dataset checksum recorded in the lock that no longer matches the loaded
    corpus's provenance is flagged, never silently treated as still valid."""
    cases_by_task = _small_cases_by_task()
    provenance = load_provenance()
    augmentation_results: dict[str, TaskAugmentationResult] = {}
    experiment_manifest, validation_manifest = _build_manifests(cases_by_task, provenance)

    lock = write_privileged_artifacts(
        experiment_manifest,
        validation_manifest,
        augmentation_results,
        provenance,
        privileged_dir=tmp_path / "privileged",
    )

    drifted_provenance = dataclasses.replace(
        provenance, evalplus_dataset_hash="deadbeef-different-dataset"
    )
    results = verify_against_lock(
        lock, cases_by_task, drifted_provenance, augmentation_results
    )
    assert all(not r.dataset_checksum_match for r in results)
    assert all(not r.passed for r in results)


def test_verify_against_lock_detects_augmentation_mismatch(tmp_path: Path) -> None:
    """Augmentation results that differ from what the lock recorded are flagged."""
    cases_by_task = _small_cases_by_task()
    provenance = load_provenance()
    experiment_manifest, validation_manifest = _build_manifests(cases_by_task, provenance)

    # Lock recorded with no augmentation results (the "frozen" state).
    lock = write_privileged_artifacts(
        experiment_manifest,
        validation_manifest,
        {},
        provenance,
        privileged_dir=tmp_path / "privileged",
    )

    # Verification run against a world where an augmented task's checksum
    # now differs from what was frozen.

    drifted_augmentation_results = {
        "HumanEval/6": TaskAugmentationResult(
            task_id="HumanEval/6",
            algorithm_version="supplementary-generation-v1",
            raw_candidate_count=0,
            duplicate_of_existing_count=0,
            contract_rejected=(),
            infeasible=(),
            accepted=(),
            original_case_ids=(),
            original_checksum="orig",
            supplementary_checksum="supp",
            combined_checksum="drifted-checksum",
            combined_unique_count=0,
            feasibility_check_total_sec=0.0,
            feasibility_check_max_single_sec=0.0,
        )
    }

    results = verify_against_lock(
        lock, cases_by_task, provenance, drifted_augmentation_results
    )
    assert all(not r.augmentation_checksum_match for r in results)
    assert all(not r.passed for r in results)


def test_verify_against_lock_regenerates_successfully_when_artifact_missing(
    tmp_path: Path,
) -> None:
    """A missing on-disk privileged file doesn't block verification: deterministic
    regeneration from the corpus alone is sufficient to confirm content identity."""
    cases_by_task = _small_cases_by_task()
    provenance = load_provenance()
    augmentation_results: dict[str, TaskAugmentationResult] = {}
    experiment_manifest, validation_manifest = _build_manifests(cases_by_task, provenance)

    privileged_dir = tmp_path / "privileged"
    lock = write_privileged_artifacts(
        experiment_manifest,
        validation_manifest,
        augmentation_results,
        provenance,
        privileged_dir=privileged_dir,
    )

    for entry in lock.entries:
        Path(entry.privileged_path).unlink()

    results = verify_against_lock(lock, cases_by_task, provenance, augmentation_results)
    assert all(not r.on_disk_present for r in results)
    assert all(r.on_disk_checksum_match is None for r in results)
    assert all(r.on_disk_bytes_match_rebuild is None for r in results)
    assert all(r.logical_checksum_match for r in results)
    assert all(r.size_match for r in results)
    assert all(r.passed for r in results)


def test_verify_against_lock_refuses_redacted_view_as_privileged_manifest(
    tmp_path: Path,
) -> None:
    """If a redacted view ends up at the privileged path, verification must
    refuse to treat it as the privileged manifest rather than silently comparing."""
    cases_by_task = _small_cases_by_task()
    provenance = load_provenance()
    augmentation_results: dict[str, TaskAugmentationResult] = {}
    experiment_manifest, validation_manifest = _build_manifests(cases_by_task, provenance)

    lock = write_privileged_artifacts(
        experiment_manifest,
        validation_manifest,
        augmentation_results,
        provenance,
        privileged_dir=tmp_path / "privileged",
    )

    experiment_entry = next(
        e for e in lock.entries if e.artifact_id == "primary_experiment_task_manifest"
    )
    redacted_payload = {
        "manifest_kind": "primary_experiment_task_manifest_redacted",
        "tasks": [],
    }
    Path(experiment_entry.privileged_path).write_text(
        json.dumps(redacted_payload), encoding="utf-8"
    )

    with pytest.raises(ManifestKindMismatchError):
        verify_against_lock(lock, cases_by_task, provenance, augmentation_results)


def test_write_privileged_artifacts_refuses_silent_overwrite_of_differing_artifact(
    tmp_path: Path,
) -> None:
    """A second build with different content must not silently clobber the
    first build's frozen artifact unless force=True is passed explicitly."""
    provenance = load_provenance()
    privileged_dir = tmp_path / "privileged"

    cases_a = {"T/0": _cases(100), "T/1": _cases(100)}
    experiment_a, validation_a = _build_manifests(cases_a, provenance)
    write_privileged_artifacts(
        experiment_a, validation_a, {}, provenance, privileged_dir=privileged_dir
    )

    cases_b = {"T/0": _cases(100, provenance="other-provenance"), "T/1": _cases(100)}
    experiment_b, validation_b = _build_manifests(cases_b, provenance)

    with pytest.raises(FrozenArtifactConflictError):
        write_privileged_artifacts(
            experiment_b, validation_b, {}, provenance, privileged_dir=privileged_dir
        )

    # force=True explicitly authorizes replacing the previously frozen evidence.
    lock_b = write_privileged_artifacts(
        experiment_b, validation_b, {}, provenance, privileged_dir=privileged_dir, force=True
    )
    assert lock_b.entries[0].logical_sha256 == experiment_b.manifest_checksum
