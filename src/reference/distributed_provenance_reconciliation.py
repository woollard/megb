"""MEGB-03H.2C.3B.3: reconciliation between the accepted calibration
evidence chain (``src.reference.calibration_schema``) and the standalone,
provider-neutral distributed-provenance manifest
(``src.distributed.provenance_manifest``).

The **only** module in ``src/reference/`` permitted to import
``src.distributed`` -- no dependency-direction test forbids this
direction (only the reverse, ``src/distributed`` importing
``src.reference``, is forbidden and remains unaffected by this
checkpoint; see ``tests/test_distributed_dependency_direction.py``).
Kept as its own small module rather than folded into the already-large
``calibration_schema.py`` (over 1500 lines, already carrying a
``too-many-lines`` pylint disable), mirroring the existing
``calibration_summary.py``/``calibration_trace.py`` module-size
precedent.

Implements exactly the two reconciliation checks this checkpoint's own
frozen design (§1) names:

* a :class:`~src.reference.calibration_schema.CalibrationRunContext`'s
  ``distributed_run_context_checksum``/``provenance_manifest_checksum``
  must resolve to the real
  :class:`~src.distributed.provenance.DistributedRunContext`/
  :class:`~src.distributed.provenance_manifest.DistributedProvenanceManifest`
  that produced it;
* a :class:`~src.reference.calibration_schema.CalibrationInvocationRecord`'s
  ``worker_execution_context_checksum`` must resolve to a real
  :class:`~src.distributed.provenance.WorkerExecutionContext` *within
  that same manifest* (covers: unknown worker checksum, worker from
  another run, substituted worker context, invocation/manifest
  mismatch).

Never mutates any input.
"""

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.provenance_manifest import (
    DistributedProvenanceManifest,
    resolve_worker_context,
)
from src.reference.calibration_schema import (
    CalibrationInvocationRecord,
    CalibrationRunContext,
    InvalidCalibrationRecordError,
)


class DistributedProvenanceReconciliationError(InvalidCalibrationRecordError):
    """Raised when a calibration record's distributed-provenance
    cross-reference checksum(s) do not resolve against a real
    :class:`~src.distributed.provenance_manifest.DistributedProvenanceManifest`
    -- missing manifest, wrong manifest checksum, wrong distributed-run
    checksum, unknown/foreign/substituted worker checksum, or an
    invocation/manifest mismatch."""


def reconcile_calibration_run_context(
    context: CalibrationRunContext, manifest: DistributedProvenanceManifest
) -> None:
    """Raise :class:`DistributedProvenanceReconciliationError` unless
    ``context`` was produced under exactly ``manifest``'s own distributed
    run: both ``context.distributed_run_context_checksum`` and
    ``context.provenance_manifest_checksum`` must equal
    ``manifest.run_context.run_context_checksum``/
    ``manifest.manifest_checksum`` respectively. Never mutates either
    input."""
    if context.distributed_run_context_checksum != manifest.run_context.run_context_checksum:
        raise DistributedProvenanceReconciliationError(
            f"CalibrationRunContext.distributed_run_context_checksum "
            f"{context.distributed_run_context_checksum!r} does not match "
            f"manifest.run_context.run_context_checksum "
            f"{manifest.run_context.run_context_checksum!r} -- wrong distributed-run checksum"
        )
    if context.provenance_manifest_checksum != manifest.manifest_checksum:
        raise DistributedProvenanceReconciliationError(
            f"CalibrationRunContext.provenance_manifest_checksum "
            f"{context.provenance_manifest_checksum!r} does not match "
            f"manifest.manifest_checksum {manifest.manifest_checksum!r} -- wrong manifest "
            f"checksum"
        )


def reconcile_calibration_invocation_worker(
    invocation: CalibrationInvocationRecord, manifest: DistributedProvenanceManifest
) -> None:
    """Raise :class:`DistributedProvenanceReconciliationError` unless
    ``invocation.worker_execution_context_checksum`` resolves to a real
    :class:`~src.distributed.provenance.WorkerExecutionContext` within
    ``manifest`` (via
    :func:`~src.distributed.provenance_manifest.resolve_worker_context`)
    -- covers unknown worker checksum, worker from another run, and
    substituted worker context. Also reconciles ``invocation.context``
    against the same ``manifest`` (via
    :func:`reconcile_calibration_run_context`), so an
    invocation/manifest mismatch (an invocation whose own run context
    does not point at this manifest at all) is rejected before the
    worker-checksum lookup ever happens. Never mutates any input."""
    reconcile_calibration_run_context(invocation.context, manifest)
    try:
        resolve_worker_context(manifest, invocation.worker_execution_context_checksum)
    except InvalidDistributedProvenanceError as exc:
        raise DistributedProvenanceReconciliationError(
            f"CalibrationInvocationRecord {invocation.invocation_id!r}: "
            f"worker_execution_context_checksum "
            f"{invocation.worker_execution_context_checksum!r} does not resolve within "
            f"manifest {manifest.manifest_checksum!r}: {exc}"
        ) from exc


def reconcile_all_invocations(
    invocations: tuple[CalibrationInvocationRecord, ...],
    manifest: DistributedProvenanceManifest,
) -> None:
    """Apply :func:`reconcile_calibration_invocation_worker` to every
    entry in ``invocations``, in order, raising on the first failure
    encountered -- the distributed-provenance analogue of
    :func:`~src.reference.calibration_schema.reconcile_all`."""
    for invocation in invocations:
        reconcile_calibration_invocation_worker(invocation, manifest)


__all__ = [
    "DistributedProvenanceReconciliationError",
    "reconcile_calibration_run_context",
    "reconcile_calibration_invocation_worker",
    "reconcile_all_invocations",
]
