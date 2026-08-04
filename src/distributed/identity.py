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
    require_positive_int as _require_positive_int,
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
    """Raised when the same ``worker_participant_id`` appears more than
    once in a set being aggregated -- a duplicate *observation* of the
    same execution participant, rejected rather than silently
    deduplicated, per the authorization's own "duplicate worker/
    invocation provenance rejection where appropriate" requirement.

    Not raised merely because two distinct participants share identical
    configuration provenance (region/machine type/image/etc.) -- that is
    genuine multiplicity (e.g. a homogeneous fleet), not a duplicate, and
    :func:`aggregate_worker_provenance` must count both. Duplication is
    judged solely by ``worker_participant_id`` -- MEGB-03H.2C.3B.1
    conformance audit, correction 2."""


def require_workers_belong_to_run(
    run_context: DistributedRunContext, workers: tuple[WorkerExecutionContext, ...]
) -> None:
    """Raise :class:`MismatchedWorkerContextError` for the first worker in
    ``workers`` whose ``parent_run_context_checksum`` does not equal
    ``run_context.run_context_checksum`` -- the one reconciliation check
    every aggregation/summary function in this package (and
    :mod:`~src.distributed.safe_summary`) shares."""
    for worker in workers:
        if worker.parent_run_context_checksum != run_context.run_context_checksum:
            raise MismatchedWorkerContextError(
                f"worker_context_checksum {worker.worker_context_checksum!r} has "
                f"parent_run_context_checksum {worker.parent_run_context_checksum!r}, which "
                f"does not match run_context.run_context_checksum "
                f"{run_context.run_context_checksum!r} -- mixed-context worker set rejected"
            )


def _histogram(values: list[str]) -> tuple[tuple[str, int], ...]:
    """A deterministic, order-independent (value, count) histogram: sorted
    by ``value``, so two calls with the same multiset in different input
    order produce a byte-identical result."""
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return tuple(sorted(counts.items()))


def _require_histogram(obj: object, field_name: str, expected_total: int) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, tuple) or not all(
        isinstance(item, tuple)
        and len(item) == 2
        and isinstance(item[0], str)
        and item[0]
        and isinstance(item[1], int)
        and not isinstance(item[1], bool)
        and item[1] > 0
        for item in value
    ):
        raise InvalidDistributedProvenanceError(
            f"{field_name!r} must be a tuple of (nonempty str, positive int) pairs, got {value!r}"
        )
    keys = [item[0] for item in value]
    if keys != sorted(keys):
        raise InvalidDistributedProvenanceError(
            f"{field_name!r} must be sorted by key for deterministic, order-independent "
            f"serialization, got {value!r}"
        )
    total = sum(item[1] for item in value)
    if total > expected_total:
        raise InvalidDistributedProvenanceError(
            f"{field_name!r} counts sum to {total}, more than admitted_worker_count "
            f"({expected_total})"
        )


# ---------------------------------------------------------------------------
# Mixed-worker deterministic aggregation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MixedWorkerProvenanceSummary:  # pylint: disable=too-many-instance-attributes
    """Deterministic, order-independent, multiplicity-aware aggregate over
    the worker contexts contributing to one run -- the type that lets a
    run use multiple workers, zones, or provisioning classes without
    misrepresenting them as one homogeneous worker, and without
    collapsing a genuine multi-worker topology down to the count of
    *distinct configurations* rather than the count of *actual
    participants* (MEGB-03H.2C.3B.1 conformance audit, correction 2).

    ``admitted_worker_count`` is the actual headcount of workers admitted
    to (i.e. actually contributing to) this run -- not an allowed or
    intended topology, but the real composition
    :func:`aggregate_worker_provenance` was called with.
    ``worker_participant_checksums`` is one ``worker_context_checksum``
    per admitted worker, sorted; because each legitimate participant
    carries a distinct ``worker_participant_id``, these are always
    pairwise distinct in a non-tampered summary (a repeated value would
    mean the same participant's ``WorkerExecutionContext`` was
    constructed twice with different content, which
    :func:`aggregate_worker_provenance` cannot see -- it only sees
    ``worker_participant_id`` collisions, checked before this type is
    ever constructed). The four ``*_counts`` fields are deterministic
    histograms (value, count) sorted by value -- this is where genuine
    multiplicity (many workers sharing one provisioning class, region,
    machine type, or image) is explicitly counted, not merely implied by
    a distinct-value count that would silently collapse repeats.

    Deliberately does not track "peak concurrency": that is an *observed*
    runtime measurement (how many workers were simultaneously busy at
    some instant), not a *provenance* fact (what infrastructure was
    admitted to the run) -- the same distinction this project's own
    calibration schema already draws between identity/context fields and
    measured telemetry fields. A future H.2C.3D/H.2C.3B.2 qualification-
    report design should record peak concurrency as its own measured
    metric, not fold it into this identity type.
    """

    distributed_provenance_schema_version: str
    checksum_algorithm_version: str
    run_context_checksum: str
    admitted_worker_count: int
    worker_participant_checksums: tuple[str, ...]
    provisioning_class_counts: tuple[tuple[str, int], ...]
    region_counts: tuple[tuple[str, int], ...]
    zone_counts: tuple[tuple[str, int], ...]
    machine_type_counts: tuple[tuple[str, int], ...]
    worker_image_digest_counts: tuple[tuple[str, int], ...]
    aggregate_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _require_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_sha256_hex(self, "run_context_checksum")
        _require_positive_int(self, "admitted_worker_count")
        if (
            not isinstance(self.worker_participant_checksums, tuple)
            or len(self.worker_participant_checksums) != self.admitted_worker_count
        ):
            raise InvalidDistributedProvenanceError(
                "worker_participant_checksums must be a tuple of length admitted_worker_count "
                f"({self.admitted_worker_count}), got {self.worker_participant_checksums!r}"
            )
        if list(self.worker_participant_checksums) != sorted(self.worker_participant_checksums):
            raise InvalidDistributedProvenanceError(
                "worker_participant_checksums must be stored in sorted order for deterministic, "
                "order-independent aggregation"
            )
        if len(set(self.worker_participant_checksums)) != len(self.worker_participant_checksums):
            raise DuplicateWorkerProvenanceError(
                "worker_participant_checksums contains a duplicate entry -- each admitted "
                "worker must carry a distinct worker_context_checksum (distinct "
                "worker_participant_id), or this summary would misrepresent the same "
                "participant as two"
            )
        for field_name in (
            "provisioning_class_counts",
            "region_counts",
            "zone_counts",
            "machine_type_counts",
            "worker_image_digest_counts",
        ):
            _require_histogram(self, field_name, self.admitted_worker_count)
        for required_full_total_field in (
            "provisioning_class_counts",
            "region_counts",
            "machine_type_counts",
            "worker_image_digest_counts",
        ):
            total = sum(count for _, count in getattr(self, required_full_total_field))
            if total != self.admitted_worker_count:
                raise InvalidDistributedProvenanceError(
                    f"{required_full_total_field!r} counts sum to {total}, expected exactly "
                    f"admitted_worker_count ({self.admitted_worker_count}) -- every admitted "
                    f"worker has exactly one region, provisioning class, machine type, and "
                    f"image digest (only zone_counts may sum to less, since zone is optional)"
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
        "admitted_worker_count": summary.admitted_worker_count,
        "worker_participant_checksums": list(summary.worker_participant_checksums),
        "provisioning_class_counts": [list(pair) for pair in summary.provisioning_class_counts],
        "region_counts": [list(pair) for pair in summary.region_counts],
        "zone_counts": [list(pair) for pair in summary.zone_counts],
        "machine_type_counts": [list(pair) for pair in summary.machine_type_counts],
        "worker_image_digest_counts": [
            list(pair) for pair in summary.worker_image_digest_counts
        ],
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
            admitted_worker_count=data["admitted_worker_count"],
            worker_participant_checksums=tuple(data["worker_participant_checksums"]),
            provisioning_class_counts=tuple(
                tuple(pair) for pair in data["provisioning_class_counts"]
            ),
            region_counts=tuple(tuple(pair) for pair in data["region_counts"]),
            zone_counts=tuple(tuple(pair) for pair in data["zone_counts"]),
            machine_type_counts=tuple(tuple(pair) for pair in data["machine_type_counts"]),
            worker_image_digest_counts=tuple(
                tuple(pair) for pair in data["worker_image_digest_counts"]
            ),
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
    """Deterministically aggregate ``workers`` under ``run_context`` --
    the actual worker-context composition admitted to this run, not an
    allowed or intended topology.

    Rejects (via :class:`MixedWorkerReconciliationError`, a subclass of
    :class:`~src.distributed._checksums.InvalidDistributedProvenanceError`):
    an empty ``workers`` tuple; any worker whose
    ``parent_run_context_checksum`` does not equal
    ``run_context.run_context_checksum`` (a mismatched/mixed context);
    and a duplicate ``worker_participant_id`` within ``workers`` (the
    same execution participant reported twice). Does **not** reject two
    workers that merely share identical configuration provenance --
    genuine multiplicity (e.g. a homogeneous fleet) is counted, not
    collapsed or rejected. Order-independent: the input order of
    ``workers`` never affects the returned summary's own
    ``aggregate_checksum``.
    """
    if not workers:
        raise EmptyWorkerSetError(
            "aggregate_worker_provenance requires at least one worker context"
        )
    require_workers_belong_to_run(run_context, workers)
    participant_ids = [worker.worker_participant_id for worker in workers]
    if len(set(participant_ids)) != len(participant_ids):
        raise DuplicateWorkerProvenanceError(
            "workers contains a duplicate worker_participant_id -- the same execution "
            "participant was reported more than once; duplicate observation is rejected, "
            "not silently deduplicated (distinct participants sharing identical configuration "
            "provenance are not duplicates and must not be rejected)"
        )
    checksums = sorted(worker.worker_context_checksum for worker in workers)
    return MixedWorkerProvenanceSummary(
        distributed_provenance_schema_version=run_context.distributed_provenance_schema_version,
        checksum_algorithm_version=run_context.checksum_algorithm_version,
        run_context_checksum=run_context.run_context_checksum,
        admitted_worker_count=len(workers),
        worker_participant_checksums=tuple(checksums),
        provisioning_class_counts=_histogram(
            [worker.provisioning_class.value for worker in workers]
        ),
        region_counts=_histogram([worker.region for worker in workers]),
        zone_counts=_histogram([worker.zone for worker in workers if worker.zone is not None]),
        machine_type_counts=_histogram([worker.machine_type for worker in workers]),
        worker_image_digest_counts=_histogram(
            [worker.worker_image_digest for worker in workers]
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
    ``run_context`` (checksum mismatch).

    **Valid only when the calling production integration can guarantee a
    given production result was produced entirely by this single worker
    context** (MEGB-03H.2C.3B.1 conformance audit, correction 2). No such
    indivisible-work-unit invariant is currently frozen or enforced
    anywhere in the accepted or proposed design -- neither
    ``ReferenceTaskResult`` nor any H.2C.3B.2 interface named in the
    architecture doc guarantees one-worker-per-task execution. Until that
    invariant is frozen (a proposed H.2C.3B.2 deliverable) or shown to
    hold by construction, a real production integration must use
    :func:`aggregate_production_identity_for` instead, which makes no
    such assumption."""
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


# ---------------------------------------------------------------------------
# AggregateProductionIdentityProjection (MEGB-03H.2C.3B.1 conformance audit,
# correction 2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregateProductionIdentityProjection:  # pylint: disable=too-many-instance-attributes
    """The production-identity-bearing fields aggregated, deterministically
    and multiplicity-aware, over *every* worker context that contributed
    to producing one production result -- for use whenever a single
    production work item's candidate execution is not guaranteed to have
    been produced entirely by one worker (e.g. retried across workers, or
    a work-item granularity that is not yet frozen as indivisible; see
    :func:`production_identity_projection_for`'s own docstring).

    Deliberately makes no single-worker assumption: this projection is
    correct whether one worker or many contributed. Two runs whose
    contributing-worker *composition* differs (different counts, not
    merely different distinct values) produce different
    ``projection_checksum`` values, closing the gap a naive single-worker
    ``ProductionIdentityProjection`` would leave open for a multi-worker
    work item.
    """

    distributed_provenance_schema_version: str
    checksum_algorithm_version: str
    environment_class: str
    logical_environment_id: str
    cloud_provider: str
    network_isolation_policy_checksum: str
    contributing_worker_count: int
    machine_type_counts: tuple[tuple[str, int], ...]
    provisioning_class_counts: tuple[tuple[str, int], ...]
    worker_image_digest_counts: tuple[tuple[str, int], ...]
    worker_implementation_version_counts: tuple[tuple[str, int], ...]
    host_runtime_identity_checksum_counts: tuple[tuple[str, int], ...]
    telemetry_policy_identity_checksum_counts: tuple[tuple[str, int], ...]
    projection_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _require_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str_fields(
            self,
            ("environment_class", "logical_environment_id", "cloud_provider"),
        )
        _require_sha256_hex(self, "network_isolation_policy_checksum")
        _require_positive_int(self, "contributing_worker_count")
        for field_name in (
            "machine_type_counts",
            "provisioning_class_counts",
            "worker_image_digest_counts",
            "worker_implementation_version_counts",
            "host_runtime_identity_checksum_counts",
            "telemetry_policy_identity_checksum_counts",
        ):
            _require_histogram(self, field_name, self.contributing_worker_count)
            total = sum(count for _, count in getattr(self, field_name))
            if total != self.contributing_worker_count:
                raise InvalidDistributedProvenanceError(
                    f"{field_name!r} counts sum to {total}, expected exactly "
                    f"contributing_worker_count ({self.contributing_worker_count})"
                )

        payload = _aggregate_production_identity_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.projection_checksum and self.projection_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"projection_checksum {self.projection_checksum!r} does not match the "
                f"recomputed checksum {expected_checksum!r} over its own contents -- tampered "
                f"or corrupted aggregate production identity projection"
            )
        object.__setattr__(self, "projection_checksum", expected_checksum)


def _aggregate_production_identity_payload(
    projection: AggregateProductionIdentityProjection,
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
        "contributing_worker_count": projection.contributing_worker_count,
        "machine_type_counts": [list(pair) for pair in projection.machine_type_counts],
        "provisioning_class_counts": [
            list(pair) for pair in projection.provisioning_class_counts
        ],
        "worker_image_digest_counts": [
            list(pair) for pair in projection.worker_image_digest_counts
        ],
        "worker_implementation_version_counts": [
            list(pair) for pair in projection.worker_implementation_version_counts
        ],
        "host_runtime_identity_checksum_counts": [
            list(pair) for pair in projection.host_runtime_identity_checksum_counts
        ],
        "telemetry_policy_identity_checksum_counts": [
            list(pair) for pair in projection.telemetry_policy_identity_checksum_counts
        ],
    }


def aggregate_production_identity_projection_to_dict(
    projection: AggregateProductionIdentityProjection,
) -> dict[str, Any]:
    """Full-fidelity serialization of an
    :class:`AggregateProductionIdentityProjection`."""
    return {
        **_aggregate_production_identity_payload(projection),
        "projection_checksum": projection.projection_checksum,
    }


def aggregate_production_identity_projection_from_dict(
    data: Mapping[str, Any]
) -> AggregateProductionIdentityProjection:
    """Inverse of :func:`aggregate_production_identity_projection_to_dict`."""
    try:
        return AggregateProductionIdentityProjection(
            distributed_provenance_schema_version=data["distributed_provenance_schema_version"],
            checksum_algorithm_version=data["checksum_algorithm_version"],
            environment_class=data["environment_class"],
            logical_environment_id=data["logical_environment_id"],
            cloud_provider=data["cloud_provider"],
            network_isolation_policy_checksum=data["network_isolation_policy_checksum"],
            contributing_worker_count=data["contributing_worker_count"],
            machine_type_counts=tuple(tuple(pair) for pair in data["machine_type_counts"]),
            provisioning_class_counts=tuple(
                tuple(pair) for pair in data["provisioning_class_counts"]
            ),
            worker_image_digest_counts=tuple(
                tuple(pair) for pair in data["worker_image_digest_counts"]
            ),
            worker_implementation_version_counts=tuple(
                tuple(pair) for pair in data["worker_implementation_version_counts"]
            ),
            host_runtime_identity_checksum_counts=tuple(
                tuple(pair) for pair in data["host_runtime_identity_checksum_counts"]
            ),
            telemetry_policy_identity_checksum_counts=tuple(
                tuple(pair) for pair in data["telemetry_policy_identity_checksum_counts"]
            ),
            projection_checksum=data["projection_checksum"],
        )
    except KeyError as exc:
        raise InvalidDistributedProvenanceError(
            f"missing required aggregate production identity projection field: {exc}"
        ) from exc


def aggregate_production_identity_for(
    run_context: DistributedRunContext,
    workers: tuple[WorkerExecutionContext, ...],
) -> AggregateProductionIdentityProjection:
    """Derive the :class:`AggregateProductionIdentityProjection` for every
    worker in ``workers`` that contributed to one production result --
    the multi-worker-safe alternative to
    :func:`production_identity_projection_for`. Rejects an empty
    ``workers`` tuple, a mismatched parent run context, or a duplicate
    ``worker_participant_id`` (same rules as
    :func:`aggregate_worker_provenance`)."""
    if not workers:
        raise EmptyWorkerSetError(
            "aggregate_production_identity_for requires at least one worker context"
        )
    require_workers_belong_to_run(run_context, workers)
    participant_ids = [worker.worker_participant_id for worker in workers]
    if len(set(participant_ids)) != len(participant_ids):
        raise DuplicateWorkerProvenanceError(
            "workers contains a duplicate worker_participant_id -- the same execution "
            "participant was reported more than once"
        )
    return AggregateProductionIdentityProjection(
        distributed_provenance_schema_version=run_context.distributed_provenance_schema_version,
        checksum_algorithm_version=run_context.checksum_algorithm_version,
        environment_class=run_context.environment_class.value,
        logical_environment_id=run_context.logical_environment_id,
        cloud_provider=run_context.cloud_provider.value,
        network_isolation_policy_checksum=run_context.network_isolation_policy_checksum,
        contributing_worker_count=len(workers),
        machine_type_counts=_histogram([worker.machine_type for worker in workers]),
        provisioning_class_counts=_histogram(
            [worker.provisioning_class.value for worker in workers]
        ),
        worker_image_digest_counts=_histogram(
            [worker.worker_image_digest for worker in workers]
        ),
        worker_implementation_version_counts=_histogram(
            [worker.worker_implementation_version for worker in workers]
        ),
        host_runtime_identity_checksum_counts=_histogram(
            [worker.host_runtime_identity_checksum for worker in workers]
        ),
        telemetry_policy_identity_checksum_counts=_histogram(
            [worker.telemetry_policy_identity_checksum for worker in workers]
        ),
    )


__all__ = [
    "MixedWorkerReconciliationError",
    "EmptyWorkerSetError",
    "MismatchedWorkerContextError",
    "DuplicateWorkerProvenanceError",
    "require_workers_belong_to_run",
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
    "AggregateProductionIdentityProjection",
    "aggregate_production_identity_projection_to_dict",
    "aggregate_production_identity_projection_from_dict",
    "aggregate_production_identity_for",
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_PROVENANCE_SCHEMA_VERSION",
]
