"""Tests for src.reference.reference_cache (MEGB-03G.2).

Covers: valid hits, misses, malformed/truncated/checksum-invalid entries,
schema/version mismatch, atomic writes, conflicting-write refusal, the
non-cacheable-status contract, leakage checks, and the gitignore
confirmation. Uses only synthetic fixtures and temporary directories -- no
privileged artifacts, no Docker.
"""

# See tests/test_reference_cache_key.py's note: this file intentionally
# builds its own local fixtures independent of the schema/aggregation test
# layers.
# pylint: disable=duplicate-code

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from src.evaluators.schema import FailureCategory
from src.reference.cache_key import cache_key_for, cache_key_to_dict
from src.reference.oracle import COMPARISON_PROFILE_VERSION
from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EXECUTION_PROFILE_ID_FULL,
)
from src.reference.reference_cache import (
    CACHE_ENTRY_SCHEMA_VERSION,
    DEFAULT_CACHE_DIR,
    CacheDisposition,
    NonCacheableResultError,
    ReferenceResultCache,
)
from src.reference.result_redaction import task_result_to_dict
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


def _invalid_result(task_id: str = "HumanEval/0") -> ReferenceTaskResult:
    candidate_id = f"cand-{task_id}"
    candidate_sha256 = hashlib.sha256(f"candidate-source-for-{task_id}".encode()).hexdigest()
    return ReferenceTaskResult(
        task_id=task_id,
        candidate_id=candidate_id,
        candidate_sha256=candidate_sha256,
        context=_run_context(),
        status=MeasurementStatus.INVALID_INFRASTRUCTURE,
        q_ref_task=None,
        reference_case_total=0,
        reference_case_pass_count=0,
        first_failure_category=FailureCategory.INFRASTRUCTURE_ERROR,
        oracle_version="oracle-v1",
        reference_case_checksum=hashlib.sha256(f"cases-for-{task_id}".encode()).hexdigest(),
        evaluated_at="2026-08-01T00:00:01Z",
        duration_seconds=0.1,
    )


# --- Valid hits and ordinary misses ------------------------------------------


def test_put_then_get_is_a_valid_hit(tmp_path: Path) -> None:
    """Put then get is a valid hit."""
    cache = ReferenceResultCache(tmp_path / "cache")
    result = _valid_result()
    write = cache.put(result)
    assert write.disposition == CacheDisposition.WRITE_ACCEPTED

    lookup = cache.get(cache_key_for(result))
    assert lookup.disposition == CacheDisposition.VALID_HIT
    assert lookup.task_result == result


def test_get_on_empty_cache_is_a_miss(tmp_path: Path) -> None:
    """Get on empty cache is a miss."""
    cache = ReferenceResultCache(tmp_path / "cache")
    lookup = cache.get(cache_key_for(_valid_result()))
    assert lookup.disposition == CacheDisposition.MISS
    assert lookup.task_result is None


def test_get_for_a_different_key_is_a_miss(tmp_path: Path) -> None:
    """Get for a different key is a miss."""
    cache = ReferenceResultCache(tmp_path / "cache")
    cache.put(_valid_result(task_id="HumanEval/0"))
    lookup = cache.get(cache_key_for(_valid_result(task_id="HumanEval/1")))
    assert lookup.disposition == CacheDisposition.MISS


def test_reference_case_checksum_mismatch_is_a_miss_not_a_stale_hit(tmp_path: Path) -> None:
    """Regression guard for the original cache-key defect: a corrected
    reference case must never serve the old (now-mismatched) cached result."""
    cache = ReferenceResultCache(tmp_path / "cache")
    original = _valid_result(reference_case_checksum="a" * 64)
    cache.put(original)
    corrected_key = cache_key_for(_valid_result(reference_case_checksum="b" * 64))
    lookup = cache.get(corrected_key)
    assert lookup.disposition == CacheDisposition.MISS


# --- Non-cacheable status contract ------------------------------------------


def test_put_refuses_non_valid_result(tmp_path: Path) -> None:
    """Put refuses non valid result."""
    cache = ReferenceResultCache(tmp_path / "cache")
    with pytest.raises(NonCacheableResultError):
        cache.put(_invalid_result())


# --- Idempotent and conflicting writes ---------------------------------------


def test_put_same_content_twice_is_idempotent(tmp_path: Path) -> None:
    """Put same content twice is idempotent."""
    cache = ReferenceResultCache(tmp_path / "cache")
    result = _valid_result()
    first = cache.put(result)
    second = cache.put(result)
    assert first.disposition == CacheDisposition.WRITE_ACCEPTED
    assert second.disposition == CacheDisposition.WRITE_ACCEPTED


def test_put_different_content_under_same_key_is_conflicting(tmp_path: Path) -> None:
    """Same key (task/candidate/versions identical) but a different result
    body (e.g. a different pass count) must never silently overwrite."""
    cache = ReferenceResultCache(tmp_path / "cache")
    result_a = _valid_result(duration_seconds=0.1)
    cache.put(result_a)
    # Construct a different task_result whose cache key is nonetheless
    # identical: cache_key_for() does not depend on duration_seconds, so a
    # different duration_seconds is exactly a same-key/different-content case.
    result_b = _valid_result(duration_seconds=99.9)
    write = cache.put(result_b)
    assert write.disposition == CacheDisposition.CONFLICTING_WRITE


def test_conflicting_write_does_not_alter_the_stored_entry(tmp_path: Path) -> None:
    """Conflicting write does not alter the stored entry."""
    cache = ReferenceResultCache(tmp_path / "cache")
    result_a = _valid_result(duration_seconds=0.1)
    cache.put(result_a)
    cache.put(_valid_result(duration_seconds=99.9))
    lookup = cache.get(cache_key_for(result_a))
    assert lookup.disposition == CacheDisposition.VALID_HIT
    assert lookup.task_result is not None
    assert lookup.task_result.duration_seconds == 0.1


# --- Atomic writes ------------------------------------------------------------


def test_put_leaves_no_temp_files_behind(tmp_path: Path) -> None:
    """Put leaves no temp files behind."""
    cache_dir = tmp_path / "cache"
    cache = ReferenceResultCache(cache_dir)
    cache.put(_valid_result())
    leftover_temp_files = list(cache_dir.glob(".tmp-*"))
    assert not leftover_temp_files


def test_cache_file_is_named_by_its_own_key_digest(tmp_path: Path) -> None:
    """Cache file is named by its own key digest."""
    cache_dir = tmp_path / "cache"
    cache = ReferenceResultCache(cache_dir)
    result = _valid_result()
    cache.put(result)
    key = cache_key_for(result)
    assert (cache_dir / f"{key.key_digest}.json").exists()


# --- Malformed / truncated / checksum-invalid entries ------------------------


def test_malformed_json_entry_is_corrupt(tmp_path: Path) -> None:
    """Malformed json entry is corrupt."""
    cache_dir = tmp_path / "cache"
    cache = ReferenceResultCache(cache_dir)
    result = _valid_result()
    key = cache_key_for(result)
    (cache_dir / f"{key.key_digest}.json").write_text("{not valid json", encoding="utf-8")
    lookup = cache.get(key)
    assert lookup.disposition == CacheDisposition.CORRUPT


def test_truncated_entry_is_corrupt(tmp_path: Path) -> None:
    """Truncated entry is corrupt."""
    cache_dir = tmp_path / "cache"
    cache = ReferenceResultCache(cache_dir)
    result = _valid_result()
    key = cache_key_for(result)
    cache.put(result)
    path = cache_dir / f"{key.key_digest}.json"
    full_content = path.read_text(encoding="utf-8")
    path.write_text(full_content[: len(full_content) // 2], encoding="utf-8")
    lookup = cache.get(key)
    assert lookup.disposition == CacheDisposition.CORRUPT


def test_tampered_checksum_entry_is_corrupt(tmp_path: Path) -> None:
    """Tampered checksum entry is corrupt."""
    cache_dir = tmp_path / "cache"
    cache = ReferenceResultCache(cache_dir)
    result = _valid_result()
    key = cache_key_for(result)
    cache.put(result)
    path = cache_dir / f"{key.key_digest}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["task_result"]["q_ref_task"] = 0.0  # tamper without recomputing entry_checksum
    path.write_text(json.dumps(payload), encoding="utf-8")
    lookup = cache.get(key)
    assert lookup.disposition == CacheDisposition.CORRUPT


def test_entry_missing_required_field_is_corrupt(tmp_path: Path) -> None:
    """Entry missing required field is corrupt."""
    cache_dir = tmp_path / "cache"
    cache = ReferenceResultCache(cache_dir)
    result = _valid_result()
    key = cache_key_for(result)
    cache.put(result)
    path = cache_dir / f"{key.key_digest}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["entry_checksum"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    lookup = cache.get(key)
    assert lookup.disposition == CacheDisposition.CORRUPT


def test_entry_whose_stored_key_does_not_match_requested_key_is_corrupt(tmp_path: Path) -> None:
    """Defense in depth: even though the file path is content-addressed by
    the key digest, the embedded cache_key must also match exactly."""
    cache_dir = tmp_path / "cache"
    cache = ReferenceResultCache(cache_dir)
    result = _valid_result()
    key = cache_key_for(result)
    cache.put(result)
    path = cache_dir / f"{key.key_digest}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    other_key = cache_key_for(_valid_result(task_id="HumanEval/999"))
    payload["cache_key"] = cache_key_to_dict(other_key)
    # Recompute the checksum over the tampered payload (matching the
    # module's own canonicalization) so the checksum check itself passes,
    # isolating the stored-key-vs-requested-key check specifically.
    payload_without_checksum = {k: v for k, v in payload.items() if k != "entry_checksum"}
    canonical = json.dumps(payload_without_checksum, sort_keys=True)
    payload["entry_checksum"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")
    lookup = cache.get(key)
    assert lookup.disposition == CacheDisposition.CORRUPT


# --- Schema/version mismatch --------------------------------------------------


def test_entry_schema_version_mismatch_is_stale_incompatible(tmp_path: Path) -> None:
    """Entry schema version mismatch is stale incompatible."""
    cache_dir = tmp_path / "cache"
    cache = ReferenceResultCache(cache_dir)
    result = _valid_result()
    key = cache_key_for(result)
    cache.put(result)
    path = cache_dir / f"{key.key_digest}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cache_entry_schema_version"] = "reference-result-cache-entry-v0"
    path.write_text(json.dumps(payload), encoding="utf-8")
    lookup = cache.get(key)
    assert lookup.disposition == CacheDisposition.STALE_INCOMPATIBLE


def test_cache_key_schema_version_mismatch_is_stale_incompatible(tmp_path: Path) -> None:
    """Cache key schema version mismatch is stale incompatible."""
    cache_dir = tmp_path / "cache"
    cache = ReferenceResultCache(cache_dir)
    result = _valid_result()
    key = cache_key_for(result)
    cache.put(result)
    path = cache_dir / f"{key.key_digest}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cache_key_schema_version"] = "reference-result-cache-key-v0"
    path.write_text(json.dumps(payload), encoding="utf-8")
    lookup = cache.get(key)
    assert lookup.disposition == CacheDisposition.STALE_INCOMPATIBLE


# --- Leakage checks ------------------------------------------------------------


def test_cache_entry_never_contains_diagnostics_content(tmp_path: Path) -> None:
    """A result whose (currently-always-empty-in-production) diagnostics
    field somehow carried sensitive content must not leak it any more than
    task_result_to_dict already governs -- the cache stores exactly that
    privileged serialization, never anything additional."""
    cache_dir = tmp_path / "cache"
    cache = ReferenceResultCache(cache_dir)
    result = _valid_result(diagnostics={"expected_output": "SECRET-CANARY"})
    cache.put(result)
    key = cache_key_for(result)
    path = cache_dir / f"{key.key_digest}.json"
    raw_text = path.read_text(encoding="utf-8")
    assert "SECRET-CANARY" in raw_text  # present, because it's in the privileged task_result itself
    # The cache does not add any *additional* leakage beyond what
    # task_result_to_dict already serializes -- confirm the on-disk entry's
    # task_result section is byte-identical to the direct privileged
    # serialization.
    payload = json.loads(raw_text)
    assert payload["task_result"] == task_result_to_dict(result)


def test_valid_hit_requires_no_privileged_evidence_outside_the_cache(tmp_path: Path) -> None:
    """A cache hit is retrievable using only the cache directory -- no other
    privileged source (oracle, partition) needs to be consulted."""
    cache_dir = tmp_path / "cache"
    cache = ReferenceResultCache(cache_dir)
    result = _valid_result()
    cache.put(result)

    # A fresh cache instance pointed at the same directory, with nothing
    # else available, must still produce a full valid hit.
    fresh_cache = ReferenceResultCache(cache_dir)
    lookup = fresh_cache.get(cache_key_for(result))
    assert lookup.disposition == CacheDisposition.VALID_HIT
    assert lookup.task_result == result


# --- Gitignore confirmation ---------------------------------------------------


def test_default_cache_directory_is_gitignored() -> None:
    """Default cache directory is gitignored."""
    probe_path = DEFAULT_CACHE_DIR / "probe-entry.json"
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(probe_path)],
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
    )
    assert result.returncode == 0, (
        f"{probe_path} is not gitignored -- artifacts/privileged/ must remain excluded"
    )


def test_cache_entry_schema_version_constant_is_stable() -> None:
    """Cache entry schema version constant is stable."""
    assert CACHE_ENTRY_SCHEMA_VERSION == "reference-result-cache-entry-v1"
