# [MEGB-03] Implement the Privileged Reference Evaluator \(S^*\)

## Epic Status

**Status:** In progress (MEGB-03A accepted; MEGB-03A.1 accepted, supplementary evidence accepted for partition eligibility only; MEGB-03B accepted; MEGB-03C accepted, including addendum commit `a883650`; MEGB-03D accepted; MEGB-03E accepted (original scope, commits `728c601`/`951c309`), Approved Correction v2 pending acceptance (commits `99b921d`/`55435da`); MEGB-03F complete including Approved Correction v2, pending acceptance (commits `410388d`, `99b921d`, `55435da`); MEGB-03G not started, Approved MEGB-03G Compatibility Amendment accepted as a specification-only correction — implementation not yet authorized)  
**Execution mode:** Sequential gated subtasks  
**Subtasks:** MEGB-03A, MEGB-03A.1, MEGB-03B through MEGB-03I  
**Dependencies:** MEGB-01 and MEGB-02, complete

## Epic Objective

Implement the privileged reference evaluator \(S^*\) used to estimate functional correctness for candidate solutions across all 164 HumanEval tasks.

The evaluator must combine:

- the version-pinned benchmark corpus and privilege boundary established in MEGB-01;
- the isolated candidate-execution worker implemented in MEGB-02;
- the original HumanEval and expanded HumanEval+ evidence supplied by the pinned EvalPlus version; and
- a deterministic, frozen partition separating optimization-visible development evidence from reference-only evidence.

The evaluator produces the privileged reference measurement \(Q_{\mathrm{ref}}\). It must never be exposed to, queried by, or used as feedback within candidate generation, revision, or selection.

## Approved Design Amendment

**Amendment precedence:** where any approved amendment in this ticket
(this section and MEGB-03A.1's own amendment content) conflicts with
earlier text elsewhere in this ticket — including hardcoded task counts,
denominators, or task-set language — the amendment governs. Original text
is preserved verbatim throughout as historical context; it is not
authoritative once superseded by an approved amendment.

The original MEGB-03 specification treated the full HumanEval+ suite as \(S^*\). MEGB-04 subsequently required the evidence to be divided into disjoint development and reference-only pools.

This refactored epic moves that partition upstream into MEGB-03A and MEGB-03B so the reference evaluator is constructed around the correct boundary from the outset.

The resulting policies are:

1. **Primary experimental reference measurement:** \(Q_{\mathrm{ref}}\) is computed exclusively from the frozen `reference_only` pool.
2. **Optimization-visible evidence:** MEGB-04 constructs \(S_1 \dots S_4\) exclusively from the disjoint `development` pool.
3. **Compatibility measurement:** conventional full-suite HumanEval+ performance may be computed for upstream parity and diagnostic compatibility, but it must have a distinct evaluator/profile identifier and must not be described as held out.
4. **Freeze timing:** the partition must be versioned, checksummed, and frozen before any experimental candidate is generated.
5. **No silent fallback:** if the pinned corpus cannot support the planned development and reference pools for all 164 tasks, implementation stops and the experimental design is amended explicitly.
6. **164-task validation vs. 163-task experimental aggregation (MEGB-03A.1):**
   `Q_ref` as defined by this epic (MEGB-03E/G) is computed over
   `reference_validation_task_manifest` — all 164 tasks — and this does not
   change. It must never be confused with the *primary factorial
   experiment's* own aggregation (MEGB-04's `Q_meas`/benchmark score and
   MEGB-06's `G(k,N)`/`Q_meas(k,N)`/`Q_ref(k,N)`), which is computed over
   the disjoint `primary_experiment_task_manifest` (expected 163 tasks,
   excluding `HumanEval/39` — see MEGB-03A.1). Any artifact reporting "the
   164 tasks" versus "the primary experiment tasks" must cite the specific
   manifest and its checksum, never a bare count.

## Measurement Claim

The evaluator does not observe true functional correctness directly and must not be described as un-gameable, infallible, or equivalent to formal verification.

It is a privileged reference measurement system:

\[
S^* = (C^*, O^*, M^*, P^*)
\]

where:

- \(C^*\) is functional correctness relative to each HumanEval task specification and documented input domain;
- \(O^*\) is the frozen reference-only HumanEval+ test evidence and trusted expected outcomes;
- \(M^*\) accepts a task only when every required reference-only case satisfies the version-pinned EvalPlus comparison rules; and
- \(P^*\) is deterministic, isolated, non-adaptive execution using the MEGB-02 candidate-execution boundary.

The primary benchmark score is:

\[
Q_{\mathrm{ref}} = \frac{1}{164}\sum_{i=1}^{164} q_{\mathrm{ref},i}
\]

with:

\[
q_{\mathrm{ref},i} =
\begin{cases}
1, & \text{if the candidate passes every required reference-only case for task } i \\
0, & \text{if the candidate produces a validly measured failure} \\
\text{undefined}, & \text{if the measurement itself is invalid.}
\end{cases}
\]

A final 164-task \(Q_{\mathrm{ref}}\) may be reported only when every required task measurement is valid.

## Epic Dependencies

- `[MEGB-01] Establish HumanEval Corpus and Privileged Evaluation Boundary`
- `[MEGB-02] Implement Isolated Candidate Execution Worker`

## Global Architectural Constraints

These constraints apply to every subtask and may not be weakened by a local implementation decision.

### Privileged evaluation boundary

The reference evaluator runs only in the trusted evaluation environment.

Candidate code may receive only:

- its own source code;
- the task entry point;
- one authorized invocation's arguments;
- explicit execution limits; and
- the MEGB-02 protocol version.

Candidate code must never receive:

- canonical solutions;
- expected outputs;
- test-suite source code;
- the complete collection of reference test inputs;
- future test inputs;
- reference-evaluator source code;
- dataset or oracle files;
- aggregate or per-case reference feedback during optimization; or
- prior \(S^*\) results that could influence generation, revision, or selection.

Expected outputs and comparison logic remain on the trusted side of the execution boundary. Candidate code must never execute directly in the trusted controller process.

### No adaptive reference evaluation

A candidate must be frozen before \(S^*\) is invoked.

Every reference evaluation must record:

- candidate artifact hash;
- originating experiment-run and optimization-run identifiers;
- optimization configuration hash;
- candidate-selection rule;
- timestamp at which the candidate was frozen;
- reference-evaluator version; and
- reference-evaluation timestamp.

The evaluator must not operate as an interactive oracle. Reference results may not be returned to the optimizer for revision, reselection, or additional generation within the originating experimental run.

### Valid candidate failure versus invalid measurement

Candidate failures are valid measurements and produce `q_ref_task = 0.0`. They include:

- wrong output;
- syntax error;
- candidate exception;
- timeout;
- memory exhaustion;
- process-limit exhaustion; and
- output-limit exhaustion.

Measurement-system failures produce `q_ref_task = None` and must never be converted into candidate failures. They include:

- missing or corrupt oracle data;
- controller or sandbox-backend failure;
- evaluator serialization defects;
- missing test evidence;
- malformed worker responses; and
- unclassified infrastructure errors.

### Deterministic and versioned measurement process

Dataset, partition, oracle, evaluator, comparison, protocol, execution-profile, and configuration versions must be recorded. Any outcome-affecting change requires a new evaluator or measurement-process version.

### No premature experimental execution

This epic may validate canonical, known-incorrect, synthetic, and fixed parity candidates. It must not evaluate confirmatory experimental candidates before the appropriate MEGB-06 selection-freeze and authorization gate.

## Epic Execution Protocol

Claude or another developer agent must work through the subtasks sequentially.

For each authorized subtask:

1. Read this epic's objective, amendment, global constraints, and current subtask.
2. Inspect the implementation and artifacts produced by completed dependencies.
3. Present a short implementation plan before modifying code.
4. Implement only the current subtask.
5. Run the subtask's required tests and relevant regression tests.
6. Update only the current subtask's status and completion record.
7. Produce the standard checkpoint report.
8. Stop and wait for explicit authorization before starting the next subtask.

Do not begin a later subtask merely because related implementation appears convenient. If unavoidable work overlaps a later subtask, identify the overlap and request approval before proceeding.

Each completed subtask should correspond to a separate commit. Do not rewrite requirements after implementation. Any requirement change must be proposed as a versioned amendment and approved before work continues.

## Standard Checkpoint Report

At the end of every subtask, report:

1. **Summary:** what was implemented or decided.
2. **Files changed:** created, modified, deleted, and intentionally untracked files.
3. **Tests:** exact commands, pass/fail/skip counts, and relevant environment details.
4. **Acceptance matrix:** every criterion marked `PASS`, `FAIL`, `BLOCKED`, or `DEFERRED` with evidence.
5. **Design decisions:** choices that constrain later subtasks.
6. **Deviations:** differences from this specification and why they occurred.
7. **Known limitations:** unresolved technical or scientific limitations.
8. **Handoff artifacts:** paths, identifiers, versions, and checksums produced for the next subtask.
9. **Repository state:** branch, commit status, and proposed commit contents.
10. **Next-step readiness:** whether the next subtask's prerequisites are satisfied.

After producing the report, stop. Do not begin the next subtask.

## Subtask Status

- [x] MEGB-03A — Inventory EvalPlus evidence and validate partition feasibility
- [x] MEGB-03A.1 — Resolve evidence-limited task eligibility
- [x] MEGB-03B — Build and freeze the development/reference partition
- [x] MEGB-03C — Construct the privileged oracle artifact
- [x] MEGB-03D — Validate upstream EvalPlus parity and the validation corpus
- [x] MEGB-03E — Implement typed result models and scoring semantics
- [x] MEGB-03F — Implement the task-level reference evaluator
- [ ] MEGB-03G — Implement aggregation, caching, redaction, and audit
- [ ] MEGB-03H — Calibrate resources and verify deterministic measurement
- [ ] MEGB-03I — Add CLI, configuration, documentation, CI, and final acceptance

---

## MEGB-03A — Inventory EvalPlus Evidence and Validate Partition Feasibility

### Status

**Status:** Accepted

### Objective

Inventory the version-pinned HumanEval/EvalPlus evidence and determine whether every one of the 164 tasks can support the planned optimization-visible development systems and a disjoint reference-only evaluator.

This subtask is analysis and artifact generation. It does not freeze the partition or implement candidate evaluation.

### Dependencies

- MEGB-01 complete.
- MEGB-02 complete.

### Requirements

1. Load the privileged, version-pinned EvalPlus fields established by MEGB-01 for exactly 164 tasks, including:
   - `task_id`;
   - `entry_point`;
   - corrected `canonical_solution`;
   - `base_input`;
   - `plus_input`;
   - task contract metadata where available;
   - comparison tolerance such as `atol`;
   - dataset version; and
   - dataset checksum.
2. Do not generate generic inputs from function signatures.
3. Define a stable, versioned serialization for test inputs and compute stable case identifiers using the task ID and serialized input.
4. Detect exact duplicate cases and serialization collisions before any assignment.
5. Produce a per-task inventory containing:
   - base-case count;
   - plus-case count;
   - unique combined-case count;
   - duplicate counts and provenance;
   - applicable comparison metadata;
   - mutation-sensitive behavior where known; and
   - minimum available cases after deduplication.
6. Evaluate feasibility for:
   - at least 30 development cases per task;
   - a nonempty reference-only pool per task; and
   - five MEGB-04 observation-set replicates whose 30-case `O4` sets can differ meaningfully.
7. Recommend and justify a development-pool size or deterministic allocation rule. A pool of exactly 30 cases is not sufficient if the design claims five distinct `O4` replicates.
8. If any task cannot support the intended design, identify the task and block partition construction. Do not silently reduce its evidence budget.
9. Produce both human-readable and machine-readable inventory artifacts with dataset provenance and checksums.

### Acceptance Criteria

- Exactly 164 version-pinned tasks are inventoried.
- Every eligible case has a stable identifier.
- Duplicates and identifier collisions are detected and reported.
- Development/reference feasibility is reported for every task.
- The recommended allocation supports MEGB-04's nested evidence budgets or explicitly blocks the design.
- Inventory artifacts include dataset version, dataset checksum, algorithm version, and artifact checksum.
- No partition is frozen and no candidate code is executed.

### Required Tests

- Task-count validation.
- Stable-serialization and stable-case-ID tests.
- Duplicate and collision-detection tests.
- Repeated-generation determinism test.
- Dataset-version and checksum validation.
- Insufficient-evidence failure test using a synthetic task.

### Non-Goals

- Assigning cases to development or reference-only pools.
- Constructing expected outputs.
- Implementing `S1–S4`.
- Executing candidate solutions.
- Selecting experimental parameters based on experimental outcomes.

### Handoff Artifacts

- Evidence inventory JSON.
- Human-readable feasibility report.
- Case-serialization and identifier specification.
- Recommended partition configuration.
- Checksums for every artifact.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-03B requires explicit authorization.

### Completion Record

- Status: Accepted (pending explicit authorization to begin MEGB-03B)
- Commit: 81005b9ffc1d1ffb4629c4e8b32d9619c56c4b01
- Completed: 2026-08-01
- Tests: `pytest tests/test_reference_case_serialization.py tests/test_reference_inventory.py -v` — 24/24 passed (6 serialization + 18 inventory, including 3 real-corpus integration tests); full offline suite 106/106 passed; mypy clean (35 files); pylint 10.00/10.
- Deviations: Recommended-policy numeric constants (30 dev / 20 reference-only / 150 target) are MEGB-03A's own justified recommendation, not literal ticket text (the ticket asks for "a" allocation rule with justification, not a specific number). `mutation_sensitive_info` is reported as explicitly unavailable rather than fabricated, since EvalPlus's integrated fields carry no per-case generation-strategy tag.
- Handoff: `artifacts/reference/evidence_inventory.json` (full per-task data, checksum `4086bfb647ccf6bc1d2e15b8f15ed9d9f158f4afa93633ea32d14c9367f2dada`), `artifacts/reference/feasibility_report.md` (human-readable), `artifacts/reference/recommended_partition_config.json` (recommended per-task dev/reference counts). **Two tasks are BLOCKED under the current policy: `HumanEval/39` (12 unique cases) and `HumanEval/55` (45 unique cases after dedup) — MEGB-03B cannot freeze a partition including these two tasks without an explicit, approved design amendment.** 23 tasks are LIMITED (feasible, but only with overlapping O4 replicates); 139 are OK.

---

## MEGB-03A.1 — Resolve Evidence-Limited Task Eligibility

### Status

**Status:** ACCEPTED. Policy finalized, task eligibility resolved, supplementary evidence generated and reviewed (per-task review artifacts produced), and cross-ticket amendments applied. The supplementary evidence's review acceptance (Decision 8) is granted for **partition eligibility only** — expected outputs and semantic oracle validity remain MEGB-03C's responsibility and are not addressed or claimed by this acceptance.

### Objective

Resolve, before any partition is frozen, which of the 164 tasks are eligible
for the primary factorial experiment versus retained only in the 164-task
reference-evaluator validation set — and finalize the uniform
development/reference policy those eligible tasks will use. This subtask
is a decision and specification amendment: it settles per-task
eligibility, finalizes policy constants, classifies every evidence-limited
task, and specifies (without executing) a supplementary-evidence procedure
and the cross-ticket amendments needed so validation and experimental
scores can never be confused. It does not assign partition membership,
generate supplementary evidence, modify evaluator code, or begin MEGB-03B.

This subtask exists because MEGB-03A's decision-analysis addendum's
recommendation to assign zero development cases to evidence-limited tasks
was rejected: a task with zero development-visible evidence has no
optimization-visible measurement and therefore no defined gaming event,
which is incompatible with MEGB-04/06's experimental design (every task in
the primary factorial experiment must be measurable by *both* an
optimization-visible system and the reference evaluator).

### Dependencies

- MEGB-03A complete and accepted.
- The MEGB-03A partition-policy decision-analysis addendum accepted.

### Approved Design Principles

1. The MEGB-03 reference-evaluator validation set retains all 164 tasks —
   `Q_ref` and the reference-evaluator validation described in MEGB-03C–H
   are never reduced below 164 tasks.
2. The primary factorial experiment (MEGB-04/05/06) includes only tasks
   that can support all four visible evidence budgets MEGB-04 defines
   (\(O_1{=}1, O_2{=}3, O_3{=}10, O_4{=}30\), nested subsets of one
   development pool per task) and a nonempty, scientifically defensible
   reference-only pool.
3. `HumanEval/39` is **provisionally excluded a priori** from the primary
   factorial experiment: its complete legitimate domain (contract `1 <= n
   <= 12`, integer) has exactly 12 inputs, and all 12 are already present
   in the pinned evidence (verified in the MEGB-03A addendum, §1 and §6).
   It remains in the 164-task reference-evaluator validation set.
4. `HumanEval/55` is **provisionally designated for systematic,
   task-contract-derived augmentation** before partitioning, rather than
   exclusion — its domain (`n >= 0`, integer) is unbounded.
5. `development_target = 40` and `minimum_reference_only = 30` are adopted
   as the leading uniform policy for evaluation in this subtask. Replicates
   may overlap but must be distinct (no two of a task's five O4 replicates
   may be literally identical). This is a stricter reference floor than
   MEGB-03A's original recommendation (20) and a lower development target
   (40, not 150) — see Requirement 1 for why.
6. Every task with fewer than 70 unique legitimate cases (i.e., failing
   `development_target=40 + minimum_reference_only=30`) must be
   individually classified as finite/exhausted or augmentable, with an
   exclusion or augmentation recommendation.
7. `HumanEval/55` requires a specified (not executed) deterministic
   supplementary-input procedure, including provenance, versioning,
   independent review, resource calibration, and checksum requirements.
8. Two explicit manifests must be defined:
   `reference_validation_task_manifest` (164 tasks) and
   `primary_experiment_task_manifest` (expected 163 tasks, subject to the
   remaining eligibility review in Requirement 2 below).
9. Amendments required to MEGB-03 through MEGB-06 so benchmark-validation
   scores (164-task `Q_ref`) and primary-experiment scores (163-task,
   pending final review) can never be confused must be specified.

### Requirements

1. **Evaluate and record the `development_target=40,
   minimum_reference_only=30` policy.** This combination was already
   computed in the MEGB-03A addendum (§3, §4): 160/164 tasks satisfy it
   (4 fail — see Requirement 2), and at `development_target=40` zero tasks
   produce literally duplicate O4 replicate sets (mean pairwise Jaccard
   0.603 — overlapping but distinct, satisfying Design Principle 5's hard
   constraint). Record this evaluation as the finalized policy pending
   authorization of MEGB-03B, superseding MEGB-03A's original
   `dev=150/ref=20` recommendation.

2. **Identify and classify every task with fewer than 70 unique cases.**
   Exactly four tasks fail `development_target=40 + minimum_reference_only=30
   = 70` under the pinned corpus:

   | Task | Unique cases | Entry point | Domain | Classification | Recommendation |
   |---|---:|---|---|---|---|
   | `HumanEval/39` | 12 | `prime_fib` | `1 <= n <= 12` (12 integers) | **Finite, exhausted** (12/12 covered) | Exclude from primary experiment (Design Principle 3); retain in validation |
   | `HumanEval/55` | 45 | `fib` | `n >= 0` (unbounded) | Augmentable | Augment before partitioning (Design Principle 4); needs +25 cases to reach 70 |
   | `HumanEval/6` | 69 | `parse_nested_parens` | balanced-paren strings over `"(", ")", " "` (unbounded) | Augmentable | Augment; needs +1 case to reach 70 |
   | `HumanEval/63` | 65 | `fibfib` | `n >= 0`, integer (unbounded) | Augmentable | Augment; needs +5 cases to reach 70 |

   Only `HumanEval/39` has a domain that is structurally incapable of
   supplying more legitimate evidence; the other three have unbounded
   domains and are classified augmentable, at modest estimated cost (1–25
   cases). This inventory must be re-verified against whatever dataset
   version is pinned at MEGB-03B execution time — these counts are tied to
   human-eval==1.0.3 / evalplus==0.3.1.

3. **Specify (do not execute) a deterministic supplementary-input
   procedure for `HumanEval/55`** (and, if approved, `HumanEval/6` and
   `HumanEval/63`), covering at minimum:
   - **Domain-derived generation rule:** sample additional non-negative
     integers not already covered by the existing 45 cases (e.g. filling
     domain gaps such as 9 and 19–26, or extending beyond the current
     maximum of 86), respecting the documented contract exactly — no
     signature-based generic fuzzing.
   - **Provenance:** every generated case must carry an explicit
     `evidence_source` tag (e.g. `megb-contract-augmentation-v1`)
     distinguishing it from originally-sourced EvalPlus evidence in every
     downstream artifact (inventory, partition manifest, oracle records).
   - **Versioning:** a dedicated augmentation-algorithm version, recorded
     alongside the existing `case_id_algorithm_version` /
     `inventory_algorithm_version` scheme from MEGB-03A.
   - **Independent review:** augmented cases must be reviewed against the
     pinned EvalPlus canonical solution and contract before acceptance —
     specify who/what performs this review (e.g. a fixed validation script
     comparing contract satisfaction and canonical-solution executability)
     and what "review passed" means operationally.
   - **Resource calibration:** augmented cases must go through the same
     MEGB-02 execution-limit calibration as existing evidence (no
     special-cased execution profile).
   - **Checksum requirements:** the augmented-case set must have its own
     checksum, and any oracle artifact incorporating it (MEGB-03C) must
     record both the original and augmented case-set checksums separately.

4. **Define two explicit manifests** (schemas and field lists only — no
   instances constructed yet):
   - `reference_validation_task_manifest`: exactly 164 task IDs, used
     exclusively by MEGB-03's own reference-evaluator construction and
     validation (MEGB-03C through 03H). Never described as the primary
     experiment's task set.
   - `primary_experiment_task_manifest`: expected 163 task IDs (164 minus
     `HumanEval/39`), subject to final confirmation once Requirement 3's
     augmentation decisions for `HumanEval/6`/`HumanEval/55`/`HumanEval/63`
     are resolved. Used exclusively by MEGB-04/05/06. Must record which
     tasks were augmented and under which augmentation version.
   - Both manifests must carry independent checksums, and any artifact
     referencing "the 164 tasks" versus "the primary experiment tasks"
     must cite the specific manifest and its checksum, never a bare count.

5. **Specify required cross-ticket amendments** so benchmark-validation
   and experimental scores cannot be confused:

   - **MEGB-03** (this epic): `Q_ref` (MEGB-03E/G) is computed over
     `reference_validation_task_manifest` (164 tasks) — already the
     design; no change needed beyond citing the manifest explicitly by
     name once it exists (MEGB-03E/G should reference
     `reference_validation_task_manifest`'s checksum, not a bare "164").

   - **MEGB-04** currently assumes a single, undifferentiated 164-task
     population (`expected_task_count: 164` in its configuration;
     `Q_meas^(k) = (1/164) * sum_{i=1}^{164} ...` in Requirement 8). It
     must be amended to:
     (a) construct \(S_1 \ldots S_4\) and their five O4 replicates only
     over `primary_experiment_task_manifest` (163 tasks, pending final
     count);
     (b) change its benchmark-aggregation denominator from the literal
     164 to `len(primary_experiment_task_manifest)`, citing that
     manifest's checksum in every aggregate result; and
     (c) explicitly document that `HumanEval/39` (and any task ultimately
     excluded rather than augmented) has no \(S_1 \ldots S_4\)
     measurement and is therefore absent from every MEGB-04 aggregate,
     while still appearing in MEGB-03's reference-evaluator validation.

   - **MEGB-05** does not hardcode a task count and requires no amendment
     beyond consuming `primary_experiment_task_manifest` wherever it
     currently assumes "every task."

   - **MEGB-06** currently hardcodes "all 164 HumanEval tasks" as its fixed
     task set (Experimental Design), requires "exactly 164 public tasks"
     in its Preflight Validation Gate, sums primary/secondary outcomes
     over \(i=1\) to 164, and requires the factorial matrix to "cover all
     164 tasks." Every one of these must be amended to reference
     `primary_experiment_task_manifest` and its resolved count (expected
     163, not 164) instead of a literal 164. This is a material amendment,
     not cosmetic: MEGB-06 §17 (Failure and Exclusion Policy) already
     forbids excluding any task, stream, replicate, or condition *after
     unblinding* — which confirms task-eligibility decisions like this one
     belong here, before preregistration, and must be finalized (not
     revisited) once MEGB-06's preregistration is filed.

### Acceptance Criteria

- `development_target=40, minimum_reference_only=30` is evaluated against
  the full 164-task inventory and its outcome (satisfying/failing task
  counts, duplicate-O4-set incidence, mean pairwise Jaccard) is recorded.
- Every task with fewer than 70 unique cases is individually identified,
  classified finite/exhausted or augmentable, and given an explicit
  exclusion or augmentation recommendation.
- `HumanEval/39` is documented as provisionally excluded from the primary
  experiment and retained in the reference-evaluator validation set.
- `HumanEval/55` is documented as designated for augmentation, with a
  fully specified (not executed) procedure covering generation rule,
  provenance, versioning, independent review, resource calibration, and
  checksums.
- Both manifests (`reference_validation_task_manifest`,
  `primary_experiment_task_manifest`) have documented schemas, expected
  counts, and checksum requirements, without any instance yet constructed.
- Required amendments to MEGB-04 and MEGB-06 (and confirmation that
  MEGB-03/05 need none beyond manifest citation) are specified concretely
  enough to be applied as ticket edits without further analysis.
- No partition membership is assigned, no supplementary evidence is
  generated, no evaluator code is modified, and MEGB-03B is not begun.

### Required Tests

None — this subtask produces specification and decision documents only,
consistent with its non-goals. (Contrast with MEGB-03A, which produced
executable inventory code with tests; this subtask's "evaluation" of the
`dev=40/ref=30` policy reuses MEGB-03A's already-tested inventory code and
existing test suite rather than adding new production code.)

### Non-Goals

- Assigning any case to `development` or `reference_only`.
- Generating any supplementary evidence for `HumanEval/6`, `HumanEval/55`,
  or `HumanEval/63`.
- Constructing either manifest as a real, checksummed artifact.
- Modifying MEGB-04, MEGB-05, or MEGB-06 ticket text directly (this
  subtask specifies the required amendments; applying them to those
  ticket files is out of scope here).
- Beginning MEGB-03B.

### Handoff Artifacts

- This ticket section (MEGB-03A.1) itself, as the specification record.
- The task-eligibility classification table (Requirement 2).
- The supplementary-input procedure specification for `HumanEval/55`
  (Requirement 3).
- The two manifest schema definitions (Requirement 4).
- The cross-ticket amendment specification (Requirement 5).

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-03B requires
explicit authorization, and its own authorization now additionally
requires the `HumanEval/6`/`HumanEval/55`/`HumanEval/63` augmentation
decisions from this subtask to be resolved (approved, executed, or
explicitly deferred) — not merely specified.

### Completion Record

- Status: ACCEPTED
- Commits: d56231a (execution), 4b8362d (commit-hash record)
- Completed: 2026-08-01
- Tests: `pytest tests/test_reference_augmentation.py -v` — 13/13 passed; full offline suite 119/119 passed; mypy clean (37 files); pylint 10.00/10.
- Deviations: None from the authorized decisions. The `development_target=40`/`minimum_reference_only=30` policy evaluation and the `<70`-case classification both reused MEGB-03A's already-computed grid data rather than recomputing, since nothing about the underlying corpus changed.
- Handoff: `src/reference/augmentation.py` (generators, contract validation, feasibility checks, checksums); `artifacts/reference/augmentation/generation_procedures_v1.{md,json}` (frozen procedure, checksum `31705af14ef914a8b495d980c3a9a962b4039b1f6aa574cdad85c706e7289c00`); `artifacts/reference/augmentation/{humaneval_55,humaneval_63,humaneval_6}_review.md` (per-task review artifacts — Decision 7); `artifacts/reference/augmentation/augmentation_results.json` (machine-readable summary). Combined unique-case counts achieved: HumanEval/55 = 202 (45 original + 157 accepted), HumanEval/63 = 202 (65 original + 137 accepted), HumanEval/6 = 287 (69 original + 218 accepted) — all comfortably exceed the >=100 target. Zero candidates were contract-rejected or infeasible across all three tasks. **All generated evidence requires your explicit review acceptance (Decision 8) before MEGB-03B may use it.**

---

## MEGB-03B — Build and Freeze the Development/Reference Partition

### Status

**Status:** ACCEPTED. Executed per the MEGB-03A.1-authorized execution rules (163-task `primary_experiment_task_manifest`, 40/≥30 split, `HumanEval/39` excluded; 164-task `reference_validation_task_manifest`, unsplit) and artifact-finalized per the subsequent privileged-artifact-policy authorization (see `docs/measurement/privileged-artifact-policy.md`). Commits `471a4b0` and `1748685`. See the "Requirements" text above for the original specification and the completion record below for what was actually executed and any deviations.

### Objective

Create, validate, and freeze the deterministic manifest assigning every eligible case to exactly one of two disjoint pools: `development` or `reference_only`.

### Dependencies

- MEGB-03A complete and accepted.
- MEGB-03A.1 complete and accepted (task eligibility resolved, policy finalized, manifests specified).
- Partition configuration explicitly approved.

### Requirements

1. Consume the evidence inventory and approved allocation rule from MEGB-03A.
2. Operate independently for every task.
3. Use the versioned MEGB input serialization and stable case identifiers.
4. Use a deterministic, documented SHA-256 ranking procedure incorporating:
   - partition algorithm version;
   - frozen partition seed;
   - task ID; and
   - stable case ID.
5. Never use Python runtime hashes or platform-dependent ordering.
6. Assign every eligible unique case to exactly one pool.
7. Ensure the development pool satisfies the approved MEGB-04 evidence and replicate requirements.
8. Preserve a nonempty, scientifically useful reference-only pool for every task.
9. Prohibit overlap between development and reference-only evidence.
10. Record base/plus provenance for each case without changing the pool assignment semantics.
11. Record:
    - dataset version and checksum;
    - partition algorithm and version;
    - partition seed;
    - per-task case counts;
    - ordered stable case IDs;
    - case provenance;
    - creation timestamp; and
    - manifest checksum.
12. Freeze the manifest before any experimental candidate generation.
13. Treat any later outcome-affecting partition change as a new partition version and experimental amendment.
14. Expose only development case identifiers—not expected outputs—through artifacts intended for MEGB-04.

### Acceptance Criteria

- Every eligible unique case appears exactly once.
- Development and reference-only pools are disjoint for every task.
- All 164 tasks satisfy the approved minimum counts.
- Repeated construction with the same inputs produces the same manifest checksum.
- Altering the seed or algorithm version changes the manifest identity.
- The manifest is immutable once marked frozen.
- Public and optimization-visible views cannot carry expected outputs or reference-only cases.

### Required Tests

- Exhaustive assignment and disjointness tests.
- Per-task minimum-count tests.
- Stable-order and deterministic-checksum tests.
- Seed/version sensitivity tests.
- Manifest-tamper detection.
- Public-view redaction tests.
- Freeze-state transition tests.

### Non-Goals

- Generating MEGB-04 observation-set replicates.
- Constructing oracle outputs.
- Evaluating candidates.
- Repartitioning after inspecting experimental results.

### Handoff Artifacts

- Frozen privileged partition manifest.
- Redacted development-pool manifest/view.
- Partition-validation report.
- Partition checksum and version.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-03C requires explicit authorization.

### Completion Record

- Status: ACCEPTED (per MEGB-03A.1's authorized execution rules and the subsequent privileged-artifact-policy authorization — see both "Standard Checkpoint Report"s for full detail)
- Commits: aabee566b7b0cc5eaf19b5c5405365b98e8aae0a (initial partition execution, excludes the two large full manifests); 471a4b0 (artifact-finalization: lock file, build/verify CLI, tests, docs; this commit record)
- Completed: 2026-08-01
- Tests: `pytest tests/test_reference_partition.py tests/test_reference_partition_lock.py -v` — 26/26 passed (18 partition tests + 8 new lock tests, including regression tests for two real determinism bugs found and fixed — see Deviations). Full offline suite 145/145 passed. mypy clean (32 files in `src/`). pylint 10.00/10.
- Deviations:
  1. **Cross-process determinism bug (initial execution)**: `DatasetProvenance.loaded_at` (a fresh wall-clock timestamp on every `load_provenance()` call) was embedded, unstripped, in both manifests' checksummed payload, making every manifest checksum spuriously non-reproducible across separate process runs even though nothing about the corpus or code had changed. The in-process "rebuild is byte-stable" test had passed only because it reused one cached provenance object rather than reloading it, masking the bug. Fixed by stripping `dataset_provenance.loaded_at` before hashing (mirroring MEGB-03A's own earlier `generated_at`-stripping fix); added a dedicated regression test constructing two provenance objects differing only in `loaded_at` and asserting equal checksums; verified by running the driver as two separate OS processes and confirming identical checksums.
  2. **Second, related determinism bug (artifact-finalization)**: while implementing the privileged-artifact lock, discovered that the same two volatile fields (`generated_at`, `dataset_provenance.loaded_at`) were still embedded unstripped in the manifest *dataclass instances themselves* (only the temporary hashing payload had them stripped) — so writing the full manifest to disk and rebuilding it in a fresh process produced different file bytes on every run, even though `manifest_checksum` itself was stable. This would have broken `verify`'s "regenerate and compare bytes" requirement. Fixed by adding `_stabilized_manifest_payload()` (strips both fields before serializing to bytes) and using it for every privileged-artifact write and verification comparison; confirmed by running `build` twice in separate processes and `verify` afterward, all producing byte-identical output.
  3. **Module split for a real pylint failure, not preference**: the lock/verification code was first written inline in `partition.py`, which then failed pylint's module line-count ceiling (1012/1000). Rather than disable the check, split the privileged-artifact lock logic into a new `src/reference/partition_lock.py`, and the CLI (`build`/`verify` argparse entry point, which needs symbols from both) into a new `src/reference/partition_cli.py` — this also resolved a genuine circular-import risk (`partition_lock` depends on `partition`; putting the CLI in `partition.py` would have made `partition` depend back on `partition_lock`). The build/verify entry point is now `python -m src.reference.partition_cli {build|verify}`.
- Handoff:
  - Library: `src/reference/partition.py` (ranking, partition/manifest construction, validation, redaction, `load_real_corpus_inputs`); `src/reference/partition_lock.py` (`LockEntry`/`LockFile`, `write_privileged_artifacts`, `verify_against_lock`, `FrozenArtifactConflictError`, `ManifestKindMismatchError`); `src/reference/partition_cli.py` (`build`/`verify` CLI).
  - Committed artifacts: `artifacts/reference/partition/{primary_experiment_task_manifest_redacted.json,partition_validation_report.md,partition.lock.json}`.
  - Privileged (gitignored, not in git) artifacts: `artifacts/privileged/reference/partition/{primary_experiment_task_manifest.json,reference_validation_task_manifest.json}` — present on disk, verified via `python -m src.reference.partition_cli verify` (PASS on both).
  - Final lock checksums (from `partition.lock.json`, `lock_schema_version: partition-lock-v1`):
    - `primary_experiment_task_manifest`: `logical_sha256=c85ec9d3cd073821e06b875ccb54e9a7d2b958eeb093dd30afda37f2d5ac1b71`, `size_bytes=9517190`, `expected_task_count=163`.
    - `reference_validation_task_manifest`: `logical_sha256=832620da24471ffe85946fc1ccac7e7ff8a375ab16a452b0b2d60a1b9d8a59b9`, `size_bytes=9486515`, `expected_task_count=164`.
  - These `logical_sha256` values are unchanged from the initial execution's manifest checksums — the artifact-finalization work relocated and anchored the artifacts without altering partition content.
  - Artifact policy: see `docs/measurement/privileged-artifact-policy.md` for the full policy (what's committed vs. privileged, lock-file schema, build/verify CLI, determinism note, backup requirement, and the default-policy statement for MEGB-03C oracle artifacts).

---

## MEGB-03C — Construct the Privileged Oracle Artifact

### Status

**Status:** ACCEPTED. Executed per the "Approved Execution Amendment (MEGB-03C)" below; the "Requirements" text beneath it is preserved as historical/original context per this ticket's amendment-precedence rule. Commits `cf25124` and `cbd4fad`.

### Approved Execution Amendment (MEGB-03C)

Authorized execution rules (supersede conflicting original "Requirements" text below per this ticket's amendment-precedence rule):

1. Before oracle construction, run the MEGB-03B lock verification (`python -m src.reference.partition_cli verify`) and refuse to continue unless both frozen manifests reproduce exactly.
2. Construct physically separated expected-output artifacts:
   - development oracle: the 40 development cases for each of the 163 experimental tasks; intended only for the trusted side of MEGB-04;
   - reference-only oracle: every reference-only case for the 163 experimental tasks; intended only for S\*;
   - reference-validation-only oracle: `HumanEval/39`'s complete 12-case domain.
3. Create a composite 164-task reference-validation manifest that references those physically separated artifacts without duplicating expected-output bytes.
4. Preserve strict access boundaries: MEGB-04 may later mount only the development oracle; S\* may mount the reference-only oracle; the 164-task validation workflow may resolve the composite; candidate code and candidate-generation/selection runtimes may mount none of them.
5. Use the corrected, pinned EvalPlus canonical solutions and comparison semantics, preserving task-specific tolerances, normalization behavior, input-mutation semantics, stable case identifiers, evidence provenance, partition membership, canonical-solution hashes, and dataset/augmentation/partition/implementation versions.
6. Never replace EvalPlus comparison behavior with universal Python equality.
7. For supplementary HumanEval/6, /55, and /63 inputs: generate expected outputs only now; bind them to the accepted supplementary-input checksums; record their provenance separately; fail oracle construction if the corrected canonical solution or comparison procedure cannot produce an unambiguous valid oracle; never drop a difficult supplementary case silently.
8. Distinguish oracle-generation failure from candidate failure. No candidate code is executed in this subtask.
9. Apply the established privileged-artifact policy (`docs/measurement/privileged-artifact-policy.md`): full oracle bytes remain under `artifacts/privileged/` and outside git; committed machine-readable lock records anchor their identities; committed artifacts may include schemas, counts, provenance, checksums, generation commands, and redacted reports — but no expected outputs; regeneration and verification must be deterministic and byte-stable; frozen mismatch must fail rather than overwrite; `--force` requires an explicit new artifact version or approved amendment.
10. The oracle lock must record: artifact and profile identity; authorized consumer; task and case counts; dataset, augmentation, and partition checksums; canonical-solution hashes; comparison-profile versions; generator/code revision; logical and byte-level checksums; byte sizes; generation command; and freeze state.
11. Required tests (at least): complete case coverage with no missing/duplicate oracle records; separation of development, reference-only, and `HumanEval/39` validation artifacts; floating-point tolerance behavior; normalization behavior; mutation-sensitive cases; supplementary-evidence handling; corrupt/missing partition and source artifacts; canonical-generation failure classification; deterministic cross-process regeneration; lock mismatch and silent-overwrite refusal; public/redacted artifact leakage; and authorized-consumer boundaries.
12. Document the access model and backup requirement; no external upload is performed in this subtask.

Non-goals unchanged from below: no upstream parity validation (MEGB-03D), no candidate-level evaluation.

### Objective

Construct or load trusted expected results for the frozen evidence using the version-pinned EvalPlus ground-truth and comparison procedures.

### Dependencies

- MEGB-03B complete and accepted.

### Requirements

1. Use corrected, version-pinned EvalPlus canonical solutions.
2. Generate expected results only in the trusted environment.
3. Follow EvalPlus task-specific comparison semantics.
4. Preserve configured floating-point tolerances.
5. Support task-specific normalization where required.
6. Handle input mutation according to EvalPlus semantics.
7. Distinguish oracle-generation failure from candidate failure.
8. Never replace EvalPlus comparison behavior with a universal Python `==`.
9. Materialize or cache expected results as a versioned privileged artifact.
10. Bind every oracle record to:
    - task ID;
    - stable case ID;
    - pool membership;
    - input provenance;
    - expected-output representation;
    - comparison profile; and
    - oracle-generation status.
11. Include artifact-level metadata:
    - dataset version and checksum;
    - partition version and checksum;
    - oracle implementation version;
    - generation timestamp;
    - canonical-solution hashes;
    - base, plus, development, and reference-only case counts;
    - comparison-profile versions; and
    - artifact checksum.
12. Store expected outputs and comparison logic behind the privileged boundary.
13. Refuse construction when dataset, partition, or canonical-solution checksums do not match.

### Acceptance Criteria

- Every frozen eligible case has one valid oracle record or an explicit oracle-generation failure.
- No missing or duplicate oracle records exist.
- Tolerance, normalization, and mutation semantics are represented.
- Oracle failures cannot be serialized as candidate failures.
- Artifact checksums detect modification.
- No optimizer-visible artifact contains expected outputs.

### Required Tests

- Oracle record construction and serialization.
- Floating-point tolerance cases.
- Task-specific normalization cases.
- Mutation-sensitive cases.
- Missing/corrupt source artifact tests.
- Oracle-generation failure classification.
- Privileged/public-view redaction tests.

### Non-Goals

- Proving parity with upstream across a candidate corpus; that belongs to MEGB-03D.
- Executing arbitrary candidate code.
- Implementing task- or benchmark-level scoring.

### Handoff Artifacts

- Versioned privileged oracle artifact.
- Comparison-profile registry.
- Oracle-generation report and checksums.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-03D requires explicit authorization.

### Completion Record

- Status: ACCEPTED (per the "Approved Execution Amendment (MEGB-03C)" above); addendum commit `a883650` (pre-MEGB-03D verification fixes, see below) does not change this acceptance
- Commits: cf25124, cbd4fad, a883650 (addendum)
- Completed: 2026-08-01
- Tests: `pytest tests/test_reference_oracle.py tests/test_reference_oracle_lock.py -v` — 30/30 passed (21 oracle-construction tests including 1 integration smoke test against the real corpus; 9 oracle-lock tests). Full offline suite 175/175 passed. Full integration-marked (non-Docker) suite 9/9 passed. mypy clean (47 files across `src/` + `tests/`). pylint 10.00/10 for `src/` + `tests/` (one pre-existing, out-of-scope duplicate-code finding between `src/reference/partition_cli.py` and `tests/test_reference_partition_lock.py` — both already-accepted MEGB-03B code, predating this subtask; flagged as a background task rather than fixed here).
- Addendum (commit `a883650`, before MEGB-03D began): pre-flight verification requested ahead of parity execution surfaced two real gaps, both fixed:
  1. An oracle build could complete diagnostic construction with an unresolved original-provenance generation failure recorded explicitly, yet still be frozen into a privileged release and pass verification — the failure was visible per-record but never actually blocked release. `write_privileged_oracle_artifacts`/`verify_oracle_against_lock` now call `require_release_ready()` first and raise `UnresolvedGenerationFailureError` (writing/verifying nothing) if any record has a non-success status; `oracle_cli`'s `build` checks this before writing the committed composite manifest too.
  2. `sys.set_int_max_str_digits(0)` was a permanent, process-wide mutation set at import time. Replaced with a context manager (`unbounded_int_str_digits`) confined to exactly the oracle serialization/deserialization calls that can touch a huge int, restoring the prior process value via `try`/`finally` even on exception.
  Both covered by new regression tests; re-verified against the real corpus (`oracle_cli verify`, unaffected since it has zero generation failures).
- Deviations (original execution):
  1. **A third determinism-class bug, caught before it reached the artifact**: some canonical solutions (HumanEval/83, HumanEval/139) produce legitimate integers over a million digits on their largest `plus_input` cases. CPython 3.11+'s integer-string-conversion-length guard rejects `json.dumps`/`str()` on such integers by default (a DoS hardening measure, irrelevant here since these are pinned-benchmark values, not attacker input). Fixed via `sys.set_int_max_str_digits(0)` in `oracle.py`, documented inline (see addendum above for the subsequent scoping fix).
  2. **Module split for `duplicate-code`, not just line-count**: `oracle_lock.py` and `oracle_cli.py` deliberately mirror `partition_lock.py`/`partition_cli.py`'s write/verify/CLI patterns (same lesson-learned stabilized-payload fix, same refuse-silent-overwrite/on-disk-vs-rebuild verification shape). Consolidating into one shared base was not authorized in this subtask ("execute only MEGB-03C") since `partition_lock.py`/`partition_cli.py` are already MEGB-03B-accepted; the resulting `pylint` `duplicate-code` findings are suppressed with documented, file-scoped disables rather than silently ignored, and consolidation is noted as sensible future cleanup.
  3. **Two severities for oracle-generation failure, not one**: an original-provenance (upstream EvalPlus) case that fails oracle generation is recorded as an explicit `ORACLE_STATUS_GENERATION_FAILED` record and the build continues (matching the original ticket's acceptance criterion "one valid oracle record or an explicit oracle-generation failure"); a supplementary-provenance (MEGB-03A.1) case that fails aborts the whole build with `AmbiguousSupplementaryOracleError` and writes nothing (matching the amendment's stricter requirement 7). On the real corpus, zero cases of either kind failed — 124,493/124,493 succeeded.
  4. **Comparison semantics reused, not reimplemented**: `compare_outputs`/`comparison_profile_for_task` call EvalPlus's own `is_floats`/`_poly` (from the pinned `evalplus==0.3.1`) directly rather than re-deriving the tolerance/special-oracle math independently, per requirement 6 ("never replace EvalPlus comparison behavior with universal Python equality"). HumanEval/32 (`find_zero`) is the only HumanEval-specific special oracle in EvalPlus's comparison code; MBPP's special oracles don't apply since MEGB only evaluates HumanEval.
  5. **`partition.py` extended, not modified in effect**: added `gather_eligible_cases_and_args` (and args-preserving variants of the existing private case-reconstruction helpers) so oracle construction can recover each case's actual argument tuple; the existing `gather_eligible_cases` is now a thin wrapper delegating to the new function, with identical behavior — confirmed by the full pre-existing MEGB-03B test suite (26 tests) still passing unchanged.
- Handoff:
  - Library: `src/reference/oracle.py` (`ComparisonProfile`/`compare_outputs`/`comparison_profile_for_task`, `OracleRecord`/`generate_oracle_record`, `OracleArtifact`/`build_oracle_artifacts`, `ReferenceValidationCompositeManifest`, `AmbiguousSupplementaryOracleError`); `src/reference/oracle_lock.py` (`OracleLockEntry`/`OracleLockFile`, `write_privileged_oracle_artifacts`, `verify_oracle_against_lock`, `FrozenArtifactConflictError`, `ManifestKindMismatchError`); `src/reference/oracle_cli.py` (`build`/`verify` CLI, with the mandatory MEGB-03B partition-lock pre-check).
  - Committed artifacts: `artifacts/reference/oracle/{reference_validation_composite_manifest.json,oracle.lock.json}`.
  - Privileged (gitignored, not in git) artifacts: `artifacts/privileged/reference/oracle/{development_oracle.json,reference_only_oracle.json,reference_validation_only_oracle.json}` — present on disk, verified via `python -m src.reference.oracle_cli verify` (PASS on all three).
  - Final lock checksums (from `oracle.lock.json`, `lock_schema_version: oracle-lock-v1`):
    - `development_oracle`: `logical_sha256=80662e4176be9bed96bb2de74b23cad59815c3485ca0cc736eb972cb7ae2514b`, `size_bytes=463936464`, 163 tasks, 6,520 cases, `trusted_consumers=["MEGB-04-trusted-side"]`.
    - `reference_only_oracle`: `logical_sha256=aca19c40e464ba1ba9c884d4fa5a2439726bea563c03c832a6d939cbd483123c`, `size_bytes=723830836`, 163 tasks, 117,961 cases, `trusted_consumers=["S*"]`.
    - `reference_validation_only_oracle`: `logical_sha256=be3d0db9c5fc3457bb8ce34a5b3935d7ca832065cb953d3ceee7a1c75f639933`, `size_bytes=5871`, 1 task (`HumanEval/39`), 12 cases, `trusted_consumers=["MEGB-03D"]`.
    - Composite manifest checksum: `565a263f179d4870ea5c4f4ab6f4929ce2c8c64174cc4fef645251826b4f8e29` (164 tasks indexed; zero reference-only or `HumanEval/39` case IDs committed, per the same boundary MEGB-03B established for development-pool-only committed IDs).
  - Total real-corpus coverage: 6,520 + 117,961 + 12 = 124,493 cases, matching MEGB-03B's frozen validation-manifest total exactly; zero oracle-generation failures.
  - Policy: `docs/measurement/privileged-artifact-policy.md` extended with the concrete MEGB-03C oracle section (access model / authorized-consumer table, lock-field extensions, resource note on the ~1.2 GB combined privileged size, backup requirement).
  - Flagged, not fixed here: a pre-existing `pylint` `duplicate-code` finding between two already-accepted MEGB-03B files (`src/reference/partition_cli.py` / `tests/test_reference_partition_lock.py`), spun off as a background task rather than touched under this subtask's "execute only MEGB-03C" scope.

---

## MEGB-03D — Validate Upstream EvalPlus Parity and the Validation Corpus

### Status

**Status:** Executed, pending your acceptance. See the "Approved Execution Amendment (MEGB-03D)" below for the authorized construction rules; the "Requirements" text beneath it is preserved as historical/original context per this ticket's amendment-precedence rule.

### Approved Execution Amendment (MEGB-03D)

Authorized execution rules (supersede conflicting original "Requirements" text below per this ticket's amendment-precedence rule):

1. Freeze a nonexperimental parity/validation corpus before running parity analysis.
2. Include: corrected canonical solutions; candidates failing original HumanEval evidence; candidates passing original evidence but failing expanded EvalPlus evidence; hardcoded candidates; boundary-condition failures; type-handling failures; numerical-tolerance failures; mutation-sensitive failures; stateful candidates; and resource-exhausting candidates where the MEGB-02 validation harness can classify them safely.
3. Include at least one validated `PASS_BASE_FAIL_PLUS` candidate. Preserve its task, source hash, provenance, and upstream/MEGB classifications.
4. Compare the pinned upstream EvalPlus implementation with the MEGB oracle/comparison layer on the fixed corpus.
5. Require task-level classification agreement for every upstream-comparable sample. A mismatch must: block parity acceptance; identify the task, comparison profile, and semantic difference; avoid exposing hidden expected outputs in public reports; and be resolved or approved as a new versioned semantic profile.
6. Keep three concepts separate: upstream full-suite HumanEval+ compatibility; primary 163-task reference-only experimental measurement; 164-task reference-evaluator validation. Full-suite compatibility performance is never labeled as held out.
7. Do not use confirmatory experimental candidates or any outcomes from MEGB-05/06.
8. Do not implement the production MEGB-03F evaluator early. Candidate execution for parity uses a narrowly scoped validation harness over MEGB-02; expected outputs and comparison stay on the trusted side; candidate code never receives reference evidence; the harness is clearly marked validation-only.
9. HumanEval/6, /55, and /63 have no upstream EvalPlus counterpart. Validate them separately: independent implementation or independently specified contract-derived oracle where practical; task-appropriate boundary and metamorphic checks; comparison against the MEGB-03C expected outputs; reported as supplementary-oracle validation, not upstream parity.
10. Verify the exhaustive 12-case HumanEval/39 validation profile separately from the 163-task parity corpus.
11. Record pinned EvalPlus version, private/internal API dependencies (e.g. `_poly`), Python/NumPy versions, corpus checksum, commands, and environment.
12. Full parity and supplementary-validation artifacts follow the privileged/redacted artifact policy (`docs/measurement/privileged-artifact-policy.md`). Public reports contain classifications and aggregate counts only — no expected outputs or hidden case details.
13. Required acceptance evidence: frozen parity-corpus checksum; zero unexplained upstream/MEGB classification mismatches; at least one `PASS_BASE_FAIL_PLUS` example; complete supplementary-oracle validation for tasks 6, 55, and 63; exhaustive HumanEval/39 validation; no privileged leakage; deterministic rerun; full regression, mypy, and pylint results.

Non-goals unchanged from below: no typed evaluator-result implementation (MEGB-03E), no production task-level evaluator (MEGB-03F).

### Objective

Demonstrate that the MEGB oracle and comparison layer reproduce the pinned upstream EvalPlus classifications on a fixed validation corpus, and establish known-correct and known-incorrect candidates for later evaluator validation.

### Dependencies

- MEGB-03C complete and accepted.

### Requirements

1. Build a fixed, versioned parity corpus containing corrected canonical solutions and representative incorrect candidates.
2. Include known-incorrect candidates covering, as practical:
   - failures on original HumanEval evidence;
   - pass-base/fail-plus behavior;
   - hardcoded solutions;
   - boundary-condition failures;
   - type-handling failures;
   - numerical-tolerance failures;
   - mutation-sensitive failures; and
   - resource-exhausting behavior.
3. Include at least one validated `PASS_BASE_FAIL_PLUS` example.
4. Evaluate the fixed corpus using the pinned upstream EvalPlus implementation.
5. Evaluate equivalent evidence using the MEGB oracle/comparison layer without exposing expected results to candidate-side code.
6. Require task-level classification parity for every sample.
7. Resolve divergences or record them as explicitly approved, versioned semantic differences before experimental use.
8. Preserve exact upstream and MEGB versions, commands, environment metadata, corpus hashes, and results.
9. Keep full-suite compatibility classifications distinct from primary reference-only classifications.

### Acceptance Criteria

- The parity corpus is frozen and checksummed.
- Corrected canonical solutions produce expected oracle/comparison results.
- MEGB classifications match pinned upstream EvalPlus for every required parity sample.
- At least one `PASS_BASE_FAIL_PLUS` candidate is validated.
- Any intentional semantic difference is approved, documented, and versioned.
- No experimental candidate is evaluated.

### Required Tests

- Automated upstream-versus-MEGB classification comparison.
- Canonical-solution comparison tests.
- Known-incorrect category tests.
- Base/plus outcome classification tests.
- Corpus and result checksum validation.
- Environment/version mismatch refusal tests.

### Non-Goals

- Final MEGB-03 candidate-execution orchestration.
- Full 164-task release validation through the final evaluator.
- Interpreting pass-base/fail-plus behavior as intentional gaming.

### Handoff Artifacts

- Frozen parity corpus.
- Upstream parity results.
- Known-incorrect validation corpus.
- Approved semantic-difference record, if needed.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-03E requires explicit authorization.

### Completion Record

- Status: ACCEPTED (per the "Approved Execution Amendment (MEGB-03D)" above), including the pre-MEGB-03D MEGB-03C corrections in commit `a883650`
- Commits: 5d29992, dd81002
- Completed: 2026-08-01
- Tests: `pytest tests/test_parity_corpus.py tests/test_parity.py tests/test_parity_lock.py tests/test_supplementary_oracle_validation.py -v` — 46/46 passed offline/integration (17 corpus-structure + 10 offline classification + 9 lock/verify + 8 supplementary-validation + 2 HumanEval/39 non-Docker); 3 Docker-marked tests (full 11-candidate corpus agreement, HumanEval/39 MEGB-side agreement) run and passed against the real corpus via `megb-runner:local`. Full offline suite 226/226 passed. mypy clean (56 files across `src/`+`tests/`). pylint 10.00/10 for `src/`+`tests/` (the one pre-existing, out-of-scope duplicate-code finding between two already-accepted MEGB-03B files remains unchanged, per earlier subtasks' notes).
- Deviations:
  1. **A genuine macOS/Python-3.14 EvalPlus incompatibility, found and safely worked around**: `evalplus.eval.reliability_guard`'s memory-limit call (`resource.setrlimit(RLIMIT_AS, ...)`) fails unconditionally on this validation host (confirmed independent of the requested limit — even setting a trivially small value fails identically), which without a fix would have crashed every single upstream classification. Worked around via EvalPlus's own documented escape hatch (`EVALPLUS_MAX_MEMORY_BYTES=-1`), scoped to exactly the upstream-classification call via a context manager that restores the prior environment afterward (`src.reference.parity._disabled_upstream_memory_guard`) — never left set process-wide. Because this removes upstream's own memory guard on this host, the corpus's one memory-exhausting candidate was deliberately sized (~2 GB, confirmed safe via direct experimentation) to be safe to run unprotected on an 8 GB+ host rather than depend on that guard being functional; it still reliably exceeds MEGB-02's real 256 MB container memory limit.
  2. **Local Docker tag-index drift, not a code issue**: this host's Docker Desktop intermittently drops the `megb-runner:local` name→ID tag reference (`docker inspect` reports "no such object" even though `docker images`/`docker image ls` still list it) after periods of inactivity. Recovered each time via `docker tag <id> megb-runner:local` (same image, same name — a daemon-local refresh, not a rebuild or any change to MEGB-02's pinned image). Noted here since it may recur for future MEGB-03 subtasks reusing the same Docker backend.
  3. **Empirical sample-index discovery, not an assumption**: the `PASS_BASE_FAIL_PLUS` and `numerical-tolerance` candidates' actual divergent `plus_input` cases were located by direct execution against the real corpus (indices 11/45/100/105/200/357 and 823 respectively) rather than guessed, and recorded on the corpus entries via `focus_plus_indices` so a fixed-size default sample can never silently miss an already-observed real edge case.
  4. **Resource-exhausting candidates get a smaller plus-sample size** (3 instead of the default 30) purely for runtime — each invocation either exhausts its full wall-clock timeout or gets OOM-killed, so a larger sample would multiply runtime for the same coverage. This does not weaken what those two candidates test (timeout/OOM classification, not per-case output diversity).
- Handoff:
  - Library: `src/reference/parity_corpus.py` (frozen 11-candidate `PARITY_CORPUS` + 2-candidate `HUMANEVAL_39_VALIDATION_CORPUS`, `check_corpus_covers_required_categories`); `src/reference/parity.py` (`classify_upstream`/`classify_megb`/`compare_classifications`/`run_parity_corpus`, the `_disabled_upstream_memory_guard` environment workaround); `src/reference/parity_lock.py` (`ParityArtifact`/`EnvironmentRecord`, `write_privileged_parity_artifact`, `verify_parity_against_lock`, `redact_parity_artifact`); `src/reference/parity_cli.py` (`build`/`verify` CLI, refuses to freeze on any classification disagreement); `src/reference/supplementary_oracle_validation.py` (independent HumanEval/6/55/63 validation: stack-based `parse_nested_parens`, memoized-recursive `fib`/`fibfib`, plus metamorphic/recurrence checks).
  - Committed artifacts: `artifacts/reference/parity/{parity_report_redacted.json,parity.lock.json}`.
  - Privileged (gitignored, not in git) artifact: `artifacts/privileged/reference/parity/parity_results.json` — present on disk, verified via `python -m src.reference.parity_cli verify` (PASS).
  - **Acceptance evidence (all satisfied):**
    - Frozen parity-corpus checksum: `logical_sha256=614555848e0c904080b1790efd32625ed012346166b2a8ad256a4d711a17c4ee` (`parity-corpus-v1`), reproduced identically by `verify`.
    - Zero unexplained upstream/MEGB classification mismatches: 11/11 candidates agree (`agreement_count=11`, `candidate_count=11`).
    - At least one validated `PASS_BASE_FAIL_PLUS` example: **two** — `he0-pass-base-fail-plus` (task `HumanEval/0`, off-by-one `<=` vs `<`, source `sha256:516a9a3c...`) and `he0-numerical-tolerance-fudge` (same task, `threshold*0.999` fudge, source `sha256:287fcc04...`) — both agree between upstream and MEGB.
    - Complete supplementary-oracle validation for tasks 6, 55, and 63: HumanEval/6 — 218/218 independent-implementation matches, 20/20 metamorphic checks; HumanEval/55 — 157/157 matches, 157/157 recurrence checks; HumanEval/63 — 137/137 matches, 137/137 recurrence checks. All three `all_valid=True`.
    - Exhaustive HumanEval/39 validation: both `HUMANEVAL_39_VALIDATION_CORPUS` candidates (corrected canonical, deliberately-wrong hardcoded) run against the full 12-case domain (10 base + 2 plus, never subsampled) via both upstream and MEGB-02, agreeing on both (`PASS_BASE_PASS_PLUS` / `FAIL_BASE_FAIL_PLUS`).
    - No privileged leakage: `parity_report_redacted.json` confirmed to contain no `mismatch_detail`, no per-side `detail` strings, no candidate source code, no expected/actual output values — classifications, agreement booleans, source hashes, and aggregate counts only.
    - Deterministic rerun: `python -m src.reference.parity_cli verify` regenerated the full corpus fresh and matched the committed lock exactly (`logical_checksum`, `size`, `on_disk_checksum`, `on_disk_bytes_match_rebuild`, `dataset_checksum` all `True`).
    - Full regression/mypy/pylint: see Tests above.
  - Three concepts kept distinct per requirement 6: upstream full-suite HumanEval+ compatibility (this subtask's parity corpus, `base`/`plus` outcomes) is never conflated with MEGB-03B's primary 163-task reference-only experimental partition, nor with the 164-task reference-validation corpus (HumanEval/39's separate exhaustive-domain section here) — none of MEGB-03D's classifications feed into or are labeled as "held out" experimental performance.
  - Policy: `docs/measurement/privileged-artifact-policy.md` extended with the concrete MEGB-03D parity section (committed/privileged split rationale, environment-record contents, build/verify CLI, the macOS/Python-3.14 `reliability_guard` environment note, backup requirement).

---

## MEGB-03E — Implement Typed Result Models and Scoring Semantics

### Status

**Status:** ACCEPTED (original scope), commits `728c601`/`951c309`. Executed per the original "Requirements" below — no execution amendment was needed; the text is self-contained and does not conflict with any accepted MEGB-03B/03C/03D semantics. **Approved Correction v2 applied, pending acceptance** (see below): commits `99b921d`, `55435da`, fixing a schema defect surfaced during MEGB-03F trust-boundary review.

### Objective

Define typed, versioned task- and benchmark-level result models that distinguish candidate correctness from measurement validity and distinguish primary reference-only scoring from full-suite compatibility diagnostics.

### Dependencies

- MEGB-03D complete and accepted.

### Requirements

1. Define an immutable `ReferenceEvaluationContext` containing at least:

   ```python
   @dataclass(frozen=True)
   class ReferenceEvaluationContext:
       experiment_run_id: str
       optimization_run_id: str
       candidate_id: str
       candidate_sha256: str
       candidate_frozen_at: str
       candidate_selection_rule: str
       optimization_config_sha256: str
       evaluator_version: str
       dataset_version: str
       partition_version: str
       execution_profile_id: str
   ```

2. Define measurement status independently of candidate correctness:

   ```python
   class MeasurementStatus(str, Enum):
       VALID = "VALID"
       INVALID_ORACLE = "INVALID_ORACLE"
       INVALID_INFRASTRUCTURE = "INVALID_INFRASTRUCTURE"
       INVALID_PROTOCOL = "INVALID_PROTOCOL"
       INCOMPLETE = "INCOMPLETE"
   ```

3. Define a typed task result containing at least:
   - task, candidate, and candidate-hash identifiers;
   - measurement status;
   - primary `q_ref_task`;
   - reference-only case totals and pass counts;
   - optional full-suite base/plus diagnostic statuses and counts;
   - first candidate-failure category;
   - execution-failure counts;
   - evaluator, dataset, partition, oracle, and execution-profile versions;
   - relevant checksums; and
   - timestamps and duration.
4. Set `q_ref_task = 1.0` only when all required reference-only cases pass.
5. Set `q_ref_task = 0.0` for a validly measured candidate failure.
6. Set `q_ref_task = None` for invalid or incomplete measurement.
7. Treat case-level pass fractions as diagnostic only; never substitute them for binary task scoring.
8. Define full-suite compatibility outcomes:

   ```python
   class ReferenceOutcome(str, Enum):
       PASS_BASE_PASS_PLUS = "PASS_BASE_PASS_PLUS"
       PASS_BASE_FAIL_PLUS = "PASS_BASE_FAIL_PLUS"
       FAIL_BASE_FAIL_PLUS = "FAIL_BASE_FAIL_PLUS"
       FAIL_BASE_PASS_PLUS = "FAIL_BASE_PASS_PLUS"
       INVALID_MEASUREMENT = "INVALID_MEASUREMENT"
   ```

9. Treat `PASS_BASE_FAIL_PLUS` as evidence of insufficient original evidence, not automatic proof of intentional gaming.
10. Treat `FAIL_BASE_PASS_PLUS` as an anomaly requiring investigation for comparison mismatch, oracle inconsistency, nondeterminism, execution-order effects, or implementation defects.
11. Define a benchmark result containing:
    - expected, evaluated, valid, invalid, and incomplete task counts;
    - tasks passing primary reference-only evidence;
    - optional base/full-suite compatibility scores;
    - primary \(Q_{\mathrm{ref}}\);
    - evaluator and artifact versions;
    - candidate-set manifest hash; and
    - aggregate measurement status.
12. Never silently change the denominator. Emit final \(Q_{\mathrm{ref}}\) only for 164 valid required task measurements.
13. Define privileged and redacted public projections. Public or optimizer-visible results must exclude:
    - failing inputs;
    - expected outputs;
    - per-case pass/fail vectors;
    - canonical outputs;
    - exception details containing test data; and
    - unapproved reference-test counts.

### Acceptance Criteria

- Models are typed, immutable, versioned, and round-trip serializable.
- Valid candidate failures produce zero; invalid measurements produce `None`.
- Primary and compatibility metrics cannot be confused by identifier or schema.
- Missing or invalid tasks preserve the 164-task denominator and prevent final \(Q_{\mathrm{ref}}\).
- Redacted projections contain only authorized fields.
- Result construction rejects inconsistent counts, hashes, versions, or statuses.

### Required Tests

- Task-result construction and schema validation.
- All-pass scoring.
- Pass-base/fail-plus diagnostic scoring.
- Candidate execution-failure scoring.
- Invalid-measurement propagation.
- Denominator preservation.
- Serialization round trips.
- Configuration/version validation.
- Public-result redaction and feedback-leakage tests.

### Non-Goals

- Executing candidate code.
- Implementing persistent caching or audit storage.
- Benchmark-gaming delta calculation.

### Handoff Artifacts

- Typed evaluation context.
- Task and benchmark result schemas.
- Measurement-status and outcome taxonomies.
- Privileged/public projection specification.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-03F requires explicit authorization.

### Completion Record

- Status: ACCEPTED.
- Commit: `728c601`.
- Completed: 2026-08-01.
- Tests: `src/reference/result_schema.py` + `src/reference/result_redaction.py`, 84 new tests across `tests/test_result_schema.py` (60) and `tests/test_result_redaction.py` (24), all offline/synthetic (no Docker, no network). Organized to map onto the ticket's "Required Tests" list:
  - Task-result construction and schema validation: context field validation (empty strings, malformed sha256), task-result field validation (empty/malformed strings, negative counts/duration, `reference_case_pass_count > reference_case_total`, unknown/negative `execution_failure_counts` keys/values), frozen/immutability checks.
  - All-pass scoring: `q_ref_task=1.0` requires `reference_case_pass_count == reference_case_total`; rejected otherwise; full-164-task benchmark computes `q_ref=1.0`.
  - Pass-base/fail-plus diagnostic scoring: `FullSuiteDiagnostic` construction/consistency checks for all four `ReferenceOutcome` values (including `FAIL_BASE_PASS_PLUS` as a representable, never-suppressed anomaly, and `INVALID_MEASUREMENT`'s relaxed zero-count case); benchmark-level `full_suite_outcome_counts` aggregation.
  - Candidate execution-failure scoring: `q_ref_task=0.0` requires a candidate-attributable `first_failure_category` and `reference_case_pass_count < reference_case_total`; fractional/bool `q_ref_task` rejected; case-level pass fraction (e.g. 4/5) never substituted for the binary score; mixed pass/fail benchmark computes the correct fraction.
  - Invalid-measurement propagation: every non-VALID `MeasurementStatus` forces `q_ref_task=None` and `full_suite_diagnostic=None`; `INCOMPLETE` requires `first_failure_category=NONE`; other invalid statuses require a measurement-apparatus category; `aggregate_status` reflects the worst status present (or `INCOMPLETE` when any task is missing outright).
  - Denominator preservation: `expected_task_count` must be exactly 164; missing tasks or any non-VALID/INCOMPLETE task among an otherwise-full set forces `q_ref=None`; duplicate `task_id` and over-count rejected.
  - Serialization round trips: `context`/`FullSuiteDiagnostic`/`ReferenceTaskResult`/`ReferenceBenchmarkResult` all round-trip exactly through `*_to_dict`/`*_from_dict`, including `diagnostics` content and `None`-valued optional fields.
  - Configuration/version validation: every task result must share the benchmark's exact `context` and `oracle_version`; mismatches (candidate identity, `evaluator_version`, `oracle_version`) are rejected; `task_manifest_checksum` must be a valid sha256 hex digest.
  - Public-result redaction and feedback-leakage tests: `redact_task_result`/`redact_benchmark_result` never include `diagnostics`, the full `context`, or `candidate_sha256`; `reference_case_total`/`reference_case_pass_count` (the "unapproved reference-test counts" of requirement 13) are excluded unless `include_reference_case_counts=True` is explicitly passed, and that flag propagates correctly to every nested task redaction.
  - Full offline regression suite (`pytest -m "not integration and not docker"`): 283 passed, 0 failed (up from 263 before this subtask).
  - `mypy --strict` (via the pinned `pyproject.toml` config) over `src/`: clean, 39 source files.
  - `pylint` over `src/` and `tests/`: 10.00/10 (one pre-existing, already-accepted `duplicate-code` note in `tests/test_parity_lock.py` unrelated to this subtask).
- Deviations: The literal ticket text ("Requirements" above) specifies a richer schema than a first draft implemented — the first draft was caught and fully reworked before finalizing, rather than left partially conformant:
  1. `ReferenceTaskResult` carries typed `reference_case_total`/`reference_case_pass_count` fields (not a free-form diagnostics entry), with construction-time consistency checks tying them to `q_ref_task` (requirements 4/5/7).
  2. `FullSuiteDiagnostic` is a separate, validated nested type (not just a bare `ReferenceOutcome` label) carrying `base_total`/`base_pass_count`/`plus_total`/`plus_pass_count`, with the outcome checked for consistency against the counts.
  3. `ReferenceTaskResult` additionally carries `execution_failure_counts` (a category→count mapping, validated against `FailureCategory`), `oracle_version`, `reference_case_checksum` (sha256 of the specific reference-only case set consumed), and `duration_seconds`.
  4. `ReferenceBenchmarkResult` additionally carries `task_manifest_checksum` (pinning exactly which 164-task reference-validation manifest the run was evaluated against — so the denominator's *identity*, not just its size, cannot silently drift) and `oracle_version` (checked against every task result), and exposes `invalid_task_count`, `incomplete_task_count`, `primary_pass_count`, `full_suite_outcome_counts`, and `aggregate_status` as properties rather than stored/duplicated fields, to avoid any possibility of a stored aggregate drifting out of sync with the underlying `task_results`.
  5. The benchmark-level "candidate/run identity" check was generalized from a fixed subset of fields to full `ReferenceEvaluationContext` equality against every task result — simpler and stronger than checking a hand-picked field list, and it also catches evaluator/dataset/partition/execution-profile version drift within one benchmark run, which the ticket's "configuration/version validation" required test explicitly calls for.
- Handoff: `src/reference/result_schema.py` (typed models: `ReferenceEvaluationContext`, `MeasurementStatus`, `ReferenceOutcome`, `FullSuiteDiagnostic`, `ReferenceTaskResult`, `ReferenceBenchmarkResult`, `InvalidReferenceResultError`) and `src/reference/result_redaction.py` (privileged `*_to_dict`/`*_from_dict` serialization and development-facing `redact_task_result`/`redact_benchmark_result` projections) are ready for MEGB-03F to populate by executing candidates through MEGB-02 and MEGB-03C/03D's oracle/comparison layer. No candidate execution, persistent caching/audit storage, or benchmark-gaming delta calculation is implemented here, per this ticket's Non-Goals — those remain MEGB-03F's and MEGB-06's responsibility respectively.

#### Post-Acceptance Addendum: Reconciling the "263"/"283" Figures with MEGB-03D's "226/226"

The "Full offline regression suite ... 283 passed, 0 failed (up from 263 before this subtask)" line above is preserved as originally written, but its "263" comparison point does not use the same marker selection as MEGB-03D's own accepted completion record above ("Full offline suite 226/226 passed"), and is corrected here rather than edited into the original text:

- MEGB-03D's `226/226` was obtained with `pytest -m "not docker"` (excludes only Docker-marked tests; includes non-Docker `integration`-marked tests requiring network access). Verified directly by checking out commit `dd81002` (MEGB-03D's own commit-hash-recorded state) and rerunning that exact command: **226 passed, 24 deselected.**
- MEGB-03E's "263" (an intermediate, never-reported-to-the-user figure from mid-subtask) and "283" both used the narrower `pytest -m "not integration and not docker"` (excludes both integration and Docker tests). At the same `dd81002` commit, that narrower command yields **199 passed, 51 deselected** — not 226 — because it additionally excludes the non-Docker integration tests.
- Rerunning both marker selections at this subtask's final state (`951c309`) gives a consistent, marker-independent reconciliation:

  | Marker selection | MEGB-03D (`dd81002`) | MEGB-03E (`951c309`) | Delta |
  |---|---|---|---|
  | `-m "not docker"` (MEGB-03D's own command) | 226 passed, 24 deselected | 310 passed, 24 deselected | **+84** |
  | `-m "not integration and not docker"` (this subtask's command) | 199 passed, 51 deselected | 283 passed, 51 deselected | **+84** |

  Both marker selections agree: MEGB-03E added exactly 84 tests, none of them `integration`- or `docker`-marked. The "up from 263" phrasing above understated the true pre-subtask baseline by comparing against a stale intermediate count rather than either of the two committed reference points (`226` under MEGB-03D's own command, or `199` under this subtask's narrower one).

#### Approved Correction (v2): Separate Run / Task-Specific / Candidate-Set Identity

Surfaced during MEGB-03F trust-boundary review, after MEGB-03E's original acceptance above: `ReferenceBenchmarkResult` required every `ReferenceTaskResult.context` to match the benchmark's `candidate_context` by full equality, which embedded a single `candidate_sha256` shared across all 164 tasks. This cannot represent a legitimate 164-task benchmark run — HumanEval tasks are independent programming problems, so a real run evaluates 164 *different* task-specific candidate solutions. Verified empirically before fixing: constructing a benchmark with two task results differing only in `candidate_sha256` (everything else identical) was unconditionally rejected. The original "Requirements"/"Completion Record" text above is preserved verbatim as historical context; this section supersedes it where they conflict, per this ticket's amendment-precedence rule.

**Corrected design:**
- **`ReferenceRunContext`** (renamed from `ReferenceEvaluationContext`): shared run/evaluator/dataset/partition/execution-profile identity, genuinely common across all 164 tasks. Contains no candidate field at all — no singular `candidate_id`/`candidate_frozen_at` implying one candidate for the whole run (renamed to `portfolio_frozen_at`/`portfolio_selection_rule`, describing the one atomic freeze/selection event that produced the whole 164-solution portfolio).
- **`candidate_id`/`candidate_sha256`** moved directly onto `ReferenceTaskResult`: each task's own, independently-varying candidate identity.
- **`ReferenceValidationCandidateSetManifest`** (new; named explicitly — not the generic "`CandidateSetManifest`" of the first correction draft — because it is exactly-164-entries and belongs specifically to the MEGB-03 reference-validation aggregate; the name itself now makes it unambiguous that this type must never be reused for MEGB-06's separate 163-task experimental population): a versioned, self-checksummed, exactly-164-entry binding of the whole run's task-to-candidate mapping (`CandidateSetEntry`: `task_id`/`candidate_id`/`candidate_sha256`), plus `task_manifest_id`/`task_manifest_checksum` (which 164-task reference-validation manifest) and `selection_provenance_sha256` (an opaque, caller-supplied checksum of whatever selection/provenance record accompanies the whole portfolio). The manifest's own checksum is always recomputed from canonical contents at construction — never accepted as an unverified caller-provided value — so a reordered, duplicated, or hand-edited entry is caught by the act of (re)constructing the manifest, including on reload from persisted storage. **`candidate_sha256` is never required to be unique across entries** — confirmed empirically (two entries for different tasks sharing an identical `candidate_sha256`, everything else distinct, construct and pass benchmark validation without error): only `task_id` uniqueness is enforced, since a candidate portfolio may legitimately reuse identical source across independent tasks (e.g. two tasks both correctly solved by the same helper snippet). The sole required invariant is that each task result's own candidate identity matches its manifest entry *exactly* — never a claim of global hash uniqueness.
- `ReferenceBenchmarkResult` now verifies: `run_context` equality across every task result; `oracle_version` equality; `candidate_set_manifest.task_manifest_checksum` consistency with the benchmark's own; and that every task result's own candidate identity matches its `candidate_set_manifest` entry exactly — while explicitly permitting, and requiring for a real run, different `candidate_id`/`candidate_sha256` values across tasks (and permitting, without any additional check, identical `candidate_sha256` values recurring across different tasks).
- This type remains the MEGB-03 evaluator-validation aggregate over exactly 164 tasks; it is not, and must never be silently reused as or confused with, MEGB-06's separate 163-task primary-experiment aggregate.

**Schema version:** `RESULT_SCHEMA_VERSION` incremented `reference-result-schema-v1` → `reference-result-schema-v2` (a breaking change). Every serialized payload (`task_result_to_dict`/`benchmark_result_to_dict`) is now stamped with `schema_version`; deserialization checks this explicitly and raises `UnsupportedResultSchemaVersionError` on any mismatch rather than silently misparsing a differently-shaped payload under the current field names. **No migration path is needed or provided**: confirmed by searching the full repository for any JSON/lock-file artifact referencing `"reference-result-schema-v1"` — none exists. No code ever wired the v1 schema into any lock/build/CLI pipeline; its only consumers were `src/reference/result_schema.py`/`result_redaction.py`/`reference_evaluator.py` themselves and their own test suites, all updated by this same correction.

**MEGB-03F change required:** `evaluate_reference` gains explicit `candidate_id`/`candidate_sha256` parameters (this task's own identity) alongside the renamed `run_context` parameter — a narrow signature change, since the function was already called once per task per the original design; no change to its orchestration logic.

**Tests:** 61 new/updated regression tests across `tests/test_result_schema.py` (87 total), `tests/test_result_redaction.py` (21 total), `tests/test_reference_evaluator.py` (43 total, offline), and `tests/test_reference_evaluator_docker.py` (3, real Docker) — covering: different candidate ids/hashes across tasks now accepted (the core fix); mismatched shared run context rejected; missing/duplicate/reordered/tampered candidate-set entries rejected; candidate-set checksum mismatch rejected; the 164-task denominator still enforced; reduced/full evaluator profiles still cannot be mixed (via `run_context` equality); task-specific candidate identity remains redacted in both `redact_task_result`/`redact_benchmark_result`; and schema-version mismatch on deserialize rejected explicitly. Full offline regression suite (`pytest -m "not integration and not docker"`): 350 passed (up from 283 before this correction). Real Docker vertical slice: 3/3 passed. Full Docker-marked suite: 26/26 passed for tests actually affected by or exercising this correction (one unrelated, pre-existing MEGB-02 test failure — `test_no_containers_remain_after_adversarial_exit_paths` — was traced to a stale, 5-hour-old leftover container from an earlier, unrelated session predating this correction; removed and reconfirmed passing in isolation, not a regression from this change). `mypy --strict` over `src/`: clean, 40 files. `pylint` over `src/`+`tests/`: 10.00/10 (one pre-existing, already-accepted `duplicate-code` finding, unrelated).

**Commits:** `99b921d` (initial v2 correction), `55435da` (rename `CandidateSetManifest` → `ReferenceValidationCandidateSetManifest` per follow-up review; confirms no code change was needed for candidate_sha256 uniqueness, which was already correctly unconstrained).

#### Schema Completion (v3): Comparison-Profile Identity

Surfaced while implementing MEGB-03G.1's `aggregate_reference_results` (not during MEGB-03E/03F themselves): the Approved Correction (v2) above is otherwise complete and is preserved verbatim as historical context; this section supersedes it only where it conflicts, per this ticket's amendment-precedence rule, and does not reopen or rewrite the v2 narrative.

**Defect:** `ComparisonProfile.profile_version`/`COMPARISON_PROFILE_VERSION` was verified once by `evaluate_reference` at evaluation time but was never itself a field on `ReferenceRunContext` or `ReferenceTaskResult`. There was no way for `aggregate_reference_results` (or any later consumer reloading a persisted result) to independently re-verify comparison-profile consistency across already-constructed task results from data alone — a real defense-in-depth gap, though not exploitable in the pre-v3 codebase (there was exactly one module-level `COMPARISON_PROFILE_VERSION` constant, and every `ReferenceTaskResult` in existence had already been checked against it before construction).

**Corrected design:**
- `ReferenceRunContext` gains `comparison_profile_version: str` (immutable, required-nonempty, included automatically in the dataclass's existing equality check).
- `evaluate_reference` now validates `run_context.comparison_profile_version` against `evidence.comparison_profile.profile_version` before any candidate code executes, in addition to the existing `evidence.comparison_profile.profile_version` vs. `COMPARISON_PROFILE_VERSION` check.
- `ReferenceTaskResult` preserves this identity via its existing `context` field — no new field was added directly to `ReferenceTaskResult`, since duplicating it there would create a second, independently driftable copy of the same value.
- `aggregate_reference_results` (MEGB-03G.1) needs no new dedicated check: its existing `_require_shared_run_context` (full `ReferenceRunContext` equality across all 164 task results) now catches a comparison-profile inconsistency automatically, exactly like it already catches `execution_profile_id`/`evaluator_version` inconsistency. Unlike those two fields, comparison-profile identity does not itself differ between the full and reduced-development profiles, so no separate "must equal the accepted constant" gate was added for it.
- `run_context_to_dict`/`run_context_from_dict` serialize/deserialize the new field like every other `ReferenceRunContext` field.
- `redact_benchmark_result` exposes `comparison_profile_version` alongside the other already-exposed version identifiers (`evaluator_version`, `oracle_version`) — a version tag, not case content, consistent with the existing redaction policy.

**Schema version:** `RESULT_SCHEMA_VERSION` incremented `reference-result-schema-v2` → `reference-result-schema-v3` (a breaking change). Both v1 and v2 payloads are now rejected explicitly by the deserializers. **No migration path is needed or provided**: confirmed by a repo-wide search (including `artifacts/privileged/`) for any persisted artifact stamping `"reference-result-schema-v1"` or `"reference-result-schema-v2"` — none exists; the only remaining occurrences of those strings are this ticket's own historical narrative and the test suite's own stale-version rejection fixtures. `reference-validation-candidate-set-manifest-v1`, `partition-v1`/`PARTITION_ALGORITHM_VERSION`, `oracle-v1`/`ORACLE_ALGORITHM_VERSION`, and `COMPARISON_PROFILE_VERSION`'s own value are all unchanged.

**Tests:** 9 new/updated tests across `tests/test_result_schema.py` (88 total), `tests/test_result_redaction.py` (24 total), `tests/test_reference_evaluator.py` (44 total, offline), `tests/test_reference_evaluator_docker.py` (3, real Docker), and `tests/test_reference_aggregation.py` (20 total) — covering: matching comparison profile accepted (via existing happy-path coverage); mismatched comparison profile on `run_context` rejected before execution; mixed comparison profiles across task results rejected by aggregation; `run_context` serialization round trip (generic equality check now covers the new field); both v1 and v2 payloads rejected under the v3 deserializer; `comparison_profile_version` exposed in `redact_benchmark_result`; and the existing reduced/full evaluator-profile separation tests re-confirmed green under the v3 context. Full offline suite (`pytest -m "not docker"`): 402 passed, 27 deselected, 0 failed. Real Docker vertical slice: 3/3 passed. `mypy src tests`: clean, 65 files. `pylint src tests`: 10.00/10, **exit code 0** — the three `R0801` duplicate-code findings between `tests/test_reference_aggregation.py`'s local fixtures and `tests/test_result_schema.py`'s were resolved with a file-scoped `# pylint: disable=duplicate-code` suppression (justification: the two test files intentionally construct the accepted result-schema objects independently to validate different boundaries — schema-level invariants vs. the public aggregation boundary — and sharing fixtures would couple two independently valuable test layers), matching the precedent already established for `tests/test_reference_partition_lock.py`. No global disable, no `--exit-zero`, no behavior change for the lint finding.

**Commit:** `c71b1b7`.

---

## MEGB-03F — Implement the Task-Level Reference Evaluator

### Status

**Status:** Complete, pending acceptance. Executed per the original "Requirements" below — no execution amendment was needed. The literal 3-argument illustrative signature (`evaluate_reference(task_id, candidate_code, context)`) was extended with explicit `evidence`, `backend`, and `profile` parameters — documented as a deviation below — since a pure 3-argument function cannot discover privileged oracle evidence or a backend/profile on its own; the ticket itself invites "an interface similar to" this signature. Commit `410388d`. **Approved Correction v2 applied, pending acceptance together with MEGB-03E's**: commits `99b921d`, `55435da` — `evaluate_reference` now takes explicit task-specific `candidate_id`/`candidate_sha256` parameters alongside the renamed `run_context` (see MEGB-03E's "Approved Correction (v2)" section above for the full defect analysis and fix).

### Objective

Implement trusted-side orchestration for evaluating one frozen candidate against one task's frozen reference-only evidence through the MEGB-02 execution boundary.

### Dependencies

- MEGB-03E complete and accepted.

### Requirements

1. Implement an interface similar to:

   ```python
   def evaluate_reference(
       task_id: str,
       candidate_code: str,
       context: ReferenceEvaluationContext,
   ) -> ReferenceTaskResult:
       ...
   ```

2. Verify candidate identity and SHA-256 before execution.
3. Verify dataset, partition, oracle, evaluator, comparison, protocol, and execution-profile versions and checksums.
4. For every authorized reference-only case:
   1. keep expected output and comparison rules in the trusted evaluator;
   2. send only candidate source, entry point, current arguments, limits, and protocol version through MEGB-02;
   3. receive candidate output or structured execution failure;
   4. compare output on the trusted side;
   5. write a privileged per-case diagnostic; and
   6. destroy invocation-specific candidate state according to the execution profile.
5. Never execute candidate code in the trusted controller process.
6. Never reveal expected outputs before, during, or after invocation.
7. Use deterministic test ordering defined by the execution profile.
8. The high-assurance profile must prevent writable state from carrying across independent candidate executions.
9. If batching or persistent workers are introduced, treat them as a distinct versioned measurement process, test state/order sensitivity, compare against fresh-process execution, and demonstrate unchanged task classifications on the validation corpus.
10. Map MEGB-02 candidate statuses to valid candidate failures and infrastructure/protocol statuses to invalid measurements according to MEGB-03E.
11. Prevent unclassified failures from becoming valid zero scores.
12. Preserve privileged per-case diagnostics while returning only the authorized task result projection.
13. Support a reduced development profile with a distinct evaluator identifier. Never label reduced results as full \(S^*\).

### Acceptance Criteria

- A frozen candidate can be evaluated for one task without privileged evidence entering the candidate environment.
- Candidate hash mismatch blocks execution.
- Correct candidate outputs pass; wrong outputs and candidate execution failures produce valid zero scores.
- Oracle, infrastructure, and protocol failures produce invalid measurements with `q_ref_task = None`.
- State does not carry across high-assurance invocations.
- Full and reduced profiles have distinct identifiers and output metadata.
- A small vertical slice containing correct, incorrect, malicious, and infrastructure-failure cases passes before full-corpus use.

### Required Tests

- Correct candidate and wrong-output tests.
- Syntax, exception, timeout, memory, process, and output-limit mapping tests.
- Candidate-hash verification.
- Missing/corrupt oracle tests.
- Sandbox-backend and malformed-response injection.
- Deterministic ordering tests.
- Cross-case state-isolation tests.
- Privileged evidence exfiltration attempts targeting expected outputs, future inputs, canonical solutions, dataset files, evaluator configuration, prior results, and repository contents.
- Full-versus-mini identifier tests.

### Non-Goals

- Benchmark aggregation.
- Candidate generation, revision, or selection.
- Adaptive querying of \(S^*\).
- Performance batching unless separately approved and versioned.

### Handoff Artifacts

- Task-level reference evaluator.
- Privileged per-case diagnostic schema/artifacts.
- High-assurance and reduced execution-profile bindings.
- Vertical-slice validation report.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-03G requires explicit authorization.

### Completion Record

- Status: Complete, pending acceptance.
- Commit: `410388d`.
- Completed: 2026-08-01.
- Tests: `src/reference/reference_evaluator.py`, 46 new tests across `tests/test_reference_evaluator.py` (43, offline/synthetic, no Docker) and `tests/test_reference_evaluator_docker.py` (3, real Docker vertical slice against the actual dataset via `DockerPerInvocationBackend`). Organized against the ticket's "Required Tests" list:
  - Correct candidate and wrong-output tests: offline (synthetic `double` task) and real-Docker (HumanEval/0 `has_close_elements`) coverage of both.
  - Syntax/exception/timeout/memory/process/output-limit mapping: parametrized test over all 6 candidate-attributable `ExecutionStatus` values, plus an exhaustiveness test (`test_every_execution_status_value_is_mapped`) asserting every `ExecutionStatus` member is accounted for — guards requirement 11 ("prevent unclassified failures from becoming valid zero scores").
  - Candidate-hash verification: mismatch raises `CandidateIdentityMismatchError` before any `backend.execute()` call.
  - Missing/corrupt oracle: a case with a `ORACLE_STATUS_GENERATION_FAILED` record produces `INVALID_ORACLE`, `q_ref_task=None`.
  - Sandbox-backend/malformed-response injection: `PROTOCOL_ERROR`/`INFRASTRUCTURE_ERROR` execution statuses invalidate the task and stop early (remaining cases never attempted).
  - Deterministic ordering: `ReferenceTaskEvidence` rejects unsorted/duplicate `case_id`s at construction; requests are sent in `case_id` order.
  - Cross-case state isolation: each case gets its own request with only its own args (never another case's), and `backend.execute()` is called exactly once per case with a distinct request object each time.
  - Privileged-evidence exfiltration attempts: `CandidateExecutionRequest`'s fixed field set is asserted to have no room for oracle content; candidate source is passed through byte-for-byte; none of `context`'s privileged identifiers ever appear in a request; the real-Docker malicious-candidate test attempts to read an oracle-flavored file path and is confirmed to neither crash the evaluator nor receive anything it wasn't given.
  - Full-versus-mini identifiers: `FULL_EXECUTION_PROFILE`/`REDUCED_DEV_EXECUTION_PROFILE` have distinct `profile_id`/`evaluator_version`; a reduced-profile run evaluates fewer cases and its result's context always carries the reduced (never full) evaluator_version.
  - Configuration/version validation (additional, beyond the literal required-tests list but needed for requirement 3): mismatches on `context.dataset_version`/`partition_version`/`execution_profile_id`/`evaluator_version` and on `evidence.oracle_version`/`protocol_version`/`comparison_profile.profile_version` all raise `ReferenceEvaluatorVersionMismatchError` before any execution.
  - Full offline regression suite (`pytest -m "not integration and not docker"`): 326 passed, 0 failed (up from 283 before this subtask; +43 new offline tests).
  - Real Docker vertical slice (`pytest tests/test_reference_evaluator_docker.py`): 3/3 passed against the real dataset and the real pinned `megb-runner:local` image.
  - `mypy --strict` over `src/`: clean, 40 source files.
  - `pylint` over `src/` and `tests/`: 10.00/10 (one pre-existing, already-accepted `duplicate-code` note in `tests/test_parity_lock.py`, unrelated to this subtask; a second, narrowly-scoped `duplicate-code` disable was added in `tests/test_reference_evaluator_docker.py` for HumanEval/0's own canonical algorithm text, which also appears verbatim as unrelated fixture data in `parity_corpus.py`).
- Deviations:
  1. **Signature extension** (documented in Status above): `evaluate_reference` takes explicit `evidence: ReferenceTaskEvidence`, `backend: ExecutionBackend`, and `profile: ExecutionProfile` parameters beyond the ticket's illustrative `(task_id, candidate_code, context)`. `ReferenceTaskEvidence` is a new, non-MEGB-03E type bundling the task's authorized cases (`ReferenceCase`: `case_id`/`args`/`OracleRecord`), entry point, comparison profile, and version/checksum metadata — the trusted-side evidence bundle a pure 3-argument function has no way to locate on its own.
  2. **Real bugs caught before landing** (see commit message for detail): (a) `OracleRecord.expected_output` is tagged-JSON and must be `decode_value()`-d before `compare_outputs` — confirmed against MEGB-03D's own `parity.py` usage pattern, which always decodes fresh rather than reading a stored tagged value; (b) MEGB-03E's accepted `ReferenceTaskResult` schema requires a measurement-apparatus `FailureCategory` (never `NONE`) for any non-VALID, non-INCOMPLETE status — caught by the schema's own validation firing during testing, not assumed. Both fixed before any test was declared passing.
  3. **INVALID_ORACLE's FailureCategory**: MEGB-03E's accepted taxonomy has no dedicated oracle-failure category; `INVALID_ORACLE` results are stamped `FailureCategory.INFRASTRUCTURE_ERROR` (a broken/missing oracle record is an evaluation-infrastructure defect, not a candidate/sandbox protocol failure) — a scoping choice within the existing accepted categories, not a change to MEGB-03E's schema itself.
  4. **Reduced-development profile**: implemented as a smaller, deterministic case subset (`max_cases_per_task`) run through the exact same `ExecutionBackend` as the full profile — never a less-isolated execution mechanism — with a distinct `profile_id`/`evaluator_version` so a reduced result's `ReferenceEvaluationContext.evaluator_version` can never be mistaken for full S*.
  5. **Batching/persistent workers**: not implemented (an explicit non-goal); every case is one independent, sequential `backend.execute()` call.
  6. **Privileged per-case diagnostic persistence**: `PrivilegedCaseDiagnostic` is returned in-memory (as the second element of `evaluate_reference`'s return tuple) but never written to durable storage — that is MEGB-03G's "Audit" responsibility, per its own ticket title and MEGB-03E's Non-Goals excluding "persistent caching or audit storage."
- Handoff: `src/reference/reference_evaluator.py` (`evaluate_reference`, `ReferenceCase`, `ReferenceTaskEvidence`, `ExecutionProfile`, `FULL_EXECUTION_PROFILE`/`REDUCED_DEV_EXECUTION_PROFILE`, `PrivilegedCaseDiagnostic`, and the three error types) is ready for MEGB-03G to build aggregation, caching, redaction, and audit storage on top of. MEGB-03G will need to assemble `ReferenceTaskEvidence` per task (from the privileged oracle artifacts and partition case/args data — not yet wired into an automatic loader; MEGB-03F only defines the evidence *shape*, construction is currently manual/test-only) and call `evaluate_reference` once per task to build up a `ReferenceBenchmarkResult`.

#### Capacity-Planning Input for MEGB-03G (Mandatory)

Measured directly from the real Docker vertical slice (`DockerPerInvocationBackend`, ≈0.25s/case observed): **≈3 minutes per task-specific candidate** (one task's full case set against its own candidate), and **≈8.2 sequential hours per full 164-task candidate-portfolio sweep** — the MEGB-03 reference-validation aggregate's own unit of work (164 task-candidate pairs; 117,961 total cases at ≈0.25s/case).

This is distinct from MEGB-06's primary-execution workload, which must never be sized using the MEGB-03 figures above without translation:

- **MEGB-06 primary execution:** 163 tasks × at most 32 distinct candidates per task × candidate-stream replicates (`R_s`).
- **Worst-case unique reference workload:** `5,216 × R_s` task-candidate pairs (163 × 32 = 5,216), ≈`260.8 × R_s` sequential hours at the current ≈3 min/pair rate.
- Measurement systems, observation replicates, budgets, and selection policies increase *coordinate mappings* (which specific candidate is evaluated against which task, under which system) but cannot increase the maximum beyond 32 unique candidates per task and stream.
- This workload derives from MEGB-05/06 selection semantics (how many distinct candidates a stream may select per task), not from MEGB-04's optimization-loop cadence (how often the loop iterates) — the two are independent quantities and must not be conflated when estimating total compute.

---

## MEGB-03G — Implement Aggregation, Caching, Redaction, and Audit

### Status

**Status:** Not started. **Approved MEGB-03G Compatibility Amendment applied** (see below); the original "Objective" through "Completion Record" text beneath it is preserved verbatim as historical context per this ticket's amendment-precedence rule, and is superseded wherever it conflicts with the amendment. Implementation is not yet authorized.

### Approved MEGB-03G Compatibility Amendment

Authorized following a read-only downstream compatibility review of MEGB-03G against the accepted MEGB-03E/F Approved Correction (v2) schema and the installed MEGB-04 through MEGB-09 specifications. That review found two defects that make the original text below unimplementable or unsafe as written, and two production-readiness gaps the original text left unaddressed:

1. The original requirement 1 signature — `aggregate_reference_results(task_results: Sequence[ReferenceTaskResult]) -> ReferenceBenchmarkResult` — cannot construct a valid v2 `ReferenceBenchmarkResult`. That type's `__post_init__` mandatorily requires `run_context: ReferenceRunContext` and `candidate_set_manifest: ReferenceValidationCandidateSetManifest` as separate inputs, neither of which is derivable from a bare `Sequence[ReferenceTaskResult]` alone.
2. The original requirement 7 cache-key tuple omitted `reference_case_checksum` — a field that exists on `ReferenceTaskResult` since the MEGB-03E/F Approved Correction (v2) — creating a real risk of stale cache reuse across a corrected reference case.
3. The original text specified caching and resumption but no production execution strategy, despite MEGB-06's worst-case volume (5,216 × R_s unique task-candidate pairs) being sequentially infeasible at the measured ~3 minutes/task-candidate rate (~260.8 × R_s sequential hours).
4. The original text did not explicitly require the aggregator to reject mixed-profile or reduced-development task results from the primary 164-task aggregate, though this was implied by the instruction to preserve distinct full-suite-compatibility identifiers.

This amendment corrects all four points. It governs MEGB-03G's eventual implementation; it does not itself authorize that implementation, and it does not amend MEGB-04 through MEGB-09.

#### 1. Corrected aggregation interface

Replace the original requirement 1 signature with a nonredundant interface equivalent to:

```python
def aggregate_reference_results(
    task_results: Sequence[ReferenceTaskResult],
    candidate_set_manifest: ReferenceValidationCandidateSetManifest,
) -> ReferenceBenchmarkResult:
    ...
```

The implementation must:

- require exactly 164 nonempty task results;
- derive the shared `ReferenceRunContext` from the task results themselves (e.g. from their common `context` field) rather than accepting it as a second, independently suppliable argument;
- verify every task result carries the identical run context; reject any run-context mismatch;
- verify every task result's `candidate_id`/`candidate_sha256` matches its corresponding `candidate_set_manifest` entry exactly;
- verify task-manifest identity/checksum, oracle version, evaluator version, comparison-profile identity, execution-profile identity, and schema-version consistency across every task result and against the manifest;
- reject missing, duplicate, reordered, or otherwise inconsistent task results (e.g. two results for the same task ID, a task ID absent from the manifest, or a result count that does not match the manifest's 164 entries);
- never synthesize, default, or fill in a run context or candidate-set manifest that was not itself present in and validated against the supplied inputs.

If a separate run-context argument is preferred over deriving it from the task results, define one typed aggregation-input object binding context, manifest, and results together (e.g. a `ReferenceAggregationInput` dataclass) rather than accepting duplicated, independently suppliable context and results arguments — a caller must never be able to pass a run context that disagrees with what the task results themselves carry without that disagreement being rejected before aggregation proceeds.

#### 2. Explicit profile separation

The primary 164-task validation aggregate — the one whose `q_ref` is the primary \(Q_{\mathrm{ref}}\) — must accept only task results produced under the full reference-only evaluator and execution profile (`FULL_EXECUTION_PROFILE`).

`aggregate_reference_results` must reject, rather than silently average over:

- task results produced under `REDUCED_DEV_EXECUTION_PROFILE` or any other non-full profile;
- a task-result set that mixes evaluator, execution, comparison, or oracle profile identities across tasks;
- full-suite HumanEval+ compatibility diagnostics (`FullSuiteDiagnostic`) presented or substituted as primary `q_ref_task` values;
- any task result whose task ID belongs to the 163-task `primary_experiment_task_manifest` rather than the 164-task `reference_validation_task_manifest` (i.e. any attempt to hand MEGB-06's experimental candidate set to this aggregator).

The following must remain distinct artifacts, never collapsed into one number or one identifier:

- full reference-only primary task results (the ones this aggregator consumes);
- reduced-development smoke results (MEGB-03F's reduced profile, used during development only);
- full-suite HumanEval+ compatibility diagnostics (preserved under their own identifier, per the original requirement 6);
- the 164-task validation \(Q_{\mathrm{ref}}\) aggregate this subtask produces;
- MEGB-06's later, separately built 163-task experimental aggregate.

MEGB-03G must not implement, construct, or expose any interface for MEGB-06's 163-task experimental aggregate. That aggregate is MEGB-06I's own responsibility, built from its own dataset builder against `primary_experiment_task_manifest`; MEGB-03G's aggregator and cache exist to serve the 164-task validation aggregate and to supply reusable, content-addressed `S^*` results that MEGB-06H may consume, not to compute MEGB-06's estimands itself.

#### 3. Complete cache identity

Add `reference_case_checksum` to the cache key.

The complete content-addressed cache key must bind every outcome-affecting input, including at least:

- task ID;
- candidate SHA-256;
- reference-case checksum;
- dataset identity/checksum;
- partition identity/checksum;
- oracle identity/checksum;
- comparison-profile identity/version;
- full evaluator version;
- execution-profile identity;
- protocol version;
- any other relevant implementation or artifact version that affects the measured outcome.

Run IDs, experiment/optimization run identities, and selection-coordinate identities (e.g. `random_control_replicate_id`) belong in audit and coordinate-to-result mapping records — per the original requirement 9 and per MEGB-06H's own mapping requirement — not in the content-addressed cache key itself, unless a specific run or selection identity is later shown to affect execution semantics (in which case it must be added to the key, not layered on top as a second, weaker identity check).

Only a valid, completed result may be reused as a valid cache hit. Invalid or incomplete results must never be reused as if valid; they follow the frozen recovery/resumption policy (retry under the accepted MEGB-03 infrastructure-failure policy), never a silent second attempt disguised as a cache hit.

#### 4. Production execution orchestration

MEGB-03G must not merely record the sequential baseline as an accepted limitation. It must implement and validate a production task-candidate orchestration path providing:

- content-addressed caching (per section 3 above);
- safe resumption after interruption, without duplicating a valid accepted result or silently re-executing it;
- bounded, configurable parallelism across task-candidate pairs;
- resource-aware queueing and backpressure, so bounded parallelism cannot exceed the isolation boundary's safe concurrent-container capacity;
- deterministic result ordering and identity, independent of actual execution or completion order;
- append-only execution/audit records for every invocation, whether served from cache or newly executed;
- controlled interruption and restart, with no ambiguous or double-counted in-flight execution;
- exact reconciliation of expected, observed, cache-hit, and newly executed counts after any run.

The accepted MEGB-02 isolation boundary must remain unchanged by this orchestration work — bounded parallelism means more concurrent isolated executions, never a weaker or shared execution boundary between them.

Case batching (executing multiple reference cases for one candidate in a single process/container invocation, as distinct from parallelizing across task-candidate pairs) is not mandatory. If any batched candidate-execution path is introduced, it requires explicit validation, before acceptance, of: equivalence with the unbatched path's results; resource-limit behavior under batching; cross-case state isolation (no candidate may retain state or infer information across cases within a batch); output-bound behavior; timeout behavior; and adversarial-input behavior — mirroring the equivalence-and-isolation evidence MEGB-07E requirement 23 requires of any batched path proposed for the private evaluator.

#### 5. Throughput evidence

Benchmark, at minimum:

- the current sequential execution path;
- representative bounded-concurrency configurations (at least two distinct concurrency levels beyond sequential);
- cold-cache behavior (no prior cached results available);
- warm-cache behavior (a representative fraction of results already cached);
- interruption/resumption behavior (measuring correctness and any resumption overhead, not just wall time).

For each configuration, record: environment description; concurrency level; task and case counts exercised; cache state; wall time; throughput (task-candidates per unit time); resource usage (at minimum CPU and memory); and failure counts by category.

Using the measured rates, project:

- the full 164-task validation-portfolio runtime under each benchmarked configuration;
- MEGB-06's worst-case volume of 5,216 × \(R_s\) unique task-candidate pairs;
- the ~260.8 × \(R_s\) sequential-hour baseline these worst-case pairs imply at the current ~3-minute/task-candidate sequential rate;
- the corresponding measured bounded-parallel projection(s) for the same worst-case volume.

MEGB-03G's checkpoint report must state one of the following explicitly, supported by the measured throughput evidence above:

- production reference execution is ready for MEGB-06A's feasibility evaluation, with the measured throughput and projected runtime/cost figures MEGB-06A needs to reason about \(R_s\); or
- downstream readiness is **BLOCKED**, with the specific measured reason (e.g. concurrency ceiling, resource limit, or cost).

MEGB-03G must not assume that MEGB-06H will independently solve any missing execution capacity — MEGB-06A is the downstream feasibility gate that consumes this evidence, and it is authorized to reduce \(R_s\), request further optimization, or halt on the basis of what MEGB-03G actually measured, not on an unstated assumption that capacity will materialize later.

#### 6. Required tests (in addition to the original "Required Tests" below)

- v2 aggregation construction from a valid 164-entry manifest and matching task-result set.
- Manifest/result identity mismatch rejection: mismatched run context, mismatched candidate identity, mismatched task-manifest checksum, mismatched oracle/evaluator/comparison/execution/schema versions.
- Repeated candidate SHA-256 values across *different* tasks remain valid (per the MEGB-03E/F Approved Correction (v2) — candidate-hash uniqueness is never required across tasks).
- Rejection of reduced-development-profile results, full-suite-compatibility diagnostics presented as primary `q_ref_task`, mixed-profile task-result sets, and 163-task experimental task IDs presented to the 164-task aggregator.
- Cache-key sensitivity to every key component listed in section 3, with a dedicated test for `reference_case_checksum` specifically (two otherwise-identical results differing only in `reference_case_checksum` must produce different cache keys and must not be treated as a cache hit for one another).
- Valid-result reuse (cache hit) and invalid/incomplete-result nonreuse (never a cache hit; follows the frozen recovery policy instead).
- Sequential/parallel semantic equivalence: the same task-candidate inputs produce the same accepted results and the same final aggregate regardless of concurrency level.
- Bounded concurrency and backpressure behavior, including a configuration that intentionally exceeds available capacity.
- Interruption/resumption without duplicate accepted results and without silently dropping an in-flight execution.
- Deterministic canonical ordering of results in the aggregate output, independent of execution/completion order.
- Audit/execution-count reconciliation: expected, cache-hit, newly executed, failed, and total counts reconcile exactly after a run, including an interrupted-and-resumed run.
- Protected-data and reference-isolation checks: the orchestration and cache layers expose no reference-only evidence, expected outputs, or canonical solutions outside the accepted privileged boundary.
- Throughput-report schema and reproducibility: the throughput report itself is typed, versioned, checksummed, and its projections are recomputable from its recorded raw measurements.

#### 7. Preserved scope

This amendment is specification-only. It does not amend MEGB-04 through MEGB-09; none of their text is affected. It does not authorize exposing privileged evidence beyond the boundary already accepted in MEGB-03B/03C/03D. It does not authorize beginning MEGB-03G implementation — that remains a separate, explicitly authorized step.

#### Internal Checkpoint Log (MEGB-03G.1–G.5)

Tracks the internal execution-plan checkpoints from the accepted MEGB-03G pre-implementation plan. Each checkpoint requires its own explicit authorization; this log is updated only for checkpoints actually authorized and executed, and only this table — no other part of this ticket — is touched to record that progress.

| Checkpoint | Status | Commit(s) | Tests | Deviations |
| --- | --- | --- | --- | --- |
| MEGB-03G.1 — Aggregation and Profile Enforcement (original submission) | Superseded by the correction below; not accepted as originally submitted | `8a3974b` | 19 focused (`tests/test_reference_aggregation.py`) + full offline suite 396 passed, 27 deselected, 0 failed; `mypy src tests` clean; `pylint src tests` 9.99/10, exit code 8 (not suppressed) | Found and reported without fixing (per the "stop and report a schema gap" instruction): comparison-profile identity (`COMPARISON_PROFILE_VERSION`) had no persisted field on `ReferenceTaskResult`/`ReferenceRunContext`, so the aggregator could not independently re-verify it. Also left an un-suppressed `R0801` duplicate-code finding (exit code 8) pending separate authorization. Preserved here as historical context; superseded by the row below. |
| MEGB-03G.1 correction — schema completeness (comparison-profile identity) | **ACCEPTED** (acceptance covers aggregation and full-profile enforcement only, per commits `c71b1b7`/`e02370e`; does not extend to caching, orchestration, audit, redaction persistence, throughput, or CLI, which remain unimplemented and belong to later MEGB-03G.2–G.5 checkpoints) | `8a3974b`, `c71b1b7`, `e02370e` | 9 new/updated tests across `test_result_schema.py` (88), `test_result_redaction.py` (24), `test_reference_evaluator.py` (44), `test_reference_evaluator_docker.py` (3, real Docker), `test_reference_aggregation.py` (20) + full offline suite 402 passed, 27 deselected, 0 failed; real Docker vertical slice 3/3 passed using the v3 context; `mypy src tests` clean; `pylint src tests` **10.00/10, exit code 0** | Schema gap closed: `ReferenceRunContext.comparison_profile_version` added (v3; see MEGB-03E's "Schema Completion (v3)" section above for the full defect analysis and fix — `RESULT_SCHEMA_VERSION` `reference-result-schema-v2` → `reference-result-schema-v3`, both v1 and v2 payloads rejected, no persisted artifact required migration). The comparison-profile invariant is enforced two ways: `evaluate_reference` now validates `run_context.comparison_profile_version` against the evidence's actual comparison profile before execution, and `aggregate_reference_results`'s existing run-context-equality check now catches cross-task comparison-profile inconsistency automatically (no new dedicated aggregation check needed). The 3 `R0801` findings were resolved with a file-scoped `# pylint: disable=duplicate-code` suppression in `tests/test_reference_aggregation.py`, justified there and matching the `test_reference_partition_lock.py` precedent — no global disable, no `--exit-zero`, no behavior change. |
| MEGB-03G.2 — Content Cache, Audit, and Artifact Persistence (original submission) | Superseded by the correction below; not accepted as originally submitted | `fd55f56` | 79 focused (33 `test_reference_cache_key.py` + 21 `test_reference_cache.py` + 25 `test_reference_audit.py`) + full offline suite 481 passed, 27 deselected, 0 failed; `mypy src tests` clean; `pylint src tests` 10.00/10, exit code 0 | Found and reported without fixing (per the "stop and report a schema gap" instruction): `protocol_version` sourced from the live `EXECUTION_PROTOCOL_VERSION` constant rather than a persisted `ReferenceRunContext`/`ReferenceTaskResult` field. A subsequent cache-provenance audit (requested before accepting this checkpoint) found this was one of four related gaps; superseded by the row below. `PrivilegedCaseDiagnostic` persistence remains deferred entirely in both submissions, per explicit scope. The production-code `R0801` duplicate-code suppression in `reference_audit.py`'s module docstring is preserved unchanged by the correction. |
| MEGB-03G.2 correction — cache-provenance audit (execution-protocol/dataset/partition-checksum completeness) | **ACCEPTED** (accepted together with the original implementation commits below as one accepted checkpoint: `fd55f56` initial cache/audit implementation, `d0852fb` initial checkpoint record, `c8baea4` cache-provenance/v4 correction, `970dba9` corrected checkpoint record; accepted requirements explicitly include `execution_protocol_version`/`dataset_checksum`/`task_manifest_checksum` on `ReferenceRunContext`, `expected_output` inclusion in `reference_case_checksum`, result-schema v4, cache-key/cache-entry v2, audit-record v2, and the decision not to migrate nonexistent persisted artifacts) | `fd55f56`, `d0852fb`, `c8baea4`, `970dba9` | 23 new/updated tests across `test_result_schema.py`, `test_result_redaction.py`, `test_reference_evaluator.py`, `test_reference_aggregation.py`, `test_reference_cache_key.py`, `test_reference_cache.py`, `test_reference_evaluator_docker.py` + full offline suite 504 passed, 27 deselected, 0 failed; real Docker vertical slice 3/3 passed and complete Docker-marked suite 27/27 passed under v4, no leftover containers; `mypy src tests` clean; `pylint src tests` 10.00/10, exit code 0 | A full provenance audit (against the approved MEGB-03G cache-key amendment, the v3 result schema, and the dataset/partition/oracle lock schemas) confirmed four gaps, closed together as one coherent correction: (1) `execution_protocol_version` added to `ReferenceRunContext`, verified by `evaluate_reference` against the protocol actually used, derived by `cache_key_for()` exclusively from the persisted context (never a live constant); (2) `dataset_checksum` added (content-bound, = `DatasetProvenance.evalplus_dataset_hash`, natively 32 characters — not forced into sha256-hex format); (3) `task_manifest_checksum` added (sha256-hex, matching `ReferenceBenchmarkResult`'s existing field of the same name/purpose, now cross-checked for agreement); (4) `reference_case_checksum`'s hash payload extended to include `oracle_record.expected_output`, not just case identity/build-success — closing the gap where a corrected canonical solution regenerating the same case IDs with a different expected output was previously invisible to the checksum. `oracle_version`/`evaluator_version`/`execution_profile_id`/`comparison_profile_version` were confirmed to be legitimate human-managed version labels for project-controlled code, not gaps. Cascading breaking version bumps, each confirmed via repo-wide search (including `artifacts/privileged/`) to have no persisted artifact of any older version: `RESULT_SCHEMA_VERSION` v3→v4 (rejects v1/v2/v3); `CACHE_KEY_SCHEMA_VERSION` v1→v2; `CACHE_ENTRY_SCHEMA_VERSION` v1→v2; `AUDIT_RECORD_SCHEMA_VERSION` v1→v2. No migration path provided for any of them. |
| MEGB-03G.3 — Production Orchestration and Resumption | **ACCEPTED** | `98e6f81`, `96d8409`, `d046970` | 31 focused (`tests/test_reference_orchestrator.py`) + full offline suite 535 passed, 27 deselected, 0 failed; `mypy src tests` clean; `pylint src tests` 10.00/10, exit code 0 | `src/reference/reference_orchestrator.py` adds `WorkItem`/`OrchestrationConfig`/`RetryPolicy`/`WorkItemOutcome`/`OrchestrationRunSummary`, an `EvidenceResolver` protocol + `MappingEvidenceResolver`, and `ReferenceOrchestrator` (cache-first execution, deduplication by a prospective cache key computed before any execution, bounded concurrency/backpressure via a sliding admission window over `ThreadPoolExecutor`, a retry policy scoped to `INVALID_INFRASTRUCTURE` only, and cooperative-cancellation/`KeyboardInterrupt` handling that preserves accepted results and resumes via cache hits). Does not call `aggregate_reference_results` and does not require `ReferenceValidationCandidateSetManifest` or a 163/164 count. Accepted together with three reviewed architectural decisions, each confirmed correct for this checkpoint's scope: (1) **`MappingEvidenceResolver` in place of a privileged-corpus-reading resolver** — accepted as the correct scope boundary; the protocol abstraction keeps the orchestrator independently testable and avoids coupling orchestration policy to privileged MEGB-03B/03C corpus details, deferring a production resolver to a later, explicitly authorized step. (2) **`run()` catches and does not propagate `KeyboardInterrupt`**, returning a typed `interrupted=True` `OrchestrationRunSummary` instead — accepted as preferable for a batch execution engine, enabling clean auditing, partial reporting, and deterministic resumption; `d046970` strengthens `run()`'s own docstring to state this contract explicitly (callers must check `summary.interrupted` themselves). (3) **`_logically_equivalent()` reconciles `CONFLICTING_WRITE` via semantic equivalence**, deliberately ignoring the observational fields `evaluated_at`/`duration_seconds` — accepted as the correct design; `d046970` strengthens its docstring to name the semantic (must-match) vs. observational (excluded) fields explicitly and confirms it is the single centralized definition, used at exactly one call site. |
| MEGB-03G.4 — Equivalence, Security, and Throughput Validation | Implemented and executed; **readiness: `ORCHESTRATION_READY_FOR_MEGB_03H`**; awaiting acceptance | `888430c`, `e13a997` | 25 focused (`tests/test_g4_benchmark.py`, offline/fake-backend) + full offline suite 560 passed, 27 deselected, 0 failed; `mypy src tests` clean; `pylint src tests` 10.00/10, exit code 0; real-Docker execution below | `src/reference/g4_benchmark.py` implements the frozen benchmark plan (see "Approved MEGB-03G.4 Benchmark Plan" above) and was executed once against a real `DockerPerInvocationBackend` via `python -m src.reference.g4_benchmark`. **Calibration:** 3 samples, `0.478s`/`0.278s`/`0.328s`, mean `0.361s`/invocation — well under the threshold needed to require scaling (`scale_factor=1.0`; unscaled projection `129.3s` vs. the `3300s` (55-minute) target, so every run used its full frozen `N`: throughput-sweep 8, cross-tier 4, interruption 6; `358` total case invocations). **Throughput sweep** (MEDIAN tier, N=8): concurrency 1 → `13.86s`; concurrency 2 → `6.34s`; concurrency 4 → `4.77s`; best speedup **2.905×** (≥1.5× criterion met). **Cross-tier equivalence:** LOW/MEDIAN/HIGH all `equivalent=true`, zero mismatched work items. **Warm-cache check:** all 8 items were cache hits, `fresh_execution_keys=0`. **Interruption/resumption:** first run interrupted after 1 of 6 items (5 correctly `NOT_STARTED`); resumed run completed all 6 with 0 unstarted (`fully_completed_without_gaps=true`). **Leftover containers:** none, confirmed both by the report's own check and an independent `docker ps -a --filter name=megb-runner-` after the run. Total wall-clock: `66.5s` (well within the 60-minute ceiling and the 55-minute target). Isolation preservation and deterministic ordering are inherited unchanged from MEGB-03G.3's own accepted guarantees (no candidate batching, no backend/orchestrator changes) rather than re-measured by a dedicated new check here. Two implementation-level defects were found and fixed while validating the offline wiring (zero-padded case-ID lexical-sort bug; `evaluate_reference`'s hardcoded `dataset_version == HUMANEVAL_PLUS_VERSION` check forcing the real version label instead of a synthetic one) — both are pure bugfixes in the new G.4 code itself, not changes to any already-accepted module. Per section 4, this readiness state is an orchestration-qualification claim only — it does not claim final MEGB-06A readiness, which remains MEGB-03H's and MEGB-06A's determination. |
| MEGB-03G.5 — Documentation, CI, and Final Acceptance | Not started | — | — | — |

### Approved MEGB-03G.2–G.5 Scope Amendment

Authorized following a read-only scope and compatibility review of MEGB-03G.2 through MEGB-03G.5 against MEGB-03H, MEGB-03I, and the relevant MEGB-06 reference-evaluation requirements (conducted after MEGB-03G.1's acceptance). This amendment is additive to the "Approved MEGB-03G Compatibility Amendment" above: it does not reopen or alter MEGB-03G.1's already-accepted scope, and it supersedes conflicting text only where explicitly noted below, per this ticket's amendment-precedence rule. All prior amendment text is preserved verbatim as historical context.

#### 1. Manifest-independent orchestration

The MEGB-03G.2 cache and the MEGB-03G.3 orchestration primitive operate on individual task-candidate-evaluator work items independently of any benchmark manifest. They must:

- support the 164-task reference-validation workflow (feeding MEGB-03G.1's `aggregate_reference_results`); and
- be reusable, unmodified, by MEGB-06H for its own 163-task experimental workflow against `primary_experiment_task_manifest`.

Only `aggregate_reference_results` remains restricted to the 164-entry `ReferenceValidationCandidateSetManifest`. MEGB-03G must not construct a 163-task \(Q_{\mathrm{ref}}\) aggregate, \(Q_{\mathrm{meas}}\), gaming delta, or any other MEGB-06 scientific result — that remains exclusively MEGB-06I's responsibility, per the original amendment's section 2.

#### 2. Protected cache and diagnostic storage

- The persistent reference-result cache is a **privileged artifact** and must live under `artifacts/privileged/`, following the policy already established in `docs/measurement/privileged-artifact-policy.md` for MEGB-03B/03C/03D — regardless of whether `ReferenceTaskResult.diagnostics` is currently empty in practice. Cache contents must never be committed to git.
- Cache serialization must use a typed, versioned, integrity-checked schema (mirroring the existing lock-file pattern: schema/algorithm version, checksums, refusal of silent overwrite).
- `PrivilegedCaseDiagnostic` records are not part of the append-only safe audit log described in the original requirement 9 — that schema is intentionally limited to identity/version/timestamp/status fields and contains no case-level content.
- If `PrivilegedCaseDiagnostic` records are persisted at all (e.g. for debugging), they must use a separate privileged location and retention policy from both the cache and the audit log, never commingled with either.
- Committed audit records must use an explicit field allowlist and must never contain case inputs, case identifiers, expected outputs, canonical solutions, candidate code, exception payloads, or free-form diagnostics.

#### 3. MEGB-03G.4 versus MEGB-03H

MEGB-03G.4 owns **orchestration qualification**:

- sequential/concurrent semantic equivalence;
- isolation preservation;
- cache correctness;
- deterministic output ordering;
- bounded concurrency and backpressure;
- interruption/resumption correctness;
- infrastructure-level throughput measurement.

MEGB-03H owns **scientific execution qualification**:

- real-corpus resource calibration;
- the frozen high-assurance execution profile;
- repeated-run and environmental determinism;
- definitive runtime and compute projections used by MEGB-06A.

**Supersedes the original amendment's section 5 readiness-declaration language:** MEGB-03G.4's checkpoint report must name its readiness state as one of:

- `ORCHESTRATION_READY_FOR_MEGB_03H`; or
- `ORCHESTRATION_BLOCKED`.

MEGB-03G.4 must not claim final readiness for MEGB-06A — that determination remains MEGB-03H's and MEGB-06A's, made after the real-corpus execution profile is frozen. MEGB-03H must reconcile its own runtime/resource measurements against MEGB-03G.4's infrastructure-level throughput projections and report any material divergence, rather than independently producing an unrelated estimate (see MEGB-03H's own "Approved Compatibility Note" below).

#### 4. Corrected MEGB-03G.4 benchmark plan

The previously proposed 15–20 tasks × 3 candidates scale is rejected: at the measured ≈3 minutes per task-candidate pair, its sequential leg alone would take approximately 135–180 minutes, which cannot satisfy a 60-minute total ceiling.

MEGB-03G.4 must instead use **synthetic, non-privileged `ReferenceTaskEvidence` workloads** with case counts selected to represent low, median, and high workload sizes. No real reference-only inputs, expected outputs, canonical solutions, or privileged manifests are required or permitted for this orchestration benchmark.

Before any material Docker execution, MEGB-03G.4 must produce a benchmark plan that is itself frozen and separately accepted, specifying:

- the exact synthetic workload definitions and their checksums;
- the number of task-candidate work items;
- concurrency levels — provisionally 1, 2, and 4, unless MEGB-02's own demonstrated concurrent-execution evidence safely supports a higher level;
- cold-cache, warm-cache, and interrupted/resumed runs;
- a total wall-clock ceiling of 60 minutes;
- an abort condition if that ceiling, or a declared host-resource ceiling, is exceeded.

**Minimum `ORCHESTRATION_READY_FOR_MEGB_03H` criteria:**

- 100% typed-result equivalence between sequential and concurrent execution;
- zero isolation violations;
- zero missing or duplicate accepted work items;
- deterministic final ordering;
- exact expected cache-hit behavior, with no backend execution for valid hits;
- successful interruption and resumption without repeating already-accepted work;
- at least one bounded-concurrency configuration achieving ≥1.5× throughput over sequential execution on the same host and workload;
- no unresolved infrastructure error or resource leak.

Failure of any correctness, isolation, or resumption criterion is `ORCHESTRATION_BLOCKED`. Failure to reach the throughput threshold must also be reported as `ORCHESTRATION_BLOCKED` unless explicitly accepted through a later amendment. These are infrastructure-readiness criteria only — MEGB-03H remains responsible for determining whether the frozen real-corpus execution profile is feasible for MEGB-06.

#### 5. MEGB-03G.5 versus MEGB-03I

MEGB-03G.5 owns only MEGB-03G's own acceptance matrix, documentation, CI coverage, and handoff to MEGB-03H. It must not claim final MEGB-03 epic acceptance — that remains MEGB-03I's "Final Acceptance Criteria" and epic-wide acceptance matrix.

MEGB-03G.5 may provide internal build/verify commands for its own cache, audit, or benchmark artifacts, following the existing `*_cli.py` pattern already established by `partition_cli.py`/`oracle_cli.py`/`parity_cli.py`. It must not implement the user-facing `evaluate-reference` CLI, which remains owned exclusively by MEGB-03I.

Expensive throughput checks (MEGB-03G.4's benchmark) must use a designated manual or scheduled workflow and must not run on every push, consistent with the pattern MEGB-03I requirement 9 already establishes for full-suite validation.

#### 6. Compatibility diagnostics

Confirmation only, no new requirement: the already-proven invariant that `FullSuiteDiagnostic` may be attached to a task result but can never affect `q_ref_task` or benchmark `q_ref` remains in force, per MEGB-03G.1's accepted regression test (`test_full_suite_diagnostic_never_affects_q_ref`). No additional implementation is required for this unless later work is found to violate it.

### Approved MEGB-03G.4 Benchmark Plan (Frozen)

Satisfies section 4's requirement, above, that a benchmark plan be frozen and separately accepted before any material Docker execution for MEGB-03G.4. Nothing here authorizes exceeding the corrected scale rejection already recorded in section 4 (the original 15–20 tasks × 3 candidates plan remains rejected).

**1. Synthetic workload (fully non-privileged, frozen now, no real corpus content)**

- `entry_point = "g4_compute"`; canonical solution `def g4_compute(n):\n    return (n * 2) + 1\n` — sha256 `f677aa4cceca480683e70c3a23d2fd095f8ac3e77fd487432364095cdced5e47`.
- Comparison profile: default kind, `atol=0.0`, via the existing `comparison_profile_for_task` (purely structural; not a binding to any real task).
- Benchmark-only run-context identity, never confusable with the real corpus: `dataset_version="synthetic-g4-benchmark-v1"`, `dataset_checksum = sha256("g4-benchmark-synthetic-dataset-v1") = 620d891af7232d54263877049d3e8720fc81cb38e3f2afad3e476b7e6936f8a9`; `task_manifest_checksum = sha256("g4-benchmark-synthetic-manifest-v1") = 2660eefaf368c747f88db3842d5d4c021279e6b1c6bd60b7be1cdb318f0f8977`.
- Three tiers by per-task case count: **LOW=1**, **MEDIAN=5**, **HIGH=20** (args `n=1..count`). Task IDs are namespaced per (tier, run) as `G4Bench/{tier}-{run_label}/{i}` so every run below is guaranteed a cold cache (no accidental reuse across runs that are each supposed to measure a fresh execution) — coldness by construction, not by clearing state.
- One fixed correct candidate reused across tasks within a run; per-task dedup still yields one unique cache key per task_id (candidate_sha256 alone never collapses distinct tasks — already proven in MEGB-03G.3).

**2. Calibration step (runs first, sequential, N=3 single-case LOW invocations, concurrency=1)**

Measures real per-invocation Docker overhead (`measured_per_invocation_sec`) on the executing host before any other run proceeds.

**3. Scaling rule (per this checkpoint's requested modification — supersedes a plan that merely "fits")**

- `total_case_invocations` for the workload below at full (unscaled) size = 358 (throughput sweep 120 + cross-tier equivalence 208 + interruption/resumption 30; the warm-cache run contributes ~0 real invocations).
- `projected_seconds = measured_per_invocation_sec × total_case_invocations` (a conservative, concurrency-blind upper bound — concurrent legs will finish faster in wall-clock than this projects, giving additional real margin beyond what the projection itself claims).
- Target ceiling: **55 minutes (3300s)**, not 60 — a deliberate 5-minute headroom, per this checkpoint's instruction not to merely "fit."
- If `projected_seconds > 3300`, scale every tier's/run's item count `N` down by the same factor `min(1.0, 3300 / projected_seconds)` (rounded down, minimum 1 per run), preserving the plan's relative proportions (throughput-sweep : cross-tier : interruption item counts) rather than cutting one section disproportionately. Re-derive `total_case_invocations` and `projected_seconds` from the scaled counts and confirm the scaled projection is under the ceiling before proceeding.
- If `measured_per_invocation_sec` is so high that even `N=1` per run cannot fit under 3300s, stop and report `ORCHESTRATION_BLOCKED` for the throughput-measurement portion specifically, rather than silently running over budget; correctness-only runs (equivalence, cache, interruption) may still proceed at `N=1` if they independently fit.
- The checkpoint report must record: `measured_per_invocation_sec`, the calibration run's own raw timings, `total_case_invocations` (unscaled and scaled), `projected_seconds` (unscaled and scaled), the scaling factor applied (or "no scaling required"), and the resulting per-run `N` actually used — sufficient for the chosen workload size to be independently reproduced from these inputs.

**4. Work items per run (at full, unscaled size — subject to section 3's scaling rule)**

- **Throughput sweep** (proves the ≥1.5× criterion): MEDIAN tier, N=8 unique work items per run, run cold at concurrency **1, 2, and 4** (3 runs, each in its own task namespace) = 8×5×3 = 120 case invocations (unscaled).
- **Cross-tier correctness/equivalence**: for each of LOW, MEDIAN, HIGH tiers, N=4 unique work items, run once at concurrency=1 (sequential) and once at concurrency=4 (concurrent), each pair in its own task namespace; the two runs' typed outcomes (per work item, ignoring only the observational `evaluated_at`/`duration_seconds` fields — the same semantic/observational distinction `_logically_equivalent()` already draws) must match exactly. Case invocations: (1×4 + 5×4 + 20×4) × 2 legs = 104 × 2 = 208 (unscaled).
- **Warm-cache run**: immediately re-run the MEDIAN throughput-sweep's concurrency=4 run's N=8 items a second time — every item must be a `CACHE_HIT` with zero backend calls.
- **Interruption/resumption**: MEDIAN tier, N=6, concurrency=2, in its own task namespace; cooperative cancellation triggered once the first item completes; a second `run()` call over the same 6 items must then complete the rest with zero duplicate accepted results. Case invocations: 6×5 = 30 (unscaled), split across the two `run()` calls.

**5. Ceiling and abort**

60-minute absolute ceiling per the original amendment; this plan targets ≤55 minutes actual/projected per section 3. Abort with `ORCHESTRATION_BLOCKED` if either the (possibly re-scaled) projection or actual measured elapsed time would exceed 60 minutes, or if any existing MEGB-02 host-resource ceiling is hit, or if the leftover-container check (the same one the Docker CI job already runs) finds anything left behind.

**Minimum `ORCHESTRATION_READY_FOR_MEGB_03H` criteria** are exactly the amendment's own list in section 4 above (100% sequential/concurrent typed-result equivalence; zero isolation violations; zero missing or duplicate accepted work items; deterministic final ordering; exact cache-hit behavior with no backend execution for valid hits; successful interruption/resumption without repeating already-accepted work; at least one concurrency configuration achieving ≥1.5× throughput over sequential on the same host/workload; no unresolved infrastructure error or resource leak).

### Approved MEGB-03G.4 Correction (Synthetic Evaluator Provenance + Ordering/Isolation Validation)

Authorized after reviewing the first MEGB-03G.4 run (commits `888430c`, `e13a997`, `9db967b`; readiness declared `ORCHESTRATION_READY_FOR_MEGB_03H`). That declaration is **not accepted** and does not qualify readiness, for two reasons, both corrected below. The measurements themselves (calibration `0.361s`/invocation, best speedup `2.905×`, `66.5s` total wall-clock) are preserved as **historical context only** — the frozen threshold (`≥1.5×`, 60-minute ceiling, 1/2/4 concurrency levels, cache/interruption/equivalence criteria) is unchanged by this correction and must not be re-litigated.

**Defect 1 — false provenance.** The prior run set `dataset_version = HUMANEVAL_PLUS_VERSION` (and, less visibly, also reused `PARTITION_ALGORITHM_VERSION`, `ORACLE_ALGORITHM_VERSION`, `COMPARISON_PROFILE_VERSION`, `EVALUATOR_VERSION_FULL`, `EXECUTION_PROFILE_ID_FULL`, and `EXECUTION_PROTOCOL_VERSION` — every real-corpus identity `evaluate_reference`'s internal cross-check touches) purely to satisfy `evaluate_reference`'s hardcoded `evidence.dataset_version == HUMANEVAL_PLUS_VERSION` assertion. This is unacceptable: a synthetic benchmark result must never carry any real-corpus identity, even as an inert label.

**Defect 2 — omitted validation.** The frozen plan's own minimum criteria already required "zero isolation violations" and "deterministic final ordering" against the real backend. The prior run only *asserted* these were "inherited unchanged from MEGB-03G.3's synthetic-backend tests" rather than actually measuring them against a real `DockerPerInvocationBackend`. That assertion is insufficient — MEGB-03G.4's whole purpose is to validate G.3's synthetic-backend guarantees hold under the real MEGB-02 boundary, not to assume it.

#### 1. Benchmark-only evaluator adapter — design

**The result schema has no conflict.** `ReferenceRunContext`/`ReferenceTaskEvidence`/`ReferenceTaskResult`/`ExecutionProfile` validate their string identity fields only for nonempty-ness (or sha256-hex shape where a checksum is required) — none of them hardcode a comparison against any real constant. The real-corpus cross-check lives *only* inside `evaluate_reference`'s own `_verify_versions` (in `src.reference.reference_evaluator`), which this correction never touches. There is therefore no schema conflict to report — the fix is a new, separate, benchmark-only evaluation function that never calls or is called by `evaluate_reference`.

**New module `src/reference/g4_benchmark_evaluator.py`** defines its own fully synthetic identity constants, none equal to any real MEGB-03B/C/E/F constant:

- `G4_EVALUATOR_VERSION = "megb-03g4-benchmark-evaluator-v1"`
- `G4_EXECUTION_PROFILE_ID = "megb-03g4-benchmark-profile-v1"`
- `G4_EXECUTION_PROTOCOL_VERSION = "megb-03g4-benchmark-protocol-v1"`
- `G4_DATASET_VERSION = "megb-03g4-synthetic-dataset-v1"`
- `G4_PARTITION_VERSION = "megb-03g4-synthetic-partition-v1"`
- `G4_ORACLE_VERSION = "megb-03g4-synthetic-oracle-v1"`
- `G4_COMPARISON_PROFILE_VERSION = "megb-03g4-synthetic-comparison-v1"`
- `G4_DATASET_CHECKSUM`/`G4_TASK_MANIFEST_CHECKSUM`: sha256 of fixed literal synthetic labels (unchanged in kind from the prior run, already never real).

`evaluate_g4_benchmark_candidate(evidence, candidate_code, candidate_id, candidate_sha256, run_context, *, backend, profile)` mirrors `evaluate_reference`'s *shape* (same parameter list, same real `ExecutionBackend`/`CandidateExecutionRequest` boundary, same `compare_outputs` comparison utility, same `ReferenceTaskResult` construction) but performs its own internal consistency check — `run_context`'s fields must match `evidence`'s fields and this module's own `G4_*` constants — never against `HUMANEVAL_PLUS_VERSION`/`PARTITION_ALGORITHM_VERSION`/`ORACLE_ALGORITHM_VERSION`/`COMPARISON_PROFILE_VERSION`/`EVALUATOR_VERSION_FULL`/`EXECUTION_PROFILE_ID_FULL`/`EXECUTION_PROTOCOL_VERSION`. It never claims to be HumanEval, EvalPlus, the frozen reference partition, or S\* — its own `oracle_version`/`partition_version`/`comparison_profile_version`/`evaluator_version`/`execution_profile_id`/`execution_protocol_version` are all `G4_*`-prefixed and structurally distinct from every real constant (proved by a direct equality-negation test, not just by convention).

`ReferenceTaskEvidence`/`ReferenceCase`/`OracleRecord`/`ComparisonProfile` (all already-accepted, generic MEGB-03C/F types) are still reused as *containers* — reusing a generic, content-agnostic schema is not the same as claiming real content — but every value stored inside them (`pool`, `provenance`, `comparison_profile.profile_version`, task/case IDs, `expected_output`) is fully synthetic, matching the original plan's own already-accepted requirement.

#### 2. Required additive extension to MEGB-03G.3

To let the orchestrator call `evaluate_g4_benchmark_candidate` instead of `evaluate_reference` for this benchmark's work items — without weakening `evaluate_reference` or adding any bypass inside it — `ReferenceOrchestrator.__init__`/`OrchestrationConfig` gains one new, purely additive constructor parameter:

```python
evaluator: Evaluator = evaluate_reference
```

(`Evaluator` a `Protocol` matching `evaluate_reference`'s exact call signature.) Defaulting to the real `evaluate_reference` means **every existing MEGB-03G.3 behavior, test, and production call site is byte-for-byte unchanged** — this is confirmed, not assumed, by re-running the complete existing `tests/test_reference_orchestrator.py` suite unmodified after the change and requiring 100% pass with no edits to that file. `_execute_with_retries`'s one hardcoded call becomes `self._evaluator(...)`. This is the only change to already-accepted G.3 code in this correction; `evaluate_reference` itself, `reference_cache.py`, `reference_audit.py`, and `cache_key.py` are all untouched.

#### 3. Structural non-contamination proof (required tests, offline)

- `aggregate_reference_results` rejects any G4 benchmark result set: proved on two independent grounds — wrong count (`_require_exact_count`, since G4 batches are never 164 items) and, separately, profile mismatch (`_require_full_reference_profile` rejects `G4_EVALUATOR_VERSION`/`G4_EXECUTION_PROFILE_ID` even if artificially padded to 164).
- A G4 result can never be mixed into the same `ReferenceBenchmarkResult`/aggregation call as a real result: `_require_shared_run_context`'s existing run-context-equality check already rejects any context whose `dataset_version`/`partition_version`/`oracle_version`/`comparison_profile_version`/`evaluator_version`/`execution_profile_id`/`execution_protocol_version` differ from the real profile's — proved directly rather than assumed.
- A G4 result can never contribute to `q_ref`/`Q_ref`: `ReferenceBenchmarkResult.q_ref` is only ever computed over `task_results` actually inside a constructed benchmark result, and the previous bullet already proves a G4 result can never enter one.
- Cache-collision freedom: primarily structural (a dedicated `g4_benchmark_cache/` directory, never the production `artifacts/privileged/reference/cache/`), reinforced by every one of the six version/checksum fields in `ReferenceResultCacheKey` differing from the real profile's own — proved by direct field-inequality assertions, not probabilistic digest non-collision.
- Manifest-independence is unchanged: the orchestrator still never imports `ReferenceValidationCandidateSetManifest`/`primary_experiment_task_manifest`/`aggregate_reference_results` (already covered by an existing G.3 test); this correction adds no new manifest coupling.

#### 4. Real-Docker ordering validation (new, Docker-marked, joins the existing Docker-marked suite — not the throughput benchmark's own "not on every push" path, since this is a bounded correctness check, not an expensive measurement)

A concurrency=4 run whose per-item candidates have deliberately staggered sleep durations (longest-sleeping item admitted first) so real completion order provably differs from admission order. Verifies: actual completion order (observed via a thread-safe completion-order recorder wrapping the real backend) differs from input order; `summary.outcomes` order exactly matches declared `input_ordinal`; each outcome's `task_id`/`candidate_id` matches its own work item; a second, independent run over the same items reproduces identical ordering and associations; zero duplicate or missing accepted results.

#### 5. Real-Docker concurrent-isolation validation (new, Docker-marked)

Multiple writer/reader candidate pairs, run concurrently (concurrency=4) through the orchestrator, each pair using the *same* fixed in-container filename but a distinct per-pair secret: a writer candidate writes its own secret to that filename and briefly sleeps (keeping its container alive concurrently with other pairs' containers); a reader candidate (a logically separate work item/container) attempts to read the same filename and returns what it finds. Verifies: every reader's result is `"NOT_FOUND"` — never any writer's secret, including its own pair's (since MEGB-02 gives every invocation, even within the same pair, a fresh container with no persistent state) — proving no writable-state sharing between concurrently-running containers; each writer's own result correctly reflects its own secret; no result is ever attributed to the wrong work item under concurrency; `docker ps -a --filter name=megb-runner-` shows no leftover container after the test, including on a failure path.

#### 6. Safe qualification report (committed, non-privileged)

`src/reference/g4_qualification_report.py` derives a committed JSON report plus a Markdown rendering, deterministically from a `G4BenchmarkReport`, containing only: benchmark-plan version/checksum; synthetic-workload version/checksum; implementation commit SHA and dirty-state flag; Docker image ID/provenance checksum; host/platform summary; configuration counts/concurrency levels; aggregate timing/throughput; equivalence/isolation/ordering booleans and mismatch counts; cache/resumption counts; leftover-container result; readiness classification. It must never contain candidate source, individual synthetic inputs/expected outputs, real task/case identifiers, privileged paths, or raw exception/diagnostic payloads — enforced by an explicit field allowlist (mirroring `AUDIT_RECORD_FIELD_NAMES`'s own pattern) and a leakage test. The JSON report is self-checksummed (a `report_checksum` field over its own canonical remaining content, same auto-compute-or-reject pattern as `ReferenceResultCacheKey`/`ReferenceValidationCandidateSetManifest`). Both files are committed to git (unlike the raw run log/audit-log directory, which stays gitignored).

#### 7. Verification and re-run

The corrected benchmark is re-run in full from a clean synthetic cache directory (a fresh `g4_benchmark_cache/`, never reusing the historical run's entries, which in any case used different — now-corrected — identity fields and would miss regardless). Only this corrected run may establish `ORCHESTRATION_READY_FOR_MEGB_03H`. The historical run's measurements remain in the checkpoint log as superseded context, not as evidence for readiness.

### Objective

Implement benchmark-level aggregation, content-addressed result reuse, public-result redaction, and append-only auditing without creating an adaptive reference oracle.

### Dependencies

- MEGB-03F complete and accepted.

### Requirements

1. Implement:

   ```python
   def aggregate_reference_results(
       task_results: Sequence[ReferenceTaskResult],
   ) -> ReferenceBenchmarkResult:
       ...
   ```

2. Aggregate exactly 164 expected tasks with equal task weight.
3. Report evaluated, valid, invalid, incomplete, base-pass diagnostic, full-suite-pass diagnostic, and primary reference-only-pass counts as applicable.
4. Compute primary \(Q_{\mathrm{ref}}\) only when every required task measurement is valid.
5. Never silently reduce or change the denominator.
6. Preserve full-suite compatibility metrics under distinct identifiers.
7. Cache or reuse a valid reference result only when the complete tuple matches:
   - candidate hash;
   - task ID;
   - dataset checksum;
   - partition checksum;
   - oracle checksum;
   - comparison profile;
   - execution profile;
   - evaluator version; and
   - protocol version.
8. Never rerun a valid measurement silently. Infrastructure-invalid or incomplete results may be resumed under explicit policy.
9. Create an append-only audit record for every \(S^*\) invocation containing:
   - caller;
   - experiment and optimization run IDs;
   - candidate ID and hash;
   - freeze metadata and selection rule;
   - evaluator, dataset, partition, oracle, and execution versions;
   - invocation timestamp;
   - result-artifact location; and
   - final measurement status.
10. Make repeated or adaptive querying visible in the audit trail.
11. Produce privileged detailed artifacts and redacted public artifacts.
12. Verify that optimizer-visible outputs never contain unauthorized evidence.

### Acceptance Criteria

- Complete valid input produces the correct unweighted 164-task aggregate.
- Missing, duplicate, invalid, or inconsistent tasks prevent final \(Q_{\mathrm{ref}}\).
- Result reuse is content-addressed and version-safe.
- Every invocation produces one append-only audit entry.
- Repeated invocations are visible rather than overwritten.
- Redacted outputs pass all feedback-leakage checks.

### Required Tests

- Complete aggregation and denominator preservation.
- Missing, duplicate, invalid, and inconsistent task inputs.
- Cache-key sensitivity to every outcome-affecting version.
- Valid-result reuse and invalid-result resumption behavior.
- Audit-record construction and append-only behavior.
- Public projection and feedback-leakage tests.
- Candidate-manifest hash validation.

### Non-Goals

- CLI implementation.
- Experimental unblinding.
- Gaming-delta or intentionality analysis.

### Handoff Artifacts

- Benchmark aggregator.
- Content-addressed reference-result store/cache.
- Append-only audit facility.
- Privileged and redacted result writers.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-03H requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-03H — Calibrate Resources and Verify Deterministic Measurement

### Status

**Status:** Not started. **Approved Compatibility Note (MEGB-03G.4 Reconciliation)** applies (see below); the original "Objective" through "Completion Record" text beneath it is preserved verbatim as historical context and is superseded only where it conflicts with the note.

### Approved Compatibility Note (MEGB-03G.4 Reconciliation)

Authorized alongside the "Approved MEGB-03G.2–G.5 Scope Amendment" in MEGB-03G's own section (see that ticket section's item 3 for the full boundary analysis between MEGB-03G.4's orchestration qualification and this subtask's scientific execution qualification).

This note narrows original requirement 12 ("estimate full-suite runtime and compute requirements for CI and experimental planning"): MEGB-03H must **reconcile** its own runtime/resource measurements against MEGB-03G.4's `ORCHESTRATION_READY_FOR_MEGB_03H` infrastructure-level throughput projections, and report any material divergence, rather than independently producing an unrelated runtime estimate from scratch. MEGB-03G.4's projections are necessarily provisional — measured under whatever execution limits existed before this subtask freezes the high-assurance execution profile (requirements 4–5 below) — so a limit change here that materially changes per-task timing must be reflected in a revised joint estimate, not silently left to diverge from MEGB-03G.4's earlier figures. MEGB-03H remains the sole owner of the frozen real-corpus execution profile and the definitive runtime/compute projection MEGB-06A ultimately consumes; MEGB-03G.4 explicitly does not claim that authority (see MEGB-03G's own amendment).

### Objective

Calibrate and freeze the evaluator's execution profile using corrected canonical solutions, then demonstrate stable classifications under repeated execution.

### Dependencies

- MEGB-03G complete and accepted.

### Requirements

1. Run all corrected canonical solutions through the complete reference process for all 164 tasks.
2. Measure runtime and resource use for every task and case.
3. Identify failures attributable to evaluator limits rather than candidate behavior.
4. Establish, justify, version, and document the high-assurance execution-limit profile.
5. Freeze the profile before experimental candidate evaluation.
6. Treat a universal timeout as an execution policy, not evidence of a particular complexity class.
7. Do not tune limits after observing experimental candidate outcomes without:
   - incrementing the evaluator/process version;
   - documenting the amendment;
   - rerunning every affected candidate; and
   - treating the change as a new measurement process.
8. Given identical candidate source/hash, task, dataset, partition, oracle, comparison, execution profile, evaluator version, protocol version, and seed where applicable, require identical task classification.
9. Repeatedly evaluate the fixed canonical and known-incorrect corpora to detect:
   - nondeterministic candidate behavior;
   - environmental instability;
   - order sensitivity; and
   - evaluator instability.
10. Mark and document instability explicitly rather than selecting a favorable run.
11. Validate the reduced mini profile separately and prevent it from being reported as full \(S^*\).
12. Estimate full-suite runtime and compute requirements for CI and experimental planning.

### Acceptance Criteria

- Corrected canonical solutions produce 164/164 valid primary task measurements and \(Q_{\mathrm{ref}} = 1.0\).
- No canonical failure is caused by an unexplained evaluator limit.
- The high-assurance execution profile is versioned and frozen.
- Repeated fixed-corpus classifications are identical or produce explicit instability/invalid statuses.
- Full and mini profiles remain distinguishable.
- Runtime/resource reports are reproducible and checksummed.

### Required Tests

- Full 164-task canonical validation.
- Repeated canonical and known-incorrect corpus runs.
- Test-order sensitivity checks.
- Environment and version consistency checks.
- Explicit instability propagation tests.
- Mini/full identifier and configuration tests.
- Frozen-profile mutation refusal tests.

### Non-Goals

- Selecting limits based on experimental candidates.
- Treating resource limits as algorithmic-complexity measurement.
- Running the MEGB-06 experiment.

### Handoff Artifacts

- Frozen high-assurance execution profile.
- Reduced smoke-test profile.
- Canonical validation results.
- Determinism and instability report.
- Runtime/resource calibration report.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-03I requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-03I — Add CLI, Configuration, Documentation, CI, and Final Acceptance

### Status

**Status:** Not started

### Objective

Package the accepted reference evaluator as a reproducible, noninteractive, documented workflow; integrate validation into CI; and demonstrate satisfaction of every MEGB-03 acceptance criterion.

### Dependencies

- MEGB-03H complete and accepted.

### Requirements

1. Provide a noninteractive CLI similar to:

   ```bash
   megb evaluate-reference \
     --run-manifest artifacts/runs/run-001/manifest.json \
     --candidate-manifest artifacts/runs/run-001/frozen-candidates.json \
     --evaluator-config configs/evaluators/reference-v1.yaml \
     --output artifacts/runs/run-001/reference/
   ```

2. The CLI must:
   - verify manifests, versions, and candidate hashes;
   - refuse unfinalized candidate manifests;
   - display progress without revealing hidden evidence;
   - support explicit resumption of interrupted infrastructure failures;
   - never rerun valid task measurements silently;
   - write append-only JSONL task results;
   - write a benchmark-level summary;
   - return nonzero for invalid or incomplete evaluation; and
   - record the exact reproducibility command.
3. Create a versioned evaluator configuration containing at least:

   ```yaml
   evaluator_id: human-eval-plus-reference-only-v1
   dataset: humaneval
   dataset_version: pinned-version
   dataset_checksum: pinned-checksum
   partition_version: partition-v1
   partition_checksum: pinned-partition-checksum
   evidence_pool: reference_only
   oracle_version: oracle-v1
   protocol_version: "1"
   execution_profile: reference-high-assurance-v1
   test_suite: reference_only
   task_scoring: all_cases_pass
   benchmark_aggregation: unweighted_task_mean
   expected_task_count: 164
   ```

4. Provide a separately identified full-suite compatibility configuration, if supported. It must not emit primary \(Q_{\mathrm{ref}}\).
5. Configuration changes that can affect outcomes require a new evaluator version.
6. Create:
   - `docs/measurement/reference-evaluator.md`; and
   - `docs/measurement/reference-evaluator-validity.md`.
7. Documentation must describe:
   - \(C^*\), \(O^*\), \(M^*\), and \(P^*\);
   - the operational definition of primary \(Q_{\mathrm{ref}}\);
   - the development/reference partition and freeze procedure;
   - the distinction between reference performance and true correctness;
   - full-suite compatibility diagnostics;
   - dataset, partition, and oracle provenance;
   - comparison semantics;
   - execution policy and resource calibration;
   - scoring and aggregation;
   - candidate-freezing procedure;
   - access, blinding, and feedback restrictions;
   - reproducibility procedure;
   - known limitations; and
   - threats to validity.
8. Integrate unit and smoke validation into ordinary CI.
9. Run full-suite canonical and parity validation in a designated integration or scheduled workflow appropriate to its cost.
10. CI must distinguish skipped-by-policy tests from unavailable infrastructure and must not silently claim full validation when only the mini profile ran.
11. Produce a final acceptance matrix mapping every epic criterion to implementation, test, evidence, and limitation.

### Final Acceptance Criteria

- The evaluator covers exactly 164 version-pinned HumanEval tasks.
- The development and reference-only pools are frozen, checksummed, and disjoint.
- The primary \(Q_{\mathrm{ref}}\) uses only reference-only evidence.
- Evidence exposed through MEGB-04 cannot be represented as held-out evidence in primary \(Q_{\mathrm{ref}}\).
- All corrected canonical solutions receive valid primary task measurements with `q_ref_task = 1.0`.
- Aggregate canonical performance is \(Q_{\mathrm{ref}} = 1.0\).
- MEGB classifications match pinned upstream EvalPlus on the fixed parity corpus.
- A validated corpus includes candidates that pass original HumanEval evidence but fail expanded evidence.
- Candidate code never executes in the trusted evaluator process.
- Hidden inputs, expected outputs, oracle data, and reference logic remain outside the candidate environment.
- Candidate artifacts are frozen and hash-verified before evaluation.
- Reference results cannot be used as feedback within the originating optimization run.
- Candidate failures produce valid zero scores.
- Measurement-system failures produce undefined scores and invalidate or leave the aggregate incomplete.
- Missing or invalid tasks never silently change the denominator.
- Primary, full-suite compatibility, and mini evaluator variants have distinct identifiers.
- Repeated evaluation is deterministic under frozen configuration or returns explicit instability.
- Detailed reference evidence is excluded from public and optimizer-visible output.
- Every \(S^*\) invocation creates an append-only audit record.
- The complete evaluation is reproducible from recorded configuration, manifests, hashes, versions, artifacts, and command.
- Documentation explicitly states that \(Q_{\mathrm{ref}}\) is a privileged measurement estimate, not direct access to latent true correctness.

### Required Final Verification

- Complete unit-test suite.
- Complete MEGB-02 security regression suite relevant to evaluator integration.
- 164-task canonical-solution validation.
- Upstream EvalPlus parity suite.
- Known-incorrect candidate suite.
- Isolation and privileged-evidence exfiltration suite.
- Determinism suite.
- Invalid-measurement injection suite.
- Feedback-leakage/redaction suite.
- CLI end-to-end smoke and resume tests.
- Configuration, manifest, and checksum validation.
- Type checking and linting.
- CI execution evidence.

### Non-Goals

- Implementing MEGB-04 measurement systems.
- Candidate generation or optimization.
- Running MEGB-06 confirmatory candidates.
- Calculating gaming deltas.
- Classifying intentional versus accidental gaming.

### Handoff Artifacts

- Released privileged reference-evaluator implementation.
- Frozen primary and optional compatibility configurations.
- Trusted oracle and comparison layer.
- Frozen partition and oracle artifacts.
- Typed task and benchmark result models.
- Candidate-manifest verification.
- Append-only evaluation CLI and audit trail.
- Privileged detailed and redacted public results.
- Complete validation evidence.
- Measurement-definition and validity documentation.
- Final acceptance matrix.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. Do not begin MEGB-04 without explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## Epic Non-Goals

MEGB-03 does not:

- implement candidate generation;
- implement an optimization loop;
- expose reference results during optimization;
- calculate benchmark-gaming deltas;
- classify intentional versus accidental gaming;
- claim formal verification of candidate correctness;
- claim that HumanEval+ or the reference-only pool is un-gameable;
- eliminate model-training contamination;
- generate generic property tests from signatures;
- evaluate algorithmic efficiency as a separate construct; or
- introduce private adversarial tests beyond HumanEval+.

## Threats to Validity That Must Be Documented

At minimum:

- HumanEval+ and the reference-only partition remain finite measurement systems.
- HumanEval+ tasks and tests are publicly available.
- Evaluated models may have encountered tasks or tests during training.
- Deterministic partitioning does not make publicly sourced evidence genuinely secret.
- Canonical solutions and comparison rules may contain defects.
- The tested input domain may not cover all intended realizations.
- Passing every test does not prove functional correctness.
- Execution limits may introduce construct-irrelevant failures.
- Python-version or platform differences may affect results.
- Failures across cases and tasks are not statistically independent.
- Partition choices may affect measured robustness and reference outcomes.
- Full-suite compatibility results reuse development-visible evidence and are not held-out estimates.
- \(Q_{\mathrm{ref}}\) is a stronger proxy for the construct, not the construct itself.

## Requirement Traceability

This table maps the original MEGB-03 specification into the refactored gated subtasks.

| Original section | Refactored location |
| --- | --- |
| Objective and Measurement Claim | Epic Objective, Approved Design Amendment, Measurement Claim |
| Dependencies | Epic Dependencies |
| Privileged Evaluation Boundary | Global Architectural Constraints; MEGB-03F; MEGB-03I |
| No Adaptive Reference Evaluation | Global Architectural Constraints; MEGB-03G; MEGB-03I |
| 1. Reference Dataset Integration | MEGB-03A |
| MEGB-04 development/reference precondition | Approved Design Amendment; MEGB-03A; MEGB-03B |
| 2. Reference Oracle Construction | MEGB-03C |
| Upstream behavioral equivalence | MEGB-03D |
| 3. Candidate Evaluation Interface | MEGB-03E; MEGB-03F |
| 4. Task-Level Result Schema | MEGB-03E |
| 5. Measurement Status | Global Architectural Constraints; MEGB-03E; MEGB-03F |
| 6. Scoring Policy | Measurement Claim; MEGB-03E |
| 7. Benchmark-Level Aggregation | MEGB-03E; MEGB-03G |
| 8. Base–Plus Discrepancy | MEGB-03D; MEGB-03E; MEGB-03G |
| 9. Test Execution | MEGB-03F |
| 10. Test Ordering and Candidate State | MEGB-03F; MEGB-03H |
| 11. Full and Reduced Test Suites | MEGB-03F; MEGB-03H; MEGB-03I |
| 12. Resource Calibration | MEGB-03H |
| 13. Determinism | MEGB-03H |
| 14. Audit Trail | MEGB-03G |
| 15. Command-Line Interface | MEGB-03I |
| 16. Configuration | MEGB-03I |
| 17. Documentation | MEGB-03I |
| Unit Tests | Assigned to MEGB-03A through MEGB-03I by owned behavior |
| Canonical-Solution Validation | MEGB-03D comparison layer; MEGB-03H complete evaluator |
| Upstream Parity Validation | MEGB-03D |
| Known-Incorrect Candidate Validation | MEGB-03D; MEGB-03F; MEGB-03H |
| Isolation Validation | MEGB-03F; MEGB-03I |
| Determinism Validation | MEGB-03H |
| Invalid-Measurement Validation | MEGB-03E; MEGB-03F; MEGB-03G; MEGB-03I |
| Feedback-Leakage Validation | MEGB-03E; MEGB-03G; MEGB-03I |
| Acceptance Criteria | Distributed to subtask acceptance criteria and consolidated in MEGB-03I |
| Non-Goals | Epic Non-Goals and subtask Non-Goals |
| Threats to Validity | Epic Threats to Validity; MEGB-03I documentation |
| Deliverables | Subtask Handoff Artifacts; MEGB-03I final handoff |

## Epic Completion Rule

MEGB-03 is complete only when:

1. every subtask MEGB-03A through MEGB-03I is accepted;
2. every completion record identifies its commit and validation evidence;
3. the final acceptance matrix contains no unresolved `FAIL` or unapproved `DEFERRED` item;
4. the frozen reference evaluator and its primary `reference_only` measurement definition are reproducible; and
5. MEGB-03I has produced its checkpoint report and stopped before MEGB-04.
