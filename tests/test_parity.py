"""Tests for MEGB-03D's upstream-vs-MEGB parity classification (src.reference.parity)."""

import pytest

from src.dataset import PrivilegedTaskView, load_privileged_view, load_public_view
from src.execution.docker_backend import DockerPerInvocationBackend
from src.reference.parity import (
    OUTCOME_FAIL_BASE_FAIL_PLUS,
    OUTCOME_PASS_BASE_FAIL_PLUS,
    OUTCOME_PASS_BASE_PASS_PLUS,
    ParityOutcome,
    SideClassification,
    classify_megb,
    classify_upstream,
    compare_classifications,
    run_parity_corpus,
)
from src.reference.parity_corpus import (
    HUMANEVAL_39_VALIDATION_CORPUS,
    PARITY_CORPUS,
    ParityCandidate,
)

pytestmark = pytest.mark.integration


def _corpus_by_id() -> dict[str, ParityCandidate]:
    return {c.candidate_id: c for c in PARITY_CORPUS}


def _real_tasks() -> tuple[dict[str, PrivilegedTaskView], dict[str, str]]:
    priv = {t.task_id: t for t in load_privileged_view()}
    pub = {t.task_id: t.prompt for t in load_public_view()}
    return priv, pub


def _classify_candidate(candidate_id: str) -> ParityOutcome:
    priv, pub = _real_tasks()
    candidate = _corpus_by_id()[candidate_id]
    return classify_upstream(
        priv[candidate.task_id],
        pub[candidate.task_id],
        candidate.source_code,
        focus_plus_indices=candidate.focus_plus_indices,
    )


# --- compare_classifications: pure logic, no corpus/network needed ---------


def _outcome(label: str) -> ParityOutcome:
    side = SideClassification(passed=True, sample_size=1, detail="stub")
    return ParityOutcome(base=side, plus=side, outcome=label)


def test_compare_classifications_agree_when_outcomes_match() -> None:
    """Identical outcomes agree, with no mismatch detail."""
    upstream = _outcome(OUTCOME_PASS_BASE_PASS_PLUS)
    megb = _outcome(OUTCOME_PASS_BASE_PASS_PLUS)
    agree, detail = compare_classifications(upstream, megb)
    assert agree
    assert detail is None


def test_compare_classifications_disagree_reports_detail_without_output_values() -> None:
    """A genuine mismatch is flagged, and the detail names outcomes/counts,
    never any output value."""
    upstream = _outcome(OUTCOME_PASS_BASE_PASS_PLUS)
    megb = _outcome(OUTCOME_FAIL_BASE_FAIL_PLUS)
    agree, detail = compare_classifications(upstream, megb)
    assert not agree
    assert detail is not None
    assert OUTCOME_PASS_BASE_PASS_PLUS in detail
    assert OUTCOME_FAIL_BASE_FAIL_PLUS in detail


# --- classify_upstream: real corpus, no Docker required ---------------------


def test_classify_upstream_corrected_canonical_passes_base_and_plus() -> None:
    """An exact copy of the canonical solution passes both sides."""
    outcome = _classify_candidate("he0-corrected-canonical")
    assert outcome.outcome == OUTCOME_PASS_BASE_PASS_PLUS
    assert outcome.base.passed
    assert outcome.plus.passed


def test_classify_upstream_finds_the_required_pass_base_fail_plus_candidate() -> None:
    """The corpus's designated PASS_BASE_FAIL_PLUS candidate reproduces that
    outcome via the real upstream EvalPlus implementation (acceptance
    criterion: at least one validated PASS_BASE_FAIL_PLUS example)."""
    outcome = _classify_candidate("he0-pass-base-fail-plus")
    assert outcome.outcome == OUTCOME_PASS_BASE_FAIL_PLUS
    assert outcome.base.passed
    assert not outcome.plus.passed


def test_classify_upstream_fails_original_evidence_candidate_fails_base() -> None:
    """A candidate wrong on the original/base evidence is classified as such."""
    outcome = _classify_candidate("he0-fails-original")
    assert not outcome.base.passed
    assert outcome.outcome == OUTCOME_FAIL_BASE_FAIL_PLUS


def test_classify_upstream_boundary_index_error_counts_as_failure() -> None:
    """An IndexError-raising candidate is classified as a failure, not a crash."""
    outcome = _classify_candidate("he0-boundary-index-error")
    assert not outcome.base.passed


def test_classify_upstream_type_handling_str_bool_fails_every_case() -> None:
    """Returning a string instead of a bool never accidentally compares equal."""
    outcome = _classify_candidate("he0-type-handling-str-bool")
    assert outcome.outcome == OUTCOME_FAIL_BASE_FAIL_PLUS


def test_classify_upstream_mutation_sensitive_candidate_still_passes() -> None:
    """Sorting the input list in place doesn't corrupt the classification."""
    outcome = _classify_candidate("he0-mutation-sensitive-inplace-sort")
    assert outcome.outcome == OUTCOME_PASS_BASE_PASS_PLUS


def test_classify_upstream_stateful_candidate_still_passes() -> None:
    """A module-level call counter that never affects the result is still correct."""
    outcome = _classify_candidate("he55-stateful-call-counter")
    assert outcome.outcome == OUTCOME_PASS_BASE_PASS_PLUS


# --- classify_megb: requires Docker + megb-runner:local ---------------------


@pytest.mark.docker
def test_run_parity_corpus_agrees_with_upstream_for_every_candidate() -> None:
    """The full frozen corpus: MEGB-02 execution + MEGB-03C comparison agrees
    with the pinned upstream EvalPlus implementation for every candidate.

    Uses ``run_parity_corpus`` (not raw ``classify_upstream``/``classify_megb``
    calls) so resource-exhausting candidates get their smaller plus-sample
    size, keeping this test's runtime bounded.
    """
    priv, pub = _real_tasks()
    backend = DockerPerInvocationBackend()

    results = run_parity_corpus(PARITY_CORPUS, priv, pub, backend)
    disagreements = [r for r in results if not r.agree]
    assert not disagreements, [(r.candidate_id, r.mismatch_detail) for r in disagreements]


# --- HumanEval/39: exhaustive 12-case validation, its own separate corpus ---


def test_classify_upstream_humaneval_39_exhaustive_domain_agrees_for_both_candidates() -> None:
    """HumanEval/39's exhaustive 12-case domain (base n=1..10, plus n=11,12):
    both the corrected canonical solution and a deliberately wrong candidate
    classify as expected via the real upstream EvalPlus implementation,
    covering every case (never a subsample) — MEGB-03D requirement 10."""
    priv, pub = _real_tasks()
    task = priv["HumanEval/39"]
    full_plus_coverage = len(task.plus_input)

    for candidate in HUMANEVAL_39_VALIDATION_CORPUS:
        outcome = classify_upstream(
            priv[candidate.task_id],
            pub[candidate.task_id],
            candidate.source_code,
            plus_sample_size=full_plus_coverage,
        )
        assert outcome.base.sample_size == len(task.base_input)
        assert outcome.plus.sample_size == full_plus_coverage
        if candidate.candidate_id == "he39-corrected-canonical":
            assert outcome.outcome == OUTCOME_PASS_BASE_PASS_PLUS
        else:
            assert outcome.outcome == OUTCOME_FAIL_BASE_FAIL_PLUS


@pytest.mark.docker
def test_classify_megb_humaneval_39_exhaustive_domain_agrees_with_upstream() -> None:
    """Same exhaustive HumanEval/39 domain, through MEGB-02 + MEGB-03C's
    comparison layer, agreeing with the upstream classification above."""
    priv, pub = _real_tasks()
    backend = DockerPerInvocationBackend()
    task = priv["HumanEval/39"]
    full_plus_coverage = len(task.plus_input)

    for candidate in HUMANEVAL_39_VALIDATION_CORPUS:
        upstream = classify_upstream(
            priv[candidate.task_id],
            pub[candidate.task_id],
            candidate.source_code,
            plus_sample_size=full_plus_coverage,
        )
        megb = classify_megb(
            priv[candidate.task_id],
            pub[candidate.task_id],
            candidate.source_code,
            backend,
            plus_sample_size=full_plus_coverage,
        )
        agree, detail = compare_classifications(upstream, megb)
        assert agree, f"{candidate.candidate_id}: {detail}"
