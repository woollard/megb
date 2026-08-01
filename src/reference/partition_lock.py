"""MEGB-03B privileged-artifact lock: keep full manifest bytes out of git.

The two full partition manifests (``primary_experiment_task_manifest.json``
and ``reference_validation_task_manifest.json``) are large and, in later
subtasks, will carry oracle-relevant content — they are never committed.
Instead this module writes them to a gitignored privileged directory and
commits a small ``partition.lock.json`` that anchors their identity via
checksums, size, and generation provenance. A ``verify`` mode regenerates
both manifests from the pinned corpus and confirms they still match the
lock, without ever printing privileged case contents.

This is the default policy for all later MEGB-03 subtasks producing
privileged/oracle artifacts, not just this one (see
``docs/measurement/privileged-artifact-policy.md``).
"""

import dataclasses
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from src.dataset import DatasetProvenance
from src.reference.augmentation import TaskAugmentationResult
from src.reference.partition import (
    BUILD_COMMAND,
    EXPECTED_EXPERIMENT_TASK_COUNT,
    EXPECTED_VALIDATION_TASK_COUNT,
    LOCK_PATH,
    LOCK_SCHEMA_VERSION,
    PARTITION_ALGORITHM_VERSION,
    PARTITION_SEED,
    PRIVILEGED_OUTPUT_DIR,
    CaseWithProvenance,
    PrimaryExperimentManifest,
    ReferenceValidationManifest,
    _checksum_manifest,  # pylint: disable=protected-access
    build_primary_experiment_manifest,
    build_reference_validation_manifest,
)


class FrozenArtifactConflictError(ValueError):
    """Raised when a differing privileged artifact already exists and force wasn't requested."""


class ManifestKindMismatchError(ValueError):
    """Raised when a file's manifest_kind doesn't match the expected artifact ID.

    Guards specifically against verifying a redacted view as if it were the
    privileged manifest.
    """


@dataclass(frozen=True)
class LockEntry:
    """One privileged artifact's identity anchor: everything needed to detect
    tampering, drift, or accidental substitution without storing its bytes."""

    artifact_id: str
    privileged_path: str
    schema_version: str
    algorithm_version: str
    dataset_checksum: str
    augmentation_checksums: Mapping[str, str]
    partition_seed: str
    expected_task_count: int
    expected_case_summary: Mapping[str, object]
    size_bytes: int
    logical_sha256: str
    generation_command: str
    generating_code_revision: str
    generating_code_dirty: bool
    trusted_consumers: tuple[str, ...]


@dataclass(frozen=True)
class LockFile:
    """The complete, committed lock covering every privileged partition artifact."""

    lock_schema_version: str
    generated_at: str
    entries: tuple[LockEntry, ...]


@dataclass(frozen=True)
class ArtifactVerificationResult:
    """Per-artifact verification outcome. Never carries case contents, only booleans/checksums."""

    artifact_id: str
    logical_checksum_match: bool
    size_match: bool
    on_disk_present: bool
    on_disk_checksum_match: bool | None
    on_disk_bytes_match_rebuild: bool | None
    dataset_checksum_match: bool
    augmentation_checksum_match: bool
    passed: bool


def _serialize_manifest(payload: Mapping[str, object]) -> bytes:
    """Canonical byte serialization used for both writing and hashing manifests.

    Using one shared function for both purposes guarantees the recorded
    size_bytes in the lock always matches what actually gets written to disk.
    """
    return (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def _stabilized_manifest_payload(
    manifest: PrimaryExperimentManifest | ReferenceValidationManifest,
) -> dict[str, object]:
    """Wall-clock-free dict form of a manifest, used for privileged-artifact bytes.

    ``generated_at`` and the nested ``dataset_provenance.loaded_at`` are
    fresh timestamps on every build (see ``_stable_dataset_provenance`` in
    ``partition.py``); left unstripped, the on-disk privileged file would
    differ on every rebuild even with byte-identical corpus/code — the same
    determinism bug already found twice in this project. Stripping them here
    makes the privileged file itself, and its recorded size, reproducible.
    """
    payload = dict(dataclasses.asdict(manifest))
    payload["generated_at"] = ""
    dataset_provenance_dict = payload.get("dataset_provenance")
    if isinstance(dataset_provenance_dict, dict):
        dataset_provenance_dict = dict(dataset_provenance_dict)
        dataset_provenance_dict["loaded_at"] = ""
        payload["dataset_provenance"] = dataset_provenance_dict
    return payload


def _logical_checksum_from_payload(payload: Mapping[str, object]) -> str:
    """Recompute a manifest's content-only checksum from a (e.g. on-disk) payload dict.

    Mirrors the stripping applied when ``manifest_checksum`` was first
    computed in ``build_primary_experiment_manifest`` /
    ``build_reference_validation_manifest``: the checksum field itself,
    ``generated_at``, and the nested ``dataset_provenance.loaded_at`` are
    excluded from what gets hashed. Lets on-disk content be checked against
    the lock without needing to rebuild the manifest from the corpus.
    """
    stripped = dict(payload)
    stripped["manifest_checksum"] = ""
    stripped["generated_at"] = ""
    dataset_provenance_dict = stripped.get("dataset_provenance")
    if isinstance(dataset_provenance_dict, dict):
        dataset_provenance_dict = dict(dataset_provenance_dict)
        dataset_provenance_dict["loaded_at"] = ""
        stripped["dataset_provenance"] = dataset_provenance_dict
    return _checksum_manifest(stripped)


def _git_head_sha() -> tuple[str, bool]:
    """Return (HEAD commit SHA, whether the working tree has uncommitted changes).

    Best-effort: returns ("unknown", True) if git is unavailable, never raises.
    """
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
        return sha, bool(status.strip())
    except Exception:  # pylint: disable=broad-exception-caught
        return "unknown", True


def _build_lock_entry(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    artifact_id: str,
    privileged_path: Path,
    manifest_bytes: bytes,
    logical_checksum: str,
    dataset_provenance: DatasetProvenance,
    augmentation_results: Mapping[str, TaskAugmentationResult],
    expected_task_count: int,
    expected_case_summary: Mapping[str, object],
    trusted_consumers: tuple[str, ...],
    code_sha: str,
    code_dirty: bool,
) -> LockEntry:
    return LockEntry(
        artifact_id=artifact_id,
        privileged_path=str(privileged_path),
        schema_version=LOCK_SCHEMA_VERSION,
        algorithm_version=PARTITION_ALGORITHM_VERSION,
        dataset_checksum=dataset_provenance.evalplus_dataset_hash,
        augmentation_checksums={
            task_id: result.combined_checksum
            for task_id, result in sorted(augmentation_results.items())
        },
        partition_seed=PARTITION_SEED,
        expected_task_count=expected_task_count,
        expected_case_summary=expected_case_summary,
        size_bytes=len(manifest_bytes),
        logical_sha256=logical_checksum,
        generation_command=BUILD_COMMAND,
        generating_code_revision=code_sha,
        generating_code_dirty=code_dirty,
        trusted_consumers=trusted_consumers,
    )


# pylint: disable-next=too-many-locals,too-many-arguments,too-many-positional-arguments
def write_privileged_artifacts(
    experiment_manifest: PrimaryExperimentManifest,
    validation_manifest: ReferenceValidationManifest,
    augmentation_results: Mapping[str, TaskAugmentationResult],
    dataset_provenance: DatasetProvenance,
    privileged_dir: Path = PRIVILEGED_OUTPUT_DIR,
    force: bool = False,
) -> LockFile:
    """Write both full manifests to the privileged directory and build the lock file.

    Refuses to silently overwrite an existing, differing privileged file
    unless force=True: the caller must explicitly acknowledge replacing
    already-frozen evidence.
    """
    privileged_dir.mkdir(parents=True, exist_ok=True)

    experiment_bytes = _serialize_manifest(_stabilized_manifest_payload(experiment_manifest))
    validation_bytes = _serialize_manifest(_stabilized_manifest_payload(validation_manifest))

    experiment_path = privileged_dir / "primary_experiment_task_manifest.json"
    validation_path = privileged_dir / "reference_validation_task_manifest.json"

    for path, new_bytes in (
        (experiment_path, experiment_bytes),
        (validation_path, validation_bytes),
    ):
        if path.exists() and not force:
            existing_bytes = path.read_bytes()
            if existing_bytes != new_bytes:
                raise FrozenArtifactConflictError(
                    f"{path} already exists and differs from the freshly built "
                    "artifact; refusing to overwrite silently. Pass force=True "
                    "to replace it deliberately (this destroys the previous "
                    "frozen evidence)."
                )
            continue
        path.write_bytes(new_bytes)

    code_sha, code_dirty = _git_head_sha()

    entries = (
        _build_lock_entry(
            artifact_id="primary_experiment_task_manifest",
            privileged_path=experiment_path,
            manifest_bytes=experiment_bytes,
            logical_checksum=experiment_manifest.manifest_checksum,
            dataset_provenance=dataset_provenance,
            augmentation_results=augmentation_results,
            expected_task_count=EXPECTED_EXPERIMENT_TASK_COUNT,
            expected_case_summary={
                "development_cases_per_task": experiment_manifest.development_target,
                "min_reference_only_cases_per_task": experiment_manifest.min_reference_only,
            },
            trusted_consumers=("MEGB-03C",),
            code_sha=code_sha,
            code_dirty=code_dirty,
        ),
        _build_lock_entry(
            artifact_id="reference_validation_task_manifest",
            privileged_path=validation_path,
            manifest_bytes=validation_bytes,
            logical_checksum=validation_manifest.manifest_checksum,
            dataset_provenance=dataset_provenance,
            augmentation_results=augmentation_results,
            expected_task_count=EXPECTED_VALIDATION_TASK_COUNT,
            expected_case_summary={
                "total_case_count": sum(len(t.case_ids) for t in validation_manifest.tasks),
            },
            trusted_consumers=("MEGB-03C", "MEGB-03D", "MEGB-03H"),
            code_sha=code_sha,
            code_dirty=code_dirty,
        ),
    )

    return LockFile(
        lock_schema_version=LOCK_SCHEMA_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        entries=entries,
    )


def write_lock_file(lock: LockFile, lock_path: Path = LOCK_PATH) -> None:
    """Persist the lock file (committed; never gitignored)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(dataclasses.asdict(lock), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_lock_file(lock_path: Path = LOCK_PATH) -> LockFile:
    """Load a previously written lock file for verification."""
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    entries = tuple(LockEntry(**entry) for entry in data["entries"])
    return LockFile(
        lock_schema_version=data["lock_schema_version"],
        generated_at=data["generated_at"],
        entries=entries,
    )


# pylint: disable-next=too-many-locals
def verify_against_lock(
    lock: LockFile,
    cases_by_task: Mapping[str, Sequence[CaseWithProvenance]],
    dataset_provenance: DatasetProvenance,
    augmentation_results: Mapping[str, TaskAugmentationResult],
) -> tuple[ArtifactVerificationResult, ...]:
    """Regenerate both manifests and compare against the lock.

    Read-only: never writes anything and never prints/returns privileged
    case contents, only checksums, sizes, and pass/fail booleans. Raises
    ManifestKindMismatchError if an on-disk file's manifest_kind doesn't
    match what's expected at that path (e.g. a redacted view sitting where
    the privileged manifest should be).
    """
    fresh_by_id: dict[str, PrimaryExperimentManifest | ReferenceValidationManifest] = {
        "primary_experiment_task_manifest": build_primary_experiment_manifest(
            cases_by_task, dataset_provenance
        ),
        "reference_validation_task_manifest": build_reference_validation_manifest(
            cases_by_task, dataset_provenance
        ),
    }
    fresh_augmentation_checksums = {
        task_id: result.combined_checksum for task_id, result in augmentation_results.items()
    }

    results = []
    for entry in lock.entries:
        fresh_manifest = fresh_by_id[entry.artifact_id]
        fresh_bytes = _serialize_manifest(_stabilized_manifest_payload(fresh_manifest))
        fresh_logical = fresh_manifest.manifest_checksum

        logical_match = fresh_logical == entry.logical_sha256
        size_match = len(fresh_bytes) == entry.size_bytes
        dataset_match = dataset_provenance.evalplus_dataset_hash == entry.dataset_checksum
        augmentation_match = fresh_augmentation_checksums == dict(entry.augmentation_checksums)

        privileged_path = Path(entry.privileged_path)
        on_disk_present = privileged_path.exists()
        on_disk_checksum_match: bool | None = None
        on_disk_bytes_match_rebuild: bool | None = None
        if on_disk_present:
            on_disk_payload = json.loads(privileged_path.read_text(encoding="utf-8"))
            actual_kind = on_disk_payload.get("manifest_kind")
            if actual_kind != entry.artifact_id:
                raise ManifestKindMismatchError(
                    f"{privileged_path}: manifest_kind={actual_kind!r} does not "
                    f"match expected artifact_id={entry.artifact_id!r} — refusing "
                    "to verify (e.g. a redacted view must never be treated as "
                    "the privileged manifest)"
                )
            on_disk_checksum_match = (
                _logical_checksum_from_payload(on_disk_payload) == entry.logical_sha256
            )
            on_disk_bytes_match_rebuild = privileged_path.read_bytes() == fresh_bytes

        passed = (
            logical_match
            and size_match
            and dataset_match
            and augmentation_match
            and on_disk_checksum_match is not False
            and on_disk_bytes_match_rebuild is not False
        )
        results.append(
            ArtifactVerificationResult(
                artifact_id=entry.artifact_id,
                logical_checksum_match=logical_match,
                size_match=size_match,
                on_disk_present=on_disk_present,
                on_disk_checksum_match=on_disk_checksum_match,
                on_disk_bytes_match_rebuild=on_disk_bytes_match_rebuild,
                dataset_checksum_match=dataset_match,
                augmentation_checksum_match=augmentation_match,
                passed=passed,
            )
        )
    return tuple(results)
