# MEGB-03H.2C.3B.2C — Offline End-to-End Synthetic Distributed Qualification Plan

Frozen before any implementation code for this checkpoint was written or
modified. This plan is committed standalone, and its own git blob
SHA-1/sha256 are referenced (not embedded) by the later-generated safe
qualification report, exactly mirroring the established
`megb-03h2c3b2b3-fault-injection-plan.md` pattern.

## Scope and explicit non-claims

This checkpoint qualifies **only the offline, provider-neutral,
in-process coordinator/worker path** already accepted in
MEGB-03H.2C.3B.1 (provenance types), B.2A (orchestration contracts),
B.2B.1 (atomic stores), B.2B.2 (coordinator/worker engine), and B.2B.3
(in-process fault-injection/recovery conformance). It uses the same
in-memory stores, the same `LogicalClock`, and the same synthetic,
harmless workload discipline as B.2B.3.

Readiness this checkpoint may report is exactly one of:

- `OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3`
- `BLOCKED_OFFLINE_DISTRIBUTED_PATH`

This checkpoint explicitly **does not** and **may not** claim: H.2C.3D
readiness; GCP readiness; durable-process recovery; cross-host recovery;
Docker/native-Linux equivalence; calibration-provenance completeness; or
real scientific-result validity. MEGB-03H.2C.3B.3 remains mandatory
before H.2C.3D, unaffected by this checkpoint. No GCP/`gcloud`/cloud
resource/Docker/privileged artifact/HumanEval evidence/real
candidate/model API call is used anywhere in this checkpoint.

## Synthetic workload (frozen)

### Deterministic transform

```
synthetic_transform(candidate_content: bytes) -> bytes:
    return hashlib.sha256(candidate_content).digest()[:16]
```

A fixed, harmless, deterministic byte transform — never source-code
execution, never a real scientific computation. Every "successful"
executor invocation in this checkpoint computes exactly this function
over the candidate content it resolved from the artifact store and
returns it as `result_content`; the committed `result_content_checksum`
is `hashlib.sha256(synthetic_transform(candidate_content)).hexdigest()`
in every case, which is what makes the serial/distributed equivalence
comparison meaningful (both paths, given the same candidate content,
must produce byte-identical output).

### Path-coverage workload (8 items) — exercises the full 17-step path

All content is `f"e2e-synthetic-candidate-{n:02d}".encode()`,
`workload_class=WorkloadClass.SYNTHETIC_QUALIFICATION_CANDIDATE`,
`data_classification=DataClassification.SYNTHETIC`. Each item requests
`100` cents at admission. Total requested exposure: 800 cents ($8.00).

| id | required behavior | worker(s) | expected outcome(s) | retries |
|---|---|---|---|---|
| `e2e-01` | successful outcome | `worker-a` | `EXECUTED_AND_COMMITTED` | 0 |
| `e2e-02` | successful outcome, second worker context | `worker-b` | `EXECUTED_AND_COMMITTED` | 0 |
| `e2e-03` | retryable failure then success | `worker-a` | `RETRY_SCHEDULED` then `EXECUTED_AND_COMMITTED` | 1 |
| `e2e-04` | non-retryable failure | `worker-a` | `RETRY_EXHAUSTED`, `TerminalDispositionReason.NON_RETRYABLE_EXECUTOR_FAILURE` | 0 |
| `e2e-05` | duplicate delivery / stale lease | `worker-a` (stale), `worker-b` (real) | `STALE_LEASE` then `EXECUTED_AND_COMMITTED` | 0 |
| `e2e-06` | committed-result recovery + one impossible outbox intent abandoned | `worker-a` (crash window), `worker-a` (recovery) | `RECOVERED_COMMITTED_RESULT`; one synthetic orphan outbox intent reconciles `ABANDONED` | 0 |
| `e2e-07` | cancellation before admission | none (never leased) | `CANCELLED_NOT_STARTED` | 0 |
| `e2e-08` | reversed completion order under real concurrency | `worker-a` (slower), `worker-b` (faster) | both `EXECUTED_AND_COMMITTED`; result ordering by `input_ordinal` regardless of completion order | 0 |

`e2e-01`/`e2e-02`/`e2e-08` (three items, `input_ordinal` 0/1/2 in
admission order) are admitted together and run under
`coordinator.run()` at concurrency 2, with `e2e-08`'s worker
deliberately delayed past a `threading.Barrier` release relative to
`e2e-01`'s so it completes *after* `e2e-01` despite being admitted
*before* it in ordinal terms is not required — the frozen requirement
is only that whichever of the two racing items finishes first, the
returned `CoordinatorRunSummary.outcomes` is sorted by `input_ordinal`,
not completion order. `e2e-03` through `e2e-07` are exercised via direct
sequential `admit()`/`invoke_worker()` calls (concurrency is irrelevant
to what they individually prove), mirroring B.2B.3's own established
per-fault-point test shape.

### Equivalence workload (4 items) — exercises noninterference only

Distinct, uniformly-successful content, no injected faults:
`f"e2e-eq-synthetic-{n:02d}".encode()` for n in 1..4, each requesting
100 cents. Run four times, each under a distinct `scientific_work_id`
suffix so runs never collide in a shared store:

1. **Serial baseline** — no coordinator, no queue, no budget: for each
   item, directly compute `synthetic_transform(content)` and its sha256
   hexdigest. Not a claim about the engine; a reference computation
   only.
2. **Distributed, concurrency 1** — `coordinator.run()`, one worker,
   personal environment.
3. **Distributed, concurrency 2** — `coordinator.run()`, two workers,
   personal environment. Same shared personal budget store as the
   path-coverage workload and run (2) above (see "Cost accounting"
   below).
4. **Distributed, generic concurrency 4** — `coordinator.run()`, four
   workers, `EnvironmentClass.COMPANY_PLAYGROUND`, its own separate
   environment/budget store. Labeled explicitly **non-personal** in
   every artifact this run produces; does not imply company
   authorization; not counted against the $50 personal ceiling.

Required exact agreement across (1)/(2)/(3): scientific work identity
(`scientific_work_id`), typed terminal outcome (`outcome_kind`),
result-content checksum, retry count (frozen at 0 for every equivalence
item), input ordering, and aggregate outcome-kind counts. Required
agreement between (4) and (2)/(3): aggregate outcome-kind counts and
per-item result-content checksums only (peak concurrency is expected to
differ and is not part of the equivalence claim). Any mismatch anywhere
in this section blocks readiness. Wall-clock duration is never used as
evidence for anything in this checkpoint.

### Cost accounting (integer cents, frozen)

Primary personal-environment qualification run (shared
`PersonalEnvironmentPolicy`, `EnvironmentClass.PERSONAL_BOOTSTRAP`,
`max_admitted_workers=2`, `spending_ceiling_cents=5000`): path-coverage
workload (≤800 cents requested; `e2e-04`/`e2e-07` never finalize, so
actual finalized total is ≤600 cents) + equivalence concurrency-1 run
(400 cents) + equivalence concurrency-2 run (400 cents, distinct
`scientific_work_id`s from run (2)) = **at most 1,600 cents ($16.00)
requested, well under the frozen $50.00 ceiling** with no worker count
ever exceeding 2. The generic concurrency-4 comparison uses a separate,
non-personal `AtomicBudgetStore`/policy instance entirely and is
excluded from this ceiling by design.

## Candidate-manifest construction and generation-plane capability

A new `GenerationPlaneArtifactCapability` (`src/distributed/artifact_capabilities.py`,
additive) is the **only** object this checkpoint's synthetic publisher
uses to create candidate artifacts:

- Composes only `ArtifactWriterProtocol` (bare `put`) — no reference to
  `AtomicWorkStoreProtocol`, `BudgetReservationProtocol`,
  `WorkerRegistryProtocol`, `AuditSinkProtocol`, or any reader of
  `RESULT_ARTIFACT`-kind content. It structurally cannot resolve a
  result artifact, read a work record, or observe budget/audit state,
  because it never holds a reference to any of those objects, not
  merely by convention.
- Its one method, `publish_candidate`, structurally rejects any
  `artifact_kind != ArtifactKind.CANDIDATE_MANIFEST_ENTRY` before
  touching the backing writer (the exact mirror image of
  `WorkerArtifactCapability.publish_result`'s existing
  `RESULT_ARTIFACT`-only check).

A new frozen `CandidateManifest` (`src/distributed/candidate_manifest.py`)
records every published entry as an immutable, checksummed whole:
`distributed_orchestration_schema_version`, `checksum_algorithm_version`,
`manifest_entries: tuple[ArtifactReference, ...]` (sorted by
`artifact_reference_id`), `manifest_checksum` (self-computed over the
sorted entries' own `reference_checksum`s). `build_candidate_manifest`
publishes every item through a `GenerationPlaneArtifactCapability` and
returns the resulting `CandidateManifest`. The execution plane (the
coordinator and every worker invocation) receives only
`WorkDescriptor.candidate_artifact_reference` values drawn from this
manifest — an opaque reference plus checksums, never raw candidate
bytes and never the manifest object itself.

## Provenance requirements

A single `DistributedRunContext` (`run_intent=DistributedRunIntent.QUALIFICATION_CANDIDATE`,
`environment_class=EnvironmentClass.PERSONAL_BOOTSTRAP`) plus two
`WorkerExecutionContext`s (`worker-a`, `worker-b`, both bound to that
run context's checksum) are run through
`evaluate_qualification_gate` and must yield `ProvenanceGateReadiness.READY`
with both `qualification_identity` and `worker_summary` populated. Three
negative constructions are frozen and must each yield `BLOCKED`: (a) a
run context with `run_intent=SMOKE_TEST` → `NOT_QUALIFICATION_INTENT`;
(b) a worker context with a deliberately mismatched
`parent_run_context_checksum` → `MIXED_CONTEXT_WORKERS`; (c) two worker
contexts sharing one `worker_participant_id` → `DUPLICATE_WORKER_PROVENANCE`.
None of these three negative constructions is ever admitted through the
coordinator — they exercise the gate function directly, in isolation,
exactly as B.2B.1's own qualification-gate tests already do for other
provenance shapes.

## Peak concurrency measurement

A `PeakConcurrencyTrackingExecutor` wraps the real transform/scripted
executor for every `coordinator.run()` invocation: a `threading.Lock`
plus an active-invocation counter incremented at the start of
`execute()` and decremented at the end, retaining the observed maximum.
This is a genuine measurement of realized concurrent executor
invocations (which may be less than the configured worker count if
threads happen to serialize), never an assumed or asserted value, and
never a wall-clock timing. Recorded separately for the personal
concurrency-2 run (`measured_peak_concurrency_personal`) and the generic
concurrency-4 run (`measured_peak_concurrency_generic`) — never
conflated into one field, so the generic figure can never be
misread as a personal-environment result.

## Acceptance criteria (frozen; identical in substance to the authorization)

At minimum, this checkpoint's own test suite must prove, before any
result is observed:

1. the qualification gate accepts the complete-provenance construction
   and rejects each of the three incomplete/mixed-provenance
   constructions above;
2. `GenerationPlaneArtifactCapability` and `WorkerArtifactCapability`
   remain structurally disjoint — the former can never publish a
   `RESULT_ARTIFACT`, the latter can never publish a
   `CANDIDATE_MANIFEST_ENTRY`, and neither exposes the other's
   forbidden operation under any argument;
2a. the generation-plane capability holds no reference to any
   result/reference/work/budget/audit store — checked structurally
   (its `__init__` accepts only a writer; `dir()`/`vars()` carries no
   other collaborator attribute) as well as behaviorally (any attempt
   to call a read method raises `AttributeError`, since no such method
   exists);
3. queue-visible `QueueWorkMessage` records for every path-coverage and
   equivalence item contain only the already-established allowlisted
   field set (`queue_work_message_field_names()`), confirmed by exact
   field-set equality, not merely "no forbidden substring";
4. every admitted work item ends in exactly one authoritative result or
   one typed terminal outcome — never both, never neither;
5. `e2e-05`'s duplicate/stale delivery never re-executes the real,
   already-leased attempt, and `e2e-06`'s redelivery after a
   committed-but-not-yet-finalized crash window recovers via
   `RECOVERED_COMMITTED_RESULT` without a second executor invocation;
6. no stale-lease commit succeeds (the fenced generation on `e2e-05`'s
   stale attempt is rejected, mirroring B.2B.3's own C6/C7 proofs, now
   exercised end-to-end through `admit()`/`invoke_worker()` rather than
   direct store manipulation);
7. `e2e-03`'s retry preserves `scientific_work_id` across both attempts
   while its `lease_generation`/attempt identity changes;
8. `e2e-08`'s two-item concurrent run returns results ordered by
   `input_ordinal` regardless of which worker's executor completed
   first;
9. concurrency 1 and concurrency 2 produce exactly equivalent scientific
   outcomes for the equivalence workload (see above); the generic
   concurrency-4 comparison produces equivalent aggregate outcomes
   without ever being labeled personal or company-authorized;
10. budget reservation and finalization reconcile exactly: every
    finalized reservation's `actual_cost_cents` equals its requested
    cost (100 cents), every cancelled/never-admitted item's reservation
    is released or never created, and the sum of
    finalized+released+still-reserved equals the sum requested, with
    zero silently unaccounted cents;
11. the audit outbox has no `still_pending_keys` and no unresolved
    deliverable event once `dispatch_audit()` is called a final time;
    `e2e-06`'s deliberately impossible orphan intent is abandoned and
    stops consuming pending capacity;
12. the queue has no unacknowledged completed work once every item
    reaches a terminal state;
13. worker/topology multiplicity in the safe report (the
    `MixedWorkerProvenanceSummary` histograms) matches the actual
    `worker-a`/`worker-b` (or `worker-a..worker-d` for the generic run)
    topology used, exactly;
14. actual peak concurrency for the personal concurrency-2 run and the
    generic concurrency-4 run is measured (never assumed) and both
    values appear in the report, separately labeled;
15. the safe report contains no candidate bytes, prompts, source,
    participant IDs, raw exceptions, infrastructure identifiers, paths,
    credentials, or free-form diagnostics — checked by an AST-based
    field-name/identifier scan mirroring
    `tests/test_fault_conformance_boundaries.py`'s established pattern.

Criteria are frozen at this point and may not be weakened, narrowed, or
deleted after observing test results. If a defect is found in accepted
B.2B.1/B.2B.2/B.2B.3 code while proving any of the above, it is fixed
narrowly with a regression test and reported — never worked around by
softening a criterion here.

## Report fields (frozen)

A new, safe, self-checksummed, versioned report,
`OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION =
"megb-03h2c3b2c-offline-e2e-qualification-v1"`
(`src/distributed/offline_e2e_qualification_report.py`), containing
exactly:

- `schema_version`
- `plan_sha256`, `plan_git_blob_sha1` (this document, referenced by
  checksum after this standalone commit, never embedded)
- `workload_sha256` (sha256 over a canonical repr of the frozen
  workload definition above: item ids, content seeds, requested costs,
  expected outcome kinds, transform name)
- `distributed_provenance_schema_version`,
  `distributed_orchestration_schema_version` (referenced, not
  reproduced)
- `fault_conformance_report_checksum` (the already-accepted B.2B.3
  report's own `3a0d6e71cf7162144f193b534b64eef6f604a5e3cd2276f70ef954e60b148b56`,
  referenced by value, confirmed live via
  `fault_conformance_cli.verify()` in this checkpoint's own preflight)
- `run_context_checksum`, `qualification_identity_checksum` (from the
  accepted-provenance construction only)
- `worker_topology_provisioning_class_counts`,
  `worker_topology_region_counts`, `worker_topology_machine_type_counts`
  (each a sorted tuple of `(label, count)` pairs, reusing
  `MixedWorkerProvenanceSummary`'s own safe histogram shape — never a
  raw `worker_participant_id`)
- `admitted_count`, `completed_count`, `failed_count`, `retried_count`,
  `cancelled_count` (path-coverage workload)
- `duplicate_delivery_count`, `redelivery_count`
- `budget_requested_cents_total`, `budget_finalized_cents_total`,
  `budget_released_cents_total`
- `measured_peak_concurrency_personal`, `measured_peak_concurrency_generic`
- `audit_delivered_count`, `audit_abandoned_count`, `audit_still_pending_count`
- `queue_unacknowledged_count`
- `serial_vs_distributed_equivalent: bool`
- `generic_concurrency4_equivalent: bool`
- `readiness` (always derived: `OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3`
  iff every count/bool above is within its required value —
  `audit_still_pending_count == 0`, `queue_unacknowledged_count == 0`,
  both equivalence booleans `True`, `failed_count` limited to the one
  frozen `e2e-04` non-retryable failure — else
  `BLOCKED_OFFLINE_DISTRIBUTED_PATH`; never independently settable)
- `report_checksum` (self-computed, auto-stamped, tamper-checked on
  load — mirroring `fault_conformance.py`'s established pattern exactly)

No candidate bytes, prompts, source, participant IDs, raw exceptions,
infrastructure identifiers, paths, credentials, or free-form diagnostic
field is ever present. `render_markdown` renders the same safe fields
only. `build`/`verify` offline CLI commands
(`python -m src.distributed.offline_e2e_qualification_report_cli
build|verify`) reproduce the committed report deterministically from a
clean checkout, exactly mirroring
`src/distributed/fault_conformance_cli.py`'s established shape.

## Mechanism constraints (mandatory, matching B.2B.3)

No wall-clock sleep; no process termination; no signal; no subprocess;
no Docker; no network access; no GCP/`gcloud`; no real candidate
content, HumanEval evidence, or model API call. All concurrency uses
real Python threads bounded by `coordinator.run()`'s own
`threading.Semaphore`, synchronized where needed with
`threading.Barrier`, and measured with the `LogicalClock` — never
wall-clock time as scientific evidence.
