"""Ingestion and parsing pipeline for the HumanEval dataset."""

from pathlib import Path
from typing import Any


def load_human_eval_tasks(data_path: Path) -> list[dict[str, Any]]:
    """Load and parse HumanEval tasks from the local dataset copy.

    Args:
        data_path: Path to the HumanEval problems file, e.g.
            ``data/human-eval/HumanEval.jsonl.gz``.

    Returns:
        A list of task records, each containing at least ``task_id``,
        ``prompt``, ``canonical_solution``, ``test``, and ``entry_point``.
    """
    raise NotImplementedError(
        "HumanEval ingestion not yet implemented; data/ is currently empty."
    )
