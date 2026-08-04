"""MEGB-03H.2C.3B.1: the safe, allowlisted redacted-summary projection
suitable for a committed qualification report.

Structurally excludes (no field exists for any of them -- the strongest
available exclusion guarantee, mirroring
``src.reference.reference_audit.ReferenceAuditRecord``'s own "structurally
cannot carry X" design):

* every raw operational identifier (see
  :mod:`~src.distributed.protected_mapping` instead);
* per-worker ``zone`` (region only, per the field-ownership matrix's
  concept #3 rationale -- avoids per-record infrastructure-topology
  fingerprinting);
* coordinator/worker-fleet/queue/object-store implementation version and
  the retry/lease policy's own fields (Ambiguity 2 in the field-ownership
  matrix: the accepted audit tags these "(1), (3)" -- qualification
  identity plus protected/audit-only -- without the "(4) safe summary"
  tag, and this module resolves that literally and conservatively);
* managed-model/candidate-generation-plane provenance (reserved for
  MEGB-03H.2C.3G).

This module deliberately never imports
:mod:`~src.distributed.protected_mapping` -- there is no code path from a
raw operational identifier into this type.
"""

import dataclasses
from dataclasses import dataclass
from typing import Any, Mapping

from src.distributed._checksums import (
    InvalidDistributedProvenanceError,
    require_checksum_algorithm_version as _require_checksum_algorithm_version,
    require_nonempty_str_fields as _require_nonempty_str_fields,
    require_schema_version as _require_schema_version,
    require_sha256_hex as _require_sha256_hex,
    sha256_of as _sha256_of,
)
from src.distributed.identity import (
    EmptyWorkerSetError,
    MismatchedWorkerContextError,
    QualificationIdentity,
)
from src.distributed.provenance import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
    DistributedRunContext,
    WorkerExecutionContext,
)


@dataclass(frozen=True)
class SafeRedactedSummary:  # pylint: disable=too-many-instance-attributes
    """Allowlisted, safe-to-commit projection of one distributed run's
    provenance. Every field here is either a closed-enum value, a logical/
    pseudonymous label, a content-bound checksum, or a coarse aggregate --
    never a raw infrastructure identifier and never a per-worker
    zone-level value."""

    distributed_provenance_schema_version: str
    checksum_algorithm_version: str
    environment_class: str
    logical_environment_id: str
    run_intent: str
    distributed_run_id: str
    cloud_provider: str
    network_isolation_policy_checksum: str
    deployment_topology_policy_id: str
    deployment_topology_policy_version: str
    qualification_identity_checksum: str
    distinct_worker_count: int
    regions_observed: tuple[str, ...]
    machine_types_observed: tuple[str, ...]
    provisioning_classes_observed: tuple[str, ...]
    worker_image_digests_observed: tuple[str, ...]
    worker_implementation_versions_observed: tuple[str, ...]
    summary_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _require_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str_fields(
            self,
            (
                "run_intent",
                "distributed_run_id",
                "environment_class",
                "logical_environment_id",
                "cloud_provider",
                "deployment_topology_policy_id",
                "deployment_topology_policy_version",
            ),
        )
        _require_sha256_hex(self, "network_isolation_policy_checksum")
        _require_sha256_hex(self, "qualification_identity_checksum")
        if (
            not isinstance(self.distinct_worker_count, int)
            or isinstance(self.distinct_worker_count, bool)
            or self.distinct_worker_count < 1
        ):
            raise InvalidDistributedProvenanceError(
                f"distinct_worker_count must be a positive int, got {self.distinct_worker_count!r}"
            )
        for field_name in (
            "regions_observed",
            "machine_types_observed",
            "provisioning_classes_observed",
            "worker_image_digests_observed",
            "worker_implementation_versions_observed",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple) or not all(
                isinstance(item, str) and item for item in value
            ):
                raise InvalidDistributedProvenanceError(
                    f"{field_name!r} must be a tuple of nonempty strings, got {value!r}"
                )
            if list(value) != sorted(set(value)):
                raise InvalidDistributedProvenanceError(
                    f"{field_name!r} must be a sorted, deduplicated tuple for deterministic "
                    f"serialization, got {value!r}"
                )

        payload = _safe_redacted_summary_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.summary_checksum and self.summary_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"summary_checksum {self.summary_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or corrupted "
                f"safe redacted summary"
            )
        object.__setattr__(self, "summary_checksum", expected_checksum)


def _safe_redacted_summary_payload(summary: SafeRedactedSummary) -> dict[str, Any]:
    return {
        "distributed_provenance_schema_version": summary.distributed_provenance_schema_version,
        "checksum_algorithm_version": summary.checksum_algorithm_version,
        "environment_class": summary.environment_class,
        "logical_environment_id": summary.logical_environment_id,
        "run_intent": summary.run_intent,
        "distributed_run_id": summary.distributed_run_id,
        "cloud_provider": summary.cloud_provider,
        "network_isolation_policy_checksum": summary.network_isolation_policy_checksum,
        "deployment_topology_policy_id": summary.deployment_topology_policy_id,
        "deployment_topology_policy_version": summary.deployment_topology_policy_version,
        "qualification_identity_checksum": summary.qualification_identity_checksum,
        "distinct_worker_count": summary.distinct_worker_count,
        "regions_observed": list(summary.regions_observed),
        "machine_types_observed": list(summary.machine_types_observed),
        "provisioning_classes_observed": list(summary.provisioning_classes_observed),
        "worker_image_digests_observed": list(summary.worker_image_digests_observed),
        "worker_implementation_versions_observed": list(
            summary.worker_implementation_versions_observed
        ),
    }


def safe_redacted_summary_to_dict(summary: SafeRedactedSummary) -> dict[str, Any]:
    """Full-fidelity serialization -- safe to commit."""
    return {**_safe_redacted_summary_payload(summary), "summary_checksum": summary.summary_checksum}


def safe_redacted_summary_from_dict(data: Mapping[str, Any]) -> SafeRedactedSummary:
    """Inverse of :func:`safe_redacted_summary_to_dict`."""
    try:
        return SafeRedactedSummary(
            distributed_provenance_schema_version=data["distributed_provenance_schema_version"],
            checksum_algorithm_version=data["checksum_algorithm_version"],
            environment_class=data["environment_class"],
            logical_environment_id=data["logical_environment_id"],
            run_intent=data["run_intent"],
            distributed_run_id=data["distributed_run_id"],
            cloud_provider=data["cloud_provider"],
            network_isolation_policy_checksum=data["network_isolation_policy_checksum"],
            deployment_topology_policy_id=data["deployment_topology_policy_id"],
            deployment_topology_policy_version=data["deployment_topology_policy_version"],
            qualification_identity_checksum=data["qualification_identity_checksum"],
            distinct_worker_count=data["distinct_worker_count"],
            regions_observed=tuple(data["regions_observed"]),
            machine_types_observed=tuple(data["machine_types_observed"]),
            provisioning_classes_observed=tuple(data["provisioning_classes_observed"]),
            worker_image_digests_observed=tuple(data["worker_image_digests_observed"]),
            worker_implementation_versions_observed=tuple(
                data["worker_implementation_versions_observed"]
            ),
            summary_checksum=data["summary_checksum"],
        )
    except KeyError as exc:
        raise InvalidDistributedProvenanceError(
            f"missing required safe redacted summary field: {exc}"
        ) from exc


def build_safe_redacted_summary(
    run_context: DistributedRunContext,
    workers: tuple[WorkerExecutionContext, ...],
    qualification_identity: QualificationIdentity,
) -> SafeRedactedSummary:
    """Build the :class:`SafeRedactedSummary` for ``run_context`` and its
    contributing ``workers``. Raises if any worker does not belong to
    ``run_context``, if ``workers`` is empty, or if
    ``qualification_identity`` was not derived from ``run_context``."""
    if not workers:
        raise EmptyWorkerSetError(
            "build_safe_redacted_summary requires at least one worker context"
        )
    for worker in workers:
        if worker.parent_run_context_checksum != run_context.run_context_checksum:
            raise MismatchedWorkerContextError(
                f"worker.parent_run_context_checksum {worker.parent_run_context_checksum!r} "
                f"does not match run_context.run_context_checksum "
                f"{run_context.run_context_checksum!r}"
            )
    if qualification_identity.run_context_checksum != run_context.run_context_checksum:
        raise MismatchedWorkerContextError(
            "qualification_identity was not derived from run_context "
            f"({qualification_identity.run_context_checksum!r} != "
            f"{run_context.run_context_checksum!r})"
        )
    return SafeRedactedSummary(
        distributed_provenance_schema_version=run_context.distributed_provenance_schema_version,
        checksum_algorithm_version=run_context.checksum_algorithm_version,
        environment_class=run_context.environment_class.value,
        logical_environment_id=run_context.logical_environment_id,
        run_intent=run_context.run_intent.value,
        distributed_run_id=run_context.distributed_run_id,
        cloud_provider=run_context.cloud_provider.value,
        network_isolation_policy_checksum=run_context.network_isolation_policy_checksum,
        deployment_topology_policy_id=run_context.deployment_topology_policy_id,
        deployment_topology_policy_version=run_context.deployment_topology_policy_version,
        qualification_identity_checksum=qualification_identity.identity_checksum,
        distinct_worker_count=len(workers),
        regions_observed=tuple(sorted({worker.region for worker in workers})),
        machine_types_observed=tuple(sorted({worker.machine_type for worker in workers})),
        provisioning_classes_observed=tuple(
            sorted({worker.provisioning_class.value for worker in workers})
        ),
        worker_image_digests_observed=tuple(
            sorted({worker.worker_image_digest for worker in workers})
        ),
        worker_implementation_versions_observed=tuple(
            sorted({worker.worker_implementation_version for worker in workers})
        ),
    )


def safe_summary_field_names() -> frozenset[str]:
    """The exact set of field names :class:`SafeRedactedSummary` declares
    -- used by ``tests/test_distributed_leakage.py`` to structurally
    assert that no excluded concept (``zone``, coordinator/fleet/queue/
    object-store implementation version, retry/lease policy fields, or
    any raw operational identifier from
    :class:`~src.distributed.protected_mapping.ProtectedOperationalMapping`)
    is present."""
    return frozenset(field.name for field in dataclasses.fields(SafeRedactedSummary))


__all__ = [
    "SafeRedactedSummary",
    "safe_redacted_summary_to_dict",
    "safe_redacted_summary_from_dict",
    "build_safe_redacted_summary",
    "safe_summary_field_names",
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_PROVENANCE_SCHEMA_VERSION",
]
