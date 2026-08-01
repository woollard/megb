# MEGB-03 Partition-Policy Decision Addendum

**Status:** Decision-analysis only. No partition assigned or frozen, no
supplementary evidence generated, no MEGB-03B work begun. All numbers
below are computed from the MEGB-03A evidence inventory
(`artifacts/reference/evidence_inventory.json`, checksum
`4086bfb647ccf6bc1d2e15b8f15ed9d9f158f4afa93633ea32d14c9367f2dada`)
against the pinned corpus (human-eval==1.0.3, evalplus==0.3.1, dataset
v0.1.10). The analysis script is exploratory (not part of the committed
`src/reference` package) and reuses only already-tested primitives
(`stable_case_id`, `load_privileged_view`).

---

## 1. HumanEval/39 and HumanEval/55 in detail

| | HumanEval/39 | HumanEval/55 |
|---|---|---|
| Entry point | `prime_fib` | `fib` |
| Contract | `assert type(n) == int`; `assert 1 <= n <= 12` | `assert n >= 0`; `assert isinstance(n, int)` |
| Valid input domain | Exactly 12 integers (`n ∈ [1,12]`) | Unbounded (`n ∈ [0, ∞)`) |
| base_input count | 10 | 5 |
| plus_input count | 2 | 45 |
| Raw combined count | 12 | 50 |
| Duplicate cases (base∩plus) | 0 | 5 |
| **Unique combined count** | **12** | **45** |
| Domain coverage | **12 / 12 — fully exhausted** | 43 unique `n` values, range 0–86, with gaps (e.g. 9, 19–26 missing) |

**HumanEval/39 is not merely evidence-poor — its entire valid input domain
has exactly 12 elements, and all 12 are already covered.** There is no
legitimate 13th input; `n=13` (or anything outside `[1,12]`) violates the
documented contract. This is a hard ceiling, not a sampling gap.

**HumanEval/55's domain is unbounded**, so its shortfall (45 unique cases,
5 of which duplicate across base/plus) is a sampling gap, not a hard
ceiling — see §6.

---

## 2. Unique combined-case-count distribution (all 164 tasks)

| Statistic | Value |
|---|---|
| Minimum | 12 |
| p5 | 109 |
| p10 | 136 |
| p25 | 445 |
| **Median** | **977** |
| p75 | 1005 |
| p90 | 1008 |
| p95 | 1010 |
| Maximum | 1100 |
| Mean | 756 |

The distribution is heavily left-skewed: the bottom ~10% of tasks (by
evidence volume) account for nearly all of the practical feasibility
tension; the remaining ~90% have (often far) more than enough evidence for
any policy considered below.

---

## 3. Development-target × reference-minimum feasibility grid

For each `(dev_target, ref_minimum)` pair, a task satisfies the pair iff
`unique_count >= dev_target + ref_minimum`. "Resulting reference count"
for a satisfying task = `unique_count - dev_target` (development is capped
at the target; everything else goes to reference-only).

| dev_target | ref_min | required_total | satisfying | failing | min resulting ref | median resulting ref |
|---:|---:|---:|---:|---:|---:|---:|
| 31 | 1 | 32 | 163 | 1 | 14 | 946 |
| 31 | 10 | 41 | 163 | 1 | 14 | 946 |
| 31 | 20 | 51 | 162 | 2 | 34 | 947 |
| 31 | 30 | 61 | 162 | 2 | 34 | 947 |
| 31 | 50 | 81 | 159 | 5 | 56 | 951 |
| 35 | 1 | 36 | 163 | 1 | 10 | 942 |
| 35 | 20 | 55 | 162 | 2 | 30 | 943 |
| 35 | 50 | 85 | 159 | 5 | 52 | 947 |
| 40 | 1 | 41 | 163 | 1 | 5 | 937 |
| 40 | 20 | 60 | 162 | 2 | 25 | 938 |
| 40 | 30 | 70 | 160 | 4 | 39 | 940.5 |
| 40 | 50 | 90 | 158 | 6 | 55 | 942.5 |
| 50 | 1 | 51 | 162 | 2 | 15 | 928 |
| 50 | 20 | 70 | 160 | 4 | 29 | 930.5 |
| 50 | 30 | 80 | 159 | 5 | 37 | 932 |
| 50 | 50 | 100 | 157 | 7 | 54 | 933 |
| 60 | 1 | 61 | 162 | 2 | 5 | 918 |
| 60 | 20 | 80 | 159 | 5 | 27 | 922 |
| 60 | 30 | 90 | 158 | 6 | 35 | 922.5 |
| 60 | 50 | 110 | 155 | 9 | 52 | 923 |
| 90 | 1 | 91 | 158 | 6 | 5 | 892.5 |
| 90 | 20 | 110 | 155 | 9 | 22 | 893 |
| 90 | 30 | 120 | 151 | 13 | 37 | 896 |
| 90 | 50 | 140 | 146 | 18 | 55 | 896.5 |
| 150 | 1 | 151 | 145 | 19 | 2 | 837 |
| 150 | 20 | 170 | 139 | 25 | 22 | 839 |
| 150 | 30 | 180 | 137 | 27 | 30 | 840 |
| 150 | 50 | 200 | 134 | 30 | 50 | 841.5 |

*(Full 35-row grid, including `ref_min=10` rows omitted above for space, is
in the machine-readable output; every row was computed, none interpolated.)*

**Reading this grid:** at `dev=31, ref=1` (the loosest combination tested),
only **1 task fails** — `HumanEval/39` (12 < 32). At `dev=150, ref=20` (my
MEGB-03A recommendation), **25 tasks fail** — the 2 blocked tasks plus 23
that were "LIMITED" in the original report. Every additional unit of
`dev_target` beyond ~60 trades away an increasing number of tasks for
diminishing gains in replicate disjointness (§4).

---

## 4. Replicate-ranking analysis for dev_target ∈ {31, 40, 50, 60}

Methodology: for each task and each `dev_target`, form a development pool
of `min(dev_target, unique_count)` cases via a deterministic per-task
ranking (`sha256("dev-pool-v1"|task_id|case_id)`). Within that pool,
generate 5 "O4" replicate sets of 30 cases each, each via an independent
deterministic ranking keyed by a distinct replicate seed
(`sha256("o4-replicate-v1"|seed|task_id|case_id)`), taking the 30
lowest-ranked cases per replicate. Tasks whose pool is `< 30` cannot form
even one replicate (currently only `HumanEval/39`, at every tested target).

| dev_target | tasks excluded (pool<30) | tasks w/ ≥1 duplicate O4 pair | mean pairwise intersection | mean pairwise Jaccard | median ref-only remaining | min ref-only remaining |
|---:|---:|---:|---:|---:|---:|---:|
| 31 | 1 (HumanEval/39) | **43 / 163 (26%)** | 29.0 / 30 | **0.937** | 946 | 14 |
| 40 | 1 (HumanEval/39) | 0 / 163 | 22.5 / 30 | 0.603 | 937 | 5 |
| 50 | 1 (HumanEval/39) | 0 / 163 | 18.1 / 30 | 0.433 | 927 | **0** |
| 60 | 1 (HumanEval/39) | 0 / 163 | 15.1 / 30 | 0.338 | 917 | **0** |

**Key findings:**
- **`dev_target=31` is unusable**: with a pool of only 31 cases to draw 5×30-case
  subsets from, 26% of tasks produce at least one pair of *literally
  identical* O4 replicates (mean Jaccard 0.937 — the "5 replicates" are
  essentially the same set 5 times over). This target fails "differ
  meaningfully" outright, empirically, not just in principle.
- Overlap drops steadily as the target grows (93.7% → 60.3% → 43.3% →
  33.8% mean Jaccard for 31→40→50→60), but never reaches low overlap
  without approaching the full disjoint target of 150 (§5 shows 150 yields
  ~11% median Jaccard).
- At `dev_target ∈ {50, 60}`, at least one task's **reference-only pool
  drops to exactly 0** — this is `HumanEval/55` (45 unique cases; at
  `dev_target=50` its pool is capped at 45, leaving nothing for
  reference-only). **`HumanEval/55` silently fails the "nonempty
  reference-only pool" requirement at these targets even though it can
  still form O4 replicates** — a distinct failure mode from `HumanEval/39`,
  worth flagging explicitly since it wouldn't show up as "cannot form a
  replicate."

---

## 5. Adaptive development-pool-size policy

```
development_count_i = min(target_development_count, unique_cases_i - minimum_reference_count)
```
evaluated at `target=150, minimum_reference=20`, requiring `development_count_i > 30`:

- `HumanEval/39`: `dev_i = 12 - 20 = -8` — **fails structurally** (negative), confirming no policy parameterization rescues this task; it requires a dedicated exception regardless of adaptive tuning.
- `HumanEval/55`: `dev_i = 45 - 20 = 25`, which is `≤ 30` — **still fails the hard floor** even under the adaptive formula. Adaptive sizing does not solve the two-blocked-task problem; it only changes outcomes for tasks that already clear the floor.
- Among the 162 tasks that do clear the floor, **139 hit the full `target=150`** (capped) and **23 get a smaller, task-specific `dev_i`** ranging from 45 to 149.

**Effect on replicate overlap and comparability** (measured as each task's
own 5-replicate mean pairwise Jaccard, using its own `dev_i`):

| Group | mean pairwise Jaccard |
|---|---|
| Tasks at full target (`dev_i=150`, n=139) | median ≈ **0.11** (range ≈ 0.08–0.14) |
| Tasks below target (`dev_i<150`, n=23) | median ≈ 0.20, **worst case 0.487** (`HumanEval/63`, `dev_i=45`) |

**This is the central problem with the adaptive policy**: it makes
replicate overlap *systematically different* across tasks depending on
how much evidence each task happens to have — well-evidenced tasks get
clean, ~11%-overlap replicates, while the 23 evidence-limited tasks get up
to 49%-overlap replicates. If MEGB-04 treats "O4 replicate variance" as a
signal (e.g., comparing measurement stability across the 5 replicates),
that signal would be confounded with evidence volume rather than
reflecting only the property MEGB-04 intends to measure. Adaptive sizing
optimizes disjointness *within* each task at the cost of *comparability*
*across* tasks — a real tradeoff, not a free improvement. **This
reasoning is presented for the record only; the adaptive policy is not
implemented or frozen.**

---

## 6. Feasibility of task-aware supplementary evidence generation

**HumanEval/39 — infeasible.** The documented contract (`1 <= n <= 12`,
integer) defines a domain of exactly 12 elements, and the existing 12
cases already cover all of them (verified directly: `{1,...,12}` exactly).
There is no additional valid input to generate under the pinned EvalPlus
semantics or any other contract-respecting method. Any policy requiring
more than 12 total cases for this task **cannot** be met through
legitimate input generation — full stop. The only paths forward are: (a)
an explicit, approved exception carrying zero or minimal development
evidence for this task while keeping it in the primary 164-task `Q_ref`,
(b) formally excluding it from the primary metric (a significant
amendment — MEGB-03's acceptance criteria require exactly 164 tasks), or
(c) a fundamentally different measurement approach for this one task
(e.g., property-based rather than enumerative evidence) — out of this
addendum's scope.

**HumanEval/55 — technically feasible, not free of new concerns.** The
contract (`n >= 0`, integer) is unbounded, so additional `(n,
fib(n))` cases could be generated by evaluating the pinned EvalPlus
corrected canonical solution at new `n` values not already covered (e.g.
filling domain gaps like 9, 19–26, or extending past 86), using the same
comparison/tolerance semantics (`atol=0.0`) already governing this task.
This is a low-complexity, single-integer-argument, deterministic function
— a comparatively easy case for augmentation if it were ever pursued.

Estimated cases needed for representative target combinations (current:
45 unique):

| Target combination | Required total | Cases needed beyond current 45 |
|---|---:|---:|
| `dev=31, ref=1` (loosest tested) | 32 | 0 (already satisfied) |
| `dev=40, ref=20` | 60 | 15 |
| `dev=50, ref=20` | 70 | 25 |
| `dev=60, ref=20` | 80 | 35 |
| `dev=150, ref=20` (original "OK" target) | 170 | 125 |

**No supplementary cases have been generated.** If augmentation is later
approved, generated cases would need their own explicit provenance tag
(distinct from originally-sourced EvalPlus evidence) and would need oracle
generation via the same trusted canonical-solution execution path used for
existing cases, per CLAUDE.md's general caution against blurring
measurement-construct boundaries and MEGB-03A's own requirement not to
fabricate generic signature-based inputs — augmentation here would be
narrowly contract-bounded, not generic fuzzing, but is still a new kind of
evidence source that would need to be flagged as such.

---

## 7. Policy family comparison

| Policy family | Feasible tasks (at reasonable ref≥20) | Replicate overlap | Handles HumanEval/39 | Handles HumanEval/55 | New provenance concerns |
|---|---|---|---|---|---|
| **(a) Five disjoint O4 replicates** (`dev_target=150`) | 139 / 164 (25 fail) | ~0% (by construction) | No — requires exception regardless | No — requires exception or 125 more cases | None |
| **(b) Five overlapping-but-distinct O4 replicates** (uniform modest target, e.g. 50) | 160 / 164 (4 fail) | ~43% mean Jaccard at target=50 | No — requires exception regardless | No — requires exception at target≥50 (ref-only hits 0) | None |
| **(c) Adaptive dev-pool size** (`target=150, min_ref=20`) | 162 / 164 clear the floor (2 always fail — see §5) | Heterogeneous: ~11% (well-evidenced) to ~49% (limited) | No — dev_i goes negative | No — dev_i=25 still under floor | Cross-task comparability confound (§5) |
| **(d) Task-aware evidence augmentation** | Could reach 164/164 *if* augmentation approved for HumanEval/55 and an exception carved for HumanEval/39 | Depends on target chosen after augmentation | **No — domain is exhausted, augmentation cannot help** | Yes, technically — 15–125 cases depending on target | New evidence-provenance category requiring its own review |

No family, on its own, resolves `HumanEval/39` — every family requires an
explicit exception for this task. Families (a)/(b)/(c) additionally
require an exception (or accept a degraded reference-only pool) for
`HumanEval/55`; only (d) can close that gap for `HumanEval/55` specifically,
at the cost of introducing new evidence-provenance considerations.

---

## 8. Recommendation

**Prioritizing reference-evaluator validity over replicate disjointness,**
my recommendation is:

1. **Adopt policy family (b)** — a uniform, non-adaptive development
   target — over (a) or (c). (a) sacrifices too many tasks and shrinks
   reference-only pools for modest evidence gains; (c) creates the
   cross-task comparability confound documented in §5, which directly
   works against measurement *validity* (the priority this addendum was
   asked to weight). A uniform target keeps every task's reference-only
   pool as large as possible for a given development budget and keeps
   what a "replicate" represents comparable across tasks, even though
   replicates within a task are not perfectly disjoint.
2. **Provisionally suggest `dev_target=50, min_reference=20`** as a
   starting point for MEGB-03B to formally evaluate: satisfies 160/164
   tasks, keeps mean replicate Jaccard at a moderate ~43% (far below the
   31-target's unusable 94%), and leaves a median reference-only pool of
   ~927 cases per task — ample statistical power for `Q_ref`. This is a
   starting point, not a frozen decision.
3. **Handle `HumanEval/39` as a named, permanent exception**: assign all
   12 cases to `reference_only` (development pool = 0 for this task
   specifically), keeping it inside the primary 164-task `Q_ref` rather
   than excluding it. This preserves the "exactly 164" acceptance
   criterion and prioritizes `Q_ref`'s validity directly; the cost is
   confined to MEGB-04, which will simply have no development-visible
   evidence for this one task — a narrower, already-isolated consequence.
4. **Handle `HumanEval/55` the same way for now** (all 45 cases to
   `reference_only`, development pool = 0), rather than pursuing
   augmentation immediately. Augmentation is technically available later
   (§6) if MEGB-04 finds the missing development evidence for this one
   task to be a real practical problem — but adopting it now would add a
   new evidence-provenance category before it's shown to be necessary,
   which cuts against validity-first prioritization (fewer moving parts,
   not more, until a need is demonstrated).
5. **Family (d) (augmentation) is not recommended for adoption now** — file
   it as a documented option to revisit specifically for `HumanEval/55`
   if a future subtask demonstrates the exception in point 4 is
   scientifically costly.

This is a recommendation for approval, not an implemented decision. No
partition, manifest, or supplementary evidence has been created.
