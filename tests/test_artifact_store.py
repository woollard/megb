"""MEGB-03H.2C.3B.2B.1: construction/validation and behavior tests for
:mod:`src.distributed.artifact_store`. Harmless synthetic bytes only."""

import pytest

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.artifact_store import (
    ArtifactContentMismatchError,
    ArtifactMetadata,
    ArtifactMetadataMismatchError,
    ArtifactNotFoundError,
    InMemoryArtifactStore,
)
from src.distributed.personal_policy import DataClassification, WorkloadClass
from tests._atomic_stores_fixtures import make_result_artifact_reference, make_synthetic_content


def _metadata(**overrides: object) -> ArtifactMetadata:
    fields: dict[str, object] = {
        "workload_class": WorkloadClass.SYNTHETIC_SMOKE,
        "data_classification": DataClassification.SYNTHETIC,
    }
    fields.update(overrides)
    return ArtifactMetadata(**fields)  # type: ignore[arg-type]


def test_put_then_resolve_true() -> None:
    """Test put then resolve true."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("a")
    reference = make_result_artifact_reference(content)
    store.put(reference, content, _metadata())
    assert store.resolve(reference) is True


def test_resolve_false_for_unwritten_reference() -> None:
    """Test resolve false for unwritten reference."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("never-written")
    reference = make_result_artifact_reference(content)
    assert store.resolve(reference) is False


def test_get_returns_content_and_metadata() -> None:
    """Test get returns content and metadata."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("b")
    reference = make_result_artifact_reference(content)
    metadata = _metadata()
    store.put(reference, content, metadata)
    got_content, got_metadata = store.get(reference)
    assert got_content == content
    assert got_metadata == metadata


def test_get_raises_for_unwritten_reference() -> None:
    """Test get raises for unwritten reference."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("ghost")
    reference = make_result_artifact_reference(content)
    with pytest.raises(ArtifactNotFoundError):
        store.get(reference)


def test_put_rejects_content_not_matching_reference_checksum() -> None:
    """Test put rejects content not matching reference checksum."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("c")
    reference = make_result_artifact_reference(content)
    wrong_content = make_synthetic_content("different")
    with pytest.raises(ArtifactContentMismatchError):
        store.put(reference, wrong_content, _metadata())


def test_put_identical_write_is_idempotent() -> None:
    """Test put identical write is idempotent."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("d")
    reference = make_result_artifact_reference(content)
    metadata = _metadata()
    store.put(reference, content, metadata)
    result = store.put(reference, content, metadata)
    assert result == reference


def test_put_rejects_overwrite_with_different_content_same_checksum_slot() -> None:
    """Test put rejects overwrite with different content at the same
    checksum -- this can only be exercised by directly forcing a
    checksum collision scenario, so instead we verify the refusal path
    using the store's own already-written entry compared byte-for-byte."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("e")
    reference = make_result_artifact_reference(content)
    store.put(reference, content, _metadata())
    # A second put under the same reference/checksum must carry the same
    # bytes -- attempting different bytes under a *different* checksum
    # naturally raises ArtifactContentMismatchError (checksum mismatch),
    # which is the same defensive path; there is no way to force a true
    # sha256 collision synthetically, so this test documents that path.
    other_content = make_synthetic_content("f")
    other_reference = make_result_artifact_reference(other_content)
    with pytest.raises(ArtifactContentMismatchError):
        store.put(other_reference, content, _metadata())


def test_put_rejects_overwrite_with_different_metadata() -> None:
    """Test put rejects overwrite with different metadata."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("g")
    reference = make_result_artifact_reference(content)
    store.put(reference, content, _metadata())
    with pytest.raises(ArtifactMetadataMismatchError):
        store.put(reference, content, _metadata(workload_class=WorkloadClass.PRODUCTION))


def test_put_rejects_non_bytes_content() -> None:
    """Test put rejects non bytes content."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("h")
    reference = make_result_artifact_reference(content)
    with pytest.raises(InvalidDistributedProvenanceError):
        store.put(reference, "not-bytes", _metadata())  # type: ignore[arg-type]


def test_artifact_metadata_rejects_wrong_types() -> None:
    """Test artifact metadata rejects wrong types."""
    with pytest.raises(InvalidDistributedProvenanceError):
        ArtifactMetadata(
            workload_class="not-an-enum",  # type: ignore[arg-type]
            data_classification=DataClassification.SYNTHETIC,
        )


def test_verify_artifact_classification_accepts_matching_claim() -> None:
    """Test verify artifact classification accepts matching claim."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("i")
    reference = make_result_artifact_reference(content)
    store.put(reference, content, _metadata())
    store.verify_artifact_classification(
        reference, WorkloadClass.SYNTHETIC_SMOKE, DataClassification.SYNTHETIC
    )  # must not raise


def test_verify_artifact_classification_rejects_mismatched_workload_class() -> None:
    """Test verify_artifact_classification never trusts a queue-supplied
    classification on its own -- it must match the artifact's own
    immutably-bound metadata."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("j")
    reference = make_result_artifact_reference(content)
    store.put(reference, content, _metadata())
    with pytest.raises(ArtifactMetadataMismatchError):
        store.verify_artifact_classification(
            reference, WorkloadClass.PRODUCTION, DataClassification.SYNTHETIC
        )


def test_verify_artifact_classification_rejects_mismatched_data_classification() -> None:
    """Test verify artifact classification rejects mismatched data
    classification."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("k")
    reference = make_result_artifact_reference(content)
    store.put(reference, content, _metadata())
    with pytest.raises(ArtifactMetadataMismatchError):
        store.verify_artifact_classification(
            reference, WorkloadClass.SYNTHETIC_SMOKE, DataClassification.PRIVILEGED_REFERENCE
        )


def test_verify_artifact_classification_raises_not_found_for_unwritten_reference() -> None:
    """Test verify artifact classification raises not found for
    unwritten reference."""
    store = InMemoryArtifactStore()
    content = make_synthetic_content("never")
    reference = make_result_artifact_reference(content)
    with pytest.raises(ArtifactNotFoundError):
        store.verify_artifact_classification(
            reference, WorkloadClass.SYNTHETIC_SMOKE, DataClassification.SYNTHETIC
        )


def test_artifact_store_exposes_no_provider_uri_path_or_credential() -> None:
    """Test the store's own public surface has no provider URI/path/
    credential-shaped method or attribute."""
    store = InMemoryArtifactStore()
    forbidden_substrings = ("uri", "path", "bucket", "credential", "url")
    public_attrs = [name for name in dir(store) if not name.startswith("_")]
    for name in public_attrs:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"{name!r} matches forbidden {forbidden!r}"
