"""Tests for MEGB-03C's privileged oracle-artifact lock (write/verify of the
three physically separated oracle artifacts kept outside git, anchored by a
committed oracle.lock.json).

Deliberately mirrors test_reference_partition_lock.py's assertion patterns
(same verification-result shape, same synthetic-corpus test style) rather
than sharing a base with it — see oracle_lock.py's module docstring for why.
"""

# pylint: disable=duplicate-code

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from src.dataset import DatasetProvenance, PrivilegedTaskView, load_provenance
from src.reference.augmentation import PROVENANCE_ORIGINAL, TaskAugmentationResult
from src.reference.oracle import (
    DEVELOPMENT_ORACLE_ARTIFACT_ID,
    REFERENCE_ONLY_ORACLE_ARTIFACT_ID,
    REFERENCE_VALIDATION_ONLY_ORACLE_ARTIFACT_ID,
    OracleBuildResult,
    build_oracle_artifacts,
)
from src.reference.oracle_lock import (
    FrozenArtifactConflictError,
    ManifestKindMismatchError,
    verify_oracle_against_lock,
    write_privileged_oracle_artifacts,
)
from src.reference.partition import (
    EXCLUDED_TASK_ID,
    CaseWithProvenance,
    build_primary_experiment_manifest,
    build_reference_validation_manifest,
)
from src.reference.case_serialization import stable_case_id


def _synthetic_task(task_id: str, count: int) -> PrivilegedTaskView:
    """A trivial task whose canonical solution just doubles its integer input."""
    return PrivilegedTaskView(
        task_id=task_id,
        entry_point=task_id.replace("/", "_"),
        canonical_solution="    return n * 2\n",
        original_test="",
        contract="",
        atol=0.0,
        base_input=tuple((n,) for n in range(count)),
        plus_input=(),
    )


# pylint: disable-next=too-many-locals
def _build_result_and_inputs() -> tuple[
    OracleBuildResult,
    dict[str, TaskAugmentationResult],
    dict[str, PrivilegedTaskView],
    DatasetProvenance,
]:
    """Two experimental tasks (>=70 cases each) plus a HumanEval/39-style
    validation-only task, built into a full OracleBuildResult."""
    task_a = _synthetic_task("T/A", 100)
    task_b = _synthetic_task("T/B", 100)
    task_val = _synthetic_task(EXCLUDED_TASK_ID, 12)

    privileged_by_id = {"T/A": task_a, "T/B": task_b, EXCLUDED_TASK_ID: task_val}
    public_by_id = {tid: f"def {t.entry_point}(n):\n" for tid, t in privileged_by_id.items()}

    cases_by_task: dict[str, list[CaseWithProvenance]] = {}
    args_by_task: dict[str, dict[str, tuple[Any, ...]]] = {}
    for task_id, task in privileged_by_id.items():
        cases = []
        args_by_id: dict[str, tuple[Any, ...]] = {}
        for args in task.base_input:
            cid = stable_case_id(task_id, args)
            cases.append(CaseWithProvenance(case_id=cid, provenance=PROVENANCE_ORIGINAL))
            args_by_id[cid] = args
        cases_by_task[task_id] = cases
        args_by_task[task_id] = args_by_id

    provenance = load_provenance()
    experiment_manifest = build_primary_experiment_manifest(cases_by_task, provenance)
    validation_manifest = build_reference_validation_manifest(cases_by_task, provenance)
    build_result = build_oracle_artifacts(
        experiment_manifest,
        validation_manifest,
        cases_by_task,
        args_by_task,
        privileged_by_id,
        public_by_id,
        provenance,
    )
    return build_result, {}, privileged_by_id, provenance


def test_verify_oracle_against_lock_passes_for_freshly_written_artifacts(tmp_path: Path) -> None:
    """A lock built and immediately verified against its own artifacts passes cleanly."""
    build_result, augmentation_results, privileged_by_id, provenance = _build_result_and_inputs()
    lock = write_privileged_oracle_artifacts(
        build_result, augmentation_results, privileged_by_id, privileged_dir=tmp_path
    )

    results = verify_oracle_against_lock(lock, build_result, augmentation_results, privileged_by_id)
    assert len(results) == 3
    assert all(r.passed for r in results)
    assert all(r.logical_checksum_match for r in results)
    assert all(r.size_match for r in results)
    assert all(r.on_disk_present for r in results)
    assert all(r.on_disk_checksum_match for r in results)
    assert all(r.on_disk_bytes_match_rebuild for r in results)
    assert all(r.dataset_checksum_match for r in results)
    assert all(r.augmentation_checksum_match for r in results)
    assert all(r.canonical_solution_hashes_match for r in results)
    assert provenance.expected_task_count == 164  # sanity: real provenance loaded correctly


def test_verify_oracle_against_lock_detects_checksum_mismatch(tmp_path: Path) -> None:
    """A tampered logical_sha256 in the lock is caught, not silently accepted."""
    build_result, augmentation_results, privileged_by_id, _ = _build_result_and_inputs()
    lock = write_privileged_oracle_artifacts(
        build_result, augmentation_results, privileged_by_id, privileged_dir=tmp_path
    )
    tampered_entries = tuple(
        dataclasses.replace(entry, logical_sha256="0" * 64) if i == 0 else entry
        for i, entry in enumerate(lock.entries)
    )
    tampered_lock = dataclasses.replace(lock, entries=tampered_entries)

    results = verify_oracle_against_lock(
        tampered_lock, build_result, augmentation_results, privileged_by_id
    )
    tampered_result = next(r for r in results if r.artifact_id == tampered_entries[0].artifact_id)
    assert not tampered_result.logical_checksum_match
    assert not tampered_result.passed


def test_verify_oracle_against_lock_detects_byte_size_mismatch(tmp_path: Path) -> None:
    """A tampered size_bytes in the lock is caught, not silently accepted."""
    build_result, augmentation_results, privileged_by_id, _ = _build_result_and_inputs()
    lock = write_privileged_oracle_artifacts(
        build_result, augmentation_results, privileged_by_id, privileged_dir=tmp_path
    )
    tampered_entries = tuple(
        dataclasses.replace(entry, size_bytes=entry.size_bytes + 1) if i == 0 else entry
        for i, entry in enumerate(lock.entries)
    )
    tampered_lock = dataclasses.replace(lock, entries=tampered_entries)

    results = verify_oracle_against_lock(
        tampered_lock, build_result, augmentation_results, privileged_by_id
    )
    tampered_result = next(r for r in results if r.artifact_id == tampered_entries[0].artifact_id)
    assert not tampered_result.size_match
    assert not tampered_result.passed


def test_verify_oracle_against_lock_detects_source_dataset_mismatch(tmp_path: Path) -> None:
    """A dataset checksum recorded in the lock that no longer matches the
    freshly-built artifact's provenance is flagged, never silently accepted."""
    build_result, augmentation_results, privileged_by_id, _ = _build_result_and_inputs()
    lock = write_privileged_oracle_artifacts(
        build_result, augmentation_results, privileged_by_id, privileged_dir=tmp_path
    )
    tampered_entries = tuple(
        dataclasses.replace(entry, dataset_checksum="deadbeef-different-dataset")
        for entry in lock.entries
    )
    tampered_lock = dataclasses.replace(lock, entries=tampered_entries)

    results = verify_oracle_against_lock(
        tampered_lock, build_result, augmentation_results, privileged_by_id
    )
    assert all(not r.dataset_checksum_match for r in results)
    assert all(not r.passed for r in results)


def test_verify_oracle_against_lock_detects_canonical_solution_hash_mismatch(
    tmp_path: Path,
) -> None:
    """A canonical-solution hash recorded in the lock that no longer matches
    the current corpus's canonical solutions is flagged."""
    build_result, augmentation_results, privileged_by_id, _ = _build_result_and_inputs()
    lock = write_privileged_oracle_artifacts(
        build_result, augmentation_results, privileged_by_id, privileged_dir=tmp_path
    )
    tampered_entries = tuple(
        dataclasses.replace(
            entry,
            canonical_solution_hashes={
                task_id: "0" * 64 for task_id in entry.canonical_solution_hashes
            },
        )
        for entry in lock.entries
    )
    tampered_lock = dataclasses.replace(lock, entries=tampered_entries)

    results = verify_oracle_against_lock(
        tampered_lock, build_result, augmentation_results, privileged_by_id
    )
    assert all(not r.canonical_solution_hashes_match for r in results)
    assert all(not r.passed for r in results)


def test_verify_oracle_against_lock_regenerates_successfully_when_artifact_missing(
    tmp_path: Path,
) -> None:
    """A missing on-disk privileged file doesn't block verification: deterministic
    regeneration from the corpus alone is sufficient to confirm content identity."""
    build_result, augmentation_results, privileged_by_id, _ = _build_result_and_inputs()
    lock = write_privileged_oracle_artifacts(
        build_result, augmentation_results, privileged_by_id, privileged_dir=tmp_path
    )
    for entry in lock.entries:
        Path(entry.privileged_path).unlink()

    results = verify_oracle_against_lock(lock, build_result, augmentation_results, privileged_by_id)
    assert all(not r.on_disk_present for r in results)
    assert all(r.on_disk_checksum_match is None for r in results)
    assert all(r.on_disk_bytes_match_rebuild is None for r in results)
    assert all(r.logical_checksum_match for r in results)
    assert all(r.size_match for r in results)
    assert all(r.passed for r in results)


def test_verify_oracle_against_lock_refuses_wrong_kind_file_at_privileged_path(
    tmp_path: Path,
) -> None:
    """If a differently-scoped oracle file ends up at another artifact's
    privileged path, verification must refuse to treat it as that artifact."""
    build_result, augmentation_results, privileged_by_id, _ = _build_result_and_inputs()
    lock = write_privileged_oracle_artifacts(
        build_result, augmentation_results, privileged_by_id, privileged_dir=tmp_path
    )

    dev_entry = next(
        e for e in lock.entries if e.artifact_id == DEVELOPMENT_ORACLE_ARTIFACT_ID
    )
    wrong_kind_payload = {"artifact_kind": REFERENCE_ONLY_ORACLE_ARTIFACT_ID, "records": []}
    Path(dev_entry.privileged_path).write_text(json.dumps(wrong_kind_payload), encoding="utf-8")

    with pytest.raises(ManifestKindMismatchError):
        verify_oracle_against_lock(lock, build_result, augmentation_results, privileged_by_id)


# pylint: disable-next=too-many-locals
def test_write_privileged_oracle_artifacts_refuses_silent_overwrite_of_differing_artifact(
    tmp_path: Path,
) -> None:
    """A second build with different content must not silently clobber the
    first build's frozen artifact unless force=True is passed explicitly."""
    build_result_a, augmentation_results, privileged_by_id, _ = _build_result_and_inputs()
    write_privileged_oracle_artifacts(
        build_result_a, augmentation_results, privileged_by_id, privileged_dir=tmp_path
    )

    # A different corpus (different canonical solution) produces genuinely
    # different oracle content at the same privileged paths.
    privileged_by_id_b = dict(privileged_by_id)
    privileged_by_id_b["T/A"] = dataclasses.replace(
        privileged_by_id["T/A"], canonical_solution="    return n * 3\n"
    )
    task_a = privileged_by_id_b["T/A"]
    public_by_id = {tid: f"def {t.entry_point}(n):\n" for tid, t in privileged_by_id_b.items()}
    cases_by_task: dict[str, list[CaseWithProvenance]] = {}
    args_by_task: dict[str, dict[str, tuple[Any, ...]]] = {}
    for task_id, task in privileged_by_id_b.items():
        cases = []
        args_by_id: dict[str, tuple[Any, ...]] = {}
        for args in task.base_input:
            cid = stable_case_id(task_id, args)
            cases.append(CaseWithProvenance(case_id=cid, provenance=PROVENANCE_ORIGINAL))
            args_by_id[cid] = args
        cases_by_task[task_id] = cases
        args_by_task[task_id] = args_by_id

    provenance = load_provenance()
    experiment_manifest = build_primary_experiment_manifest(cases_by_task, provenance)
    validation_manifest = build_reference_validation_manifest(cases_by_task, provenance)
    build_result_b = build_oracle_artifacts(
        experiment_manifest,
        validation_manifest,
        cases_by_task,
        args_by_task,
        privileged_by_id_b,
        public_by_id,
        provenance,
    )
    assert task_a.canonical_solution != privileged_by_id["T/A"].canonical_solution

    with pytest.raises(FrozenArtifactConflictError):
        write_privileged_oracle_artifacts(
            build_result_b, augmentation_results, privileged_by_id_b, privileged_dir=tmp_path
        )

    lock_b = write_privileged_oracle_artifacts(
        build_result_b,
        augmentation_results,
        privileged_by_id_b,
        privileged_dir=tmp_path,
        force=True,
    )
    assert lock_b.entries[0].logical_sha256 == build_result_b.development_oracle.artifact_checksum


def test_write_privileged_oracle_artifacts_authorized_consumers_are_disjoint(
    tmp_path: Path,
) -> None:
    """Each artifact's trusted_consumers matches its authorized MEGB-03C
    boundary; candidate/candidate-generation runtimes appear in none of them."""
    build_result, augmentation_results, privileged_by_id, _ = _build_result_and_inputs()
    lock = write_privileged_oracle_artifacts(
        build_result, augmentation_results, privileged_by_id, privileged_dir=tmp_path
    )
    consumers_by_artifact = {e.artifact_id: set(e.trusted_consumers) for e in lock.entries}

    assert consumers_by_artifact[DEVELOPMENT_ORACLE_ARTIFACT_ID] == {"MEGB-04-trusted-side"}
    assert consumers_by_artifact[REFERENCE_ONLY_ORACLE_ARTIFACT_ID] == {"S*"}
    assert consumers_by_artifact[REFERENCE_VALIDATION_ONLY_ORACLE_ARTIFACT_ID] == {"MEGB-03D"}

    # No consumer set overlaps another — each artifact is exclusively scoped.
    all_sets = list(consumers_by_artifact.values())
    for i, set_a in enumerate(all_sets):
        for set_b in all_sets[i + 1 :]:
            assert not set_a & set_b
