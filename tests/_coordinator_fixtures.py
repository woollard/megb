"""MEGB-03H.2C.3B.2B.2: shared synthetic fixtures for the
``test_coordinator_*``/``test_queue_adapter``/``test_audit_outbox``/
``test_artifact_capabilities`` test modules. No privileged content, no
real infrastructure identifiers, no candidate/case data of any kind --
every content-bearing fixture below produces harmless synthetic bytes
only."""

# pylint: disable=duplicate-code
# This module's own field-dict boilerplate inherently mirrors
# tests/_atomic_stores_fixtures.py's own builders (both build the same
# underlying B.2A/B.2B.1 dataclasses) -- shared boilerplate, not shared
# logic, per this project's own established convention.

import hashlib
from dataclasses import dataclass
from typing import Any

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
)
from src.distributed.artifact_store import ArtifactMetadata, InMemoryArtifactStore
from src.distributed.atomic_work_store import AtomicWorkStore
from src.distributed.audit_outbox import InMemoryAuditOutbox
from src.distributed.audit_sink_store import InMemoryAuditSink
from src.distributed.budget_store import AtomicBudgetStore
from src.distributed.cancellation import CancellationController
from src.distributed.clock import LogicalClock
from src.distributed.coordinator import Coordinator
from src.distributed.coordinator_config import CoordinatorConfig
from src.distributed.executor import (
    ExecutorFailureReason,
    ExecutorInvocationResult,
    WorkExecutorProtocol,
    executor_failure,
    executor_success,
)
from src.distributed.personal_policy import (
    PERSONAL_BOOTSTRAP_MAX_WORKERS,
    PERSONAL_BOOTSTRAP_SPENDING_CEILING_CENTS,
    DataClassification,
    PersonalEnvironmentPolicy,
    WorkloadClass,
)
from src.distributed.provenance import EnvironmentClass
from src.distributed.queue_adapter import InMemoryAtLeastOnceQueue
from src.distributed.work_contracts import ArtifactKind, ArtifactReference, WorkDescriptor
from src.distributed.worker_contracts import WorkerRegistration
from src.distributed.worker_registry_store import InMemoryWorkerRegistry
from tests._distributed_orchestration_fixtures import make_sha256

ROUTING_ENVIRONMENT_CLASS = EnvironmentClass.PERSONAL_BOOTSTRAP.value
ROUTING_LOGICAL_ENVIRONMENT_ID = "env-logical-coordinator-tests"
RUN_CTX = make_sha256("coordinator-run-context")


def make_synthetic_content(seed: str) -> bytes:
    """Harmless synthetic bytes -- never real candidate/oracle/benchmark
    content."""
    return f"synthetic-coordinator-content-{seed}".encode("utf-8")


def make_default_policy(**overrides: Any) -> PersonalEnvironmentPolicy:
    """A personal-bootstrap policy at exactly the accepted ceilings,
    unless overridden."""
    fields: dict[str, Any] = {
        "distributed_orchestration_schema_version": DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "environment_class": EnvironmentClass.PERSONAL_BOOTSTRAP,
        "allowed_workload_classes": (WorkloadClass.SYNTHETIC_SMOKE,),
        "max_admitted_workers": PERSONAL_BOOTSTRAP_MAX_WORKERS,
        "spending_ceiling_cents": PERSONAL_BOOTSTRAP_SPENDING_CEILING_CENTS,
    }
    fields.update(overrides)
    return PersonalEnvironmentPolicy(**fields)


def make_default_config(**overrides: Any) -> CoordinatorConfig:
    """A default CoordinatorConfig at the accepted personal-bootstrap
    ceiling, unless overridden."""
    fields: dict[str, Any] = {
        "max_admitted_workers": PERSONAL_BOOTSTRAP_MAX_WORKERS,
        "max_in_flight_work": 10,
        "lease_duration_ticks": 5,
        "visibility_timeout_ticks": 5,
        "heartbeat_interval_ticks": 2,
        "audit_outbox_max_pending": 10,
    }
    fields.update(overrides)
    return CoordinatorConfig(**fields)


def publish_candidate(
    artifact_store: InMemoryArtifactStore,
    content: bytes,
    *,
    reference_id: str = "candidate-0001",
    workload_class: WorkloadClass = WorkloadClass.SYNTHETIC_SMOKE,
    data_classification: DataClassification = DataClassification.SYNTHETIC,
) -> ArtifactReference:
    """The one, trusted-publisher-only path a candidate artifact ever
    enters an artifact store through in these tests -- direct ``put``,
    never through the coordinator/worker engine, which never authors a
    candidate artifact itself."""
    metadata = ArtifactMetadata(
        workload_class=workload_class, data_classification=data_classification
    )
    reference = ArtifactReference(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        artifact_kind=ArtifactKind.CANDIDATE_MANIFEST_ENTRY,
        artifact_reference_id=reference_id,
        content_checksum=hashlib.sha256(content).hexdigest(),
        metadata_checksum=metadata.metadata_checksum,
    )
    artifact_store.put(reference, content, metadata)
    return reference


def make_work_descriptor(
    scientific_work_id: str,
    input_ordinal: int,
    candidate_reference: ArtifactReference,
    *,
    run_context_checksum: str = RUN_CTX,
) -> WorkDescriptor:
    """A synthetic WorkDescriptor referencing an already-published
    candidate artifact."""
    return WorkDescriptor(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        scientific_work_id=scientific_work_id,
        input_ordinal=input_ordinal,
        distributed_run_context_checksum=run_context_checksum,
        candidate_artifact_reference=candidate_reference,
    )


def make_worker_registration(
    worker_participant_id: str, *, run_context_checksum: str = RUN_CTX, logical_clock: int = 0
) -> WorkerRegistration:
    """A synthetic WorkerRegistration for one worker participant."""
    return WorkerRegistration(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        worker_participant_id=worker_participant_id,
        distributed_run_context_checksum=run_context_checksum,
        registered_at_logical_clock=logical_clock,
    )


class ScriptedExecutor:
    """A synthetic :class:`~src.distributed.executor.WorkExecutorProtocol`
    whose per-invocation behavior is scripted -- the one injected
    "does the scientific work" seam every test uses in place of any real
    execution. Counts invocations and records every ``candidate_content``
    it was called with, so tests can assert the executor was (or, for
    recovery-path tests, was **not**) invoked."""

    def __init__(
        self,
        script: list[ExecutorInvocationResult] | None = None,
        *,
        default_result_content: bytes = b"synthetic-result",
    ) -> None:
        self._script = script
        self._default_result_content = default_result_content
        self.invocation_count = 0
        self.received_contents: list[bytes] = []

    def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
        """Return this call's scripted result, or the default success
        once the script is exhausted."""
        self.invocation_count += 1
        self.received_contents.append(candidate_content)
        if self._script is not None and self.invocation_count <= len(self._script):
            return self._script[self.invocation_count - 1]
        return executor_success(self._default_result_content)


class RaisingExecutor:
    """A synthetic executor that always raises -- for "executor raises
    without leaking its message" tests. The message itself is
    deliberately distinctive so a test can assert it never appears
    anywhere in the resulting safe outcome/audit records."""

    def __init__(self, message: str = "unsafe-diagnostic-should-never-leak") -> None:
        self.message = message
        self.invocation_count = 0

    def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
        """Always raise ``RuntimeError(self.message)``."""
        del candidate_content
        self.invocation_count += 1
        raise RuntimeError(self.message)


def retryable_failure() -> ExecutorInvocationResult:
    """A scripted retryable executor failure."""
    return executor_failure(ExecutorFailureReason.RETRYABLE_EXECUTION_ERROR)


def terminal_failure() -> ExecutorInvocationResult:
    """A scripted terminal (non-retryable) executor failure."""
    return executor_failure(ExecutorFailureReason.TERMINAL_INVALID_OUTPUT)


@dataclass
class CoordinatorEnvironment:  # pylint: disable=too-many-instance-attributes
    """Every synthetic dependency one coordinator test needs, bundled for
    convenient construction. Not itself a checksum-bound orchestration
    type -- purely a test-composition convenience."""

    clock: LogicalClock
    work_store: AtomicWorkStore
    artifact_store: InMemoryArtifactStore
    budget_store: AtomicBudgetStore
    policy: PersonalEnvironmentPolicy
    worker_registry: InMemoryWorkerRegistry
    queue: InMemoryAtLeastOnceQueue
    audit_sink: InMemoryAuditSink
    audit_outbox: InMemoryAuditOutbox
    cancellation: CancellationController
    config: CoordinatorConfig

    def make_coordinator(self, executor: WorkExecutorProtocol) -> Coordinator:
        """Build a Coordinator wired to every store/adapter in this
        environment, plus the given (synthetic) executor."""
        return Coordinator(
            config=self.config,
            clock=self.clock,
            work_store=self.work_store,
            artifact_reader=self.artifact_store,
            artifact_writer=self.artifact_store,
            budget_store=self.budget_store,
            policy=self.policy,
            worker_registry=self.worker_registry,
            queue=self.queue,
            audit_sink=self.audit_sink,
            audit_outbox=self.audit_outbox,
            cancellation=self.cancellation,
            executor=executor,
        )


def build_environment(
    *,
    max_admitted_workers: int = PERSONAL_BOOTSTRAP_MAX_WORKERS,
    max_in_flight_work: int = 10,
    budget_ceiling_cents: int = PERSONAL_BOOTSTRAP_SPENDING_CEILING_CENTS,
) -> CoordinatorEnvironment:
    """One fully-wired, synthetic coordinator environment -- fresh stores,
    a fresh queue/outbox/registry, and one shared fresh logical clock at
    tick 0 (the coordinator and its queue must observe the exact same
    clock, or visibility-timeout/lease-duration ticks would drift out of
    sync)."""
    clock = LogicalClock()
    return CoordinatorEnvironment(
        clock=clock,
        work_store=AtomicWorkStore(),
        artifact_store=InMemoryArtifactStore(),
        budget_store=AtomicBudgetStore(
            budget_ceiling_cents=budget_ceiling_cents, max_admitted_workers=max_admitted_workers
        ),
        policy=make_default_policy(max_admitted_workers=max_admitted_workers),
        worker_registry=InMemoryWorkerRegistry(),
        queue=InMemoryAtLeastOnceQueue(
            clock,
            max_in_flight=max_in_flight_work,
            visibility_timeout_ticks=5,
            routing_environment_class=ROUTING_ENVIRONMENT_CLASS,
            routing_logical_environment_id=ROUTING_LOGICAL_ENVIRONMENT_ID,
        ),
        audit_sink=InMemoryAuditSink(),
        audit_outbox=InMemoryAuditOutbox(max_pending=10),
        cancellation=CancellationController(),
        config=make_default_config(
            max_admitted_workers=max_admitted_workers, max_in_flight_work=max_in_flight_work
        ),
    )
