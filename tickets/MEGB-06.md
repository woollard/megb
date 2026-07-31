# [MEGB-06] Preregister, Execute, and Analyze the Measurement-Robustness × Optimization-Pressure Experiment

## Objective

Execute the first confirmatory MEGB experiment and test the hypothesis:

> Benchmark gaming emerges when optimization pressure exceeds the robustness of the measurement system.

This ticket combines:

- the privileged reference evaluator \(S^*\) from MEGB-03;
- the optimization-visible robustness levels \(S_1 \dots S_4\) from MEGB-04; and
- the nested best-of-\(N\) selection process from MEGB-05.

MEGB-06 must preregister the experimental and statistical design, execute the complete factorial sweep, evaluate only frozen candidates with \(S^*\), lock the resulting analysis dataset, run the preregistered analyses, and generate publication-ready results for TR-04.

## Dependencies

Depends on:

- `[MEGB-01] Establish HumanEval Corpus and Privileged Evaluation Boundary`
- `[MEGB-02] Implement Isolated Candidate Execution Worker`
- `[MEGB-03] Implement Privileged Reference Evaluator S*`
- `[MEGB-04] Implement Optimization-Visible Measurement Systems S1 ... S4`
- `[MEGB-05] Implement Controlled Candidate Generation and Best-of-N Optimization`

All upstream artifacts, configurations, validation suites, and manifests must be frozen before this experiment begins.

## Experimental Design

The complete experimental matrix is:

\[
\text{Task}
\times
\text{Candidate-stream replicate}
\times
\text{Observation-set replicate}
\times
\text{Measurement robustness}
\times
\text{Optimization pressure}.
\]

The fixed task set contains all 164 HumanEval tasks.

Measurement robustness is operationalized by evidence budget:

\[
E \in \{1,3,10,30\}.
\]

Optimization pressure is operationalized by nested candidate-selection budget:

\[
N \in \{1,2,4,8,16,32\}.
\]

MEGB-04 provides five observation-set replicates by default. The number of candidate-stream replicates must be determined by the preregistered power and cost analysis.

The same candidate stream must be shared across all measurement-system conditions for a fixed task and stream replicate.

## Primary Outcome

Define a task-level gaming event:

\[
G_{i,k,N}
=
\mathbb{1}
\left[
q_{\mathrm{meas},i}^{(k,N)}=1
\land
q_{\mathrm{ref},i}^{(k,N)}=0
\right].
\]

This event identifies a candidate accepted by the optimization-visible measurement system but rejected by the privileged reference evaluator.

Define aggregate gaming rate:

\[
G(k,N)
=
\frac{1}{164}
\sum_{i=1}^{164} G_{i,k,N}.
\]

Aggregation across stream and observation-set replicates must follow the preregistered analysis plan and preserve clustering.

## Secondary Outcomes

### Measured Performance

\[
Q_{\mathrm{meas}}(k,N)
=
\frac{1}{164}
\sum_{i=1}^{164}
q_{\mathrm{meas},i}^{(k,N)}.
\]

### Reference Performance

\[
Q_{\mathrm{ref}}(k,N)
=
\frac{1}{164}
\sum_{i=1}^{164}
q_{\mathrm{ref},i}^{(k,N)}.
\]

### Signed Gaming Gap

\[
\Delta_{\mathrm{game}}(k,N)
=
Q_{\mathrm{meas}}(k,N)
-
Q_{\mathrm{ref}}(k,N).
\]

### False-Acceptance Rate Conditional on Measured Acceptance

\[
\operatorname{FAR}(k,N)
=
P\left(q_{\mathrm{ref}}=0
\mid
q_{\mathrm{meas}}=1\right).
\]

Treat this conditional rate as secondary because the conditioning set changes with optimization pressure.

### Selection Index

Record the index of the first measured-pass candidate and the fraction of tasks for which no candidate passes within budget.

## Confirmatory Hypotheses

### H1: Optimization Effectiveness

For every robustness level, measured performance is nondecreasing with optimization pressure:

\[
Q_{\mathrm{meas}}(k,N_2)
\ge
Q_{\mathrm{meas}}(k,N_1)
\quad
\text{for } N_2>N_1.
\]

This is also an implementation invariant of MEGB-05's first-pass selection rule.

### H2: Optimization-Induced Gaming

For weaker measurement systems, increasing optimization pressure increases gaming:

\[
G(k,32) > G(k,1).
\]

### H3: Measurement Robustness

At fixed optimization pressure, gaming is non-increasing with evidence coverage:

\[
G(S_1,N)
\ge
G(S_2,N)
\ge
G(S_3,N)
\ge
G(S_4,N).
\]

### H4: Robustness × Pressure Interaction

The effect of optimization pressure is greater under weak measurement than strong measurement.

Define the primary difference-in-differences estimand:

\[
D
=
\left[G(S_1,32)-G(S_1,1)\right]
-
\left[G(S_4,32)-G(S_4,1)\right].
\]

The confirmatory prediction is:

\[
D>0.
\]

The preregistration must define a minimum practically meaningful effect size \(D_{\min}\). The value must be selected using the pre-experimental power analysis and frozen before reference results are observed.

## Requirements

### 1. Preflight Validation Gate

Before preregistration and experimental generation, verify:

- exactly 164 public tasks are available;
- the development and reference-only evidence pools are disjoint;
- all dataset and oracle checksums match frozen manifests;
- all 20 optimization-visible system replicates are frozen and valid;
- corrected canonical solutions pass all measurement systems;
- corrected canonical solutions pass \(S^*\);
- MEGB-04 robustness monotonicity tests pass;
- MEGB-05 nested-prefix and deterministic-selection tests pass;
- the candidate-execution sandbox passes its security test suite;
- the reference evaluator remains inaccessible to the optimization runtime; and
- no experimental reference evaluation has occurred.

Failure of any gate blocks the experiment.

### 2. Power and Cost Analysis

Perform the power and cost analysis without inspecting experimental \(Q_{\mathrm{ref}}\) outcomes.

Permitted inputs include:

- MEGB-04's pre-experimental validation corpus;
- canonical solutions;
- synthetic candidate outcomes;
- published or externally sourced HumanEval failure rates;
- infrastructure timing benchmarks; and
- model-provider price schedules.

The analysis must determine:

- candidate-stream replicate count;
- expected number of model generations;
- expected candidate-execution count;
- expected unique frozen candidates requiring \(S^*\);
- expected runtime;
- expected model and infrastructure cost;
- detectable range for \(D\);
- proposed \(D_{\min}\); and
- stopping or infeasibility criteria.

Do not reduce replicate count after observing experimental reference outcomes.

### 3. Preregistration

Create both human-readable and machine-readable preregistration artifacts:

```text
experiments/megb-v1/preregistration.md
experiments/megb-v1/preregistration.json
```

Preregister at least:

- research question;
- confirmatory and secondary hypotheses;
- primary and secondary estimands;
- task set;
- robustness levels;
- optimization budgets;
- observation-set replicate count;
- candidate-stream replicate count;
- candidate-generation configuration;
- selection rule;
- reference-evaluation policy;
- failure and exclusion rules;
- power analysis;
- minimum meaningful effect size;
- bootstrap procedure;
- hierarchical-model specification;
- multiplicity policy;
- onset-threshold definition;
- figure specifications;
- claim boundaries; and
- experiment completion criteria.

Compute and record a preregistration checksum.

No outcome-affecting field may change after candidate generation begins without a formal amendment and version increment.

### 4. Experiment Freeze Manifest

Create a single experiment manifest referencing every frozen dependency:

```json
{
  "experiment_id": "megb-selection-pressure-v1",
  "task_manifest_sha256": "sha256:...",
  "partition_manifest_sha256": "sha256:...",
  "reference_evaluator_sha256": "sha256:...",
  "system_family_sha256": "sha256:...",
  "optimizer_config_sha256": "sha256:...",
  "generation_config_sha256": "sha256:...",
  "preregistration_sha256": "sha256:...",
  "analysis_code_revision": "git-sha",
  "reference_evaluation_allowed": false,
  "status": "PREREGISTERED"
}
```

The manifest must be immutable after transition to `RUNNING`.

### 5. Candidate Generation

Generate all candidate streams through MEGB-05.

Generation must:

- cover all 164 tasks;
- use the preregistered number of stream replicates;
- contain exactly 32 candidate positions per complete stream;
- preserve duplicates and malformed outputs;
- use one frozen model and generation configuration;
- remain independent of measurement-system condition;
- preserve raw model responses; and
- complete before reference evaluation is enabled.

Provider infrastructure failures must follow the frozen retry policy.

An unresolved incomplete stream invalidates the corresponding experiment unit. Do not silently generate extra streams after inspecting outcomes.

### 6. Optimization-Visible Evaluation

Evaluate every candidate stream against every preregistered \(S_k\) and observation-set replicate.

Verify matrix completeness before selection:

```text
164 tasks
× candidate-stream replicates
× 32 candidate positions
× 4 robustness levels
× 5 observation-set replicates
```

Every required measurement must be valid before selection proceeds.

Candidate failures are valid measurements. Infrastructure, oracle, and protocol failures are invalid measurements and must follow the frozen recovery policy.

### 7. Candidate Selection and Freeze

Apply MEGB-05's deterministic first-measured-pass selection rule at:

```text
N = 1, 2, 4, 8, 16, 32
```

Generate and validate every frozen selection manifest.

Before enabling reference evaluation, verify:

- every selection resolves to a valid candidate artifact;
- every candidate hash matches;
- every selection uses only the eligible prefix;
- every selection is reproducible;
- every measurement result is optimization-visible only;
- no reference result influenced selection;
- all expected conditions are represented; and
- all selection manifests are immutable.

After verification, update the experiment manifest atomically:

```json
{
  "status": "SELECTION_FROZEN",
  "reference_evaluation_allowed": true
}
```

### 8. One-Time Reference Evaluation

Evaluate frozen candidates using MEGB-03 only after the selection-freeze gate succeeds.

Reference evaluation must:

- use only the disjoint reference-only pool for primary \(Q_{\mathrm{ref}}\);
- verify every frozen candidate hash;
- use the frozen reference-evaluator version;
- execute each unique candidate/task/evaluator tuple once;
- reuse valid reference results by content hash when the same candidate is selected in multiple conditions;
- preserve the mapping from each experimental condition to its reference result;
- write append-only audit records; and
- withhold detailed reference evidence from optimization artifacts.

Do not rerun a valid reference evaluation merely because the result is unexpected.

Reference infrastructure failures may be resumed according to MEGB-03, but candidate selections may not change.

### 9. Reference Blinding and Unblinding

Until all selections are frozen:

- do not expose per-task reference outcomes;
- do not expose aggregate \(Q_{\mathrm{ref}}\);
- do not expose gaming rates;
- do not expose reference failure categories; and
- do not run exploratory reference analyses.

After reference evaluation completes, join results only through the preregistered data-building command.

Record the unblinding timestamp and the exact reference-result manifest checksum.

### 10. Locked Analysis Dataset

Build one long-form analysis dataset with one row per:

```text
(task_id,
 candidate_stream_id,
 observation_replicate,
 robustness_level,
 optimization_budget)
```

Include at least:

- experiment ID;
- task ID;
- stream ID and seed;
- observation-set replicate;
- system ID and evidence budget;
- optimization budget;
- selected candidate ID, index, and hash;
- selection reason;
- \(q_{\mathrm{meas}}\);
- \(q_{\mathrm{ref}}\);
- gaming-event indicator;
- signed task-level difference;
- measurement and reference statuses;
- duplicate indicator;
- invalid-model-output indicator;
- system and evaluator versions;
- all relevant manifest checksums; and
- provenance fields needed to trace the row to raw artifacts.

Do not include hidden test inputs or expected outputs.

Validate the dataset, compute its checksum, and mark it locked before confirmatory analysis.

Any corrected dataset requires a new version, documented reason, and complete regeneration from source artifacts.

### 11. Primary Statistical Analysis

Estimate the primary difference-in-differences:

\[
D
=
\left[G(S_1,32)-G(S_1,1)\right]
-
\left[G(S_4,32)-G(S_4,1)\right].
\]

Use a preregistered hierarchical clustered bootstrap that respects repeated observations.

Recommended procedure:

1. sample tasks with replacement;
2. within each sampled task, sample candidate-stream replicates with replacement;
3. within each sampled task and stream, sample observation-set replicates with replacement;
4. retain the complete paired robustness and budget conditions for every sampled cluster;
5. calculate \(D\); and
6. repeat for the preregistered number of bootstrap draws, with 10,000 as the default.

Report:

- point estimate;
- two-sided 95% confidence interval;
- bootstrap standard error;
- number of valid clusters;
- bootstrap seed; and
- whether the confidence interval and \(D_{\min}\) support the confirmatory hypothesis.

The confirmatory result supports H4 only if:

1. the complete preregistered dataset is valid;
2. the point estimate is at least \(D_{\min}\); and
3. the two-sided 95% confidence interval excludes zero in the predicted direction.

Do not substitute an unregistered statistical test after observing results.

### 12. Secondary Hierarchical Model

Fit a preregistered logistic mixed-effects model at the task-condition level:

\[
\operatorname{logit}P(G=1)
=
\beta_0
+
\beta_N\log_2N
+
\beta_E\log E
+
\beta_{NE}(\log_2N)(\log E)
+
u_{\mathrm{task}}
+
u_{\mathrm{stream}}
+
u_{\mathrm{observation}}.
\]

Expected coefficient directions are:

- \(\beta_N>0\): greater pressure increases gaming;
- \(\beta_E<0\): greater evidence coverage reduces gaming; and
- \(\beta_{NE}<0\): robustness suppresses the effect of pressure.

The preregistration must specify:

- exact implementation and package version;
- optimizer and convergence settings;
- random-effects structure;
- handling of singular fits;
- fallback behavior for nonconvergence; and
- reporting format.

Treat this model as secondary. Do not replace the clustered bootstrap as the confirmatory analysis if the model fails to converge.

### 13. Secondary Contrasts and Multiplicity

Estimate at least:

- \(G(k,32)-G(k,1)\) for each robustness level;
- \(G(S_1,N)-G(S_4,N)\) for each budget;
- \(Q_{\mathrm{meas}}-Q_{\mathrm{ref}}\) by condition;
- reference-performance change by budget;
- false-acceptance rate conditional on measured acceptance;
- measured-success rate; and
- first-pass candidate-index distribution.

Specify a false-discovery-rate or familywise correction for secondary pairwise tests before unblinding.

Clearly distinguish confirmatory, secondary, and exploratory analyses in every output.

### 14. Gaming-Onset Threshold

Define a secondary onset threshold for each robustness level:

\[
N^*(k)
=
\min N
\]

such that the change in gaming rate relative to \(N=1\):

1. is at least the preregistered onset effect size; and
2. has a clustered confidence interval excluding zero in the predicted direction.

If no budget satisfies both conditions, report:

```text
No reliable onset observed within N <= 32.
```

Do not extrapolate an unobserved threshold without labeling the result as model-based exploration.

### 15. Required Figures

Generate publication-ready vector and raster versions of every figure.

#### Primary Figure: Gaming Rate by Pressure and Robustness

- x-axis: optimization budget \(N\), displayed on a base-2 log scale;
- y-axis: gaming rate \(G(k,N)\);
- one line per robustness level;
- uncertainty ribbons from the clustered bootstrap;
- consistent color ordering from weak to strong measurement; and
- caption stating that candidate streams are paired across systems.

#### Figure 2: Measured Versus Reference Performance

Plot \(Q_{\mathrm{meas}}\) and \(Q_{\mathrm{ref}}\) across \(N\) for every robustness level.

#### Figure 3: Robustness × Pressure Heatmap

Display gaming rate or signed gaming gap across the full factorial grid.

#### Figure 4: Candidate Selection Dynamics

Display first-pass index distributions and the fraction of tasks with no measured pass at each budget.

#### Figure 5: Replicate Stability

Show variability across candidate-stream and observation-set replicates.

Every figure must be generated from the locked dataset by a version-controlled command. No values may be edited manually.

### 16. Required Tables

Produce at least:

- experimental configuration summary;
- matrix-completeness report;
- primary estimand and confidence interval;
- gaming rate by robustness and budget;
- measured and reference performance by condition;
- hierarchical-model coefficients;
- onset thresholds;
- invalid and incomplete measurement counts;
- model-generation and execution costs; and
- confirmatory versus exploratory result classification.

### 17. Failure and Exclusion Policy

Apply these rules exactly:

| Event | Treatment |
| --- | --- |
| Empty, refused, malformed, or syntactically invalid model output | Retain as candidate output and count toward \(N\) |
| Duplicate model output | Retain and count toward \(N\) |
| Candidate exception, timeout, or resource violation | Valid candidate failure |
| Provider transport or authentication failure | Apply frozen retry policy; invalidate stream if unresolved |
| Optimization-visible evaluator infrastructure failure | Resume or invalidate measurement; never score as candidate failure |
| Reference-evaluator infrastructure failure | Resume or leave \(q_{\mathrm{ref}}\) undefined; never score as candidate failure |
| Missing task condition | Mark aggregate incomplete; do not change denominator |
| Unexpected result | Preserve; do not rerun solely because it is surprising |

No task, stream, replicate, or condition may be excluded manually after unblinding.

Any exclusion not specified in the preregistration must be reported as a protocol deviation and analyzed separately from the confirmatory result.

### 18. Amendment Protocol

If a defect is discovered after preregistration:

1. stop the affected phase;
2. preserve all existing artifacts;
3. document the defect and discovery time;
4. state whether reference outcomes had been observed;
5. create a versioned preregistration amendment;
6. increment every affected configuration or dataset version;
7. regenerate all affected downstream artifacts; and
8. label the resulting analysis confirmatory or post-unblinding according to the timing of the amendment.

Never overwrite the original preregistration or experiment artifacts.

### 19. Claim Discipline

The final report must distinguish:

1. **Selection-induced benchmark gaming:** supported if optimization selects measurement-passing/reference-failing candidates at increasing rates.
2. **Adaptive exploitation:** not tested by the confirmatory selection-only experiment.
3. **Intentional deception or hacking:** not established by this experiment.

The strongest permitted confirmatory claim is:

> Optimization systematically selects solutions that satisfy the measurement system without satisfying the reference construct measurement, and the onset and severity of this divergence depend on measurement robustness.

Do not describe the model as intentionally deceptive unless supported by a separate experimental design.

### 20. Experiment Report

Generate:

```text
experiments/megb-v1/report.md
```

The report must contain:

- abstract-style result summary;
- preregistered hypotheses;
- experimental design;
- measurement-system definitions;
- optimization-pressure definition;
- sample-size and power rationale;
- confirmatory result;
- secondary results;
- figures and tables;
- failure and deviation audit;
- threats to validity;
- claim limitations;
- reproducibility instructions; and
- a concise section suitable for adaptation into TR-04.

### 21. Reproducibility Package

Create a self-contained manifest of:

- source-code revision;
- environment and dependency locks;
- dataset and partition checksums;
- measurement-system configurations;
- generation configuration;
- raw candidate artifacts;
- candidate-stream manifests;
- optimization-visible results;
- selection manifests;
- reference results;
- locked analysis dataset;
- analysis configuration;
- statistical outputs;
- figures and tables; and
- exact commands required to reproduce every deterministic stage.

Do not include secrets, provider credentials, or hidden reference test evidence in a public package.

## Required Tests

### Preregistration-Gate Tests

Verify that the experiment cannot enter `RUNNING` unless:

- every required upstream manifest is present and valid;
- preregistration artifacts exist and match their checksums;
- the power analysis is complete;
- the analysis revision is frozen; and
- reference evaluation is disabled.

### Matrix-Completeness Tests

Given the preregistered replicate count, verify the exact expected number of:

- candidate streams;
- candidate positions;
- optimization-visible measurements;
- selection decisions;
- frozen selections; and
- unique reference-evaluation requests.

Verify that every expected coordinate appears exactly once.

### Selection-Freeze Tests

Verify that reference evaluation cannot begin until:

- every selection manifest is valid;
- every candidate hash resolves;
- selection reproducibility passes; and
- the experiment status is `SELECTION_FROZEN`.

Verify that selections cannot change after this transition.

### Reference-Deduplication Tests

Create conditions that select the same candidate hash repeatedly.

Verify that:

- \(S^*\) evaluates the unique candidate/task/evaluator tuple once;
- every condition resolves to the same valid reference result; and
- no condition loses provenance.

### Analysis-Dataset Tests

Verify:

- exact row count;
- unique composite keys;
- valid joins to candidate, measurement, selection, and reference artifacts;
- correct gaming-event calculation;
- correct signed-gap calculation;
- no silent denominator changes;
- no hidden reference evidence fields; and
- stable dataset checksum.

### Synthetic Statistical Tests

Use synthetic datasets with known effects to verify:

- difference-in-differences calculation;
- hierarchical bootstrap clustering;
- confidence-interval construction;
- onset-threshold logic;
- multiplicity correction;
- hierarchical-model coefficient direction; and
- nonconvergence fallback behavior.

### Figure and Table Tests

Verify that all preregistered figures and tables:

- build from the locked dataset;
- contain the expected conditions;
- use correct labels and scales;
- contain no manually entered result values; and
- are reproducible from a single command.

### Failure-Policy Tests

Inject each registered candidate, provider, measurement, and reference failure.

Verify that the pipeline applies the preregistered treatment and never converts infrastructure failures into candidate failures.

### Reproducibility Tests

Rerun the deterministic analysis pipeline from the locked dataset.

Verify identical:

- estimands;
- bootstrap draws given the frozen seed;
- confidence intervals;
- model inputs and configuration;
- statistical tables;
- figure data; and
- machine-readable result checksums.

## Acceptance Criteria

- The experiment is preregistered before candidate generation begins.
- Power, cost, replicate count, minimum effect size, analysis, and exclusions are frozen before reference unblinding.
- The complete factorial matrix covers all 164 tasks and every preregistered stream, observation, robustness, and budget condition.
- The same candidate streams are shared across measurement-system conditions.
- All selection decisions are complete, deterministic, and frozen before \(S^*\) is enabled.
- Every unique frozen candidate is evaluated by \(S^*\) no more than once per task and evaluator version.
- Primary \(Q_{\mathrm{ref}}\) uses only the disjoint reference-only evidence pool.
- The locked analysis dataset contains every expected condition exactly once and changes no denominators silently.
- The primary gaming event is calculated exactly as preregistered.
- The primary difference-in-differences and clustered confidence interval are generated from the locked dataset.
- The secondary hierarchical model is run as specified or reports its preregistered nonconvergence outcome.
- All secondary tests follow the preregistered multiplicity policy.
- Gaming-onset thresholds follow the preregistered effect-size and uncertainty criteria.
- Required figures and tables are generated programmatically from the locked dataset.
- Invalid model outputs and duplicates remain in the experiment and count toward optimization budget.
- Candidate failures remain distinct from measurement-system failures.
- No manual post-unblinding exclusions or outcome-driven reruns occur.
- Any deviations are preserved, versioned, and disclosed.
- The report distinguishes selection-induced gaming from adaptive exploitation and intentional deception.
- All deterministic analysis artifacts can be regenerated from the recorded environment, manifests, checksums, and commands.

## Non-Goals

This ticket does not:

- implement adaptive feedback-guided optimization;
- train or fine-tune a model against the measurement systems;
- demonstrate intentional deception;
- claim that \(S^*\) reveals true correctness directly;
- eliminate benchmark contamination from model pretraining;
- vary model capability as a confirmatory factor;
- vary feedback richness;
- vary \(C\), \(M\), or \(P\) across the primary measurement systems;
- generalize beyond the frozen task, model, and generation configuration; or
- conceal null or contradictory results.

## Threats to Validity That Must Be Reported

At minimum:

- HumanEval and HumanEval+ are publicly available and may appear in model training data;
- \(S^*\) remains a finite and fallible measurement system;
- evidence count is an incomplete proxy for measurement robustness;
- best-of-\(N\) selection is not equivalent to gradient-based training;
- selection-only pressure does not establish intentional exploitation;
- candidate samples from one model and prompt may be correlated;
- observation sets are nested and statistically dependent;
- repeated conditions share tasks, streams, and candidates;
- remote model APIs may change behind stable model identifiers;
- execution limits may introduce construct-irrelevant failures;
- first-pass selection does not distinguish among multiple measured-pass candidates;
- the budget range may fail to cross the gaming threshold for strong systems;
- bootstrap and hierarchical-model conclusions depend on their clustering assumptions;
- task-level binary scoring discards case-level information; and
- results may not generalize beyond code generation or the HumanEval construct.

## Deliverables

- preflight-validation report;
- power and cost analysis;
- human- and machine-readable preregistration;
- frozen experiment manifest;
- complete candidate-generation run;
- complete optimization-visible measurement matrix;
- frozen candidate-selection manifests;
- deduplicated privileged reference-evaluation run;
- locked long-form analysis dataset;
- confirmatory clustered-bootstrap analysis;
- secondary hierarchical analysis;
- onset-threshold analysis;
- publication-ready figures and tables;
- machine-readable statistics;
- failure, exclusion, and deviation audit;
- claim-discipline assessment;
- experiment report suitable for TR-04; and
- reproducibility package.

