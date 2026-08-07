# MEGB-03H.2C.3B.4A — Production Distributed-Provenance Integration Design and Persistence Audit

**Status: frozen design and read-only audit only. No production schema
modified, no version bumped, no `src/`/`tests/` file touched, no real
privileged artifact opened.** This document is B.4A's own deliverable —
the design B.4B must implement, not implementation itself.

**Corrected in place** (this is a design document, amended in place per
this project's established convention — unlike the ticket's own
append-only row history, which records the correction as a new row
without editing the prior execution row). The correction traced the
actual `ReferenceResultCache.get → ReferenceOrchestrator → audit →
aggregate_reference_results` code path and found the original version's
§1/§4/§5 design (`str | None` fields, no explicit producer/consumer
split) was insufficient: it could not express "this task's bytes were
produced by a different distributed run than the one now consuming it,"
which is the ordinary, expected shape of cache reuse. This version
replaces those sections with an explicit orchestration-substrate
discriminator, a derived (never caller-asserted) identity-construction
path, and a named producer/consumer provenance split. Sections unaffected
by the correction (§0 scope, most of aggregation reasoning, the
persisted-artifact audit) are carried forward with field-name updates
only.

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

`src/distributed/identity.py` already defines `ProductionIdentityProjection`
and `AggregateProductionIdentityProjection` (built during the
MEGB-03H.2C.3B.1 conformance-audit correction) — exactly the
outcome-affecting subset of provenance a production integration needs,
already resolved against the field-ownership matrix, already
self-checksummed. This design wires those existing types into the
production schemas; it does not redesign them.

**One further precedent this correction relies on**:
`src/reference/distributed_provenance_reconciliation.py` is documented as
**"the only module in `src/reference/` permitted to import
`src.distributed`"** (enforced by
`tests/test_distributed_dependency_direction.py`) and already implements
the calibration-side analogue of everything §3 below needs
(`reconcile_calibration_run_context`, `reconcile_calibration_invocation_worker`).
The new production-side construction/reconciliation logic belongs there,
extending it — not in `result_schema.py`, which must not import
`src.distributed` directly.

## 1. Orchestration-substrate discriminator

**Problem this closes**: the original design relied on field-`None`-ness
alone to distinguish "no distributed execution" from "distributed
execution," with no explicit, closed statement of which mode a record is
in — exactly what this correction's instruction rejects ("do not rely on
`None` alone").

**Design**: a new closed enum, owned by `src/reference/result_schema.py`
(a reference-execution concern, not a `src.distributed` concept — `B.1`'s
`EnvironmentClass` is deliberately not modified or extended):

```python
class ReferenceOrchestrationSubstrate(str, Enum):
    LOCAL_REFERENCE_ORCHESTRATOR = "LOCAL_REFERENCE_ORCHESTRATOR"
    DISTRIBUTED_REFERENCE_ORCHESTRATOR = "DISTRIBUTED_REFERENCE_ORCHESTRATOR"
```

`LOCAL_REFERENCE_ORCHESTRATOR` covers the **only mode any real reference
evaluation has ever actually used in this repository**: the MEGB-03G.3/G.4
orchestrator running directly against a local Docker backend, never
through the (still entirely offline/synthetic) distributed
coordinator/worker system. `DISTRIBUTED_REFERENCE_ORCHESTRATOR` covers
execution admitted through that system. Closed by design, exactly
mirroring `CloudProvider`'s own closed-but-extensible pattern — a third
mode is added by adding a member, never by accepting a free-form string.

**Where it enters** (three places, as required):

- `ReferenceRunContext.orchestration_substrate` — the **consuming**
  orchestration session's own substrate (see §2's "consuming vs.
  producing" distinction).
- `ReferenceResultCacheKey.orchestration_substrate` — participates
  directly in `key_digest`'s hashed payload (§5) as an explicit,
  structural guarantee, not merely an emergent consequence of `None`
  never colliding with a real checksum.
- `ReferenceAuditRecord.consuming_orchestration_substrate` and
  `producing_orchestration_substrate` — both, since the two can differ on
  a cache hit (§9).

**Frozen structural invariants** (enforced in `__post_init__`, raising
`InvalidReferenceResultError` — or a `ReferenceResultProducerProvenance`-scoped
equivalent, §3 — on violation, never silently coerced):

1. `orchestration_substrate == LOCAL_REFERENCE_ORCHESTRATOR` **requires**
   `distributed_run_context_checksum is None` and
   `distributed_provenance_manifest_checksum is None` on
   `ReferenceRunContext`, and requires every distributed-specific field on
   `ReferenceResultProducerProvenance` (§3) to be `None`/empty/zero for any
   task result whose own `producer_provenance.substrate` is also `LOCAL_REFERENCE_ORCHESTRATOR`.
2. `orchestration_substrate == DISTRIBUTED_REFERENCE_ORCHESTRATOR`
   **requires** both `ReferenceRunContext` checksums to be present
   (non-`None`, valid sha256 hex). For any `producer_provenance` whose own
   `substrate` is `DISTRIBUTED_REFERENCE_ORCHESTRATOR`, **all** of
   `distributed_run_context_checksum`, `distributed_provenance_manifest_checksum`,
   `contributing_worker_context_checksums` (nonempty),
   `contributing_worker_contexts_checksum`, `contributing_worker_count`
   (≥ 1), and `production_identity_checksum` must be present and
   internally consistent (§3's derivation, independently re-verified at
   construction) — **a distributed producer_provenance with any of these
   missing is a construction-time `InvalidReferenceResultError`, never
   silently accepted and never reinterpreted as local.**
3. A task's own `producer_provenance.substrate` is **independent** of the
   consuming `ReferenceRunContext.orchestration_substrate` — a
   `DISTRIBUTED_REFERENCE_ORCHESTRATOR` session may legitimately serve a
   `LOCAL_REFERENCE_ORCHESTRATOR`-produced cache hit (an older, pre-B.4B
   or genuinely local-only cache entry reused by a distributed-capable
   consumer) and vice versa (a `LOCAL_REFERENCE_ORCHESTRATOR` session
   consulting a shared cache store may hit a `DISTRIBUTED_REFERENCE_ORCHESTRATOR`-produced
   entry). No cross-constraint links the two; each is independently valid
   per invariants 1/2 above. **Recommended, not mandated, B.4B
   enhancement**: `ReferenceBenchmarkResult` could expose a derived
   "producer substrates observed" set (mirroring `MixedWorkerProvenanceSummary`'s
   own aggregation pattern) purely so a reader can see at a glance whether
   a 164-task aggregate is homogeneously distributed-produced or a mix —
   not required by this correction, flagged as optional.
4. **Cache separation**: `ReferenceResultCacheKey.orchestration_substrate`
   entering the digest (§5) means a `LOCAL_REFERENCE_ORCHESTRATOR` cache
   key and a `DISTRIBUTED_REFERENCE_ORCHESTRATOR` cache key **can never
   collide**, structurally — not merely because `production_identity_checksum`
   happens to be `None` on one side (which is also true, but this makes it
   a second, independent guarantee rather than the only one).
5. **Local-mode `None` semantics, preserved exactly**: for
   `LOCAL_REFERENCE_ORCHESTRATOR`, `production_identity_checksum` remains
   `None` in the cache key, preserving today's existing local cache
   behavior (two local executions with identical cache-key-relevant
   fields already hit each other, unchanged by this design) — `None` is
   valid and expected for local mode; it is only ever *insufficient as
   the sole discriminator*, which invariant 4's explicit `orchestration_substrate`
   field now resolves.

## 2. Run-level identity — consuming session, not per-task

`ReferenceRunContext.distributed_run_context_checksum`/
`distributed_provenance_manifest_checksum` (unchanged names from the
original design) now have an explicitly stated, narrower meaning:
**the distributed run (if any) that the current, consuming orchestration
session is itself operating under** — a session-level fact, shared across
all 164 tasks in one benchmark by construction, exactly like every other
`ReferenceRunContext` field already is. For a session with zero
distributed backend involvement (the common case today), both are `None`
and `orchestration_substrate = LOCAL_REFERENCE_ORCHESTRATOR`.

**This is deliberately not the same thing as "which distributed run
actually produced task N's bytes."** That is a **per-task, producer-side**
fact (§3/§6) — because a single consuming session may legitimately serve
some tasks fresh (producer = consumer, values agree) and some from cache
entries written under a different historical distributed run entirely
(producer ≠ consumer). Conflating the two — as the original design
implicitly did by treating `ReferenceRunContext`'s distributed fields as
if they were also the per-task producer identity — is exactly the defect
§6 traces and fixes.

`aggregate_reference_results`'s existing shared-run-context equality check
(`src/reference/aggregation.py::_require_shared_run_context`) requires no
modification: these two fields are session-level, so they are trivially
identical across all 164 task results' `.context`, by the same
construction as `experiment_run_id` already is today.

## 3. Worker and production identity — derived, not caller-asserted

**New type**, owned by `src/reference/result_schema.py` (nested within
`ReferenceTaskResult`'s own schema, not a `src.distributed` type):

```python
@dataclass(frozen=True)
class ReferenceResultProducerProvenance:
    substrate: ReferenceOrchestrationSubstrate
    distributed_run_context_checksum: str | None
    distributed_provenance_manifest_checksum: str | None
    contributing_worker_context_checksums: tuple[str, ...]  # sorted, deduplicated — §4
    contributing_worker_contexts_checksum: str | None       # derived — §4
    contributing_worker_count: int                          # derived — §4
    production_identity_checksum: str | None                # derived — this section
    producer_provenance_checksum: str = ""                  # self-checksum, auto-compute-or-reject
```

`ReferenceTaskResult` gains exactly one new field: `producer_provenance:
ReferenceResultProducerProvenance` — **always present** (never a
top-level `None`), so the substrate discriminator itself is always
structurally available for the invariants in §1 to check, rather than
being inferable only from the absence of other fields.

**Frozen construction/reconciliation path** (new function,
`build_reference_result_producer_provenance`, added to
`src/reference/distributed_provenance_reconciliation.py` — the one module
permitted to import `src.distributed`; not implemented by this
checkpoint, only designed):

```python
def build_reference_result_producer_provenance(
    *,
    lock: ManifestLockFile,
    claimed_distributed_run_context_checksum: str,
    claimed_distributed_provenance_manifest_checksum: str,
    contributing_worker_context_checksums: tuple[str, ...],
    claimed_production_identity_checksum: str | None = None,
) -> ReferenceResultProducerProvenance:
```

1. **Resolve the protected manifest through its validated lock.** Finds
   the `ManifestLockEntry` in `lock` whose `manifest_checksum` equals
   `claimed_distributed_provenance_manifest_checksum`, then loads and
   verifies the actual protected manifest bytes against that entry —
   reusing the same containment-validated, self-checksummed verification
   chain `verify_against_lock`/`load_lock_file` already establish
   (`src/distributed/provenance_manifest_lock.py`). **New B.4B-scoped
   primitive this depends on**: `provenance_manifest_lock.py` needs a
   public `resolve_verified_manifest(lock, manifest_checksum) ->
   DistributedProvenanceManifest` (today, the equivalent logic exists only
   as the private `_load_protected_manifest`, and `verify_against_lock`
   returns pass/fail booleans, not the manifest object) — named here, not
   implemented.
2. **Verify the run-context and manifest checksums.** Compares
   `manifest.run_context.run_context_checksum ==
   claimed_distributed_run_context_checksum` and
   `manifest.manifest_checksum == claimed_distributed_provenance_manifest_checksum`,
   raising `DistributedProvenanceReconciliationError` on any mismatch —
   the identical two-check shape `reconcile_calibration_run_context`
   already applies to the calibration side, applied here to the
   production side.
3. **Resolve every contributing worker checksum.** For each entry in
   `contributing_worker_context_checksums`, calls the existing
   `resolve_worker_context(manifest, checksum)`
   (`src/distributed/provenance_manifest.py`) — raises
   `InvalidDistributedProvenanceError` (wrapped as
   `DistributedProvenanceReconciliationError`) for any checksum not
   present in *this specific* manifest.
4. **Reject unknown, duplicate, substituted, or wrong-run workers.**
   Unknown/wrong-run collapse into step 3's own failure mode (`resolve_worker_context`
   only searches within one manifest's own worker set, which — by
   `DistributedProvenanceManifest.__post_init__`'s own existing
   `require_workers_belong_to_run` check — can only ever contain workers
   whose `parent_run_context_checksum` already matches that manifest's run
   context; there is no way for a "wrong-run" worker to be present in the
   manifest being searched at all). Duplicate is checked explicitly before
   step 3 (`len(set(checksums)) != len(checksums)` → reject). Substitution
   (a checksum resolving to a real but different worker than intended) is
   structurally prevented by the checksum being a content-bound sha256
   identity of that specific worker's own fields — a substituted worker
   would require a hash collision.
5. **Deterministically construct `AggregateProductionIdentityProjection`.**
   Calls the existing, unmodified
   `aggregate_production_identity_for(manifest.run_context, resolved_workers)`
   (`src/distributed/identity.py`) over the resolved
   `WorkerExecutionContext` objects from step 3, in the manifest's own
   canonical (checksum-sorted) order.
6. **Derive `production_identity_checksum`.** Equals the resulting
   `AggregateProductionIdentityProjection.projection_checksum` exactly —
   never independently computed by this function, only read off the
   already-self-checksummed projection.
7. **Refuse a disagreeing caller-supplied checksum.** If
   `claimed_production_identity_checksum` is not `None` and differs from
   step 6's derived value, raise — the same auto-compute-or-reject
   discipline every self-checksummed type in this codebase already
   applies, extended here to a *cross-type* derivation rather than a
   type's own internal recomputation.

`contributing_worker_contexts_checksum`/`contributing_worker_count` (§4)
are computed from the same resolved, sorted, deduplicated tuple as a
final step, and `producer_provenance_checksum` is computed last, over the
whole assembled record.

**Why `production_identity_checksum` alone is insufficient** (motivating
§4's separate field): `AggregateProductionIdentityProjection`'s own
checksum is computed *only* from outcome-affecting configuration fields —
`worker_participant_id` is deliberately excluded (by design, so
config-equivalent workers share one checksum, §5's required cache-reuse
property). Consequently, **two different actual contributor sets that
happen to share identical configuration produce an identical
`production_identity_checksum`** — correct and intended for cache
identity, but it means this checksum alone cannot answer "which
specific workers actually contributed," which reconciliation/audit needs.
`contributing_worker_contexts_checksum` closes exactly this gap: it
changes whenever the actual participant *set* changes (e.g. a retry moves
a task to a differently-`worker_participant_id`'d but identically
configured worker), even when `production_identity_checksum` stays fixed.

## 4. Worker-set reconciliation without exposure

**`contributing_worker_context_checksums` semantics, stated explicitly**:
a **sorted, deduplicated tuple of distinct participant identities** — one
entry per contributing `worker_participant_id`'s own
`worker_context_checksum`, never a multiset/histogram. The same
participant cannot appear twice (duplicate rejected at construction, §3
step 4). Genuine **multiplicity** — multiple *distinct* workers
contributing to one task (e.g. an infrastructure retry that moved
execution to a second worker) — is fully represented as additional
distinct tuple entries, exactly mirroring
`MixedWorkerProvenanceSummary`'s own "genuine multiplicity... counted, not
collapsed" precedent. Per-*configuration* multiplicity (how many
contributing workers shared machine type X) remains entirely
`AggregateProductionIdentityProjection`'s own internal histogram
responsibility (§3, unchanged, reused as-is) — `contributing_worker_context_checksums`
answers a different question ("which participants") than the projection's
histograms answer ("what configuration mix").

**Derived fields, bound into the task result's own self-checksum**:

- `contributing_worker_contexts_checksum: str | None` — sha256 over the
  canonical-JSON sorted list of `contributing_worker_context_checksums`
  (the same canonical-hashing convention every other checksum in this
  codebase already uses, e.g. `MixedWorkerProvenanceSummary.aggregate_checksum`).
  `None` iff `substrate == LOCAL_REFERENCE_ORCHESTRATOR`.
- `contributing_worker_count: int` — `len(contributing_worker_context_checksums)`.
  `0` iff `substrate == LOCAL_REFERENCE_ORCHESTRATOR`.

Both participate in `ReferenceResultProducerProvenance.producer_provenance_checksum`'s
own payload (so tampering with either is caught the same way tampering
with any other field already is), and both — **not the raw tuple** —
propagate into `ReferenceAuditRecord` and any safe/redacted projection
(§8/§9). The raw `contributing_worker_context_checksums` tuple itself
remains only on the always-privileged, full-fidelity `ReferenceTaskResult`.
This gives full reconciliation capability (a verifier holding the
privileged result can recompute `contributing_worker_contexts_checksum`
from the raw tuple and confirm it matches) without exposing or letting an
external reader correlate individual worker pseudonyms across tasks or
runs from the safe/audit path alone — mirroring
`SafeRedactedSummary`'s own established zone-exclusion precedent for
exactly this class of per-record topology-fingerprinting concern.

## 5. Cache identity

`ReferenceResultCacheKey` gains **two** new fields (revised from the
original design's one):

- `orchestration_substrate: str` — §1's discriminator, entering the
  digest directly.
- `production_identity_checksum: str | None` — unchanged from the
  original design, `AggregateProductionIdentityProjection.projection_checksum`.

**Nothing else** from the distributed side enters the cache key —
`distributed_run_context_checksum`, `distributed_provenance_manifest_checksum`,
`contributing_worker_context_checksums`/`contributing_worker_contexts_checksum`/
`contributing_worker_count`, any run/participant/attempt/delivery id, and
any timestamp remain deliberately excluded, unchanged from the original
design's rationale (`cache_key.py`'s own "run IDs... belong in
audit/mapping records instead" precedent). This still satisfies every
required cache-identity property (cross-worker same-run reuse, cross-run
reuse for equivalent environments, invalidation on any real configuration
change, B.1's region/zone-excluded/provisioning-class-included
determination unchanged) exactly as the original design established —
§1's addition only strengthens the local/distributed separation
guarantee from emergent to structural, and does not change any other
cache-reuse property.

## 6. Producer-versus-consumer provenance for cache hits

### 6.1 Traced: what the code does today

`ReferenceOrchestrator._execute_key_group`
(`src/reference/reference_orchestrator.py:702-726`): on `CacheDisposition.VALID_HIT`,
`lookup.task_result` — **the cached object exactly as originally stored,
including its own originally-embedded `.context`** — is returned
unmodified, with no rebinding step of any kind:

```python
if lookup.disposition == CacheDisposition.VALID_HIT:
    ...
    return KeyExecutionResult(
        WorkItemDisposition.CACHE_HIT, lookup.task_result, 0, "served from cache"
    )
```

`_append_audit` (`reference_orchestrator.py:977-1000`) builds the audit
record from **`representative.run_context`** — the current work item's
own (consuming) context — for every run-identity field
(`experiment_run_id`, `optimization_run_id`, `portfolio_frozen_at`,
`portfolio_selection_rule`, `evaluator_version`, `dataset_version`,
`partition_version`, `execution_profile_id`, `comparison_profile_version`,
`execution_protocol_version`, `dataset_checksum`, `task_manifest_checksum`)
— **not** from `task_result.context`. Only outcome-of-execution fields
(`candidate_id`, `candidate_sha256`, `oracle_version`,
`reference_case_checksum`, `task_id`, `status`, `duration_seconds`) are
sourced from `task_result` itself. This means the audit record **already**
implicitly reflects the *consuming* run's identity for every run-level
field — a sound, if undocumented, precedent this design's audit matrix
(§9) makes explicit rather than inventing.

**The actual gap**: the returned `ReferenceTaskResult` object that flows
onward into `aggregate_reference_results`
(`src/reference/aggregation.py::_require_shared_run_context`) still
carries the *producer's* `.context` embedded, unconditionally. Because
`ReferenceRunContext`'s full dataclass equality includes fields **not**
part of the cache key (`experiment_run_id`, `optimization_run_id`,
`optimization_config_sha256`, `portfolio_frozen_at`,
`portfolio_selection_rule`), **a cache hit whose original producing run
differs from the consuming run in any of those fields today produces a
`ReferenceTaskResult` that cannot coexist with a fresh (consumer-context)
result in one `ReferenceBenchmarkResult` aggregate** —
`_require_shared_run_context` rejects the mix the moment even one cached
result's context disagrees. This is a genuine, pre-existing (not
introduced by B.4A) architectural gap: today, cross-run cache reuse only
actually works if callers happen to keep those five fields byte-identical
across "different" runs — which defeats the purpose of per-run identity
tracking. This correction's design (below) closes this gap as a
byproduct of satisfying the distributed-provenance requirement, since the
same rebinding mechanism generalizes to both.

### 6.2 Frozen mechanism

**On every `VALID_HIT`, the orchestrator constructs a new
`ReferenceTaskResult`** (never mutates or returns the cached object
as-is — it is `frozen=True`, so this is structural, not merely a style
choice) via a new function, `rebind_cached_result_to_consuming_context`
(owned by `src/reference/result_schema.py` — no `src.distributed` import
needed, since it operates purely on already-constructed
`ReferenceRunContext`/`ReferenceTaskResult` objects):

```python
def rebind_cached_result_to_consuming_context(
    cached_result: ReferenceTaskResult,
    consuming_context: ReferenceRunContext,
) -> ReferenceTaskResult:
```

This function:

1. Confirms `cached_result` and `consuming_context` agree on every field
   that already participates in `ReferenceResultCacheKey` (dataset,
   partition, oracle, comparison profile, evaluator, execution profile,
   protocol version, task manifest checksum, `orchestration_substrate`,
   `production_identity_checksum`) — this is already guaranteed by the
   fact that a `VALID_HIT` occurred (the lookup key was computed from
   `consuming_context`), so this is a redundant, cheap defensive
   assertion, not new trust.
2. Returns a **new** `ReferenceTaskResult` with `context = consuming_context`
   (satisfying "the aggregator receives a coherent current scientific/run
   context") and `producer_provenance = cached_result.producer_provenance`
   **carried through unchanged** — the cached entry's original producing
   run/manifest/worker-set/production-identity remain exactly as they
   were at cache-write time, immutable and fully attributable (satisfying
   "producing provenance... remains immutable and attributable" and
   "without erasing producing provenance"). Every other field
   (`candidate_id`, `candidate_sha256`, `status`, `q_ref_task`,
   `reference_case_total`, `reference_case_pass_count`,
   `first_failure_category`, `oracle_version`, `reference_case_checksum`,
   `evaluated_at`, `duration_seconds`, `execution_failure_counts`,
   `full_suite_diagnostic`, `diagnostics`) is carried through unchanged
   from `cached_result` — these are outcome-of-execution facts, correctly
   producer-sourced regardless of who is now consuming them.

This is a **rebinding**, not a new persisted type: no new versioned
wrapper artifact is written to disk, and no new schema-version constant
is required beyond `RESULT_SCHEMA_VERSION`'s own bump (§13) for
`ReferenceTaskResult`'s new `producer_provenance` field itself. The
"new versioned cache-consumption binding" the correction's instruction
anticipated is `ReferenceResultProducerProvenance` (§3) — the field that
makes rebinding safe (because it is *disjoint* from `context`, swapping
`context` cannot destroy it) — plus this one pure function; no additional
wrapper type is needed once the producer/consumer split exists as a first-class
field split within `ReferenceTaskResult` itself.

**Where this is called**: `_execute_key_group`'s `VALID_HIT` branch,
replacing the bare `lookup.task_result` return with
`rebind_cached_result_to_consuming_context(lookup.task_result,
representative.run_context)`. `_append_audit`'s existing sourcing
(`run_context=representative.run_context` for run-identity fields,
`task_result=...` for outcome fields) requires **no change** — it already
does the right thing, as traced in §6.1 — except that it must now also
source the *producing*-side audit fields (§9) from
`cached_result.producer_provenance` specifically (the pre-rebind object,
or equivalently `rebound_result.producer_provenance`, since rebinding
preserves it unchanged) rather than from `rebound_result.context`.

**Checklist against every required property**:

- *Producing run/manifest/worker-set/production identity remain immutable
  and attributable*: `producer_provenance` is carried through unchanged by
  construction (never reconstructed, never merged).
- *Consuming run and manifest recorded separately*: `context` (→
  `ReferenceRunContext.distributed_run_context_checksum`/`manifest_checksum`,
  §2) always reflects the consumer; `producer_provenance` always reflects
  the producer. Two disjoint field sets, never conflated.
- *Cache hit never claims a current worker freshly executed the result*:
  `producer_provenance.contributing_worker_context_checksums` are always
  the *original* producer's workers; nothing in this design ever
  substitutes the consuming session's own (possibly nonexistent, for a
  `LOCAL_REFERENCE_ORCHESTRATOR` consumer) workers into a cache-hit
  result.
- *Equivalent production identities may reuse cache across runs*:
  unchanged from §5 — `production_identity_checksum` excludes run/manifest
  identity by construction.
- *Fresh and cached results may coexist in one aggregate*: guaranteed —
  every task result entering `aggregate_reference_results`, fresh or
  rebound, carries `context == consuming_context` by construction, so
  `_require_shared_run_context`'s existing equality check trivially
  passes regardless of how many distinct historical producing runs
  contributed cache hits.
- *Aggregator receives coherent current context without erasing producing
  provenance*: both halves of the checklist above, simultaneously.
- *Audit distinguishes producer from consumer for cache hits*: §9.
- *Missing/stale/unverifiable producer provenance rejected or classified
  stale, never silently rebound*: `rebind_cached_result_to_consuming_context`
  performs **no** re-verification of `producer_provenance` against any
  manifest (that already happened once, at the original cache-write time,
  via §3's construction path) — it only requires `producer_provenance` to
  already be internally self-consistent, which
  `ReferenceResultProducerProvenance.__post_init__`'s own checksum
  re-verification (run on every deserialization, including the cache's
  own `task_result_from_dict`) already structurally guarantees. A cache
  entry whose stored `producer_provenance` fails that self-check —
  corrupted, tampered, or stamped under a stale schema version — is
  rejected by the cache's own existing `CORRUPT`/`STALE_INCOMPATIBLE`
  disposition **before** `rebind_cached_result_to_consuming_context` is
  ever called, exactly mirroring how a corrupted `task_result` is already
  rejected today.

## 7. Aggregation

Unchanged in substance from the original design, restated precisely
against the corrected field names: **run-level** fields (§2:
`ReferenceRunContext.orchestration_substrate`/`distributed_run_context_checksum`/
`distributed_provenance_manifest_checksum`) are shared across all 164
tasks by construction (consuming-session facts, and — per §6 — every
task result entering an aggregate carries the *consuming* context
regardless of fresh/cache-hit origin), so `_require_shared_run_context`
needs no modification. **Task-level** fields (§3/§4:
`ReferenceTaskResult.producer_provenance`, including its own nested
substrate) are free to differ per task — exactly like `candidate_id`
already does, and now additionally like "which historical run actually
produced this task's bytes" legitimately does too.

## 8. Redaction

Unchanged core protections (no new raw identifier anywhere; the full
`DistributedProvenanceManifest`, `ProtectedOperationalMapping`, and
individual `WorkerExecutionContext` objects remain protected/never
embedded — only checksums ever appear in any production schema).

**Recommended redacted-view allowlist** (`redact_task_result`), revised
for the corrected field set: include `orchestration_substrate` (both
consuming, via `context`, and producing, via `producer_provenance.substrate`
— coarse, closed-enum values, safe), `distributed_run_context_checksum`/
`distributed_provenance_manifest_checksum` (consuming, from `context`),
and from `producer_provenance`: `distributed_run_context_checksum`/
`distributed_provenance_manifest_checksum` (producing),
`production_identity_checksum`, `contributing_worker_contexts_checksum`,
`contributing_worker_count`. **Exclude** the raw
`contributing_worker_context_checksums` tuple (§4's fingerprinting
rationale, unchanged). This is still a B.4A recommendation, not an
instruction-mandated resolution — flagged in §10.

## 9. Audit-field matrix

`ReferenceAuditRecord` gains, as flat scalar fields (never a nested
object — preserving this record's own established "flat,
independently-serializable" discipline; the constituent checksums already
give full reconciliation capability without embedding
`ReferenceResultProducerProvenance` itself):

| Field | Source (fresh or cache hit, uniformly) |
|---|---|
| `consuming_orchestration_substrate` | `run_context.orchestration_substrate` (`representative.run_context`, i.e. the current work item's context — unchanged sourcing from today's code) |
| `consuming_distributed_run_context_checksum` | `run_context.distributed_run_context_checksum` |
| `consuming_distributed_provenance_manifest_checksum` | `run_context.distributed_provenance_manifest_checksum` |
| `producing_orchestration_substrate` | `task_result.producer_provenance.substrate` |
| `producing_distributed_run_context_checksum` | `task_result.producer_provenance.distributed_run_context_checksum` |
| `producing_distributed_provenance_manifest_checksum` | `task_result.producer_provenance.distributed_provenance_manifest_checksum` |
| `production_identity_checksum` | `task_result.producer_provenance.production_identity_checksum` — inherently a producer-side fact only; no separate "consuming" variant exists (production identity describes who executed the candidate, never who is now reading the result) |
| `contributing_worker_contexts_checksum` | `task_result.producer_provenance.contributing_worker_contexts_checksum` |
| `contributing_worker_count` | `task_result.producer_provenance.contributing_worker_count` |
| `cache_disposition` | unchanged, existing field |

**Nullability rule, stated once, governed by substrate alone — not by
`cache_disposition`**: every `consuming_*`/`producing_*` pair is
`None`/`0` **if and only if** its own substrate value is
`LOCAL_REFERENCE_ORCHESTRATOR`; populated and internally verified
whenever its substrate is `DISTRIBUTED_REFERENCE_ORCHESTRATOR` — per §1's
invariants, independent of whether the record describes a fresh execution
or a cache hit. `cache_disposition` is an orthogonal axis: it says
*whether* a cache lookup occurred and what it found, not *what
substrate* was involved.

**Illustrative combinations** (not exhaustive — the general rule above is
authoritative):

| Scenario | `consuming_orchestration_substrate` | `producing_orchestration_substrate` | `production_identity_checksum` |
|---|---|---|---|
| Fresh execution, local session | `LOCAL_...` | `LOCAL_...` | `None` |
| Fresh execution, distributed session | `DISTRIBUTED_...` | `DISTRIBUTED_...` (equal to consuming — producer = consumer for fresh) | Present |
| Cache hit, local session, local-produced entry | `LOCAL_...` | `LOCAL_...` | `None` |
| Cache hit, distributed session, **local**-produced (legacy) entry | `DISTRIBUTED_...` | `LOCAL_...` | `None` |
| Cache hit, distributed session, distributed-produced entry from a **different** historical run | `DISTRIBUTED_...` | `DISTRIBUTED_...` (values differ from consuming) | Present, equal to the producing run's own |
| Cache hit, distributed session, distributed-produced entry from **this same** run (a retry-then-reused-within-run case) | `DISTRIBUTED_...` | `DISTRIBUTED_...` (values equal consuming) | Present |

## 10. Remaining and updated unresolved decisions

**Resolved by this correction** (were open in the original design):

- Producer-vs-consumer cache-hit handling: §6's rebinding mechanism,
  concretely specified, not deferred to B.4B.
- The substrate-vs-`None` ambiguity: §1's explicit enum.
- Worker-set exposure vs. reconciliation tension: §4's derived-checksum
  split.

**Still open, carried forward or newly surfaced**:

1. **Naming**: `ReferenceOrchestrationSubstrate`,
   `ReferenceResultProducerProvenance`, and
   `rebind_cached_result_to_consuming_context` are this document's
   proposed names — provisional, per the correction's own framing of the
   enum values as "provisionally" named; B.4B may rename during
   implementation review without needing a further B.4A round, provided
   the field semantics/invariants above are preserved.
2. **`resolve_verified_manifest`** (§3, step 1) is a new small public
   primitive this design depends on but does not implement — B.4B must
   add it to `provenance_manifest_lock.py` before
   `build_reference_result_producer_provenance` can be implemented.
3. **Audit/redaction granularity of `contributing_worker_contexts_checksum`/`count`**
   (§8/§9): including these two derived (non-raw) fields is this
   document's recommendation, reasoned by analogy, not an
   instruction-mandated resolution — needs explicit confirmation before
   B.4B implements `redact_task_result`/`ReferenceAuditRecord`.
4. **Optional benchmark-level "producer substrates observed" summary**
   (§1, invariant 3): flagged as an option, not required.
5. **Local-mode cache non-distinguishability** (unchanged from the
   original design): two distinct `LOCAL_REFERENCE_ORCHESTRATOR`
   executions still share a cache key with no further distinction (e.g.
   different developer machines) — a pre-existing characteristic, not a
   regression this design introduces, and out of this checkpoint's scope
   to resolve.

## 11. Cache-reuse decision table

Revised to reflect §1's `orchestration_substrate` participating in the
digest directly, alongside `production_identity_checksum`.

| # | Scenario | `orchestration_substrate` | `production_identity_checksum` | Cache outcome |
|---|---|---|---|---|
| 1 | Same run, same worker | Identical (`DISTRIBUTED_...`) | Identical | **Hit** |
| 2 | Same run, different worker, equivalent configuration | Identical | Identical (`worker_participant_id` excluded from the projection) | **Hit** |
| 3 | Different run, equivalent production identity | Identical | Identical (`distributed_run_id`/manifest checksum excluded from the projection) | **Hit** — the required cross-run reuse property |
| 4 | Different worker image | Identical | Differs | **Miss** |
| 5 | Different machine type/resource profile | Identical | Differs | **Miss** |
| 6a | Different region/zone only | Identical | Identical (region/zone excluded per B.1, unchanged) | **Hit** — acknowledged consequence, not redesigned |
| 6b | Different provisioning class (Spot ↔ On-Demand) | Identical | Differs | **Miss** |
| 7 | Different manifest/run, equivalent production identity | Identical | Identical; `producer_provenance.distributed_run_context_checksum`/`manifest_checksum` differ from the consuming session's own (§2/§6) | **Hit** — cache identity and run-provenance-traceability intentionally decoupled |
| 8 | Stale or unverifiable worker provenance | N/A — never reaches key construction | N/A | **Rejected at construction** (§3 steps 3/4), not a cache miss |
| 9 | Legacy pre-B.4 entry vs. new-schema `None` (local) entry | Old entry lacks the field/version entirely | — | Old: `STALE_INCOMPATIBLE`. New `None` (local): its own distinct partition |
| 10 (**new**) | Local-mode consumer, distributed-mode cache entry, or vice versa | Differs (`LOCAL_...` vs. `DISTRIBUTED_...`) | — (moot — substrate alone already differs) | **Miss** — structurally guaranteed by §1's cache-key participation, independent of `production_identity_checksum`'s own value |

## 12. Persisted-artifact audit (unchanged from the original round; read-only, no privileged content opened)

Carried forward verbatim — this correction added no new field to any
persisted-artifact-relevant constant beyond what was already anticipated
(the version-bump matrix, §13, still bumps the same four constants; the
reasons are refined, not the artifact-impact conclusion).

Zero tracked `.json`/`.jsonl` artifacts anywhere in the repository
(including gitignored paths on disk) are stamped with any of the four
affected schema-version strings. One gitignored, non-privileged artifact
exists and is already documented stale
(`artifacts/reference/g4_benchmark_audit/g4_benchmark_audit_log.jsonl`,
66 `reference-audit-record-v2` records — relied on its own module
docstring, not re-opened). One real, gitignored, genuinely privileged
artifact exists: `artifacts/privileged/reference/g4_benchmark_cache/`,
49 real files from the same G.4 run (confirmed by directory listing
only — **still not opened, not read, by this correction either**). Under
the version bumps below, all 49 become schema-incompatible and are
rejected via the cache's own existing `STALE_INCOMPATIBLE` disposition —
expected, non-blocking, regenerable by rerunning G.4, no migration
provided, exactly the same conclusion as the original round.

## 13. Proposed version-bump matrix (revised)

| Constant | Current | Proposed | Reason (revised) |
|---|---|---|---|
| `RESULT_SCHEMA_VERSION` | `reference-result-schema-v4` | `reference-result-schema-v5` | `ReferenceRunContext` gains `orchestration_substrate` + 2 checksum fields (§2); `ReferenceTaskResult` gains one new field, `producer_provenance: ReferenceResultProducerProvenance` (§3/§4) — a nested nested type, not independently versioned (mirrors `FullSuiteDiagnostic`/`CandidateSetEntry`'s existing precedent of participating in `RESULT_SCHEMA_VERSION` without their own constant) |
| `CACHE_KEY_SCHEMA_VERSION` | `reference-result-cache-key-v2` | `reference-result-cache-key-v3` | `ReferenceResultCacheKey` gains **two** fields (§5: `orchestration_substrate`, `production_identity_checksum`) — revised from the original round's one-field reason |
| `CACHE_ENTRY_SCHEMA_VERSION` | `reference-result-cache-entry-v2` | `reference-result-cache-entry-v3` | Depends on both `RESULT_SCHEMA_VERSION` and `CACHE_KEY_SCHEMA_VERSION`, unchanged reasoning from the original round |
| `AUDIT_RECORD_SCHEMA_VERSION` | `reference-audit-record-v3` | `reference-audit-record-v4` | `ReferenceAuditRecord` gains 9 fields (§9) — revised in count and shape from the original round's 3-field proposal (adds the explicit consuming/producing split and the two substrate fields) |
| Redacted/safe-report schema (`result_redaction.py`) | n/a (no independent constant) | n/a — tracks `RESULT_SCHEMA_VERSION` v5 | Unchanged from the original round; §8's allowlist is code-level only |
| `DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION`, `src/distributed/identity.py` types | Unchanged | **Unchanged** | Still reused as-is; this correction adds no field to either |
| **New**: `resolve_verified_manifest` (§3 step 1) | Does not exist | New public function, `src/distributed/provenance_manifest_lock.py` | No new schema-version constant of its own — a function addition, not a persisted-shape change; named here as a B.4B implementation dependency |
| **New**: `ReferenceResultProducerProvenance` (§3) | Does not exist | New nested type, `src/reference/result_schema.py`, participates in `RESULT_SCHEMA_VERSION` v5 | Owns `producer_provenance_checksum` as its own self-check field; no independent version constant, per the `FullSuiteDiagnostic` precedent cited above |

`EXECUTION_PROTOCOL_VERSION` determination is unchanged from the original
round (not bumped; the actual MEGB-02 wire-protocol identity lives on
`CandidateExecutionRequest`/`Result.protocol_version` in
`src/execution/protocol.py`/`wire.py`, untouched by any field this design
adds).

## 14. Required B.4B negative-test matrix (extended)

The 10 items from the original round, revised where the corrected design
changes what's being tested, plus the 11 new items this correction's
instruction requires:

1. Missing/dangling manifest checksum → §3 step 1/2 rejection.
2. Unadmitted or substituted worker → §3 step 3/4 rejection.
3. Mismatched production-identity projection (caller-supplied value
   disagrees with the derived one) → §3 step 7 rejection.
4. Mixed workers not sharing `parent_run_context_checksum` → rejected by
   the existing, reused `require_workers_belong_to_run` during manifest
   resolution.
5. Cross-run equivalent cache reuse (positive test: identical `key_digest`
   across two different producing runs) → §11 row 3.
6. Changed worker image/machine type cache invalidation (positive
   contrast test: differing `key_digest`) → §11 rows 4/5.
7. Stale pre-B.4 schema rejection (`reference-result-cache-key-v2`-stamped
   payload under v3 code) → `STALE_INCOMPATIBLE`.
8. Audit/cache/result disagreement (an audit record whose
   `production_identity_checksum` does not equal its accompanying
   result's) → reconciliation-failure test.
9. Safe-report leakage (structural allowlist test: raw
   `contributing_worker_context_checksums` absent from `redact_task_result`'s
   output; no `ProtectedOperationalMapping`-owned field name anywhere).
10. Raw GCP identifier rejection (defense-in-depth, mirroring
    `protected_mapping.py`'s pattern; largely already true by the sha256-hex
    format check).
11. **(new)** Distributed mode (`orchestration_substrate ==
    DISTRIBUTED_REFERENCE_ORCHESTRATOR`) with any single required
    provenance field missing (parametrized over each of
    `distributed_run_context_checksum`, `distributed_provenance_manifest_checksum`,
    `contributing_worker_context_checksums`, `production_identity_checksum`)
    → §1 invariant 2 rejection, one test per field.
12. **(new)** Local mode carrying any distributed field populated →
    §1 invariant 1 rejection.
13. **(new)** Local/distributed cache separation (positive test:
    identical hypothetical configuration, differing only in
    `orchestration_substrate` → different `key_digest`) → §11 row 10.
14. **(new)** Unknown worker checksum (already covered in spirit by item
    2, made explicit as its own parametrized case here per the
    correction's own itemization).
15. **(new)** Duplicate worker checksum in the caller-supplied tuple →
    §3 step 4 rejection.
16. **(new)** Substituted worker (a checksum resolving to a real worker
    from a *different* manifest than claimed) → §3 step 1's manifest
    resolution scoping rejection.
17. **(new)** Wrong-run worker (a checksum that would only resolve under
    a different run's manifest) → same as 16, distinct assertion.
18. **(new)** Contributor-set change with equivalent production identity
    (two different, disjoint `contributing_worker_context_checksums` sets
    that happen to share one `production_identity_checksum`, differing
    `contributing_worker_contexts_checksum`) → proves §3's "insufficiency"
    rationale directly, and confirms `contributing_worker_contexts_checksum`
    actually distinguishes the two.
19. **(new)** Cross-run cache hit preserving producer and consumer
    provenance (end-to-end: rebind a cached result from run A into
    consuming run B; assert `context == run_B`,
    `producer_provenance == <run A's original>` unchanged) → §6.2's
    central property.
20. **(new)** Mixed fresh/cache-hit 164-task aggregation (some tasks
    fresh under run B, some rebound cache hits originally produced under
    run A; assert the resulting `ReferenceBenchmarkResult` constructs
    successfully — the exact scenario §6.1 found broken pre-correction).
21. **(new)** Stale producer provenance (a cache entry whose stored
    `producer_provenance` fails its own self-checksum re-verification on
    load) → rejected via the cache's existing `CORRUPT` disposition,
    before `rebind_cached_result_to_consuming_context` is ever reached.
22. **(new)** Cache-hit audit falsely claiming fresh execution (assert
    `cache_disposition == VALID_HIT` audit records always have
    `producing_*` fields sourced from `producer_provenance`, never
    silently equal to `consuming_*` unless they were already equal, i.e.
    assert the audit builder never substitutes consumer identity into a
    producing field).
23. **(new)** Producer/consumer audit-field consistency (parametrized
    over every row of §9's illustrative combinations table, asserting the
    nullability rule holds exactly).

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
  — the calibration-side integration this design's §2/§3 pattern mirrors,
  and whose `src/reference/distributed_provenance_reconciliation.py`
  precedent this correction's §3 construction path extends.
- `docs/reference/version-registry.md` — current values for every
  constant in §13's version-bump matrix.
