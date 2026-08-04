"""MEGB-03H.2C.3B.1: qualification identity, production identity
projection, and deterministic mixed-worker aggregation.

Three distinct identity concepts, per the authorization's own "Identity
semantics" section:

* :class:`QualificationIdentity` -- changes when any field capable of
  changing timing, telemetry availability, isolation behavior, recovery
  behavior, or equivalence changes. Built from a
  :class:`~src.distributed.provenance.DistributedRunContext` plus the
  full, deterministically-ordered set of contributing
  :class:`~src.distributed.provenance.WorkerExecutionContext`\\ s.
* :class:`ProductionIdentityProjection` -- the strict subset of fields
  capable of changing candidate correctness, resource-limit behavior, or
  measurement validity, per the field-ownership matrix
  (``docs/reference/megb-03h2c3b1-provenance-field-matrix.md``).
* :func:`aggregate_worker_provenance` -- deterministic, order-independent
  aggregation of many worker contexts under one run context, rejecting a
  mismatched parent or a duplicate worker content-checksum.

"Protected operational audit identity" and "safe redacted reporting" are
implemented in :mod:`~src.distributed.protected_mapping` and
:mod:`~src.distributed.safe_summary` respectively -- this module never
imports either, since qualification/production identity must never
depend on, or be influenced by, raw operational identifiers.
"""

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
from src.distributed.provenance import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
    DistributedRunContext,
    WorkerExecutionContext,
)


class MixedWorkerReconciliationError(InvalidDistributedProvenanceError):
    """Base class for every way a set of worker contexts can fail to
    reconcile against one run context. Subclassed so callers -- notably
    :mod:`~src.distributed.qualification_gate` -- can distinguish exactly
    which reconciliation failure occurred without string-matching an
    exception message."""


class EmptyWorkerSetError(MixedWorkerReconciliationError):
    """Raised when an aggregation/summary/gate function is given zero
    worker contexts -- unprovenanced evidence, per the authorization's own
    "reject unprovenanced... evidence" requirement."""


class MismatchedWorkerContextError(MixedWorkerReconciliationError):
    """Raised when a worker's ``parent_run_context_checksum`` does not
    match the run context it is being reconciled against -- mixed-context
    evidence."""


class DuplicateWorkerProvenanceError(MixedWorkerReconciliationError):
    """Raised when the same ``worker_context_checksum`` appears more than
    once in a set being aggregated -- duplicate worker/invocation
    provenance, rejected rather than silently deduplicated, per the
    authorization's own "duplicate worker/invocation provenance rejection
    where appropriate" requirement."""


# ---------------------------------------------------------------------------
# Mixed-worker deterministic aggregation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MixedWorkerProvenanceSummary:
    """Deterministic, order-independent aggregate over the worker
    contexts contributing to one run -- the type that lets a run use
    multiple workers, zones, or provisioning classes without
    misrepresenting them as one homogeneous worker.

    ``worker_context_checksums`` is always stored sorted, so two calls to
    :func:`aggregate_worker_provenance` with the same worker set in a
    different order produce byte-identical results (and therefore the
    same ``aggregate_checksum``).
    """

    distributed_provenance_schema_version: str
    checksum_algorithm_version: str
    run_context_checksum: str
    worker_context_checksums: tuple[str, ...]
    distinct_region_count: int
    distinct_provisioning_class_count: int
    distinct_worker_image_digest_count: int
    aggregate_checksum: str = ""

    def __post_init__(self) -> None:
        _require_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_sha256_hex(self, "run_context_checksum")
        if (
            not isinstance(self.worker_context_checksums, tuple)
            or not self.worker_context_checksums
        ):
            raise InvalidDistributedProvenanceError(
                "worker_context_checksums must be a nonempty tuple, got "
                f"{self.worker_context_checksums!r}"
            )
        if list(self.worker_context_checksums) != sorted(self.worker_context_checksums):
            raise InvalidDistributedProvenanceError(
                "worker_context_checksums must be stored in sorted order for deterministic, "
                "order-independent aggregation"
            )
        if len(set(self.worker_context_checksums)) != len(self.worker_context_checksums):
            raise DuplicateWorkerProvenanceError(
                "worker_context_checksums contains a duplicate entry -- duplicate worker "
                "provenance is rejected, not silently deduplicated"
            )
        for field_name in (
            "distinct_region_count",
            "distinct_provisioning_class_count",
            "distinct_worker_image_digest_count",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise InvalidDistributedProvenanceError(
                    f"{field_name!r} must be a positive int, got {value!r}"
                )

        payload = _mixed_worker_summary_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.aggregate_checksum and self.aggregate_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"aggregate_checksum {self.aggregate_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or corrupted "
                f"mixed-worker provenance summary"
            )
        object.__setattr__(self, "aggregate_checksum", expected_checksum)


def _mixed_worker_summary_payload(summary: MixedWorkerProvenanceSummary) -> dict[str, Any]:
    return {
        "distributed_provenance_schema_version": summary.distributed_provenance_schema_version,
        "checksum_algorithm_version": summary.checksum_algorithm_version,
        "run_context_checksum": summary.run_context_checksum,
        "worker_context_checksums": list(summary.worker_context_checksums),
        "distinct_region_count": summary.distinct_region_count,
        "distinct_provisioning_class_count": summary.distinct_provisioning_class_count,
        "distinct_worker_image_digest_count": summary.distinct_worker_image_digest_count,
    }


def mixed_worker_provenance_summary_to_dict(
    summary: MixedWorkerProvenanceSummary,
) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`MixedWorkerProvenanceSummary`."""
    return {
        **_mixed_worker_summary_payload(summary),
        "aggregate_checksum": summary.aggregate_checksum,
    }


def mixed_worker_provenance_summary_from_dict(
    data: Mapping[str, Any]
) -> MixedWorkerProvenanceSummary:
    """Inverse of :func:`mixed_worker_provenance_summary_to_dict`."""
    try:
        return MixedWorkerProvenanceSummary(
            distributed_provenance_schema_version=data["distributed_provenance_schema_version"],
            checksum_algorithm_version=data["checksum_algorithm_version"],
            run_context_checksum=data["run_context_checksum"],
            worker_context_checksums=tuple(data["worker_context_checksums"]),
            distinct_region_count=data["distinct_region_count"],
            distinct_provisioning_class_count=data["distinct_provisioning_class_count"],
            distinct_worker_image_digest_count=data["distinct_worker_image_digest_count"],
            aggregate_checksum=data["aggregate_checksum"],
        )
    except KeyError as exc:
        raise InvalidDistributedProvenanceError(
            f"missing required mixed-worker provenance summary field: {exc}"
        ) from exc


def aggregate_worker_provenance(
    run_context: DistributedRunContext,
    workers: tuple[WorkerExecutionContext, ...],
) -> MixedWorkerProvenanceSummary:
    """Deterministically aggregate ``workers`` under ``run_context``.

    Rejects (via :class:`MixedWorkerReconciliationError`, a subclass of
    :class:`~src.distributed._checksums.InvalidDistributedProvenanceError`):
    an empty ``workers`` tuple; any worker whose
    ``parent_run_context_checksum`` does not equal
    ``run_context.run_context_checksum`` (a mismatched/mixed context);
    and a duplicate ``worker_context_checksum`` within ``workers``.
    Order-independent: the input order of ``workers`` never affects the
    returned summary's own ``aggregate_checksum``.
    """
    if not workers:
        raise EmptyWorkerSetError(
            "aggregate_worker_provenance requires at least one worker context"
        )
    for worker in workers:
        if worker.parent_run_context_checksum != run_context.run_context_checksum:
            raise MismatchedWorkerContextError(
                f"worker_context_checksum {worker.worker_context_checksum!r} has "
                f"parent_run_context_checksum {worker.parent_run_context_checksum!r}, which "
                f"does not match run_context.run_context_checksum "
                f"{run_context.run_context_checksum!r} -- mixed-context worker set rejected"
            )
    checksums = [worker.worker_context_checksum for worker in workers]
    if len(set(checksums)) != len(checksums):
        raise DuplicateWorkerProvenanceError(
            "workers contains a duplicate worker_context_checksum -- duplicate worker "
            "provenance is rejected, not silently deduplicated"
        )
    return MixedWorkerProvenanceSummary(
        distributed_provenance_schema_version=run_context.distributed_provenance_schema_version,
        checksum_algorithm_version=run_context.checksum_algorithm_version,
        run_context_checksum=run_context.run_context_checksum,
        worker_context_checksums=tuple(sorted(checksums)),
        distinct_region_count=len({worker.region for worker in workers}),
        distinct_provisioning_class_count=len(
            {worker.provisioning_class for worker in workers}
        ),
        distinct_worker_image_digest_count=len(
            {worker.worker_image_digest for worker in workers}
        ),
    )


# ---------------------------------------------------------------------------
# QualificationIdentity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QualificationIdentity:
    """The identity that must change whenever any field capable of
    changing timing, telemetry availability, isolation behavior, recovery
    behavior, or equivalence changes -- i.e. every field on
    :class:`~src.distributed.provenance.DistributedRunContext` and every
    field on every contributing
    :class:`~src.distributed.provenance.WorkerExecutionContext`, via
    ``run_context_checksum``/the aggregated worker checksums. This is
    deliberately the *broadest* identity in this package -- everything
    the qualification gate inspects is, by definition, part of it.
    """

    distributed_provenance_schema_version: str
    checksum_algorithm_version: str
    run_context_checksum: str
    worker_aggregate_checksum: str
    identity_checksum: str = ""

    def __post_init__(self) -> None:
        _require_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_sha256_hex(self, "run_context_checksum")
        _require_sha256_hex(self, "worker_aggregate_checksum")
        payload = _qualification_identity_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.identity_checksum and self.identity_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"identity_checksum {self.identity_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or corrupted "
                f"qualification identity"
            )
        object.__setattr__(self, "identity_checksum", expected_checksum)


def _qualification_identity_payload(identity: QualificationIdentity) -> dict[str, Any]:
    return {
        "distributed_provenance_schema_version": identity.distributed_provenance_schema_version,
        "checksum_algorithm_version": identity.checksum_algorithm_version,
        "run_context_checksum": identity.run_context_checksum,
        "worker_aggregate_checksum": identity.worker_aggregate_checksum,
    }


def qualification_identity_to_dict(identity: QualificationIdentity) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`QualificationIdentity`."""
    return {
        **_qualification_identity_payload(identity),
        "identity_checksum": identity.identity_checksum,
    }


def qualification_identity_from_dict(data: Mapping[str, Any]) -> QualificationIdentity:
    """Inverse of :func:`qualification_identity_to_dict`."""
    try:
        return QualificationIdentity(
            distributed_provenance_schema_version=data["distributed_provenance_schema_version"],
            checksum_algorithm_version=data["checksum_algorithm_version"],
            run_context_checksum=data["run_context_checksum"],
            worker_aggregate_checksum=data["worker_aggregate_checksum"],
            identity_checksum=data["identity_checksum"],
        )
    except KeyError as exc:
        raise InvalidDistributedProvenanceError(
            f"missing required qualification identity field: {exc}"
        ) from exc


def qualification_identity_for(
    run_context: DistributedRunContext,
    worker_summary: MixedWorkerProvenanceSummary,
) -> QualificationIdentity:
    """Derive the :class:`QualificationIdentity` for ``run_context`` and
    its already-aggregated ``worker_summary``. Raises if ``worker_summary``
    was not built from ``run_context`` (checksum mismatch)."""
    if worker_summary.run_context_checksum != run_context.run_context_checksum:
        raise MismatchedWorkerContextError(
            f"worker_summary.run_context_checksum {worker_summary.run_context_checksum!r} does "
            f"not match run_context.run_context_checksum {run_context.run_context_checksum!r}"
        )
    return QualificationIdentity(
        distributed_provenance_schema_version=run_context.distributed_provenance_schema_version,
        checksum_algorithm_version=run_context.checksum_algorithm_version,
        run_context_checksum=run_context.run_context_checksum,
        worker_aggregate_checksum=worker_summary.aggregate_checksum,
    )


# ---------------------------------------------------------------------------
# ProductionIdentityProjection
# ---------------------------------------------------------------------------
#
# Fields capable of changing candidate correctness, resource-limit
# behavior, or measurement validity -- per the field-ownership matrix's
# Qual./Prod. columns. Deliberately excludes: distributed_run_id (an
# identifier, not an outcome-affecting fact), coordinator/worker-fleet/
# queue/object-store implementation version and the retry/lease policy
# (audit/recovery-only, per the accepted audit's own "(1),(3)" tagging),
# region/zone/cpu_architecture (timing-only, per Ambiguity 1's own
# resolution -- machine_type is the one field reclassified INTO this
# projection).


@dataclass(frozen=True)
class ProductionIdentityProjection:  # pylint: disable=too-many-instance-attributes
    """The subset of run/worker provenance capable of changing candidate
    correctness, resource-limit behavior, or measurement validity -- the
    fields a future production result/cache identity integration
    (required before MEGB-03H.2C.3F, per the accepted audit's revised
    blocking precondition) must incorporate. See
    ``docs/reference/megb-03h2c3b1-integration-map.md``.
    """

    distributed_provenance_schema_version: str
    checksum_algorithm_version: str
    environment_class: str
    logical_environment_id: str
    cloud_provider: str
    network_isolation_policy_checksum: str
    machine_type: str
    provisioning_class: str
    worker_image_digest: str
    worker_implementation_version: str
    host_runtime_identity_checksum: str
    telemetry_policy_identity_checksum: str
    projection_checksum: str = ""

    def __post_init__(self) -> None:
        _require_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str_fields(
            self,
            (
                "environment_class",
                "logical_environment_id",
                "cloud_provider",
                "machine_type",
                "provisioning_class",
                "worker_implementation_version",
            ),
        )
        _require_sha256_hex(self, "network_isolation_policy_checksum")
        _require_sha256_hex(self, "worker_image_digest")
        _require_sha256_hex(self, "host_runtime_identity_checksum")
        _require_sha256_hex(self, "telemetry_policy_identity_checksum")
        payload = _production_identity_projection_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.projection_checksum and self.projection_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"projection_checksum {self.projection_checksum!r} does not match the "
                f"recomputed checksum {expected_checksum!r} over its own contents -- tampered "
                f"or corrupted production identity projection"
            )
        object.__setattr__(self, "projection_checksum", expected_checksum)


def _production_identity_projection_payload(
    projection: ProductionIdentityProjection,
) -> dict[str, Any]:
    return {
        "distributed_provenance_schema_version": (
            projection.distributed_provenance_schema_version
        ),
        "checksum_algorithm_version": projection.checksum_algorithm_version,
        "environment_class": projection.environment_class,
        "logical_environment_id": projection.logical_environment_id,
        "cloud_provider": projection.cloud_provider,
        "network_isolation_policy_checksum": projection.network_isolation_policy_checksum,
        "machine_type": projection.machine_type,
        "provisioning_class": projection.provisioning_class,
        "worker_image_digest": projection.worker_image_digest,
        "worker_implementation_version": projection.worker_implementation_version,
        "host_runtime_identity_checksum": projection.host_runtime_identity_checksum,
        "telemetry_policy_identity_checksum": projection.telemetry_policy_identity_checksum,
    }


def production_identity_projection_to_dict(
    projection: ProductionIdentityProjection,
) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`ProductionIdentityProjection`."""
    return {
        **_production_identity_projection_payload(projection),
        "projection_checksum": projection.projection_checksum,
    }


def production_identity_projection_from_dict(
    data: Mapping[str, Any]
) -> ProductionIdentityProjection:
    """Inverse of :func:`production_identity_projection_to_dict`."""
    try:
        return ProductionIdentityProjection(
            distributed_provenance_schema_version=data["distributed_provenance_schema_version"],
            checksum_algorithm_version=data["checksum_algorithm_version"],
            environment_class=data["environment_class"],
            logical_environment_id=data["logical_environment_id"],
            cloud_provider=data["cloud_provider"],
            network_isolation_policy_checksum=data["network_isolation_policy_checksum"],
            machine_type=data["machine_type"],
            provisioning_class=data["provisioning_class"],
            worker_image_digest=data["worker_image_digest"],
            worker_implementation_version=data["worker_implementation_version"],
            host_runtime_identity_checksum=data["host_runtime_identity_checksum"],
            telemetry_policy_identity_checksum=data["telemetry_policy_identity_checksum"],
            projection_checksum=data["projection_checksum"],
        )
    except KeyError as exc:
        raise InvalidDistributedProvenanceError(
            f"missing required production identity projection field: {exc}"
        ) from exc


def production_identity_projection_for(
    run_context: DistributedRunContext,
    worker: WorkerExecutionContext,
) -> ProductionIdentityProjection:
    """Derive the :class:`ProductionIdentityProjection` for one worker
    within ``run_context``. One projection per worker (not per run) --
    two workers in the same run may differ in every field this
    projection carries (different machine type, provisioning class,
    image), and each must be independently comparable against a future
    production cache entry. Raises if ``worker`` does not belong to
    ``run_context`` (checksum mismatch)."""
    if worker.parent_run_context_checksum != run_context.run_context_checksum:
        raise MismatchedWorkerContextError(
            f"worker.parent_run_context_checksum {worker.parent_run_context_checksum!r} does "
            f"not match run_context.run_context_checksum {run_context.run_context_checksum!r}"
        )
    return ProductionIdentityProjection(
        distributed_provenance_schema_version=run_context.distributed_provenance_schema_version,
        checksum_algorithm_version=run_context.checksum_algorithm_version,
        environment_class=run_context.environment_class.value,
        logical_environment_id=run_context.logical_environment_id,
        cloud_provider=run_context.cloud_provider.value,
        network_isolation_policy_checksum=run_context.network_isolation_policy_checksum,
        machine_type=worker.machine_type,
        provisioning_class=worker.provisioning_class.value,
        worker_image_digest=worker.worker_image_digest,
        worker_implementation_version=worker.worker_implementation_version,
        host_runtime_identity_checksum=worker.host_runtime_identity_checksum,
        telemetry_policy_identity_checksum=worker.telemetry_policy_identity_checksum,
    )


__all__ = [
    "MixedWorkerReconciliationError",
    "EmptyWorkerSetError",
    "MismatchedWorkerContextError",
    "DuplicateWorkerProvenanceError",
    "MixedWorkerProvenanceSummary",
    "mixed_worker_provenance_summary_to_dict",
    "mixed_worker_provenance_summary_from_dict",
    "aggregate_worker_provenance",
    "QualificationIdentity",
    "qualification_identity_to_dict",
    "qualification_identity_from_dict",
    "qualification_identity_for",
    "ProductionIdentityProjection",
    "production_identity_projection_to_dict",
    "production_identity_projection_from_dict",
    "production_identity_projection_for",
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_PROVENANCE_SCHEMA_VERSION",
]
