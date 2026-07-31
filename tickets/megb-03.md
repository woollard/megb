# [MEGB-03] Implement Privileged Reference Evaluator (S^*)

## Objective

Implement the privileged reference evaluator (S^*) used to estimate functional correctness for candidate solutions across all 164 HumanEval tasks.

The evaluator must combine:

* the benchmark corpus and privilege boundary defined in MEGB-01;
* the isolated candidate-execution worker implemented in MEGB-02; and
* the original HumanEval and expanded HumanEval+ test evidence.

The evaluator produces the reference measurement (Q_{\mathrm{ref}}). It must never be exposed to, queried by, or used as feedback within the candidate optimization loop.

## Measurement Claim

The evaluator does not observe “true correctness” directly and must not be described as un-gameable or infallible.

It is a privileged reference measurement system:

[
S^* = (C^*, O^*, M^*, P^*)
]

where:

* (C^*): functional correctness relative to each HumanEval task specification and documented input domain;
* (O^*): original HumanEval test inputs plus HumanEval+ test inputs and reference outcomes;
* (M^*): task-level pass only when every required output satisfies the version-pinned EvalPlus comparison rules; and
* (P^*): deterministic, isolated, non-adaptive execution using the MEGB-02 candidate worker.

The resulting score is:

[
Q_{\mathrm{ref}} =
\frac{1}{164}
\sum_{i=1}^{164} q_{\mathrm{ref},i}
]

with:

[
q_{\mathrm{ref},i} =
\begin{cases}
1, & \text{if the candidate passes every required test for task } i \
0, & \text{if the candidate produces a validly measured failure} \
\text{undefined}, & \text{if the measurement itself is invalid}
\end{cases}
]

## Dependencies

Depends on:

* `[MEGB-01] Establish HumanEval Corpus and Privileged Evaluation Boundary`
* `[MEGB-02] Implement Isolated Candidate Execution Worker`

## Architectural Constraints

### Privileged Evaluation Boundary

The reference evaluator runs only in the trusted evaluation environment.

Candidate code may receive:

* its own source code;
* the task entry point;
* one test invocation’s arguments;
* explicit execution limits; and
* the MEGB-02 protocol version.

Candidate code must never receive:

* canonical solutions;
* expected outputs;
* test-suite source code;
* the complete collection of reference test inputs;
* future test inputs;
* reference-evaluator source code;
* dataset files;
* aggregate or per-test reference feedback during optimization; or
* prior (S^*) results that could influence candidate generation.

Expected outputs and comparison logic remain on the trusted side of the execution boundary.

### No Adaptive Reference Evaluation

A candidate must be frozen before (S^*) is invoked.

Every reference evaluation must record:

* candidate artifact hash;
* originating optimization-run ID;
* optimization configuration hash;
* candidate-selection rule;
* timestamp at which the candidate was frozen;
* reference-evaluator version; and
* reference-evaluation timestamp.

The evaluator must not operate as an interactive oracle.

Reference results may not be returned to the optimizer for revision, selection, or additional generation within the same experimental run.

## Requirements

### 1. Reference Dataset Integration

Use the version-pinned HumanEval+ data established by MEGB-01.

For every task, load the privileged fields required by EvalPlus, including:

* `task_id`;
* `entry_point`;
* corrected `canonical_solution`;
* `base_input`;
* `plus_input`;
* task contract metadata where available;
* comparison tolerance such as `atol`; and
* dataset version and checksum.

HumanEval+ defines:

* `base_input` as inputs represented by the original HumanEval tests; and
* `plus_input` as the expanded inputs introduced by EvalPlus.

Do not dynamically generate generic inputs from function signatures in this ticket.

### 2. Reference Oracle Construction

Construct or load expected results on the trusted side using the version-pinned EvalPlus ground-truth procedure.

The oracle implementation must:

* use the corrected EvalPlus canonical solutions;
* follow EvalPlus’s task-specific comparison semantics;
* preserve configured floating-point tolerances;
* support task-specific output normalization where required;
* handle input mutation according to EvalPlus semantics;
* distinguish oracle-generation failure from candidate failure; and
* cache or materialize expected results as a versioned privileged artifact.

Do not replace EvalPlus comparison logic with a universal Python `==`.

If EvalPlus logic must be adapted to the MEGB execution protocol, validate behavioral equivalence against the pinned upstream implementation.

The expected-output artifact must include:

* dataset version;
* dataset checksum;
* oracle implementation version;
* generation timestamp;
* canonical-solution hash;
* number of base cases;
* number of plus cases; and
* artifact checksum.

### 3. Candidate Evaluation Interface

Implement an interface similar to:

```python
def evaluate_reference(
    task_id: str,
    candidate_code: str,
    context: ReferenceEvaluationContext,
) -> ReferenceTaskResult:
    ...
```

The context must identify:

```python
@dataclass(frozen=True)
class ReferenceEvaluationContext:
    experiment_run_id: str
    optimization_run_id: str
    candidate_id: str
    candidate_sha256: str
    evaluator_version: str
    dataset_version: str
    execution_profile_id: str
```

The evaluator must verify the candidate hash before execution.

### 4. Task-Level Result Schema

Return a typed result containing at least:

```python
@dataclass(frozen=True)
class ReferenceTaskResult:
    task_id: str
    candidate_id: str
    candidate_sha256: str

    measurement_status: MeasurementStatus
    q_ref_task: float | None

    passed_base: bool | None
    passed_plus: bool | None

    base_cases_total: int
    base_cases_passed: int
    plus_cases_total: int
    plus_cases_passed: int

    first_failure_category: str | None
    execution_failure_counts: Mapping[str, int]

    evaluator_version: str
    dataset_version: str
    dataset_checksum: str
    oracle_artifact_checksum: str
    execution_profile_id: str

    started_at: str
    duration_sec: float
```

A public or optimizer-visible result must not contain:

* failing test inputs;
* expected outputs;
* per-test failure details;
* canonical output values; or
* information that would enable targeted revision.

Detailed diagnostics must remain in a privileged artifact.

### 5. Measurement Status

Define a measurement-level status distinct from candidate correctness:

```python
class MeasurementStatus(str, Enum):
    VALID = "VALID"
    INVALID_ORACLE = "INVALID_ORACLE"
    INVALID_INFRASTRUCTURE = "INVALID_INFRASTRUCTURE"
    INVALID_PROTOCOL = "INVALID_PROTOCOL"
    INCOMPLETE = "INCOMPLETE"
```

Candidate failures such as these are valid measurements and produce:

```python
measurement_status = MeasurementStatus.VALID
q_ref_task = 0.0
```

Candidate failures include:

* wrong output;
* syntax error;
* candidate exception;
* timeout;
* memory exhaustion;
* process-limit exhaustion; and
* output-limit exhaustion.

Measurement-system failures must not be converted into candidate failures.

Measurement-system failures include:

* missing or corrupt oracle data;
* controller failure;
* sandbox backend failure;
* evaluator serialization defect;
* missing test evidence; and
* unclassified infrastructure error.

For a measurement-system failure:

```python
q_ref_task = None
```

### 6. Scoring Policy

For each task:

```python
q_ref_task = 1.0
```

only if all required base and plus test cases pass.

Otherwise:

```python
q_ref_task = 0.0
```

provided the measurement status is valid.

Case-level pass fractions are diagnostic only. They must not be substituted for the primary task-level binary score.

This prevents tasks with more test cases from receiving greater weight in the benchmark-level score.

### 7. Benchmark-Level Aggregation

Implement:

```python
def aggregate_reference_results(
    task_results: Sequence[ReferenceTaskResult],
) -> ReferenceBenchmarkResult:
    ...
```

The aggregate result must contain:

* number of expected tasks;
* number of evaluated tasks;
* number of valid task measurements;
* number of invalid or incomplete task measurements;
* number of tasks passing base tests;
* number of tasks passing all reference tests;
* HumanEval base score;
* (Q_{\mathrm{ref}});
* evaluator and dataset versions;
* candidate-set manifest hash; and
* aggregate measurement status.

Do not silently change the denominator when tasks are missing or invalid.

A final 164-task (Q_{\mathrm{ref}}) may be reported only when all required task measurements are valid.

Otherwise, the benchmark result must be marked `INCOMPLETE` or `INVALID`.

### 8. Base–Plus Discrepancy

Record whether each task falls into one of these diagnostic categories:

```python
class ReferenceOutcome(str, Enum):
    PASS_BASE_PASS_PLUS = "PASS_BASE_PASS_PLUS"
    PASS_BASE_FAIL_PLUS = "PASS_BASE_FAIL_PLUS"
    FAIL_BASE_FAIL_PLUS = "FAIL_BASE_FAIL_PLUS"
    FAIL_BASE_PASS_PLUS = "FAIL_BASE_PASS_PLUS"
    INVALID_MEASUREMENT = "INVALID_MEASUREMENT"
```

`PASS_BASE_FAIL_PLUS` is the primary observable signature of insufficient evidence in the original HumanEval measurement system.

Do not automatically label this outcome as intentional gaming. Intentional exploitation, test overfitting, accidental underspecification, and ordinary incorrectness require later analysis.

`FAIL_BASE_PASS_PLUS` should be treated as a diagnostic anomaly and investigated for:

* comparison mismatch;
* oracle inconsistency;
* nondeterminism;
* execution-order effects; or
* implementation defects.

### 9. Test Execution

For every reference case:

1. Keep the expected output in the trusted evaluator.
2. Send only the current input to the MEGB-02 candidate worker.
3. Receive the candidate output or structured execution failure.
4. Compare the result on the trusted side.
5. Record a privileged per-case diagnostic result.
6. Destroy all invocation-specific candidate state according to the selected execution profile.

The candidate must not receive the expected result before, during, or after invocation.

The evaluator must not execute candidate code directly in the trusted controller process.

### 10. Test Ordering and Candidate State

Use a deterministic test-order policy specified by the execution profile.

The high-assurance reference profile must prevent writable state from carrying across independent candidate executions.

If batching or persistent per-task workers are introduced for performance, they must be:

* explicitly versioned as a different measurement process (P);
* tested for order and state sensitivity;
* compared against the fresh-process implementation; and
* shown not to change task-level outcomes on the validation corpus.

Performance optimizations may not silently change the evaluator’s measurement process.

### 11. Full and Reduced Test Suites

The full pinned HumanEval+ suite is the authoritative implementation of (S^*).

A reduced HumanEval+ mini suite may be supported for:

* local development;
* pull-request smoke tests; and
* rapid infrastructure validation.

The reduced evaluator must have a distinct identifier, such as:

```text
human-eval-plus-mini-v1
```

It must never be reported as the full (S^*) result.

Full-suite reference evaluation must run in a designated integration or scheduled CI workflow.

### 12. Resource Calibration

Before freezing evaluator version 1:

1. Run all corrected canonical solutions through the complete reference process.
2. Measure runtime and resource use for every task and test case.
3. Identify failures caused by evaluator limits rather than candidate behavior.
4. Establish and document the execution-limit profile.
5. Freeze the profile before evaluating experimental candidates.

A universal timeout is an execution policy, not evidence of a particular algorithmic complexity class.

Do not tune resource limits after observing experimental candidate outcomes without:

* incrementing the evaluator version;
* documenting the change;
* rerunning all affected candidates; and
* treating the change as a new measurement process.

### 13. Determinism

Given identical:

* candidate source;
* candidate hash;
* task ID;
* dataset version;
* oracle version;
* execution profile;
* evaluator version; and
* random seed where applicable,

the evaluator must return the same task-level classification.

Run repeated-evaluation tests to detect:

* nondeterministic candidate behavior;
* environmental instability;
* order sensitivity; and
* evaluator instability.

If deterministic classification cannot be achieved for a task, mark and document the instability rather than silently selecting a favorable result.

### 14. Audit Trail

Every invocation of (S^*) must create an append-only audit record containing:

* caller;
* experiment-run ID;
* optimization-run ID;
* candidate ID and hash;
* evaluator version;
* dataset and oracle versions;
* execution profile;
* invocation timestamp;
* result-artifact location; and
* final measurement status.

The audit trail must make repeated or adaptive querying of (S^*) visible.

### 15. Command-Line Interface

Provide a noninteractive CLI similar to:

```bash
megb evaluate-reference \
  --run-manifest artifacts/runs/run-001/manifest.json \
  --candidate-manifest artifacts/runs/run-001/frozen-candidates.json \
  --evaluator-config configs/evaluators/reference-v1.yaml \
  --output artifacts/runs/run-001/reference/
```

The CLI must:

* verify manifest and candidate hashes;
* refuse unfinalized candidate manifests;
* display progress without revealing hidden test evidence;
* support resuming interrupted infrastructure failures;
* never rerun valid task measurements silently;
* write append-only JSONL task results;
* write a benchmark-level summary;
* return a nonzero exit code for invalid or incomplete evaluation; and
* record the exact reproducibility command.

### 16. Configuration

Create a versioned evaluator configuration similar to:

```yaml
evaluator_id: human-eval-plus-reference-v1
dataset: humaneval
dataset_version: pinned-version
dataset_checksum: pinned-checksum
oracle_version: oracle-v1
protocol_version: "1"
execution_profile: reference-high-assurance-v1
test_suite: full
require_base_tests: true
require_plus_tests: true
task_scoring: all_cases_pass
benchmark_aggregation: unweighted_task_mean
expected_task_count: 164
```

Configuration changes that can affect outcomes require a new evaluator version.

### 17. Documentation

Create:

```text
docs/measurement/reference-evaluator.md
docs/measurement/reference-evaluator-validity.md
```

The documentation must describe:

* (C^*), (O^*), (M^*), and (P^*);
* operational definition of (Q_{\mathrm{ref}});
* distinction between reference performance and true correctness;
* dataset and oracle provenance;
* comparison semantics;
* execution policy;
* scoring and aggregation;
* candidate-freezing procedure;
* access and feedback restrictions;
* reproducibility procedure;
* known limitations; and
* threats to validity.

## Required Tests

### Unit Tests

Test:

* task-result construction;
* benchmark aggregation;
* all-pass scoring;
* base-pass/plus-fail scoring;
* candidate execution-failure scoring;
* invalid-measurement propagation;
* denominator preservation;
* manifest validation;
* candidate-hash verification;
* configuration version validation;
* audit-record generation; and
* public-result redaction.

### Canonical-Solution Validation

Run the corrected EvalPlus canonical solution for every one of the 164 tasks.

Required result:

```text
164 / 164 valid measurements
164 / 164 q_ref_task = 1.0
Q_ref = 1.0
```

Any failure blocks release of the evaluator.

### Upstream Parity Validation

Evaluate a fixed validation corpus using:

1. the pinned upstream EvalPlus implementation; and
2. the MEGB privileged reference evaluator.

Task-level pass/fail classifications must match for every sample.

Any divergence must be resolved or documented as an intentional, versioned semantic difference before the evaluator can be used experimentally.

### Known-Incorrect Candidate Validation

Evaluate a curated corpus of known-incorrect solutions, including:

* candidates that fail original HumanEval tests;
* candidates that pass original tests but fail HumanEval+;
* hardcoded solutions;
* boundary-condition failures;
* type-handling failures;
* numerical-tolerance failures;
* mutation-sensitive failures; and
* resource-exhausting candidates.

The corpus must contain at least one validated `PASS_BASE_FAIL_PLUS` example and should cover as many tasks as practical.

### Isolation Validation

Use candidates that attempt to recover:

* expected outputs;
* future test inputs;
* canonical solutions;
* EvalPlus data files;
* evaluator configuration;
* prior candidate results; and
* host repository contents.

All attempts must fail without exposing privileged evidence.

### Determinism Validation

Evaluate the same fixed candidate corpus repeatedly under identical configuration.

Task-level classifications and aggregate scores must be identical.

Any stochastic or environmentally unstable behavior must produce an explicit invalid or instability result.

### Invalid-Measurement Validation

Inject:

* missing oracle records;
* corrupt oracle checksums;
* controller failures;
* sandbox-backend failures;
* malformed worker responses; and
* incomplete task results.

Verify that none are scored as candidate failures and that no final (Q_{\mathrm{ref}}) is emitted for an incomplete 164-task run.

### Feedback-Leakage Validation

Verify that optimizer-visible outputs contain only authorized information and never include:

* failing inputs;
* expected outputs;
* per-case pass/fail vectors;
* exception details containing test data; or
* reference-test counts not approved for release.

## Acceptance Criteria

* The evaluator covers exactly 164 version-pinned HumanEval tasks.
* All corrected canonical solutions receive valid task measurements and (q_{\mathrm{ref},i}=1.0).
* Aggregate canonical performance is (Q_{\mathrm{ref}}=1.0).
* MEGB task-level classifications match the pinned upstream EvalPlus implementation on the fixed parity corpus.
* A validated set of candidates passes the original HumanEval evidence but fails HumanEval+, producing `PASS_BASE_FAIL_PLUS`.
* Candidate code never executes in the trusted evaluator process.
* Hidden expected outputs and reference logic remain outside the candidate environment.
* Candidate artifacts are frozen and hash-verified before evaluation.
* Reference results cannot be used as feedback within the originating optimization run.
* Candidate failures produce valid zero scores.
* Measurement-system failures produce undefined scores and invalidate or leave the aggregate incomplete.
* Missing or invalid tasks never silently change the denominator.
* Full and mini evaluator variants have distinct identifiers and cannot be confused in output artifacts.
* Repeated evaluation is deterministic under a frozen configuration.
* Detailed reference evidence is excluded from optimizer-visible output.
* Every (S^*) invocation creates an append-only audit record.
* The complete evaluation can be reproduced from the recorded configuration, manifests, artifact hashes, and command.
* The evaluator documentation explicitly states that (Q_{\mathrm{ref}}) is a privileged measurement estimate, not direct access to latent true correctness.

## Non-Goals

This ticket does not:

* implement candidate generation;
* implement an optimization loop;
* expose reference results during optimization;
* calculate benchmark-gaming deltas;
* classify intentional versus accidental gaming;
* claim formal verification of candidate correctness;
* claim that HumanEval+ is un-gameable;
* eliminate model-training contamination;
* generate generic property tests from signatures;
* evaluate algorithmic efficiency as a separate construct; or
* introduce private adversarial tests beyond HumanEval+.

## Threats to Validity That Must Be Documented

At minimum:

* HumanEval+ remains a finite measurement system;
* HumanEval+ tests and tasks are publicly available;
* evaluated models may have encountered tasks or tests during training;
* canonical solutions and comparison rules may contain defects;
* the tested input domain may not cover all intended realizations;
* passing all tests does not prove functional correctness;
* execution limits may introduce construct-irrelevant failures;
* Python-version or platform differences may affect results;
* failures across tests and tasks are not statistically independent; and
* (Q_{\mathrm{ref}}) is a stronger proxy for the construct, not the construct itself.

## Deliverables

* privileged reference-evaluator implementation;
* trusted oracle and comparison layer;
* typed task-level and benchmark-level result models;
* versioned evaluator configuration;
* candidate-manifest freezing and hash verification;
* append-only reference-evaluation CLI;
* privileged detailed results and redacted public results;
* audit logging;
* unit tests;
* canonical-solution validation;
* upstream EvalPlus parity suite;
* known-incorrect candidate suite;
* isolation and feedback-leakage tests;
* determinism tests;
* invalid-measurement tests; and
* measurement-definition and validity documentation.

