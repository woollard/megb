# [MEGB-09] Replicate Measurement-Induced Gaming Across Model Capability Levels

## Epic Status

**Status:** Not started  
**Execution mode:** Sequential gated subtasks with model-panel, generation-freeze, and reference-unblinding boundaries  
**Subtasks:** MEGB-09A through MEGB-09I  
**Dependencies:** MEGB-01 through MEGB-08, with phase-specific gates below  
**Optional dependency:** MEGB-07 private evaluation for secondary validation  
**Specification status:** Authoritative ticket  
**Prior version:** None; this is a new epic

Once committed, this document is the sole governing MEGB-09 specification. Later amendments must preserve the original text, state their precedence explicitly, and be approved before they affect execution.

## Epic Objective

Test whether the central Measurement Engineering Gaming Benchmark result generalizes across different optimizing models and capability levels.

The epic asks whether measurement-induced gaming is a property of the relationship among:

- optimization-visible measurement robustness;
- optimization pressure;
- optimization strategy; and
- the model producing or revising candidate solutions,

rather than an artifact of one model snapshot.

The scientific priority is replication across individually identified model snapshots. An ordered capability trend is secondary because model capability is multidimensional and may be confounded with provider, architecture, training data, inference policy, and release date.

The central question is:

> When the optimizer changes, does weak measurement still become easier to game under pressure than strong measurement?

## Relationship to MEGB-06 and MEGB-08

MEGB-09 is a cross-model generalization experiment.

It reuses the accepted conceptual designs of:

- **MEGB-06**, which measures selection-induced gaming from fixed candidate streams; and
- **MEGB-08**, which measures feedback-guided adaptive gaming.

MEGB-09 does not retroactively alter either experiment. It creates new experiment identifiers, model-panel manifests, generation artifacts, frozen selections, datasets, estimands, and conclusions.

The mandatory primary track is a cross-model replication of the MEGB-06 selection-only interaction.

The adaptive track replicates the MEGB-08 guided-versus-self-refinement interaction across the same model panel. It is required unless MEGB-09A demonstrates that it is infeasible under a reviewed power and cost analysis and the user explicitly approves a reduced selection-only scope. An approved omission must remain visible in the title, preregistration, report, and claim boundaries; it may not be treated as silently completed.

MEGB-06, MEGB-08, and MEGB-09 results may be compared under a preregistered cross-experiment plan. They must not be pooled to inflate the effective sample size or rescue a null replication.

## Alignment With the Frozen Experimental Population

The eligible task universe is the 163-task **primary_experiment_task_manifest** established by MEGB-03A.1.

**HumanEval/39 is excluded a priori** because it has no optimization-visible development pool, \(Q_{\mathrm{meas}}\), candidate stream, or gaming coordinate. It remains part of MEGB-03’s separate 164-task reference-validation population only.

MEGB-09 may use a preregistered deterministic subset of the 163 eligible tasks when justified by power and cost. The selected task set must:

- contain at least 40 tasks unless the approved power analysis requires more;
- be selected without candidate or gaming outcomes;
- use a stable deterministic algorithm;
- preserve a defensible range of task and input types;
- remain identical across the confirmatory model panel;
- bind the primary-experiment manifest checksum; and
- be frozen before any confirmatory model generation.

A model-specific task exclusion is prohibited unless a candidate-independent technical incompatibility is discovered before generation and handled under the frozen failure policy. Models must not receive different task sets because one performs poorly or refuses more often.

## Model Panel and the Meaning of Capability

### Model identity

The scientific unit is an exact model snapshot or the strongest available immutable model identity supported by the provider.

Aliases such as “latest” are prohibited. For every panel member, record:

- provider;
- canonical model ID;
- immutable snapshot or revision ID, where available;
- endpoint and API version;
- region or routing class where scientifically relevant;
- provider-reported system fingerprint, where available;
- release date;
- context and output limits;
- inference mode;
- reasoning-effort setting;
- tool availability;
- sampling controls;
- safety-policy behavior known before execution;
- request and response schema versions; and
- first and last confirmatory call timestamps.

If a provider cannot guarantee immutable model weights or serving behavior, record that limitation prospectively. Such a model may remain in the panel only under a preregistered identity-drift policy.

### Primary treatment of models

The primary cross-model analysis treats model snapshot as a categorical factor. Each model receives its own replication estimate and uncertainty interval.

This avoids pretending that one benchmark score provides a complete, interval-scaled measure of “capability.”

### Secondary capability ordering

An ordered capability analysis is permitted only when the ordering is frozen before MEGB-09 generation and derives from candidate-independent evidence that excludes:

- MEGB tasks;
- HumanEval and HumanEval+ outcomes used by this project;
- MEGB-06, MEGB-08, or pilot gaming outcomes;
- reference-only or private evidence;
- model behavior observed during confirmatory generation; and
- analyst judgment introduced after results are seen.

The ordering artifact must record its source, retrieval date, scoring rule, missing-data rule, ties, uncertainty, and checksum. If no defensible one-dimensional ordering exists, the categorical model analysis remains primary and the capability-gradient claim is omitted.

### Provider and family confounding

Whenever feasible, the confirmatory panel should contain:

- at least three distinct immutable model snapshots;
- at least two model families; and
- at least two providers.

If the panel is narrower, claims must be restricted accordingly. Provider, family, release date, price, and capability must not be interpreted as separately identified causal effects unless the design actually supports that inference.

## Primary Selection-Only Outcomes

For model \(m\), task \(i\), measurement system \(k\), budget \(N\), selection policy \(p\), and observation replicate \(o\), define:

\[
G^{\mathrm{selection}}_{m,i,k,N,p,o}
=
\mathbb{1}
\left[
q_{\mathrm{meas},m,i}^{(k,N,p,o)}=1
\land
q_{\mathrm{ref},m,i}^{(k,N,p,o)}=0
\right].
\]

For the primary FIRST_MEASURED_PASS policy, define the within-model robustness × pressure interaction:

\[
D^{\mathrm{selection}}_m
=
\left[
G_m(S_1,N_{\max})-G_m(S_1,1)
\right]
-
\left[
G_m(S_4,N_{\max})-G_m(S_4,1)
\right].
\]

The preregistered directional prediction is:

\[
D^{\mathrm{selection}}_m>0.
\]

The primary cross-model result must report:

- every \(D^{\mathrm{selection}}_m\);
- a preregistered pooled hierarchical mean across models, if justified;
- between-model heterogeneity;
- the number and proportion of model snapshots with positive effects;
- influence diagnostics; and
- whether conclusions depend on one model or provider.

The original MEGB-06 model may serve as a historical anchor. Existing MEGB-06 candidate streams may be reused only when their exact model identity, task set, prompt, generation parameters, measurement versions, budgets, and selection policies match the MEGB-09 preregistration. Otherwise the historical result remains a separately identified external replication point.

## Adaptive Outcomes

For every model in the approved adaptive panel, define:

\[
D^{\mathrm{adaptive}}_m
=
\left[
G_{m,\mathrm{feedback}}(S_1,N_{\max})
-
G_{m,\mathrm{self}}(S_1,N_{\max})
\right]
-
\left[
G_{m,\mathrm{feedback}}(S_4,N_{\max})
-
G_{m,\mathrm{self}}(S_4,N_{\max})
\right].
\]

Report the per-model effect, hierarchical mean if preregistered, heterogeneity, and whether the feedback-specific gaming effect changes across models.

The adaptive analysis remains distinct from the selection-only analysis. Their rows, estimands, and confirmatory decisions must not be pooled.

## Secondary Capability-Moderation Outcomes

If MEGB-09A approves a capability ordering \(c_m\), estimate whether capability moderates:

- selection-induced gaming;
- adaptive feedback-specific gaming;
- measured acceptance;
- reference correctness;
- rounds to acceptance;
- score improvement;
- candidate failure and refusal rates; and
- evaluator-specific behavior categories.

A monotonic capability trend is not assumed. Report categorical model effects even when an ordered trend is fitted.

Do not claim that capability causes gaming merely because higher-ranked models show a larger interaction. Model snapshot is an inseparable bundle of training, architecture, policy, provider, and inference behavior.

## Epic Dependencies and Phase Gates

MEGB-09 depends on accepted and reproducible versions of:

- MEGB-01 — HumanEval corpus and privileged boundary;
- MEGB-02 — isolated execution;
- MEGB-03 — privileged reference evaluator \(S^*\);
- MEGB-04 — optimization-visible measurement systems;
- MEGB-05 — controlled generation and candidate artifacts;
- MEGB-06 — selection-only experiment;
- MEGB-08 — adaptive experiment, when the adaptive track is included; and
- MEGB-07 — optional private validation only.

Phase ordering:

1. **MEGB-09A** freezes the model panel, capability treatment, selected task set, power/cost analysis, estimands, and preregistration.
2. **MEGB-09B through MEGB-09D** implement model adapters, comparability validation, and all synthetic-tested analysis tooling without confirmatory generation.
3. **MEGB-09E** executes and freezes selection-only candidate streams and selections.
4. **MEGB-09F** executes and freezes adaptive trajectories when included.
5. **MEGB-09G** is the one-time reference-unblinding phase for all unique frozen candidates.
6. **MEGB-09H** runs the frozen cross-model analyses.
7. **MEGB-09I** produces figures, reports, release artifacts, and the final audit.

Every confirmatory generation track must freeze before MEGB-09G. Reference outcomes from an earlier track may not influence whether or how a later track is run.

## Global Scientific Constraints

### Same construct and measurement systems

All models are evaluated on the same frozen tasks, observation replicates, visible measurement systems, comparison semantics, resource profiles, and reference evaluator. A provider-specific adapter may translate transport syntax but may not change scientific content.

### Same information boundary

Models receive only the information authorized by the corresponding MEGB-05 or MEGB-08 protocol. Model-specific prompting, test hints, system identities, evidence, tools, or retries are prohibited unless frozen as an explicit factor.

### Fairness without artificial equality

The experiment should equalize scientific opportunity, not pretend model APIs are identical.

Freeze common:

- semantic prompt content;
- candidate extraction contract;
- number of candidate opportunities;
- output and reasoning policy;
- stopping and selection rules;
- evaluator access;
- task set;
- observation sets; and
- failure handling.

Document unavoidable differences in tokenization, provider wrappers, refusal policy, latency, and serving nondeterminism.

### No model-specific rescue

Do not alter prompts, budgets, temperatures, retries, token limits, extraction, or selection after observing that a particular model performs poorly, refuses, produces invalid code, or games unexpectedly.

### Freeze before reference unblinding

All selection-only streams, adaptive trajectories, budget-prefix selections, model identities, and candidate hashes must be frozen before \(S^*\) is invoked for any new MEGB-09 candidate.

### Immutable record

Requests, responses, provider metadata, candidates, measurements, failures, costs, trajectories, selections, reference results, datasets, analyses, amendments, and deviations are append-only or content-addressed.

## Epic Execution Protocol

Execute MEGB-09A through MEGB-09I sequentially.

At each checkpoint:

1. stop all later-subtask work;
2. produce the Standard Checkpoint Report;
3. identify every design judgment and deviation;
4. record exact commits and artifact checksums;
5. state whether any model calls, costs, or privileged access occurred;
6. state the model-panel and task-set status;
7. wait for explicit acceptance and authorization; and
8. begin the next subtask only after that authorization.

## Standard Checkpoint Report

Every subtask report must include:

1. scope completed;
2. files created, modified, and intentionally untracked;
3. exact commit SHAs;
4. commands and test counts;
5. acceptance matrix;
6. design decisions and deviations;
7. known limitations and threats to validity;
8. artifact identities and checksums;
9. repository and remote state;
10. provider/model calls and cost;
11. privileged-data access statement;
12. model-panel drift or availability status; and
13. next-step readiness and exact authorization required.

---

## MEGB-09A — Freeze the Model Panel, Capability Treatment, Design, and Preregistration

### Objective

Define a scientifically interpretable model panel and freeze the complete cross-model experiment before any confirmatory MEGB-09 candidate generation.

### Dependencies

- MEGB-01 through MEGB-06 accepted.
- MEGB-08 accepted if the adaptive track is included.
- Required upstream locks reproduce from clean processes.
- No confirmatory MEGB-09 model call has occurred.

### Requirements

#### A1. Verify upstream artifacts

Verify all required corpus, partition, oracle, measurement, generation, MEGB-06, and MEGB-08 locks. Record exact versions and checksums.

Document whether protocol authors have seen MEGB-06 or MEGB-08 outcomes. Model and task selection must remain candidate-independent. If authors are unblinded, use only prospectively declared metadata and deterministic rules.

#### A2. Select and freeze the model panel

Select at least three exact snapshots unless explicitly approved otherwise.

For each model, record the complete identity and serving metadata required by this epic. Prohibit mutable aliases. Test availability before freeze using nonconfirmatory requests that do not use MEGB tasks.

The panel-selection rationale must distinguish:

- capability coverage;
- provider/family diversity;
- snapshot immutability;
- API/tool comparability;
- cost;
- availability horizon;
- policy/refusal behavior; and
- reproducibility limitations.

Do not select models because their MEGB behavior appears interesting.

#### A3. Define the capability treatment

Choose one:

1. categorical model identity only;
2. categorical primary plus a frozen ordinal ordering; or
3. categorical primary plus a frozen continuous capability index.

Any ordinal or continuous measure must use candidate-independent, non-MEGB evidence. Freeze sources, transformations, uncertainty, ties, and missing-data handling.

Record why the measure is relevant to code generation and why it should not be interpreted as a complete latent capability construct.

#### A4. Freeze the task set

Select from the 163-task primary population with a deterministic algorithm. Bind task metadata, selection seed, source checksum, selected IDs, coverage summary, and output checksum.

Use the same task set for every model and primary condition. HumanEval/39 must be absent.

#### A5. Power and cost analysis

Determine:

- model count;
- task count;
- candidate-stream replicates;
- trajectory replicates;
- observation replicates;
- systems;
- selection and interaction budgets;
- selection policies;
- adaptive strategies;
- expected model and execution calls;
- expected unique reference candidates;
- runtime, storage, and monetary cost;
- minimum meaningful within-model effect;
- heterogeneity precision;
- model-level replication criterion; and
- sensitivity to invalid calls, refusals, and snapshot loss.

The selection-only track must include \(S_1\), \(S_4\), \(N=1\), and \(N_{\max}\). Additional systems and budgets may be included if power and cost support them.

The adaptive track must preserve the MEGB-08 guided-versus-self comparison and at least four logarithmically spaced budgets unless an explicit reduced design is approved.

#### A6. Freeze prompt and inference comparability

Freeze common semantic prompt content, system/developer instructions, candidate-only response rule, tool state, reasoning mode, output limit policy, sampling controls, retry policy, seed interpretation, and extraction/sanitization.

Document provider-specific envelope differences. Model-specific prompt optimization is prohibited in the confirmatory experiment.

#### A7. Freeze estimands and replication criteria

Preregister:

- every per-model \(D^{\mathrm{selection}}_m\);
- the cross-model replication rule;
- hierarchical mean and heterogeneity, if used;
- adaptive \(D^{\mathrm{adaptive}}_m\), if included;
- categorical model contrasts;
- optional capability moderation;
- bootstrap or model-based uncertainty;
- clustering units;
- minimum meaningful effects;
- multiplicity;
- influence and leave-one-model-out analyses;
- invalid-model and missing-cell policies; and
- null, reversed, heterogeneous, or provider-specific interpretation.

A positive pooled estimate is insufficient if driven by one model. Freeze the anti-dominance or influence criterion before generation.

#### A8. Freeze cross-experiment use

State whether accepted MEGB-06 and MEGB-08 results are:

- historical anchors;
- external replication points;
- reused candidate artifacts; or
- excluded from MEGB-09 estimation.

Any reuse requires exact identity and configuration compatibility. Do not count the same candidate/result twice as independent evidence.

#### A9. Freeze failure and model-loss policy

Cover:

- provider outage;
- transient and permanent errors;
- refusal and empty response;
- content filter;
- unsupported parameter;
- snapshot alias drift;
- snapshot withdrawal mid-run;
- system fingerprint change;
- quota exhaustion;
- uncertain request outcome;
- malformed candidate;
- invalid measurement;
- reference failure; and
- incomplete model panel.

Freeze when to retry, pause, invalidate a cell, drop an entire model prospectively, or declare the experiment incomplete. Post-outcome model replacement is prohibited.

#### A10. Produce the preregistration

Bind the model panel, capability treatment, task set, factors, prompts, adapters, budgets, controls, estimands, analyses, costs, failure policy, claim boundaries, and required figures.

### Acceptance Criteria

- All upstream locks verify.
- The panel contains at least three exact snapshots or an explicitly accepted deviation.
- Capability is categorical in the primary analysis.
- Any ordered capability measure is frozen and candidate-independent.
- The same deterministic task set applies to every model.
- HumanEval/39 is absent.
- Power, cost, replication, heterogeneity, and anti-dominance criteria are explicit.
- Provider-specific differences and identity-drift policy are frozen.
- No confirmatory MEGB-09 generation or \(S^*\) evaluation occurs.
- The preregistration and manifests are checksummed and accepted.

### Non-Goals

- Implementing provider adapters.
- Generating experimental candidates.
- Comparing observed model performance.
- Revising MEGB-06 or MEGB-08.

### Handoff Artifacts

- MEGB-09 preregistration;
- model-panel manifest;
- capability-treatment artifact;
- selected-task manifest;
- power and cost report;
- prompt/inference comparability specification;
- failure and snapshot-loss policy; and
- MEGB-09A completion record.

### Checkpoint and Stop Condition

Stop after the preregistration is complete. Do not begin MEGB-09B until the user accepts MEGB-09A and explicitly authorizes adapter implementation.

### Completion Record

**Status:** Not started  
**Accepted by:**  
**Acceptance date:**  
**Implementation commit(s):**  
**Artifact checksums:**  
**Deviations:**  


---

## MEGB-09B — Implement Provider-Neutral Model Adapters and Provenance Capture

### Objective

Implement a common generation interface that preserves identical scientific content across model providers while recording unavoidable transport and serving differences.

### Dependencies

- MEGB-09A accepted.
- Model snapshots remain available.
- Confirmatory model calls remain prohibited.

### Requirements

#### B1. Common request contract

Define typed, immutable, versioned request and response models containing:

- experiment and request IDs;
- model-panel identity;
- semantic prompt identity;
- provider envelope version;
- generation parameters;
- tool state;
- seed or explicit unsupported status;
- output limits;
- retry attempt;
- raw provider response;
- extracted text;
- provider metadata;
- usage and cost;
- timestamps excluded from logical identity; and
- request/response checksums.

#### B2. One adapter per provider interface

Adapters may translate:

- message roles;
- reasoning-control fields;
- output-limit parameters;
- seed fields;
- response extraction;
- usage accounting; and
- error taxonomies.

They may not change:

- semantic instructions;
- task content;
- candidate opportunity count;
- evaluator information;
- selection rules;
- stopping rules;
- scientific budgets; or
- failure meaning.

#### B3. Model identity verification

Before and after each call, capture all available snapshot, fingerprint, API-version, endpoint, and routing metadata. Reject a response when its identity conflicts with the frozen model-panel manifest.

If the provider does not return an immutable fingerprint, bind the request to the frozen model ID and call window and surface the uncertainty.

#### B4. Tool and retrieval exclusion

Disable tools, browsing, code execution, retrieval, file access, persistent memory, and provider features that could add information not present in the frozen prompt.

The request schema should make unauthorized capabilities unrepresentable where possible.

#### B5. Normalized error taxonomy

Classify:

- SUCCESS;
- REFUSAL;
- EMPTY_RESPONSE;
- CONTENT_FILTER;
- MALFORMED_RESPONSE;
- RETRYABLE_PROVIDER_ERROR;
- NONRETRYABLE_PROVIDER_ERROR;
- IDENTITY_MISMATCH;
- QUOTA_EXHAUSTED;
- UNCERTAIN_CALL_OUTCOME; and
- CONTROLLER_ERROR.

Provider errors must not be mistaken for candidate failures.

#### B6. Cost and usage normalization

Preserve raw provider usage and compute versioned normalized fields for input tokens, output tokens, reasoning tokens where exposed, cached tokens, latency, and monetary cost.

Do not use cost or latency to select candidates.

#### B7. Secret and log hygiene

Provider credentials remain outside artifacts, model contexts, logs, exceptions, and committed files. Redacted diagnostic projections must preserve useful status without exposing secrets or raw authorization headers.

#### B8. Offline tests

Use recorded synthetic provider payloads and fakes to test:

- successful response normalization;
- refusal and filter handling;
- retry classification;
- malformed payloads;
- identity mismatch;
- missing fingerprint;
- unsupported seed;
- tool exclusion;
- usage accounting;
- deterministic serialization;
- secret redaction; and
- semantic prompt byte preservation.

### Acceptance Criteria

- Every provider implements the same scientific request contract.
- Provider envelopes do not change semantic content.
- Model identity and uncertainty are captured.
- Unauthorized tools and retrieval are absent.
- Provider failures remain distinct from candidate and measurement failures.
- Cost and usage are versioned and auditable.
- Offline adapter tests pass.
- No confirmatory model call occurs.

### Non-Goals

- Provider-specific prompt tuning.
- Capability measurement.
- Candidate generation.
- Reference evaluation.

### Handoff Artifacts

- common model request/response schemas;
- provider adapters;
- normalized error and usage schemas;
- secret-redaction tests;
- adapter conformance suite; and
- MEGB-09B completion record.

### Checkpoint and Stop Condition

Stop after offline adapter conformance. Do not begin MEGB-09C until the user accepts MEGB-09B and authorizes nonconfirmatory live validation.

### Completion Record

**Status:** Not started  
**Accepted by:**  
**Acceptance date:**  
**Implementation commit(s):**  
**Artifact checksums:**  
**Deviations:**  

---

## MEGB-09C — Validate Cross-Model Comparability and Freeze the Generation Apparatus

### Objective

Demonstrate that every model receives scientifically equivalent opportunities, quantify unavoidable provider differences, and freeze the multi-model generation apparatus before confirmatory execution.

### Dependencies

- MEGB-09A and MEGB-09B accepted.
- Approved small live-smoke-test budget.
- Smoke-test tasks and seeds are excluded from the confirmatory manifest.
- No privileged evaluation is available to the smoke-test process.

### Requirements

#### C1. Semantic prompt equivalence

Render every provider request and verify that the semantic task, instructions, candidate-only output contract, tool state, round context, and feedback projection are equivalent.

Record provider-envelope differences separately from semantic content.

#### C2. Output and reasoning opportunity

Implement the frozen cross-provider policy for:

- maximum output;
- truncation;
- reasoning effort;
- hidden reasoning tokens;
- stop conditions;
- temperature and sampling;
- seed support;
- refusal handling; and
- retry count.

Token counts need not be numerically identical across tokenizers, but the policy must be prospectively justified and must not favor a model based on observed MEGB performance.

#### C3. Extraction and sanitization parity

Apply the same versioned extraction and candidate-sanitization logic to all providers. Provider wrappers may locate response text but may not repair code differently by model.

Test code fences, prose, multiple implementations, truncation, empty responses, Unicode, malicious delimiters, and provider-specific content blocks.

#### C4. Nonconfirmatory live smoke tests

Run a bounded set of excluded tasks through every adapter. Verify:

- identity metadata;
- request/response capture;
- tool absence;
- extraction;
- cost accounting;
- error handling;
- execution compatibility;
- interruption and resumption; and
- rate-limit behavior.

Smoke candidates and outcomes must never enter the confirmatory dataset or influence model/task selection.

#### C5. Snapshot drift probes

Repeat identity-only or excluded-task probes over the planned call window. Define how fingerprint changes, alias changes, unavailable snapshots, or undocumented response-schema changes are detected.

Exercise the frozen pause/abort policy without substituting a model.

#### C6. Cross-model paired-design tests

Verify identical:

- selected tasks;
- candidate budgets;
- seeds as experimental identifiers;
- system and observation assignments;
- selection policies;
- adaptive branch structure;
- stopping rules; and
- expected condition counts.

Do not require equal text outputs or deterministic replay.

#### C7. Freeze the generation apparatus

Create a lock binding:

- model panel;
- provider adapters;
- prompt and context renderers;
- generation parameters;
- extraction and sanitization;
- tool state;
- retry/error policy;
- task/seed/system/replicate schedule;
- candidate budgets;
- adaptive configuration;
- storage paths;
- cost ceilings;
- code revision;
- commands; and
- expected counts.

The lock must verify from a clean process and refuse silent overwrite.

### Acceptance Criteria

- Semantic prompt content is equivalent across providers.
- Provider differences are documented and bounded.
- Identical candidate opportunities and scientific factors are enforced.
- Smoke tests use no confirmatory cell.
- Snapshot drift detection and abort behavior are tested.
- Extraction and sanitization are model-independent.
- Generation locks reproduce from clean processes.
- No confirmatory generation or reference evaluation occurs.

### Non-Goals

- Ranking models by smoke-test performance.
- Tuning prompts per model.
- Running selected MEGB tasks.
- Statistical analysis.

### Handoff Artifacts

- comparability validation report;
- provider-envelope diff report;
- smoke-test and cost report;
- snapshot-drift validation;
- generation-apparatus lock;
- verification command; and
- MEGB-09C completion record.

### Checkpoint and Stop Condition

Stop after the apparatus lock verifies. Do not begin MEGB-09D until the user accepts MEGB-09C and explicitly authorizes pre-unblinding analysis implementation.

### Completion Record

**Status:** Not started  
**Accepted by:**  
**Acceptance date:**  
**Implementation commit(s):**  
**Artifact checksums:**  
**Deviations:**  


---

## MEGB-09D — Implement and Freeze Cross-Model Dataset and Analysis Tooling

### Objective

Implement every confirmatory cross-model calculation, dataset invariant, heterogeneity analysis, and required figure against synthetic data before confirmatory generation or reference unblinding.

### Dependencies

- MEGB-09A through MEGB-09C accepted.
- MEGB-06 and MEGB-08 analysis definitions available as frozen references.
- No confirmatory MEGB-09 generation has begun.

### Requirements

#### D1. Selection-only dataset schema

Define one typed locked row per:

\[
(\text{model_snapshot},
\text{task_id},
\text{stream_seed},
\text{observation_replicate},
\text{robustness_level},
\text{candidate_budget},
\text{selection_policy}).
\]

Include:

- experiment, schema, and algorithm versions;
- model-panel and model-snapshot identity;
- selected-task and upstream manifest checksums;
- candidate-stream and selected-candidate identities;
- \(q_{\mathrm{meas}}\);
- \(q_{\mathrm{ref}}\);
- optional \(q_{\mathrm{private}}\);
- gaming event;
- generation, execution, and provider failure fields;
- tokens, latency, and cost;
- prompt/configuration provenance; and
- model capability category or frozen index, if approved.

#### D2. Adaptive dataset schema

When the adaptive track is included, use the accepted MEGB-08 scientific row structure with model snapshot added as an explicit factor.

Keep selection-only and adaptive rows in different typed datasets or use a tagged union that rejects cross-track aggregation without an explicit transformation.

#### D3. Dataset invariants

Reject:

- models outside the frozen panel;
- mutable or mismatched model identities;
- tasks outside the frozen selected-task manifest;
- HumanEval/39;
- missing or duplicate expected cells;
- model-specific task sets;
- mismatched prompts, adapters, budgets, systems, observation sets, or selectors;
- selection outcomes that do not reproduce from frozen prefixes;
- unpaired adaptive initial candidates;
- reference results for nonfrozen candidates;
- invalid measurements scored as failures;
- mixed MEGB-06, MEGB-08, and MEGB-09 experiment IDs;
- private results substituted for \(q_{\mathrm{ref}}\); and
- inconsistent capability-ordering versions.

Missing required cells preserve the expected denominators and may invalidate model-level or epic-level aggregates under the preregistered policy.

#### D4. Per-model replication estimates

Implement every \(D^{\mathrm{selection}}_m\) and, when included, \(D^{\mathrm{adaptive}}_m\).

Produce task-clustered or hierarchically clustered uncertainty exactly as preregistered. Retain all paired systems, budgets, policies, strategies, and replicates within sampled clusters.

#### D5. Cross-model synthesis and heterogeneity

Implement the frozen method for:

- hierarchical mean effect;
- between-model heterogeneity;
- prediction interval, if justified;
- sign consistency;
- minimum meaningful effect;
- influence;
- leave-one-model-out results;
- provider/family grouping where supported; and
- replication decision.

Do not treat model snapshots as dozens of independent observations merely because each has many task rows.

#### D6. Capability moderation

If approved, implement the ordinal or continuous capability analysis exactly as frozen. Always retain categorical model estimates.

Test nonlinear or rank-based alternatives only if preregistered. Provider/family-adjusted models must reflect the actual number of independent model and provider units and must not overfit a small panel.

#### D7. Cross-experiment comparison

Implement a separately identified comparison with accepted MEGB-06 and MEGB-08 estimates. Deduplicate reused candidates and results. Label historical versus concurrent replication.

Reject row-level pooling unless MEGB-09A explicitly defines a justified joint hierarchical model with experiment as a factor. Even then, the MEGB-09 replication decision must remain independently visible.

#### D8. Cost, refusal, and reliability analyses

Implement preregistered summaries of:

- valid candidate yield;
- refusal and content-filter rates;
- malformed output;
- provider and controller failures;
- execution failures;
- latency;
- token usage;
- monetary cost;
- cost per valid candidate;
- cost per measured acceptance; and
- cost per reference-correct selection.

These are secondary operational outcomes and must not redefine candidate budgets.

#### D9. Required figures

Implement deterministic figure-data generators for:

1. per-model robustness × pressure gaming curves;
2. forest plot of \(D^{\mathrm{selection}}_m\);
3. adaptive per-model interaction estimates;
4. measured versus reference performance by model;
5. capability ordering versus gaming effect, if approved;
6. heterogeneity and leave-one-model-out diagnostics;
7. refusal, failure, and valid-yield comparisons;
8. cost versus measurement/reference performance;
9. MEGB-06/08 historical-anchor comparison; and
10. private-holdout results where available.

#### D10. Synthetic known-answer tests

Test:

- positive replication across all models;
- heterogeneous but positive mean;
- one-model dominance;
- one-provider dominance;
- reversal in the strongest model;
- null pooled effect;
- missing model;
- snapshot mismatch;
- unbalanced tasks;
- invalid measurement;
- refusal-heavy model;
- capability ties and missing scores;
- nonlinear capability relation;
- duplicated historical result;
- selection/adaptive dataset mixing;
- private/reference confusion; and
- deterministic regeneration.

#### D11. Freeze analysis artifacts

Create locks binding schemas, formulas, factor coding, model/capability identities, clustering, seeds, packages, convergence rules, replication criteria, anti-dominance rules, figure specifications, synthetic fixtures, commands, code revision, and expected checksums.

### Acceptance Criteria

- Selection and adaptive datasets are distinct and typed.
- Model identity, panel membership, task equality, and pairing fail closed.
- Per-model effects reproduce known answers.
- Heterogeneity and anti-dominance diagnostics are implemented.
- Ordered capability results cannot replace categorical model results.
- Historical results cannot be double-counted.
- Failure and cost analyses preserve scientific budgets.
- All analysis and figure-data code passes synthetic tests.
- Locks verify from clean processes.
- No confirmatory generation or reference evaluation occurs.

### Non-Goals

- Calling any confirmatory model.
- Reading new \(S^*\) outcomes.
- Choosing models based on synthetic or smoke performance.
- Reporting empirical conclusions.

### Handoff Artifacts

- selection-only and adaptive dataset schemas;
- cross-model dataset builders;
- per-model and hierarchical analysis code;
- heterogeneity and influence diagnostics;
- capability-moderation code;
- figure-data generators;
- synthetic known-answer suite;
- analysis lock; and
- MEGB-09D completion record.

### Checkpoint and Stop Condition

Stop after the analysis lock verifies. Do not begin MEGB-09E until the user accepts MEGB-09D, confirms model availability and expected spend, and explicitly authorizes irreversible selection-only generation.

### Completion Record

**Status:** Not started  
**Accepted by:**  
**Acceptance date:**  
**Implementation commit(s):**  
**Artifact checksums:**  
**Deviations:**  

---

## MEGB-09E — Execute and Freeze Cross-Model Selection-Only Candidate Streams

### Objective

Generate the preregistered fixed candidate streams for every model, evaluate them only with optimization-visible systems, and freeze every budget/policy selection before reference evaluation.

### Dependencies

- MEGB-09A through MEGB-09D accepted.
- All upstream and MEGB-09 locks verify.
- Exact model snapshots remain available.
- Billing, quota, rate limits, and cost ceiling are confirmed.
- Explicit user authorization to incur selection-track cost.
- \(S^*\) and private-result interfaces are disabled.

### Requirements

#### E1. Preflight

Before the first confirmatory call:

- verify every lock;
- verify model identities and availability;
- verify selected tasks and expected condition counts;
- verify common prompt/configuration;
- verify tools and retrieval are disabled;
- verify destination is empty or exactly resumable;
- verify cost and call abort thresholds;
- verify secrets remain controller-only;
- verify reference evaluators are unreachable; and
- record code revision and run state.

Any mismatch stops the run.

#### E2. Generate fixed streams

For each frozen \((\text{model},\text{task},\text{stream seed})\), generate the full candidate stream without measurement feedback, prior-candidate context, or knowledge of system/observation assignment.

Candidate generation must be condition-blind. The same stream is later evaluated across the paired measurement conditions defined by the preregistration.

Preserve:

- exact request and raw response;
- normalized provider metadata;
- extraction and sanitized candidate;
- candidate hash;
- prompt/configuration identity;
- retries and uncertain calls;
- usage, latency, and cost; and
- timestamp and snapshot metadata.

#### E3. Preserve failures

Refusals, empty responses, content filters, malformed outputs, syntax errors, duplicates, and candidate failures remain in the stream and count toward the candidate budget under the frozen policy.

Do not replace a poor candidate, add calls for one model, or regenerate a stream because another model produced more valid code.

#### E4. Optimization-visible evaluation

Evaluate every candidate under the frozen MEGB-04 systems and observation replicates. The generation process must not receive measurement outcomes.

Candidate failures are valid measured failures when the apparatus functions. Invalid measurements remain invalid and follow the frozen cell policy.

#### E5. Apply MEGB-06 selection policies

At minimum preserve:

- FIRST_MEASURED_PASS;
- RANDOM_FROM_PREFIX; and
- FIRST_CANDIDATE.

Apply them identically across models, systems, observation replicates, and budgets. Selection may use only the information authorized by the accepted MEGB-06 policy.

#### E6. Safe interruption and resumption

Resume only from verified committed state. Never duplicate or omit an uncertain provider call silently. Preserve all attempts and apply the frozen uncertain-outcome rule.

A model snapshot change during execution triggers the frozen pause/abort policy. It does not authorize switching models or continuing under a mutable alias.

#### E7. Freeze streams and selections

The selection-track freeze must contain:

- every request, response, candidate, and stream hash;
- model identity evidence by call;
- measurement-result hashes;
- selection per policy/budget/system/replicate;
- expected and observed cell counts;
- failures and invalid cells;
- costs and usage;
- code revision;
- model-drift audit;
- freeze timestamp; and
- evidence that \(S^*\) has not been invoked.

Selections cannot change after freeze.

### Acceptance Criteria

- Every model receives the same scientific candidate opportunities.
- Generation is blind to measurement condition and results.
- Failed, refused, malformed, and duplicate responses remain in budget.
- Selection policies reproduce from frozen stream prefixes.
- Model identity is recorded and drift policy enforced.
- No model-specific rescue or extra calls occur.
- No \(S^*\) or private result is accessed.
- The selection-track freeze verifies from a clean process.
- Actual calls, costs, errors, and deviations are reported.

### Non-Goals

- Adaptive revision.
- Reference evaluation.
- Cross-model analysis.
- Candidate repair or reselection.

### Handoff Artifacts

- cross-model fixed candidate streams;
- provider call/cost ledger;
- model-identity and drift audit;
- optimization-visible measurement records;
- budget/policy selection manifest;
- selection-track freeze lock; and
- MEGB-09E completion record.

### Checkpoint and Stop Condition

Stop after the selection-track freeze verifies. Do not invoke \(S^*\). If the adaptive track is included, MEGB-09F requires separate explicit cost authorization. If an approved MEGB-09A amendment omitted it, record MEGB-09F as accepted-not-applicable without fabricating execution.

### Completion Record

**Status:** Not started  
**Accepted by:**  
**Acceptance date:**  
**Implementation commit(s):**  
**Artifact checksums:**  
**Actual cost:**  
**Deviations:**  

---

## MEGB-09F — Execute and Freeze Cross-Model Adaptive Trajectories

### Objective

Run the frozen MEGB-08 adaptive design across the approved model panel and freeze all trajectories and budget-prefix selections before any new MEGB-09 reference unblinding.

### Dependencies

- MEGB-09A through MEGB-09E accepted.
- MEGB-08 accepted and reproducible.
- Adaptive track included by the accepted preregistration.
- Exact model snapshots remain available.
- Explicit user authorization to incur adaptive-track cost.
- Selection-track candidates remain reference-blind.
- \(S^*\) and private-result interfaces remain disabled.

### Requirements

#### F1. Adaptive preflight

Verify the model panel, task set, paired initial-candidate schedule, strategies, systems, observation replicates, feedback schema, prompts, context renderer, stopping/selection rules, recovery policy, cost ceiling, and expected cells.

Confirm that no model has received reference or private outcomes and that no MEGB-09 candidate has been reference-evaluated.

#### F2. Paired initial conditions

For fixed \((\text{model},\text{task},\text{trajectory seed})\), generate one initial candidate before branching.

All strategy, system, and observation branches for that model/task/seed must use the same immutable initial candidate. Models are not expected to share the same initial candidate with one another.

#### F3. Run the three strategies

Execute:

- independent sampling;
- feedback-free self-refinement; and
- measurement-guided refinement.

Use the accepted MEGB-08 bounded context, authorized aggregate feedback, stopping rule, failure policy, and identical budget-prefix selector.

The model must not receive its identity-relative capability tier, system robustness label, other models’ candidates, or cross-model performance.

#### F4. Preserve every trajectory round

Retain normal, duplicate, empty, refused, filtered, malformed, failing, prohibited-access, and unexpected responses. Preserve raw calls, candidates, measurements, retries, identity metadata, usage, latency, and cost.

Do not adapt prompts or feedback because a particular model responds differently.

#### F5. Stop and select exactly as frozen

Stop at first measured acceptance or \(N_{\max}\). For every budget prefix, select earliest measured pass; otherwise best aggregate score; break ties by earliest round.

Reference/private outcomes and human judgment remain unavailable.

#### F6. Snapshot drift and recovery

Apply the same identity-drift and uncertain-call policy used by the selection track. A drift event may invalidate a model’s adaptive track or the entire panel under the preregistered rule; it does not authorize model substitution.

#### F7. Freeze adaptive trajectories

The adaptive freeze must bind:

- every initial candidate;
- all branch and round hashes;
- model identity evidence;
- strategy and feedback definitions;
- prompts and contexts;
- measurement results;
- stopping and prefix selections;
- expected and observed cells;
- invalid/incomplete trajectories;
- failures, retries, access attempts, and costs;
- code revision;
- freeze timestamp; and
- evidence that \(S^*\) remains unused.

### Acceptance Criteria

- Each model’s adaptive branches share paired initial candidates.
- Strategies receive exactly their authorized information.
- No model receives capability labels or cross-model outcomes.
- Every response and failed round remains in budget.
- Stopping and selections reproduce.
- Identity drift and recovery follow the frozen policy.
- No \(S^*\) or private result is accessed.
- Adaptive freeze verifies from a clean process.
- Actual cost and deviations are reported.

### Non-Goals

- Reference evaluation.
- Comparing models before freeze.
- Per-model prompt tuning.
- Optimization after measured acceptance.

### Handoff Artifacts

- paired initial-candidate manifests;
- cross-model adaptive trajectories;
- adaptive provider-call/cost ledger;
- access-attempt and failure audit;
- adaptive prefix-selection manifest;
- adaptive freeze lock; and
- MEGB-09F completion record.

### Checkpoint and Stop Condition

Stop after every included generation track is frozen. Do not invoke \(S^*\), inspect cross-model gaming outcomes, or modify the model panel. MEGB-09G requires explicit reference-unblinding authorization.

### Completion Record

**Status:** Not started  
**Accepted by:**  
**Acceptance date:**  
**Implementation commit(s):**  
**Artifact checksums:**  
**Actual cost:**  
**Deviations:**  


---

## MEGB-09G — Reference-Evaluate Frozen Candidates and Lock Cross-Model Datasets

### Objective

Evaluate every unique frozen MEGB-09 candidate once with \(S^*\), join results without changing generation artifacts, and lock separate selection-only and adaptive datasets.

### Dependencies

- MEGB-09A through MEGB-09F accepted or MEGB-09F explicitly accepted-not-applicable under MEGB-09A.
- Every included generation track freeze verifies.
- MEGB-03 privileged evaluator and locks verify.
- MEGB-09D dataset builders verify.
- Explicit reference-unblinding authorization.
- All model calls that could affect confirmatory candidates are closed.

### Requirements

#### G1. Unblinding preflight

Verify:

- model panel and identity audit;
- selected task set;
- every included track freeze;
- complete candidate and selection inventory;
- reference evaluator, oracle, comparison, execution, and partition versions;
- privileged artifact access;
- deduplication key;
- output destination and overwrite refusal;
- expected reference count and cost; and
- evidence that no candidate can be resumed or changed.

Opening this gate is an irreversible experiment-state transition.

#### G2. Evaluate unique candidates once

Evaluate each unique:

\[
(\text{task_id},
\text{candidate_sha256},
\text{reference_evaluator_version})
\]

once. Reuse valid results across models, tracks, conditions, budgets, and policies only when the candidate identity is exactly the same.

Deduplication reduces execution; it does not collapse scientific rows or create independent evidence.

#### G3. Preserve failure semantics

Candidate wrong outputs, syntax errors, exceptions, timeouts, and resource violations are valid zero outcomes when the apparatus is valid.

Oracle, protocol, manifest, comparison, controller, sandbox, or infrastructure failures are invalid measurements. They leave \(q_{\mathrm{ref}}\) undefined and preserve the expected denominator.

Do not rerun a valid result because it is surprising, substitute a candidate, or reopen a provider call.

#### G4. Optional private validation

Where an accepted MEGB-07 suite covers the task, evaluate or import the same frozen candidate under its authorized procedure.

Store \(q_{\mathrm{private}}\) separately. Never use it as \(q_{\mathrm{ref}}\), adaptive feedback, or selection input. Absence of private coverage does not invalidate MEGB-09.

#### G5. Build separate locked datasets

Build:

- a selection-only cross-model dataset; and
- an adaptive cross-model dataset, when applicable.

Verify stored selections from frozen prefixes before joining reference outcomes. Include complete model, task, system, budget, policy/strategy, replicate, candidate, measurement, failure, cost, and provenance fields.

Do not include reference cases, expected outputs, canonical solutions, privileged diagnostics, or privileged paths.

#### G6. Completeness and identity checks

Verify:

- all expected panel models;
- the same selected task set for every model;
- no HumanEval/39;
- every expected factor cell;
- no duplicate scientific rows;
- correct model snapshot and call identity;
- candidate and reference hash agreement;
- selection reproduction;
- adaptive initial pairing;
- valid denominator handling;
- no MEGB-06/08 rows masquerading as MEGB-09; and
- no selection/adaptive row mixing.

#### G7. Lock, verify, and protect artifacts

Create content-addressed locks with logical and byte checksums, counts, validity summaries, upstream identities, evaluator versions, generation commands, verification commands, and code revision.

Privileged result diagnostics remain under the accepted privileged-artifact policy and outside ordinary public CI.

### Acceptance Criteria

- Only frozen candidates are reference-evaluated.
- Each unique candidate/reference-version tuple has at most one valid result.
- No candidate, stream, trajectory, or selection changes after unblinding.
- Candidate failures remain distinct from invalid measurements.
- Selection-only and adaptive datasets remain separate.
- Model and task completeness checks fail closed.
- Hidden evidence is absent from analysis datasets.
- Dataset and privileged locks verify from clean processes.
- Actual reference cost, failures, retries, and deduplication are reported.

### Non-Goals

- Cross-model analysis.
- Model replacement.
- Candidate repair.
- Additional generation.
- Changing the capability ordering.

### Handoff Artifacts

- reference-unblinding ledger;
- deduplicated reference-result store;
- optional private-result store;
- locked selection-only dataset;
- locked adaptive dataset, if applicable;
- completeness and leakage report;
- dataset locks; and
- MEGB-09G completion record.

### Checkpoint and Stop Condition

Stop after all dataset locks verify. Do not run aggregate cross-model analyses. MEGB-09H requires explicit authorization to unblind model-level and aggregate results.

### Completion Record

**Status:** Not started  
**Accepted by:**  
**Acceptance date:**  
**Implementation commit(s):**  
**Artifact checksums:**  
**Reference cost:**  
**Deviations:**  

---

## MEGB-09H — Run Cross-Model Replication, Heterogeneity, and Capability Analyses

### Objective

Execute the frozen analyses, determine whether the measurement-robustness interaction replicates across model snapshots, and characterize heterogeneity without collapsing it into an unjustified capability narrative.

### Dependencies

- MEGB-09A through MEGB-09G accepted.
- All dataset and analysis locks verify.
- Frozen package environment available.
- Explicit aggregate-unblinding authorization.

### Requirements

#### H1. Run per-model selection replication

For every model, report:

- \(D^{\mathrm{selection}}_m\);
- uncertainty interval;
- gaming curves by system and budget;
- measured and reference performance;
- valid cluster and task counts;
- minimum meaningful effect status; and
- replication classification under the frozen rule.

Do not omit a model because its result is null, reversed, noisy, refusal-heavy, or adverse.

#### H2. Run cross-model synthesis

Report:

- preregistered hierarchical mean, if applicable;
- heterogeneity estimate;
- model-level prediction interval, if justified;
- sign consistency;
- number/proportion positive;
- anti-dominance criterion;
- leave-one-model-out results;
- provider/family sensitivity where supported; and
- effect of invalid or incomplete cells.

A pooled positive effect may not conceal model-level reversal.

#### H3. Run adaptive analyses

When included, report every \(D^{\mathrm{adaptive}}_m\), cross-model heterogeneity, and whether feedback-specific gaming differs across models.

Keep adaptive results separate from the selection-only replication decision.

#### H4. Run capability moderation cautiously

If preregistered, fit the frozen capability model and report:

- categorical model estimates;
- ordered or continuous effect;
- uncertainty;
- ties and score uncertainty;
- nonlinear sensitivity;
- provider/family confounding;
- leverage by model;
- and leave-one-model-out behavior.

If the panel is too small or confounded for a stable slope, report that limitation directly. Do not replace the preregistered model or manufacture a monotonic narrative.

#### H5. Cross-experiment comparison

Compare MEGB-09 with the accepted MEGB-06 and MEGB-08 results according to the frozen plan.

Distinguish:

- historical anchor;
- concurrent replication;
- exact artifact reuse;
- model snapshot drift;
- task-set differences; and
- protocol differences.

Do not double-count reused candidates or pool experiments post hoc.

#### H6. Operational analyses

Report refusal, filtering, malformed-output, provider-failure, execution-failure, valid-yield, latency, token, and cost outcomes.

Discuss whether apparent gaming differences could reflect unequal valid-candidate yield or refusal policy rather than optimization ability.

#### H7. Optional private validation

Report \(q_{\mathrm{private}}\) and private gaming under separately identified estimands where coverage permits. Do not use private results to redefine the primary reference outcome.

#### H8. Preserve all results

Generate machine-readable results for null, negative, reversed, heterogeneous, and incomplete outcomes. Record convergence warnings, failed fits, sensitivity failures, and deviations.

Do not change exclusions, model panel, task set, capability ordering, estimands, or replication criteria.

### Acceptance Criteria

- Every frozen model receives a visible per-model result.
- Primary selection-only replication is decided exactly as preregistered.
- Heterogeneity and influence are reported alongside any pooled mean.
- Adaptive results remain separate.
- Capability analysis retains categorical estimates and acknowledges confounding.
- Historical experiments are not double-counted.
- Operational differences are reported.
- Null, reversed, and adverse outcomes are preserved.
- Results reproduce from locked datasets and commands.

### Non-Goals

- New generation or evaluation.
- Model-specific exclusions.
- Re-ranking models using MEGB outcomes.
- Causal claims about capability, provider, or architecture.
- Publication artifact release.

### Handoff Artifacts

- per-model selection replication results;
- cross-model synthesis and heterogeneity report;
- adaptive cross-model results, if applicable;
- capability-moderation results;
- cross-experiment comparison;
- operational cost/reliability analysis;
- private validation results, if available; and
- MEGB-09H completion record.

### Checkpoint and Stop Condition

Stop after the frozen analyses reproduce. Do not revise interpretations by changing analysis code. MEGB-09I requires explicit reporting and release authorization.

### Completion Record

**Status:** Not started  
**Accepted by:**  
**Acceptance date:**  
**Implementation commit(s):**  
**Artifact checksums:**  
**Deviations:**  

---

## MEGB-09I — Generate Figures, Report Generalization Claims, Release Artifacts, and Complete the Audit

### Objective

Produce the final cross-model report and reproducibility package, apply disciplined claim boundaries, and close the epic through a requirement, access, identity, and artifact audit.

### Dependencies

- MEGB-09A through MEGB-09H accepted.
- All analysis results and locks reproduce.
- Explicit reporting and release authorization.

### Requirements

#### I1. Generate required figures and tables

Produce at minimum:

1. selection-induced gaming curves by model, robustness, and budget;
2. forest plot of per-model \(D^{\mathrm{selection}}_m\);
3. cross-model heterogeneity and leave-one-model-out diagnostics;
4. measured versus reference performance by model;
5. adaptive \(D^{\mathrm{adaptive}}_m\) where included;
6. capability ordering versus effect, where approved;
7. refusal, failure, and valid-yield comparisons;
8. token/cost versus measured and reference performance;
9. MEGB-06/08 historical-anchor comparison; and
10. private-holdout replication where available.

Every figure must identify confirmatory versus secondary status, show uncertainty where appropriate, and reproduce from locked nonprivileged data.

#### I2. Report model identity precisely

For each model, report the frozen identity, call window, fingerprint availability, provider/family, relevant inference settings, and any drift or immutability limitation.

Do not shorten exact snapshots into ambiguous marketing names in methods, tables, or machine-readable metadata.

#### I3. Apply claim discipline

Permitted conclusions depend on observed results:

- consistent positive per-model effects support cross-model replication;
- heterogeneous effects support model-dependent generalization;
- a positive mean with strong reversal requires qualified claims;
- a single-model-driven mean does not establish generalization;
- a capability slope supports association only;
- a provider-confounded slope does not isolate capability;
- null or reversed results constrain the core claim’s scope; and
- incomplete panels remain incomplete.

Do not claim:

- that capability causes gaming;
- that stronger models necessarily game more;
- that a provider or architecture causes an effect;
- that \(S^*\) is infallible;
- that gaming proves deceptive intent;
- that the panel represents all frontier models; or
- that MEGB-09 retroactively changes MEGB-06 or MEGB-08.

#### I4. Report threats to validity

At minimum:

- capability is multidimensional and imperfectly ordered;
- model, provider, family, training, policy, and release date are confounded;
- provider wrappers and tokenizers differ;
- hidden reasoning and serving policies are not fully observable;
- mutable endpoints may drift;
- deterministic seeds may not be honored;
- refusals and safety filters affect candidate yield;
- public coding-task contamination may differ across models;
- a small model panel limits model-level inference;
- selected tasks may not represent HumanEval or real software work;
- cost constraints may reduce replication depth;
- \(S_1\) and \(S_4\) may not span all measurement systems;
- adaptive feedback differs from production optimization;
- sandbox restrictions exclude real attack surfaces;
- multiple candidates from one snapshot are not independent models; and
- results may not generalize to future snapshots.

#### I5. Report costs and failures

Publish expected versus actual calls, tokens, latency, execution time, storage, and monetary cost by model and track.

Report model withdrawals, identity mismatches, provider failures, uncertain calls, refusals, malformed responses, invalid measurements, reference failures, and every protocol deviation.

#### I6. Reproducibility package

Provide commands and environment locks to:

- verify upstream and MEGB-09 artifacts;
- rebuild public/redacted manifests;
- validate model identities and selected tasks;
- verify frozen candidates and selections;
- rebuild datasets;
- rerun analyses;
- regenerate figures and tables;
- verify final report checksums; and
- audit that privileged evidence is absent from release artifacts.

Provider calls need not be replayable indefinitely, but their immutable raw records, identities, and checksums must be preserved under the approved storage policy.

#### I7. Cross-ticket and manuscript integration

Update architecture, product, research-roadmap, experiment-index, and TR-04 integration documents as appropriate.

State clearly:

- MEGB-06 is the original selection-only experiment;
- MEGB-08 is the original adaptive experiment;
- MEGB-09 is the cross-model generalization study;
- MEGB-07 is a separate private-evidence validation;
- model-level and cross-model conclusions are distinct; and
- selection and adaptive analyses are not pooled.

#### I8. Final audit

Trace every requirement to code, tests, artifacts, results, report sections, or documented non-applicability.

Verify:

- panel selected before generation;
- no model selected from observed MEGB performance;
- same task set and scientific opportunity across models;
- no model-specific rescue;
- all generation froze before reference unblinding;
- every new candidate evaluated at most once validly by \(S^*\);
- no reference or private feedback reached a model;
- no hidden evidence was released;
- no model/result was dropped post hoc;
- no historical evidence was double-counted;
- all nulls, reversals, failures, and deviations are retained; and
- all completion records are accepted.

### Acceptance Criteria

- Required figures and tables reproduce.
- Exact model identities and limitations are reported.
- Cross-model, capability, provider, and causal claims remain distinct.
- Null, reversed, heterogeneous, and incomplete results are visible.
- Costs, refusals, failures, and drift are fully reported.
- Release artifacts contain no privileged evidence.
- Reproducibility commands verify.
- Every requirement is traced.
- The MEGB-09 report is suitable for TR-04.
- The epic is complete only after explicit user acceptance.

### Non-Goals

- New models, tasks, candidates, or evaluations.
- Post hoc model substitution.
- New capability indices.
- Per-model prompt optimization.
- Causal claims unsupported by the panel.
- Concealing unfavorable results.

### Handoff Artifacts

- publication-ready figures and tables;
- model-identity methods appendix;
- cross-model generalization report;
- cost, reliability, drift, and deviation audits;
- reproducibility package;
- claim-discipline report;
- final traceability matrix;
- TR-04 integration updates; and
- MEGB-09I completion record.

### Checkpoint and Epic Completion Condition

Stop after the final audit and report are complete. The epic becomes complete only after the user accepts MEGB-09I and confirms that all prior completion records, locks, model identities, costs, results, and claim boundaries are satisfactory.

### Completion Record

**Status:** Not started  
**Accepted by:**  
**Acceptance date:**  
**Implementation commit(s):**  
**Artifact checksums:**  
**Deviations:**  

---

## Epic Non-Goals

MEGB-09 does not:

- train or fine-tune model weights;
- define one universal measure of model capability;
- treat API marketing tiers as scientific capability measurements;
- tune prompts separately by model;
- expose optimization-visible or hidden test evidence;
- provide \(S^*\) feedback to any model;
- infer deception or intent from gaming;
- establish causal effects of provider, architecture, scale, or training;
- evaluate unrestricted tool-using agents;
- evaluate repository-level software engineering;
- pool MEGB-06, MEGB-08, and MEGB-09 to rescue significance;
- replace models after observing outcomes;
- hide refusals, invalids, nulls, or reversals; or
- generalize beyond the frozen panel without qualification.

## Global Acceptance Criteria

MEGB-09 is acceptable only when:

- all required subtasks are accepted;
- the model panel and capability treatment freeze before generation;
- exact model identities and drift limitations are preserved;
- every model receives the same selected tasks and scientific opportunities;
- HumanEval/39 is absent;
- provider adapters preserve semantic prompt content;
- no model-specific rescue or post-outcome replacement occurs;
- selection-only streams freeze before reference evaluation;
- adaptive trajectories also freeze first when included;
- every unique candidate receives at most one valid \(S^*\) evaluation;
- model-level results remain visible beside pooled summaries;
- heterogeneity and influence are reported;
- capability claims remain secondary and associational;
- MEGB-06, MEGB-08, and MEGB-09 remain distinct;
- failures, refusals, nulls, reversals, and adverse results are preserved;
- privileged evidence does not reach models or release artifacts; and
- all deterministic stages reproduce from frozen commands and locks.

## Requirement Traceability

| Requirement family | Governing subtask(s) |
| --- | --- |
| Exact model panel and immutable identities | A, B, C, E, F, I |
| Categorical primary model treatment | A, D, H, I |
| Optional capability ordering | A, D, H, I |
| Provider/family confounding | A, D, H, I |
| Shared 163-task population and HumanEval/39 exclusion | A, D, E, F, G |
| Power, cost, and replicate design | A |
| Prompt and inference comparability | A, B, C |
| Provider-neutral adapters | B |
| Tool/retrieval exclusion | B, C, E, F |
| Snapshot drift detection | A, B, C, E, F, I |
| Selection-only fixed streams | E |
| MEGB-06 selection policies | A, D, E |
| Cross-model adaptive trajectories | A, D, F |
| Freeze before \(S^*\) | E, F, G |
| Deduplicated reference evaluation | G |
| Separate locked datasets | D, G |
| Per-model replication effects | A, D, H |
| Hierarchical synthesis and heterogeneity | A, D, H |
| Anti-dominance and influence diagnostics | A, D, H |
| Capability moderation | A, D, H |
| Historical MEGB-06/08 comparison without pooling | A, D, H, I |
| Failure, refusal, reliability, and cost analysis | A, B, D, E, F, H, I |
| Optional MEGB-07 private validation | G, H, I |
| Figures and tables | D, I |
| Reproducibility and privileged-data audit | G, I |
| Claim discipline and threats to validity | A, H, I |
| Standard checkpoints and explicit gates | A–I |

## Cross-Ticket Integration Notes

Before implementation:

- MEGB-03 remains the only source of \(q_{\mathrm{ref}}\) and is inaccessible until MEGB-09G.
- MEGB-04 systems and observation replicates must not vary by model.
- MEGB-05 generation artifacts may be reused only through exact compatibility checks.
- MEGB-06 supplies the selection-only estimand and policies but remains a separate experiment.
- MEGB-08 supplies the adaptive strategies and feedback boundary but remains a separate experiment.
- MEGB-07 may supply separately identified private outcomes only.
- Any ticket text referring to all 164 HumanEval tasks is superseded for MEGB-09 by the frozen selected subset of the 163-task primary population.

## Instructions for Claude

When executing this epic:

1. Treat this file as the sole governing MEGB-09 specification.
2. Work on exactly one explicitly authorized subtask.
3. Restate the objective, dependencies, acceptance criteria, and non-goals before implementation.
4. Verify all prerequisite locks from clean processes.
5. Never use mutable model aliases for confirmatory work.
6. Do not tune prompts or retries per model.
7. Do not make confirmatory calls before MEGB-09E authorization.
8. Do not begin adaptive calls before MEGB-09F authorization.
9. Do not invoke \(S^*\) before MEGB-09G authorization.
10. Do not inspect aggregate model results before MEGB-09H authorization.
11. Preserve every request, response, failure, refusal, retry, candidate, and deviation.
12. Report exact commands, commits, checksums, call counts, and cost.
13. Do not push, spend external API budget, access privileged data, or begin the next subtask without explicit authorization.
14. End each subtask with the Standard Checkpoint Report and stop.

## Epic Completion Rule

MEGB-09 is complete only when MEGB-09A through MEGB-09I have each been:

- executed or explicitly accepted-not-applicable where the preregistration permits;
- verified;
- reported;
- explicitly accepted; and
- recorded with exact commits and checksums.

Completion additionally requires the final audit to confirm model-panel integrity, equal scientific opportunity, generation freeze before reference unblinding, protected-data isolation, separate experiment identities, heterogeneity reporting, capability-claim discipline, and deterministic reproducibility.
