# [MEGB-07] Replicate the Gaming Result Against a Private Post-Snapshot Adversarial Holdout

## Epic Status

**Status:** Not started  
**Execution mode:** Sequential gated subtasks with a candidate-blind suite-freeze boundary  
**Subtasks:** MEGB-07A through MEGB-07H  
**Dependencies:** MEGB-01 through MEGB-06, with phase-specific gates below  
**Specification status:** Authoritative refactored ticket  
**Supersedes:** the historical monolithic MEGB-07 ticket

This document is the sole governing MEGB-07 specification once committed to the repository. Historical MEGB-07 files may be retained for audit history, but their requirements must not be combined with this ticket.

## Epic Objective

Construct a private, candidate-blind adversarial test suite and use it to replicate the MEGB-06 result without relying exclusively on public HumanEval+ evidence.

The private suite must:

- be created after the evaluated model snapshot to the extent supported by available provenance;
- remain unavailable to candidate generation and optimization;
- be constructed without inspecting experimental candidates or outcomes;
- use independently validated task-specific inputs and reference outputs;
- be reviewed and frozen before public reference unblinding;
- evaluate only candidates already selected and frozen by MEGB-06; and
- produce a separately identified private reference measurement \(Q_{\mathrm{private}}\).

The replication asks:

> Does the interaction between measurement robustness and optimization pressure replicate when candidate performance is evaluated against newly created, private, post-snapshot evidence?

## Status of This Experiment

MEGB-07 is a contamination-resistant replication of MEGB-06.

It does not replace:

- the primary MEGB-06 confirmatory result;
- MEGB-03’s reference-only result;
- the HumanEval+ compatibility diagnostic; or
- the private-suite result with a claim of direct access to correctness.

It provides an additional measurement system:

\[
S^\dagger =
(C^\dagger,O^\dagger,M^\dagger,P^\dagger),
\]

where:

- \(C^\dagger\): the same HumanEval functional-correctness construct;
- \(O^\dagger\): newly created private inputs and trusted expected outputs;
- \(M^\dagger\): the same all-cases-must-pass task-scoring rule; and
- \(P^\dagger\): isolated execution through the accepted MEGB-02 boundary or an equivalence-validated process profile.

The private evaluator remains finite and fallible. It must never be described as an infallible ground truth.

## Alignment With the Frozen Experimental Population

MEGB-07 evaluates only tasks represented in the frozen MEGB-06 experiment.

The eligible universe is the 163-task **primary_experiment_task_manifest** established by MEGB-03A.1 and consumed by MEGB-04 through MEGB-06. **HumanEval/39** is excluded a priori because it has no optimization-visible measurement, candidate stream, or gaming coordinate.

Full private coverage therefore means all 163 eligible experimental tasks—not all 164 HumanEval tasks.

If full coverage is infeasible, MEGB-07 may use a preregistered candidate-independent subset of the primary population, subject to MEGB-07A’s power, coverage, and minimum-size requirements. Every private task-set artifact and analysis must bind both:

- the frozen primary-experiment manifest checksum; and
- the frozen private-subset manifest checksum.

## Experimental and Selection-Policy Alignment

MEGB-06 contains three selection policies:

1. **FIRST_MEASURED_PASS** — the primary measurement-directed policy;
2. **RANDOM_FROM_PREFIX** — the paired candidate-availability control; and
3. **FIRST_CANDIDATE** — the no-selection control.

The primary MEGB-07 replication estimand applies to **FIRST_MEASURED_PASS**. Private outcomes for the control policies must also be retained and analyzed under the preregistered control plan. They may not be substituted for the primary replication result or pooled post hoc to rescue it.

## Primary Private Outcome

For each task \(i\) in the frozen private task set, define:

\[
q_{\mathrm{private},i}
=
\begin{cases}
1, & \text{if the frozen candidate passes every private case for task } i,\\
0, & \text{if it produces a validly measured failure},\\
\text{undefined}, & \text{if the private measurement is invalid}.
\end{cases}
\]

Let \(\mathcal{T}_{\mathrm{private}}\) be the preregistered private task set and let

\[
T_{\mathrm{private}}
=
\left|\mathcal{T}_{\mathrm{private}}\right|.
\]

Then:

\[
Q_{\mathrm{private}}(k,N,p)
=
\frac{1}{T_{\mathrm{private}}}
\sum_{i\in\mathcal{T}_{\mathrm{private}}}
q_{\mathrm{private},i}^{(k,N,p)}.
\]

A final aggregate is emitted only when every required task measurement is valid. Missing or invalid measurements preserve the frozen denominator and make the aggregate incomplete or invalid.

Define the private gaming event:

\[
G^\dagger_{i,k,N,p}
=
\mathbb{1}
\left[
q_{\mathrm{meas},i}^{(k,N,p)}=1
\land
q_{\mathrm{private},i}^{(k,N,p)}=0
\right],
\]

and aggregate private gaming rate:

\[
G^\dagger(k,N,p)
=
\frac{1}{T_{\mathrm{private}}}
\sum_{i\in\mathcal{T}_{\mathrm{private}}}
G^\dagger_{i,k,N,p}.
\]

## Primary Replication Estimand

For the primary **FIRST_MEASURED_PASS** policy, define:

\[
D^\dagger
=
\left[
G^\dagger(S_1,32)-G^\dagger(S_1,1)
\right]
-
\left[
G^\dagger(S_4,32)-G^\dagger(S_4,1)
\right].
\]

The preregistered prediction is:

\[
D^\dagger > 0.
\]

Before private evaluation, freeze:

- the minimum practically meaningful replication effect;
- the clustered uncertainty procedure;
- the required directional-consistency criterion;
- the confidence-interval criterion;
- the treatment of a smaller but directionally consistent effect;
- the status and multiplicity treatment of policy-control contrasts; and
- the rule for a null, reversed, or inconclusive replication.

Do not change the replication criterion after observing private outcomes.

## Epic Dependencies and Phase Gates

MEGB-07 depends on:

- [MEGB-01] Establish HumanEval Corpus and Privileged Evaluation Boundary;
- [MEGB-02] Implement Isolated Candidate Execution Worker;
- [MEGB-03] Implement Privileged Reference Evaluator \(S^*\);
- [MEGB-04] Implement Optimization-Visible Measurement Systems \(S_1\dots S_4\);
- [MEGB-05] Implement Controlled Candidate Generation and Selection-Only Optimization; and
- [MEGB-06] Preregister, Execute, and Analyze the Measurement-Robustness × Optimization-Pressure Experiment.

Phase-specific ordering:

1. **MEGB-07A through MEGB-07D** may begin after the evaluated model and primary experimental design are frozen. They must be completed, accepted, and checksummed before MEGB-06H authorizes public reference unblinding.
2. **MEGB-07E** may implement the private evaluator after MEGB-07D without executing experimental candidates. Its authors must remain blind to MEGB-06 candidates and public/private experimental outcomes until MEGB-07E is accepted; it should run during the blind interval whenever feasible.
3. **MEGB-07F** requires MEGB-06 selections to be frozen, MEGB-07D’s suite to remain frozen, MEGB-07E to be accepted, and the explicit private-evaluation authorization gate to pass.
4. **MEGB-07G and MEGB-07H** require the private replication dataset to be locked.

## Global Blinding and Scientific Constraints

### Candidate-blind suite construction

Before MEGB-07D freezes the suite, suite authors and construction tooling must not access:

- MEGB-06 candidate source code;
- selected candidate identities or hashes;
- optimization-visible measurements;
- MEGB-03 reference outcomes for experimental candidates;
- per-task gaming events;
- aggregate MEGB-06 outcomes;
- private pilot outcomes involving confirmatory candidates; or
- failure examples selected because they support the hypothesis.

The suite-freeze manifest must record that these sources were unavailable.

If prospective blinding has already been lost, stop. Continue only under a separately approved, deterministic, candidate-independent construction amendment that documents the loss of blinding and its consequences. Do not silently relabel retrospective construction as candidate-blind.

### No private optimization target

Private contracts, inputs, expected outputs, evaluator diagnostics, and results must not be available to:

- candidate generation;
- optimization-visible measurement systems;
- candidate selection;
- adaptive revision loops;
- ordinary public CI; or
- prompts sent to the evaluated model.

### Freeze before unblinding

The suite, contracts, cases, oracle artifacts, comparison profile, mutation-validation results, review records, storage policy, task-set manifest, and release policy must be frozen before MEGB-06 public reference outcomes are exposed.

### Candidate immutability

Private evaluation is limited to candidates already selected and frozen by MEGB-06. Private outcomes can never trigger regeneration, revision, reselection, additional candidate evaluation, or changes to the public experiment.

### Failure semantics

Candidate wrong answers, exceptions, timeouts, and resource violations are valid zero measurements when the apparatus functions correctly. Private oracle, manifest, protocol, controller, sandbox, or infrastructure failures are invalid measurements with \(q_{\mathrm{private}}=\text{None}\) and prevent final aggregation.

### Immutable scientific record

Preregistrations, protocols, private-suite versions, reviews, manifests, candidate mappings, evaluation results, locked datasets, analyses, releases, amendments, and deviations are append-only or versioned. Unexpected and contradictory results are preserved.

## Epic Execution Protocol

Work through MEGB-07A through MEGB-07H sequentially. The only permitted cross-epic concurrency is candidate-blind suite work explicitly authorized by the phase gates above.

For each authorized subtask:

1. Read the epic objective, definitions, constraints, and current subtask.
2. Inspect accepted dependency artifacts without crossing the current blinding boundary.
3. Present a short implementation or execution plan.
4. Execute only the authorized subtask.
5. Run required validation and relevant regressions.
6. Update only the current subtask status and completion record.
7. Produce the standard checkpoint report.
8. Stop and wait for explicit authorization.

Do not begin later subtasks early. Do not cross the suite-freeze, public-unblinding, private-evaluation, dataset-lock, analysis, or release gate without explicit authorization. Requirement changes require a versioned amendment.

## Standard Checkpoint Report

At every checkpoint, report:

1. **Summary:** what was implemented, reviewed, executed, or frozen.
2. **Files/artifacts changed:** including intentionally private or untracked artifacts without exposing their contents.
3. **Tests and validation:** exact commands, results, skips, and environment.
4. **Acceptance matrix:** every criterion marked PASS, FAIL, BLOCKED, or DEFERRED.
5. **Scientific state:** construction phase, blinding state, candidate-access state, and whether public/private outcomes exist.
6. **Design decisions:** choices constraining later work.
7. **Deviations/amendments:** timing and consequences.
8. **Known limitations:** unresolved engineering or scientific issues.
9. **Handoff artifacts:** paths or private identifiers, versions, hashes, and freeze states.
10. **Repository/experiment state:** branch, commit, manifests, authorizations, and next permitted transition.

Then stop. Do not begin the next subtask.

## Subtask Status

- [ ] MEGB-07A — Freeze model provenance, blinding protocol, private task set, and preregistration
- [ ] MEGB-07B — Specify task contracts and construct candidate-blind private inputs
- [ ] MEGB-07C — Build independent oracles and trusted expected-output artifacts
- [ ] MEGB-07D — Validate mutations, complete independent review, and freeze the private suite
- [ ] MEGB-07E — Implement and validate the privileged private evaluator
- [ ] MEGB-07F — Evaluate frozen candidates and lock the private replication dataset
- [ ] MEGB-07G — Run replication and public–private agreement analyses
- [ ] MEGB-07H — Generate figures, report, release artifacts, and final audit

---

## MEGB-07A — Freeze Model Provenance, Blinding Protocol, Private Task Set, and Preregistration

### Status

**Status:** Not started

### Objective

Establish the post-snapshot claim, candidate-blind authoring environment, private task population, power/cost basis, replication estimands, and release policy before constructing private cases.

### Dependencies

- Evaluated model identity and generation configuration are frozen.
- The MEGB-03A.1 primary experimental task manifest is frozen.
- MEGB-06 design, factors, policies, and analysis structure are available without experimental outcomes.
- No suite author has inspected experimental candidates or outcomes.

### Requirements

1. Record model provenance:
   - provider;
   - exact model identifier;
   - model version or snapshot where available;
   - documented release date;
   - candidate-generation dates;
   - generation-configuration checksum; and
   - evidence supporting the post-snapshot timing claim.
2. If the provider exposes no stable snapshot, state exactly what is known and limit the claim accordingly.
3. Define the authoring team, reviewers, roles, access groups, machines/environments, and audit mechanism.
4. Produce signed or otherwise attributable candidate-blind attestations covering every suite author and reviewer.
5. Verify that candidate source, selected identities, visible measurements, public reference results, gaming outcomes, and candidate-derived failure examples are inaccessible.
6. Freeze the eligible task universe as the 163-task **primary_experiment_task_manifest** and record its checksum.
7. Prefer all 163 eligible tasks when feasible.
8. If full coverage is infeasible, select a subset that:
   - contains at least 40 tasks unless the power analysis requires more;
   - uses a frozen deterministic candidate-independent algorithm;
   - covers numeric, string, sequence, collection, and logical tasks where available;
   - includes simple and constraint-sensitive specifications;
   - records selected and excluded task IDs;
   - documents every exclusion;
   - preserves the original prompt and entry point; and
   - excludes **HumanEval/39** and every task outside the primary manifest.
9. Conduct a private-replication power and cost analysis before case construction.
10. Freeze:
    - private task count;
    - minimum and target case counts;
    - minimum manually reviewed case count;
    - mutation-score threshold;
    - stream/observation/policy coverage;
    - \(D^\dagger\) practical-effect threshold;
    - clustered bootstrap and confidence-interval criteria;
    - directional replication rule;
    - policy-control analysis status;
    - multiplicity treatment;
    - missing/invalid-task policy; and
    - completion/infeasibility criteria.
11. Preregister external-model-use policy. Default: no private contract, generator, case, or expected-output content may be sent to an external generative-model API.
12. If model assistance is proposed, preregister provider/model, retention terms, relation to the evaluated model, exposed evidence, independent validation, and impact on the post-snapshot claim.
13. Preregister one release policy:
    - release after evaluation;
    - release after paper acceptance;
    - encrypted archive with delayed key disclosure; or
    - retained private suite with aggregate validation release.
14. Produce human- and machine-readable preregistration artifacts and checksums.
15. Do not construct private cases or inspect experimental artifacts in this subtask.

### Acceptance Criteria

- Model provenance supports only claims warranted by available metadata.
- Candidate-blind access restrictions and attestations are complete.
- The private task-set manifest is deterministic, checksummed, and a subset of the frozen 163-task primary population.
- **HumanEval/39** is absent.
- The task count is at least 40 unless an approved power-based amendment says otherwise.
- Power, cost, case-count, mutation, inference, failure, control, and release rules are frozen.
- Human- and machine-readable preregistrations are mutually consistent.
- No experimental candidate or outcome was accessible.

### Required Tests and Validation

- Primary-manifest identity/checksum and subset validation.
- **HumanEval/39**, out-of-manifest, duplicate, and substituted-task rejection.
- Deterministic task-selection reconstruction.
- Task-category coverage validation.
- Preregistration required-field and human/machine consistency tests.
- Power/cost arithmetic and sensitivity checks.
- Candidate-artifact access probes from authoring environments.
- Attestation and audit-record completeness.
- Snapshot-date and suite-start ordering validation.

### Non-Goals

- Reviewing task ambiguity.
- Writing private contracts or cases.
- Constructing expected outputs.
- Evaluating experimental candidates.
- Inspecting public reference outcomes.

### Handoff Artifacts

- Model-snapshot provenance record.
- Candidate-blind authoring protocol and attestations.
- Frozen private task-set manifest and checksum.
- Private-replication power/cost analysis.
- Human- and machine-readable preregistration.
- Frozen external-model-use and release policies.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-07B requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Candidate-blind; no experimental outcomes available
- Deviations: —
- Handoff: —

---

## MEGB-07B — Specify Task Contracts and Construct Candidate-Blind Private Inputs

### Status

**Status:** Not started

### Objective

Review each selected task, freeze its intended contract, and construct candidate-blind private input evidence without generating trusted outputs.

### Dependencies

- MEGB-07A complete and accepted.
- Candidate-blind authoring boundary remains intact.

### Requirements

1. Review every selected task for:
   - undefined input domains;
   - ambiguous expected behavior;
   - conflicting examples;
   - underspecified edge cases;
   - numerical-tolerance requirements;
   - permitted input mutation;
   - multiple valid outputs; and
   - disagreement between HumanEval and corrected EvalPlus interpretations.
2. Classify every selected task as one of:

       ELIGIBLE
       ELIGIBLE_WITH_DOCUMENTED_CONTRACT
       AMBIGUOUS
       EXCLUDED

3. Resolve ambiguity before case construction or exclude the task according to the preregistered policy.
4. Never resolve ambiguity by observing candidate behavior.
5. For every eligible task, create a versioned private contract defining:
   - valid input domain;
   - invalid or out-of-scope inputs;
   - relationships among arguments;
   - expected return type;
   - output-comparison semantics;
   - numerical tolerance;
   - mutation semantics;
   - determinism expectations; and
   - resource assumptions.
6. Derive contracts from the public prompt and documented benchmark interpretation, not from experimental candidates.
7. Create at least 50 unique valid private cases per included task unless the preregistration contains a task-specific approved exception.
8. Include, where valid:
   - manually constructed boundary cases;
   - common cases;
   - empty or minimum-size cases;
   - maximum or stress-oriented cases within the intended domain;
   - duplicated-value cases;
   - ordering-sensitive cases;
   - sign and zero cases;
   - Unicode or unusual-character cases;
   - floating-point edge cases;
   - off-by-one boundaries;
   - branch/condition boundaries; and
   - deterministic task-specific generator cases.
9. Design adversarial cases against candidate-independent implementation patterns:
   - hardcoded examples;
   - constant returns;
   - incomplete branching;
   - off-by-one errors;
   - wrong comparison operators;
   - duplicate handling;
   - ordering assumptions;
   - integer/float confusion;
   - empty-input failures;
   - incorrect mutation behavior;
   - inappropriate asymptotic shortcuts;
   - state retained across calls; and
   - test-order dependence.
10. Use at least ten explicitly designated manually reviewed boundary or adversarial cases per task.
11. Do not infer valid inputs solely from generic function-signature inspection.
12. Permitted design inputs are limited to:
    - the task specification;
    - corrected canonical solutions;
    - independently written nonexperimental reference solutions where already available;
    - generic mutation operators;
    - pre-experimental validation mutants; and
    - common programming-error taxonomies.
13. Enforce the frozen external-model-use policy.
14. Validate every input against its contract before acceptance.
15. Detect duplicate inputs and stable-case-ID collisions.
16. Store full private inputs only inside the approved private boundary.
17. Produce a redacted public summary containing counts, task IDs where allowed, contract statuses, provenance categories, and checksums—but no private input values.
18. Do not generate trusted expected outputs or execute experimental candidates.

### Acceptance Criteria

- Every selected task has a completed ambiguity classification.
- Only eligible or documented-contract tasks proceed.
- Every included task has a frozen versioned contract.
- Every included task meets its preregistered unique-case and manually reviewed-case minimums.
- Every case is contract-valid, candidate-blind, uniquely identified, and provenance-tagged.
- Adversarial coverage addresses the preregistered generic failure taxonomy.
- No private input appears outside the approved storage boundary.
- No experimental candidate or outcome influenced construction.
- No trusted expected output has been generated.

### Required Tests and Validation

- Contract schema/version/checksum tests.
- Contract-validation tests for every case.
- Duplicate/collision detection.
- Per-task case-count and manual-review minimums.
- Provenance and category-coverage validation.
- Deterministic generator reconstruction and changed-version sensitivity.
- External-model-use policy enforcement.
- Private-storage and public-redaction leakage tests.
- Candidate/outcome access probes.
- Explicit test that expected-output artifacts do not yet exist.

### Non-Goals

- Writing or approving expected outputs.
- Mutation scoring.
- Final independent review.
- Freezing the suite.
- Evaluating experimental candidates.

### Handoff Artifacts

- Task ambiguity review.
- Versioned private contract specifications.
- Private input generators and manually reviewed inputs.
- Private input manifest, IDs, provenance, and checksums.
- Redacted construction summary.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-07C requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Candidate-blind; no experimental outcomes available
- Deviations: —
- Handoff: —
## MEGB-07C — Build Independent Oracles and Trusted Expected-Output Artifacts

### Status

**Status:** Not started

### Objective

Construct independently validated trusted outputs for every accepted private input while preserving physical and logical separation from candidate execution.

### Dependencies

- MEGB-07B complete and accepted.
- Candidate-blind authoring boundary remains intact.
- Private contracts and input manifests are immutable for this oracle version.

### Requirements

1. For every included task, maintain:
   - the corrected EvalPlus canonical solution; and
   - a separately authored reference implementation or independently specified oracle.
2. The independent implementation must not copy the canonical solution line by line.
3. Record author, implementation provenance, source hash, task ID, contract version, and review status.
4. Execute every private input against both trusted implementations.
5. A case is oracle-eligible only when:
   - both implementations execute validly;
   - both outputs agree under the frozen comparison profile; and
   - no contract ambiguity remains.
6. Reuse the accepted MEGB-03 comparison semantics where they apply. Any private task-specific comparison rule requires a versioned, reviewed profile tied to the private contract.
7. Resolve implementation disagreements without inspecting experimental candidates.
8. Never choose the output that causes more experimental candidates to fail.
9. A contract correction, input correction, reference correction, or comparison change must increment the affected version and deterministically regenerate downstream oracle artifacts.
10. Generate expected outputs only inside the trusted private environment.
11. For every expected-output record, include:
    - schema and oracle versions;
    - task ID and private case ID;
    - private contract version;
    - input checksum;
    - expected-output checksum;
    - canonical-solution hash;
    - independent-solution hash;
    - comparison-profile ID;
    - agreement status;
    - generation environment/protocol version; and
    - generation timestamp excluded from logical identity where appropriate.
12. Store expected-output contents separately from public schemas, redacted manifests, and candidate-facing request types.
13. Expected outputs, independent implementations, canonical solutions, and comparison internals must never enter candidate execution requests.
14. Produce a composite oracle index containing counts and checksums without exposing outputs.
15. Require deterministic reconstruction from frozen inputs, implementations, comparison profiles, and environment.
16. Classify every unresolved failure explicitly. Do not freeze partial or ambiguous oracle output as release-ready.
17. Do not execute any experimental candidate.

### Acceptance Criteria

- Every eligible private case has two valid trusted evaluations in agreement.
- Every expected output is contract-bound, versioned, checksummed, and deterministically reconstructable.
- Unresolved disagreements or generation failures block release readiness.
- Trusted implementations are independently authored and provenance-recorded.
- Candidate-facing protocols have no field capable of carrying expected outputs or trusted implementation content.
- Public/redacted artifacts reveal no private input or output value.
- No experimental candidate or outcome was accessed.

### Required Tests and Validation

- Independent/canonical agreement over every private case.
- Comparison-profile determinism and tolerance tests.
- Expected-output schema, version, and checksum tests.
- Cross-process deterministic reconstruction.
- Corrupt, missing, ambiguous, and partial-oracle refusal.
- Contract/input/reference/comparison version-sensitivity tests.
- Candidate-request field-set and serialization leakage tests.
- Public composite-index redaction tests.
- Trusted/private storage-boundary tests.
- Candidate/outcome access probes.

### Non-Goals

- Mutation validation.
- Final reviewer approval.
- Suite freezing.
- Experimental-candidate execution.
- Public release of private evidence.

### Handoff Artifacts

- Independent reference implementations and provenance.
- Trusted comparison profiles.
- Private expected-output artifacts.
- Oracle composite index and checksums.
- Agreement and generation-validation report.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-07D requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Candidate-blind; no experimental outcomes available
- Deviations: —
- Handoff: —

---

## MEGB-07D — Validate Mutations, Complete Independent Review, and Freeze the Private Suite

### Status

**Status:** Not started

### Objective

Establish candidate-independent sensitivity, complete independent review, verify the private storage boundary, and atomically freeze the private holdout before public reference unblinding.

### Dependencies

- MEGB-07C complete and accepted.
- Candidate-blind authoring boundary remains intact.
- MEGB-06 public reference outcomes remain unavailable.

### Requirements

1. Build a candidate-independent mutation corpus using at least:
   - constant return;
   - deleted branch;
   - inverted conditional;
   - comparator replacement;
   - arithmetic-operator replacement;
   - boundary shift;
   - removed iteration;
   - early return;
   - incorrect initialization;
   - dropped element;
   - duplicate removal or insertion;
   - sort-order reversal; and
   - type-conversion changes.
2. Record operator version, source hash, mutation location, generation status, validity status, and equivalence classification.
3. Identify invalid and equivalent mutants separately from non-equivalent mutants.
4. For each task, compute:

   \[
   \operatorname{MutationScore}_i
   =
   \frac{
   \text{non-equivalent mutants rejected}
   }{
   \text{non-equivalent mutants evaluated}
   }.
   \]

5. Apply the preregistered minimum mutation-score threshold. The default target is at least 90 percent unless MEGB-07A froze another justified threshold.
6. Do not add cases after observing experimental candidate survival.
7. Require a second independent review for every proposed task.
8. The reviewer must verify:
   - contract consistency with the prompt;
   - input validity;
   - expected-output agreement;
   - comparison semantics and tolerances;
   - adversarial-case relevance;
   - mutation construction and equivalence classification;
   - mutation-score result;
   - candidate-blind provenance;
   - storage classification; and
   - readiness for freeze.
9. Record one review status:

       APPROVED
       APPROVED_WITH_NOTES
       REVISION_REQUIRED
       REJECTED

10. Only approved or approved-with-notes tasks satisfying the preregistered policy may enter the frozen suite.
11. If one person performs author and reviewer roles, require temporally separated passes, independent checklists, and explicit disclosure of weaker independence.
12. Recompute final task count, task-category coverage, case counts, and power after candidate-blind exclusions.
13. If the final suite violates the preregistered minimum task count, case count, power, or mutation threshold, stop and amend while still blind. Do not proceed because MEGB-06 is waiting.
14. Verify every corrected canonical and independent reference solution receives:

       q_private_task = 1.0

    for every included task.
15. Verify the private storage boundary excludes full suite content from:
    - the public repository;
    - candidate-generation environments;
    - optimizer-visible containers;
    - model prompts;
    - ordinary experiment logs;
    - public CI artifacts; and
    - public issue descriptions.
16. Require access controls, audit logging, encryption where available, versioned backups, immutable checksums, and a documented recovery procedure.
17. The public repository may retain only schemas, evaluator interfaces, aggregate metadata, approved task IDs, case counts, manifest checksums, and nonleaking summaries.
18. Freeze separate privileged artifacts for:
    - contracts;
    - private inputs;
    - independent implementations;
    - expected outputs;
    - comparison profiles;
    - mutation corpus/results; and
    - review records.
19. Create a nonsecret suite manifest containing at least:

       {
         "suite_id": "megb-private-holdout-v1",
         "suite_schema_version": "private-suite-v1",
         "evaluated_model_id": "pinned-model",
         "model_snapshot_date": "YYYY-MM-DD",
         "suite_creation_started_at": "YYYY-MM-DD",
         "suite_frozen_at": "YYYY-MM-DD",
         "primary_task_manifest_sha256": "sha256:...",
         "private_task_manifest_sha256": "sha256:...",
         "task_count": 40,
         "case_count": 2000,
         "contract_manifest_sha256": "sha256:...",
         "input_manifest_sha256": "sha256:...",
         "oracle_manifest_sha256": "sha256:...",
         "comparison_profile_sha256": "sha256:...",
         "mutation_validation_sha256": "sha256:...",
         "review_manifest_sha256": "sha256:...",
         "release_policy_sha256": "sha256:...",
         "experimental_candidates_inspected": false,
         "experimental_outcomes_inspected": false,
         "status": "FROZEN"
       }

20. The public suite manifest must not contain private inputs, expected outputs, reference implementation content, failing case IDs, or mutation details that disclose cases.
21. Verify every manifest checksum resolves to the exact frozen artifact.
22. Require a new suite version for any post-freeze change. Never overwrite or silently mutate a frozen suite.
23. Timestamp or publish the nonsecret suite identity, model-snapshot claim, task count, case count, construction protocol, suite checksum, manifest checksum, and preregistration checksum before private candidate evaluation.
24. Produce a signed freeze authorization and candidate-blind construction attestation.
25. Do not implement or run experimental candidate evaluation in this subtask.

### Acceptance Criteria

- Every included task meets the preregistered mutation threshold.
- Equivalent and invalid mutants are separated from the denominator.
- Every included task has acceptable independent review.
- Canonical and independent reference solutions pass every included private case.
- Final task/case counts, category coverage, and power satisfy the frozen plan.
- Private artifacts are access-controlled, backed up, checksummed, and absent from public/candidate environments.
- The nonsecret suite manifest resolves every frozen privileged artifact without revealing content.
- Suite construction is demonstrably candidate-blind.
- The suite was frozen and timestamped before MEGB-06 public reference unblinding.
- Any subsequent change necessarily creates a new suite version.
- MEGB-06H’s private-holdout prerequisite is satisfied.
- No experimental candidate was evaluated.

### Required Tests and Validation

- Mutation-operator behavior and version tests.
- Equivalent/invalid-mutant classification checks.
- Per-task mutation-score reconstruction and threshold enforcement.
- Canonical and independent-solution full-suite tests.
- Review-schema/status/completeness validation.
- Final task/case/power/category threshold checks.
- Candidate-blind attestation and access-audit validation.
- Private-path, environment, container, prompt, log, CI, and public-artifact leakage tests.
- Manifest-to-artifact checksum resolution.
- Freeze immutability, overwrite refusal, and version-increment tests.
- Missing/corrupt privileged artifact refusal.
- Nonsecret-manifest redaction scan.
- Freeze/public-unblinding timestamp-order test.
- Backup/recovery procedure verification without exposing contents.

### Non-Goals

- Implementing the private evaluator.
- Evaluating experimental candidates.
- Viewing MEGB-06 public reference outcomes.
- Releasing private cases.
- Revising MEGB-06 selections.

### Handoff Artifacts

- Frozen private suite and privileged artifact set.
- Mutation corpus and validation report.
- Independent review records.
- Canonical/reference full-pass evidence.
- Private storage, access, backup, and recovery policy.
- Nonsecret suite manifest and checksum.
- Candidate-blind construction attestation.
- Freeze authorization and timestamp evidence.
- MEGB-06H holdout-gate handoff.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-07A through MEGB-07D are now complete only after explicit acceptance of this checkpoint. MEGB-06H may use the accepted freeze manifest. MEGB-07E requires separate authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Suite frozen while candidate-blind; no experimental outcomes available
- Deviations: —
- Handoff: —

---

## MEGB-07E — Implement and Validate the Privileged Private Evaluator

### Status

**Status:** Not started

### Objective

Implement the trusted private evaluation boundary, typed results, redacted projections, and synthetic-tested replication-analysis pipeline without executing experimental candidates.

### Dependencies

- MEGB-07D complete and accepted.
- Frozen private-suite artifacts and manifest are available inside the privileged environment.
- MEGB-02 execution boundary is accepted.
- Experimental candidates and public/private experimental outcomes remain inaccessible to this subtask’s implementers.

### Requirements

1. Implement a private evaluator separate from MEGB-03’s \(S^*\), conceptually:

       def evaluate_private(
           evidence: PrivateTaskEvidence,
           candidate_code: str,
           context: PrivateEvaluationContext,
           *,
           backend: ExecutionBackend,
           profile: PrivateExecutionProfile,
       ) -> PrivateTaskResult:
           ...

2. Keep private evidence loading behind an explicit trusted-side adapter. Public or optimizer-visible packages must not import privileged evidence loaders.
3. Define immutable, typed, versioned, round-trip-serializable models for:
   - PrivateEvaluationContext;
   - PrivateExecutionProfile;
   - PrivateCaseEvidence;
   - PrivateTaskEvidence;
   - PrivateCaseDiagnostic;
   - PrivateTaskResult;
   - PrivateBenchmarkResult; and
   - redacted public/audit projections.
4. The evaluation context must bind:
   - suite ID and version;
   - private-suite manifest checksum;
   - primary and private task-manifest checksums;
   - contract and oracle versions;
   - comparison profile;
   - execution profile;
   - protocol/evaluator versions;
   - task ID;
   - candidate ID and SHA-256; and
   - source experiment/frozen-selection identity.
5. Verify every relevant checksum, version, task membership, candidate hash, and freeze state before execution.
6. Reject **HumanEval/39**, tasks outside the private subset, unfrozen candidates, unfrozen suites, and mismatched suite/task/candidate contexts.
7. Execute candidate code only through the accepted MEGB-02 boundary or a separately frozen process profile proven classification-equivalent and isolation-equivalent.
8. Candidate execution receives only:
   - candidate source;
   - public entry point;
   - the current private input; and
   - frozen resource limits.
9. Never pass expected outputs, future inputs, full task manifests, comparison logic, trusted implementation code, or private diagnostics into candidate execution.
10. Decode candidate outputs and compare them only after execution returns to the trusted controller.
11. Preserve per-case state isolation. A candidate may not carry writable state between private cases or infer future cases.
12. Use the frozen private comparison profile and all-cases-must-pass rule.
13. Map valid candidate wrong answers and candidate execution failures to \(q_{\mathrm{private,task}}=0\).
14. Map oracle, manifest, protocol, controller, sandbox, and infrastructure failures to \(q_{\mathrm{private,task}}=\text{None}\) with a typed invalid-measurement status.
15. Exhaustively map every execution status. Unknown statuses must fail closed.
16. Record privately at least:

       @dataclass(frozen=True)
       class PrivateTaskResult:
           schema_version: str
           suite_id: str
           suite_version: str
           task_id: str
           candidate_id: str
           candidate_sha256: str
           measurement_status: str
           q_private_task: float | None
           cases_total: int
           cases_passed: int
           first_failure_category: str | None
           execution_failure_counts: Mapping[str, int]
           contract_version: str
           comparison_profile_id: str
           execution_profile_id: str
           suite_manifest_sha256: str
           started_at: str
           duration_sec: float

17. Detailed per-case diagnostics remain privileged and in memory or approved private storage only.
18. Default redacted projections may expose only approved identifiers, versions, aggregate status, \(q_{\mathrm{private,task}}\), and nonleaking aggregate metadata.
19. Public results must never expose:
   - private inputs;
   - expected outputs;
   - failing case IDs;
   - per-case pass vectors;
   - trusted implementation content;
   - exception details containing private evidence; or
   - privileged artifact paths.
20. Implement append-only audit-record schemas and content-addressed result identities.
21. Benchmark aggregation must require the exact frozen private task set and checksum. Missing, duplicate, substituted, extra, invalid, or out-of-manifest tasks prevent a final \(Q_{\mathrm{private}}\).
22. Measure actual per-case and per-task runtime using nonexperimental fixtures and estimate private-evaluation cost. Do not weaken isolation for speed.
23. If a batched path is proposed, require explicit equivalence and adversarial-state-isolation evidence before it becomes the private evaluator’s process profile.
24. Do not load or execute any MEGB-06 experimental candidate.
25. Implement the locked-dataset schema and analysis functions before private outcomes exist.
26. Implement and synthetic-test:
    - private gaming-event calculation;
    - \(Q_{\mathrm{private}}\) and \(G^\dagger\);
    - the primary \(D^\dagger\) estimand;
    - the MEGB-06-compatible clustered bootstrap restricted to the private task set;
    - replication-criterion logic;
    - policy-control contrasts and multiplicity handling;
    - public/private agreement tables and disagreement rates;
    - the preregistered chance-corrected agreement statistic;
    - task-category summaries; and
    - figure/table data transformations.
27. Generate synthetic datasets covering positive replication, null, reversed effect, weaker directional effect, sparse events, policy-control differences, public/private disagreement patterns, and missing/invalid measurements.
28. Freeze the exact analysis-code revision, dependency versions, seed behavior, draw count, and expected synthetic outputs before MEGB-07F.
29. After this freeze, analysis changes require a versioned amendment recording whether private outcomes existed.
30. Do not calculate any statistic from experimental candidates or private experimental outcomes.

### Acceptance Criteria

- The evaluator and all result models are typed, immutable, versioned, and serializable.
- Every trusted dependency is verified before execution.
- Expected outputs and other private oracle content remain exclusively trusted-side.
- Candidate code sees only its current authorized input.
- Valid candidate failures produce zero; invalid measurements produce None.
- Unknown statuses and inconsistent contexts fail closed.
- Full private benchmark aggregation requires the exact frozen private task population.
- Redacted outputs contain no private evidence.
- Static and runtime isolation prevent candidate-generation and optimization packages from accessing the evaluator or evidence.
- Runtime/cost estimates are recorded without changing the accepted isolation boundary.
- Replication, control, and agreement analyses recover known synthetic effects and edge cases.
- The analysis-code revision and expected synthetic outputs are frozen before private evaluation.
- Evaluator and analysis implementation was completed without access to experimental candidates or outcomes.
- No experimental candidate was evaluated.

### Required Tests and Validation

- Model construction, validation, immutability, and serialization tests.
- Suite/task/candidate checksum and version mismatch refusal.
- **HumanEval/39**, out-of-subset, unfrozen-suite, and unfrozen-candidate rejection.
- Request field-set and wire-serialization tests proving no oracle content crosses the boundary.
- Correct answer, wrong answer, exception, timeout, OOM, process, output, syntax, protocol, oracle, and infrastructure classifications.
- Unknown-status completeness test.
- Current-input-only and future-input exfiltration tests.
- Cross-case state-isolation and test-order-dependence tests.
- Expected-output, path, log, exception, and redaction leakage tests.
- Exact private-task-set aggregation and denominator preservation.
- Missing/duplicate/substituted/extra/invalid task rejection.
- Static forbidden-import and runtime private-artifact access tests.
- Real isolated-execution vertical slices using synthetic or nonexperimental fixtures.
- Runtime/cost measurement and any approved batching-equivalence tests.
- Synthetic \(D^\dagger\), clustered-bootstrap, replication-criterion, and policy-control tests.
- Synthetic public/private agreement, disagreement, chance-correction, and task-category tests.
- Missing/invalid-denominator and frozen-analysis-revision tests.

### Non-Goals

- Executing experimental candidates.
- Joining public and private results.
- Running replication statistics.
- Releasing private cases.
- Changing the frozen suite.

### Handoff Artifacts

- Private evaluator implementation and trusted loader boundary.
- Typed private result and diagnostic models.
- Redacted projection schemas.
- Audit/result identity schemas.
- Isolation and leakage evidence.
- Runtime/cost feasibility report.
- Frozen synthetic-validated private-replication analysis implementation.
- Private-evaluator documentation.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-07F requires explicit authorization and cannot begin until its MEGB-06 dependencies and private-evaluation gate are satisfied.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Suite frozen; no experimental private outcomes exist
- Deviations: —
- Handoff: —

---

## MEGB-07F — Evaluate Frozen Candidates and Lock the Private Replication Dataset

### Status

**Status:** Not started

### Objective

Authorize one-time private evaluation of frozen MEGB-06 candidates, preserve complete provenance, and lock a nonleaking private-replication analysis dataset.

### Dependencies

- MEGB-07D and MEGB-07E complete and accepted.
- MEGB-06 selections and candidate manifests are frozen.
- MEGB-06H’s public reference results and locked public analysis dataset are available for authorized joining.
- The suite-freeze timestamp predates MEGB-06 public reference unblinding.
- Private evaluation is still disabled at subtask start.

### Requirements

1. Verify:
   - suite freeze manifest and checksum;
   - candidate-blind construction attestation;
   - freeze/public-unblinding timestamp order;
   - private task-set manifest and checksum;
   - MEGB-06 experiment, selection, and candidate-manifest roots;
   - every selected candidate hash;
   - accepted evaluator/comparison/execution profiles; and
   - the absence of prior private experimental results.
2. Atomically authorize private evaluation only after all gates pass.
3. Record authorization timestamp, actor, code revision, suite checksum, candidate-root checksum, and exact execution command.
4. Evaluate only candidates resolved through valid frozen MEGB-06 selection manifests for tasks in the private subset.
5. Include every preregistered selection policy and condition required by the MEGB-07A plan.
6. Never:
   - generate a candidate;
   - revise or normalize selected source differently;
   - change selection rules;
   - select using private results;
   - rerun optimization;
   - add candidates because results are surprising; or
   - change the private suite.
7. Evaluate each unique tuple once:

       (
         task_id,
         candidate_sha256,
         private_suite_version,
         private_evaluator_version,
         comparison_profile_id,
         execution_profile_id
       )

8. Reuse a valid content-addressed result wherever the same candidate was selected in multiple conditions.
9. Do not reuse incomplete, invalid, corrupt, or version-mismatched results.
10. Resume only invalid infrastructure operations under the frozen policy. Never rerun a valid measurement because its outcome is unexpected.
11. Write append-only privileged result and audit records.
12. Preserve a complete mapping from every MEGB-06 selection coordinate to its private result identity.
13. Produce execution counts, unique-candidate counts, cache/reuse counts, failures, runtime, storage, and cost.
14. Build a long-form private-replication dataset with one row per:

       (
         task_id,
         candidate_stream_id,
         observation_replicate,
         robustness_level,
         optimization_budget,
         selection_policy,
         selection_control_replicate_if_any
       )

15. Include:
   - experiment and suite identities;
   - primary/private task-manifest checksums;
   - selected candidate ID, index, and hash;
   - selection reason and policy;
   - \(q_{\mathrm{meas}}\);
   - MEGB-03 paired experimental \(q_{\mathrm{ref}}\);
   - private \(q_{\mathrm{private}}\);
   - public-reference gaming event;
   - private gaming event;
   - signed public and private task-level gaps;
   - all measurement statuses;
   - stream, observation, system, budget, and policy provenance;
   - duplicate/invalid-output indicators; and
   - source artifact/version/checksum fields.
16. Do not include private inputs, expected outputs, failing case IDs, per-case vectors, trusted implementation content, or evidence-bearing exception details.
17. Validate exact expected row count from the frozen private task set and preregistered factors.
18. Require composite-key uniqueness and complete artifact joins.
19. Preserve the frozen private denominator. Missing or invalid required rows make aggregates unavailable rather than shrinking the task set.
20. Reject **HumanEval/39**, any task outside the private subset, mismatched primary/private manifests, and any coordinate absent from the frozen MEGB-06 design.
21. Lock the canonical dataset before analysis.
22. Record dataset schema/version, row count, logical checksum, physical checksum where relevant, build command, code revision, dependency versions, and lock timestamp.
23. Any correction requires a new dataset version, documented reason, preservation of the prior version, and deterministic regeneration.
24. Stop before running replication or agreement statistics.

### Acceptance Criteria

- Private evaluation was authorized only after suite and selection freezes.
- Every evaluated candidate was frozen by MEGB-06 and belongs to a private-subset task.
- Each unique candidate/task/suite/evaluator tuple was validly evaluated no more than once.
- Duplicate selections reuse one valid result without losing coordinate provenance.
- No candidate was generated, revised, replaced, or reselected.
- Every expected coordinate maps to one private result or an explicit preregistered invalid disposition.
- Candidate failures remain distinct from private measurement failures.
- The locked dataset is complete, unique, traceable, checksummed, and free of private case content.
- Missing/invalid data never silently change the denominator.
- **HumanEval/39** and out-of-manifest tasks are absent.
- No replication statistic was run before lock.

### Required Tests and Validation

- Private-evaluation authorization and state-transition tests.
- Suite/candidate freeze and timestamp-order validation.
- Candidate-hash and selection-manifest resolution.
- **HumanEval/39** and task-manifest boundary tests.
- Unique-evaluation deduplication with repeated selected hashes.
- Invalid-result nonreuse and frozen recovery-policy tests.
- No-generation/revision/reselection enforcement.
- Exact row-count and composite-key uniqueness.
- Selection-to-private-result provenance joins.
- \(q_{\mathrm{meas}}\), \(q_{\mathrm{ref}}\), \(q_{\mathrm{private}}\), gaming-event, and signed-gap calculations.
- Selection-policy/control-coordinate coverage.
- Missing/duplicate/substituted/extra/invalid row handling.
- Hidden-evidence field and exception leakage rejection.
- Dataset lock, checksum, deterministic rebuild, and versioned-correction tests.
- Execution/reuse/cost accounting.

### Non-Goals

- Running confirmatory or agreement analyses.
- Modifying the suite.
- Evaluating nonselected candidates.
- Changing MEGB-06 outcomes.
- Releasing private evidence.

### Handoff Artifacts

- Deduplicated privileged private results and audit.
- Private-evaluation authorization record.
- Selection-to-private-result mapping.
- Locked private-replication dataset.
- Dataset validation and provenance report.
- Execution, reuse, failure, runtime, storage, and cost report.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-07G requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Private outcomes exist; replication dataset locked
- Deviations: —
- Handoff: —

---

## MEGB-07G — Run Replication and Public–Private Agreement Analyses

### Status

**Status:** Not started

### Objective

Execute the frozen private-replication and public/private agreement analyses against the locked dataset without changing methods in response to outcomes.

### Dependencies

- MEGB-07F complete and accepted.
- Private-replication dataset is locked.
- Analysis code, dependencies, seeds, thresholds, and criteria were frozen in MEGB-07E.

### Requirements

1. Verify:
   - locked dataset logical and physical checksums;
   - dataset schema and private task-set checksum;
   - preregistration checksum;
   - frozen analysis-code revision;
   - dependency versions;
   - bootstrap seed and draw count; and
   - synthetic expected-output checksums.
2. Run the primary **FIRST_MEASURED_PASS** replication analysis:

   \[
   D^\dagger
   =
   \left[
   G^\dagger(S_1,32)-G^\dagger(S_1,1)
   \right]
   -
   \left[
   G^\dagger(S_4,32)-G^\dagger(S_4,1)
   \right].
   \]

3. Use the preregistered MEGB-06-compatible clustered bootstrap restricted to \(\mathcal{T}_{\mathrm{private}}\), preserving paired task, stream, observation, robustness, budget, and policy structure.
4. Report:
   - point estimate;
   - two-sided 95 percent confidence interval;
   - bootstrap standard error;
   - valid task/stream/observation clusters;
   - seed and draws;
   - minimum replication effect;
   - directional consistency with MEGB-06;
   - private task count;
   - stream and observation replicate counts; and
   - whether the preregistered replication criterion was met.
5. Apply the frozen rule for a smaller but directionally consistent effect.
6. Report null, reversed, weaker, or inconclusive replication exactly as specified. Do not redefine success.
7. Run preregistered private-outcome analyses for **RANDOM_FROM_PREFIX** and **FIRST_CANDIDATE**.
8. Calculate policy-control contrasts under the frozen inference and multiplicity plan.
9. Do not pool MEGB-06 and MEGB-07 outcomes to manufacture significance or rescue a failed replication.
10. Compare MEGB-03 paired experimental \(q_{\mathrm{ref}}\) and private \(q_{\mathrm{private}}\) using:
    - raw task-level agreement;
    - pass/pass count;
    - pass/fail count;
    - fail/pass count;
    - fail/fail count;
    - disagreement rate;
    - agreement by robustness and budget;
    - agreement by selection policy;
    - agreement by task category; and
    - the preregistered chance-corrected statistic where informative.
11. Interpret:

        q_ref = 1, q_private = 0

    as possible public-reference insensitivity or private construct divergence—not automatic proof that the public evaluator is wrong.
12. Interpret:

        q_ref = 0, q_private = 1

    as possible private-suite insensitivity, specification difference, or incompleteness—not automatic proof that the private evaluator is wrong.
13. Investigate disagreements only through frozen non-evidence-bearing metadata and separately authorized private review.
14. Do not change either evaluator, the task set, contracts, cases, outputs, candidate selections, or locked dataset.
15. Classify analyses as primary replication, required control, secondary agreement, or exploratory exactly as preregistered.
16. Preserve null, contradictory, and unexpected outcomes.
17. Produce machine-readable results, human-readable analysis, and an append-only deviation/amendment ledger.
18. Checksum every output and record the exact deterministic command.
19. Stop before publication figure production or release-policy execution.

### Acceptance Criteria

- Every analysis consumes the exact locked dataset and frozen code/configuration.
- \(D^\dagger\), uncertainty, and replication status match the preregistered implementation.
- Cluster resampling preserves the paired design.
- Control-policy analyses and multiplicity follow the frozen plan.
- Public/private agreement is reported without designating either evaluator as infallible ground truth.
- MEGB-06 and MEGB-07 outcomes are not pooled to alter replication status.
- Null, reversed, weaker, and contradictory outcomes remain preserved.
- Every result is classified, machine-readable, checksummed, and reproducible.

### Required Tests and Validation

- Locked-input, analysis-revision, dependency, seed, and checksum gate.
- Deterministic rerun against frozen synthetic fixtures.
- \(D^\dagger\), bootstrap, interval, and replication-criterion verification.
- Policy-control contrast and multiplicity verification.
- Agreement table, disagreement rate, chance-correction, and category-summary verification.
- Missing/invalid measurement and denominator handling.
- No-pooling and no-post-outcome-method-change enforcement where technically possible.
- Machine-readable schema and output checksum tests.

### Non-Goals

- Changing the suite or evaluators.
- Re-evaluating candidates.
- Rewriting analysis code for a cleaner story.
- Producing manually edited figures.
- Releasing private cases.
- Claiming intentional deception.

### Handoff Artifacts

- Primary private replication result.
- Policy-control results.
- Public/private agreement and disagreement analysis.
- Machine-readable statistics.
- Human-readable analysis report.
- Deviation, amendment, and interpretation ledger.
- Output checksums and reproducibility commands.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-07H requires explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Private outcomes analyzed; suite remains protected
- Deviations: —
- Handoff: —

---

## MEGB-07H — Generate Figures, Report, Release Artifacts, and Final Audit

### Status

**Status:** Not started

### Objective

Generate publication artifacts from frozen results, execute the preregistered release policy, document limitations, and produce final evidence that every MEGB-07 requirement was satisfied.

### Dependencies

- MEGB-07G complete and accepted.
- Analysis outputs and deviation ledger are frozen.
- Release policy was preregistered in MEGB-07A.

### Requirements

1. Generate every figure and table programmatically from locked/checksummed artifacts.
2. Required figures:
   1. **Private gaming rate by optimization pressure and robustness**
      - same axes and visual grammar as the MEGB-06 primary figure;
      - base-2 budget scale where used in MEGB-06;
      - clustered uncertainty ribbons; and
      - paired-design caption.
   2. **Public versus private reference comparison**
      - paired \(Q_{\mathrm{ref}}\) and \(Q_{\mathrm{private}}\) curves.
   3. **Public/private disagreement heatmap**
      - disagreement rates across robustness, pressure, and policy where preregistered.
   4. **Task-level agreement matrix**
      - pass/pass, pass/fail, fail/pass, and fail/fail counts.
   5. **Mutation sensitivity summary**
      - private-suite mutation scores by task or approved category.
3. Required tables:
   - model-snapshot and suite-construction provenance;
   - private task/case coverage;
   - mutation and independent-review summary;
   - private evaluation completeness and failure counts;
   - primary replication estimate and interval;
   - private gaming rates by condition;
   - policy-control contrasts;
   - public/private agreement and disagreement;
   - runtime, storage, and cost;
   - amendments/deviations; and
   - primary/control/secondary/exploratory classification.
4. No figure or table value may be entered or edited manually.
5. Create:
   - **experiments/megb-private-v1/report.md**;
   - **docs/measurement/private-holdout.md**; and
   - a machine-readable final acceptance matrix.
6. The report must include:
   - research question and status as a replication;
   - model-snapshot provenance and claim limitation;
   - candidate-blind construction protocol;
   - task-selection and coverage rationale;
   - contracts, independent oracles, and comparison semantics;
   - mutation validation and independent review;
   - suite freeze and public-unblinding ordering;
   - private evaluator and failure semantics;
   - frozen-candidate evaluation and deduplication;
   - primary replication and policy-control results;
   - public/private agreement analysis;
   - figures and tables;
   - null, weaker, contradictory, and unexpected outcomes;
   - amendments and deviations;
   - threats to validity;
   - reproducibility instructions;
   - release-policy status; and
   - TR-04-ready text.
7. Enforce claim discipline:
   - private post-snapshot evidence reduces one contamination pathway;
   - HumanEval prompts and construct definitions remain public;
   - snapshot provenance may be imperfect;
   - the suite is finite and fallible;
   - selection-induced gaming is not intentional deception;
   - adaptive exploitation is not tested; and
   - failed or weaker replication must be reported plainly.
8. Execute exactly the preregistered release policy:
   - release the complete suite after evaluation;
   - defer release until paper acceptance;
   - publish an encrypted archive with delayed key disclosure; or
   - retain the suite privately and release aggregate validation evidence.
9. Do not release private cases before candidate selection and private evaluation are complete.
10. If release is deferred, publish or timestamp the suite ID, model-snapshot claim, task count, case count, construction protocol, manifest checksum, preregistration checksum, freeze timestamp, and release commitment.
11. Separate public and private reproducibility packages.
12. Public packages must exclude:
    - unreleased private inputs and expected outputs;
    - independent reference implementation content where protected;
    - privileged diagnostics;
    - evidence-bearing exceptions;
    - private storage paths;
    - credentials, access tokens, and provider secrets.
13. Private packages must include enough information for authorized deterministic reconstruction and independent audit.
14. Verify all figures and tables regenerate from one command or documented command set.
15. Integrate public schema, redaction, synthetic-analysis, state-machine, manifest, and release-policy tests into ordinary CI.
16. Private-content validation must run only in an explicitly privileged workflow and must fail loudly—not silently skip—when required protected inputs are unavailable.
17. Produce final privacy, access, artifact-lineage, secret, and evidence-leakage audits.
18. Produce a final acceptance matrix mapping every epic requirement to implementation, tests, evidence, freeze state, release state, and limitation.
19. Record the final source revision, environment locks, artifact checksums, commands, and completion timestamp.

### Final Acceptance Criteria

- The suite was constructed after the evaluated model snapshot to the extent supported by available evidence.
- Task selection and suite construction were candidate-blind.
- The private task set is a frozen subset of the 163-task primary experimental population and excludes **HumanEval/39**.
- Every included task has a reviewed contract and independently agreeing oracle.
- Every private case is contract-valid, uniquely identified, and checksummed.
- Every included task passes the preregistered mutation-sensitivity threshold and independent review.
- The suite was frozen before MEGB-06 public reference unblinding.
- Private evidence remained inaccessible to candidate generation, optimization, and selection.
- Only MEGB-06 frozen candidates were evaluated.
- No candidate was regenerated, revised, replaced, or reselected after private outcomes.
- Every unique candidate/task/suite/evaluator tuple was evaluated no more than once validly.
- Candidate failures remained distinct from private measurement failures.
- The private replication dataset is complete, locked, traceable, and free of private evidence.
- \(D^\dagger\), clustered uncertainty, control contrasts, and replication status were generated exactly as preregistered.
- Public/private agreement and disagreement were reported without privileging either evaluator as truth.
- Null, contradictory, or weaker private results were preserved and reported.
- Figures and tables were generated programmatically from locked artifacts.
- The release policy was executed exactly as frozen.
- Public artifacts contain no unreleased private evidence or secrets.
- The final report limits the contamination-resistance claim to private test evidence, not private task specifications or proof of correctness.
- Every deterministic authorized artifact regenerates from recorded commands, versions, and checksums.

### Required Final Verification

- Model-snapshot, task-selection, and blinding provenance checks.
- Complete contract/input/oracle/mutation/review validation.
- Suite-freeze and public-unblinding timestamp ordering.
- Private storage/access/backup/recovery audit.
- Evaluator classification, isolation, and leakage suites.
- Frozen-candidate identity and unique-evaluation deduplication.
- Exact dataset completeness, lock, and lineage checks.
- Deterministic replication and agreement analysis rerun.
- Figure/table generation tests.
- Public/private package content and secret scans.
- Release-policy state-transition tests.
- Type checking, linting, CI evidence, and privileged-workflow evidence.

### Non-Goals

- Modifying MEGB-06’s confirmatory result.
- Generating or optimizing candidates.
- Adaptive optimization.
- Intentionality or deception claims.
- Claiming the private evaluator is infallible.
- Concealing failed replication.
- Releasing private evidence contrary to the frozen policy.

### Handoff Artifacts

- Publication-ready figures and tables.
- Final MEGB-07 replication report.
- TR-04-ready replication section.
- Machine-readable statistics and acceptance matrix.
- Public/private agreement analysis.
- Privacy, access, and artifact-lineage audits.
- Public reproducibility package.
- Authorized private reproducibility package.
- Release or delayed-release artifacts.
- Final checksum and environment manifest.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. Do not begin MEGB-08 or any additional private evaluation without explicit authorization.

### Completion Record

- Status: Not started
- Commit/state transition: —
- Completed: —
- Tests: —
- Blinding state: Final analysis complete; release state recorded
- Deviations: —
- Handoff: —

---

## Epic Non-Goals

MEGB-07 does not:

- replace MEGB-06’s confirmatory experiment;
- alter MEGB-06 candidates, selections, or outcomes;
- expose the private suite as another optimization target;
- generate new model candidates;
- implement adaptive optimization;
- establish intentional deception;
- make HumanEval prompts or task specifications private;
- prove the absence of all training contamination;
- formally verify candidate correctness;
- claim that \(S^\dagger\) or \(S^*\) is infallible;
- tune private cases against experimental candidate failures;
- pool public and private outcomes post hoc to manufacture significance; or
- conceal a null, weaker, reversed, or contradictory replication.

## Threats to Validity That Must Be Reported

At minimum:

- HumanEval task prompts remain public even when tests are private;
- model snapshot dates and provider behavior may be uncertain;
- post-snapshot tests reduce but do not eliminate contamination concerns;
- a private task subset may not represent all 163 eligible tasks;
- task exclusions and ambiguity adjudication may affect representativeness;
- test authors may inherit assumptions from public canonical solutions;
- independent implementations may share conceptual errors;
- mutation score does not guarantee construct coverage;
- manually authored adversarial cases may reflect author biases;
- private test count remains a finite proxy for correctness;
- stronger private evidence may alter the intended construct;
- suite secrecy complicates immediate public reproducibility;
- smaller task sets reduce statistical power;
- private and public suites may differ in difficulty and domain coverage;
- public/private disagreement may reflect construct divergence rather than evaluator quality;
- external model assistance, if used, may weaken the post-snapshot claim;
- execution limits may introduce construct-irrelevant failure;
- control-policy candidates share underlying streams and are statistically dependent;
- the replication reuses MEGB-06 candidates and is not an independent model-generation replication; and
- results may not generalize beyond the evaluated model snapshot, task family, or selection-only regime.

## Requirement Traceability

| Original MEGB-07 section | Refactored location |
| --- | --- |
| Objective and Status of This Experiment | Epic Objective; Status of This Experiment |
| Dependencies and Blinding Requirement | Epic Dependencies and Phase Gates; Global Constraints; MEGB-07A/D/F |
| Research Question | Epic Objective |
| Primary Private Outcome | Primary Private Outcome; MEGB-07E/F/G |
| Primary Replication Estimand | Primary Replication Estimand; MEGB-07A/E/G |
| 1. Evaluated Model Snapshot | MEGB-07A |
| 2. Private Task Set | Alignment; MEGB-07A |
| 3. Task Ambiguity Review | MEGB-07B |
| 4. Private Contract Specification | MEGB-07B |
| 5. Private Input Construction | MEGB-07B |
| 6. Candidate-Blind Adversarial Design | MEGB-07B |
| 7. External Model Use | MEGB-07A/B |
| 8. Independent Reference Implementation | MEGB-07C |
| 9. Expected-Output Artifact | MEGB-07C |
| 10. Mutation Validation | MEGB-07D |
| 11. Private Suite Review | MEGB-07D |
| 12. Private Storage Boundary | Global Constraints; MEGB-07D/E/H |
| 13. Private Suite Manifest | MEGB-07D |
| 14. Private Evaluator | MEGB-07E |
| 15. Private Result Schema | MEGB-07E |
| 16. Frozen-Candidate Evaluation | MEGB-07F |
| 17. Private Replication Dataset | MEGB-07E schema; MEGB-07F lock |
| 18. Private Replication Analysis | MEGB-07A/E/G |
| 19. Public–Private Agreement Analysis | MEGB-07E/G |
| 20. Required Figures | MEGB-07E transformations; MEGB-07H |
| 21. Release Policy | MEGB-07A/D/H |
| Privacy-Boundary Tests | MEGB-07B/D/E/H |
| Contract and Oracle Tests | MEGB-07B/C/D |
| Canonical-Solution Tests | MEGB-07D |
| Mutation Tests | MEGB-07D |
| Freeze Tests | MEGB-07D/F/H |
| Candidate-Freeze Tests | MEGB-07F |
| Measurement-Failure Tests | MEGB-07E/F |
| Analysis Tests | MEGB-07E/G/H |
| Acceptance Criteria | Distributed across subtasks; consolidated in MEGB-07H |
| Non-Goals | Epic and subtask Non-Goals |
| Threats to Validity | Epic threats; MEGB-07H report |
| Deliverables | Subtask Handoff Artifacts; MEGB-07H final handoff |

## Epic Completion Rule

MEGB-07 is complete only when:

1. every subtask MEGB-07A through MEGB-07H is accepted;
2. MEGB-07D’s suite-freeze timestamp predates MEGB-06 public reference unblinding;
3. every completion record identifies its commit or immutable state transition and evidence;
4. the private dataset and analysis inputs are locked;
5. the final acceptance matrix contains no unresolved FAIL or unapproved DEFERRED item;
6. the preregistered release policy is executed and recorded;
7. every public artifact passes privacy, evidence-leakage, and secret scans;
8. all deterministic authorized results and publication artifacts regenerate from frozen inputs; and
9. MEGB-07H produces its checkpoint report and stops before MEGB-08.




---
