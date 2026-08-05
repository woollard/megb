"""MEGB-03H.2C.3B.2B.2: construction/behavior tests for
:mod:`src.distributed.artifact_capabilities` -- worker read-only candidate
access plus narrowly-scoped result publication, enforced structurally."""

# pylint: disable=duplicate-code
# This file's own `_metadata`/`_reference` synthetic builders inherently
# mirror tests/test_artifact_store.py's own equivalent helpers (both
# build the same ArtifactMetadata/ArtifactReference shapes) -- shared
# boilerplate, not shared logic, per this project's own established
# convention.

import hashlib

import pytest

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
)
from src.distributed.artifact_capabilities import (
    ArtifactCapabilityViolationError,
    WorkerArtifactCapability,
)
from src.distributed.artifact_store import ArtifactMetadata, InMemoryArtifactStore
from src.distributed.personal_policy import DataClassification, WorkloadClass
from src.distributed.work_contracts import ArtifactKind, ArtifactReference
from tests._coordinator_fixtures import make_synthetic_content, publish_candidate


def _metadata(**overrides: object) -> ArtifactMetadata:
    fields: dict[str, object] = {
        "workload_class": WorkloadClass.SYNTHETIC_SMOKE,
        "data_classification": DataClassification.SYNTHETIC,
    }
    fields.update(overrides)
    return ArtifactMetadata(**fields)  # type: ignore[arg-type]


def _reference(
    content: bytes, metadata: ArtifactMetadata, *, artifact_kind: ArtifactKind, reference_id: str
) -> ArtifactReference:
    return ArtifactReference(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        artifact_kind=artifact_kind,
        artifact_reference_id=reference_id,
        content_checksum=hashlib.sha256(content).hexdigest(),
        metadata_checksum=metadata.metadata_checksum,
    )


def test_capability_resolves_and_reads_a_published_candidate() -> None:
    """Test capability resolves and reads a published candidate --
    read-only access works for an already-published candidate."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("candidate")
    reference = publish_candidate(store, content)
    capability = WorkerArtifactCapability(store, store)
    assert capability.resolve(reference) is True
    got_content, got_metadata = capability.get(reference)
    assert got_content == content
    assert got_metadata.workload_class == WorkloadClass.SYNTHETIC_SMOKE


def test_capability_verifies_classification_against_bound_metadata() -> None:
    """Test capability verifies classification against bound metadata."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("candidate-2")
    reference = publish_candidate(store, content)
    capability = WorkerArtifactCapability(store, store)
    capability.verify_artifact_classification(
        reference, WorkloadClass.SYNTHETIC_SMOKE, DataClassification.SYNTHETIC
    )  # must not raise


def test_capability_publishes_a_result_artifact() -> None:
    """Test capability publishes a result artifact -- the one write path
    a worker has."""
    store = InMemoryArtifactStore()
    result_content = make_synthetic_content("result")
    metadata = _metadata()
    reference = _reference(
        result_content, metadata, artifact_kind=ArtifactKind.RESULT_ARTIFACT, reference_id="r-1"
    )
    capability = WorkerArtifactCapability(store, store)
    capability.publish_result(reference, result_content, metadata)
    assert capability.resolve(reference) is True


def test_capability_refuses_to_publish_a_candidate_kind_reference() -> None:
    """Test capability refuses to publish a candidate-kind reference --
    a worker can never author or overwrite a candidate artifact through
    its own result-publication method."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("attempted-candidate")
    metadata = _metadata()
    reference = _reference(
        content,
        metadata,
        artifact_kind=ArtifactKind.CANDIDATE_MANIFEST_ENTRY,
        reference_id="attempted-candidate-0001",
    )
    capability = WorkerArtifactCapability(store, store)
    with pytest.raises(ArtifactCapabilityViolationError):
        capability.publish_result(reference, content, metadata)
    assert capability.resolve(reference) is False


def test_capability_cannot_publish_a_differently_classified_copy_of_a_candidate() -> None:
    """Test that a worker cannot use its result-publication method to
    smuggle a lower-classified copy of an already-published candidate's
    content into the store -- the artifact_kind check alone already
    blocks it, but this test proves the end-to-end refusal explicitly."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("shared-candidate-bytes")
    publish_candidate(
        store, content, data_classification=DataClassification.PRIVILEGED_REFERENCE
    )
    lower_metadata = _metadata(data_classification=DataClassification.SYNTHETIC)
    reference = _reference(
        content,
        lower_metadata,
        artifact_kind=ArtifactKind.CANDIDATE_MANIFEST_ENTRY,
        reference_id="reclassification-attempt-0001",
    )
    capability = WorkerArtifactCapability(store, store)
    with pytest.raises(ArtifactCapabilityViolationError):
        capability.publish_result(reference, content, lower_metadata)


def test_capability_has_no_unrestricted_put_method() -> None:
    """Test the capability object structurally exposes no unrestricted
    write path -- only ``publish_result``, never a bare ``put``."""
    store = InMemoryArtifactStore()
    capability = WorkerArtifactCapability(store, store)
    assert not hasattr(capability, "put")
