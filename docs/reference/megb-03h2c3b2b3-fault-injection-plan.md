# MEGB-03H.2C.3B.2B.3 Fault-Injection, Recovery, and Resumption Conformance Plan

**Status: FROZEN before any implementation code for this checkpoint was
written or modified.** This plan enumerates, exhaustively, every fault
point and invariant this checkpoint's own conformance suite must exercise
and prove. Once frozen (this document's own git blob, as committed), no
fault point or invariant listed here may be weakened, narrowed, or deleted
to obtain a `IN_PROCESS_RECOVERY_READY_FOR_B2C` readiness classification --
only genuine defects discovered during implementation may be fixed, with
their own regression test added to this same matrix, never by editing this
plan after the fact.

This plan governs **MEGB-03H.2C.3B.2B.3** only -- in-process fault
injection, recovery, and resumption conformance for the already-accepted
MEGB-03H.2C.3B.2B.1 (atomic stores) and MEGB-03H.2C.3B.2B.2 (coordinator/
worker engine, including its correction) code. It does not authorize or
scope MEGB-03H.2C.3B.2C (offline end-to-end synthetic qualification) or
MEGB-03H.2C.3B.3 (calibration/qualification provenance integration), and it
makes **no durable-process, cross-host, or cloud-recovery claim of any
kind** -- every fault point below is proven entirely in-process, using
synthetic, deterministic, in-memory mechanisms.

## Fault-injection mechanism (mandatory constraints)

Every fault point below must be exercised using only:

- deterministic typed fault points (a scripted executor outcome, a direct
  authoritative-store call simulating a crash window, a typed exception);
- `threading.Barrier`/`threading.Event`/`threading.Lock` for genuine
  thread contention (never a race that merely *usually* resolves one way);
- the injected `LogicalClock` for any time-dependent behavior (lease
  duration, visibility timeout, expiry) -- never wall-clock time;
- synthetic exceptions raised by injected fakes (`RaisingExecutor`, a
  sink configured to fail, a store call invoked out of its normal
  sequence to simulate an interrupted process).

**Never** used: wall-clock `sleep`, process termination (`os.kill`,
`sys.exit`, `SIGKILL`/`SIGTERM`), signals, `subprocess`, Docker, or network
access of any kind.

**"Coordinator restart" is defined, precisely, as constructing a new
`Coordinator` instance around the *same* in-memory store/queue/outbox
objects a prior `Coordinator` instance used** -- proving that no
coordinator-local field (other than `_lease_expiry`, itself an explicitly
scoped, documented, non-authoritative optimization) is required for
correct recovery. This is **in-process component recreation**, not
process-crash durability, and every conformance-report entry that exercises
it is labeled as such.

## Fault matrix

### Admission boundaries (A1-A5)

| ID | Boundary | Description |
|----|----------|-------------|
| A1 | Before budget reservation | Crash/observation point before `AtomicBudgetStore.reserve` is ever called. |
| A2 | After reservation, before work creation | Reservation exists (`RESERVED`); no `AuthoritativeWorkRecord` yet. |
| A3 | After work creation, before audit intent | `AuthoritativeWorkRecord` exists, bound to the reservation; no admission audit-outbox entry yet. |
| A4 | After audit intent, before queue publication | Admission audit-outbox entry exists (`PENDING`, unconditional-existence reconciliation); `queue.publish` not yet called. |
| A5 | After publication, before admission returns | `queue.publish` succeeded; `admit()` has not yet returned to its caller. |

### Worker boundaries (W1-W9)

| ID | Boundary | Description |
|----|----------|-------------|
| W1 | After delivery, before lease | `queue.receive()` returned a message; no lease acquired yet. |
| W2 | After lease, before executor | Lease acquired and work transitioned to `EXECUTING`; injected executor not yet invoked. |
| W3 | Executor raises a retryable failure | `WorkExecutorProtocol.execute` returns a scripted retryable `ExecutorInvocationResult`. |
| W4 | Executor raises a non-retryable (terminal) failure | `WorkExecutorProtocol.execute` returns a scripted terminal `ExecutorInvocationResult`. |
| W5 | After result-artifact write, before outbox intent | `WorkerArtifactCapability.publish_result` succeeded; `InMemoryAuditOutbox.enqueue` for the result-committed event not yet called. |
| W6 | After outbox intent, before authoritative commit | Result-committed audit-outbox entry enqueued (`PENDING`, reconciliation-bound); `AtomicWorkStoreProtocol.commit_result` not yet called. |
| W7 | After commit, before budget finalization | `commit_result` succeeded (state `RESULT_COMMITTED`); `AtomicBudgetStore.finalize` not yet called. |
| W8 | After finalization, before queue acknowledgement | `finalize` succeeded (reservation `FINALIZED`); `queue.ack` not yet called. |
| W9 | After acknowledgement, before result return | `queue.ack` succeeded; `invoke_worker` has not yet constructed/returned its `WorkOutcome`. |

### Additional fault categories (C1-C13)

| ID | Category |
|----|----------|
| C1 | Audit-sink failure during dispatch |
| C2 | Audit outbox at capacity (full) |
| C3 | Orphan/losing intent becomes permanently impossible (`ABANDONED`) |
| C4 | Queue duplicate delivery / redelivery |
| C5 | Queue acknowledgement failure (simulated: ack deliberately skipped, proving redelivery recovers) |
| C6 | Lease expiry and reassignment |
| C7 | Stale and future fencing generations |
| C8 | Cancellation at each phase (before admission, before lease, after lease/before commit, after commit) |
| C9 | Retry success (retryable failure then success) and retry exhaustion |
| C10 | Conflicting result and conflicting actual-cost replay |
| C11 | Coordinator recreation around the same in-memory stores |
| C12 | Reservation-without-work-creation crash window (admission A1/A2 companion, store-level) |
| C13 | Budget exhaustion and orphan-reservation recovery |

### Concurrency/race validation (R1-R10)

| ID | Scenario |
|----|----------|
| R1 | Concurrency = 1 under the generic synthetic (non-personal) policy |
| R2 | Concurrency = 2 under the generic synthetic policy |
| R3 | Concurrency = 4 under the generic synthetic policy |
| R4 | Personal-bootstrap policy rejects concurrency above 2 (construction-time, before any admission) |
| R5 | Deliberately reversed completion order still yields deterministic, input-ordinal-sorted results |
| R6 | Duplicate deliveries racing (before lease and after commit) |
| R7 | Cancellation racing commit |
| R8 | Lease expiry racing commit |
| R9 | Outbox dispatch racing authoritative reconciliation (dispatch reads mid-transition state safely) |
| R10 | Concurrent budget reservations at the exact ceiling (no oversubscription) |

## Invariants (I1-I13) -- frozen before any test result is observed

| ID | Invariant |
|----|-----------|
| I1 | At most one authoritative committed result exists per scientific-work item. |
| I2 | No execution (injected executor invocation) occurs after a committed result already exists for that work item. |
| I3 | No stale lease (a superseded/forged/wrong-generation lease) can commit a result. |
| I4 | No acknowledgement occurs before a durable, checksum-verified result commit. |
| I5 | No double budget finalization occurs for the same reservation. |
| I6 | No silent budget leak -- every reservation ends `FINALIZED` or `RELEASED`, never permanently `RESERVED` with no path to resolution. |
| I7 | No queue-visible work is ever lost -- every published message is eventually delivered, and every admitted-but-unpublished record is diagnosable and resumable. |
| I8 | No authoritative state transition occurs without a corresponding audit intent already enqueued (or a typed, recoverable reconciliation state accounting for its absence). |
| I9 | No outbox intent whose reconciliation clause has become permanently impossible continues to consume outbox pending-capacity indefinitely. |
| I10 | No terminal evidence (a committed result, a terminal disposition) is ever erased by a retry, a cancellation, or a redelivery. |
| I11 | Every admitted work item's lifecycle ends in exactly one of: terminal (committed+acknowledged, cancelled, dead-lettered), retryable (scheduled for reassignment), resumable (a diagnosable, safely-retriable crash-window state), or explicitly blocked (policy/budget refusal) -- never an undefined or silently-dropped state. |
| I12 | Returned/observed result ordering is deterministic (ordered by `input_ordinal`) regardless of completion order or thread interleaving. |
| I13 | No raw exception text, candidate/result content, or protected/infrastructure identifier ever appears in a safe audit event, outcome, or the conformance report itself. |

## Acceptance discipline

- Every (fault point, invariant) pair actually exercised by this
  checkpoint's test suite is recorded as one `ConformanceEntry` in the
  safe, committed conformance report (see
  `src/distributed/fault_conformance.py`).
- A fault point is not required to be crossed against every invariant --
  only the invariants it can plausibly threaten need be recorded against
  it (e.g. W3/W4 threaten I2/I10/I11/I13; W7 threatens I5/I6; C3 threatens
  I9; R10 threatens I6). The full mapping actually exercised is recorded
  in the generated report, not predetermined here, since which invariants
  a given fault point threatens is itself part of what the conformance
  suite demonstrates.
- `IN_PROCESS_RECOVERY_READY_FOR_B2C` may be reported only if every
  recorded entry passed. Otherwise the report must read
  `BLOCKED_IN_PROCESS_RECOVERY`, and the underlying defect must be fixed
  narrowly (with its own regression test added to this same matrix, not a
  weakening of this plan) before readiness can be reconsidered.
- This plan's own frozen content is referenced by the conformance report
  via `plan_checksum` -- the sha256 of this file's contents as committed
  in the fault-plan commit, computed and recorded when the report is
  generated (this document does not, and cannot, self-checksum its own
  bytes).
