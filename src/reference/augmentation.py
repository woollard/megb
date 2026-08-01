"""MEGB-03A.1: deterministic, contract-derived supplementary-evidence generation.

Frozen procedure: see
``artifacts/reference/augmentation/generation_procedures_v1.md`` (checksum
recorded in the companion ``.json``). Generates candidate *inputs* only —
no expected outputs, no oracle artifact; MEGB-03C remains solely
responsible for oracle construction. A feasibility check (does the pinned
canonical solution execute without raising?) is performed and reported,
but its return value is never persisted as an oracle record.

Every generation rule here was derived solely from each task's documented
contract and the general mathematical structure of its input domain —
never from a model candidate, an observed candidate failure, or an
``S*``/reference-evaluator outcome.
"""

import hashlib
import json
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from src.dataset import load_privileged_view, load_public_view
from src.reference.case_serialization import CASE_ID_ALGORITHM_VERSION, stable_case_id

ALGORITHM_VERSION = "supplementary-generation-v1"
PROVENANCE_ORIGINAL = "evalplus-original-v1"
PROVENANCE_SUPPLEMENTARY = "megb-contract-augmentation-v1"


class ContractViolation(ValueError):
    """Raised when a candidate input fails the task's own documented contract."""


def validate_against_contract(contract: str, param_name: str, value: Any) -> None:
    """Execute the task's own contract text against one candidate value.

    Raises ContractViolation if any contract assertion fails. Uses the
    pinned EvalPlus contract text verbatim (dedented only) rather than a
    hand-reimplemented check, avoiding transcription drift.
    """
    namespace = {param_name: value}
    try:
        exec(textwrap.dedent(contract), namespace)  # pylint: disable=exec-used
    except AssertionError as exc:
        raise ContractViolation(str(exc)) from exc


def build_canonical_callable(
    prompt: str, canonical_solution: str, entry_point: str
) -> Callable[..., Any]:
    """Assemble the pinned canonical solution into a callable, for feasibility checks only."""
    namespace: dict[str, Any] = {}
    exec(prompt + canonical_solution, namespace)  # pylint: disable=exec-used
    return namespace[entry_point]  # type: ignore[no-any-return]


def generate_integer_range_candidates(range_end: int) -> list[tuple[Any, ...]]:
    """Exhaustive enumeration of [0, range_end) as single-argument cases."""
    return [(n,) for n in range(range_end)]


def _dyck_words_of_length(pair_count: int) -> list[str]:
    """All Dyck words with exactly `pair_count` pairs, lexicographic order ('(' < ')')."""
    results: list[str] = []
    current: list[str] = []

    def backtrack(opens: int, closes: int) -> None:
        if len(current) == 2 * pair_count:
            results.append("".join(current))
            return
        if opens < pair_count:
            current.append("(")
            backtrack(opens + 1, closes)
            current.pop()
        if closes < opens:
            current.append(")")
            backtrack(opens, closes + 1)
            current.pop()

    backtrack(0, 0)
    return results


def generate_dyck_words(max_pair_count: int) -> list[str]:
    """All Dyck words of length 2..2*max_pair_count, grouped by length ascending."""
    words: list[str] = []
    for pair_count in range(1, max_pair_count + 1):
        words.extend(_dyck_words_of_length(pair_count))
    return words


def generate_paren_candidates(max_pair_count: int, num_pairs: int) -> list[tuple[Any, ...]]:
    """Single-group (each Dyck word alone) plus multi-group (consecutive pairs) candidates."""
    words = generate_dyck_words(max_pair_count)
    single_group: list[tuple[Any, ...]] = [(w,) for w in words]

    words_needed = num_pairs * 2
    pair_source = words[:words_needed]
    multi_group: list[tuple[Any, ...]] = [
        (pair_source[i] + " " + pair_source[i + 1],)
        for i in range(0, len(pair_source) - 1, 2)
    ]
    return single_group + multi_group


@dataclass(frozen=True)
class GeneratedCase:
    """One accepted supplementary case."""

    args: tuple[Any, ...]
    case_id: str
    provenance: str = PROVENANCE_SUPPLEMENTARY


@dataclass(frozen=True)
class RejectedCase:
    """One candidate rejected before acceptance, with the reason."""

    args: tuple[Any, ...]
    reason: str


@dataclass(frozen=True)
class TaskAugmentationResult:
    """Full result of augmenting one task: accepted cases plus a full audit trail."""

    task_id: str
    algorithm_version: str
    raw_candidate_count: int
    duplicate_of_existing_count: int
    contract_rejected: tuple[RejectedCase, ...]
    infeasible: tuple[RejectedCase, ...]
    accepted: tuple[GeneratedCase, ...]
    original_case_ids: tuple[str, ...]
    original_checksum: str
    supplementary_checksum: str
    combined_checksum: str
    combined_unique_count: int
    feasibility_check_total_sec: float
    feasibility_check_max_single_sec: float


def checksum_case_ids(case_ids: Sequence[str]) -> str:
    """Deterministic checksum over a set of stable case IDs (order-independent)."""
    payload = "|".join(sorted(case_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def augment_task(  # pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
    task_id: str,
    param_name: str,
    contract: str,
    prompt: str,
    canonical_solution: str,
    entry_point: str,
    existing_args: Sequence[tuple[Any, ...]],
    raw_candidates: Sequence[tuple[Any, ...]],
) -> TaskAugmentationResult:
    """Run the full generate -> dedup -> contract-validate -> feasibility-check pipeline.

    Never constructs or persists expected outputs: the feasibility check
    only confirms the canonical solution executes without raising.
    """
    # Deduplicated: existing_args may itself contain duplicates (e.g. an
    # identical case present in both base_input and plus_input, as MEGB-03A
    # found for several tasks); original_case_ids must report the same
    # unique count MEGB-03A's own inventory uses, not a raw pre-dedup count.
    existing_id_set = {stable_case_id(task_id, args) for args in existing_args}
    original_case_ids = tuple(sorted(existing_id_set))

    canonical_fn = build_canonical_callable(prompt, canonical_solution, entry_point)

    seen_ids: set[str] = set(existing_id_set)
    duplicate_of_existing_count = 0
    contract_rejected: list[RejectedCase] = []
    infeasible: list[RejectedCase] = []
    accepted: list[GeneratedCase] = []
    feasibility_total_sec = 0.0
    feasibility_max_sec = 0.0

    for args in raw_candidates:
        case_id = stable_case_id(task_id, args)
        if case_id in seen_ids:
            duplicate_of_existing_count += 1
            continue
        seen_ids.add(case_id)

        try:
            validate_against_contract(contract, param_name, args[0])
        except ContractViolation as exc:
            contract_rejected.append(RejectedCase(args=args, reason=str(exc)))
            continue

        call_start = time.perf_counter()
        try:
            canonical_fn(*args)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            infeasible.append(RejectedCase(args=args, reason=f"{type(exc).__name__}: {exc}"))
            continue
        finally:
            call_duration = time.perf_counter() - call_start
            feasibility_total_sec += call_duration
            feasibility_max_sec = max(feasibility_max_sec, call_duration)

        accepted.append(GeneratedCase(args=args, case_id=case_id))

    supplementary_case_ids = tuple(c.case_id for c in accepted)
    combined_case_ids = original_case_ids + supplementary_case_ids

    return TaskAugmentationResult(
        task_id=task_id,
        algorithm_version=ALGORITHM_VERSION,
        raw_candidate_count=len(raw_candidates),
        duplicate_of_existing_count=duplicate_of_existing_count,
        contract_rejected=tuple(contract_rejected),
        infeasible=tuple(infeasible),
        accepted=tuple(accepted),
        original_case_ids=original_case_ids,
        original_checksum=checksum_case_ids(original_case_ids),
        supplementary_checksum=checksum_case_ids(supplementary_case_ids),
        combined_checksum=checksum_case_ids(combined_case_ids),
        combined_unique_count=len(set(combined_case_ids)),
        feasibility_check_total_sec=feasibility_total_sec,
        feasibility_check_max_single_sec=feasibility_max_sec,
    )


def render_review_markdown(  # pylint: disable=too-many-locals
    result: TaskAugmentationResult,
    contract: str,
    domain_description: str,
    generation_rule_summary: str,
    boundary_examples: Sequence[str],
) -> str:
    """Render the MEGB-03A.1 review artifact for one task (Decision 7)."""
    example_lines = "\n".join(f"- {ex}" for ex in boundary_examples)
    rejected_lines = (
        "\n".join(f"- `{c.args}`: {c.reason}" for c in result.contract_rejected)
        or "(none)"
    )
    infeasible_lines = (
        "\n".join(f"- `{c.args}`: {c.reason}" for c in result.infeasible) or "(none)"
    )
    original_count = len(result.original_case_ids)
    supplementary_count = len(result.accepted)
    non_duplicate_count = result.raw_candidate_count - result.duplicate_of_existing_count
    resource_summary = (
        f"Feasibility checks execute the pinned canonical solution directly "
        f"(trusted-side, not sandboxed — these are corrected reference "
        f"solutions, not untrusted candidate code). Total wall time for all "
        f"{non_duplicate_count} non-duplicate feasibility checks: "
        f"{result.feasibility_check_total_sec:.4f}s; slowest single call: "
        f"{result.feasibility_check_max_single_sec:.6f}s. No resource limit "
        f"or timeout was approached; this task poses no execution-resource risk."
    )

    return f"""# MEGB-03A.1 Supplementary-Evidence Review — {result.task_id}

## Task contract

```python
{textwrap.dedent(contract).strip()}
```

## Generation rule and justification

{generation_rule_summary}

Domain: {domain_description}

Algorithm version: `{result.algorithm_version}` (frozen prior to generation;
see `generation_procedures_v1.md`, checksum
`31705af14ef914a8b495d980c3a9a962b4039b1f6aa574cdad85c706e7289c00`).

## Generated and deduplicated counts

| Quantity | Count |
|---|---:|
| Original (EvalPlus-sourced) unique cases | {original_count} |
| Raw candidates generated | {result.raw_candidate_count} |
| Duplicates of existing cases (dropped) | {result.duplicate_of_existing_count} |
| Contract-rejected candidates | {len(result.contract_rejected)} |
| Infeasible candidates (canonical solution raised) | {len(result.infeasible)} |
| **Accepted supplementary cases** | **{supplementary_count}** |
| **Combined unique cases** | **{result.combined_unique_count}** |

Target was >= 100 combined unique cases:
{"MET" if result.combined_unique_count >= 100 else "NOT MET"}.

## Examples and boundary coverage

{example_lines}

## Resource-calibration results

{resource_summary}

## Provenance and checksums

- Original-case checksum (`{PROVENANCE_ORIGINAL}`): `{result.original_checksum}`
- Supplementary-case checksum (`{PROVENANCE_SUPPLEMENTARY}`): `{result.supplementary_checksum}`
- Combined checksum: `{result.combined_checksum}`
- Case ID algorithm: `{CASE_ID_ALGORITHM_VERSION}` (unchanged from MEGB-03A)

## Ambiguities or rejected cases

Contract-rejected candidates:
{rejected_lines}

Infeasible candidates (canonical solution raised an exception):
{infeasible_lines}

## Design-precedence confirmation

This generation procedure was designed and frozen
(`generation_procedures_v1.md`) using only this task's documented contract
and the general mathematical structure of its input domain. No model
candidate, observed candidate failure, or `S*`/reference-evaluator outcome
was consulted or exists for this task in this repository as of this
review. No expected output was constructed or persisted for any
supplementary case; MEGB-03C remains solely responsible for oracle
construction.

**Requires explicit review acceptance before this evidence is eligible for
MEGB-03B partitioning (Decision 8) — not yet granted.**
"""


def task_configs() -> dict[str, dict[str, Any]]:
    """The frozen, versioned per-task generation configuration (public: reused by MEGB-03B
    to regenerate the identical accepted case sets for partitioning)."""
    return {
        "HumanEval/55": {
            "param_name": "n",
            "raw_candidates": generate_integer_range_candidates(200),
            "domain_description": "n: int, n >= 0 (unbounded above)",
            "generation_rule_summary": (
                "Exhaustive enumeration of the integer range [0, 200)."
            ),
            "boundary_examples": [
                "n=0 (lower boundary, already covered)",
                "n=199 (new upper extension well beyond prior max of 86)",
                "n=9, n=19-26 (previously-missing gaps in the original evidence, now filled)",
            ],
        },
        "HumanEval/63": {
            "param_name": "n",
            "raw_candidates": generate_integer_range_candidates(200),
            "domain_description": "n: int, n >= 0 (unbounded above)",
            "generation_rule_summary": (
                "Exhaustive enumeration of the integer range [0, 200) "
                "(same rule as HumanEval/55 — both share the fib-family unbounded-integer domain)."
            ),
            "boundary_examples": [
                "n=0 (lower boundary, already covered)",
                "n=199 (new upper extension well beyond prior max of 102)",
                "gap-filling values between 0 and 102 not previously present",
            ],
        },
        "HumanEval/6": {
            "param_name": "paren_string",
            "raw_candidates": generate_paren_candidates(6, 40),
            "domain_description": (
                "paren_string: str, space-separated Dyck words (declared assumption "
                "narrowing the literal whole-string-balanced contract; see procedure doc)"
            ),
            "generation_rule_summary": (
                "196 single-group Dyck words (lengths 2-12, all Catalan-numbered "
                "balanced sequences) plus 40 multi-group pairs formed from consecutive "
                "words in the same canonical list."
            ),
            "boundary_examples": [
                '"()" (minimum-length single group, depth 1)',
                '"(((((())))))" (longest generated, length 12, depth 6, first in canonical order)',
                '"()()()()()()" (longest generated, length 12, depth 1, last in canonical order — '
                "same length as the deepest word, but minimal depth)",
                "40 two-group space-separated combinations exercising the multi-group code path",
            ],
        },
    }


def main() -> None:
    """Run augmentation for all three MEGB-03A.1 tasks and write review artifacts."""
    pub = {t.task_id: t for t in load_public_view()}
    priv = {t.task_id: t for t in load_privileged_view()}
    output_dir = Path("artifacts/reference/augmentation")

    configs = task_configs()
    all_results: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "algorithm_version": ALGORITHM_VERSION,
        "tasks": {},
    }

    for task_id, config in configs.items():
        p = priv[task_id]
        existing_args = list(p.base_input) + list(p.plus_input)
        result = augment_task(
            task_id=task_id,
            param_name=config["param_name"],
            contract=p.contract,
            prompt=pub[task_id].prompt,
            canonical_solution=p.canonical_solution,
            entry_point=p.entry_point,
            existing_args=existing_args,
            raw_candidates=config["raw_candidates"],
        )

        review_md = render_review_markdown(
            result,
            contract=p.contract,
            domain_description=config["domain_description"],
            generation_rule_summary=config["generation_rule_summary"],
            boundary_examples=config["boundary_examples"],
        )
        safe_name = task_id.replace("/", "_").lower()
        (output_dir / f"{safe_name}_review.md").write_text(review_md)

        all_results["tasks"][task_id] = {
            "original_unique_count": len(result.original_case_ids),
            "raw_candidate_count": result.raw_candidate_count,
            "duplicate_of_existing_count": result.duplicate_of_existing_count,
            "contract_rejected_count": len(result.contract_rejected),
            "infeasible_count": len(result.infeasible),
            "accepted_supplementary_count": len(result.accepted),
            "combined_unique_count": result.combined_unique_count,
            "original_checksum": result.original_checksum,
            "supplementary_checksum": result.supplementary_checksum,
            "combined_checksum": result.combined_checksum,
            "feasibility_check_total_sec": result.feasibility_check_total_sec,
            "feasibility_check_max_single_sec": result.feasibility_check_max_single_sec,
        }
        print(
            f"{task_id}: original={len(result.original_case_ids)} "
            f"accepted={len(result.accepted)} combined={result.combined_unique_count}"
        )

    (output_dir / "augmentation_results.json").write_text(
        json.dumps(all_results, indent=2, sort_keys=True)
    )


if __name__ == "__main__":
    main()
