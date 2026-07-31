# [MEGB-05] Implement Controlled Candidate Generation and Best-of-\(N\) Optimization

## Objective

Implement the optimization-pressure harness for the first MEGB experiment.

The harness must:

1. generate fixed candidate streams under a frozen model configuration;
2. evaluate the same candidates against every optimization-visible measurement system \(S_k\);
3. apply deterministic best-of-\(N\) selection using only \(Q_{\mathrm{meas}}\);
4. freeze and hash the selected candidates; and
5. produce immutable candidate manifests for later reference evaluation by \(S^*\).

This ticket operationalizes optimization pressure as the number of candidate solutions available for selection:

\[
N \in \{1,2,4,8,16,32\}.
\]

It does not invoke \(S^*\) or calculate \(Q_{\mathrm{ref}}\).

## Dependencies

Depends on:

- `[MEGB-01] Establish HumanEval Corpus and Privileged Evaluation Boundary`
- `[MEGB-02] Implement Isolated Candidate Execution Worker`
- `[MEGB-03] Implement Privileged Reference Evaluator S*`
- `[MEGB-04] Implement Optimization-Visible Measurement Systems S1 ... S4`

## Primary Experimental Regime

The confirmatory experiment uses **selection-only optimization pressure**.

Candidate generation is independent of the measurement system. The model does not receive evaluator feedback and does not revise candidates interactively.

For every task and candidate-stream replicate:

1. generate one ordered stream of 32 candidate solutions;
2. preserve the raw and normalized candidate artifacts;
3. evaluate every candidate against every \(S_k\) and measurement-system replicate;
4. select a candidate independently at each optimization budget using a frozen deterministic rule; and
5. freeze the resulting selection manifest before any reference evaluation occurs.

The same candidate stream must be used across all measurement systems, robustness levels, observation-set replicates, and optimization budgets.

This creates a paired experiment: the candidate population is fixed, and only the measurement system and selection budget change.

## Scientific Rationale

The first experiment should isolate selection pressure before introducing adaptive model behavior.

An adaptive revision loop would additionally vary:

- model context;
- feedback interpretation;
- conversation history;
- prompt length;
- revision strategy;
- stopping behavior; and
- candidate distributions across measurement systems.

Selection-only optimization supports the cleaner claim:

> Holding the candidate distribution fixed, increasing selection pressure against an imperfect measurement system increases the probability of selecting a candidate that performs well under the measurement but poorly under the privileged reference evaluator.

Adaptive optimization may be added later as a separate, explicitly versioned experimental regime. It must not be pooled with the confirmatory selection-only results.

## Nested Optimization Budgets

Generate the maximum candidate stream once. Define every smaller budget as a prefix of that stream:

| Budget \(N\) | Eligible candidates |
| ---: | --- |
| 1 | Candidate 1 |
| 2 | Candidates 1–2 |
| 4 | Candidates 1–4 |
| 8 | Candidates 1–8 |
| 16 | Candidates 1–16 |
| 32 | Candidates 1–32 |

For a stream \((c_1, c_2, \ldots, c_{32})\), define:

\[
\mathcal{C}_N = \{c_1, \ldots, c_N\}.
\]

The eligible candidate sets must satisfy:

\[
\mathcal{C}_1
\subset
\mathcal{C}_2
\subset
\mathcal{C}_4
\subset
\mathcal{C}_8
\subset
\mathcal{C}_{16}
\subset
\mathcal{C}_{32}.
\]

Do not regenerate candidates independently for each budget.

## Requirements

### 1. Model-Generation Interface

Implement a provider-independent candidate-generation interface similar to:

```python
def generate_candidate_stream(
    task: PublicTaskDefinition,
    config: GenerationConfig,
    stream_context: CandidateStreamContext,
) -> CandidateStreamManifest:
    ...
```

The interface may use LiteLLM or another repository-approved abstraction, but provider-specific behavior must remain behind a versioned adapter.

Candidate generation must have access only to:

- the public task ID;
- the public task prompt;
- the authorized system prompt;
- the frozen generation configuration; and
- the candidate-stream seed where supported.

Candidate generation must not have access to:

- development test inputs;
- expected outputs;
- measurement-system source code;
- measurement results;
- reference-only test evidence;
- canonical solutions;
- \(S^*\) source code or results;
- prior candidates from other experimental conditions; or
- Git repository contents beyond explicitly authorized prompt artifacts.

### 2. Frozen Generation Configuration

Define a typed, immutable configuration containing at least:

```python
@dataclass(frozen=True)
class GenerationConfig:
    provider: str
    model_id: str
    model_version: str | None
    prompt_template_id: str
    system_prompt_id: str
    temperature: float
    top_p: float
    max_output_tokens: int
    stop_sequences: tuple[str, ...]
    requested_seed: int | None
    candidates_per_stream: int
    retry_policy_id: str
    sanitizer_version: str
    tool_profile_id: str
```

Record the complete provider request parameters and provider-returned model metadata for every generation.

If the provider does not guarantee deterministic seeded output, preserve the original response artifact. Experimental reproducibility must rely on the frozen candidate artifacts rather than assuming that a future API call will recreate identical text.

Any change that may affect candidate generation requires a new generation-configuration version.

### 3. Prompt Construction

Create a versioned prompt renderer.

The prompt must be identical across measurement-system conditions.

The renderer must record:

- prompt-template version;
- system-prompt version;
- task ID;
- exact rendered prompt hash;
- token count where available; and
- any provider-specific message transformation.

The prompt must not name the active measurement-system robustness level or reveal its evidence budget in the confirmatory selection-only experiment.

### 4. Candidate Artifact Preservation

For every generation, preserve:

- raw provider response;
- extracted candidate source;
- sanitizer output;
- extraction and sanitizer diagnostics;
- candidate hash;
- generation request metadata;
- provider response metadata;
- stream ID;
- candidate index; and
- generation timestamp.

Raw responses are immutable.

Sanitized source must be derived deterministically from the raw response using a frozen sanitizer version.

Never edit a candidate manually after generation.

### 5. Invalid Model Outputs

Distinguish model outputs from infrastructure failures.

The following are model outputs and count toward optimization budget \(N\):

- empty responses;
- refusals;
- malformed Markdown;
- unextractable code;
- syntactically invalid Python;
- missing entry points;
- duplicate solutions; and
- candidate code that fails during execution.

These must remain in the ordered stream and receive their ordinary measurement outcome.

Provider transport failures, authentication failures, rate-limit failures, and controller crashes are infrastructure failures. Apply only the frozen retry policy. If retries are exhausted, mark the stream incomplete rather than silently substituting an additional generation.

### 6. Duplicate Handling

Do not remove or replace duplicate candidates.

Every completed model generation consumes one position in the candidate stream, even when its normalized candidate hash duplicates an earlier position.

Record duplicate relationships for analysis:

```json
{
  "candidate_id": "candidate-017",
  "duplicate_of": "candidate-004"
}
```

Evaluation results may be safely cached by candidate hash and measurement-system configuration, but cached evaluation must not change candidate indices or effective budget.

### 7. Candidate Stream Manifest

Write one immutable manifest per task and stream replicate.

Example:

```json
{
  "schema_version": "1",
  "task_id": "HumanEval/0",
  "stream_id": "stream-003",
  "stream_seed": 1031,
  "model_id": "pinned-model",
  "generation_config_hash": "sha256:...",
  "prompt_hash": "sha256:...",
  "expected_candidate_count": 32,
  "completed_candidate_count": 32,
  "status": "COMPLETE",
  "candidates": [
    {
      "candidate_index": 1,
      "candidate_id": "candidate-001",
      "candidate_sha256": "sha256:...",
      "raw_response_sha256": "sha256:...",
      "generation_seed": 1031,
      "candidate_status": "EXTRACTED",
      "duplicate_of": null
    }
  ],
  "manifest_sha256": "sha256:..."
}
```

Candidate indices are one-based, stable, and immutable.

### 8. Measurement Evaluation Matrix

Evaluate each candidate in a complete stream against every configured optimization-visible system and replicate from MEGB-04.

The evaluation matrix is:

\[
\text{Task}
\times
\text{Candidate-stream replicate}
\times
\text{Candidate index}
\times
\text{Measurement robustness level}
\times
\text{Observation-set replicate}.
\]

All candidate evaluation must occur through the MEGB-04 interface and MEGB-02 isolated execution worker.

Evaluation may be parallelized, but parallel execution must not affect results, ordering, selection, or artifact identity.

### 9. Measurement Cache

Implement an immutable content-addressed cache keyed by at least:

```text
candidate_sha256
system_id
system_version
observation_manifest_checksum
comparison_profile_id
execution_profile_id
```

Do not reuse results across mismatched system definitions or execution profiles.

Cache hits and misses must be recorded.

An invalid or incomplete measurement must not be reused as a valid result.

### 10. Deterministic Selection Rule

For each tuple:

```text
(task_id, stream_id, system_id, optimization_budget_n)
```

apply the following selection rule:

1. Consider only candidates with `candidate_index <= N`.
2. Require a valid measurement for every candidate needed by the selection rule.
3. Select the lowest-index candidate with \(q_{\mathrm{meas}}=1\).
4. If no candidate passes, select candidate index 1.
5. Record the selection reason and complete eligible-prefix hash.

Formally:

\[
c^*_{k,N} =
\begin{cases}
c_j, & j = \min\{i \leq N : q_{\mathrm{meas}}^{(k)}(c_i)=1\} \\
c_1, & \text{if no such }j\text{ exists.}
\end{cases}
\]

Do not use any of the following as tie-breakers:

- \(Q_{\mathrm{ref}}\);
- HumanEval+ reference outcomes;
- code length;
- model confidence;
- human judgment;
- later candidates once an earlier passing candidate exists; or
- any unregistered auxiliary metric.

The selection rule models a process that stops at the first measured success.

### 11. Selection Decision Schema

Write an append-only selection record containing at least:

```json
{
  "schema_version": "1",
  "task_id": "HumanEval/0",
  "stream_id": "stream-003",
  "system_id": "S2-r3",
  "system_version": "v1",
  "optimization_budget_n": 8,
  "eligible_prefix_sha256": "sha256:...",
  "selected_candidate_index": 6,
  "selected_candidate_id": "candidate-006",
  "selected_candidate_sha256": "sha256:...",
  "selection_reason": "FIRST_MEASURED_PASS",
  "Q_meas": 1.0,
  "reference_evaluated": false,
  "selection_config_sha256": "sha256:...",
  "timestamp": "2026-07-31T16:00:00Z"
}
```

Supported selection reasons must include:

```text
FIRST_MEASURED_PASS
NO_MEASURED_PASS_DEFAULT_FIRST
INVALID_MEASUREMENT_ABORT
INCOMPLETE_STREAM_ABORT
```

### 12. Frozen Candidate Manifest

After all measurement-only selections are complete, produce a frozen candidate manifest for downstream reference evaluation.

The manifest must include:

- experiment run ID;
- task ID;
- candidate-stream ID and checksum;
- measurement-system ID and version;
- observation-set replicate;
- optimization budget;
- selected candidate ID and hash;
- selection record checksum;
- selection configuration checksum;
- code revision;
- freeze timestamp; and
- manifest checksum.

The manifest must explicitly state:

```json
{
  "selection_complete": true,
  "reference_evaluation_started": false
}
```

Once frozen, candidate selections may not be changed, regenerated, or replaced.

MEGB-03 must evaluate only candidates identified by a valid frozen manifest.

### 13. Reference-Evaluator Isolation

The MEGB-05 package and runtime must not:

- import the privileged reference evaluator;
- read reference-only evidence;
- read reference expected outputs;
- query \(S^*\);
- read prior \(Q_{\mathrm{ref}}\) results; or
- modify selections after reference evaluation.

The dependency direction is:

```text
candidate generation
        ↓
optimization-visible measurement
        ↓
deterministic selection
        ↓
frozen candidate manifest
        ↓
separate privileged reference evaluation
```

The final arrow is outside MEGB-05.

### 14. Optimization-Pressure Monotonicity

For the deterministic first-pass selection rule:

\[
Q_{\mathrm{meas}}(k,N)
\]

must be nondecreasing as \(N\) increases.

Once a passing candidate appears in a stream for a given system, the selected candidate must remain unchanged at every larger budget.

If this invariant fails, treat it as an implementation defect or invalid measurement—not as an experimental result.

### 15. Configuration

Create a versioned configuration similar to:

```yaml
optimizer_id: selection-only-first-pass-v1
regime: selection_only
candidate_stream_length: 32
optimization_budgets:
  - 1
  - 2
  - 4
  - 8
  - 16
  - 32
selection_rule: first_measured_pass
fallback_rule: first_candidate
duplicate_policy: preserve_and_count
invalid_model_output_policy: preserve_and_count
infrastructure_failure_policy: retry_then_invalidate_stream
reference_feedback_allowed: false
measurement_feedback_to_model: none
```

The number of candidate-stream replicates is configured by MEGB-06 based on the preregistered power and cost analysis. MEGB-05 must support arbitrary replicate counts without changing the optimizer definition.

### 16. Command-Line Interface

Provide noninteractive commands similar to:

```bash
megb generate-candidate-streams \
  --task-manifest artifacts/corpus/public-tasks.json \
  --generation-config configs/generation/model-v1.yaml \
  --stream-config configs/optimization/streams-v1.yaml \
  --output artifacts/candidate-streams/
```

```bash
megb evaluate-candidate-streams \
  --candidate-streams artifacts/candidate-streams/ \
  --system-family-manifest artifacts/measurement-systems/frozen-v1.json \
  --output artifacts/measurement-results/
```

```bash
megb select-candidates \
  --candidate-streams artifacts/candidate-streams/ \
  --measurement-results artifacts/measurement-results/ \
  --optimizer-config configs/optimization/selection-only-v1.yaml \
  --output artifacts/frozen-selections/
```

Every command must:

- validate input checksums;
- write append-only results;
- support safe resumption;
- avoid overwriting valid completed artifacts;
- return a nonzero exit code for incomplete or invalid runs; and
- record the exact reproducibility command.

### 17. Audit and Cost Records

Record:

- provider request count;
- completed generation count;
- retry count;
- input and output tokens where available;
- provider-reported cost where available;
- wall-clock duration;
- candidate-execution count;
- cache hit and miss counts;
- incomplete streams;
- invalid measurements;
- selection count; and
- artifact checksums.

Operational cost metadata must not affect candidate selection.

### 18. Documentation

Create:

```text
docs/experiments/selection-pressure.md
docs/experiments/candidate-generation.md
```

Document:

- the operational definition of optimization pressure;
- why selection-only optimization is confirmatory;
- nested candidate prefixes;
- frozen model and prompt configuration;
- invalid-output and duplicate policies;
- deterministic selection;
- candidate freezing;
- reference-evaluator isolation;
- reproducibility limitations of remote model APIs;
- cost accounting;
- known limitations; and
- threats to validity.

## Required Tests

### Candidate-Stream Tests

Verify:

- exactly 32 ordered candidate positions in a complete stream;
- stable one-based candidate indices;
- immutable raw-response artifacts;
- deterministic extraction and sanitation;
- candidate and artifact checksum validation;
- duplicate preservation;
- invalid model-output preservation;
- provider infrastructure failure classification; and
- incomplete-stream behavior after exhausted retries.

### Budget-Prefix Tests

Verify exactly:

```text
C1  = candidates[1:1]
C2  = candidates[1:2]
C4  = candidates[1:4]
C8  = candidates[1:8]
C16 = candidates[1:16]
C32 = candidates[1:32]
```

Verify that every smaller budget is a strict prefix of every larger configured budget.

### Shared-Candidate Tests

Verify that every measurement-system condition receives identical candidate source and candidate hashes for the same:

```text
(task_id, stream_id, candidate_index)
```

No measurement system may trigger candidate regeneration.

### Selection-Rule Tests

Test streams in which:

- the first candidate passes;
- only candidate 2 passes;
- only candidate 7 passes;
- several candidates pass;
- no candidate passes;
- candidates are duplicated;
- candidates are syntactically invalid; and
- one measurement is invalid.

Verify the exact selected candidate and selection reason at every optimization budget.

### Optimization Monotonicity Tests

For every test stream and system, verify:

\[
Q_{\mathrm{meas}}(N=1)
\le
Q_{\mathrm{meas}}(N=2)
\le
Q_{\mathrm{meas}}(N=4)
\le
Q_{\mathrm{meas}}(N=8)
\le
Q_{\mathrm{meas}}(N=16)
\le
Q_{\mathrm{meas}}(N=32).
\]

Once a passing candidate is selected, verify that the selected hash remains unchanged at larger budgets.

### Freeze-Manifest Tests

Verify:

- every selected candidate hash resolves to the candidate-stream artifact;
- every selection record resolves to valid measurement results;
- freeze manifests reject missing or mismatched checksums;
- frozen selections cannot be overwritten;
- incomplete streams cannot produce valid freeze manifests; and
- reference evaluation has not occurred before freeze.

### Reference-Isolation Tests

Verify that the MEGB-05 package and runtime cannot:

- import \(S^*\);
- read reference manifests;
- read reference expected outputs;
- read prior reference results; or
- call the reference-evaluation command.

### Resumption Tests

Interrupt generation, measurement, and selection at controlled points.

Verify that resumption:

- preserves completed artifacts;
- does not duplicate completed model requests;
- does not reorder candidate indices;
- does not change selection outcomes; and
- does not overwrite valid records.

### Reproducibility Tests

Using fixed stored candidate artifacts, rerun measurement and selection.

Verify identical:

- candidate hashes;
- measurement lookups;
- selected candidate hashes;
- selection reasons;
- eligible-prefix hashes; and
- freeze-manifest checksums, excluding explicitly documented timestamp fields.

## Acceptance Criteria

- The harness generates immutable ordered streams of 32 candidate positions per task and stream replicate.
- The same candidate streams are used across every \(S_k\) and observation-set replicate.
- Optimization budgets are exactly \(1,2,4,8,16,32\) and use nested prefixes.
- Model, prompt, sampling, extraction, sanitizer, retry, and tool configurations are frozen and versioned.
- Raw provider responses and normalized candidate artifacts are preserved and checksummed.
- Duplicate candidates remain in the stream and count toward \(N\).
- Invalid model outputs remain in the stream and count toward \(N\).
- Infrastructure failures are not silently converted into model candidates.
- Candidate selection uses only optimization-visible measurement outcomes.
- Selection always chooses the lowest-index measured-pass candidate, falling back to candidate 1 when none pass.
- \(Q_{\mathrm{meas}}\) is nondecreasing with optimization budget for every fixed stream and measurement system.
- Once a measured-pass candidate is selected, larger budgets preserve the same selection.
- Selection is deterministic and reproducible from frozen candidate and measurement artifacts.
- Frozen candidate manifests are created before any reference evaluation.
- MEGB-05 cannot access, import, or invoke \(S^*\).
- No candidate is regenerated, edited, or replaced after observing reference results.
- Commands support safe resumption without reordering, duplicating, or overwriting valid artifacts.
- Complete generation, measurement, selection, audit, and cost records are preserved.

## Non-Goals

This ticket does not:

- implement adaptive feedback-guided optimization;
- expose measurement feedback to the candidate-generating model;
- invoke \(S^*\);
- calculate \(Q_{\mathrm{ref}}\);
- calculate gaming deltas;
- run the final factorial experiment;
- perform statistical analysis;
- generate publication figures;
- choose the number of experimental stream replicates;
- compare model capabilities; or
- classify intentional versus accidental gaming.

## Threats to Validity That Must Be Documented

At minimum:

- best-of-\(N\) selection is not identical to gradient-based model training;
- selection-only pressure does not demonstrate intentional exploitation;
- remote model APIs may not reproduce identical outputs when rerun;
- model providers may update behavior behind stable identifiers;
- candidate streams may contain correlated samples;
- early-first-pass selection does not distinguish among multiple measured-pass candidates;
- malformed outputs and duplicates reduce effective candidate diversity while still consuming budget;
- the maximum budget of 32 may not reach the gaming threshold for every task or system;
- candidate-generation prompts may favor particular implementation styles; and
- results may not generalize beyond the frozen model and sampling configuration.

## Deliverables

- provider-independent candidate-generation interface;
- frozen generation and prompt configurations;
- deterministic candidate extraction and sanitation;
- immutable raw and normalized candidate artifacts;
- ordered candidate-stream manifests;
- measurement-evaluation matrix and cache;
- deterministic best-of-\(N\) selector;
- append-only selection records;
- frozen candidate manifests for MEGB-03;
- generation, measurement, selection, audit, and cost CLIs;
- unit and integration tests;
- resumption and reference-isolation tests; and
- candidate-generation and selection-pressure documentation.

