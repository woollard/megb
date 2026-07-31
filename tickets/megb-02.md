# [MEGB-02] Implement Isolated Candidate Execution Worker

## Objective

Build the isolated execution substrate used to run untrusted, model-generated Python code without exposing the host repository, credentials, evaluator implementation, canonical solutions, or privileged test evidence.

This ticket implements execution infrastructure only. It does not determine whether a candidate solution is correct and does not calculate (Q_{\mathrm{ref}}), (Q_{\mathrm{meas}}), or any benchmark score.

## Motivation

HumanEval exists to execute model-generated code, and its official repository warns that candidate programs must not be run outside a robust security sandbox.

For MEGB, isolation also serves a measurement function: a candidate optimized against a weaker measurement system must not be able to inspect the privileged reference evaluator (S^*), its hidden tests, or its expected outputs.

The execution boundary must therefore separate:

* the trusted evaluation controller;
* the untrusted candidate program; and
* all privileged evaluation evidence.

## Dependency

Depends on:

* `[MEGB-01] Establish HumanEval Corpus and Privileged Evaluation Boundary`

## Threat Model

Treat every candidate solution as deliberately adversarial.

The execution worker must protect:

* the host operating system;
* the Git repository;
* environment variables and credentials;
* canonical HumanEval solutions;
* HumanEval+ tests;
* future private adversarial tests;
* other candidate executions; and
* the availability of the evaluation process.

Expected adversarial behaviors include:

* infinite loops;
* excessive memory allocation;
* process or thread spawning;
* filesystem inspection;
* filesystem modification;
* environment-variable inspection;
* network access;
* subprocess execution;
* oversized stdout or stderr output;
* interpreter termination;
* malformed protocol output; and
* attempts to infer or retrieve hidden test evidence.

This implementation is a research-grade isolation baseline, not a formally verified defense against container-runtime or kernel vulnerabilities. Document the residual threat explicitly.

## Architectural Boundary

Candidate code must execute in a fresh isolated container or equivalent OS-level sandbox.

The trusted evaluation controller remains outside the candidate environment.

```text
Trusted evaluator
    |
    | serialized function invocation
    v
Isolated candidate worker
    |
    | serialized result or failure
    v
Trusted evaluator
```

The candidate environment may receive:

* candidate source code;
* the target entry-point name;
* one invocation’s arguments and keyword arguments;
* explicit execution limits; and
* a protocol version.

The candidate environment must never receive:

* canonical solutions;
* hidden tests;
* expected outputs;
* the complete sequence of future test inputs;
* evaluator source code;
* repository contents;
* host environment variables; or
* host filesystem mounts.

## Requirements

### 1. Execution Interface

Implement a public interface similar to:

```python
def execute_candidate(
    request: CandidateExecutionRequest,
) -> CandidateExecutionResult:
    ...
```

Define typed, immutable request and result models.

The request must include:

```python
@dataclass(frozen=True)
class CandidateExecutionRequest:
    candidate_code: str
    entry_point: str
    args: tuple[Any, ...]
    kwargs: Mapping[str, Any]
    limits: ExecutionLimits
    protocol_version: str
```

The result must distinguish execution completion from semantic correctness.

```python
@dataclass(frozen=True)
class CandidateExecutionResult:
    status: ExecutionStatus
    return_value: Any | None
    exception_type: str | None
    exception_message: str | None
    wall_time_sec: float
    exit_code: int | None
    terminating_signal: int | None
    stdout: str
    stderr: str
    backend_id: str
    backend_version: str
```

Exact field organization may change if justified, but the interface must preserve equivalent diagnostic information.

### 2. Execution Status Taxonomy

Support at least the following statuses:

```python
class ExecutionStatus(str, Enum):
    COMPLETED = "COMPLETED"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    CANDIDATE_EXCEPTION = "CANDIDATE_EXCEPTION"
    TIMEOUT = "TIMEOUT"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    PROCESS_LIMIT = "PROCESS_LIMIT"
    OUTPUT_LIMIT = "OUTPUT_LIMIT"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
```

Do not include `WRONG_ANSWER` or `PASSED`.

Those are evaluator-level judgments and belong in later measurement-system tickets.

### 3. Safe Serialization Protocol

Implement a versioned, deterministic serialization protocol between the trusted controller and the isolated worker.

The protocol must:

* support the value types required by HumanEval and HumanEval+;
* preserve distinctions such as tuple versus list where relevant;
* reject unsupported types explicitly;
* impose maximum request and response sizes;
* validate all messages against a schema;
* return structured protocol errors; and
* never use `pickle`, `marshal`, `eval`, or another unsafe deserialization mechanism across the trust boundary.

A tagged JSON representation is acceptable.

Example:

```json
{
  "protocol_version": "1",
  "operation": "invoke",
  "entry_point": "has_close_elements",
  "args": [
    {
      "type": "list",
      "items": [
        {"type": "float", "value": 1.0},
        {"type": "float", "value": 2.0}
      ]
    },
    {"type": "float", "value": 0.5}
  ],
  "kwargs": {}
}
```

### 4. Containerized Execution Backend

Implement a container-backed execution backend.

Each execution must use a fresh candidate process. The first implementation may use one fresh container per invocation in favor of isolation and simplicity. Performance optimization can occur later only if it preserves experimental equivalence.

The container configuration must include:

* no network access;
* no host repository mount;
* no Docker socket mount;
* no host credential or configuration mount;
* read-only root filesystem;
* bounded writable temporary storage;
* execution as a non-root user;
* all Linux capabilities dropped;
* `no-new-privileges`;
* explicit memory limit;
* explicit CPU limit;
* explicit process-count limit;
* explicit file-descriptor limit;
* wall-clock timeout enforced by the trusted controller; and
* cleanup after success, failure, or controller interruption.

Use a minimal runner image with a base image pinned by digest. Record the runner-image digest in execution metadata.

Do not use host `subprocess` isolation alone as the production execution boundary.

### 5. Default Execution Limits

Define centralized, configurable defaults:

```python
@dataclass(frozen=True)
class ExecutionLimits:
    wall_time_sec: float = 2.0
    memory_mb: int = 256
    cpu_count: float = 1.0
    max_processes: int = 32
    max_open_files: int = 64
    max_stdout_bytes: int = 65_536
    max_stderr_bytes: int = 65_536
    max_request_bytes: int = 1_048_576
    max_response_bytes: int = 1_048_576
    temp_storage_mb: int = 16
```

These values are initial process-safety defaults, not claims about acceptable algorithmic complexity.

The limits must be configurable by later evaluators without modifying worker code.

### 6. Filesystem Isolation

The candidate must not be able to read:

* the repository working tree;
* dataset files;
* evaluator source code;
* hidden tests;
* canonical solutions;
* host home directories;
* SSH configuration;
* cloud credentials; or
* arbitrary host paths.

The candidate must not be able to modify the container’s root filesystem.

If writable temporary storage is provided, it must be:

* ephemeral;
* size-bounded;
* unique to the invocation; and
* destroyed after execution.

### 7. Environment Isolation

Do not inherit the host environment.

Construct an explicit allowlist containing only the minimal variables required to run the worker.

Tests must verify that a canary secret placed in the controller environment is unavailable to candidate code.

### 8. Network Isolation

Candidate code must not be able to establish inbound or outbound network connections.

Tests must cover at least:

* TCP connection attempts;
* DNS resolution attempts; and
* access to common cloud-instance metadata addresses.

Successful denial is the required behavior. Do not rely solely on candidate-visible exceptions as proof of isolation.

### 9. Output Control

Enforce stdout and stderr limits while the process is running.

Do not accumulate unlimited output in controller memory before applying the limit.

When a candidate exceeds an output limit:

* terminate the invocation;
* return `OUTPUT_LIMIT`;
* preserve a bounded prefix or tail for diagnosis; and
* record that truncation occurred.

### 10. Cleanup and Failure Containment

All containers, processes, temporary files, and invocation-specific resources must be cleaned up in a `finally`-equivalent path.

Cleanup must occur after:

* normal completion;
* syntax error;
* candidate exception;
* timeout;
* out-of-memory termination;
* protocol failure;
* controller cancellation; and
* unexpected infrastructure failure.

No failed invocation may affect the outcome of a later invocation.

### 11. Observability

Produce structured execution metadata sufficient to reproduce and diagnose each invocation.

Include:

* invocation ID;
* protocol version;
* backend identifier and version;
* runner-image digest;
* configured limits;
* start timestamp;
* wall-clock duration;
* exit code or signal;
* execution status;
* output-truncation indicators; and
* infrastructure-error details when applicable.

Do not log candidate source code, function arguments, return values, or secrets by default. These may be stored only through an explicit higher-level experiment logging policy.

### 12. Documentation

Create:

```text
docs/security/execution-threat-model.md
docs/security/execution-sandbox.md
```

The documentation must explain:

* protected assets;
* trust boundaries;
* enforced controls;
* known limitations;
* supported platforms;
* local setup;
* CI requirements;
* how runner images are pinned and updated; and
* why process resource limits do not establish algorithmic complexity.

## Required Tests

### Unit Tests

Test:

* request validation;
* result validation;
* serialization round trips;
* tuple/list distinction;
* unsupported-type rejection;
* malformed-message rejection;
* request-size enforcement;
* response-size enforcement; and
* status classification.

### Sandbox Integration Tests

Execute candidate programs that attempt to:

1. return a normal value;
2. raise a Python exception;
3. contain invalid syntax;
4. loop indefinitely;
5. allocate memory beyond the limit;
6. spawn processes until blocked;
7. write excessive stdout;
8. read a host-side canary file;
9. read a host environment-variable canary;
10. modify the root filesystem;
11. write within the bounded temporary directory;
12. connect to an external network address;
13. resolve a DNS hostname;
14. access a cloud metadata endpoint;
15. terminate the interpreter; and
16. emit malformed protocol output.

Tests must verify both the returned status and the absence of access to protected host data.

### Isolation Regression Test

Run two candidate invocations sequentially.

The first candidate must attempt to write a unique secret to every writable location available to it. The second candidate must be unable to recover that secret.

### Cleanup Test

After forced timeout and controller cancellation, verify that no invocation container or worker process remains active.

## Acceptance Criteria

* A valid candidate function executes and returns a correctly serialized value.
* Syntax errors and candidate exceptions return distinct structured statuses.
* Infinite loops terminate within the configured wall-clock tolerance and return `TIMEOUT`.
* Memory exhaustion returns `OUT_OF_MEMORY` or a documented platform-specific equivalent that remains distinguishable from ordinary candidate exceptions.
* Process spawning is bounded without destabilizing the host.
* Excessive output is terminated without unbounded controller memory growth.
* Candidate code cannot access the host repository, hidden evaluator assets, host environment canaries, or host filesystem canaries.
* Candidate code cannot access the network or cloud metadata endpoints.
* The root filesystem is read-only and temporary storage is bounded and ephemeral.
* Every execution occurs as a non-root user with capabilities dropped and privilege escalation disabled.
* No candidate invocation receives hidden tests, expected outputs, canonical solutions, or future test inputs.
* Sequential invocations do not share writable state.
* All invocation resources are cleaned up after every tested termination path.
* Unit and sandbox integration tests pass in the designated CI environment.
* The implementation does not assign correctness scores or contain HumanEval-specific evaluation logic.

## Non-Goals

This ticket does not:

* load or interpret HumanEval test assertions;
* implement HumanEval+ evaluation;
* decide whether returned values are correct;
* calculate (Q_{\mathrm{ref}}), (Q_{\mathrm{meas}}), or gaming deltas;
* detect algorithmic complexity classes;
* optimize container startup performance;
* provide a multi-tenant production sandbox;
* defend formally against container-runtime or kernel zero-day vulnerabilities; or
* implement any optimization loop.

## Deliverables

* typed execution request and result models;
* versioned safe serialization protocol;
* isolated candidate-worker image;
* trusted controller-side execution backend;
* centralized resource-limit configuration;
* unit tests;
* adversarial sandbox integration tests;
* isolation and cleanup regression tests;
* execution threat-model documentation; and
* sandbox setup and operations documentation.

