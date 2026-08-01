"""Tests for MEGB-03D's independent supplementary-oracle validation
(HumanEval/6, /55, and /63 — no upstream EvalPlus counterpart)."""

from typing import Any

import pytest

from src.dataset import PrivilegedTaskView, load_privileged_view, load_public_view
from src.reference.augmentation import PROVENANCE_ORIGINAL, PROVENANCE_SUPPLEMENTARY
from src.reference.partition import gather_eligible_cases_and_args
from src.reference.supplementary_oracle_validation import (
    SUPPLEMENTARY_TASK_IDS,
    independent_fib,
    independent_fibfib,
    independent_parse_nested_parens,
    validate_supplementary_task,
)

pytestmark = pytest.mark.integration


# --- independent implementations: pure unit tests, no corpus needed --------


def test_independent_fib_matches_known_values() -> None:
    """Sanity-check the independent fib implementation against known values,
    matching the canonical solution's own documented doctest examples."""
    assert independent_fib(10) == 55
    assert independent_fib(1) == 1
    assert independent_fib(8) == 21


def test_independent_fibfib_matches_known_values() -> None:
    """Sanity-check against the canonical solution's own defining recurrence."""
    assert independent_fibfib(0) == 0
    assert independent_fibfib(1) == 0
    assert independent_fibfib(2) == 1
    expected_fibfib_3 = independent_fibfib(2) + independent_fibfib(1) + independent_fibfib(0)
    assert independent_fibfib(3) == expected_fibfib_3


def test_independent_parse_nested_parens_matches_known_values() -> None:
    """Sanity-check against the task's own documented example."""
    assert independent_parse_nested_parens("(()()) ((())) () ((())()())") == [2, 3, 1, 3]


# --- full validation against the real, frozen MEGB-03C oracle --------------


def _real_corpus_inputs(
    task_id: str,
) -> tuple[PrivilegedTaskView, str, dict[str, tuple[Any, ...]], dict[str, str]]:
    priv = {t.task_id: t for t in load_privileged_view()}
    pub = {t.task_id: t.prompt for t in load_public_view()}
    cases_by_task, _augmentation_results, args_by_task = gather_eligible_cases_and_args(priv, pub)
    provenance_by_case = {c.case_id: c.provenance for c in cases_by_task[task_id]}
    return priv[task_id], pub[task_id], args_by_task[task_id], provenance_by_case


@pytest.mark.parametrize("task_id", SUPPLEMENTARY_TASK_IDS)
def test_validate_supplementary_task_all_valid_on_real_corpus(task_id: str) -> None:
    """Every supplementary case for each task validates independently, and
    every metamorphic check passes, against the real, frozen MEGB-03A.1
    supplementary evidence."""
    privileged, prompt, args_by_case, provenance_by_case = _real_corpus_inputs(task_id)
    result = validate_supplementary_task(
        task_id, privileged, prompt, args_by_case, provenance_by_case
    )

    assert result.total_supplementary_cases > 0
    assert result.independent_match_count == result.total_supplementary_cases
    assert result.metamorphic_checks_passed == result.metamorphic_checks_total
    assert result.metamorphic_checks_total > 0
    assert result.all_valid


def test_validate_supplementary_task_only_counts_supplementary_provenance_cases() -> None:
    """Original-provenance cases (upstream EvalPlus evidence, which does have
    an oracle already validated by MEGB-03C/MEGB-03D's parity corpus) are
    excluded from this count — only the contract-derived supplementary
    cases are in scope here."""
    task_id = "HumanEval/55"
    privileged, prompt, args_by_case, provenance_by_case = _real_corpus_inputs(task_id)
    result = validate_supplementary_task(
        task_id, privileged, prompt, args_by_case, provenance_by_case
    )

    supplementary_count = sum(
        1 for cid in args_by_case if provenance_by_case.get(cid) == PROVENANCE_SUPPLEMENTARY
    )
    original_count = sum(
        1 for cid in args_by_case if provenance_by_case.get(cid) == PROVENANCE_ORIGINAL
    )
    assert result.total_supplementary_cases == supplementary_count
    assert result.total_supplementary_cases < len(args_by_case)
    assert original_count > 0  # sanity: original-provenance cases really do exist too


def test_validate_supplementary_task_all_valid_is_false_when_cases_are_empty() -> None:
    """An empty case set is never silently reported as "all valid" —
    validation requires a nonempty, genuinely-checked case set."""
    task_id = "HumanEval/55"
    privileged, prompt, _args_by_case, _provenance_by_case = _real_corpus_inputs(task_id)
    result = validate_supplementary_task(task_id, privileged, prompt, {}, {})
    assert result.total_supplementary_cases == 0
    assert not result.all_valid
