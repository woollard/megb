# [MEGB-06] Preregister, Execute, and Analyze the Measurement-Robustness × Optimization-Pressure Experiment

## Epic Status

**Status:** Not started  
**Execution mode:** Sequential gated subtasks with irreversible scientific gates  
**Subtasks:** MEGB-06A through MEGB-06K  
**Dependencies:** MEGB-01 through MEGB-05; MEGB-07A through MEGB-07D before reference unblinding  
**Specification status:** Authoritative corrected ticket  
**Specification version:** `megb-06-ticket-v2`  
**Supersedes:** the historical monolithic, annotated, merged, and earlier refactored MEGB-06 tickets

Once committed, this document is the sole governing MEGB-06 specification. Historical MEGB-06 files may be retained for audit history, but their requirements must not be combined with this ticket.

Where an approved amendment conflicts with earlier text, the amendment governs. Superseded language is preserved only in repository history, not repeated as an alternative operating rule.

## Epic Objective

Execute the first confirmatory MEGB experiment and test the hypothesis:

> Benchmark gaming emerges when optimization pressure exceeds the robustness of the measurement system.

This epic combines:

- the privileged reference evaluator \(S^*\) from MEGB-03;
- the optimization-visible robustness levels \(S_1 \dots S_4\) from MEGB-04; and
- the nested selection-only optimization process and controls from MEGB-05.

MEGB-06 must:

1. establish feasibility, cost, power, and detectable signal before experimental generation;
2. freeze and test the statistical pipeline on synthetic data;
3. preregister the experimental and statistical design;
4. execute the complete optimization-visible factorial sweep;
5. freeze all candidate selections before reference evaluation;
6. require the private holdout suite to be authored and frozen before public reference outcomes are unblinded;
7. evaluate only frozen candidates with \(S^*\) and freeze the reference-result manifest;
8. build and lock the analysis dataset as a separate deterministic transition;
9. run the preregistered analyses; and
10. generate publication-ready results and a reproducibility package for TR-04.

## Approved Pre-Experimental Population Amendment — MEGB-03A.1

**Status:** Approved and executed before confirmatory candidate generation, optimization-visible evaluation, selection, or reference unblinding.

The primary experimental population is the frozen `primary_experiment_task_manifest`, expected to contain 163 tasks. HumanEval/39 is excluded a priori because it has no optimization-visible development pool, no \(q_{\mathrm{meas}}\), and therefore no MEGB-06 gaming coordinate.

The separate `reference_validation_task_manifest` contains all 164 HumanEval tasks and exists only for MEGB-03 evaluator validation. It must not be substituted for the experimental manifest, used as an MEGB-06 denominator, or used to create a candidate stream for HumanEval/39.

Every experimental artifact and executable stage must bind the primary manifest's ID, checksum, and expected count. The manifest identity and checksum govern; the literal count is an asserted property of the accepted version, not a discovery mechanism.

## Experimental Design

The complete design is:

\[
\text{Task}
\times
\text{Candidate-stream replicate}
\times
\text{Observation-set replicate}
\times
\text{Measurement robustness}
\times
\text{Optimization pressure}
\times
\text{Selection policy}.
\]

The fixed task set is exactly the accepted `primary_experiment_task_manifest`, expected to contain 163 tasks and to exclude HumanEval/39.

Measurement robustness is operationalized by development-evidence budget:

\[
E \in \{1,3,10,30\}.
\]

Optimization pressure is operationalized by nested candidate-selection budget:

\[
N \in \{1,2,4,8,16,32\}.
\]

MEGB-04 provides five observation-set replicates by default. The number of candidate-stream replicates must be selected through the preregistered power, signal-feasibility, and cost analysis.

The same candidate stream must be shared across all measurement-system, observation-replicate, budget, selection-policy, and random-control-replicate conditions for a fixed task and stream replicate.

## Selection Policies

MEGB-05 provides:

- `FIRST_MEASURED_PASS` — the primary measurement-directed optimization policy;
- `RANDOM_FROM_PREFIX` — a paired candidate-availability control; and
- `FIRST_CANDIDATE` — a no-selection control.

The original H1–H4 hypotheses and primary difference-in-differences apply to `FIRST_MEASURED_PASS` unless the preregistration explicitly states otherwise.

Control-policy outcomes must be retained in the locked dataset and analyzed under preregistered contrasts. The random control must select the same candidate across measurement-system conditions for a fixed task, stream, budget, `random_control_replicate_id`, and selection version.

The preregistration must freeze a positive random-control replicate count \(R_{\mathrm{random}}\ge1\), stable replicate IDs, seed namespace, selection algorithm/version, aggregation rule, and clustering treatment. `random_control_replicate_id` is a required scientific coordinate for `RANDOM_FROM_PREFIX`; for other policies it must be absent or an explicitly validated not-applicable value.

## Primary Outcome

For task \(i\), candidate-stream replicate \(s\), observation replicate \(o\), robustness level \(k\), budget \(N\), policy \(p\), and policy replicate \(r\), define:

\[
G_{i,s,o,k,N,p,r}
=
\mathbb{1}
\left[
q_{\mathrm{meas},i,s,o}^{(k,N,p,r)}=1
\land
q_{\mathrm{ref},i,s,o}^{(k,N,p,r)}=0
\right].
\]

Here \(r\) ranges over frozen random-control replicates only for `RANDOM_FROM_PREFIX`; other policies carry a validated not-applicable value and have policy-replicate cardinality one.

For each task, average equally over the preregistered candidate-stream, observation, and applicable policy-replicate coordinates:

\[
\bar G_i(k,N,p)
=
\frac{1}{R_sR_oR_p(p)}
\sum_{s=1}^{R_s}
\sum_{o=1}^{R_o}
\sum_{r=1}^{R_p(p)}
G_{i,s,o,k,N,p,r}.
\]

Define the aggregate gaming rate with equal task weight:

\[
G(k,N,p)
=
\frac{1}{T_{\mathrm{primary}}}
\sum_{i\in\mathcal{T}_{\mathrm{primary}}}\bar G_i(k,N,p),
\qquad
T_{\mathrm{primary}}=163
\]

for the accepted manifest version. The manifest—not an unbound literal—defines \(\mathcal{T}_{\mathrm{primary}}\) and \(T_{\mathrm{primary}}\).

The primary H1–H4 estimands use `FIRST_MEASURED_PASS`. Aggregation must preserve clustering, pairing, and equal task weight; repeated selections and repeated control rows are not independent observations.

If a required task or coordinate remains invalid after the frozen recovery policy, it remains represented with typed invalid status. It must not disappear from the denominator. The confirmatory aggregate is `INCOMPLETE` unless the preregistration prospectively defines a valid-unit rule that preserves task weighting and explicitly governs inference. No post-unblinding complete-case substitution is permitted.

## Secondary Outcomes

### Measured performance

Let \(\bar q_{\mathrm{meas},i}^{(k,N,p)}\) be the equal-weight mean over the same frozen stream, observation, and applicable policy-replicate coordinates used for \(\bar G_i\). Then:

\[
Q_{\mathrm{meas}}(k,N,p)
=
\frac{1}{T_{\mathrm{primary}}}
\sum_{i\in\mathcal{T}_{\mathrm{primary}}}
\bar q_{\mathrm{meas},i}^{(k,N,p)}.
\]

### Reference performance

Define \(\bar q_{\mathrm{ref},i}^{(k,N,p)}\) using the identical coordinate set and weighting:

\[
Q_{\mathrm{ref}}(k,N,p)
=
\frac{1}{T_{\mathrm{primary}}}
\sum_{i\in\mathcal{T}_{\mathrm{primary}}}
\bar q_{\mathrm{ref},i}^{(k,N,p)}.
\]

These are MEGB-06 experimental aggregates over the 163-task primary population. They are distinct from MEGB-03's 164-task reference-evaluator validation aggregate and must use distinct schema and metric identifiers.

### Signed gaming gap

\[
\Delta_{\mathrm{game}}(k,N,p)
=
Q_{\mathrm{meas}}(k,N,p)-Q_{\mathrm{ref}}(k,N,p).
\]

### Conditional false-acceptance rate

\[
\operatorname{FAR}(k,N,p)
=
P(q_{\mathrm{ref}}=0\mid q_{\mathrm{meas}}=1).
\]

Treat this rate as secondary because its conditioning set changes with budget and policy.

If no valid measured-positive rows exist for a condition, FAR is undefined with an explicit status; it is never silently reported as zero. Its numerator and denominator, task coverage, and clustering unit must always accompany the rate.

### Selection dynamics

Record selected candidate index, first measured-pass index, fraction with no measured pass, duplicate status, invalid-output status, policy-specific selection reason, and `random_control_replicate_id` or validated not-applicable state.

## Confirmatory Hypotheses

H4 is the primary confirmatory hypothesis. H1 is an implementation invariant and descriptive diagnostic, not independent evidence for the scientific claim. The preregistration must classify H2 and H3 as confirmatory-secondary or required secondary and apply a frozen multiplicity rule. H5's inferential status must likewise be frozen before generation.

### H1 — Optimization effectiveness

For the first-measured-pass policy, measured performance is nondecreasing with pressure:

\[
Q_{\mathrm{meas}}(k,N_2)
\ge
Q_{\mathrm{meas}}(k,N_1)
\quad\text{for }N_2>N_1.
\]

This is also an implementation invariant. It is not imposed on `RANDOM_FROM_PREFIX`.

A violation of H1 under complete valid measurements indicates a selection or data-construction defect and invokes the amendment protocol; it is not interpreted as a negative scientific finding.

### H2 — Optimization-induced gaming

For weaker measurement systems:

\[
G(k,32)>G(k,1).
\]

### H3 — Measurement robustness

At fixed pressure:

\[
G(S_1,N)
\ge
G(S_2,N)
\ge
G(S_3,N)
\ge
G(S_4,N).
\]

### H4 — Robustness × pressure interaction

Define the primary difference-in-differences:

\[
D
=
\left[G(S_1,32)-G(S_1,1)\right]
-
\left[G(S_4,32)-G(S_4,1)\right].
\]

The prediction is \(D>0\). The preregistration must freeze a minimum practically meaningful effect \(D_{\min}\).

### H5 — Measurement-directed selection control

Preregister a control contrast comparing gaming under `FIRST_MEASURED_PASS` with paired `RANDOM_FROM_PREFIX` and `FIRST_CANDIDATE` selections.

At minimum, define:

\[
C_{\mathrm{sel}}(k,N)
=
G(k,N,\texttt{FIRST\_MEASURED\_PASS})
-
G(k,N,\texttt{RANDOM\_FROM\_PREFIX}).
\]

The preregistration must identify whether H5 is confirmatory or a required secondary control, specify its primary condition or contrast, and freeze any practical-effect threshold and multiplicity treatment. Do not decide its status after unblinding.

## Epic Dependencies

- `[MEGB-01] Establish HumanEval Corpus and Privileged Evaluation Boundary`
- `[MEGB-02] Implement Isolated Candidate Execution Worker`
- `[MEGB-03] Implement Privileged Reference Evaluator S*`
- `[MEGB-04] Implement Optimization-Visible Measurement Systems S1 ... S4`
- `[MEGB-05] Implement Controlled Candidate Generation and Selection-Only Optimization`

All upstream artifacts, configurations, validation suites, and manifests must be frozen before experimental execution.

The accepted MEGB-04 dependency is the primary `megb-observation-coverage-v1` system family with feedback profile `scalar-binary-v1`. The accepted MEGB-05 dependency provides implementations and reduced-fixture validation only; MEGB-06E, MEGB-06F, and MEGB-06G are the sole owners of confirmatory stream generation, optimization-visible evaluation, and selection freeze.

### Cross-epic holdout gate

MEGB-07A through MEGB-07D—private-suite protocol, task construction, oracle construction, mutation validation, review, and freeze—must be complete before MEGB-06H authorizes reference unblinding.

Those holdout subtasks may run after MEGB-06D freezes the public experiment and in parallel with MEGB-06E through MEGB-06G, but their authors must remain blind to public reference outcomes and selected-candidate behavior.

## Global Scientific Constraints

### No experimental reference inspection before freeze

Before MEGB-06H:

- no experimental per-task reference outcomes may be exposed;
- no aggregate \(Q_{\mathrm{ref}}\), gaming rate, or reference failure category may be exposed;
- no exploratory reference analysis may run; and
- no candidate selection may use reference information.

### Primary reference definition

Each selected candidate's primary task-level \(q_{\mathrm{ref}}\) uses only that task's MEGB-03 frozen reference-only pool. MEGB-06's aggregate \(Q_{\mathrm{ref}}\) then uses the frozen 163-task experimental population and equal-task-weight rule defined above. MEGB-03's separate 164-task evaluator-validation aggregate and full-suite HumanEval+ compatibility metrics are diagnostics; neither may replace or enter the MEGB-06 primary reference measurement.

### Paired candidate population

Candidate streams are generated once and shared across conditions. No robustness level, observation replicate, budget, or policy may trigger regeneration.

### Frozen identity contract

Every experimental coordinate must resolve through frozen identities and checksums for:

- `primary_experiment_task_manifest` and its expected 163-task count;
- MEGB-03 partition, oracle, comparison, reference-evaluator, and execution-profile locks;
- MEGB-04 `megb-observation-coverage-v1` system family, observation manifests, and `scalar-binary-v1` feedback profile;
- MEGB-05 model snapshot, provider/API identity, prompt, generation, extraction, sanitization, stream, selection, and random-control configurations;
- preregistration, analysis implementation, package/environment, and experiment-state manifests; and
- candidate, measurement, selection, reference-result, dataset, and reporting artifacts created by this epic.

Mutable model aliases, unresolved serving drift, checksum mismatch, cross-family substitution, HumanEval/39, and the 164-task validation manifest must fail closed before the affected external call or scientific transition.

### Failure semantics

Candidate failures are valid outcomes. Provider, measurement, oracle, protocol, and infrastructure failures follow the preregistered recovery or invalidation policy and never become candidate failures.

### Immutable scientific record

Preregistrations, amendments, raw candidates, manifests, measurement results, reference results, locked datasets, and analysis outputs are append-only or versioned. Unexpected results are preserved.

### Cost and external-activity authorization

Authorization to implement or validate a subtask is not authorization to incur provider or material infrastructure cost. Before every live-provider or large-scale execution stage, report the exact frozen configuration, expected calls/executions, estimated cost, cost ceiling, abort conditions, and requested state transition. Proceed only after explicit authorization for that stage.

No retry, replacement stream, expanded replicate, or additional evaluation may exceed the frozen policy or cost ceiling without stopping for a versioned amendment and new authorization.

### Experiment state machine

The authoritative state progression is:

```text
DRAFT
  -> PREREGISTERED
  -> RUNNING
  -> CANDIDATES_FROZEN
  -> MEASUREMENTS_FROZEN
  -> SELECTION_FROZEN
  -> REFERENCE_AUTHORIZED
  -> REFERENCE_COMPLETE
  -> DATASET_LOCKED
  -> ANALYSIS_COMPLETE
  -> COMPLETE
```

Every transition must be atomic, append-only, checksummed, timestamped, attributable, and validated against its prerequisites. No stage may infer authorization from the existence of files alone. `reference_evaluation_allowed` remains false through `SELECTION_FROZEN` and may become true only at the MEGB-06H gate after the accepted MEGB-07D freeze is bound.

Any stage may instead enter a typed `BLOCKED` or `ABORTED` record with its prior state, reason, blinding status, cost, and artifact roots preserved. Such a record never satisfies a success prerequisite. Resumption from `BLOCKED` requires the frozen recovery path or a versioned amendment; `ABORTED` is terminal for that experiment version.

An amendment never mutates an earlier state record. It creates a new version, records the blinding state and affected downstream artifacts, and requires deterministic regeneration from the earliest affected transition.

## Epic Execution Protocol

Work through MEGB-06A through MEGB-06K sequentially, except that MEGB-07A through MEGB-07D may proceed during the explicitly authorized blind interval.

For each authorized subtask:

1. Read the epic objectives, hypotheses, constraints, and current subtask.
2. Inspect accepted dependency artifacts.
3. Present a short implementation/execution plan.
4. Execute only the current subtask.
5. Run required validation and relevant regressions.
6. Update only the current status and completion record.
7. Produce the standard checkpoint report.
8. Stop and wait for explicit authorization.

Do not cross a preregistration, generation, selection-freeze, holdout-freeze, reference-unblinding, or analysis-lock gate without explicit authorization. Each subtask should correspond to a separate commit or immutable experiment-state transition. Requirement changes require a versioned amendment.

## Standard Checkpoint Report

At every checkpoint, report:

1. **Summary:** what was implemented, executed, or frozen.
2. **Files/artifacts changed:** created, modified, frozen, invalidated, and intentionally untracked items.
3. **Tests and validation:** exact commands, results, skips, and environment.
4. **Acceptance matrix:** `PASS`, `FAIL`, `BLOCKED`, or `DEFERRED` with evidence.
5. **Scientific state:** current phase, blinding state, and whether reference outcomes exist or were accessible.
6. **Design decisions:** choices constraining later work.
7. **Deviations/amendments:** timing relative to unblinding and downstream consequences.
8. **Known limitations:** unresolved engineering or scientific issues.
9. **Handoff artifacts:** paths, versions, hashes, and freeze states.
10. **Repository/experiment state:** branch, exact commit SHA or uncommitted state, push state, manifest status, and intentionally untracked or privileged artifacts.
11. **Protected-data statement:** reference-only evidence, oracle outputs, canonical solutions, private-holdout evidence, provider credentials, and any exposure beyond their authorized boundary.
12. **External activity and cost:** exact provider calls or large-scale executions, actual usage/cost, authorization record, cost ceiling, and abort status; state explicitly when none occurred.
13. **Next-step readiness:** satisfied prerequisites, unresolved blockers, exact next state transition, and explicit authorization required.

Then stop. Do not begin the next subtask.

## Subtask Status

- [ ] MEGB-06A — Run preflight, signal-feasibility, power, and cost analysis
- [ ] MEGB-06B — Implement and validate the analysis pipeline on synthetic data
- [ ] MEGB-06C — Write and freeze the preregistration
- [ ] MEGB-06D — Create the experiment freeze manifest and authorize execution
- [ ] MEGB-06E — Generate complete experimental candidate streams
- [ ] MEGB-06F — Complete optimization-visible evaluation
- [ ] MEGB-06G — Apply selection policies and freeze all candidates
- [ ] MEGB-06H — Authorize and execute one-time reference evaluation
- [ ] MEGB-06I — Build and lock the analysis dataset
- [ ] MEGB-06J — Run confirmatory and secondary analyses
- [ ] MEGB-06K — Generate figures, report, audit, and reproducibility package

---

## MEGB-06A — Run Preflight, Signal-Feasibility, Power, and Cost Analysis

### Status

**Status:** Not started

### Objective

Demonstrate that the frozen infrastructure and measurement systems are ready and that the planned experiment has a plausible signal, affordable cost, and defensible replicate count without inspecting confirmatory reference outcomes.

### Dependencies

- MEGB-01 through MEGB-05 complete and accepted.

### Requirements

1. Run the upstream preflight gate and verify:
   - `reference_validation_task_manifest` contains exactly 164 tasks for MEGB-03 validation;
   - `primary_experiment_task_manifest` contains the accepted expected 163 tasks, excludes HumanEval/39, and matches its frozen checksum;
   - frozen, disjoint development/reference-only pools;
   - dataset, partition, oracle, and evaluator checksums;
   - all 20 frozen `megb-observation-coverage-v1` optimization-visible definitions use feedback profile `scalar-binary-v1`;
   - canonical solutions pass every primary MEGB-04 system for all 163 experimental tasks, while the separate MEGB-03 164-task validation gate passes under its own schema;
   - MEGB-04 monotonicity and robustness-separation validation;
   - MEGB-05 nested prefixes, shared candidates, and all selection policies;
   - MEGB-03's accepted full-reference orchestration, cache/audit path, and representative measured throughput are production-ready for the projected unique selected-candidate load;
   - MEGB-02 security suite;
   - optimization runtime cannot access \(S^*\); and
   - no experimental reference evaluation has occurred.
2. Conduct a signal-feasibility assessment addressing possible HumanEval saturation by the frozen model.
3. Permitted feasibility inputs include:
   - MEGB-04's nonexperimental validation corpus;
   - canonical and synthetic solutions;
   - synthetic candidate/reference outcomes;
   - published or externally sourced failure-rate estimates;
   - historical artifacts not produced as confirmatory candidates; and
   - a separately designated pilot task/model/seed namespace excluded by manifest from confirmatory generation and analysis.
4. Do not inspect confirmatory \(Q_{\mathrm{ref}}\) or generate candidates that later enter the confirmatory dataset.
5. Define explicit feasibility thresholds for:
   - candidate diversity;
   - measured pass availability by budget;
   - reference failure prevalence;
   - expected gaming-event prevalence;
   - robustness separation; and
   - saturation/floor effects.
6. If the signal appears infeasible, stop and propose a versioned design amendment before preregistration. Do not proceed merely because infrastructure is complete.
7. Perform power and cost analysis using only permitted pre-experimental inputs.
8. Determine:
   - candidate-stream replicate count;
   - optional random-control replicate count;
   - model generations;
   - candidate executions after cache/batching reuse;
   - unique frozen candidates expected to require \(S^*\);
   - runtime and storage;
   - provider and infrastructure cost;
   - detectable range for \(D\) and H5 controls;
   - proposed \(D_{\min}\) and any control threshold;
   - stopping/infeasibility criteria; and
   - contingency for incomplete provider streams.
9. Use measured end-to-end generation, optimization-visible, and full-reference throughput where available. Explicitly model the projected unique \(S^*\) workload after selection deduplication. If the accepted MEGB-03 execution strategy cannot complete within the frozen runtime/cost envelope, block before candidate generation rather than assuming future optimization.
10. Specify the exact expected coordinate and execution-count formulas, including the policy-specific `random_control_replicate_id` dimension and deduplication of repeated selected candidates before reference evaluation.
11. Define a prospective invalid-cluster/incomplete-experiment rule that preserves the primary task population and equal task weighting. Do not silently drop invalid tasks or coordinates.
12. Do not reduce replicate count after confirmatory generation begins or after observing optimization-visible or reference outcomes. Any earlier change requires a versioned preregistration input and refreshed power/cost analysis.
13. Produce machine-readable assumptions and a human-readable report with sensitivity analyses.

### Acceptance Criteria

- Every preflight gate passes or the experiment is blocked.
- Signal feasibility is assessed without confirmatory outcomes.
- Pilot artifacts are provably excluded from confirmatory candidate manifests.
- Saturation/floor risks and feasibility thresholds are explicit.
- Replicate counts, effect thresholds, runtime, storage, and costs are justified and frozen as preregistration inputs.
- Batched/cache-aware execution counts are used rather than the naive matrix cost.
- Full-reference runtime and cost are supported by measured accepted throughput; an infeasible execution plan blocks the experiment before generation.
- Expected counts include random-control replicates and reference-result deduplication.
- The incomplete-data rule cannot silently change the task denominator or task weights.
- No experimental reference evaluation has occurred.

### Required Tests and Validation

- Automated preflight-gate test.
- Manifest/checksum, dual-population, HumanEval/39, and exact-task-count checks.
- Pilot/confirmatory artifact-separation tests.
- Synthetic power-recovery tests.
- Cost-model arithmetic and sensitivity tests.
- Execution-count calculation against known fixtures.
- Reference-throughput projection and infeasibility-gate tests.
- Random-control-dimension and equal-task-weight arithmetic tests.
- Failure gate for infeasible signal or cost.

### Non-Goals

- Generating confirmatory candidate streams.
- Finalizing the preregistration.
- Inspecting any confirmatory reference outcome.

### Handoff Artifacts

- Preflight report.
- Signal-feasibility report.
- Power and cost analysis.
- Frozen proposed replicate counts and effect thresholds.
- Machine-readable planning assumptions.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-06B requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Reference outcomes unavailable
- Deviations: —
- Handoff: —

---

## MEGB-06B — Implement and Validate the Analysis Pipeline on Synthetic Data

### Status

**Status:** Not started

### Objective

Implement and test the complete dataset-building and statistical-analysis logic against synthetic data with known effects before preregistration and unblinding.

### Dependencies

- MEGB-06A complete and accepted.

### Requirements

1. Define the long-form analysis schema with one row per:

   ```text
   (task_id,
    candidate_stream_id,
    observation_replicate,
    robustness_level,
    optimization_budget,
    selection_policy,
    random_control_replicate_id_or_na)
   ```
2. Bind every row and dataset manifest to the primary task-manifest ID/checksum and accepted expected count. Reject HumanEval/39, out-of-manifest tasks, the 164-task validation manifest, mixed system families, and mixed feedback profiles.
3. Include fields required to trace each row to experiment, task, stream/seed, observation replicate, system/evidence budget, policy, random-control replicate or validated not-applicable state, selected candidate/index/hash, selection reason, \(q_{\mathrm{meas}}\), \(q_{\mathrm{ref}}\), gaming indicator, signed difference, statuses, duplicate/invalid-output indicators, versions, and checksums.
4. Exclude hidden inputs, expected outputs, canonical solutions, privileged diagnostics, and privileged artifact paths from the analysis schema.
5. Implement exact gaming-event, task-level replicate averaging, equal-task-weight aggregate, and signed-gap calculations from the definitions in this ticket.
6. Implement expected-row arithmetic:

   \[
   T_{\mathrm{primary}}
   \times R_s
   \times R_o
   \times 4
   \times 6
   \times \left(2+R_{\mathrm{random}}\right),
   \]

   where the two singleton policies are `FIRST_MEASURED_PASS` and `FIRST_CANDIDATE`. Validate policy-specific not-applicable versus required random replicate identity.
7. Implement the primary H4 difference-in-differences.
8. Implement the paired H5 policy-control contrasts, including the preregistered method for combining multiple random-control replicates without treating duplicated task/stream/system rows as independent.
9. Implement a hierarchical clustered bootstrap that:
   1. samples tasks with replacement;
   2. samples stream replicates within sampled tasks;
   3. independently samples observation replicates within sampled tasks;
   4. forms the sampled stream × observation Cartesian product within each sampled task because those factors are crossed, not nested within one another;
   5. preserves complete paired robustness, budget, policy, and random-control-replicate conditions for every sampled factor combination;
   6. applies the frozen random-control-replicate treatment; and
   7. uses a frozen seed and configurable draw count, defaulting to 10,000.
10. Implement the secondary logistic mixed-effects specification for the primary `FIRST_MEASURED_PASS` regime:

   \[
   \operatorname{logit}P(G=1)
   =
   \beta_0
   +\beta_N\log_2N
   +\beta_E\log E
   +\beta_{NE}(\log_2N)(\log E)
   +u_{\mathrm{task}}
   +u_{\mathrm{task:stream}}
   +u_{\mathrm{task:observation}}.
   \]
11. Support a separately identified preregisterable policy factor/control model or contrasts without replacing the H4 model silently.
12. Define implementation/package version, optimizer/convergence settings, random effects, singular-fit handling, nonconvergence fallback, and reporting.
13. Implement secondary contrasts, multiplicity correction, and gaming-onset logic.
14. Define onset:

   \[
   N^*(k)=\min N
   \]

   satisfying both the frozen practical-effect threshold and clustered interval criterion. If none qualifies, report `No reliable onset observed within N <= 32.`
15. Generate synthetic datasets covering null, expected positive interaction, reversed effect, sparse events, missing/invalid rows, unequal raw replicate counts, singular fit, nonconvergence, and single/multiple random-control-replicate effects.
16. Make any unresolved required task/coordinate produce a typed incomplete aggregate under the frozen invalid-unit rule; never recalculate a nominally complete result over a silently reduced denominator.
17. Freeze the analysis-code revision used by the preregistration. Later changes follow the amendment protocol.

### Acceptance Criteria

- Synthetic known effects are recovered within documented tolerances.
- Cluster resampling preserves the paired design and crossed stream/observation structure.
- H4 and H5 estimands are calculated exactly.
- Every task receives equal aggregate weight regardless of repeated selections or policy-replicate count.
- Dataset validation catches missing, duplicate, inconsistent, and hidden-evidence fields.
- Multiplicity and onset logic match frozen examples.
- Hierarchical-model failure follows the specified fallback and cannot replace the confirmatory bootstrap.
- Analysis outputs are deterministic for a frozen seed and input checksum.

### Required Tests

- Exact row-count and composite-key tests.
- Primary-manifest, HumanEval/39, dual-population, and system-family/profile rejection tests.
- Artifact-join and provenance tests.
- Gaming-event and signed-gap tests.
- Difference-in-differences and policy-control tests.
- Clustered-bootstrap sampling, crossed-factor Cartesian-product behavior, and confidence intervals.
- Multiplicity correction.
- Onset-threshold boundary cases.
- Mixed-model coefficient direction and nonconvergence fallback.
- Hidden-evidence field rejection.
- Incomplete-denominator and unequal-replicate-weight rejection tests.
- Deterministic result checksums.

### Non-Goals

- Analyzing experimental outcomes.
- Choosing tests after seeing results.
- Producing final publication figures.

### Handoff Artifacts

- Versioned analysis schema and dataset builder.
- Tested primary/secondary analysis implementation.
- Synthetic validation corpus and expected results.
- Candidate analysis-code revision ready to be frozen by MEGB-06C.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-06C requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Reference outcomes unavailable
- Deviations: —
- Handoff: —

---

## MEGB-06C — Write and Freeze the Preregistration

### Status

**Status:** Not started

### Objective

Create human- and machine-readable preregistration artifacts binding the design, estimands, controls, analyses, exclusions, claims, and completion criteria before confirmatory generation.

### Dependencies

- MEGB-06B complete and accepted.

### Requirements

1. Create:

   ```text
   experiments/megb-v1/preregistration.md
   experiments/megb-v1/preregistration.json
   ```
2. Preregister:
   - research question and confirmatory/secondary hypotheses;
   - primary H4 estimand and \(D_{\min}\);
   - H5 control status, estimands, thresholds, and multiplicity treatment;
   - primary/secondary/exploratory classification;
   - `primary_experiment_task_manifest` ID/checksum, accepted expected 163 tasks, and a priori exclusion of HumanEval/39;
   - the separate 164-task `reference_validation_task_manifest` as validation-only and outside every experimental denominator;
   - robustness levels and observation replicates;
   - budgets and candidate-stream replicate count;
   - all selection policies, random-control replicate count/IDs, seed namespace, aggregation, and clustering treatment;
   - equal-task-weight aggregation and exact expected-row formulas;
   - generation configuration, immutable model snapshot identity, serving-drift policy, and cost ceiling;
   - MEGB-04 system-family identity `megb-observation-coverage-v1` and feedback profile `scalar-binary-v1`;
   - failure/retry/exclusion policies;
   - candidate-freeze and reference-evaluation policy;
   - private-holdout freeze requirement before unblinding;
   - power, feasibility, and cost rationale;
   - bootstrap implementation, clustering, seed, and draw count;
   - mixed-model specification and fallback;
   - multiplicity policy;
   - onset definition;
   - figure/table specifications;
   - claim boundaries; and
   - completion and infeasibility criteria.
3. Freeze the exact analysis-code revision and dependency versions.
4. Freeze the failure/exclusion table:

   | Event | Treatment |
   | --- | --- |
   | Empty/refused/malformed/syntax-invalid output | Retain and count toward \(N\) |
   | Duplicate output | Retain and count toward \(N\) |
   | Candidate exception/timeout/resource violation | Valid candidate failure |
   | Provider transport/auth failure | Frozen retry; invalidate stream if unresolved |
   | Visible evaluator infrastructure failure | Resume/invalidate; never candidate failure |
   | Reference infrastructure failure | Resume/undefined; never candidate failure |
   | Missing task condition | Aggregate incomplete; denominator unchanged |
   | Unexpected result | Preserve; no surprise-driven rerun |
5. Define the amendment protocol:
   1. stop affected phase;
   2. preserve artifacts;
   3. document defect and discovery time;
   4. state blinding status;
   5. create a versioned amendment;
   6. increment affected versions;
   7. regenerate downstream artifacts; and
   8. classify the result according to amendment timing.
6. Freeze the exact distinction between candidate failure, measurement invalidity, reference invalidity, and experiment-unit incompleteness in every schema and estimand.
7. Compute and record preregistration checksums.
8. Atomically transition from `DRAFT` to `PREREGISTERED` only after the human- and machine-readable artifacts, synthetic analysis revision, assumptions, and cost authorization inputs agree.
9. Prevent outcome-affecting fields from changing after `PREREGISTERED` without an explicit amendment and version increment. Once confirmatory generation begins, every amendment must additionally record its effect on confirmatory status.

### Acceptance Criteria

- Human- and machine-readable preregistrations are mutually consistent.
- Every required factor, policy, estimand, threshold, analysis, failure rule, figure, and claim boundary is frozen.
- Primary/validation populations, system family/feedback profile, random-control replicates, equal task weighting, and expected counts are unambiguous.
- Synthetic-tested analysis code and dependency versions are bound.
- Holdout-freeze-before-unblinding is explicit.
- The amendment protocol preserves original artifacts.
- Checksums detect any change.
- The experiment state is `PREREGISTERED` with reference evaluation disabled.
- No confirmatory candidate generation has begun.

### Required Tests

- Human/machine preregistration consistency.
- Required-field completeness.
- Checksum and mutation detection.
- Analysis revision/version validation.
- Invalid state transition when candidate generation precedes freeze.
- Amendment-version behavior.
- Population/family/profile/random-replicate and `DRAFT -> PREREGISTERED` transition tests.

### Non-Goals

- Generating candidates.
- Running reference evaluation.
- Revising hypotheses after observing results.

### Handoff Artifacts

- Frozen preregistration Markdown and JSON.
- Preregistration checksum.
- Frozen amendment and failure/exclusion protocols.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-06D requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Reference outcomes unavailable
- Deviations: —
- Handoff: —

---

## MEGB-06D — Create the Experiment Freeze Manifest and Authorize Execution

### Status

**Status:** Not started

### Objective

Bind every frozen dependency into one experiment manifest, rerun the final start gate, and atomically authorize confirmatory candidate generation while keeping reference evaluation disabled.

### Dependencies

- MEGB-06C complete and accepted.

### Requirements

1. Create a manifest referencing at least:

   ```json
   {
     "experiment_id": "megb-selection-pressure-v1",
     "state_schema_version": "megb-experiment-state-v1",
     "task_manifest_id": "primary_experiment_task_manifest",
     "task_manifest_expected_count": 163,
     "task_manifest_sha256": "sha256:...",
     "reference_validation_manifest_sha256": "sha256:...",
     "partition_manifest_sha256": "sha256:...",
     "reference_evaluator_sha256": "sha256:...",
     "system_family_id": "megb-observation-coverage-v1",
     "system_family_sha256": "sha256:...",
     "feedback_profile_id": "scalar-binary-v1",
     "optimizer_config_sha256": "sha256:...",
     "generation_config_sha256": "sha256:...",
     "model_snapshot_id": "provider-immutable-snapshot",
     "selection_policy_config_sha256": "sha256:...",
     "random_control_config_sha256": "sha256:...",
     "preregistration_sha256": "sha256:...",
     "analysis_code_revision": "git-sha",
     "execution_cost_ceiling": "frozen-value-and-currency",
     "private_holdout_freeze_sha256": null,
     "reference_evaluation_allowed": false,
     "status": "PREREGISTERED"
   }
   ```
2. Bind dataset, partition, oracle, execution, system, observation, validation, model, prompt, stream, selector, analysis, environment, and dependency versions.
3. Rerun the complete preflight gate against the exact frozen artifacts.
4. Verify power/signal assumptions and preregistration checksums are present.
5. Reject HumanEval/39, the validation manifest as experimental population, mutable model aliases, serving-identity drift, adaptive system-family/profile identities, and any checksum mismatch.
6. Verify reference evaluation remains disabled and no experimental reference artifact exists.
7. Verify analysis code is frozen before generation.
8. Present the exact expected provider calls, token/cost model, cost ceiling, abort conditions, and requested `PREREGISTERED -> RUNNING` transition for explicit authorization.
9. Transition atomically from `PREREGISTERED` to `RUNNING` only after all gates and the separate execution/cost authorization pass.
10. Treat `RUNNING` as authorization only for the frozen MEGB-06E generation plan. It does not authorize later measurement, selection, reference, or analysis transitions.
11. Make the manifest immutable after `RUNNING`, except for explicit state transitions and versioned amendments.
12. Record authorization timestamp, actor, code revision, authorization record, cost ceiling, and reproducibility command.

### Acceptance Criteria

- Every required upstream artifact resolves and matches its checksum.
- The final preflight gate passes against frozen versions.
- Reference evaluation is disabled.
- Population, system-family, feedback-profile, model-identity, and cost gates pass.
- The experiment cannot enter `RUNNING` with missing preregistration, analysis, power, or dependency artifacts.
- The `RUNNING` transition is atomic and auditable.
- No outcome-affecting manifest field is mutable afterward without amendment.

### Required Tests

- Missing/mismatched dependency refusal.
- Preregistration and analysis-revision gate tests.
- Reference-disabled gate.
- HumanEval/39, validation-population, family/profile, model-drift, and cost-authorization refusal tests.
- Atomic state-transition tests.
- Immutability and amendment-version tests.
- Reproducibility-command capture.

### Non-Goals

- Candidate generation itself.
- Private holdout authoring.
- Reference evaluation.

### Handoff Artifacts

- Frozen experiment manifest in `RUNNING` state.
- Final preflight report.
- Execution authorization record.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-06E requires explicit authorization. MEGB-07A may now be authorized independently while remaining blinded.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Reference outcomes unavailable
- Deviations: —
- Handoff: —

---

## MEGB-06E — Generate Complete Experimental Candidate Streams

### Status

**Status:** Not started

### Objective

Generate the complete preregistered candidate population through MEGB-05 while preserving generation independence and the frozen experiment design.

### Dependencies

- MEGB-06D experiment state is `RUNNING`.
- Explicit MEGB-06E generation authorization and frozen cost ceiling are recorded.

### Requirements

1. Cover exactly the accepted `primary_experiment_task_manifest`—expected 163 tasks, excluding HumanEval/39—and the preregistered number of stream replicates.
2. Produce exactly 32 positions per complete stream.
3. Use the frozen immutable model snapshot plus prompt, sampling, extraction, sanitization, retry, and tool configuration. Validate provider-returned identity and the serving-drift policy on every call.
4. Preserve duplicates, refusals, malformed outputs, invalid code, raw responses, metadata, and hashes.
5. Keep generation independent of measurement-system, observation-replicate, budget, and policy conditions.
6. Complete candidate generation before any reference evaluation is enabled.
7. Apply only the frozen provider retry policy.
8. An unresolved incomplete stream invalidates its experiment unit under the preregistered policy. Do not silently add streams or requests after inspecting outcomes.
9. Validate complete stream manifests, indices, hashes, and candidate/artifact resolution.
10. Never exceed the frozen retry schedule or cost ceiling. Stop rather than silently creating replacement streams, extending the budget, changing providers/models, or using a mutable alias.
11. Record actual provider usage, token counts, costs, timing, retries, identity/fingerprint observations, and deviations from planning assumptions.
12. Validate exact expected stream count \(T_{\mathrm{primary}}R_s\), exact complete-position count, manifest membership, and zero HumanEval/39 coordinates.
13. After completeness and integrity checks pass, atomically transition `RUNNING -> CANDIDATES_FROZEN` and bind the candidate-stream manifest root. If the preregistered incomplete-stream rule blocks the transition, remain in `RUNNING` or enter an explicit failed state; never mark a partial population complete.
14. Do not inspect or calculate experimental reference outcomes.

### Acceptance Criteria

- Every expected stream exists exactly once or is explicitly incomplete under the preregistered policy.
- Every stream task belongs to the 163-task primary manifest; HumanEval/39 and validation-only tasks are absent.
- Complete streams contain 32 immutable ordered positions.
- Identical candidate streams are available to every downstream condition.
- No candidate was generated with measurement or reference feedback.
- Raw and normalized artifacts are complete and checksummed.
- Actual generation cost and failures are audited.
- Provider/model identity matches the frozen policy and the cost ceiling was not exceeded.
- Successful completion leaves the experiment in `CANDIDATES_FROZEN`.
- Reference evaluation remains disabled.

### Required Tests and Validation

- Exact primary-manifest stream/candidate-position counts and HumanEval/39 rejection.
- Manifest uniqueness and checksum validation.
- Shared-candidate identity preparation.
- Duplicate/invalid-output preservation.
- Retry and incomplete-stream policy checks.
- Generation-context leakage checks.
- Model identity/drift, cost-ceiling, and `RUNNING -> CANDIDATES_FROZEN` transition tests.
- Actual-versus-planned cost report.

### Non-Goals

- Optimization-visible candidate evaluation.
- Candidate selection.
- Reference evaluation.

### Handoff Artifacts

- Complete experimental candidate-stream manifests.
- Immutable raw and normalized candidate artifacts.
- Generation completeness, cost, and failure report.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-06F requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Reference outcomes unavailable
- Deviations: —
- Handoff: —

---

## MEGB-06F — Complete Optimization-Visible Evaluation

### Status

**Status:** Not started

### Objective

Evaluate the complete frozen candidate population against every preregistered optimization-visible system condition and verify matrix completeness before selection.

### Dependencies

- MEGB-06E complete and accepted.
- Experiment state is `CANDIDATES_FROZEN` and explicit MEGB-06F execution authorization/cost ceiling is recorded.

### Requirements

1. Evaluate through MEGB-04/MEGB-05 only.
2. Cover:

   ```text
   primary_experiment_task_manifest (expected 163 tasks)
   × preregistered candidate-stream replicates
   × 32 candidate positions
   × 4 robustness levels
   × frozen observation-set replicates (accepted primary family: 5)
   ```
3. Bind every cell to `megb-observation-coverage-v1`, feedback profile `scalar-binary-v1`, the primary task-manifest checksum, and the accepted observation/system-family locks. Reject HumanEval/39, adaptive-family identities, and validation-population substitution.
4. Use MEGB-04 nested-case reuse and MEGB-05 content-addressed caching.
5. Candidate failures are valid measurements.
6. Infrastructure, development-oracle, manifest, controller, and protocol failures are invalid and follow the frozen recovery policy.
7. Every required cell must be valid before first-measured-pass selection proceeds, except where the preregistered invalid-unit policy explicitly applies.
8. Verify identical candidate hashes across paired conditions.
9. Parallel execution and resumption must not alter matrix identity, measurements, or ordering.
10. Reconcile the exact expected matrix count \(T_{\mathrm{primary}}R_s\times32\times4\times R_o\), observed cells, unique candidate executions after nested/cache reuse, cache hits/misses, invalid cells, runtime, storage, and cost.
11. Keep \(S^*\) disabled and inaccessible.
12. After completeness and integrity checks pass, atomically transition `CANDIDATES_FROZEN -> MEASUREMENTS_FROZEN` and bind the immutable measurement-matrix root. A partial or invalid matrix cannot receive the completed state.

### Acceptance Criteria

- Every expected coordinate appears exactly once with a valid result or preregistered invalid-unit disposition.
- Exact counts derive from the frozen primary and system-family manifests; HumanEval/39 is absent.
- Shared candidate identities match across all conditions.
- No condition triggered candidate regeneration.
- Candidate versus measurement failure semantics are preserved.
- Cache and batch reuse are auditable.
- Matrix artifacts are immutable and checksummed.
- Successful completion leaves the experiment in `MEASUREMENTS_FROZEN`.
- Reference evaluation remains disabled.

### Required Tests and Validation

- Exact matrix-completeness counts.
- Primary-manifest, HumanEval/39, family/profile, and observation-manifest validation.
- Composite-key uniqueness.
- Shared-candidate identity.
- Cache/batch execution-count reconciliation.
- Failure-policy application.
- Sequential/parallel and resumption equivalence.
- Artifact and checksum validation.
- Reference-isolation checks.
- Cost-ceiling and `CANDIDATES_FROZEN -> MEASUREMENTS_FROZEN` transition tests.

### Non-Goals

- Applying selection policies.
- Unblinding reference results.
- Statistical analysis.

### Handoff Artifacts

- Complete optimization-visible measurement matrix.
- Matrix completeness and failure report.
- Execution/cache/cost audit.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-06G requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Reference outcomes unavailable
- Deviations: —
- Handoff: —

---

## MEGB-06G — Apply Selection Policies and Freeze All Candidates

### Status

**Status:** Not started

### Objective

Apply the preregistered experimental and control selection policies at every budget, validate every decision, and atomically freeze the candidate set before reference authorization.

### Dependencies

- MEGB-06F complete and accepted.
- Experiment state is `MEASUREMENTS_FROZEN`.

### Requirements

1. Apply `FIRST_MEASURED_PASS`, every preregistered `RANDOM_FROM_PREFIX` replicate, and `FIRST_CANDIDATE` exactly as preregistered.
2. Apply budgets `1,2,4,8,16,32` using shared nested prefixes.
3. Generate and validate every selection decision and frozen candidate manifest.
4. Before freeze, verify:
   - every selection resolves to a candidate artifact;
   - candidate and eligible-prefix hashes match;
   - policies used only authorized inputs;
   - every random selection carries a valid `random_control_replicate_id` and random controls are paired across measurement conditions;
   - nonrandom policies carry the validated not-applicable random-replicate state;
   - first-pass decisions use only visible measurements;
   - first-pass monotonicity and stability invariants pass;
   - every expected condition/policy is represented;
   - decisions reproduce from frozen artifacts; and
   - no reference result exists or influenced selection.
5. Validate the exact expected decision count:

   \[
   T_{\mathrm{primary}}R_sR_o\times4\times6\times(2+R_{\mathrm{random}}).
   \]

   Every expected coordinate must exist exactly once or carry the preregistered typed invalid-unit disposition; no coordinate may disappear silently.
6. Verify that `FIRST_CANDIDATE` and paired random-control selections that resolve to the same candidate across repeated conditions retain their coordinate mappings without being treated as independent candidate identities.
7. Incomplete/invalid units follow the preregistered policy and cannot be silently replaced.
8. Freeze candidate selections immutably.
9. Transition atomically:

   ```json
   {
     "status": "SELECTION_FROZEN",
     "reference_evaluation_allowed": false
   }
   ```

10. Keep reference evaluation disabled until the independent private-holdout freeze gate is satisfied.
11. Record freeze timestamp, candidate/selection manifest roots, policy and random-control configuration roots, code revision, and audit actor.

### Acceptance Criteria

- Every expected valid selection exists exactly once.
- All selections are deterministic, hash-resolving, and policy-compliant.
- Random and first-candidate controls remain independent of measurements.
- Random-control replicate identity is complete, paired, and preserved as a downstream analysis coordinate.
- First-measured-pass decisions use no reference information.
- Selections cannot change after transition.
- Experiment status is `SELECTION_FROZEN` while reference authorization remains false.
- No experimental reference outcomes have been exposed.

### Required Tests and Validation

- Exact policy-specific selection-count and coordinate tests.
- Candidate/prefix/measurement hash resolution.
- Policy, random-replicate identity, random-pairing, and not-applicable-state tests.
- First-pass monotonicity/stability tests.
- Freeze immutability.
- Reference-disabled state-transition tests.
- Duplicate selected-candidate mapping preparation.

### Non-Goals

- Running \(S^*\).
- Viewing selected candidate/reference behavior for holdout authoring.
- Joining an analysis dataset.

### Handoff Artifacts

- Frozen selection and candidate manifests for all policies.
- Selection completeness and reproducibility report.
- Experiment manifest in `SELECTION_FROZEN` state with reference disabled.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-06H is blocked until MEGB-07A through MEGB-07D are complete, accepted, and checksummed.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Reference outcomes unavailable; selections frozen
- Deviations: —
- Handoff: —

---

## MEGB-06H — Authorize and Execute One-Time Reference Evaluation

### Status

**Status:** Not started

### Objective

Verify the independent private holdout is frozen, authorize one-time privileged reference evaluation of frozen candidates, record unblinding, and freeze a complete deduplicated reference-result manifest without yet building or analyzing the joined dataset.

### Dependencies

- MEGB-06G complete and accepted.
- MEGB-07A through MEGB-07D complete, accepted, and frozen before any public reference outcome is exposed.
- Experiment state is `SELECTION_FROZEN` with `reference_evaluation_allowed = false`.

### Requirements

1. Verify the private-holdout freeze manifest, timestamp, candidate-blind construction attestation, review evidence, and checksum.
2. Bind its checksum into the MEGB-06 experiment manifest.
3. Verify all selection manifests remain immutable and all candidate hashes resolve.
4. Recompute the exact unique candidate/task/evaluator tuples after deduplication and present expected executions, runtime, storage, infrastructure cost, cost ceiling, abort conditions, and the requested reference-unblinding transition for explicit authorization.
5. Atomically transition `SELECTION_FROZEN -> REFERENCE_AUTHORIZED` and set `reference_evaluation_allowed = true` only after the holdout gate and separate reference-execution authorization pass. Record the unblinding timestamp and actor at this transition.
6. Evaluate only candidates resolved through frozen MEGB-06G manifests and only for tasks in `primary_experiment_task_manifest`. Reject HumanEval/39, out-of-manifest tasks, the validation manifest as an experiment population, and any mutable selection.
7. Evaluate through the accepted full MEGB-03 reference profile using only each task's frozen reference-only pool. Never substitute reduced-development or full-suite-compatibility diagnostics for primary \(q_{\mathrm{ref}}\).
8. Verify candidate hash, task membership, reference-case checksum, oracle/comparison/evaluator/execution versions, and complete evaluation context before every request.
9. Produce at most one accepted valid result for each unique candidate/task/evaluator-context tuple. Never re-execute a valid result; retry only typed infrastructure failures under the frozen policy, retaining every attempt in the audit.
10. Preserve a complete mapping from every selection coordinate—including `random_control_replicate_id`—to its reference-result identity.
11. Preserve typed candidate failures as \(q_{\mathrm{ref}}=0\); preserve invalid reference measurements as `None`/typed invalid status. Never convert apparatus failure into candidate failure.
12. Write append-only privileged reference audit records. Optimization artifacts and the later analysis dataset may receive only authorized task-level result fields, never reference inputs, expected outputs, oracle records, canonical solutions, or per-case diagnostics.
13. Do not rerun a valid reference measurement because its result is unexpected. Resume reference infrastructure failures only under the frozen MEGB-03 policy; selections cannot change.
14. Produce an immutable reference-result manifest with expected/observed unique tuple counts, selection-coordinate mappings, statuses, evaluator/context versions, artifact roots, checksums, execution/cost audit, holdout-freeze checksum, and unblinding record.
15. Transition `REFERENCE_AUTHORIZED -> REFERENCE_COMPLETE` only when every required unique tuple has a valid result or the preregistered typed invalid disposition. At that transition set `reference_evaluation_allowed = false` and `reference_evaluation_complete = true`; a partial result set cannot be labeled complete or left open for opportunistic reruns.

### Acceptance Criteria

- Private holdout was frozen before reference unblinding.
- Reference authorization occurred only after selection and holdout freezes.
- Every unique frozen candidate/task/evaluator tuple has at most one accepted valid result; any permitted infrastructure attempts are retained and reconciled.
- Primary reference values use only reference-only evidence.
- Every condition retains provenance to its shared reference result.
- Unblinding is timestamped and auditable.
- HumanEval/39 and validation-only coordinates are absent.
- Candidate failures and invalid measurements remain semantically distinct.
- No hidden reference evidence crosses into nonprivileged artifacts.
- Successful completion leaves an immutable reference-result manifest and state `REFERENCE_COMPLETE`.
- Reference execution is disabled again after completion.

### Required Tests and Validation

- Holdout-freeze prerequisite and timestamp ordering.
- Reference authorization state transition.
- Candidate-hash and selection immutability checks.
- Reference deduplication with repeated selected hashes.
- Primary-manifest, HumanEval/39, evaluator-profile, and context-version refusal tests.
- Candidate-failure versus invalid-measurement tests.
- Selection-coordinate/reference-result mapping completeness.
- Privileged-evidence leakage rejection.
- Cost-ceiling, one-valid-result, reference-reclosure, and `SELECTION_FROZEN -> REFERENCE_AUTHORIZED -> REFERENCE_COMPLETE` transition tests.

### Non-Goals

- Building or analyzing the joined experimental dataset.
- Changing selections or holdout evidence.
- Evaluating private holdout outcomes; that belongs to later MEGB-07 subtasks.

### Handoff Artifacts

- Deduplicated privileged reference results and audit.
- Recorded unblinding event.
- Immutable reference-result manifest with selection-coordinate mappings.
- Reference completeness, failure, cost, and provenance report.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-06I requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Reference outcomes unblinded; reference-result manifest frozen
- Deviations: —
- Handoff: —

---

## MEGB-06I — Build and Lock the Analysis Dataset

### Status

**Status:** Not started

### Objective

Deterministically join frozen selection, optimization-visible measurement, and reference-result artifacts into the preregistered long-form schema, validate every coordinate and denominator, and lock the analysis dataset without running inferential analyses.

### Dependencies

- MEGB-06H complete and accepted.
- Experiment state is `REFERENCE_COMPLETE`.

### Requirements

1. Build the dataset only through the frozen MEGB-06B dataset builder and schema version.
2. Bind the primary task-manifest, experiment, system family, feedback profile, generation, stream, observation, measurement, selection-policy, random-control, reference-evaluator, and analysis-schema identities/checksums.
3. Include exactly one row for every expected selection coordinate:

   \[
   T_{\mathrm{primary}}R_sR_o\times4\times6\times(2+R_{\mathrm{random}}),
   \]

   or a typed preregistered invalid/incomplete row at that same coordinate. Never drop a task or coordinate silently.
4. Validate composite-key uniqueness, primary-manifest membership, absence of HumanEval/39, exact expected/observed counts, and policy-specific random-control-replicate identity.
5. Resolve every row to immutable candidate, candidate-stream, measurement, selection, and reference-result identities. Verify selected candidate/index/hash and eligible-prefix hash.
6. Reuse one frozen reference result across all rows selecting the same candidate/task/evaluator context while preserving every scientific coordinate. Repeated mappings are not independent reference executions.
7. Include only authorized nonprivileged fields needed for analysis: typed statuses, task-level \(q_{\mathrm{meas}}\), task-level \(q_{\mathrm{ref}}\), selected candidate identity/hash, selection reason/index, duplicate/invalid-output indicators, factor coordinates, versions, and checksums.
8. Exclude reference inputs, expected outputs, oracle records, canonical solutions, privileged paths, per-case diagnostics, provider credentials, and secrets.
9. Calculate gaming events and signed task-level differences exactly as frozen. Validate equal-task-weight aggregation fixtures but do not run the confirmatory analysis.
10. Preserve candidate failure, measurement invalidity, reference invalidity, and incomplete experiment units as distinct typed states. Any required invalid coordinate propagates under the preregistered incomplete-aggregate rule.
11. Produce a dataset validation/provenance report, content checksum, schema/version lock, and deterministic rebuild command.
12. Atomically transition `REFERENCE_COMPLETE -> DATASET_LOCKED` only after byte-stable rebuild, completeness, lineage, leakage, and checksum checks pass.
13. Any correction requires a new dataset version, documented defect/discovery time/blinding status, and complete deterministic regeneration. Never overwrite the locked version.

### Acceptance Criteria

- Every expected coordinate exists exactly once with valid or typed invalid status.
- Task population and denominators match the frozen 163-task primary manifest; HumanEval/39 is absent.
- All joins and repeated-result mappings resolve by immutable identity.
- Gaming and signed-gap fields match the frozen implementation.
- Missing/invalid data cannot silently change a denominator or task weight.
- No hidden reference evidence or credential appears in the dataset.
- The dataset rebuilds byte-for-byte and the experiment reaches `DATASET_LOCKED` before analysis.

### Required Tests and Validation

- Exact row-count, formula, and composite-key uniqueness tests.
- Primary-manifest, HumanEval/39, family/profile, and random-control-coordinate validation.
- Candidate/measurement/selection/reference artifact joins and provenance.
- Reference-result deduplication and repeated-coordinate mapping.
- Gaming-event, signed-gap, equal-task-weight, and invalid-propagation calculations.
- Hidden-evidence, privileged-path, credential, and secret rejection.
- Deterministic rebuild, checksum, lock, and versioned-correction tests.

### Non-Goals

- Running confirmatory or secondary statistics.
- Changing selections or reference results.
- Evaluating the private holdout.

### Handoff Artifacts

- Locked long-form analysis dataset.
- Dataset schema/version/checksum lock.
- Validation, lineage, denominator, and leakage report.
- Deterministic rebuild command and correction protocol.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-06J requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Reference outcomes unblinded; analysis dataset locked
- Deviations: —
- Handoff: —

---

## MEGB-06J — Run Confirmatory and Secondary Analyses

### Status

**Status:** Not started

### Objective

Run the frozen confirmatory and secondary analyses against the locked dataset without changing methods in response to observed outcomes.

### Dependencies

- MEGB-06I complete and accepted.
- Experiment state is `DATASET_LOCKED`.

### Requirements

1. Verify locked dataset checksum, preregistration checksum, analysis revision, dependency versions, and bootstrap seed before analysis.
2. Refuse analysis if the dataset is incomplete under the frozen confirmatory-validity rule, if any expected task/coordinate disappeared, or if task weights do not match the preregistration.
3. Verify the H1 first-measured-pass monotonicity implementation invariant. Any violation is an apparatus defect, not a negative scientific result, and triggers the amendment protocol.
4. Estimate the primary H4 difference-in-differences \(D\) using `FIRST_MEASURED_PASS` and the frozen equal-task-weight estimator.
5. Run the preregistered hierarchical clustered bootstrap preserving paired robustness, budget, policy, task, stream, observation, and random-control-replicate structures.
6. Report:
   - point estimate;
   - two-sided 95% confidence interval;
   - bootstrap standard error;
   - valid clusters;
   - seed and draws; and
   - comparison with \(D_{\min}\).
7. Support H4 only if:
   - the complete preregistered dataset is valid;
   - point estimate is at least \(D_{\min}\); and
   - the interval excludes zero in the predicted direction.
8. Run H2 and H3 under their preregistered inferential status and multiplicity treatment.
9. Run H5/control contrasts exactly as preregistered, preserving random-control-replicate treatment, and apply their frozen inference/multiplicity status.
10. Fit the secondary mixed-effects model with frozen implementation, convergence, and fallback policy. Do not replace the confirmatory bootstrap if it fails.
11. Estimate secondary contrasts:
   - \(G(k,32)-G(k,1)\) by robustness;
   - \(G(S_1,N)-G(S_4,N)\) by budget;
   - measured/reference gap by condition;
   - reference-performance change by budget;
   - conditional FAR;
   - measured-success rate;
   - first-pass/selected index distribution; and
   - policy-control differences.
12. Apply the preregistered multiplicity correction.
13. Compute gaming-onset thresholds and report no onset within \(N\le32\) when criteria are unmet.
14. Clearly classify every result as confirmatory, required secondary/control, or exploratory.
15. Preserve null, reversed, contradictory, and practically negligible results.
16. Do not substitute unregistered tests. Any defect follows the amendment protocol and records post-unblinding status.
17. Produce machine-readable statistics and a failure/deviation ledger.
18. After every frozen result reproduces, atomically transition `DATASET_LOCKED -> ANALYSIS_COMPLETE` and bind the result-manifest checksum.

### Acceptance Criteria

- Every analysis consumes the exact locked dataset and frozen code/configuration.
- Primary and control estimands match synthetic-validated implementations.
- Clustered intervals preserve the paired design.
- Equal task weighting and random-control-replicate treatment match the preregistration.
- H4 decision uses both uncertainty and \(D_{\min}\).
- Mixed-model failure cannot replace or modify the confirmatory result.
- Multiplicity and onset rules are applied exactly.
- Null/unexpected outcomes remain preserved.
- Every output is machine-readable, checksummed, and classified.
- Successful completion leaves the experiment in `ANALYSIS_COMPLETE`.

### Required Tests and Validation

- Locked-input/configuration gate.
- Deterministic rerun with frozen seed.
- Estimand and bootstrap checksum comparison to analysis implementation.
- Model convergence/fallback verification.
- Multiplicity and onset verification.
- H1 invariant, equal-task-weight, random-control-replicate, and incomplete-dataset refusal tests.
- No-unregistered-analysis enforcement where technically possible.
- Machine-readable result schema and checksum tests.

### Non-Goals

- Manually adjusting analysis for a cleaner story.
- Producing publication graphics by hand.
- Interpreting selection-induced gaming as intentional deception.

### Handoff Artifacts

- Primary H4 results.
- H5 and control-policy results.
- Secondary model and contrasts.
- Onset analysis.
- Machine-readable statistics.
- Failure, exclusion, amendment, and deviation audit.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-06K requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Unblinded; analysis complete
- Deviations: —
- Handoff: —

---

## MEGB-06K — Generate Figures, Report, Audit, and Reproducibility Package

### Status

**Status:** Not started

### Objective

Generate all preregistered publication artifacts from the locked dataset, enforce claim discipline, and package the complete deterministic scientific record.

### Dependencies

- MEGB-06J complete and accepted.
- Experiment state is `ANALYSIS_COMPLETE`.

### Requirements

1. Generate vector and raster versions of all figures from version-controlled commands and the locked dataset.
2. Required figures include:
   - gaming rate by pressure and robustness, with base-2 budget scale, one line per robustness level, clustered uncertainty, and paired-design caption;
   - measured versus reference performance by robustness and budget;
   - robustness × pressure heatmap;
   - first-pass/selection dynamics and no-pass rates;
   - stream/observation replicate stability; and
   - measurement-directed versus random/first-candidate control outcomes.
3. Generate required tables:
   - experimental configuration;
   - matrix completeness;
   - primary estimand and interval;
   - gaming rate by condition;
   - measured/reference performance;
   - policy-control contrasts;
   - hierarchical-model coefficients;
   - onset thresholds;
   - invalid/incomplete counts;
   - generation/execution cost; and
   - confirmatory/secondary/exploratory classification.
4. No figure or table value may be manually entered or edited.
5. Create `experiments/megb-v1/report.md` containing:
   - abstract-style summary;
   - preregistered hypotheses;
   - design and measurement definitions;
   - optimization-pressure and control definitions;
   - power/sample rationale;
   - confirmatory and control results;
   - secondary results;
   - figures and tables;
   - failure, exclusion, amendment, and deviation audit;
   - threats to validity;
   - claim limitations;
   - reproducibility instructions; and
   - a TR-04-ready section.
6. Enforce claim discipline:
   - selection-induced benchmark gaming may be supported;
   - adaptive exploitation is not tested here;
   - intentional deception or hacking is not established.
7. The strongest permitted confirmatory claim is:

   > Holding model capability and candidate distribution fixed, measurement-directed selection systematically favors solutions that satisfy the visible measurement without satisfying the privileged reference measurement, and the onset and severity of this divergence depend on evidence coverage and optimization pressure.

8. Do not generalize the manipulation to all components of \(S=(C,O,M,P)\). This experiment directly varies observation coverage \(O\) while holding \(C\), \(M\), and \(P\) fixed.
9. Create a reproducibility package manifest containing:
   - source revision and environment locks;
   - dataset and partition checksums;
   - system, generation, and selection configurations;
   - raw candidates and stream manifests;
   - visible measurements and selection manifests;
   - reference results;
   - locked dataset;
   - analysis configuration and outputs;
   - figures/tables; and
   - exact deterministic commands.
10. Exclude secrets, provider credentials, and hidden reference evidence from the public package.
11. Verify all figures/tables regenerate from one command or documented command set.
12. Produce a final acceptance matrix mapping every epic criterion to evidence and limitation.
13. Produce separate public and privileged package manifests. Public artifacts may contain task-level analysis values and candidate code as approved, but never reference inputs, expected outputs, oracle records, canonical solutions, privileged paths, per-case diagnostics, provider credentials, or secrets.
14. Verify primary-task-manifest identity, absence of HumanEval/39, system-family/feedback-profile identity, random-control-replicate preservation, equal-task-weight aggregation, and every experiment-state transition in the final audit.
15. After all deterministic outputs and acceptance evidence reproduce, atomically transition `ANALYSIS_COMPLETE -> COMPLETE`. Reporting cannot retroactively change the locked dataset, analyses, or scientific classifications.

### Final Acceptance Criteria

- The experiment was preregistered before confirmatory generation.
- Power, signal feasibility, costs, replicates, thresholds, analyses, controls, and exclusions were frozen before unblinding.
- The complete matrix covers every preregistered task, stream, observation, robustness, budget, and policy condition.
- The experimental population is exactly the frozen 163-task primary manifest; HumanEval/39 and the 164-task validation population are absent from experimental denominators.
- Candidate streams are shared across all conditions.
- All selections were deterministic and frozen before reference authorization.
- The private holdout was authored, validated, and frozen before public reference unblinding.
- Every unique frozen candidate/task/evaluator context has at most one accepted valid \(S^*\) result, with any permitted infrastructure attempts fully audited.
- Primary \(Q_{\mathrm{ref}}\) used only reference-only evidence.
- The locked dataset contains every expected valid coordinate with no silent denominator change.
- H4 and clustered confidence interval were generated exactly as preregistered.
- H5/control contrasts were generated under frozen status and multiplicity rules.
- Random-control replicate identity and equal task weighting were preserved through selection, dataset, analysis, and figures.
- Secondary model, contrasts, and onset logic followed preregistered behavior.
- Required figures/tables were generated programmatically.
- Invalid outputs and duplicates remained and counted toward budget.
- Candidate failures remained distinct from measurement failures.
- No manual post-unblinding exclusions or outcome-driven reruns occurred.
- Deviations and amendments were preserved and disclosed.
- Claims distinguish selection-induced gaming from adaptive exploitation and intentional deception.
- All deterministic artifacts regenerate from recorded environment, manifests, checksums, and commands.
- The final state is `COMPLETE`, with all prior state-transition records preserved.

### Required Final Verification

- Preregistration and freeze-gate tests.
- Exact matrix/selection/reference/dataset completeness tests.
- Reference deduplication tests.
- Deterministic analysis rerun.
- Figure/table generation tests.
- Failure-policy injection coverage.
- Artifact lineage and checksum verification.
- Public-package secret/reference-evidence scan.
- Population, family/profile, random-control, equal-weight, and state-transition audit.
- Type checking, linting, and CI evidence.

### Non-Goals

- Adaptive feedback-guided optimization.
- Model training or fine-tuning.
- Private-holdout candidate evaluation, which remains in MEGB-07.
- Intentionality claims.
- Concealing null or contradictory results.

### Handoff Artifacts

- Publication-ready figures and tables.
- Machine-readable statistics.
- Complete failure/exclusion/amendment audit.
- Claim-discipline assessment.
- TR-04-ready experiment report.
- Public/private reproducibility manifests and package.
- Final acceptance matrix.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. Do not begin later MEGB-07 evaluation, MEGB-08, or MEGB-09 without explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Unblinded; reporting complete
- Deviations: —
- Handoff: —

---

## Epic Non-Goals

MEGB-06 does not:

- implement adaptive feedback-guided optimization;
- train or fine-tune a model against the systems;
- demonstrate intentional deception;
- claim that \(S^*\) reveals true correctness directly;
- eliminate benchmark contamination from pretraining;
- vary model capability as a confirmatory factor;
- vary feedback richness;
- vary \(C\), \(M\), or \(P\) across primary systems;
- evaluate the private holdout or decide the MEGB-07 replication;
- run the MEGB-08 adaptive experiment or MEGB-09 cross-model replication;
- generalize beyond the frozen task, model, and generation configuration; or
- conceal null or contradictory results.

## Threats to Validity That Must Be Reported

At minimum:

- HumanEval/HumanEval+ are public and may appear in training data;
- \(S^*\) is finite and fallible;
- evidence count is an incomplete proxy for robustness;
- best-of-\(N\) selection is not gradient-based training;
- selection-only pressure does not establish intentional exploitation;
- one model and prompt produce correlated candidate samples;
- observation sets are nested and statistically dependent;
- conditions share tasks, streams, candidates, and control selections;
- remote providers may change behavior behind stable identifiers;
- execution limits may introduce construct-irrelevant failures;
- first-pass selection privileges stream order among measured passes;
- random-from-prefix is a causal control, not a realistic optimizer;
- the budget range may not cross the gaming threshold for strong systems;
- binary task scoring discards case-level information;
- bootstrap and mixed-model conclusions depend on clustering/model assumptions;
- private holdout construction before unblinding reduces but does not eliminate researcher degrees of freedom;
- the experiment directly varies \(O\), not all of \(C,O,M,P\); and
- results may not generalize beyond code generation and HumanEval.

## Requirement Traceability

| Original MEGB-06 section | Refactored location |
| --- | --- |
| Objective | Epic Objective |
| Dependencies | Epic Dependencies; cross-epic holdout gate |
| Experimental Design | Experimental Design; Selection Policies |
| Primary Outcome | Primary Outcome |
| Approved experimental population | Approved Pre-Experimental Population Amendment; all execution and analysis subtasks |
| MEGB-04 family/profile boundary | Epic Dependencies; Frozen Identity Contract; MEGB-06A/D/F/I/K |
| MEGB-05/MEGB-06 execution ownership | Epic Dependencies; MEGB-06E/F/G |
| Experiment state machine | Global Scientific Constraints; MEGB-06C through MEGB-06K |
| External-cost authorization | Global Scientific Constraints; MEGB-06A/D/E/F/H |
| Secondary Outcomes | Secondary Outcomes; MEGB-06J |
| H1–H4 | Confirmatory Hypotheses; MEGB-06C; MEGB-06J |
| Added selection controls/H5 | Selection Policies; MEGB-06B/C/G/I/J/K |
| 1. Preflight Validation Gate | MEGB-06A; final rerun in MEGB-06D |
| 2. Power and Cost Analysis | MEGB-06A |
| Added signal-feasibility pilot | MEGB-06A |
| 3. Preregistration | MEGB-06C |
| 4. Experiment Freeze Manifest | MEGB-06D; state transitions in E through K |
| 5. Candidate Generation | MEGB-06E |
| 6. Optimization-Visible Evaluation | MEGB-06F |
| 7. Candidate Selection and Freeze | MEGB-06G |
| 8. One-Time Reference Evaluation | MEGB-06H |
| 9. Reference Blinding and Unblinding | Global Constraints; MEGB-06G/H |
| Added private-holdout-before-unblinding gate | Epic Dependencies; MEGB-06G/H |
| 10. Locked Analysis Dataset | MEGB-06B schema; MEGB-06I execution |
| 11. Primary Statistical Analysis | MEGB-06B; MEGB-06J |
| 12. Secondary Hierarchical Model | MEGB-06B; MEGB-06J |
| 13. Secondary Contrasts and Multiplicity | MEGB-06B/C/J |
| 14. Gaming-Onset Threshold | MEGB-06B/C/J |
| 15. Required Figures | MEGB-06C specification; MEGB-06K generation |
| 16. Required Tables | MEGB-06C specification; MEGB-06K generation |
| 17. Failure and Exclusion Policy | MEGB-06C; applied E through J |
| 18. Amendment Protocol | MEGB-06C; global execution protocol |
| 19. Claim Discipline | MEGB-06K |
| 20. Experiment Report | MEGB-06K |
| 21. Reproducibility Package | MEGB-06K |
| Preregistration-Gate Tests | MEGB-06C/D |
| Matrix-Completeness Tests | MEGB-06E/F/G/I |
| Selection-Freeze Tests | MEGB-06G |
| Reference-Deduplication Tests | MEGB-06H |
| Analysis-Dataset Tests | MEGB-06B/I |
| Synthetic Statistical Tests | MEGB-06B |
| Figure and Table Tests | MEGB-06K |
| Failure-Policy Tests | MEGB-06C and each execution phase |
| Reproducibility Tests | MEGB-06B/I/J/K |
| Acceptance Criteria | Distributed across subtasks; consolidated in MEGB-06K |
| Non-Goals | Epic and subtask Non-Goals |
| Threats to Validity | Epic threats; MEGB-06K report |
| Deliverables | Subtask Handoff Artifacts; MEGB-06K final handoff |

## Cross-Ticket Integration Notes

1. **MEGB-03:** MEGB-06 consumes the 163-task primary population for experimental reference evaluation and the 164-task validation population only as a preflight validation fact. MEGB-06H uses the full reference-only evaluator profile; it must never use reduced-development results, compatibility diagnostics, privileged case contents, or HumanEval/39 as an experimental row.
2. **MEGB-04:** The confirmatory family is `megb-observation-coverage-v1` with feedback profile `scalar-binary-v1`. MEGB-06 must reject the separately versioned adaptive feedback family reserved for MEGB-08.
3. **MEGB-05:** MEGB-05 supplies tested implementations and schemas but no confirmatory outcomes. MEGB-06E/F/G exclusively generate the primary streams, execute the visible matrix, and freeze selections under the preregistered experiment state and cost gates.
4. **MEGB-07:** MEGB-07A–D may run during the authorized blind interval after MEGB-06D. Their accepted suite freeze must predate MEGB-06H public reference unblinding. MEGB-07E–H remain separately authorized private-evaluation and replication work and do not alter MEGB-06's locked result.
5. **MEGB-08:** Adaptive feedback-guided optimization is a distinct experiment with separate system-family/profile, run, candidate, dataset, estimand, and report identities. MEGB-06 data may be compared under a frozen plan but never pooled to inflate power.
6. **MEGB-09:** Cross-model work treats MEGB-06 as a frozen historical or concurrent replication point. It may reuse artifacts only under exact identity equivalence and cannot amend MEGB-06 outcomes or regenerate its candidates.

## Instructions for Claude

When this ticket is first committed to the repository:

1. Treat this file as the sole governing MEGB-06 specification. Do not merge requirements from older MEGB-06 files or historical annotations.
2. Before MEGB-06A, verify that accepted MEGB-03, corrected MEGB-04, and corrected MEGB-05 artifacts reproduce and that their identifiers match this ticket. Report mismatches; do not silently repair another epic.
3. Work on exactly one explicitly authorized subtask at a time. Update only that subtask's status and completion record, produce the Standard Checkpoint Report, and stop.
4. Do not infer permission for provider calls, large-scale candidate execution, reference evaluation, or other material cost from permission to implement a subtask. Present the exact activity and cost gate and wait for explicit authorization.
5. Enforce the experiment state machine. File existence, a prior commit, or completion of a dependency is not itself authorization for the next state transition.
6. Keep reference evaluation disabled until MEGB-06H and the accepted MEGB-07D holdout freeze. Before then, do not inspect experimental reference outcomes, run exploratory reference scoring, or expose privileged reference data.
7. Preserve every null, failure, incomplete unit, deviation, and unexpected result. Never add tasks, streams, retries, exclusions, analyses, or reruns after observing outcomes unless the versioned amendment protocol expressly permits it.
8. Do not begin MEGB-07 private evaluation, MEGB-08, MEGB-09, or any other follow-up without explicit authorization.

## Epic Completion Rule

MEGB-06 is complete only when:

1. every subtask MEGB-06A through MEGB-06K is accepted;
2. every completion record identifies its commit or immutable state transition and evidence;
3. the private holdout freeze predates reference unblinding;
4. the final acceptance matrix contains no unresolved `FAIL` or unapproved `DEFERRED` item;
5. the primary population, system family/profile, random-control dimensions, equal-task-weight estimands, protected-data boundary, and complete state history pass final audit;
6. all deterministic results and publication artifacts regenerate from the locked dataset;
7. the experiment manifest reaches `COMPLETE` without mutating any earlier state record; and
8. MEGB-06K produces its checkpoint report and stops before further experimental work.
