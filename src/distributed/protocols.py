"""MEGB-03H.2C.3B.2A: provider-neutral structural interfaces for the
storage/queue/registry/audit boundaries a future coordinator/worker engine
(MEGB-03H.2C.3B.2B, not this checkpoint) will implement.

Every interface here is a :class:`typing.Protocol` -- a structural
signature only, never a concrete implementation, never in-memory state,
never a thread/process pool. This checkpoint's own explicit non-goal is
"a working coordinator loop... queue polling... cloud adapters" -- these
Protocols exist so B.2B can implement (and this checkpoint's own tests can
exercise via a minimal synthetic fake, never a real backing store) against
a frozen, typed contract, without this module itself providing any
runtime behavior.

**MEGB-03H.2C.3B.2B.1 correction:** adds
:class:`AtomicWorkStoreProtocol` -- the provider-neutral contract for the
single authoritative, revisioned work-state record B.2B.1's own
atomicity audit found :class:`ResultStoreProtocol` and
:class:`LeaseStateStoreProtocol` cannot express by composition. Those two
Protocols are retained, unmodified in method shape, but their docstrings
now mark them non-authoritative for the commit path -- see each one's own
docstring below.

**MEGB-03H.2C.3B.2B.2 addition:** adds :class:`ArtifactReaderProtocol`,
:class:`ArtifactWriterProtocol`, and :class:`BudgetReservationProtocol` --
the coordinator/worker engine's own additional dependency-injection
boundaries, additive to every Protocol above (the minimal
:class:`ArtifactStoreProtocol` B.2A already defined is untouched). Also
completes two Protocol declarations that were incomplete relative to
their own already-accepted concrete implementations --
:meth:`AtomicWorkStoreProtocol.transition_to_executing` (already present
on ``AtomicWorkStore`` since B.2B.1; simply never declared on the
Protocol, since no B.2B.1 caller needed it) and
:meth:`WorkerRegistryProtocol.registration_status` (already present on
``InMemoryWorkerRegistry`` since B.2B.1, same reason). Neither change
alters any concrete class's behavior or any existing test; both are
Protocol-declaration completeness fixes the coordinator engine's own use
surfaced, not schema/data-shape changes (Protocols carry no
``distributed_orchestration_schema_version``/self-checksum field to bump
in the first place)."""

from typing import Callable, Protocol

from src.distributed.artifact_store import ArtifactMetadata
from src.distributed.atomic_work_store import AuthoritativeWorkRecord
from src.distributed.budget_store import BudgetReservation
from src.distributed.personal_policy import DataClassification, WorkloadClass
from src.distributed.state_machine import WorkItemState
from src.distributed.work_contracts import (
    Acknowledgement,
    ArtifactReference,
    CancellationRequest,
    ExecutionAttempt,
    QueueWorkMessage,
    ResultCommit,
    TerminalDisposition,
    WorkDescriptor,
)
from src.distributed.worker_contracts import Lease, LeaseRenewal, WorkerRegistration


class WorkQueueProtocol(Protocol):
    """The work-admission and delivery boundary. Mirrors the "Work
    admission and leasing" abstraction named in
    ``docs/architecture/gcp-distributed-reference-execution.md`` §3."""

    def publish(self, descriptor: WorkDescriptor) -> QueueWorkMessage:
        """Admit ``descriptor`` and return its initial, unleased
        :class:`QueueWorkMessage`."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def lease(self, message: QueueWorkMessage, lease: Lease) -> QueueWorkMessage:
        """Return the :class:`QueueWorkMessage` reflecting ``lease``
        having been issued against it."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def cancel(self, request: CancellationRequest) -> None:
        """Cancel the work item ``request`` names."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class ArtifactStoreProtocol(Protocol):
    """The immutable-artifact persistence boundary. Mirrors the
    "Object/artifact persistence" abstraction named in
    ``docs/architecture/gcp-distributed-reference-execution.md`` §3."""

    def resolve(self, reference: ArtifactReference) -> bool:
        """``True`` if ``reference`` names content this store actually
        holds -- never returns or transports the content itself through
        this interface."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class ResultStoreProtocol(Protocol):
    """**Non-authoritative / deprecated for the commit path
    (MEGB-03H.2C.3B.2B.1 correction).** This Protocol's own signature
    carries no revision or compare-and-swap parameter, so composing its
    ``commit_result``/``acknowledge`` with
    :class:`LeaseStateStoreProtocol`'s own ``transition`` to implement the
    authoritative commit decision is exactly the check-then-write race
    B.2B.1's atomicity audit found unsound (see
    :mod:`~src.distributed.atomic_work_store`'s own module docstring for
    the full audit). :class:`AtomicWorkStoreProtocol` below supersedes
    ``commit_result``/``acknowledge`` entirely for the authoritative path;
    B.2B.2 (the coordinator/worker engine, not yet implemented) must not
    call this Protocol for authoritative result commit or acknowledgement.
    No legitimate remaining role was identified for this Protocol,
    including ``get_result`` as a read-only projection -- any reporting
    view should read :meth:`AtomicWorkStoreProtocol.read` directly rather
    than maintain a second, independently-writable source of truth for the
    same data. Retained, unmodified, only because a real backend
    implementing it already exists in principle and no accepted schema
    is being deleted by this correction."""

    def get_result(self, scientific_work_id: str) -> ResultCommit | None:
        """The currently durable :class:`ResultCommit` for
        ``scientific_work_id``, or ``None`` if none exists yet."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def commit_result(self, commit: ResultCommit) -> ResultCommit:
        """Durably persist ``commit``, reconciling against any existing
        commit for the same work item (see
        :func:`~src.distributed.work_contracts.reconcile_result_commit`),
        and return the durable commit of record."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def acknowledge(self, ack: Acknowledgement) -> None:
        """Durably record ``ack`` against its already-committed result."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class LeaseStateStoreProtocol(Protocol):
    """**Non-authoritative / deprecated for the commit path
    (MEGB-03H.2C.3B.2B.1 correction).** Symmetric to
    :class:`ResultStoreProtocol` above: this Protocol's ``transition``/
    ``current_lease``/``renew_lease``/``record_terminal_disposition`` carry
    no shared revision with :class:`ResultStoreProtocol`'s own methods, so
    composing the two to implement fenced lease validation plus durable
    result commit as one authoritative decision is the same unsound
    check-then-write composition B.2B.1's atomicity audit found.
    :class:`AtomicWorkStoreProtocol` below supersedes every mutating
    method here (``transition``, ``renew_lease`` as a state-changing
    operation, ``record_terminal_disposition``) for the authoritative
    path; B.2B.2 must not call this Protocol for authoritative lease or
    state-machine mutation. No legitimate remaining role was identified,
    including ``get_state``/``current_lease`` as read-only projections --
    same reasoning as :class:`ResultStoreProtocol`'s own docstring above.
    Retained, unmodified, for the same reason."""

    def get_state(self, scientific_work_id: str) -> WorkItemState:
        """The current :class:`~src.distributed.state_machine.WorkItemState`
        for ``scientific_work_id``."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def transition(self, scientific_work_id: str, next_state: WorkItemState) -> None:
        """Durably transition ``scientific_work_id`` to ``next_state``,
        validated against
        :func:`~src.distributed.state_machine.validate_transition`."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def current_lease(self, scientific_work_id: str) -> Lease | None:
        """The currently valid :class:`Lease` for ``scientific_work_id``,
        or ``None`` if unleased."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def renew_lease(self, renewal: LeaseRenewal) -> Lease:
        """Apply ``renewal`` to the currently valid lease and return the
        renewed :class:`Lease`."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def record_terminal_disposition(self, disposition: TerminalDisposition) -> None:
        """Durably record ``disposition`` as this work item's final,
        closed outcome."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class AtomicWorkStoreProtocol(Protocol):
    """**The provider-neutral atomic-store contract (MEGB-03H.2C.3B.2B.1
    correction)** every real backend must uphold for the single
    authoritative, revisioned per-work state record -- an in-memory
    ``threading.Lock``-protected store here
    (:class:`~src.distributed.atomic_work_store.AtomicWorkStore`, which
    structurally implements this Protocol); a GCP Firestore transaction, a
    DynamoDB conditional write, or a Spanner mutation elsewhere (none
    accessed or implemented in this checkpoint).

    **Linearizability requirement:** every mutating method below must
    behave, from the perspective of every other concurrent caller
    operating on the same ``scientific_work_id``, as if it executed
    atomically at a single instant between invocation and return -- no
    caller may ever observe or act upon a partially-applied mutation, and
    the combined effect of any two concurrent mutations on the same work
    item must equal the effect of *some* sequential ordering of them. A
    caller whose attempted ordering loses this race must see an explicit
    compare-and-swap rejection (a revision or fencing-generation
    conflict), never silent corruption, a lost update, or a torn read.
    This Protocol intentionally does not mandate *how* linearizability is
    achieved -- only that it holds from every caller's observable point of
    view -- so a real distributed backend may substitute its own native
    atomic primitive for :class:`~src.distributed.atomic_work_store.AtomicWorkStore`'s
    single process-local lock.

    B.2B.2 (the coordinator/worker scheduling engine, not yet
    implemented, separately authorized) must depend on this Protocol
    alone for every authoritative work-state mutation -- never on
    :class:`LeaseStateStoreProtocol`/:class:`ResultStoreProtocol` above,
    and never directly on the concrete
    :class:`~src.distributed.atomic_work_store.AtomicWorkStore` class."""

    def create_if_absent(
        self,
        scientific_work_id: str,
        distributed_run_context_checksum: str,
        reservation_id: str,
        reservation_validator: Callable[[str], bool],
    ) -> AuthoritativeWorkRecord:
        """Create a fresh, revision-0 record bound to a currently valid
        ``reservation_id`` (validated by ``reservation_validator``), or
        idempotently return an already-existing record without
        re-validating the reservation."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def read(self, scientific_work_id: str) -> AuthoritativeWorkRecord:
        """The current authoritative record and its revision."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def acquire_lease(
        self,
        scientific_work_id: str,
        expected_revision: int,
        lease: Lease,
        *,
        reservation_validator: Callable[[str], bool],
    ) -> AuthoritativeWorkRecord:
        """Atomic CAS transition to ``LEASED``, fenced by
        ``lease.lease_generation`` and re-validated against
        ``reservation_validator``, both inside the same indivisible step
        -- a work item must never become leaseable without a currently
        valid reservation."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def transition_to_executing(
        self, scientific_work_id: str, expected_revision: int
    ) -> AuthoritativeWorkRecord:
        """Atomic CAS transition to ``EXECUTING``."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def renew_lease(
        self, scientific_work_id: str, expected_revision: int, renewal: LeaseRenewal
    ) -> AuthoritativeWorkRecord:
        """Atomic fencing-validated heartbeat; never a state transition."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def mark_retryable(
        self, scientific_work_id: str, expected_revision: int
    ) -> AuthoritativeWorkRecord:
        """Atomic CAS transition to ``RETRYABLE``."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def reassign_lease(
        self,
        scientific_work_id: str,
        expected_revision: int,
        new_lease: Lease,
        *,
        reservation_validator: Callable[[str], bool],
    ) -> AuthoritativeWorkRecord:
        """Atomic CAS reassignment to ``LEASED`` under a fresh, strictly
        higher lease generation, with the same reservation re-validation
        as :meth:`acquire_lease`."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def dead_letter(
        self, scientific_work_id: str, expected_revision: int, disposition: TerminalDisposition
    ) -> AuthoritativeWorkRecord:
        """Atomic CAS transition to ``DEAD_LETTERED``."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def request_cancellation(
        self, scientific_work_id: str, expected_revision: int, request: CancellationRequest
    ) -> AuthoritativeWorkRecord:
        """Atomic CAS transition to ``CANCELLED``; illegal, and rejected,
        from a state where terminal evidence already exists."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def commit_result(
        self,
        scientific_work_id: str,
        expected_revision: int,
        attempt: ExecutionAttempt,
        commit: ResultCommit,
        artifact_resolver: Callable[[ArtifactReference], bool],
    ) -> AuthoritativeWorkRecord:
        """The atomic, indivisible commit decision: identity/fencing
        validation, idempotent-vs-conflicting result reconciliation,
        durable-artifact confirmation via ``artifact_resolver``, and the
        ``RESULT_COMMITTED`` transition, all within one linearizable
        step."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def acknowledge(
        self, scientific_work_id: str, expected_revision: int, ack: Acknowledgement
    ) -> AuthoritativeWorkRecord:
        """Atomic CAS transition to ``ACKNOWLEDGED_COMPLETED``; only
        legal once a durable, checksum-verified result commit is already
        present."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class ArtifactReaderProtocol(Protocol):
    """**MEGB-03H.2C.3B.2B.2 addition.** The trusted, read-only artifact
    boundary the coordinator's admission path and every worker's
    execution path depend on -- additive to, and a superset of,
    :class:`ArtifactStoreProtocol` above (which the accepted B.2A
    execution-plane contracts deliberately kept minimal, ``resolve``
    only). Returns checksum-verified immutable content and metadata on
    every call; never trusts a caller-supplied classification claim.
    Carries no ``put``/write method at all -- capability separation for
    read-only callers (workers resolving already-published candidate
    artifacts) is expressed by simply never handing them anything more
    than this Protocol, not by convention alone."""

    def resolve(self, reference: ArtifactReference) -> bool:
        """``True`` iff ``reference`` names content this store actually
        holds under its exact composite content/metadata identity."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def get(self, reference: ArtifactReference) -> tuple[bytes, ArtifactMetadata]:
        """Checksum-verified ``(content, metadata)`` for ``reference``."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def verify_artifact_classification(
        self,
        reference: ArtifactReference,
        claimed_workload_class: WorkloadClass,
        claimed_data_classification: DataClassification,
    ) -> None:
        """Raise unless the claim matches the artifact's own immutably-
        bound metadata."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class ArtifactWriterProtocol(Protocol):
    """**MEGB-03H.2C.3B.2B.2 addition.** The narrow, write-only artifact
    boundary -- deliberately just ``put``, so a capability-separated view
    (see :mod:`~src.distributed.artifact_capabilities`) can compose this
    with :class:`ArtifactReaderProtocol` while still enforcing, at the
    view layer, which ``artifact_kind`` a given caller may ever write."""

    def put(
        self, reference: ArtifactReference, content: bytes, metadata: ArtifactMetadata
    ) -> ArtifactReference:
        """Durably store ``content`` under ``reference``, bound to
        ``metadata`` -- see
        :meth:`~src.distributed.artifact_store.InMemoryArtifactStore.put`."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class BudgetReservationProtocol(Protocol):
    """**MEGB-03H.2C.3B.2B.2 addition.** The exact-integer-cent budget
    reservation boundary the coordinator's admission path depends on --
    every method here operates on ``int`` cents only, never a ``float``."""

    def reserve(
        self, reservation_id: str, requested_cost_cents: int, requested_worker_count: int
    ) -> BudgetReservation:
        """Atomically admit a new reservation, or idempotently return an
        exact-match existing one."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def release(self, reservation_id: str) -> BudgetReservation:
        """Atomically release a still-``RESERVED`` reservation."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def finalize(self, reservation_id: str, actual_cost_cents: int) -> BudgetReservation:
        """Atomically finalize a still-``RESERVED`` reservation with its
        measured actual cost."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def get(self, reservation_id: str) -> BudgetReservation:
        """The current reservation of record."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class WorkerRegistryProtocol(Protocol):
    """The worker-fleet membership boundary. Mirrors the
    "Worker-fleet control" abstraction named in
    ``docs/architecture/gcp-distributed-reference-execution.md`` §3.

    **MEGB-03H.2C.3B.2B.2 addition:** ``get_registration``/
    ``registration_status`` -- both additive, read-only; no existing
    method's behavior changes. (``registration_status`` already existed
    on the concrete B.2B.1 ``InMemoryWorkerRegistry``; this Protocol had
    simply not yet declared it, since no B.2A/B.2B.1 caller needed it.)"""

    def register(self, registration: WorkerRegistration) -> WorkerRegistration:
        """Admit ``registration`` and return the registry's own record of
        it."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def active_worker_participant_ids(self) -> tuple[str, ...]:
        """Every currently active worker's ``worker_participant_id``,
        deterministically ordered."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def registration_status(self, worker_participant_id: str):  # type: ignore[no-untyped-def]
        """The current registration status for ``worker_participant_id``
        -- typed as a bare return (rather than importing
        :mod:`~src.distributed.worker_registry_store`, avoiding a needless
        import-direction dependency from this contract module onto a
        concrete store module) -- callers compare against
        :class:`~src.distributed.worker_registry_store.WorkerRegistrationStatus.ACTIVE`."""
        raise NotImplementedError  # pragma: no cover -- Protocol method

    def get_registration(self, worker_participant_id: str) -> WorkerRegistration:
        """The full, currently-registered :class:`WorkerRegistration` for
        ``worker_participant_id``."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


class AuditSinkProtocol(Protocol):
    """The safe-audit-event emission boundary."""

    def emit(self, event) -> None:  # type: ignore[no-untyped-def]
        """Durably emit a
        :class:`~src.distributed.safe_audit.SafeAuditEvent`. Typed as a
        bare parameter (rather than importing
        :mod:`~src.distributed.safe_audit`) to avoid a needless import
        cycle risk between this module and every other contract module
        it already depends on; callers pass a real ``SafeAuditEvent``."""
        raise NotImplementedError  # pragma: no cover -- Protocol method


__all__ = [
    "WorkQueueProtocol",
    "ArtifactStoreProtocol",
    "ResultStoreProtocol",
    "LeaseStateStoreProtocol",
    "AtomicWorkStoreProtocol",
    "ArtifactReaderProtocol",
    "ArtifactWriterProtocol",
    "BudgetReservationProtocol",
    "WorkerRegistryProtocol",
    "AuditSinkProtocol",
]
