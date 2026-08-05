"""MEGB-03H.2C.3B.2B.1: synthetic in-memory immutable artifact store.

Content-addressed: every stored artifact is keyed by its own
content-checksum-bound :class:`~src.distributed.work_contracts.ArtifactReference`;
this module never accepts an overwrite of the same reference with
different content or metadata, supports idempotent identical re-writes,
and exposes no provider URI, filesystem path, bucket name, or
credential -- only the opaque ``ArtifactReference`` this repository
already established, plus small, harmless bytes.

**Never treats queue-supplied classification as authoritative on its
own**: :func:`verify_artifact_classification` re-verifies a caller's
claimed ``workload_class``/``data_classification`` against the
immutable metadata actually bound to the artifact at write time -- a
caller cannot silently substitute a different classification for
already-stored content merely by asserting one in a queue message.

Tests using this module must use harmless synthetic bytes only -- never
real candidate, oracle, or benchmark content."""

import hashlib
import threading
from dataclasses import dataclass

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.personal_policy import DataClassification, WorkloadClass
from src.distributed.work_contracts import ArtifactReference


class ArtifactContentMismatchError(InvalidDistributedProvenanceError):
    """Raised when caller-supplied content's own sha256 does not match
    ``reference.artifact_checksum``, when an overwrite attempt supplies
    different content than what is already stored under the same
    reference, or when a stored artifact's content no longer matches its
    own checksum on read (corruption)."""


class ArtifactMetadataMismatchError(InvalidDistributedProvenanceError):
    """Raised when an overwrite attempt supplies different immutable
    metadata (``workload_class``/``data_classification``) than what is
    already bound to this reference, or when a caller's claimed
    classification does not match the artifact's own immutably-bound
    metadata."""


class ArtifactNotFoundError(InvalidDistributedProvenanceError):
    """Raised when ``get``/``verify_artifact_classification`` names a
    reference this store does not hold."""


@dataclass(frozen=True)
class ArtifactMetadata:
    """Immutable typed metadata bound to one artifact at write time.
    Deliberately excludes any raw resource name, path, or credential --
    only closed-enum classification values. Not a wire/schema type (no
    ``distributed_orchestration_schema_version``/self-checksum field):
    it is bound to, and only ever compared against, an already-checksummed
    :class:`~src.distributed.work_contracts.ArtifactReference`, never
    transmitted independently."""

    workload_class: WorkloadClass
    data_classification: DataClassification

    def __post_init__(self) -> None:
        if not isinstance(self.workload_class, WorkloadClass):
            raise InvalidDistributedProvenanceError(
                f"workload_class must be a WorkloadClass, got {self.workload_class!r}"
            )
        if not isinstance(self.data_classification, DataClassification):
            raise InvalidDistributedProvenanceError(
                f"data_classification must be a DataClassification, got "
                f"{self.data_classification!r}"
            )


class InMemoryArtifactStore:
    """Synthetic, single-process, lock-protected content-addressed
    artifact store. Keyed by ``artifact_checksum`` (not by
    ``artifact_reference_id``) -- two references with the same content
    checksum are, by construction, the same immutable artifact."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._content: dict[str, bytes] = {}
        self._metadata: dict[str, ArtifactMetadata] = {}

    def put(
        self, reference: ArtifactReference, content: bytes, metadata: ArtifactMetadata
    ) -> ArtifactReference:
        """Durably store ``content`` under ``reference``, bound to
        ``metadata``. Rejects content whose own sha256 does not match
        ``reference.artifact_checksum``. An identical repeat write
        (same checksum, same content, same metadata) is a harmless
        no-op, returning the same reference; a write with the same
        checksum but different content or metadata is refused."""
        if not isinstance(reference, ArtifactReference):
            raise InvalidDistributedProvenanceError(
                f"reference must be an ArtifactReference, got {reference!r}"
            )
        if not isinstance(content, bytes):
            raise InvalidDistributedProvenanceError(f"content must be bytes, got {content!r}")
        if not isinstance(metadata, ArtifactMetadata):
            raise InvalidDistributedProvenanceError(
                f"metadata must be an ArtifactMetadata, got {metadata!r}"
            )
        computed_checksum = hashlib.sha256(content).hexdigest()
        if computed_checksum != reference.artifact_checksum:
            raise ArtifactContentMismatchError(
                f"content's own sha256 {computed_checksum!r} does not match "
                f"reference.artifact_checksum {reference.artifact_checksum!r}"
            )
        with self._lock:
            existing_content = self._content.get(reference.artifact_checksum)
            if existing_content is not None:
                if existing_content != content:
                    raise ArtifactContentMismatchError(
                        f"artifact_checksum {reference.artifact_checksum!r} already stores "
                        f"different content -- refusing overwrite"
                    )
                existing_metadata = self._metadata[reference.artifact_checksum]
                if existing_metadata != metadata:
                    raise ArtifactMetadataMismatchError(
                        f"artifact_checksum {reference.artifact_checksum!r} already carries "
                        f"different metadata ({existing_metadata!r} != {metadata!r}) -- "
                        f"refusing overwrite"
                    )
                return reference
            self._content[reference.artifact_checksum] = content
            self._metadata[reference.artifact_checksum] = metadata
            return reference

    def resolve(self, reference: ArtifactReference) -> bool:
        """``True`` iff ``reference`` names content this store actually
        holds -- never returns or transports the content itself."""
        with self._lock:
            return reference.artifact_checksum in self._content

    def get(self, reference: ArtifactReference) -> tuple[bytes, ArtifactMetadata]:
        """A trusted read: returns ``(content, metadata)``, re-verifying
        the stored content against its own checksum every time (not
        merely on write) -- corruption is detected on read, not assumed
        absent."""
        with self._lock:
            content = self._content.get(reference.artifact_checksum)
            metadata = self._metadata.get(reference.artifact_checksum)
        if content is None or metadata is None:
            raise ArtifactNotFoundError(
                f"no artifact stored for artifact_checksum {reference.artifact_checksum!r}"
            )
        computed_checksum = hashlib.sha256(content).hexdigest()
        if computed_checksum != reference.artifact_checksum:
            raise ArtifactContentMismatchError(
                f"stored content's own sha256 {computed_checksum!r} no longer matches "
                f"artifact_checksum {reference.artifact_checksum!r} -- corruption detected on "
                f"read"
            )
        return content, metadata

    def verify_artifact_classification(
        self,
        reference: ArtifactReference,
        claimed_workload_class: WorkloadClass,
        claimed_data_classification: DataClassification,
    ) -> None:
        """Raise :class:`ArtifactMetadataMismatchError` unless
        ``claimed_workload_class``/``claimed_data_classification`` match
        the metadata immutably bound to ``reference`` at write time --
        the one required check that prevents a queue-supplied
        classification claim from ever being trusted on its own."""
        _, metadata = self.get(reference)
        if (
            metadata.workload_class != claimed_workload_class
            or metadata.data_classification != claimed_data_classification
        ):
            raise ArtifactMetadataMismatchError(
                f"claimed classification (workload_class={claimed_workload_class!r}, "
                f"data_classification={claimed_data_classification!r}) does not match the "
                f"artifact's own immutably-bound metadata {metadata!r}"
            )


__all__ = [
    "ArtifactContentMismatchError",
    "ArtifactMetadataMismatchError",
    "ArtifactNotFoundError",
    "ArtifactMetadata",
    "InMemoryArtifactStore",
]
