"""MEGB-03H.2C.3B.2B.2: capability-separated artifact views.

**Only a trusted publisher may create candidate or classification-metadata
artifacts.** In this checkpoint's own scope, that publisher is whatever
composes the engine (a test fixture, or a future coordinator-external
seeding step) calling
:meth:`~src.distributed.artifact_store.InMemoryArtifactStore.put` directly
-- the coordinator/worker engine itself never authors a
``CANDIDATE_MANIFEST_ENTRY`` artifact.

:class:`WorkerArtifactCapability` is the one object a worker invocation
ever receives for artifact access. It is **structurally**, not merely by
convention, incapable of:

* creating or overwriting a candidate-kind artifact (its own
  :meth:`publish_result` rejects any ``artifact_kind`` other than
  ``RESULT_ARTIFACT`` before ever touching the backing writer);
* trusting a queue-supplied classification claim (every read goes through
  :class:`~src.distributed.protocols.ArtifactReaderProtocol`'s own
  checksum-verified ``get``/``verify_artifact_classification``, never a
  bare field read).

A caller holding only this capability object has no way to reach the
backing store's unrestricted ``put`` at all -- there is no attribute or
method on this class that exposes it.

**MEGB-03H.2C.3B.2C addition:** :class:`GenerationPlaneArtifactCapability`
is the structural mirror image, formalizing the trusted publisher named
above as a real capability-separated class rather than a raw test
helper calling the store directly. See
:mod:`~src.distributed.candidate_manifest` for the immutable,
checksummed manifest this capability's publications are recorded into."""

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.artifact_store import ArtifactMetadata
from src.distributed.personal_policy import DataClassification, WorkloadClass
from src.distributed.protocols import ArtifactReaderProtocol, ArtifactWriterProtocol
from src.distributed.work_contracts import ArtifactKind, ArtifactReference


class ArtifactCapabilityViolationError(InvalidDistributedProvenanceError):
    """Raised when a caller attempts to use a capability-separated view
    outside what it structurally permits -- here, publishing anything
    other than a ``RESULT_ARTIFACT``-kind reference through
    :meth:`WorkerArtifactCapability.publish_result`."""


class GenerationPlaneArtifactCapability:
    """**MEGB-03H.2C.3B.2C addition.** The one object a trusted candidate
    publisher uses to create candidate-manifest artifacts. Composes only
    a bare :class:`~src.distributed.protocols.ArtifactWriterProtocol` --
    no reference to any read boundary, work store, budget store, worker
    registry, or audit sink is ever held. This is the structural mirror
    image of :class:`WorkerArtifactCapability`: where that class can
    publish only ``RESULT_ARTIFACT`` and never read/write a candidate,
    this class can publish only ``CANDIDATE_MANIFEST_ENTRY`` and has no
    read method of any kind -- it cannot resolve a result artifact,
    inspect a work record, or observe budget/audit state, because it
    holds no such reference at all, not merely by convention."""

    def __init__(self, writer: ArtifactWriterProtocol) -> None:
        self._writer = writer

    def publish_candidate(
        self, reference: ArtifactReference, content: bytes, metadata: ArtifactMetadata
    ) -> ArtifactReference:
        """Publish ``content``/``metadata`` under ``reference`` -- but
        only if ``reference.artifact_kind == ArtifactKind.CANDIDATE_MANIFEST_ENTRY``.
        Raises :class:`ArtifactCapabilityViolationError` for any other
        kind, including ``RESULT_ARTIFACT`` -- the generation plane can
        never author or overwrite a result artifact."""
        if reference.artifact_kind != ArtifactKind.CANDIDATE_MANIFEST_ENTRY:
            raise ArtifactCapabilityViolationError(
                f"generation-plane artifact capability may only publish artifact_kind="
                f"CANDIDATE_MANIFEST_ENTRY, got {reference.artifact_kind!r}"
            )
        return self._writer.put(reference, content, metadata)


class WorkerArtifactCapability:
    """Read-only artifact access (candidate resolution, classification
    verification) plus narrowly-scoped result-artifact publication --
    nothing else. Constructed once per worker invocation by the
    coordinator/engine composition layer; never handed a reference to the
    unrestricted backing store."""

    def __init__(self, reader: ArtifactReaderProtocol, writer: ArtifactWriterProtocol) -> None:
        self._reader = reader
        self._writer = writer

    def resolve(self, reference: ArtifactReference) -> bool:
        """Delegate to the read-only reader."""
        return self._reader.resolve(reference)

    def get(self, reference: ArtifactReference) -> tuple[bytes, ArtifactMetadata]:
        """Delegate to the read-only reader."""
        return self._reader.get(reference)

    def verify_artifact_classification(
        self,
        reference: ArtifactReference,
        claimed_workload_class: WorkloadClass,
        claimed_data_classification: DataClassification,
    ) -> None:
        """Delegate to the read-only reader."""
        self._reader.verify_artifact_classification(
            reference, claimed_workload_class, claimed_data_classification
        )

    def publish_result(
        self, reference: ArtifactReference, content: bytes, metadata: ArtifactMetadata
    ) -> ArtifactReference:
        """Publish ``content``/``metadata`` under ``reference`` -- but
        only if ``reference.artifact_kind == ArtifactKind.RESULT_ARTIFACT``.
        Raises :class:`ArtifactCapabilityViolationError` for any other
        kind, including ``CANDIDATE_MANIFEST_ENTRY`` -- a worker can never
        author or overwrite a candidate artifact, and can never publish a
        differently-classified copy of one under this method, since the
        only kind this method ever accepts is the result kind."""
        if reference.artifact_kind != ArtifactKind.RESULT_ARTIFACT:
            raise ArtifactCapabilityViolationError(
                f"worker artifact capability may only publish artifact_kind="
                f"RESULT_ARTIFACT, got {reference.artifact_kind!r}"
            )
        return self._writer.put(reference, content, metadata)


__all__ = [
    "ArtifactCapabilityViolationError",
    "GenerationPlaneArtifactCapability",
    "WorkerArtifactCapability",
]
