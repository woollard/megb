# [MEGB-05] Implement Controlled Candidate Generation and Selection-Only Optimization

## Epic Status

**Status:** Not started  
**Execution mode:** Sequential gated subtasks  
**Subtasks:** MEGB-05A through MEGB-05G  
**Dependencies:** MEGB-01 through MEGB-04  
**Specification status:** Authoritative corrected ticket  
**Specification version:** `megb-05-ticket-v2`  
**Supersedes:** the historical monolithic, annotated, merged, and earlier refactored MEGB-05 tickets

Once committed, this document is the sole governing MEGB-05 specification. Historical MEGB-05 files may be retained for audit history, but their requirements must not be combined with this ticket.

Where an approved amendment conflicts with earlier text, the amendment governs. Superseded language is preserved only in repository history, not repeated as an alternative operating rule.

## Epic Objective

Implement the optimization-pressure harness for the first MEGB experiment.

The harness must:

1. generate fixed candidate streams under a frozen model and prompt configuration;
2. preserve every candidate position, including duplicates and invalid model outputs;
3. evaluate the same candidates against every optimization-visible measurement system \(S_k\);
4. apply preregisterable selection policies over nested best-of-\(N\) prefixes;
5. implement and validate the freeze-and-hash transition that MEGB-06 will apply before reference evaluation; and
6. produce schemas and reduced-fixture immutable candidate manifests suitable for later one-time evaluation by \(S^*\).

This epic operationalizes optimization pressure as the number of candidate solutions available to a selection process:

\[
N \in \{1,2,4,8,16,32\}.
\]

MEGB-05 does not invoke \(S^*\), calculate \(Q_{\mathrm{ref}}\), calculate gaming deltas, or run the final experiment.

## Approved Pre-Experimental Population Amendment — MEGB-03A.1

**Status:** Approved and executed before any MEGB-05 confirmatory candidate generation or measurement.

Every primary-regime task collection, candidate stream, measurement matrix, selection coordinate, and freeze manifest must explicitly consume the frozen `primary_experiment_task_manifest` established by MEGB-03A.1.

The accepted manifest contains 163 tasks and excludes HumanEval/39 a priori. HumanEval/39 has no optimization-visible development pool or \(q_{\mathrm{meas}}\) and must never receive a candidate stream, measurement row, selection record, or frozen experimental candidate under this ticket.

The separate 164-task `reference_validation_task_manifest` belongs to MEGB-03 validation and must not be substituted for the MEGB-05 experimental task population.

Every configured run must bind the primary task-manifest ID, checksum, and expected count. Task membership is determined by the frozen manifest—not by discovering available prompt files or iterating over the full HumanEval corpus.

## Implementation Versus Confirmatory Execution Boundary

MEGB-05 implements and validates reusable experimental machinery. It does **not** execute the confirmatory MEGB-06 experiment.

During MEGB-05A through MEGB-05G:

- ordinary tests use deterministic mock/fake providers;
- integration tests use synthetic, reduced, or explicitly nonconfirmatory fixtures;
- any authorized live-provider smoke test uses tasks and seed namespaces excluded from every confirmatory manifest;
- no full 163-task production stream is generated;
- no complete confirmatory measurement matrix is executed;
- no confirmatory selection or candidate manifest is frozen; and
- no production provider spend occurs without a separate explicit smoke-test authorization and cost ceiling.

MEGB-06C/D owns preregistration and experiment authorization. MEGB-06E, MEGB-06F, and MEGB-06G are the sole owners of confirmatory stream generation, optimization-visible evaluation, and selection freeze respectively.

MEGB-05 handoff artifacts are schemas, implementations, CLIs, locks, test fixtures, and nonconfirmatory validation evidence—not experimental outcomes.

## Model Identity and Serving-Drift Contract

Confirmatory configurations must identify the strongest immutable provider snapshot available. Mutable aliases such as `latest` are prohibited.

For every request, the generation layer must record, where available:

- provider and endpoint;
- canonical model ID;
- immutable snapshot/revision ID;
- API version and region/routing class where scientifically relevant;
- provider-returned model ID and system fingerprint;
- request and response schema versions;
- inference/reasoning mode;
- sampling parameters;
- tool state;
- request timestamp; and
- token usage and cost metadata.

If immutable serving identity is unavailable, the configuration must state that uncertainty and define a frozen drift-detection and pause/abort policy. A fingerprint or returned-model mismatch never authorizes silent substitution, alias retargeting, or model replacement.

## Confirmatory Experimental Regime Implemented Here and Executed in MEGB-06

The confirmatory experiment uses **selection-only optimization pressure**. MEGB-05 implements and validates the following semantics; MEGB-06 alone executes them over the primary population.

Candidate generation is independent of the measurement system. The model receives no evaluator feedback and does not revise candidates interactively.

For every task and candidate-stream replicate:

1. generate one ordered stream of 32 candidate positions;
2. preserve raw and normalized artifacts;
3. evaluate every candidate against every frozen \(S_k\) and observation replicate;
4. apply each authorized selection policy independently at every nested budget; and
5. freeze all selections before any reference evaluation occurs.

The same candidate stream must be used across:

- all four robustness levels;
- all observation-set replicates;
- all optimization budgets; and
- all selection-policy conditions.

This creates a paired experiment: the candidate population is fixed while measurement robustness, selection policy, and eligible budget vary under explicit control.

## Scientific Rationale

The first experiment isolates selection pressure before introducing adaptive behavior.

An adaptive revision loop would additionally vary model context, feedback interpretation, conversation history, prompt length, revision strategy, stopping behavior, and candidate distributions. Adaptive optimization belongs to MEGB-08 and must not be pooled with the confirmatory selection-only results.

Selection-only optimization supports the claim:

> Holding the candidate distribution fixed, increasing measurement-directed selection pressure against an imperfect measurement system increases the probability of selecting a candidate that performs well under that measurement but poorly under the privileged reference evaluator.

## Approved Selection-Control Amendment

The original MEGB-05 specified only first-measured-pass selection. The refactored epic adds two controls needed to distinguish measurement-directed selection from the mere availability of a larger candidate pool.

The supported policies are:

1. **`FIRST_MEASURED_PASS` — experimental policy.** Select the lowest-index candidate in the eligible prefix with valid \(q_{\mathrm{meas}}=1\); fall back to candidate 1 if none passes.
2. **`RANDOM_FROM_PREFIX` — candidate-availability control.** Select uniformly from the eligible prefix using a frozen deterministic seed without consulting measurement outcomes.
3. **`FIRST_CANDIDATE` — no-selection control.** Select candidate 1 at every budget without consulting measurement outcomes.

The random-control key must exclude measurement-system identity and observation-replicate identity. For a fixed experiment, task, candidate stream, budget, random-control replicate, and selection version, it must choose the same candidate across all \(S_k\) conditions. This prevents the control from injecting measurement-system-specific random differences.

Only `FIRST_MEASURED_PASS` is expected to produce nondecreasing measured success and stable selection after the first passing candidate appears. Those monotonicity claims do not apply to `RANDOM_FROM_PREFIX`.

## Random-Control Replicate Contract

`RANDOM_FROM_PREFIX` may use one or more preregistered random-control replicates. The experiment configuration must freeze:

- the exact replicate count;
- stable replicate IDs;
- seed namespace;
- selection algorithm and version; and
- downstream aggregation and clustering treatment.

`random_control_replicate_id` is a scientific coordinate, not incidental metadata. It must appear in selection decisions, freeze manifests, expected-row calculations, downstream datasets, and audit records whenever the policy is `RANDOM_FROM_PREFIX`. For other policies it must be absent or an explicitly validated not-applicable value.

If exactly one random-control replicate is used, that decision must be explicit in the preregistration. Downstream tickets must not infer a default by silently dropping the dimension.

## Nested Optimization Budgets

Generate the maximum stream once. Define every smaller budget as a prefix:

| Budget \(N\) | Eligible candidates |
| ---: | --- |
| 1 | Candidate 1 |
| 2 | Candidates 1–2 |
| 4 | Candidates 1–4 |
| 8 | Candidates 1–8 |
| 16 | Candidates 1–16 |
| 32 | Candidates 1–32 |

For stream \((c_1,c_2,\ldots,c_{32})\):

\[
\mathcal{C}_N = \{c_1,\ldots,c_N\},
\]

and:

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

Candidates must not be regenerated independently for different budgets or selection policies.

## Epic Dependencies

- `[MEGB-01] Establish HumanEval Corpus and Privileged Evaluation Boundary`
- `[MEGB-02] Implement Isolated Candidate Execution Worker`
- `[MEGB-03] Implement Privileged Reference Evaluator S*`
- `[MEGB-04] Implement Optimization-Visible Measurement Systems S1 ... S4`
- MEGB-04's frozen system-family manifest, validation evidence, and accepted execution profile.

## Global Architectural Constraints

### Generation independence

Candidate generation may access only:

- public task ID and prompt;
- authorized system prompt;
- frozen generation configuration;
- frozen prompt renderer; and
- candidate-stream seed where supported.

It must not access:

- development or reference-only test inputs;
- expected outputs or canonical solutions;
- measurement-system implementation or manifests;
- measurement results or feedback;
- \(S^*\) implementation, evidence, or results;
- prior candidates from other experimental conditions; or
- repository contents beyond explicitly authorized prompt artifacts.

### Primary task-manifest boundary

Every primary-regime interface must require `task_manifest_id`, `task_manifest_checksum`, and expected task count. It must reject HumanEval/39, out-of-manifest tasks, the 164-task reference-validation manifest, and manifest/checksum mismatches before provider calls or measurement execution.

### Candidate-stream integrity

Every completed model response consumes exactly one immutable stream position. Duplicates, refusals, malformed output, and invalid code remain in place and count toward \(N\). Infrastructure failures follow the frozen retry policy and never become synthetic candidate positions.

### Shared-candidate design

For a fixed `(task_id, stream_id, candidate_index)`, every measurement and selection condition must reference the identical candidate artifact and hash. No condition may trigger regeneration or manual editing.

### Reference isolation

MEGB-05 ends at a frozen candidate manifest. Its package and runtime cannot import, read, query, or invoke \(S^*\), reference-only evidence, expected outputs, or prior reference results.

### Freeze before unblinding

Selections are immutable once frozen. They may not be regenerated, replaced, or modified after any reference evaluation begins.

### No confirmatory execution in MEGB-05

MEGB-05 validates execution semantics only on mock, synthetic, reduced, or explicitly excluded fixtures. A command configured with the confirmatory experiment ID, primary run namespace, production task manifest, or MEGB-06 freeze manifest must refuse to run until invoked through an authorized MEGB-06 state transition.

## Epic Execution Protocol

Work through MEGB-05A through MEGB-05G sequentially.

For each authorized subtask:

1. Read the epic objective, amendments, constraints, and current subtask.
2. Inspect artifacts from completed dependencies.
3. Present a short implementation plan before modifying code.
4. Implement only the current subtask.
5. Run its required tests and relevant regressions.
6. Update only the current status and completion record.
7. Produce the standard checkpoint report.
8. Stop and wait for explicit authorization.

Do not begin later subtasks early. If unavoidable overlap is discovered, identify it and obtain approval. Each subtask should correspond to a separate commit. Requirement changes require an explicit, versioned amendment.

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
9. **Repository state:** branch, exact commit SHA or uncommitted state, push state, and intentionally untracked or privileged artifacts.
10. **Protected-data statement:** whether any reference-only evidence, oracle output, canonical solution, secret, or provider credential was read, serialized, logged, or exposed outside its authorized boundary.
11. **External activity and cost:** provider calls, other external side effects, token usage, cost, authorization record, and cost ceiling; state explicitly when none occurred.
12. **Next-step readiness:** whether the next subtask's prerequisites are satisfied and the exact authorization required to continue.

After reporting, stop. Do not begin the next subtask.

## Subtask Status

- [ ] MEGB-05A — Implement provider-independent generation and frozen configuration
- [ ] MEGB-05B — Implement prompts, extraction, sanitization, and candidate artifacts
- [ ] MEGB-05C — Implement immutable candidate-stream orchestration with safe resumption
- [ ] MEGB-05D — Implement the complete measurement-matrix and cache machinery
- [ ] MEGB-05E — Implement nested budgets and experimental/control selectors
- [ ] MEGB-05F — Implement selection-freeze, operational CLIs, and audit
- [ ] MEGB-05G — Document, integrate CI, and complete acceptance

---

## MEGB-05A — Implement Provider-Independent Generation and Frozen Configuration

### Status

**Status:** Not started

### Objective

Implement a provider-independent candidate-generation boundary and immutable configuration without yet generating complete candidate streams.

### Dependencies

- MEGB-04 complete and accepted.
- The corrected MEGB-04 authoritative ticket, frozen primary `megb-observation-coverage-v1` system family using feedback profile `scalar-binary-v1`, and accepted MEGB-04 validation artifacts are available.

### Requirements

1. Define a provider-independent interface similar to:

   ```python
   def generate_candidate_stream(
       task: PublicTaskDefinition,
       config: GenerationConfig,
       stream_context: CandidateStreamContext,
   ) -> CandidateStreamManifest:
       ...
   ```

   This subtask may define the interface and single-generation primitive while deferring full stream orchestration to MEGB-05C.
2. Keep provider-specific behavior behind a versioned adapter.
3. Provide a deterministic mock/fake adapter for offline tests.
4. Define an immutable configuration containing at least:

   ```python
   @dataclass(frozen=True)
   class GenerationConfig:
       provider: str
       model_id: str
       model_snapshot_id: str | None
       provider_api_version: str
       reasoning_profile_id: str
       prompt_template_id: str
       system_prompt_id: str
       temperature: float
       top_p: float
       max_output_tokens: int
       stop_sequences: tuple[str, ...]
       requested_seed: int | None
       candidates_per_stream: int
       retry_policy_id: str
       model_identity_policy_id: str
       sanitizer_version: str
       tool_profile_id: str
   ```
5. Validate that `candidates_per_stream` is 32 for the primary regime while permitting explicitly versioned nonexperimental smoke configurations.
6. Define `CandidateStreamContext` with experiment/run identity, task ID, `primary_experiment_task_manifest` ID/checksum, stream ID, stream replicate/seed, configuration checksum, expected candidate count, and explicit `confirmatory_execution_authorized` state.
7. Reject HumanEval/39, out-of-primary-manifest tasks, the reference-validation manifest, and confirmatory execution outside an authorized MEGB-06 state transition.
8. Record complete provider request parameters and provider-returned model metadata for every request.
9. Enforce the Model Identity and Serving-Drift Contract before, during, and after every authorized live call.
10. Define a frozen retry policy distinguishing retryable provider infrastructure failures from completed model outputs.
11. Treat transport failures, authentication failures, rate limits, identity mismatches, uncertain call outcomes, and controller crashes under the frozen provider/error taxonomy.
12. If retries are exhausted, return an incomplete operation; never synthesize or silently substitute a candidate.
13. When seeded determinism is not guaranteed, treat preserved response artifacts—not future API replay—as the basis of reproducibility.
14. Require a new generation-configuration version for any outcome-affecting change.
15. Enforce the generation access boundary and implementation-only boundary defined in the epic constraints.

### Acceptance Criteria

- Provider adapters implement one common typed interface.
- Provider-specific request/response behavior does not leak into experiment orchestration.
- Configuration is immutable, serializable, checksummed, and versioned.
- Every request and response records exact available provider metadata.
- Primary task-manifest membership and model identity are verified before calls.
- Infrastructure failures follow the frozen retry taxonomy.
- Exhausted retries cannot create candidate positions.
- Generation code cannot access measurement or reference artifacts.
- Offline tests require no provider credentials.
- No confirmatory provider call can occur from MEGB-05 acceptance workflows.

### Required Tests

- Configuration validation and round-trip serialization.
- Version/checksum sensitivity.
- Mock provider success, refusal, malformed output, rate-limit, transport, authentication, and exhausted-retry cases.
- Provider metadata capture.
- Mutable alias rejection, model-identity mismatch, missing-fingerprint, and drift-policy tests.
- Primary-task-manifest, HumanEval/39, and unauthorized-confirmatory-run rejection tests.
- Seed-supported and seed-unsupported behavior.
- Forbidden generation-context and artifact-access tests.

### Non-Goals

- Prompt rendering and code extraction.
- Producing complete 32-position streams.
- Calling a real provider in ordinary unit tests.
- Making any confirmatory provider call or spending against a confirmatory budget.
- Candidate measurement or selection.

### Handoff Artifacts

- Provider-independent generation interface.
- Versioned provider adapters and offline mock.
- Frozen generation and retry configuration schemas.
- Generation access-boundary tests.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-05B requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-05B — Implement Prompts, Extraction, Sanitization, and Candidate Artifacts

### Status

**Status:** Not started

### Objective

Implement deterministic prompt construction and immutable transformation of raw provider responses into normalized candidate artifacts.

### Dependencies

- MEGB-05A complete and accepted.

### Requirements

1. Implement a versioned prompt renderer.
2. Render identical prompts across every measurement, robustness, replicate, budget, and selection-policy condition.
3. Record:
   - prompt-template version;
   - system-prompt version;
   - task ID;
   - primary-task-manifest ID and checksum;
   - exact rendered prompt hash;
   - token count where available; and
   - provider-specific message transformation.
4. Do not name the active measurement system, robustness level, evidence budget, selection policy, or observation replicate in the confirmatory prompt.
5. Implement deterministic response extraction and sanitization under frozen versions.
6. Preserve for every completed generation:
   - immutable raw provider response;
   - extracted source;
   - sanitized/normalized source;
   - extraction and sanitization diagnostics;
   - raw and normalized hashes;
   - request and response metadata;
   - stream ID and candidate index when assigned; and
   - generation timestamp.
7. Bind every artifact to the exact provider/model identity fields available under the Model Identity and Serving-Drift Contract.
8. Never manually edit generated source.
9. Classify the following as completed model outputs that consume positions:
   - empty responses;
   - refusals;
   - malformed Markdown;
   - unextractable code;
   - syntactically invalid Python;
   - missing entry point;
   - duplicate source; and
   - code that later fails in execution.
10. Keep model-output classification distinct from provider/controller infrastructure failure.
11. Define immutable artifact schemas and content-addressed storage.
12. Ensure stored raw responses can reconstruct every deterministic derived artifact.

### Acceptance Criteria

- Identical authorized inputs produce identical rendered prompts and hashes.
- Prompt contents are invariant across experimental conditions.
- Raw responses are immutable and checksummed.
- Extraction and sanitization are deterministic and versioned.
- Every malformed or invalid model output remains representable as a candidate artifact.
- Infrastructure failures cannot masquerade as candidate artifacts.
- Normalized candidates are derivable from preserved raw responses without manual edits.

### Required Tests

- Prompt snapshot/hash tests across all condition metadata.
- Provider-message transformation tests.
- Markdown fence, plain code, multiple block, empty, refusal, malformed, and unextractable response cases.
- Deterministic sanitizer tests.
- Syntax and entry-point diagnostic tests.
- Artifact immutability and checksum tests.
- Raw-to-derived reproducibility tests.

### Non-Goals

- Full stream orchestration.
- Duplicate relationship assignment across a stream.
- Candidate execution or scoring.

### Handoff Artifacts

- Versioned prompt renderer and templates.
- Extraction and sanitization implementations.
- Raw and normalized candidate artifact schemas/store.
- Prompt and artifact validation fixtures.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-05C requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-05C — Implement Immutable Candidate-Stream Orchestration With Safe Resumption

### Status

**Status:** Not started

### Objective

Implement and validate orchestration for ordered 32-position candidate streams, duplicate/invalid-output preservation, and interruption/resumption without generating the confirmatory MEGB-06 population.

### Dependencies

- MEGB-05B complete and accepted.

### Requirements

1. Implement orchestration capable of producing one ordered stream of exactly 32 candidate positions per task and stream replicate. Demonstrate it with deterministic mock providers and reduced nonconfirmatory fixtures only.
2. Candidate indices are one-based, stable, and immutable.
3. Assign one position for every completed provider response regardless of output quality.
4. Preserve duplicate candidates in place. Record `duplicate_of` relationships but do not remove, replace, or renumber them.
5. Evaluation may later reuse duplicate results by content hash, but reuse must not alter indices or effective budget.
6. Apply only the frozen provider retry policy to infrastructure failures.
7. If retries are exhausted before all 32 completed responses exist, mark the stream `INCOMPLETE`; do not generate an unplanned extra response or shift indices.
8. Write an immutable stream manifest containing at least:
   - schema version;
   - experiment/run mode and confirmatory-authorization state;
   - primary-task-manifest ID, expected count, and checksum;
   - task and stream IDs;
   - stream seed where applicable;
   - configured model snapshot identity, provider-returned identity/fingerprint, and drift status;
   - generation-configuration and prompt hashes;
   - expected and completed candidate counts;
   - stream status;
   - each candidate index, ID, candidate hash, raw-response hash, generation seed, status, and duplicate relationship;
   - artifact references; and
   - manifest checksum.
9. Stream resumption must:
   - preserve completed artifacts;
   - avoid duplicate provider requests for completed positions;
   - resume at the first unresolved position;
   - preserve original indices and seeds;
   - retain retry/audit history; and
   - never overwrite valid artifacts.
10. Preserve request counts, retry counts, token usage, provider cost where available, and wall-clock timing.
11. Support arbitrary stream-replicate counts configured later by MEGB-06 without changing the generation definition.
12. Reject HumanEval/39, out-of-manifest tasks, primary-manifest mismatches, mutable aliases, identity drift, and confirmatory run namespaces during MEGB-05 validation.
13. Any live smoke configuration must carry an explicit nonconfirmatory experiment ID, excluded task/seed manifest, authorization record, and cost ceiling.

### Acceptance Criteria

- A complete stream has exactly 32 immutable ordered positions.
- Duplicates and invalid model outputs remain and count toward every eligible prefix.
- Infrastructure failures do not consume positions unless a provider returned a completed response.
- Exhausted retries create an incomplete stream.
- Repeated validation reproduces the same stream and manifest identity from frozen artifacts.
- Interrupted streams resume without duplicate requests, reordering, or overwrite.
- Every candidate artifact and manifest checksum resolves correctly.
- Mock/reduced validation proves the 32-position contract without producing a confirmatory stream.
- Primary-task and model-identity boundaries fail closed.

### Required Tests

- Complete 32-position mock-provider stream.
- One-based index and prefix-stability tests.
- Duplicate preservation and `duplicate_of` tests.
- Invalid-output preservation tests.
- Infrastructure-failure/exhausted-retry incomplete-stream tests.
- Interruptions before request, after response preservation, and during manifest update.
- Resume idempotence and no-duplicate-request tests.
- Manifest tamper and artifact-hash mismatch tests.
- Arbitrary stream-replicate configuration tests.
- Confirmatory-namespace refusal and excluded-smoke-fixture tests.

### Non-Goals

- Measuring candidates.
- Choosing experimental stream-replicate count.
- Regenerating outputs to improve diversity.

### Handoff Artifacts

- Candidate-stream orchestration.
- Immutable stream manifests and artifact index.
- Resumption state machine.
- Nonconfirmatory generation audit and cost records.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-05D requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-05D — Implement the Complete Measurement-Matrix and Cache Machinery

### Status

**Status:** Not started

### Objective

Implement and validate evaluation-matrix and cache behavior against reduced nonconfirmatory fixtures while preserving the semantics required for later full MEGB-06 execution.

### Dependencies

- MEGB-05C complete and accepted.
- Frozen MEGB-04 system-family manifest available.

### Requirements

1. Implement construction of the matrix:

   \[
   \text{Task}
   \times
   \text{Candidate-stream replicate}
   \times
   \text{Candidate index}
   \times
   \text{Robustness level}
   \times
   \text{Observation replicate}.
   \]
2. Evaluate candidates only through the accepted MEGB-04 interface and execution profile.
3. Bind every matrix to `primary_experiment_task_manifest`, the accepted MEGB-04 `megb-observation-coverage-v1` system-family lock, and feedback profile `scalar-binary-v1`. Reject HumanEval/39, out-of-manifest tasks, adaptive-family identities, and mismatched manifest/family/profile checksums.
4. For fixed `(task_id, stream_id, candidate_index)`, pass identical source and hash to every system condition.
5. No measurement system may trigger candidate regeneration, prompt alteration, sanitization changes, or source edits.
6. Exploit MEGB-04 nested-result reuse so `S1–S4` outcomes are derived from accepted cached per-case results rather than redundant execution.
7. Implement an immutable content-addressed cache keyed by at least:
   - candidate hash;
   - primary-task-manifest checksum;
   - system/family version;
   - observation-manifest checksum;
   - partition checksum;
   - comparison profile;
   - execution profile;
   - protocol/evaluator version; and
   - relevant code/artifact versions.
8. Record cache hits and misses.
9. Do not reuse results across mismatched definitions or profiles.
10. Do not treat invalid or incomplete measurements as valid cache entries.
11. Parallel execution may change completion order but must not affect result identity, matrix ordering, selection, or artifacts.
12. Implement safe resumption that preserves valid completed cells and retries only according to the frozen invalid-measurement recovery policy.
13. Produce a completeness report before selection.
14. Validate full dimension arithmetic synthetically, but execute only reduced nonconfirmatory matrices in MEGB-05. A full 163-task experiment matrix requires MEGB-06F authorization.

### Acceptance Criteria

- Every required matrix cell for a complete configured nonconfirmatory validation run is present and valid before selection.
- Identical candidate source/hash is used across every paired system condition.
- Valid cached outcomes are reused only under complete key equivalence.
- Invalid/incomplete cells remain distinguishable and block affected selection.
- Sequential and parallel execution produce identical canonicalized matrix artifacts.
- Resumption does not recompute or overwrite valid results.
- Measurement execution counts and cache behavior are auditable.

### Required Tests

- Matrix-dimension and completeness tests.
- Shared-candidate identity tests.
- No-regeneration tests.
- Cache-key sensitivity and invalid-cache exclusion.
- Duplicate-candidate cache reuse without index collapse.
- Sequential/parallel equivalence.
- Interrupted-matrix resumption.
- Corrupt/mismatched MEGB-04 manifest refusal.
- Invalid-measurement propagation.
- Primary-manifest, HumanEval/39, system-family, scalar-binary-feedback-profile, and confirmatory-matrix refusal tests.

### Non-Goals

- Candidate selection.
- Reference evaluation.
- Statistical analysis.

### Handoff Artifacts

- Measurement-matrix implementation and complete reduced-fixture matrix.
- Immutable content-addressed measurement cache.
- Reduced-fixture completeness and execution-count report plus synthetic full-dimension arithmetic validation.
- Resumption and recovery artifacts.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-05E requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-05E — Implement Nested Budgets and Experimental/Control Selectors

### Status

**Status:** Not started

### Objective

Implement exact nested candidate prefixes and deterministic experimental/control selection policies using only their authorized inputs.

### Dependencies

- MEGB-05D complete and accepted.

### Requirements

1. Define budgets exactly as `1, 2, 4, 8, 16, 32`.
2. Bind every prefix and selection decision to the primary-task-manifest ID/checksum, task ID, stream identity, MEGB-04 system-family/profile identity, and run mode. Reject HumanEval/39, out-of-manifest tasks, and unauthorized confirmatory run state.
3. For every stream, construct strict ordered prefixes:

   ```text
   C1  = candidates[1:1]
   C2  = candidates[1:2]
   C4  = candidates[1:4]
   C8  = candidates[1:8]
   C16 = candidates[1:16]
   C32 = candidates[1:32]
   ```
4. Never regenerate candidates by budget or policy.
5. Implement `FIRST_MEASURED_PASS`:
   - consider only indices `<= N`;
   - require valid measurements needed by the rule;
   - choose the lowest-index candidate with `q_meas = 1`;
   - choose candidate 1 if none passes;
   - never consult reference outcomes, code length, model confidence, human judgment, later candidates after an earlier pass, or auxiliary metrics.
6. Formally:

   \[
   c^*_{k,N} =
   \begin{cases}
   c_j, & j=\min\{i\le N:q_{\mathrm{meas}}^{(k)}(c_i)=1\} \\
   c_1, & \text{if no such }j\text{ exists.}
   \end{cases}
   \]
7. Implement `FIRST_CANDIDATE`, selecting candidate 1 for every budget and condition without reading measurement outcomes.
8. Implement `RANDOM_FROM_PREFIX`, selecting uniformly from indices `1..N` using a documented cryptographic or reproducibly specified pseudorandom mapping.
9. The random selection key must include:
   - selection algorithm/version;
   - experiment or preregistration seed namespace;
   - task ID;
   - candidate-stream ID;
   - optimization budget; and
   - required `random_control_replicate_id` for the random policy.
10. The random key must exclude system ID, robustness level, observation replicate, candidate measurement, and all reference information so the same candidate is selected across measurement conditions.
11. Record a typed append-only decision containing:
    - schema and selection-policy versions;
   - task, stream, system condition, and budget;
   - primary-task-manifest ID and checksum;
    - eligible-prefix hash;
    - selected candidate index, ID, and hash;
    - selection policy and reason;
    - authorized task-level `q_meas` where the policy uses it;
   - random seed/key commitment where applicable;
   - `random_control_replicate_id` for random selections or validated not-applicable state otherwise;
    - measurement and selection configuration checksums;
    - `reference_evaluated = false`; and
    - timestamp.
12. Supported reasons include at least:

    ```text
    FIRST_MEASURED_PASS
    NO_MEASURED_PASS_DEFAULT_FIRST
    FIRST_CANDIDATE_CONTROL
    RANDOM_FROM_PREFIX_CONTROL
    INVALID_MEASUREMENT_ABORT
    INCOMPLETE_STREAM_ABORT
    ```
13. Invalid required measurements abort `FIRST_MEASURED_PASS`; incomplete streams cannot produce valid decisions for unsupported budgets.
14. For `FIRST_MEASURED_PASS`, verify measured success is nondecreasing with \(N\) and selection remains unchanged after the first passing candidate appears.
15. Do not apply that monotonic-selection invariant to the random control.
16. All policies must be deterministic from frozen candidate, measurement, policy, and seed artifacts.
17. Validate selectors over complete synthetic/reduced coordinate sets only. MEGB-06G is the sole owner of confirmatory selection execution and freeze.

### Acceptance Criteria

- Every budget is an exact prefix of one shared stream.
- `FIRST_MEASURED_PASS` chooses the exact earliest measured pass or candidate 1 fallback.
- `FIRST_CANDIDATE` always selects candidate 1.
- `RANDOM_FROM_PREFIX` is deterministic, approximately uniform under distribution tests, and invariant across measurement-system conditions.
- Random-control replicate identity is explicit, validated, and preserved as a downstream scientific coordinate.
- No policy accesses unauthorized reference information.
- Only the measurement-directed policy reads task-level `q_meas`.
- First-pass measured success is nondecreasing and selection stabilizes after first success.
- Invalid measurements and incomplete streams produce explicit abort reasons.
- Decision records resolve to immutable candidate and measurement artifacts.

### Required Tests

- Exact prefix tests for all budgets.
- First-pass streams where candidate 1, 2, 7, several candidates, or no candidates pass.
- Duplicate, syntactically invalid, and invalid-measurement cases.
- First-candidate invariance across all budgets/conditions.
- Random-control determinism, range, approximate-uniformity, and cross-system invariance.
- Random-key sensitivity to task, stream, budget, control replicate, and algorithm version.
- Random-key insensitivity to system and observation-replicate identity.
- Random-control replicate required/not-applicable, expected-coordinate, and downstream-schema tests.
- Primary-manifest and unauthorized-confirmatory-selection rejection tests.
- First-pass optimization monotonicity and selected-hash stability.
- Decision schema, hash, and reason validation.
- Reference-access prohibition tests.

### Non-Goals

- Freezing downstream candidate manifests.
- Evaluating selected candidates with \(S^*\).
- Adaptive feedback or candidate revision.
- Claiming random-control outcome monotonicity.

### Handoff Artifacts

- Nested-prefix constructor.
- Versioned selection-policy registry.
- Append-only selection-decision schema and reduced-fixture records.
- First-pass and control-policy validation report.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-05F requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-05F — Implement Selection Freeze, Operational CLIs, and Audit

### Status

**Status:** Not started

### Objective

Implement and validate immutable downstream candidate-manifest freezing, noninteractive generation/measurement/selection commands, and operational audit/cost recording without freezing confirmatory MEGB-06 candidates or crossing the reference boundary.

### Dependencies

- MEGB-05E complete and accepted.

### Requirements

1. Implement a frozen candidate-manifest schema and writer, and demonstrate one manifest for every valid selected condition in complete reduced nonconfirmatory fixtures. Each manifest contains:
   - experiment-run ID;
   - run mode and confirmatory-authorization state;
   - primary-task-manifest ID, expected count, and checksum;
   - task ID;
   - candidate-stream ID and checksum;
   - selection policy and version;
   - measurement-system identity/version where applicable;
   - observation replicate;
   - optimization budget;
   - selected candidate ID, index, and hash;
   - selection-record and configuration checksums;
   - random-control commitment and `random_control_replicate_id` where applicable;
   - code revision;
   - freeze timestamp; and
   - manifest checksum.
2. Every frozen manifest must state:

   ```json
   {
     "selection_complete": true,
     "reference_evaluation_started": false
   }
   ```
3. Frozen selections cannot be changed, regenerated, replaced, or overwritten.
4. Incomplete streams or invalid required measurements cannot produce valid freeze manifests.
5. MEGB-03 may later evaluate only candidates resolved through valid frozen manifests.
6. During MEGB-05, reject any attempt to freeze a manifest under a confirmatory MEGB-06 experiment ID or authorization state. MEGB-06G performs the real selection-freeze transition.
7. Provide noninteractive commands for:
   - generating candidate streams;
   - evaluating candidate streams against the frozen MEGB-04 family; and
   - applying policies and freezing selections.
8. Every command must:
   - validate input checksums and freeze states;
   - write append-only results;
   - support safe resumption;
   - avoid overwriting valid artifacts;
   - return nonzero for incomplete/invalid runs; and
   - record the exact reproducibility command.
9. Record:
   - provider requests and completed generations;
   - retries and incomplete streams;
   - input/output tokens and provider-reported cost where available;
   - generation and execution wall time;
   - candidate execution count;
   - cache hits/misses;
   - invalid measurements;
   - selection counts by policy/reason; and
   - artifact checksums.
10. Operational cost metadata must not affect selection.
11. Enforce the dependency direction:

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
12. The MEGB-05 package/runtime cannot import \(S^*\), read reference manifests/evidence/expected outputs/results, or invoke the reference command.

### Acceptance Criteria

- Every valid decision can produce one immutable, hash-resolving frozen candidate manifest.
- Acceptance evidence uses only reduced nonconfirmatory fixtures; no MEGB-06 candidate is frozen.
- Invalid/incomplete inputs cannot be frozen.
- Frozen selections cannot be overwritten or modified.
- CLIs validate, resume, audit, and fail explicitly as required.
- Interrupted generation, measurement, and selection preserve completed artifacts and final identities.
- Audit and cost records are complete but cannot influence selection.
- MEGB-05 stops before reference evaluation and cannot access \(S^*\).

### Required Tests

- Candidate and selection-record hash resolution.
- Missing/mismatched checksum refusal.
- Freeze-state transition and immutability tests.
- Incomplete-stream/invalid-measurement freeze refusal.
- End-to-end CLI smoke tests with mock provider and reduced task/system fixtures.
- Controlled interruption and resumption at all three stages.
- No duplicate requests, reordering, or valid-artifact overwrite on resume.
- Reference package/import/file/command isolation tests.
- Audit/cost completeness and selection-independence tests.
- Confirmatory experiment-ID/state refusal and primary-task-manifest boundary tests.

### Non-Goals

- Invoking MEGB-03.
- Calculating reference metrics or gaming gaps.
- Choosing confirmatory stream-replicate count.

### Handoff Artifacts

- Candidate freeze schemas/writers and reduced-fixture frozen manifests for all policies.
- Generation, measurement, and selection CLIs.
- Append-only audit and cost records.
- End-to-end reduced-fixture execution evidence.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. MEGB-05G requires explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## MEGB-05G — Document, Integrate CI, and Complete Acceptance

### Status

**Status:** Not started

### Objective

Document the selection-pressure measurement, integrate validation into CI, and demonstrate satisfaction of every MEGB-05 requirement before experimental use.

### Dependencies

- MEGB-05F complete and accepted.

### Requirements

1. Create:
   - `docs/experiments/selection-pressure.md`; and
   - `docs/experiments/candidate-generation.md`.
2. Document:
   - operational definition of optimization pressure;
   - why selection-only optimization is the confirmatory first regime;
   - shared candidate streams and nested prefixes;
   - frozen model, prompt, sampling, extraction, sanitizer, retry, and tool configurations;
   - invalid-output and duplicate policies;
   - `FIRST_MEASURED_PASS`, `RANDOM_FROM_PREFIX`, and `FIRST_CANDIDATE`;
   - why the control policies are necessary;
   - cross-system pairing of random control selections;
   - candidate freezing and one-time reference boundary;
   - resumption behavior;
   - remote-API reproducibility limits;
   - audit and cost accounting;
   - known limitations; and
   - threats to validity.
3. Document the MEGB-05/MEGB-06 ownership boundary: MEGB-05 implements and validates on nonconfirmatory fixtures; MEGB-06 alone executes the full primary population.
4. Integrate offline configuration, prompt, artifact, stream, prefix, selector, manifest, audit, and isolation tests into ordinary CI.
5. Add explicit integration coverage for MEGB-04 execution using mock/reduced fixtures. Do not add a MEGB-05 workflow that executes the full primary matrix; that belongs to an authorized MEGB-06 run.
6. CI must never require production provider credentials for ordinary pull-request validation.
7. Provider smoke tests, if enabled, must use explicit protected configuration, excluded task/seed manifests, and a cost ceiling, and may not expose secrets to candidate code or artifacts.
8. Produce a final acceptance matrix mapping every epic criterion to implementation, test, evidence, and limitation.

### Final Acceptance Criteria

- Mock/reduced integration evidence demonstrates immutable ordered 32-position streams per configured task and stream replicate.
- Every primary-regime interface binds `primary_experiment_task_manifest`, expected 163 tasks, and rejects HumanEval/39 and the 164-task validation manifest.
- The same candidate streams are used across every \(S_k\), observation replicate, budget, and selection policy.
- Budgets are exactly `1,2,4,8,16,32` and use nested prefixes.
- Model, prompt, sampling, extraction, sanitizer, retry, and tool configurations are frozen and versioned.
- Raw provider responses and normalized candidates are preserved and checksummed.
- Duplicates remain in the stream and count toward \(N\).
- Invalid model outputs remain in the stream and count toward \(N\).
- Infrastructure failures never silently become candidate positions.
- `FIRST_MEASURED_PASS` uses only optimization-visible measurements and chooses the lowest-index pass with candidate-1 fallback.
- `FIRST_CANDIDATE` and `RANDOM_FROM_PREFIX` do not consult measurements.
- Random control selections are deterministic and paired across measurement-system conditions.
- Random-control replicate identity is explicit in decisions, manifests, audits, and downstream handoff schemas.
- First-pass measured success is nondecreasing with budget, and selection remains fixed after the earliest passing candidate becomes eligible.
- No monotonicity claim is incorrectly imposed on random control selections.
- Every policy is reproducible from frozen candidate, measurement, configuration, and seed artifacts.
- Frozen candidate manifests exist before reference evaluation.
- MEGB-05 cannot access, import, read, or invoke \(S^*\).
- No candidate can be regenerated, edited, or replaced after reference outcomes are observed.
- Commands resume safely without reordering, duplicate requests, or valid-artifact overwrite.
- Generation, measurement, selection, audit, execution-count, and cost records are complete.
- The entire reduced-fixture pipeline is reproducible from recorded commands and checksums.
- No confirmatory provider calls, full primary matrix, or MEGB-06 selection freeze occurred during MEGB-05.

### Required Final Verification

- Full offline/unit suite.
- Provider-adapter contract tests with mock provider.
- Prompt invariance and artifact reproducibility tests.
- Complete stream, duplicate, invalid-output, and incomplete-stream tests.
- Exact budget-prefix tests.
- Shared-candidate matrix tests.
- Measurement-cache and resumption tests.
- Experimental/control selection-policy suite.
- Random-control pairing and distribution tests.
- First-pass monotonicity tests.
- Frozen-manifest and reference-isolation tests.
- CLI end-to-end reduced-fixture test.
- Primary-task-manifest, HumanEval/39, model-identity/drift, and unauthorized-confirmatory-state tests.
- Type checking and linting.
- CI execution evidence.

### Non-Goals

- Running the final factorial experiment.
- Calling production providers as part of ordinary acceptance.
- Invoking \(S^*\).
- Statistical analysis or publication figures.

### Handoff Artifacts

- Provider-independent generation interface.
- Frozen generation, prompt, selection, and stream configurations.
- Immutable raw and normalized candidate artifacts.
- Candidate-stream schemas/orchestration and reduced-fixture manifests.
- Measurement-matrix/cache implementation and reduced-fixture evidence.
- Versioned experimental/control selectors.
- Append-only selection records.
- Candidate-freeze schema/writer and reduced-fixture manifests ready for MEGB-06G.
- Operational CLIs, audit, and cost records.
- Unit, integration, resumption, and isolation tests.
- Candidate-generation and selection-pressure documentation.
- Final acceptance matrix.

### Checkpoint and Stop Condition

Produce the standard checkpoint report and stop. Do not begin MEGB-06 without explicit authorization.

### Completion Record

- Status: Not started
- Commit: —
- Completed: —
- Tests: —
- Deviations: —
- Handoff: —

---

## Epic Non-Goals

MEGB-05 does not:

- implement adaptive feedback-guided optimization;
- expose measurement feedback to the candidate-generating model;
- invoke \(S^*\);
- calculate \(Q_{\mathrm{ref}}\);
- calculate gaming deltas;
- run the final factorial experiment;
- generate the full 163-task confirmatory candidate population;
- execute the complete confirmatory measurement matrix;
- execute or freeze confirmatory selections;
- make production-provider calls except a separately authorized, excluded-fixture smoke test with a cost ceiling;
- perform statistical analysis;
- generate publication figures;
- choose the number of experimental stream replicates;
- compare model capabilities; or
- classify intentional versus accidental gaming.

## Threats to Validity That Must Be Documented

At minimum:

- best-of-\(N\) selection is not identical to gradient-based training;
- selection-only pressure does not demonstrate intentional exploitation;
- random-from-prefix is a control for measurement-directed selection, not a model of a realistic optimizer;
- remote model APIs may not reproduce identical outputs when called again;
- providers may update behavior behind stable identifiers;
- candidate streams may contain correlated samples;
- first-pass selection does not distinguish among multiple measured-pass candidates beyond stream order;
- malformed outputs and duplicates reduce effective diversity while still consuming budget;
- a maximum budget of 32 may not reach a gaming threshold for every task or system;
- candidate prompts may favor particular implementation styles;
- seeded random-control pairing introduces dependence across measurement conditions by design;
- provider retry behavior can affect stream completion and selection feasibility;
- public benchmark contamination may affect the candidate distribution; and
- results may not generalize beyond the frozen model and sampling configuration.

## Requirement Traceability

| Original MEGB-05 section | Refactored location |
| --- | --- |
| Objective | Epic Objective |
| Dependencies | Epic Dependencies |
| Approved experimental population | Approved Pre-Experimental Population Amendment; Global Constraints; MEGB-05A; MEGB-05C through MEGB-05G |
| MEGB-04 system-family and scalar-binary feedback boundary | Epic Dependencies; MEGB-05D; MEGB-05E |
| MEGB-05/MEGB-06 execution ownership | Implementation Versus Confirmatory Execution Boundary; Global Constraints; MEGB-05C through MEGB-05G |
| Model identity and serving drift | Model Identity and Serving-Drift Contract; MEGB-05A; MEGB-05C; MEGB-05G |
| Random-control replicate dimension | Random-Control Replicate Contract; MEGB-05E; MEGB-05F; MEGB-05G |
| Primary Experimental Regime | Confirmatory Experimental Regime Implemented Here and Executed in MEGB-06; Global Constraints |
| Scientific Rationale | Scientific Rationale |
| Nested Optimization Budgets | Nested Optimization Budgets; MEGB-05E |
| 1. Model-Generation Interface | MEGB-05A |
| 2. Frozen Generation Configuration | MEGB-05A |
| 3. Prompt Construction | MEGB-05B |
| 4. Candidate Artifact Preservation | MEGB-05B |
| 5. Invalid Model Outputs | Global Constraints; MEGB-05B; MEGB-05C |
| 6. Duplicate Handling | MEGB-05C; MEGB-05D |
| 7. Candidate Stream Manifest | MEGB-05C |
| 8. Measurement Evaluation Matrix | MEGB-05D |
| 9. Measurement Cache | MEGB-05D |
| 10. Deterministic Selection Rule | MEGB-05E |
| Added selection controls | Approved Selection-Control Amendment; MEGB-05E |
| 11. Selection Decision Schema | MEGB-05E |
| 12. Frozen Candidate Manifest | MEGB-05F |
| 13. Reference-Evaluator Isolation | Global Constraints; MEGB-05F; MEGB-05G |
| 14. Optimization-Pressure Monotonicity | MEGB-05E; limited explicitly to first-pass policy |
| 15. Configuration | MEGB-05A; MEGB-05E; MEGB-05G |
| 16. Command-Line Interface | MEGB-05F |
| 17. Audit and Cost Records | MEGB-05C; MEGB-05D; MEGB-05F |
| 18. Documentation | MEGB-05G |
| Candidate-Stream Tests | MEGB-05B; MEGB-05C |
| Budget-Prefix Tests | MEGB-05E |
| Shared-Candidate Tests | MEGB-05D |
| Selection-Rule Tests | MEGB-05E |
| Optimization Monotonicity Tests | MEGB-05E |
| Freeze-Manifest Tests | MEGB-05F |
| Reference-Isolation Tests | MEGB-05F; MEGB-05G |
| Resumption Tests | MEGB-05C; MEGB-05D; MEGB-05F |
| Reproducibility Tests | MEGB-05B through MEGB-05G |
| Acceptance Criteria | Distributed across subtasks; consolidated in MEGB-05G |
| Non-Goals | Epic and subtask Non-Goals |
| Threats to Validity | Epic threats; MEGB-05G documentation |
| Deliverables | Subtask Handoff Artifacts; MEGB-05G final handoff |

## Cross-Ticket Integration Notes

1. **MEGB-03:** MEGB-05 may use the public task definition and the identity/checksum of `primary_experiment_task_manifest`; it may not read privileged partition membership, reference-only inputs, oracle outputs, canonical solutions, or reference results. HumanEval/39 remains available only to MEGB-03's separate 164-task reference-validation path and is absent from every MEGB-05 experimental coordinate.
2. **MEGB-04:** MEGB-05 consumes only the corrected, frozen primary `megb-observation-coverage-v1` system family using feedback profile `scalar-binary-v1`, plus its public optimization-visible interface. Adaptive-system variants belong to MEGB-08 and must not enter this experiment's matrix, selector, or cache namespace.
3. **MEGB-06:** MEGB-05 hands off implementations, schemas, locks, CLIs, and reduced nonconfirmatory evidence. After preregistration and authorization, MEGB-06E generates the real streams, MEGB-06F executes the real optimization-visible matrix, and MEGB-06G applies and freezes the real selections.
4. **MEGB-07:** Final analysis must preserve candidate-stream replicate, observation replicate, random-control replicate, task, system, policy, and budget identities. MEGB-05 must not collapse those coordinates in its handoff schemas.
5. **MEGB-08:** Adaptive optimization is a separate follow-up system family and experiment. It must use separate family, cache, configuration, and run identifiers so that adaptive and selection-only results cannot be pooled accidentally.
6. **MEGB-09:** Any later robustness or reproducibility claims consume frozen MEGB-05/06 artifacts and must not regenerate candidates or reinterpret selection decisions.

## Instructions for Claude

When this ticket is first committed to the repository:

1. Treat this file as the sole governing MEGB-05 specification. Do not merge requirements from older MEGB-05 files or historical inline annotations.
2. Before MEGB-05A, inspect the accepted MEGB-03 and corrected MEGB-04 artifacts and report any schema or identifier mismatch. Do not repair another epic silently.
3. Work on exactly one authorized subtask at a time. Update only that subtask's status and completion record, produce the Standard Checkpoint Report, and stop.
4. Use mocks and reduced or explicitly excluded fixtures for MEGB-05 acceptance. Refuse a confirmatory experiment ID, namespace, task population, authorization state, or freeze transition.
5. Do not make a live provider call unless the user separately authorizes the precise smoke-test configuration and cost ceiling. Never interpret general authorization to implement MEGB-05 as authorization to incur provider cost.
6. Do not access or invoke `S*`, reference-only evidence, oracle records, canonical solutions, or prior reference outcomes. If an existing import or helper crosses that boundary, stop and report it.
7. Do not begin MEGB-06 or any later epic without explicit authorization.

## Epic Completion Rule

MEGB-05 is complete only when:

1. every subtask MEGB-05A through MEGB-05G is accepted;
2. every completion record identifies its commit and validation evidence;
3. the final acceptance matrix contains no unresolved `FAIL` or unapproved `DEFERRED` item;
4. experimental and control selection-policy definitions, including random-control replicate semantics, are frozen before confirmatory execution;
5. every primary-regime interface binds the 163-task primary manifest and rejects HumanEval/39 and the 164-task validation manifest;
6. frozen candidate manifests can be produced from reduced fixtures without any reference access;
7. no confirmatory provider stream, full primary matrix, confirmatory selection, or confirmatory candidate freeze occurred during MEGB-05; and
8. MEGB-05G produces its checkpoint report and stops before MEGB-06.
