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

**Amended twice further, in place, same convention**: a second round
(§1a, §5/§5a/§5b, §6.2, §9, §11) corrected a genuine internal
contradiction — the first round's own invariant 4 already claimed
local/distributed cache keys can never collide, while its invariant 3
simultaneously permitted a distributed session to serve a local-produced
cache hit — resolving it by prohibiting cross-substrate reuse
structurally and renaming the cache-key field to `production_substrate`
with explicit write/lookup ownership rules. A third round (§3a, §6.2
precondition 5) closed two remaining absences found during final
acceptance reconciliation: neither round stated *when*, relative to
cache lookup, a distributed `production_identity_checksum` is even
derivable (§3 as written was entirely post-hoc), and neither described
the *consuming* session's own manifest/provenance as independently
verified — only the producer's.

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
  producing" distinction), and simultaneously the substrate the session
  **requires** any evidence (fresh or cached) it consumes to have been
  produced under (§1a).
- `ReferenceResultCacheKey.production_substrate` — **renamed from the
  prior round's `orchestration_substrate`**, precisely to avoid the
  ambiguity this correction closes (§5 defines its ownership rules in
  full: producer-derived on write, consumer-required on lookup).
  Participates directly in `key_digest`'s hashed payload as an explicit,
  structural guarantee that a local key and a distributed key can never
  collide — not merely an emergent consequence of `None` never colliding
  with a real checksum.
- `ReferenceAuditRecord.consuming_orchestration_substrate` and
  `producing_orchestration_substrate` — both, retained for full
  attributability even though §1a now requires them to be equal on every
  valid record (§9).

### 1a. Cross-substrate reuse is prohibited (correction)

**This corrects a genuine internal contradiction in the prior round**:
that version's invariant 4 already claimed local/distributed cache keys
"can never collide," while its own invariant 3 simultaneously claimed a
distributed session "may legitimately serve a `LOCAL_...`-produced cache
hit" — two mutually incompatible statements. This correction resolves the
contradiction in favor of invariant 4's own structural guarantee, which
is the one this project's other checksum-identity mechanisms already
establish as the load-bearing one.

**Frozen rules, replacing the prior round's invariant 3 in full**:

- **Fresh execution requires `producer_provenance.substrate ==
  ReferenceRunContext.orchestration_substrate`** — trivially true by
  construction (producer and consumer are the same session), but stated
  as an explicit, checked invariant rather than an implicit consequence.
- **Cache reuse requires `producer_provenance.substrate` (of the stored
  entry) to equal the substrate the consumer requires evidence to have
  been produced under** — which is exactly `ReferenceRunContext.orchestration_substrate`
  of the consuming session performing the lookup (no separate,
  independently configurable "required substrate" knob is introduced;
  the consuming session's own declared substrate **is** its requirement).
- **`LOCAL_REFERENCE_ORCHESTRATOR` evidence cannot satisfy a
  `DISTRIBUTED_REFERENCE_ORCHESTRATOR` request**, and **distributed
  evidence cannot silently satisfy a local request** — enforced
  structurally, not merely by convention: because `production_substrate`
  (§5) participates in `key_digest`'s hashed payload, a lookup performed
  under one substrate computes a **different digest** than any entry
  stored under the other substrate. The two never occupy the same
  storage slot, so there is nothing to "find and then reject" — the
  entry is simply never located.
- **A substrate mismatch is a cache miss/incompatible entry, never a
  valid hit, and never silently rebound.** `rebind_cached_result_to_consuming_context`
  (§6.2) is only ever reached after a `VALID_HIT`, which by the digest
  argument above cannot occur across substrates — so no rebind-time
  substrate check is a rescue path; it is defense-in-depth against a
  hash-collision-class bug, not the primary enforcement mechanism (§6.2's
  tightened precondition list re-verifies this explicitly regardless).
- **`MEGB-03H.2C.3F` qualification may consume only distributed-produced
  evidence with verified distributed provenance** — a direct consequence
  of the rules above, stated as its own policy anchor: any H.2C.3F
  consuming session's `ReferenceRunContext.orchestration_substrate` must
  be `DISTRIBUTED_REFERENCE_ORCHESTRATOR`, which structurally excludes
  every `LOCAL_REFERENCE_ORCHESTRATOR`-produced cache entry from ever
  satisfying its lookups, by the same digest-disjointness argument.

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
3. **(Corrected — see §1a)** A task's own `producer_provenance.substrate`
   **must equal** the consuming `ReferenceRunContext.orchestration_substrate`
   for every valid result, fresh or cache-derived — cross-substrate reuse
   is prohibited, not merely "independent." **Recommended, not mandated,
   B.4B enhancement** (unaffected by this correction):
   `ReferenceBenchmarkResult` could expose a derived "producer substrates
   observed" set — now necessarily a singleton set for any valid
   aggregate, per this invariant, so its diagnostic value is narrower
   than the prior round envisioned, but still flagged as optional, not
   required.
4. **Cache separation**: `ReferenceResultCacheKey.production_substrate`
   entering the digest (§5) means a `LOCAL_REFERENCE_ORCHESTRATOR` cache
   key and a `DISTRIBUTED_REFERENCE_ORCHESTRATOR` cache key **can never
   collide** — this is now the **primary** enforcement mechanism for
   invariant 3 above (§1a), not a secondary, independent guarantee
   alongside a permitted cross-substrate hit path; there is no such path.
5. **Local-mode `None` semantics, preserved exactly**: for
   `LOCAL_REFERENCE_ORCHESTRATOR`, `production_identity_checksum` remains
   `None` in the cache key, preserving today's existing local cache
   behavior (two local executions with identical cache-key-relevant
   fields already hit each other, unchanged by this design) — `None` is
   valid and expected for local mode; it is only ever *insufficient as
   the sole discriminator*, which invariant 4's explicit
   `production_substrate` field resolves (§5 confirms local and
   distributed keys are disjoint even before any other field is
   compared).

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

### 3a. Prospective cache-key derivation before execution (correction)

**Gap this closes**: §3 as written describes `build_reference_result_producer_provenance`
entirely post-hoc — called with an already-known `contributing_worker_context_checksums`,
with no statement of *when* this happens relative to cache lookup. This
is correct for describing provenance **attached to a completed result**,
but a cache-first orchestrator (§6.1: `CachePolicy.CACHE_FIRST` consults
`self._cache.get(key)` before ever calling the evaluator) needs a
`ReferenceResultCacheKey` — and therefore a `production_identity_checksum`
— **before execution has happened**, when the "actual" contributor set
in the post-hoc sense does not yet exist. This section freezes how that
is possible without accepting a speculative or caller-asserted identity.

**The resolution: distinguish *assignment* from *execution*.** A
distributed coordinator's admission/leasing step (`AtomicWorkStore.acquire_lease`,
already accepted, B.2B.1) already binds a work item to a specific,
already-admitted worker **before that worker executes anything** — the
worker's own `WorkerExecutionContext` already exists in the manifest at
lease time; only the *candidate's own execution on it* is still pending.
This existing lease-time binding is exactly the "frozen contributor set"
this section needs — no new scheduling concept is introduced.

**Frozen sequence, distributed mode only** (local mode has no worker
set to assign or freeze at any point — `production_identity_checksum`
is `None` regardless of timing, so this entire section is vacuous for
`LOCAL_REFERENCE_ORCHESTRATOR`, stated explicitly to avoid implying
otherwise):

1. **The intended contributor/worker set is assigned and frozen before
   lookup.** The coordinator's lease/admission decision (already an
   accepted B.2B.1/B.2B.2 concept) fixes which worker(s)' `WorkerExecutionContext`
   checksum(s) will execute this task, before execution starts. This
   assignment is what "frozen" means here — not a new commitment
   mechanism, the existing lease.
2. **Its worker contexts are verified against the manifest.** The
   assigned checksum(s) are resolved via the same
   `resolve_worker_context(manifest, checksum)` call §3 step 3 already
   uses — proving the assignment names a real, admitted worker, not a
   caller-fabricated one, before any lookup is attempted.
3. **`AggregateProductionIdentityProjection` is derived from that frozen
   set.** The identical `aggregate_production_identity_for(manifest.run_context,
   assigned_workers)` call §3 step 5 already uses — the prospective and
   post-hoc paths share one derivation function; only the *timing* and
   the *source* of the worker set (assigned-but-not-yet-executed vs.
   actually-executed) differ.
4. **The resulting checksum forms the prospective cache key.** The
   `ReferenceResultCacheKey.production_identity_checksum` used for the
   lookup is exactly this projection's own `projection_checksum` — the
   same field, the same derivation, computed one step earlier in the
   task's lifecycle than §3's post-hoc description covers.
5. **Cache lookup occurs after contributor assignment but before candidate
   execution.** Concretely: `_execute_key_group` (§6.1) must compute the
   lookup key only after the coordinator's own lease/admission step has
   bound this task to specific worker(s) — never before (a pre-assignment
   lookup would have nothing real to derive a distributed
   `production_identity_checksum` from) and never skipped merely because
   assignment happened (that would silently fall back to executing
   without ever checking the cache).
6. **If assignment changes, the old lookup/key cannot be reused.** A
   lease expiry/reassignment (already an accepted B.2B.2/B.2B.3 concept —
   fault-conformance covers exactly this) that moves a task to a
   different worker before it completes invalidates the prospective key
   computed under step 4 — the orchestrator does not carry that stale key
   forward into a retry; it recomputes the prospective key fresh from the
   *new* assignment (steps 1–4 again) before attempting another lookup.
   No caching of the prospective key across a reassignment boundary.
7. **No speculative or caller-asserted production identity is accepted,
   prospectively or post-hoc.** The prospective path is not a relaxed or
   separate trust boundary — it uses the exact same
   `build_reference_result_producer_provenance`-family derivation (steps
   1–5 above mirror §3 steps 1/3/5/6 exactly) and the exact same
   auto-compute-or-reject discipline (§3 step 7). A caller cannot supply
   an un-derived `production_identity_checksum` for a lookup any more
   than for a write.
8. **If the contributor set cannot be frozen prospectively, execution
   must not claim a cache hit.** If the scheduling policy in effect
   cannot yet name a specific assigned worker for a task (e.g. an
   open-pool policy where any of several idle workers may pick up the
   work at execution time, not at admission time), no prospective key can
   be derived — the orchestrator must skip the cache lookup entirely for
   that task, falling through to fresh execution, mirroring the existing
   `CacheDisposition.BYPASSED_BY_POLICY` treatment already established
   for a deliberate policy-level cache bypass (§6.1's own citation of
   that mechanism). It must never substitute a placeholder, a
   session-level default, or any value not derived from a real,
   verified, frozen assignment.

This preserves cache-first candidate execution exactly as already
designed (§6.1's `CACHE_FIRST` policy is unchanged) while never
pretending production identity is knowable before scheduling has
actually committed to it.

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

- `production_substrate: str` — **renamed from the prior round's
  `orchestration_substrate`**, precisely because that name was ambiguous
  between "the consuming session's substrate" and "the substrate that
  actually produced this result" — the two are now required to agree for
  any valid record (§1a), but the cache-key field's own *ownership*
  differs by whether the key is being constructed for a **write** or a
  **lookup**, which the old name did not distinguish. Participates
  directly in `key_digest`'s hashed payload.
- `production_identity_checksum: str | None` — unchanged from the
  original design, `AggregateProductionIdentityProjection.projection_checksum`.

### 5a. `production_substrate` ownership rules (correction)

- **On cache write** (`cache_key_for`, called from
  `ReferenceOrchestrator._accept_valid_result` for a freshly executed,
  `VALID` result): `production_substrate` is derived from
  **`task_result.producer_provenance.substrate`** — never from
  `task_result.context.orchestration_substrate` directly. For a fresh
  execution the two are already required to be equal (§1a), so this is
  not a behavior change, but it fixes the *conceptually correct source*:
  the cache key must record what substrate actually produced the bytes
  being cached, and `producer_provenance` is the field that answers that
  question by definition. Reading from `context` instead would silently
  become wrong the moment any future code path violated §1a's equality
  invariant without this module also being updated — reading from
  `producer_provenance` cannot drift that way, since it is the same field
  §1a's invariant is stated *about*.
- **On cache lookup** (`ReferenceOrchestrator._execute_key_group`,
  constructing the key to call `self._cache.get(key)`): `production_substrate`
  is derived from **the substrate under which the consumer requires the
  result to have been produced** — which is exactly the consuming
  session's own `ReferenceRunContext.orchestration_substrate` (§1a: no
  separate, independently configurable "required substrate" parameter is
  introduced; the consuming session's declared substrate **is** its
  requirement, for both fresh execution and cache reuse, uniformly).
- **On a valid hit**: `rebind_cached_result_to_consuming_context` (§6.2)
  defensively re-verifies that the **expected** key's `production_substrate`
  (computed from the consuming session, as above), the **stored** key's
  `production_substrate` (persisted in the cache entry, from write time),
  and the resolved entry's own `producer_provenance.substrate` **all
  three agree** — belt-and-suspenders against a hash-collision-class bug,
  since the digest-disjointness argument in §1a already makes a
  disagreement structurally unreachable in the absence of one.
- **`ReferenceRunContext.orchestration_substrate` is unrenamed and
  unchanged**: it remains exactly the consuming session's own substrate
  (§2), never the cache key's field. The two names are now
  deliberately distinct (`orchestration_substrate` vs.
  `production_substrate`) specifically so a reader can never conflate
  "which session is asking" with "which substrate a specific piece of
  cached evidence was produced under."

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
§1a's rules only strengthen the local/distributed separation guarantee
from "permitted but rare" (the prior round's now-corrected framing) to
"structurally prohibited," and do not change any other cache-reuse
property.

### 5b. Local semantics, confirmed explicitly

- `LOCAL_REFERENCE_ORCHESTRATOR` `producer_provenance` always has an
  **empty** `contributing_worker_context_checksums` tuple, `contributing_worker_count
  == 0`, `contributing_worker_contexts_checksum is None`, and both
  `distributed_run_context_checksum`/`distributed_provenance_manifest_checksum`/
  `production_identity_checksum` are `None` — restated from §1 invariant
  1, confirmed here as the exact local-mode field shape this section's
  cache-key derivation reads from.
- Local cache keys use `production_substrate = "LOCAL_REFERENCE_ORCHESTRATOR"`
  paired with `production_identity_checksum = None` — the
  "local-compatible production-identity representation" is `None` itself,
  not a distinct sentinel checksum; this is unchanged from the original
  design's §1 invariant 5 and preserves today's existing local cache
  behavior exactly.
- Distributed cache keys **require** a non-`None`, verified
  `production_identity_checksum` — per §1 invariant 2, a distributed
  `producer_provenance` with a missing `production_identity_checksum` is
  a construction-time rejection, so no distributed cache key can ever be
  constructed with `production_identity_checksum = None` in the first
  place.
- **Local and distributed keys are disjoint even before comparing any
  other field**: `production_substrate` is itself one of the values
  hashed into `key_digest` (alongside `task_id`, `candidate_sha256`,
  `production_identity_checksum`, and every pre-existing cache-key
  field), so two keys differing only in `production_substrate` already
  hash to different digests — disjointness does not depend on, and is
  not weakened by, any coincidental agreement or disagreement among the
  remaining fields.

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

**Tightened precondition list (correction)** — the prior round's step 1
treated cross-field agreement as "already guaranteed... a redundant,
cheap defensive assertion." This correction replaces that single
hand-waved step with an explicit, ordered precondition list the function
must actually verify before constructing anything, each item independent
and separately checked (never inferred from "a `VALID_HIT` occurred, so
it must be fine"):

1. **Verify cache-entry and result self-consistency.** Re-runs the same
   structural/checksum validation `task_result_from_dict` already applies
   on every deserialization (`ReferenceTaskResult.__post_init__`,
   `ReferenceResultProducerProvenance.__post_init__`'s own
   `producer_provenance_checksum` re-verification) — confirms
   `cached_result` itself is not corrupted before anything is derived
   from it.
2. **Verify the expected key equals the stored key.** Computes the
   expected `ReferenceResultCacheKey` from `consuming_context` (using
   `consuming_context.orchestration_substrate` as the required
   `production_substrate`, §5a) and compares it field-for-field against
   the `ReferenceResultCacheKey` actually stored alongside
   `cached_result` in the cache entry — not merely trusting that the
   lookup which found this entry must have used a matching key.
3. **Verify `producer_provenance.substrate` equals the required
   production substrate.** An explicit, standalone check — even though
   step 2's key equality already implies it (§5a), stated and checked
   independently as defense-in-depth per §1a.
4. **Verify production-identity checksum equality.** Confirms
   `cached_result.producer_provenance.production_identity_checksum`
   equals the expected key's own `production_identity_checksum` (both
   `None`, for a local hit, or both the same real checksum, for a
   distributed hit) — again independently of step 2's aggregate key
   comparison.
5. **Verify task, candidate, reference-case, dataset, partition, oracle,
   comparison, evaluator, protocol, execution-profile, and
   manifest/scientific identity, per the existing cache-key and
   aggregation rules.** Re-checks every field
   `ReferenceResultCacheKey`/`_require_shared_run_context` already
   validate (`task_id`, `candidate_sha256`, `reference_case_checksum`,
   `dataset_version`/`dataset_checksum`, `partition_version`,
   `task_manifest_checksum`, `oracle_version`,
   `comparison_profile_version`, `evaluator_version`,
   `execution_profile_id`, `execution_protocol_version`) against
   `consuming_context`/the task-level fields explicitly, rather than
   relying on "the lookup already used these fields to compute the key
   that found this entry."

   **Producer/consumer manifest verification, clarified explicitly
   (correction)**:
   - **Producer manifest integrity and producer provenance are
     independently verified** — already true, at cache-*write* time, via
     §3's 7-step `build_reference_result_producer_provenance` path
     (`resolve_verified_manifest`, checksum cross-checks,
     `resolve_worker_context` per worker). This precondition does not
     redo that verification; it relies on `producer_provenance`'s own
     self-checksum (precondition 1) as proof it already happened and was
     not tampered with since.
   - **Consumer manifest integrity and current-run provenance are
     independently verified** — a genuinely new requirement this
     correction adds: for a `DISTRIBUTED_REFERENCE_ORCHESTRATOR`
     consuming session, `consuming_context.distributed_run_context_checksum`/
     `distributed_provenance_manifest_checksum` must themselves have been
     verified against a real, lock-validated
     `DistributedProvenanceManifest` — via a new function,
     `verify_consuming_run_context_provenance(context, lock)`, added
     alongside `build_reference_result_producer_provenance` in
     `src/reference/distributed_provenance_reconciliation.py` (same
     two-checksum-comparison shape as §3 steps 1–2, applied to the
     *consuming* context's own claimed run/manifest rather than a
     producer's). Called once, at the point the consuming session's own
     `ReferenceRunContext` is first constructed for a distributed run —
     not repeated per task, since it is a session-level fact (§2) —
     **before** any task in that session reaches
     `rebind_cached_result_to_consuming_context` at all. This
     precondition therefore does not re-run that verification either; it
     depends on it having already happened, exactly symmetrically with
     how it depends on the producer side already having happened.
   - **Scientific/cache-key identity fields must be compatible** — this
     precondition's own primary check, restated: the fields listed above
     must match between `cached_result` and `consuming_context`.
   - **Producer and consumer manifest checksums need not be equal for
     allowed cross-run reuse** — unchanged from the prior round: the
     **consuming** manifest identity
     (`consuming_context.distributed_provenance_manifest_checksum`, a
     session-level fact, §2) is explicitly permitted to differ from the
     cached entry's own **producing** manifest identity — that is exactly
     the cross-run reuse property §5/§11 require; this step never
     compares those two, only the fields actually listed above.
   - **Both checksums remain separately attributable in audit** —
     `consuming_distributed_provenance_manifest_checksum`/
     `producing_distributed_provenance_manifest_checksum` (§9), unchanged.
   - **Equality is required only where an existing scientific identity
     rule genuinely requires it** — stated as the general principle this
     precondition follows: the fields this step actually compares are
     exactly, and only, the fields `ReferenceResultCacheKey`/
     `_require_shared_run_context` already treat as outcome-affecting
     identity; manifest/run identity is deliberately excluded from that
     set (§5), so it is correctly excluded from this comparison too — no
     field is compared here "for extra safety" beyond what an existing
     rule already requires.
6. **Reject stale or unverifiable producer provenance.** If step 1's
   self-consistency check fails, or if `producer_provenance` is stamped
   under a schema version this code does not implement, the function
   raises rather than proceeding — the caller (`_execute_key_group`)
   never receives a rebound result in this case; the cache's own
   `CORRUPT`/`STALE_INCOMPATIBLE` disposition should already have
   prevented `VALID_HIT` from being reported in the first place, so
   reaching this step with a failure indicates a defect elsewhere, not a
   normal code path — still checked, never assumed unreachable.

Only after all six preconditions pass does construction proceed:

7. Returns a **new** `ReferenceTaskResult` with `context = consuming_context`
   (satisfying "the aggregator receives a coherent current scientific/run
   context") and `producer_provenance = cached_result.producer_provenance`
   **preserved byte-for-byte** — the cached entry's original producing
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
   producer-sourced regardless of who is now consuming them. **Only the
   consuming `ReferenceRunContext` is replaced** — every other field,
   including `producer_provenance`, is copy-constructed unmodified.
8. **Recompute any enclosing result checksum deterministically.**
   `ReferenceTaskResult` carries no top-level self-checksum field today
   (confirmed by direct inspection of `result_schema.py` — unlike
   `ReferenceResultCacheKey`/`ManifestLockEntry`/every
   `src/distributed/identity.py` type), so there is nothing at that level
   to recompute. `producer_provenance.producer_provenance_checksum` is
   unaffected by rebinding (`producer_provenance` itself is never
   modified, so its own checksum stays valid and correct, not stale). The
   on-disk cache entry's own `entry_checksum`
   (`src/reference/reference_cache.py::_entry_checksum`) is likewise
   never touched, because item 9 below means it is never recomputed
   against anything — the rebound object never reaches that code path.
   **Rule for B.4B, if a future correction adds a top-level
   `ReferenceTaskResult` checksum**: it must be recomputed deterministically
   over the *rebound* object's actual field values (not carried forward
   from `cached_result`'s own, now-stale, checksum) — the same
   auto-compute-or-reject discipline every other checksum in this
   codebase already follows.
9. **Never writes the rebound consumption view back over the original
   producer cache entry.** The return value of
   `rebind_cached_result_to_consuming_context` is a transient, in-memory
   object only — it is never passed to `self._cache.put(...)`. The cache
   is written to exclusively from `_accept_valid_result`'s own fresh-execution
   path; `_execute_key_group`'s `VALID_HIT` branch only ever *reads* the
   cache, both before and after this correction.

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
- *Cross-substrate reuse is prohibited*: precondition 3 of §6.2's ordered
  list independently confirms `producer_provenance.substrate` equals the
  required production substrate — and, per §1a, this can never actually
  fail in the absence of a bug, since a cross-substrate lookup never
  reaches `VALID_HIT` in the first place (different `key_digest`).
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
  stale, never silently rebound*: **corrected** — the prior round claimed
  `rebind_cached_result_to_consuming_context` performs *no*
  re-verification and relies entirely on deserialization-time checks
  upstream. This correction's §6.2 precondition list (items 1 and 6) now
  has the function **itself** re-verify self-consistency before
  proceeding, in addition to (not instead of) the upstream
  `ReferenceResultProducerProvenance.__post_init__`/`task_result_from_dict`
  checks, which still provide the first line of defense (a cache entry
  whose stored `producer_provenance` fails its own self-check —
  corrupted, tampered, or stamped under a stale schema version — is
  rejected by the cache's own existing `CORRUPT`/`STALE_INCOMPATIBLE`
  disposition before `VALID_HIT` is ever reported at all). Belt-and-suspenders,
  not redundant waste: the two checks run in different components
  (`ReferenceResultCache` vs. the orchestrator's own rebind step), so a
  defect in one does not silently disable the other.

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

**Five invariants for a valid record, stated explicitly (correction — new)**:

1. `consuming_distributed_run_context_checksum`/`consuming_distributed_provenance_manifest_checksum`
   **may differ** from
   `producing_distributed_run_context_checksum`/`producing_distributed_provenance_manifest_checksum`
   — this is the entire point of the producer/consumer split (§6), and is
   expected, not anomalous, whenever a cache hit reuses evidence from a
   different historical distributed run.
2. `consuming_orchestration_substrate` **must equal**
   `producing_orchestration_substrate` on every valid record — §1a's
   cross-substrate prohibition, restated as an audit-level invariant.
   There is no valid record with these two fields disagreeing; a
   disagreement in stored data indicates corruption or a defect
   upstream, not a legitimate cross-substrate scenario.
3. **One shared `production_identity_checksum` is valid precisely because
   equality is required** — since invariant 2 guarantees the producing
   and consuming substrates always match, there is never a scenario
   requiring two different `production_identity_checksum` values (a
   "consuming" one and a "producing" one) on the same record; the single
   field is sufficient by construction, not by omission.
4. `contributing_worker_contexts_checksum`/`contributing_worker_count`
   **remain the producer's own values, unchanged by rebinding** (§6.2
   precondition 7) — they never reflect anything about the consuming
   session's own (possibly nonexistent) workers.
5. **`cache_disposition == VALID_HIT` is itself proof that no worker of
   the current, consuming session executed this item** — a `VALID_HIT`
   audit record's `producing_*` fields describe evidence that already
   existed before this invocation began; `cache_disposition` and the
   `producing_*` fields together give a reader everything needed to
   confirm this without cross-referencing anything else.

**Illustrative combinations** (not exhaustive — the general rule and the
five invariants above are authoritative; **the prior round's "distributed
session, local-produced (legacy) entry" row is removed** — per §1a that
scenario is a cache **miss**, not a hit, so no audit record with
disagreeing `consuming_*`/`producing_*` substrates can ever exist):

| Scenario | `consuming_orchestration_substrate` | `producing_orchestration_substrate` | `production_identity_checksum` |
|---|---|---|---|
| Fresh execution, local session | `LOCAL_...` | `LOCAL_...` (equal — producer = consumer) | `None` |
| Fresh execution, distributed session | `DISTRIBUTED_...` | `DISTRIBUTED_...` (equal — producer = consumer) | Present |
| Cache hit, local session, local-produced entry | `LOCAL_...` | `LOCAL_...` (equal) | `None` |
| Cache hit, distributed session, distributed-produced entry from a **different** historical run | `DISTRIBUTED_...` | `DISTRIBUTED_...` (equal; the *checksums*, not the substrate, differ from consuming — see invariant 1) | Present, equal to the producing run's own |
| Cache hit, distributed session, distributed-produced entry from **this same** run (a retry-then-reused-within-run case) | `DISTRIBUTED_...` | `DISTRIBUTED_...` (equal; values also equal consuming) | Present |

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

Revised to reflect §5's `production_substrate` (renamed from the prior
round's `orchestration_substrate`) participating in the digest directly,
alongside `production_identity_checksum`, and §1a's explicit
cross-substrate prohibition.

| # | Scenario | `production_substrate` | `production_identity_checksum` | Cache outcome |
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
| 10a (**corrected**) | Consuming session requires `LOCAL_REFERENCE_ORCHESTRATOR` evidence; the only matching-otherwise entry on disk was produced under `DISTRIBUTED_REFERENCE_ORCHESTRATOR` | `LOCAL_REFERENCE_ORCHESTRATOR` (required) vs. `DISTRIBUTED_REFERENCE_ORCHESTRATOR` (stored) — differ | Moot — `production_substrate` alone already differs | **Miss/incompatible** — distributed evidence cannot silently satisfy a local request (§1a); different `key_digest`, the entry is never located |
| 10b (**corrected**) | Consuming session requires `DISTRIBUTED_REFERENCE_ORCHESTRATOR` evidence (e.g. `MEGB-03H.2C.3F` qualification); the only matching-otherwise entry on disk was produced under `LOCAL_REFERENCE_ORCHESTRATOR` | `DISTRIBUTED_REFERENCE_ORCHESTRATOR` (required) vs. `LOCAL_REFERENCE_ORCHESTRATOR` (stored) — differ | Moot | **Miss/incompatible** — local evidence cannot satisfy a distributed request (§1a); this is the specific case that makes `MEGB-03H.2C.3F` qualification structurally unable to silently accept local-only evidence |

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
| `CACHE_KEY_SCHEMA_VERSION` | `reference-result-cache-key-v2` | `reference-result-cache-key-v3` | `ReferenceResultCacheKey` gains **two** fields (§5: `production_substrate` — renamed from this correction's own prior-round `orchestration_substrate` naming — and `production_identity_checksum`) — field count unchanged from the immediately prior round, name corrected |
| `CACHE_ENTRY_SCHEMA_VERSION` | `reference-result-cache-entry-v2` | `reference-result-cache-entry-v3` | Depends on both `RESULT_SCHEMA_VERSION` and `CACHE_KEY_SCHEMA_VERSION`, unchanged reasoning from the original round |
| `AUDIT_RECORD_SCHEMA_VERSION` | `reference-audit-record-v3` | `reference-audit-record-v4` | `ReferenceAuditRecord` gains 9 fields (§9) — revised in count and shape from the original round's 3-field proposal (adds the explicit consuming/producing split and the two substrate fields) |
| Redacted/safe-report schema (`result_redaction.py`) | n/a (no independent constant) | n/a — tracks `RESULT_SCHEMA_VERSION` v5 | Unchanged from the original round; §8's allowlist is code-level only |
| `DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION`, `src/distributed/identity.py` types | Unchanged | **Unchanged** | Still reused as-is; this correction adds no field to either |
| **New**: `resolve_verified_manifest` (§3 step 1) | Does not exist | New public function, `src/distributed/provenance_manifest_lock.py` | No new schema-version constant of its own — a function addition, not a persisted-shape change; named here as a B.4B implementation dependency |
| **New** (this correction): `verify_consuming_run_context_provenance` (§6.2 precondition 5) | Does not exist | New function, `src/reference/distributed_provenance_reconciliation.py` | No new schema-version constant — a function addition, verifying the *consuming* session's own claimed distributed run/manifest identity against a real lock-validated manifest, symmetric with `build_reference_result_producer_provenance`'s existing verification of the *producer* side |
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
    `production_substrate` → different `key_digest`) → §11 rows 10a/10b.
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
24. **(this correction, new)** Local-requiring consumer against a
    distributed-produced entry (§11 row 10a): construct a
    `LOCAL_REFERENCE_ORCHESTRATOR` consuming session and a real, otherwise
    field-identical `DISTRIBUTED_REFERENCE_ORCHESTRATOR`-produced cache
    entry; assert the lookup returns `MISS` (never `VALID_HIT`, and never
    a `CORRUPT`/rejected-after-found disposition — it must not be located
    at all).
25. **(this correction, new)** Distributed-requiring consumer against a
    local-produced entry (§11 row 10b, the `MEGB-03H.2C.3F`-relevant
    direction): same shape as item 24, substrates reversed; assert
    `MISS`. Directly demonstrates "local evidence cannot silently satisfy
    a distributed request."
26. **(this correction, new)** `production_substrate` write-time
    derivation source (§5a): construct a `ReferenceTaskResult` whose
    `context.orchestration_substrate` and `producer_provenance.substrate`
    are (artificially, for test purposes) different; assert
    `cache_key_for` raises rather than silently choosing one — proves the
    cache-key builder does not read from `context` as a fallback.
27. **(this correction, new)** Rebind precondition 2 (expected key equals
    stored key): corrupt/mutate a stored cache entry's persisted
    `ReferenceResultCacheKey` (in isolation from `task_result` itself, so
    item 1's self-consistency check alone would not catch it) so it no
    longer matches what a fresh `cache_key_for(cached_result)`
    recomputation would produce; assert
    `rebind_cached_result_to_consuming_context` rejects it.
28. **(this correction, new)** Rebind precondition 5 (full scientific
    identity re-verification): construct a `consuming_context` that
    differs from a cached entry's own context in a field the cache key
    *does* cover (e.g. `execution_protocol_version`) without going
    through the cache's own lookup path (a direct unit-level call to
    `rebind_cached_result_to_consuming_context`); assert rejection —
    proves the function does not merely trust "a `VALID_HIT` occurred
    upstream."
29. **(this correction, new)** `MEGB-03H.2C.3F` distributed-evidence-only
    policy (§1a): an end-to-end-shaped test asserting that a
    `DISTRIBUTED_REFERENCE_ORCHESTRATOR` consuming session can never
    construct a `ReferenceBenchmarkResult` containing any task result
    whose `producer_provenance.substrate` is
    `LOCAL_REFERENCE_ORCHESTRATOR` — either because no such cache hit is
    ever reachable (items 24/25) or, defensively, via an explicit
    aggregate-level assertion if B.4B chooses to add one.
30. **(this correction, new)** Prospective key equals post-hoc key for an
    unretried task (§3a): execute a task end-to-end under a single,
    unchanged worker assignment; assert the prospective
    `production_identity_checksum` computed before execution (§3a steps
    1–4) equals the post-hoc one `build_reference_result_producer_provenance`
    derives after execution (§3 steps 5–6) — proves the two derivation
    paths agree when nothing changes between them.
31. **(this correction, new)** Prospective key invalidated by
    reassignment (§3a step 6): compute a prospective key under an initial
    lease/assignment, then force a lease expiry/reassignment to a
    different (but configuration-equivalent) worker before completion;
    assert the orchestrator does not reuse the original prospective
    lookup result for the eventual cache write — the write's own key is
    recomputed fresh from the *new* assignment.
32. **(this correction, new)** Cache lookup skipped, not faked, when
    assignment cannot be frozen (§3a step 8): under a scheduling policy
    that cannot yet name a specific worker for a task, assert the
    orchestrator records `CacheDisposition.BYPASSED_BY_POLICY` (or
    proceeds directly to fresh execution) rather than constructing any
    `ReferenceResultCacheKey` with a placeholder or fabricated
    `production_identity_checksum`.
33. **(this correction, new)** Consumer manifest/provenance independently
    verified (§6.2 precondition 5): construct a `DISTRIBUTED_REFERENCE_ORCHESTRATOR`
    `ReferenceRunContext` whose claimed `distributed_run_context_checksum`/
    `distributed_provenance_manifest_checksum` do not resolve against any
    real, lock-validated manifest; assert
    `verify_consuming_run_context_provenance` rejects it — independent of,
    and using a different code path than, the producer-side verification
    §3 already tests.

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
