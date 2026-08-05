"""MEGB-03H.2C.3B.2B.1: synthetic record factories shared across the
``test_atomic_*``/``test_artifact_store``/``test_budget_store``/
``test_worker_registry_store``/``test_audit_sink_store`` test modules.

Callers needing ``make_sha256``/``make_lease``/``make_execution_attempt``
import them directly from
``tests/_distributed_orchestration_fixtures.py`` (this module does not
re-export them, to avoid duplicating that module's own builders). This
module adds only the content-aware builders that module does not
provide: a real artifact/result commit whose checksum is computed from
actual harmless synthetic bytes, required by
:mod:`~src.distributed.artifact_store`'s own checksum verification. No
privileged content, no real infrastructure identifiers, no candidate/case
data of any kind."""

# pylint: disable=duplicate-code
# This module's own field-dict boilerplate inherently mirrors
# tests/_distributed_orchestration_fixtures.py's own builders (both build
# the same underlying B.2A dataclasses) -- shared boilerplate, not shared
# logic, per this project's own established convention.

import hashlib
from typing import Any

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
)
from src.distributed.artifact_store import ArtifactMetadata
from src.distributed.personal_policy import DataClassification, WorkloadClass
from src.distributed.work_contracts import (
    ArtifactKind,
    ArtifactReference,
    ExecutionAttempt,
    ResultCommit,
)

#: The default classification bound to every artifact reference this
#: module builds unless a caller supplies its own ``metadata=`` --
#: matches every existing race/budget test's own default so a bare
#: ``make_result_artifact_reference(content)`` composes directly with a
#: same-default ``ArtifactMetadata()`` construction at the call site.
_DEFAULT_METADATA = ArtifactMetadata(
    workload_class=WorkloadClass.SYNTHETIC_SMOKE,
    data_classification=DataClassification.SYNTHETIC,
)


def make_synthetic_content(seed: str) -> bytes:
    """Harmless synthetic bytes -- never real candidate/oracle/benchmark
    content."""
    return f"synthetic-artifact-content-{seed}".encode("utf-8")


def make_result_artifact_reference(
    content: bytes, *, metadata: ArtifactMetadata | None = None, **overrides: Any
) -> ArtifactReference:
    """Make result artifact reference -- unlike
    ``_distributed_orchestration_fixtures.make_result_artifact_reference``,
    this variant's ``content_checksum`` is computed from real,
    caller-supplied bytes (required by
    :class:`~src.distributed.artifact_store.InMemoryArtifactStore`'s own
    checksum verification), and ``metadata_checksum`` is bound to a real
    :class:`~src.distributed.artifact_store.ArtifactMetadata`'s own
    checksum (defaulting to synthetic/non-privileged) -- required by the
    MEGB-03H.2C.3B.2B.1 content-bound-classification correction. Pass
    ``metadata=`` explicitly when a test needs the reference bound to a
    non-default classification (e.g. to exercise a policy refusal)."""
    if metadata is None:
        metadata = _DEFAULT_METADATA
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "artifact_kind": ArtifactKind.RESULT_ARTIFACT,
        "artifact_reference_id": "result-artifact-0001",
        "content_checksum": hashlib.sha256(content).hexdigest(),
        "metadata_checksum": metadata.metadata_checksum,
    }
    fields.update(overrides)
    return ArtifactReference(**fields)


def make_result_commit(
    attempt: ExecutionAttempt, content: bytes, **overrides: Any
) -> ResultCommit:
    """Make result commit bound to real, caller-supplied content bytes."""
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "scientific_work_id": attempt.scientific_work_id,
        "attempt_checksum": attempt.attempt_checksum,
        "lease_generation": attempt.lease_generation,
        "result_content_checksum": hashlib.sha256(content).hexdigest(),
        "result_artifact_reference": make_result_artifact_reference(content),
    }
    fields.update(overrides)
    return ResultCommit(**fields)
