"""MEGB-03H.2C.3B.1: tests for ``src.distributed.identity`` -- mixed-
worker aggregation, qualification identity, and production identity
projection."""

import dataclasses
from typing import Any

import pytest

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.identity import (
    DuplicateWorkerProvenanceError,
    EmptyWorkerSetError,
    MismatchedWorkerContextError,
    ProductionIdentityProjection,
    aggregate_worker_provenance,
    mixed_worker_provenance_summary_from_dict,
    mixed_worker_provenance_summary_to_dict,
    production_identity_projection_for,
    production_identity_projection_from_dict,
    production_identity_projection_to_dict,
    qualification_identity_for,
    qualification_identity_from_dict,
    qualification_identity_to_dict,
)
from src.distributed.provenance import EnvironmentClass, ProvisioningClass
from tests._distributed_fixtures import (
    make_run_and_worker,
    make_run_context,
    make_two_region_workers,
    make_worker_context,
)

# ---------------------------------------------------------------------------
# Mixed-worker aggregation
# ---------------------------------------------------------------------------


def test_aggregate_rejects_empty_worker_set() -> None:
    """Test aggregate rejects empty worker set."""
    run_context = make_run_context()
    with pytest.raises(EmptyWorkerSetError):
        aggregate_worker_provenance(run_context, ())


def test_aggregate_rejects_mismatched_parent_context() -> None:
    """Test aggregate rejects mismatched parent context."""
    run_a = make_run_context(distributed_run_id="run-a")
    run_b = make_run_context(distributed_run_id="run-b")
    assert run_a.run_context_checksum != run_b.run_context_checksum
    worker_from_b = make_worker_context(parent_run_context_checksum=run_b.run_context_checksum)
    with pytest.raises(MismatchedWorkerContextError):
        aggregate_worker_provenance(run_a, (worker_from_b,))


def test_aggregate_rejects_duplicate_worker_provenance() -> None:
    """Test aggregate rejects duplicate worker provenance."""
    run_context, worker = make_run_and_worker()
    duplicate = make_worker_context(parent_run_context_checksum=run_context.run_context_checksum)
    assert worker.worker_context_checksum == duplicate.worker_context_checksum
    with pytest.raises(DuplicateWorkerProvenanceError):
        aggregate_worker_provenance(run_context, (worker, duplicate))


def test_aggregate_single_worker() -> None:
    """Test aggregate single worker."""
    run_context, worker = make_run_and_worker()
    summary = aggregate_worker_provenance(run_context, (worker,))
    assert summary.worker_context_checksums == (worker.worker_context_checksum,)
    assert summary.distinct_region_count == 1
    assert summary.distinct_provisioning_class_count == 1
    assert summary.distinct_worker_image_digest_count == 1


def test_aggregate_mixed_workers_multiple_regions_and_provisioning_classes() -> None:
    """Test aggregate mixed workers multiple regions and provisioning classes."""
    run_context = make_run_context()
    worker_a = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        region="us-central1",
        provisioning_class=ProvisioningClass.ON_DEMAND,
        worker_image_digest="1" * 64,
    )
    worker_b = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        region="us-east1",
        provisioning_class=ProvisioningClass.SPOT,
        worker_image_digest="2" * 64,
    )
    summary = aggregate_worker_provenance(run_context, (worker_a, worker_b))
    assert summary.distinct_region_count == 2
    assert summary.distinct_provisioning_class_count == 2
    assert summary.distinct_worker_image_digest_count == 2
    # a run with multiple workers/zones/provisioning classes is not
    # misrepresented as one homogeneous worker
    assert len(summary.worker_context_checksums) == 2


def test_aggregate_is_order_independent() -> None:
    """Test aggregate is order independent."""
    run_context = make_run_context()
    worker_a, worker_b = make_two_region_workers(run_context)
    summary_forward = aggregate_worker_provenance(run_context, (worker_a, worker_b))
    summary_backward = aggregate_worker_provenance(run_context, (worker_b, worker_a))
    assert summary_forward.aggregate_checksum == summary_backward.aggregate_checksum
    assert summary_forward == summary_backward


def test_aggregate_is_frozen() -> None:
    """Test aggregate is frozen."""
    run_context, worker = make_run_and_worker()
    summary = aggregate_worker_provenance(run_context, (worker,))
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.distinct_region_count = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# QualificationIdentity
# ---------------------------------------------------------------------------


def test_qualification_identity_deterministic_for_same_content() -> None:
    """Test qualification identity deterministic for same content."""
    run_context, worker = make_run_and_worker()
    summary_1 = aggregate_worker_provenance(run_context, (worker,))
    summary_2 = aggregate_worker_provenance(run_context, (worker,))
    identity_1 = qualification_identity_for(run_context, summary_1)
    identity_2 = qualification_identity_for(run_context, summary_2)
    assert identity_1.identity_checksum == identity_2.identity_checksum


def test_qualification_identity_changes_with_worker_set() -> None:
    """Test qualification identity changes with worker set."""
    run_context = make_run_context()
    worker_a = make_worker_context(parent_run_context_checksum=run_context.run_context_checksum)
    worker_b = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        machine_type="c2-standard-8",
    )
    identity_one_worker = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (worker_a,))
    )
    identity_two_workers = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (worker_a, worker_b))
    )
    assert identity_one_worker.identity_checksum != identity_two_workers.identity_checksum


def test_qualification_identity_rejects_mismatched_summary() -> None:
    """Test qualification identity rejects mismatched summary."""
    run_a = make_run_context(distributed_run_id="run-a")
    run_b = make_run_context(distributed_run_id="run-b")
    worker_b = make_worker_context(parent_run_context_checksum=run_b.run_context_checksum)
    summary_b = aggregate_worker_provenance(run_b, (worker_b,))
    with pytest.raises(MismatchedWorkerContextError):
        qualification_identity_for(run_a, summary_b)


def test_qualification_identity_is_frozen() -> None:
    """Test qualification identity is frozen."""
    run_context, worker = make_run_and_worker()
    identity = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (worker,))
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.identity_checksum = "0" * 64  # type: ignore[misc]


def test_qualification_identity_checksum_tampering_detected() -> None:
    """Test qualification identity checksum tampering detected."""
    run_context, worker = make_run_and_worker()
    identity = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (worker,))
    )
    payload = qualification_identity_to_dict(identity)
    payload["worker_aggregate_checksum"] = "0" * 64
    with pytest.raises(InvalidDistributedProvenanceError, match="identity_checksum"):
        qualification_identity_from_dict(payload)


def test_qualification_identity_round_trip() -> None:
    """Test qualification identity round trip."""
    run_context, worker = make_run_and_worker()
    identity = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (worker,))
    )
    restored = qualification_identity_from_dict(qualification_identity_to_dict(identity))
    assert restored == identity


def test_mixed_worker_summary_round_trip() -> None:
    """Test mixed worker summary round trip."""
    run_context, worker = make_run_and_worker()
    summary = aggregate_worker_provenance(run_context, (worker,))
    restored = mixed_worker_provenance_summary_from_dict(
        mixed_worker_provenance_summary_to_dict(summary)
    )
    assert restored == summary


def test_mixed_worker_summary_checksum_tampering_detected() -> None:
    """Test mixed worker summary checksum tampering detected."""
    run_context, worker = make_run_and_worker()
    summary = aggregate_worker_provenance(run_context, (worker,))
    payload = mixed_worker_provenance_summary_to_dict(summary)
    payload["distinct_region_count"] = 99
    with pytest.raises(InvalidDistributedProvenanceError, match="aggregate_checksum"):
        mixed_worker_provenance_summary_from_dict(payload)


def test_production_identity_projection_round_trip() -> None:
    """Test production identity projection round trip."""
    run_context, worker = make_run_and_worker()
    projection = production_identity_projection_for(run_context, worker)
    restored = production_identity_projection_from_dict(
        production_identity_projection_to_dict(projection)
    )
    assert restored == projection


def test_production_identity_projection_checksum_tampering_detected() -> None:
    """Test production identity projection checksum tampering detected."""
    run_context, worker = make_run_and_worker()
    projection = production_identity_projection_for(run_context, worker)
    payload = production_identity_projection_to_dict(projection)
    payload["machine_type"] = "c2-standard-8"
    with pytest.raises(InvalidDistributedProvenanceError, match="projection_checksum"):
        production_identity_projection_from_dict(payload)


# ---------------------------------------------------------------------------
# ProductionIdentityProjection
# ---------------------------------------------------------------------------


def test_production_identity_projection_deterministic() -> None:
    """Test production identity projection deterministic."""
    run_context, worker = make_run_and_worker()
    projection_1 = production_identity_projection_for(run_context, worker)
    projection_2 = production_identity_projection_for(run_context, worker)
    assert projection_1.projection_checksum == projection_2.projection_checksum


def test_production_identity_projection_rejects_foreign_worker() -> None:
    """Test production identity projection rejects foreign worker."""
    run_a = make_run_context(distributed_run_id="run-a")
    run_b = make_run_context(distributed_run_id="run-b")
    worker_b = make_worker_context(parent_run_context_checksum=run_b.run_context_checksum)
    with pytest.raises(MismatchedWorkerContextError):
        production_identity_projection_for(run_a, worker_b)


@pytest.mark.parametrize(
    "worker_override",
    [
        {"machine_type": "c2-standard-8"},
        {"provisioning_class": ProvisioningClass.SPOT},
        {"worker_image_digest": "9" * 64},
        {"worker_implementation_version": "2.0.0"},
        {"host_runtime_identity_checksum": "1" * 64},
        {"telemetry_policy_identity_checksum": "2" * 64},
    ],
)
def test_production_identity_projection_changes_with_correctness_affecting_fields(
    worker_override: dict[str, Any],
) -> None:
    """Test production identity projection changes with correctness affecting fields."""
    run_context = make_run_context()
    baseline_worker = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum
    )
    changed_worker = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum, **worker_override
    )
    baseline_projection = production_identity_projection_for(run_context, baseline_worker)
    changed_projection = production_identity_projection_for(run_context, changed_worker)
    assert baseline_projection.projection_checksum != changed_projection.projection_checksum


def test_production_identity_projection_field_names_exclude_timing_only_concepts() -> None:
    """region/zone/cpu_architecture are timing-only (Ambiguity 1) and
    coordinator/fleet-version/distributed_run_id are audit-only/non-
    outcome-affecting (Ambiguity 2) -- neither belongs on
    ProductionIdentityProjection at all: structural exclusion (no field
    exists), not merely a value that happens not to change."""
    field_names = {f.name for f in dataclasses.fields(ProductionIdentityProjection)}
    assert "region" not in field_names
    assert "zone" not in field_names
    assert "cpu_architecture" not in field_names
    # audit/recovery-only concepts (Ambiguity 2) also excluded
    assert "coordinator_implementation_version" not in field_names
    assert "worker_fleet_implementation_version" not in field_names
    assert "distributed_run_id" not in field_names


def test_production_identity_projection_is_per_worker_not_per_run() -> None:
    """Two workers in the same run may differ in every production-
    identity field -- each gets its own, independently comparable
    projection."""
    run_context = make_run_context()
    worker_small = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        machine_type="n2-standard-2",
    )
    worker_large = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        machine_type="c2-standard-8",
    )
    projection_small = production_identity_projection_for(run_context, worker_small)
    projection_large = production_identity_projection_for(run_context, worker_large)
    assert projection_small.machine_type != projection_large.machine_type
    assert projection_small.projection_checksum != projection_large.projection_checksum


# ---------------------------------------------------------------------------
# Personal vs. company / environment separation, at the identity level
# ---------------------------------------------------------------------------


def test_personal_and_company_qualification_identities_never_equal() -> None:
    """Test personal and company qualification identities never equal."""
    personal_run = make_run_context(environment_class=EnvironmentClass.PERSONAL_BOOTSTRAP)
    company_run = make_run_context(environment_class=EnvironmentClass.COMPANY_PLAYGROUND)
    personal_worker = make_worker_context(
        parent_run_context_checksum=personal_run.run_context_checksum
    )
    company_worker = make_worker_context(
        parent_run_context_checksum=company_run.run_context_checksum
    )
    personal_identity = qualification_identity_for(
        personal_run, aggregate_worker_provenance(personal_run, (personal_worker,))
    )
    company_identity = qualification_identity_for(
        company_run, aggregate_worker_provenance(company_run, (company_worker,))
    )
    assert personal_identity.identity_checksum != company_identity.identity_checksum
