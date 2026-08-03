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

    A pluggable boundary, not a fixed implementation: H.2C supplies the
    production implementation once real controller-side telemetry exists
    (mapping ``work_item``/``evidence`` into a real
    :class:`~src.reference.calibration_schema.CalibrationRunContext` and
    populating genuine ``contributing_invocation_ids``); H.2B.1's own tests
    supply a synthetic one. This module has no opinion on how that mapping
    is done.
    """

    def __call__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        work_item: "WorkItem",
        evidence: ReferenceTaskEvidence,
        task_evaluation_replicate_id: int,
        attempts: int,
        disposition: "WorkItemDisposition",
        task_result: ReferenceTaskResult | None,
    ) -> "CalibrationTaskEvaluationRecord":
        """Build the calibration-trace record summarizing this attempt."""


class TraceRecorder(Protocol):
    """Typed calibration-trace boundary a fresh :class:`CachePolicy`
    requires and ``CACHE_FIRST`` never touches.

    Called once per complete (post-retry) fresh execution, before any
    cache mutation is considered for that attempt -- a caller whose
    ``record_fresh_attempt`` raises guarantees the orchestrator never
    reaches ``ReferenceResultCache.put()`` for that attempt (see
    :meth:`~src.reference.reference_orchestrator.ReferenceOrchestrator._accept_valid_result`).
    """

    def record_fresh_attempt(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        work_item: "WorkItem",
        evidence: ReferenceTaskEvidence,
        task_evaluation_replicate_id: int,
        attempts: int,
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
        attempts: int,
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
            attempts=attempts,
            disposition=disposition,
            task_result=task_result,
        )
        self.sink.append_task_evaluation_record(record)
