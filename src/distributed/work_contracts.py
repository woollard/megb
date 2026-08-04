"""MEGB-03H.2C.3B.2A: provider-neutral work/result contracts for the
reference-execution plane.

Every type here is a typed, immutable, versioned, self-checksummed
dataclass following the exact auto-compute-or-reject pattern established
throughout :mod:`~src.distributed.provenance`/:mod:`~src.distributed.identity`
-- construction recomputes the checksum from the object's own contents and
rejects a caller-supplied value that does not match.

Identity separation (the authorization's own required distinctions):

* **Scientific work identity** -- :attr:`WorkDescriptor.scientific_work_id`.
  Stable across every redelivery, retry, and lease reassignment; never
  changes for the same underlying unit of scientific work.
* **Queue delivery identity** -- :attr:`QueueWorkMessage.delivery_id`. A
  new, distinct value every time the same work item is (re)delivered by
  the queue abstraction (Pub/Sub-style at-least-once delivery); the
  ``scientific_work_id`` it carries never changes.
* **Execution attempt identity** -- :attr:`ExecutionAttempt.attempt_checksum`,
  deterministically derived from ``(scientific_work_id, lease_generation,
  worker_participant_id, distributed_run_context_checksum)``. Because
  :attr:`~src.distributed.worker_contracts.Lease.lease_generation` is
  coordinator-issued and monotonically increasing per work item, a retry
  (a new lease generation) always produces a new, distinct attempt
  identity while ``scientific_work_id`` stays constant -- exactly
  "retries have distinct attempt identities without changing scientific
  work identity."
* **Result-content identity** -- :attr:`ResultCommit.result_content_checksum`.
  Two attempts (even under different lease generations, even from
  different workers) that produce byte-identical results share the same
  result-content identity, which is what makes an identical duplicate
  commit idempotently recognizable (see :func:`reconcile_result_commit`).

Queue-visible records (:class:`QueueWorkMessage`) carry only opaque
references, checksums, schema/version identifiers, the input ordinal,
run/provenance checksums, lease/attempt information, and allowlisted
routing metadata -- there is structurally no field for candidate source,
prompts, canonical solutions, expected outputs, reference cases,
privileged diagnostics, credentials, raw infrastructure identifiers, or
unrestricted exception text. Candidate material enters only through an
immutable, checksummed :class:`ArtifactReference` -- this package has no
authority to generate or alter one.
"""

import dataclasses
from dataclasses import dataclass
from enum import Enum
from typing import Any

# pylint: disable=duplicate-code
# ExecutionAttempt's leading fields intentionally mirror
# src.distributed.worker_contracts.Lease's own leading fields (both
# identify one work item/worker/generation) -- shared boilerplate, not
# shared logic, per this project's own established convention (see e.g.
# src/reference/reference_orchestrator.py's own module-level disable).
from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
    require_checksum_algorithm_version as _require_checksum_algorithm_version,
    require_non_negative_int as _require_non_negative_int,
    require_nonempty_str as _require_nonempty_str,
    require_nonempty_str_fields as _require_nonempty_str_fields,
    require_orchestration_schema_version as _require_orchestration_schema_version,
    require_positive_int as _require_positive_int,
    require_sha256_hex as _require_sha256_hex,
    sha256_of as _sha256_of,
)


# ---------------------------------------------------------------------------
# ArtifactReference
# ---------------------------------------------------------------------------


class ArtifactKind(str, Enum):
    """Closed set of artifact kinds this package's contracts may
    reference. Managed-model/candidate-generation-plane artifact kinds
    are deliberately absent -- reserved for MEGB-03H.2C.3G, never
    designed here."""

    CANDIDATE_MANIFEST_ENTRY = "CANDIDATE_MANIFEST_ENTRY"
    RESULT_ARTIFACT = "RESULT_ARTIFACT"


@dataclass(frozen=True)
class ArtifactReference:
    """An opaque, checksummed pointer to immutable content held entirely
    outside this package (a candidate-manifest entry or a durably-stored
    result artifact) -- never the content itself. This is the only way
    candidate material may enter a :class:`WorkDescriptor`/
    :class:`QueueWorkMessage`: as an opaque reference plus a checksum,
    never inline source."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    artifact_kind: ArtifactKind
    artifact_reference_id: str
    artifact_checksum: str
    reference_checksum: str = ""

    def __post_init__(self) -> None:
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        if not isinstance(self.artifact_kind, ArtifactKind):
            raise InvalidDistributedProvenanceError(
                f"artifact_kind must be an ArtifactKind, got {self.artifact_kind!r}"
            )
        _require_nonempty_str(self, "artifact_reference_id")
        _require_sha256_hex(self, "artifact_checksum")
        payload = _artifact_reference_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.reference_checksum and self.reference_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"reference_checksum {self.reference_checksum!r} does not match the "
                f"recomputed checksum {expected_checksum!r} over its own contents -- tampered "
                f"or corrupted artifact reference"
            )
        object.__setattr__(self, "reference_checksum", expected_checksum)


def _artifact_reference_payload(reference: ArtifactReference) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": (
            reference.distributed_orchestration_schema_version
        ),
        "checksum_algorithm_version": reference.checksum_algorithm_version,
        "artifact_kind": reference.artifact_kind.value,
        "artifact_reference_id": reference.artifact_reference_id,
        "artifact_checksum": reference.artifact_checksum,
    }


def artifact_reference_to_dict(reference: ArtifactReference) -> dict[str, Any]:
    """Full-fidelity serialization of an :class:`ArtifactReference`."""
    return {
        **_artifact_reference_payload(reference),
        "reference_checksum": reference.reference_checksum,
    }


# ---------------------------------------------------------------------------
# WorkDescriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkDescriptor:
    """One unit of reference-execution work. Bound to its owning
    :class:`~src.distributed.provenance.DistributedRunContext` by
    ``distributed_run_context_checksum`` -- a checksum reference, never
    embedding -- mirroring :class:`~src.distributed.provenance.WorkerExecutionContext`'s
    own binding pattern. Deliberately carries no candidate source,
    prompt, canonical solution, expected output, or reference case --
    only an opaque, checksummed :class:`ArtifactReference` to the
    already-immutable candidate manifest entry it names."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    scientific_work_id: str
    input_ordinal: int
    distributed_run_context_checksum: str
    candidate_artifact_reference: ArtifactReference
    work_descriptor_checksum: str = ""

    def __post_init__(self) -> None:
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str(self, "scientific_work_id")
        _require_non_negative_int(self, "input_ordinal")
        _require_sha256_hex(self, "distributed_run_context_checksum")
        if not isinstance(self.candidate_artifact_reference, ArtifactReference):
            raise InvalidDistributedProvenanceError(
                "candidate_artifact_reference must be an ArtifactReference, got "
                f"{self.candidate_artifact_reference!r}"
            )
        payload = _work_descriptor_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.work_descriptor_checksum and self.work_descriptor_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"work_descriptor_checksum {self.work_descriptor_checksum!r} does not match "
                f"the recomputed checksum {expected_checksum!r} over its own contents -- "
                f"tampered or corrupted work descriptor"
            )
        object.__setattr__(self, "work_descriptor_checksum", expected_checksum)


def _work_descriptor_payload(descriptor: WorkDescriptor) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": (
            descriptor.distributed_orchestration_schema_version
        ),
        "checksum_algorithm_version": descriptor.checksum_algorithm_version,
        "scientific_work_id": descriptor.scientific_work_id,
        "input_ordinal": descriptor.input_ordinal,
        "distributed_run_context_checksum": descriptor.distributed_run_context_checksum,
        "candidate_artifact_reference": artifact_reference_to_dict(
            descriptor.candidate_artifact_reference
        ),
    }


def work_descriptor_to_dict(descriptor: WorkDescriptor) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`WorkDescriptor`."""
    return {
        **_work_descriptor_payload(descriptor),
        "work_descriptor_checksum": descriptor.work_descriptor_checksum,
    }


# ---------------------------------------------------------------------------
# QueueWorkMessage -- the queue-visible, allowlisted projection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueueWorkMessage:  # pylint: disable=too-many-instance-attributes
    """The only shape a work item may take on a queue abstraction's wire.
    Structurally excludes (no field exists for any of them): candidate
    source, prompts, canonical solutions, expected outputs, reference
    cases, privileged diagnostics, credentials or credential references,
    raw project/bucket/queue/instance/host/container/path/service-account
    identifiers, and unrestricted exception text.

    ``delivery_id`` is the **queue delivery identity** -- distinct on
    every redelivery of the same ``scientific_work_id`` (Pub/Sub-style
    at-least-once semantics); ``lease_generation``/``attempt_checksum``
    are ``None`` until the message has actually been leased to a worker.
    ``routing_environment_class``/``routing_logical_environment_id`` are
    the only routing metadata this type carries -- both already safe,
    logical values per
    :class:`~src.distributed.provenance.DistributedRunContext`'s own
    established convention, never a raw resource name."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    scientific_work_id: str
    delivery_id: str
    input_ordinal: int
    distributed_run_context_checksum: str
    candidate_artifact_reference: ArtifactReference
    lease_generation: int | None
    attempt_checksum: str | None
    routing_environment_class: str
    routing_logical_environment_id: str
    message_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str_fields(
            self,
            (
                "scientific_work_id",
                "delivery_id",
                "routing_environment_class",
                "routing_logical_environment_id",
            ),
        )
        _require_non_negative_int(self, "input_ordinal")
        _require_sha256_hex(self, "distributed_run_context_checksum")
        if not isinstance(self.candidate_artifact_reference, ArtifactReference):
            raise InvalidDistributedProvenanceError(
                "candidate_artifact_reference must be an ArtifactReference, got "
                f"{self.candidate_artifact_reference!r}"
            )
        if self.lease_generation is not None:
            if (
                not isinstance(self.lease_generation, int)
                or isinstance(self.lease_generation, bool)
                or self.lease_generation < 1
            ):
                raise InvalidDistributedProvenanceError(
                    f"lease_generation must be a positive int or None, got "
                    f"{self.lease_generation!r}"
                )
        if self.attempt_checksum is not None:
            _require_sha256_hex(self, "attempt_checksum")

        payload = _queue_work_message_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.message_checksum and self.message_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"message_checksum {self.message_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted queue work message"
            )
        object.__setattr__(self, "message_checksum", expected_checksum)


def _queue_work_message_payload(message: QueueWorkMessage) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": (
            message.distributed_orchestration_schema_version
        ),
        "checksum_algorithm_version": message.checksum_algorithm_version,
        "scientific_work_id": message.scientific_work_id,
        "delivery_id": message.delivery_id,
        "input_ordinal": message.input_ordinal,
        "distributed_run_context_checksum": message.distributed_run_context_checksum,
        "candidate_artifact_reference": artifact_reference_to_dict(
            message.candidate_artifact_reference
        ),
        "lease_generation": message.lease_generation,
        "attempt_checksum": message.attempt_checksum,
        "routing_environment_class": message.routing_environment_class,
        "routing_logical_environment_id": message.routing_logical_environment_id,
    }


def queue_work_message_to_dict(message: QueueWorkMessage) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`QueueWorkMessage`."""
    return {**_queue_work_message_payload(message), "message_checksum": message.message_checksum}


def queue_work_message_field_names() -> frozenset[str]:
    """The exact set of field names :class:`QueueWorkMessage` declares --
    used by leakage tests to structurally assert that no forbidden
    concept (candidate source, prompt, canonical solution, credential,
    raw resource name, unrestricted exception text) is present."""
    return frozenset(field.name for field in dataclasses.fields(QueueWorkMessage))


def work_descriptor_to_queue_message(  # pylint: disable=too-many-arguments
    descriptor: WorkDescriptor,
    *,
    delivery_id: str,
    routing_environment_class: str,
    routing_logical_environment_id: str,
    lease_generation: int | None = None,
    attempt_checksum: str | None = None,
) -> QueueWorkMessage:
    """Project a :class:`WorkDescriptor` onto its queue-visible
    :class:`QueueWorkMessage` form -- the only sanctioned path from a
    work descriptor onto a queue's wire, so every queue message is
    provably derived from, and consistent with, a real work descriptor."""
    schema_version = descriptor.distributed_orchestration_schema_version
    return QueueWorkMessage(
        distributed_orchestration_schema_version=schema_version,
        checksum_algorithm_version=descriptor.checksum_algorithm_version,
        scientific_work_id=descriptor.scientific_work_id,
        delivery_id=delivery_id,
        input_ordinal=descriptor.input_ordinal,
        distributed_run_context_checksum=descriptor.distributed_run_context_checksum,
        candidate_artifact_reference=descriptor.candidate_artifact_reference,
        lease_generation=lease_generation,
        attempt_checksum=attempt_checksum,
        routing_environment_class=routing_environment_class,
        routing_logical_environment_id=routing_logical_environment_id,
    )


# ---------------------------------------------------------------------------
# CancellationRequest
# ---------------------------------------------------------------------------


class CancellationScope(str, Enum):
    """Distinguishes cancellation before any lease was ever issued from
    cancellation after execution had already begun -- the authorization's
    own required distinction ("cancellation before admission differs
    from cancellation after execution begins")."""

    BEFORE_ADMISSION = "BEFORE_ADMISSION"
    AFTER_LEASE = "AFTER_LEASE"


@dataclass(frozen=True)
class CancellationRequest:
    """A typed request to cancel one unit of scientific work."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    scientific_work_id: str
    cancellation_scope: CancellationScope
    requested_at_logical_clock: int
    cancellation_checksum: str = ""

    def __post_init__(self) -> None:
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str(self, "scientific_work_id")
        if not isinstance(self.cancellation_scope, CancellationScope):
            raise InvalidDistributedProvenanceError(
                f"cancellation_scope must be a CancellationScope, got {self.cancellation_scope!r}"
            )
        _require_non_negative_int(self, "requested_at_logical_clock")
        payload = _cancellation_request_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.cancellation_checksum and self.cancellation_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"cancellation_checksum {self.cancellation_checksum!r} does not match the "
                f"recomputed checksum {expected_checksum!r} over its own contents -- tampered "
                f"or corrupted cancellation request"
            )
        object.__setattr__(self, "cancellation_checksum", expected_checksum)


def _cancellation_request_payload(request: CancellationRequest) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": (
            request.distributed_orchestration_schema_version
        ),
        "checksum_algorithm_version": request.checksum_algorithm_version,
        "scientific_work_id": request.scientific_work_id,
        "cancellation_scope": request.cancellation_scope.value,
        "requested_at_logical_clock": request.requested_at_logical_clock,
    }


def cancellation_request_to_dict(request: CancellationRequest) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`CancellationRequest`."""
    return {
        **_cancellation_request_payload(request),
        "cancellation_checksum": request.cancellation_checksum,
    }


# ---------------------------------------------------------------------------
# ExecutionAttempt
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionAttempt:
    """The **execution attempt identity** -- deterministically derived
    from ``(scientific_work_id, lease_generation, worker_participant_id,
    distributed_run_context_checksum)``. A retry under a new
    (coordinator-issued, monotonically increasing) ``lease_generation``
    always produces a new, distinct ``attempt_checksum`` while
    ``scientific_work_id`` stays constant -- this is what "retries have
    distinct attempt identities without changing scientific work
    identity" means concretely."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    scientific_work_id: str
    worker_participant_id: str
    lease_generation: int
    distributed_run_context_checksum: str
    attempt_checksum: str = ""

    def __post_init__(self) -> None:
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str_fields(self, ("scientific_work_id", "worker_participant_id"))
        _require_positive_int(self, "lease_generation")
        _require_sha256_hex(self, "distributed_run_context_checksum")
        payload = _execution_attempt_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.attempt_checksum and self.attempt_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"attempt_checksum {self.attempt_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted execution attempt"
            )
        object.__setattr__(self, "attempt_checksum", expected_checksum)


def _execution_attempt_payload(attempt: ExecutionAttempt) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": (
            attempt.distributed_orchestration_schema_version
        ),
        "checksum_algorithm_version": attempt.checksum_algorithm_version,
        "scientific_work_id": attempt.scientific_work_id,
        "worker_participant_id": attempt.worker_participant_id,
        "lease_generation": attempt.lease_generation,
        "distributed_run_context_checksum": attempt.distributed_run_context_checksum,
    }


def execution_attempt_to_dict(attempt: ExecutionAttempt) -> dict[str, Any]:
    """Full-fidelity serialization of an :class:`ExecutionAttempt`."""
    return {**_execution_attempt_payload(attempt), "attempt_checksum": attempt.attempt_checksum}


# ---------------------------------------------------------------------------
# ResultCommit / Acknowledgement
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultCommit:
    """A durable claim that ``attempt_checksum`` produced a result whose
    content identity is ``result_content_checksum``. Two attempts (even
    under different lease generations, even from different workers)
    that produce byte-identical results share the same
    ``result_content_checksum`` -- the **result-content identity**,
    distinct from both the scientific work identity and the execution
    attempt identity that produced it."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    scientific_work_id: str
    attempt_checksum: str
    lease_generation: int
    result_content_checksum: str
    result_artifact_reference: ArtifactReference
    commit_checksum: str = ""

    def __post_init__(self) -> None:
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str(self, "scientific_work_id")
        _require_sha256_hex(self, "attempt_checksum")
        _require_positive_int(self, "lease_generation")
        _require_sha256_hex(self, "result_content_checksum")
        if not isinstance(self.result_artifact_reference, ArtifactReference):
            raise InvalidDistributedProvenanceError(
                "result_artifact_reference must be an ArtifactReference, got "
                f"{self.result_artifact_reference!r}"
            )
        if self.result_artifact_reference.artifact_kind != ArtifactKind.RESULT_ARTIFACT:
            raise InvalidDistributedProvenanceError(
                "result_artifact_reference must have artifact_kind=RESULT_ARTIFACT, got "
                f"{self.result_artifact_reference.artifact_kind!r}"
            )
        payload = _result_commit_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.commit_checksum and self.commit_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"commit_checksum {self.commit_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted result commit"
            )
        object.__setattr__(self, "commit_checksum", expected_checksum)


def _result_commit_payload(commit: ResultCommit) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": (
            commit.distributed_orchestration_schema_version
        ),
        "checksum_algorithm_version": commit.checksum_algorithm_version,
        "scientific_work_id": commit.scientific_work_id,
        "attempt_checksum": commit.attempt_checksum,
        "lease_generation": commit.lease_generation,
        "result_content_checksum": commit.result_content_checksum,
        "result_artifact_reference": artifact_reference_to_dict(commit.result_artifact_reference),
    }


def result_commit_to_dict(commit: ResultCommit) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`ResultCommit`."""
    return {**_result_commit_payload(commit), "commit_checksum": commit.commit_checksum}


class ConflictingResultCommitError(InvalidDistributedProvenanceError):
    """Raised by :func:`reconcile_result_commit` when an incoming commit
    for the same ``scientific_work_id`` carries a different
    ``result_content_checksum`` than an already-durable commit --
    conflicting commits block rather than silently overwrite."""


class ResultCommitReconciliation(str, Enum):
    """The two, and only two, outcomes of :func:`reconcile_result_commit`."""

    ACCEPTED_NEW = "ACCEPTED_NEW"
    IDEMPOTENT_DUPLICATE = "IDEMPOTENT_DUPLICATE"


def reconcile_result_commit(
    existing: ResultCommit | None, incoming: ResultCommit
) -> ResultCommitReconciliation:
    """Reconcile ``incoming`` against ``existing`` (``None`` if this work
    item has no durable commit yet). Returns ``ACCEPTED_NEW`` when there
    is no prior commit; returns ``IDEMPOTENT_DUPLICATE`` when
    ``incoming.result_content_checksum`` matches an existing commit's
    (the crash-after-commit-before-ack / duplicate-delivery case,
    reconciled idempotently); raises :class:`ConflictingResultCommitError`
    when the two commits' ``result_content_checksum`` values differ --
    conflicting commits must never silently overwrite one another."""
    if existing is None:
        return ResultCommitReconciliation.ACCEPTED_NEW
    if existing.scientific_work_id != incoming.scientific_work_id:
        raise InvalidDistributedProvenanceError(
            "reconcile_result_commit requires existing and incoming to share the same "
            f"scientific_work_id, got {existing.scientific_work_id!r} and "
            f"{incoming.scientific_work_id!r}"
        )
    if existing.result_content_checksum == incoming.result_content_checksum:
        return ResultCommitReconciliation.IDEMPOTENT_DUPLICATE
    raise ConflictingResultCommitError(
        f"conflicting result commit for scientific_work_id {incoming.scientific_work_id!r}: "
        f"existing result_content_checksum {existing.result_content_checksum!r} != incoming "
        f"{incoming.result_content_checksum!r} -- refusing to overwrite"
    )


@dataclass(frozen=True)
class Acknowledgement:
    """A typed acknowledgement of a specific, already-durable
    :class:`ResultCommit`. Binds to that commit by both
    ``attempt_checksum`` and ``result_content_checksum`` -- see
    :func:`require_commit_before_ack`, which enforces that an
    acknowledgement can only ever be validated against the commit it
    actually names."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    scientific_work_id: str
    attempt_checksum: str
    result_content_checksum: str
    ack_checksum: str = ""

    def __post_init__(self) -> None:
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str(self, "scientific_work_id")
        _require_sha256_hex(self, "attempt_checksum")
        _require_sha256_hex(self, "result_content_checksum")
        payload = _acknowledgement_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.ack_checksum and self.ack_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"ack_checksum {self.ack_checksum!r} does not match the recomputed checksum "
                f"{expected_checksum!r} over its own contents -- tampered or corrupted "
                f"acknowledgement"
            )
        object.__setattr__(self, "ack_checksum", expected_checksum)


def _acknowledgement_payload(ack: Acknowledgement) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": ack.distributed_orchestration_schema_version,
        "checksum_algorithm_version": ack.checksum_algorithm_version,
        "scientific_work_id": ack.scientific_work_id,
        "attempt_checksum": ack.attempt_checksum,
        "result_content_checksum": ack.result_content_checksum,
    }


def acknowledgement_to_dict(ack: Acknowledgement) -> dict[str, Any]:
    """Full-fidelity serialization of an :class:`Acknowledgement`."""
    return {**_acknowledgement_payload(ack), "ack_checksum": ack.ack_checksum}


def require_commit_before_ack(commit: ResultCommit, ack: Acknowledgement) -> None:
    """Raise :class:`InvalidDistributedProvenanceError` unless ``ack``
    names exactly the ``commit`` it acknowledges (matching
    ``scientific_work_id``, ``attempt_checksum``, and
    ``result_content_checksum``) -- "acknowledgement occurs only after
    durable, checksum-verified result commit" enforced as a direct
    equality check, not a convention."""
    if (
        commit.scientific_work_id != ack.scientific_work_id
        or commit.attempt_checksum != ack.attempt_checksum
        or commit.result_content_checksum != ack.result_content_checksum
    ):
        raise InvalidDistributedProvenanceError(
            "acknowledgement does not match the result commit it claims to acknowledge -- "
            f"commit=({commit.scientific_work_id!r}, {commit.attempt_checksum!r}, "
            f"{commit.result_content_checksum!r}) ack=({ack.scientific_work_id!r}, "
            f"{ack.attempt_checksum!r}, {ack.result_content_checksum!r})"
        )


# ---------------------------------------------------------------------------
# TerminalDisposition
# ---------------------------------------------------------------------------


class TerminalDispositionKind(str, Enum):
    """Closed set of terminal outcomes a unit of scientific work may
    reach. Mirrors :class:`~src.distributed.state_machine.WorkItemState`'s
    own three terminal states plus the acknowledged-completed success
    case."""

    COMPLETED_ACKNOWLEDGED = "COMPLETED_ACKNOWLEDGED"
    CANCELLED_BEFORE_ADMISSION = "CANCELLED_BEFORE_ADMISSION"
    CANCELLED_AFTER_LEASE = "CANCELLED_AFTER_LEASE"
    DEAD_LETTERED = "DEAD_LETTERED"


class TerminalDispositionReason(str, Enum):
    """Closed set of reasons a terminal disposition was reached -- never
    free-form diagnostic text, per the authorization's own "terminal
    disposition is typed and closed, with no free-form diagnostic in
    safe records" requirement."""

    NORMAL_COMPLETION = "NORMAL_COMPLETION"
    USER_REQUESTED_CANCELLATION = "USER_REQUESTED_CANCELLATION"
    RETRY_CEILING_EXCEEDED = "RETRY_CEILING_EXCEEDED"
    LEASE_REASSIGNMENT_LIMIT_EXCEEDED = "LEASE_REASSIGNMENT_LIMIT_EXCEEDED"


@dataclass(frozen=True)
class TerminalDisposition:
    """The typed, closed final outcome of one unit of scientific work."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    scientific_work_id: str
    disposition: TerminalDispositionKind
    disposition_reason: TerminalDispositionReason
    attempt_count: int
    disposition_checksum: str = ""

    def __post_init__(self) -> None:
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str(self, "scientific_work_id")
        if not isinstance(self.disposition, TerminalDispositionKind):
            raise InvalidDistributedProvenanceError(
                f"disposition must be a TerminalDispositionKind, got {self.disposition!r}"
            )
        if not isinstance(self.disposition_reason, TerminalDispositionReason):
            raise InvalidDistributedProvenanceError(
                f"disposition_reason must be a TerminalDispositionReason, got "
                f"{self.disposition_reason!r}"
            )
        _require_non_negative_int(self, "attempt_count")
        payload = _terminal_disposition_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.disposition_checksum and self.disposition_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"disposition_checksum {self.disposition_checksum!r} does not match the "
                f"recomputed checksum {expected_checksum!r} over its own contents -- tampered "
                f"or corrupted terminal disposition"
            )
        object.__setattr__(self, "disposition_checksum", expected_checksum)


def _terminal_disposition_payload(disposition: TerminalDisposition) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": (
            disposition.distributed_orchestration_schema_version
        ),
        "checksum_algorithm_version": disposition.checksum_algorithm_version,
        "scientific_work_id": disposition.scientific_work_id,
        "disposition": disposition.disposition.value,
        "disposition_reason": disposition.disposition_reason.value,
        "attempt_count": disposition.attempt_count,
    }


def terminal_disposition_to_dict(disposition: TerminalDisposition) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`TerminalDisposition`."""
    return {
        **_terminal_disposition_payload(disposition),
        "disposition_checksum": disposition.disposition_checksum,
    }


__all__ = [
    "ArtifactKind",
    "ArtifactReference",
    "artifact_reference_to_dict",
    "WorkDescriptor",
    "work_descriptor_to_dict",
    "QueueWorkMessage",
    "queue_work_message_to_dict",
    "queue_work_message_field_names",
    "work_descriptor_to_queue_message",
    "CancellationScope",
    "CancellationRequest",
    "cancellation_request_to_dict",
    "ExecutionAttempt",
    "execution_attempt_to_dict",
    "ResultCommit",
    "result_commit_to_dict",
    "ConflictingResultCommitError",
    "ResultCommitReconciliation",
    "reconcile_result_commit",
    "Acknowledgement",
    "acknowledgement_to_dict",
    "require_commit_before_ack",
    "TerminalDispositionKind",
    "TerminalDispositionReason",
    "TerminalDisposition",
    "terminal_disposition_to_dict",
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION",
]
