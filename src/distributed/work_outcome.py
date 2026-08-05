"""MEGB-03H.2C.3B.2B.2: the coordinator/worker engine's own typed,
immutable, safe result taxonomy.

Deliberately **not** schema-versioned/self-checksummed -- like
:class:`~src.distributed.atomic_work_store.AuthoritativeWorkRecord`, this
is in-process return-value state, never (in this checkpoint's scope)
persisted, cached, or transmitted across a process boundary (no cache/
result/calibration-schema integration is authorized here). If a future
checkpoint serializes or persists it, that checkpoint must perform the
schema/version audit this one does not need to."""

from dataclasses import dataclass
from enum import Enum

from src.distributed._checksums import (
    InvalidDistributedProvenanceError,
    require_non_negative_int as _require_non_negative_int,
    require_nonempty_str as _require_nonempty_str,
)
from src.distributed.executor import ExecutorFailureReason
from src.distributed.personal_policy import AdmissionRefusalReason


class WorkOutcomeKind(str, Enum):
    """The closed, eleven-member outcome taxonomy this checkpoint's own
    authorization names explicitly."""

    EXECUTED_AND_COMMITTED = "EXECUTED_AND_COMMITTED"
    RECOVERED_COMMITTED_RESULT = "RECOVERED_COMMITTED_RESULT"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    BUDGET_BLOCKED = "BUDGET_BLOCKED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    CANCELLED_NOT_STARTED = "CANCELLED_NOT_STARTED"
    STALE_LEASE = "STALE_LEASE"
    CONFLICTING_RESULT = "CONFLICTING_RESULT"
    AUDIT_PENDING = "AUDIT_PENDING"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


_COMMITTED_KINDS = frozenset(
    {WorkOutcomeKind.EXECUTED_AND_COMMITTED, WorkOutcomeKind.RECOVERED_COMMITTED_RESULT}
)


@dataclass(frozen=True)
class WorkOutcome:  # pylint: disable=too-many-instance-attributes
    """One work item's final, safe, typed outcome. Every optional field
    is present if and only if it applies to ``outcome_kind`` -- never a
    partially-populated record. No field here can carry raw candidate
    content, a raw exception message, or an infrastructure identifier."""

    scientific_work_id: str
    input_ordinal: int
    outcome_kind: WorkOutcomeKind
    result_content_checksum: str | None
    policy_refusal_reasons: tuple[AdmissionRefusalReason, ...]
    executor_failure_reason: ExecutorFailureReason | None

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _require_nonempty_str(self, "scientific_work_id")
        _require_non_negative_int(self, "input_ordinal")
        if not isinstance(self.outcome_kind, WorkOutcomeKind):
            raise InvalidDistributedProvenanceError(
                f"outcome_kind must be a WorkOutcomeKind, got {self.outcome_kind!r}"
            )
        if self.result_content_checksum is not None and self.outcome_kind not in _COMMITTED_KINDS:
            raise InvalidDistributedProvenanceError(
                "result_content_checksum may only be present for a committed outcome_kind"
            )
        if self.outcome_kind in _COMMITTED_KINDS and self.result_content_checksum is None:
            raise InvalidDistributedProvenanceError(
                "a committed outcome_kind requires a result_content_checksum"
            )
        if not isinstance(self.policy_refusal_reasons, tuple) or not all(
            isinstance(reason, AdmissionRefusalReason) for reason in self.policy_refusal_reasons
        ):
            raise InvalidDistributedProvenanceError(
                "policy_refusal_reasons must be a tuple of AdmissionRefusalReason"
            )
        if self.policy_refusal_reasons and self.outcome_kind != WorkOutcomeKind.POLICY_BLOCKED:
            raise InvalidDistributedProvenanceError(
                "policy_refusal_reasons may only be present for POLICY_BLOCKED"
            )
        if self.outcome_kind == WorkOutcomeKind.POLICY_BLOCKED and not self.policy_refusal_reasons:
            raise InvalidDistributedProvenanceError(
                "POLICY_BLOCKED requires at least one policy_refusal_reason"
            )
        if self.executor_failure_reason is not None and not isinstance(
            self.executor_failure_reason, ExecutorFailureReason
        ):
            raise InvalidDistributedProvenanceError(
                "executor_failure_reason must be an ExecutorFailureReason or None"
            )
        if self.executor_failure_reason is not None and self.outcome_kind not in (
            WorkOutcomeKind.RETRY_SCHEDULED,
            WorkOutcomeKind.RETRY_EXHAUSTED,
        ):
            raise InvalidDistributedProvenanceError(
                "executor_failure_reason may only be present for RETRY_SCHEDULED/RETRY_EXHAUSTED"
            )


def make_work_outcome(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    scientific_work_id: str,
    input_ordinal: int,
    outcome_kind: WorkOutcomeKind,
    *,
    result_content_checksum: str | None = None,
    policy_refusal_reasons: tuple[AdmissionRefusalReason, ...] = (),
    executor_failure_reason: ExecutorFailureReason | None = None,
) -> WorkOutcome:
    """The one construction helper the coordinator/worker engine uses to
    build a :class:`WorkOutcome` -- its keyword-only optional parameters
    mirror the type's own per-``outcome_kind`` field-presence invariants."""
    return WorkOutcome(
        scientific_work_id=scientific_work_id,
        input_ordinal=input_ordinal,
        outcome_kind=outcome_kind,
        result_content_checksum=result_content_checksum,
        policy_refusal_reasons=policy_refusal_reasons,
        executor_failure_reason=executor_failure_reason,
    )


@dataclass(frozen=True)
class CoordinatorRunSummary:
    """The full result of one coordinator run: every outcome, ordered by
    ``input_ordinal`` regardless of completion order (see
    :func:`build_run_summary`)."""

    outcomes: tuple[WorkOutcome, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.outcomes, tuple) or not all(
            isinstance(outcome, WorkOutcome) for outcome in self.outcomes
        ):
            raise InvalidDistributedProvenanceError("outcomes must be a tuple of WorkOutcome")
        ordinals = [outcome.input_ordinal for outcome in self.outcomes]
        if ordinals != sorted(ordinals):
            raise InvalidDistributedProvenanceError(
                "outcomes must be ordered by input_ordinal"
            )

    def count(self, outcome_kind: WorkOutcomeKind) -> int:
        """The number of outcomes of exactly ``outcome_kind``."""
        return sum(1 for outcome in self.outcomes if outcome.outcome_kind == outcome_kind)


def build_run_summary(outcomes: list[WorkOutcome]) -> CoordinatorRunSummary:
    """Build a :class:`CoordinatorRunSummary`, sorting ``outcomes`` by
    ``input_ordinal`` -- the one place completion-order results become
    deterministic, input-ordinal-ordered output, regardless of which
    work item's worker finished first."""
    return CoordinatorRunSummary(
        outcomes=tuple(sorted(outcomes, key=lambda outcome: outcome.input_ordinal))
    )


__all__ = [
    "WorkOutcomeKind",
    "WorkOutcome",
    "make_work_outcome",
    "CoordinatorRunSummary",
    "build_run_summary",
]
