# MEGB-03H.2C.3B.1 — Distributed-Execution Provenance Field-Ownership Matrix

**Status: implemented.** Restates all 16 concepts from the accepted
`megb-03h2c3a-gcp-provenance-audit.md` as concrete field ownership in the
new, standalone, provider-neutral types this checkpoint implements
(`src/distributed/`), per the authorization's step 2. No accepted schema
(`src/reference/calibration_schema.py`, `result_schema.py`, `cache_key.py`,
`reference_audit.py`) is modified — every "owning record" below is either
an existing, untouched schema or a new type in `src/distributed/`.

**Corrected after the MEGB-03H.2C.3B.1 conformance audit (correction
2).** A checksum over a *set* of distinct `WorkerExecutionContext`
values does not bind the actual topology of a distributed run: two
workers with identical configuration provenance previously collapsed
under the original "duplicate worker provenance" rejection rule, which
would have incorrectly blocked any homogeneous fleet. `WorkerExecutionContext`
now carries `worker_participant_id` (a safe, logical/pseudonymous
identifier, mirroring `logical_environment_id`'s own pattern) so that
distinct execution participants are never conflated merely because they
share configuration — duplication is now judged solely by
`worker_participant_id`. `MixedWorkerProvenanceSummary` is now a
deterministic multiset/histogram (`admitted_worker_count` plus
per-dimension `(value, count)` histograms for provisioning class,
region, zone, machine type, and worker-image digest), not a deduplicated
set of distinct values, so the *actual admitted* worker composition is
bound, not merely the *distinct configurations* observed. A new
`AggregateProductionIdentityProjection` (multiplicity-aware, over
however many workers contributed to one production result) supplements
the original per-worker `ProductionIdentityProjection`, since no
indivisible one-worker-per-production-work-item invariant is frozen or
enforced anywhere in the accepted or proposed design (see
`production_identity_projection_for`'s own docstring). "Peak
concurrency" is deliberately **not** bound by any identity type here — it
is an observed runtime measurement, not a provenance fact, mirroring
this project's own established identity-vs-telemetry split; a future
H.2C.3D/H.2C.3B.2 qualification-report design should record it as its
own measured metric.

## Legend

- **Run-level**: carried once per `DistributedRunContext`.
- **Worker-level**: carried once per `WorkerExecutionContext` (one run may
  have many worker contexts — region/zone/provisioning class/image may
  differ across them; see "mixed-worker" handling below).
- **Qual.** = enters the H.2C.3D `QualificationIdentity` checksum.
- **Prod.** = enters the future `ProductionIdentityProjection` (fields
  capable of changing candidate correctness, resource-limit behavior, or
  measurement validity, per this authorization's own identity-semantics
  rule).
- **Protected** = never appears in a safe committed report; lives only in
  `ProtectedOperationalMapping`, joined back via `logical_environment_id`.
- **Safe summary** = appears in `SafeRedactedSummary`.

## Matrix

| # | Concept | Owning record | Scope | Qual. | Prod. | Protected | Safe summary | Checksum vs. label | Affects |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Environment class + logical environment identity | `DistributedRunContext.environment_class` / `.logical_environment_id` | Run | Yes | Yes | raw project/account id only (via `ProtectedOperationalMapping`) | Yes | Content-bound (participates in `run_context_checksum`) | Equivalence/interpretation of every measurement in the run |
| 2 | Cloud provider | `DistributedRunContext.cloud_provider` | Run | Yes | Yes | No | Yes | Content-bound label (closed enum) | Resource + timing (telemetry quality/overhead, per H.2C.2B) |
| 3 | Region and zone | `WorkerExecutionContext.region` / `.zone` | Worker | Yes (region only) | No (timing-only, per the accepted audit's own scoping) | `zone` excluded from safe summary by design (§ below); nothing raw | `region` only, aggregate | Content-bound label | Timing only |
| 4 | Machine type and CPU architecture | `WorkerExecutionContext.machine_type` / `.cpu_architecture` | Worker | Yes | **Yes — reclassified, see Ambiguity 1** | No | Yes | Content-bound label | Resource-limit behavior (CPU/memory ceiling) + timing |
| 5 | Spot vs. On-Demand provisioning class | `WorkerExecutionContext.provisioning_class` | Worker (per-invocation) | Yes | Yes | No | Yes | Content-bound label (closed enum) | Resource + measurement validity (preemption/retry) |
| 6 | Worker VM/image content identity | `WorkerExecutionContext.worker_image_digest` (+ `worker_image_digest_scheme_version`) | Worker | Yes | Yes | No | Yes | Content digest + versioned scheme | Resource-limit + measurement validity |
| 7 | Worker implementation/version | `WorkerExecutionContext.worker_implementation_id` / `.worker_implementation_version` | Worker | Yes | Yes | No | Yes | Content-bound label | Measurement validity (terminal-state confirmation logic) |
| 8 | Coordinator implementation/version | `DistributedRunContext.coordinator_implementation_id` / `.coordinator_implementation_version` | Run | Yes | No (completeness/orchestration, not candidate outcome) | No | **No — see Ambiguity 2** | Content-bound label | Audit/recovery only (completeness/ordering trust) |
| 9 | Worker-fleet implementation/version | `DistributedRunContext.worker_fleet_implementation_id` / `.worker_fleet_implementation_version` | Run | Yes | No | No | **No — see Ambiguity 2** | Content-bound label | Audit/recovery only (Spot-recovery guarantees) |
| 10 | Queue implementation/version | `DistributedRunContext.queue_implementation_id` / `.queue_implementation_version` | Run | No (benign) | No | No | No | Content-bound label | Audit/recovery only |
| 11 | Object-store implementation/version | `DistributedRunContext.object_store_implementation_id` / `.object_store_implementation_version` | Run | No (benign) | No | No | No | Content-bound label | Audit/recovery only |
| 12 | Runner-image digest | *Unchanged*: `CandidateExecutionResult.runner_image_digest` (`src/execution/protocol.py`) | n/a | n/a | n/a | n/a | n/a | n/a | Already persisted/bound; no new field — this is the per-invocation candidate-container image, distinct from concept 6's worker VM/boot image |
| 13 | Network/isolation policy identity | `DistributedRunContext.network_isolation_policy_checksum` | Run | Yes | Yes | No | Yes | Checksum only (over the frozen, accepted isolation-flag set — flags themselves never restated per-record) | Correctness + resource (isolation strength) |
| 14 | Telemetry policy and host/runtime identity | *Unchanged*: `TelemetryCollectionPolicy` / `HostRuntimeContext` (`src/reference/calibration_schema.py`) + new `WorkerExecutionContext.host_runtime_identity_checksum` / `.telemetry_policy_identity_checksum` (opaque cross-references, provider-neutral, computed with the same canonical-JSON sha256 so they can be reconciled at integration time) | Worker | Yes | Yes | No | Yes (checksums only, not the underlying policy content) | Checksum reference | Measurement validity |
| 15 | Retry/lease policy identity | `DistributedRunContext.retry_lease_policy` (`RetryLeasePolicy`: lease duration, retry ceiling, dead-letter threshold, self-checksummed) | Run | Yes | No | No | **No — see Ambiguity 2** | Typed record + its own checksum | Audit/recovery only (completeness/duplication characteristics) |
| 16 | Checksum-algorithm version | `checksum_algorithm_version` field on every new self-checksummed type in `src/distributed/` | Global | Yes (unsupported value rejected explicitly) | n/a | No | Yes | Explicit version label, paired with every checksum it governs | Design discipline; automatically load-bearing once any checksum is compared |

Additional fields required by the authorization's own "Distributed run
context" / "Worker execution context" lists that are not separately
numbered concepts in the accepted audit:

- `DistributedRunContext.run_intent` (`SMOKE_TEST` / `QUALIFICATION_CANDIDATE`) — **new, see Ambiguity 3**. Qual: yes. Prod: no. Safe summary: yes.
- `DistributedRunContext.deployment_topology_policy_id` / `.deployment_topology_policy_version` — the "allowed deployment topology or other run-level constraints" the authorization names. Qual: yes. Prod: no. Safe summary: yes (labels only).
- `DistributedRunContext.distributed_run_id` — logical run identifier (mirrors `calibration_run_id`). Qual: yes. Prod: no (an identifier, not an outcome-affecting fact — excluded from `ProductionIdentityProjection` per the authorization's own "run IDs... must not create false cache misses" rule). Safe summary: yes (it is logical/opaque, not a raw resource name).
- `WorkerExecutionContext.parent_run_context_checksum` — binds each worker context to its owning run context by checksum (not by embedding the full context), per the authorization's own explicit field name. Used for reconciliation in `aggregate_worker_provenance`, not itself a separate "concept."

## Ambiguities resolved explicitly (per the authorization's step 2 instruction)

**Ambiguity 1 — machine type's production-identity membership.** The
accepted audit's own H.2C.3B.1 scope table tags machine type/CPU
architecture as timing-scoped only ("(1), (4)"), by analogy with
region/zone. This authorization's own identity-semantics rule (§4, item
2) defines production identity as covering fields "capable of changing
candidate correctness, resource-limit behavior, or measurement
validity." Machine type governs the effective CPU/memory ceiling a
candidate runs under — directly resource-limit behavior (a candidate
could time out or OOM on a smaller machine type and not on a larger
one) — which is a stricter, more recently-stated rule than the audit's
own timing-only scoping. **Resolved**: machine type is included in
`ProductionIdentityProjection`; CPU architecture is not (kept
timing-only, matching the existing `HostRuntimeContext.architecture`
precedent, since within this project's Python/Docker execution model
architecture differences are not expected to change correctness).
Region/zone remain timing-only and excluded from `ProductionIdentityProjection`,
matching the audit's explicit scoping. This is a field-categorization
decision inside this checkpoint's own new, additive types — it does not
modify any accepted schema.

**Ambiguity 2 — whether "(1), (3)"-tagged concepts (coordinator/fleet
version, retry/lease policy) belong in `SafeRedactedSummary`.** The
audit's per-concept table tags these three concepts "(1), (3)" —
qualification identity plus "protected, audit-only" — without the "(4)
safe redacted summary" tag machine type and region explicitly carry.
Read literally, category (3)'s own definition ("never in a safe
committed summary") appears to conflict with treating a plain version
string as sensitive. **Resolved literally, conservatively, in favor of
the audit's explicit tagging as written**: coordinator/worker-fleet
implementation version and the retry/lease policy's own fields are
excluded from `SafeRedactedSummary` (they still fully participate in
`run_context_checksum` and therefore in `QualificationIdentity`). This
is deliberately the more conservative reading — omitting a safe-looking
version label from a public report costs nothing, while including a
field the accepted audit explicitly withheld from safe summaries would
be a real over-disclosure risk if the audit's authors intended something
narrower than "just a version string" (e.g. a version string that could
fingerprint a specific unreleased fleet-controller build). Queue/
object-store implementation version (benign, not even qualification-
identity-bearing) are excluded from the safe summary for the same
reason, a fortiori.

**Ambiguity 3 — how the gate distinguishes a personal-bootstrap
smoke/connectivity check from an intentional H.2C.3D qualification
attempt**, both of which can originate from the same
`environment_class=PERSONAL_BOOTSTRAP` value (H.2C.3D's own qualifying
runs are explicitly personal-environment runs, per the accepted
amendment — `environment_class` alone cannot be the signal). **Resolved**
by adding a new, explicit `DistributedRunIntent` enum
(`SMOKE_TEST` / `QUALIFICATION_CANDIDATE`) to `DistributedRunContext`,
mirroring the already-established `H2C2BQualificationReport.qualifying`
boolean and the `-diagnostic-` run-identity-tagging precedent this same
audit's concept #1 rationale explicitly cites. The qualification gate
(`evaluate_qualification_gate`) rejects any run whose `run_intent !=
QUALIFICATION_CANDIDATE` as `BLOCKED`, structurally preventing a
smoke-test record from being mislabeled as qualifying evidence — the
same "typed guard, not a convention" discipline this project has used
throughout MEGB-03H.2C.

## Managed-model provenance

Not represented anywhere in `src/distributed/`. Per the accepted audit,
this concept is reserved for MEGB-03H.2C.3G, not designed here. No name,
field, or module in this checkpoint's new types could be mistaken for a
managed-model/candidate-generation-plane concept — confirmed by the
dependency-direction test (`tests/test_distributed_dependency_direction.py`)
and by direct review of every field listed above.
