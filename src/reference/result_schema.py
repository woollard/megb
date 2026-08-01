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

**Approved Correction (v2, post-MEGB-03F trust-boundary review):** v1 forced
every ``ReferenceTaskResult`` in a benchmark to carry an *identical*
candidate identity (via a single shared ``ReferenceEvaluationContext``
that embedded ``candidate_id``/``candidate_sha256``), which cannot
represent a real 164-task benchmark run — HumanEval tasks are independent
programming problems, so a legitimate run necessarily evaluates 164
*different* task-specific candidate solutions, one per task. v2 splits this
into: a shared :class:`ReferenceRunContext` (run/evaluator/dataset/
partition/execution-profile identity, genuinely common across all 164
tasks); a task-specific ``candidate_id``/``candidate_sha256`` directly on
:class:`ReferenceTaskResult`; and a versioned, self-checksummed
:class:`ReferenceValidationCandidateSetManifest` binding the frozen, ordered task-to-candidate
mapping for the whole benchmark, verified against every task result by
:class:`ReferenceBenchmarkResult`. This is a breaking schema change —
``RESULT_SCHEMA_VERSION`` is incremented accordingly, and v1 payloads are
rejected explicitly (see ``src.reference.result_redaction``) rather than
silently misparsed under v2 field names. No v1 artifact has ever been
persisted (no code wired v1 into any lock/build/CLI pipeline), so no
migration path is required or provided.

**Approved Correction (v3, post-MEGB-03G.1 schema-completeness review):**
surfaced while implementing MEGB-03G.1's ``aggregate_reference_results``:
``ComparisonProfile.profile_version``/``COMPARISON_PROFILE_VERSION`` was
verified once by ``evaluate_reference`` at evaluation time but was never
itself a field on :class:`ReferenceRunContext` or :class:`ReferenceTaskResult`
-- there was no way for a benchmark-level aggregator (or any later
consumer reloading persisted results) to independently re-verify
comparison-profile consistency across already-constructed results from
data alone. v3 adds ``comparison_profile_version`` directly to
:class:`ReferenceRunContext`, so it is included in the run context's
equality check (and therefore in every place that already enforces
run-context equality: :class:`ReferenceBenchmarkResult`'s per-task
validation and ``aggregate_reference_results``), serialized/deserialized
like every other run-context field, and validated by ``evaluate_reference``
against the evidence's actual comparison profile before any candidate code
executes. This is a breaking schema change -- ``RESULT_SCHEMA_VERSION`` is
incremented accordingly, and both v1 and v2 payloads are rejected
explicitly. No v2 (or v1) artifact has ever been persisted (no code wires
either into any lock/build/CLI pipeline), so no migration path is required
or provided here either. This correction does not change
``reference-validation-candidate-set-manifest-v1``,
``partition-v1``/``PARTITION_ALGORITHM_VERSION``,
``oracle-v1``/``ORACLE_ALGORITHM_VERSION``, or
``COMPARISON_PROFILE_VERSION``'s own value -- only ``RESULT_SCHEMA_VERSION``
moves, from ``reference-result-schema-v2`` to ``reference-result-schema-v3``.
"""

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from src.evaluators.schema import FailureCategory

RESULT_SCHEMA_VERSION = "reference-result-schema-v3"
REQUIRED_TASK_COUNT = 164

REFERENCE_VALIDATION_CANDIDATE_SET_MANIFEST_SCHEMA_VERSION = (
    "reference-validation-candidate-set-manifest-v1"
)
REFERENCE_VALIDATION_CANDIDATE_SET_ALGORITHM_VERSION = "reference-validation-candidate-set-v1"

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_VALID_FAILURE_CATEGORY_VALUES = frozenset(category.value for category in FailureCategory)


class InvalidReferenceResultError(ValueError):
    """Raised when a result's fields are internally inconsistent.

    Construction must fail loudly rather than silently accept a
    self-contradictory result (e.g. a "VALID" measurement claiming a
    fractional ``q_ref_task``, or a benchmark result whose per-status task
    counts don't sum to its evaluated count).
    """


class InvalidReferenceValidationCandidateSetManifestError(InvalidReferenceResultError):
    """Raised when a :class:`ReferenceValidationCandidateSetManifest` is internally inconsistent
    or its checksum does not match its own recomputed contents.

    A subclass of :class:`InvalidReferenceResultError` so existing callers
    that catch the base type continue to catch this too.
    """


class UnsupportedResultSchemaVersionError(InvalidReferenceResultError):
    """Raised when deserializing a payload stamped with a different
    ``RESULT_SCHEMA_VERSION`` than this module currently implements.

    Deserialization must fail explicitly on a version mismatch rather than
    attempt to parse an older (or newer) payload shape under the current
    field names.
    """


@dataclass(frozen=True)
class ReferenceRunContext:
    """Immutable identity/provenance shared across every task result in one
    reference-evaluation benchmark run.

    Deliberately contains no candidate-identity field: a benchmark run
    evaluates 164 *different* task-specific candidate solutions (one per
    independent HumanEval task), so nothing here may vary per task or imply
    a single candidate. Task-specific candidate identity lives on
    :class:`ReferenceTaskResult` instead, and the whole set's identity lives
    in :class:`ReferenceValidationCandidateSetManifest`. ``portfolio_frozen_at``/
    ``portfolio_selection_rule`` describe the one atomic freeze/selection
    event that produced the entire 164-solution portfolio evaluated in this
    run, per the Global Architectural Constraint "No adaptive reference
    evaluation" — required to record run/config/selection-rule identifiers
    letting a later audit reconstruct exactly why and when this portfolio
    was evaluated. ``comparison_profile_version`` (v3) records the
    comparison-profile identity every task result was compared under —
    added so run-context equality (already enforced everywhere a benchmark
    or aggregate is constructed) also catches a comparison-profile
    inconsistency, not just dataset/partition/execution/evaluator drift.
    """

    experiment_run_id: str
    optimization_run_id: str
    optimization_config_sha256: str
    portfolio_frozen_at: str
    portfolio_selection_rule: str
    evaluator_version: str
    dataset_version: str
    partition_version: str
    execution_profile_id: str
    comparison_profile_version: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self, "experiment_run_id")
        _require_nonempty_str(self, "optimization_run_id")
        _require_sha256_hex(self, "optimization_config_sha256")
        _require_nonempty_str(self, "portfolio_frozen_at")
        _require_nonempty_str(self, "portfolio_selection_rule")
        _require_nonempty_str(self, "evaluator_version")
        _require_nonempty_str(self, "dataset_version")
        _require_nonempty_str(self, "partition_version")
        _require_nonempty_str(self, "execution_profile_id")
        _require_nonempty_str(self, "comparison_profile_version")


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
class CandidateSetEntry:
    """One task's binding within a :class:`ReferenceValidationCandidateSetManifest`: which
    task-specific candidate was frozen for evaluation against that task.

    No room for privileged content: exactly three plain string identifiers,
    never a source blob, expected output, or test case.
    """

    task_id: str
    candidate_id: str
    candidate_sha256: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self, "task_id")
        _require_nonempty_str(self, "candidate_id")
        _require_sha256_hex(self, "candidate_sha256")


def _candidate_set_manifest_checksum(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    manifest_schema_version: str,
    algorithm_version: str,
    task_manifest_id: str,
    task_manifest_checksum: str,
    selection_provenance_sha256: str,
    entries: tuple[CandidateSetEntry, ...],
) -> str:
    hasher = hashlib.sha256()
    for value in (
        manifest_schema_version,
        algorithm_version,
        task_manifest_id,
        task_manifest_checksum,
        selection_provenance_sha256,
    ):
        hasher.update(value.encode("utf-8"))
        hasher.update(b"\x00")
    for entry in entries:
        hasher.update(entry.task_id.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(entry.candidate_id.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(entry.candidate_sha256.encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


@dataclass(frozen=True)
class ReferenceValidationCandidateSetManifest:
    """Versioned, self-checksummed binding of the whole benchmark's
    task-to-candidate mapping: exactly one :class:`CandidateSetEntry` per
    required task, ordered by ``task_id``.

    ``manifest_checksum`` is always recomputed from the manifest's own
    canonical contents at construction time — never accepted as an
    unverified caller-provided value. If a caller supplies a nonempty
    ``manifest_checksum`` that does not match the recomputation, this is a
    tampered or corrupted manifest and construction fails; otherwise the
    recomputed value is stamped in automatically. This is the same
    auto-compute-or-reject pattern already established by
    :class:`~src.reference.reference_evaluator.ReferenceTaskEvidence`, so
    reordering, duplicating, or hand-editing one entry after the fact is
    caught the moment the manifest is (re)constructed — including when
    reloaded from persisted storage (see
    ``src.reference.result_redaction.candidate_set_manifest_from_dict``,
    which reconstructs through this same constructor).
    """

    manifest_schema_version: str
    algorithm_version: str
    task_manifest_id: str
    task_manifest_checksum: str
    selection_provenance_sha256: str
    entries: tuple[CandidateSetEntry, ...]
    expected_task_count: int = REQUIRED_TASK_COUNT
    manifest_checksum: str = ""

    def __post_init__(self) -> None:
        _require_nonempty_str(self, "manifest_schema_version")
        _require_nonempty_str(self, "algorithm_version")
        _require_nonempty_str(self, "task_manifest_id")
        _require_sha256_hex(self, "task_manifest_checksum")
        _require_sha256_hex(self, "selection_provenance_sha256")
        _require_non_negative_int(self, "expected_task_count")
        if self.expected_task_count != REQUIRED_TASK_COUNT:
            raise InvalidReferenceValidationCandidateSetManifestError(
                f"expected_task_count must be exactly {REQUIRED_TASK_COUNT} "
                f"(never a silently different denominator), got {self.expected_task_count}"
            )
        if len(self.entries) != self.expected_task_count:
            raise InvalidReferenceValidationCandidateSetManifestError(
                f"candidate_set_manifest must contain exactly {self.expected_task_count} "
                f"entries (one per required task), got {len(self.entries)}"
            )
        task_ids = [entry.task_id for entry in self.entries]
        if len(task_ids) != len(set(task_ids)):
            raise InvalidReferenceValidationCandidateSetManifestError(
                "candidate_set_manifest entries contains duplicate task_id entries"
            )
        if task_ids != sorted(task_ids):
            raise InvalidReferenceValidationCandidateSetManifestError(
                "candidate_set_manifest entries must be sorted by task_id for "
                "deterministic, reorder-proof serialization"
            )
        expected_checksum = _candidate_set_manifest_checksum(
            self.manifest_schema_version,
            self.algorithm_version,
            self.task_manifest_id,
            self.task_manifest_checksum,
            self.selection_provenance_sha256,
            self.entries,
        )
        if self.manifest_checksum and self.manifest_checksum != expected_checksum:
            raise InvalidReferenceValidationCandidateSetManifestError(
                f"manifest_checksum {self.manifest_checksum!r} does not match the "
                f"recomputed checksum {expected_checksum!r} over its own contents — "
                f"tampered or corrupted candidate-set manifest"
            )
        object.__setattr__(self, "manifest_checksum", expected_checksum)


@dataclass(frozen=True)
class ReferenceTaskResult:
    """One task's reference-evaluation (S*) result for its own task-specific
    frozen candidate solution.

    Deliberately separates *candidate correctness* (``q_ref_task``) from
    *measurement validity* (``status``): a broken oracle or infrastructure
    failure must never be silently folded into a candidate failure, and a
    candidate failure must never be silently folded into a measurement
    failure. ``full_suite_diagnostic`` is an independent, optional
    diagnostic and is never used to derive or override ``q_ref_task`` —
    requirement 6 keeps these concepts separate. ``candidate_id``/
    ``candidate_sha256`` are this task's own candidate identity — every task
    in a real 164-task benchmark run has different code and therefore a
    different hash here; only ``context`` (the shared
    :class:`ReferenceRunContext`) must be identical across all 164 tasks.
    """

    task_id: str
    candidate_id: str
    candidate_sha256: str
    context: ReferenceRunContext
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
        _require_nonempty_str(self, "candidate_id")
        _require_sha256_hex(self, "candidate_sha256")
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
    """Aggregate reference-evaluation (S*) result for one frozen 164-solution
    candidate portfolio across the full 164-task reference-evaluator
    validation corpus — the MEGB-03 evaluator-validation aggregate. This is
    a distinct concept from MEGB-06's 163-task experimental aggregate: this
    type's ``expected_task_count``/denominator is always exactly 164 and
    must never be silently reused as or confused with MEGB-06's separate
    163-task primary-experiment metric.

    ``q_ref`` enforces "never silently change the denominator": it is only
    ever computed as an average over exactly ``expected_task_count`` VALID
    task results. If any expected task is missing or its measurement is not
    VALID, ``q_ref`` is ``None`` — never a mean over a smaller, silently
    substituted denominator. ``task_manifest_checksum`` pins exactly which
    164-task reference-validation manifest this benchmark was evaluated
    against, so the denominator's identity — not just its size — cannot
    silently drift between runs. ``candidate_set_manifest`` pins exactly
    which task-specific candidate solution was evaluated for every task;
    every task result's own ``candidate_id``/``candidate_sha256`` must match
    its manifest entry exactly, so a task result cannot silently claim to
    measure a different candidate than the one the frozen portfolio
    actually bound to that task.
    """

    run_context: ReferenceRunContext
    candidate_set_manifest: ReferenceValidationCandidateSetManifest
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
        if self.candidate_set_manifest.expected_task_count != self.expected_task_count:
            raise InvalidReferenceResultError(
                f"candidate_set_manifest.expected_task_count "
                f"({self.candidate_set_manifest.expected_task_count}) does not match "
                f"expected_task_count ({self.expected_task_count})"
            )
        if self.candidate_set_manifest.task_manifest_checksum != self.task_manifest_checksum:
            raise InvalidReferenceResultError(
                f"candidate_set_manifest.task_manifest_checksum "
                f"({self.candidate_set_manifest.task_manifest_checksum!r}) does not match "
                f"task_manifest_checksum ({self.task_manifest_checksum!r})"
            )
        task_ids = [result.task_id for result in self.task_results]
        if len(task_ids) != len(set(task_ids)):
            raise InvalidReferenceResultError("task_results contains duplicate task_id entries")
        if len(self.task_results) > self.expected_task_count:
            raise InvalidReferenceResultError(
                f"task_results has {len(self.task_results)} entries, more than "
                f"expected_task_count={self.expected_task_count}"
            )
        candidate_by_task_id = {
            entry.task_id: entry for entry in self.candidate_set_manifest.entries
        }
        for result in self.task_results:
            self._validate_task_result_against_run(result, candidate_by_task_id)

    def _validate_task_result_against_run(
        self,
        result: ReferenceTaskResult,
        candidate_by_task_id: Mapping[str, CandidateSetEntry],
    ) -> None:
        if result.context != self.run_context:
            raise InvalidReferenceResultError(
                f"task_result for {result.task_id!r} was evaluated under a different "
                f"run_context than this benchmark's run_context"
            )
        if result.oracle_version != self.oracle_version:
            raise InvalidReferenceResultError(
                f"task_result for {result.task_id!r} has oracle_version "
                f"{result.oracle_version!r}, expected {self.oracle_version!r}"
            )
        entry = candidate_by_task_id.get(result.task_id)
        if entry is None:
            raise InvalidReferenceResultError(
                f"task_result for {result.task_id!r} has no corresponding entry in "
                f"candidate_set_manifest"
            )
        candidate_identity_matches = (
            entry.candidate_id == result.candidate_id
            and entry.candidate_sha256 == result.candidate_sha256
        )
        if not candidate_identity_matches:
            raise InvalidReferenceResultError(
                f"task_result for {result.task_id!r} candidate identity "
                f"(candidate_id={result.candidate_id!r}, "
                f"candidate_sha256={result.candidate_sha256!r}) does not match "
                f"candidate_set_manifest entry (candidate_id={entry.candidate_id!r}, "
                f"candidate_sha256={entry.candidate_sha256!r})"
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
