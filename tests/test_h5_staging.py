"""Tests for MEGB-03H.2B.2's H.5 staging identity and complete-run gate
(src.reference.h5_staging). Synthetic 164-task fixtures only, via
tests/_h5_fixtures.py -- no real privileged corpus access, no Docker.

Required-coverage for this checkpoint: successful 164/164 gate pass; valid
canonical timeout/zero result blocks promotion; 163/164, duplicate, extra,
reordered, mixed-context, mixed-profile, and candidate-manifest-mismatch
rejections; incomplete/non-release-ready trace rejections; staging from
another run/profile/manifest identity rejected.
"""

# See _h5_fixtures.py's own note: this file intentionally builds on that
# shared fixtures module rather than each test module reimplementing its
# own 164-task manifest/result/trace builders.
# pylint: disable=duplicate-code

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from src.evaluators.schema import FailureCategory
from src.reference.calibration_schema import CalibrationStage, TelemetryUnavailableReason
from src.reference.h5_staging import build_staging_cache, evaluate_complete_run_gate
from src.reference.reference_cache import ReferenceResultCache
from src.reference.result_schema import MeasurementStatus
from tests import _h5_fixtures as fx


def _staged_cache(tmp_path: Path, task_results: Any) -> ReferenceResultCache:
    cache = ReferenceResultCache(tmp_path / "staging_cache")
    for result in task_results:
        write = cache.put(result)
        assert write.disposition.value == "WRITE_ACCEPTED"
    return cache


def _gate_inputs(
    tmp_path: Path,
    task_results: Any = None,
    manifest: Any = None,
    context: Any = None,
) -> dict[str, Any]:
    manifest = manifest if manifest is not None else fx.candidate_set_manifest()
    context = context if context is not None else fx.full_run_context()
    task_results = task_results if task_results is not None else fx.valid_task_results(context)
    identity = fx.staging_identity(manifest)
    cal_ctx = fx.calibration_context()
    invocations, task_evaluations = fx.full_trace_for_results(cal_ctx, task_results)
    staging_cache = _staged_cache(tmp_path, task_results)
    return {
        "identity": identity,
        "candidate_set_manifest": manifest,
        "task_results": task_results,
        "staging_cache": staging_cache,
        "invocations": invocations,
        "task_evaluations": task_evaluations,
    }


# ---------------------------------------------------------------------------
# H5StagingIdentity validation
# ---------------------------------------------------------------------------


def test_staging_identity_requires_exactly_164() -> None:
    """H5StagingIdentity rejects any expected_task_count other than 164."""
    manifest = fx.candidate_set_manifest()
    with pytest.raises(ValueError):
        fx.staging_identity(manifest, expected_task_count=163)


def test_staging_identity_requires_sha256_checksums() -> None:
    """H5StagingIdentity rejects a non-sha256-hex task_manifest_checksum."""
    manifest = fx.candidate_set_manifest()
    with pytest.raises(ValueError):
        fx.staging_identity(manifest, task_manifest_checksum="not-a-checksum")


def test_build_staging_cache_is_rooted_under_the_identity_checksum(tmp_path: Path) -> None:
    """The staging cache directory is rooted under the identity's own
    checksum -- never the raw, operator-supplied calibration_run_id."""
    manifest = fx.candidate_set_manifest()
    identity = fx.staging_identity(manifest)
    cache = build_staging_cache(identity, root=tmp_path)
    assert identity.identity_checksum() in str(cache.cache_dir)
    assert Path(cache.cache_dir).is_relative_to(tmp_path)


# ---------------------------------------------------------------------------
# Successful gate
# ---------------------------------------------------------------------------


def test_gate_passes_for_a_perfect_164_task_run(tmp_path: Path) -> None:
    """A genuinely perfect 164/164 run passes the gate with Q_ref == 1.0."""
    inputs = _gate_inputs(tmp_path)
    result = evaluate_complete_run_gate(**inputs)
    assert result.passed is True
    assert result.benchmark_result is not None
    assert result.benchmark_result.q_ref == 1.0


# ---------------------------------------------------------------------------
# Valid canonical timeout/zero blocks promotion
# ---------------------------------------------------------------------------


def test_valid_zero_result_with_timeout_category_blocks_gate(tmp_path: Path) -> None:
    """A VALID measurement with q_ref_task=0.0 and a limit-attributable
    first_failure_category (TIMEOUT) fails the gate."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)
    results = fx.replace_result(
        results,
        "HumanEval/0",
        context,
        status=MeasurementStatus.VALID,
        q_ref_task=0.0,
        reference_case_pass_count=4,
        first_failure_category=FailureCategory.TIMEOUT,
    )
    inputs = _gate_inputs(tmp_path, task_results=results, context=context)
    result = evaluate_complete_run_gate(**inputs)
    assert result.passed is False
    assert result.benchmark_result is None


# ---------------------------------------------------------------------------
# Count/order/duplicate/extra rejections (delegated to aggregate_reference_results)
# ---------------------------------------------------------------------------


def test_163_of_164_fails_the_gate(tmp_path: Path) -> None:
    """163 of 164 expected task results fails the gate."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)[:-1]
    inputs = _gate_inputs(tmp_path, task_results=results, context=context)
    assert evaluate_complete_run_gate(**inputs).passed is False


def test_duplicate_task_id_fails_the_gate(tmp_path: Path) -> None:
    """A duplicate task_id in place of the missing 164th result fails the gate."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)
    results = results[:-1] + (results[0],)
    manifest = fx.candidate_set_manifest()
    cache = ReferenceResultCache(tmp_path / "staging_cache")
    seen_task_ids: set[str] = set()
    for result in results:
        if result.task_id in seen_task_ids:
            continue
        seen_task_ids.add(result.task_id)
        cache.put(result)
    identity = fx.staging_identity(manifest)
    cal_ctx = fx.calibration_context()
    invocations, task_evaluations = fx.full_trace_for_results(
        cal_ctx, fx.valid_task_results(context)
    )
    gate_result = evaluate_complete_run_gate(
        identity=identity,
        candidate_set_manifest=manifest,
        task_results=results,
        staging_cache=cache,
        invocations=invocations,
        task_evaluations=task_evaluations,
    )
    assert gate_result.passed is False


def test_reordered_results_fail_the_gate(tmp_path: Path) -> None:
    """Reordered (non-canonical) results are still rejected by the gate."""
    context = fx.full_run_context()
    results = tuple(reversed(fx.valid_task_results(context)))
    inputs = _gate_inputs(tmp_path, task_results=results, context=context)
    assert evaluate_complete_run_gate(**inputs).passed is False


# ---------------------------------------------------------------------------
# Mixed context / mixed profile / candidate-manifest mismatch
# ---------------------------------------------------------------------------


def test_mixed_run_context_fails_the_gate(tmp_path: Path) -> None:
    """A run whose task results don't share one identical run_context fails the gate."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)
    other_context = fx.full_run_context(experiment_run_id="a-different-experiment")
    results = fx.replace_result(results, "HumanEval/0", other_context)
    inputs = _gate_inputs(tmp_path, task_results=results, context=context)
    assert evaluate_complete_run_gate(**inputs).passed is False


def test_reduced_dev_profile_fails_the_gate(tmp_path: Path) -> None:
    """A reduced-dev execution profile fails the gate (full profile only)."""
    context = fx.full_run_context(
        execution_profile_id="docker-megb02-reduced-dev-v1",
        evaluator_version="reference-evaluator-reduced-dev-v1",
    )
    results = fx.valid_task_results(context)
    inputs = _gate_inputs(tmp_path, task_results=results, context=context)
    assert evaluate_complete_run_gate(**inputs).passed is False


def test_candidate_manifest_mismatch_fails_the_gate(tmp_path: Path) -> None:
    """Supplying a candidate_set_manifest that doesn't match the frozen
    identity's checksum fails the gate."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)
    real_manifest = fx.candidate_set_manifest()
    wrong_manifest = fx.candidate_set_manifest(task_manifest_id="a-different-manifest-id")
    identity = fx.staging_identity(real_manifest)  # frozen against the REAL manifest
    cal_ctx = fx.calibration_context()
    invocations, task_evaluations = fx.full_trace_for_results(cal_ctx, results)
    staging_cache = _staged_cache(tmp_path, results)
    result = evaluate_complete_run_gate(
        identity=identity,
        candidate_set_manifest=wrong_manifest,  # caller supplies a DIFFERENT manifest
        task_results=results,
        staging_cache=staging_cache,
        invocations=invocations,
        task_evaluations=task_evaluations,
    )
    assert result.passed is False
    assert "candidate_set_manifest" in result.reason


# ---------------------------------------------------------------------------
# Incomplete / non-release-ready trace
# ---------------------------------------------------------------------------


def test_incomplete_task_evaluation_fails_the_gate(tmp_path: Path) -> None:
    """An INCOMPLETE, non-superseded task-evaluation record fails the gate."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)
    inputs = _gate_inputs(tmp_path, task_results=results, context=context)
    cal_ctx = fx.calibration_context()
    incomplete_eval = dataclasses.replace(
        inputs["task_evaluations"][0],
        measurement_status=MeasurementStatus.INCOMPLETE,
        q_ref_task=None,
        record_checksum="",
    )
    inputs["task_evaluations"] = (incomplete_eval,) + inputs["task_evaluations"][1:]
    del cal_ctx
    assert evaluate_complete_run_gate(**inputs).passed is False


def test_not_yet_instrumented_telemetry_fails_release_readiness(tmp_path: Path) -> None:
    """A NOT_YET_INSTRUMENTED telemetry field fails release-readiness."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)
    inputs = _gate_inputs(tmp_path, task_results=results, context=context)
    tampered = dataclasses.replace(
        inputs["invocations"][0],
        candidate_wall_time_unavailable_reason=TelemetryUnavailableReason.NOT_YET_INSTRUMENTED,
        record_checksum="",
    )
    inputs["invocations"] = (tampered,) + inputs["invocations"][1:]
    result = evaluate_complete_run_gate(**inputs)
    assert result.passed is False
    assert "release-ready" in result.reason


def test_trace_reconciliation_failure_fails_the_gate(tmp_path: Path) -> None:
    """A dropped contributing invocation record fails trace reconciliation."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)
    inputs = _gate_inputs(tmp_path, task_results=results, context=context)
    # Drop the contributing invocation entirely -- the task-evaluation
    # record's own contributing_invocation_ids can no longer be resolved.
    inputs["invocations"] = inputs["invocations"][1:]
    assert evaluate_complete_run_gate(**inputs).passed is False


def test_wrong_calibration_stage_fails_the_gate(tmp_path: Path) -> None:
    """A calibration trace stamped with the wrong stage (H3, not H5) fails the gate."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)
    manifest = fx.candidate_set_manifest()
    identity = fx.staging_identity(manifest)
    wrong_stage_ctx = fx.calibration_context(stage=CalibrationStage.H3)
    invocations, task_evaluations = fx.full_trace_for_results(wrong_stage_ctx, results)
    staging_cache = _staged_cache(tmp_path, results)
    result = evaluate_complete_run_gate(
        identity=identity,
        candidate_set_manifest=manifest,
        task_results=results,
        staging_cache=staging_cache,
        invocations=invocations,
        task_evaluations=task_evaluations,
    )
    assert result.passed is False
    assert "H5" in result.reason


# ---------------------------------------------------------------------------
# Staging from another run/profile/manifest identity is rejected
# ---------------------------------------------------------------------------


def test_staging_from_a_different_calibration_run_id_is_rejected(tmp_path: Path) -> None:
    """An identity frozen against a different calibration_run_id is rejected."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)
    manifest = fx.candidate_set_manifest()
    real_identity = fx.staging_identity(manifest)
    other_identity = fx.staging_identity(manifest, calibration_run_id="a-different-run")
    assert real_identity != other_identity
    cal_ctx = fx.calibration_context()  # stamped with the REAL run id
    invocations, task_evaluations = fx.full_trace_for_results(cal_ctx, results)
    staging_cache = _staged_cache(tmp_path, results)
    result = evaluate_complete_run_gate(
        identity=other_identity,
        candidate_set_manifest=manifest,
        task_results=results,
        staging_cache=staging_cache,
        invocations=invocations,
        task_evaluations=task_evaluations,
    )
    assert result.passed is False


def test_staging_from_a_different_execution_profile_identity_is_rejected(tmp_path: Path) -> None:
    """An identity frozen against a different execution_profile_id is rejected."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)
    manifest = fx.candidate_set_manifest()
    other_identity = fx.staging_identity(manifest, execution_profile_id="a-different-profile")
    inputs = _gate_inputs(tmp_path, task_results=results, manifest=manifest, context=context)
    inputs["identity"] = other_identity
    assert evaluate_complete_run_gate(**inputs).passed is False


def test_staging_from_a_different_candidate_manifest_is_rejected(tmp_path: Path) -> None:
    """An identity frozen against a different candidate-set manifest is rejected."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)
    manifest_a = fx.candidate_set_manifest()
    manifest_b = fx.candidate_set_manifest(task_manifest_id="a-different-manifest-id")
    identity_for_b = fx.staging_identity(manifest_b)
    cal_ctx = fx.calibration_context()
    invocations, task_evaluations = fx.full_trace_for_results(cal_ctx, results)
    staging_cache = _staged_cache(tmp_path, results)
    # identity was frozen against manifest_b, but the caller supplies manifest_a.
    result = evaluate_complete_run_gate(
        identity=identity_for_b,
        candidate_set_manifest=manifest_a,
        task_results=results,
        staging_cache=staging_cache,
        invocations=invocations,
        task_evaluations=task_evaluations,
    )
    assert result.passed is False


# ---------------------------------------------------------------------------
# Staged-entry content/key validation
# ---------------------------------------------------------------------------


def test_staged_entry_missing_from_staging_cache_fails_the_gate(tmp_path: Path) -> None:
    """A task result never actually persisted into the staging cache fails the gate."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context)
    manifest = fx.candidate_set_manifest()
    identity = fx.staging_identity(manifest)
    cal_ctx = fx.calibration_context()
    invocations, task_evaluations = fx.full_trace_for_results(cal_ctx, results)
    # Stage only 163 of the 164 -- the 164th's content was never persisted.
    staging_cache = _staged_cache(tmp_path, results[:-1])
    result = evaluate_complete_run_gate(
        identity=identity,
        candidate_set_manifest=manifest,
        task_results=results,
        staging_cache=staging_cache,
        invocations=invocations,
        task_evaluations=task_evaluations,
    )
    assert result.passed is False
    assert "staged entry" in result.reason
