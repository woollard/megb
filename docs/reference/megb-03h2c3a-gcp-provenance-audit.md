# MEGB-03H.2C.3A — GCP Distributed-Execution Provenance/Schema-Gap Audit

**Status: read-only audit. No accepted schema was modified in producing
this document.** Mirrors `megb-03h2c2a-collector-provenance-audit.md`'s
own read-only-determination pattern, applied to the distributed-execution
provenance concepts the "Approved MEGB-03H.2C.3 Planning Amendment"
requires this checkpoint to audit.

**Corrected after initial review** (this remains a read-only audit; no
schema was modified in producing the correction either): two changes
from the original version of this document. **First**, the gate this
audit's findings impose can no longer be deferred only to MEGB-03H.2C.3F
— MEGB-03H.2C.3D itself produces empirical distributed-qualification
evidence (timing, telemetry, recovery, ordering, equivalence
conclusions) whose interpretation depends on the execution environment
that produced it, so **no H.2C.3D qualification run may begin until the
required distributed-execution provenance schema is implemented,
versioned, tested, and persisted** (§"Revised blocking precondition"
below). **Second**, MEGB-03H.2C.3B is decomposed into two separately
gated internal checkpoints — **H.2C.3B.1** (this schema/identity design,
with tests) and **H.2C.3B.2** (provider-neutral orchestration interfaces
and offline synthetic tests, which may proceed once H.2C.3B.1's schema
exists for the interfaces to be built against). The concept list is also
expanded from 14 to 16 items, matching the more granular set the
correcting authorization named.

## Method

For each concept the amendment names, this audit inspects the currently
accepted schemas — `src/execution/protocol.py`
(`CandidateExecutionResult`), `src/reference/result_schema.py`
(`ReferenceRunContext`), `src/reference/cache_key.py`
(`ReferenceResultCacheKey`), `src/reference/reference_audit.py`
(`ReferenceAuditRecord`), and `src/reference/calibration_schema.py`
(`CalibrationRunContext`, `CalibrationInvocationRecord`,
`HostRuntimeContext`, `TelemetryCollectionPolicy`,
`CollectorMethodProvenance`) — and classifies whether each concept can
already be represented, and if not, whether the gap is outcome-affecting.
No field was added, removed, or renamed anywhere in this pass.

## Classification legend

- **Persisted/bound** — a field already exists and is bound into a
  self-checksum (tampering or omission is detectable).
- **Persisted/label** — a field already exists that can carry this
  concept as a free-form version/identity string, even though it was not
  designed with a distributed-execution provider in mind.
- **Audit-only** — worth recording for debugging/operational history,
  but its absence does not change how a downstream consumer should
  interpret a measurement's quality, validity, or scientific meaning.
- **Missing/benign** — does not exist, and its absence would not change
  any interpretation even if it did exist.
- **Missing/outcome-affecting** — does not exist, and its absence means
  a scientifically-relevant provenance dimension could differ across
  records with no way to detect or account for it.

## Concept-by-concept audit (revised: 16 concepts)

| # | Concept | Classification | Where (if persisted) | Rationale |
|---|---|---|---|---|
| 1 | Environment class and logical environment identity (personal-bootstrap vs. company-playground, plus a distinct logical run-scoped identity) | **Missing/outcome-affecting** | — | No field anywhere distinguishes which environment produced a record. Without it, a personal-bootstrap synthetic result could be silently indistinguishable from a company-playground scientific one at the schema level — exactly the failure mode threat #8/#9 in `gcp-distributed-execution-threat-model.md` describe. This project already has the analogous concept at the *diagnostic-report* level (`H2C2BQualificationReport.qualifying`, `run_identity`'s `-diagnostic-` tagging) but nothing equivalent exists in the *persisted calibration schema*. |
| 2 | Cloud provider | **Missing/outcome-affecting** | — | H.2C.2B itself empirically proved provider/host materially changes achievable telemetry quality (macOS/Docker Desktop → `BOUNDARY_ONLY` only) and overhead (70–130× the frozen gate). `HostRuntimeContext`'s existing OS/kernel fields describe *symptoms* consistent with a given provider but do not name it directly. |
| 3 | Region and zone | **Missing/outcome-affecting for timing only** | — | This project already treats per-invocation timing as host-dependent (the `0.418s`/invocation baseline, the H.1 concurrency-aware projection formula). Region/zone is a proxy for underlying hardware/network characteristics affecting *timing*, not *correctness*/*value* measurements. |
| 4 | Machine type and CPU architecture | **Partially persisted; specific machine type missing/outcome-affecting for timing** | `HostRuntimeContext.architecture` (coarse CPU family, e.g. `x86_64`/`arm64`) | The coarse architecture family is covered. The *specific* GCP machine type/shape (e.g. `n2-standard-4` vs. `c2-standard-8`) is not — different shapes have different CPU generations/core counts/memory bandwidth, affecting timing the same way region/zone does. |
| 5 | Spot versus On-Demand provisioning class | **Missing/outcome-affecting** | — | A Spot-preempted-and-retried invocation may have a materially different resource/timing profile than an uninterrupted On-Demand one. The existing `TelemetryUnavailableReason`/`WorkItemDisposition` taxonomies distinguish infrastructure retry generally but not *why* — a real interpretability gap. |
| 6 | Worker VM/image content identity (the outer VM/boot image, distinct from the runner container image) | **Missing/outcome-affecting** | — | A genuinely new concept: today's schema tracks only `runner_image_digest`. The worker VM's own boot/base image determines the Docker daemon version, cgroup driver, and kernel — all proven materially relevant to telemetry quality/overhead by H.2C.2B. |
| 7 | Worker implementation/version (the per-VM worker process code) | **Missing/outcome-affecting** | — | Distinct from #6 (image content) and #9 (fleet controller) — the worker *process*'s own code version determines exactly how it drives Docker, resolves telemetry collectors, and confirms terminal state (the H.2C.2A/2B-established logic). A worker-process bug or version drift changes measured outcomes independent of the VM image or fleet controller. |
| 8 | Coordinator implementation/version | **Missing/outcome-affecting** | — | The execution-plane coordinator's own admission/reconciliation logic version affects retry/lease/ordering guarantees a downstream consumer relies on to trust a trace's completeness — distinct from the worker's own version (#7) and the fleet controller's (#9). |
| 9 | Worker-fleet implementation/version (the MIG/fleet-controller layer) | **Missing/outcome-affecting** | — | Mirrors the already-accepted precedent of `backend_id`/`backend_version` — the fleet-controller identity is relevant to interpreting Spot-recovery/replacement guarantees under a specific implementation, distinct from the coordinator (#8) and worker process (#7). |
| 10 | Queue implementation/version (Pub/Sub or otherwise) | **Missing/benign** | — | The calibration schema's own reconciliation (`reconcile_task_evaluation`, content-checksum-bound contributor sets) is already robust to duplicate/out-of-order delivery from any admission mechanism. Useful operational/audit value; not required for scientific validity. |
| 11 | Object-store implementation/version | **Missing/benign** | — | Same reasoning as #10 — `CalibrationTraceStore`'s durability/checksum discipline is storage-backend-agnostic by design. |
| 12 | Runner-image digest | **Persisted/bound** | `CandidateExecutionResult.runner_image_digest` | Already exists, already content-addressed, already flows through the execution→calibration adapter chain. No gap. |
| 13 | Network/isolation policy identity (the specific `--network none`/capability-drop/mount configuration in force) | **Missing/outcome-affecting** | — | MEGB-02's isolation flags are currently a fixed constant in `docker_backend.py`'s `_build_docker_run_command`, never independently identified per-record. A future accidental flag drift (e.g. a Terraform/worker-image change that weakens a flag) would be undetectable from the calibration record alone without an explicit policy identity to check against the frozen, accepted baseline. |
| 14 | Telemetry policy and host/runtime identity | **Persisted/bound** | `TelemetryCollectionPolicy` + `HostRuntimeContext` (run-level, embedded in `CalibrationRunContext`), `CollectorMethodProvenance` (per-metric, embedded in `CalibrationInvocationRecord`) | The strongest-covered concept in this entire audit — exactly the subject of the H.2C.2A provenance/schema correction and its terminal-state-proof audit. No gap; already anticipates method/quality/disposition varying by host. Extended here only to note it must also carry the new #2–#6/#13 fields (see design table below), not redesigned. |
| 15 | Retry/lease policy identity (Pub/Sub lease duration, retry-count ceiling, dead-letter threshold) | **Missing/outcome-affecting** | — | The existing `RETRY_EXHAUSTED`/3-consecutive-failure circuit breaker is a *behavior*, not an *identified policy* — two runs under different lease/retry configurations could show different completeness/duplication characteristics with no recorded way to distinguish which configuration produced a given trace. |
| 16 | Checksum-algorithm version (for any new content-bound field this correction adds) | **Missing/benign today; becomes outcome-affecting the moment #1–#15 are implemented** | — | Every existing self-checksummed type in this project (`HostRuntimeContext`, `TelemetryCollectionPolicy`, `CollectorMethodProvenance`, etc.) computes its checksum via a fixed, implicit SHA-256-over-canonical-JSON algorithm with no separate algorithm-version label of its own — a pre-existing, already-reported gap (see `docs/reference/version-registry.md`'s own `H5StagingIdentity.identity_checksum()` "reported gap, not silently versioned" precedent). H.2C.3B.1 must not repeat that gap for any *new* checksummed type it introduces. |

**Not part of this numbered list, by design**: managed-model identity,
endpoint/protocol version, region, decoding configuration, and model-
provider provenance remain **owned by MEGB-03H.2C.3G**, not this audit
or H.2C.3B.1. This document requires only that **the generation-plane
schema boundary be reserved now** — i.e., H.2C.3B.1's own type design
must not use a name, field, or namespace that a future generation-
provenance schema would need, and must not fold any candidate-generation
concept into the calibration schema this audit inspects. No generation-
provenance type is designed, named, or stubbed out in this pass.

## Summary

| Classification | Count | Concepts |
|---|---|---|
| Persisted/bound | 2 | #12 runner-image digest, #14 telemetry policy/host-runtime identity |
| Missing/benign (today) | 3 | #10 queue implementation/version, #11 object-store implementation/version, #16 checksum-algorithm version (becomes outcome-affecting once new checksummed types exist) |
| Missing/outcome-affecting | 11 | #1 environment class/identity, #2 cloud provider, #3 region/zone (timing-scoped), #4 machine type (timing-scoped), #5 Spot/On-Demand class, #6 worker VM/image identity, #7 worker implementation/version, #8 coordinator implementation/version, #9 worker-fleet implementation/version, #13 network/isolation policy identity, #15 retry/lease policy identity |

(Execution-backend implementation/version, previously listed separately
in this audit's first version, is folded into #7/#8/#9 above — the
original single "execution-backend" concept is, on closer inspection,
three distinct implementation layers, matching the corrected concept
list's own granularity. `CandidateExecutionResult.backend_id`/
`backend_version` remains a persisted/label field usable for whichever
of the three a future design decides it best represents, or a new field
may be added — an H.2C.3B.1 design decision, not resolved here.)

## H.2C.3B.1 scope: typing, versioning, content-binding, persistence, and redaction

For each missing/outcome-affecting concept above, H.2C.3B.1 must decide
— **with tests**, not merely as prose — the following, none of it
implemented in this audit:

| # | Concept | Proposed typed representation | Versioned? | Content-bound? | Field category |
|---|---|---|---|---|---|
| 1 | Environment class/identity | A closed enum (`PERSONAL_BOOTSTRAP`/`COMPANY_PLAYGROUND`) plus a separate, stable **logical** run-scoped identity string (never the raw GCP project number/ID) | Yes (the identity scheme itself) | Yes, embedded in `CalibrationRunContext` alongside `TelemetryCollectionPolicy`/`HostRuntimeContext` | (1) qualification-report identity; (2) production cache/result identity |
| 2 | Cloud provider | A closed enum (extensible, not a free string) | Yes | Yes | (1), (2) |
| 3 | Region/zone | Coarse, safe strings (e.g. `us-central1`, not a full zone-letter-granular value unless proven necessary) | Yes | Yes, but only in the timing-relevant record scope | (1) for H.2C.3D; (4) safe redacted summary aggregate only — never per-record in a way that could be cross-referenced to infer real infrastructure topology |
| 4 | Machine type/CPU architecture | A safe descriptive string (e.g. `n2-standard-4`) — machine *type* names are not secret, unlike instance IDs | Yes | Yes | (1), (4) |
| 5 | Spot/On-Demand class | A closed enum | Yes | Yes, per-invocation (an individual invocation's own provisioning class, not just a run-level default) | (1), (2) |
| 6 | Worker VM/image content identity | A content digest (mirroring `runner_image_digest`'s own pattern) — never a mutable image name/tag | Yes (the digest itself is content-addressed; the *scheme* for computing it is separately versioned) | Yes | (1), (2) |
| 7 | Worker implementation/version | A version string (mirrors `backend_version`'s own precedent) | Yes | Yes | (1), (2) |
| 8 | Coordinator implementation/version | A version string | Yes | Yes | (1), (3) — coordinator version is relevant to trusting completeness claims, but is not itself part of what makes two *invocation* records comparable, so it is audit-only at the invocation level while still entering the run-level qualification identity |
| 9 | Worker-fleet implementation/version | A version string | Yes | Yes | (1), (3) — same reasoning as #8 |
| 13 | Network/isolation policy identity | A checksum over the frozen, accepted isolation-flag set (mirroring how `task_manifest_checksum` pins a frozen manifest) — not the flags themselves restated in every record | Yes (the checksum algorithm) | Yes | (1), (2) — this one is safety-critical enough to enter *both* |
| 15 | Retry/lease policy identity | A small, typed policy record (lease duration, retry ceiling, dead-letter threshold) plus its own checksum | Yes | Yes | (1), (3) |
| 16 | Checksum-algorithm version | An explicit, paired version label for every *new* checksummed type this correction introduces — closing the gap this audit itself names (§ above), not repeating `H5StagingIdentity`'s own reported omission | Yes, by definition | N/A (it is itself the versioning mechanism) | (3) |

**Four field categories, applied consistently across the table above**
(exactly the categorization the correcting authorization required):

1. **Enters qualification-report identity for H.2C.3D** — the field
   must be present, typed, and checked by H.2C.3D's own qualification
   report (mirroring `H2C2BQualificationReport`'s own `run_identity`/
   `qualifying` precedent) before that checkpoint's results may be
   labeled qualifying at all.
2. **Enters production result/cache identity before H.2C.3F** — the
   field must be integrated into `ReferenceResultCacheKey`/
   `ReferenceRunContext`/`ReferenceAuditRecord` (the **production**
   schemas, not only the calibration schema this audit's first pass
   focused on) wherever it can affect outcome interpretation, so a
   production cache entry can never be unsafely reused across
   materially different environments (e.g. a company-playground GCP
   result silently satisfying a lookup that should require a different
   provider/region/machine-type combination). This is a **broader**
   blocking precondition than the first version of this audit stated —
   corrected here explicitly.
3. **Remains protected, audit-only metadata** — recorded (if at all)
   only in an operational/audit tier, never in the scientific schema's
   own identity-bearing fields, and never in a safe committed summary.
4. **Appears in safe redacted summaries** — coarse, aggregate, or
   pre-approved-safe values only (e.g. region as `us-central1`, never a
   specific zone letter combined with other fields in a way that could
   fingerprint a specific VM).

**Absolute rule, restated from the correcting authorization**: raw
personal or company **project IDs, hostnames, instance IDs, container
IDs, filesystem paths, credentials**, or any other raw infrastructure
identifier **must never appear in safe committed reports**, under any
field category. Where a project/environment binding is genuinely
required (category 1/2 above), the design must use a **stable logical
identifier** (e.g. an enum plus a run-scoped opaque label) or a
**content-bound pseudonymous checksum** (a one-way hash of the raw
identifier, salted per the H.2C.3B.1 design, never reversible from the
committed artifact alone) — and the mapping from that logical/
pseudonymous value back to the real infrastructure identifier is itself
**protected operational metadata**, held outside any committed,
publicly-readable artifact, exactly mirroring this project's own
established distinction between `reference_case_checksum` (safe,
committed) and the real, privileged case content it is derived from.
**Nothing here may be silently encoded into an unrelated version
string** (e.g. `execution_profile_id`, `evaluator_version`) — the
H.2C.2A provenance audit's own founding complaint about exactly this
anti-pattern applies with equal force here.

## Revised blocking precondition

Per the amendment's own instruction: **do not modify any accepted
schema in H.2C.3A**; a missing outcome-affecting field found here is a
documented gap and a blocking precondition, not something to implement
now.

**Corrected scope of the gate**: the 11 missing/outcome-affecting
concepts above (#1–#9, #13, #15) are **no longer deferrable only to
H.2C.3F**. They are now a blocking precondition to:

- **MEGB-03H.2C.3D** (personal synthetic distributed qualification) —
  reversing the first version of this audit's own conclusion. H.2C.3D
  produces empirical timing, telemetry, recovery, ordering, and
  equivalence conclusions whose correct interpretation *depends on*
  which environment, provider, region, machine type, provisioning
  class, and implementation versions produced them — exactly the
  concepts this table lists. **No H.2C.3D qualification run may begin
  until the schema in the table above is implemented, versioned,
  tested, and persisted** (H.2C.3B.1's own deliverable), and **no
  result from an environment lacking that provenance may be labeled
  qualifying or used to justify readiness** — mirroring
  `H2C2BQualificationReport.qualifying`'s own existing precedent for
  exactly this kind of guard.
- **MEGB-03H.2C.3F** (company-playground deployment and native-Linux
  qualification) — as before, but now **additionally** requiring the
  same identity be integrated into **production** result/cache
  identities (`ReferenceResultCacheKey`/`ReferenceRunContext`/
  `ReferenceAuditRecord`), not only the calibration schema, wherever it
  can affect outcomes — preventing unsafe reuse of a cached/audited
  result across materially different environments. This is the
  corrected, broader scope of "blocking precondition to H.2C.3F" the
  first version of this audit did not state.

**Not blocked**: **MEGB-03H.2C.3C** may still perform personal-project
bootstrap and non-qualifying connectivity/deployment smoke checks — no
qualifying result is produced or claimed there, so the gate above does
not apply. **MEGB-03H.2C.3B.2** (provider-neutral orchestration
interfaces and offline synthetic tests) may proceed once H.2C.3B.1's
schema exists for its interfaces to be built against — H.2C.3B.2 is
explicitly gated *on* H.2C.3B.1, not exempted from it.

**Timing-scoped concepts** (#3 region/zone, #4 machine type) remain
recommended for the same H.2C.3B.1 correction pass for consistency,
though their outcome-affecting scope is narrower (timing interpretation
only, per the audit table above). **Concepts #10/#11/#16** (queue/
object-store implementation version, checksum-algorithm version) are
not independently blocking — #10/#11 remain genuinely benign per their
own classification, and #16 is a *design discipline* H.2C.3B.1 must
follow while implementing the others, not a separate blocking gap.
**Managed-model provenance** (explicitly outside this numbered list) is
not a blocking precondition to H.2C.3D or H.2C.3F at all — it belongs
to H.2C.3G's own scope and must be resolved before *that* checkpoint
persists any candidate-generation record, independently of this gate's
own timeline.

## H.2C.3B.1 / H.2C.3B.2 decomposition

**H.2C.3B.1 — Distributed-execution provenance schema and identity
semantics.** Deliverables: the typed/versioned/content-bound/persisted/
redacted design decisions in the table above, implemented as new,
additive types (mirroring `HostRuntimeContext`/`TelemetryCollectionPolicy`/
`CollectorMethodProvenance`'s own established pattern), embedded in
`CalibrationRunContext`/`CalibrationInvocationRecord` at the appropriate
run-level/per-invocation granularity; the corresponding integration into
`ReferenceResultCacheKey`/`ReferenceRunContext`/`ReferenceAuditRecord`
required before H.2C.3F (see above); a `CALIBRATION_SCHEMA_VERSION` bump
(v2→v3) and, if the production schemas are touched, their own
appropriate version bumps, following the same no-migration-needed
pattern already confirmed multiple times in this project's history (no
real persisted calibration or production artifact exists anywhere in
the repository today); offline synthetic tests proving construction,
round-trip, checksum-tamper rejection, and the safe-vs-protected field
split, mirroring `test_calibration_telemetry_provenance_schema.py`'s own
established test shape. **No cloud access; ticket/schema/test work
only.**

**H.2C.3B.2 — Provider-neutral orchestration interfaces and offline
synthetic tests.** Deliverables: the work-admission/leasing, worker-
fleet-control, run-submission/cancellation/resumption/reconciliation,
and cost-estimation-and-authorization interfaces named in the
architecture doc's §3, designed *against* H.2C.3B.1's own schema (not
before it exists), with offline synthetic (no real GCP) tests proving
the interface contracts. **No cloud access.**

Both remain **separately authorized** — this audit installs the
decomposition and the schema-design requirements only; it does not
authorize either checkpoint's own implementation.

## Decision register

| Item | Status |
|---|---|
| GCP as the initial distributed-execution provider | **Frozen by the accepted amendment** |
| Provider-neutral application boundary (no GCP concepts in scientific schemas without justification) | **Frozen by the accepted amendment** |
| Personal-bootstrap / company-playground two-environment model, with hard technical guardrails | **Frozen by the accepted amendment** |
| Mandatory credential/permissioning interaction protocol | **Frozen by the accepted amendment** |
| Compute Engine (not GKE/Cloud Run/containerized Cloud Batch) as the initial worker substrate | **Frozen by the accepted amendment**, with an explicit reopening condition (a later checkpoint proving nested isolation/telemetry correctness) |
| H.2C.3A–H checkpoint decomposition | **Frozen by the accepted amendment** |
| Company-playground qualification gate (16-item list) | **Frozen by the accepted amendment** |
| Personal $50 / company $1,500 cost ceilings | **Frozen by the accepted amendment** |
| Two-plane separation (reference-execution plane vs. candidate-generation plane, connected only by an immutable checksummed manifest) | **Corrected and frozen by this correction pass** — not merely recommended; the non-transitive-permissions property (execution-plane SA never holds Vertex permission; generation-plane SA never holds privileged-reference/Docker-host access) is a structural IAM-design requirement, reconfirmed at H.2C.3B.1 (IAM role design) and H.2C.3E (SRE review) |
| Provider-neutral abstraction list, now plane-tagged (§3 of the architecture doc) | **Recommended by H.2C.3A**, corrected for plane tagging |
| GCP product mapping, now plane-tagged (§4 of the architecture doc) | **Recommended by H.2C.3A**, corrected for plane tagging — still requires the user's approval as the first real implementation step (H.2C.3B.2, once H.2C.3B.1's schema exists) |
| Trust-boundary diagram and preserved-invariants list | **Recommended by H.2C.3A**, corrected to show the two planes and their single cross-plane channel |
| 29-row threat/control matrix (25 original + 4 new plane-separation rows) | **Recommended by H.2C.3A**, corrected — several detective/preventive controls require empirical qualification (see "Verifying checkpoint" column) before being trusted; rows 26/27 (Vertex-reach and privileged-access structural closures) are verifiable ahead of time via IAM policy review, not only empirically |
| H.2C.3B decomposed into H.2C.3B.1 (provenance schema/identity semantics, with tests) and H.2C.3B.2 (provider-neutral orchestration interfaces and offline synthetic tests, gated on H.2C.3B.1) | **Frozen by this correction pass** |
| Just-in-time credential/permission matrix (§4 of the promotion doc) | **Recommended by H.2C.3A** — every role/API/permission is a proposal to be reconfirmed against current GCP documentation and company IAM conventions at the checkpoint that actually requests it |
| Cost model structure and formulas | **Recommended by H.2C.3A** |
| Specific pricing figures used in the cost model | **Provisional, requiring re-verification** — see `gcp-experiment-cost-model.md` §1/§8; not fit for a real billing decision without reconfirmation at H.2C.3C/H.2C.3G |
| Proposed Vertex model portfolio (Qwen3-Coder-480B-A35B-Instruct / Qwen3-Next-80B-A3B-Instruct / Kimi K2 Thinking) | **Explicitly NOT frozen** — a proposal only, per the accepted amendment §6; still requires the user's approval, and separately, H.2C.3G's own availability/pricing/identifier verification |
| Environment class/identity, cloud provider, worker VM/image identity, worker/coordinator/worker-fleet implementation versions, provisioning class, network/isolation policy identity, retry/lease policy identity as new typed/versioned/content-bound calibration-schema fields | **Blocked by a provenance/schema gap — gate moved forward to H.2C.3D** (corrected; no longer deferrable to H.2C.3F only) — see "Revised blocking precondition" above; H.2C.3B.1 must implement this, with tests, before any H.2C.3D qualification run begins |
| Same identity fields integrated into production result/cache identity (`ReferenceResultCacheKey`/`ReferenceRunContext`/`ReferenceAuditRecord`) | **Blocked by a provenance/schema gap — new finding of this correction pass** — required before H.2C.3F, in addition to (not instead of) the calibration-schema integration above |
| Region/zone, machine-type fields (timing-interpretation scope) | **Blocked by a provenance/schema gap** (narrower scope) — recommended for the same H.2C.3B.1 correction pass |
| Checksum-algorithm version labeling for any new checksummed type this correction introduces | **Blocked by a provenance/schema gap** — a design-discipline requirement on H.2C.3B.1 itself, not an independently blocking gap |
| Managed-model provenance schema (provider/identifier/version/region/protocol) | **Reserved, not designed, by this correction pass** — schema boundary only; scoped entirely to H.2C.3G, not H.2C.3D or H.2C.3F |
| SRE-reviewed IAM/networking/quota/logging/budget configuration for the company playground | **Requires SRE input** — explicitly deferred to H.2C.3E |
| Exact console/`gcloud` steps for any credential boundary | **Requires the user's approval at the specific checkpoint that reaches it** (first at H.2C.3C), per the mandatory interaction protocol |
| Whether the distributed architecture actually achieves EXACT cgroup telemetry and an acceptable overhead on real Compute Engine (vs. this project's own Docker-Desktop finding) | **Requires empirical qualification** — H.2C.3F's own native-Linux qualification is the checkpoint that answers this; nothing in this document assumes the answer |
| Whether Spot recovery, at-least-once idempotency, and deterministic ordering hold under real distributed conditions | **Requires empirical qualification** — H.2C.3D (synthetic, personal) and H.2C.3F (real, company) |
| Full campaign cost, once the model portfolio and candidate/replicate counts are frozen | **Requires empirical qualification** — H.2C.3G |

## Related documents

- `megb-03h2c2a-collector-provenance-audit.md` — the precedent this
  audit's method and structure follow.
- `docs/architecture/gcp-distributed-reference-execution.md`
- `docs/security/gcp-distributed-execution-threat-model.md`
- `docs/operations/gcp-environment-promotion.md`
- `docs/measurement/gcp-experiment-cost-model.md`
- `tickets/megb-03.md` — "Approved MEGB-03H.2C.3 Planning Amendment"
