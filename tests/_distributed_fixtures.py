"""Synthetic distributed-provenance record factories shared across the
``test_distributed_*.py`` modules.

Every factory builds a structurally valid record by default, with any
field overridable via keyword arguments -- mirrors
``tests/_calibration_fixtures.py``'s own established pattern. No
privileged content, no real infrastructure identifiers, no candidate/case
data of any kind.
"""

from typing import Any

from src.distributed.provenance import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
    CloudProvider,
    DistributedRunContext,
    DistributedRunIntent,
    EnvironmentClass,
    ProvisioningClass,
    RetryLeasePolicy,
    WorkerExecutionContext,
)


def make_retry_lease_policy(**overrides: Any) -> RetryLeasePolicy:
    """Make retry lease policy."""
    fields: dict[str, Any] = {
        "lease_duration_sec": 30.0,
        "retry_ceiling": 3,
        "dead_letter_threshold": 5,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
    }
    fields.update(overrides)
    return RetryLeasePolicy(**fields)


def make_run_context(**overrides: Any) -> DistributedRunContext:
    """Make run context."""
    fields: dict[str, Any] = {
        "distributed_provenance_schema_version": DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "environment_class": EnvironmentClass.PERSONAL_BOOTSTRAP,
        "logical_environment_id": "env-logical-0000000000000001",
        "run_intent": DistributedRunIntent.QUALIFICATION_CANDIDATE,
        "distributed_run_id": "distributed-run-0001",
        "cloud_provider": CloudProvider.GCP,
        "coordinator_implementation_id": "coordinator",
        "coordinator_implementation_version": "1.0.0",
        "worker_fleet_implementation_id": "fleet-controller",
        "worker_fleet_implementation_version": "1.0.0",
        "queue_implementation_id": "pubsub",
        "queue_implementation_version": "1.0.0",
        "object_store_implementation_id": "gcs",
        "object_store_implementation_version": "1.0.0",
        "network_isolation_policy_checksum": "a" * 64,
        "retry_lease_policy": make_retry_lease_policy(),
        "deployment_topology_policy_id": "single-zone-single-fleet",
        "deployment_topology_policy_version": "1.0.0",
    }
    fields.update(overrides)
    return DistributedRunContext(**fields)


def make_worker_context(
    parent_run_context_checksum: str | None = None, **overrides: Any
) -> WorkerExecutionContext:
    """Make worker context."""
    fields: dict[str, Any] = {
        "distributed_provenance_schema_version": DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "parent_run_context_checksum": (
            parent_run_context_checksum
            if parent_run_context_checksum is not None
            else "b" * 64
        ),
        "worker_participant_id": "worker-participant-0000000000001",
        "region": "us-central1",
        "zone": None,
        "machine_type": "n2-standard-4",
        "cpu_architecture": "x86_64",
        "provisioning_class": ProvisioningClass.ON_DEMAND,
        "worker_image_digest": "c" * 64,
        "worker_image_digest_scheme_version": "worker-image-digest-v1",
        "worker_implementation_id": "worker",
        "worker_implementation_version": "1.0.0",
        "host_runtime_identity_checksum": "d" * 64,
        "telemetry_policy_identity_checksum": "e" * 64,
    }
    fields.update(overrides)
    return WorkerExecutionContext(**fields)


def make_run_and_worker(
    run_overrides: dict[str, Any] | None = None,
    worker_overrides: dict[str, Any] | None = None,
) -> tuple[DistributedRunContext, WorkerExecutionContext]:
    """Build one mutually-consistent (run_context, worker_context) pair --
    ``worker_context.parent_run_context_checksum`` is always
    ``run_context.run_context_checksum``."""
    run_context = make_run_context(**(run_overrides or {}))
    worker_context = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        **(worker_overrides or {}),
    )
    return run_context, worker_context


def make_two_region_workers(
    run_context: DistributedRunContext,
) -> tuple[WorkerExecutionContext, WorkerExecutionContext]:
    """Two distinct, mutually-consistent worker contexts under
    ``run_context``, differing in participant id, region, and worker-
    image digest -- shared by every test proving a run can use multiple
    workers/zones without misrepresenting them as one homogeneous
    worker."""
    worker_a = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        worker_participant_id="worker-participant-a",
        region="us-central1",
    )
    worker_b = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        worker_participant_id="worker-participant-b",
        region="us-east1",
        worker_image_digest="9" * 64,
    )
    return worker_a, worker_b


def make_homogeneous_workers(
    run_context: DistributedRunContext, count: int
) -> tuple[WorkerExecutionContext, ...]:
    """``count`` distinct execution participants sharing byte-identical
    configuration provenance (region, machine type, image, provisioning
    class) -- the legitimate "homogeneous fleet" case: distinct
    participants, not duplicates, per the MEGB-03H.2C.3B.1 conformance
    audit's correction 2 (two workers with identical configuration
    provenance must not be rejected merely for that reason)."""
    return tuple(
        make_worker_context(
            parent_run_context_checksum=run_context.run_context_checksum,
            worker_participant_id=f"worker-participant-{i:04d}",
        )
        for i in range(count)
    )
