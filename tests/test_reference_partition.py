"""Tests for MEGB-03B's development/reference partition construction."""

import dataclasses
from pathlib import Path

import pytest

from src.dataset import load_privileged_view, load_provenance, load_public_view
from src.reference.partition import (
    EXCLUDED_TASK_ID,
    EXPECTED_EXPERIMENT_TASK_COUNT,
    EXPECTED_VALIDATION_TASK_COUNT,
    CaseWithProvenance,
    PartitionInfeasibleError,
    build_primary_experiment_manifest,
    build_reference_validation_manifest,
    build_task_partition,
    gather_eligible_cases,
    rank_case,
    redact_primary_experiment_manifest,
    validate_primary_experiment_manifest,
    verify_augmentation_reproducibility,
)


def _cases(count: int, provenance: str = "evalplus-original-v1") -> list[CaseWithProvenance]:
    return [CaseWithProvenance(case_id=f"case-{i}", provenance=provenance) for i in range(count)]


def test_rank_case_is_deterministic() -> None:
    """Repeated calls with identical inputs produce identical ranks."""
    assert rank_case("T/0", "c1") == rank_case("T/0", "c1")


def test_rank_case_differs_by_task_case_seed_and_version() -> None:
    """Any single differing input changes the rank."""
    base = rank_case("T/0", "c1", "partition-v1", "seed-a")
    assert rank_case("T/1", "c1", "partition-v1", "seed-a") != base
    assert rank_case("T/0", "c2", "partition-v1", "seed-a") != base
    assert rank_case("T/0", "c1", "partition-v2", "seed-a") != base
    assert rank_case("T/0", "c1", "partition-v1", "seed-b") != base


def test_build_task_partition_assigns_exact_counts() -> None:
    """Exactly 40 development cases, all remaining go to reference_only."""
    partition = build_task_partition("T/0", _cases(100))
    assert len(partition.development_case_ids) == 40
    assert len(partition.reference_only_case_ids) == 60
    assert partition.total_unique_case_count == 100


def test_build_task_partition_has_zero_overlap() -> None:
    """No case ID appears in both pools."""
    partition = build_task_partition("T/0", _cases(200))
    assert not set(partition.development_case_ids) & set(partition.reference_only_case_ids)


def test_build_task_partition_is_exhaustive() -> None:
    """Every eligible case ends up in exactly one pool."""
    cases = _cases(150)
    partition = build_task_partition("T/0", cases)
    assigned = set(partition.development_case_ids) | set(partition.reference_only_case_ids)
    assert assigned == {c.case_id for c in cases}


def test_build_task_partition_raises_below_minimum() -> None:
    """Fewer than 70 (40 + 30) eligible cases raises, never silently reduces the budget."""
    with pytest.raises(PartitionInfeasibleError):
        build_task_partition("T/0", _cases(69))


def test_build_task_partition_boundary_at_exactly_70() -> None:
    """Exactly 70 eligible cases is feasible (40 dev + 30 ref, the minimum floor)."""
    partition = build_task_partition("T/0", _cases(70))
    assert len(partition.development_case_ids) == 40
    assert len(partition.reference_only_case_ids) == 30


def test_build_task_partition_does_not_stratify_by_provenance() -> None:
    """Assignment depends only on case_id rank, never on provenance.

    A case's pool membership must be identical regardless of which
    provenance label is attached to it — provenance is recorded, not used
    to select or privilege cases.
    """
    cases_a = _cases(100, provenance="evalplus-original-v1")
    cases_b = [CaseWithProvenance(case_id=c.case_id, provenance="other-tag") for c in cases_a]

    partition_a = build_task_partition("T/0", cases_a)
    partition_b = build_task_partition("T/0", cases_b)

    assert partition_a.development_case_ids == partition_b.development_case_ids
    assert partition_a.reference_only_case_ids == partition_b.reference_only_case_ids


def test_build_task_partition_reports_provenance_counts_per_pool() -> None:
    """Provenance counts in each pool reflect the actual mix assigned there."""
    mixed = _cases(60, "original") + _cases(60, "supplementary")
    # Re-tag case IDs to avoid collisions between the two _cases() calls.
    mixed = [
        CaseWithProvenance(case_id=f"{c.provenance}-{i}", provenance=c.provenance)
        for i, c in enumerate(mixed)
    ]
    partition = build_task_partition("T/0", mixed)

    dev_total = sum(partition.development_provenance_counts.values())
    ref_total = sum(partition.reference_only_provenance_counts.values())
    assert dev_total == 40
    assert ref_total == 80


def test_different_seed_changes_manifest_checksum() -> None:
    """A different partition seed changes which cases land in which pool (usually)."""
    cases_by_task = {"T/0": _cases(200), "T/1": _cases(200)}
    manifest_a = build_primary_experiment_manifest(
        cases_by_task, load_provenance(), excluded_task_id="none"
    )
    manifest_b = build_primary_experiment_manifest(
        cases_by_task, load_provenance(), excluded_task_id="none", partition_seed="alternate-seed"
    )
    assert manifest_a.manifest_checksum != manifest_b.manifest_checksum


def test_rebuild_from_identical_inputs_is_byte_stable() -> None:
    """Rebuilding from identical inputs reproduces the identical checksum."""
    cases_by_task = {"T/0": _cases(200), "T/1": _cases(200)}
    manifest_a = build_primary_experiment_manifest(
        cases_by_task, load_provenance(), excluded_task_id="none"
    )
    manifest_b = build_primary_experiment_manifest(
        cases_by_task, load_provenance(), excluded_task_id="none"
    )
    assert manifest_a.manifest_checksum == manifest_b.manifest_checksum


def test_manifest_checksum_ignores_dataset_provenance_load_timestamp() -> None:
    """Two otherwise-identical DatasetProvenance objects differing only in
    ``loaded_at`` (as would happen on two separate process runs, since
    ``load_provenance()`` stamps a fresh wall-clock time each load) must
    still produce the same manifest checksum — the load timestamp is not
    part of what's being hashed as content.
    """
    cases_by_task = {"T/0": _cases(200)}
    provenance_a = load_provenance()
    provenance_b = dataclasses.replace(provenance_a, loaded_at="2000-01-01T00:00:00+00:00")
    assert provenance_a.loaded_at != provenance_b.loaded_at  # sanity: they really do differ

    manifest_a = build_primary_experiment_manifest(
        cases_by_task, provenance_a, excluded_task_id="none"
    )
    manifest_b = build_primary_experiment_manifest(
        cases_by_task, provenance_b, excluded_task_id="none"
    )
    assert manifest_a.manifest_checksum == manifest_b.manifest_checksum


def test_build_primary_experiment_manifest_excludes_named_task() -> None:
    """The excluded task never appears in the experimental manifest."""
    cases_by_task = {"T/0": _cases(200), "HumanEval/39": _cases(200)}
    manifest = build_primary_experiment_manifest(cases_by_task, load_provenance())
    task_ids = {p.task_id for p in manifest.task_partitions}
    assert "HumanEval/39" not in task_ids
    assert "T/0" in task_ids


def test_build_reference_validation_manifest_includes_all_tasks_unsplit() -> None:
    """The validation manifest has no development/reference split - just full case sets."""
    cases_by_task = {"T/0": _cases(50), "HumanEval/39": _cases(12)}
    manifest = build_reference_validation_manifest(cases_by_task, load_provenance())
    by_id = {t.task_id: t for t in manifest.tasks}
    assert len(by_id["T/0"].case_ids) == 50
    assert len(by_id["HumanEval/39"].case_ids) == 12


def test_validate_primary_experiment_manifest_flags_all_checks_true_for_valid_manifest() -> None:
    """A well-formed manifest passes every structural validation."""
    cases_by_task = {f"T/{i}": _cases(100) for i in range(3)}
    manifest = build_primary_experiment_manifest(
        cases_by_task, load_provenance(), excluded_task_id="none"
    )
    checks = validate_primary_experiment_manifest(manifest, excluded_task_id="none")
    assert all(
        checks[key]
        for key in (
            "unique_task_ids",
            "all_development_counts_equal_target",
            "min_reference_only_satisfies_floor",
            "exhaustive_assignment",
            "zero_dev_ref_overlap",
            "excluded_task_absent",
        )
    )


def test_redact_primary_experiment_manifest_excludes_reference_only() -> None:
    """The redacted view never carries reference_only_case_ids."""
    cases_by_task = {"T/0": _cases(100)}
    manifest = build_primary_experiment_manifest(
        cases_by_task, load_provenance(), excluded_task_id="none"
    )
    redacted = redact_primary_experiment_manifest(manifest)

    serialized = str(redacted)
    assert "reference_only" not in serialized
    tasks = redacted["tasks"]
    assert isinstance(tasks, list)
    task_entry = tasks[0]
    assert isinstance(task_entry, dict)
    assert set(task_entry.keys()) == {"task_id", "development_case_ids"}
    assert len(task_entry["development_case_ids"]) == 40


@pytest.mark.integration
def test_real_corpus_produces_163_experimental_and_164_validation_tasks() -> None:
    """End-to-end against the real pinned corpus."""
    priv = {t.task_id: t for t in load_privileged_view()}
    pub = {t.task_id: t.prompt for t in load_public_view()}
    cases_by_task, augmentation_results = gather_eligible_cases(priv, pub)

    verify_augmentation_reproducibility(
        augmentation_results,
        Path("artifacts/reference/augmentation/augmentation_results.json"),
    )

    provenance = load_provenance()
    validation_manifest = build_reference_validation_manifest(cases_by_task, provenance)
    experiment_manifest = build_primary_experiment_manifest(cases_by_task, provenance)

    assert len(validation_manifest.tasks) == EXPECTED_VALIDATION_TASK_COUNT
    assert len(experiment_manifest.task_partitions) == EXPECTED_EXPERIMENT_TASK_COUNT
    assert EXCLUDED_TASK_ID not in {p.task_id for p in experiment_manifest.task_partitions}
    assert EXCLUDED_TASK_ID in {t.task_id for t in validation_manifest.tasks}

    checks = validate_primary_experiment_manifest(experiment_manifest)
    assert all(
        checks[key]
        for key in (
            "task_count_matches_expected",
            "unique_task_ids",
            "all_development_counts_equal_target",
            "min_reference_only_satisfies_floor",
            "exhaustive_assignment",
            "zero_dev_ref_overlap",
            "excluded_task_absent",
        )
    )


@pytest.mark.integration
def test_real_corpus_checksums_are_deterministic_across_two_builds() -> None:
    """Two independent builds from the real corpus produce identical checksums."""
    priv = {t.task_id: t for t in load_privileged_view()}
    pub = {t.task_id: t.prompt for t in load_public_view()}
    provenance = load_provenance()

    cases_1, _ = gather_eligible_cases(priv, pub)
    cases_2, _ = gather_eligible_cases(priv, pub)

    manifest_1 = build_primary_experiment_manifest(cases_1, provenance)
    manifest_2 = build_primary_experiment_manifest(cases_2, provenance)
    assert manifest_1.manifest_checksum == manifest_2.manifest_checksum

    validation_1 = build_reference_validation_manifest(cases_1, provenance)
    validation_2 = build_reference_validation_manifest(cases_2, provenance)
    assert validation_1.manifest_checksum == validation_2.manifest_checksum
