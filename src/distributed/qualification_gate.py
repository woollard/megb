"""MEGB-03H.2C.3B.1: the H.2C.3D qualification gate.

A typed function establishing whether a distributed-run's provenance is
complete enough to support an H.2C.3D qualifying run -- mirroring
``H2C2BQualificationReport.qualifying``'s own established precedent
(a typed boolean/enum decision, never a convention). This does **not**
authorize an H.2C.3D runner or report implementation; it is the reusable
decision function a later, separately-authorized H.2C.3D checkpoint would
call.

Two provenance-completeness conditions are already enforced structurally,
not merely by this gate, and therefore never need a dedicated
:class:`ProvenanceGateFailureReason`: a stale
``distributed_provenance_schema_version``/``checksum_algorithm_version``
or a tampered checksum cannot produce a valid
:class:`~src.distributed.provenance.DistributedRunContext`/
:class:`~src.distributed.provenance.WorkerExecutionContext` object at
all -- construction itself raises
:class:`~src.distributed._checksums.UnsupportedDistributedProvenanceSchemaVersionError`,
:class:`~src.distributed._checksums.UnsupportedChecksumAlgorithmVersionError`,
or :class:`~src.distributed._checksums.InvalidDistributedProvenanceError`
before this gate ever sees the record. "Reject... stale-version, or
checksum-invalid evidence" is therefore satisfied one layer earlier than
the gate itself, by the same auto-compute-or-reject pattern used
throughout this package.
"""

from dataclasses import dataclass
from enum import Enum

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.identity import (
    MixedWorkerProvenanceSummary,
    QualificationIdentity,
    aggregate_worker_provenance,
    qualification_identity_for,
)
from src.distributed.provenance import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
    DistributedRunContext,
    DistributedRunIntent,
    WorkerExecutionContext,
)


class ProvenanceGateReadiness(str, Enum):
    """The two, and only two, outcomes of the qualification gate."""

    READY = "READY"
    BLOCKED = "BLOCKED"


class ProvenanceGateFailureReason(str, Enum):
    """Closed, safe, non-sensitive reason codes -- never free-form text,
    per the authorization's own "without free-form sensitive detail"
    requirement. Each value names a missing or incompatible provenance
    dimension, never a raw identifier or exception message."""

    NOT_QUALIFICATION_INTENT = "NOT_QUALIFICATION_INTENT"
    NO_WORKER_CONTEXTS = "NO_WORKER_CONTEXTS"
    MIXED_CONTEXT_WORKERS = "MIXED_CONTEXT_WORKERS"
    DUPLICATE_WORKER_PROVENANCE = "DUPLICATE_WORKER_PROVENANCE"


@dataclass(frozen=True)
class QualificationGateResult:
    """The gate's typed, immutable decision.

    ``readiness == READY`` if and only if ``missing_dimensions`` is empty
    and both ``qualification_identity``/``worker_summary`` are present.
    ``readiness == BLOCKED`` if and only if ``missing_dimensions`` is
    nonempty and both are ``None`` -- a blocked evaluation never partially
    computes an identity, so a caller can never accidentally treat a
    blocked result's identity as meaningful."""

    readiness: ProvenanceGateReadiness
    missing_dimensions: tuple[ProvenanceGateFailureReason, ...]
    qualification_identity: QualificationIdentity | None
    worker_summary: MixedWorkerProvenanceSummary | None

    def __post_init__(self) -> None:
        if not isinstance(self.readiness, ProvenanceGateReadiness):
            raise InvalidDistributedProvenanceError(
                f"readiness must be a ProvenanceGateReadiness, got {self.readiness!r}"
            )
        if not isinstance(self.missing_dimensions, tuple) or not all(
            isinstance(reason, ProvenanceGateFailureReason) for reason in self.missing_dimensions
        ):
            raise InvalidDistributedProvenanceError(
                f"missing_dimensions must be a tuple of ProvenanceGateFailureReason, got "
                f"{self.missing_dimensions!r}"
            )
        if self.readiness == ProvenanceGateReadiness.READY:
            if self.missing_dimensions:
                raise InvalidDistributedProvenanceError(
                    f"readiness=READY must have empty missing_dimensions, got "
                    f"{self.missing_dimensions!r}"
                )
            if self.qualification_identity is None or self.worker_summary is None:
                raise InvalidDistributedProvenanceError(
                    "readiness=READY requires both qualification_identity and worker_summary "
                    "to be present"
                )
        else:
            if not self.missing_dimensions:
                raise InvalidDistributedProvenanceError(
                    "readiness=BLOCKED requires a nonempty missing_dimensions"
                )
            if self.qualification_identity is not None or self.worker_summary is not None:
                raise InvalidDistributedProvenanceError(
                    "readiness=BLOCKED must not carry a qualification_identity or "
                    "worker_summary -- a blocked evaluation never partially computes an identity"
                )


def evaluate_qualification_gate(
    run_context: DistributedRunContext,
    workers: tuple[WorkerExecutionContext, ...],
) -> QualificationGateResult:
    """Evaluate whether ``run_context``/``workers`` are complete enough to
    support an H.2C.3D qualifying run.

    Enumerates every applicable :class:`ProvenanceGateFailureReason`
    rather than stopping at the first one found, so a caller sees the
    full picture of what is missing in one evaluation. Structurally
    prevents a personal-bootstrap/smoke-test record from being mislabeled
    as qualifying evidence: ``run_intent != QUALIFICATION_CANDIDATE``
    always blocks, regardless of ``environment_class`` (both
    ``PERSONAL_BOOTSTRAP`` and ``COMPANY_PLAYGROUND`` may be
    ``QUALIFICATION_CANDIDATE`` -- H.2C.3D's own qualifying runs are
    explicitly personal-environment runs, per the accepted amendment;
    ``environment_class`` alone is never the signal, per Ambiguity 3 in
    the field-ownership matrix)."""
    reasons: list[ProvenanceGateFailureReason] = []
    if run_context.run_intent != DistributedRunIntent.QUALIFICATION_CANDIDATE:
        reasons.append(ProvenanceGateFailureReason.NOT_QUALIFICATION_INTENT)
    if not workers:
        reasons.append(ProvenanceGateFailureReason.NO_WORKER_CONTEXTS)
        return QualificationGateResult(
            readiness=ProvenanceGateReadiness.BLOCKED,
            missing_dimensions=tuple(reasons),
            qualification_identity=None,
            worker_summary=None,
        )
    if any(
        worker.parent_run_context_checksum != run_context.run_context_checksum
        for worker in workers
    ):
        reasons.append(ProvenanceGateFailureReason.MIXED_CONTEXT_WORKERS)
    worker_checksums = [worker.worker_context_checksum for worker in workers]
    if len(set(worker_checksums)) != len(worker_checksums):
        reasons.append(ProvenanceGateFailureReason.DUPLICATE_WORKER_PROVENANCE)

    if reasons:
        return QualificationGateResult(
            readiness=ProvenanceGateReadiness.BLOCKED,
            missing_dimensions=tuple(reasons),
            qualification_identity=None,
            worker_summary=None,
        )

    worker_summary = aggregate_worker_provenance(run_context, workers)
    qualification_identity = qualification_identity_for(run_context, worker_summary)
    return QualificationGateResult(
        readiness=ProvenanceGateReadiness.READY,
        missing_dimensions=(),
        qualification_identity=qualification_identity,
        worker_summary=worker_summary,
    )


__all__ = [
    "ProvenanceGateReadiness",
    "ProvenanceGateFailureReason",
    "QualificationGateResult",
    "evaluate_qualification_gate",
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_PROVENANCE_SCHEMA_VERSION",
]
