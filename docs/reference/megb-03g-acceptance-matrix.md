# MEGB-03G Acceptance Matrix

## Status

Produced by MEGB-03G.5. Covers MEGB-03G's own scope only (aggregation,
caching, orchestration, redaction, audit, and G.4 orchestration
qualification). **Does not claim MEGB-03 epic completion** — that remains
MEGB-03I's "Final Acceptance Criteria" and epic-wide acceptance matrix
(`tickets/megb-03.md`). Readiness handed off by this matrix is
`ORCHESTRATION_READY_FOR_MEGB_03H` only; MEGB-03H owns scientific execution
qualification and MEGB-06A owns final feasibility, per the "Approved
MEGB-03G.2–G.5 Scope Amendment" section 3.

Legend: **PASS** — implemented, tested, accepted. **N/A** — requirement
superseded/reassigned by an accepted amendment (reason given).

## 1. Original MEGB-03G requirements

| # | Requirement | Status | Implementation | Verifying tests | Docs | Limitation / downstream owner |
|---|---|---|---|---|---|---|
| 1 | `aggregate_reference_results` interface | PASS (as corrected by the Compatibility Amendment §1) | [`aggregation.py:80`](../../src/reference/aggregation.py) — takes `task_results` + `candidate_set_manifest`, derives shared context from results themselves | [`tests/test_reference_aggregation.py`](../../tests/test_reference_aggregation.py) (24 tests) | This matrix; ticket Compatibility Amendment §1 | — |
| 2 | Aggregate exactly 164 tasks, equal weight | PASS | `_require_exact_count`, `REQUIRED_TASK_COUNT` in `aggregation.py` | `test_reference_aggregation.py` | — | — |
| 3 | Report evaluated/valid/invalid/incomplete/base-pass/full-suite-pass/primary counts | PASS (MEGB-03E schema, consumed unchanged by G.1) | `ReferenceBenchmarkResult.status_counts`/`full_suite_outcome_counts` in [`result_schema.py`](../../src/reference/result_schema.py) | `tests/test_result_schema.py` (MEGB-03E) | — | Schema owned by MEGB-03E, already accepted |
| 4 | Compute primary Q_ref only when every required task measurement is valid | PASS (MEGB-03E schema) | `ReferenceBenchmarkResult.q_ref` property | `tests/test_result_schema.py` | — | Schema owned by MEGB-03E |
| 5 | Never silently reduce/change the denominator | PASS | `expected_task_count=REQUIRED_TASK_COUNT` fixed at construction; `_require_exact_count` rejects any other count | `test_reference_aggregation.py` | — | — |
| 6 | Preserve full-suite compatibility metrics under distinct identifiers | PASS | `full_suite_diagnostic`/`full_suite_outcome_counts`; `aggregate_reference_results` never inspects or folds them into `q_ref` | `test_full_suite_diagnostic_never_affects_q_ref` (cited in Scope Amendment §6) | — | — |
| 7 | Cache/reuse keyed on complete outcome-affecting tuple | PASS (as corrected by Compatibility Amendment §3 — adds `reference_case_checksum`) | [`cache_key.py:115`](../../src/reference/cache_key.py) `ReferenceResultCacheKey` (12 fields; see [version-registry.md](version-registry.md)) | `tests/test_reference_cache_key.py` (39 tests) | [version-registry.md](version-registry.md) | — |
| 8 | Never rerun a valid measurement silently; infra-invalid/incomplete may be resumed under policy | PASS | `ReferenceResultCache.put` raises `NonCacheableResultError` for non-`VALID`; orchestrator retry scoped to `INVALID_INFRASTRUCTURE` only | `test_reference_cache.py` (21), `test_reference_orchestrator.py` (33) | [cache-recovery-runbook.md](../operations/cache-recovery-runbook.md) | — |
| 9 | Append-only audit record schema (caller, run IDs, candidate id/hash, freeze metadata, versions, timestamp, artifact location, status) | PASS | [`reference_audit.py:86`](../../src/reference/reference_audit.py) `ReferenceAuditRecord` (24 fields, explicit allowlist) | `tests/test_reference_audit.py` (28 tests) | This matrix; [privileged-artifact-policy.md](../measurement/privileged-artifact-policy.md) | — |
| 10 | Repeated/adaptive querying visible in audit trail | PASS | `ReferenceAuditLog.append` never rewrites/removes; `ReferenceOrchestrator._append_audit` called on every disposition (cache hit, miss, fresh execution, retry) | `test_reference_audit.py`, `test_reference_orchestrator.py` | — | — |
| 11 | Produce privileged detailed + redacted public artifacts | PASS | [`reference_cache.py`](../../src/reference/reference_cache.py) (privileged) + [`result_redaction.py`](../../src/reference/result_redaction.py) (redacted) | `test_reference_cache.py`, `tests/test_result_redaction.py` (27 tests) | [privileged-artifact-policy.md](../measurement/privileged-artifact-policy.md) | — |
| 12 | Verify optimizer-visible outputs never contain unauthorized evidence | PASS | `redact_task_result`/`redact_benchmark_result` explicit allowlists (never `diagnostics`, full `context`, candidate identity by default) | `test_result_redaction.py` feedback-leakage tests | — | — |

## 2. Approved MEGB-03G Compatibility Amendment

| Section | Requirement | Status | Implementation | Verifying tests |
|---|---|---|---|---|
| §1 | Corrected aggregation interface (context/manifest derived and verified, not independently suppliable) | PASS | `aggregation.py` — `_require_shared_run_context`, `_require_canonical_order` | `test_reference_aggregation.py` |
| §2 | Explicit profile separation (reject reduced-dev, mixed-profile, full-suite-as-primary, 163-task IDs) | PASS | `_require_full_reference_profile`, `ReferenceBenchmarkResult.__post_init__` | `test_reference_aggregation.py` |
| §3 | Complete cache identity (`reference_case_checksum` added) | PASS | `cache_key.py` 12-field key | `test_reference_cache_key.py` (dedicated `reference_case_checksum`-sensitivity test) |
| §4 | Production execution orchestration (cache, resumption, bounded parallelism, backpressure, deterministic ordering, append-only audit, controlled interruption, exact reconciliation) | PASS | [`reference_orchestrator.py`](../../src/reference/reference_orchestrator.py) `ReferenceOrchestrator` | `test_reference_orchestrator.py` (33 tests) |
| §5 | Throughput evidence (sequential + ≥2 concurrency levels, cold/warm cache, interruption/resumption, projections) | PASS — orchestration-qualification only, see Scope Amendment §3 | G.4 benchmark + qualification report | `test_g4_benchmark.py` (26) + real-Docker run |
| §6 | Required tests (v2 aggregation, mismatch rejection, cache-key sensitivity, equivalence, backpressure, interruption, ordering, reconciliation, protected-data checks, throughput-report reproducibility) | PASS | See per-row test files above | Aggregate: 24+39+21+28+33+27 = 172 focused tests across G.1–G.3 |
| §7 | Preserved scope (specification-only; no MEGB-04–09 amendment; no privilege-boundary expansion) | PASS | No such amendment made; privilege boundary unchanged | — |

## 3. Approved MEGB-03G.2–G.5 Scope Amendment

| Section | Requirement | Status | Implementation | Verifying tests |
|---|---|---|---|---|
| §1 | Manifest-independent cache/orchestration; only `aggregate_reference_results` restricted to the 164-entry manifest; reusable unmodified by MEGB-06H | PASS | `reference_orchestrator.py` module docstring: "manifest-independent... never imports or requires `ReferenceValidationCandidateSetManifest`..."; `aggregation.py` is the sole manifest-restricted entry point | `test_reference_orchestrator.py` (no manifest dependency in any test) |
| §2 | Protected cache/diagnostic storage (privileged cache never committed; typed/versioned/integrity-checked; `PrivilegedCaseDiagnostic` never in the audit log; committed audit uses explicit allowlist) | PASS | `reference_cache.py` (`artifacts/privileged/reference/cache/`, gitignored); `reference_audit.py` (`AUDIT_RECORD_FIELD_NAMES` allowlist, no diagnostic field) | `test_reference_cache.py`, `test_reference_audit.py` |
| §3 | MEGB-03G.4 vs. MEGB-03H boundary; readiness must be `ORCHESTRATION_READY_FOR_MEGB_03H`/`ORCHESTRATION_BLOCKED` only | PASS | G.4 accepted with readiness `ORCHESTRATION_READY_FOR_MEGB_03H` | `docs/measurement/megb-03g4-qualification-report.{json,md}` |
| §4 | Corrected G.4 benchmark plan (synthetic workloads, frozen plan, minimum readiness criteria) | PASS | "Approved MEGB-03G.4 Benchmark Plan (Frozen)" in ticket; `g4_benchmark.py`/`g4_benchmark_evaluator.py` | `test_g4_benchmark.py`, `test_g4_benchmark_evaluator.py`, real-Docker run |
| §5 | MEGB-03G.5 vs. MEGB-03I (acceptance matrix/docs/CI only; no user-facing CLI; expensive benchmark on a manual/scheduled workflow only) | PASS (this document + `.github/workflows/g4-qualification.yml`) | This matrix; new `workflow_dispatch`-only workflow | Workflow syntax validated (see final checkpoint) |
| §6 | Compatibility diagnostics (`FullSuiteDiagnostic` never affects `q_ref_task`) | PASS (confirmation only, no new work required) | — | `test_full_suite_diagnostic_never_affects_q_ref` |

## 4. G.1 — Aggregation and Profile Enforcement

**Status: ACCEPTED** (`8a3974b`, `c71b1b7`, `e02370e`). See ticket checkpoint log row for full detail. Covers aggregation and full-profile enforcement only — caching, orchestration, audit, redaction persistence, throughput, and CLI belong to G.2–G.5.

## 5. G.2 — Cache, Audit, and Privileged Persistence

**Status: ACCEPTED** (`fd55f56`, `d0852fb`, `c8baea4`, `970dba9`). Cache-provenance audit closed four gaps (`execution_protocol_version`, `dataset_checksum`, `task_manifest_checksum` on `ReferenceRunContext`; `expected_output` in `reference_case_checksum`). Result-schema v4, cache-key/entry v2, audit-record v2.

## 6. G.3 — Orchestration, Backpressure, and Resumption

**Status: ACCEPTED** (`98e6f81`, `96d8409`, `d046970`). `ReferenceOrchestrator` — cache-first execution, prospective-key deduplication, bounded-concurrency admission window, `INVALID_INFRASTRUCTURE`-scoped retry, cooperative-cancellation resumption. Does not call `aggregate_reference_results`; manifest-independent by design (confirmed above).

## 7. G.4 — Equivalence, Security, and Throughput Qualification

**Status: conformance correction in progress.** A read-only workflow audit (MEGB-03G.5's `g4-qualification.yml`) found that `G4_DATASET_VERSION`/`G4_DATASET_CHECKSUM`/`G4_TASK_MANIFEST_CHECKSUM` never matched the "Approved MEGB-03G.4 Benchmark Plan (Frozen)"'s own normative values — a divergence present since the original implementation and never remediated through the v1, v2, or report-schema corrections. The decision was to restore implementation conformance (not retroactively amend the plan): the three identities are corrected to their frozen values and `G4_EVALUATOR_VERSION` bumps `v2`→`v3`. **Only a clean-cache run under evaluator v3 and the corrected, frozen identities may re-establish `ORCHESTRATION_READY_FOR_MEGB_03H`.** The prior v2 run (report checksum `9f6e68865f829821ddd6651adf778b83f1cd195239f2a80b9b7ea4dcd1269879`, measured best speedup **1.8227692031888638×**) is superseded and preserved as historical evidence only, not as acceptance grounds. See [version-registry.md](version-registry.md)'s conformance-correction note and the ticket's "Approved MEGB-03G.4/G.5 Conformance Correction" section for full detail.

## 8. Known limitations and explicit downstream ownership

- **Real-corpus resource calibration, the frozen high-assurance execution profile, repeated-run/environmental determinism, and definitive runtime/compute projections for MEGB-06A** are explicitly **MEGB-03H's** responsibility, not this matrix's. G.4's throughput figures are infrastructure-level projections only.
- **The 163-task experimental `Q_meas`/gaming-delta aggregate** is explicitly **MEGB-06I's** responsibility. MEGB-03G never constructs it, per Scope Amendment §1.
- **The user-facing `evaluate-reference` CLI** is explicitly **MEGB-03I's** responsibility. MEGB-03G.5 provides only internal build/verify/qualification commands (see [reference-evaluation-architecture.md](reference-evaluation-architecture.md#internal-commands)).
- **`PrivilegedCaseDiagnostic` persistence**, if ever needed, is an explicit later decision left to a future subtask — not implemented by G.2–G.4 (confirmed: appears only in evaluator return-type signatures, discarded — `_diagnostics` — at the orchestrator's sole call site).
- **Full MEGB-03 epic acceptance** remains MEGB-03I's "Final Acceptance Criteria" and epic-wide acceptance matrix — not claimed here.
