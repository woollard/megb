"""MEGB-03B: build and freeze the development/reference partition.

Constructs two distinct, non-overlapping-in-purpose manifests:

* ``primary_experiment_task_manifest`` — 163 tasks (every task except
  ``HumanEval/39``), each split into exactly 40 ``development`` cases and
  the remaining (>= 30) ``reference_only`` cases via a deterministic
  SHA-256 ranking procedure.
* ``reference_validation_task_manifest`` — all 164 tasks, each with its
  full accepted unique case set (original plus, where applicable,
  MEGB-03A.1's accepted supplementary evidence) and no development/
  reference split. Used only by MEGB-03's own canonical/parity validation
  (MEGB-03C onward), never by the primary experiment.

``HumanEval/39`` never receives a development pool or an S1-S4 definition;
it participates only in the validation manifest, with its 12 exhaustive
cases.

No expected outputs are constructed here (MEGB-03C's responsibility); this
module only assigns already-accepted candidate *inputs* to pools.
"""

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.dataset import (
    DatasetProvenance,
    PrivilegedTaskView,
    load_privileged_view,
    load_provenance,
    load_public_view,
)
from src.reference.augmentation import (
    PROVENANCE_ORIGINAL,
    PROVENANCE_SUPPLEMENTARY,
    TaskAugmentationResult,
    augment_task,
    task_configs,
)
from src.reference.case_serialization import stable_case_id

PARTITION_ALGORITHM_VERSION = "partition-v1"
PARTITION_SEED = "megb-03b-seed-v1"
DEVELOPMENT_TARGET = 40
MIN_REFERENCE_ONLY = 30
EXCLUDED_TASK_ID = "HumanEval/39"
EXPECTED_VALIDATION_TASK_COUNT = 164
EXPECTED_EXPERIMENT_TASK_COUNT = 163

# Privileged-artifact policy (see docs/measurement/privileged-artifact-policy.md):
# full manifest bytes live outside git; a committed lock file anchors their
# identity via checksums, size, and generation provenance.
LOCK_SCHEMA_VERSION = "partition-lock-v1"
COMMITTED_OUTPUT_DIR = Path("artifacts/reference/partition")
PRIVILEGED_OUTPUT_DIR = Path("artifacts/privileged/reference/partition")
LOCK_PATH = COMMITTED_OUTPUT_DIR / "partition.lock.json"
AUGMENTATION_RESULTS_PATH = Path("artifacts/reference/augmentation/augmentation_results.json")
BUILD_COMMAND = "python -m src.reference.partition_cli build"


class PartitionInfeasibleError(ValueError):
    """Raised when a task cannot support the required development + reference-only budget."""


@dataclass(frozen=True)
class CaseWithProvenance:
    """One eligible case, tagged with where it came from."""

    case_id: str
    provenance: str


@dataclass(frozen=True)
class TaskPartition:
    """The development/reference_only split for one experimental task."""

    task_id: str
    development_case_ids: tuple[str, ...]
    reference_only_case_ids: tuple[str, ...]
    development_provenance_counts: Mapping[str, int]
    reference_only_provenance_counts: Mapping[str, int]
    total_unique_case_count: int


@dataclass(frozen=True)
class ReferenceValidationTaskEntry:
    """One task's full, unsplit case set for the 164-task validation manifest."""

    task_id: str
    case_ids: tuple[str, ...]
    provenance_counts: Mapping[str, int]


@dataclass(frozen=True)
class PrimaryExperimentManifest:
    """The frozen 163-task development/reference_only partition manifest."""

    manifest_kind: str
    partition_algorithm_version: str
    partition_seed: str
    development_target: int
    min_reference_only: int
    dataset_provenance: DatasetProvenance
    task_partitions: tuple[TaskPartition, ...]
    generated_at: str
    manifest_checksum: str = ""


@dataclass(frozen=True)
class ReferenceValidationManifest:
    """The frozen 164-task reference-validation manifest (no development/reference split)."""

    manifest_kind: str
    dataset_provenance: DatasetProvenance
    tasks: tuple[ReferenceValidationTaskEntry, ...]
    generated_at: str
    manifest_checksum: str = ""


def rank_case(
    task_id: str,
    case_id: str,
    partition_algorithm_version: str = PARTITION_ALGORITHM_VERSION,
    partition_seed: str = PARTITION_SEED,
) -> str:
    """Deterministic SHA-256 ranking key for one (task, case) pair.

    Never uses Python's built-in hash() or any platform-dependent
    ordering. Changing the algorithm version or seed changes every
    ranking, and therefore every downstream manifest checksum.
    """
    payload = f"{partition_algorithm_version}|{partition_seed}|{task_id}|{case_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_task_partition(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    task_id: str,
    eligible_cases: Sequence[CaseWithProvenance],
    development_target: int = DEVELOPMENT_TARGET,
    min_reference_only: int = MIN_REFERENCE_ONLY,
    partition_algorithm_version: str = PARTITION_ALGORITHM_VERSION,
    partition_seed: str = PARTITION_SEED,
) -> TaskPartition:
    """Assign one task's eligible cases to development/reference_only pools.

    Applies the identical ranking procedure regardless of provenance — no
    stratification or hand-selection by original-vs-supplementary origin.
    Raises PartitionInfeasibleError (no silent fallback) if the task
    cannot support the required budget.
    """
    total = len(eligible_cases)
    required_minimum = development_target + min_reference_only
    if total < required_minimum:
        raise PartitionInfeasibleError(
            f"{task_id}: only {total} eligible cases; requires at least "
            f"{required_minimum} ({development_target} development + "
            f"{min_reference_only} reference-only)"
        )

    ranked = sorted(
        eligible_cases,
        key=lambda c: rank_case(task_id, c.case_id, partition_algorithm_version, partition_seed),
    )
    development = ranked[:development_target]
    reference_only = ranked[development_target:]

    def _provenance_counts(cases: Sequence[CaseWithProvenance]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for case in cases:
            counts[case.provenance] = counts.get(case.provenance, 0) + 1
        return counts

    return TaskPartition(
        task_id=task_id,
        development_case_ids=tuple(c.case_id for c in development),
        reference_only_case_ids=tuple(c.case_id for c in reference_only),
        development_provenance_counts=_provenance_counts(development),
        reference_only_provenance_counts=_provenance_counts(reference_only),
        total_unique_case_count=total,
    )


class AugmentationReproducibilityError(ValueError):
    """Raised when regenerated evidence doesn't match MEGB-03A.1's frozen checksums."""


def _original_eligible_case_args(task: PrivilegedTaskView) -> dict[str, tuple[Any, ...]]:
    """Deduplicated, EvalPlus-sourced case_id -> args map for a task with no augmentation."""
    seen: dict[str, tuple[Any, ...]] = {}
    for args in list(task.base_input) + list(task.plus_input):
        seen.setdefault(stable_case_id(task.task_id, args), args)
    return seen


def _original_eligible_cases(task: PrivilegedTaskView) -> list[CaseWithProvenance]:
    """Deduplicated, EvalPlus-sourced cases for a task with no augmentation."""
    return [
        CaseWithProvenance(case_id=cid, provenance=PROVENANCE_ORIGINAL)
        for cid in _original_eligible_case_args(task)
    ]


def _augmented_eligible_cases_and_args(
    task_id: str, privileged: PrivilegedTaskView, prompt: str
) -> tuple[list[CaseWithProvenance], TaskAugmentationResult, dict[str, tuple[Any, ...]]]:
    """Regenerate an augmented task's combined case set, deterministically.

    Reruns MEGB-03A.1's exact frozen procedure (task_configs()) rather than
    reading a persisted list, since the whole point of a deterministic
    procedure is that regeneration must reproduce it byte-for-byte — this
    doubles as the "deterministic byte-stable reconstruction" check.
    """
    config = task_configs()[task_id]
    result = augment_task(
        task_id=task_id,
        param_name=config["param_name"],
        contract=privileged.contract,
        prompt=prompt,
        canonical_solution=privileged.canonical_solution,
        entry_point=privileged.entry_point,
        existing_args=list(privileged.base_input) + list(privileged.plus_input),
        raw_candidates=config["raw_candidates"],
    )
    cases = [
        CaseWithProvenance(case_id=cid, provenance=PROVENANCE_ORIGINAL)
        for cid in result.original_case_ids
    ] + [CaseWithProvenance(case_id=c.case_id, provenance=c.provenance) for c in result.accepted]

    args_by_id = dict(_original_eligible_case_args(privileged))
    for generated in result.accepted:
        args_by_id[generated.case_id] = generated.args
    return cases, result, args_by_id


def _augmented_eligible_cases(
    task_id: str, privileged: PrivilegedTaskView, prompt: str
) -> tuple[list[CaseWithProvenance], TaskAugmentationResult]:
    cases, result, _args_by_id = _augmented_eligible_cases_and_args(task_id, privileged, prompt)
    return cases, result


def verify_augmentation_reproducibility(
    results: Mapping[str, TaskAugmentationResult], frozen_results_path: Path
) -> None:
    """Cross-check regenerated augmentation checksums against MEGB-03A.1's committed artifact.

    Raises AugmentationReproducibilityError on any mismatch rather than
    silently proceeding with divergent evidence.
    """
    frozen = json.loads(frozen_results_path.read_text())
    for task_id, result in results.items():
        frozen_task = frozen["tasks"][task_id]
        for field_name in ("original_checksum", "supplementary_checksum", "combined_checksum"):
            current = getattr(result, field_name)
            expected = frozen_task[field_name]
            if current != expected:
                raise AugmentationReproducibilityError(
                    f"{task_id}.{field_name}: regenerated={current!r} "
                    f"!= frozen(MEGB-03A.1)={expected!r}"
                )


def gather_eligible_cases_and_args(
    privileged_by_id: Mapping[str, PrivilegedTaskView], public_by_id: Mapping[str, str]
) -> tuple[
    dict[str, list[CaseWithProvenance]],
    dict[str, TaskAugmentationResult],
    dict[str, dict[str, tuple[Any, ...]]],
]:
    """Gather every task's eligible case set (all 164 tasks), including each case's args.

    Returns (cases_by_task, augmentation_results_for_the_three_augmented_tasks,
    args_by_task). ``args_by_task[task_id][case_id]`` is the actual argument
    tuple behind a case — needed by MEGB-03C to execute the canonical
    solution and construct oracle records; partition assignment itself
    (this module) only ever needs the case_id.
    """
    augmented_task_ids = set(task_configs().keys())
    cases_by_task: dict[str, list[CaseWithProvenance]] = {}
    augmentation_results: dict[str, TaskAugmentationResult] = {}
    args_by_task: dict[str, dict[str, tuple[Any, ...]]] = {}

    for task_id, privileged in privileged_by_id.items():
        if task_id in augmented_task_ids:
            cases, result, args_by_id = _augmented_eligible_cases_and_args(
                task_id, privileged, public_by_id[task_id]
            )
            cases_by_task[task_id] = cases
            augmentation_results[task_id] = result
            args_by_task[task_id] = args_by_id
        else:
            args_by_id = _original_eligible_case_args(privileged)
            cases_by_task[task_id] = [
                CaseWithProvenance(case_id=cid, provenance=PROVENANCE_ORIGINAL)
                for cid in args_by_id
            ]
            args_by_task[task_id] = args_by_id

    return cases_by_task, augmentation_results, args_by_task


def gather_eligible_cases(
    privileged_by_id: Mapping[str, PrivilegedTaskView], public_by_id: Mapping[str, str]
) -> tuple[dict[str, list[CaseWithProvenance]], dict[str, TaskAugmentationResult]]:
    """Gather every task's eligible case set (all 164 tasks).

    Returns (cases_by_task, augmentation_results_for_the_three_augmented_tasks).
    """
    cases_by_task, augmentation_results, _args_by_task = gather_eligible_cases_and_args(
        privileged_by_id, public_by_id
    )
    return cases_by_task, augmentation_results


def _checksum_manifest(payload: Mapping[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _stable_dataset_provenance(dataset_provenance: DatasetProvenance) -> DatasetProvenance:
    """Strip the volatile load timestamp before hashing.

    ``DatasetProvenance.loaded_at`` is set fresh on every call to
    ``load_provenance()`` (a new wall-clock timestamp each process run) —
    embedding it unstripped would make every manifest checksum spuriously
    non-reproducible across separate runs, even with byte-identical
    corpus/code (the same class of bug already found and fixed in
    MEGB-03A's inventory checksum).
    """
    return dataclasses.replace(dataset_provenance, loaded_at="")


def build_reference_validation_manifest(
    cases_by_task: Mapping[str, Sequence[CaseWithProvenance]],
    dataset_provenance: DatasetProvenance,
) -> ReferenceValidationManifest:
    """Build the 164-task, unsplit reference-validation manifest."""
    entries = []
    for task_id in sorted(cases_by_task):
        cases = cases_by_task[task_id]
        counts: dict[str, int] = {}
        for case in cases:
            counts[case.provenance] = counts.get(case.provenance, 0) + 1
        entries.append(
            ReferenceValidationTaskEntry(
                task_id=task_id,
                case_ids=tuple(sorted(c.case_id for c in cases)),
                provenance_counts=counts,
            )
        )

    manifest = ReferenceValidationManifest(
        manifest_kind="reference_validation_task_manifest",
        dataset_provenance=dataset_provenance,
        tasks=tuple(entries),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    stable_payload = dataclasses.asdict(
        dataclasses.replace(
            manifest,
            manifest_checksum="",
            generated_at="",
            dataset_provenance=_stable_dataset_provenance(dataset_provenance),
        )
    )
    return dataclasses.replace(manifest, manifest_checksum=_checksum_manifest(stable_payload))


def build_primary_experiment_manifest(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    cases_by_task: Mapping[str, Sequence[CaseWithProvenance]],
    dataset_provenance: DatasetProvenance,
    excluded_task_id: str = EXCLUDED_TASK_ID,
    development_target: int = DEVELOPMENT_TARGET,
    min_reference_only: int = MIN_REFERENCE_ONLY,
    partition_algorithm_version: str = PARTITION_ALGORITHM_VERSION,
    partition_seed: str = PARTITION_SEED,
) -> PrimaryExperimentManifest:
    """Build the 163-task development/reference_only partition manifest.

    `excluded_task_id` never receives a partition entry here.
    """
    partitions = []
    for task_id in sorted(cases_by_task):
        if task_id == excluded_task_id:
            continue
        partitions.append(
            build_task_partition(
                task_id,
                cases_by_task[task_id],
                development_target=development_target,
                min_reference_only=min_reference_only,
                partition_algorithm_version=partition_algorithm_version,
                partition_seed=partition_seed,
            )
        )

    manifest = PrimaryExperimentManifest(
        manifest_kind="primary_experiment_task_manifest",
        partition_algorithm_version=partition_algorithm_version,
        partition_seed=partition_seed,
        development_target=development_target,
        min_reference_only=min_reference_only,
        dataset_provenance=dataset_provenance,
        task_partitions=tuple(partitions),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    stable_payload = dataclasses.asdict(
        dataclasses.replace(
            manifest,
            manifest_checksum="",
            generated_at="",
            dataset_provenance=_stable_dataset_provenance(dataset_provenance),
        )
    )
    return dataclasses.replace(manifest, manifest_checksum=_checksum_manifest(stable_payload))


def validate_primary_experiment_manifest(
    manifest: PrimaryExperimentManifest, excluded_task_id: str = EXCLUDED_TASK_ID
) -> dict[str, object]:
    """Run the required MEGB-03B validations and return a structured report."""
    task_ids = [p.task_id for p in manifest.task_partitions]
    dev_counts = [len(p.development_case_ids) for p in manifest.task_partitions]
    ref_counts = [len(p.reference_only_case_ids) for p in manifest.task_partitions]
    overlaps = [
        set(p.development_case_ids) & set(p.reference_only_case_ids)
        for p in manifest.task_partitions
    ]
    exhaustive_ok = all(
        len(p.development_case_ids) + len(p.reference_only_case_ids) == p.total_unique_case_count
        for p in manifest.task_partitions
    )

    return {
        "task_count": len(task_ids),
        "task_count_matches_expected": len(task_ids) == EXPECTED_EXPERIMENT_TASK_COUNT,
        "unique_task_ids": len(set(task_ids)) == len(task_ids),
        "all_development_counts_equal_target": set(dev_counts) == {manifest.development_target},
        "min_reference_only_count": min(ref_counts) if ref_counts else None,
        "min_reference_only_satisfies_floor": (
            min(ref_counts) >= manifest.min_reference_only if ref_counts else False
        ),
        "exhaustive_assignment": exhaustive_ok,
        "zero_dev_ref_overlap": all(len(o) == 0 for o in overlaps),
        "excluded_task_absent": excluded_task_id not in task_ids,
    }


def redact_primary_experiment_manifest(manifest: PrimaryExperimentManifest) -> dict[str, object]:
    """Development-facing view: development case IDs only.

    Never includes reference_only_case_ids, raw inputs, expected outputs,
    or oracle data (none of which this module ever stores in the first
    place — only case identifiers).
    """
    return {
        "manifest_kind": "primary_experiment_task_manifest_redacted",
        "partition_algorithm_version": manifest.partition_algorithm_version,
        "development_target": manifest.development_target,
        "tasks": [
            {
                "task_id": p.task_id,
                "development_case_ids": list(p.development_case_ids),
            }
            for p in manifest.task_partitions
        ],
        "source_manifest_checksum": manifest.manifest_checksum,
    }


def render_validation_report(  # pylint: disable=too-many-locals
    experiment_manifest: PrimaryExperimentManifest,
    validation_manifest: ReferenceValidationManifest,
    checks: Mapping[str, object],
    rebuild_checksum: str,
    reseeded_checksum: str,
) -> str:
    """Render the MEGB-03B human-readable partition-validation report."""
    provenance_examples = "\n".join(
        f"- `{p.task_id}`: development={dict(p.development_provenance_counts)}, "
        f"reference_only={dict(p.reference_only_provenance_counts)}"
        for p in experiment_manifest.task_partitions
        if PROVENANCE_SUPPLEMENTARY in p.development_provenance_counts
        or PROVENANCE_SUPPLEMENTARY in p.reference_only_provenance_counts
    )
    deterministic_match = rebuild_checksum == experiment_manifest.manifest_checksum
    seed_changes_identity = reseeded_checksum != experiment_manifest.manifest_checksum

    def _pf(flag: object) -> str:
        return "PASS" if flag else "FAIL"

    rows = [
        (
            f"Exactly {EXPECTED_EXPERIMENT_TASK_COUNT} experimental tasks",
            f"{checks['task_count']} — {_pf(checks['task_count_matches_expected'])}",
        ),
        ("Task IDs unique", _pf(checks["unique_task_ids"])),
        (
            f"Exactly {experiment_manifest.development_target} development cases per task",
            _pf(checks["all_development_counts_equal_target"]),
        ),
        (
            f"At least {experiment_manifest.min_reference_only} reference-only cases per task",
            f"min={checks['min_reference_only_count']} — "
            f"{_pf(checks['min_reference_only_satisfies_floor'])}",
        ),
        (
            "Exhaustive assignment (dev + ref == total unique)",
            _pf(checks["exhaustive_assignment"]),
        ),
        ("Zero development/reference overlap", _pf(checks["zero_dev_ref_overlap"])),
        (
            f"`{EXCLUDED_TASK_ID}` absent from experimental partition",
            _pf(checks["excluded_task_absent"]),
        ),
        (
            "Deterministic byte-stable reconstruction (rebuild, compare checksum)",
            f"rebuild=`{rebuild_checksum}` — {_pf(deterministic_match)}",
        ),
        (
            "Changed seed changes manifest identity",
            f"reseeded=`{reseeded_checksum}` — {_pf(seed_changes_identity)}",
        ),
    ]
    table = "\n".join(f"| {label} | {result} |" for label, result in rows)

    return f"""# MEGB-03B Partition Validation Report

Generated: {experiment_manifest.generated_at}

## Manifests

- `reference_validation_task_manifest`: {len(validation_manifest.tasks)} tasks,
  checksum `{validation_manifest.manifest_checksum}`
- `primary_experiment_task_manifest`: {len(experiment_manifest.task_partitions)} tasks,
  checksum `{experiment_manifest.manifest_checksum}`
- Partition algorithm: `{experiment_manifest.partition_algorithm_version}`,
  seed: `{experiment_manifest.partition_seed}`
- Development target: {experiment_manifest.development_target},
  minimum reference-only: {experiment_manifest.min_reference_only}

## Required validations

| Check | Result |
|---|---|
{table}

## Provenance counts for augmented tasks

{provenance_examples or "(none)"}

## Scope confirmation

No MEGB-04 observation sets were generated, no expected outputs were
constructed, no candidate code was executed, and MEGB-03C was not begun.
This report covers partition assignment only.
"""


def load_real_corpus_inputs() -> tuple[
    Mapping[str, Sequence[CaseWithProvenance]],
    Mapping[str, TaskAugmentationResult],
    DatasetProvenance,
]:
    """Load the pinned corpus and reconstruct the eligible-cases-by-task view.

    Shared by the build/verify CLI (``partition_cli.py``) and anything else
    that needs the same real-corpus inputs used to build the manifests.
    """
    priv = {t.task_id: t for t in load_privileged_view()}
    pub = {t.task_id: t.prompt for t in load_public_view()}
    provenance = load_provenance()
    cases_by_task, augmentation_results = gather_eligible_cases(priv, pub)
    verify_augmentation_reproducibility(augmentation_results, AUGMENTATION_RESULTS_PATH)
    return cases_by_task, augmentation_results, provenance
