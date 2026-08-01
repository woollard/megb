"""MEGB-03A: evidence inventory and development/reference partition feasibility.

Analysis and artifact generation only. Does not assign cases to
development or reference-only pools (MEGB-03B), does not construct
expected outputs (MEGB-03C), and does not execute candidate code.

Per the epic's "No silent fallback" policy: a task that cannot support the
minimum development + reference-only evidence budget is reported as
``BLOCKED`` with its true case count — never silently downgraded or
dropped from the inventory.
"""

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from src.dataset import DatasetProvenance, PrivilegedTaskView, load_privileged_view, load_provenance
from src.reference.case_serialization import (
    CASE_ID_ALGORITHM_VERSION,
    canonical_case_representation,
    stable_case_id,
)

INVENTORY_ALGORITHM_VERSION = "megb-03a-inventory-v1"

_MUTATION_SENSITIVITY_UNAVAILABLE = (
    "unknown: not exposed by the currently integrated EvalPlus fields "
    "(base_input/plus_input carry no per-case generation-strategy tag)"
)


class CaseIdCollisionError(ValueError):
    """Raised when two different cases hash to the same stable case ID.

    Should not occur with SHA-256; this is a defensive check, not an
    expected runtime path.
    """


@dataclass(frozen=True)
class PartitionFeasibilityPolicy:
    """Recommended (not frozen) policy MEGB-03A evaluates feasibility against.

    ``target_development_cases`` is deliberately exactly
    ``num_o4_replicates * o4_replicate_size``: a development pool at least
    this large can support ``num_o4_replicates`` fully *disjoint* replicates
    of size ``o4_replicate_size``, the strongest and most easily justified
    reading of MEGB-04's "differ meaningfully" requirement (zero shared
    cases). Below this target but at or above ``min_development_cases``,
    replicates would need to overlap.
    """

    min_development_cases: int = 30
    min_reference_only_cases: int = 20
    num_o4_replicates: int = 5
    o4_replicate_size: int = 30
    target_development_cases: int = 150  # 5 * 30


DEFAULT_POLICY = PartitionFeasibilityPolicy()


@dataclass(frozen=True)
class DuplicateCaseGroup:
    """Two or more (source, index) occurrences sharing one stable case ID."""

    case_id: str
    occurrences: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class TaskCaseInventory:
    """Per-task evidence inventory and partition-feasibility classification."""

    task_id: str
    base_case_count: int
    plus_case_count: int
    unique_combined_case_count: int
    duplicate_groups: tuple[DuplicateCaseGroup, ...]
    contract: str
    atol: float
    mutation_sensitive_info: str
    minimum_available_cases_after_dedup: int
    feasibility: str  # "OK" | "LIMITED" | "BLOCKED"
    feasibility_reason: str
    recommended_development_cases: int
    recommended_reference_only_cases: int


@dataclass(frozen=True)
class EvidenceInventory:
    """Complete MEGB-03A inventory artifact: all 164 tasks plus provenance."""

    inventory_algorithm_version: str
    case_id_algorithm_version: str
    dataset_provenance: DatasetProvenance
    expected_task_count: int
    policy: PartitionFeasibilityPolicy
    tasks: tuple[TaskCaseInventory, ...]
    generated_at: str
    artifact_checksum: str = ""


def _collect_cases(task: PrivilegedTaskView) -> list[tuple[str, int, tuple[Any, ...]]]:
    """Return (source, index, args) triples for every base+plus case of a task."""
    cases: list[tuple[str, int, tuple[Any, ...]]] = []
    for index, args in enumerate(task.base_input):
        cases.append(("base", index, args))
    for index, args in enumerate(task.plus_input):
        cases.append(("plus", index, args))
    return cases


def _classify_feasibility(
    unique_count: int, policy: PartitionFeasibilityPolicy
) -> tuple[str, str, int, int]:
    """Classify one task's feasibility. Returns (status, reason, dev_count, ref_count)."""
    required_minimum = policy.min_development_cases + policy.min_reference_only_cases
    if unique_count < required_minimum:
        return (
            "BLOCKED",
            f"only {unique_count} unique cases available; requires at least "
            f"{policy.min_development_cases} development + "
            f"{policy.min_reference_only_cases} reference-only "
            f"({required_minimum} total)",
            0,
            0,
        )

    reference_only = policy.min_reference_only_cases
    development = unique_count - reference_only
    if development >= policy.target_development_cases:
        surplus = development - policy.target_development_cases
        development = policy.target_development_cases
        reference_only += surplus
        return (
            "OK",
            f"supports {policy.num_o4_replicates} fully disjoint "
            f"{policy.o4_replicate_size}-case O4 replicates",
            development,
            reference_only,
        )

    return (
        "LIMITED",
        f"only {development} development cases available "
        f"(< target {policy.target_development_cases}); "
        f"{policy.num_o4_replicates} fully disjoint "
        f"{policy.o4_replicate_size}-case O4 replicates not possible, "
        "overlapping replicates would be required",
        development,
        reference_only,
    )


def _inventory_one_task(  # pylint: disable=too-many-locals
    task: PrivilegedTaskView, policy: PartitionFeasibilityPolicy
) -> TaskCaseInventory:
    cases = _collect_cases(task)

    canonical_by_case_id: dict[str, str] = {}
    occurrences_by_case_id: dict[str, list[tuple[str, int]]] = {}
    for source, index, args in cases:
        case_id = stable_case_id(task.task_id, args)
        canonical = canonical_case_representation(task.task_id, args)
        if case_id in canonical_by_case_id:
            if canonical_by_case_id[case_id] != canonical:
                raise CaseIdCollisionError(
                    f"case ID collision for task {task.task_id}: "
                    f"case_id={case_id!r} maps to two different cases"
                )
            occurrences_by_case_id[case_id].append((source, index))
        else:
            canonical_by_case_id[case_id] = canonical
            occurrences_by_case_id[case_id] = [(source, index)]

    duplicate_groups = tuple(
        DuplicateCaseGroup(case_id=case_id, occurrences=tuple(occurrences))
        for case_id, occurrences in occurrences_by_case_id.items()
        if len(occurrences) > 1
    )
    unique_count = len(canonical_by_case_id)

    feasibility, reason, dev_count, ref_count = _classify_feasibility(unique_count, policy)

    return TaskCaseInventory(
        task_id=task.task_id,
        base_case_count=len(task.base_input),
        plus_case_count=len(task.plus_input),
        unique_combined_case_count=unique_count,
        duplicate_groups=duplicate_groups,
        contract=task.contract,
        atol=task.atol,
        mutation_sensitive_info=_MUTATION_SENSITIVITY_UNAVAILABLE,
        minimum_available_cases_after_dedup=unique_count,
        feasibility=feasibility,
        feasibility_reason=reason,
        recommended_development_cases=dev_count,
        recommended_reference_only_cases=ref_count,
    )


def _compute_checksum(inventory: EvidenceInventory) -> str:
    """Checksum over stable content only.

    Excludes ``artifact_checksum`` (the field being computed) and
    ``generated_at`` (a wall-clock timestamp that legitimately differs
    between otherwise-identical runs) — including either would make the
    checksum spuriously non-reproducible.
    """
    stable = dataclasses.replace(inventory, artifact_checksum="", generated_at="")
    payload = json.dumps(
        dataclasses.asdict(stable),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_evidence_inventory(
    tasks: Sequence[PrivilegedTaskView],
    provenance: DatasetProvenance,
    policy: PartitionFeasibilityPolicy = DEFAULT_POLICY,
    expected_task_count: int = 164,
) -> EvidenceInventory:
    """Build the evidence inventory for a given set of tasks.

    Pure function: takes tasks/provenance directly, so it is unit-testable
    with synthetic tasks independently of network access or the real
    pinned corpus.
    """
    task_inventories = tuple(_inventory_one_task(task, policy) for task in tasks)
    inventory = EvidenceInventory(
        inventory_algorithm_version=INVENTORY_ALGORITHM_VERSION,
        case_id_algorithm_version=CASE_ID_ALGORITHM_VERSION,
        dataset_provenance=provenance,
        expected_task_count=expected_task_count,
        policy=policy,
        tasks=task_inventories,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    return dataclasses.replace(inventory, artifact_checksum=_compute_checksum(inventory))


def load_and_build_evidence_inventory(
    policy: PartitionFeasibilityPolicy = DEFAULT_POLICY,
) -> EvidenceInventory:
    """Build the evidence inventory from the real, pinned MEGB-01 corpus."""
    tasks = load_privileged_view()
    provenance = load_provenance()
    return build_evidence_inventory(tasks, provenance, policy)


def render_feasibility_report(inventory: EvidenceInventory) -> str:
    """Render a human-readable Markdown feasibility report."""
    blocked = [t for t in inventory.tasks if t.feasibility == "BLOCKED"]
    limited = [t for t in inventory.tasks if t.feasibility == "LIMITED"]
    ok = [t for t in inventory.tasks if t.feasibility == "OK"]
    duplicates = [t for t in inventory.tasks if t.duplicate_groups]

    lines = [
        "# MEGB-03A Evidence Inventory and Partition Feasibility Report",
        "",
        f"Generated: {inventory.generated_at}",
        f"Inventory algorithm version: {inventory.inventory_algorithm_version}",
        f"Case ID algorithm version: {inventory.case_id_algorithm_version}",
        f"Dataset (HumanEval) package version: "
        f"{inventory.dataset_provenance.human_eval_package_version}",
        f"Dataset (EvalPlus) package version: "
        f"{inventory.dataset_provenance.evalplus_package_version}",
        f"EvalPlus dataset version: {inventory.dataset_provenance.evalplus_dataset_version}",
        f"EvalPlus dataset hash: {inventory.dataset_provenance.evalplus_dataset_hash}",
        f"Artifact checksum: {inventory.artifact_checksum}",
        "",
        "## Policy evaluated",
        "",
        f"- Minimum development cases: {inventory.policy.min_development_cases}",
        f"- Minimum reference-only cases: {inventory.policy.min_reference_only_cases}",
        f"- Target development cases (for {inventory.policy.num_o4_replicates} disjoint "
        f"{inventory.policy.o4_replicate_size}-case O4 replicates): "
        f"{inventory.policy.target_development_cases}",
        "",
        "## Summary",
        "",
        f"- Tasks inventoried: {len(inventory.tasks)} (expected {inventory.expected_task_count})",
        f"- OK (supports disjoint O4 replicates): {len(ok)}",
        f"- LIMITED (meets minimum, overlapping replicates only): {len(limited)}",
        f"- BLOCKED (cannot meet minimum development + reference-only budget): {len(blocked)}",
        f"- Tasks with duplicate cases: {len(duplicates)}",
        "",
    ]

    if blocked:
        lines.append("## BLOCKED tasks (partition construction cannot proceed for these)")
        lines.append("")
        lines.append(
            "Per the epic's no-silent-fallback policy, these tasks are reported "
            "explicitly rather than silently reduced or excluded. MEGB-03B must "
            "not freeze a partition until each is resolved by an explicit, "
            "approved design amendment."
        )
        lines.append("")
        for t in blocked:
            lines.append(
                f"- `{t.task_id}`: {t.unique_combined_case_count} unique cases "
                f"(base={t.base_case_count}, plus={t.plus_case_count}) — {t.feasibility_reason}"
            )
        lines.append("")

    if limited:
        lines.append("## LIMITED tasks (feasible, but only with overlapping O4 replicates)")
        lines.append("")
        for t in limited:
            lines.append(
                f"- `{t.task_id}`: {t.unique_combined_case_count} unique cases — "
                f"{t.feasibility_reason}"
            )
        lines.append("")

    if duplicates:
        lines.append("## Tasks with duplicate cases")
        lines.append("")
        for t in duplicates:
            lines.append(f"- `{t.task_id}`: {len(t.duplicate_groups)} duplicate case group(s)")
        lines.append("")

    return "\n".join(lines)


def write_inventory_artifacts(inventory: EvidenceInventory, output_dir: Path) -> None:
    """Write the machine-readable inventory, recommended config, and report."""
    output_dir.mkdir(parents=True, exist_ok=True)

    inventory_path = output_dir / "evidence_inventory.json"
    inventory_path.write_text(
        json.dumps(dataclasses.asdict(inventory), indent=2, sort_keys=True, default=str) + "\n"
    )

    config = {
        "inventory_algorithm_version": inventory.inventory_algorithm_version,
        "case_id_algorithm_version": inventory.case_id_algorithm_version,
        "policy": dataclasses.asdict(inventory.policy),
        "dataset_version": inventory.dataset_provenance.evalplus_dataset_version,
        "dataset_checksum": inventory.dataset_provenance.evalplus_dataset_hash,
        "artifact_checksum": inventory.artifact_checksum,
        "per_task_recommendation": [
            {
                "task_id": t.task_id,
                "feasibility": t.feasibility,
                "recommended_development_cases": t.recommended_development_cases,
                "recommended_reference_only_cases": t.recommended_reference_only_cases,
            }
            for t in inventory.tasks
        ],
    }
    config_path = output_dir / "recommended_partition_config.json"
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")

    report_path = output_dir / "feasibility_report.md"
    report_path.write_text(render_feasibility_report(inventory))


def main() -> None:
    """Regenerate the MEGB-03A inventory artifacts from the real pinned corpus."""
    inventory = load_and_build_evidence_inventory()
    write_inventory_artifacts(inventory, Path("artifacts/reference"))
    print(render_feasibility_report(inventory))


if __name__ == "__main__":
    main()
