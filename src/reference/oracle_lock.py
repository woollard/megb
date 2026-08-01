"""MEGB-03C privileged-artifact lock: keep full oracle bytes out of git.

Establishes the default policy stated in
``docs/measurement/privileged-artifact-policy.md`` for MEGB-03C and all
later MEGB-03 subtasks producing privileged/oracle artifacts: expected-output
bytes never reach git. Instead, this module writes the three physically
separated oracle artifacts (development / reference-only /
reference-validation-only) to a gitignored privileged directory and commits
a small ``oracle.lock.json`` that anchors their identity — mirroring
``src.reference.partition_lock`` exactly, extended with the oracle-specific
identity fields MEGB-03C's execution amendment requires (canonical-solution
hashes, comparison-profile version, authorized consumer).

Deliberately duplicates (rather than shares a base with) `partition_lock`'s
write/verify/stabilized-payload machinery: `partition_lock.py` is already
MEGB-03B-accepted code, and refactoring it into a shared abstraction wasn't
authorized for this subtask ("execute only MEGB-03C"). Consolidating both
into one generic privileged-artifact-lock primitive is flagged as sensible
future cleanup, not done here.
"""

# pylint: disable=duplicate-code
# See the module docstring above: this intentionally mirrors
# src.reference.partition_lock's write/verify pattern rather than sharing a
# base with it.

import dataclasses
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.dataset import PrivilegedTaskView
from src.reference.oracle import (
    COMPARISON_PROFILE_VERSION,
    DEVELOPMENT_ORACLE_ARTIFACT_ID,
    ORACLE_ALGORITHM_VERSION,
    REFERENCE_ONLY_ORACLE_ARTIFACT_ID,
    REFERENCE_VALIDATION_ONLY_ORACLE_ARTIFACT_ID,
    OracleArtifact,
    OracleBuildResult,
    require_release_ready,
    unbounded_int_str_digits,
)

LOCK_SCHEMA_VERSION = "oracle-lock-v1"
COMMITTED_OUTPUT_DIR = Path("artifacts/reference/oracle")
PRIVILEGED_OUTPUT_DIR = Path("artifacts/privileged/reference/oracle")
LOCK_PATH = COMMITTED_OUTPUT_DIR / "oracle.lock.json"
BUILD_COMMAND = "python -m src.reference.oracle_cli build"

FREEZE_STATE_FROZEN = "frozen"

_TRUSTED_CONSUMERS = {
    DEVELOPMENT_ORACLE_ARTIFACT_ID: ("MEGB-04-trusted-side",),
    REFERENCE_ONLY_ORACLE_ARTIFACT_ID: ("S*",),
    REFERENCE_VALIDATION_ONLY_ORACLE_ARTIFACT_ID: ("MEGB-03D",),
}

_ARTIFACT_FILENAMES = {
    DEVELOPMENT_ORACLE_ARTIFACT_ID: "development_oracle.json",
    REFERENCE_ONLY_ORACLE_ARTIFACT_ID: "reference_only_oracle.json",
    REFERENCE_VALIDATION_ONLY_ORACLE_ARTIFACT_ID: "reference_validation_only_oracle.json",
}


class FrozenArtifactConflictError(ValueError):
    """Raised when a differing privileged oracle artifact exists and force wasn't requested."""


class ManifestKindMismatchError(ValueError):
    """Raised when a file's artifact_kind doesn't match the expected artifact ID.

    Guards specifically against verifying a differently-scoped oracle file
    (e.g. the reference-only artifact) as if it were another artifact.
    """


@dataclass(frozen=True)
class OracleLockEntry:
    """One privileged oracle artifact's identity anchor."""

    artifact_id: str
    privileged_path: str
    schema_version: str
    algorithm_version: str
    comparison_profile_version: str
    dataset_checksum: str
    augmentation_checksums: Mapping[str, str]
    partition_checksum: str
    canonical_solution_hashes: Mapping[str, str]
    expected_task_count: int
    expected_case_summary: Mapping[str, object]
    size_bytes: int
    logical_sha256: str
    generation_command: str
    generating_code_revision: str
    generating_code_dirty: bool
    trusted_consumers: tuple[str, ...]
    freeze_state: str


@dataclass(frozen=True)
class OracleLockFile:
    """The complete, committed lock covering every privileged oracle artifact."""

    lock_schema_version: str
    generated_at: str
    entries: tuple[OracleLockEntry, ...]


@dataclass(frozen=True)
class OracleArtifactVerificationResult:
    """Per-artifact verification outcome. Never carries expected-output contents."""

    artifact_id: str
    logical_checksum_match: bool
    size_match: bool
    on_disk_present: bool
    on_disk_checksum_match: bool | None
    on_disk_bytes_match_rebuild: bool | None
    dataset_checksum_match: bool
    augmentation_checksum_match: bool
    canonical_solution_hashes_match: bool
    passed: bool


def _serialize_artifact(payload: Mapping[str, object]) -> bytes:
    """Canonical byte serialization used for both writing and hashing oracle artifacts."""
    return (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def _stabilized_artifact_payload(artifact: OracleArtifact) -> dict[str, Any]:
    """Wall-clock-free dict form of an oracle artifact, used for privileged-artifact bytes.

    Mirrors ``src.reference.partition_lock``'s ``_stabilized_manifest_payload``:
    ``generated_at`` and ``dataset_provenance.loaded_at`` are fresh
    timestamps on every build; left unstripped, the on-disk file would
    differ on every rebuild even with byte-identical corpus/code/canonical
    solutions.
    """
    payload = dict(dataclasses.asdict(artifact))
    payload["generated_at"] = ""
    dataset_provenance_dict = payload.get("dataset_provenance")
    if isinstance(dataset_provenance_dict, dict):
        dataset_provenance_dict = dict(dataset_provenance_dict)
        dataset_provenance_dict["loaded_at"] = ""
        payload["dataset_provenance"] = dataset_provenance_dict
    return payload


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


def _canonical_solution_hashes(
    task_ids: set[str], privileged_by_id: Mapping[str, PrivilegedTaskView]
) -> dict[str, str]:
    return {
        task_id: hashlib.sha256(
            (privileged_by_id[task_id].canonical_solution).encode("utf-8")
        ).hexdigest()
        for task_id in sorted(task_ids)
    }


def _build_lock_entry(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    artifact: OracleArtifact,
    privileged_path: Path,
    artifact_bytes: bytes,
    augmentation_results: Mapping[str, Any],
    privileged_by_id: Mapping[str, PrivilegedTaskView],
    code_sha: str,
    code_dirty: bool,
) -> OracleLockEntry:
    task_ids = {record.task_id for record in artifact.records}
    return OracleLockEntry(
        artifact_id=artifact.artifact_kind,
        privileged_path=str(privileged_path),
        schema_version=LOCK_SCHEMA_VERSION,
        algorithm_version=ORACLE_ALGORITHM_VERSION,
        comparison_profile_version=COMPARISON_PROFILE_VERSION,
        dataset_checksum=artifact.dataset_provenance.evalplus_dataset_hash,
        augmentation_checksums={
            task_id: result.combined_checksum
            for task_id, result in sorted(augmentation_results.items())
            if task_id in task_ids
        },
        partition_checksum=artifact.partition_checksum,
        canonical_solution_hashes=_canonical_solution_hashes(task_ids, privileged_by_id),
        expected_task_count=len(task_ids),
        expected_case_summary={"case_count": len(artifact.records)},
        size_bytes=len(artifact_bytes),
        logical_sha256=artifact.artifact_checksum,
        generation_command=BUILD_COMMAND,
        generating_code_revision=code_sha,
        generating_code_dirty=code_dirty,
        trusted_consumers=_TRUSTED_CONSUMERS[artifact.artifact_kind],
        freeze_state=FREEZE_STATE_FROZEN,
    )


def write_privileged_oracle_artifacts(
    build_result: OracleBuildResult,
    augmentation_results: Mapping[str, Any],
    privileged_by_id: Mapping[str, PrivilegedTaskView],
    privileged_dir: Path = PRIVILEGED_OUTPUT_DIR,
    force: bool = False,
) -> OracleLockFile:
    """Write all three oracle artifacts to the privileged directory and build the lock file.

    Refuses to silently overwrite an existing, differing privileged file
    unless force=True — matching ``partition_lock.write_privileged_artifacts``.

    Refuses to write anything at all — no privileged bytes, no lock — if
    ``build_result`` has any unresolved oracle-generation failure
    (``UnresolvedGenerationFailureError``). A build that couldn't establish
    ground truth for every case must never receive a valid frozen/released
    state or be handed to a downstream consumer.
    """
    require_release_ready(build_result)

    privileged_dir.mkdir(parents=True, exist_ok=True)
    code_sha, code_dirty = _git_head_sha()

    artifacts = (
        build_result.development_oracle,
        build_result.reference_only_oracle,
        build_result.reference_validation_only_oracle,
    )
    entries = []
    with unbounded_int_str_digits():
        for artifact in artifacts:
            path = privileged_dir / _ARTIFACT_FILENAMES[artifact.artifact_kind]
            artifact_bytes = _serialize_artifact(_stabilized_artifact_payload(artifact))

            if path.exists() and not force:
                existing_bytes = path.read_bytes()
                if existing_bytes != artifact_bytes:
                    raise FrozenArtifactConflictError(
                        f"{path} already exists and differs from the freshly built "
                        "artifact; refusing to overwrite silently. Pass force=True "
                        "to replace it deliberately (this destroys the previous "
                        "frozen evidence; requires an explicit new artifact version "
                        "or approved amendment per the privileged-artifact policy)."
                    )
            else:
                path.write_bytes(artifact_bytes)

            entries.append(
                _build_lock_entry(
                    artifact, path, artifact_bytes, augmentation_results, privileged_by_id,
                    code_sha, code_dirty,
                )
            )

    return OracleLockFile(
        lock_schema_version=LOCK_SCHEMA_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        entries=tuple(entries),
    )


def write_oracle_lock_file(lock: OracleLockFile, lock_path: Path = LOCK_PATH) -> None:
    """Persist the lock file (committed; never gitignored)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(dataclasses.asdict(lock), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_oracle_lock_file(lock_path: Path = LOCK_PATH) -> OracleLockFile:
    """Load a previously written oracle lock file for verification."""
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    entries = tuple(OracleLockEntry(**entry) for entry in data["entries"])
    return OracleLockFile(
        lock_schema_version=data["lock_schema_version"],
        generated_at=data["generated_at"],
        entries=entries,
    )


# pylint: disable-next=too-many-locals
def verify_oracle_against_lock(
    lock: OracleLockFile,
    build_result: OracleBuildResult,
    augmentation_results: Mapping[str, Any],
    privileged_by_id: Mapping[str, PrivilegedTaskView],
) -> tuple[OracleArtifactVerificationResult, ...]:
    """Compare a freshly regenerated oracle build against the committed lock.

    Read-only: never writes anything and never prints/returns expected-output
    contents, only checksums, sizes, and pass/fail booleans. Raises
    ManifestKindMismatchError if an on-disk file's artifact_kind doesn't
    match what's expected at that path.

    Raises ``UnresolvedGenerationFailureError`` if the freshly rebuilt
    ``build_result`` has any unresolved oracle-generation failure — even a
    lock file that looks internally consistent must never verify as valid
    against a build that couldn't establish ground truth for every case.
    """
    require_release_ready(build_result)

    fresh_by_id: dict[str, OracleArtifact] = {
        DEVELOPMENT_ORACLE_ARTIFACT_ID: build_result.development_oracle,
        REFERENCE_ONLY_ORACLE_ARTIFACT_ID: build_result.reference_only_oracle,
        REFERENCE_VALIDATION_ONLY_ORACLE_ARTIFACT_ID: build_result.reference_validation_only_oracle,
    }

    results = []
    with unbounded_int_str_digits():
        for entry in lock.entries:
            fresh_artifact = fresh_by_id[entry.artifact_id]
            fresh_bytes = _serialize_artifact(_stabilized_artifact_payload(fresh_artifact))
            task_ids = {record.task_id for record in fresh_artifact.records}

            logical_match = fresh_artifact.artifact_checksum == entry.logical_sha256
            size_match = len(fresh_bytes) == entry.size_bytes
            dataset_match = (
                fresh_artifact.dataset_provenance.evalplus_dataset_hash == entry.dataset_checksum
            )
            fresh_augmentation_checksums = {
                task_id: result.combined_checksum
                for task_id, result in augmentation_results.items()
                if task_id in task_ids
            }
            augmentation_match = fresh_augmentation_checksums == dict(
                entry.augmentation_checksums
            )
            canonical_hashes_match = _canonical_solution_hashes(
                task_ids, privileged_by_id
            ) == dict(entry.canonical_solution_hashes)

            privileged_path = Path(entry.privileged_path)
            on_disk_present = privileged_path.exists()
            on_disk_checksum_match: bool | None = None
            on_disk_bytes_match_rebuild: bool | None = None
            if on_disk_present:
                on_disk_payload = json.loads(privileged_path.read_text(encoding="utf-8"))
                actual_kind = on_disk_payload.get("artifact_kind")
                if actual_kind != entry.artifact_id:
                    raise ManifestKindMismatchError(
                        f"{privileged_path}: artifact_kind={actual_kind!r} does not "
                        f"match expected artifact_id={entry.artifact_id!r} — refusing "
                        "to verify (a differently-scoped oracle file must never be "
                        "treated as this artifact)"
                    )
                stripped = dict(on_disk_payload)
                stripped["artifact_checksum"] = ""
                on_disk_checksum_match = _logical_checksum_matches(stripped, entry.logical_sha256)
                on_disk_bytes_match_rebuild = privileged_path.read_bytes() == fresh_bytes

            passed = (
                logical_match
                and size_match
                and dataset_match
                and augmentation_match
                and canonical_hashes_match
                and on_disk_checksum_match is not False
                and on_disk_bytes_match_rebuild is not False
            )
            results.append(
                OracleArtifactVerificationResult(
                    artifact_id=entry.artifact_id,
                    logical_checksum_match=logical_match,
                    size_match=size_match,
                    on_disk_present=on_disk_present,
                    on_disk_checksum_match=on_disk_checksum_match,
                    on_disk_bytes_match_rebuild=on_disk_bytes_match_rebuild,
                    dataset_checksum_match=dataset_match,
                    augmentation_checksum_match=augmentation_match,
                    canonical_solution_hashes_match=canonical_hashes_match,
                    passed=passed,
                )
            )
    return tuple(results)


def _logical_checksum_matches(stripped_payload: Mapping[str, Any], expected: str) -> bool:
    """Recompute an artifact's logical checksum from an on-disk (stabilized) payload.

    The on-disk payload is already wall-clock-free (written via
    ``_stabilized_artifact_payload``), so only the self-referential
    ``artifact_checksum`` field needs stripping before recomputing.
    """
    serialized = json.dumps(stripped_payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest() == expected
