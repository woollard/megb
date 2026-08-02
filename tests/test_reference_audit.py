"""Tests for src.reference.reference_audit (MEGB-03G.2).

Covers: audit append behavior (multiple records, none overwritten), the
explicit field-allowlist enforcement, and leakage tests for candidate code,
case IDs, expected outputs, canonical solutions, diagnostics, tracebacks,
and privileged paths. Synthetic fixtures and temporary directories only --
no privileged artifacts, no Docker.
"""

# See tests/test_reference_cache_key.py's note: this file intentionally
# builds its own local fixtures independent of the schema/aggregation/cache
# test layers.
# pylint: disable=duplicate-code

import dataclasses
import hashlib
from pathlib import Path

import pytest

from src.evaluators.schema import FailureCategory
from src.reference.oracle import COMPARISON_PROFILE_VERSION
from src.reference.reference_audit import (
    AUDIT_RECORD_FIELD_NAMES,
    AUDIT_RECORD_SCHEMA_VERSION,
    InvalidAuditRecordError,
    ReferenceAuditLog,
    ReferenceAuditRecord,
    audit_record_from_dict,
    audit_record_to_dict,
    build_audit_record,
)
from src.reference.reference_cache import CacheDisposition
from src.reference.reference_evaluator import EVALUATOR_VERSION_FULL, EXECUTION_PROFILE_ID_FULL
from src.reference.result_schema import MeasurementStatus, ReferenceRunContext, ReferenceTaskResult

_SHA_CONFIG = "b" * 64

_FORBIDDEN_CONTENT = {
    "candidate_code": "def solve(): return 'CANDIDATE-CODE-CANARY'",
    "case_input": "CASE-INPUT-CANARY",
    "case_id": "CASE-ID-CANARY",
    "expected_output": "EXPECTED-OUTPUT-CANARY",
    "canonical_solution": "CANONICAL-SOLUTION-CANARY",
    "traceback": "Traceback (most recent call last): TRACEBACK-CANARY",
}


def _run_context(**overrides: str) -> ReferenceRunContext:
    fields = {
        "experiment_run_id": "exp-1",
        "optimization_run_id": "opt-1",
        "optimization_config_sha256": _SHA_CONFIG,
        "portfolio_frozen_at": "2026-08-01T00:00:00Z",
        "portfolio_selection_rule": "best_of_run",
        "evaluator_version": EVALUATOR_VERSION_FULL,
        "dataset_version": "humaneval-plus-v0.1.10",
        "partition_version": "partition-v1",
        "execution_profile_id": EXECUTION_PROFILE_ID_FULL,
        "comparison_profile_version": COMPARISON_PROFILE_VERSION,
        "execution_protocol_version": "reference-evaluator-execution-protocol-v1",
        "dataset_checksum": "fe585eb4df8c88d844eeb463ea4d0302",
        "task_manifest_checksum": "d" * 64,
    }
    fields.update(overrides)
    return ReferenceRunContext(**fields)


def _valid_result(task_id: str = "HumanEval/0", **overrides: object) -> ReferenceTaskResult:
    candidate_id = f"cand-{task_id}"
    candidate_sha256 = hashlib.sha256(f"candidate-source-for-{task_id}".encode()).hexdigest()
    fields: dict[str, object] = {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "candidate_sha256": candidate_sha256,
        "context": _run_context(),
        "status": MeasurementStatus.VALID,
        "q_ref_task": 1.0,
        "reference_case_total": 5,
        "reference_case_pass_count": 5,
        "first_failure_category": FailureCategory.NONE,
        "oracle_version": "oracle-v1",
        "reference_case_checksum": hashlib.sha256(f"cases-for-{task_id}".encode()).hexdigest(),
        "evaluated_at": "2026-08-01T00:00:01Z",
        "duration_seconds": 0.25,
    }
    fields.update(overrides)
    return ReferenceTaskResult(**fields)  # type: ignore[arg-type]


def _record(**overrides: object) -> ReferenceAuditRecord:
    result = _valid_result()
    built = build_audit_record(
        caller="MEGB-03G.2-test",
        run_context=result.context,
        task_result=result,
        cache_disposition=CacheDisposition.WRITE_ACCEPTED,
        invocation_id="inv-0",
        invoked_at="2026-08-01T00:00:02Z",
        result_artifact_location="artifacts/privileged/reference/cache/deadbeef.json",
    )
    if not overrides:
        return built
    return dataclasses.replace(built, **overrides)  # type: ignore[arg-type]


# --- Construction and field allowlist ----------------------------------------


def test_build_audit_record_constructs() -> None:
    """Build audit record constructs."""
    record = _record()
    assert record.audit_schema_version == AUDIT_RECORD_SCHEMA_VERSION
    assert record.status == "VALID"
    assert record.cache_disposition == "WRITE_ACCEPTED"


def test_audit_record_field_allowlist_is_exhaustive_and_safe() -> None:
    """The allowlist contains only safe identity/version/status/timing
    fields -- nothing named after case content, candidate source, or
    free-form diagnostics."""
    forbidden_name_fragments = (
        "candidate_code",
        "case_input",
        "case_id",
        "expected_output",
        "canonical_solution",
        "diagnostic",
        "traceback",
        "exception",
    )
    for field_name in AUDIT_RECORD_FIELD_NAMES:
        for fragment in forbidden_name_fragments:
            assert fragment not in field_name, f"{field_name!r} looks unsafe for an audit record"


def test_audit_record_to_dict_keys_are_exactly_the_allowlist() -> None:
    """Audit record to dict keys are exactly the allowlist."""
    record = _record()
    assert set(audit_record_to_dict(record).keys()) == AUDIT_RECORD_FIELD_NAMES


def test_wrong_audit_schema_version_rejected() -> None:
    """Wrong audit schema version rejected."""
    with pytest.raises(InvalidAuditRecordError, match="audit_schema_version"):
        _record(audit_schema_version="reference-audit-record-v0")


def test_unknown_cache_disposition_rejected() -> None:
    """Unknown cache disposition rejected."""
    with pytest.raises(InvalidAuditRecordError, match="cache_disposition"):
        _record(cache_disposition="NOT_A_REAL_DISPOSITION")


def test_unknown_status_rejected() -> None:
    """Unknown status rejected."""
    with pytest.raises(InvalidAuditRecordError, match="status"):
        _record(status="NOT_A_REAL_STATUS")


def test_negative_duration_rejected() -> None:
    """Negative duration rejected."""
    with pytest.raises(InvalidAuditRecordError, match="duration_seconds"):
        _record(duration_seconds=-0.1)


@pytest.mark.parametrize(
    "field_name",
    [
        "caller",
        "experiment_run_id",
        "optimization_run_id",
        "candidate_id",
        "candidate_sha256",
        "execution_protocol_version",
        "dataset_checksum",
        "task_manifest_checksum",
        "task_id",
        "invocation_id",
        "invoked_at",
        "result_artifact_location",
    ],
)
def test_empty_string_field_rejected(field_name: str) -> None:
    """Empty string field rejected."""
    with pytest.raises(InvalidAuditRecordError):
        _record(**{field_name: ""})


def test_audit_record_is_frozen() -> None:
    """Audit record is frozen."""
    record = _record()
    with pytest.raises(AttributeError):
        record.status = "INCOMPLETE"  # type: ignore[misc]


# --- Round trip ---------------------------------------------------------------


def test_audit_record_round_trip_preserves_all_fields() -> None:
    """Audit record round trip preserves all fields."""
    record = _record()
    restored = audit_record_from_dict(audit_record_to_dict(record))
    assert restored == record


# --- Append behavior ------------------------------------------------------------


def test_append_adds_one_line_per_record(tmp_path: Path) -> None:
    """Append adds one line per record."""
    log = ReferenceAuditLog(tmp_path / "audit.jsonl")
    log.append(_record(invocation_id="inv-1"))
    log.append(_record(invocation_id="inv-2"))
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_repeated_invocations_are_visible_not_overwritten(tmp_path: Path) -> None:
    """Repeated invocations are visible not overwritten."""
    log = ReferenceAuditLog(tmp_path / "audit.jsonl")
    log.append(_record(invocation_id="inv-1"))
    log.append(_record(invocation_id="inv-1"))  # a second, repeated invocation
    records = log.read_all()
    assert len(records) == 2
    assert all(record.invocation_id == "inv-1" for record in records)


def test_read_all_preserves_append_order(tmp_path: Path) -> None:
    """Read all preserves append order."""
    log = ReferenceAuditLog(tmp_path / "audit.jsonl")
    log.append(_record(invocation_id="inv-1"))
    log.append(_record(invocation_id="inv-2"))
    log.append(_record(invocation_id="inv-3"))
    records = log.read_all()
    assert [record.invocation_id for record in records] == ["inv-1", "inv-2", "inv-3"]


def test_read_all_on_nonexistent_log_is_empty(tmp_path: Path) -> None:
    """Read all on nonexistent log is empty."""
    log = ReferenceAuditLog(tmp_path / "does-not-exist.jsonl")
    assert not log.read_all()


# --- Leakage tests --------------------------------------------------------------


def test_audit_record_never_contains_forbidden_content_in_values() -> None:
    """Even if a caller tried to smuggle case content through the one
    free-text-shaped field this schema has (result_artifact_location or
    caller), the *other* forbidden categories can never appear because no
    field exists to carry them -- diagnostics/case inputs/canonical
    solutions are never read from task_result.diagnostics at all."""
    result = _valid_result(
        diagnostics={
            "case_input": _FORBIDDEN_CONTENT["case_input"],
            "expected_output": _FORBIDDEN_CONTENT["expected_output"],
            "canonical_solution": _FORBIDDEN_CONTENT["canonical_solution"],
            "traceback": _FORBIDDEN_CONTENT["traceback"],
        }
    )
    record = build_audit_record(
        caller="MEGB-03G.2-test",
        run_context=result.context,
        task_result=result,
        cache_disposition=CacheDisposition.VALID_HIT,
        invocation_id="inv-leak-check",
        invoked_at="2026-08-01T00:00:02Z",
        result_artifact_location="artifacts/privileged/reference/cache/deadbeef.json",
    )
    serialized = str(audit_record_to_dict(record))
    for label, canary in _FORBIDDEN_CONTENT.items():
        assert canary not in serialized, f"{label} leaked into the audit record"


def test_audit_record_has_no_diagnostics_field_at_all() -> None:
    """Audit record has no diagnostics field at all."""
    assert "diagnostics" not in AUDIT_RECORD_FIELD_NAMES


def test_result_artifact_location_is_a_pointer_not_privileged_content() -> None:
    """result_artifact_location must be a safe path/digest pointer -- this
    test documents and checks the expected shape rather than raw content."""
    record = _record()
    assert record.result_artifact_location.startswith("artifacts/privileged/reference/cache/")
    assert _FORBIDDEN_CONTENT["case_input"] not in record.result_artifact_location
