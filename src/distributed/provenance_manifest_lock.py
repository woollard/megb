"""MEGB-03H.2C.3B.3 correction: the protected-manifest lock -- keeps full
``DistributedProvenanceManifest`` bytes out of git while making the
committed safe report's ``provenance_manifest_checksum`` a verifiable
reference rather than a dangling one.

Mirrors ``src.reference.partition_lock``'s own already-established
privileged-artifact-lock pattern exactly (full bytes under a gitignored
``artifacts/privileged/`` path; a small, committed ``*.lock.json``
anchoring identity via checksums, counts, and generation provenance; a
``verify`` mode that never prints protected contents). Pure logic only
-- never imports ``subprocess`` (this package's own established
"no subprocess" boundary, per
``tests/test_distributed_dependency_direction.py``): callers (which run
outside ``src/distributed/``) compute ``generating_code_revision``/
``generating_code_dirty`` themselves and pass them in as plain values,
exactly as ``DistributedProvenanceManifest.generation_command``/
``code_revision`` are themselves already caller-supplied plain fields.

Labeled explicitly as **synthetic protected evidence** everywhere it
appears (never real HumanEval/candidate evidence) -- using synthetic
data does not remove the need for the protected-artifact policy this
module implements.
"""

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.provenance_manifest import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION,
    DistributedProvenanceManifest,
    distributed_provenance_manifest_from_dict,
    distributed_provenance_manifest_to_dict,
)

MANIFEST_LOCK_SCHEMA_VERSION = "megb-03h2c3b3-distributed-provenance-manifest-lock-v1"

DEFAULT_PROTECTED_MANIFEST_PATH = Path(
    "artifacts/privileged/distributed_provenance/calibration_provenance_manifest.json"
)
DEFAULT_MANIFEST_LOCK_PATH = Path(
    "artifacts/reference/distributed_provenance/calibration_provenance_manifest.lock.json"
)

_ARTIFACT_ID = "calibration_provenance_manifest"


class FrozenManifestConflictError(InvalidDistributedProvenanceError):
    """Raised when a differing protected manifest already exists on disk
    and ``force`` was not requested -- refusing to silently overwrite
    already-frozen (synthetic) protected evidence."""


@dataclass(frozen=True)
class ManifestLockEntry:  # pylint: disable=too-many-instance-attributes
    """One protected manifest's identity anchor: everything needed to
    detect tampering, drift, substitution, or a dangling checksum
    without storing the manifest's own bytes here."""

    artifact_id: str
    protected_path: str
    schema_version: str
    checksum_algorithm_version: str
    manifest_checksum: str
    distributed_run_context_checksum: str
    expected_worker_count: int
    safe_topology_summary_checksum: str
    size_bytes: int
    generation_command: str
    generating_code_revision: str
    generating_code_dirty: bool
    authorized_consumers: tuple[str, ...]


@dataclass(frozen=True)
class ManifestLockFile:
    """The complete, committed lock covering the protected calibration-
    provenance manifest artifact."""

    lock_schema_version: str
    entries: tuple[ManifestLockEntry, ...]


@dataclass(frozen=True)
class ManifestVerificationResult:
    """Per-artifact verification outcome. Never carries manifest
    contents -- only booleans and checksums."""

    artifact_id: str
    on_disk_present: bool
    manifest_checksum_match: bool | None
    distributed_run_context_checksum_match: bool | None
    topology_summary_checksum_match: bool | None
    worker_count_match: bool | None
    passed: bool


def _serialize_manifest(manifest: DistributedProvenanceManifest) -> bytes:
    """Canonical byte serialization used for both writing and hashing
    the protected manifest -- one shared function so the lock's own
    recorded ``size_bytes`` always matches what is actually written."""
    payload = distributed_provenance_manifest_to_dict(manifest)
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_protected_manifest(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    manifest: DistributedProvenanceManifest,
    *,
    generation_command: str,
    generating_code_revision: str,
    generating_code_dirty: bool,
    authorized_consumers: tuple[str, ...],
    protected_path: Path = DEFAULT_PROTECTED_MANIFEST_PATH,
    force: bool = False,
) -> ManifestLockEntry:
    """Write ``manifest``'s full bytes to ``protected_path`` (a
    gitignored, synthetic-protected-evidence path) and build the
    corresponding :class:`ManifestLockEntry`.

    Refuses to silently overwrite an existing, differing protected file
    unless ``force=True`` -- the caller must explicitly acknowledge
    replacing already-frozen evidence, mirroring
    ``src.reference.partition_lock.write_privileged_artifacts``'s own
    established discipline."""
    protected_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = _serialize_manifest(manifest)

    if protected_path.exists() and not force:
        existing_bytes = protected_path.read_bytes()
        if existing_bytes != manifest_bytes:
            raise FrozenManifestConflictError(
                f"{protected_path} already exists and differs from the freshly built "
                "protected manifest; refusing to overwrite silently. Pass force=True "
                "to replace it deliberately (this destroys the previous frozen "
                "synthetic protected evidence)."
            )
    else:
        protected_path.write_bytes(manifest_bytes)

    return ManifestLockEntry(
        artifact_id=_ARTIFACT_ID,
        protected_path=str(protected_path),
        schema_version=manifest.distributed_provenance_manifest_schema_version,
        checksum_algorithm_version=manifest.checksum_algorithm_version,
        manifest_checksum=manifest.manifest_checksum,
        distributed_run_context_checksum=manifest.run_context.run_context_checksum,
        expected_worker_count=len(manifest.worker_execution_contexts),
        safe_topology_summary_checksum=manifest.topology_summary.aggregate_checksum,
        size_bytes=len(manifest_bytes),
        generation_command=generation_command,
        generating_code_revision=generating_code_revision,
        generating_code_dirty=generating_code_dirty,
        authorized_consumers=authorized_consumers,
    )


def write_lock_file(
    entry: ManifestLockEntry, lock_path: Path = DEFAULT_MANIFEST_LOCK_PATH
) -> ManifestLockFile:
    """Build and persist the committed lock file (never gitignored) for
    one protected-manifest entry."""
    lock = ManifestLockFile(lock_schema_version=MANIFEST_LOCK_SCHEMA_VERSION, entries=(entry,))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(dataclasses.asdict(lock), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return lock


def load_lock_file(lock_path: Path = DEFAULT_MANIFEST_LOCK_PATH) -> ManifestLockFile:
    """Load a previously written lock file for verification."""
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    entries = tuple(ManifestLockEntry(**entry) for entry in data["entries"])
    return ManifestLockFile(lock_schema_version=data["lock_schema_version"], entries=entries)


def _load_protected_manifest(entry: ManifestLockEntry) -> DistributedProvenanceManifest | None:
    protected_path = Path(entry.protected_path)
    if not protected_path.exists():
        return None
    data = json.loads(protected_path.read_text(encoding="utf-8"))
    return distributed_provenance_manifest_from_dict(data)


def verify_against_lock(lock: ManifestLockFile) -> tuple[ManifestVerificationResult, ...]:
    """Read the protected manifest bytes referenced by each of ``lock``'s
    entries and compare against the lock's own recorded identity.
    Read-only: never writes anything, never prints/returns manifest
    contents -- only checksums and pass/fail booleans.

    A missing protected artifact is reported as
    ``on_disk_present=False``/``passed=False`` rather than raising --
    callers that want "regenerate a missing artifact, then verify" call
    the deterministic build path first (mirroring
    ``src.reference.partition_lock``'s own established shape)."""
    results = []
    for entry in lock.entries:
        manifest = _load_protected_manifest(entry)
        on_disk_present = manifest is not None
        manifest_checksum_match: bool | None = None
        run_context_checksum_match: bool | None = None
        topology_checksum_match: bool | None = None
        worker_count_match: bool | None = None
        if manifest is not None:
            manifest_checksum_match = manifest.manifest_checksum == entry.manifest_checksum
            run_context_checksum_match = (
                manifest.run_context.run_context_checksum
                == entry.distributed_run_context_checksum
            )
            topology_checksum_match = (
                manifest.topology_summary.aggregate_checksum
                == entry.safe_topology_summary_checksum
            )
            worker_count_match = (
                len(manifest.worker_execution_contexts) == entry.expected_worker_count
            )
        passed = (
            on_disk_present
            and bool(manifest_checksum_match)
            and bool(run_context_checksum_match)
            and bool(topology_checksum_match)
            and bool(worker_count_match)
        )
        results.append(
            ManifestVerificationResult(
                artifact_id=entry.artifact_id,
                on_disk_present=on_disk_present,
                manifest_checksum_match=manifest_checksum_match,
                distributed_run_context_checksum_match=run_context_checksum_match,
                topology_summary_checksum_match=topology_checksum_match,
                worker_count_match=worker_count_match,
                passed=passed,
            )
        )
    return tuple(results)


def manifest_lock_entry_to_dict(entry: ManifestLockEntry) -> Mapping[str, object]:
    """Full-fidelity serialization of one :class:`ManifestLockEntry` --
    safe, committed-lock-suitable in its entirety (never manifest
    contents, only identity/checksum/provenance fields)."""
    return dataclasses.asdict(entry)


__all__ = [
    "MANIFEST_LOCK_SCHEMA_VERSION",
    "DEFAULT_PROTECTED_MANIFEST_PATH",
    "DEFAULT_MANIFEST_LOCK_PATH",
    "FrozenManifestConflictError",
    "ManifestLockEntry",
    "ManifestLockFile",
    "ManifestVerificationResult",
    "write_protected_manifest",
    "write_lock_file",
    "load_lock_file",
    "verify_against_lock",
    "manifest_lock_entry_to_dict",
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION",
]
