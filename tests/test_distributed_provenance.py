"""MEGB-03H.2C.3B.1: construction, validation, immutability, round-trip,
checksum-tamper, and version-rejection tests for
``src.distributed.provenance`` and ``src.distributed.protected_mapping``.
"""

import dataclasses
from typing import Any

import pytest

from src.distributed._checksums import (
    InvalidDistributedProvenanceError,
    UnsupportedChecksumAlgorithmVersionError,
    UnsupportedDistributedProvenanceSchemaVersionError,
)
from src.distributed.protected_mapping import (
    ProtectedOperationalMapping,
    protected_operational_mapping_from_dict,
    protected_operational_mapping_to_dict,
)
from src.distributed.provenance import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
    DistributedRunIntent,
    EnvironmentClass,
    ProvisioningClass,
    distributed_run_context_from_dict,
    distributed_run_context_to_dict,
    retry_lease_policy_from_dict,
    retry_lease_policy_to_dict,
    worker_execution_context_from_dict,
    worker_execution_context_to_dict,
)
from tests._distributed_fixtures import (
    make_retry_lease_policy,
    make_run_and_worker,
    make_run_context,
    make_worker_context,
)

# ---------------------------------------------------------------------------
# 1. Construction and validation
# ---------------------------------------------------------------------------


def test_run_context_constructs_and_computes_checksum() -> None:
    """Test run context constructs and computes checksum."""
    context = make_run_context()
    assert len(context.run_context_checksum) == 64
    assert context.environment_class == EnvironmentClass.PERSONAL_BOOTSTRAP


def test_worker_context_constructs_and_computes_checksum() -> None:
    """Test worker context constructs and computes checksum."""
    run_context, worker = make_run_and_worker()
    assert worker.parent_run_context_checksum == run_context.run_context_checksum
    assert len(worker.worker_context_checksum) == 64


def test_retry_lease_policy_rejects_non_positive_lease_duration() -> None:
    """Test retry lease policy rejects non positive lease duration."""
    with pytest.raises(InvalidDistributedProvenanceError, match="lease_duration_sec"):
        make_retry_lease_policy(lease_duration_sec=0.0)


def test_worker_context_rejects_invalid_zone() -> None:
    """Test worker context rejects invalid zone."""
    with pytest.raises(InvalidDistributedProvenanceError, match="zone"):
        make_worker_context(zone="")


def test_worker_context_accepts_none_zone() -> None:
    """Test worker context accepts none zone."""
    worker = make_worker_context(zone=None)
    assert worker.zone is None


def test_worker_context_accepts_present_zone() -> None:
    """Test worker context accepts present zone."""
    worker = make_worker_context(zone="us-central1-a")
    assert worker.zone == "us-central1-a"


def test_run_context_rejects_non_enum_environment_class() -> None:
    """Test run context rejects non enum environment class."""
    with pytest.raises(InvalidDistributedProvenanceError, match="environment_class"):
        make_run_context(environment_class="PERSONAL_BOOTSTRAP")


def test_run_context_rejects_bad_network_isolation_checksum() -> None:
    """Test run context rejects bad network isolation checksum."""
    with pytest.raises(
        InvalidDistributedProvenanceError, match="network_isolation_policy_checksum"
    ):
        make_run_context(network_isolation_policy_checksum="not-a-sha256")


def test_worker_context_rejects_bad_worker_image_digest() -> None:
    """Test worker context rejects bad worker image digest."""
    with pytest.raises(InvalidDistributedProvenanceError, match="worker_image_digest"):
        make_worker_context(worker_image_digest="short")


# ---------------------------------------------------------------------------
# 2. Immutability
# ---------------------------------------------------------------------------


def test_run_context_is_frozen() -> None:
    """Test run context is frozen."""
    context = make_run_context()
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.distributed_run_id = "other"  # type: ignore[misc]


def test_worker_context_is_frozen() -> None:
    """Test worker context is frozen."""
    _, worker = make_run_and_worker()
    with pytest.raises(dataclasses.FrozenInstanceError):
        worker.region = "us-east1"  # type: ignore[misc]


def test_retry_lease_policy_is_frozen() -> None:
    """Test retry lease policy is frozen."""
    policy = make_retry_lease_policy()
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.retry_ceiling = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. Deterministic round trips
# ---------------------------------------------------------------------------


def test_run_context_round_trip() -> None:
    """Test run context round trip."""
    context = make_run_context()
    restored = distributed_run_context_from_dict(distributed_run_context_to_dict(context))
    assert restored == context


def test_worker_context_round_trip() -> None:
    """Test worker context round trip."""
    _, worker = make_run_and_worker()
    restored = worker_execution_context_from_dict(worker_execution_context_to_dict(worker))
    assert restored == worker


def test_round_trip_is_byte_stable() -> None:
    """Test round trip is byte stable."""
    context = make_run_context()
    payload_1 = distributed_run_context_to_dict(context)
    payload_2 = distributed_run_context_to_dict(
        distributed_run_context_from_dict(payload_1)
    )
    assert payload_1 == payload_2


# ---------------------------------------------------------------------------
# 4. Checksum tampering
# ---------------------------------------------------------------------------


def test_run_context_checksum_tampering_detected() -> None:
    """Test run context checksum tampering detected."""
    context = make_run_context()
    payload = distributed_run_context_to_dict(context)
    payload["distributed_run_id"] = "tampered-run-id"
    with pytest.raises(InvalidDistributedProvenanceError, match="run_context_checksum"):
        distributed_run_context_from_dict(payload)


def test_worker_context_checksum_tampering_detected() -> None:
    """Test worker context checksum tampering detected."""
    _, worker = make_run_and_worker()
    payload = worker_execution_context_to_dict(worker)
    payload["machine_type"] = "c2-standard-8"
    with pytest.raises(InvalidDistributedProvenanceError, match="worker_context_checksum"):
        worker_execution_context_from_dict(payload)


def test_retry_lease_policy_checksum_tampering_detected() -> None:
    """Test retry lease policy checksum tampering detected."""
    policy = make_retry_lease_policy()
    payload = retry_lease_policy_to_dict(policy)
    payload["retry_ceiling"] = 99
    with pytest.raises(InvalidDistributedProvenanceError, match="policy_checksum"):
        retry_lease_policy_from_dict(payload)


# ---------------------------------------------------------------------------
# 5. Unsupported schema / checksum-algorithm versions
# ---------------------------------------------------------------------------


def test_run_context_rejects_unsupported_schema_version() -> None:
    """Test run context rejects unsupported schema version."""
    with pytest.raises(UnsupportedDistributedProvenanceSchemaVersionError):
        make_run_context(distributed_provenance_schema_version="some-other-v1")


def test_run_context_rejects_unsupported_checksum_algorithm_version() -> None:
    """Test run context rejects unsupported checksum algorithm version."""
    with pytest.raises(UnsupportedChecksumAlgorithmVersionError):
        make_run_context(checksum_algorithm_version="md5-v1")


def test_worker_context_rejects_unsupported_schema_version() -> None:
    """Test worker context rejects unsupported schema version."""
    with pytest.raises(UnsupportedDistributedProvenanceSchemaVersionError):
        make_worker_context(distributed_provenance_schema_version="some-other-v1")


def test_retry_lease_policy_rejects_unsupported_checksum_algorithm_version() -> None:
    """Test retry lease policy rejects unsupported checksum algorithm version."""
    with pytest.raises(UnsupportedChecksumAlgorithmVersionError):
        make_retry_lease_policy(checksum_algorithm_version="md5-v1")


# ---------------------------------------------------------------------------
# 6. Missing required fields
# ---------------------------------------------------------------------------


def test_run_context_from_dict_missing_field_raises() -> None:
    """Test run context from dict missing field raises."""
    context = make_run_context()
    payload = distributed_run_context_to_dict(context)
    del payload["cloud_provider"]
    with pytest.raises(InvalidDistributedProvenanceError, match="missing required"):
        distributed_run_context_from_dict(payload)


def test_worker_context_from_dict_missing_field_raises() -> None:
    """Test worker context from dict missing field raises."""
    _, worker = make_run_and_worker()
    payload = worker_execution_context_to_dict(worker)
    del payload["machine_type"]
    with pytest.raises(InvalidDistributedProvenanceError, match="missing required"):
        worker_execution_context_from_dict(payload)


# ---------------------------------------------------------------------------
# 7. Different identities change the checksum (the concept-by-concept list)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"environment_class": EnvironmentClass.COMPANY_PLAYGROUND},
        {"coordinator_implementation_version": "2.0.0"},
        {"worker_fleet_implementation_version": "2.0.0"},
        {"queue_implementation_version": "2.0.0"},
        {"object_store_implementation_version": "2.0.0"},
        {"network_isolation_policy_checksum": "f" * 64},
        {"deployment_topology_policy_version": "2.0.0"},
        {"distributed_run_id": "distributed-run-0002"},
        {"logical_environment_id": "env-logical-0000000000000002"},
        {"run_intent": DistributedRunIntent.SMOKE_TEST},
    ],
)
def test_run_context_field_changes_change_checksum(override: dict[str, Any]) -> None:
    """Test run context field changes change checksum."""
    baseline = make_run_context()
    changed = make_run_context(**override)
    assert changed.run_context_checksum != baseline.run_context_checksum


@pytest.mark.parametrize(
    "override",
    [
        {"region": "us-east1"},
        {"machine_type": "c2-standard-8"},
        {"cpu_architecture": "arm64"},
        {"provisioning_class": ProvisioningClass.SPOT},
        {"worker_image_digest": "9" * 64},
        {"worker_image_digest_scheme_version": "worker-image-digest-v2"},
        {"worker_implementation_version": "2.0.0"},
        {"host_runtime_identity_checksum": "1" * 64},
        {"telemetry_policy_identity_checksum": "2" * 64},
        {"zone": "us-central1-a"},
    ],
)
def test_worker_context_field_changes_change_checksum(override: dict[str, Any]) -> None:
    """Test worker context field changes change checksum."""
    run_context, baseline = make_run_and_worker()
    changed = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum, **override
    )
    assert changed.worker_context_checksum != baseline.worker_context_checksum


def test_run_context_retry_lease_policy_change_changes_checksum() -> None:
    """Test run context retry lease policy change changes checksum."""
    baseline = make_run_context()
    changed = make_run_context(retry_lease_policy=make_retry_lease_policy(retry_ceiling=9))
    assert changed.run_context_checksum != baseline.run_context_checksum


# ---------------------------------------------------------------------------
# 8. Same labels, different content-bound image identities -> not equal
# ---------------------------------------------------------------------------


def test_same_labels_different_worker_image_digest_are_distinct() -> None:
    """Test same labels different worker image digest are distinct."""
    run_context, _ = make_run_and_worker()
    worker_a = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        worker_image_digest="a" * 64,
    )
    worker_b = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        worker_image_digest="b" * 64,
    )
    assert worker_a.worker_context_checksum != worker_b.worker_context_checksum
    assert worker_a != worker_b


# ---------------------------------------------------------------------------
# 9. Personal vs. company separation
# ---------------------------------------------------------------------------


def test_personal_and_company_contexts_are_distinct_even_with_matching_other_fields() -> None:
    """Test personal and company contexts are distinct even with matching other fields."""
    personal = make_run_context(environment_class=EnvironmentClass.PERSONAL_BOOTSTRAP)
    company = make_run_context(environment_class=EnvironmentClass.COMPANY_PLAYGROUND)
    assert personal.run_context_checksum != company.run_context_checksum
    assert personal != company


def test_spot_and_on_demand_are_distinct() -> None:
    """Test spot and on demand are distinct."""
    run_context, _ = make_run_and_worker()
    spot = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        provisioning_class=ProvisioningClass.SPOT,
    )
    on_demand = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        provisioning_class=ProvisioningClass.ON_DEMAND,
    )
    assert spot.worker_context_checksum != on_demand.worker_context_checksum


# ---------------------------------------------------------------------------
# 10. ProtectedOperationalMapping
# ---------------------------------------------------------------------------


def _make_mapping(**overrides: object) -> ProtectedOperationalMapping:
    fields: dict[str, object] = {
        "distributed_provenance_schema_version": DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
        "checksum_algorithm_version": CHECKSUM_ALGORITHM_VERSION,
        "logical_environment_id": "env-logical-0000000000000001",
        "raw_cloud_project_id": "example-project-42",
        "raw_subscription_or_account_id": None,
        "raw_instance_identifiers": ("instance-a",),
        "raw_hostnames": ("worker-1.internal",),
        "raw_container_ids": ("abc123",),
        "raw_filesystem_paths": ("/var/lib/worker",),
        "raw_service_account_identities": ("sa@example.iam.gserviceaccount.com",),
        "raw_credential_references": ("projects/x/secrets/y/versions/1",),
        "raw_resource_names": ("queue-topic-a",),
    }
    fields.update(overrides)
    return ProtectedOperationalMapping(**fields)  # type: ignore[arg-type]


def test_protected_mapping_constructs_and_round_trips() -> None:
    """Test protected mapping constructs and round trips."""
    mapping = _make_mapping()
    restored = protected_operational_mapping_from_dict(
        protected_operational_mapping_to_dict(mapping)
    )
    assert restored == mapping


def test_protected_mapping_checksum_tampering_detected() -> None:
    """Test protected mapping checksum tampering detected."""
    mapping = _make_mapping()
    payload = protected_operational_mapping_to_dict(mapping)
    payload["raw_cloud_project_id"] = "tampered-project"
    with pytest.raises(InvalidDistributedProvenanceError, match="mapping_checksum"):
        protected_operational_mapping_from_dict(payload)


@pytest.mark.parametrize(
    "field_name,secret_value",
    [
        (
            "raw_credential_references",
            "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
        ),
        ("raw_credential_references", '{"type": "service_account", "project_id": "x"}'),
        ("raw_credential_references", "AKIAIOSFODNN7EXAMPLE"),
        ("raw_service_account_identities", "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ0123456"),
        ("raw_credential_references", "ya29.a0ARrdaM_example_token_value_here"),
        ("raw_credential_references", "xoxb-1234-abcdefghijklmnop"),
        ("raw_cloud_project_id", "-----BEGIN RSA PRIVATE KEY-----"),
    ],
)
def test_protected_mapping_rejects_secret_shaped_values(field_name: str, secret_value: str) -> None:
    """Test protected mapping rejects secret shaped values."""
    overrides: dict[str, object] = {}
    if field_name == "raw_cloud_project_id":
        overrides[field_name] = secret_value
    else:
        overrides[field_name] = (secret_value,)
    with pytest.raises(InvalidDistributedProvenanceError):
        _make_mapping(**overrides)


def test_protected_mapping_rejects_empty_raw_identifiers() -> None:
    """Test protected mapping rejects empty raw identifiers."""
    with pytest.raises(InvalidDistributedProvenanceError):
        _make_mapping(raw_instance_identifiers=("",))
