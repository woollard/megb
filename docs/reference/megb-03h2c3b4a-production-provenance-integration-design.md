# MEGB-03H.2C.3B.4A — Production Distributed-Provenance Integration Design and Persistence Audit

**Status: frozen design and read-only audit only. No production schema
modified, no version bumped, no `src/`/`tests/` file touched, no real
privileged artifact opened.** This document is B.4A's own deliverable —
the design B.4B must implement, not implementation itself.

## 0. Scope and what this closes

`docs/reference/megb-03h2c3a-gcp-provenance-audit.md`'s "Revised blocking
precondition" and the accepted `MEGB-03H.2C.3E — COMPLETE:
BLOCKED_PRODUCTION_PROVENANCE_SCHEMA` acceptance record both name the same
gap: distributed-execution provenance is integrated into the
**calibration** schema (`src/distributed/provenance.py`,
`calibration_provenance_report.py`, `provenance_manifest.py` — all
accepted, MEGB-03H.2C.3B.1/B.3) but **not** into the **production**
identities — `ReferenceRunContext` (`src/reference/result_schema.py`),
`ReferenceResultCacheKey` (`src/reference/cache_key.py`), and
`ReferenceAuditRecord` (`src/reference/reference_audit.py`). This document
designs that integration.

**Major finding that reshapes this design**: `src/distributed/identity.py`
(built during the MEGB-03H.2C.3B.1 conformance-audit correction) already
defines `ProductionIdentityProjection` and
`AggregateProductionIdentityProjection` — exactly the outcome-affecting
subset of provenance a production integration needs, already resolved
against the field-ownership matrix, already self-checksummed. B.4A's job
is therefore **not** to invent a new identity concept, but to decide how
the existing `src/distributed/` types bind into the existing `src/reference/`
production schemas — a wiring design, not a from-scratch identity design.

## 1. Run-level identity

**Question**: which safe checksum binds `ReferenceRunContext` to the
distributed run and protected provenance manifest?

**Design**: `ReferenceRunContext` gains two new fields, mirroring exactly
the pattern `MEGB-03H.2C.3B.3` already established on the calibration side
(`CalibrationRunContext.distributed_run_context_checksum`/
`provenance_manifest_checksum`, `CALIBRATION_SCHEMA_VERSION` v2→v3):

- `distributed_run_context_checksum: str | None` — `DistributedRunContext.run_context_checksum`.
- `distributed_provenance_manifest_checksum: str | None` — `DistributedProvenanceManifest.manifest_checksum`.

Both participate in `ReferenceRunContext`'s existing dataclass equality
(automatic — no change to any equality logic required), so
`aggregate_reference_results`'s existing shared-run-context check
(`src/reference/aggregation.py::_require_shared_run_context`) already
catches an inconsistency in either field with no code change of its own.

Why both, not just the manifest checksum (which structurally contains the
run context): the narrower `distributed_run_context_checksum` lets a
verifier confirm run-level identity without resolving the full protected
manifest, exactly the same justification B.3 already gave for carrying
both on the calibration side. `str | None` (not required) — see §8,
Unresolved Decision 1.

## 2. Worker-level identity

**Question**: how does each freshly executed `ReferenceTaskResult` prove
which admitted worker executed it?

**Design**: `ReferenceTaskResult` gains:

- `contributing_worker_context_checksums: tuple[str, ...]` — sorted,
  deduplicated `WorkerExecutionContext.worker_context_checksum` values for
  every worker that contributed to *this task's* execution. Empty tuple
  only when `distributed_run_context_checksum` is `None` (legacy/local —
  see §8).

This is a **proof**, not a bare claim: each checksum is only meaningful if
it independently resolves against the run's `DistributedProvenanceManifest`
via the already-accepted `resolve_worker_context(manifest, checksum)`
(`src/distributed/provenance_manifest.py`), which raises
`InvalidDistributedProvenanceError` for any checksum not present in that
specific manifest — "a checksum without a persisted, verifiable referenced
manifest is insufficient," the same discipline that function's own
docstring already states. A verifier holding the protected manifest can
resolve every checksum to a real `WorkerExecutionContext`; a verifier
without manifest access still gets tamper-evidence (the checksums are
sha256 hex, opaque, and meaningless to fabricate without matching a real
context), never a raw identifier.

**Why not `ProductionIdentityProjection` (the single-worker type)
directly**: that type's own docstring is explicit that it is "valid only
when the calling production integration can guarantee a given production
result was produced entirely by this single worker context" and that "no
such indivisible-work-unit invariant is currently frozen or enforced
anywhere... a real production integration must use
`aggregate_production_identity_for` instead." No B.2B interface freezes
one-worker-per-task execution (confirmed by re-reading
`src/distributed/executor.py`/`coordinator.py` — retries can reassign a
work item to a different worker). B.4A therefore designs against
`AggregateProductionIdentityProjection` uniformly (§3), never the
single-worker projection, even for the common case where exactly one
worker in fact executed a given task — this is conservative, not wasteful:
`aggregate_production_identity_for` with a length-1 `workers` tuple
degrades to exactly the single-worker case with `contributing_worker_count
== 1`.

## 3. Production identity

**Already resolved by the existing `src/distributed/identity.py`.**
`ReferenceTaskResult` gains:

- `production_identity_checksum: str | None` —
  `AggregateProductionIdentityProjection.projection_checksum`, computed
  from the `WorkerExecutionContext` objects `contributing_worker_context_checksums`
  (§2) resolve to, via `aggregate_production_identity_for(run_context, workers)`.

This directly reuses the already-accepted field set (`environment_class`,
`logical_environment_id`, `cloud_provider`, `network_isolation_policy_checksum`,
`contributing_worker_count`, and per-field histograms of `machine_type`,
`provisioning_class`, `worker_image_digest`, `worker_implementation_version`,
`host_runtime_identity_checksum`, `telemetry_policy_identity_checksum`) —
**no new field-ownership decision is made here**; B.4A only decides where
this existing checksum is *embedded*. `region`/`zone`/`cpu_architecture`
are excluded from this checksum because `ProductionIdentityProjection`/
`AggregateProductionIdentityProjection` already exclude them (B.1's own
"timing-only" determination) — see §8, Unresolved Decision 2 for the one
place this exclusion has a real consequence for cache reuse.

## 4. Cache identity

**Question**: which production-provenance checksum enters
`ReferenceResultCacheKey`?

**Design**: `ReferenceResultCacheKey` gains exactly one new field:

- `production_identity_checksum: str | None` — the identical value from
  §3, copied from `task_result.production_identity_checksum` by
  `cache_key_for`.

**Nothing else** from the distributed side enters the cache key —
`distributed_run_context_checksum`, `distributed_provenance_manifest_checksum`,
`contributing_worker_context_checksums`, `distributed_run_id`,
`worker_participant_id`, any attempt/delivery/lease id, and any timestamp
are all deliberately excluded, per the explicit instruction and per this
key's own existing "run IDs, portfolio-selection IDs... belong in
audit/mapping records instead" precedent
(`src/reference/cache_key.py`'s own module docstring). This single field
addition is sufficient to satisfy every required cache-identity property:

- **Cross-worker, same-run reuse**: `AggregateProductionIdentityProjection`
  excludes `worker_participant_id` from its own checksum payload — two
  different but identically-configured workers in the same run yield the
  same `production_identity_checksum`.
- **Cross-run reuse**: the projection excludes `distributed_run_id` and
  any manifest checksum — two different runs with equivalent
  outcome-affecting environments yield the same `production_identity_checksum`,
  hence the same cache key.
- **Invalidation on real change**: `machine_type`, `provisioning_class`,
  `worker_image_digest`, `worker_implementation_version`,
  `host_runtime_identity_checksum`, and `telemetry_policy_identity_checksum`
  all participate in the projection's own checksum — any one changing
  changes `production_identity_checksum`, hence the cache key.
- **Region/zone/provisioning-class per the B.1 determination, not
  redesigned here**: region and zone are excluded from the projection
  (B.1's timing-only classification, unchanged by this design);
  provisioning class (Spot vs. On-Demand) **is** included, so a
  Spot→On-Demand change for otherwise-identical configuration **does**
  invalidate the cache key.

## 5. Audit identity

**Question**: which run, manifest, worker, and production-identity
checksums enter `ReferenceAuditRecord`?

**Design**: `ReferenceAuditRecord` gains, mirroring §1 and §3 exactly (safe
identity/checksum fields only, consistent with this record's existing
"structurally cannot carry X" discipline):

- `distributed_run_context_checksum: str | None`
- `distributed_provenance_manifest_checksum: str | None`
- `production_identity_checksum: str | None`

**Deliberately excluded from the audit record**:
`contributing_worker_context_checksums`. Unlike the run-level and
aggregate-production checksums (each a single coarse value, identical
across many tasks or many runs), the per-task worker-checksum *list*
reveals per-task worker-multiplicity/retry patterns at fine granularity —
the same category of concern that already led
`src.distributed.safe_summary.SafeRedactedSummary` to exclude per-worker
`zone` from its own safe projection ("avoids per-record
infrastructure-topology fingerprinting"). This detail remains available
only on the always-privileged `ReferenceTaskResult` itself (§2), never on
the audit record — see §7 for the full redaction rationale, and §8,
Unresolved Decision 3, since this specific granularity call is a B.4A
recommendation, not something the authorizing instruction resolved
explicitly.

This lets an audit record be reconciled against the cache/result identity
it accompanies, and — for an operator holding the protected manifest —
against the full evidence chain, without ever inspecting the privileged
cache entry itself, exactly the rationale the v2 audit-record correction
already gives for `execution_protocol_version`/`dataset_checksum`/
`task_manifest_checksum`.

## 6. Aggregation

**Question**: how can a 164-task aggregate contain results from multiple
admitted workers without violating the shared-run-context invariant?

**Design**: no change to `ReferenceBenchmarkResult`'s or
`aggregate_reference_results`'s existing invariant is needed, because the
new fields split cleanly along the boundary those functions already
enforce:

- **Run-level** (§1: `distributed_run_context_checksum`,
  `distributed_provenance_manifest_checksum`) lives on `ReferenceRunContext`
  — identical across all 164 tasks in one benchmark run by construction
  (one distributed run produces the whole benchmark), so the existing
  `result.context != run_context` equality check
  (`_require_shared_run_context`) already enforces consistency with zero
  new code.
- **Task-level** (§2/§3: `contributing_worker_context_checksums`,
  `production_identity_checksum`) lives on `ReferenceTaskResult` — free to
  differ per task, exactly like `candidate_id`/`candidate_sha256` already
  do. Two tasks executed by different workers (different machine type,
  different Spot lease, a retry that moved a task to a second worker) are
  simply two different `production_identity_checksum` values in the same
  benchmark — never rejected, never required to match.

This is precisely *why* §2/§3 must live on `ReferenceTaskResult` and never
on `ReferenceRunContext`: placing per-worker identity on the shared run
context would force either a single-worker-only run (contradicting real
multi-worker fleets) or an artificial "first worker wins"/concatenated
representation — exactly the outcome the authorizing instruction's "must
not be placed in the shared `ReferenceRunContext`" constraint forbids.

**Optional, not required, B.4B enhancement**: `ReferenceBenchmarkResult`
could gain a derived, benchmark-level `MixedWorkerProvenanceSummary` (via
`aggregate_worker_provenance`) over the union of every task's contributing
workers, purely for reporting — no instruction requires this, and B.4A
does not mandate it; flagged as an option for B.4B to accept or decline.

## 7. Redaction

**Question**: which checksums are safe to expose, and which mappings
remain protected?

**Unchanged, existing protections** (this design adds no new raw
identifier anywhere): the full `DistributedProvenanceManifest` (embedding
complete `WorkerExecutionContext` records, `generation_command`,
`code_revision`) remains protected operational/calibration evidence, never
committed; `ProtectedOperationalMapping` remains the only place a raw GCP
project ID, hostname, instance ID, or service-account identity may live,
joined back only via `logical_environment_id`; individual
`WorkerExecutionContext` objects are never embedded in any production
schema — only their checksums (§2) are, and resolving a checksum to its
full context requires the protected manifest.

**Safe to expose in the full-fidelity privileged `ReferenceTaskResult`/
`ReferenceRunContext`/`ReferenceAuditRecord` (i.e. `*_to_dict`,
non-redacted)**: all five new fields from §1/§2/§3/§5 — every one is
either a sha256 hex checksum or (for `contributing_worker_context_checksums`)
a tuple of the same.

**Recommended narrower allowlist for `redact_task_result`/
`redact_benchmark_result`** (`src/reference/result_redaction.py`) — a B.4A
recommendation, not an instruction-mandated resolution (see §8, Unresolved
Decision 3): include `distributed_run_context_checksum`,
`distributed_provenance_manifest_checksum`, and
`production_identity_checksum` (three single, coarse, run/aggregate-level
checksums — safe by the same reasoning `SafeRedactedSummary` already
applies to its own coarse, deduplicated `*_observed` tuples); **exclude**
`contributing_worker_context_checksums` from the redacted view for the
per-task-fingerprinting reason given in §5.

**What must never appear in any redacted or safe path, restated from the
existing accepted rule (unchanged by this design)**: raw project IDs,
zones/resource names, instance IDs, service-account addresses, hostnames,
filesystem paths, credentials, and any protected manifest content.

## 8. Unresolved decisions (require explicit resolution, at latest by B.4B's own authorization)

**1. Are the new fields required or optional?** This design makes every
new field `Optional` (`str | None` / empty tuple), with `None` meaning "no
distributed execution substrate recorded" — covering the **only mode any
real reference-evaluation execution has ever actually used in this
repository**: the MEGB-03G.3/G.4 orchestrator running directly against a
local Docker backend, not through the (still entirely offline/synthetic)
distributed coordinator/worker system. Neither accepted `EnvironmentClass`
member (`PERSONAL_BOOTSTRAP`, `COMPANY_PLAYGROUND`) describes this
"no distributed substrate at all" case, and extending that closed enum is
explicitly a B.1-owned decision this checkpoint must not silently make.
Making the fields required would force every non-distributed execution
path to synthesize a fictitious `DistributedRunContext`/
`WorkerExecutionContext` pair, which this design does not recommend.
**Decision needed**: confirm the Optional/`None`-means-legacy design
(this document's default), or separately authorize a B.1 amendment adding
a third `EnvironmentClass` (e.g. `LOCAL_DEVELOPMENT`) so the fields can be
required.

**2. Region/zone exclusion from cache identity, restated as a real
consequence, not merely cited**: because `ProductionIdentityProjection`/
`AggregateProductionIdentityProjection` exclude region and zone (B.1's own
timing-only determination, which this design does not redesign), two
executions in different GCP regions with otherwise-identical
configuration **share a cache key** under this design. This is the
literal, intended consequence of not redesigning B.1's decision — flagged
explicitly here so it is an acknowledged design consequence, not a
silently-inherited surprise discovered later.

**3. Audit/redaction granularity of `contributing_worker_context_checksums`**
(§5/§7): the exclusion recommendation is B.4A's own judgment, reasoned by
analogy to `SafeRedactedSummary`'s zone exclusion — the authorizing
instruction does not itself state whether per-task worker-checksum lists
are safe to expose. Needs explicit confirmation (or a different call)
before B.4B implements `redact_task_result`/`ReferenceAuditRecord`.

**4. `None`-vs-`None` cache equivalence**: with fields Optional, two
distinct non-distributed (legacy/local) executions currently share a
cache key already (today's pre-B.4 behavior, unchanged) — this design
does not attempt to further distinguish "which laptop" produced a local
result, since no such distinction exists in today's schema either. Noted
as a pre-existing characteristic this checkpoint does not resolve, not a
regression this design introduces.

## 9. Cache-reuse decision table

All nine required scenarios, evaluated against `production_identity_checksum`
(§4) — the only new field entering cache identity.

| # | Scenario | `production_identity_checksum` | Cache outcome |
|---|---|---|---|
| 1 | Same run, same worker | Identical | **Hit** |
| 2 | Same run, different worker with equivalent (byte-identical) configuration | Identical (`worker_participant_id` excluded from the projection) | **Hit** |
| 3 | Different run, equivalent production identity (same machine type/provisioning class/image/implementation version/host-runtime/telemetry-policy/environment) | Identical (`distributed_run_id`/manifest checksum excluded from the projection) | **Hit** — the explicitly required cross-run reuse property |
| 4 | Different worker image (`worker_image_digest`) | Differs | **Miss** |
| 5 | Different machine type or resource profile | Differs | **Miss** |
| 6a | Different region or zone only, configuration otherwise identical | Identical (region/zone excluded per B.1, §8 Decision 2) | **Hit** — acknowledged consequence, not redesigned |
| 6b | Different provisioning class (Spot ↔ On-Demand) only | Differs | **Miss** |
| 7 | Different distributed manifest/run, equivalent production identity | Identical `production_identity_checksum`; `distributed_run_context_checksum`/`distributed_provenance_manifest_checksum` differ | **Hit** — cache identity and run-provenance-traceability are intentionally decoupled (§1 vs. §4) |
| 8 | Stale or unverifiable worker provenance (`contributing_worker_context_checksums` entry does not resolve against the claimed manifest via `resolve_worker_context`) | N/A — never reaches key construction | **Rejected at construction/verification**, not a cache miss — mirrors `resolve_worker_context`'s existing "insufficient without a verifiable manifest" rule |
| 9 | Legacy pre-B.4 cache entry (old `cache_key_schema_version`) vs. a new-schema entry with `production_identity_checksum = None` | Schema version differs (old entries lack the field/version entirely) | Old entry: **`STALE_INCOMPATIBLE`**, rejected outright by the existing schema-version check (no migration, matching every prior schema bump's own precedent). New-schema `None` (local/legacy) entry: its own valid, distinct partition — **never** treated as equivalent to any real distributed `production_identity_checksum` |

## 10. Persisted-artifact audit (read-only; no privileged content opened)

**Tracked, committed artifacts**: a repository-wide search (`grep -rl`,
`.json`/`.jsonl`, entire working tree including gitignored paths on disk)
for the literal strings `reference-result-schema-v*`,
`reference-result-cache-key-v*`, `reference-result-cache-entry-v*`, and
`reference-audit-record-v*` returns **zero matches**. This matches each
schema's own module docstring claim that no persisted artifact of any of
these four families has ever existed as a *tracked* artifact.

**Gitignored, regenerable, non-privileged**:
`artifacts/reference/g4_benchmark_audit/g4_benchmark_audit_log.jsonl` — 66
`reference-audit-record-v2`-stamped records from the real MEGB-03G.4
benchmark run, per `reference_audit.py`'s own module docstring (this
document did not re-open the file; the docstring's existing statement was
relied on, since audit records are structurally non-privileged by design
and this fact is already recorded). Already stale today, following the
v2→v3 `cache_disposition` addendum (no migration provided, regenerable by
rerunning G.4) — the same fate a B.4B `AUDIT_RECORD_SCHEMA_VERSION`
v3→v4 bump (§11) would give it again, consistent with this project's
established no-migration-for-regenerable-artifacts precedent.

**Gitignored, regenerable, but genuinely privileged — found, not opened**:
`artifacts/privileged/reference/g4_benchmark_cache/` contains **49 real
files**, content-addressed by cache-key digest filenames (confirmed by
directory listing only — `find`, not `cat`/`Read`), produced by the same
real MEGB-03G.4 benchmark run. **This document did not open, read, or
inspect any of these 49 files** — per instruction, doing so would be
opening real privileged benchmark contents. Their likely stamp is
`reference-result-cache-entry-v2` / `RESULT_SCHEMA_VERSION
reference-result-schema-v4` / `CACHE_KEY_SCHEMA_VERSION
reference-result-cache-key-v2` (today's current versions, per
`reference_cache.py`'s own docstring cross-reference to this same G.4
run) — **inferred from existing documentation, not confirmed by direct
inspection**, and B.4B should treat this as needing explicit confirmation
(or simply proceed on the assumption below) before touching this
directory. **Consequence for B.4B**: under the version-bump matrix in
§11, all 49 entries become schema-incompatible and are rejected via the
cache's own existing `STALE_INCOMPATIBLE` disposition (never silently
reinterpreted) — exactly the audit-log precedent above, and exactly
scenario 9 in §9's decision table. This is expected, acceptable fallout
(gitignored, non-committed, regenerable by rerunning G.4), not a blocker,
and not a migration this document is designing.

**Tracked, non-artifact (source) fixtures**: 16 test files construct
`ReferenceRunContext` directly, 7 construct `ReferenceResultCacheKey`
(directly or via `cache_key_for`), and 1 constructs `ReferenceAuditRecord`
(directly or via `build_audit_record`) — ordinary, expected,
mechanically-updatable call sites (adding the new Optional fields, which
default-compatible construction can supply as `None`/`()`), the same kind
of update every prior schema-version bump in this codebase has already
required and performed. Not enumerated file-by-file here; B.4B's own
implementation pass is the correct place to update them.

## 11. Proposed version-bump matrix

| Constant | Current | Proposed | Reason |
|---|---|---|---|
| `RESULT_SCHEMA_VERSION` | `reference-result-schema-v4` | `reference-result-schema-v5` | `ReferenceRunContext` gains 2 fields (§1); `ReferenceTaskResult` gains 3 fields (§2/§3) — a field-shape change, same discipline as every prior bump in this module |
| `CACHE_KEY_SCHEMA_VERSION` | `reference-result-cache-key-v2` | `reference-result-cache-key-v3` | `ReferenceResultCacheKey` gains 1 field (§4) |
| `CACHE_ENTRY_SCHEMA_VERSION` | `reference-result-cache-entry-v2` | `reference-result-cache-entry-v3` | Depends on both `RESULT_SCHEMA_VERSION` (embedded `task_result`) and `CACHE_KEY_SCHEMA_VERSION` (embedded `cache_key`), mirroring the existing v1→v2 bump's own stated reason |
| `AUDIT_RECORD_SCHEMA_VERSION` | `reference-audit-record-v3` | `reference-audit-record-v4` | `ReferenceAuditRecord` gains 3 fields (§5) |
| Redacted/safe-report schema (`result_redaction.py` — no dedicated version constant exists today; redaction follows `RESULT_SCHEMA_VERSION`) | n/a | n/a — tracks `RESULT_SCHEMA_VERSION` v5 | No independent version constant to bump; the recommended §7 allowlist is a code-level change to `redact_task_result`, gated by the same v5 stamp |
| `DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION` | `megb-03h2c3b3-distributed-provenance-manifest-v1` | **Unchanged** | This design reads `DistributedProvenanceManifest`/`resolve_worker_context` but adds no field to it — no reason to bump |
| `src/distributed/identity.py` types (`ProductionIdentityProjection`, `AggregateProductionIdentityProjection`) | Already versioned via `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION` | **Unchanged** | Reused as-is (§3) — this design adds no field to either type |

**`EXECUTION_PROTOCOL_VERSION` — explicitly not bumped, determination
explained**: two distinct, same-named-in-spirit but unrelated constants
exist. `EXECUTION_PROTOCOL_VERSION = "reference-evaluator-execution-protocol-v1"`
(`src/reference/reference_evaluator.py`) is the reference-evaluator's own
comparison/execution-profile identity — already persisted on
`ReferenceRunContext.execution_protocol_version` since the v4 correction,
unaffected by this design. The actual MEGB-02 candidate-execution **wire**
protocol identity lives on `CandidateExecutionRequest.protocol_version`/
`CandidateExecutionResult.protocol_version` (`src/execution/protocol.py`),
serialized by `src/execution/wire.py`. **None of the fields this design
adds cross that wire boundary** — nothing here changes what a Docker
runner container sends or receives; the new fields are populated entirely
on the controller/reference side, after execution, from
`src/distributed/` types. No wire-protocol version bump is warranted.

## 12. Required B.4B negative-test matrix

All ten scenarios named by the authorizing instruction, each mapped to the
mechanism in this design that must reject it:

1. **Missing/dangling manifest checksum** — `distributed_provenance_manifest_checksum`
   set but does not resolve to any real manifest available to the
   verifier → reject at the same boundary `resolve_worker_context` already
   rejects an unresolvable `worker_context_checksum`.
2. **Unadmitted or substituted worker** — a `contributing_worker_context_checksums`
   entry not present in the claimed run's `DistributedProvenanceManifest`
   → `InvalidDistributedProvenanceError` via `resolve_worker_context`.
3. **Mismatched production-identity projection** — a `production_identity_checksum`
   that does not equal `aggregate_production_identity_for(run_context,
   resolved_workers).projection_checksum` when independently recomputed
   → reject (tampered or fabricated claim).
4. **Mixed workers in one aggregate that do not share
   `parent_run_context_checksum`** — already rejected by
   `require_workers_belong_to_run`/`MismatchedWorkerContextError`
   (existing, reused unchanged) when resolving `contributing_worker_context_checksums`.
5. **Cross-run equivalent cache reuse** — a **positive** test: two
   `ReferenceTaskResult`s built from different `DistributedRunContext`s
   with byte-identical `AggregateProductionIdentityProjection` inputs
   produce an **identical** `ReferenceResultCacheKey.key_digest` (proves
   §9 scenario 3, not a rejection).
6. **Changed worker image/machine type cache invalidation** — a **positive**
   contrast test: identical run/task, one field of the projection changed
   → different `key_digest` (proves §9 scenarios 4/5).
7. **Stale pre-B.4 schema rejection** — a `reference-result-cache-key-v2`-stamped
   payload (missing `production_identity_checksum` entirely) deserialized
   under v3 code → `InvalidCacheKeyError`/`STALE_INCOMPATIBLE`, no silent
   reinterpretation under the new field names.
8. **Audit/cache/result disagreement** — a `ReferenceAuditRecord` whose
   `production_identity_checksum` does not equal the `ReferenceTaskResult`/
   `ReferenceResultCacheKey` it accompanies → reconciliation failure (new
   check; no such cross-check exists pre-B.4, since the field itself is
   new).
9. **Safe-report leakage** — a structural field-allowlist test (mirroring
   `tests/test_distributed_leakage.py`'s existing pattern) asserting
   `contributing_worker_context_checksums` is absent from whatever
   `redact_task_result` returns, and that no raw project ID, hostname, or
   any other `ProtectedOperationalMapping`-owned field name ever appears
   on any of the four new field sets.
10. **Raw GCP identifier rejection** — a `_reject_if_looks_like_secret`
    style defense-in-depth test (mirroring
    `src/distributed/protected_mapping.py`'s existing pattern) confirming
    a value shaped like a raw project ID/service-account email/credential
    passed into any of the new checksum-typed fields is rejected by the
    existing sha256-hex-format validation (a raw identifier is
    structurally not a valid 64-character hex digest, so this is largely
    already true by construction — the test proves it, not adds new logic).

## Related documents

- `docs/reference/megb-03h2c3a-gcp-provenance-audit.md` — source of the
  blocking precondition this design closes.
- `docs/operations/megb-03h2c3e-access-readiness-review.md` — the
  checkpoint that confirmed the gap was still open and proposed this
  checkpoint's identifier.
- `docs/reference/megb-03h2c3b1-provenance-field-matrix.md`,
  `megb-03h2c3b1-integration-map.md` — the original field-ownership
  determination this design reuses without redesigning.
- `docs/reference/megb-03h2c3b3-calibration-provenance-integration-design.md`
  — the calibration-side integration this design's §1 pattern mirrors.
- `docs/reference/version-registry.md` — current values for every
  constant in §11's version-bump matrix.
