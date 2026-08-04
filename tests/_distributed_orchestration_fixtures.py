"""MEGB-03H.2C.3B.2A: synthetic orchestration-contract record factories
shared across the ``test_distributed_*.py`` orchestration test modules --
mirrors ``tests/_distributed_fixtures.py``'s own established pattern for
the B.1 provenance types. No privileged content, no real infrastructure
identifiers, no candidate/case data of any kind."""

import hashlib
from typing import Any

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
)
from src.distributed.provenance import EnvironmentClass
from src.distributed.personal_policy import PersonalEnvironmentPolicy, WorkloadClass
from src.distributed.work_contracts import (
    Acknowledgement,
    ArtifactKind,
    ArtifactReference,
    CancellationRequest,
    CancellationScope,
    ExecutionAttempt,
    QueueWorkMessage,
    ResultCommit,
    TerminalDisposition,
    TerminalDispositionKind,
    TerminalDispositionReason,
    WorkDescriptor,
    work_descriptor_to_queue_message,
)
from src.distributed.worker_contracts import Lease, LeaseRenewal, WorkerRegistration


def make_sha256(seed: str) -> str:
    """A deterministic, valid-shaped sha256 hex digest from ``seed`` --
    never a real credential or content hash, purely a synthetic
    placeholder shared by every fixture below."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def make_run_context_checksum(seed: str = "synthetic-run-context") -> str:
    """A synthetic, sha256-shaped stand-in for a real
    ``DistributedRunContext.run_context_checksum`` -- this module never
    imports ``src.distributed.provenance``'s own context builders,
    keeping orchestration-contract fixtures independent of B.1's own
    fixtures."""
    return make_sha256(seed)


def make_candidate_artifact_reference(**overrides: Any) -> ArtifactReference:
    """Make candidate artifact reference."""
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "artifact_kind": ArtifactKind.CANDIDATE_MANIFEST_ENTRY,
        "artifact_reference_id": "candidate-manifest-entry-0001",
        "artifact_checksum": make_sha256("candidate-content"),
    }
    fields.update(overrides)
    return ArtifactReference(**fields)


def make_result_artifact_reference(**overrides: Any) -> ArtifactReference:
    """Make result artifact reference."""
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "artifact_kind": ArtifactKind.RESULT_ARTIFACT,
        "artifact_reference_id": "result-artifact-0001",
        "artifact_checksum": make_sha256("result-content"),
    }
    fields.update(overrides)
    return ArtifactReference(**fields)


def make_work_descriptor(**overrides: Any) -> WorkDescriptor:
    """Make work descriptor."""
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "scientific_work_id": "work-0000000000000001",
        "input_ordinal": 0,
        "distributed_run_context_checksum": make_run_context_checksum(),
        "candidate_artifact_reference": make_candidate_artifact_reference(),
    }
    fields.update(overrides)
    return WorkDescriptor(**fields)


def make_queue_work_message(**overrides: Any) -> QueueWorkMessage:
    """Make queue work message."""
    descriptor_overrides = overrides.pop("descriptor_overrides", None)
    descriptor = make_work_descriptor(**(descriptor_overrides or {}))
    fields: dict[str, Any] = {
        "delivery_id": "delivery-0000000000000001",
        "routing_environment_class": EnvironmentClass.PERSONAL_BOOTSTRAP.value,
        "routing_logical_environment_id": "env-logical-0000000000000001",
        "lease_generation": None,
        "attempt_checksum": None,
    }
    fields.update(overrides)
    return work_descriptor_to_queue_message(descriptor, **fields)


def make_execution_attempt(**overrides: Any) -> ExecutionAttempt:
    """Make execution attempt."""
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "scientific_work_id": "work-0000000000000001",
        "worker_participant_id": "worker-participant-a",
        "lease_generation": 1,
        "distributed_run_context_checksum": make_run_context_checksum(),
    }
    fields.update(overrides)
    return ExecutionAttempt(**fields)


def make_result_commit(attempt: ExecutionAttempt | None = None, **overrides: Any) -> ResultCommit:
    """Make result commit."""
    attempt = attempt if attempt is not None else make_execution_attempt()
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "scientific_work_id": attempt.scientific_work_id,
        "attempt_checksum": attempt.attempt_checksum,
        "lease_generation": attempt.lease_generation,
        "result_content_checksum": make_sha256("result-content"),
        "result_artifact_reference": make_result_artifact_reference(),
    }
    fields.update(overrides)
    return ResultCommit(**fields)


def make_acknowledgement(commit: ResultCommit | None = None, **overrides: Any) -> Acknowledgement:
    """Make acknowledgement."""
    commit = commit if commit is not None else make_result_commit()
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "scientific_work_id": commit.scientific_work_id,
        "attempt_checksum": commit.attempt_checksum,
        "result_content_checksum": commit.result_content_checksum,
    }
    fields.update(overrides)
    return Acknowledgement(**fields)


def make_cancellation_request(**overrides: Any) -> CancellationRequest:
    """Make cancellation request."""
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "scientific_work_id": "work-0000000000000001",
        "cancellation_scope": CancellationScope.BEFORE_ADMISSION,
        "requested_at_logical_clock": 0,
    }
    fields.update(overrides)
    return CancellationRequest(**fields)


def make_terminal_disposition(**overrides: Any) -> TerminalDisposition:
    """Make terminal disposition."""
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "scientific_work_id": "work-0000000000000001",
        "disposition": TerminalDispositionKind.COMPLETED_ACKNOWLEDGED,
        "disposition_reason": TerminalDispositionReason.NORMAL_COMPLETION,
        "attempt_count": 1,
    }
    fields.update(overrides)
    return TerminalDisposition(**fields)


def make_worker_registration(**overrides: Any) -> WorkerRegistration:
    """Make worker registration."""
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "worker_participant_id": "worker-participant-a",
        "distributed_run_context_checksum": make_run_context_checksum(),
        "registered_at_logical_clock": 0,
    }
    fields.update(overrides)
    return WorkerRegistration(**fields)


def make_lease(**overrides: Any) -> Lease:
    """Make lease."""
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "scientific_work_id": "work-0000000000000001",
        "worker_participant_id": "worker-participant-a",
        "lease_generation": 1,
        "lease_issued_at_logical_clock": 0,
        "lease_duration_logical_ticks": 10,
    }
    fields.update(overrides)
    return Lease(**fields)


def make_lease_renewal(lease: Lease | None = None, **overrides: Any) -> LeaseRenewal:
    """Make lease renewal."""
    lease = lease if lease is not None else make_lease()
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "scientific_work_id": lease.scientific_work_id,
        "worker_participant_id": lease.worker_participant_id,
        "lease_generation": lease.lease_generation,
        "renewed_at_logical_clock": lease.lease_issued_at_logical_clock + 1,
    }
    fields.update(overrides)
    return LeaseRenewal(**fields)


def make_personal_environment_policy(**overrides: Any) -> PersonalEnvironmentPolicy:
    """Make personal environment policy."""
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "environment_class": EnvironmentClass.PERSONAL_BOOTSTRAP,
        "allowed_workload_classes": tuple(
            sorted(
                (WorkloadClass.SYNTHETIC_SMOKE, WorkloadClass.SYNTHETIC_QUALIFICATION_CANDIDATE),
                key=lambda item: item.value,
            )
        ),
        "max_admitted_workers": 2,
        "spending_ceiling_usd": 50.0,
    }
    fields.update(overrides)
    return PersonalEnvironmentPolicy(**fields)
