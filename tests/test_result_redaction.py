"""Tests for src.reference.result_redaction (MEGB-03E/03F Approved Correction, v2).

Covers the ticket's "serialization round trips" and "public-result
redaction and feedback-leakage" required-test categories, plus the v2
correction's own required coverage: task-specific candidate identity stays
redacted, the candidate-set manifest and its checksum round-trip and
re-verify on reload, and a schema-version mismatch on deserialize fails
explicitly rather than silently misparsing.
"""

# This file's fixture helpers necessarily mirror test_result_schema.py's own
# (both build well-formed ReferenceTaskResult/CandidateSetManifest objects
# from the same required fields); introducing a shared conftest fixture for
# this isn't warranted in this narrowly scoped subtask.
# pylint: disable=duplicate-code

import dataclasses

import pytest

from src.evaluators.schema import FailureCategory
from src.reference.result_redaction import (
    benchmark_result_from_dict,
    benchmark_result_to_dict,
    candidate_set_entry_from_dict,
    candidate_set_entry_to_dict,
    candidate_set_manifest_from_dict,
    candidate_set_manifest_to_dict,
    full_suite_diagnostic_from_dict,
    full_suite_diagnostic_to_dict,
    redact_benchmark_result,
    redact_task_result,
    run_context_from_dict,
    run_context_to_dict,
    task_result_from_dict,
    task_result_to_dict,
)
from src.reference.result_schema import (
    CANDIDATE_SET_ALGORITHM_VERSION,
    CANDIDATE_SET_MANIFEST_SCHEMA_VERSION,
    REQUIRED_TASK_COUNT,
    RESULT_SCHEMA_VERSION,
    CandidateSetEntry,
    CandidateSetManifest,
    FullSuiteDiagnostic,
    InvalidCandidateSetManifestError,
    MeasurementStatus,
    ReferenceBenchmarkResult,
    ReferenceOutcome,
    ReferenceRunContext,
    ReferenceTaskResult,
    UnsupportedResultSchemaVersionError,
)

_SHA_B = "b" * 64
_SHA_CASE = "c" * 64
_SHA_MANIFEST = "d" * 64
_SHA_SELECTION_PROVENANCE = "e" * 64
_ORACLE_VERSION = "oracle-v1"

_CANDIDATE_ID = "cand-HumanEval/39"
_CANDIDATE_SHA256 = "1" * 64


def _run_context() -> ReferenceRunContext:
    return ReferenceRunContext(
        experiment_run_id="exp-1",
        optimization_run_id="opt-1",
        optimization_config_sha256=_SHA_B,
        portfolio_frozen_at="2026-07-01T00:00:00Z",
        portfolio_selection_rule="best_of_run",
        evaluator_version="reference-evaluator-v1",
        dataset_version="humaneval-plus-v0.1.10",
        partition_version="partition-v1",
        execution_profile_id="docker-megb02-v1",
    )


def _task_result_with_diagnostics() -> ReferenceTaskResult:
    return ReferenceTaskResult(
        task_id="HumanEval/39",
        candidate_id=_CANDIDATE_ID,
        candidate_sha256=_CANDIDATE_SHA256,
        context=_run_context(),
        status=MeasurementStatus.VALID,
        q_ref_task=0.0,
        reference_case_total=12,
        reference_case_pass_count=9,
        first_failure_category=FailureCategory.WRONG_OUTPUT,
        oracle_version=_ORACLE_VERSION,
        reference_case_checksum=_SHA_CASE,
        evaluated_at="2026-07-01T00:00:01Z",
        duration_seconds=0.42,
        execution_failure_counts={FailureCategory.WRONG_OUTPUT.value: 3},
        full_suite_diagnostic=FullSuiteDiagnostic(
            outcome=ReferenceOutcome.PASS_BASE_FAIL_PLUS,
            base_total=1,
            base_pass_count=1,
            plus_total=10,
            plus_pass_count=6,
        ),
        diagnostics={
            "expected_output": "this must never be redacted-exposed",
            "canonical_solution": "def prime_fib(n): ...",
            "raw_stderr": "Traceback ...",
        },
    )


def _minimal_pass_task_result() -> ReferenceTaskResult:
    return ReferenceTaskResult(
        task_id="HumanEval/0",
        candidate_id="cand-HumanEval/0",
        candidate_sha256="2" * 64,
        context=_run_context(),
        status=MeasurementStatus.VALID,
        q_ref_task=1.0,
        reference_case_total=5,
        reference_case_pass_count=5,
        first_failure_category=FailureCategory.NONE,
        oracle_version=_ORACLE_VERSION,
        reference_case_checksum=_SHA_CASE,
        evaluated_at="2026-07-01T00:00:01Z",
        duration_seconds=0.1,
    )


def _candidate_set_manifest_for(*results: ReferenceTaskResult) -> CandidateSetManifest:
    """A minimal candidate-set manifest binding exactly ``results``' own
    (task_id, candidate_id, candidate_sha256) plus filler entries for the
    remaining required tasks, so ``ReferenceBenchmarkResult`` construction
    (which always requires a full 164-entry manifest) succeeds."""
    entries = [
        CandidateSetEntry(
            task_id=result.task_id,
            candidate_id=result.candidate_id,
            candidate_sha256=result.candidate_sha256,
        )
        for result in results
    ]
    used_task_ids = {entry.task_id for entry in entries}
    filler_index = 0
    while len(entries) < REQUIRED_TASK_COUNT:
        task_id = f"Filler/{filler_index}"
        filler_index += 1
        if task_id in used_task_ids:
            continue
        entries.append(
            CandidateSetEntry(
                task_id=task_id,
                candidate_id=f"cand-{task_id}",
                candidate_sha256="3" * 64,
            )
        )
    entries.sort(key=lambda entry: entry.task_id)
    return CandidateSetManifest(
        manifest_schema_version=CANDIDATE_SET_MANIFEST_SCHEMA_VERSION,
        algorithm_version=CANDIDATE_SET_ALGORITHM_VERSION,
        task_manifest_id="reference-validation-composite-manifest",
        task_manifest_checksum=_SHA_MANIFEST,
        selection_provenance_sha256=_SHA_SELECTION_PROVENANCE,
        entries=tuple(entries),
    )


def test_run_context_round_trip_preserves_all_fields() -> None:
    """run_context_from_dict(run_context_to_dict(x)) == x."""
    context = _run_context()
    assert run_context_from_dict(run_context_to_dict(context)) == context


def test_full_suite_diagnostic_round_trip() -> None:
    """full_suite_diagnostic_from_dict(full_suite_diagnostic_to_dict(x)) == x."""
    diagnostic = FullSuiteDiagnostic(
        outcome=ReferenceOutcome.PASS_BASE_FAIL_PLUS,
        base_total=1,
        base_pass_count=1,
        plus_total=10,
        plus_pass_count=6,
    )
    assert full_suite_diagnostic_from_dict(full_suite_diagnostic_to_dict(diagnostic)) == diagnostic


def test_candidate_set_entry_round_trip() -> None:
    """candidate_set_entry_from_dict(candidate_set_entry_to_dict(x)) == x."""
    entry = CandidateSetEntry(
        task_id="HumanEval/0", candidate_id="cand-1", candidate_sha256="4" * 64
    )
    assert candidate_set_entry_from_dict(candidate_set_entry_to_dict(entry)) == entry


def test_candidate_set_manifest_round_trip() -> None:
    """candidate_set_manifest_from_dict(candidate_set_manifest_to_dict(x)) == x."""
    manifest = _candidate_set_manifest_for(_minimal_pass_task_result())
    restored = candidate_set_manifest_from_dict(candidate_set_manifest_to_dict(manifest))
    assert restored == manifest


def test_candidate_set_manifest_reload_detects_tampering() -> None:
    """Reloading a manifest whose persisted entries were hand-edited (with a
    stale checksum) is rejected — the checksum is always recomputed on
    reconstruction, so tampering is caught by the act of deserializing."""
    manifest = _candidate_set_manifest_for(_minimal_pass_task_result())
    payload = candidate_set_manifest_to_dict(manifest)
    tampered_entry = dict(payload["entries"][0])
    tampered_entry["candidate_sha256"] = "9" * 64
    payload["entries"] = [tampered_entry] + list(payload["entries"][1:])
    with pytest.raises(InvalidCandidateSetManifestError):
        candidate_set_manifest_from_dict(payload)


def test_task_result_round_trip_preserves_diagnostics_and_candidate_identity() -> None:
    """Privileged serialization round-trips diagnostics and candidate identity exactly."""
    result = _task_result_with_diagnostics()
    restored = task_result_from_dict(task_result_to_dict(result))
    assert restored == result
    assert restored.diagnostics["expected_output"] == "this must never be redacted-exposed"
    assert restored.candidate_id == _CANDIDATE_ID
    assert restored.candidate_sha256 == _CANDIDATE_SHA256


def test_task_result_round_trip_with_none_full_suite_diagnostic() -> None:
    """A None full_suite_diagnostic round-trips as None, not a placeholder."""
    result = _minimal_pass_task_result()
    restored = task_result_from_dict(task_result_to_dict(result))
    assert restored.full_suite_diagnostic is None


def test_task_result_to_dict_stamps_schema_version() -> None:
    """Every serialized task result is stamped with the current schema version."""
    payload = task_result_to_dict(_minimal_pass_task_result())
    assert payload["schema_version"] == RESULT_SCHEMA_VERSION


def test_task_result_from_dict_rejects_wrong_schema_version() -> None:
    """A payload stamped with a different schema_version is rejected explicitly,
    never silently parsed under the current field names."""
    payload = task_result_to_dict(_minimal_pass_task_result())
    payload["schema_version"] = "reference-result-schema-v1"
    with pytest.raises(UnsupportedResultSchemaVersionError):
        task_result_from_dict(payload)


def test_benchmark_result_round_trip_preserves_task_results_and_manifest() -> None:
    """Privileged benchmark serialization round-trips every nested task
    result and the full candidate-set manifest."""
    result = _task_result_with_diagnostics()
    manifest = _candidate_set_manifest_for(result)
    benchmark = ReferenceBenchmarkResult(
        run_context=_run_context(),
        candidate_set_manifest=manifest,
        task_results=(result,),
        task_manifest_checksum=_SHA_MANIFEST,
        oracle_version=_ORACLE_VERSION,
        evaluated_at="2026-07-01T00:00:02Z",
        duration_seconds=1.5,
    )
    restored = benchmark_result_from_dict(benchmark_result_to_dict(benchmark))
    assert restored == benchmark


def test_benchmark_result_from_dict_rejects_wrong_schema_version() -> None:
    """A benchmark payload stamped with a different schema_version is rejected explicitly."""
    result = _task_result_with_diagnostics()
    manifest = _candidate_set_manifest_for(result)
    benchmark = ReferenceBenchmarkResult(
        run_context=_run_context(),
        candidate_set_manifest=manifest,
        task_results=(result,),
        task_manifest_checksum=_SHA_MANIFEST,
        oracle_version=_ORACLE_VERSION,
        evaluated_at="2026-07-01T00:00:02Z",
        duration_seconds=1.5,
    )
    payload = benchmark_result_to_dict(benchmark)
    payload["schema_version"] = "reference-result-schema-v1"
    with pytest.raises(UnsupportedResultSchemaVersionError):
        benchmark_result_from_dict(payload)


def test_redact_task_result_default_excludes_diagnostics_entirely() -> None:
    """The redacted view never includes the diagnostics mapping or its contents."""
    redacted = redact_task_result(_task_result_with_diagnostics())
    assert "diagnostics" not in redacted
    assert "expected_output" not in redacted
    assert "canonical_solution" not in redacted
    assert "raw_stderr" not in redacted


def test_redact_task_result_default_excludes_reference_case_counts() -> None:
    """The unapproved reference-test counts (requirement 13) are excluded by default."""
    redacted = redact_task_result(_task_result_with_diagnostics())
    assert "reference_case_total" not in redacted
    assert "reference_case_pass_count" not in redacted


def test_redact_task_result_always_excludes_candidate_identity_and_context() -> None:
    """Task-specific candidate identity (candidate_id/candidate_sha256) and the
    full run context are never included in the redacted view, under either
    value of include_reference_case_counts."""
    for include_counts in (False, True):
        redacted = redact_task_result(
            _task_result_with_diagnostics(), include_reference_case_counts=include_counts
        )
        assert "context" not in redacted
        assert "candidate_id" not in redacted
        assert "candidate_sha256" not in redacted


def test_redact_task_result_includes_task_level_classification_fields() -> None:
    """The redacted view includes task-level classifications and safe aggregate counts."""
    redacted = redact_task_result(_task_result_with_diagnostics())
    assert redacted["task_id"] == "HumanEval/39"
    assert redacted["status"] == "VALID"
    assert redacted["q_ref_task"] == 0.0
    assert redacted["first_failure_category"] == "WRONG_OUTPUT"
    assert redacted["full_suite_diagnostic"]["outcome"] == "PASS_BASE_FAIL_PLUS"
    assert redacted["execution_failure_counts"][FailureCategory.WRONG_OUTPUT.value] == 3


def test_redact_task_result_opt_in_exposes_reference_case_counts() -> None:
    """include_reference_case_counts=True exposes only the totals, nothing else."""
    redacted = redact_task_result(
        _task_result_with_diagnostics(), include_reference_case_counts=True
    )
    assert redacted["reference_case_total"] == 12
    assert redacted["reference_case_pass_count"] == 9
    assert "expected_output" not in redacted
    assert "canonical_solution" not in redacted
    assert "raw_stderr" not in redacted
    assert "candidate_sha256" not in redacted


def test_redact_benchmark_result_excludes_candidate_identity_and_manifest() -> None:
    """The redacted benchmark view never exposes any candidate_sha256/candidate_id,
    diagnostics, or the full candidate-set manifest — only its aggregate checksum."""
    result = _task_result_with_diagnostics()
    manifest = _candidate_set_manifest_for(result)
    benchmark = ReferenceBenchmarkResult(
        run_context=_run_context(),
        candidate_set_manifest=manifest,
        task_results=(result,),
        task_manifest_checksum=_SHA_MANIFEST,
        oracle_version=_ORACLE_VERSION,
        evaluated_at="2026-07-01T00:00:02Z",
        duration_seconds=1.5,
    )
    redacted = redact_benchmark_result(benchmark)
    assert "candidate_id" not in redacted
    assert "candidate_set_manifest" not in redacted
    assert redacted["candidate_set_manifest_checksum"] == manifest.manifest_checksum
    assert redacted["q_ref"] is None
    assert redacted["evaluated_task_count"] == 1
    assert redacted["valid_task_count"] == 1
    assert redacted["missing_task_count"] == REQUIRED_TASK_COUNT - 1
    assert redacted["task_manifest_checksum"] == _SHA_MANIFEST
    for task_redaction in redacted["task_results"]:
        assert "diagnostics" not in task_redaction
        assert "candidate_id" not in task_redaction
        assert "candidate_sha256" not in task_redaction
        assert "expected_output" not in task_redaction
        assert "reference_case_total" not in task_redaction
        assert "reference_case_pass_count" not in task_redaction


def test_redact_benchmark_result_never_leaks_privileged_data_via_repr() -> None:
    """No privileged diagnostic content leaks into the redacted payload even
    when serialized to a flat string (defense in depth beyond key checks)."""
    result = _task_result_with_diagnostics()
    manifest = _candidate_set_manifest_for(result)
    benchmark = ReferenceBenchmarkResult(
        run_context=_run_context(),
        candidate_set_manifest=manifest,
        task_results=(result,),
        task_manifest_checksum=_SHA_MANIFEST,
        oracle_version=_ORACLE_VERSION,
        evaluated_at="2026-07-01T00:00:02Z",
        duration_seconds=1.5,
    )
    redacted_text = repr(redact_benchmark_result(benchmark))
    assert "this must never be redacted-exposed" not in redacted_text
    assert "def prime_fib" not in redacted_text
    assert _CANDIDATE_SHA256 not in redacted_text


def test_redact_benchmark_result_status_counts_are_json_safe_string_keys() -> None:
    """status_counts and full_suite_outcome_counts keys must be plain strings."""
    result = _task_result_with_diagnostics()
    manifest = _candidate_set_manifest_for(result)
    benchmark = ReferenceBenchmarkResult(
        run_context=_run_context(),
        candidate_set_manifest=manifest,
        task_results=(result,),
        task_manifest_checksum=_SHA_MANIFEST,
        oracle_version=_ORACLE_VERSION,
        evaluated_at="2026-07-01T00:00:02Z",
        duration_seconds=1.5,
    )
    redacted = redact_benchmark_result(benchmark)
    assert redacted["status_counts"]["VALID"] == 1
    assert redacted["status_counts"]["INCOMPLETE"] == 0
    assert redacted["full_suite_outcome_counts"]["PASS_BASE_FAIL_PLUS"] == 1
    assert redacted["aggregate_status"] == "INCOMPLETE"


def test_redact_benchmark_result_opt_in_propagates_to_nested_task_results() -> None:
    """include_reference_case_counts propagates down to every nested task redaction."""
    result = _task_result_with_diagnostics()
    manifest = _candidate_set_manifest_for(result)
    benchmark = ReferenceBenchmarkResult(
        run_context=_run_context(),
        candidate_set_manifest=manifest,
        task_results=(result,),
        task_manifest_checksum=_SHA_MANIFEST,
        oracle_version=_ORACLE_VERSION,
        evaluated_at="2026-07-01T00:00:02Z",
        duration_seconds=1.5,
    )
    redacted = redact_benchmark_result(benchmark, include_reference_case_counts=True)
    assert redacted["task_results"][0]["reference_case_total"] == 12
    assert redacted["task_results"][0]["reference_case_pass_count"] == 9


def test_candidate_set_entry_has_no_room_for_privileged_content() -> None:
    """CandidateSetEntry structurally cannot carry oracle content or source text."""
    field_names = {f.name for f in dataclasses.fields(CandidateSetEntry)}
    assert field_names == {"task_id", "candidate_id", "candidate_sha256"}
