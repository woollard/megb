"""MEGB-03D: compare the pinned upstream EvalPlus implementation against the
MEGB oracle/comparison layer on the frozen parity corpus.

For each :class:`~src.reference.parity_corpus.ParityCandidate`, this module
independently derives two classifications of the *same* candidate against
the *same* (task, input-set) pair:

* **upstream** — via EvalPlus's own ``evalplus.eval.untrusted_check`` (a
  ``multiprocessing.Process``-isolated execution, exactly the pinned
  library's own mechanism), with ground truth from EvalPlus's own
  ``evalplus.gen.util.trusted_exec``.
* **megb** — via a narrowly scoped, validation-only harness over MEGB-02
  (``src.execution.docker_backend.execute_candidate``, one fresh container
  per invocation), with ground truth computed trusted-side and compared via
  ``src.reference.oracle.compare_outputs`` — never exposing the expected
  value to the candidate.

Both classifications reduce to the same four-way outcome MEGB-03E's
``ReferenceOutcome`` will later formalize (``PASS_BASE_PASS_PLUS`` etc.);
this module defines the same string values without depending on MEGB-03E,
which is not yet implemented.

This is explicitly a validation harness, not the production evaluator
(MEGB-03F): it runs a fixed 11-candidate corpus, not arbitrary optimizer
output, and every comparison happens once, offline, for parity evidence.

**Environment note**: ``evalplus.eval.reliability_guard``'s memory-limit
call (``resource.setrlimit(RLIMIT_AS, ...)``) fails unconditionally on at
least one validation host used for this subtask (macOS + CPython 3.14 —
confirmed independent of the requested limit value, so this is a platform
incompatibility, not a sizing issue). Every upstream classification in this
module works around it the same documented way EvalPlus itself supports:
setting ``EVALPLUS_MAX_MEMORY_BYTES=-1`` (see
``evalplus.eval.query_maximum_memory_bytes``) for the scope of the call,
via :func:`_disabled_upstream_memory_guard`, restoring the prior
environment afterward. This means upstream execution has **no OS-level
memory guard** on such hosts; :mod:`src.reference.parity_corpus`'s one
memory-exhausting candidate is deliberately sized to be safe to run
unprotected on an 8GB+ host (see its docstring) rather than relying on this
guard being functional.
"""

import contextlib
import copy
import hashlib
import os
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping, Sequence

from evalplus.eval import PASS as EVALPLUS_PASS
from evalplus.eval import untrusted_check
from evalplus.eval.utils import time_limit
from evalplus.gen.util import trusted_exec

from src.dataset import PrivilegedTaskView
from src.execution.backend import ExecutionBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    ExecutionLimits,
    ExecutionStatus,
)
from src.reference.augmentation import build_canonical_callable
from src.reference.oracle import ComparisonProfile, comparison_profile_for_task, compare_outputs
from src.reference.parity_corpus import (
    CATEGORY_RESOURCE_EXHAUSTING_MEMORY,
    CATEGORY_RESOURCE_EXHAUSTING_TIME,
    ParityCandidate,
)

PARITY_PROTOCOL_VERSION = "1"
PARITY_TRUSTED_TIME_LIMIT_SEC = 5.0
DEFAULT_PLUS_SAMPLE_SIZE = 30
EVALPLUS_DATASET_NAME = "humaneval"

# Resource-exhausting candidates are inherently slow per invocation (each one
# either runs out its full wall-clock timeout or gets OOM-killed); a much
# smaller plus sample keeps their total runtime bounded without weakening
# what they're actually testing (timeout/OOM classification, not per-case
# output diversity).
_SLOW_CATEGORY_PLUS_SAMPLE_SIZE = 3
_SLOW_CATEGORIES = frozenset(
    {CATEGORY_RESOURCE_EXHAUSTING_TIME, CATEGORY_RESOURCE_EXHAUSTING_MEMORY}
)

OUTCOME_PASS_BASE_PASS_PLUS = "PASS_BASE_PASS_PLUS"
OUTCOME_PASS_BASE_FAIL_PLUS = "PASS_BASE_FAIL_PLUS"
OUTCOME_FAIL_BASE_FAIL_PLUS = "FAIL_BASE_FAIL_PLUS"
OUTCOME_FAIL_BASE_PASS_PLUS = "FAIL_BASE_PASS_PLUS"

_EVALPLUS_MAX_MEMORY_BYTES_ENV = "EVALPLUS_MAX_MEMORY_BYTES"
_EVALPLUS_MEMORY_GUARD_DISABLED_VALUE = "-1"


@contextlib.contextmanager
def _disabled_upstream_memory_guard() -> Iterator[None]:
    """Work around ``reliability_guard``'s memory limit failing unconditionally
    on at least one validation host (see module docstring). Confined to the
    scope of one upstream call and restored (removed or reset) afterward —
    never left set process-wide beyond that.
    """
    previous = os.environ.get(_EVALPLUS_MAX_MEMORY_BYTES_ENV)
    os.environ[_EVALPLUS_MAX_MEMORY_BYTES_ENV] = _EVALPLUS_MEMORY_GUARD_DISABLED_VALUE
    try:
        yield
    finally:
        if previous is None:
            del os.environ[_EVALPLUS_MAX_MEMORY_BYTES_ENV]
        else:
            os.environ[_EVALPLUS_MAX_MEMORY_BYTES_ENV] = previous


def _sample_plus_input(
    plus_input: Sequence[tuple[Any, ...]],
    plus_sample_size: int,
    focus_indices: Sequence[int],
) -> list[tuple[Any, ...]]:
    """The default prefix sample, plus any explicitly known focus indices.

    Ensures an already-observed real edge case (recorded on the candidate
    via ``focus_plus_indices``) is never silently dropped just because it
    falls outside a fixed-size prefix sample.
    """
    indices = sorted(set(range(min(plus_sample_size, len(plus_input)))) | set(focus_indices))
    return [plus_input[i] for i in indices]


def _derive_outcome(base_passed: bool, plus_passed: bool) -> str:
    if base_passed and plus_passed:
        return OUTCOME_PASS_BASE_PASS_PLUS
    if base_passed and not plus_passed:
        return OUTCOME_PASS_BASE_FAIL_PLUS
    if not base_passed and plus_passed:
        return OUTCOME_FAIL_BASE_PASS_PLUS
    return OUTCOME_FAIL_BASE_FAIL_PLUS


@dataclass(frozen=True)
class SideClassification:
    """One side (base or plus) of a classification, with diagnostic detail.

    ``detail`` is a plain description of counts/status only (e.g. "6/999
    mismatched", "timeout") — never an expected or actual output value.
    """

    passed: bool
    sample_size: int
    detail: str


@dataclass(frozen=True)
class ParityOutcome:
    """A candidate's full classification on one execution path (upstream or MEGB)."""

    base: SideClassification
    plus: SideClassification
    outcome: str


# pylint: disable-next=too-many-locals
# pylint: disable-next=too-many-locals,too-many-arguments,too-many-positional-arguments
def classify_upstream(
    privileged: PrivilegedTaskView,
    prompt: str,
    candidate_source: str,
    plus_sample_size: int = DEFAULT_PLUS_SAMPLE_SIZE,
    focus_plus_indices: Sequence[int] = (),
) -> ParityOutcome:
    """Classify a candidate using EvalPlus's own pinned execution/comparison.

    Calls ``evalplus.eval.untrusted_check`` directly — the same
    ``multiprocessing.Process``-isolated mechanism the pinned
    ``evalplus==0.3.1`` uses for its own evaluation — never MEGB-02.
    """
    code = prompt + candidate_source
    canonical_code = prompt + privileged.canonical_solution
    base_input = list(privileged.base_input)
    plus_input = _sample_plus_input(
        privileged.plus_input, plus_sample_size, focus_plus_indices
    )

    with _disabled_upstream_memory_guard():
        base_expected, base_ref_time = trusted_exec(
            canonical_code, base_input, privileged.entry_point, record_time=True
        )
        plus_expected, plus_ref_time = trusted_exec(
            canonical_code, plus_input, privileged.entry_point, record_time=True
        )

        base_stat, _base_details = untrusted_check(
            EVALPLUS_DATASET_NAME,
            code,
            base_input,
            privileged.entry_point,
            expected=base_expected,
            atol=privileged.atol,
            ref_time=base_ref_time,
        )
        plus_stat, _plus_details = untrusted_check(
            EVALPLUS_DATASET_NAME,
            code,
            plus_input,
            privileged.entry_point,
            expected=plus_expected,
            atol=privileged.atol,
            ref_time=plus_ref_time,
        )

    base_passed = base_stat == EVALPLUS_PASS
    plus_passed = plus_stat == EVALPLUS_PASS
    return ParityOutcome(
        base=SideClassification(
            passed=base_passed, sample_size=len(base_input), detail=f"stat={base_stat}"
        ),
        plus=SideClassification(
            passed=plus_passed, sample_size=len(plus_input), detail=f"stat={plus_stat}"
        ),
        outcome=_derive_outcome(base_passed, plus_passed),
    )


def _megb_side(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    inputs: list[tuple[Any, ...]],
    candidate_code: str,
    entry_point: str,
    canonical_fn: Callable[..., Any],
    profile: ComparisonProfile,
    backend: ExecutionBackend,
    limits: ExecutionLimits,
) -> SideClassification:
    mismatches = 0
    for args in inputs:
        try:
            with time_limit(PARITY_TRUSTED_TIME_LIMIT_SEC):
                expected = canonical_fn(*copy.deepcopy(args))
        except Exception:  # pylint: disable=broad-exception-caught
            # The canonical solution is trusted and already proven (MEGB-03C);
            # a failure here would indicate corpus/environment drift, not a
            # candidate defect — treat conservatively as a mismatch rather
            # than silently skipping the case.
            mismatches += 1
            continue

        request = CandidateExecutionRequest(
            candidate_code=candidate_code,
            entry_point=entry_point,
            args=args,
            kwargs={},
            limits=limits,
            protocol_version=PARITY_PROTOCOL_VERSION,
        )
        result = backend.execute(request)
        if result.status != ExecutionStatus.COMPLETED:
            mismatches += 1
            continue
        if not compare_outputs(profile, args, result.return_value, expected):
            mismatches += 1

    return SideClassification(
        passed=mismatches == 0,
        sample_size=len(inputs),
        detail=f"{mismatches}/{len(inputs)} mismatched",
    )


def classify_megb(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    privileged: PrivilegedTaskView,
    prompt: str,
    candidate_source: str,
    backend: ExecutionBackend,
    limits: ExecutionLimits | None = None,
    plus_sample_size: int = DEFAULT_PLUS_SAMPLE_SIZE,
    focus_plus_indices: Sequence[int] = (),
) -> ParityOutcome:
    """Classify a candidate using MEGB-02's execution backend + MEGB-03C's comparison.

    Validation-only: this is a narrowly scoped harness over
    ``ExecutionBackend``, never the production MEGB-03F evaluator. Expected
    outputs are computed trusted-side (never passed to the candidate) and
    compared via ``compare_outputs`` — the exact same comparison MEGB-03C's
    oracle construction and any later production evaluator will use.
    """
    resolved_limits = limits or ExecutionLimits()
    profile = comparison_profile_for_task(privileged.entry_point, privileged.atol)
    canonical_fn = build_canonical_callable(
        prompt, privileged.canonical_solution, privileged.entry_point
    )
    candidate_code = prompt + candidate_source

    base_input = list(privileged.base_input)
    plus_input = _sample_plus_input(
        privileged.plus_input, plus_sample_size, focus_plus_indices
    )

    base = _megb_side(
        base_input, candidate_code, privileged.entry_point, canonical_fn, profile,
        backend, resolved_limits,
    )
    plus = _megb_side(
        plus_input, candidate_code, privileged.entry_point, canonical_fn, profile,
        backend, resolved_limits,
    )
    return ParityOutcome(base=base, plus=plus, outcome=_derive_outcome(base.passed, plus.passed))


@dataclass(frozen=True)
class ParityResult:
    """One candidate's complete parity comparison: upstream vs. MEGB, and agreement."""

    candidate_id: str
    task_id: str
    category: str
    candidate_source_sha256: str
    upstream: ParityOutcome
    megb: ParityOutcome
    agree: bool
    mismatch_detail: str | None


def compare_classifications(
    upstream: ParityOutcome, megb: ParityOutcome
) -> tuple[bool, str | None]:
    """Compare two classifications, returning (agree, mismatch_detail).

    ``mismatch_detail`` never contains expected/actual output values — only
    the outcome labels and per-side pass/fail summary, safe for a public
    report.
    """
    if upstream.outcome == megb.outcome:
        return True, None
    detail = (
        f"upstream={upstream.outcome} (base: {upstream.base.detail}, "
        f"plus: {upstream.plus.detail}) vs megb={megb.outcome} "
        f"(base: {megb.base.detail}, plus: {megb.plus.detail})"
    )
    return False, detail


def _source_sha256(source_code: str) -> str:
    return hashlib.sha256(source_code.encode("utf-8")).hexdigest()


def run_parity_candidate(
    candidate: ParityCandidate,
    privileged_by_id: Mapping[str, PrivilegedTaskView],
    public_by_id: Mapping[str, str],
    backend: ExecutionBackend,
    plus_sample_size: int = DEFAULT_PLUS_SAMPLE_SIZE,
) -> ParityResult:
    """Run one candidate through both the upstream and MEGB classification paths.

    Resource-exhausting candidates use a much smaller plus sample regardless
    of ``plus_sample_size`` — see ``_SLOW_CATEGORIES``.
    """
    privileged = privileged_by_id[candidate.task_id]
    prompt = public_by_id[candidate.task_id]
    resolved_plus_sample_size = (
        _SLOW_CATEGORY_PLUS_SAMPLE_SIZE
        if candidate.category in _SLOW_CATEGORIES
        else plus_sample_size
    )

    upstream = classify_upstream(
        privileged,
        prompt,
        candidate.source_code,
        resolved_plus_sample_size,
        focus_plus_indices=candidate.focus_plus_indices,
    )
    megb = classify_megb(
        privileged,
        prompt,
        candidate.source_code,
        backend,
        plus_sample_size=resolved_plus_sample_size,
        focus_plus_indices=candidate.focus_plus_indices,
    )
    agree, mismatch_detail = compare_classifications(upstream, megb)

    return ParityResult(
        candidate_id=candidate.candidate_id,
        task_id=candidate.task_id,
        category=candidate.category,
        candidate_source_sha256=_source_sha256(candidate.source_code),
        upstream=upstream,
        megb=megb,
        agree=agree,
        mismatch_detail=mismatch_detail,
    )


def run_parity_corpus(
    corpus: Sequence[ParityCandidate],
    privileged_by_id: Mapping[str, PrivilegedTaskView],
    public_by_id: Mapping[str, str],
    backend: ExecutionBackend,
    plus_sample_size: int = DEFAULT_PLUS_SAMPLE_SIZE,
) -> tuple[ParityResult, ...]:
    """Run every candidate in the frozen parity corpus through both classification paths."""
    return tuple(
        run_parity_candidate(candidate, privileged_by_id, public_by_id, backend, plus_sample_size)
        for candidate in corpus
    )
