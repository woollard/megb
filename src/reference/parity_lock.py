"""MEGB-03D privileged-artifact lock: keep the full parity results out of git.

Applies the same policy as MEGB-03B/03C (see
``docs/measurement/privileged-artifact-policy.md``): the full parity
artifact (per-candidate detail, including mismatch-detail text) stays under
``artifacts/privileged/`` and outside git; a committed lock anchors its
identity; a committed *redacted* report carries only classifications,
agreement booleans, candidate source hashes, and aggregate mismatch
counts — never expected outputs or free-text semantic-difference detail.

Deliberately mirrors ``partition_lock``/``oracle_lock``'s write/verify
pattern rather than sharing a base with them — see those modules' own
docstrings for why (their consolidation is flagged as future cleanup, not
done here).
"""

# pylint: disable=duplicate-code

import dataclasses
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.dataset import DatasetProvenance
from src.reference.parity import ParityResult

LOCK_SCHEMA_VERSION = "parity-lock-v1"
PARITY_ARTIFACT_KIND = "parity_results"
COMMITTED_OUTPUT_DIR = Path("artifacts/reference/parity")
PRIVILEGED_OUTPUT_DIR = Path("artifacts/privileged/reference/parity")
PRIVILEGED_FILENAME = "parity_results.json"
LOCK_PATH = COMMITTED_OUTPUT_DIR / "parity.lock.json"
BUILD_COMMAND = "python -m src.reference.parity_cli build"
TRUSTED_CONSUMERS = ("MEGB-03E", "MEGB-03F")


class FrozenArtifactConflictError(ValueError):
    """Raised when a differing privileged parity artifact exists and force wasn't requested."""


@dataclass(frozen=True)
class EnvironmentRecord:
    """Pinned versions/APIs the parity comparison depends on (requirement 11)."""

    evalplus_version: str
    human_eval_version: str
    python_version: str
    numpy_version: str
    evalplus_internal_apis: tuple[str, ...]
    docker_backend_id: str
    runner_image_digest: str


@dataclass(frozen=True)
class ParityArtifact:
    """The complete, privileged parity-comparison artifact."""

    artifact_kind: str
    parity_corpus_version: str
    dataset_provenance: DatasetProvenance
    results: tuple[ParityResult, ...]
    environment: EnvironmentRecord
    generated_at: str
    artifact_checksum: str = ""


@dataclass(frozen=True)
class ParityLockEntry:
    """The privileged parity artifact's identity anchor."""

    artifact_id: str
    privileged_path: str
    schema_version: str
    parity_corpus_version: str
    dataset_checksum: str
    candidate_count: int
    agreement_count: int
    size_bytes: int
    logical_sha256: str
    generation_command: str
    generating_code_revision: str
    generating_code_dirty: bool
    trusted_consumers: tuple[str, ...]


@dataclass(frozen=True)
class ParityLockFile:
    """The committed lock covering the privileged parity artifact."""

    lock_schema_version: str
    generated_at: str
    entries: tuple[ParityLockEntry, ...]


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


def _strip_dataset_provenance_loaded_at(payload: dict[str, Any]) -> dict[str, Any]:
    dataset_provenance_dict = payload.get("dataset_provenance")
    if isinstance(dataset_provenance_dict, dict):
        dataset_provenance_dict = dict(dataset_provenance_dict)
        dataset_provenance_dict["loaded_at"] = ""
        payload["dataset_provenance"] = dataset_provenance_dict
    return payload


def _stabilized_artifact_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Wall-clock-free dict form used for privileged-artifact bytes (writing
    and on-disk/rebuild byte comparison). Keeps ``artifact_checksum`` as-is —
    the file on disk should show the real, already-computed checksum."""
    stripped = dict(payload)
    stripped["generated_at"] = ""
    return _strip_dataset_provenance_loaded_at(stripped)


def _logical_checksum_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Strip volatile fields *and* the self-referential checksum field before
    hashing — mirrors partition.py's own fix for the same class of
    cross-process determinism bug. Used only to compute/recompute the
    content-only checksum, never for the bytes actually written to disk."""
    stripped = dict(payload)
    stripped["artifact_checksum"] = ""
    stripped["generated_at"] = ""
    return _strip_dataset_provenance_loaded_at(stripped)


def _serialize_artifact(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def finalize_parity_artifact(
    parity_corpus_version: str,
    dataset_provenance: DatasetProvenance,
    results: tuple[ParityResult, ...],
    environment: EnvironmentRecord,
) -> ParityArtifact:
    """Build a ``ParityArtifact`` with its content-only checksum computed."""
    artifact = ParityArtifact(
        artifact_kind=PARITY_ARTIFACT_KIND,
        parity_corpus_version=parity_corpus_version,
        dataset_provenance=dataset_provenance,
        results=results,
        environment=environment,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    stable_payload = _logical_checksum_payload(dataclasses.asdict(artifact))
    checksum = hashlib.sha256(
        json.dumps(stable_payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()
    return dataclasses.replace(artifact, artifact_checksum=checksum)


def redact_parity_artifact(artifact: ParityArtifact) -> dict[str, object]:
    """The committed, public view: classifications, agreement, and aggregate
    counts only — never the free-text ``mismatch_detail`` or raw per-side
    ``detail`` strings (kept privileged-only)."""
    return {
        "manifest_kind": "parity_report_redacted",
        "parity_corpus_version": artifact.parity_corpus_version,
        "generated_at": artifact.generated_at,
        "candidates": [
            {
                "candidate_id": result.candidate_id,
                "task_id": result.task_id,
                "category": result.category,
                "candidate_source_sha256": result.candidate_source_sha256,
                "upstream_outcome": result.upstream.outcome,
                "megb_outcome": result.megb.outcome,
                "agree": result.agree,
            }
            for result in artifact.results
        ],
        "candidate_count": len(artifact.results),
        "agreement_count": sum(1 for r in artifact.results if r.agree),
        "source_artifact_checksum": artifact.artifact_checksum,
    }


def write_privileged_parity_artifact(
    artifact: ParityArtifact,
    privileged_dir: Path = PRIVILEGED_OUTPUT_DIR,
    force: bool = False,
) -> ParityLockFile:
    """Write the full parity artifact to the privileged directory and build the lock file."""
    privileged_dir.mkdir(parents=True, exist_ok=True)
    path = privileged_dir / PRIVILEGED_FILENAME
    artifact_bytes = _serialize_artifact(_stabilized_artifact_payload(dataclasses.asdict(artifact)))

    if path.exists() and not force:
        existing_bytes = path.read_bytes()
        if existing_bytes != artifact_bytes:
            raise FrozenArtifactConflictError(
                f"{path} already exists and differs from the freshly built artifact; "
                "refusing to overwrite silently. Pass force=True to replace it "
                "deliberately (this destroys the previous frozen evidence; requires an "
                "explicit new artifact version or approved amendment per the "
                "privileged-artifact policy)."
            )
    else:
        path.write_bytes(artifact_bytes)

    code_sha, code_dirty = _git_head_sha()
    entry = ParityLockEntry(
        artifact_id=PARITY_ARTIFACT_KIND,
        privileged_path=str(path),
        schema_version=LOCK_SCHEMA_VERSION,
        parity_corpus_version=artifact.parity_corpus_version,
        dataset_checksum=artifact.dataset_provenance.evalplus_dataset_hash,
        candidate_count=len(artifact.results),
        agreement_count=sum(1 for r in artifact.results if r.agree),
        size_bytes=len(artifact_bytes),
        logical_sha256=artifact.artifact_checksum,
        generation_command=BUILD_COMMAND,
        generating_code_revision=code_sha,
        generating_code_dirty=code_dirty,
        trusted_consumers=TRUSTED_CONSUMERS,
    )
    return ParityLockFile(
        lock_schema_version=LOCK_SCHEMA_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        entries=(entry,),
    )


def write_parity_lock_file(lock: ParityLockFile, lock_path: Path = LOCK_PATH) -> None:
    """Persist the lock file (committed; never gitignored)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(dataclasses.asdict(lock), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_parity_lock_file(lock_path: Path = LOCK_PATH) -> ParityLockFile:
    """Load a previously written parity lock file for verification."""
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    entries = tuple(ParityLockEntry(**entry) for entry in data["entries"])
    return ParityLockFile(
        lock_schema_version=data["lock_schema_version"],
        generated_at=data["generated_at"],
        entries=entries,
    )


@dataclass(frozen=True)
class ParityVerificationResult:
    """Verification outcome. Never carries mismatch-detail text or raw case content."""

    artifact_id: str
    logical_checksum_match: bool
    size_match: bool
    on_disk_present: bool
    on_disk_checksum_match: bool | None
    on_disk_bytes_match_rebuild: bool | None
    dataset_checksum_match: bool
    passed: bool


# pylint: disable-next=too-many-locals
def verify_parity_against_lock(
    lock: ParityLockFile, fresh_artifact: ParityArtifact
) -> tuple[ParityVerificationResult, ...]:
    """Compare a freshly regenerated parity artifact against the committed lock.

    Read-only: never writes anything and never prints/returns mismatch-detail
    text or per-case content, only checksums, sizes, and pass/fail booleans.
    """
    fresh_bytes = _serialize_artifact(
        _stabilized_artifact_payload(dataclasses.asdict(fresh_artifact))
    )

    results = []
    for entry in lock.entries:
        logical_match = fresh_artifact.artifact_checksum == entry.logical_sha256
        size_match = len(fresh_bytes) == entry.size_bytes
        dataset_match = (
            fresh_artifact.dataset_provenance.evalplus_dataset_hash == entry.dataset_checksum
        )

        privileged_path = Path(entry.privileged_path)
        on_disk_present = privileged_path.exists()
        on_disk_checksum_match: bool | None = None
        on_disk_bytes_match_rebuild: bool | None = None
        if on_disk_present:
            on_disk_bytes = privileged_path.read_bytes()
            on_disk_bytes_match_rebuild = on_disk_bytes == fresh_bytes
            on_disk_payload = json.loads(on_disk_bytes.decode("utf-8"))
            recomputed = hashlib.sha256(
                json.dumps(
                    _logical_checksum_payload(on_disk_payload),
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            ).hexdigest()
            on_disk_checksum_match = recomputed == entry.logical_sha256

        passed = (
            logical_match
            and size_match
            and dataset_match
            and on_disk_checksum_match is not False
            and on_disk_bytes_match_rebuild is not False
        )
        results.append(
            ParityVerificationResult(
                artifact_id=entry.artifact_id,
                logical_checksum_match=logical_match,
                size_match=size_match,
                on_disk_present=on_disk_present,
                on_disk_checksum_match=on_disk_checksum_match,
                on_disk_bytes_match_rebuild=on_disk_bytes_match_rebuild,
                dataset_checksum_match=dataset_match,
                passed=passed,
            )
        )
    return tuple(results)
