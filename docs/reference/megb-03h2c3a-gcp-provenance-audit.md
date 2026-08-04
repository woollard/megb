# MEGB-03H.2C.3A — GCP Distributed-Execution Provenance/Schema-Gap Audit

**Status: read-only audit. No accepted schema was modified in producing
this document.** Mirrors `megb-03h2c2a-collector-provenance-audit.md`'s
own read-only-determination pattern, applied to the distributed-execution
provenance concepts the "Approved MEGB-03H.2C.3 Planning Amendment"
requires this checkpoint to audit.

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

## Concept-by-concept audit

| # | Concept | Classification | Where (if persisted) | Rationale |
|---|---|---|---|---|
| 1 | Environment identity (personal-bootstrap vs. company-playground) | **Missing/outcome-affecting** | — | No field anywhere distinguishes which environment produced a record. Without it, a personal-bootstrap synthetic result could be silently indistinguishable from a company-playground scientific one at the schema level — exactly the failure mode threat #8/#9 in `gcp-distributed-execution-threat-model.md` describe. This project already has the analogous concept at the *diagnostic-report* level (`H2C2BQualificationReport.qualifying`, `run_identity`'s `-diagnostic-` tagging) but nothing equivalent exists in the *persisted calibration schema* (`CalibrationRunContext`/`CalibrationInvocationRecord`). |
| 2 | Cloud provider | **Missing/outcome-affecting** | — | H.2C.2B itself empirically proved provider/host materially changes achievable telemetry quality (macOS/Docker Desktop → `BOUNDARY_ONLY` only, exact cgroup path unreachable) and overhead (70–130× the frozen gate). A future GCP-vs-some-other-substrate comparison needs an explicit provider label to be interpretable — `HostRuntimeContext`'s existing OS/kernel fields describe *symptoms* consistent with a given provider but do not name it directly, and two different providers could plausibly present similar OS/kernel signatures on their own Linux VM images. |
| 3 | GCP project number, or a safe non-secret project identity | **Audit-only** | — | Supports independently verifying concept #1's claimed environment identity (threat #9's detective control) but is not itself the scientifically load-bearing concept, and embedding a GCP-specific "project_number" field directly into the calibration schema would violate the accepted amendment's provider-neutrality requirement. Belongs in an operational/audit log tier, not the scientific schema. |
| 4 | Region and zone semantics | **Missing/outcome-affecting for timing only** | — | This project's own established methodology already treats per-invocation timing as host-dependent (the `0.418s`/invocation baseline, the whole H.1 calibration design's concurrency-aware projection formula). Region/zone is a reasonable proxy for underlying hardware/network characteristics that affect *timing* measurements; it does not affect *correctness* or *value* measurements (peak memory, process count, candidate correctness), so the outcome-affecting classification is scoped to timing-sensitive calibration only. |
| 5 | Worker image identity (the outer VM/worker-controller image, distinct from the runner container image) | **Missing/outcome-affecting** | — | A genuinely new concept: today's schema tracks only `runner_image_digest` (the per-invocation candidate-execution container). The proposed architecture adds a second image layer — the worker VM's own boot/base image, which determines the Docker daemon version, cgroup driver, and kernel the worker runs — all three proven materially relevant to telemetry quality/overhead by H.2C.2B. |
| 6 | Runner image digest | **Persisted/bound** | `CandidateExecutionResult.runner_image_digest` | Already exists, already content-addressed (via `compute_provenance.sh`'s digest-pinning discipline), already flows through the existing execution→calibration adapter chain. No gap. |
| 7 | Worker machine architecture/type | **Partially persisted; specific machine type missing/outcome-affecting for timing** | `HostRuntimeContext.architecture` (CPU architecture family, e.g. `x86_64`/`arm64`) | The coarse CPU architecture family is already covered. The *specific* GCP machine type/shape (e.g. `n2-standard-4` vs. `c2-standard-8`) is not — different shapes have different CPU generations, core counts, and memory bandwidth, directly affecting timing measurements the same way region/zone does (#4). Not outcome-affecting for correctness/value measurements. |
| 8 | Worker-fleet implementation/version | **Missing/outcome-affecting** | — | Mirrors the already-accepted precedent of `backend_id`/`backend_version` (which track the execution-backend implementation) — a worker-fleet identity is the distributed-orchestration analogue, relevant to interpreting retry/idempotency/completeness guarantees of a calibration trace produced under a specific fleet-controller implementation. |
| 9 | Queue/admission implementation/version (Pub/Sub or otherwise) | **Missing/benign** | — | The calibration schema's own reconciliation (`reconcile_task_evaluation`, content-checksum-bound contributor sets) is *already designed to be robust to duplicate/out-of-order delivery from any admission mechanism* — this is exactly what makes the at-least-once-delivery invariant in the architecture doc (§6) hold without a schema change. Useful operational/audit value; not required for scientific validity. |
| 10 | Object-store implementation/version | **Missing/benign** | — | Same reasoning as #9 — the calibration trace's own durability/checksum-verification discipline (`CalibrationTraceStore`) is storage-backend-agnostic by design; which object store backs it does not change how a downstream consumer should interpret the trace's content. |
| 11 | Execution-backend implementation/version | **Persisted/label** | `CandidateExecutionResult.backend_id`/`backend_version` | Already exists as free-form strings (currently `"docker"` per `docker_backend.py`'s `BACKEND_ID` constant); a GCP-worker execution backend would set a new value here with no schema change required. |
| 12 | Telemetry collector policy and method | **Persisted/bound** | `TelemetryCollectionPolicy` (run-level, embedded in `CalibrationRunContext`), `CollectorMethodProvenance` (per-metric, embedded in `CalibrationInvocationRecord`) | The strongest-covered concept in this entire audit — this is exactly the subject of the H.2C.2A provenance/schema correction and its terminal-state-proof audit. No gap; the existing design already anticipates method/quality/disposition varying by host. |
| 13 | Spot/On-Demand provisioning class, where outcome-affecting | **Missing/outcome-affecting** | — | A Spot-preempted-and-retried invocation may have a materially different resource/timing profile than an uninterrupted On-Demand one. The existing `TelemetryUnavailableReason`/`WorkItemDisposition` taxonomies distinguish *infrastructure retry* generally but do not distinguish *why* (ordinary transient failure vs. a Spot reclaim specifically) — a real interpretability gap for anyone later asking "was this invocation's timing affected by preemption recovery." |
| 14 | Managed-model provider, model identifier/version, region, request protocol | **Missing/outcome-affecting, but scoped to a different schema family** | — | Directly relevant to candidate *generation* provenance (reproducibility of what a model produced, under what identity/version/protocol) — but `CalibrationRunContext`/`CalibrationInvocationRecord` model *reference execution* (H.3–H.6), not candidate generation. This concept belongs to a not-yet-designed candidate-generation/model-invocation provenance schema, which is explicitly H.2C.3G's own scope (the model-portfolio freeze and "define the managed-inference reproducibility/provenance record" requirement already named in the accepted amendment §6) — not a gap *in* the calibration schema this audit is inspecting. |

## Summary

| Classification | Count | Concepts |
|---|---|---|
| Persisted/bound | 2 | #6 runner image digest, #12 telemetry collector policy/method |
| Persisted/label | 1 | #11 execution-backend implementation/version |
| Audit-only | 1 | #3 GCP project number/safe identity |
| Missing/benign | 2 | #9 queue/admission implementation/version, #10 object-store implementation/version |
| Missing/outcome-affecting | 7 (+1 scoped elsewhere) | #1 environment identity, #2 cloud provider, #4 region/zone (timing-scoped), #5 worker image identity, #7 machine type (timing-scoped), #8 worker-fleet implementation/version, #13 Spot/On-Demand provisioning class; #14 managed-model provenance (outcome-affecting, but belongs to a separate future schema, not this one) |

## Blocking precondition

Per the amendment's own instruction: **do not modify any accepted
schema in H.2C.3A**; a missing outcome-affecting field found here is a
documented gap and a blocking precondition, not something to implement
now.

**None of the seven missing/outcome-affecting gaps above (#1, #2, #4,
#5, #7, #8, #13) block H.2C.3B** (provider-neutral distributed-execution
*interfaces* and *offline synthetic tests* — no real persistence of
scientific evidence occurs there; the interfaces should be designed
*aware* of these gaps so they don't have to be retrofitted later, but no
schema correction is required to design an interface). They likewise do
not block **H.2C.3C** (personal bootstrap, synthetic-only by
construction — never produces scientific evidence at all, per its own
stage-allowlist guardrail) or **H.2C.3D** (personal synthetic
distributed qualification — proves the distributed *mechanics* work,
not a scientific record).

**They are a blocking precondition to H.2C.3F** (company-playground
deployment and native-Linux qualification) — the first checkpoint in
the H.2C.3A–H decomposition that would persist real
`CalibrationInvocationRecord`/`CalibrationRunContext` data representing
actual distributed-execution provenance. A schema correction closing
gaps #1, #2, #5, #8, and #13 at minimum (the concepts most directly
tied to scientific-integrity and telemetry-interpretation risk) must be
separately authorized, designed, and implemented — following the same
narrow-correction, version-bump discipline the H.2C.2A provenance/schema
correction already established — before H.2C.3F persists any real
result. Gaps #4/#7 (region/zone, machine type) are recommended for the
same correction pass for consistency, though their outcome-affecting
scope is narrower (timing interpretation only). Gap #14 (managed-model
provenance) is not a blocking precondition to H.2C.3F at all — it
belongs to H.2C.3G's own scope and must be resolved before *that*
checkpoint persists any candidate-generation record, independently of
H.2C.3F's own timeline.

**Recommended narrowest correction** (for the separately authorized
checkpoint that will actually perform it, not implemented here): extend
`HostRuntimeContext` with a small set of additional allowlisted,
non-identifying fields (`cloud_provider`, `region`, `machine_type`) and
add a new, run-level `DistributedExecutionPolicy`-shaped type (mirroring
`TelemetryCollectionPolicy`'s own existing shape) carrying
`environment_identity`, `worker_fleet_implementation_id/version`, and
`provisioning_class` (Spot/On-Demand), embedded in `CalibrationRunContext`
alongside the existing `TelemetryCollectionPolicy`/`HostRuntimeContext` —
the same "run-level requested/actual" split this project already applies
to telemetry, applied here to distributed-execution provenance. This
would require a `CALIBRATION_SCHEMA_VERSION` bump (v2→v3), following the
same no-migration-needed pattern already confirmed twice in this
project's history (no real persisted calibration artifact exists
anywhere in the repository today, confirmed as recently as the H.2C.2A
correction's own audit).

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
| Provider-neutral abstraction list (§2 of the architecture doc) | **Recommended by H.2C.3A** |
| GCP product mapping (§3 of the architecture doc) | **Recommended by H.2C.3A** — still requires the user's approval as the first real implementation step (H.2C.3B) |
| Trust-boundary diagram and preserved-invariants list | **Recommended by H.2C.3A** |
| 25-row threat/control matrix | **Recommended by H.2C.3A** — several detective/preventive controls require empirical qualification (see "Verifying checkpoint" column) before being trusted |
| Just-in-time credential/permission matrix (§4 of the promotion doc) | **Recommended by H.2C.3A** — every role/API/permission is a proposal to be reconfirmed against current GCP documentation and company IAM conventions at the checkpoint that actually requests it |
| Cost model structure and formulas | **Recommended by H.2C.3A** |
| Specific pricing figures used in the cost model | **Provisional, requiring re-verification** — see `gcp-experiment-cost-model.md` §1/§8; not fit for a real billing decision without reconfirmation at H.2C.3C/H.2C.3G |
| Proposed Vertex model portfolio (Qwen3-Coder-480B-A35B-Instruct / Qwen3-Next-80B-A3B-Instruct / Kimi K2 Thinking) | **Explicitly NOT frozen** — a proposal only, per the accepted amendment §6; still requires the user's approval, and separately, H.2C.3G's own availability/pricing/identifier verification |
| Environment identity, cloud provider, worker image identity, worker-fleet version, provisioning class as new persisted calibration-schema fields | **Blocked by a provenance/schema gap** — see "Blocking precondition" above; requires its own separately authorized correction checkpoint before H.2C.3F |
| Region/zone, machine-type fields (timing-interpretation scope) | **Blocked by a provenance/schema gap** (narrower scope) — recommended for the same correction pass |
| Managed-model provenance schema (provider/identifier/version/region/protocol) | **Blocked by a provenance/schema gap**, scoped to H.2C.3G, not H.2C.3F |
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
