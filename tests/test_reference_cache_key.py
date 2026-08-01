"""Tests for src.reference.cache_key (MEGB-03G.2).

Covers: deterministic construction, every outcome-affecting field
independently changing cache identity, non-outcome provenance never
changing cache identity, schema/tamper rejection, and serialization round
trips. Synthetic fixtures only -- no privileged artifacts, no Docker.
"""

# This file intentionally builds its own local fixtures (ReferenceRunContext/
# ReferenceTaskResult) independent of tests/test_result_schema.py's and
# tests/test_reference_aggregation.py's, for the same reason documented
# there: this test layer validates the cache-key boundary specifically, and
# sharing fixtures would couple independently valuable test layers.
# pylint: disable=duplicate-code

import hashlib

import pytest

from src.evaluators.schema import FailureCategory
from src.reference.cache_key import (
    CACHE_KEY_SCHEMA_VERSION,
    InvalidCacheKeyError,
    ReferenceResultCacheKey,
    cache_key_for,
    cache_key_from_dict,
    cache_key_to_dict,
)
from src.reference.oracle import COMPARISON_PROFILE_VERSION
from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EXECUTION_PROFILE_ID_FULL,
    EXECUTION_PROTOCOL_VERSION,
)
from src.reference.result_schema import MeasurementStatus, ReferenceRunContext, ReferenceTaskResult

_SHA_CONFIG = "b" * 64


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
    }
    fields.update(overrides)
    return ReferenceRunContext(**fields)


def _task_result(
    task_id: str = "HumanEval/0",
    context: ReferenceRunContext | None = None,
    **overrides: object,
) -> ReferenceTaskResult:
    candidate_id = f"cand-{task_id}"
    candidate_sha256 = hashlib.sha256(f"candidate-source-for-{task_id}".encode()).hexdigest()
    fields: dict[str, object] = {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "candidate_sha256": candidate_sha256,
        "context": context if context is not None else _run_context(),
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


def _key_fields(**overrides: str) -> dict[str, str]:
    fields = {
        "cache_key_schema_version": CACHE_KEY_SCHEMA_VERSION,
        "task_id": "HumanEval/0",
        "candidate_sha256": "1" * 64,
        "reference_case_checksum": "2" * 64,
        "dataset_version": "humaneval-plus-v0.1.10",
        "partition_version": "partition-v1",
        "oracle_version": "oracle-v1",
        "comparison_profile_version": COMPARISON_PROFILE_VERSION,
        "evaluator_version": EVALUATOR_VERSION_FULL,
        "execution_profile_id": EXECUTION_PROFILE_ID_FULL,
        "protocol_version": EXECUTION_PROTOCOL_VERSION,
    }
    fields.update(overrides)
    return fields


# --- Deterministic construction ---------------------------------------------


def test_cache_key_for_is_deterministic() -> None:
    """The same task result always produces the same key digest."""
    result = _task_result()
    key_a = cache_key_for(result)
    key_b = cache_key_for(result)
    assert key_a.key_digest == key_b.key_digest
    assert len(key_a.key_digest) == 64


def test_cache_key_constructs_with_well_formed_fields() -> None:
    """Cache key constructs with well formed fields."""
    key = ReferenceResultCacheKey(**_key_fields())
    assert len(key.key_digest) == 64


# --- Every outcome-affecting field changes identity -------------------------


def test_task_id_changes_cache_identity() -> None:
    """Task id changes cache identity."""
    key_a = cache_key_for(_task_result(task_id="HumanEval/0"))
    key_b = cache_key_for(_task_result(task_id="HumanEval/1"))
    assert key_a.key_digest != key_b.key_digest


def test_candidate_sha256_changes_cache_identity() -> None:
    """Candidate sha256 changes cache identity."""
    key_a = cache_key_for(_task_result(candidate_sha256="1" * 64))
    key_b = cache_key_for(_task_result(candidate_sha256="2" * 64))
    assert key_a.key_digest != key_b.key_digest


def test_reference_case_checksum_changes_cache_identity() -> None:
    """The exact field the original MEGB-03G cache-key tuple omitted."""
    key_a = cache_key_for(_task_result(reference_case_checksum="a" * 64))
    key_b = cache_key_for(_task_result(reference_case_checksum="b" * 64))
    assert key_a.key_digest != key_b.key_digest


def test_dataset_version_changes_cache_identity() -> None:
    """Dataset version changes cache identity."""
    key_a = cache_key_for(_task_result(context=_run_context(dataset_version="v1")))
    key_b = cache_key_for(_task_result(context=_run_context(dataset_version="v2")))
    assert key_a.key_digest != key_b.key_digest


def test_partition_version_changes_cache_identity() -> None:
    """Partition version changes cache identity."""
    key_a = cache_key_for(_task_result(context=_run_context(partition_version="p1")))
    key_b = cache_key_for(_task_result(context=_run_context(partition_version="p2")))
    assert key_a.key_digest != key_b.key_digest


def test_oracle_version_changes_cache_identity() -> None:
    """Oracle version changes cache identity."""
    key_a = cache_key_for(_task_result(oracle_version="oracle-v1"))
    key_b = cache_key_for(_task_result(oracle_version="oracle-v2"))
    assert key_a.key_digest != key_b.key_digest


def test_comparison_profile_version_changes_cache_identity() -> None:
    """Comparison profile version changes cache identity."""
    key_a = cache_key_for(_task_result(context=_run_context(comparison_profile_version="c1")))
    key_b = cache_key_for(_task_result(context=_run_context(comparison_profile_version="c2")))
    assert key_a.key_digest != key_b.key_digest


def test_evaluator_version_changes_cache_identity() -> None:
    """Evaluator version changes cache identity."""
    key_a = cache_key_for(_task_result(context=_run_context(evaluator_version="e1")))
    key_b = cache_key_for(_task_result(context=_run_context(evaluator_version="e2")))
    assert key_a.key_digest != key_b.key_digest


def test_execution_profile_id_changes_cache_identity() -> None:
    """Execution profile id changes cache identity."""
    key_a = cache_key_for(_task_result(context=_run_context(execution_profile_id="p1")))
    key_b = cache_key_for(_task_result(context=_run_context(execution_profile_id="p2")))
    assert key_a.key_digest != key_b.key_digest


def test_protocol_version_changes_cache_identity() -> None:
    """protocol_version is sourced from EXECUTION_PROTOCOL_VERSION rather
    than a per-result field (see cache_key.py's documented limitation), so
    this is tested directly on the key model rather than through
    cache_key_for()."""
    key_a = ReferenceResultCacheKey(**_key_fields(protocol_version="proto-v1"))
    key_b = ReferenceResultCacheKey(**_key_fields(protocol_version="proto-v2"))
    assert key_a.key_digest != key_b.key_digest


def test_cache_key_uses_the_live_execution_protocol_version_constant() -> None:
    """Cache key uses the live execution protocol version constant."""
    key = cache_key_for(_task_result())
    assert key.protocol_version == EXECUTION_PROTOCOL_VERSION


# --- Non-outcome provenance never changes identity --------------------------


def test_experiment_run_id_does_not_change_cache_identity() -> None:
    """Experiment run id does not change cache identity."""
    key_a = cache_key_for(_task_result(context=_run_context(experiment_run_id="exp-a")))
    key_b = cache_key_for(_task_result(context=_run_context(experiment_run_id="exp-b")))
    assert key_a.key_digest == key_b.key_digest


def test_optimization_run_id_does_not_change_cache_identity() -> None:
    """Optimization run id does not change cache identity."""
    key_a = cache_key_for(_task_result(context=_run_context(optimization_run_id="opt-a")))
    key_b = cache_key_for(_task_result(context=_run_context(optimization_run_id="opt-b")))
    assert key_a.key_digest == key_b.key_digest


def test_candidate_display_id_does_not_change_cache_identity() -> None:
    """Candidate display id does not change cache identity."""
    key_a = cache_key_for(_task_result(candidate_id="cand-display-a"))
    key_b = cache_key_for(_task_result(candidate_id="cand-display-b"))
    assert key_a.key_digest == key_b.key_digest


def test_portfolio_selection_metadata_does_not_change_cache_identity() -> None:
    """Portfolio selection metadata does not change cache identity."""
    key_a = cache_key_for(
        _task_result(
            context=_run_context(
                portfolio_frozen_at="2026-01-01T00:00:00Z", portfolio_selection_rule="rule-a"
            )
        )
    )
    key_b = cache_key_for(
        _task_result(
            context=_run_context(
                portfolio_frozen_at="2027-01-01T00:00:00Z", portfolio_selection_rule="rule-b"
            )
        )
    )
    assert key_a.key_digest == key_b.key_digest


def test_evaluated_at_and_duration_do_not_change_cache_identity() -> None:
    """Evaluated at and duration do not change cache identity."""
    key_a = cache_key_for(_task_result(evaluated_at="2026-01-01T00:00:00Z", duration_seconds=0.1))
    key_b = cache_key_for(_task_result(evaluated_at="2027-06-01T00:00:00Z", duration_seconds=99.9))
    assert key_a.key_digest == key_b.key_digest


# --- Schema/tamper rejection -------------------------------------------------


def test_wrong_cache_key_schema_version_rejected() -> None:
    """Wrong cache key schema version rejected."""
    with pytest.raises(InvalidCacheKeyError, match="cache_key_schema_version"):
        ReferenceResultCacheKey(
            **_key_fields(cache_key_schema_version="reference-result-cache-key-v0")
        )


def test_tampered_key_digest_rejected() -> None:
    """Tampered key digest rejected."""
    good = ReferenceResultCacheKey(**_key_fields())
    assert good.key_digest != "0" * 64
    with pytest.raises(InvalidCacheKeyError, match="key_digest"):
        ReferenceResultCacheKey(**{**_key_fields(), "key_digest": "0" * 64})


@pytest.mark.parametrize("field_name", ["candidate_sha256", "reference_case_checksum"])
def test_non_sha256_field_rejected(field_name: str) -> None:
    """Non sha256 field rejected."""
    with pytest.raises(InvalidCacheKeyError, match="sha256"):
        ReferenceResultCacheKey(**_key_fields(**{field_name: "not-a-sha256"}))


@pytest.mark.parametrize(
    "field_name",
    [
        "task_id",
        "dataset_version",
        "partition_version",
        "oracle_version",
        "comparison_profile_version",
        "evaluator_version",
        "execution_profile_id",
        "protocol_version",
    ],
)
def test_empty_string_field_rejected(field_name: str) -> None:
    """Empty string field rejected."""
    with pytest.raises(InvalidCacheKeyError):
        ReferenceResultCacheKey(**_key_fields(**{field_name: ""}))


def test_cache_key_is_frozen() -> None:
    """Cache key is frozen."""
    key = ReferenceResultCacheKey(**_key_fields())
    with pytest.raises(AttributeError):
        key.task_id = "other"  # type: ignore[misc]


# --- Serialization round trip ------------------------------------------------


def test_cache_key_round_trip_preserves_all_fields() -> None:
    """Cache key round trip preserves all fields."""
    key = cache_key_for(_task_result())
    restored = cache_key_from_dict(cache_key_to_dict(key))
    assert restored == key


def test_cache_key_from_dict_rejects_tampered_digest() -> None:
    """Cache key from dict rejects tampered digest."""
    key = cache_key_for(_task_result())
    payload = cache_key_to_dict(key)
    payload["key_digest"] = "0" * 64
    with pytest.raises(InvalidCacheKeyError):
        cache_key_from_dict(payload)
