"""Ingestion, validation, and privilege-boundary enforcement for the HumanEval corpus.

Integrates two pinned upstream sources (see ``requirements.txt``):

* ``human-eval`` (openai/human-eval) — the original 164 HumanEval tasks.
* ``evalplus`` (evalplus/evalplus) — the HumanEval+ expanded test evidence,
  corrected canonical solutions, input contracts, and comparison tolerances.

HumanEval+ is authoritative for ``prompt``, ``canonical_solution``, and the
expanded test evidence: EvalPlus ships independently authored, verified
reference solutions (not merely a small patch set over the originals), a
fact confirmed empirically during MEGB-01 (see
``docs/decisions/0001-humaneval-corpus-and-privilege-boundary.md``) and
consistent with MEGB-03's explicit instruction to score against "the
corrected EvalPlus canonical solutions". The original human-eval package is
used as a structural cross-check (task_id set and entry_point must match
exactly) and as the source of the single original "public example" test
string used by weaker measurement systems (e.g. S1).

The module exposes exactly two data views, per ARCHITECTURE.md Section 2 and
CLAUDE.md's non-negotiable rule that S*'s evidence must never reach the
optimization process:

* :func:`load_public_view` — the only interface optimizer and
  candidate-generation code may use. Returns ``PublicTaskView`` records,
  which structurally cannot carry canonical solutions or test evidence.
* :func:`load_privileged_view` — canonical solutions, HumanEval+ test
  evidence, contracts, and tolerances. Must only be called by privileged
  evaluator code (the gold evaluator and later measurement systems), never by
  the optimization loop.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from typing import Any, Mapping, Sequence

import human_eval.data
from evalplus.data import get_human_eval_plus, get_human_eval_plus_hash
from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION

EXPECTED_TASK_COUNT = 164

_REQUIRED_HUMAN_EVAL_FIELDS = frozenset(
    {"task_id", "prompt", "entry_point", "canonical_solution", "test"}
)
_REQUIRED_HUMAN_EVAL_PLUS_FIELDS = frozenset(
    {
        "task_id",
        "prompt",
        "entry_point",
        "canonical_solution",
        "contract",
        "atol",
        "base_input",
        "plus_input",
    }
)


class DatasetValidationError(ValueError):
    """Raised when the HumanEval / HumanEval+ corpora fail structural validation."""


@dataclass(frozen=True)
class PublicTaskView:
    """The public optimization view of one HumanEval task.

    Contains only the evidence authorized for candidate generation and
    measurement-system selection. Deliberately excludes canonical solutions
    and any test evidence.
    """

    task_id: str
    prompt: str
    entry_point: str


@dataclass(frozen=True)
class PrivilegedTaskView:
    """The privileged reference view of one HumanEval task.

    Carries canonical solutions and HumanEval+ test evidence. Must only be
    consumed by privileged evaluator code.
    """

    task_id: str
    entry_point: str
    canonical_solution: str
    original_test: str
    contract: str
    atol: float
    base_input: tuple[tuple[Any, ...], ...]
    plus_input: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True)
class DatasetProvenance:
    """Recorded package/dataset provenance for one loaded corpus.

    ``human_eval_prompt_diff_count`` and
    ``human_eval_canonical_solution_diff_count`` record how many of the 164
    tasks have textually different ``prompt`` / ``canonical_solution``
    content between the two upstream sources. These are expected to be
    nonzero: EvalPlus intentionally corrects a small number of prompts and
    supplies independently authored canonical solutions for the majority of
    tasks. They are recorded as diagnostics, not validation failures.
    """

    human_eval_package_version: str
    human_eval_dataset_sha256: str
    human_eval_commit_sha: str | None
    evalplus_package_version: str
    evalplus_dataset_version: str
    evalplus_dataset_hash: str
    expected_task_count: int
    human_eval_prompt_diff_count: int
    human_eval_canonical_solution_diff_count: int
    loaded_at: str


@dataclass(frozen=True)
class _HumanEvalCorpus:
    """Internal bundle tying both views to one provenance record."""

    provenance: DatasetProvenance
    public_tasks: tuple[PublicTaskView, ...]
    privileged_tasks: tuple[PrivilegedTaskView, ...]


def _index_by_task_id(
    records: Sequence[Mapping[str, Any]], source_name: str
) -> dict[str, Mapping[str, Any]]:
    """Build a task_id-indexed dict from raw records, rejecting duplicates."""
    index: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if "task_id" not in record:
            raise DatasetValidationError(f"{source_name}: record missing 'task_id' field")
        task_id = record["task_id"]
        if task_id in index:
            raise DatasetValidationError(f"{source_name}: duplicate task_id '{task_id}'")
        index[task_id] = record
    return index


def _require_exact_task_count(
    index: Mapping[str, Any], source_name: str, expected_task_count: int
) -> None:
    if len(index) != expected_task_count:
        raise DatasetValidationError(
            f"{source_name}: expected {expected_task_count} tasks, found {len(index)}"
        )


def _require_fields(
    record: Mapping[str, Any], required_fields: frozenset[str], task_id: str, source_name: str
) -> None:
    missing = required_fields - record.keys()
    if missing:
        raise DatasetValidationError(
            f"{task_id} ({source_name}): missing required fields {sorted(missing)}"
        )


@dataclass(frozen=True)
class _ValidatedCorpus:
    """Result of validating and merging the two raw upstream corpora."""

    public_tasks: tuple[PublicTaskView, ...]
    privileged_tasks: tuple[PrivilegedTaskView, ...]
    human_eval_prompt_diff_count: int
    human_eval_canonical_solution_diff_count: int


def _validate_and_build(
    raw_human_eval: Sequence[Mapping[str, Any]],
    raw_human_eval_plus: Sequence[Mapping[str, Any]],
    expected_task_count: int = EXPECTED_TASK_COUNT,
) -> _ValidatedCorpus:
    """Validate raw HumanEval / HumanEval+ records and build the two data views.

    HumanEval+ (``raw_human_eval_plus``) is authoritative for ``prompt`` and
    ``canonical_solution``. HumanEval (``raw_human_eval``) is used as a
    structural cross-check (task_id set and entry_point must match exactly)
    and as the source of ``original_test``.

    Pure function: takes raw records (not yet deduplicated), so it can detect
    malformed, missing, and duplicate records independently of network access.

    Raises:
        DatasetValidationError: if the corpora are malformed, incomplete, or
            structurally misaligned with each other.
    """
    he_index = _index_by_task_id(raw_human_eval, "HumanEval")
    hep_index = _index_by_task_id(raw_human_eval_plus, "HumanEval+")

    _require_exact_task_count(he_index, "HumanEval", expected_task_count)
    _require_exact_task_count(hep_index, "HumanEval+", expected_task_count)

    if he_index.keys() != hep_index.keys():
        diff = set(he_index) ^ set(hep_index)
        raise DatasetValidationError(
            f"task_id sets differ between HumanEval and HumanEval+: {sorted(diff)}"
        )

    public_tasks = []
    privileged_tasks = []
    prompt_diff_count = 0
    canonical_solution_diff_count = 0
    for task_id in sorted(he_index):
        he_record = he_index[task_id]
        hep_record = hep_index[task_id]
        _require_fields(he_record, _REQUIRED_HUMAN_EVAL_FIELDS, task_id, "HumanEval")
        _require_fields(hep_record, _REQUIRED_HUMAN_EVAL_PLUS_FIELDS, task_id, "HumanEval+")

        if he_record["entry_point"] != hep_record["entry_point"]:
            raise DatasetValidationError(
                f"{task_id}: entry_point mismatch between HumanEval and HumanEval+"
            )
        if he_record["prompt"] != hep_record["prompt"]:
            prompt_diff_count += 1
        if he_record["canonical_solution"] != hep_record["canonical_solution"]:
            canonical_solution_diff_count += 1

        public_tasks.append(
            PublicTaskView(
                task_id=task_id,
                prompt=hep_record["prompt"],
                entry_point=hep_record["entry_point"],
            )
        )
        privileged_tasks.append(
            PrivilegedTaskView(
                task_id=task_id,
                entry_point=hep_record["entry_point"],
                canonical_solution=hep_record["canonical_solution"],
                original_test=he_record["test"],
                contract=hep_record["contract"],
                atol=float(hep_record["atol"]),
                base_input=tuple(tuple(case) for case in hep_record["base_input"]),
                plus_input=tuple(tuple(case) for case in hep_record["plus_input"]),
            )
        )

    return _ValidatedCorpus(
        public_tasks=tuple(public_tasks),
        privileged_tasks=tuple(privileged_tasks),
        human_eval_prompt_diff_count=prompt_diff_count,
        human_eval_canonical_solution_diff_count=canonical_solution_diff_count,
    )


def _load_raw_human_eval_records() -> list[Mapping[str, Any]]:
    """Stream raw HumanEval records from the installed human-eval package.

    Uses ``stream_jsonl`` rather than ``read_problems`` so duplicate task_ids
    in the underlying file are visible to validation instead of being
    silently collapsed by dict construction.
    """
    return list(human_eval.data.stream_jsonl(human_eval.data.HUMAN_EVAL))


def _load_raw_human_eval_plus_records() -> list[Mapping[str, Any]]:
    """Load raw HumanEval+ records via the pinned evalplus package."""
    return list(get_human_eval_plus().values())


def _build_provenance(validated: _ValidatedCorpus) -> DatasetProvenance:
    human_eval_dataset_path = Path(human_eval.data.HUMAN_EVAL)
    human_eval_dataset_sha256 = hashlib.sha256(human_eval_dataset_path.read_bytes()).hexdigest()

    return DatasetProvenance(
        human_eval_package_version=version("human-eval"),
        human_eval_dataset_sha256=human_eval_dataset_sha256,
        # Not exposed by the PyPI-distributed human-eval package; the exact
        # pinned package version plus this dataset checksum together provide
        # the reproducibility guarantee instead.
        human_eval_commit_sha=None,
        evalplus_package_version=version("evalplus"),
        evalplus_dataset_version=HUMANEVAL_PLUS_VERSION,
        evalplus_dataset_hash=get_human_eval_plus_hash(version=HUMANEVAL_PLUS_VERSION),
        expected_task_count=EXPECTED_TASK_COUNT,
        human_eval_prompt_diff_count=validated.human_eval_prompt_diff_count,
        human_eval_canonical_solution_diff_count=(
            validated.human_eval_canonical_solution_diff_count
        ),
        loaded_at=datetime.now(timezone.utc).isoformat(),
    )


@lru_cache(maxsize=1)
def _load_corpus() -> _HumanEvalCorpus:
    raw_human_eval = _load_raw_human_eval_records()
    raw_human_eval_plus = _load_raw_human_eval_plus_records()
    validated = _validate_and_build(raw_human_eval, raw_human_eval_plus)
    return _HumanEvalCorpus(
        provenance=_build_provenance(validated),
        public_tasks=validated.public_tasks,
        privileged_tasks=validated.privileged_tasks,
    )


def load_public_view() -> tuple[PublicTaskView, ...]:
    """Return the public optimization view: task_id, prompt, entry_point only.

    This is the only dataset interface optimizer and candidate-generation
    code may use.
    """
    return _load_corpus().public_tasks


def load_privileged_view() -> tuple[PrivilegedTaskView, ...]:
    """Return the privileged reference view: canonical solutions, HumanEval+
    test evidence, contracts, and tolerances.

    Must only be called by privileged evaluator code, never by the
    optimization loop or candidate-generation code.
    """
    return _load_corpus().privileged_tasks


def load_provenance() -> DatasetProvenance:
    """Return the recorded dataset/package provenance for the loaded corpus."""
    return _load_corpus().provenance
