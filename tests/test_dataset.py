"""Tests for the HumanEval corpus loader and public/privileged privilege boundary."""

from dataclasses import fields
from typing import Any, Mapping

import pytest

from src.dataset import (
    EXPECTED_TASK_COUNT,
    DatasetValidationError,
    PrivilegedTaskView,
    PublicTaskView,
    _validate_and_build,
    load_privileged_view,
    load_provenance,
    load_public_view,
)


def _he_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "task_id": "T/0",
        "prompt": "def f(x):\n    pass\n",
        "entry_point": "f",
        "canonical_solution": "    return x\n",
        "test": "def check(candidate):\n    assert candidate(1) == 1\n",
    }
    record.update(overrides)
    return record


def _hep_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "task_id": "T/0",
        "prompt": "def f(x):\n    pass\n",
        "entry_point": "f",
        "canonical_solution": "    return x\n",
        "contract": "",
        "atol": 0,
        "base_input": [[1], [2]],
        "plus_input": [[3], [4], [5]],
    }
    record.update(overrides)
    return record


def test_happy_path_builds_aligned_views() -> None:
    """Two well-formed, aligned records produce matching public/privileged views."""
    he = [_he_record()]
    hep = [_hep_record()]

    result = _validate_and_build(he, hep, expected_task_count=1)

    assert result.public_tasks == (
        PublicTaskView(task_id="T/0", prompt="def f(x):\n    pass\n", entry_point="f"),
    )
    assert result.privileged_tasks[0].canonical_solution == "    return x\n"
    assert result.privileged_tasks[0].original_test == he[0]["test"]
    assert result.privileged_tasks[0].base_input == ((1,), (2,))
    assert result.privileged_tasks[0].plus_input == ((3,), (4,), (5,))
    assert result.human_eval_prompt_diff_count == 0
    assert result.human_eval_canonical_solution_diff_count == 0


def test_prompt_mismatch_is_recorded_not_raised() -> None:
    """A differing prompt is a diagnostic count, not a validation failure."""
    he = [_he_record(prompt="def f(x):\n    pass  # original\n")]
    hep = [_hep_record()]

    result = _validate_and_build(he, hep, expected_task_count=1)

    assert result.human_eval_prompt_diff_count == 1
    # HumanEval+ is authoritative for the public prompt.
    assert result.public_tasks[0].prompt == hep[0]["prompt"]


def test_canonical_solution_mismatch_is_recorded_not_raised() -> None:
    """A differing canonical solution is a diagnostic count, not a validation failure."""
    he = [_he_record(canonical_solution="    return x + 0\n")]
    hep = [_hep_record(canonical_solution="    return x\n")]

    result = _validate_and_build(he, hep, expected_task_count=1)

    assert result.human_eval_canonical_solution_diff_count == 1
    assert result.privileged_tasks[0].canonical_solution == "    return x\n"


def test_entry_point_mismatch_raises() -> None:
    """entry_point must match exactly between HumanEval and HumanEval+."""
    he = [_he_record(entry_point="f")]
    hep = [_hep_record(entry_point="g")]

    with pytest.raises(DatasetValidationError, match="entry_point mismatch"):
        _validate_and_build(he, hep, expected_task_count=1)


def test_missing_required_field_raises() -> None:
    """A record missing a required field is rejected."""
    he = [_he_record()]
    del he[0]["test"]
    hep = [_hep_record()]

    with pytest.raises(DatasetValidationError, match="missing required fields"):
        _validate_and_build(he, hep, expected_task_count=1)


def test_record_missing_task_id_raises() -> None:
    """A record with no task_id at all is rejected."""
    he = [_he_record()]
    del he[0]["task_id"]
    hep = [_hep_record()]

    with pytest.raises(DatasetValidationError, match="missing 'task_id'"):
        _validate_and_build(he, hep, expected_task_count=1)


def test_duplicate_task_id_raises() -> None:
    """Duplicate task_ids within a raw record stream are rejected."""
    he = [_he_record(), _he_record()]
    hep = [_hep_record(), _hep_record(task_id="T/1")]

    with pytest.raises(DatasetValidationError, match="duplicate task_id"):
        _validate_and_build(he, hep, expected_task_count=1)


def test_task_id_set_mismatch_raises() -> None:
    """HumanEval and HumanEval+ must cover the same set of task_ids."""
    he = [_he_record(task_id="T/0")]
    hep = [_hep_record(task_id="T/1")]

    with pytest.raises(DatasetValidationError, match="task_id sets differ"):
        _validate_and_build(he, hep, expected_task_count=1)


def test_unexpected_task_count_raises() -> None:
    """The corpus must contain exactly the expected number of tasks."""
    he = [_he_record()]
    hep = [_hep_record()]

    with pytest.raises(DatasetValidationError, match="expected 2 tasks, found 1"):
        _validate_and_build(he, hep, expected_task_count=2)


def test_public_task_view_cannot_carry_privileged_fields() -> None:
    """PublicTaskView structurally excludes canonical solutions and test evidence."""
    public_field_names = {f.name for f in fields(PublicTaskView)}
    privileged_only_field_names = {f.name for f in fields(PrivilegedTaskView)} - public_field_names

    assert public_field_names == {"task_id", "prompt", "entry_point"}
    assert "canonical_solution" in privileged_only_field_names
    assert "base_input" in privileged_only_field_names
    assert "plus_input" in privileged_only_field_names
    for privileged_field in privileged_only_field_names:
        assert not hasattr(PublicTaskView, privileged_field)


@pytest.mark.integration
def test_real_corpus_has_exactly_164_aligned_tasks() -> None:
    """The real pinned corpus loads exactly 164 tasks, aligned across both views."""
    public_tasks = load_public_view()
    privileged_tasks = load_privileged_view()

    assert len(public_tasks) == EXPECTED_TASK_COUNT
    assert len({t.task_id for t in public_tasks}) == EXPECTED_TASK_COUNT
    assert len(privileged_tasks) == EXPECTED_TASK_COUNT
    assert len({t.task_id for t in privileged_tasks}) == EXPECTED_TASK_COUNT
    assert {t.task_id for t in public_tasks} == {t.task_id for t in privileged_tasks}

    entry_points_by_task: Mapping[str, str] = {t.task_id: t.entry_point for t in public_tasks}
    for privileged in privileged_tasks:
        assert entry_points_by_task[privileged.task_id] == privileged.entry_point


@pytest.mark.integration
def test_real_corpus_provenance_is_pinned_and_recorded() -> None:
    """Provenance records pinned versions, checksums, and known diagnostic diff counts."""
    provenance = load_provenance()

    assert provenance.expected_task_count == EXPECTED_TASK_COUNT
    assert provenance.human_eval_package_version
    assert provenance.evalplus_package_version
    assert len(provenance.human_eval_dataset_sha256) == 64
    assert provenance.evalplus_dataset_hash
    # Pinned exactly via requirements.txt (human-eval==1.0.3, evalplus==0.3.1);
    # regression values observed against that exact pinned pair.
    assert provenance.human_eval_prompt_diff_count == 1
    assert provenance.human_eval_canonical_solution_diff_count == 164


@pytest.mark.integration
def test_real_corpus_human_eval_0_matches_known_content() -> None:
    """A spot check against real, known HumanEval/0 content."""
    public_tasks = {t.task_id: t for t in load_public_view()}
    task = public_tasks["HumanEval/0"]

    assert task.entry_point == "has_close_elements"
    assert "has_close_elements" in task.prompt
