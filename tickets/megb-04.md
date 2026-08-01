# [MEGB-04] Implement Optimization-Visible Measurement Systems \(S_1 \dots S_4\)

## Epic Status

**Status:** Not started  
**Execution mode:** Sequential gated subtasks  
**Subtasks:** MEGB-04A through MEGB-04G  
**Dependencies:** MEGB-01, MEGB-02, and MEGB-03
**Specification status:** Authoritative corrected ticket  
**Specification version:** `megb-04-ticket-v2`  
**Supersedes:** the historical monolithic, annotated, merged, and earlier refactored MEGB-04 tickets

Once committed, this document is the sole governing MEGB-04 specification. Historical MEGB-04 files may be retained for audit history, but their requirements must not be combined with this ticket.

Where an approved amendment in this ticket conflicts with earlier text, the amendment governs. Superseded language is preserved only in repository history, not repeated as an alternative operating rule.

## Epic Objective

Implement a family of optimization-visible measurement systems with controlled, monotonically increasing evidence coverage.

The systems provide the independent variable for the first MEGB experiment:

> As evidence coverage increases, the measurement system becomes harder to exploit under otherwise identical optimization conditions.

The first experiment manipulates only Observation Design \(O\). Construct Specification \(C\), Measurement Model \(M\), and Measurement Process \(P\) must remain fixed across systems.

## Alignment With Refactored MEGB-03

MEGB-04 does not create or alter the development/reference partition.

It consumes the partition frozen by MEGB-03B:

1. **Development pool:** the only evidence from which \(S_1 \dots S_4\) may be constructed.
2. **Reference-only pool:** evidence reserved exclusively for the primary experimental \(S^*\).

The primary \(Q_{\mathrm{ref}}\) is computed by MEGB-03 from `reference_only` evidence. Conventional full-suite HumanEval+ performance may exist as a separately identified compatibility diagnostic, but development evidence exposed through \(S_1 \dots S_4\) must never be described as held out.

Before MEGB-04A begins, the MEGB-03 partition must be frozen, versioned, checksummed, disjoint, and feasible for every task in the primary experimental population.

## Approved Pre-Experimental Population Amendment — MEGB-03A.1

**Status:** Approved and executed before any MEGB-04 candidate evaluation or experimental optimization.

MEGB-03A.1 established two distinct task populations:

1. **Reference-validation population:** `reference_validation_task_manifest`, containing all 164 HumanEval tasks for MEGB-03 compatibility and evaluator validation.
2. **Primary experimental population:** `primary_experiment_task_manifest`, containing 163 tasks and excluding HumanEval/39 a priori.

HumanEval/39 is structurally ineligible for the optimization-visible experiment because its complete legitimate input domain is already exhausted by the pinned evidence. It therefore has no development pool, no \(S_1\dots S_4\) measurement, and no task-level \(q_{\mathrm{meas}}\). It must not be scored as zero, inserted into an experimental denominator, or represented by a synthetic observation set.

All MEGB-04 observation manifests, registry definitions, task evaluations, aggregates, canonical-validation requirements, and freeze artifacts must consume `primary_experiment_task_manifest` and bind its checksum. Its accepted expected size is 163, but the manifest identity and checksum—not an unbound literal—govern execution.

The separate 164-task `reference_validation_task_manifest` may be verified as an upstream MEGB-03 artifact, but it does not define the MEGB-04 system population.

## Trusted Development-Oracle Boundary

MEGB-04 requires expected outputs for development cases but must not import or access MEGB-03's reference-only evaluator path.

The trusted MEGB-04 controller may consume only MEGB-03C's frozen **development oracle** through an explicitly authorized development-only loader. The loader and every evaluation context must bind:

- development-oracle artifact ID and logical checksum;
- oracle schema and generation version;
- partition and primary-task-manifest checksums;
- comparison-profile ID;
- authorized-consumer identity; and
- trusted storage policy.

The optimizer-visible runtime and candidate subprocess must never receive or access:

- development expected outputs;
- the reference-only oracle;
- the full reference-validation oracle;
- canonical solutions;
- privileged oracle diagnostics; or
- any loader capable of resolving those artifacts.

MEGB-04 must reject mixed development/reference oracle records, unauthorized consumers, task/case provenance mismatches, and checksum or version mismatches before candidate execution.

## Experimental Design

For each task and observation-set replicate, construct four nested observation sets:

\[
O_1 \subset O_2 \subset O_3 \subset O_4
\]

with the following default evidence budgets:

| System | Development cases per task | Interpretation |
| --- | ---: | --- |
| \(S_1\) | 1 | Extremely sparse evidence |
| \(S_2\) | 3 | Low evidence coverage |
| \(S_3\) | 10 | Moderate evidence coverage |
| \(S_4\) | 30 | High evidence coverage |
| \(S^*\) | Disjoint reference-only pool | Privileged reference measurement |

Use five deterministic observation-set replicates by default:

```text
r1, r2, r3, r4, r5
```

All four optimization-visible systems must use the same:

- HumanEval task specification;
- candidate source and entry point;
- isolated execution backend and process semantics;
- expected-output oracle semantics;
- output-comparison rules;
- execution limits;
- all-cases-must-pass task scoring rule;
- optimizer-visible feedback schema;
- logging policy; and
- deterministic execution procedure.

Only the number and coverage of development cases may differ.

## Measurement Architecture

For every optimization-visible system:

- \(C\): functional correctness relative to the HumanEval task specification;
- \(O_k\): the system-specific nested subset of frozen development evidence;
- \(M\): binary task acceptance if and only if every selected case passes; and
- \(P\): deterministic isolated candidate execution using the same frozen process across robustness levels.

The accepted-solution sets must be monotonic:

\[
\mathcal{A}(S_1)
\supseteq
\mathcal{A}(S_2)
\supseteq
\mathcal{A}(S_3)
\supseteq
\mathcal{A}(S_4).
\]

For a fixed candidate, task, and replicate, passing \(S_{k+1}\) must imply passing \(S_k\).

## Approved Execution-Efficiency Amendment

Evaluating each system independently, with a new container for every case, would make the full candidate matrix unnecessarily expensive and could render the experiment infeasible.

MEGB-04 therefore introduces a separately versioned batched task-evaluation process subject to strict equivalence requirements:

1. For one candidate, task, and observation replicate, evaluate the union \(O_4\) once.
2. Derive \(S_1\), \(S_2\), \(S_3\), and \(S_4\) from the cached per-case outcomes because the sets are nested.
3. Do not execute the same candidate/case/process tuple repeatedly when a valid content-addressed result already exists.
4. Prevent writable candidate state from carrying between cases.
5. Do not preload or disclose future inputs to candidate code.
6. Keep expected outputs and comparison logic on the trusted side.
7. Demonstrate task-level classification equivalence to the MEGB-02 high-assurance per-invocation path on the complete validation corpus.
8. Treat the batched path as a distinct, frozen measurement-process version. It becomes the common \(P\) for all four systems only after equivalence and adversarial isolation tests pass.

The accepted primary execution profile must evaluate and preserve a valid outcome for every visible case in \(O_4\). It must not short-circuit after the first candidate failure. Complete visible-case outcomes are required for reproducible nested derivation, empirical validation, and the separately versioned adaptive feedback extension described below. This does not expose case-level information to the optimizer.

If equivalence or isolation cannot be demonstrated, stop and revise the execution design or experimental scale. Do not silently trade away the measurement boundary for speed.

## Reserved Adaptive-Feedback Extension Contract

MEGB-04's primary system family uses the binary optimizer-visible feedback profile:

    scalar-binary-v1

MEGB-08 may add the separately versioned profile:

    aggregate-case-score-v1

Changing feedback richness creates a new adaptive system-family identity. It must not mutate, overwrite, or retroactively relabel the MEGB-06 family, manifests, measurements, or results.

The adaptive family may reuse the same frozen:

- primary task population;
- development partition;
- observation manifests;
- expected-output oracle semantics;
- comparison profile;
- complete-case execution evidence;
- all-cases-must-pass binary task score; and
- isolation boundary.

It must use distinct feedback-profile and system-family versions. Its authorized projection may derive an aggregate visible-case fraction only from complete valid visible-case outcomes. MEGB-08 owns the exact adaptive schema, rounding, coarse-failure collapse, and trajectory behavior; MEGB-04 owns the invariant that the underlying evidence and binary \(q_{\mathrm{meas}}\) remain unchanged.

Adaptive system references must be unambiguous by identity or required family context. A bare `S1-r1` identifier must never silently resolve to different feedback behavior in different callers.

## Epic Dependencies

- `[MEGB-01] Establish HumanEval Corpus and Privileged Evaluation Boundary`
- `[MEGB-02] Implement Isolated Candidate Execution Worker`
- `[MEGB-03] Implement Privileged Reference Evaluator S*`
- Specifically, MEGB-03B's frozen partition and the accepted MEGB-03 oracle/comparison artifacts.

## Global Architectural Constraints

### Controlled-variable discipline

Across \(S_1 \dots S_4\), only the selected development evidence may differ. Any change to comparison rules, scoring, execution limits, feedback, logging, or candidate treatment creates a new system family and cannot be pooled with the primary experiment.

### Trusted-side comparison

Candidate code receives authorized inputs but never expected outputs, comparison logic, future inputs, observation manifests, or privileged diagnostic artifacts. Candidate code never executes in the trusted controller process.

### Isolation from \(S^*\)

Enforce the dependency direction:

```text
shared corpus, nonprivileged schemas, comparison semantics, and execution interfaces
        ├── trusted development-oracle adapter → optimization-visible measurement systems
        └── privileged reference-only adapter → privileged reference evaluator
```

The optimization-visible branch must not import or depend on the privileged reference branch.

Its package and runtime must not contain:

- reference-only manifests or inputs;
- reference expected outputs;
- privileged reference result artifacts;
- credentials or capabilities that invoke \(S^*\); or
- prior \(S^*\) results.

### Candidate failure versus invalid measurement

Wrong outputs and candidate execution failures are valid zero measurements. Oracle, infrastructure, protocol, manifest, or controller failures are invalid measurements with `q_meas_task = None` and must prevent final aggregation.

### Frozen experimental definitions

The system family, observation manifests, comparison profile, execution profile, feedback profile, validation corpus, validation results, and code revision must be frozen before experimental optimization begins.

## Epic Execution Protocol

Work through MEGB-04A through MEGB-04G sequentially.

For each authorized subtask:

1. Read the epic objective, amendments, global constraints, and current subtask.
2. Inspect the implementation and artifacts produced by completed dependencies.
3. Present a short implementation plan before modifying code.
4. Implement only the current subtask.
5. Run the required tests and relevant regressions.
6. Update only the current subtask's status and completion record.
7. Produce the standard checkpoint report.
8. Stop and wait for explicit authorization.

Do not begin later subtasks early. If unavoidable overlap is discovered, identify it and obtain approval before proceeding. Each completed subtask should correspond to a separate commit. Requirement changes require an explicit, versioned amendment.

## Standard Checkpoint Report

At the end of every subtask, report:

1. **Summary:** what was implemented or decided.
2. **Files changed:** created, modified, deleted, and intentionally untracked files.
3. **Tests:** exact commands, results, skips, and environment details.
4. **Acceptance matrix:** every criterion marked `PASS`, `FAIL`, `BLOCKED`, or `DEFERRED` with evidence.
5. **Design decisions:** choices constraining later work.
6. **Deviations:** differences from this specification.
7. **Known limitations:** unresolved engineering or scientific issues.
8. **Handoff artifacts:** paths, versions, identifiers, and checksums.
9. **Repository state:** branch, exact commit SHA(s), proposed commit contents, and remote/push state.
10. **Protected-data statement:** development-oracle access, reference-oracle access, and evidence that no privileged content crossed the optimizer/candidate boundary.
11. **Cost and external activity:** Docker/runtime cost, external calls if any, and confirmation when none occurred.
12. **Next-step readiness:** whether the next subtask's prerequisites are satisfied and the exact authorization required.

After reporting, stop. Do not begin the next subtask.

## Subtask Status

- [ ] MEGB-04A — Validate the frozen partition and generate observation manifests
- [ ] MEGB-04B — Implement the immutable system registry and configuration
- [ ] MEGB-04C — Implement and validate efficient batched case execution
- [ ] MEGB-04D — Implement task evaluation, scoring, and result models
- [ ] MEGB-04E — Implement feedback, aggregation, and reference isolation
- [ ] MEGB-04F — Validate empirical robustness and monotonicity
- [ ] MEGB-04G — Freeze, document, integrate CI, and complete acceptance

---

## MEGB-04A — Validate the Frozen Partition and Generate Observation Manifests

### Status

**Status:** Not started

### Objective

Consume and validate the partition frozen in MEGB-03B, then generate five deterministic families of nested development-only observation sets.

### Dependencies

- MEGB-03B complete and accepted.
- MEGB-03A.1 supplementary evidence accepted for partition eligibility.
- MEGB-03 partition configuration, locks, and feasibility report available.
- `primary_experiment_task_manifest` and `reference_validation_task_manifest` reproduce from clean processes.

### Requirements

1. Load—not recreate—the frozen MEGB-03 partition manifest.
2. Verify:
   - dataset version and checksum;
   - partition version, algorithm, seed, and checksum;
   - exactly the frozen primary-experiment task count, expected 163;
   - exactly 164 tasks in the separate reference-validation manifest;
   - HumanEval/39 absent from the primary manifest and present only in reference validation;
   - stable and unique case IDs within each task;
   - exhaustive assignment of eligible cases;
   - zero overlap between development and reference-only pools;
   - exactly 40 development cases for every primary task;
   - at least 30 reference-only cases for every primary task;
   - original-versus-supplementary evidence provenance for HumanEval/6, HumanEval/55, and HumanEval/63; and
   - accepted augmentation checksums for those three tasks.
3. Refuse execution when the partition is absent, mutable, corrupt, incompatible, or insufficient.
4. Reject HumanEval/39, every task outside `primary_experiment_task_manifest`, and any attempt to substitute the 164-task validation manifest for the experimental manifest.
5. Generate five default replicate families using frozen seeds `r1` through `r5`.
6. For each task and replicate, deterministically rank the development pool using a documented stable SHA-256 procedure incorporating:
   - observation-selection algorithm version;
   - replicate seed;
   - task ID; and
   - stable case ID.
7. Assign the ranked prefixes:
   - first 1 case to \(O_1\);
   - first 3 cases to \(O_2\);
   - first 10 cases to \(O_3\); and
   - first 30 cases to \(O_4\).
8. Require strict nesting within every task and replicate.
9. Confirm that the approved development-pool design allows meaningful replicate variation at `O4`; report duplicate `O4` sets across replicates and block release if the approved design requires distinct sets but does not produce them.
10. Each manifest must record:
   - system ID and robustness level;
   - replicate ID;
   - task ID;
   - ordered case IDs;
   - case count;
   - primary-task-manifest ID and checksum;
   - development-pool and partition checksums;
   - selection algorithm and version;
   - replicate seed; and
   - manifest checksum.
11. Observation manifests contain case identifiers only. They must not contain inputs, expected outputs, comparison values, or reference-only identifiers.
12. Repeated construction from identical inputs must be byte-for-byte deterministic where the format permits.

### Acceptance Criteria

- The consumed partition passes every integrity and disjointness check.
- Every primary task has exactly 40 development cases and at least 30 reference-only cases.
- Exactly five replicate families and 20 system/replicate definitions are generated by default.
- For every task in the frozen 163-task primary manifest and all five replicates, lengths are exactly 1, 3, 10, and 30.
- HumanEval/39 and every out-of-manifest task are absent.
- `O1 ⊂ O2 ⊂ O3 ⊂ O4` for every task and replicate.
- No observation set contains a reference-only case.
- Manifest checksums are stable across repeated generation.
- Replicate variation satisfies the approved feasibility policy.
- No expected output or raw case evidence appears in an observation manifest.

### Required Tests

- Partition integrity, uniqueness, exhaustive assignment, and disjointness tests.
- Partition version/checksum mismatch refusal.
- Exact 40-development/30-reference-minimum and accepted-augmentation checksum tests.
- Primary-versus-validation manifest boundary and HumanEval/39 rejection tests.
- Observation-set size and strict-nesting tests over all tasks/replicates.
- Reference-only exclusion tests.
- Cross-machine-stable ordering/checksum test using fixed fixtures.
- Changed seed/version changes checksum.
- Insufficient development evidence failure.
- Duplicate-replicate detection.
- Manifest redaction tests.

### Non-Goals

- Constructing or modifying the development/reference partition.
- Implementing evaluators or scoring.
- Loading expected outputs into optimizer-visible artifacts.
- Selecting budgets using experimental model outputs.

### Handoff Artifacts

- Five replicated nested observation-manifest families.
- Partition-consumption validation report.
- Observation-selection algorithm specification.
- Manifest checksums and replicate-variation report.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-04B requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-04B — Implement the Immutable System Registry and Configuration

### Status

**Status:** Not started

### Objective

Implement immutable, versioned definitions for resolving every optimization-visible measurement system and its shared controlled variables.

### Dependencies

- MEGB-04A complete and accepted.

### Requirements

1. Implement a registry resolving identifiers `S1-r1` through `S4-r5`.
2. Define an immutable schema similar to:

   ```python
   @dataclass(frozen=True)
   class MeasurementSystemDefinition:
       system_id: str
       system_version: str
       system_family: str
       robustness_level: int
       replicate_id: str
       evidence_budget: int
       task_manifest_checksum: str
       observation_manifest_checksum: str
       partition_manifest_checksum: str
       development_oracle_checksum: str
       comparison_profile_id: str
       execution_profile_id: str
       feedback_profile_id: str
   ```

3. Bind each definition to one frozen observation manifest and the common:
   - primary-experiment task manifest;
   - trusted development-oracle artifact;
   - construct profile;
   - comparison profile;
   - execution profile;
   - feedback profile;
   - task-scoring policy;
   - aggregation policy; and
   - expected task count.
4. Validate that only evidence budget and selected case IDs vary across robustness levels within a replicate.
5. Reject unknown, duplicate, mutable, or checksum-inconsistent definitions.
6. Reject HumanEval/39, tasks outside the primary manifest, unauthorized oracle consumers, reference-only oracle artifacts, and task/case/oracle provenance mismatches.
7. Require a new system or family version for changes to evidence, comparison rules, scoring, execution, limits, feedback, logging, or aggregation.
8. Create a frozen configuration similar to:

   ```yaml
   system_family: megb-observation-coverage-v1
   construct_profile: humaneval-functional-correctness-v1
   task_manifest_id: primary_experiment_task_manifest
   task_manifest_checksum: pinned-primary-task-manifest-checksum
   partition_manifest_checksum: pinned-partition-checksum
   development_oracle_checksum: pinned-development-oracle-checksum
   comparison_profile: evalplus-compatible-v1
   execution_profile: optimization-visible-batched-v1
   feedback_profile: scalar-binary-v1
   task_scoring: all_cases_pass
   benchmark_aggregation: unweighted_task_mean
   expected_task_count: 163
   robustness_levels:
     S1: 1
     S2: 3
     S3: 10
     S4: 30
   replicates: [r1, r2, r3, r4, r5]
   ```
9. Do not freeze the final execution-profile value until MEGB-04C has passed equivalence validation; allow an explicit pre-freeze state rather than silently substituting a profile.

### Acceptance Criteria

- Exactly 20 default definitions resolve to the expected immutable metadata.
- All definitions consume frozen MEGB-04A manifests.
- Controlled-variable validation proves that only observation coverage differs.
- Invalid identities, versions, checksums, or cross-profile combinations are rejected.
- Configuration changes affecting outcomes require a new version.
- Pre-freeze configuration cannot be used for experimental optimization.

### Required Tests

- Registry resolution for all 20 definitions.
- Duplicate/unknown identifier rejection.
- Manifest and partition checksum validation.
- Cross-system controlled-variable equivalence tests.
- Mutation and freeze-state tests.
- Configuration round-trip and version tests.

### Non-Goals

- Candidate execution.
- Task scoring.
- Final system-family freeze.

### Handoff Artifacts

- Immutable system-definition models and registry.
- Pre-freeze system-family configuration.
- Controlled-variable validation report.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-04C requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-04C — Implement and Validate Efficient Batched Case Execution

### Status

**Status:** Not started

### Objective

Implement a task-evaluation process that evaluates the 30-case `O4` union once per candidate/task/replicate and safely reuses its per-case outcomes to derive every nested robustness result.

### Dependencies

- MEGB-04B complete and accepted.
- MEGB-02 high-assurance execution backend available as the equivalence reference.

### Requirements

1. Define a separately versioned batch/task-execution interface rather than changing MEGB-02's accepted per-invocation contract silently.
2. For one candidate, task, and replicate:
   - resolve `O4` as the union required for `S1–S4`;
   - execute each unique case at most once for a valid result;
   - retain case outcomes by stable case ID; and
   - derive smaller-system outcomes from the nested prefixes without re-execution.
3. Preserve the trusted-side comparison boundary. Expected outputs and comparison rules never enter candidate code.
4. Do not expose the observation manifest, future inputs, or the complete input collection to candidate code.
5. Present only the current authorized case to each candidate subprocess.
6. Reset candidate runtime state between cases, including:
   - Python process state;
   - imported candidate modules;
   - environment mutations;
   - current working directory and writable temporary state;
   - open file descriptors;
   - child/descendant processes; and
   - captured output buffers.
7. Ensure candidate code cannot inspect or interfere with the trusted batch supervisor, its protocol channel, future inputs, or prior outputs.
8. Bound CPU, memory, process count, writable storage, wall time, and output for every case and for the containing task evaluation.
9. Map individual candidate failures to structured per-case outcomes without terminating unrelated remaining cases.
10. Evaluate all 30 authorized \(O_4\) cases for every valid task evaluation. Short-circuiting after a candidate failure is prohibited in the accepted profile.
11. Use content-addressed caching keyed by candidate hash, task ID, case ID, primary-task-manifest checksum, development-oracle checksum, comparison profile, execution profile, evaluator version, protocol version, and relevant artifact checksums.
12. Never reuse invalid infrastructure/protocol results as valid cached measurements.
13. Compare batched classifications against fresh MEGB-02 per-invocation classifications on:
    - all corrected canonical solutions;
    - the known-incorrect validation corpus;
    - mutation-sensitive and stateful candidates;
    - candidates that spawn descendants;
    - timeout, OOM, process-limit, and output-flood candidates; and
    - protocol/FD interference candidates.
14. Require identical task classifications and authorized feedback between processes.
15. Measure and report execution-count, runtime, and resource reduction relative to independent per-system/per-case execution.
16. Do not select the batched profile as the common \(P\) until equivalence and isolation tests pass.

### Acceptance Criteria

- One candidate/task/replicate requires no more than one valid execution per unique `O4` case.
- `S1–S4` outcomes can be reproduced from cached nested-prefix case results.
- Every valid task evaluation contains a complete 30-case `O4` outcome vector in trusted storage.
- Candidate state cannot carry between cases.
- Candidate code cannot observe future cases, expected outputs, manifests, or supervisor state.
- Descendant processes and writable state are removed between cases and after completion.
- Batched and MEGB-02 high-assurance classifications match on the complete validation corpus.
- Candidate and infrastructure failures retain the correct semantics.
- The execution profile is versioned and its efficiency gain is quantified.

### Required Tests

- Nested-union execution-count tests.
- Complete-case/no-short-circuit tests for wrong output and every candidate-failure category.
- Cache-key and invalid-cache exclusion tests.
- Fresh-process equivalence tests.
- Stateful/global-variable and filesystem carryover attacks.
- Future-input and manifest exfiltration attempts.
- Supervisor/protocol/FD interference attacks.
- Child-process cleanup tests.
- Timeout, OOM, process, storage, and output-limit tests.
- Canonical and known-incorrect corpus equivalence.
- Cross-platform determinism checks where supported.
- Performance benchmark with a reproducible baseline.

### Non-Goals

- Changing scoring or feedback.
- Increasing the evidence budgets.
- Weakening MEGB-02's host/container boundary.
- Freezing the complete system family.

### Handoff Artifacts

- Versioned batched task-execution implementation.
- Content-addressed case-result cache.
- High-assurance equivalence report.
- Adversarial isolation report.
- Performance and execution-count report.
- Accepted execution-profile identifier.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. If equivalence or isolation fails, MEGB-04D is blocked. Otherwise MEGB-04D requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-04D — Implement Task Evaluation, Scoring, and Result Models

### Status

**Status:** Not started

### Objective

Implement task-level evaluation for any registered system using the accepted common execution profile, trusted comparison logic, binary all-cases-pass scoring, and typed results.

### Dependencies

- MEGB-04C complete and accepted.

### Requirements

1. Implement an interface similar to:

   ```python
   def evaluate_measurement_system(
       system_id: str,
       task_id: str,
       candidate_code: str,
       context: MeasurementEvaluationContext,
   ) -> MeasurementTaskResult:
       ...
   ```

2. The evaluator must:
   1. resolve the immutable system definition;
   2. verify the candidate identity and hash;
   3. load the authorized development case IDs;
   4. verify the primary-task, partition, observation, and development-oracle checksums;
   5. load expected outputs only through the authorized development-only adapter and keep them on the trusted side;
   6. execute candidate cases through the accepted MEGB execution profile;
   7. apply the shared comparison profile;
   8. calculate the task measurement; and
   9. write privileged diagnostics and an authorized projection.
3. Define a typed immutable result containing at least:

   ```python
   @dataclass(frozen=True)
   class MeasurementTaskResult:
       schema_version: str
       evaluator_version: str
       system_id: str
       system_version: str
       system_family: str
       robustness_level: int
       replicate_id: str
       task_id: str
       candidate_id: str
       candidate_sha256: str
       measurement_status: str
       q_meas_task: float | None
       cases_total: int
       cases_passed: int
       first_failure_category: str | None
       execution_failure_counts: Mapping[str, int]
       task_manifest_id: str
       task_manifest_checksum: str
       observation_manifest_checksum: str
       partition_manifest_checksum: str
       development_oracle_checksum: str
       oracle_version: str
       comparison_profile_id: str
       execution_profile_id: str
       protocol_version: str
       feedback_profile_id: str
       started_at: str
       duration_seconds: float
   ```
4. Use the same task measurement model for all systems:

   \[
   q_{\mathrm{meas},i}^{(k)} =
   \begin{cases}
   1, & \text{if every case in } O_k \text{ passes} \\
   0, & \text{if any case in } O_k \text{validly fails.}
   \end{cases}
   \]

5. Case-level pass fractions are privileged diagnostics, not the primary score.
6. Candidate failures produce `measurement_status = VALID` and `q_meas_task = 0.0`.
7. Use a frozen validity taxonomy aligned with the accepted MEGB result semantics:
   - `VALID` for a valid pass or candidate failure;
   - `INCOMPLETE` when a required result is absent and the frozen recovery policy has not produced a complete task measurement;
   - `INVALID_ORACLE` for missing, ambiguous, corrupt, or inconsistent development expected outputs;
   - `INVALID_PROTOCOL` for request/response or serialization defects; and
   - `INVALID_INFRASTRUCTURE` for controller, sandbox, container, or host failures.
8. Reject task, observation, partition, freeze, candidate-hash, version, and checksum mismatches before execution rather than emitting a scientific measurement result for the wrong context.
9. Every non-`VALID` status produces `q_meas_task = None`.
10. Exhaustively map every accepted MEGB-02 execution status. Unknown statuses fail closed as invalid apparatus measurements rather than defaulting to candidate failures.
11. Candidate execution statuses representing syntax errors, candidate exceptions, timeouts, out-of-memory, process limits, and output limits are valid candidate failures. MEGB-02 protocol and infrastructure statuses map to the corresponding invalid measurement status.
12. Measurement-system failures must never become candidate failures.
13. Derive results for nested systems from the same complete accepted per-case evidence.
14. Validate that passing `S4` implies passing `S3`, passing `S3` implies passing `S2`, and passing `S2` implies passing `S1` for every fixed candidate/task/replicate.
15. Candidate code never executes in the trusted controller process.

### Acceptance Criteria

- Every registered system can evaluate a frozen candidate/task pair.
- Candidate hash, system version, and manifest checksums are verified.
- Development-oracle identity and authorized-consumer context are verified.
- All four systems use identical scoring and comparison semantics.
- Valid candidate failures produce zero; invalid measurements produce `None`.
- Task results are typed, immutable, and serializable.
- Nested-system results are monotonic by construction and verification.
- Privileged case diagnostics are separate from authorized outputs.

### Required Tests

- Correct and incorrect candidate scoring.
- Each MEGB-02 candidate-failure category.
- Exhaustive execution-status mapping and unknown-status failure.
- Injected oracle, execution, manifest, and protocol failures.
- Result schema and serialization.
- Candidate-hash and version mismatch refusal.
- Nested-prefix derivation.
- Exhaustive monotonicity property tests over synthetic case vectors.
- Trusted-side comparison and candidate-boundary tests.
- Development-only oracle loading, mixed-provenance rejection, and reference-oracle access prohibition.

### Non-Goals

- Benchmark aggregation.
- Final optimizer-visible feedback API.
- Empirical robustness validation.

### Handoff Artifacts

- Optimization-visible task evaluator.
- Measurement evaluation context and task-result schemas.
- Privileged per-case/task diagnostics.
- Task-level scoring and monotonicity tests.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-04E requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-04E — Implement Feedback, Aggregation, and Reference Isolation

### Status

**Status:** Not started

### Objective

Implement the common optimizer-visible scalar feedback projection, complete primary-manifest aggregation, and enforce architectural and runtime isolation from \(S^*\).

### Dependencies

- MEGB-04D complete and accepted.

### Requirements

1. Define one versioned feedback projection shared by all systems. The default projection exposes only authorized fields equivalent to:

   ```json
   {
     "system_id": "S2-r3",
     "task_id": "HumanEval/0",
     "feedback_profile": "scalar-binary-v1",
     "measurement_status": "VALID",
     "q_meas": 0.0
   }
   ```
2. Do not expose:
   - selected inputs;
   - expected outputs;
   - failing case IDs;
   - case-level pass vectors;
   - exception traces containing evidence;
   - canonical outputs;
   - development/reference partition details;
   - reference-only information;
   - \(S^*\) results; or
   - privileged diagnostic counts outside the approved schema.
3. Bind this projection to `scalar-binary-v1`. The separately versioned MEGB-08 `aggregate-case-score-v1` projection requires a distinct adaptive system-family identifier under the Reserved Adaptive-Feedback Extension Contract. Do not vary feedback silently or mutate historical MEGB-06 identities.
4. Implement unweighted aggregation:

   \[
   Q_{\mathrm{meas}}^{(k)} =
   \frac{1}{T_{\mathrm{primary}}}
   \sum_{i\in\mathcal{T}_{\mathrm{primary}}}
   q_{\mathrm{meas},i}^{(k)},
   \]

   where \(\mathcal{T}_{\mathrm{primary}}\) is the exact frozen `primary_experiment_task_manifest` and \(T_{\mathrm{primary}}=163\) for the accepted MEGB-03A.1 manifest.

5. Do not weight tasks by case count.
6. Preserve the exact frozen primary-manifest denominator. Never infer membership from available result rows.
7. Emit a final system score only when every required primary-manifest task measurement is present, unique, context-consistent, and valid. Otherwise mark the benchmark result `INCOMPLETE` or `INVALID` without shrinking the denominator.
8. Reject HumanEval/39, extra tasks, duplicate tasks, substituted tasks, primary-manifest checksum mismatches, and attempts to aggregate the 164-task reference-validation population.
9. Enforce static dependency isolation: optimizer-facing client, feedback, generation, and selection packages cannot import the trusted development-oracle loader, privileged reference evaluator, or privileged storage adapters. The trusted MEGB-04 controller may import only the development-only loader through its approved interface.
10. Enforce runtime isolation: the optimizer environment cannot read or invoke:
   - reference-only manifests or inputs;
   - reference expected outputs;
   - reference result artifacts;
   - canonical solutions; or
   - credentials/capabilities for \(S^*\).
11. Shared schemas and interfaces must not contain optional privileged fields that can accidentally be populated across the boundary.
12. Log privileged diagnostics separately from optimizer-visible feedback.

### Acceptance Criteria

- All 20 systems expose the same schema and feedback-profile version.
- Differences across systems are limited to identity and the resulting scalar measurement.
- No unauthorized evidence survives projection, serialization, logs, or errors.
- Complete valid task sets aggregate to the correct unweighted mean.
- Missing or invalid tasks prevent final aggregation without changing the denominator.
- HumanEval/39, extra tasks, and the reference-validation manifest are rejected from MEGB-04 aggregation.
- Optimizer-facing code cannot import trusted oracle loaders or access or invoke \(S^*\); the trusted controller can resolve only the authorized development oracle.
- Runtime artifacts contain no reference-only data or credentials.

### Required Tests

- Feedback schema equivalence across all systems.
- Redaction and serialization leakage tests.
- Exception/error-message leakage tests.
- Complete aggregation and denominator preservation.
- Missing, duplicate, substituted, extra, HumanEval/39, invalid, and incomplete task cases.
- Task-level `q_meas` versus benchmark-level `Q_meas` schema tests.
- Static forbidden-import/dependency tests.
- Runtime attempts to read reference manifests, expected outputs, result artifacts, and credentials.
- Attempted \(S^*\) invocation from the optimizer runtime.

### Non-Goals

- Rich adaptive feedback for MEGB-08.
- Empirical FAR analysis.
- Candidate generation or selection.

### Handoff Artifacts

- Versioned scalar feedback projection.
- Benchmark-level result and aggregator.
- Reference-isolation policy and tests.
- Privileged versus optimizer-visible output writers.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-04F requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-04F — Validate Empirical Robustness and Monotonicity

### Status

**Status:** Not started

### Objective

Build or consume a fixed nonexperimental validation corpus and establish before experimental optimization that the configured systems are valid, monotonic, and meaningfully separated in false-acceptance behavior.

### Dependencies

- MEGB-04E complete and accepted.
- Accepted MEGB-03 privileged reference evaluator.

### Requirements

1. Build or import a frozen validation corpus containing:
   - corrected canonical solutions;
   - known incorrect model-generated solutions;
   - HumanEval-base-pass/HumanEval+-fail solutions;
   - hardcoded solutions;
   - boundary-condition failures;
   - type-handling failures;
   - numerical failures;
   - mutation-generated candidates; and
   - resource-exhausting candidates.
2. Every validation candidate must have a privileged primary reference classification from \(S^*\).
3. Do not use confirmatory experimental model outputs to tune system definitions.
4. Run all corrected canonical solutions against every system and replicate.
5. Require, for every system replicate:

   ```text
   163 / 163 valid primary-manifest canonical measurements
   Q_meas = 1.0
   ```
   Bind the exact primary-manifest checksum in the validation result. HumanEval/39 has no MEGB-04 canonical measurement.
6. For every validation candidate and replicate, verify:

   ```text
   pass(S4) implies pass(S3)
   pass(S3) implies pass(S2)
   pass(S2) implies pass(S1)
   ```
7. For reference-incorrect candidates, calculate:

   \[
   \operatorname{FAR}(S_k) =
   P\left(q_{\mathrm{meas}}^{(k)}=1 \mid q_{\mathrm{ref}}=0\right).
   \]

8. Also report:
   - reference-incorrect candidates evaluated;
   - number accepted at each robustness level;
   - false-rejection rate on corrected canonical solutions;
   - pairwise acceptance-set differences;
   - replicate mean and variance;
   - per-task coverage where appropriate; and
   - monotonicity violations.
9. Require non-increasing false-acceptance rates:

   \[
   \operatorname{FAR}(S_1)
   \ge \operatorname{FAR}(S_2)
   \ge \operatorname{FAR}(S_3)
   \ge \operatorname{FAR}(S_4).
   \]

10. Require at least one adjacent system pair to show a nonzero reduction in accepted reference-incorrect candidates.
11. If systems do not separate empirically, stop and revise evidence budgets or validation design before candidate generation. Any revision requires a new system-family version and complete rerun.
12. Do not inspect confirmatory experimental \(Q_{\mathrm{ref}}\) outcomes.

### Acceptance Criteria

- The validation corpus is fixed, versioned, checksummed, and nonexperimental.
- All corrected canonical solutions pass all 20 system/replicate definitions.
- Canonical coverage is exactly the frozen primary manifest; HumanEval/39 and out-of-manifest tasks are absent.
- Zero monotonicity violations occur.
- FAR is non-increasing with evidence coverage.
- At least one adjacent robustness pair shows nonzero empirical separation.
- Replicate mean, variance, and acceptance-set differences are reported.
- Validation results are reproducible from frozen artifacts and commands.

### Required Tests

- Full canonical matrix tests.
- Primary-task-manifest coverage, checksum, and HumanEval/39 exclusion tests.
- Monotonicity tests over every corpus candidate and replicate.
- FAR and false-rejection calculations.
- Acceptance-set difference calculations.
- Replicate summary tests.
- Synthetic analysis tests with known expected outcomes.
- Validation-corpus and result checksum tests.
- Failure gate when robustness separation is absent.

### Non-Goals

- Estimating the final optimization-pressure effect.
- Calculating gaming deltas on confirmatory candidates.
- Tuning against confirmatory reference outcomes.
- Inferring intentional exploitation.

### Handoff Artifacts

- Frozen robustness-validation corpus.
- Privileged reference classifications.
- Validation measurement matrix.
- FAR, false-rejection, monotonicity, and replicate analysis.
- Robustness-validation report and checksums.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. If robustness separation fails, MEGB-04G is blocked pending an approved amendment. Otherwise MEGB-04G requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-04G — Freeze, Document, Integrate CI, and Complete Acceptance

### Status

**Status:** Not started

### Objective

Freeze the validated system family, document its measurement design and limitations, integrate its verification into CI, and produce final evidence that every MEGB-04 criterion is satisfied.

### Dependencies

- MEGB-04F complete and accepted.

### Requirements

1. Finalize the system-family configuration using the accepted MEGB-04C execution profile.
2. Create a signed or checksummed freeze manifest containing:
   - dataset version and checksum;
   - primary-experiment task-manifest ID, expected count, and checksum;
   - separate reference-validation task-manifest ID, count, and checksum as an upstream validation record;
   - development/reference partition version and checksum;
   - development-oracle artifact ID, schema/version, authorized-consumer identity, and checksum;
   - observation-set manifest checksums;
   - system definitions and versions;
   - replicate seeds;
   - comparison profile;
   - execution profile;
   - feedback profile;
   - scoring and aggregation profiles;
   - validation-corpus checksum;
   - validation-results checksum;
   - code revision; and
   - freeze timestamp.
3. Require every optimization run to reference the freeze manifest.
4. Any outcome-affecting change requires a new system-family version, new freeze manifest, and complete validation rerun.
5. Create:
   - `docs/measurement/optimization-visible-systems.md`; and
   - `docs/measurement/observation-coverage-validation.md`.
6. Document:
   - the controlled-variable design;
   - why only \(O\) changes;
   - evidence budgets;
   - consumption of the MEGB-03 partition;
   - replicate construction and variation;
   - nesting guarantees;
   - shared scoring and aggregation;
   - optimizer-visible feedback;
   - the reserved separately versioned adaptive-feedback extension contract;
   - batched execution and equivalence evidence;
   - empirical robustness validation;
   - freeze and amendment procedure;
   - known limitations; and
   - threats to validity.
7. Integrate unit, manifest, registry, scoring, feedback, isolation, and synthetic analysis tests into ordinary CI.
8. Place expensive full canonical/validation-matrix and batched-equivalence checks in an explicit integration or scheduled workflow where appropriate.
9. CI must not silently claim validation when required Docker, privileged artifacts, or integration inputs are unavailable.
10. Produce a final acceptance matrix mapping every epic criterion to implementation, tests, evidence, and limitations.

### Final Acceptance Criteria

- Four optimization-visible systems are implemented at budgets 1, 3, 10, and 30.
- Exactly five deterministic observation-set replicates are produced by default.
- Observation sets are strictly nested within every task and replicate.
- MEGB-04 consumes the frozen MEGB-03 partition; development and reference-only evidence remain disjoint and checksummed.
- MEGB-04 consumes exactly the frozen 163-task primary manifest and excludes HumanEval/39; the 164-task validation population remains separate.
- Expected outputs come only from the authorized frozen development oracle; reference-only and validation oracles remain inaccessible.
- \(C\), \(M\), and \(P\) are identical across robustness levels.
- The accepted execution process matches MEGB-02 high-assurance task classifications on the complete validation corpus.
- Per-case outcomes are safely reused to derive nested systems without exposing future inputs or carrying candidate state.
- All corrected canonical solutions pass every system and replicate.
- Candidate acceptance is monotonic across nested systems.
- FAR on the fixed reference-incorrect corpus is non-increasing with evidence coverage.
- At least one adjacent robustness pair shows nonzero empirical separation.
- Every system uses the same versioned optimizer-feedback projection.
- Optimizer-visible outputs contain no selected cases, expected outputs, failure vectors, privileged diagnostics, or reference evidence.
- Optimization-visible code and runtime cannot access or invoke \(S^*\).
- System scores use an unweighted mean across exactly the frozen primary-manifest task population, expected 163.
- Missing or invalid task measurements never silently alter the denominator.
- All manifests, configurations, validation results, process profiles, and code revisions are frozen before experimental optimization.
- The complete system family and validation analysis are reproducible from recorded commands and checksums.

### Required Final Verification

- Partition-consumption and disjointness tests.
- Complete observation-manifest tests over the frozen 163-task primary population and five replicates.
- Separate 164-task reference-validation manifest verification and boundary tests.
- HumanEval/39 and out-of-primary-manifest rejection tests.
- Development-oracle authorization, checksum, provenance, and reference-oracle isolation tests.
- Registry and controlled-variable equivalence tests.
- Batched/high-assurance execution equivalence and adversarial isolation suites.
- Full canonical-solution matrix.
- Full validation-corpus monotonicity and FAR analysis.
- Feedback equivalence and leakage tests.
- Static and runtime reference-isolation tests.
- Invalid-measurement and denominator-preservation tests.
- Configuration, freeze-manifest, version, and checksum tests.
- Type checking and linting.
- CI execution evidence.

### Non-Goals

- Candidate generation.
- Optimization-pressure selection.
- Running the confirmatory TR-04 experiment.
- Adaptive feedback.
- Gaming-delta or intentionality analysis.

### Handoff Artifacts

- Five replicated nested observation-manifest families.
- Immutable measurement-system registry.
- Accepted batched task-execution profile and equivalence evidence.
- Optimization-visible evaluator implementation.
- Typed task and benchmark results.
- Versioned scalar optimizer-feedback projection.
- Reserved adaptive-feedback extension contract and compatibility tests.
- Configuration files for \(S_1 \dots S_4\).
- Frozen robustness-validation corpus and analysis.
- System-family freeze manifest.
- Unit and integration tests.
- Reference-isolation and feedback-leakage evidence.
- Measurement-design and validation documentation.
- Final acceptance matrix.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. Do not begin MEGB-05 without explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## Epic Non-Goals

MEGB-04 does not:

- generate model candidates;
- implement the optimization-pressure loop;
- vary model capability;
- vary optimization budget;
- calculate gaming deltas;
- classify intentional versus accidental gaming;
- vary the measurement model;
- vary execution stability across robustness levels;
- expose richer diagnostic feedback;
- claim that test count exhausts measurement robustness; or
- run the final TR-04 experiment.

## Threats to Validity That Must Be Documented

At minimum:

- test count is an incomplete proxy for observation quality;
- cases may differ substantially in discriminative power;
- nested subsets create statistical dependence between systems;
- HumanEval+ evidence is publicly available and may appear in model training data;
- deterministic reference partitioning does not create genuinely private evidence;
- replicate subsets are drawn from one benchmark-specific development pool;
- replicate `O4` sets may overlap substantially even when they are not identical;
- the all-cases-must-pass rule may saturate at high coverage;
- robustness ordering on the validation corpus may not generalize to every candidate distribution;
- execution caching or batching may introduce state, order, timing, or process effects despite equivalence testing;
- finite functional tests do not prove correctness;
- results from variation in \(O\) do not automatically generalize to failures in \(C\), \(M\), or \(P\); and
- changing feedback richness in a later experiment changes the measurement system and requires separate identifiers and claims.

## Requirement Traceability

| Original MEGB-04 section | Refactored location |
| --- | --- |
| Objective | Epic Objective |
| Dependencies | Epic Dependencies |
| Approved MEGB-03A.1 population amendment | Approved Pre-Experimental Population Amendment; MEGB-04A/B/E/F/G |
| Required MEGB-03 Precondition | Alignment With Refactored MEGB-03; MEGB-04A |
| Trusted development-oracle consumption | Trusted Development-Oracle Boundary; MEGB-04B/D/G |
| Experimental Design | Experimental Design; MEGB-04A; MEGB-04B |
| Measurement Architecture | Measurement Architecture; Global Constraints; MEGB-04D |
| 1. Development and Reference Partition | MEGB-03A/B; MEGB-04A consumes and validates it |
| 2. Replicated Observation-Set Manifests | MEGB-04A |
| 3. Measurement-System Registry | MEGB-04B |
| 4. Evaluator Interface | MEGB-04D |
| 5. Task Scoring | MEGB-04D |
| 6. Measurement Result Schema | MEGB-04D |
| 7. Optimizer-Visible Feedback | MEGB-04E |
| 8. Benchmark-Level Aggregation | MEGB-04E |
| 9. Isolation From \(S^*\) | Global Constraints; MEGB-04E; MEGB-04G |
| 10. Configuration | MEGB-04B; MEGB-04G |
| 11. Robustness Validation Corpus | MEGB-04F |
| 12. Empirical Robustness Metrics | MEGB-04F |
| 13. Freeze and Audit Procedure | MEGB-04G |
| 14. Documentation | MEGB-04G |
| Partition Tests | MEGB-04A |
| Observation-Set Tests | MEGB-04A |
| Canonical-Solution Tests | MEGB-04F; MEGB-04G |
| Monotonicity Tests | MEGB-04D; MEGB-04F |
| Robustness-Separation Tests | MEGB-04F |
| Feedback-Equivalence Tests | MEGB-04E; MEGB-04G |
| Reference-Isolation Tests | MEGB-04E; MEGB-04G |
| Invalid-Measurement Tests | MEGB-04D; MEGB-04E; MEGB-04G |
| Acceptance Criteria | Distributed across subtask criteria; consolidated in MEGB-04G |
| Non-Goals | Epic and subtask Non-Goals |
| Threats to Validity | Epic threats; MEGB-04G documentation |
| Deliverables | Subtask Handoff Artifacts; MEGB-04G final handoff |
| Execution-efficiency redesign | Approved Execution-Efficiency Amendment; MEGB-04C |
| Adaptive-feedback compatibility | Reserved Adaptive-Feedback Extension Contract; MEGB-04C/E/G |

## Cross-Ticket Integration Notes

- **MEGB-03:** MEGB-04 consumes `primary_experiment_task_manifest`, the frozen partition, and the authorized development oracle. MEGB-03's 164-task reference-validation population and reference-only oracle remain separate.
- **MEGB-05:** candidate generation and selection must bind the MEGB-04 system-family lock, primary-task-manifest checksum, system/replicate identities, and scalar-binary feedback profile. MEGB-05 may not substitute the adaptive family.
- **MEGB-06:** the confirmatory selection-only experiment uses `megb-observation-coverage-v1` with `scalar-binary-v1`, the 163-task primary population, and the frozen five-replicate manifests.
- **MEGB-07:** the private evaluator is independent of MEGB-04 and must not become an optimization-visible feedback source.
- **MEGB-08:** adaptive feedback uses a distinct family/profile identity under the Reserved Adaptive-Feedback Extension Contract. It may derive aggregate visible-case scores only from complete valid per-case outcomes and may not mutate MEGB-06 artifacts.
- **MEGB-09:** every cross-model condition must use the exact same accepted MEGB-04 family, observation manifests, execution profile, and feedback identity appropriate to its selection-only or adaptive track.

## Instructions for Claude

When executing this epic:

1. Treat this file as the sole governing MEGB-04 specification.
2. Work on exactly one explicitly authorized subtask at a time.
3. Restate the current subtask's objective, dependencies, acceptance criteria, and non-goals before implementation.
4. Verify prerequisite locks from clean processes.
5. Bind every experimental artifact to `primary_experiment_task_manifest`; reject HumanEval/39.
6. Never substitute the 164-task reference-validation population for the 163-task experimental population.
7. Load expected outputs only through the authorized trusted development-oracle adapter.
8. Do not access the reference-only oracle, canonical solutions, or \(S^*\).
9. Do not short-circuit accepted \(O_4\) task execution; preserve complete trusted per-case outcomes.
10. Keep `scalar-binary-v1` and the later adaptive feedback family/version separate.
11. Use lowercase \(q\) for task-level values and uppercase \(Q\) for benchmark aggregates.
12. Report exact commands, collected/pass/fail/deselected test counts, commits, checksums, and privileged access.
13. Do not push, begin MEGB-05, or start the next subtask without explicit authorization.
14. End every subtask with the Standard Checkpoint Report and stop.

## Epic Completion Rule

MEGB-04 is complete only when:

1. every subtask MEGB-04A through MEGB-04G is accepted;
2. every completion record identifies its commit and validation evidence;
3. the final acceptance matrix contains no unresolved `FAIL` or unapproved `DEFERRED` item;
4. the system-family freeze manifest binds every outcome-affecting artifact and process version;
5. robustness separation is demonstrated before confirmatory candidate generation; and
6. MEGB-04G produces its checkpoint report and stops before MEGB-05.
