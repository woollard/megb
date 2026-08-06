"""MEGB-03H.2C.3B.3: the distributed-provenance manifest -- a typed,
immutable, versioned, self-checksummed artifact bundling everything a
later calibration-provenance reconciliation needs to prove a given
calibration invocation was actually produced by a specific, real,
content-bound distributed run.

Composes exclusively already-accepted ``src.distributed`` types rather
than reimplementing any of them: :class:`~src.distributed.provenance.DistributedRunContext`,
:class:`~src.distributed.provenance.WorkerExecutionContext`,
:class:`~src.distributed.identity.MixedWorkerProvenanceSummary` (via
:func:`~src.distributed.identity.aggregate_worker_provenance`),
:class:`~src.distributed.identity.QualificationIdentity` (via
:func:`~src.distributed.identity.qualification_identity_for`),
:func:`~src.distributed.qualification_gate.evaluate_qualification_gate`,
and :class:`~src.distributed.safe_summary.SafeRedactedSummary` (via
:func:`~src.distributed.safe_summary.build_safe_redacted_summary`). This
module adds only two new plain fields (``generation_command``,
``code_revision``) and the manifest's own wrapping/checksum/resolution
logic.

Per this checkpoint's own frozen design
(``docs/reference/megb-03h2c3b3-calibration-provenance-integration-design.md``
§2/§7): the **full** manifest (embedding complete
``WorkerExecutionContext`` records, ``generation_command``,
``code_revision``) is protected operational/calibration evidence, never
committed to a public report path -- only ``safe_redacted_summary`` and
``manifest_checksum`` themselves are safe to embed in any committed
report. Never imports ``src.reference`` (this package's own established
layering rule, unchanged by this checkpoint).
"""

# This module's own _SECRET_LOOKING_PATTERNS/_reject_if_looks_like_secret
# deliberately duplicate src.distributed.protected_mapping's own private
# pattern set (see the docstring above) rather than cross-importing a
# private helper across modules -- shared boilerplate, not shared logic,
# mirroring this project's own established per-module small-helper-
# duplication precedent.
# pylint: disable=duplicate-code

import re
from dataclasses import dataclass
from typing import Any, Mapping

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    InvalidDistributedProvenanceError,
    require_nonempty_str as _require_nonempty_str,
    require_sha256_hex as _require_sha256_hex,
    sha256_of as _sha256_of,
)
from src.distributed.identity import (
    MixedWorkerProvenanceSummary,
    QualificationIdentity,
    aggregate_worker_provenance,
    mixed_worker_provenance_summary_from_dict,
    mixed_worker_provenance_summary_to_dict,
    qualification_identity_for,
    qualification_identity_from_dict,
    qualification_identity_to_dict,
    require_workers_belong_to_run,
)
from src.distributed.provenance import (
    DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
    DistributedRunContext,
    WorkerExecutionContext,
    distributed_run_context_from_dict,
    distributed_run_context_to_dict,
    worker_execution_context_from_dict,
    worker_execution_context_to_dict,
)
from src.distributed.qualification_gate import (
    ProvenanceGateFailureReason,
    ProvenanceGateReadiness,
    evaluate_qualification_gate,
)
from src.distributed.safe_summary import (
    SafeRedactedSummary,
    build_safe_redacted_summary,
    safe_redacted_summary_from_dict,
    safe_redacted_summary_to_dict,
)

# MEGB-03H.2C.3B.3: a fourth, independent src.distributed schema family
# (alongside DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
# DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION, and the B.2C-introduced
# OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION) -- this manifest's own
# field shape evolves on its own version counter, per this project's
# established one-schema-family-per-persisted-shape discipline.
DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION = (
    "megb-03h2c3b3-distributed-provenance-manifest-v1"
)

# Defense-in-depth only -- not a complete secret-detection guarantee.
# Duplicated from src.distributed.protected_mapping's own private pattern
# set rather than cross-importing a private helper across modules,
# mirroring this project's established per-module small-helper-
# duplication precedent (e.g. each safe-report module defines its own
# small checksum/validation helpers rather than importing another
# module's private ones).
_SECRET_LOOKING_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r'"type"\s*:\s*"service_account"'),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    re.compile(r"ya29\.[0-9A-Za-z_\-]+"),
    re.compile(r"xox[baprs]-[0-9A-Za-z\-]+"),
)


def _reject_if_looks_like_secret(value: str, field_name: str) -> None:
    for pattern in _SECRET_LOOKING_PATTERNS:
        if pattern.search(value):
            raise InvalidDistributedProvenanceError(
                f"{field_name!r} contains a value matching a known credential/secret shape -- "
                f"refusing to construct a DistributedProvenanceManifest carrying it."
            )


class UnsupportedDistributedProvenanceManifestSchemaVersionError(
    InvalidDistributedProvenanceError
):
    """Raised when deserializing a payload stamped with a different
    ``DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION`` than this module
    currently implements."""


def _require_manifest_schema_version(obj: object) -> None:
    value = getattr(obj, "distributed_provenance_manifest_schema_version")
    if value != DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION:
        raise UnsupportedDistributedProvenanceManifestSchemaVersionError(
            f"distributed_provenance_manifest_schema_version {value!r} does not match the "
            f"version this module implements "
            f"({DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION!r})"
        )


@dataclass(frozen=True)
class DistributedProvenanceManifest:  # pylint: disable=too-many-instance-attributes
    """The full, protected, self-checksummed distributed-provenance
    manifest for one distributed run. Never committed as-is -- see
    ``safe_redacted_summary`` for the one field safe to embed in a
    committed report, and ``manifest_checksum`` for the one opaque,
    content-bound identifier safe to reference by value.

    ``__post_init__`` independently re-verifies worker/context
    consistency (every worker belongs to ``run_context``, no duplicate
    ``worker_participant_id``) even though :func:`build_distributed_provenance_manifest`
    already enforces this via :func:`~src.distributed.identity.aggregate_worker_provenance`
    -- a hand-constructed instance bypassing the builder is equally
    rejected, never merely a builder-level convenience check."""

    distributed_provenance_manifest_schema_version: str
    checksum_algorithm_version: str
    run_context: DistributedRunContext
    worker_execution_contexts: tuple[WorkerExecutionContext, ...]
    topology_summary: MixedWorkerProvenanceSummary
    qualification_identity: QualificationIdentity
    qualification_gate_readiness: str
    qualification_gate_missing_dimensions: tuple[str, ...]
    generation_command: str
    code_revision: str
    safe_redacted_summary: SafeRedactedSummary
    manifest_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _require_manifest_schema_version(self)
        if self.checksum_algorithm_version != CHECKSUM_ALGORITHM_VERSION:
            raise InvalidDistributedProvenanceError(
                f"checksum_algorithm_version {self.checksum_algorithm_version!r} does not "
                f"match the version this package implements ({CHECKSUM_ALGORITHM_VERSION!r})"
            )
        if not isinstance(self.run_context, DistributedRunContext):
            raise InvalidDistributedProvenanceError(
                f"run_context must be a DistributedRunContext, got {self.run_context!r}"
            )
        if (
            not isinstance(self.worker_execution_contexts, tuple)
            or not self.worker_execution_contexts
        ):
            raise InvalidDistributedProvenanceError(
                "worker_execution_contexts must be a nonempty tuple of WorkerExecutionContext, "
                f"got {self.worker_execution_contexts!r}"
            )
        if not all(
            isinstance(worker, WorkerExecutionContext) for worker in self.worker_execution_contexts
        ):
            raise InvalidDistributedProvenanceError(
                "every entry in worker_execution_contexts must be a WorkerExecutionContext"
            )
        require_workers_belong_to_run(self.run_context, self.worker_execution_contexts)
        participant_ids = [
            worker.worker_participant_id for worker in self.worker_execution_contexts
        ]
        if len(set(participant_ids)) != len(participant_ids):
            raise InvalidDistributedProvenanceError(
                "worker_execution_contexts contains a duplicate worker_participant_id -- the "
                "same execution participant cannot be reported more than once in one manifest"
            )
        checksums = [
            worker.worker_context_checksum for worker in self.worker_execution_contexts
        ]
        if checksums != sorted(checksums):
            raise InvalidDistributedProvenanceError(
                "worker_execution_contexts must be stored sorted by worker_context_checksum "
                "for deterministic, order-independent serialization"
            )
        if not isinstance(self.topology_summary, MixedWorkerProvenanceSummary):
            raise InvalidDistributedProvenanceError(
                "topology_summary must be a MixedWorkerProvenanceSummary, got "
                f"{self.topology_summary!r}"
            )
        if self.topology_summary.run_context_checksum != self.run_context.run_context_checksum:
            raise InvalidDistributedProvenanceError(
                "topology_summary was not built from run_context (run_context_checksum "
                "mismatch)"
            )
        if not isinstance(self.qualification_identity, QualificationIdentity):
            raise InvalidDistributedProvenanceError(
                "qualification_identity must be a QualificationIdentity, got "
                f"{self.qualification_identity!r}"
            )
        if (
            self.qualification_identity.run_context_checksum
            != self.run_context.run_context_checksum
        ):
            raise InvalidDistributedProvenanceError(
                "qualification_identity was not derived from run_context (run_context_checksum "
                "mismatch)"
            )
        try:
            ProvenanceGateReadiness(self.qualification_gate_readiness)
        except ValueError as exc:
            raise InvalidDistributedProvenanceError(
                f"qualification_gate_readiness {self.qualification_gate_readiness!r} is not a "
                "valid ProvenanceGateReadiness value"
            ) from exc
        if not isinstance(self.qualification_gate_missing_dimensions, tuple):
            raise InvalidDistributedProvenanceError(
                "qualification_gate_missing_dimensions must be a tuple, got "
                f"{type(self.qualification_gate_missing_dimensions).__name__}"
            )
        for reason in self.qualification_gate_missing_dimensions:
            try:
                ProvenanceGateFailureReason(reason)
            except ValueError as exc:
                raise InvalidDistributedProvenanceError(
                    f"qualification_gate_missing_dimensions entry {reason!r} is not a valid "
                    "ProvenanceGateFailureReason value"
                ) from exc
        _require_nonempty_str(self, "generation_command")
        _require_nonempty_str(self, "code_revision")
        _reject_if_looks_like_secret(self.generation_command, "generation_command")
        _reject_if_looks_like_secret(self.code_revision, "code_revision")
        if not isinstance(self.safe_redacted_summary, SafeRedactedSummary):
            raise InvalidDistributedProvenanceError(
                "safe_redacted_summary must be a SafeRedactedSummary, got "
                f"{self.safe_redacted_summary!r}"
            )
        if (
            self.safe_redacted_summary.qualification_identity_checksum
            != self.qualification_identity.identity_checksum
        ):
            raise InvalidDistributedProvenanceError(
                "safe_redacted_summary was not built from qualification_identity (checksum "
                "mismatch)"
            )

        payload = _manifest_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.manifest_checksum and self.manifest_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"manifest_checksum {self.manifest_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or corrupted "
                f"distributed provenance manifest"
            )
        object.__setattr__(self, "manifest_checksum", expected_checksum)


def _manifest_payload(manifest: DistributedProvenanceManifest) -> dict[str, Any]:
    return {
        "distributed_provenance_manifest_schema_version": (
            manifest.distributed_provenance_manifest_schema_version
        ),
        "checksum_algorithm_version": manifest.checksum_algorithm_version,
        "run_context": distributed_run_context_to_dict(manifest.run_context),
        "worker_execution_contexts": [
            worker_execution_context_to_dict(worker)
            for worker in manifest.worker_execution_contexts
        ],
        "topology_summary": mixed_worker_provenance_summary_to_dict(manifest.topology_summary),
        "qualification_identity": qualification_identity_to_dict(manifest.qualification_identity),
        "qualification_gate_readiness": manifest.qualification_gate_readiness,
        "qualification_gate_missing_dimensions": list(
            manifest.qualification_gate_missing_dimensions
        ),
        "generation_command": manifest.generation_command,
        "code_revision": manifest.code_revision,
        "safe_redacted_summary": safe_redacted_summary_to_dict(manifest.safe_redacted_summary),
    }


def distributed_provenance_manifest_to_dict(
    manifest: DistributedProvenanceManifest,
) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`DistributedProvenanceManifest`
    -- protected evidence, never a safe/committed report. Caller-managed
    temporary/synthetic path only."""
    return {**_manifest_payload(manifest), "manifest_checksum": manifest.manifest_checksum}


def distributed_provenance_manifest_from_dict(
    data: Mapping[str, Any]
) -> DistributedProvenanceManifest:
    """Inverse of :func:`distributed_provenance_manifest_to_dict`."""
    try:
        return DistributedProvenanceManifest(
            distributed_provenance_manifest_schema_version=data[
                "distributed_provenance_manifest_schema_version"
            ],
            checksum_algorithm_version=data["checksum_algorithm_version"],
            run_context=distributed_run_context_from_dict(data["run_context"]),
            worker_execution_contexts=tuple(
                worker_execution_context_from_dict(worker)
                for worker in data["worker_execution_contexts"]
            ),
            topology_summary=mixed_worker_provenance_summary_from_dict(data["topology_summary"]),
            qualification_identity=qualification_identity_from_dict(
                data["qualification_identity"]
            ),
            qualification_gate_readiness=data["qualification_gate_readiness"],
            qualification_gate_missing_dimensions=tuple(
                data["qualification_gate_missing_dimensions"]
            ),
            generation_command=data["generation_command"],
            code_revision=data["code_revision"],
            safe_redacted_summary=safe_redacted_summary_from_dict(data["safe_redacted_summary"]),
            manifest_checksum=data["manifest_checksum"],
        )
    except KeyError as exc:
        raise InvalidDistributedProvenanceError(
            f"missing required distributed provenance manifest field: {exc}"
        ) from exc
    except ValueError as exc:
        raise InvalidDistributedProvenanceError(
            f"malformed distributed provenance manifest: {exc}"
        ) from exc


def build_distributed_provenance_manifest(
    run_context: DistributedRunContext,
    workers: tuple[WorkerExecutionContext, ...],
    *,
    generation_command: str,
    code_revision: str,
) -> DistributedProvenanceManifest:
    """Build the :class:`DistributedProvenanceManifest` for ``run_context``
    and its contributing ``workers``. Rejects (via
    :mod:`~src.distributed.identity`'s own
    :class:`~src.distributed.identity.MixedWorkerReconciliationError`
    subclasses) an empty ``workers`` tuple, any worker whose
    ``parent_run_context_checksum`` does not match ``run_context``, or a
    duplicate ``worker_participant_id`` -- before this manifest is ever
    constructed."""
    topology_summary = aggregate_worker_provenance(run_context, workers)
    qualification_identity = qualification_identity_for(run_context, topology_summary)
    gate_result = evaluate_qualification_gate(run_context, workers)
    safe_summary = build_safe_redacted_summary(run_context, workers, qualification_identity)
    sorted_workers = tuple(
        sorted(workers, key=lambda worker: worker.worker_context_checksum)
    )
    return DistributedProvenanceManifest(
        distributed_provenance_manifest_schema_version=(
            DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION
        ),
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        run_context=run_context,
        worker_execution_contexts=sorted_workers,
        topology_summary=topology_summary,
        qualification_identity=qualification_identity,
        qualification_gate_readiness=gate_result.readiness.value,
        qualification_gate_missing_dimensions=tuple(
            reason.value for reason in gate_result.missing_dimensions
        ),
        generation_command=generation_command,
        code_revision=code_revision,
        safe_redacted_summary=safe_summary,
    )


def resolve_worker_context(
    manifest: DistributedProvenanceManifest, worker_context_checksum: str
) -> WorkerExecutionContext:
    """Return the :class:`~src.distributed.provenance.WorkerExecutionContext`
    in ``manifest`` whose ``worker_context_checksum`` equals
    ``worker_context_checksum``. Raises
    :class:`~src.distributed._checksums.InvalidDistributedProvenanceError`
    if none resolves -- "a checksum without a persisted, verifiable
    referenced manifest is insufficient": this is the one function that
    turns a bare checksum string into a verified reference."""
    _require_sha256_hex(
        _ChecksumHolder(worker_context_checksum), "worker_context_checksum"
    )
    for worker in manifest.worker_execution_contexts:
        if worker.worker_context_checksum == worker_context_checksum:
            return worker
    raise InvalidDistributedProvenanceError(
        f"worker_context_checksum {worker_context_checksum!r} does not resolve to any "
        f"WorkerExecutionContext in this manifest (manifest_checksum "
        f"{manifest.manifest_checksum!r}) -- unknown worker, worker from another run, or "
        f"substituted worker context"
    )


@dataclass(frozen=True)
class _ChecksumHolder:
    """Tiny adapter so :func:`~src.distributed._checksums.require_sha256_hex`
    (which reads its field off an object via ``getattr``) can validate a
    bare string argument without a bespoke inline regex here."""

    worker_context_checksum: str


__all__ = [
    "DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION",
    "UnsupportedDistributedProvenanceManifestSchemaVersionError",
    "DistributedProvenanceManifest",
    "distributed_provenance_manifest_to_dict",
    "distributed_provenance_manifest_from_dict",
    "build_distributed_provenance_manifest",
    "resolve_worker_context",
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_PROVENANCE_SCHEMA_VERSION",
]
