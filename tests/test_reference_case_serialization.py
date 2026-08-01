"""Unit tests for MEGB-03A's stable, versioned case serialization."""

from src.reference.case_serialization import (
    CASE_ID_ALGORITHM_VERSION,
    canonical_case_representation,
    stable_case_id,
)


def test_stable_case_id_is_deterministic() -> None:
    """Repeated calls with identical inputs produce identical IDs."""
    args = ([1.0, 2.0, 3.0], 0.5)
    assert stable_case_id("HumanEval/0", args) == stable_case_id("HumanEval/0", args)


def test_stable_case_id_differs_by_args() -> None:
    """Different arguments for the same task produce different IDs."""
    id_a = stable_case_id("HumanEval/0", ([1.0, 2.0, 3.0], 0.5))
    id_b = stable_case_id("HumanEval/0", ([1.0, 2.0, 3.0], 0.6))
    assert id_a != id_b


def test_stable_case_id_differs_by_task() -> None:
    """The same arguments under a different task_id produce different IDs."""
    args = ([1.0, 2.0, 3.0], 0.5)
    assert stable_case_id("HumanEval/0", args) != stable_case_id("HumanEval/1", args)


def test_stable_case_id_distinguishes_list_from_tuple_args() -> None:
    """A list-valued arg and a tuple-valued arg with the same elements differ.

    Reuses execution.wire's tuple-vs-list tagging, so this distinction
    (which matters for some HumanEval signatures) is preserved here too.
    """
    id_list = stable_case_id("HumanEval/0", ([1, 2, 3],))
    id_tuple = stable_case_id("HumanEval/0", ((1, 2, 3),))
    assert id_list != id_tuple


def test_canonical_representation_includes_version_and_task_id() -> None:
    """The canonical representation is versioned and human-inspectable."""
    canonical = canonical_case_representation("HumanEval/0", (1, 2))
    assert canonical.startswith(f"{CASE_ID_ALGORITHM_VERSION}|HumanEval/0|")


def test_canonical_representation_is_stable_across_calls() -> None:
    """The canonical string itself (not just its hash) is stable."""
    args = ({"a": 1, "b": [1, 2]},)
    first = canonical_case_representation("HumanEval/0", args)
    second = canonical_case_representation("HumanEval/0", args)
    assert first == second
