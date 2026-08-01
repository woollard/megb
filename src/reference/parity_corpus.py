"""MEGB-03D: the frozen, nonexperimental parity/validation corpus.

Every candidate here is hand-authored by us specifically to exercise one
category of known behavior — never a confirmatory experimental candidate,
never an outcome from MEGB-05/06 (per the MEGB-03D execution amendment,
requirement 7). Each candidate's actual upstream/MEGB classification is
determined empirically by running it (see ``src.reference.parity``), not
asserted in advance; this module only fixes *what code* runs, so the corpus
itself is frozen and checksummed before any parity analysis (requirement 1).

Two tasks carry the corpus: ``HumanEval/0`` (``has_close_elements`` — a
float-list/threshold task, good for boundary/type/tolerance/mutation
variations) and ``HumanEval/55`` (``fib`` — a simple recursive-int task,
good for hardcoded/stateful/resource-exhausting variations).
"""

from dataclasses import dataclass

PARITY_CORPUS_VERSION = "parity-corpus-v1"

CATEGORY_CORRECTED_CANONICAL = "corrected_canonical_solution"
CATEGORY_FAILS_ORIGINAL = "fails_original_evidence"
CATEGORY_PASS_BASE_FAIL_PLUS = "pass_base_fail_plus"
CATEGORY_HARDCODED = "hardcoded"
CATEGORY_BOUNDARY = "boundary_condition_failure"
CATEGORY_TYPE_HANDLING = "type_handling_failure"
CATEGORY_NUMERICAL_TOLERANCE = "numerical_tolerance_failure"
CATEGORY_MUTATION_SENSITIVE = "mutation_sensitive_failure"
CATEGORY_STATEFUL = "stateful_candidate"
CATEGORY_RESOURCE_EXHAUSTING_TIME = "resource_exhausting_time"
CATEGORY_RESOURCE_EXHAUSTING_MEMORY = "resource_exhausting_memory"

REQUIRED_CATEGORIES = frozenset(
    {
        CATEGORY_CORRECTED_CANONICAL,
        CATEGORY_FAILS_ORIGINAL,
        CATEGORY_PASS_BASE_FAIL_PLUS,
        CATEGORY_HARDCODED,
        CATEGORY_BOUNDARY,
        CATEGORY_TYPE_HANDLING,
        CATEGORY_NUMERICAL_TOLERANCE,
        CATEGORY_MUTATION_SENSITIVE,
        CATEGORY_STATEFUL,
        CATEGORY_RESOURCE_EXHAUSTING_TIME,
        CATEGORY_RESOURCE_EXHAUSTING_MEMORY,
    }
)


@dataclass(frozen=True)
class ParityCandidate:
    """One hand-authored candidate in the frozen parity corpus.

    ``source_code`` is the candidate function body only (indented, no
    ``def`` line) — combined with the task's own prompt the same way
    ``src.reference.augmentation.build_canonical_callable`` combines a
    canonical solution, so it can be assembled into a runnable function for
    either the upstream or the MEGB-02 execution path.

    ``focus_plus_indices`` names specific ``plus_input`` indices already
    known (from prior empirical probing while authoring this corpus) to
    exercise this candidate's divergent behavior. They are merged into the
    default prefix sample at parity-run time so a real edge case already
    observed once is never silently missed just because it falls outside a
    fixed-size sample — never used to fabricate a result, only to keep an
    already-observed real behavior covered.
    """

    candidate_id: str
    task_id: str
    category: str
    source_code: str
    description: str
    focus_plus_indices: tuple[int, ...] = ()


PARITY_CORPUS: tuple[ParityCandidate, ...] = (
    ParityCandidate(
        candidate_id="he0-corrected-canonical",
        task_id="HumanEval/0",
        category=CATEGORY_CORRECTED_CANONICAL,
        source_code=(
            "    sorted_numbers = sorted(numbers)\n"
            "    for i in range(len(sorted_numbers) - 1):\n"
            "        if sorted_numbers[i + 1] - sorted_numbers[i] < threshold:\n"
            "            return True\n"
            "    return False\n"
        ),
        description="Exact copy of the pinned EvalPlus canonical solution.",
    ),
    ParityCandidate(
        candidate_id="he0-fails-original",
        task_id="HumanEval/0",
        category=CATEGORY_FAILS_ORIGINAL,
        source_code="    return False\n",
        description=(
            "Always returns False; wrong on 4/7 base (original-evidence-equivalent) cases."
        ),
    ),
    ParityCandidate(
        candidate_id="he0-pass-base-fail-plus",
        task_id="HumanEval/0",
        category=CATEGORY_PASS_BASE_FAIL_PLUS,
        source_code=(
            "    sorted_numbers = sorted(numbers)\n"
            "    for i in range(len(sorted_numbers) - 1):\n"
            "        if sorted_numbers[i + 1] - sorted_numbers[i] <= threshold:\n"
            "            return True\n"
            "    return False\n"
        ),
        description=(
            "Off-by-one comparison operator (<= instead of <): matches all 7 base cases "
            "but disagrees on 6/999 plus cases (indices 11, 45, 100, 105, 200, 357) where "
            "two elements differ by exactly threshold — empirically confirmed "
            "PASS_BASE_FAIL_PLUS."
        ),
        focus_plus_indices=(11, 45, 100, 105, 200, 357),
    ),
    ParityCandidate(
        candidate_id="he55-hardcoded",
        task_id="HumanEval/55",
        category=CATEGORY_HARDCODED,
        source_code="    return 55\n",
        description="Hardcoded to the n=10 base example's expected value (fib(10)==55).",
    ),
    ParityCandidate(
        candidate_id="he0-boundary-index-error",
        task_id="HumanEval/0",
        category=CATEGORY_BOUNDARY,
        source_code=(
            "    sorted_numbers = sorted(numbers)\n"
            "    for i in range(len(sorted_numbers)):\n"
            "        if sorted_numbers[i + 1] - sorted_numbers[i] < threshold:\n"
            "            return True\n"
            "    return False\n"
        ),
        description=(
            "Off-by-one loop bound (range(len(...)) instead of range(len(...)-1)) raises "
            "IndexError on the last element for lists with >=1 item."
        ),
    ),
    ParityCandidate(
        candidate_id="he0-type-handling-str-bool",
        task_id="HumanEval/0",
        category=CATEGORY_TYPE_HANDLING,
        source_code=(
            "    sorted_numbers = sorted(numbers)\n"
            "    for i in range(len(sorted_numbers) - 1):\n"
            "        if sorted_numbers[i + 1] - sorted_numbers[i] < threshold:\n"
            '            return "True"\n'
            '    return "False"\n'
        ),
        description=(
            'Returns the string "True"/"False" instead of the bool True/False — correct '
            "logic, wrong return type; mismatches on every case since str != bool in Python."
        ),
    ),
    ParityCandidate(
        candidate_id="he0-numerical-tolerance-fudge",
        task_id="HumanEval/0",
        category=CATEGORY_NUMERICAL_TOLERANCE,
        source_code=(
            "    sorted_numbers = sorted(numbers)\n"
            "    for i in range(len(sorted_numbers) - 1):\n"
            "        if sorted_numbers[i + 1] - sorted_numbers[i] < threshold * 0.999:\n"
            "            return True\n"
            "    return False\n"
        ),
        description=(
            "Applies a 0.1% tolerance fudge to the threshold: matches all 7 base cases but "
            "disagrees on 1/999 plus case (index 823) — empirically confirmed "
            "PASS_BASE_FAIL_PLUS."
        ),
        focus_plus_indices=(823,),
    ),
    ParityCandidate(
        candidate_id="he0-mutation-sensitive-inplace-sort",
        task_id="HumanEval/0",
        category=CATEGORY_MUTATION_SENSITIVE,
        source_code=(
            "    numbers.sort()\n"
            "    for i in range(len(numbers) - 1):\n"
            "        if numbers[i + 1] - numbers[i] < threshold:\n"
            "            return True\n"
            "    return False\n"
        ),
        description=(
            "Sorts the input list in place (numbers.sort()) instead of sorting a copy "
            "(sorted(numbers)). Logic is otherwise identical to the canonical solution, so "
            "this validates that in-place mutation of a candidate's argument is safely "
            "isolated by both the upstream and MEGB-02 execution paths (no shared-state "
            "corruption), not that the candidate is wrong."
        ),
    ),
    ParityCandidate(
        candidate_id="he55-stateful-call-counter",
        task_id="HumanEval/55",
        category=CATEGORY_STATEFUL,
        source_code=(
            "    global _he55_call_count\n"
            "    try:\n"
            "        _he55_call_count += 1\n"
            "    except NameError:\n"
            "        _he55_call_count = 1\n"
            "    if n == 0:\n"
            "        return 0\n"
            "    if n <= 2:\n"
            "        return 1\n"
            "    a, b = 1, 1\n"
            "    for _ in range(3, n + 1):\n"
            "        a, b = b, a + b\n"
            "    return b\n"
        ),
        description=(
            "Maintains a module-level call counter but never lets it affect the returned "
            "value, so it is correct regardless of invocation order or isolation — this "
            "validates that per-invocation state doesn't leak into (or corrupt) the result, "
            "not that the candidate is wrong. See parity report for the isolation-scope "
            "note: MEGB-02 launches one fresh container per invocation, a stronger "
            "per-call isolation guarantee than upstream's own per-batch subprocess."
        ),
    ),
    ParityCandidate(
        candidate_id="he55-resource-exhausting-infinite-loop",
        task_id="HumanEval/55",
        category=CATEGORY_RESOURCE_EXHAUSTING_TIME,
        source_code="    while True:\n        pass\n",
        description=(
            "Infinite loop — both the upstream per-case time_limit (SIGALRM) and MEGB-02's "
            "per-invocation wall_time_sec safely classify this as a timeout rather than "
            "hanging the harness."
        ),
    ),
    ParityCandidate(
        candidate_id="he55-resource-exhausting-memory",
        task_id="HumanEval/55",
        category=CATEGORY_RESOURCE_EXHAUSTING_MEMORY,
        source_code="    x = [0] * (25 * 10 ** 7)\n    return len(x)\n",
        description=(
            "Allocates ~2GB (deliberately sized to be safe to run unprotected on an "
            "8GB validation host — see the parity report's environment notes on "
            "evalplus's reliability_guard memory limit being non-functional on "
            "macOS/Python 3.14 for this run) and returns the allocation's length, "
            "never the correct fib(n). MEGB-02's real per-container memory_mb=256 "
            "cgroup limit safely OOM-kills it; upstream (unprotected on this host) "
            "instead fails on correctness, since 250000000 never equals a requested "
            "fib(n). Both sides FAIL, by different mechanisms — an intentional, "
            "documented property of this candidate, not a bug."
        ),
    ),
)

HUMANEVAL_39_TASK_ID = "HumanEval/39"

#: A separate, small validation corpus for HumanEval/39's exhaustive 12-case
#: domain (base_input n=1..10, plus_input n=11,12 — see MEGB-03A.1's
#: "domain exhausted at 12 cases" finding), run and reported independently
#: of the 163-task PARITY_CORPUS per the MEGB-03D execution amendment,
#: requirement 10.
HUMANEVAL_39_VALIDATION_CORPUS: tuple[ParityCandidate, ...] = (
    ParityCandidate(
        candidate_id="he39-corrected-canonical",
        task_id=HUMANEVAL_39_TASK_ID,
        category=CATEGORY_CORRECTED_CANONICAL,
        source_code=(
            "    import random\n"
            "    def miller_rabin(n, k=10):\n"
            '        """Test if n is prime using the Miller-Rabin primality test."""\n'
            "        if n < 2:\n"
            "            return False\n"
            "        if n == 2 or n == 3:\n"
            "            return True\n"
            "        if n % 2 == 0:\n"
            "            return False\n"
            "        r = 0\n"
            "        d = n - 1\n"
            "        while d % 2 == 0:\n"
            "            r += 1\n"
            "            d //= 2\n"
            "        for _ in range(k):\n"
            "            a = random.randint(2, n - 2)\n"
            "            x = pow(a, d, n)\n"
            "            if x == 1 or x == n - 1:\n"
            "                continue\n"
            "            for _ in range(r - 1):\n"
            "                x = pow(x, 2, n)\n"
            "                if x == n - 1:\n"
            "                    break\n"
            "            else:\n"
            "                return False\n"
            "        return True\n"
            "    c_prime = 0\n"
            "    a, b = 0, 1\n"
            "    while c_prime < n:\n"
            "        a, b = b, a + b\n"
            "        if miller_rabin(b):\n"
            "            c_prime += 1\n"
            "    return b\n"
        ),
        description="Exact copy of the pinned EvalPlus canonical solution for HumanEval/39.",
    ),
    ParityCandidate(
        candidate_id="he39-fails-original",
        task_id=HUMANEVAL_39_TASK_ID,
        category=CATEGORY_FAILS_ORIGINAL,
        source_code="    return 2\n",
        description=(
            "Hardcoded to the n=1 base case's expected value (prime_fib(1)==2); "
            "wrong for n=2..12."
        ),
    ),
)


def check_corpus_covers_required_categories() -> None:
    """Fail fast if a required category has no representative candidate.

    Not a test itself — called by both the build CLI and the test suite so
    a corpus edit that silently drops a category is caught immediately.
    """
    covered = {c.category for c in PARITY_CORPUS}
    missing = REQUIRED_CATEGORIES - covered
    if missing:
        raise ValueError(f"parity corpus is missing required categories: {sorted(missing)}")
