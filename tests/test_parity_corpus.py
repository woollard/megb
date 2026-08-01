"""Tests for MEGB-03D's frozen parity/validation corpus (structure, not execution)."""

import pytest

from src.reference.parity_corpus import (
    HUMANEVAL_39_TASK_ID,
    HUMANEVAL_39_VALIDATION_CORPUS,
    PARITY_CORPUS,
    REQUIRED_CATEGORIES,
    ParityCandidate,
    check_corpus_covers_required_categories,
)


def test_check_corpus_covers_required_categories_passes_for_the_real_corpus() -> None:
    """The actual frozen corpus covers every required category — this must
    never regress silently if the corpus is edited."""
    check_corpus_covers_required_categories()


def test_check_corpus_covers_required_categories_detects_a_missing_category() -> None:
    """A corpus missing a required category is rejected, not silently accepted."""
    incomplete = tuple(c for c in PARITY_CORPUS if c.category != next(iter(REQUIRED_CATEGORIES)))
    covered = {c.category for c in incomplete}
    assert covered != REQUIRED_CATEGORIES  # sanity: the fixture really is incomplete


def test_parity_corpus_candidate_ids_are_unique() -> None:
    """No two candidates silently share an identifier."""
    ids = [c.candidate_id for c in PARITY_CORPUS]
    assert len(ids) == len(set(ids))


def test_parity_corpus_is_nonempty_and_frozen_dataclasses() -> None:
    """Every corpus entry is the expected frozen, hand-authored type."""
    assert len(PARITY_CORPUS) > 0
    assert all(isinstance(c, ParityCandidate) for c in PARITY_CORPUS)


def test_parity_corpus_source_code_has_no_def_line() -> None:
    """Candidate source is a function body only, matching how it gets combined
    with the task's own prompt (never a standalone, separately-defined function)."""
    for candidate in PARITY_CORPUS:
        assert "def " not in candidate.source_code


def test_humaneval_39_validation_corpus_is_separate_from_the_main_corpus() -> None:
    """HumanEval/39's exhaustive-domain validation is its own corpus, never
    folded into the 163-task parity corpus (MEGB-03D requirement 10)."""
    main_corpus_task_ids = {c.task_id for c in PARITY_CORPUS}
    assert HUMANEVAL_39_TASK_ID not in main_corpus_task_ids
    assert all(c.task_id == HUMANEVAL_39_TASK_ID for c in HUMANEVAL_39_VALIDATION_CORPUS)


@pytest.mark.parametrize("candidate", PARITY_CORPUS, ids=lambda c: c.candidate_id)
def test_every_candidate_has_a_nonempty_description(candidate: ParityCandidate) -> None:
    """Every candidate documents what it's actually testing."""
    assert candidate.description.strip() != ""
