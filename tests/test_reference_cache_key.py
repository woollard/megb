"""Tests for src.reference.cache_key (MEGB-03G.2, v4 cache-provenance correction).

Covers: deterministic construction, every outcome-affecting field
(including the v4 content checksums) independently changing cache
identity, non-outcome provenance never changing cache identity,
schema/tamper rejection, cache-key reconstruction from a serialized result
without consulting any live/mutable default, and serialization round
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
from src.reference.result_redaction import task_result_from_dict, task_result_to_dict
from src.reference.result_schema import MeasurementStatus, ReferenceRunContext, ReferenceTaskResult

_SHA_CONFIG = "b" * 64
_DATASET_CHECKSUM = "fe585eb4df8c88d844eeb463ea4d0302"
_TASK_MANIFEST_CHECKSUM = "d" * 64


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
        "execution_protocol_version": EXECUTION_PROTOCOL_VERSION,
        "dataset_checksum": _DATASET_CHECKSUM,
        "task_manifest_checksum": _TASK_MANIFEST_CHECKSUM,
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
        "dataset_checksum": _DATASET_CHECKSUM,
        "partition_version": "partition-v1",
        "task_manifest_checksum": _TASK_MANIFEST_CHECKSUM,
        "oracle_version": "oracle-v1",
        "comparison_profile_version": COMPARISON_PROFILE_VERSION,
        "evaluator_version": EVALUATOR_VERSION_FULL,
        "execution_profile_id": EXECUTION_PROFILE_ID_FULL,
        "execution_protocol_version": EXECUTION_PROTOCOL_VERSION,
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
    """A well-formed key constructs and stamps a real digest."""
    key = ReferenceResultCacheKey(**_key_fields())
    assert len(key.key_digest) == 64


# --- Every outcome-affecting field changes identity -------------------------


def test_task_id_changes_cache_identity() -> None:
    """Different task_id values produce different cache keys."""
    key_a = cache_key_for(_task_result(task_id="HumanEval/0"))
    key_b = cache_key_for(_task_result(task_id="HumanEval/1"))
    assert key_a.key_digest != key_b.key_digest


def test_candidate_sha256_changes_cache_identity() -> None:
    """Different candidate_sha256 values produce different cache keys."""
    key_a = cache_key_for(_task_result(candidate_sha256="1" * 64))
    key_b = cache_key_for(_task_result(candidate_sha256="2" * 64))
    assert key_a.key_digest != key_b.key_digest


def test_reference_case_checksum_changes_cache_identity() -> None:
    """The exact field the original MEGB-03G cache-key tuple omitted."""
    key_a = cache_key_for(_task_result(reference_case_checksum="a" * 64))
    key_b = cache_key_for(_task_result(reference_case_checksum="b" * 64))
    assert key_a.key_digest != key_b.key_digest


def test_dataset_version_changes_cache_identity() -> None:
    """Different dataset_version labels produce different cache keys."""
    key_a = cache_key_for(_task_result(context=_run_context(dataset_version="v1")))
    key_b = cache_key_for(_task_result(context=_run_context(dataset_version="v2")))
    assert key_a.key_digest != key_b.key_digest


def test_dataset_checksum_changes_cache_identity() -> None:
    """The v4 content-bound dataset checksum independently changes cache
    identity, distinct from the dataset_version label."""
    key_a = cache_key_for(_task_result(context=_run_context(dataset_checksum="1" * 32)))
    key_b = cache_key_for(_task_result(context=_run_context(dataset_checksum="2" * 32)))
    assert key_a.key_digest != key_b.key_digest


def test_partition_version_changes_cache_identity() -> None:
    """Different partition_version labels produce different cache keys."""
    key_a = cache_key_for(_task_result(context=_run_context(partition_version="p1")))
    key_b = cache_key_for(_task_result(context=_run_context(partition_version="p2")))
    assert key_a.key_digest != key_b.key_digest


def test_task_manifest_checksum_changes_cache_identity() -> None:
    """The v4 content-bound partition/task-manifest checksum independently
    changes cache identity, distinct from the partition_version label."""
    key_a = cache_key_for(_task_result(context=_run_context(task_manifest_checksum="a" * 64)))
    key_b = cache_key_for(_task_result(context=_run_context(task_manifest_checksum="b" * 64)))
    assert key_a.key_digest != key_b.key_digest


def test_oracle_version_changes_cache_identity() -> None:
    """Different oracle_version values produce different cache keys."""
    key_a = cache_key_for(_task_result(oracle_version="oracle-v1"))
    key_b = cache_key_for(_task_result(oracle_version="oracle-v2"))
    assert key_a.key_digest != key_b.key_digest


def test_comparison_profile_version_changes_cache_identity() -> None:
    """Different comparison_profile_version values produce different cache keys."""
    key_a = cache_key_for(_task_result(context=_run_context(comparison_profile_version="c1")))
    key_b = cache_key_for(_task_result(context=_run_context(comparison_profile_version="c2")))
    assert key_a.key_digest != key_b.key_digest


def test_evaluator_version_changes_cache_identity() -> None:
    """Different evaluator_version values produce different cache keys."""
    key_a = cache_key_for(_task_result(context=_run_context(evaluator_version="e1")))
    key_b = cache_key_for(_task_result(context=_run_context(evaluator_version="e2")))
    assert key_a.key_digest != key_b.key_digest


def test_execution_profile_id_changes_cache_identity() -> None:
    """Different execution_profile_id values produce different cache keys."""
    key_a = cache_key_for(_task_result(context=_run_context(execution_profile_id="p1")))
    key_b = cache_key_for(_task_result(context=_run_context(execution_profile_id="p2")))
    assert key_a.key_digest != key_b.key_digest


def test_execution_protocol_version_changes_cache_identity() -> None:
    """The v4-persisted execution_protocol_version independently changes
    cache identity -- this is the field the original G.2 submission sourced
    from a live module constant instead of the result's own context."""
    key_a = cache_key_for(_task_result(context=_run_context(execution_protocol_version="proto-v1")))
    key_b = cache_key_for(_task_result(context=_run_context(execution_protocol_version="proto-v2")))
    assert key_a.key_digest != key_b.key_digest


def test_cache_key_for_derives_execution_protocol_version_from_context_only() -> None:
    """cache_key_for() reads execution_protocol_version exclusively from
    task_result.context -- even when that value differs from the live
    EXECUTION_PROTOCOL_VERSION module constant, the key follows the
    persisted context, never the constant."""
    context = _run_context(execution_protocol_version="a-completely-different-protocol-id")
    key = cache_key_for(_task_result(context=context))
    assert key.execution_protocol_version == "a-completely-different-protocol-id"
    assert key.execution_protocol_version != EXECUTION_PROTOCOL_VERSION


# --- Non-outcome provenance never changes identity --------------------------


def test_experiment_run_id_does_not_change_cache_identity() -> None:
    """experiment_run_id never influences cache identity."""
    key_a = cache_key_for(_task_result(context=_run_context(experiment_run_id="exp-a")))
    key_b = cache_key_for(_task_result(context=_run_context(experiment_run_id="exp-b")))
    assert key_a.key_digest == key_b.key_digest


def test_optimization_run_id_does_not_change_cache_identity() -> None:
    """optimization_run_id never influences cache identity."""
    key_a = cache_key_for(_task_result(context=_run_context(optimization_run_id="opt-a")))
    key_b = cache_key_for(_task_result(context=_run_context(optimization_run_id="opt-b")))
    assert key_a.key_digest == key_b.key_digest


def test_candidate_display_id_does_not_change_cache_identity() -> None:
    """candidate_id (the display id, not the hash) never influences cache identity."""
    key_a = cache_key_for(_task_result(candidate_id="cand-display-a"))
    key_b = cache_key_for(_task_result(candidate_id="cand-display-b"))
    assert key_a.key_digest == key_b.key_digest


def test_portfolio_selection_metadata_does_not_change_cache_identity() -> None:
    """portfolio_frozen_at/portfolio_selection_rule never influence cache identity."""
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
    """evaluated_at/duration_seconds never influence cache identity."""
    key_a = cache_key_for(_task_result(evaluated_at="2026-01-01T00:00:00Z", duration_seconds=0.1))
    key_b = cache_key_for(_task_result(evaluated_at="2027-06-01T00:00:00Z", duration_seconds=99.9))
    assert key_a.key_digest == key_b.key_digest


# --- Schema/tamper rejection -------------------------------------------------


def test_wrong_cache_key_schema_version_rejected() -> None:
    """An unrecognized cache_key_schema_version is rejected."""
    with pytest.raises(InvalidCacheKeyError, match="cache_key_schema_version"):
        ReferenceResultCacheKey(
            **_key_fields(cache_key_schema_version="reference-result-cache-key-v1")
        )


def test_tampered_key_digest_rejected() -> None:
    """A key_digest that does not match the recomputed digest is rejected."""
    good = ReferenceResultCacheKey(**_key_fields())
    assert good.key_digest != "0" * 64
    with pytest.raises(InvalidCacheKeyError, match="key_digest"):
        ReferenceResultCacheKey(**{**_key_fields(), "key_digest": "0" * 64})


@pytest.mark.parametrize("field_name", ["candidate_sha256", "reference_case_checksum"])
def test_non_sha256_field_rejected(field_name: str) -> None:
    """candidate_sha256/reference_case_checksum must be 64-character hex."""
    with pytest.raises(InvalidCacheKeyError, match="sha256"):
        ReferenceResultCacheKey(**_key_fields(**{field_name: "not-a-sha256"}))


def test_non_sha256_task_manifest_checksum_rejected() -> None:
    """task_manifest_checksum must also be 64-character hex (it is our own
    sha256-computed manifest checksum, unlike dataset_checksum's native
    32-character upstream format)."""
    with pytest.raises(InvalidCacheKeyError, match="task_manifest_checksum"):
        ReferenceResultCacheKey(**_key_fields(task_manifest_checksum="not-a-checksum"))


def test_dataset_checksum_accepts_its_native_non_sha256_format() -> None:
    """dataset_checksum's authoritative source (evalplus's own dataset hash)
    is a 32-character digest, not 64-character sha256 -- this must not be
    forced into sha256-hex format, only required nonempty."""
    key = ReferenceResultCacheKey(**_key_fields(dataset_checksum=_DATASET_CHECKSUM))
    assert key.dataset_checksum == _DATASET_CHECKSUM
    assert len(_DATASET_CHECKSUM) == 32


@pytest.mark.parametrize(
    "field_name",
    [
        "task_id",
        "dataset_version",
        "dataset_checksum",
        "partition_version",
        "oracle_version",
        "comparison_profile_version",
        "evaluator_version",
        "execution_profile_id",
        "execution_protocol_version",
    ],
)
def test_empty_string_field_rejected(field_name: str) -> None:
    """Every required string field must be nonempty."""
    with pytest.raises(InvalidCacheKeyError):
        ReferenceResultCacheKey(**_key_fields(**{field_name: ""}))


def test_cache_key_is_frozen() -> None:
    """ReferenceResultCacheKey instances must be immutable."""
    key = ReferenceResultCacheKey(**_key_fields())
    with pytest.raises(AttributeError):
        key.task_id = "other"  # type: ignore[misc]


# --- Serialization round trip and live-default independence -----------------


def test_cache_key_round_trip_preserves_all_fields() -> None:
    """cache_key_from_dict(cache_key_to_dict(x)) == x."""
    key = cache_key_for(_task_result())
    restored = cache_key_from_dict(cache_key_to_dict(key))
    assert restored == key


def test_cache_key_from_dict_rejects_tampered_digest() -> None:
    """A tampered key_digest is rejected on deserialize, not silently accepted."""
    key = cache_key_for(_task_result())
    payload = cache_key_to_dict(key)
    payload["key_digest"] = "0" * 64
    with pytest.raises(InvalidCacheKeyError):
        cache_key_from_dict(payload)


def test_cache_key_reconstructed_from_serialized_result_matches_original() -> None:
    """Regression guard for the v4 correction: a task_result serialized to
    dict and reloaded, potentially in a process where the live
    EXECUTION_PROTOCOL_VERSION constant has since changed, still reproduces
    exactly the original cache key -- cache_key_for() never consults a
    live/mutable default, only the persisted, validated result context."""
    context = _run_context(execution_protocol_version="frozen-protocol-from-the-past")
    original_result = _task_result(context=context)
    original_key = cache_key_for(original_result)

    reloaded_result = task_result_from_dict(task_result_to_dict(original_result))
    reloaded_key = cache_key_for(reloaded_result)

    assert reloaded_key == original_key
    assert reloaded_key.execution_protocol_version == "frozen-protocol-from-the-past"
