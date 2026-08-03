"""MEGB-03G.2: the safe, append-only audit-record schema for reference
(S*) invocations.

Implements original MEGB-03G requirement 9's audit-record schema (caller;
experiment/optimization run IDs; candidate ID and hash; freeze metadata and
selection rule; evaluator/dataset/partition/oracle/execution versions;
invocation timestamp; result-artifact location; final measurement status),
extended per the "Approved MEGB-03G.2-G.5 Scope Amendment" to also carry
cache disposition and duration.

Uses an explicit field allowlist (:data:`AUDIT_RECORD_FIELD_NAMES`, tested
against ``dataclasses.fields(ReferenceAuditRecord)`` in
``tests/test_reference_audit.py``) rather than a free-form mapping: this
schema structurally cannot carry candidate code, case inputs, case
identifiers, expected outputs, canonical solutions,
:class:`~src.reference.reference_evaluator.PrivilegedCaseDiagnostic`
objects, exception payloads/tracebacks, or free-form diagnostics, because
none of those has a field here at all. ``result_artifact_location`` is a
cache-key digest or path pointer only -- never privileged content, and
never a path that itself reveals case identity (the digest is derived from
version/checksum fields, not from raw case IDs or inputs).

This is a distinct, safe artifact from the privileged
:class:`~src.reference.reference_cache.ReferenceResultCache`: the audit log
is intended to be committable in principle (no case content, no candidate
source, no oracle-derived data), unlike the cache, which is always
privileged. Neither ever stores
:class:`~src.reference.reference_evaluator.PrivilegedCaseDiagnostic`
records -- persisting those, if ever needed, is an explicit later decision
left to a future subtask, per this amendment.

``ReferenceAuditRecord`` intentionally repeats a handful of
``ReferenceRunContext``'s field declarations (``portfolio_frozen_at``,
``portfolio_selection_rule``, ``evaluator_version``, ``dataset_version``,
``partition_version``) verbatim, by name and type, rather than embedding or
subclassing ``ReferenceRunContext`` itself: this record must stay a flat,
independently-serializable, privileged-content-free schema, and composing
the full context would either pull in fields this schema must not carry or
require modifying the already-accepted ``ReferenceRunContext`` -- out of
scope for this checkpoint. The resulting field-declaration overlap is
expected and accepted, not a defect.

**Resolved (v2 audit-record schema, post-MEGB-03G.2 cache-provenance
audit):** adds ``execution_protocol_version``, ``dataset_checksum``, and
``task_manifest_checksum`` -- the same three safe identity/checksum fields
the ``result_schema`` v4 correction added to ``ReferenceRunContext`` --
so an audit record can be reconciled against the cache/result identity it
accompanies without needing to inspect the privileged result itself.
``AUDIT_RECORD_SCHEMA_VERSION`` moves from ``reference-audit-record-v1`` to
``reference-audit-record-v2`` accordingly.

**Resolved (v3 audit-record schema, MEGB-03H.2B.1 trace-coverage/audit-
schema correction):** ``cache_disposition`` may now legally carry
``CacheDisposition.BYPASSED_BY_POLICY``, recorded whenever a fresh
:class:`~src.reference.orchestration_trace.CachePolicy` bypasses the cache
read and/or write entirely -- previously misrecorded as ``MISS``, which
means "a real lookup found nothing" and is factually wrong for a
deliberate bypass. Although ``cache_disposition``'s own validation
(``{member.value for member in CacheDisposition}``) is already computed
dynamically against the current enum, adding a new legal value is still a
schema-semantic expansion of what this versioned, persisted record type
may contain, not merely an implementation detail -- so the version moves
regardless, matching the v1-to-v2 precedent above. No field was added or
removed. A real, locally-persisted (gitignored, non-privileged, explicitly
"generated local operational log" per this module's own docstring)
``reference-audit-record-v2`` artifact exists on disk from the MEGB-03G.4
benchmark run (``artifacts/reference/g4_benchmark_audit/g4_benchmark_audit_log.jsonl``,
66 records, none using the new value); this move makes it stale exactly as
the v1-to-v2 move already established no migration path is provided --
regenerable by rerunning the G.4 benchmark, not lost data.
``AUDIT_RECORD_SCHEMA_VERSION`` moves from ``reference-audit-record-v2`` to
``reference-audit-record-v3`` accordingly.
"""

# See the note above: the field-declaration overlap with
# ReferenceRunContext is intentional and does not indicate shared logic
# that should be refactored -- suppressing here rather than coupling this
# record's schema to ReferenceRunContext's or modifying the latter's
# already-accepted definition.
# pylint: disable=duplicate-code

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.reference.reference_cache import CacheDisposition
from src.reference.result_schema import MeasurementStatus, ReferenceRunContext, ReferenceTaskResult

AUDIT_RECORD_SCHEMA_VERSION = "reference-audit-record-v3"

DEFAULT_AUDIT_LOG_PATH = Path("artifacts/reference/audit/reference_audit_log.jsonl")


class InvalidAuditRecordError(ValueError):
    """Raised when a :class:`ReferenceAuditRecord`'s fields are internally
    inconsistent (e.g. an empty required identity field)."""


def _require_nonempty_str(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or value == "":
        raise InvalidAuditRecordError(f"{field_name!r} must be a nonempty string, got {value!r}")


@dataclass(frozen=True)
class ReferenceAuditRecord:
    """One append-only audit entry for a single reference-evaluation
    (S*) invocation or cache consultation.

    Every field is a safe identity/version/status/timing value. There is no
    field capable of carrying case content, candidate source, or
    privileged diagnostics -- see the module docstring.
    """

    audit_schema_version: str
    caller: str
    experiment_run_id: str
    optimization_run_id: str
    candidate_id: str
    candidate_sha256: str
    portfolio_frozen_at: str
    portfolio_selection_rule: str
    evaluator_version: str
    dataset_version: str
    partition_version: str
    oracle_version: str
    execution_profile_id: str
    comparison_profile_version: str
    execution_protocol_version: str
    dataset_checksum: str
    task_manifest_checksum: str
    reference_case_checksum: str
    task_id: str
    invocation_id: str
    invoked_at: str
    duration_seconds: float
    cache_disposition: str
    status: str
    result_artifact_location: str

    def __post_init__(self) -> None:
        for field_name in (
            "audit_schema_version",
            "caller",
            "experiment_run_id",
            "optimization_run_id",
            "candidate_id",
            "candidate_sha256",
            "portfolio_frozen_at",
            "portfolio_selection_rule",
            "evaluator_version",
            "dataset_version",
            "partition_version",
            "oracle_version",
            "execution_profile_id",
            "comparison_profile_version",
            "execution_protocol_version",
            "dataset_checksum",
            "task_manifest_checksum",
            "reference_case_checksum",
            "task_id",
            "invocation_id",
            "invoked_at",
            "cache_disposition",
            "status",
            "result_artifact_location",
        ):
            _require_nonempty_str(self, field_name)
        if self.audit_schema_version != AUDIT_RECORD_SCHEMA_VERSION:
            raise InvalidAuditRecordError(
                f"audit_schema_version {self.audit_schema_version!r} does not match "
                f"the version this module implements ({AUDIT_RECORD_SCHEMA_VERSION!r})"
            )
        if self.cache_disposition not in {member.value for member in CacheDisposition}:
            raise InvalidAuditRecordError(
                f"cache_disposition {self.cache_disposition!r} is not a known "
                f"CacheDisposition value"
            )
        if self.status not in {member.value for member in MeasurementStatus}:
            raise InvalidAuditRecordError(
                f"status {self.status!r} is not a known MeasurementStatus value"
            )
        if not isinstance(self.duration_seconds, (int, float)) or isinstance(
            self.duration_seconds, bool
        ) or self.duration_seconds < 0:
            raise InvalidAuditRecordError(
                f"duration_seconds must be a non-negative number, got {self.duration_seconds!r}"
            )


AUDIT_RECORD_FIELD_NAMES = frozenset(
    field.name for field in dataclasses.fields(ReferenceAuditRecord)
)


def build_audit_record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    caller: str,
    run_context: ReferenceRunContext,
    task_result: ReferenceTaskResult,
    cache_disposition: CacheDisposition,
    invocation_id: str,
    invoked_at: str,
    result_artifact_location: str,
) -> ReferenceAuditRecord:
    """Build the audit record for one reference-evaluation invocation or
    cache consultation.

    Derives every field from ``run_context``/``task_result`` themselves
    (never from ``task_result.diagnostics`` or any per-case detail) plus the
    caller-supplied invocation metadata. ``result_artifact_location`` must
    be a safe pointer only -- e.g. a cache-key digest or the cache entry's
    relative path -- never privileged content and never anything that
    reveals case identity (case IDs/inputs are not part of the cache key
    and therefore cannot appear in a location derived from it).
    """
    return ReferenceAuditRecord(
        audit_schema_version=AUDIT_RECORD_SCHEMA_VERSION,
        caller=caller,
        experiment_run_id=run_context.experiment_run_id,
        optimization_run_id=run_context.optimization_run_id,
        candidate_id=task_result.candidate_id,
        candidate_sha256=task_result.candidate_sha256,
        portfolio_frozen_at=run_context.portfolio_frozen_at,
        portfolio_selection_rule=run_context.portfolio_selection_rule,
        evaluator_version=run_context.evaluator_version,
        dataset_version=run_context.dataset_version,
        partition_version=run_context.partition_version,
        oracle_version=task_result.oracle_version,
        execution_profile_id=run_context.execution_profile_id,
        comparison_profile_version=run_context.comparison_profile_version,
        execution_protocol_version=run_context.execution_protocol_version,
        dataset_checksum=run_context.dataset_checksum,
        task_manifest_checksum=run_context.task_manifest_checksum,
        reference_case_checksum=task_result.reference_case_checksum,
        task_id=task_result.task_id,
        invocation_id=invocation_id,
        invoked_at=invoked_at,
        duration_seconds=task_result.duration_seconds,
        cache_disposition=cache_disposition.value,
        status=task_result.status.value,
        result_artifact_location=result_artifact_location,
    )


def audit_record_to_dict(record: ReferenceAuditRecord) -> dict[str, Any]:
    """Serialize an audit record. Output keys are exactly
    :data:`AUDIT_RECORD_FIELD_NAMES` -- nothing more, nothing less."""
    return dataclasses.asdict(record)


def audit_record_from_dict(data: Mapping[str, Any]) -> ReferenceAuditRecord:
    """Inverse of :func:`audit_record_to_dict`."""
    return ReferenceAuditRecord(**{name: data[name] for name in AUDIT_RECORD_FIELD_NAMES})


class ReferenceAuditLog:
    """Append-only JSONL audit log.

    Each :meth:`append` call adds exactly one line; nothing is ever
    rewritten or removed. Safe to commit in principle -- see the module
    docstring for why this schema carries no privileged content --
    though not committed by default in practice (see
    ``docs/measurement/privileged-artifact-policy.md``'s "MEGB-03G"
    section: treated as a generated local operational log, mirroring
    ``g4_benchmark_audit/``). ``ReferenceOrchestrator`` (MEGB-03G.3,
    accepted) is the production caller, appending one record per
    invocation attempt via its own ``_append_audit`` method regardless of
    disposition (cache hit, miss, fresh execution, retry).
    """

    def __init__(self, path: Path | None = None) -> None:
        """Open (creating the parent directory if needed) the audit log at
        ``path``, or :data:`DEFAULT_AUDIT_LOG_PATH` if omitted."""
        self._path = path if path is not None else DEFAULT_AUDIT_LOG_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        """The JSONL file this log appends to."""
        return self._path

    def append(self, record: ReferenceAuditRecord) -> None:
        """Append ``record`` as one new line. Never rewrites or removes an
        existing line."""
        line = json.dumps(audit_record_to_dict(record), sort_keys=True)
        with open(self._path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def read_all(self) -> tuple[ReferenceAuditRecord, ...]:
        """Read every record, in append order. Empty if the log doesn't
        exist yet."""
        if not self._path.exists():
            return ()
        lines = self._path.read_text(encoding="utf-8").splitlines()
        return tuple(
            audit_record_from_dict(json.loads(line)) for line in lines if line.strip()
        )
