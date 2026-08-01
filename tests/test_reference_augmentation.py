"""Tests for MEGB-03A.1's deterministic supplementary-evidence generation."""

import pytest

from src.reference.augmentation import (
    ContractViolation,
    augment_task,
    build_canonical_callable,
    checksum_case_ids,
    generate_dyck_words,
    generate_integer_range_candidates,
    generate_paren_candidates,
    validate_against_contract,
)

_FIB_CONTRACT = '\n    assert n >= 0, "invalid inputs" # $_CONTRACT_$\n'
_FIB_PROMPT = "def fib(n):\n    pass\n"
_FIB_CANONICAL = "    if n <= 1:\n        return n\n    return fib(n - 1) + fib(n - 2)\n"


def test_generate_integer_range_candidates_is_exhaustive_and_ordered() -> None:
    """The integer generator produces exactly [0, N) in ascending order."""
    candidates = generate_integer_range_candidates(10)
    assert candidates == [(n,) for n in range(10)]


def test_generate_dyck_words_matches_catalan_numbers() -> None:
    """Dyck-word counts per length match the Catalan sequence."""
    words = generate_dyck_words(6)
    catalan = [1, 2, 5, 14, 42, 132]
    for pair_count, expected_count in zip(range(1, 7), catalan):
        length = pair_count * 2
        assert sum(1 for w in words if len(w) == length) == expected_count
    assert len(words) == sum(catalan)


def test_generate_dyck_words_are_all_balanced() -> None:
    """Every generated word is genuinely balanced (never negative, ends at zero)."""
    for word in generate_dyck_words(5):
        depth = 0
        for ch in word:
            depth += 1 if ch == "(" else -1
            assert depth >= 0
        assert depth == 0


def test_generate_dyck_words_canonical_order_prefers_open_paren() -> None:
    """Lexicographic order with '(' < ')' — the first word of each length is fully nested."""
    words = generate_dyck_words(3)
    length4 = [w for w in words if len(w) == 4]
    assert length4[0] == "(())"  # '(' preferred over ')' at every choice point
    assert length4[-1] == "()()"


def test_generate_paren_candidates_produces_single_and_multi_group() -> None:
    """Single-group candidates come first, followed by the requested number of pairs."""
    candidates = generate_paren_candidates(max_pair_count=2, num_pairs=1)
    words = generate_dyck_words(2)
    assert len(candidates) == len(words) + 1
    assert candidates[: len(words)] == [(w,) for w in words]
    assert candidates[-1] == (words[0] + " " + words[1],)


def test_validate_against_contract_accepts_valid_input() -> None:
    """A value satisfying the contract raises nothing."""
    validate_against_contract(_FIB_CONTRACT, "n", 5)


def test_validate_against_contract_rejects_invalid_input() -> None:
    """A value violating the contract raises ContractViolation, not a bare AssertionError."""
    with pytest.raises(ContractViolation):
        validate_against_contract(_FIB_CONTRACT, "n", -1)


def test_build_canonical_callable_executes_correctly() -> None:
    """The assembled canonical solution behaves as the real function."""
    fn = build_canonical_callable(_FIB_PROMPT, _FIB_CANONICAL, "fib")
    assert fn(10) == 55


def test_checksum_case_ids_is_order_independent_but_content_sensitive() -> None:
    """Checksum ignores input order but changes when the underlying set changes."""
    assert checksum_case_ids(["b", "a", "c"]) == checksum_case_ids(["a", "b", "c"])
    assert checksum_case_ids(["a", "b"]) != checksum_case_ids(["a", "b", "c"])


def test_augment_task_end_to_end_with_synthetic_fib() -> None:
    """Full pipeline: dedup, contract validation, feasibility check, checksums."""
    result = augment_task(
        task_id="Synthetic/fib",
        param_name="n",
        contract=_FIB_CONTRACT,
        prompt=_FIB_PROMPT,
        canonical_solution=_FIB_CANONICAL,
        entry_point="fib",
        existing_args=[(0,), (1,), (2,)],
        raw_candidates=generate_integer_range_candidates(10),
    )

    assert result.duplicate_of_existing_count == 3  # 0, 1, 2 already existed
    assert len(result.accepted) == 7  # 3..9
    assert len(result.contract_rejected) == 0
    assert len(result.infeasible) == 0
    assert result.combined_unique_count == 10
    assert len(result.original_case_ids) == 3


def test_augment_task_deduplicates_original_args_before_reporting() -> None:
    """existing_args containing a literal duplicate is reported as its deduplicated count."""
    result = augment_task(
        task_id="Synthetic/fib2",
        param_name="n",
        contract=_FIB_CONTRACT,
        prompt=_FIB_PROMPT,
        canonical_solution=_FIB_CANONICAL,
        entry_point="fib",
        existing_args=[(0,), (0,), (1,)],  # (0,) duplicated
        raw_candidates=generate_integer_range_candidates(5),
    )

    assert len(result.original_case_ids) == 2  # deduplicated: {0, 1}
    assert result.combined_unique_count == 5  # {0,1,2,3,4}


def test_augment_task_rejects_contract_violating_candidates() -> None:
    """A raw_candidates list containing an out-of-domain value is rejected, not accepted."""
    result = augment_task(
        task_id="Synthetic/fib3",
        param_name="n",
        contract=_FIB_CONTRACT,
        prompt=_FIB_PROMPT,
        canonical_solution=_FIB_CANONICAL,
        entry_point="fib",
        existing_args=[],
        raw_candidates=[(0,), (-1,), (2,)],
    )

    assert len(result.contract_rejected) == 1
    assert result.contract_rejected[0].args == (-1,)
    assert len(result.accepted) == 2


def test_augment_task_marks_exception_raising_candidate_infeasible() -> None:
    """A candidate that passes the contract but crashes the canonical solution is infeasible."""
    # A canonical solution that raises for a specific in-contract value.
    canonical = "    if n == 3:\n        raise RuntimeError('boom')\n    return n\n"
    result = augment_task(
        task_id="Synthetic/fib4",
        param_name="n",
        contract=_FIB_CONTRACT,
        prompt=_FIB_PROMPT,
        canonical_solution=canonical,
        entry_point="fib",
        existing_args=[],
        raw_candidates=[(1,), (3,), (5,)],
    )

    assert len(result.infeasible) == 1
    assert result.infeasible[0].args == (3,)
    assert len(result.accepted) == 2
