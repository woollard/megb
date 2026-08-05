"""MEGB-03H.2C.3B.2B.1: atomic personal-environment admission/budget
reservation store.

**Canonical integer currency units (cents) throughout -- never a Python
``float``** for this store's own accumulation/enforcement logic, per this
checkpoint's own explicit "never binary floating-point comparison"
requirement. Python's arbitrary-precision ``int`` makes overflow
structurally impossible here, and there is no way to represent NaN or
infinity in an ``int`` at all -- eliminating the entire class of
imprecise/overflowing/non-finite values by construction, not by runtime
validation alone.

Reservation identity, workload identity, and actual-cost observation are
kept as three distinct concepts throughout: ``reservation_id`` identifies
one admission attempt (idempotent on exact replay, rejected on
conflicting replay); the workload/artifact a reservation is *for* is the
caller's own concern (this store does not itself hold a workload
reference field, precisely so it cannot be confused with reservation
identity); ``actual_cost_cents`` (recorded only via
:meth:`AtomicBudgetStore.finalize`) is a measured outcome, never assumed
equal to the reservation's own ``requested_cost_cents``.

:func:`evaluate_and_reserve` composes this store with
:mod:`~src.distributed.artifact_store`'s own classification-verification
and :func:`~src.distributed.personal_policy.evaluate_admission` into the
one required policy-plus-budget admission decision -- artifact
classification is verified against the artifact store's own immutably-bound
metadata first (never trusted solely from a caller's claim), and only once
that passes does the policy check and this store's own exact-integer
ledger check run.

**MEGB-03H.2C.3B.2B.1 correction:** the prior version of this module
bridged ``requested_cost_cents`` to a Python ``float`` (``/ 100``) before
calling :func:`~src.distributed.personal_policy.evaluate_admission`, which
had at the time taken an ``estimated_cost_usd: float`` parameter. The
B.2B.1 checkpoint correction's own audit found this violated the
authorization's "no conversion to float before an authorization
comparison" requirement, since a caller-observable admission decision was
computed via a float comparison, even though this store's own ledger
(:meth:`AtomicBudgetStore.reserve`) never used one. ``evaluate_admission``
now takes ``estimated_cost_cents: int`` directly (``DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION``
v1->v2), so ``requested_cost_cents`` passes through to it unconverted --
there is no float anywhere on this module's admission/reservation path.

**Reservation/work-creation crash-window recoverability (B.2B.1
correction):** ``reserve`` before ``AtomicWorkStore.create_if_absent`` is
the mandated ordering (reservation before admission), but this module
does not and cannot claim cross-store atomicity between the two --
:class:`AtomicBudgetStore` and
:class:`~src.distributed.atomic_work_store.AtomicWorkStore` are
independent, separately-locked stores. Instead:

* ``AtomicWorkStore.create_if_absent`` now *requires* a ``reservation_id``
  and a ``reservation_validator`` callback (see that module) -- an
  authoritative work record cannot be created except against a reservation
  that validates as currently ``RESERVED`` at creation time, and
  ``acquire_lease``/``reassign_lease`` re-validate the same bound
  reservation before any ``LEASED`` transition, so a work item can never
  become leaseable without a currently valid reservation, even if the
  reservation is later released between creation and leasing.
* If a reservation succeeds but the process crashes before
  ``create_if_absent`` is ever called, :func:`diagnose_reservation_work_binding`
  below lets a recovering caller determine the reservation is
  ``RESUMABLE`` -- deterministically safe to retry (``create_if_absent``
  is itself idempotent) or to ``release``.
* If ``create_if_absent`` somehow succeeds referencing a reservation_id
  that is not (or no longer) ``RESERVED`` -- a caller/protocol violation,
  not a crash this module causes -- the resulting work record is
  permanently non-leaseable (``acquire_lease``/``reassign_lease`` reject
  it), never silently treated as admitted.
* ``release``/``finalize`` each require the reservation to still be
  ``RESERVED`` and transition it to a terminal status
  (``RELEASED``/``FINALIZED``); a second call on an already-terminal
  reservation raises :class:`ReservationNotActiveError` rather than
  double-crediting or double-debiting the budget.

This is a deterministic, recoverable two-step protocol with explicit,
non-leaseable intermediate states -- not a claim of genuine cross-store
atomicity."""

import threading
from dataclasses import dataclass
from enum import Enum

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.artifact_store import InMemoryArtifactStore
from src.distributed.atomic_work_store import AtomicWorkStore, WorkRecordNotFoundError
from src.distributed.personal_policy import (
    AdmissionDecision,
    DataClassification,
    PersonalEnvironmentPolicy,
    WorkloadClass,
    evaluate_admission,
)
from src.distributed.work_contracts import ArtifactReference


def _require_nonempty_str(value: object, field_name: str) -> None:
    if not isinstance(value, str) or value == "":
        raise InvalidDistributedProvenanceError(
            f"{field_name} must be a nonempty string, got {value!r}"
        )


def _require_non_negative_int(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvalidDistributedProvenanceError(
            f"{field_name} must be a non-negative int, got {value!r}"
        )


def _require_positive_int(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise InvalidDistributedProvenanceError(
            f"{field_name} must be a positive int, got {value!r}"
        )


class ReservationStatus(str, Enum):
    """Closed set of reservation lifecycle states."""

    RESERVED = "RESERVED"
    RELEASED = "RELEASED"
    FINALIZED = "FINALIZED"


class ReservationConflictError(InvalidDistributedProvenanceError):
    """Raised when the same ``reservation_id`` is submitted a second time
    with a different ``requested_cost_cents``/``requested_worker_count``
    than its first, already-accepted reservation."""


class ReservationNotFoundError(InvalidDistributedProvenanceError):
    """Raised when ``release``/``finalize`` names an unknown
    ``reservation_id``."""


class ReservationNotActiveError(InvalidDistributedProvenanceError):
    """Raised when ``release``/``finalize`` is called on a reservation
    that is no longer ``RESERVED`` (already released or finalized)."""


class BudgetCeilingExceededError(InvalidDistributedProvenanceError):
    """Raised when admitting a new reservation would push the sum of all
    currently ``RESERVED`` reservations' ``requested_cost_cents`` above
    the store's own ``budget_ceiling_cents``."""


class WorkerCeilingExceededError(InvalidDistributedProvenanceError):
    """Raised when admitting a new reservation would push the sum of all
    currently ``RESERVED`` reservations' ``requested_worker_count`` above
    the store's own ``max_admitted_workers``."""


@dataclass(frozen=True)
class BudgetReservation:
    """One admission reservation. Not a wire/schema type (no
    ``distributed_orchestration_schema_version``/self-checksum field):
    purely in-process ledger state, keyed by ``reservation_id``."""

    reservation_id: str
    requested_cost_cents: int
    requested_worker_count: int
    status: ReservationStatus
    actual_cost_cents: int | None

    def __post_init__(self) -> None:
        _require_nonempty_str(self.reservation_id, "reservation_id")
        _require_non_negative_int(self.requested_cost_cents, "requested_cost_cents")
        _require_positive_int(self.requested_worker_count, "requested_worker_count")
        if not isinstance(self.status, ReservationStatus):
            raise InvalidDistributedProvenanceError(
                f"status must be a ReservationStatus, got {self.status!r}"
            )
        if self.actual_cost_cents is not None:
            _require_non_negative_int(self.actual_cost_cents, "actual_cost_cents")
        if (self.status == ReservationStatus.FINALIZED) != (self.actual_cost_cents is not None):
            raise InvalidDistributedProvenanceError(
                "actual_cost_cents must be present if and only if status is FINALIZED"
            )


class AtomicBudgetStore:
    """Synthetic, single-process, lock-protected admission-ledger store.
    Every mutating method performs its entire read-check-write sequence
    while holding one internal lock, so concurrent reservations can never
    oversubscribe either ceiling -- the sum check and the write happen
    as one indivisible step, never a separate check followed by a
    separate write."""

    def __init__(self, *, budget_ceiling_cents: int, max_admitted_workers: int) -> None:
        _require_positive_int(budget_ceiling_cents, "budget_ceiling_cents")
        _require_positive_int(max_admitted_workers, "max_admitted_workers")
        self._budget_ceiling_cents = budget_ceiling_cents
        self._max_admitted_workers = max_admitted_workers
        self._lock = threading.Lock()
        self._reservations: dict[str, BudgetReservation] = {}

    def _active_reserved_cents(self) -> int:
        return sum(
            reservation.requested_cost_cents
            for reservation in self._reservations.values()
            if reservation.status == ReservationStatus.RESERVED
        )

    def _active_reserved_workers(self) -> int:
        return sum(
            reservation.requested_worker_count
            for reservation in self._reservations.values()
            if reservation.status == ReservationStatus.RESERVED
        )

    def reserve(
        self, reservation_id: str, requested_cost_cents: int, requested_worker_count: int
    ) -> BudgetReservation:
        """Atomically admit a new reservation, or idempotently return an
        exact-match existing one. Raises
        :class:`ReservationConflictError` for a same-id, different-amount
        replay; :class:`BudgetCeilingExceededError`/
        :class:`WorkerCeilingExceededError` if admitting would
        oversubscribe either ceiling -- checked and written as one
        indivisible step, so no two concurrent callers can ever both
        succeed past the ceiling."""
        _require_nonempty_str(reservation_id, "reservation_id")
        _require_non_negative_int(requested_cost_cents, "requested_cost_cents")
        _require_positive_int(requested_worker_count, "requested_worker_count")
        with self._lock:
            existing = self._reservations.get(reservation_id)
            if existing is not None:
                if (
                    existing.requested_cost_cents != requested_cost_cents
                    or existing.requested_worker_count != requested_worker_count
                ):
                    raise ReservationConflictError(
                        f"reservation_id {reservation_id!r} already reserved with different "
                        f"terms (requested_cost_cents={existing.requested_cost_cents}, "
                        f"requested_worker_count={existing.requested_worker_count}) than this "
                        f"replay (requested_cost_cents={requested_cost_cents}, "
                        f"requested_worker_count={requested_worker_count})"
                    )
                return existing
            projected_cents = self._active_reserved_cents() + requested_cost_cents
            if projected_cents > self._budget_ceiling_cents:
                raise BudgetCeilingExceededError(
                    f"reserving {requested_cost_cents} cents would bring active reservations to "
                    f"{projected_cents} cents, exceeding the {self._budget_ceiling_cents}-cent "
                    f"ceiling"
                )
            projected_workers = self._active_reserved_workers() + requested_worker_count
            if projected_workers > self._max_admitted_workers:
                raise WorkerCeilingExceededError(
                    f"reserving {requested_worker_count} worker(s) would bring active "
                    f"reservations to {projected_workers}, exceeding the "
                    f"{self._max_admitted_workers}-worker ceiling"
                )
            reservation = BudgetReservation(
                reservation_id=reservation_id,
                requested_cost_cents=requested_cost_cents,
                requested_worker_count=requested_worker_count,
                status=ReservationStatus.RESERVED,
                actual_cost_cents=None,
            )
            self._reservations[reservation_id] = reservation
            return reservation

    def release(self, reservation_id: str) -> BudgetReservation:
        """Atomically release a still-``RESERVED`` reservation, freeing
        its slot against both ceilings."""
        with self._lock:
            existing = self._reservations.get(reservation_id)
            if existing is None:
                raise ReservationNotFoundError(f"no reservation for {reservation_id!r}")
            if existing.status != ReservationStatus.RESERVED:
                raise ReservationNotActiveError(
                    f"reservation {reservation_id!r} is {existing.status.value}, not RESERVED"
                )
            released = BudgetReservation(
                reservation_id=existing.reservation_id,
                requested_cost_cents=existing.requested_cost_cents,
                requested_worker_count=existing.requested_worker_count,
                status=ReservationStatus.RELEASED,
                actual_cost_cents=None,
            )
            self._reservations[reservation_id] = released
            return released

    def finalize(self, reservation_id: str, actual_cost_cents: int) -> BudgetReservation:
        """Atomically finalize a still-``RESERVED`` reservation, recording
        ``actual_cost_cents`` as a measured outcome distinct from
        ``requested_cost_cents``."""
        _require_non_negative_int(actual_cost_cents, "actual_cost_cents")
        with self._lock:
            existing = self._reservations.get(reservation_id)
            if existing is None:
                raise ReservationNotFoundError(f"no reservation for {reservation_id!r}")
            if existing.status != ReservationStatus.RESERVED:
                raise ReservationNotActiveError(
                    f"reservation {reservation_id!r} is {existing.status.value}, not RESERVED"
                )
            finalized = BudgetReservation(
                reservation_id=existing.reservation_id,
                requested_cost_cents=existing.requested_cost_cents,
                requested_worker_count=existing.requested_worker_count,
                status=ReservationStatus.FINALIZED,
                actual_cost_cents=actual_cost_cents,
            )
            self._reservations[reservation_id] = finalized
            return finalized

    def get(self, reservation_id: str) -> BudgetReservation:
        """The current reservation of record."""
        with self._lock:
            existing = self._reservations.get(reservation_id)
        if existing is None:
            raise ReservationNotFoundError(f"no reservation for {reservation_id!r}")
        return existing


def evaluate_and_reserve(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    policy: PersonalEnvironmentPolicy,
    budget_store: AtomicBudgetStore,
    artifact_store: InMemoryArtifactStore,
    artifact_reference: ArtifactReference,
    claimed_workload_class: WorkloadClass,
    claimed_data_classification: DataClassification,
    reservation_id: str,
    requested_cost_cents: int,
    requested_worker_count: int,
) -> AdmissionDecision:
    """The one composed admission decision this checkpoint's own
    requirements ask for: verify ``claimed_workload_class``/
    ``claimed_data_classification`` against the artifact store's own
    immutably-bound metadata (never trusted from the caller alone),
    then evaluate the already-accepted personal-environment policy, and
    only if both pass, atomically reserve budget/worker capacity.
    Returns a refusing :class:`~src.distributed.personal_policy.AdmissionDecision`
    (never raises) for a policy-level refusal; raises
    :class:`~src.distributed.artifact_store.ArtifactMetadataMismatchError`
    for a classification-verification failure (an integrity violation,
    not an ordinary refusal) and the budget store's own ceiling errors
    for a ledger-level refusal."""
    artifact_store.verify_artifact_classification(
        artifact_reference, claimed_workload_class, claimed_data_classification
    )
    decision = evaluate_admission(
        policy,
        claimed_workload_class,
        claimed_data_classification,
        requested_worker_count,
        requested_cost_cents,
    )
    if not decision.admitted:
        return decision
    budget_store.reserve(reservation_id, requested_cost_cents, requested_worker_count)
    return decision


class OrphanReservationDisposition(str, Enum):
    """The outcome of :func:`diagnose_reservation_work_binding` -- a pure,
    single-item diagnostic (never a scanning/polling coordinator, out of
    this checkpoint's scope) that lets a recovering caller determine what,
    if anything, must be done after a crash between reservation and
    authoritative work creation."""

    NO_ACTION_NEEDED = "NO_ACTION_NEEDED"
    RESUMABLE = "RESUMABLE"
    ALREADY_RESOLVED = "ALREADY_RESOLVED"
    CONFLICTING_BINDING = "CONFLICTING_BINDING"


def diagnose_reservation_work_binding(
    budget_store: AtomicBudgetStore,
    work_store: AtomicWorkStore,
    scientific_work_id: str,
    reservation_id: str,
) -> OrphanReservationDisposition:
    """Determine the recovery disposition of one ``(scientific_work_id,
    reservation_id)`` pair after a possible crash between
    :meth:`AtomicBudgetStore.reserve` and
    :meth:`~src.distributed.atomic_work_store.AtomicWorkStore.create_if_absent`.

    * :attr:`OrphanReservationDisposition.RESUMABLE` -- the reservation is
      still ``RESERVED`` and no authoritative work record exists yet for
      ``scientific_work_id``: safe to retry ``create_if_absent`` (idempotent)
      or to ``release`` the reservation, at the caller's discretion.
    * :attr:`OrphanReservationDisposition.ALREADY_RESOLVED` -- no work
      record exists, and the reservation is no longer ``RESERVED``
      (already released or finalized elsewhere): nothing to reconcile.
    * :attr:`OrphanReservationDisposition.NO_ACTION_NEEDED` -- a work
      record already exists and is bound to exactly this ``reservation_id``:
      recovery already completed.
    * :attr:`OrphanReservationDisposition.CONFLICTING_BINDING` -- a work
      record exists but is bound to a *different* ``reservation_id`` than
      the one supplied: a protocol violation that must never occur under
      correct reserve-before-admission usage, surfaced rather than
      silently ignored.

    Raises :class:`ReservationNotFoundError` if ``reservation_id`` names no
    reservation at all -- there is nothing to diagnose for a reservation
    that was never made."""
    reservation = budget_store.get(reservation_id)
    try:
        record = work_store.read(scientific_work_id)
    except WorkRecordNotFoundError:
        record = None
    if record is None:
        if reservation.status == ReservationStatus.RESERVED:
            return OrphanReservationDisposition.RESUMABLE
        return OrphanReservationDisposition.ALREADY_RESOLVED
    if record.reservation_id != reservation_id:
        return OrphanReservationDisposition.CONFLICTING_BINDING
    return OrphanReservationDisposition.NO_ACTION_NEEDED


__all__ = [
    "ReservationStatus",
    "ReservationConflictError",
    "ReservationNotFoundError",
    "ReservationNotActiveError",
    "BudgetCeilingExceededError",
    "WorkerCeilingExceededError",
    "BudgetReservation",
    "AtomicBudgetStore",
    "evaluate_and_reserve",
    "OrphanReservationDisposition",
    "diagnose_reservation_work_binding",
]
