"""MEGB-03H.2B.1: fresh-execution ``CachePolicy`` and the durable
calibration-trace-recorder boundary.

Split out from ``src.reference.reference_orchestrator`` (whose
``ReferenceOrchestrator``/``OrchestrationConfig`` are this module's only
real callers) purely to keep each module under a manageable size -- there
is no behavioral reason for the split; both modules are part of the same
H.2B.1 checkpoint.
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from src.reference.reference_evaluator import ReferenceTaskEvidence
from src.reference.result_schema import ReferenceTaskResult

if TYPE_CHECKING:
    # Import-cycle-safe: only ever used here as type annotations.
    # src.reference.calibration_schema itself imports WorkItemDisposition
    # from src.reference.reference_orchestrator, and this module is
    # imported by reference_orchestrator.py -- none of these three imports
    # ever execute at runtime in a way that would form an actual cycle.
    from src.reference.calibration_schema import CalibrationTaskEvaluationRecord
    from src.reference.reference_orchestrator import WorkItem, WorkItemDisposition


class CachePolicy(str, Enum):
    """How a run consults and populates the production
    :class:`~src.reference.reference_cache.ReferenceResultCache`.

    ``CACHE_FIRST`` is the original, unchanged MEGB-03G.3 behavior: consult
    the cache before executing, write fresh valid results back. The two
    "fresh" policies (MEGB-03H's calibration stages) always bypass
    ``cache.get()`` completely -- an identical valid entry already present
    is never allowed to suppress a fresh measurement:

    - ``FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID``: execute fresh, durably
      persist the calibration trace first, then write cacheable valid
      results to the production cache exactly as ``CACHE_FIRST`` would
      (same conflict/storage-failure handling).
    - ``FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE``: execute fresh, durably
      persist the calibration trace, and never write to the production
      cache at all (e.g. H.6's repeated determinism probes, which must
      never contaminate the production cache with repeat-measurement
      noise).
    """

    CACHE_FIRST = "CACHE_FIRST"
    FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID = "FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID"
    FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE = "FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE"


FRESH_CACHE_POLICIES = frozenset(
    {
        CachePolicy.FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID,
        CachePolicy.FRESH_MEASURE_NO_PRODUCTION_CACHE_WRITE,
    }
)


class CalibrationTraceRequiredError(ValueError):
    """Raised at :class:`~src.reference.reference_orchestrator.OrchestrationConfig`
    construction time when ``cache_policy`` is a fresh policy but no
    ``trace_recorder`` was supplied -- a fresh policy's whole purpose is to
    produce a durable calibration trace, so it can never be configured
    without one."""


class ReplicateRequiresFreshPolicyError(ValueError):
    """Raised by :meth:`~src.reference.reference_orchestrator.ReferenceOrchestrator.run`
    when a submitted :class:`~src.reference.reference_orchestrator.WorkItem`
    carries a nonzero ``task_evaluation_replicate_id`` (i.e. explicit
    replicate semantics) while ``cache_policy`` is ``CACHE_FIRST`` -- a
    repeated calibration coordinate must never silently run under
    production cache-first semantics; replicate semantics require an
    explicit fresh :class:`CachePolicy`."""


class CalibrationTracePersistenceError(RuntimeError):
    """Raised when a :class:`TraceRecorder` fails to durably persist a
    fresh-policy attempt sequence -- always the *typed* error a caller sees
    (see :meth:`~src.reference.reference_orchestrator.ReferenceOrchestrator._record_fresh_attempt`,
    which wraps whatever the underlying recorder/sink actually raised via
    ``raise ... from exc``, preserving the original cause instead of
    letting an arbitrary exception type escape). Guarantees, by
    construction of its only call sites: the production cache was never
    mutated for the affected coordinate; no further work was admitted after
    this point; every already-durable trace record written before this
    failure is untouched; and the run this occurred in is left explicitly
    failed (this exception propagates out of
    :meth:`~src.reference.reference_orchestrator.ReferenceOrchestrator.run`
    rather than being folded into an apparently complete
    :class:`~src.reference.reference_orchestrator.OrchestrationRunSummary`).
    """


@dataclass(frozen=True)
class FreshExecutionAttempt:
    """One evaluator attempt within a fresh-policy key-group execution --
    the orchestration/trace boundary's typed, per-attempt identity that
    H.2C's own future work can propagate into a case-level
    :class:`~src.reference.calibration_schema.CalibrationInvocationRecord`'s
    own ``attempt_id`` (the same "first attempt is 1" convention that field
    already uses).

    Exactly one of ``task_result``/``exception_type_name`` is non-``None``:
    an attempt either produced a typed measurement -- any
    :class:`~src.reference.result_schema.MeasurementStatus`, including a
    non-``VALID`` one -- or failed via a raised exception before producing
    one, never both, never neither. ``exception_type_name`` is allowlisted,
    safe data only (the exception's class name, e.g. ``"RuntimeError"``) --
    never the exception message or traceback, mirroring this module's
    existing convention for describing backend-setup failures.
    """

    attempt_id: int
    task_result: ReferenceTaskResult | None
    exception_type_name: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.attempt_id, int)
            or isinstance(self.attempt_id, bool)
            or self.attempt_id < 1
        ):
            raise ValueError(
                f"attempt_id must be an int >= 1 (first attempt is 1), got {self.attempt_id!r}"
            )
        if (self.task_result is None) == (self.exception_type_name is None):
            raise ValueError(
                "exactly one of task_result/exception_type_name must be set, got "
                f"task_result={self.task_result!r}, "
                f"exception_type_name={self.exception_type_name!r}"
            )


class TraceSink(Protocol):
    """Durable append boundary for one
    :class:`~src.reference.calibration_schema.CalibrationTaskEvaluationRecord`.
    :class:`~src.reference.calibration_trace.CalibrationTraceStore` already
    satisfies this exactly via its own ``append_task_evaluation_record``
    method -- no adapter is required to use it here."""

    def append_task_evaluation_record(self, record: "CalibrationTaskEvaluationRecord") -> None:
        """Durably persist ``record``. Must raise on any failure to
        guarantee durability -- never silently swallow."""


class TaskEvaluationRecordBuilder(Protocol):
    """Builds the :class:`~src.reference.calibration_schema.CalibrationTaskEvaluationRecord`
    for one complete (post-retry) fresh execution attempt.

    ``attempt_records`` is the full ordered attempt history (every retry,
    including any that raised or came back non-``VALID``, each with its own
    ``attempt_id``) -- the source of the ``contributing_invocation_ids``/
    ``contributing_invocation_content_checksums`` a real implementation
    would build one :class:`~src.reference.calibration_schema.CalibrationInvocationRecord`
    per entry for. Only the *terminal eligible* attempt (``task_result``,
    the same final result also carried at top level) may contribute to the
    task's own ``measurement_status``/``q_ref_task`` -- earlier, superseded
    attempts must never be double-counted.

    A pluggable boundary, not a fixed implementation: H.2C supplies the
    production implementation once real controller-side telemetry exists
    (mapping ``work_item``/``evidence`` into a real
    :class:`~src.reference.calibration_schema.CalibrationRunContext`);
    H.2B.1's own tests supply a synthetic one. This module has no opinion
    on how that mapping is done.
    """

    def __call__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        work_item: "WorkItem",
        evidence: ReferenceTaskEvidence,
        task_evaluation_replicate_id: int,
        attempt_records: "tuple[FreshExecutionAttempt, ...]",
        disposition: "WorkItemDisposition",
        task_result: ReferenceTaskResult | None,
    ) -> "CalibrationTaskEvaluationRecord":
        """Build the calibration-trace record summarizing this attempt."""


class TraceRecorder(Protocol):
    """Typed calibration-trace boundary a fresh :class:`CachePolicy`
    requires and ``CACHE_FIRST`` never touches.

    Called once per complete (post-retry) fresh execution, before any
    cache mutation is considered for that attempt -- a caller whose
    ``record_fresh_attempt`` raises causes
    :meth:`~src.reference.reference_orchestrator.ReferenceOrchestrator._record_fresh_attempt`
    to raise :class:`CalibrationTracePersistenceError`, guaranteeing the
    orchestrator never reaches ``ReferenceResultCache.put()`` for that
    attempt (see
    :meth:`~src.reference.reference_orchestrator.ReferenceOrchestrator._accept_valid_result`).
    """

    def record_fresh_attempt(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        work_item: "WorkItem",
        evidence: ReferenceTaskEvidence,
        task_evaluation_replicate_id: int,
        attempt_records: "tuple[FreshExecutionAttempt, ...]",
        disposition: "WorkItemDisposition",
        task_result: ReferenceTaskResult | None,
    ) -> None:
        """Durably persist the calibration trace for this attempt. Must
        raise on any durability failure."""


@dataclass(frozen=True)
class CalibrationTraceRecorder:
    """Production-usable :class:`TraceRecorder`: builds one
    :class:`~src.reference.calibration_schema.CalibrationTaskEvaluationRecord`
    via a pluggable :class:`TaskEvaluationRecordBuilder`, then durably
    appends it through any :class:`TraceSink` (e.g. an already-open
    :class:`~src.reference.calibration_trace.CalibrationTraceStore`).

    H.2C's own future work only needs to supply a new ``build_record``
    implementation (real telemetry) -- neither this class nor the
    orchestrator that calls it need to change.
    """

    build_record: TaskEvaluationRecordBuilder
    sink: TraceSink

    def record_fresh_attempt(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        work_item: "WorkItem",
        evidence: ReferenceTaskEvidence,
        task_evaluation_replicate_id: int,
        attempt_records: "tuple[FreshExecutionAttempt, ...]",
        disposition: "WorkItemDisposition",
        task_result: ReferenceTaskResult | None,
    ) -> None:
        """Build then durably append the calibration-trace record for this
        attempt. Propagates any exception from either step -- the caller
        must never treat a partially-completed build+append as durable."""
        record = self.build_record(
            work_item=work_item,
            evidence=evidence,
            task_evaluation_replicate_id=task_evaluation_replicate_id,
            attempt_records=attempt_records,
            disposition=disposition,
            task_result=task_result,
        )
        self.sink.append_task_evaluation_record(record)
