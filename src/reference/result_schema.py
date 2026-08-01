"""MEGB-03E: typed, versioned task- and benchmark-level result models for the
reference evaluator (S*).

Distinguishes candidate correctness (``q_ref_task``) from measurement
validity (:class:`MeasurementStatus`), and distinguishes primary
reference-only scoring from full-suite EvalPlus compatibility diagnostics
(:class:`ReferenceOutcome` / :class:`FullSuiteDiagnostic`). Reference-only
case pass fractions are recorded for diagnostic purposes only (ticket
requirement 7): construction enforces that they are never substituted for
binary task scoring — ``q_ref_task`` is 1.0 only when every required case
passes, 0.0 only when at least one fails, and the case counts themselves are
validated for consistency with it, never derived arithmetically into a
fractional score.

``ReferenceOutcome``'s four base/plus values intentionally use the same
string labels as MEGB-03D's own ``src.reference.parity`` ``OUTCOME_*``
constants — both describe the same base/plus classification concept — but
this module does not import that one: MEGB-03D's outcomes describe
*parity-validating the comparison layer itself* against a fixed corpus, a
different concept from *a candidate's own* full-suite compatibility result,
which is what this schema represents.

This module defines schema and validation only: no candidate execution
(MEGB-03F's job), no persistent caching or audit storage, and no
benchmark-gaming delta calculation (MEGB-06's job) — see the ticket's
Non-Goals.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from src.evaluators.schema import FailureCategory

RESULT_SCHEMA_VERSION = "reference-result-schema-v1"
REQUIRED_TASK_COUNT = 164

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_VALID_FAILURE_CATEGORY_VALUES = frozenset(category.value for category in FailureCategory)


class InvalidReferenceResultError(ValueError):
    """Raised when a result's fields are internally inconsistent.

    Construction must fail loudly rather than silently accept a
    self-contradictory result (e.g. a "VALID" measurement claiming a
    fractional ``q_ref_task``, or a benchmark result whose per-status task
    counts don't sum to its evaluated count).
    """


@dataclass(frozen=True)
class ReferenceEvaluationContext:
    """Immutable identity/provenance for one candidate's reference evaluation.

    Required by the Global Architectural Constraint "No adaptive reference
    evaluation": a candidate must be frozen (``candidate_frozen_at``) before
    S* is invoked, and every reference evaluation must record the
    run/config/selection-rule identifiers that let a later audit
    reconstruct exactly why and when this candidate was evaluated.
    """

    experiment_run_id: str
    optimization_run_id: str
    candidate_id: str
    candidate_sha256: str
    candidate_frozen_at: str
    candidate_selection_rule: str
    optimization_config_sha256: str
    evaluator_version: str
    dataset_version: str
    partition_version: str
    execution_profile_id: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self, "experiment_run_id")
        _require_nonempty_str(self, "optimization_run_id")
        _require_nonempty_str(self, "candidate_id")
        _require_sha256_hex(self, "candidate_sha256")
        _require_nonempty_str(self, "candidate_frozen_at")
        _require_nonempty_str(self, "candidate_selection_rule")
        _require_sha256_hex(self, "optimization_config_sha256")
        _require_nonempty_str(self, "evaluator_version")
        _require_nonempty_str(self, "dataset_version")
        _require_nonempty_str(self, "partition_version")
        _require_nonempty_str(self, "execution_profile_id")


class MeasurementStatus(str, Enum):
    """Validity of a task measurement, independent of candidate correctness."""

    VALID = "VALID"
    INVALID_ORACLE = "INVALID_ORACLE"
    INVALID_INFRASTRUCTURE = "INVALID_INFRASTRUCTURE"
    INVALID_PROTOCOL = "INVALID_PROTOCOL"
    INCOMPLETE = "INCOMPLETE"


class ReferenceOutcome(str, Enum):
    """Full-suite (base/plus) compatibility classification for one candidate.

    ``PASS_BASE_FAIL_PLUS`` is evidence of insufficient original evidence,
    never automatic proof of intentional gaming (requirement 9).
    ``FAIL_BASE_PASS_PLUS`` is an anomaly requiring investigation —
    comparison mismatch, oracle inconsistency, nondeterminism,
    execution-order effects, or an implementation defect (requirement 10) —
    never treated as a normal outcome.
    """

    PASS_BASE_PASS_PLUS = "PASS_BASE_PASS_PLUS"
    PASS_BASE_FAIL_PLUS = "PASS_BASE_FAIL_PLUS"
    FAIL_BASE_FAIL_PLUS = "FAIL_BASE_FAIL_PLUS"
    FAIL_BASE_PASS_PLUS = "FAIL_BASE_PASS_PLUS"
    INVALID_MEASUREMENT = "INVALID_MEASUREMENT"


def _require_nonempty_str(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or value == "":
        raise InvalidReferenceResultError(
            f"{field_name!r} must be a nonempty string, got {value!r}"
        )


def _require_sha256_hex(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or not _SHA256_HEX_PATTERN.match(value):
        raise InvalidReferenceResultError(
            f"{field_name!r} must be a 64-character lowercase hex sha256 digest, got {value!r}"
        )


def _require_non_negative_int(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvalidReferenceResultError(
            f"{field_name!r} must be a non-negative int, got {value!r}"
        )


def _require_non_negative_float(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise InvalidReferenceResultError(
            f"{field_name!r} must be a non-negative number, got {value!r}"
        )


# Failure categories a VALID measurement may attribute to the candidate itself
# (the measurement ran to completion and observed the candidate fail).
_CANDIDATE_FAILURE_CATEGORIES = frozenset(
    {
        FailureCategory.WRONG_OUTPUT,
        FailureCategory.SYNTAX_ERROR,
        FailureCategory.RUNTIME_EXCEPTION,
        FailureCategory.TIMEOUT,
        FailureCategory.RESOURCE_LIMIT,
        FailureCategory.OUTPUT_LIMIT,
    }
)

# Failure categories that describe the measurement apparatus itself breaking,
# independent of anything the candidate did — never attributed to VALID results.
_MEASUREMENT_FAILURE_CATEGORIES = frozenset(
    {
        FailureCategory.PROTOCOL_ERROR,
        FailureCategory.INFRASTRUCTURE_ERROR,
    }
)


def _derive_full_suite_outcome(
    base_pass_count: int, base_total: int, plus_pass_count: int, plus_total: int
) -> ReferenceOutcome:
    base_passed = base_pass_count == base_total
    plus_passed = plus_pass_count == plus_total
    if base_passed and plus_passed:
        return ReferenceOutcome.PASS_BASE_PASS_PLUS
    if base_passed and not plus_passed:
        return ReferenceOutcome.PASS_BASE_FAIL_PLUS
    if not base_passed and not plus_passed:
        return ReferenceOutcome.FAIL_BASE_FAIL_PLUS
    return ReferenceOutcome.FAIL_BASE_PASS_PLUS


@dataclass(frozen=True)
class FullSuiteDiagnostic:
    """Optional full-suite EvalPlus base/plus compatibility diagnostic for one task.

    Diagnostic only (requirement 7 applies here too): never used to derive
    or override ``q_ref_task``. ``outcome`` must agree with the pass/total
    counts it accompanies — this is checked, not merely documented — except
    when ``outcome`` is :attr:`ReferenceOutcome.INVALID_MEASUREMENT`, which
    means the full-suite comparison itself did not produce a trustworthy
    base/plus classification and the counts are informational only.
    """

    outcome: ReferenceOutcome
    base_total: int
    base_pass_count: int
    plus_total: int
    plus_pass_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ReferenceOutcome):
            raise InvalidReferenceResultError(
                f"outcome must be a ReferenceOutcome, got {self.outcome!r}"
            )
        _require_non_negative_int(self, "base_total")
        _require_non_negative_int(self, "base_pass_count")
        _require_non_negative_int(self, "plus_total")
        _require_non_negative_int(self, "plus_pass_count")
        if self.base_pass_count > self.base_total:
            raise InvalidReferenceResultError(
                f"base_pass_count ({self.base_pass_count}) exceeds base_total ({self.base_total})"
            )
        if self.plus_pass_count > self.plus_total:
            raise InvalidReferenceResultError(
                f"plus_pass_count ({self.plus_pass_count}) exceeds plus_total ({self.plus_total})"
            )
        if self.outcome == ReferenceOutcome.INVALID_MEASUREMENT:
            return
        if self.base_total < 1 or self.plus_total < 1:
            raise InvalidReferenceResultError(
                "base_total and plus_total must each be at least 1 unless outcome is "
                "INVALID_MEASUREMENT"
            )
        expected_outcome = _derive_full_suite_outcome(
            self.base_pass_count, self.base_total, self.plus_pass_count, self.plus_total
        )
        if self.outcome != expected_outcome:
            raise InvalidReferenceResultError(
                f"outcome {self.outcome!r} is inconsistent with base "
                f"{self.base_pass_count}/{self.base_total} and plus "
                f"{self.plus_pass_count}/{self.plus_total} (expected {expected_outcome!r})"
            )


@dataclass(frozen=True)
class ReferenceTaskResult:
    """One task's reference-evaluation (S*) result for one frozen candidate.

    Deliberately separates *candidate correctness* (``q_ref_task``) from
    *measurement validity* (``status``): a broken oracle or infrastructure
    failure must never be silently folded into a candidate failure, and a
    candidate failure must never be silently folded into a measurement
    failure. ``full_suite_diagnostic`` is an independent, optional
    diagnostic and is never used to derive or override ``q_ref_task`` —
    requirement 6 keeps these concepts separate.
    """

    task_id: str
    context: ReferenceEvaluationContext
    status: MeasurementStatus
    q_ref_task: float | None
    reference_case_total: int
    reference_case_pass_count: int
    first_failure_category: FailureCategory
    oracle_version: str
    reference_case_checksum: str
    evaluated_at: str
    duration_seconds: float
    execution_failure_counts: Mapping[str, int] = field(default_factory=dict)
    full_suite_diagnostic: FullSuiteDiagnostic | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_nonempty_str(self, "task_id")
        _require_nonempty_str(self, "evaluated_at")
        _require_nonempty_str(self, "oracle_version")
        _require_sha256_hex(self, "reference_case_checksum")
        _require_non_negative_int(self, "reference_case_total")
        _require_non_negative_int(self, "reference_case_pass_count")
        _require_non_negative_float(self, "duration_seconds")
        if self.reference_case_pass_count > self.reference_case_total:
            raise InvalidReferenceResultError(
                f"task {self.task_id!r}: reference_case_pass_count "
                f"({self.reference_case_pass_count}) exceeds reference_case_total "
                f"({self.reference_case_total})"
            )
        self._validate_execution_failure_counts()
        self._validate_types()
        if self.status == MeasurementStatus.VALID:
            self._validate_valid_measurement()
        else:
            self._validate_non_valid_measurement()

    def _validate_execution_failure_counts(self) -> None:
        for category_value, count in self.execution_failure_counts.items():
            if category_value not in _VALID_FAILURE_CATEGORY_VALUES:
                raise InvalidReferenceResultError(
                    f"task {self.task_id!r}: execution_failure_counts has unknown "
                    f"category key {category_value!r}"
                )
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise InvalidReferenceResultError(
                    f"task {self.task_id!r}: execution_failure_counts[{category_value!r}] "
                    f"must be a non-negative int, got {count!r}"
                )

    def _validate_types(self) -> None:
        if not isinstance(self.status, MeasurementStatus):
            raise InvalidReferenceResultError(
                f"status must be a MeasurementStatus, got {self.status!r}"
            )
        if not isinstance(self.first_failure_category, FailureCategory):
            raise InvalidReferenceResultError(
                f"first_failure_category must be a FailureCategory, "
                f"got {self.first_failure_category!r}"
            )
        if self.full_suite_diagnostic is not None and not isinstance(
            self.full_suite_diagnostic, FullSuiteDiagnostic
        ):
            raise InvalidReferenceResultError(
                f"full_suite_diagnostic must be a FullSuiteDiagnostic or None, "
                f"got {self.full_suite_diagnostic!r}"
            )

    def _validate_valid_measurement(self) -> None:
        # pylint: disable=unidiomatic-typecheck
        if type(self.q_ref_task) is not float or self.q_ref_task not in (0.0, 1.0):
            raise InvalidReferenceResultError(
                f"task {self.task_id!r}: q_ref_task must be exactly 0.0 or 1.0 when status "
                f"is VALID (never a fraction, never None), got {self.q_ref_task!r}"
            )
        if self.reference_case_total < 1:
            raise InvalidReferenceResultError(
                f"task {self.task_id!r}: reference_case_total must be at least 1 "
                f"when status is VALID"
            )
        if self.q_ref_task == 1.0:
            if self.reference_case_pass_count != self.reference_case_total:
                raise InvalidReferenceResultError(
                    f"task {self.task_id!r}: q_ref_task is 1.0 but only "
                    f"{self.reference_case_pass_count}/{self.reference_case_total} required "
                    f"reference-only cases passed (requirement 4: all must pass)"
                )
            if self.first_failure_category != FailureCategory.NONE:
                raise InvalidReferenceResultError(
                    f"task {self.task_id!r}: first_failure_category must be NONE when "
                    f"q_ref_task is 1.0, got {self.first_failure_category!r}"
                )
        else:
            if self.reference_case_pass_count >= self.reference_case_total:
                raise InvalidReferenceResultError(
                    f"task {self.task_id!r}: q_ref_task is 0.0 but "
                    f"{self.reference_case_pass_count}/{self.reference_case_total} required "
                    f"reference-only cases passed (requirement 5: a fail needs a real failure)"
                )
            if self.first_failure_category not in _CANDIDATE_FAILURE_CATEGORIES:
                raise InvalidReferenceResultError(
                    f"task {self.task_id!r}: first_failure_category must name a "
                    f"candidate-attributable failure when q_ref_task is 0.0, "
                    f"got {self.first_failure_category!r}"
                )

    def _validate_non_valid_measurement(self) -> None:
        if self.q_ref_task is not None:
            raise InvalidReferenceResultError(
                f"task {self.task_id!r}: q_ref_task must be None when status is "
                f"{self.status.value} (a non-VALID measurement yields no correctness "
                f"signal), got {self.q_ref_task!r}"
            )
        if self.full_suite_diagnostic is not None:
            raise InvalidReferenceResultError(
                f"task {self.task_id!r}: full_suite_diagnostic must be None when status is "
                f"{self.status.value} (no full-suite diagnostic without a valid measurement)"
            )
        if self.status == MeasurementStatus.INCOMPLETE:
            if self.first_failure_category != FailureCategory.NONE:
                raise InvalidReferenceResultError(
                    f"task {self.task_id!r}: first_failure_category must be NONE when "
                    f"status is INCOMPLETE (measurement never ran far enough to categorize "
                    f"anything)"
                )
        elif self.first_failure_category not in _MEASUREMENT_FAILURE_CATEGORIES:
            raise InvalidReferenceResultError(
                f"task {self.task_id!r}: first_failure_category must name a "
                f"measurement-apparatus failure when status is {self.status.value}, "
                f"got {self.first_failure_category!r}"
            )


_AGGREGATE_STATUS_PRIORITY = (
    MeasurementStatus.INVALID_INFRASTRUCTURE,
    MeasurementStatus.INVALID_PROTOCOL,
    MeasurementStatus.INVALID_ORACLE,
    MeasurementStatus.INCOMPLETE,
)


@dataclass(frozen=True)
class ReferenceBenchmarkResult:
    """Aggregate reference-evaluation (S*) result for one frozen candidate
    across the full 164-task reference-evaluator validation corpus.

    ``q_ref`` enforces "never silently change the denominator": it is only
    ever computed as an average over exactly ``expected_task_count`` VALID
    task results. If any expected task is missing or its measurement is not
    VALID, ``q_ref`` is ``None`` — never a mean over a smaller, silently
    substituted denominator. ``task_manifest_checksum`` pins exactly which
    164-task reference-validation manifest this benchmark was evaluated
    against, so the denominator's identity — not just its size — cannot
    silently drift between runs.
    """

    candidate_context: ReferenceEvaluationContext
    task_results: tuple[ReferenceTaskResult, ...]
    task_manifest_checksum: str
    oracle_version: str
    evaluated_at: str
    duration_seconds: float
    expected_task_count: int = REQUIRED_TASK_COUNT

    def __post_init__(self) -> None:
        _require_nonempty_str(self, "evaluated_at")
        _require_nonempty_str(self, "oracle_version")
        _require_sha256_hex(self, "task_manifest_checksum")
        _require_non_negative_float(self, "duration_seconds")
        _require_non_negative_int(self, "expected_task_count")
        if self.expected_task_count != REQUIRED_TASK_COUNT:
            raise InvalidReferenceResultError(
                f"expected_task_count must be exactly {REQUIRED_TASK_COUNT} "
                f"(the reference-evaluator validation-corpus denominator), "
                f"got {self.expected_task_count}"
            )
        task_ids = [result.task_id for result in self.task_results]
        if len(task_ids) != len(set(task_ids)):
            raise InvalidReferenceResultError("task_results contains duplicate task_id entries")
        if len(self.task_results) > self.expected_task_count:
            raise InvalidReferenceResultError(
                f"task_results has {len(self.task_results)} entries, more than "
                f"expected_task_count={self.expected_task_count}"
            )
        for result in self.task_results:
            if result.context != self.candidate_context:
                raise InvalidReferenceResultError(
                    f"task_result for {result.task_id!r} was evaluated under a different "
                    f"context than candidate_context"
                )
            if result.oracle_version != self.oracle_version:
                raise InvalidReferenceResultError(
                    f"task_result for {result.task_id!r} has oracle_version "
                    f"{result.oracle_version!r}, expected {self.oracle_version!r}"
                )

    @property
    def evaluated_task_count(self) -> int:
        """Number of tasks with any result at all (attempted, regardless of status)."""
        return len(self.task_results)

    @property
    def valid_task_count(self) -> int:
        """Number of task results with :attr:`MeasurementStatus.VALID`."""
        return sum(1 for result in self.task_results if result.status == MeasurementStatus.VALID)

    @property
    def invalid_task_count(self) -> int:
        """Number of task results with any non-VALID, non-INCOMPLETE status."""
        return sum(
            1
            for result in self.task_results
            if result.status
            in (
                MeasurementStatus.INVALID_ORACLE,
                MeasurementStatus.INVALID_INFRASTRUCTURE,
                MeasurementStatus.INVALID_PROTOCOL,
            )
        )

    @property
    def incomplete_task_count(self) -> int:
        """Number of task results with :attr:`MeasurementStatus.INCOMPLETE`."""
        return sum(
            1 for result in self.task_results if result.status == MeasurementStatus.INCOMPLETE
        )

    @property
    def status_counts(self) -> Mapping[MeasurementStatus, int]:
        """Count of task results per :class:`MeasurementStatus` value."""
        counts = {status: 0 for status in MeasurementStatus}
        for result in self.task_results:
            counts[result.status] += 1
        return counts

    @property
    def missing_task_count(self) -> int:
        """Expected tasks with no result present at all (not even attempted)."""
        return self.expected_task_count - len(self.task_results)

    @property
    def primary_pass_count(self) -> int:
        """Number of tasks passing primary reference-only evidence (q_ref_task == 1.0)."""
        return sum(1 for result in self.task_results if result.q_ref_task == 1.0)

    @property
    def full_suite_outcome_counts(self) -> Mapping[ReferenceOutcome, int]:
        """Count of full-suite diagnostic outcomes among tasks that have one."""
        counts = {outcome: 0 for outcome in ReferenceOutcome}
        for result in self.task_results:
            if result.full_suite_diagnostic is not None:
                counts[result.full_suite_diagnostic.outcome] += 1
        return counts

    @property
    def aggregate_status(self) -> MeasurementStatus:
        """Single overall status summarizing the whole benchmark run.

        INCOMPLETE if any expected task is missing outright or has an
        INCOMPLETE measurement; otherwise the highest-priority invalid
        status present; otherwise VALID.
        """
        if self.missing_task_count > 0:
            return MeasurementStatus.INCOMPLETE
        counts = self.status_counts
        for status in _AGGREGATE_STATUS_PRIORITY:
            if counts[status] > 0:
                return status
        return MeasurementStatus.VALID

    @property
    def q_ref(self) -> float | None:
        """Primary reference score, or ``None`` if not computable over the full denominator."""
        if len(self.task_results) != self.expected_task_count:
            return None
        if self.valid_task_count != self.expected_task_count:
            return None
        total = sum(
            result.q_ref_task for result in self.task_results if result.q_ref_task is not None
        )
        return total / self.expected_task_count
