"""MEGB-03H.2C.3B.3 correction: the protected-manifest lock -- keeps full
``DistributedProvenanceManifest`` bytes out of git while making the
committed safe report's ``provenance_manifest_checksum`` a verifiable
reference rather than a dangling one.

Mirrors ``src.reference.partition_lock``'s own already-established
privileged-artifact-lock pattern (full bytes under a gitignored
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

**Lock-integrity correction (v1->v2).** The original v1 lock was not
itself self-checksummed: every field (including ``protected_path`` and
``authorized_consumers``) was trusted as-is, ``verify_against_lock``
opened whatever ``protected_path`` string the lock happened to contain
with no containment check, and the safe report never bound the exact
lock content it was verified against. v2 closes all three gaps:

1. :class:`ManifestLockEntry` gains ``lock_checksum``, a self-checksum
   over every other field (mirroring
   :class:`~src.distributed.calibration_provenance_report.CalibrationProvenanceReport`'s
   own ``report_checksum`` auto-compute-or-reject discipline) -- any
   tampering to any field, including ones ``verify_against_lock`` never
   directly re-derives (``schema_version``, ``generation_command``,
   ``authorized_consumers``, ...), changes this checksum.
2. ``protected_path`` is no longer trusted as arbitrary input: it must
   equal the canonical repository-relative path *derived from* the
   entry's own closed ``artifact_id`` (:func:`_canonical_protected_path`),
   rejecting absolute paths, ``..`` traversal, alternate separators, NUL/
   control characters, and unexpected nesting at construction time; at
   read time, :func:`_validate_containment` additionally resolves the
   path (dereferencing any symlink) and confirms it still lies within
   the authorized privileged subtree before any byte of the target is
   opened or read.
3. ``authorized_consumers`` is validated against a closed
   :class:`AuthorizedManifestConsumer` allowlist -- lock tampering can
   never expand which subsystems appear authorized.

The caller-facing binding of "the exact lock that was verified" lives one
layer up, in
:mod:`~src.distributed.calibration_provenance_report` (``lock_checksum``
field, schema v3) and :mod:`~src.distributed.calibration_provenance_report_cli`
(``verify()`` compares the loaded lock's own ``lock_checksum`` against the
one persisted in the accepted report, not merely against itself).
"""

import dataclasses
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from src.distributed._checksums import (
    InvalidDistributedProvenanceError,
    require_non_negative_int as _require_non_negative_int,
    require_sha256_hex as _require_sha256_hex,
    sha256_of as _sha256_of,
)
from src.distributed.provenance_manifest import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION,
    DistributedProvenanceManifest,
    distributed_provenance_manifest_from_dict,
    distributed_provenance_manifest_to_dict,
)

MANIFEST_LOCK_SCHEMA_VERSION = "megb-03h2c3b3-distributed-provenance-manifest-lock-v2"

# The single authorized root every protected-manifest path must resolve
# beneath. A plain module global (not a default-argument capture) so
# tests can isolate against a temporary root via
# ``monkeypatch.setattr(provenance_manifest_lock, "_PRIVILEGED_ROOT", ...)``
# without weakening the real, unpatched production value.
_PRIVILEGED_ROOT = Path("artifacts/privileged/distributed_provenance")

DEFAULT_MANIFEST_LOCK_PATH = Path(
    "artifacts/reference/distributed_provenance/calibration_provenance_manifest.lock.json"
)

_ARTIFACT_ID = "calibration_provenance_manifest"

# Closed map from artifact_id -> canonical filename beneath
# _PRIVILEGED_ROOT. The only place a protected-manifest path is ever
# *derived* -- ManifestLockEntry.__post_init__ validates protected_path
# against this, rather than trusting a caller- or lock-file-supplied
# path as arbitrary input.
_ARTIFACT_FILENAMES: Mapping[str, str] = {
    _ARTIFACT_ID: "calibration_provenance_manifest.json",
}

# Convenience constant for the real, unpatched production path -- for
# reference/display only. write_protected_manifest() itself always
# recomputes the canonical path fresh (see _canonical_protected_path),
# so it correctly reflects a test-patched _PRIVILEGED_ROOT even though
# this module-level constant, evaluated once at import time, does not.
DEFAULT_PROTECTED_MANIFEST_PATH = _PRIVILEGED_ROOT / _ARTIFACT_FILENAMES[_ARTIFACT_ID]


class UnknownManifestArtifactError(InvalidDistributedProvenanceError):
    """Raised when a lock entry's ``artifact_id`` is outside the closed
    set of known protected-manifest artifact kinds."""


class InvalidManifestLockEntryError(InvalidDistributedProvenanceError):
    """Raised when a :class:`ManifestLockEntry`'s fields are internally
    inconsistent: its own ``lock_checksum`` does not match its
    recomputed contents (tampered or corrupted lock), its
    ``protected_path`` is not the canonical repository-relative location
    derived from its ``artifact_id``, or ``authorized_consumers``
    contains a value outside the closed allowlist."""


class ManifestPathContainmentError(InvalidDistributedProvenanceError):
    """Raised when a protected-manifest path -- even one that is
    syntactically the canonical string -- resolves (after dereferencing
    any symlink) outside the authorized privileged subtree. Raised
    before any file content is opened or read; never discloses the
    resolved target path or its contents."""


class FrozenManifestConflictError(InvalidDistributedProvenanceError):
    """Raised when a differing protected manifest already exists on disk
    and ``force`` was not requested -- refusing to silently overwrite
    already-frozen (synthetic) protected evidence."""


class UnsupportedManifestLockSchemaVersionError(InvalidDistributedProvenanceError):
    """Raised when a :class:`ManifestLockFile` is stamped with a
    ``lock_schema_version`` other than :data:`MANIFEST_LOCK_SCHEMA_VERSION`
    -- e.g. a stale v1 lock, which predates the ``lock_checksum``
    self-check this module now requires. Never silently accepted as
    current."""


class AuthorizedManifestConsumer(str, Enum):
    """Closed, validated allowlist of subsystems permitted to consume
    the protected calibration-provenance manifest. Lock tampering can
    never expand this set: any ``authorized_consumers`` entry outside
    it is rejected at construction, never silently trusted."""

    MEGB_03H_2C_3B_3 = "MEGB-03H.2C.3B.3"


def _canonical_protected_path(artifact_id: str) -> Path:
    """The one legal ``protected_path`` for ``artifact_id``, derived
    from the closed :data:`_ARTIFACT_FILENAMES` map and the current
    (possibly test-patched) :data:`_PRIVILEGED_ROOT` -- never trusted as
    caller- or lock-file-supplied input."""
    filename = _ARTIFACT_FILENAMES.get(artifact_id)
    if filename is None:
        raise UnknownManifestArtifactError(
            f"artifact_id {artifact_id!r} is not a recognized protected-manifest artifact kind "
            f"(known: {sorted(_ARTIFACT_FILENAMES)!r})"
        )
    return _PRIVILEGED_ROOT / filename


def _reject_unsafe_path_string(value: object, field_name: str) -> None:
    """Defense-in-depth string-level rejection of every unsafe shape the
    correction names explicitly -- absolute paths, ``..`` traversal,
    alternate (``\\``) separators, and NUL/control characters -- ahead
    of (and independent from) the canonical-equality check below, so
    each malformed category fails with its own specific reason."""
    if not isinstance(value, str) or not value:
        raise InvalidManifestLockEntryError(f"{field_name!r} must be a nonempty string")
    if "\x00" in value or any(ord(char) < 0x20 for char in value):
        raise InvalidManifestLockEntryError(
            f"{field_name} contains a NUL or control character"
        )
    if "\\" in value:
        raise InvalidManifestLockEntryError(f"{field_name} must use POSIX '/' separators only")
    pure_path = PurePosixPath(value)
    if pure_path.is_absolute():
        raise InvalidManifestLockEntryError(
            f"{field_name} must be repository-relative, not absolute"
        )
    if ".." in pure_path.parts:
        raise InvalidManifestLockEntryError(
            f"{field_name} must not contain '..' path-traversal components"
        )


@dataclass(frozen=True)
class ManifestLockEntry:  # pylint: disable=too-many-instance-attributes
    """One protected manifest's identity anchor: everything needed to
    detect tampering, drift, substitution, or a dangling checksum
    without storing the manifest's own bytes here. Self-checksummed
    (``lock_checksum``, v2): construction auto-computes it when absent
    and rejects any caller-supplied value that does not match the
    recomputed checksum over every other field."""

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
    lock_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _reject_unsafe_path_string(self.protected_path, "protected_path")
        expected_path = str(_canonical_protected_path(self.artifact_id))
        if self.protected_path != expected_path:
            raise InvalidManifestLockEntryError(
                f"protected_path {self.protected_path!r} does not match the canonical path "
                f"derived from artifact_id {self.artifact_id!r} ({expected_path!r}) -- "
                "protected_path is never trusted as arbitrary input"
            )

        for field_name in (
            "schema_version",
            "checksum_algorithm_version",
            "generation_command",
            "generating_code_revision",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise InvalidManifestLockEntryError(f"{field_name!r} must be a nonempty string")

        _require_sha256_hex(self, "manifest_checksum")
        _require_sha256_hex(self, "distributed_run_context_checksum")
        _require_sha256_hex(self, "safe_topology_summary_checksum")
        _require_non_negative_int(self, "expected_worker_count")
        _require_non_negative_int(self, "size_bytes")

        if not isinstance(self.generating_code_dirty, bool):
            raise InvalidManifestLockEntryError(
                f"generating_code_dirty must be a bool, got {self.generating_code_dirty!r}"
            )

        if not isinstance(self.authorized_consumers, tuple) or not self.authorized_consumers:
            raise InvalidManifestLockEntryError(
                f"authorized_consumers must be a nonempty tuple, got {self.authorized_consumers!r}"
            )
        valid_consumers = frozenset(member.value for member in AuthorizedManifestConsumer)
        seen: set[str] = set()
        for consumer in self.authorized_consumers:
            if consumer not in valid_consumers:
                raise InvalidManifestLockEntryError(
                    f"authorized_consumers entry {consumer!r} is not in the closed allowlist "
                    f"{sorted(valid_consumers)!r} -- lock tampering must never expand access"
                )
            if consumer in seen:
                raise InvalidManifestLockEntryError(
                    f"authorized_consumers contains duplicate entry {consumer!r}"
                )
            seen.add(consumer)

        payload = _lock_entry_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.lock_checksum and self.lock_checksum != expected_checksum:
            raise InvalidManifestLockEntryError(
                f"lock_checksum {self.lock_checksum!r} does not match the recomputed checksum "
                f"{expected_checksum!r} over its own contents -- tampered or corrupted lock entry"
            )
        object.__setattr__(self, "lock_checksum", expected_checksum)


@dataclass(frozen=True)
class ManifestLockFile:
    """The complete, committed lock covering the protected calibration-
    provenance manifest artifact."""

    lock_schema_version: str
    entries: tuple[ManifestLockEntry, ...]

    def __post_init__(self) -> None:
        if self.lock_schema_version != MANIFEST_LOCK_SCHEMA_VERSION:
            raise UnsupportedManifestLockSchemaVersionError(
                f"lock_schema_version {self.lock_schema_version!r} does not match the version "
                f"this module implements ({MANIFEST_LOCK_SCHEMA_VERSION!r})"
            )


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
    size_match: bool | None
    passed: bool


def _lock_entry_payload(entry: ManifestLockEntry) -> dict[str, Any]:
    """Every :class:`ManifestLockEntry` field except ``lock_checksum``
    itself -- the payload ``lock_checksum`` is a sha256-canonical-json
    checksum over."""
    return {
        "artifact_id": entry.artifact_id,
        "protected_path": entry.protected_path,
        "schema_version": entry.schema_version,
        "checksum_algorithm_version": entry.checksum_algorithm_version,
        "manifest_checksum": entry.manifest_checksum,
        "distributed_run_context_checksum": entry.distributed_run_context_checksum,
        "expected_worker_count": entry.expected_worker_count,
        "safe_topology_summary_checksum": entry.safe_topology_summary_checksum,
        "size_bytes": entry.size_bytes,
        "generation_command": entry.generation_command,
        "generating_code_revision": entry.generating_code_revision,
        "generating_code_dirty": entry.generating_code_dirty,
        "authorized_consumers": list(entry.authorized_consumers),
    }


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
    force: bool = False,
) -> ManifestLockEntry:
    """Write ``manifest``'s full bytes to the one canonical protected
    path derived from :data:`_ARTIFACT_ID` (never a caller-supplied
    path -- closing the same "arbitrary input" gap
    :class:`ManifestLockEntry` itself now rejects) and build the
    corresponding :class:`ManifestLockEntry`.

    Refuses to silently overwrite an existing, differing protected file
    unless ``force=True`` -- the caller must explicitly acknowledge
    replacing already-frozen evidence, mirroring
    ``src.reference.partition_lock.write_privileged_artifacts``'s own
    established discipline."""
    protected_path = _canonical_protected_path(_ARTIFACT_ID)
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


def _manifest_lock_entry_from_dict(data: Mapping[str, Any]) -> ManifestLockEntry:
    """Inverse of :func:`manifest_lock_entry_to_dict` -- restores the
    ``tuple``-typed fields JSON only ever round-trips as ``list``
    (``authorized_consumers``) before construction, so
    ``ManifestLockEntry.__post_init__``'s strict ``isinstance(..., tuple)``
    checks see the correct type rather than rejecting every loaded
    entry outright."""
    fields = dict(data)
    fields["authorized_consumers"] = tuple(fields["authorized_consumers"])
    return ManifestLockEntry(**fields)


def load_lock_file(lock_path: Path = DEFAULT_MANIFEST_LOCK_PATH) -> ManifestLockFile:
    """Load a previously written lock file for verification. Each
    entry's own ``__post_init__`` re-validates its ``lock_checksum``
    (and every other invariant) against the loaded data -- a tampered
    lock fails here, before any consumer ever sees its fields."""
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    entries = tuple(_manifest_lock_entry_from_dict(entry) for entry in data["entries"])
    return ManifestLockFile(lock_schema_version=data["lock_schema_version"], entries=entries)


def _validate_containment(entry: ManifestLockEntry) -> Path:
    """Resolve ``entry.protected_path`` (dereferencing any symlink) and
    confirm it still lies within the authorized privileged subtree.
    Performed before any file content is opened or read -- a resolved
    path outside the subtree raises :class:`ManifestPathContainmentError`
    without ever disclosing the resolved target path or its contents."""
    root = _PRIVILEGED_ROOT.resolve()
    resolved = Path(entry.protected_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ManifestPathContainmentError(
            "protected-manifest path failed containment validation"
        ) from exc
    return resolved


def _load_protected_manifest(
    entry: ManifestLockEntry,
) -> tuple[DistributedProvenanceManifest | None, int | None]:
    """Containment-validate, then (if present) read and parse the
    protected manifest, returning ``(manifest_or_None, size_bytes_or_None)``.
    Containment validation always runs first, regardless of whether the
    target exists."""
    resolved_path = _validate_containment(entry)
    if not resolved_path.exists():
        return None, None
    raw_bytes = resolved_path.read_bytes()
    data = json.loads(raw_bytes.decode("utf-8"))
    return distributed_provenance_manifest_from_dict(data), len(raw_bytes)


def verify_against_lock(lock: ManifestLockFile) -> tuple[ManifestVerificationResult, ...]:
    """Read the protected manifest bytes referenced by each of ``lock``'s
    entries and compare against the lock's own recorded identity.
    Read-only: never writes anything, never prints/returns manifest
    contents -- only checksums, sizes, and pass/fail booleans.

    A missing protected artifact is reported as
    ``on_disk_present=False``/``passed=False`` rather than raising --
    callers that want "regenerate a missing artifact, then verify" call
    the deterministic build path first (mirroring
    ``src.reference.partition_lock``'s own established shape). A path
    that fails containment validation (including a symlink resolving
    outside the authorized subtree) raises
    :class:`ManifestPathContainmentError` instead -- a distinct,
    security-relevant failure mode from "simply missing"."""
    results = []
    for entry in lock.entries:
        manifest, actual_size = _load_protected_manifest(entry)
        on_disk_present = manifest is not None
        manifest_checksum_match: bool | None = None
        run_context_checksum_match: bool | None = None
        topology_checksum_match: bool | None = None
        worker_count_match: bool | None = None
        size_match: bool | None = None
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
            size_match = actual_size == entry.size_bytes
        passed = (
            on_disk_present
            and bool(manifest_checksum_match)
            and bool(run_context_checksum_match)
            and bool(topology_checksum_match)
            and bool(worker_count_match)
            and bool(size_match)
        )
        results.append(
            ManifestVerificationResult(
                artifact_id=entry.artifact_id,
                on_disk_present=on_disk_present,
                manifest_checksum_match=manifest_checksum_match,
                distributed_run_context_checksum_match=run_context_checksum_match,
                topology_summary_checksum_match=topology_checksum_match,
                worker_count_match=worker_count_match,
                size_match=size_match,
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
    "DEFAULT_MANIFEST_LOCK_PATH",
    "DEFAULT_PROTECTED_MANIFEST_PATH",
    "AuthorizedManifestConsumer",
    "FrozenManifestConflictError",
    "InvalidManifestLockEntryError",
    "ManifestPathContainmentError",
    "UnknownManifestArtifactError",
    "UnsupportedManifestLockSchemaVersionError",
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
