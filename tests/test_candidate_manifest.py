"""MEGB-03H.2C.3B.2C: offline tests for the generation-plane artifact
capability and the candidate manifest it produces. Synthetic fixtures
only."""

import pytest

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
)
from src.distributed.artifact_capabilities import (
    ArtifactCapabilityViolationError,
    GenerationPlaneArtifactCapability,
    WorkerArtifactCapability,
)
from src.distributed.artifact_store import ArtifactMetadata, InMemoryArtifactStore
from src.distributed.candidate_manifest import (
    CandidateManifest,
    InvalidCandidateManifestError,
    build_candidate_manifest,
)
from src.distributed.personal_policy import DataClassification, WorkloadClass
from src.distributed.work_contracts import ArtifactKind, ArtifactReference

_METADATA = ArtifactMetadata(
    workload_class=WorkloadClass.SYNTHETIC_QUALIFICATION_CANDIDATE,
    data_classification=DataClassification.SYNTHETIC,
)


def _result_reference(reference_id: str = "result-1") -> ArtifactReference:
    return ArtifactReference(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        artifact_kind=ArtifactKind.RESULT_ARTIFACT,
        artifact_reference_id=reference_id,
        content_checksum="0" * 64,
        metadata_checksum=_METADATA.metadata_checksum,
    )


def _candidate_reference(reference_id: str = "candidate-1") -> ArtifactReference:
    return ArtifactReference(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        artifact_kind=ArtifactKind.CANDIDATE_MANIFEST_ENTRY,
        artifact_reference_id=reference_id,
        content_checksum="1" * 64,
        metadata_checksum=_METADATA.metadata_checksum,
    )


def test_build_candidate_manifest_publishes_and_sorts_entries() -> None:
    """Test build_candidate_manifest publishes every entry and sorts the
    resulting manifest by artifact_reference_id regardless of input
    order."""
    store = InMemoryArtifactStore()
    capability = GenerationPlaneArtifactCapability(store)
    manifest = build_candidate_manifest(
        capability,
        {"b-item": b"content-b", "a-item": b"content-a"},
        metadata=_METADATA,
    )
    assert [entry.artifact_reference_id for entry in manifest.manifest_entries] == [
        "a-item",
        "b-item",
    ]
    assert len(manifest.manifest_checksum) == 64
    for entry in manifest.manifest_entries:
        assert store.resolve(entry)


def test_manifest_rejects_non_candidate_entry() -> None:
    """Test CandidateManifest construction rejects a non-candidate-kind
    entry."""
    with pytest.raises(InvalidCandidateManifestError):
        CandidateManifest(
            distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
            checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
            manifest_entries=(_result_reference(),),
        )


def test_manifest_rejects_duplicate_reference_id() -> None:
    """Test CandidateManifest construction rejects a duplicate
    artifact_reference_id."""
    with pytest.raises(InvalidCandidateManifestError):
        CandidateManifest(
            distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
            checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
            manifest_entries=(
                _candidate_reference("dup"),
                _candidate_reference("dup"),
            ),
        )


def test_manifest_rejects_unsorted_entries() -> None:
    """Test CandidateManifest construction rejects entries not sorted by
    artifact_reference_id."""
    with pytest.raises(InvalidCandidateManifestError):
        CandidateManifest(
            distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
            checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
            manifest_entries=(
                _candidate_reference("b-item"),
                _candidate_reference("a-item"),
            ),
        )


def test_manifest_rejects_checksum_tampering() -> None:
    """Test CandidateManifest construction rejects a tampered
    manifest_checksum."""
    manifest = CandidateManifest(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        manifest_entries=(_candidate_reference("a-item"),),
    )
    with pytest.raises(InvalidCandidateManifestError):
        CandidateManifest(
            distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
            checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
            manifest_entries=manifest.manifest_entries,
            manifest_checksum="0" * 64,
        )


def test_generation_plane_capability_rejects_result_artifact_kind() -> None:
    """Test GenerationPlaneArtifactCapability.publish_candidate rejects
    any artifact_kind other than CANDIDATE_MANIFEST_ENTRY."""
    store = InMemoryArtifactStore()
    capability = GenerationPlaneArtifactCapability(store)
    with pytest.raises(ArtifactCapabilityViolationError):
        capability.publish_candidate(_result_reference(), b"content", _METADATA)


def test_generation_plane_capability_has_no_read_or_result_methods() -> None:
    """Test GenerationPlaneArtifactCapability structurally exposes no
    read method (get/resolve/verify_artifact_classification) and no
    result-publishing method -- it cannot observe or author result
    content under any name."""
    store = InMemoryArtifactStore()
    capability = GenerationPlaneArtifactCapability(store)
    for forbidden_attr in ("get", "resolve", "verify_artifact_classification", "publish_result"):
        assert not hasattr(capability, forbidden_attr)


def test_generation_plane_capability_holds_only_a_writer_reference() -> None:
    """Test GenerationPlaneArtifactCapability's own instance state holds
    exactly one collaborator (the writer) -- no work store, budget
    store, worker registry, or audit sink reference of any kind."""
    store = InMemoryArtifactStore()
    capability = GenerationPlaneArtifactCapability(store)
    assert list(vars(capability).keys()) == ["_writer"]


def test_worker_artifact_capability_still_rejects_candidate_kind() -> None:
    """Test the existing WorkerArtifactCapability still rejects
    publishing a CANDIDATE_MANIFEST_ENTRY, confirming the two capability
    views remain structurally disjoint after this checkpoint's addition."""
    store = InMemoryArtifactStore()
    capability = WorkerArtifactCapability(store, store)
    with pytest.raises(ArtifactCapabilityViolationError):
        capability.publish_result(_candidate_reference(), b"content", _METADATA)
