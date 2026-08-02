"""MEGB-03E: privileged serialization and redacted projections for reference
evaluation (S*) results.

Two distinct output paths, matching the privileged-artifact policy
established in MEGB-03B/03C/03D (see
``docs/measurement/privileged-artifact-policy.md``):

* ``*_to_dict``/``*_from_dict``: full-fidelity, privileged round-trip
  serialization (including ``diagnostics``, which may carry oracle-derived
  detail, and task-specific ``candidate_id``/``candidate_sha256``). For
  trusted, privileged storage only — never for development-facing
  consumers. Every serialized payload is stamped with
  ``RESULT_SCHEMA_VERSION``; deserialization checks this explicitly and
  raises :class:`~src.reference.result_schema.UnsupportedResultSchemaVersionError`
  on any mismatch rather than attempting to parse a differently-shaped
  payload under the current field names (Approved Correction, v2).
* ``redact_*``: development-facing projections. Per ticket requirement 13,
  these exclude failing inputs, expected outputs, per-case pass/fail
  vectors, canonical outputs, exception details containing test data, and
  unapproved reference-test counts (``reference_case_total``/
  ``reference_case_pass_count`` — excluded by default, shown only when
  ``include_reference_case_counts=True``). ``diagnostics`` is never
  included at all, under either value of that flag: it is the one field
  free-form enough to accidentally carry any of the above. Task-specific
  ``candidate_id``/``candidate_sha256`` and the full ``context``/
  ``candidate_set_manifest`` are likewise never included in a redacted
  view — only the manifest's own aggregate ``manifest_checksum`` is safe
  to expose (a one-way hash revealing nothing about any individual
  candidate). Task-level classifications, the binary ``q_ref_task``/
  aggregate ``q_ref`` scores, full-suite outcome *labels* and aggregate
  base/plus counts (not per-case vectors), and categorical
  execution-failure tallies are all safe to expose and are included by
  default — this schema has no case-level identifiers anywhere to leak.

``include_reference_case_counts`` is a schema-level presentation option,
not an authorization mechanism: it performs no caller-identity check, and
the two aggregate integers it exposes (``reference_case_total``,
``reference_case_pass_count``) are not themselves privileged artifacts —
they never reveal case content, only how many required cases exist and
how many passed. No production caller of either ``redact_*`` function
exists yet in this repository. Any future ticket that introduces the
first production caller of ``redact_task_result``/``redact_benchmark_result``
must document, at that point, whether and why that consumer enables the
flag.
"""

from typing import Any, Mapping

from src.evaluators.schema import FailureCategory
from src.reference.result_schema import (
    RESULT_SCHEMA_VERSION,
    CandidateSetEntry,
    ReferenceValidationCandidateSetManifest,
    FullSuiteDiagnostic,
    MeasurementStatus,
    ReferenceBenchmarkResult,
    ReferenceOutcome,
    ReferenceRunContext,
    ReferenceTaskResult,
    UnsupportedResultSchemaVersionError,
)


def _require_schema_version(data: Mapping[str, Any], label: str) -> None:
    found = data.get("schema_version")
    if found != RESULT_SCHEMA_VERSION:
        raise UnsupportedResultSchemaVersionError(
            f"{label}: schema_version {found!r} does not match the version this module "
            f"implements ({RESULT_SCHEMA_VERSION!r}); refusing to deserialize rather than "
            f"parse a differently-shaped payload under the current field names"
        )


def run_context_to_dict(context: ReferenceRunContext) -> dict[str, str]:
    """Full-fidelity serialization of a :class:`ReferenceRunContext`."""
    return {
        "experiment_run_id": context.experiment_run_id,
        "optimization_run_id": context.optimization_run_id,
        "optimization_config_sha256": context.optimization_config_sha256,
        "portfolio_frozen_at": context.portfolio_frozen_at,
        "portfolio_selection_rule": context.portfolio_selection_rule,
        "evaluator_version": context.evaluator_version,
        "dataset_version": context.dataset_version,
        "partition_version": context.partition_version,
        "execution_profile_id": context.execution_profile_id,
        "comparison_profile_version": context.comparison_profile_version,
        "execution_protocol_version": context.execution_protocol_version,
        "dataset_checksum": context.dataset_checksum,
        "task_manifest_checksum": context.task_manifest_checksum,
    }


def run_context_from_dict(data: Mapping[str, Any]) -> ReferenceRunContext:
    """Inverse of :func:`run_context_to_dict`."""
    return ReferenceRunContext(
        experiment_run_id=data["experiment_run_id"],
        optimization_run_id=data["optimization_run_id"],
        optimization_config_sha256=data["optimization_config_sha256"],
        portfolio_frozen_at=data["portfolio_frozen_at"],
        portfolio_selection_rule=data["portfolio_selection_rule"],
        evaluator_version=data["evaluator_version"],
        dataset_version=data["dataset_version"],
        partition_version=data["partition_version"],
        execution_profile_id=data["execution_profile_id"],
        comparison_profile_version=data["comparison_profile_version"],
        execution_protocol_version=data["execution_protocol_version"],
        dataset_checksum=data["dataset_checksum"],
        task_manifest_checksum=data["task_manifest_checksum"],
    )


def full_suite_diagnostic_to_dict(diagnostic: FullSuiteDiagnostic) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`FullSuiteDiagnostic`."""
    return {
        "outcome": diagnostic.outcome.value,
        "base_total": diagnostic.base_total,
        "base_pass_count": diagnostic.base_pass_count,
        "plus_total": diagnostic.plus_total,
        "plus_pass_count": diagnostic.plus_pass_count,
    }


def full_suite_diagnostic_from_dict(data: Mapping[str, Any]) -> FullSuiteDiagnostic:
    """Inverse of :func:`full_suite_diagnostic_to_dict`."""
    return FullSuiteDiagnostic(
        outcome=ReferenceOutcome(data["outcome"]),
        base_total=data["base_total"],
        base_pass_count=data["base_pass_count"],
        plus_total=data["plus_total"],
        plus_pass_count=data["plus_pass_count"],
    )


def candidate_set_entry_to_dict(entry: CandidateSetEntry) -> dict[str, str]:
    """Full-fidelity serialization of a :class:`CandidateSetEntry`."""
    return {
        "task_id": entry.task_id,
        "candidate_id": entry.candidate_id,
        "candidate_sha256": entry.candidate_sha256,
    }


def candidate_set_entry_from_dict(data: Mapping[str, Any]) -> CandidateSetEntry:
    """Inverse of :func:`candidate_set_entry_to_dict`."""
    return CandidateSetEntry(
        task_id=data["task_id"],
        candidate_id=data["candidate_id"],
        candidate_sha256=data["candidate_sha256"],
    )


def candidate_set_manifest_to_dict(
    manifest: ReferenceValidationCandidateSetManifest,
) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`ReferenceValidationCandidateSetManifest`."""
    return {
        "manifest_schema_version": manifest.manifest_schema_version,
        "algorithm_version": manifest.algorithm_version,
        "task_manifest_id": manifest.task_manifest_id,
        "task_manifest_checksum": manifest.task_manifest_checksum,
        "selection_provenance_sha256": manifest.selection_provenance_sha256,
        "entries": [candidate_set_entry_to_dict(entry) for entry in manifest.entries],
        "expected_task_count": manifest.expected_task_count,
        "manifest_checksum": manifest.manifest_checksum,
    }


def candidate_set_manifest_from_dict(
    data: Mapping[str, Any],
) -> ReferenceValidationCandidateSetManifest:
    """Inverse of :func:`candidate_set_manifest_to_dict`.

    Reconstructs through :class:`ReferenceValidationCandidateSetManifest`'s own constructor,
    passing the stored ``manifest_checksum`` through as the "expected"
    value — the constructor always recomputes the checksum from the loaded
    entries and rejects a mismatch, so any tampering with the persisted
    payload (a reordered, duplicated, or hand-edited entry) is caught by
    the act of deserializing it, with no separate verify step needed.
    """
    return ReferenceValidationCandidateSetManifest(
        manifest_schema_version=data["manifest_schema_version"],
        algorithm_version=data["algorithm_version"],
        task_manifest_id=data["task_manifest_id"],
        task_manifest_checksum=data["task_manifest_checksum"],
        selection_provenance_sha256=data["selection_provenance_sha256"],
        entries=tuple(candidate_set_entry_from_dict(item) for item in data["entries"]),
        expected_task_count=data["expected_task_count"],
        manifest_checksum=data["manifest_checksum"],
    )


def task_result_to_dict(result: ReferenceTaskResult) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`ReferenceTaskResult`, including
    ``diagnostics`` and task-specific candidate identity. Privileged: never
    send this to a development-facing consumer."""
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "task_id": result.task_id,
        "candidate_id": result.candidate_id,
        "candidate_sha256": result.candidate_sha256,
        "context": run_context_to_dict(result.context),
        "status": result.status.value,
        "q_ref_task": result.q_ref_task,
        "reference_case_total": result.reference_case_total,
        "reference_case_pass_count": result.reference_case_pass_count,
        "first_failure_category": result.first_failure_category.value,
        "oracle_version": result.oracle_version,
        "reference_case_checksum": result.reference_case_checksum,
        "evaluated_at": result.evaluated_at,
        "duration_seconds": result.duration_seconds,
        "execution_failure_counts": dict(result.execution_failure_counts),
        "full_suite_diagnostic": (
            full_suite_diagnostic_to_dict(result.full_suite_diagnostic)
            if result.full_suite_diagnostic is not None
            else None
        ),
        "diagnostics": dict(result.diagnostics),
    }


def task_result_from_dict(data: Mapping[str, Any]) -> ReferenceTaskResult:
    """Inverse of :func:`task_result_to_dict`."""
    _require_schema_version(data, "task_result")
    full_suite_diagnostic = data.get("full_suite_diagnostic")
    return ReferenceTaskResult(
        task_id=data["task_id"],
        candidate_id=data["candidate_id"],
        candidate_sha256=data["candidate_sha256"],
        context=run_context_from_dict(data["context"]),
        status=MeasurementStatus(data["status"]),
        q_ref_task=data["q_ref_task"],
        reference_case_total=data["reference_case_total"],
        reference_case_pass_count=data["reference_case_pass_count"],
        first_failure_category=FailureCategory(data["first_failure_category"]),
        oracle_version=data["oracle_version"],
        reference_case_checksum=data["reference_case_checksum"],
        evaluated_at=data["evaluated_at"],
        duration_seconds=data["duration_seconds"],
        execution_failure_counts=dict(data.get("execution_failure_counts", {})),
        full_suite_diagnostic=(
            full_suite_diagnostic_from_dict(full_suite_diagnostic)
            if full_suite_diagnostic is not None
            else None
        ),
        diagnostics=dict(data.get("diagnostics", {})),
    )


def benchmark_result_to_dict(benchmark: ReferenceBenchmarkResult) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`ReferenceBenchmarkResult`,
    including the full :class:`ReferenceValidationCandidateSetManifest`. Privileged: never
    send this to a development-facing consumer."""
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "run_context": run_context_to_dict(benchmark.run_context),
        "candidate_set_manifest": candidate_set_manifest_to_dict(benchmark.candidate_set_manifest),
        "task_results": [task_result_to_dict(result) for result in benchmark.task_results],
        "task_manifest_checksum": benchmark.task_manifest_checksum,
        "oracle_version": benchmark.oracle_version,
        "evaluated_at": benchmark.evaluated_at,
        "duration_seconds": benchmark.duration_seconds,
        "expected_task_count": benchmark.expected_task_count,
    }


def benchmark_result_from_dict(data: Mapping[str, Any]) -> ReferenceBenchmarkResult:
    """Inverse of :func:`benchmark_result_to_dict`."""
    _require_schema_version(data, "benchmark_result")
    return ReferenceBenchmarkResult(
        run_context=run_context_from_dict(data["run_context"]),
        candidate_set_manifest=candidate_set_manifest_from_dict(data["candidate_set_manifest"]),
        task_results=tuple(task_result_from_dict(item) for item in data["task_results"]),
        task_manifest_checksum=data["task_manifest_checksum"],
        oracle_version=data["oracle_version"],
        evaluated_at=data["evaluated_at"],
        duration_seconds=data["duration_seconds"],
        expected_task_count=data["expected_task_count"],
    )


def redact_task_result(
    result: ReferenceTaskResult, *, include_reference_case_counts: bool = False
) -> dict[str, Any]:
    """Development-facing projection of one task's reference result.

    Excludes ``diagnostics``, the full ``context``, and this task's own
    ``candidate_id``/``candidate_sha256`` always — task-specific candidate
    identity remains redacted regardless of ``include_reference_case_counts``
    — and excludes ``reference_case_total``/``reference_case_pass_count``
    (the "unapproved reference-test counts" of requirement 13) unless the
    caller explicitly opts in.
    """
    redacted: dict[str, Any] = {
        "task_id": result.task_id,
        "status": result.status.value,
        "q_ref_task": result.q_ref_task,
        "first_failure_category": result.first_failure_category.value,
        "oracle_version": result.oracle_version,
        "evaluated_at": result.evaluated_at,
        "duration_seconds": result.duration_seconds,
        "execution_failure_counts": dict(result.execution_failure_counts),
        "full_suite_diagnostic": (
            full_suite_diagnostic_to_dict(result.full_suite_diagnostic)
            if result.full_suite_diagnostic is not None
            else None
        ),
    }
    if include_reference_case_counts:
        redacted["reference_case_total"] = result.reference_case_total
        redacted["reference_case_pass_count"] = result.reference_case_pass_count
    return redacted


def redact_benchmark_result(
    benchmark: ReferenceBenchmarkResult, *, include_reference_case_counts: bool = False
) -> dict[str, Any]:
    """Development-facing projection of an aggregate reference benchmark result.

    Exposes only run identifiers, aggregate scores, and the candidate-set
    manifest's own aggregate checksum (a one-way hash revealing nothing
    about any individual candidate) — never per-task candidate identity,
    the full candidate-set manifest, canonical solutions, oracle expected
    outputs, case-level identifiers, or any other privileged manifest.
    """
    status_counts = {status.value: count for status, count in benchmark.status_counts.items()}
    full_suite_outcome_counts = {
        outcome.value: count for outcome, count in benchmark.full_suite_outcome_counts.items()
    }
    return {
        "experiment_run_id": benchmark.run_context.experiment_run_id,
        "optimization_run_id": benchmark.run_context.optimization_run_id,
        "evaluator_version": benchmark.run_context.evaluator_version,
        "comparison_profile_version": benchmark.run_context.comparison_profile_version,
        "execution_protocol_version": benchmark.run_context.execution_protocol_version,
        "dataset_checksum": benchmark.run_context.dataset_checksum,
        "oracle_version": benchmark.oracle_version,
        "task_manifest_checksum": benchmark.task_manifest_checksum,
        "candidate_set_manifest_checksum": benchmark.candidate_set_manifest.manifest_checksum,
        "expected_task_count": benchmark.expected_task_count,
        "evaluated_task_count": benchmark.evaluated_task_count,
        "valid_task_count": benchmark.valid_task_count,
        "invalid_task_count": benchmark.invalid_task_count,
        "incomplete_task_count": benchmark.incomplete_task_count,
        "missing_task_count": benchmark.missing_task_count,
        "primary_pass_count": benchmark.primary_pass_count,
        "status_counts": status_counts,
        "full_suite_outcome_counts": full_suite_outcome_counts,
        "aggregate_status": benchmark.aggregate_status.value,
        "q_ref": benchmark.q_ref,
        "evaluated_at": benchmark.evaluated_at,
        "duration_seconds": benchmark.duration_seconds,
        "task_results": [
            redact_task_result(result, include_reference_case_counts=include_reference_case_counts)
            for result in benchmark.task_results
        ],
    }
