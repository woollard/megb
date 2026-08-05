"""MEGB-03H.2C.3B.2C: the immutable, checksummed candidate manifest a
trusted generation-plane publisher produces. The execution plane (the
coordinator and every worker invocation) receives only
``ArtifactReference`` values drawn from an already-published manifest --
never the manifest object itself, and never raw candidate bytes."""

import hashlib
from dataclasses import dataclass

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
    require_checksum_algorithm_version,
    require_orchestration_schema_version,
)
from src.distributed.artifact_capabilities import GenerationPlaneArtifactCapability
from src.distributed.artifact_store import ArtifactMetadata
from src.distributed.work_contracts import ArtifactKind, ArtifactReference


class InvalidCandidateManifestError(InvalidDistributedProvenanceError):
    """Raised when a :class:`CandidateManifest`'s fields are internally
    inconsistent, or it carries an entry that is not a
    ``CANDIDATE_MANIFEST_ENTRY``."""


@dataclass(frozen=True)
class CandidateManifest:
    """The complete, immutable, self-checksummed record of every
    candidate artifact one generation-plane publishing pass produced.
    ``manifest_entries`` is sorted by ``artifact_reference_id`` so two
    manifests built from the same entries in different insertion order
    are identical."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    manifest_entries: tuple[ArtifactReference, ...]
    manifest_checksum: str = ""

    def __post_init__(self) -> None:
        require_orchestration_schema_version(self)
        require_checksum_algorithm_version(self)
        if not isinstance(self.manifest_entries, tuple) or not self.manifest_entries:
            raise InvalidCandidateManifestError(
                "manifest_entries must be a nonempty tuple of ArtifactReference"
            )
        for entry in self.manifest_entries:
            if not isinstance(entry, ArtifactReference):
                raise InvalidCandidateManifestError(
                    f"manifest_entries must contain only ArtifactReference, got {entry!r}"
                )
            if entry.artifact_kind != ArtifactKind.CANDIDATE_MANIFEST_ENTRY:
                raise InvalidCandidateManifestError(
                    "manifest_entries may only contain CANDIDATE_MANIFEST_ENTRY references, "
                    f"got {entry.artifact_kind!r}"
                )
        ids = [entry.artifact_reference_id for entry in self.manifest_entries]
        if ids != sorted(ids):
            raise InvalidCandidateManifestError(
                "manifest_entries must be sorted by artifact_reference_id"
            )
        if len(ids) != len(set(ids)):
            raise InvalidCandidateManifestError(
                "manifest_entries must not contain a duplicate artifact_reference_id"
            )
        expected_checksum = _compute_manifest_checksum(self.manifest_entries)
        if self.manifest_checksum and self.manifest_checksum != expected_checksum:
            raise InvalidCandidateManifestError(
                f"manifest_checksum {self.manifest_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own entries -- tampered manifest"
            )
        object.__setattr__(self, "manifest_checksum", expected_checksum)


def _compute_manifest_checksum(entries: tuple[ArtifactReference, ...]) -> str:
    canonical = "|".join(entry.reference_checksum for entry in entries)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_candidate_manifest(
    capability: GenerationPlaneArtifactCapability,
    contents: dict[str, bytes],
    *,
    metadata: ArtifactMetadata,
) -> CandidateManifest:
    """Publish one ``CANDIDATE_MANIFEST_ENTRY`` per ``(artifact_reference_id,
    content)`` pair in ``contents`` through ``capability``, and return the
    resulting, sorted, self-checksummed manifest. The only way this
    checkpoint's synthetic workload ever enters an artifact store."""
    entries = []
    for reference_id, content in contents.items():
        content_checksum = hashlib.sha256(content).hexdigest()
        reference = ArtifactReference(
            distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
            checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
            artifact_kind=ArtifactKind.CANDIDATE_MANIFEST_ENTRY,
            artifact_reference_id=reference_id,
            content_checksum=content_checksum,
            metadata_checksum=metadata.metadata_checksum,
        )
        capability.publish_candidate(reference, content, metadata)
        entries.append(reference)
    entries.sort(key=lambda entry: entry.artifact_reference_id)
    return CandidateManifest(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        manifest_entries=tuple(entries),
    )


__all__ = [
    "InvalidCandidateManifestError",
    "CandidateManifest",
    "build_candidate_manifest",
]
