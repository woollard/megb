# MEGB-03A.1 Supplementary-Evidence Generation Procedures (v1)

**Frozen before generation.** This document fixes domain assumptions,
generation parameters, ordering, deduplication, serialization, and
versioning for the three augmentable tasks (`HumanEval/6`, `HumanEval/55`,
`HumanEval/63`) before any supplementary case is generated. Per Decision 4,
these procedures were designed using only each task's documented contract
and the general mathematical structure of its input domain — no model
candidate output, no observed candidate failure, and no `S*`/reference
outcome was consulted or exists yet for these tasks in this repository.

- **Algorithm version:** `supplementary-generation-v1`
- **Case ID / serialization:** reuses MEGB-03A's `case-id-v1`
  (`src.reference.case_serialization`) unchanged — no new serialization
  format is introduced.
- **Provenance tags:** `evalplus-original-v1` (existing, EvalPlus-sourced
  cases) versus `megb-contract-augmentation-v1` (generated cases). Every
  case in every downstream artifact carries one of these two tags.
- **Deduplication:** for each task, a candidate whose `stable_case_id`
  already exists among that task's original cases is dropped before being
  counted as supplementary — supplementary cases are additive, never
  double-counted duplicates of existing evidence.

---

## HumanEval/55 (`fib`) and HumanEval/63 (`fibfib`)

**Domain assumption:** the contract requires `isinstance(n, int)` and `n
>= 0`; the domain is otherwise unbounded above.

**Generation rule:** exhaustive enumeration of the integer range `[0,
200)` — 200 candidates, no sampling, no gaps.

**Ordering:** ascending numeric order `0, 1, 2, ..., 199` (the only
canonical order for a linear integer range).

**Rationale:** exhaustive enumeration of a bounded prefix of the naturals
is the simplest complete, contract-faithful systematic procedure for an
unbounded scalar-integer domain. `K=200` was chosen because:
- it exceeds both tasks' current maximum existing value (86 for
  `HumanEval/55`, 102 for `HumanEval/63`), so the combined set becomes
  exactly `{0, ..., 199}` — every existing case is a subset of the
  generated range, guaranteeing full gap-filling;
- it comfortably clears the >=100-combined-case target for both tasks
  with headroom, while remaining small enough to be exhaustively listed
  and audited by hand if needed.

**Contract validation:** every candidate is a Python `int` in `[0, 200)`
by construction; validity (`isinstance(n, int) and n >= 0`) is checked
mechanically per candidate regardless (see Requirement in code), not
merely assumed.

## HumanEval/6 (`parse_nested_parens`)

**Domain assumption:** the contract's literal runtime check only requires
that the *entire* string's running paren count (ignoring spaces) never go
negative and end at zero — it does not, read literally, require each
individual space-separated group to be independently balanced. Every
existing example case, however, *is* composed of independently balanced
groups, and the task's documented semantics (per-group nesting depth) are
only unambiguous when each group is independently balanced. **This
procedure therefore adopts the narrower, declared assumption that each
space-separated group must itself be a balanced parenthesis sequence
(a Dyck word)**, and treats any string that is only balanced in the
weaker, whole-string sense as out of scope for generation (an ambiguity,
not a candidate to generate) — consistent with the instruction to reject
ambiguous inputs rather than generate them to satisfy a quota.

**Generation rule:**
1. Enumerate all Dyck words (strings over `(` and `)` with a running count
   that never goes negative and ends at zero) of length `2n` for `n = 1
   .. 6` (lengths 2, 4, 6, 8, 10, 12), in canonical order: recursively,
   preferring `(` over `)` at each position whenever both are still valid
   (standard lexicographic Dyck-word generation, with `(` < `)`). Counts
   per length follow the Catalan numbers: 1, 2, 5, 14, 42, 132 — 196 Dyck
   words total.
2. **Single-group candidates:** each of the 196 Dyck words alone, as the
   complete `paren_string`.
3. **Multi-group candidates:** consecutive, non-overlapping pairs from the
   same canonical Dyck-word list — `words[0]+" "+words[1]`,
   `words[2]+" "+words[3]`, ... — consuming the first 80 words (40 pairs),
   joined by a single space, matching the multi-group structure observed
   in every existing example case.
4. Total raw candidates before deduplication: 236 (196 + 40).

**Ordering:** the fixed enumeration order above — by length ascending,
lexicographic within length, pairs taken consecutively in that same order.

**Rationale:** Dyck-word enumeration is the canonical, purely
combinatorial construction of every valid balanced-parenthesis string up
to a bounded size — it is derived entirely from the contract's own
balance definition, not from any observed model or candidate behavior.
Lengths 2–12 give comprehensive small-to-moderate depth coverage; the
40 consecutive pairs reconstruct realistic multi-group inputs using the
same deterministic source list, with no candidate- or outcome-informed
selection of which words to pair.

**Contract validation:** every candidate is checked by mechanically
executing the contract's own logic (type is `str`; every character is
`(`, `)`, or ` `; running count never negative; ends at zero) — verified
programmatically per candidate, not assumed from construction.

---

## Explicitly out of scope for this procedure

- No signature-based generic fuzzing (no case is derived from the Python
  type signature alone, independent of the contract).
- No case informed by any model-generated candidate, observed candidate
  failure, or `S*`/reference-evaluator outcome — none exist for these
  tasks in this repository as of this procedure's freeze.
- No expected-output computation. This procedure produces only candidate
  *inputs*; MEGB-03C remains solely responsible for constructing the
  trusted oracle. A feasibility check (does the pinned canonical solution
  execute without raising on this input?) is performed and reported, but
  no oracle artifact is materialized here.
