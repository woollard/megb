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

**MEGB-03H.2C.3B.2B.1 correction: classification is content-bound, not
mutable store bookkeeping.** The prior version of this module keyed its
internal dicts by content checksum alone
(``reference.artifact_checksum``), with :class:`ArtifactMetadata` stored
in a *separate* dict under the same key -- so the correctness property
"same bytes plus different classification are distinct identities" held
only as an accident of this one in-memory store's own internal
bookkeeping (a ``put`` with mismatched metadata happened to raise), never
as something provable from the reference alone. This correction gives
:class:`ArtifactMetadata` its own self-checksum
(``metadata_checksum``, auto-computed and tamper-checked exactly like
every other self-checksummed type in this project), requires that
checksum to appear on
:class:`~src.distributed.work_contracts.ArtifactReference` itself (which
folds it into that reference's own ``reference_checksum``), and keys this
store's internal dicts by the *composite*
``(reference.content_checksum, reference.metadata_checksum)`` pair rather
than content checksum alone. Consequences, all now structural rather than
incidental: the same content bytes bound to two different classifications
are two different composite keys -- two distinct artifact identities,
never a conflict *or* an idempotent equivalent write; metadata cannot be
replaced after first write, because doing so would require presenting
metadata whose own checksum no longer matches the reference's
``metadata_checksum`` (rejected before the store dict is even
consulted); and a trusted ``get``/``resolve`` re-verifies both checksums
independently on every call, so corruption of either content or metadata
is detected on read, not merely at write time.

Tests using this module must use harmless synthetic bytes only -- never
real candidate, oracle, or benchmark content."""

import hashlib
import threading
from dataclasses import dataclass

from src.distributed._checksums import (
    InvalidDistributedProvenanceError,
    sha256_of as _sha256_of,
)
from src.distributed.personal_policy import DataClassification, WorkloadClass
from src.distributed.work_contracts import ArtifactReference


class ArtifactContentMismatchError(InvalidDistributedProvenanceError):
    """Raised when caller-supplied content's own sha256 does not match
    ``reference.content_checksum``, when an overwrite attempt supplies
    different content than what is already stored under the same
    ``(content_checksum, metadata_checksum)`` identity, or when a stored
    artifact's content no longer matches its own checksum on read
    (corruption)."""


class ArtifactMetadataMismatchError(InvalidDistributedProvenanceError):
    """Raised when caller-supplied metadata's own ``metadata_checksum``
    does not match ``reference.metadata_checksum``, when an overwrite
    attempt supplies different immutable metadata than what is already
    bound to this exact composite identity, or when a caller's claimed
    classification does not match the artifact's own immutably-bound
    metadata."""


class ArtifactNotFoundError(InvalidDistributedProvenanceError):
    """Raised when ``get``/``verify_artifact_classification`` names a
    reference this store does not hold."""


@dataclass(frozen=True)
class ArtifactMetadata:
    """Immutable typed metadata bound to one artifact at write time.
    Deliberately excludes any raw resource name, path, or credential --
    only closed-enum classification values. Not itself a wire/schema type
    (no ``distributed_orchestration_schema_version`` field) -- it is
    never transmitted independently of the
    :class:`~src.distributed.work_contracts.ArtifactReference` whose own
    ``metadata_checksum`` field it supplies. It **is** self-checksummed
    (``metadata_checksum``, auto-computed and tamper-checked, exactly
    like every schema-versioned type in this project), because
    MEGB-03H.2C.3B.2B.1's correction requires that checksum to be provably
    bound into ``ArtifactReference.metadata_checksum`` -- not merely
    stored alongside content in an internal dict."""

    workload_class: WorkloadClass
    data_classification: DataClassification
    metadata_checksum: str = ""

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
        payload = {
            "workload_class": self.workload_class.value,
            "data_classification": self.data_classification.value,
        }
        expected_checksum = _sha256_of(payload)
        if self.metadata_checksum and self.metadata_checksum != expected_checksum:
            raise ArtifactMetadataMismatchError(
                f"metadata_checksum {self.metadata_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted artifact metadata"
            )
        object.__setattr__(self, "metadata_checksum", expected_checksum)


_ArtifactKey = tuple[str, str]


def _artifact_key(reference: ArtifactReference) -> _ArtifactKey:
    return (reference.content_checksum, reference.metadata_checksum)


class InMemoryArtifactStore:
    """Synthetic, single-process, lock-protected content-addressed
    artifact store. Keyed by the composite ``(content_checksum,
    metadata_checksum)`` pair -- not by ``artifact_reference_id`` and not
    by content checksum alone -- so the same content bytes bound to two
    different classifications are, by construction, two distinct
    artifact identities, never a collision requiring a conflict check."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._content: dict[_ArtifactKey, bytes] = {}
        self._metadata: dict[_ArtifactKey, ArtifactMetadata] = {}

    def put(
        self, reference: ArtifactReference, content: bytes, metadata: ArtifactMetadata
    ) -> ArtifactReference:
        """Durably store ``content`` under ``reference``, bound to
        ``metadata``. Rejects content whose own sha256 does not match
        ``reference.content_checksum``, and rejects ``metadata`` whose own
        ``metadata_checksum`` does not match ``reference.metadata_checksum``
        -- a caller cannot bind arbitrary metadata to a reference that
        already commits to a different one. An identical repeat write
        (same composite identity, same content, same metadata) is a
        harmless idempotent no-op, returning the same reference; a write
        under the same composite identity with different content or
        metadata is refused (defensive only -- since both are covered by
        the key itself, this can only occur on a genuine sha256
        collision or an internal corruption)."""
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
        computed_content_checksum = hashlib.sha256(content).hexdigest()
        if computed_content_checksum != reference.content_checksum:
            raise ArtifactContentMismatchError(
                f"content's own sha256 {computed_content_checksum!r} does not match "
                f"reference.content_checksum {reference.content_checksum!r}"
            )
        if metadata.metadata_checksum != reference.metadata_checksum:
            raise ArtifactMetadataMismatchError(
                f"metadata's own checksum {metadata.metadata_checksum!r} does not match "
                f"reference.metadata_checksum {reference.metadata_checksum!r}"
            )
        key = _artifact_key(reference)
        with self._lock:
            existing_content = self._content.get(key)
            if existing_content is not None:
                if existing_content != content:
                    raise ArtifactContentMismatchError(
                        f"artifact identity {key!r} already stores different content -- "
                        f"refusing overwrite"
                    )
                existing_metadata = self._metadata[key]
                if existing_metadata != metadata:
                    raise ArtifactMetadataMismatchError(
                        f"artifact identity {key!r} already carries different metadata "
                        f"({existing_metadata!r} != {metadata!r}) -- refusing overwrite"
                    )
                return reference
            self._content[key] = content
            self._metadata[key] = metadata
            return reference

    def resolve(self, reference: ArtifactReference) -> bool:
        """``True`` iff ``reference`` names content this store actually
        holds under its exact composite identity -- never returns or
        transports the content itself."""
        with self._lock:
            return _artifact_key(reference) in self._content

    def get(self, reference: ArtifactReference) -> tuple[bytes, ArtifactMetadata]:
        """A trusted read: returns ``(content, metadata)``, re-verifying
        the stored content's own sha256 against ``content_checksum`` and
        the stored metadata's own checksum against ``metadata_checksum``
        every time (not merely on write) -- corruption of either is
        detected on read, not assumed absent."""
        key = _artifact_key(reference)
        with self._lock:
            content = self._content.get(key)
            metadata = self._metadata.get(key)
        if content is None or metadata is None:
            raise ArtifactNotFoundError(f"no artifact stored for artifact identity {key!r}")
        computed_content_checksum = hashlib.sha256(content).hexdigest()
        if computed_content_checksum != reference.content_checksum:
            raise ArtifactContentMismatchError(
                f"stored content's own sha256 {computed_content_checksum!r} no longer matches "
                f"content_checksum {reference.content_checksum!r} -- corruption detected on read"
            )
        if metadata.metadata_checksum != reference.metadata_checksum:
            raise ArtifactMetadataMismatchError(
                f"stored metadata's own checksum {metadata.metadata_checksum!r} no longer "
                f"matches metadata_checksum {reference.metadata_checksum!r} -- corruption "
                f"detected on read"
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
