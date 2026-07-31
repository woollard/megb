# ADR 0001: HumanEval Corpus Integration and Public/Privileged View Boundary

## Status

Accepted (MEGB-01).

## Context

MEGB-01 requires integrating `openai/human-eval` and `evalplus/evalplus` as
the dataset foundation for the benchmark, defining a strict boundary between
evidence available to the optimization loop (public view) and evidence
reserved for privileged evaluation (canonical solutions, HumanEval+ test
evidence), per CLAUDE.md's non-negotiable rule that S*'s evidence must never
reach the optimization process.

ARCHITECTURE.md originally described `data/human-eval/` as a git submodule.
During implementation we deviated from that and used pip-pinned packages
instead (see Decision 1).

While implementing the loader, we discovered the two upstream sources do not
align in the way MEGB-01 initially assumed. This ADR records what we found
and the resulting design.

## Empirical Findings

Against `human-eval==1.0.3` and `evalplus==0.3.1` (evalplus dataset version
`v0.1.10`, hash `fe585eb4df8c88d844eeb463ea4d0302`):

* **`entry_point`**: identical across all 164 tasks. Treated as a hard
  structural invariant.
* **`prompt`**: differs for exactly 1 of 164 tasks (`HumanEval/115` — the
  original prompt places `import math` inside the function body; HumanEval+
  moves it to module level). This is a documented upstream EvalPlus
  correction, not a data-integrity defect.
* **`canonical_solution`**: differs for all 164 of 164 tasks. HumanEval+ does
  not merely patch a handful of buggy solutions — it ships independently
  authored reference implementations for essentially the entire benchmark.
  This confirms (rather than assumes) MEGB-03's instruction to score against
  "the corrected EvalPlus canonical solutions": EvalPlus's solutions are the
  ones actually exercised against its own `base_input`/`plus_input` test
  evidence, so they are the only internally consistent choice for a
  privileged reference oracle.
* **task_id sets**: identical (164 == 164, `HumanEval/0`..`HumanEval/163`).

## Decision 1: Pin as libraries, not a data submodule

Both packages are integrated as exact-pinned pip dependencies
(`human-eval==1.0.3`, `evalplus==0.3.1`) rather than as a git submodule.

**Why:** `human-eval`'s dataset ships bundled inside the installed package
(no network needed after install). `evalplus` fetches its dataset from a
GitHub release asset on first call and caches it locally
(`~/Library/Caches/evalplus` on macOS), independent of the pip package's own
version. A submodule would only pin `human-eval`'s data and would still need
a separate mechanism to pin `evalplus`'s release asset — so pip-pinning both
packages plus recording dataset hashes at load time (see Decision 3) gives
equivalent reproducibility with substantially less operational overhead.

**Limitation:** `evalplus` pulls a heavy transitive dependency tree
(transformers, datasets, huggingface_hub, google-generativeai, openai,
anthropic, etc.) because it is a full LLM-evaluation framework, not a
standalone dataset package. This project only uses its dataset-loading
functions (`evalplus.data.get_human_eval_plus`,
`evalplus.data.get_human_eval_plus_hash`). This is a known cost of using the
upstream library directly rather than re-vendoring its data.

## Decision 2: HumanEval+ is authoritative for prompt and canonical_solution

`PublicTaskView.prompt` and `PrivilegedTaskView.canonical_solution` are
sourced from `evalplus`, not `human_eval`. `PrivilegedTaskView.original_test`
is sourced from `human_eval` (the single assert-based `check()` function),
since MEGB-01 explicitly requires both "original tests" and "HumanEval+
tests" as distinct evidence layers — different measurement systems (e.g. S1's
sparse single-example evidence vs. S4/S*'s exhaustive evidence) draw on
different subsets of this evidence.

**Why:** Given canonical_solution differs almost universally, using
`human_eval`'s prompt (which is byte-identical to evalplus's, except for one
task) together with `evalplus`'s canonical_solution and test evidence is the
only internally consistent pairing — the canonical solution and its
constructed test cases were built to satisfy the evalplus prompt.

## Decision 3: Hard failures vs. diagnostics

* **Hard failures** (`DatasetValidationError`): task count != 164, duplicate
  or missing `task_id`, missing required fields, `task_id` set mismatch
  between sources, `entry_point` mismatch between sources.
* **Diagnostics only** (recorded in `DatasetProvenance`, not raised):
  `human_eval_prompt_diff_count`, `human_eval_canonical_solution_diff_count`.

**Why:** Per CLAUDE.md, conclusions must be supported by data and defects
must not be silently concealed. Given the empirical findings above, treating
every prompt/solution difference as a fatal error would make the loader
unusable against real upstream data. Recording the counts instead preserves
visibility (an unexpected jump in these counts on a future dataset-version
bump would be an immediate, visible signal) without blocking legitimate,
documented upstream divergence.

## Decision 4: General evaluator result schema (MEGB-01) vs. reference-evaluator schema (MEGB-03)

`src/evaluators/schema.py` defines `FailureCategory` and
`TaskMeasurementResult` as the general result contract used by
`BaseMeasurementSystem` implementations (S1..S4). `BaseMeasurementSystem.evaluate()`
was updated to return `TaskMeasurementResult` instead of a bare
`dict[str, Any]`.

**Why:** MEGB-01 explicitly requires defining "the evaluator result schema
and failure taxonomy." This is deliberately separate from and simpler than
MEGB-03's `ReferenceTaskResult` / `MeasurementStatus`, which additionally
distinguishes candidate failures from measurement-system failures for
privileged, audited evaluation. The two schemas are not meant to merge: S*'s
audit and non-adaptive-evaluation requirements are materially stricter than
what general S1..S4 evaluators need.

## Consequences

* Optimizer/candidate-generation code can only ever obtain
  `PublicTaskView` records (`task_id`, `prompt`, `entry_point`) via
  `load_public_view()` — canonical solutions and test evidence are not
  reachable through that function's return type.
* Privileged evaluator code (MEGB-02/03 and later) uses
  `load_privileged_view()`.
* Any future evalplus dataset-version bump must be treated as a new,
  versioned corpus: rerun `test_real_corpus_provenance_is_pinned_and_recorded`
  and update the regression diff-count assertions if they legitimately
  change, per CLAUDE.md's rule against silently changing metrics.
