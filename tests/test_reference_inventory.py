"""Tests for MEGB-03A's evidence inventory and partition-feasibility analysis."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.dataset import DatasetProvenance, PrivilegedTaskView
from src.reference.inventory import (
    DEFAULT_POLICY,
    CaseIdCollisionError,
    PartitionFeasibilityPolicy,
    build_evidence_inventory,
    load_and_build_evidence_inventory,
    render_feasibility_report,
    write_inventory_artifacts,
)

EXPECTED_REAL_BLOCKED_TASKS = frozenset({"HumanEval/39", "HumanEval/55"})


def _make_task(
    task_id: str = "T/0",
    base_input: tuple[tuple[Any, ...], ...] = ((1,),),
    plus_input: tuple[tuple[Any, ...], ...] = (),
    **overrides: Any,
) -> PrivilegedTaskView:
    fields: dict[str, Any] = {
        "task_id": task_id,
        "entry_point": "f",
        "canonical_solution": "    return x\n",
        "original_test": "def check(candidate):\n    pass\n",
        "contract": "",
        "atol": 0.0,
        "base_input": base_input,
        "plus_input": plus_input,
    }
    fields.update(overrides)
    return PrivilegedTaskView(**fields)


def _make_provenance(**overrides: Any) -> DatasetProvenance:
    fields: dict[str, Any] = {
        "human_eval_package_version": "1.0.3",
        "human_eval_dataset_sha256": "a" * 64,
        "human_eval_commit_sha": None,
        "evalplus_package_version": "0.3.1",
        "evalplus_dataset_version": "v0.1.10",
        "evalplus_dataset_hash": "b" * 32,
        "expected_task_count": 164,
        "human_eval_prompt_diff_count": 0,
        "human_eval_canonical_solution_diff_count": 0,
        "loaded_at": "2026-01-01T00:00:00+00:00",
    }
    fields.update(overrides)
    return DatasetProvenance(**fields)


def _cases(count: int, start: int = 0) -> tuple[tuple[Any, ...], ...]:
    return tuple((i,) for i in range(start, start + count))


def test_insufficient_evidence_is_blocked() -> None:
    """A synthetic task far below the minimum is BLOCKED, not silently reduced."""
    task = _make_task(base_input=_cases(3), plus_input=_cases(2, start=3))
    inventory = build_evidence_inventory([task], _make_provenance())

    result = inventory.tasks[0]
    assert result.feasibility == "BLOCKED"
    assert result.unique_combined_case_count == 5
    assert result.recommended_development_cases == 0
    assert result.recommended_reference_only_cases == 0
    assert "5" in result.feasibility_reason


def test_limited_feasibility_below_target() -> None:
    """A task meeting the hard minimum but below the disjoint-replicate target is LIMITED."""
    # min_development(30) + min_reference_only(20) = 50 minimum; give exactly 60.
    task = _make_task(base_input=_cases(60))
    inventory = build_evidence_inventory([task], _make_provenance())

    result = inventory.tasks[0]
    assert result.feasibility == "LIMITED"
    assert result.recommended_development_cases == 40  # 60 - 20 reference-only
    assert result.recommended_reference_only_cases == 20


def test_ok_feasibility_caps_development_and_credits_surplus_to_reference() -> None:
    """A task with ample evidence is OK, development capped at the target, surplus to reference."""
    task = _make_task(base_input=_cases(300))
    inventory = build_evidence_inventory([task], _make_provenance())

    result = inventory.tasks[0]
    assert result.feasibility == "OK"
    assert result.recommended_development_cases == DEFAULT_POLICY.target_development_cases
    # 300 - 20 (min reference) - 150 (dev target) = 130 additional surplus to reference.
    assert result.recommended_reference_only_cases == 20 + (300 - 20 - 150)


def test_boundary_exactly_at_minimum_is_not_blocked() -> None:
    """Exactly at the hard minimum (50) is feasible, not blocked."""
    task = _make_task(base_input=_cases(50))
    inventory = build_evidence_inventory([task], _make_provenance())

    assert inventory.tasks[0].feasibility in ("LIMITED", "OK")


def test_boundary_one_below_minimum_is_blocked() -> None:
    """One case short of the hard minimum (49) is blocked."""
    task = _make_task(base_input=_cases(49))
    inventory = build_evidence_inventory([task], _make_provenance())

    assert inventory.tasks[0].feasibility == "BLOCKED"


def test_duplicate_cases_across_base_and_plus_are_detected() -> None:
    """An identical case in both base_input and plus_input is a duplicate, not double-counted."""
    task = _make_task(base_input=((1, 2),), plus_input=((1, 2), (3, 4)))
    inventory = build_evidence_inventory([task], _make_provenance())

    result = inventory.tasks[0]
    assert result.base_case_count == 1
    assert result.plus_case_count == 2
    assert result.unique_combined_case_count == 2  # (1,2) counted once
    assert len(result.duplicate_groups) == 1
    occurrences = set(result.duplicate_groups[0].occurrences)
    assert occurrences == {("base", 0), ("plus", 0)}


def test_no_duplicates_reports_empty_groups() -> None:
    """A task with all-distinct cases reports no duplicate groups."""
    task = _make_task(base_input=((1,), (2,)), plus_input=((3,),))
    inventory = build_evidence_inventory([task], _make_provenance())

    assert inventory.tasks[0].duplicate_groups == ()


def test_case_id_collision_is_raised_not_silently_merged() -> None:
    """If two different cases ever hashed to the same ID, that must be a loud error.

    A true SHA-256 collision cannot be forced in a test, so this verifies
    the code path directly by making stable_case_id return a constant
    regardless of input, simulating a collision between two genuinely
    different cases.
    """
    task = _make_task(base_input=((1,), (2,)))
    with patch("src.reference.inventory.stable_case_id", return_value="constant-id"):
        with pytest.raises(CaseIdCollisionError):
            build_evidence_inventory([task], _make_provenance())


def test_mutation_sensitivity_is_reported_as_unavailable_not_fabricated() -> None:
    """Mutation-sensitivity isn't guessed at; it's explicitly reported as unavailable."""
    task = _make_task(base_input=_cases(5))
    inventory = build_evidence_inventory([task], _make_provenance())

    assert "unknown" in inventory.tasks[0].mutation_sensitive_info.lower()


def test_repeated_generation_is_deterministic() -> None:
    """Building the inventory twice from identical inputs yields an identical checksum."""
    tasks = [
        _make_task(task_id="T/0", base_input=_cases(60)),
        _make_task(task_id="T/1", base_input=_cases(10)),
    ]
    provenance = _make_provenance()

    first = build_evidence_inventory(tasks, provenance)
    second = build_evidence_inventory(tasks, provenance)

    assert first.artifact_checksum == second.artifact_checksum
    assert first.artifact_checksum != ""


def test_different_policy_changes_the_checksum() -> None:
    """A different feasibility policy is reflected in the artifact checksum."""
    task = _make_task(base_input=_cases(60))
    provenance = _make_provenance()

    default_result = build_evidence_inventory([task], provenance)
    alternate_result = build_evidence_inventory(
        [task], provenance, policy=PartitionFeasibilityPolicy(min_development_cases=10)
    )

    assert default_result.artifact_checksum != alternate_result.artifact_checksum


def test_dataset_provenance_is_recorded_on_the_inventory() -> None:
    """The inventory records the exact dataset provenance it was built from."""
    provenance = _make_provenance(evalplus_dataset_hash="deadbeef")
    inventory = build_evidence_inventory([_make_task()], provenance)

    assert inventory.dataset_provenance.evalplus_dataset_hash == "deadbeef"


def test_expected_task_count_is_recorded_independent_of_input_length() -> None:
    """expected_task_count reflects the intended full corpus size, not len(tasks)."""
    inventory = build_evidence_inventory(
        [_make_task()], _make_provenance(), expected_task_count=164
    )
    assert inventory.expected_task_count == 164
    assert len(inventory.tasks) == 1


def test_write_inventory_artifacts_produces_three_files(tmp_path: Path) -> None:
    """The three handoff artifacts are written and are valid JSON/Markdown."""
    import json  # pylint: disable=import-outside-toplevel

    task = _make_task(base_input=_cases(60))
    inventory = build_evidence_inventory([task], _make_provenance())

    write_inventory_artifacts(inventory, tmp_path)

    inventory_path = tmp_path / "evidence_inventory.json"
    config_path = tmp_path / "recommended_partition_config.json"
    report_path = tmp_path / "feasibility_report.md"

    assert inventory_path.exists()
    assert config_path.exists()
    assert report_path.exists()

    inventory_data = json.loads(inventory_path.read_text())
    assert inventory_data["artifact_checksum"] == inventory.artifact_checksum

    config_data = json.loads(config_path.read_text())
    assert config_data["artifact_checksum"] == inventory.artifact_checksum

    report_text = report_path.read_text()
    assert "MEGB-03A" in report_text


def test_render_feasibility_report_lists_blocked_tasks_explicitly() -> None:
    """A BLOCKED task is named explicitly in the report, never silently omitted."""
    task = _make_task(task_id="HumanEval/999", base_input=_cases(3))
    inventory = build_evidence_inventory([task], _make_provenance())

    report = render_feasibility_report(inventory)
    assert "HumanEval/999" in report
    assert "BLOCKED" in report


@pytest.mark.integration
def test_real_corpus_inventories_exactly_164_tasks() -> None:
    """The real pinned corpus produces exactly 164 task inventories."""
    inventory = load_and_build_evidence_inventory()

    assert len(inventory.tasks) == 164
    assert inventory.expected_task_count == 164
    assert len({t.task_id for t in inventory.tasks}) == 164


@pytest.mark.integration
def test_real_corpus_feasibility_matches_known_pinned_result() -> None:
    """Regression check: feasibility classification is stable for the exact pinned dataset.

    These values are tied to human-eval==1.0.3 / evalplus==0.3.1 (dataset
    version v0.1.10) and the default PartitionFeasibilityPolicy. A future
    dataset-version bump may legitimately change them; if so, this test
    must be updated deliberately, not silently.
    """
    inventory = load_and_build_evidence_inventory()

    blocked_task_ids = {t.task_id for t in inventory.tasks if t.feasibility == "BLOCKED"}
    limited_count = sum(1 for t in inventory.tasks if t.feasibility == "LIMITED")
    ok_count = sum(1 for t in inventory.tasks if t.feasibility == "OK")

    assert blocked_task_ids == EXPECTED_REAL_BLOCKED_TASKS
    assert limited_count == 23
    assert ok_count == 139


@pytest.mark.integration
def test_real_corpus_generation_is_deterministic() -> None:
    """Two independent builds from the real corpus produce the same checksum."""
    first = load_and_build_evidence_inventory()
    second = load_and_build_evidence_inventory()

    assert first.artifact_checksum == second.artifact_checksum
