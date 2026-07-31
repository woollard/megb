# [MEGB-07] Replicate the Gaming Result Against a Private Post-Snapshot Adversarial Holdout

## Objective

Construct a private, candidate-blind adversarial test suite and use it to replicate the MEGB-06 result without relying exclusively on public HumanEval+ evidence.

The private suite must:

* be created after the evaluated model snapshot;
* remain unavailable to candidate generation and optimization;
* be constructed without inspecting experimental candidates or outcomes;
* use independently validated task-specific inputs and reference outputs;
* be frozen before evaluation;
* evaluate only candidates already selected and frozen by MEGB-06; and
* produce a separately reported private reference measurement (Q_{\mathrm{private}}).

This ticket tests whether the observed measurement-robustness × optimization-pressure interaction persists under evidence that the evaluated model could not have memorized during pretraining.

## Status of This Experiment

MEGB-07 is a contamination-resistant replication of MEGB-06.

It does not replace:

* the primary MEGB-06 confirmatory result;
* the HumanEval+ compatibility result; or
* the MEGB-03 reference evaluator.

It provides an independent validation measurement:

[
S^\dagger =
(C^\dagger, O^\dagger, M^\dagger, P^\dagger)
]

where:

* (C^\dagger): the same HumanEval functional-correctness construct;
* (O^\dagger): newly created private inputs and outcomes;
* (M^\dagger): the same all-cases-must-pass task scoring rule;
* (P^\dagger): isolated execution using the MEGB-02 worker.

The private evaluator remains a fallible measurement system and must not be described as direct access to true correctness.

## Dependencies

Depends on:

* `[MEGB-01] Establish HumanEval Corpus and Privileged Evaluation Boundary`
* `[MEGB-02] Implement Isolated Candidate Execution Worker`
* `[MEGB-03] Implement Privileged Reference Evaluator S*`
* `[MEGB-05] Implement Controlled Candidate Generation and Best-of-N Optimization`
* `[MEGB-06] Preregister, Execute, and Analyze the Measurement-Robustness × Optimization-Pressure Experiment`

Private-suite authoring may begin before MEGB-06 completes. Candidate evaluation may begin only after MEGB-06 selections are frozen.

## Blinding Requirement

Private-suite construction must be completed without access to:

* MEGB-06 candidate source code;
* selected candidate identities;
* optimization-visible measurement outcomes;
* HumanEval+ reference outcomes for experimental candidates;
* per-task gaming events;
* aggregate MEGB-06 results; or
* failure examples selected because they support the hypothesis.

The private-suite manifest must be frozen before the authoring team is unblinded to experimental outcomes.

If MEGB-06 outcomes have already been inspected, task selection and test construction must follow a deterministic, candidate-independent procedure that was specified before accessing candidate artifacts. The loss of prospective blinding must be documented.

## Research Question

> Does the interaction between measurement robustness and optimization pressure replicate when candidate performance is evaluated against newly created, private, post-snapshot evidence?

## Primary Private Outcome

Define:

[
q_{\mathrm{private},i}
======================

\begin{cases}
1, & \text{if the frozen candidate passes every private case for task } i \
0, & \text{if it produces a validly measured failure} \
\text{undefined}, & \text{if private evaluation is invalid}
\end{cases}
]

and:

[
Q_{\mathrm{private}}
====================

\frac{1}{T}
\sum_{i=1}^{T} q_{\mathrm{private},i},
]

where (T) is the preregistered private task set.

Define the private gaming event:

[
G^\dagger_{i,k,N}
=================

\mathbb{1}
\left[
q_{\mathrm{meas},i}^{(k,N)}=1
\land
q_{\mathrm{private},i}^{(k,N)}=0
\right].
]

The aggregate private gaming rate is:

[
G^\dagger(k,N)
==============

\frac{1}{T}
\sum_{i=1}^{T}G^\dagger_{i,k,N}.
]

## Primary Replication Estimand

Use the same robustness × pressure contrast as MEGB-06:

[
D^\dagger
=========

\left[
G^\dagger(S_1,32)-G^\dagger(S_1,1)
\right]
-------

\left[
G^\dagger(S_4,32)-G^\dagger(S_4,1)
\right].
]

The preregistered prediction is:

[
D^\dagger>0.
]

The replication protocol must define:

* minimum meaningful replication effect;
* clustered uncertainty procedure;
* required directional consistency;
* required confidence-interval criterion; and
* treatment of a smaller but directionally consistent effect.

Do not change the replication criterion after observing private results.

## Requirements

### 1. Evaluated Model Snapshot

Record the evaluated model’s:

* provider;
* exact model identifier;
* model version or snapshot where available;
* documented release date;
* candidate-generation dates;
* generation-configuration checksum; and
* evidence supporting the claim that private cases were created after the relevant snapshot.

If the provider does not expose a stable model snapshot, describe the limitation explicitly. “Post-snapshot” must not be claimed more strongly than the available evidence permits.

### 2. Private Task Set

Evaluating all 164 tasks is preferred.

If full coverage is impractical, select a preregistered subset using a candidate-independent procedure.

The subset must:

* contain at least 40 tasks unless the power analysis requires more;
* be selected without reference to experimental outcomes;
* use a stable deterministic task-selection algorithm;
* cover a range of input and output types;
* include numeric, string, sequence, collection, and logical tasks where available;
* include both simple and constraint-sensitive specifications;
* record selected and excluded task IDs;
* document every exclusion; and
* preserve the original HumanEval prompt and entry point.

The exact task count must be determined by a private-replication power and cost analysis before private evaluation.

### 3. Task Ambiguity Review

Before generating private cases, review every selected task specification for:

* undefined input domains;
* ambiguous expected behavior;
* conflicting examples;
* underspecified edge cases;
* numerical-tolerance requirements;
* permitted input mutation;
* multiple valid outputs; and
* disagreement between HumanEval and corrected EvalPlus interpretations.

Classify each task as:

```text
ELIGIBLE
ELIGIBLE_WITH_DOCUMENTED_CONTRACT
AMBIGUOUS
EXCLUDED
```

Ambiguous tasks must be resolved before candidate evaluation or excluded according to the preregistered policy.

Do not resolve ambiguity by inspecting candidate behavior.

### 4. Private Contract Specification

For every eligible task, create a private contract defining:

* valid input domain;
* invalid or out-of-scope inputs;
* relationships between arguments;
* expected return type;
* output-comparison semantics;
* numerical tolerance;
* mutation semantics;
* determinism expectations; and
* resource assumptions.

The contract must be derived from the task prompt and documented benchmark interpretation—not from experimental candidate outputs.

### 5. Private Input Construction

Create at least 50 unique valid private cases per selected task unless a task-specific justification requires a different number.

Each task suite should include:

* manually constructed boundary cases;
* common-case inputs;
* empty or minimum-size inputs where valid;
* maximum or stress-oriented inputs within the intended domain;
* duplicated-value cases;
* ordering-sensitive cases;
* sign and zero cases for numeric tasks;
* Unicode or unusual-character cases where valid;
* floating-point edge cases where relevant;
* cases targeting common off-by-one errors;
* cases targeting branch and condition boundaries; and
* deterministically generated cases from a task-specific input generator.

At least ten cases per task should be explicitly designated as manually reviewed boundary or adversarial cases.

Do not infer inputs generically from function signatures alone.

### 6. Candidate-Blind Adversarial Design

Adversarial cases may target general implementation failure patterns, including:

* hardcoded examples;
* constant returns;
* incomplete branching;
* off-by-one errors;
* wrong comparison operators;
* incorrect handling of duplicates;
* incorrect ordering assumptions;
* integer/float confusion;
* empty-input failures;
* incorrect mutation behavior;
* inappropriate asymptotic shortcuts;
* state retained across calls; and
* dependence on test order.

Cases must not be designed around the behavior of MEGB-06 experimental candidates.

Permitted inputs to adversarial design include:

* the task specification;
* corrected canonical solutions;
* independently written reference solutions;
* generic mutation operators;
* pre-experimental validation mutants; and
* common programming-error taxonomies.

### 7. External Model Use

By default, do not submit private contracts, generators, cases, or expected outputs to an external generative-model API.

If model assistance is used, the protocol must preregister:

* the model and provider;
* data-retention terms;
* whether the evaluated model or a related model is involved;
* what private evidence is exposed;
* how generated cases are independently validated; and
* why the exposure does not undermine the post-snapshot claim.

Model-generated cases may supplement but must not replace independent human or deterministic validation.

### 8. Independent Reference Implementation

For every selected task, maintain:

1. the corrected EvalPlus canonical solution; and
2. a separately authored reference implementation or independently specified oracle.

The independent implementation must be written without copying the canonical solution line by line.

Every private test input must be evaluated by both reference implementations.

A test case is eligible only when:

* both implementations complete validly;
* both produce equivalent outputs under the frozen comparison rules; and
* no unresolved contract ambiguity remains.

Disagreements must be adjudicated before the suite is frozen. Do not select whichever output causes more experimental candidates to fail.

### 9. Expected-Output Artifact

Generate expected outputs in the trusted private environment.

The expected-output artifact must record:

* task ID;
* private case ID;
* private contract version;
* input checksum;
* expected-output checksum;
* canonical-solution hash;
* independent-solution hash;
* comparison-profile ID;
* agreement status; and
* generation timestamp.

Expected outputs must never enter the candidate execution environment.

### 10. Mutation Validation

Validate each private suite against a candidate-independent mutation corpus.

Mutation operators should include:

* constant return;
* deleted branch;
* inverted conditional;
* comparator replacement;
* arithmetic-operator replacement;
* boundary shift;
* removed iteration;
* early return;
* incorrect initialization;
* dropped element;
* duplicate removal or insertion;
* sort-order reversal; and
* type-conversion changes.

Identify equivalent or invalid mutants separately.

For each task, report:

[
\operatorname{MutationScore}
============================

\frac{\text{non-equivalent mutants rejected}}
{\text{non-equivalent mutants evaluated}}.
]

Define the minimum acceptable mutation score before evaluating experimental candidates. A default target of at least 90% is recommended, subject to preregistration.

Do not add cases after inspecting which experimental candidates survive.

### 11. Private Suite Review

Require a second independent review of every selected task.

The reviewer must verify:

* contract consistency with the prompt;
* input validity;
* expected-output agreement;
* comparison semantics;
* numerical tolerances;
* adversarial-case relevance;
* mutation-validation results;
* absence of experimental-candidate influence; and
* readiness for freeze.

Record review status:

```text
APPROVED
APPROVED_WITH_NOTES
REVISION_REQUIRED
REJECTED
```

Only approved tasks may enter private evaluation.

If one person performs both roles, use temporally separated passes and preserve independent checklists. Document the weaker independence.

### 12. Private Storage Boundary

Store private suite contents outside:

* the public repository;
* candidate-generation environments;
* optimizer-visible containers;
* model prompts;
* ordinary experiment logs;
* public CI artifacts; and
* public issue descriptions.

The public repository may contain:

* schemas;
* evaluator interfaces;
* aggregate metadata;
* case counts;
* task IDs where disclosure is acceptable;
* suite and manifest checksums; and
* validation summaries that reveal no test content.

Private artifacts must have:

* access controls;
* audit logging;
* encrypted storage where available;
* versioned backups;
* immutable checksums; and
* a documented release policy.

### 13. Private Suite Manifest

Before candidate evaluation, freeze a manifest containing:

```json
{
  "suite_id": "megb-private-holdout-v1",
  "evaluated_model_id": "pinned-model",
  "model_snapshot_date": "YYYY-MM-DD",
  "suite_creation_started_at": "YYYY-MM-DD",
  "suite_frozen_at": "YYYY-MM-DD",
  "task_count": 40,
  "case_count": 2000,
  "task_manifest_sha256": "sha256:...",
  "contract_manifest_sha256": "sha256:...",
  "input_manifest_sha256": "sha256:...",
  "oracle_manifest_sha256": "sha256:...",
  "comparison_profile_sha256": "sha256:...",
  "mutation_validation_sha256": "sha256:...",
  "review_manifest_sha256": "sha256:...",
  "experimental_candidates_inspected": false,
  "experimental_outcomes_inspected": false,
  "status": "FROZEN"
}
```

The manifest must not contain private inputs or expected outputs.

Any change after freeze requires a new suite version.

### 14. Private Evaluator

Implement a privileged private evaluator separate from (S^*):

```python
def evaluate_private(
    task_id: str,
    candidate_code: str,
    context: PrivateEvaluationContext,
) -> PrivateTaskResult:
    ...
```

The evaluator must:

* use MEGB-02 isolated execution;
* pass only the current input to candidate code;
* keep expected outputs on the trusted side;
* verify frozen candidate hashes;
* verify private-suite checksums;
* apply the private comparison profile;
* distinguish candidate failure from measurement failure;
* write append-only audit records; and
* expose no case-level feedback to optimization systems.

### 15. Private Result Schema

Record at least:

```python
@dataclass(frozen=True)
class PrivateTaskResult:
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
    suite_manifest_sha256: str

    started_at: str
    duration_sec: float
```

Detailed failure artifacts remain private.

Public results must not expose:

* private inputs;
* expected outputs;
* failing case IDs;
* per-case pass vectors; or
* exception details containing private evidence.

### 16. Frozen-Candidate Evaluation

Evaluate only candidates selected and frozen by MEGB-06.

Do not:

* generate new candidates;
* revise selected candidates;
* change selection rules;
* select candidates using private results;
* rerun optimization after viewing private outcomes; or
* evaluate additional candidates because the first results are surprising.

Evaluate each unique:

```text
(task_id, candidate_sha256, private_suite_version)
```

once and reuse the valid result wherever that candidate was selected in multiple conditions.

### 17. Private Replication Dataset

Create a locked private-replication analysis dataset with one row per:

```text
(task_id,
 candidate_stream_id,
 observation_replicate,
 robustness_level,
 optimization_budget)
```

Include:

* selected candidate ID and hash;
* (q_{\mathrm{meas}});
* HumanEval+ (q_{\mathrm{ref}});
* private (q_{\mathrm{private}});
* public-reference gaming event;
* private gaming event;
* measurement statuses;
* suite version and checksum;
* condition provenance; and
* task-subset membership.

Do not include private case contents.

### 18. Private Replication Analysis

Estimate:

[
D^\dagger
=========

\left[
G^\dagger(S_1,32)-G^\dagger(S_1,1)
\right]
-------

\left[
G^\dagger(S_4,32)-G^\dagger(S_4,1)
\right].
]

Use the same clustered bootstrap structure as MEGB-06, restricted to the private task set.

Report:

* point estimate;
* two-sided 95% confidence interval;
* minimum replication effect;
* directional consistency with MEGB-06;
* private task count;
* stream and observation replicate counts; and
* whether the preregistered replication criterion was met.

Do not pool MEGB-06 and MEGB-07 outcomes to rescue a failed result.

### 19. Public–Private Agreement Analysis

Compare (q_{\mathrm{ref}}) and (q_{\mathrm{private}}) using:

* raw task-level agreement;
* pass/pass count;
* pass/fail count;
* fail/pass count;
* fail/fail count;
* disagreement rate;
* agreement by robustness and budget;
* agreement by task category; and
* an appropriate chance-corrected agreement statistic where informative.

Investigate disagreements without changing either evaluator.

Interpret:

```text
q_ref = 1, q_private = 0
```

as evidence that the public reference suite may have missed a failure or that the private suite introduced a divergent construct interpretation.

Interpret:

```text
q_ref = 0, q_private = 1
```

as evidence that the private suite may be less sensitive, differently specified, or incomplete.

Neither result establishes which evaluator is “true” without further analysis.

### 20. Required Figures

Generate:

1. **Private gaming rate by optimization pressure and robustness**

   * same axes and visual grammar as the MEGB-06 primary figure;
   * uncertainty ribbons from the preregistered clustered bootstrap.

2. **Public versus private reference comparison**

   * paired (Q_{\mathrm{ref}}) and (Q_{\mathrm{private}}) curves.

3. **Public/private disagreement heatmap**

   * disagreement rates across robustness and pressure.

4. **Task-level agreement matrix**

   * pass/pass, pass/fail, fail/pass, and fail/fail counts.

5. **Mutation sensitivity summary**

   * private-suite mutation scores by task or task category.

All figures must be generated programmatically from locked artifacts.

### 21. Release Policy

Before evaluation, publish or timestamp:

* suite ID;
* model snapshot claim;
* task count;
* total case count;
* construction protocol;
* suite checksum;
* manifest checksum; and
* preregistration checksum.

Do not release private cases before candidate selection and private evaluation are complete.

After final analysis, choose and document one of:

* release the complete private suite for reproducibility;
* release it after paper acceptance;
* release an encrypted archive with delayed key disclosure; or
* retain it for future private replication while releasing sufficient aggregate validation evidence.

The policy must balance reproducibility against preserving a genuinely private future benchmark.

## Required Tests

### Privacy-Boundary Tests

Verify that candidate-generation and optimization environments cannot:

* locate private manifests;
* read private inputs;
* read expected outputs;
* import private evaluator modules;
* access private result artifacts; or
* infer private evidence from logs.

### Contract and Oracle Tests

For every private case, verify:

* input satisfies the private contract;
* both reference implementations complete;
* outputs agree;
* comparison rules are deterministic; and
* input and output checksums match the frozen manifest.

### Canonical-Solution Tests

Every corrected canonical and independent reference solution must receive:

```text
q_private_task = 1.0
```

for every included task.

Any failure blocks suite freeze.

### Mutation Tests

Verify that:

* mutation operators execute as intended;
* equivalent mutants are identified separately;
* mutation scores reproduce from frozen artifacts; and
* every task meets the preregistered mutation-score requirement.

### Freeze Tests

Verify that:

* suite contents cannot change after freeze;
* manifest checksums resolve to exact artifacts;
* experimental candidates were not inspected during construction;
* private evaluation rejects unfrozen suites; and
* any change creates a new suite version.

### Candidate-Freeze Tests

Verify that:

* every evaluated candidate was frozen by MEGB-06;
* hashes match exactly;
* no candidate is added or replaced after private results exist; and
* duplicate selections reuse one valid private result.

### Measurement-Failure Tests

Inject private oracle, sandbox, protocol, and infrastructure failures.

Verify that they produce:

```python
q_private_task = None
```

rather than candidate failure.

### Analysis Tests

Using synthetic data, verify:

* private gaming-event calculation;
* (D^\dagger);
* clustered-bootstrap logic;
* agreement tables;
* disagreement metrics;
* replication-criterion logic; and
* figure generation.

## Acceptance Criteria

* The private suite is created after the evaluated model snapshot to the extent supported by provider metadata.
* The private task set is selected independently of experimental outcomes.
* At least the preregistered number of tasks and cases are included.
* Every task has a documented valid-input contract.
* Every private case is candidate-blind and contract-valid.
* Corrected canonical and independent reference solutions agree on every included case.
* Every task passes independent review.
* Every task meets the preregistered mutation-sensitivity requirement.
* Private artifacts are frozen and checksummed before experimental candidate evaluation.
* Candidate-generation and optimization environments cannot access private evidence.
* Only MEGB-06 frozen candidates are evaluated.
* No candidate is regenerated, revised, or reselected after private evaluation.
* Each unique candidate/task/suite tuple is evaluated once.
* Candidate failures remain distinct from private measurement failures.
* The private replication dataset is complete, locked, and traceable to source artifacts.
* (D^\dagger) and its clustered confidence interval are calculated exactly as preregistered.
* Public/private agreement and disagreement are reported without privileging either evaluator as ground truth.
* Null, contradictory, or weaker private results are preserved and reported.
* Private cases are not released until evaluation and selection are complete.
* The final report accurately limits the contamination-resistance claim to private test evidence, not private task specifications.

## Non-Goals

This ticket does not:

* replace MEGB-06’s confirmatory experiment;
* expose the private suite as another optimization target;
* generate new model candidates;
* implement adaptive optimization;
* establish intentional deception;
* make the HumanEval prompts private;
* prove the absence of all training contamination;
* formally verify candidate correctness;
* claim that (S^\dagger) is infallible;
* tune private cases against experimental candidate failures; or
* combine public and private outcomes post hoc to manufacture significance.

## Threats to Validity That Must Be Reported

At minimum:

* HumanEval task prompts remain public even when tests are private;
* model snapshot dates may be uncertain;
* post-snapshot tests reduce but do not eliminate contamination concerns;
* private task subsets may not represent all 164 tasks;
* test authors may inherit assumptions from public canonical solutions;
* independent implementations may share conceptual errors;
* mutation score does not guarantee construct coverage;
* manually authored adversarial cases may reflect author biases;
* private test count remains a finite proxy for correctness;
* stronger private evidence may alter the intended construct;
* suite secrecy complicates immediate public reproducibility;
* smaller task sets reduce statistical power;
* private and public suites may differ in difficulty and domain coverage; and
* results may not generalize beyond the evaluated model snapshot.

## Deliverables

* private-replication preregistration;
* model-snapshot provenance record;
* private task-selection manifest;
* task ambiguity review;
* private contract specifications;
* private input generators and manually reviewed cases;
* independent reference implementations;
* private expected-output artifacts;
* mutation corpus and validation report;
* independent review records;
* frozen private-suite manifest and checksums;
* privileged private evaluator;
* frozen-candidate private evaluation;
* locked private-replication analysis dataset;
* clustered replication analysis;
* public/private agreement analysis;
* publication-ready figures and tables;
* privacy and access audit;
* private-suite release plan; and
* MEGB-07 replication report.

