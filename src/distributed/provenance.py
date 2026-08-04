"""MEGB-03H.2C.3B.1: provider-neutral distributed-execution provenance
schema and identity semantics.

Implements the field-ownership matrix in
``docs/reference/megb-03h2c3b1-provenance-field-matrix.md``, itself a
restatement of the 16 concepts the accepted
``docs/reference/megb-03h2c3a-gcp-provenance-audit.md`` names, as new,
standalone, self-checksummed types. This module does **not** modify any
accepted schema (``src.reference.calibration_schema``, ``result_schema``,
``cache_key``, ``reference_audit``) -- per this checkpoint's own explicit
integration-boundary instruction, those remain untouched; see
``docs/reference/megb-03h2c3b1-integration-map.md`` for exactly what a
later, separately-authorized checkpoint must do to connect this schema to
them.

Two distinct record granularities, mirroring the accepted
``CalibrationRunContext``/``CalibrationInvocationRecord`` run-level/
invocation-level split, but for the *distributed-execution* layer rather
than the calibration layer:

* :class:`DistributedRunContext` -- shared policy/orchestration identity
  for one distributed run (may span many workers, zones, or provisioning
  classes).
* :class:`WorkerExecutionContext` -- the actual execution substrate for
  one worker or invocation, bound to its owning run context by a
  checksum reference (``parent_run_context_checksum``), not by
  embedding -- a run may have many worker contexts, and embedding the
  full run context in each would not change that relationship, only
  bloat every record.

Every self-checksummed type here declares its own
``checksum_algorithm_version`` explicitly (closing the gap concept #16 of
the accepted audit names -- see ``docs/reference/version-registry.md``'s
own ``H5StagingIdentity.identity_checksum()`` "reported gap, not silently
versioned" precedent, which this module does not repeat) and recomputes
its own checksum at construction time, rejecting a caller-supplied value
that does not match -- the same auto-compute-or-reject pattern already
established throughout ``src.reference`` (e.g.
``ReferenceValidationCandidateSetManifest``, every type in
``calibration_schema``).

This module is provider-neutral by construction: no GCP SDK, no
``gcloud``, no Docker, and no import of ``src.reference`` (structurally
enforced by ``tests/test_distributed_dependency_direction.py``, mirroring
``tests/test_execution_dependency_direction.py``'s existing pattern for
``src/execution/``). Managed-model/candidate-generation-plane provenance
is explicitly out of scope -- reserved for MEGB-03H.2C.3G, not designed
here.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from src.distributed._checksums import (  # noqa: F401  (re-exported for callers)
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
    UnsupportedChecksumAlgorithmVersionError,
    UnsupportedDistributedProvenanceSchemaVersionError,
    require_checksum_algorithm_version as _require_checksum_algorithm_version,
    require_non_negative_int as _require_non_negative_int,
    require_nonempty_str as _require_nonempty_str,
    require_positive_float as _require_positive_float,
    require_schema_version as _require_schema_version,
    require_sha256_hex as _require_sha256_hex,
    sha256_of as _sha256_of,
)


# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------


class EnvironmentClass(str, Enum):
    """Which of the two accepted-amendment environments produced a
    record. Closed by design -- no third value exists; a value outside
    this set can never silently pass validation."""

    PERSONAL_BOOTSTRAP = "PERSONAL_BOOTSTRAP"
    COMPANY_PLAYGROUND = "COMPANY_PLAYGROUND"


class DistributedRunIntent(str, Enum):
    """Whether a distributed run was intended to produce H.2C.3D
    qualifying evidence, or is a personal-bootstrap/connectivity smoke
    check -- Ambiguity 3 in the field-ownership matrix. Mirrors
    ``H2C2BQualificationReport.qualifying``/the ``-diagnostic-``
    run-identity-tagging precedent: a typed field, not a convention, is
    what prevents a smoke-test record from being mislabeled as
    qualifying evidence."""

    SMOKE_TEST = "SMOKE_TEST"
    QUALIFICATION_CANDIDATE = "QUALIFICATION_CANDIDATE"


class CloudProvider(str, Enum):
    """Closed, extensible cloud-provider identity. Only ``GCP`` is a
    member today, matching the accepted amendment's own frozen initial
    provider decision -- extensible by adding new members later, never by
    accepting a free-form string."""

    GCP = "GCP"


class ProvisioningClass(str, Enum):
    """Spot vs. On-Demand, tracked per-worker-invocation (not merely a
    run-level default), per the accepted audit's own concept #5
    rationale."""

    SPOT = "SPOT"
    ON_DEMAND = "ON_DEMAND"


# ---------------------------------------------------------------------------
# RetryLeasePolicy (concept #15)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryLeasePolicy:
    """Concept #15: a small, typed retry/lease policy identity, plus its
    own checksum -- not merely a behavior, an identified, comparable
    policy (the accepted audit's own stated gap: "two runs under
    different lease/retry configurations could show different
    completeness/duplication characteristics with no recorded way to
    distinguish which configuration produced a given trace")."""

    lease_duration_sec: float
    retry_ceiling: int
    dead_letter_threshold: int
    checksum_algorithm_version: str
    policy_checksum: str = ""

    def __post_init__(self) -> None:
        _require_checksum_algorithm_version(self)
        _require_positive_float(self, "lease_duration_sec")
        _require_non_negative_int(self, "retry_ceiling")
        _require_non_negative_int(self, "dead_letter_threshold")
        payload = _retry_lease_policy_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.policy_checksum and self.policy_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"policy_checksum {self.policy_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted retry/lease policy"
            )
        object.__setattr__(self, "policy_checksum", expected_checksum)


def _retry_lease_policy_payload(policy: RetryLeasePolicy) -> dict[str, Any]:
    return {
        "checksum_algorithm_version": policy.checksum_algorithm_version,
        "lease_duration_sec": policy.lease_duration_sec,
        "retry_ceiling": policy.retry_ceiling,
        "dead_letter_threshold": policy.dead_letter_threshold,
    }


def retry_lease_policy_to_dict(policy: RetryLeasePolicy) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`RetryLeasePolicy`."""
    return {**_retry_lease_policy_payload(policy), "policy_checksum": policy.policy_checksum}


def retry_lease_policy_from_dict(data: Mapping[str, Any]) -> RetryLeasePolicy:
    """Inverse of :func:`retry_lease_policy_to_dict`."""
    try:
        return RetryLeasePolicy(
            lease_duration_sec=data["lease_duration_sec"],
            retry_ceiling=data["retry_ceiling"],
            dead_letter_threshold=data["dead_letter_threshold"],
            checksum_algorithm_version=data["checksum_algorithm_version"],
            policy_checksum=data["policy_checksum"],
        )
    except KeyError as exc:
        raise InvalidDistributedProvenanceError(
            f"missing required retry/lease policy field: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# DistributedRunContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DistributedRunContext:  # pylint: disable=too-many-instance-attributes
    """Shared policy and orchestration identity for one distributed run.

    Deliberately carries no raw infrastructure identifier -- see
    :class:`ProtectedOperationalMapping` for those, joined back only via
    ``logical_environment_id``. Deliberately carries no candidate-
    generation/managed-model field -- that schema boundary is reserved for
    MEGB-03H.2C.3G, not designed here.

    ``run_context_checksum`` is always recomputed from this object's own
    canonical contents at construction time -- never accepted as an
    unverified caller-provided value, the same auto-compute-or-reject
    pattern used throughout ``src.reference``.
    """

    distributed_provenance_schema_version: str
    checksum_algorithm_version: str
    environment_class: EnvironmentClass
    logical_environment_id: str
    run_intent: DistributedRunIntent
    distributed_run_id: str
    cloud_provider: CloudProvider
    coordinator_implementation_id: str
    coordinator_implementation_version: str
    worker_fleet_implementation_id: str
    worker_fleet_implementation_version: str
    queue_implementation_id: str
    queue_implementation_version: str
    object_store_implementation_id: str
    object_store_implementation_version: str
    network_isolation_policy_checksum: str
    retry_lease_policy: RetryLeasePolicy
    deployment_topology_policy_id: str
    deployment_topology_policy_version: str
    run_context_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _require_schema_version(self)
        _require_checksum_algorithm_version(self)
        if not isinstance(self.environment_class, EnvironmentClass):
            raise InvalidDistributedProvenanceError(
                f"environment_class must be an EnvironmentClass, got {self.environment_class!r}"
            )
        if not isinstance(self.run_intent, DistributedRunIntent):
            raise InvalidDistributedProvenanceError(
                f"run_intent must be a DistributedRunIntent, got {self.run_intent!r}"
            )
        if not isinstance(self.cloud_provider, CloudProvider):
            raise InvalidDistributedProvenanceError(
                f"cloud_provider must be a CloudProvider, got {self.cloud_provider!r}"
            )
        for field_name in (
            "logical_environment_id",
            "distributed_run_id",
            "coordinator_implementation_id",
            "coordinator_implementation_version",
            "worker_fleet_implementation_id",
            "worker_fleet_implementation_version",
            "queue_implementation_id",
            "queue_implementation_version",
            "object_store_implementation_id",
            "object_store_implementation_version",
            "deployment_topology_policy_id",
            "deployment_topology_policy_version",
        ):
            _require_nonempty_str(self, field_name)
        _require_sha256_hex(self, "network_isolation_policy_checksum")
        if not isinstance(self.retry_lease_policy, RetryLeasePolicy):
            raise InvalidDistributedProvenanceError(
                f"retry_lease_policy must be a RetryLeasePolicy, got {self.retry_lease_policy!r}"
            )

        payload = _distributed_run_context_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.run_context_checksum and self.run_context_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"run_context_checksum {self.run_context_checksum!r} does not match the "
                f"recomputed checksum {expected_checksum!r} over its own contents -- tampered "
                f"or corrupted distributed run context"
            )
        object.__setattr__(self, "run_context_checksum", expected_checksum)


def _distributed_run_context_payload(context: DistributedRunContext) -> dict[str, Any]:
    return {
        "distributed_provenance_schema_version": context.distributed_provenance_schema_version,
        "checksum_algorithm_version": context.checksum_algorithm_version,
        "environment_class": context.environment_class.value,
        "logical_environment_id": context.logical_environment_id,
        "run_intent": context.run_intent.value,
        "distributed_run_id": context.distributed_run_id,
        "cloud_provider": context.cloud_provider.value,
        "coordinator_implementation_id": context.coordinator_implementation_id,
        "coordinator_implementation_version": context.coordinator_implementation_version,
        "worker_fleet_implementation_id": context.worker_fleet_implementation_id,
        "worker_fleet_implementation_version": context.worker_fleet_implementation_version,
        "queue_implementation_id": context.queue_implementation_id,
        "queue_implementation_version": context.queue_implementation_version,
        "object_store_implementation_id": context.object_store_implementation_id,
        "object_store_implementation_version": context.object_store_implementation_version,
        "network_isolation_policy_checksum": context.network_isolation_policy_checksum,
        "retry_lease_policy": retry_lease_policy_to_dict(context.retry_lease_policy),
        "deployment_topology_policy_id": context.deployment_topology_policy_id,
        "deployment_topology_policy_version": context.deployment_topology_policy_version,
    }


def distributed_run_context_to_dict(context: DistributedRunContext) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`DistributedRunContext`."""
    return {
        **_distributed_run_context_payload(context),
        "run_context_checksum": context.run_context_checksum,
    }


def distributed_run_context_from_dict(data: Mapping[str, Any]) -> DistributedRunContext:
    """Inverse of :func:`distributed_run_context_to_dict`."""
    try:
        return DistributedRunContext(
            distributed_provenance_schema_version=data["distributed_provenance_schema_version"],
            checksum_algorithm_version=data["checksum_algorithm_version"],
            environment_class=EnvironmentClass(data["environment_class"]),
            logical_environment_id=data["logical_environment_id"],
            run_intent=DistributedRunIntent(data["run_intent"]),
            distributed_run_id=data["distributed_run_id"],
            cloud_provider=CloudProvider(data["cloud_provider"]),
            coordinator_implementation_id=data["coordinator_implementation_id"],
            coordinator_implementation_version=data["coordinator_implementation_version"],
            worker_fleet_implementation_id=data["worker_fleet_implementation_id"],
            worker_fleet_implementation_version=data["worker_fleet_implementation_version"],
            queue_implementation_id=data["queue_implementation_id"],
            queue_implementation_version=data["queue_implementation_version"],
            object_store_implementation_id=data["object_store_implementation_id"],
            object_store_implementation_version=data["object_store_implementation_version"],
            network_isolation_policy_checksum=data["network_isolation_policy_checksum"],
            retry_lease_policy=retry_lease_policy_from_dict(data["retry_lease_policy"]),
            deployment_topology_policy_id=data["deployment_topology_policy_id"],
            deployment_topology_policy_version=data["deployment_topology_policy_version"],
            run_context_checksum=data["run_context_checksum"],
        )
    except KeyError as exc:
        raise InvalidDistributedProvenanceError(
            f"missing required distributed run context field: {exc}"
        ) from exc
    except ValueError as exc:
        raise InvalidDistributedProvenanceError(
            f"malformed distributed run context: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# WorkerExecutionContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkerExecutionContext:  # pylint: disable=too-many-instance-attributes
    """The actual execution substrate for one worker or invocation.

    Bound to its owning :class:`DistributedRunContext` by
    ``parent_run_context_checksum`` (a checksum reference, never a full
    embedding -- a run may have many worker contexts across many zones/
    provisioning classes; see :func:`aggregate_worker_provenance`).

    Deliberately carries no raw instance identifier, hostname, or display
    name -- identity here is purely by content
    (``worker_context_checksum``), per the authorization's own rule that
    "run IDs, timestamps, instance IDs, display names, and retry-attempt
    IDs must not create false cache misses unless their semantics
    genuinely affect outcomes." ``zone`` is optional and, even when
    present, is deliberately excluded from :class:`SafeRedactedSummary`
    (see the field-ownership matrix's concept #3 rationale) to avoid
    per-record infrastructure-topology fingerprinting.

    ``host_runtime_identity_checksum``/``telemetry_policy_identity_checksum``
    are opaque, provider-neutral cross-references to the accepted
    ``HostRuntimeContext.host_context_checksum``/
    ``TelemetryCollectionPolicy.policy_checksum`` concepts (concept #14) --
    computed with the exact same canonical-JSON sha256 scheme
    (:data:`CHECKSUM_ALGORITHM_VERSION`) so they can be reconciled
    byte-for-byte against those calibration-schema checksums once a later,
    separately-authorized checkpoint performs the integration described in
    ``docs/reference/megb-03h2c3b1-integration-map.md``. This module does
    not embed or reconstruct ``HostRuntimeContext``/``TelemetryCollectionPolicy``
    themselves -- that would require importing ``src.reference``, which
    this module must never do.
    """

    distributed_provenance_schema_version: str
    checksum_algorithm_version: str
    parent_run_context_checksum: str
    region: str
    zone: str | None
    machine_type: str
    cpu_architecture: str
    provisioning_class: ProvisioningClass
    worker_image_digest: str
    worker_image_digest_scheme_version: str
    worker_implementation_id: str
    worker_implementation_version: str
    host_runtime_identity_checksum: str
    telemetry_policy_identity_checksum: str
    worker_context_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _require_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_sha256_hex(self, "parent_run_context_checksum")
        for field_name in (
            "region",
            "machine_type",
            "cpu_architecture",
            "worker_image_digest_scheme_version",
            "worker_implementation_id",
            "worker_implementation_version",
        ):
            _require_nonempty_str(self, field_name)
        if self.zone is not None and (not isinstance(self.zone, str) or self.zone == ""):
            raise InvalidDistributedProvenanceError(
                f"zone must be a nonempty string or None, got {self.zone!r}"
            )
        if not isinstance(self.provisioning_class, ProvisioningClass):
            raise InvalidDistributedProvenanceError(
                f"provisioning_class must be a ProvisioningClass, got {self.provisioning_class!r}"
            )
        _require_sha256_hex(self, "worker_image_digest")
        _require_sha256_hex(self, "host_runtime_identity_checksum")
        _require_sha256_hex(self, "telemetry_policy_identity_checksum")

        payload = _worker_execution_context_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.worker_context_checksum and self.worker_context_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"worker_context_checksum {self.worker_context_checksum!r} does not match the "
                f"recomputed checksum {expected_checksum!r} over its own contents -- tampered "
                f"or corrupted worker execution context"
            )
        object.__setattr__(self, "worker_context_checksum", expected_checksum)


def _worker_execution_context_payload(context: WorkerExecutionContext) -> dict[str, Any]:
    return {
        "distributed_provenance_schema_version": context.distributed_provenance_schema_version,
        "checksum_algorithm_version": context.checksum_algorithm_version,
        "parent_run_context_checksum": context.parent_run_context_checksum,
        "region": context.region,
        "zone": context.zone,
        "machine_type": context.machine_type,
        "cpu_architecture": context.cpu_architecture,
        "provisioning_class": context.provisioning_class.value,
        "worker_image_digest": context.worker_image_digest,
        "worker_image_digest_scheme_version": context.worker_image_digest_scheme_version,
        "worker_implementation_id": context.worker_implementation_id,
        "worker_implementation_version": context.worker_implementation_version,
        "host_runtime_identity_checksum": context.host_runtime_identity_checksum,
        "telemetry_policy_identity_checksum": context.telemetry_policy_identity_checksum,
    }


def worker_execution_context_to_dict(context: WorkerExecutionContext) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`WorkerExecutionContext`."""
    return {
        **_worker_execution_context_payload(context),
        "worker_context_checksum": context.worker_context_checksum,
    }


def worker_execution_context_from_dict(data: Mapping[str, Any]) -> WorkerExecutionContext:
    """Inverse of :func:`worker_execution_context_to_dict`."""
    try:
        return WorkerExecutionContext(
            distributed_provenance_schema_version=data["distributed_provenance_schema_version"],
            checksum_algorithm_version=data["checksum_algorithm_version"],
            parent_run_context_checksum=data["parent_run_context_checksum"],
            region=data["region"],
            zone=data["zone"],
            machine_type=data["machine_type"],
            cpu_architecture=data["cpu_architecture"],
            provisioning_class=ProvisioningClass(data["provisioning_class"]),
            worker_image_digest=data["worker_image_digest"],
            worker_image_digest_scheme_version=data["worker_image_digest_scheme_version"],
            worker_implementation_id=data["worker_implementation_id"],
            worker_implementation_version=data["worker_implementation_version"],
            host_runtime_identity_checksum=data["host_runtime_identity_checksum"],
            telemetry_policy_identity_checksum=data["telemetry_policy_identity_checksum"],
            worker_context_checksum=data["worker_context_checksum"],
        )
    except KeyError as exc:
        raise InvalidDistributedProvenanceError(
            f"missing required worker execution context field: {exc}"
        ) from exc
    except ValueError as exc:
        raise InvalidDistributedProvenanceError(
            f"malformed worker execution context: {exc}"
        ) from exc


__all__ = [
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_PROVENANCE_SCHEMA_VERSION",
    "InvalidDistributedProvenanceError",
    "UnsupportedChecksumAlgorithmVersionError",
    "UnsupportedDistributedProvenanceSchemaVersionError",
    "EnvironmentClass",
    "DistributedRunIntent",
    "CloudProvider",
    "ProvisioningClass",
    "RetryLeasePolicy",
    "retry_lease_policy_to_dict",
    "retry_lease_policy_from_dict",
    "DistributedRunContext",
    "distributed_run_context_to_dict",
    "distributed_run_context_from_dict",
    "WorkerExecutionContext",
    "worker_execution_context_to_dict",
    "worker_execution_context_from_dict",
]
