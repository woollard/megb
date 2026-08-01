# [MEGB-03] Implement the Privileged Reference Evaluator \(S^*\)

## Epic Status

**Status:** In progress (MEGB-03A accepted; MEGB-03B not yet authorized)  
**Execution mode:** Sequential gated subtasks  
**Subtasks:** MEGB-03A through MEGB-03I  
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

The original MEGB-03 specification treated the full HumanEval+ suite as \(S^*\). MEGB-04 subsequently required the evidence to be divided into disjoint development and reference-only pools.

This refactored epic moves that partition upstream into MEGB-03A and MEGB-03B so the reference evaluator is constructed around the correct boundary from the outset.

The resulting policies are:

1. **Primary experimental reference measurement:** \(Q_{\mathrm{ref}}\) is computed exclusively from the frozen `reference_only` pool.
2. **Optimization-visible evidence:** MEGB-04 constructs \(S_1 \dots S_4\) exclusively from the disjoint `development` pool.
3. **Compatibility measurement:** conventional full-suite HumanEval+ performance may be computed for upstream parity and diagnostic compatibility, but it must have a distinct evaluator/profile identifier and must not be described as held out.
4. **Freeze timing:** the partition must be versioned, checksummed, and frozen before any experimental candidate is generated.
5. **No silent fallback:** if the pinned corpus cannot support the planned development and reference pools for all 164 tasks, implementation stops and the experimental design is amended explicitly.

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
- [ ] MEGB-03B — Build and freeze the development/reference partition
- [ ] MEGB-03C — Construct the privileged oracle artifact
- [ ] MEGB-03D — Validate upstream EvalPlus parity and the validation corpus
- [ ] MEGB-03E — Implement typed result models and scoring semantics
- [ ] MEGB-03F — Implement the task-level reference evaluator
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
- Commit: (recorded in a follow-up commit immediately after; see repository log for "MEGB-03A: ...")
- Completed: 2026-08-01
- Tests: `pytest tests/test_reference_case_serialization.py tests/test_reference_inventory.py -v` — 24/24 passed (6 serialization + 18 inventory, including 3 real-corpus integration tests); full offline suite 106/106 passed; mypy clean (35 files); pylint 10.00/10.
- Deviations: Recommended-policy numeric constants (30 dev / 20 reference-only / 150 target) are MEGB-03A's own justified recommendation, not literal ticket text (the ticket asks for "a" allocation rule with justification, not a specific number). `mutation_sensitive_info` is reported as explicitly unavailable rather than fabricated, since EvalPlus's integrated fields carry no per-case generation-strategy tag.
- Handoff: `artifacts/reference/evidence_inventory.json` (full per-task data, checksum `4086bfb647ccf6bc1d2e15b8f15ed9d9f158f4afa93633ea32d14c9367f2dada`), `artifacts/reference/feasibility_report.md` (human-readable), `artifacts/reference/recommended_partition_config.json` (recommended per-task dev/reference counts). **Two tasks are BLOCKED under the current policy: `HumanEval/39` (12 unique cases) and `HumanEval/55` (45 unique cases after dedup) — MEGB-03B cannot freeze a partition including these two tasks without an explicit, approved design amendment.** 23 tasks are LIMITED (feasible, but only with overlapping O4 replicates); 139 are OK.

---

## MEGB-03B — Build and Freeze the Development/Reference Partition

### Status

**Status:** Not started

### Objective

Create, validate, and freeze the deterministic manifest assigning every eligible case to exactly one of two disjoint pools: `development` or `reference_only`.

### Dependencies

- MEGB-03A complete and accepted.
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

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-03C — Construct the Privileged Oracle Artifact

### Status

**Status:** Not started

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

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-03D — Validate Upstream EvalPlus Parity and the Validation Corpus

### Status

**Status:** Not started

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

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-03E — Implement Typed Result Models and Scoring Semantics

### Status

**Status:** Not started

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

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-03F — Implement the Task-Level Reference Evaluator

### Status

**Status:** Not started

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

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-03G — Implement Aggregation, Caching, Redaction, and Audit

### Status

**Status:** Not started

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

**Status:** Not started

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
