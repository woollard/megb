"""MEGB-03H.2C.3B.2A: the provider-neutral personal-environment policy
contract required by MEGB-03H.2C.3A
(``docs/operations/gcp-environment-promotion.md`` §1.1's "technical, not
merely documented, refusal").

Two typed classifications, never a filename or string heuristic:

* :class:`WorkloadClass` -- what *kind* of run is being requested
  (synthetic smoke/qualification-candidate vs. calibration/production).
* :class:`DataClassification` -- what *kind* of data the run would touch
  (synthetic/non-privileged vs. privileged-reference/real-candidate/
  production-cache).

:class:`PersonalEnvironmentPolicy` bakes the accepted amendment's own
personal-bootstrap ceilings (maximum 2 workers, $50 spending ceiling) into
*validation*, not merely documentation -- a policy claiming
``environment_class=PERSONAL_BOOTSTRAP`` with ``max_admitted_workers > 2``
or ``spending_ceiling_usd > 50.0`` fails to construct at all.
:func:`evaluate_admission` is the pure, side-effect-free decision function
a future coordinator (MEGB-03H.2C.3B.2B) would call **before** admitting
any work -- it creates no resource, authorizes no billing, and its
absence of a runtime dependency on any queue/store/cloud call is exactly
what makes "policy refusal occurs before work admission" a structural
property, not a convention.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.distributed._checksums import (
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    CHECKSUM_ALGORITHM_VERSION,
    InvalidDistributedProvenanceError,
    require_checksum_algorithm_version as _require_checksum_algorithm_version,
    require_orchestration_schema_version as _require_orchestration_schema_version,
    require_positive_float as _require_positive_float,
    require_positive_int as _require_positive_int,
    sha256_of as _sha256_of,
)
from src.distributed.provenance import EnvironmentClass

# The accepted amendment's own personal-bootstrap ceilings
# (docs/operations/gcp-environment-promotion.md §1.1) -- baked into
# PersonalEnvironmentPolicy's own validation below, not merely documented.
PERSONAL_BOOTSTRAP_MAX_WORKERS = 2
PERSONAL_BOOTSTRAP_SPENDING_CEILING_USD = 50.0


class WorkloadClass(str, Enum):
    """What kind of run is being requested. Closed by design -- the
    personal-bootstrap allowlist below is a subset of this enum, never a
    free-form string comparison."""

    SYNTHETIC_SMOKE = "SYNTHETIC_SMOKE"
    SYNTHETIC_QUALIFICATION_CANDIDATE = "SYNTHETIC_QUALIFICATION_CANDIDATE"
    CALIBRATION = "CALIBRATION"
    PRODUCTION = "PRODUCTION"


class DataClassification(str, Enum):
    """What kind of data a requested run would touch. Closed by design."""

    SYNTHETIC = "SYNTHETIC"
    NON_PRIVILEGED = "NON_PRIVILEGED"
    PRIVILEGED_REFERENCE = "PRIVILEGED_REFERENCE"
    REAL_CANDIDATE_PORTFOLIO = "REAL_CANDIDATE_PORTFOLIO"
    PRODUCTION_CACHE = "PRODUCTION_CACHE"


# The only two workload classes, and the only two data classifications, the
# personal-bootstrap environment may ever admit -- per the accepted
# amendment's own "Fixtures: Synthetic and non-privileged only" /
# "Privileged artifacts: None" / "Real candidate portfolios: None" /
# "Calibration/experiment: None" rows.
PERSONAL_BOOTSTRAP_ALLOWED_WORKLOAD_CLASSES = frozenset(
    {WorkloadClass.SYNTHETIC_SMOKE, WorkloadClass.SYNTHETIC_QUALIFICATION_CANDIDATE}
)
PERSONAL_BOOTSTRAP_ALLOWED_DATA_CLASSIFICATIONS = frozenset(
    {DataClassification.SYNTHETIC, DataClassification.NON_PRIVILEGED}
)


@dataclass(frozen=True)
class PersonalEnvironmentPolicy:
    """A typed, self-checksummed admission policy for one environment.

    When ``environment_class == PERSONAL_BOOTSTRAP``, construction itself
    enforces the accepted ceilings: ``allowed_workload_classes`` must be a
    subset of :data:`PERSONAL_BOOTSTRAP_ALLOWED_WORKLOAD_CLASSES`,
    ``max_admitted_workers`` must not exceed
    :data:`PERSONAL_BOOTSTRAP_MAX_WORKERS`, and ``spending_ceiling_usd``
    must not exceed :data:`PERSONAL_BOOTSTRAP_SPENDING_CEILING_USD`. This
    is the "technical, not merely documented, refusal" the accepted
    amendment requires -- a caller cannot construct a personal-bootstrap
    policy object that violates its own ceilings in the first place."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    environment_class: EnvironmentClass
    allowed_workload_classes: tuple[WorkloadClass, ...]
    max_admitted_workers: int
    spending_ceiling_usd: float
    policy_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        if not isinstance(self.environment_class, EnvironmentClass):
            raise InvalidDistributedProvenanceError(
                f"environment_class must be an EnvironmentClass, got {self.environment_class!r}"
            )
        if not isinstance(self.allowed_workload_classes, tuple) or not all(
            isinstance(item, WorkloadClass) for item in self.allowed_workload_classes
        ):
            raise InvalidDistributedProvenanceError(
                "allowed_workload_classes must be a tuple of WorkloadClass, got "
                f"{self.allowed_workload_classes!r}"
            )
        if list(self.allowed_workload_classes) != sorted(
            self.allowed_workload_classes, key=lambda item: item.value
        ):
            raise InvalidDistributedProvenanceError(
                "allowed_workload_classes must be stored in sorted order for deterministic "
                "serialization"
            )
        if len(set(self.allowed_workload_classes)) != len(self.allowed_workload_classes):
            raise InvalidDistributedProvenanceError(
                "allowed_workload_classes must not contain a duplicate"
            )
        _require_positive_int(self, "max_admitted_workers")
        _require_positive_float(self, "spending_ceiling_usd")

        if self.environment_class == EnvironmentClass.PERSONAL_BOOTSTRAP:
            disallowed = (
                set(self.allowed_workload_classes) - PERSONAL_BOOTSTRAP_ALLOWED_WORKLOAD_CLASSES
            )
            if disallowed:
                raise InvalidDistributedProvenanceError(
                    f"personal-bootstrap policy may not allow workload class(es) {disallowed!r} "
                    f"-- only {PERSONAL_BOOTSTRAP_ALLOWED_WORKLOAD_CLASSES!r} are permitted"
                )
            if self.max_admitted_workers > PERSONAL_BOOTSTRAP_MAX_WORKERS:
                raise InvalidDistributedProvenanceError(
                    f"personal-bootstrap policy may not admit more than "
                    f"{PERSONAL_BOOTSTRAP_MAX_WORKERS} workers, got "
                    f"{self.max_admitted_workers}"
                )
            if self.spending_ceiling_usd > PERSONAL_BOOTSTRAP_SPENDING_CEILING_USD:
                raise InvalidDistributedProvenanceError(
                    f"personal-bootstrap policy may not exceed a "
                    f"${PERSONAL_BOOTSTRAP_SPENDING_CEILING_USD:.2f} spending ceiling, got "
                    f"${self.spending_ceiling_usd:.2f}"
                )

        computed_checksum = _sha256_of(_personal_environment_policy_payload(self))
        if self.policy_checksum and self.policy_checksum != computed_checksum:
            raise InvalidDistributedProvenanceError(
                "personal environment policy checksum mismatch: stamped "
                f"{self.policy_checksum!r} vs. recomputed {computed_checksum!r} -- tampered or "
                "corrupted policy"
            )
        object.__setattr__(self, "policy_checksum", computed_checksum)


def _personal_environment_policy_payload(policy: PersonalEnvironmentPolicy) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": (
            policy.distributed_orchestration_schema_version
        ),
        "checksum_algorithm_version": policy.checksum_algorithm_version,
        "environment_class": policy.environment_class.value,
        "allowed_workload_classes": [item.value for item in policy.allowed_workload_classes],
        "max_admitted_workers": policy.max_admitted_workers,
        "spending_ceiling_usd": policy.spending_ceiling_usd,
    }


def personal_environment_policy_to_dict(policy: PersonalEnvironmentPolicy) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`PersonalEnvironmentPolicy`."""
    return {
        **_personal_environment_policy_payload(policy),
        "policy_checksum": policy.policy_checksum,
    }


class AdmissionRefusalReason(str, Enum):
    """Closed, safe reason codes for :func:`evaluate_admission` -- never
    free-form text, mirroring
    :class:`~src.distributed.qualification_gate.ProvenanceGateFailureReason`'s
    own established precedent."""

    WORKLOAD_CLASS_NOT_ALLOWLISTED = "WORKLOAD_CLASS_NOT_ALLOWLISTED"
    DATA_CLASSIFICATION_REFUSED = "DATA_CLASSIFICATION_REFUSED"
    WORKER_COUNT_CEILING_EXCEEDED = "WORKER_COUNT_CEILING_EXCEEDED"
    COST_CEILING_EXCEEDED = "COST_CEILING_EXCEEDED"


@dataclass(frozen=True)
class AdmissionDecision:
    """The typed, immutable outcome of :func:`evaluate_admission`.

    ``admitted is True`` if and only if ``refusal_reasons`` is empty --
    the same "never partially compute a positive result alongside
    failure reasons" discipline
    :class:`~src.distributed.qualification_gate.QualificationGateResult`
    already establishes."""

    admitted: bool
    refusal_reasons: tuple[AdmissionRefusalReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.refusal_reasons, tuple) or not all(
            isinstance(reason, AdmissionRefusalReason) for reason in self.refusal_reasons
        ):
            raise InvalidDistributedProvenanceError(
                f"refusal_reasons must be a tuple of AdmissionRefusalReason, got "
                f"{self.refusal_reasons!r}"
            )
        if self.admitted and self.refusal_reasons:
            raise InvalidDistributedProvenanceError(
                "admitted=True must have empty refusal_reasons"
            )
        if not self.admitted and not self.refusal_reasons:
            raise InvalidDistributedProvenanceError(
                "admitted=False requires a nonempty refusal_reasons"
            )


def evaluate_admission(
    policy: PersonalEnvironmentPolicy,
    workload_class: WorkloadClass,
    data_classification: DataClassification,
    requested_worker_count: int,
    estimated_cost_usd: float,
) -> AdmissionDecision:
    """Pure admission-refusal decision, evaluated **before** any work is
    admitted -- creates no resource, authorizes no billing, and has no
    dependency on any queue/store/cloud call. Enumerates every applicable
    :class:`AdmissionRefusalReason` rather than stopping at the first
    one, mirroring
    :func:`~src.distributed.qualification_gate.evaluate_qualification_gate`'s
    own "surface everything wrong in one evaluation" discipline."""
    reasons: list[AdmissionRefusalReason] = []
    if workload_class not in policy.allowed_workload_classes:
        reasons.append(AdmissionRefusalReason.WORKLOAD_CLASS_NOT_ALLOWLISTED)
    if data_classification not in (DataClassification.SYNTHETIC, DataClassification.NON_PRIVILEGED):
        reasons.append(AdmissionRefusalReason.DATA_CLASSIFICATION_REFUSED)
    if not isinstance(requested_worker_count, int) or isinstance(requested_worker_count, bool):
        raise InvalidDistributedProvenanceError(
            f"requested_worker_count must be an int, got {requested_worker_count!r}"
        )
    if requested_worker_count > policy.max_admitted_workers:
        reasons.append(AdmissionRefusalReason.WORKER_COUNT_CEILING_EXCEEDED)
    if not isinstance(estimated_cost_usd, (int, float)) or isinstance(estimated_cost_usd, bool):
        raise InvalidDistributedProvenanceError(
            f"estimated_cost_usd must be a number, got {estimated_cost_usd!r}"
        )
    if estimated_cost_usd > policy.spending_ceiling_usd:
        reasons.append(AdmissionRefusalReason.COST_CEILING_EXCEEDED)
    return AdmissionDecision(admitted=not reasons, refusal_reasons=tuple(reasons))


__all__ = [
    "PERSONAL_BOOTSTRAP_MAX_WORKERS",
    "PERSONAL_BOOTSTRAP_SPENDING_CEILING_USD",
    "PERSONAL_BOOTSTRAP_ALLOWED_WORKLOAD_CLASSES",
    "PERSONAL_BOOTSTRAP_ALLOWED_DATA_CLASSIFICATIONS",
    "WorkloadClass",
    "DataClassification",
    "PersonalEnvironmentPolicy",
    "personal_environment_policy_to_dict",
    "AdmissionRefusalReason",
    "AdmissionDecision",
    "evaluate_admission",
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION",
]
