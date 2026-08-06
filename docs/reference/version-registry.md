# Version and Provenance Registry (MEGB-03G)

## Status

Produced by MEGB-03G.5. Snapshot of every active accepted identity as of the
MEGB-03G.4/G.5 conformance correction's clean-cache evaluator-v3 run
(implementation commit `81ffd9d`; qualification report checksum
`4884e66fa8141b43a2ceba012666651821bb86cf2beb355fc598b004aa7afe27`, commit
`f4c7fb9`). This is a point-in-time registry, not a live document —
re-derive from source (`grep -n "_VERSION = " src/reference/*.py`) rather
than trusting this file after any later version bump.

## Two categories of identity

This registry distinguishes two fundamentally different kinds of value, a
distinction load-bearing throughout MEGB-03G (most explicitly in the G.4
execution-protocol-version correction):

- **Content checksums** — a `sha256` hex digest computed *from actual bytes*
  (a manifest's content, a workload's source, a report's own fields). These
  are reproducible: recomputing the hash from the same input always yields
  the same value, and a single-byte content change always changes it.
  Nothing about a content checksum is manually chosen.
- **Manually governed version labels** — a human-chosen string constant
  (e.g. `"reference-result-schema-v4"`) that identifies a *schema, algorithm,
  or evaluation-logic revision*. These change only when a person bumps them,
  following this project's established breaking-change discipline: every
  prior schema correction in MEGB-03G bumped its version string and rejected
  every older one, never silently reinterpreting old data under a new
  meaning.

Conflating the two is exactly the defect class the G.4 execution-protocol
correction fixed: `execution_protocol_version` is a version label (identifies
which wire-transport implementation was used), not a content checksum, and
must equal the real value whenever the real transport is genuinely reused —
giving it a distinct synthetic *label* for identical *content* was itself a
misstatement, the same way giving a real label to synthetic content would be.

## Manually governed version labels (schema / algorithm / evaluator identity)

| Constant | Value | Module | Meaning |
|---|---|---|---|
| `RESULT_SCHEMA_VERSION` | `reference-result-schema-v4` | `result_schema.py` | `ReferenceTaskResult`/`ReferenceRunContext`/`ReferenceBenchmarkResult` schema shape |
| `CACHE_KEY_SCHEMA_VERSION` | `reference-result-cache-key-v2` | `cache_key.py` | `ReferenceResultCacheKey` field shape |
| `CACHE_ENTRY_SCHEMA_VERSION` | `reference-result-cache-entry-v2` | `reference_cache.py` | On-disk cache-entry envelope shape |
| `AUDIT_RECORD_SCHEMA_VERSION` | `reference-audit-record-v3` (see "MEGB-03H.2B.1 addendum" below) | `reference_audit.py` | `ReferenceAuditRecord` field shape |
| `ORCHESTRATION_MODEL_SCHEMA_VERSION` | `reference-orchestration-v1` | `reference_orchestrator.py` | `WorkItem`/`OrchestrationRunSummary` shape |
| `EXECUTION_PROTOCOL_VERSION` | `reference-evaluator-execution-protocol-v1` | `reference_evaluator.py` | **The actual MEGB-02 execution protocol** — `CandidateExecutionRequest`/`CandidateExecutionResult` wire shape, `src.execution.wire`. Shared, unchanged transport; real for both the accepted reference evaluator *and* the G.4 synthetic benchmark evaluator (see below). |
| `EVALUATOR_VERSION_FULL` | `reference-evaluator-v1` | `reference_evaluator.py` | Full reference-only evaluator identity |
| `EVALUATOR_VERSION_REDUCED_DEV` | `reference-evaluator-reduced-dev-v1` | `reference_evaluator.py` | Reduced-development evaluator identity (MEGB-03F, dev-only) |
| `EXECUTION_PROFILE_ID_FULL` | `docker-megb02-full-v1` | `reference_evaluator.py` | Full execution-profile identity (`FULL_EXECUTION_PROFILE`) |
| `EXECUTION_PROFILE_ID_REDUCED_DEV` | `docker-megb02-reduced-dev-v1` | `reference_evaluator.py` | Reduced-dev execution-profile identity |
| `COMPARISON_PROFILE_VERSION` | `comparison-profile-v1` | `oracle.py` | Real comparison-profile algorithm identity |
| `ORACLE_ALGORITHM_VERSION` | `oracle-v1` | `oracle.py` | Real oracle-generation algorithm identity |
| `PARTITION_ALGORITHM_VERSION` | `partition-v1` | `partition.py` | Real partition algorithm identity |
| `HUMANEVAL_PLUS_VERSION` | (from `evalplus.data.humaneval`, e.g. `v0.1.10`) | `evalplus` (pinned dependency) | Real dataset version |
| `G4_EVALUATOR_VERSION` | `megb-03g4-benchmark-evaluator-v3` | `g4_benchmark_evaluator.py` | G.4 synthetic benchmark evaluator identity. **v1→v2**: v1's outputs carried incorrect `execution_protocol_version` provenance. **v2→v3**: v2's outputs carried non-conformant `dataset_version`/`dataset_checksum`/`task_manifest_checksum` (see the conformance-correction note below); each bump keeps results produced under the prior, incorrect identity distinguishable by version alone. |
| `G4_DATASET_VERSION` | `synthetic-g4-benchmark-v1` | `g4_benchmark_evaluator.py` | Synthetic dataset identity — deliberately distinct from `HUMANEVAL_PLUS_VERSION`. Restored in the conformance correction to exactly the frozen plan's own value (previously `megb-03g4-synthetic-dataset-v1`, a non-conformant divergence — see below). |
| `G4_PARTITION_VERSION` | `megb-03g4-synthetic-partition-v1` | `g4_benchmark_evaluator.py` | Synthetic partition identity — deliberately distinct from `PARTITION_ALGORITHM_VERSION` |
| `G4_ORACLE_VERSION` | `megb-03g4-synthetic-oracle-v1` | `g4_benchmark_evaluator.py` | Synthetic oracle identity — deliberately distinct from `ORACLE_ALGORITHM_VERSION` |
| `G4_COMPARISON_PROFILE_VERSION` | `megb-03g4-synthetic-comparison-v1` | `g4_benchmark_evaluator.py` | Synthetic comparison-profile identity — deliberately distinct from `COMPARISON_PROFILE_VERSION` |
| `G4_EXECUTION_PROFILE_ID` | `megb-03g4-benchmark-profile-v1` | `g4_benchmark_evaluator.py` | Synthetic execution-profile identity — deliberately distinct from `EXECUTION_PROFILE_ID_FULL` |
| `G4_REPORT_SCHEMA_VERSION` | `megb-03g4-throughput-report-v1` | `g4_benchmark.py` | Raw (non-privileged, gitignored) benchmark-report shape |
| `G4_QUALIFICATION_REPORT_SCHEMA_VERSION` | `megb-03g4-qualification-report-v2` | `g4_qualification_report.py` | Committed qualification-report shape. **v1→v2**: v1 derived `synthetic_workload_version` incorrectly (see below). |
| `BENCHMARK_PLAN_VERSION` | `megb-03g4-benchmark-plan-v1` | `g4_qualification_report.py` | The frozen G.4 benchmark plan's own identity (fixed, module-owned constant, never a caller-supplied parameter) |
| `SYNTHETIC_WORKLOAD_VERSION` | `megb-03g4-synthetic-workload-v1` | `g4_qualification_report.py` | The synthetic workload's own identity — **independent of `G4_EVALUATOR_VERSION`** (a prior version incorrectly set this field to the evaluator's version; fixed to be a separate, fixed, module-owned constant that cannot vary with the evaluator) |
| `SYNTHETIC_WORKLOAD_CHECKSUM_ALGORITHM_VERSION` | `megb-03g4-workload-checksum-algorithm-v1` | `g4_qualification_report.py` | Identifies how the workload content checksum below is canonicalized/hashed — a separate field from the checksum value itself |
| `H5_PROMOTION_MANIFEST_SCHEMA_VERSION` | `megb-03h5-promotion-manifest-v1` | `h5_promotion_manifest.py` | `H5PromotionManifest` field shape and `PromotionState`/`EntryPromotionState` state-machine semantics (the transition table in `advance_manifest` is versioned together with the manifest shape, not as a separate constant — a future state-machine change bumps this same version, per this table's own established one-version-per-persisted-shape discipline). See "MEGB-03H.2B.2 addendum" below. |
| `PROMOTION_SUMMARY_SCHEMA_VERSION` | `megb-03h5-promotion-summary-v1` | `h5_promotion.py` | `PromotionSummary` field shape — the safe, allowlisted, committed-output-suitable promotion report. See "MEGB-03H.2B.2 addendum" below. |
| `CALIBRATION_SCHEMA_VERSION` | `megb-03h-calibration-record-v3` | `calibration_schema.py` | `CalibrationRunContext`/`CalibrationInvocationRecord`/`CalibrationTaskEvaluationRecord` field shape. **v1→v2**: v1 had no persisted telemetry-collection-policy, host/runtime, or per-metric collector-method provenance — see "MEGB-03H.2C.2A addendum" below. (Introduced by MEGB-03H.2A; this row itself was missing from this registry until the H.2C.2A correction pass — a registry-currency gap, not a second schema change.) **v2→v3 (MEGB-03H.2C.3B.3)**: `CalibrationRunContext` gains `distributed_run_context_checksum`/`provenance_manifest_checksum`, and `CalibrationInvocationRecord` gains `worker_execution_context_checksum` — content-binding this schema to `src.distributed`'s provenance types, per `docs/reference/megb-03h2c3b1-integration-map.md`'s own blocking-gate item. `CalibrationTaskEvaluationRecord` gains no new field — its existing `contributing_invocation_content_checksums` already transitively binds worker provenance through each contributor's full `record_checksum`. No real persisted v1 or v2 artifact exists anywhere in this repository — no migration performed or required. See "MEGB-03H.2C.3B.3 addendum" below. |
| `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION` | `megb-03h2c3b1-distributed-provenance-v1` | `src/distributed/_checksums.py` | Field shape for every `src/distributed/` provenance/identity type (`DistributedRunContext`, `WorkerExecutionContext`, `RetryLeasePolicy`, `MixedWorkerProvenanceSummary`, `QualificationIdentity`, `ProductionIdentityProjection`, `AggregateProductionIdentityProjection`, `SafeRedactedSummary`, `ProtectedOperationalMapping`). Introduced by MEGB-03H.2C.3B.1; this row itself was missing from this registry until this MEGB-03H.2C.3B.2A pass — a registry-currency gap, not a schema change. See "MEGB-03H.2C.3B addendum" below. |
| `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION` | `megb-03h2c3b2b2-distributed-orchestration-v3` | `src/distributed/_checksums.py` | Field shape for every `src/distributed/` orchestration-contract type (`ArtifactReference`, `WorkDescriptor`, `QueueWorkMessage`, `CancellationRequest`, `ExecutionAttempt`, `ResultCommit`, `Acknowledgement`, `TerminalDisposition`, `WorkerRegistration`, `Lease`, `LeaseRenewal`, `PersonalEnvironmentPolicy`, `SafeAuditEvent`) — a schema family independent of `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION` above. **v1→v2**: v1's `PersonalEnvironmentPolicy.spending_ceiling_usd` was a `float`, and `ArtifactReference.artifact_checksum` bound content only, not classification metadata — see "MEGB-03H.2C.3B.2B.1 addendum" below. **v2→v3**: `TerminalDispositionReason` gained `NON_RETRYABLE_EXECUTOR_FAILURE`, and `ResultCommit` gained a required `actual_cost_cents` field — see "MEGB-03H.2C.3B.2B.2 correction addendum" below. Introduced by MEGB-03H.2C.3B.2A; corrected by MEGB-03H.2C.3B.2B.1 and MEGB-03H.2C.3B.2B.2's own correction. See "MEGB-03H.2C.3B addendum", "MEGB-03H.2C.3B.2B.1 addendum", and "MEGB-03H.2C.3B.2B.2 correction addendum" below. |
| `CHECKSUM_ALGORITHM_VERSION` (`src.distributed`) | `sha256-canonical-json-v1` | `src/distributed/_checksums.py` | The one checksum-derivation algorithm identity shared by **both** `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION` and `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`-stamped types — sha256 over `json.dumps(payload, sort_keys=True)`. Deliberately the same name as no other constant in this table (`SYNTHETIC_WORKLOAD_CHECKSUM_ALGORITHM_VERSION` is a distinct, unrelated identity scoped to G.4's own synthetic workload checksum) — the two never collide because they are different Python identifiers in different modules; this row exists so this document's own registry is not silently incomplete about which module's `CHECKSUM_ALGORITHM_VERSION` it is describing. Introduced by MEGB-03H.2C.3B.1; unchanged by MEGB-03H.2C.3B.2A, which reuses it rather than defining a second one. See "MEGB-03H.2C.3B addendum" below. |
| `FAULT_CONFORMANCE_REPORT_SCHEMA_VERSION` | `megb-03h2c3b2b3-fault-conformance-v1` | `src/distributed/fault_conformance.py` | `FaultConformanceReport`/`ConformanceEntry` field shape — the safe, committed MEGB-03H.2C.3B.2B.3 in-process fault-injection/recovery conformance report (mirrors `H2C2B_QUALIFICATION_REPORT_SCHEMA_VERSION`'s own self-checksummed, versioned, explicitly-allowlisted pattern). A schema family independent of both `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION` and `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION` above — this report proves conformance of code stamped with those schemas, but is not itself stamped with either. Introduced by MEGB-03H.2C.3B.2B.3; persisted at `docs/measurement/megb-03h2c3b2b3-fault-conformance-report.{json,md}`. |
| `OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION` | `megb-03h2c3b2c-offline-e2e-qualification-v2` | `src/distributed/offline_e2e_qualification_report.py` | `OfflineE2EQualificationReport` field shape — the safe, committed MEGB-03H.2C.3B.2C offline end-to-end synthetic distributed qualification report (mirrors `FAULT_CONFORMANCE_REPORT_SCHEMA_VERSION`'s own self-checksummed, versioned, exact-count-validated, derived-readiness pattern). A schema family independent of `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION`, `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`, and `FAULT_CONFORMANCE_REPORT_SCHEMA_VERSION` above — this report references the fault-conformance report's own checksum by value rather than being stamped with it. Introduced by MEGB-03H.2C.3B.2C; persisted at `docs/measurement/megb-03h2c3b2c-offline-e2e-qualification-report.{json,md}`. Scoped explicitly to offline, provider-neutral, in-process recovery — makes no H.2C.3D, GCP, durable-process, cross-host, or Docker/native-Linux-equivalence claim. **v1→v2 (MEGB-03H.2C.3B.2C correction):** v1 (never accepted or pushed — superseded, preserved only in git history at commit `edbda37`) recorded only the qualification gate's own output checksums, with no field checking that the *workload class actually used* was the qualification-candidate class rather than the smoke class. v2 adds `distributed_run_intent`, `qualifying_workload_class`, and `qualification_gate_ready` as explicit, safe, closed-enum-validated fields, plus `qualification_workload_consistent` as a fourth, wholly-derived field (never caller-settable) folded into `readiness`. No `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION` bump was required for this correction — `WorkloadClass.SYNTHETIC_QUALIFICATION_CANDIDATE` already existed in the accepted v3 enum before this correction; using it correctly is not a legal-value-set expansion. |
| `DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION` | `megb-03h2c3b3-distributed-provenance-manifest-v1` | `src/distributed/provenance_manifest.py` | `DistributedProvenanceManifest` field shape — the typed, immutable, versioned, self-checksummed, **protected** (never committed as-is) artifact bundling a `DistributedRunContext`, its full `WorkerExecutionContext` set, their `MixedWorkerProvenanceSummary`/`QualificationIdentity`/qualification-gate readiness, `generation_command`/`code_revision`, and a `SafeRedactedSummary`. A fourth, independent `src/distributed/` schema family (alongside `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION`, `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`, and `OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION` above). Introduced by MEGB-03H.2C.3B.3. Field shape unchanged by the B.3 correction, but its persistence disposition is: as of the correction, the full manifest IS persisted — as **synthetic protected evidence**, never real HumanEval/candidate evidence — under the gitignored `artifacts/privileged/distributed_provenance/` path, anchored by the new committed `MANIFEST_LOCK_SCHEMA_VERSION` lock below (superseding the original checkpoint's "never persisted to a fixed repository path" design, which left the safe report's `provenance_manifest_checksum` a dangling, unverifiable reference). See "MEGB-03H.2C.3B.3 addendum" and "MEGB-03H.2C.3B.3 correction addendum" below. |
| `MANIFEST_LOCK_SCHEMA_VERSION` | `megb-03h2c3b3-distributed-provenance-manifest-lock-v1` | `src/distributed/provenance_manifest_lock.py` | `ManifestLockEntry`/`ManifestLockFile` field shape — the small, committed, non-privileged lock anchoring the protected `DistributedProvenanceManifest`'s identity (artifact ID, protected path, schema/checksum-algorithm versions, full manifest checksum, distributed-run-context checksum, expected worker count, safe topology-summary checksum, size, generation command, generating code revision/dirty state, authorized consumers) without embedding the manifest's own bytes. A sixth, independent `src/distributed/` schema family. Mirrors `src/reference/partition_lock.py`'s already-established privileged-artifact-lock pattern exactly. Committed at `artifacts/reference/distributed_provenance/calibration_provenance_manifest.lock.json`; the protected manifest itself lives at `artifacts/privileged/distributed_provenance/calibration_provenance_manifest.json` (gitignored). Introduced by the MEGB-03H.2C.3B.3 correction. See "MEGB-03H.2C.3B.3 correction addendum" below. |
| `CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION` | `megb-03h2c3b3-calibration-provenance-report-v2` | `src/distributed/calibration_provenance_report.py` | `CalibrationProvenanceReport` field shape — the safe, committed MEGB-03H.2C.3B.3 calibration-provenance qualification-evidence report (mirrors `OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION`'s own self-checksummed, versioned, derived-readiness pattern). A fifth, independent `src/distributed/` schema family. Binds the provenance-manifest checksum, calibration run-context checksum, participating worker-context checksums, a safe topology histogram, intended-vs-measured peak concurrency, and invocation counts; `readiness`/`blocker_reasons` are always derived, never independently caller-settable. **v1→v2 (correction)**: v1 raised a hard constructor error when `measured_peak_concurrency` exceeded `intended_concurrency` or the personal-bootstrap ceiling, conflating a *failed qualification result* (valid evidence, bad outcome) with a *structural defect* (malformed data) — v2 adds three closed blocker-reason members (`MEASURED_CONCURRENCY_EXCEEDS_INTENDED`, `MEASURED_CONCURRENCY_EXCEEDS_ADMITTED_TOPOLOGY`, `PERSONAL_CONCURRENCY_CEILING_EXCEEDED`) and folds all three concurrency criteria into ordinary derived blocker reasons, never a raised error. The one real persisted v1 artifact (`docs/measurement/megb-03h2c3b3-calibration-provenance-report.{json,md}`, committed at `232d0af`) is superseded by this correction's regenerated v2 report at the same path. Stale v1 reports are rejected outright (regression-tested). Scoped explicitly to the offline calibration-provenance evidence chain — makes no GCP or H.2C.3C credential-boundary readiness claim. See "MEGB-03H.2C.3B.3 addendum" and "MEGB-03H.2C.3B.3 correction addendum" below. |

**Pairwise distinctness** (regression-tested, `tests/test_g4_qualification_report.py::test_all_five_identities_are_pairwise_distinct`):
`BENCHMARK_PLAN_VERSION`, `SYNTHETIC_WORKLOAD_VERSION`,
`SYNTHETIC_WORKLOAD_CHECKSUM_ALGORITHM_VERSION`, `G4_EVALUATOR_VERSION`, and
`G4_QUALIFICATION_REPORT_SCHEMA_VERSION` are all mutually distinct strings.

## Content checksums (reproducible from actual bytes)

| Checksum | Current value (64-char sha256 hex unless noted) | Computed from |
|---|---|---|
| `benchmark_plan_checksum` | `16b8634a5700cee173b5f5b916db1d7f8a5023bcd83332c581bb81e8db9b7fd8` | Frozen plan constants only: tier case counts, unscaled N values, concurrency tuples, calibration sample count, ceiling seconds. Unchanged across every G.4 correction — proves the frozen plan itself was never touched. |
| `synthetic_workload_checksum` | `c8e20a97f145c01ae39c56297bffa8e4dae95761095cb9d188eb93260ef92c41` | Workload *content only*: entry point, canonical solution source, tier case counts (`_synthetic_workload_checksum()` in `g4_qualification_report_cli.py`). Deliberately excludes every version/identity label — signature is `(entry_point, canonical_solution, tier_case_counts)`, nothing else, so it cannot depend on evaluator/schema/protocol/plan version, code revision, timestamps, or measured outcomes (structurally tested). |
| `docker_image_provenance_checksum` | `cdf2fa8490f2a0dd2b8470e8d7218a864afe655d3018e56dd788a47bbe7caa29` | sha256 of the runner `Dockerfile` bytes |
| `report_checksum` (final, accepted) | `4884e66fa8141b43a2ceba012666651821bb86cf2beb355fc598b004aa7afe27` — from the clean-cache evaluator-v3 run (the prior value, `9f6e68865f829821ddd6651adf778b83f1cd195239f2a80b9b7ea4dcd1269879`, belongs to the superseded, non-conformant v2 run and is preserved in git history as historical evidence only) | Every other qualification-report field, canonical JSON, sha256 — auto-recomputed and verified at construction (`G4QualificationReport.__post_init__`), never a caller-supplied value |
| `G4_DATASET_CHECKSUM` | `620d891af7232d54263877049d3e8720fc81cb38e3f2afad3e476b7e6936f8a9` | `sha256(b"g4-benchmark-synthetic-dataset-v1")` — the frozen plan's own value, restored by the conformance correction (previously `sha256(b"megb-03g4-synthetic-dataset-content-v1")` = `ecd5c87a63b86d0ff290f5a8f243668662da5047d0feac3b55625a40334ca4e6`, a non-conformant divergence — see below). Fixed synthetic constant either way, never colliding with any real `dataset_checksum`. |
| `G4_TASK_MANIFEST_CHECKSUM` | `2660eefaf368c747f88db3842d5d4c021279e6b1c6bd60b7be1cdb318f0f8977` | `sha256(b"g4-benchmark-synthetic-manifest-v1")` — the frozen plan's own value, restored by the conformance correction (previously `sha256(b"megb-03g4-synthetic-manifest-content-v1")` = `800231f3a168e18432ca35f64b202274ea0a695e52ccc3b213a650a96a126c4b`, a non-conformant divergence — see below). |
| `reference_case_checksum` | (per-case, includes `oracle_record.expected_output`) | `case_serialization.py` — bound into the cache key so a corrected canonical solution with the same case IDs but a different expected output is never invisible to the cache |
| `dataset_checksum` (real) | `DatasetProvenance.evalplus_dataset_hash` (32 chars, natively) | The real HumanEval+ corpus content |
| `manifest_checksum` (candidate-set) | sha256-hex | `ReferenceValidationCandidateSetManifest`'s own content |
| `manifest_checksum` (H.5 promotion manifest) | sha256-hex | `H5PromotionManifest`'s own content (`_checksum_of` in `h5_promotion_manifest.py`) — auto-recomputed/verified-or-rejected at construction, same discipline as every other self-checksummed type in this table |
| `summary_checksum` (H.5 promotion summary) | sha256-hex | `PromotionSummary`'s own content excluding itself (`_summary_checksum_of` in `h5_promotion.py`) — auto-recomputed/verified-or-rejected at construction |
| `identity_checksum()` (H.5 staging identity) | sha256-hex, computed on demand (not a persisted field) | `H5StagingIdentity.identity_checksum()` — sha256 of `json.dumps(dataclasses.asdict(identity), sort_keys=True)`. **No paired algorithm-version label exists for this checksum** (unlike, e.g., `synthetic_workload_checksum`'s `SYNTHETIC_WORKLOAD_CHECKSUM_ALGORITHM_VERSION`) — see the "MEGB-03H.2B.2 addendum" below for why this is a real, reported gap rather than an oversight. |

**Conformance correction: a normative plan/implementation divergence, not a
cosmetic one.** A read-only workflow audit found that `G4_DATASET_VERSION`,
`G4_DATASET_CHECKSUM`, and `G4_TASK_MANIFEST_CHECKSUM` had never matched the
"Approved MEGB-03G.4 Benchmark Plan (Frozen)" ticket section's own stated
values, since the original MEGB-03G.4 implementation — this went
unremediated through every subsequent G.4 correction round (v1, v2,
report-schema), each of which checked only that these identities were
*synthetic and non-colliding with the real corpus*, never that they matched
the frozen plan's own literal values. An earlier draft of this document
mischaracterized this as a "wording mismatch... cosmetic only"; that
characterization was itself an error and has been corrected.

The plan text was determined to be **normative, not illustrative**: its
section header states the workload is "frozen now," under a section the
"Approved MEGB-03G.2–G.5 Scope Amendment" §4 required to specify "the exact
synthetic workload definitions and their checksums" *before any material
Docker execution* — and the same section's `entry_point`/canonical-solution
values **were** implemented exactly, byte-for-byte, confirming the plan was
treated as binding for those two values and making the divergence on the
remaining three an unauthorized deviation, not a deliberate re-derivation.

**Functionally non-outcome-affecting, but not for that reason excused.**
Both the frozen and the previously-implemented values were equally fixed,
deterministic, synthetic, and non-colliding with any real corpus identity;
every equivalence/ordering/isolation/cache/interruption/throughput
measurement and the `≥1.5×` threshold were computed identically regardless
of which fixed synthetic string was used. The frozen plan preceded
execution specifically so implementation would not silently diverge from
what was reviewed and accepted, and that guarantee was violated here
regardless of outcome.

**Discovered before push and before the new `g4-qualification.yml`
workflow's first hosted execution** — during the read-only workflow audit
this MEGB-03G.5 checkpoint required prior to triggering that workflow on
GitHub, not after any external-facing run.

**Corrected in evaluator v3**: `G4_DATASET_VERSION`/`G4_DATASET_CHECKSUM`/
`G4_TASK_MANIFEST_CHECKSUM` now exactly equal the frozen plan's own values
(this table); `G4_EVALUATOR_VERSION` bumped `v2`→`v3` so any result produced
under the prior, non-conformant identity remains distinguishable by version
alone. The decision was to restore implementation conformance to the frozen
plan, not to retroactively amend the plan to legitimize the prior values.

**Verified through a new clean-cache qualification run**: only a
clean-cache benchmark run using evaluator v3 and the corrected, frozen
identities may support final `ORCHESTRATION_READY_FOR_MEGB_03H` readiness.
The prior v2 run (report checksum
`9f6e68865f829821ddd6651adf778b83f1cd195239f2a80b9b7ea4dcd1269879`) is
superseded, preserved in git history as historical evidence only, and does
not by itself establish readiness.

## MEGB-03H.2B.1 addendum: `AUDIT_RECORD_SCHEMA_VERSION` v2→v3

This registry's own "Status" note above (a point-in-time snapshot as of the
G.4/G.5 conformance correction) predates this addendum; it is recorded here
rather than by rewriting that snapshot's prose, per this project's
established convention of appending correction notes instead of silently
rewriting an already-accepted historical record.

**Current schema: `reference-audit-record-v3`** (`reference_audit.py`,
commit `a179160`, MEGB-03H.2B.1's fresh-execution-semantics correction).

**Reason:** addition of `CacheDisposition.BYPASSED_BY_POLICY`
(`reference_cache.py`) as a legal value of `ReferenceAuditRecord`'s
`cache_disposition` field. Even though that field's own validation
computes its accepted-value set dynamically from the current
`CacheDisposition` enum (rather than a separately hardcoded literal list),
adding a new legal value to an already-versioned, persisted record type is
still a schema-semantic expansion of what the record may contain — the
same reasoning already applied to every prior `v(n)`→`v(n+1)` bump in this
table, not a special exemption.

**Semantic distinction — bypass vs. miss vs. hit vs. write disposition:**
`cache_disposition` on one audit record can describe either a *read*
outcome or a *write* outcome, and (as of H.2B.1) whether the cache was
consulted at all:

- `VALID_HIT` — a real `cache.get()` call found a valid entry (served
  without a fresh evaluator invocation, or a fresh evaluation's write
  reconciled against an identical pre-existing entry).
- `MISS` — a real `cache.get()` call was made and genuinely found nothing.
  Reserved exclusively for an *attempted, empty* lookup.
- `BYPASSED_BY_POLICY` — the cache was never consulted (read) or never
  written (write) at all, because a fresh
  `~src.reference.orchestration_trace.CachePolicy` deliberately skipped it.
  Never returned by `ReferenceResultCache.get()`/`.put()` themselves;
  constructed only by `ReferenceOrchestrator` to describe this deliberate
  decision. Distinct from `MISS` precisely because no lookup was ever
  attempted — labeling a bypass as `MISS` would misrepresent it as a real,
  empty lookup.
- `WRITE_ACCEPTED` / `CONFLICTING_WRITE` / `STORAGE_INFRASTRUCTURE_FAILURE`
  — real `cache.put()` outcomes, unchanged by this correction.

**Local artifact disposition:** a real, gitignored, non-privileged
`reference-audit-record-v2`-stamped audit log exists locally at
`artifacts/reference/g4_benchmark_audit/g4_benchmark_audit_log.jsonl` (66
records, from the MEGB-03G.4 benchmark run). It is now stale under v3 and
is not migrated — consistent with the v1→v2 bump's own precedent
(documented in `reference_audit.py`'s module docstring) of never providing
a migration path for this artifact type. This is a deliberate, accepted
consequence, not an oversight: the file is explicitly a "generated local
operational log" (per `reference_audit.py`'s own docstring and
`privileged-artifact-policy.md`), regenerable at any time by rerunning the
G.4 benchmark, and it is **not** a committed or otherwise authoritative
artifact — no committed `reference-audit-record-v2` artifact exists
anywhere in this repository (confirmed by a repository-wide search), so no
migration is required for correctness.

**Historical references remain historical:** `docs/reference/megb-03h1-calibration-design.md`'s
own "Inventory" table records `AUDIT_RECORD_SCHEMA_VERSION` as
`reference-audit-record-v2` because that was the true, current value at
the time MEGB-03H.1 was produced (before H.2B.1 existed) — that table is
deliberately left unchanged. Rewriting a historical point-in-time snapshot
to reflect a version that did not yet exist when it was recorded would be
misleading, not corrective.

## MEGB-03H.2B.2 addendum: H.5 staging/promotion identities

This registry's own "Status" note predates this addendum, per this
project's established convention (see the H.2B.1 addendum above) of
appending correction notes rather than rewriting an already-accepted
historical snapshot. Introduced by MEGB-03H.2B.2 (commits `a723d19`,
`1087ce9`) and its recovery/path-safety correction (commits `81c9e4c`,
`a04baaf`) — every identifier below is newly created by this checkpoint;
none existed at any prior version, so none requires migration.

### `H5_PROMOTION_MANIFEST_SCHEMA_VERSION` = `megb-03h5-promotion-manifest-v1`

- **Purpose:** versions `H5PromotionManifest`'s field shape and the
  `PromotionState`/`EntryPromotionState` state machine it embeds
  (`PREPARED → GATE_PASSED → PREFLIGHT_PASSED → PROMOTING → COMPLETED`/
  `BLOCKED`, enforced by `advance_manifest`'s transition table). The
  transition table is not separately versioned — a future change to legal
  transitions is a shape/semantics change to this same manifest and bumps
  this one constant, matching how this table already treats every other
  schema (e.g. `CACHE_ENTRY_SCHEMA_VERSION` covers both field shape *and*
  the envelope logic that interprets it).
- **Trust classification:** manually governed version label (human-chosen,
  bumped only on a deliberate breaking change), not a content checksum.
- **Artifact privileged or safe to commit:** the constant itself is
  ordinary source code, safe to commit. A **persisted manifest instance**
  (the JSON file `save_promotion_manifest`/`load_promotion_manifest`
  read/write) is a privileged, non-committed artifact — it lives under the
  same H.5 staging root as the staging cache it describes
  (`artifacts/privileged/reference/h5_staging_cache/<identity_checksum>/promotion_manifest.json`,
  per `manifest_path_for`) and is git-ignored by the same
  `artifacts/privileged/` rule as every other privileged artifact in this
  repository. No such file currently exists anywhere in this repository or
  its history — confirmed by direct inspection during the H.2B.2
  correction's own protected-data statement — so there is nothing to
  migrate.
- **Checksum inputs:** `manifest_checksum` is computed over every other
  field (`identity`, `expected_task_ids`, `staged_entries`, `gate_outcome`,
  `preflight_outcome`, `entry_states`, `state`, `interrupted`,
  `generation`) via canonical `json.dumps(..., sort_keys=True)` + sha256
  (`_checksum_of` in `h5_promotion_manifest.py`).
- **Regeneration/verification:** `H5PromotionManifest.__post_init__`
  auto-computes `manifest_checksum` on construction and rejects a
  caller-supplied value that doesn't match its own recomputed contents
  (tamper/corruption detection); `advance_manifest` is the only way to
  produce a new, valid instance from an existing one (new `generation`,
  freshly recomputed checksum); `save_promotion_manifest` writes via
  atomic temp-file-rename with explicit `flush()`+`fsync()`;
  `load_promotion_manifest` rejects a stray, incomplete temp file left
  behind by a crash (proven in `tests/test_h5_promotion_manifest.py`'s
  crash-safe-recovery test) without disturbing the real, adjacent file.

### `PROMOTION_SUMMARY_SCHEMA_VERSION` = `megb-03h5-promotion-summary-v1`

- **Purpose:** versions `PromotionSummary`'s field shape — the safe,
  allowlisted projection of an `H5PromotionManifest` suitable for
  committed output (run/checksum identities, expected/staged/promoted/
  already-satisfied counts, gate/preflight/final states, a generation
  timestamp, its own report checksum).
- **Trust classification:** manually governed version label.
- **Artifact privileged or safe to commit:** **safe to commit** — this is
  the entire purpose of this type, structurally distinct from the manifest
  above. No field on `PromotionSummary` is capable of carrying a task or
  case identity, a candidate identity or source, an expected output, a
  cache key, a per-entry (task-linked) state, a raw diagnostic, or a
  privileged filesystem path (`candidate_set_manifest_checksum` is a safe
  artifact checksum, not a candidate identity — regression-tested in
  `tests/test_h5_promotion_correction.py::test_promotion_summary_field_allowlist_excludes_forbidden_content`).
- **Checksum inputs:** `summary_checksum` is computed over every other
  field via the same canonical `json.dumps(..., sort_keys=True)` + sha256
  pattern (`_summary_checksum_of` in `h5_promotion.py`), mirroring
  `CalibrationSummaryReport.report_checksum`'s own established precedent.
- **Regeneration/verification:** `build_promotion_summary(manifest, *,
  generated_at=...)` builds a fresh instance from a manifest and a
  caller-supplied ISO-8601 timestamp; `PromotionSummary.__post_init__`
  auto-computes/verifies `summary_checksum` and rejects an unrecognized
  `summary_schema_version` or a tampered checksum
  (`InvalidPromotionSummaryError`).

### `H5StagingIdentity.identity_checksum()` — reported gap, not silently versioned

`H5StagingIdentity`'s staging directory (`staging_dir()`) and the
promotion manifest's own path (`manifest_path_for()`) are named from
`identity_checksum()`: `sha256(json.dumps(dataclasses.asdict(identity),
sort_keys=True))`. This **is** a genuine content checksum (reproducible
from the identity's own field values, per this document's "two categories
of identity" distinction above) — but, unlike every other checksum in this
registry that pairs with a dedicated algorithm-version label (e.g.
`synthetic_workload_checksum` ↔ `SYNTHETIC_WORKLOAD_CHECKSUM_ALGORITHM_VERSION`,
`CACHE_KEY_SCHEMA_VERSION` covering `key_digest`'s own derivation), **no
such paired version constant exists for `identity_checksum()`**. This was
introduced by the H.2B.2 recovery correction (commit `81c9e4c`) as a
narrow, targeted fix for the path-traversal finding, and no algorithm
version was invented for it during that correction or during this
documentation pass, per instruction.

**Why this matters, concretely:** the checksum's inputs are exactly
`H5StagingIdentity`'s current field set and Python's `json.dumps`/
`dataclasses.asdict` canonicalization behavior. If either ever changes
(the identity gains/loses a field, or the canonicalization scheme changes)
without a version bump to distinguish old-checksum from new-checksum
directory names, the *same* logical identity would silently compute a
*different* `identity_checksum()` under old vs. new code — landing on a
different, unrelated directory rather than continuing (or being validated
against) whatever staging area a prior process had created for it. Nothing
detects or announces that transition today, because nothing versions it.

**Not remediated in this pass:** this documentation update records the
gap rather than closing it, per instruction ("do not invent one silently
during documentation. Report that gap before changing code."). No
persisted H.5 staging directory exists anywhere in this repository today
(confirmed above and in the H.2B.2 correction's own protected-data
statement), so there is no live migration concern yet — but a future
change to `H5StagingIdentity`'s fields or to `identity_checksum()`'s
canonicalization should not be made without first deciding whether this
checksum needs its own explicit algorithm-version label (analogous to
`SYNTHETIC_WORKLOAD_CHECKSUM_ALGORITHM_VERSION`) at that time.

## MEGB-03H.2C.2A addendum: `CALIBRATION_SCHEMA_VERSION` v1→v2

`CALIBRATION_SCHEMA_VERSION` was introduced by MEGB-03H.2A but — per this
registry's own "point-in-time, not live" caveat above — was never added as
a row to this table until this addendum. This addendum records both that
registry-currency gap and the real v1→v2 schema correction, together.

**Why v2 exists.** A calibration-provenance audit (MEGB-03H.2C.2A) found
that v1's `CalibrationRunContext`/`CalibrationInvocationRecord` had no
persisted representation of: (a) the *requested* telemetry collection
policy (which profile/version, which metrics, preferred method order,
configured sampling intervals) at run level; (b) a safe, allowlisted
host/runtime description (OS family, architecture, kernel release, Docker
server version, cgroup version/mode, etc.) at run level; or (c) the
*actual* per-metric collector method that was selected for each
invocation (which collector implementation/version, which method,
interface family, actual sample count, measurement quality, fallback
disposition, terminal-read coverage). A run-level policy alone cannot
substitute for per-metric provenance, since different metrics and hosts
may select different fallbacks — both had to be added, at their own
appropriate scope, not conflated into one.

**What v2 adds**, all in `calibration_schema.py`:

- `HostRuntimeContext` and `TelemetryCollectionPolicy` — both new,
  self-checksummed, immutable dataclasses, embedded as two new required
  fields (`host_runtime_context`, `telemetry_collection_policy`) on
  `CalibrationRunContext`. Because they are embedded directly in the run
  context, they participate in `context_checksum` automatically — no
  separate reconciliation logic was needed to reject contributors with
  incompatible telemetry/host provenance; `reconcile_task_evaluation`'s
  pre-existing requirement that every contributor share one
  `context_checksum` already covers it.
- `CollectorMethodProvenance` — a new, self-checksummed, immutable
  dataclass, embedded twice (`peak_memory_provenance`,
  `peak_process_provenance`) as new required fields on
  `CalibrationInvocationRecord`, one per collector-based metric. A new
  validation helper (`_require_consistent_metric_provenance`) rejects a
  provenance object whose `measurement_quality`/
  `unavailability_or_failure_reason` disagrees with the record's own
  sibling `peak_memory_quality`/`peak_memory_unavailable_reason` (or the
  process-count equivalents).
- Corrected exactness/terminal-coverage invariants, enforced independently
  at both the execution layer (`TelemetryObservation`) and this persisted
  layer (`CollectorMethodProvenance`): `quality=EXACT` requires
  `terminal_coverage=TERMINAL_READ_CONFIRMED` (scoped to collector-derived
  metrics only — `candidate_wall_time`/`observed_response_bytes` have no
  collector or terminal-read concept and are unaffected); a sampled method
  (`SAMPLED_DOCKER_STATS_MEMORY`, `SAMPLED_DOCKER_TOP_PROCESS_COUNT`) can
  never report EXACT even with a confirmed terminal read; `SAMPLED_WITH_KNOWN_ERROR`
  is rejected outright pending a real quantitative error model.
  `CgroupPeakFileCollector` now confirms container termination via an
  independent signal (`docker inspect`'s own recorded exit code) rather
  than trusting call-site ordering or file existence alone, closing a
  lifecycle race that could otherwise let a late memory peak escape an
  EXACT reading.

**No migration performed.** A targeted search of
`artifacts/privileged/reference/` (the only location any real, persisted
`CalibrationInvocationRecord`/`CalibrationTaskEvaluationRecord` could
exist, gitignored-but-locally-present) found no `calibration/`
subdirectory and no real calibration artifacts anywhere in the repository
or local working tree. Per this project's established discipline (do not
invent a migration when no real artifact exists), none was written; v1
readers simply reject v1-stamped input going forward via the normal
`UnsupportedCalibrationSchemaVersionError` path, same as any other schema
version bump in this registry.

## MEGB-03H.2C.3B addendum: distributed-execution provenance/orchestration schema identities

Three constants, all in `src/distributed/_checksums.py`, were never added
as rows to this table before this addendum — the same "registry-currency
gap, not a schema change" pattern already documented in the H.2C.2A
addendum above. No version was invented, bumped, or otherwise changed to
produce this addendum; every value below is the literal, already-in-force
constant, unmodified by this documentation pass.

### `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION` = `megb-03h2c3b1-distributed-provenance-v1`

- **Introduced:** MEGB-03H.2C.3B.1, commit `d79c1d5` (rewritten to
  `b476d8c` during the H.2C.3B.1 secret-scan remediation — content
  unchanged).
- **Trust classification:** manually governed schema-version label (not a
  content checksum).
- **Owning module:** `src/distributed/_checksums.py` (shared constant);
  enforced via `require_schema_version` on every type in
  `src/distributed/provenance.py` (`DistributedRunContext`,
  `WorkerExecutionContext`, `RetryLeasePolicy`), `identity.py`
  (`MixedWorkerProvenanceSummary`, `QualificationIdentity`,
  `ProductionIdentityProjection`, `AggregateProductionIdentityProjection`),
  `safe_summary.py` (`SafeRedactedSummary`), and `protected_mapping.py`
  (`ProtectedOperationalMapping`).
- **What carries it:** the `distributed_provenance_schema_version` field
  present on every instance of each type above — in-memory objects only;
  no persisted artifact of any of these types currently exists anywhere
  in this repository (no real GCP/distributed run has occurred as of
  MEGB-03H.2C.3B.2A — H.2C.3C, the personal GCP bootstrap, has not begun).
- **Compatibility/migration:** v1 is the only version that has ever
  existed; no migration is required or possible yet, since no persisted
  instance exists to migrate.
- **Relationship to the checksum algorithm:** every type above also
  declares `checksum_algorithm_version` and is validated against
  `CHECKSUM_ALGORITHM_VERSION` below — the schema-version and
  checksum-algorithm-version fields are independent and both required,
  matching this registry's own "two categories of identity" distinction.

### `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION` = `megb-03h2c3b2a-distributed-orchestration-v1`

- **Introduced:** MEGB-03H.2C.3B.2A, commit `04e9d83`.
- **Trust classification:** manually governed schema-version label.
- **Owning module:** `src/distributed/_checksums.py` (shared constant);
  enforced via `require_orchestration_schema_version` on every type in
  `src/distributed/work_contracts.py` (`ArtifactReference`,
  `WorkDescriptor`, `QueueWorkMessage`, `CancellationRequest`,
  `ExecutionAttempt`, `ResultCommit`, `Acknowledgement`,
  `TerminalDisposition`), `worker_contracts.py` (`WorkerRegistration`,
  `Lease`, `LeaseRenewal`), `personal_policy.py`
  (`PersonalEnvironmentPolicy`), and `safe_audit.py` (`SafeAuditEvent`).
- **What carries it:** the `distributed_orchestration_schema_version`
  field present on every instance of each type above — in-memory objects
  only, produced today exclusively by this checkpoint's own test
  fixtures (`tests/_distributed_orchestration_fixtures.py`); no queue,
  store, or coordinator implementation exists yet to persist or transmit
  one for real (MEGB-03H.2C.3B.2B's own, separately authorized, scope).
- **Compatibility/migration:** v1 is the only version that has ever
  existed; nothing to migrate.
- **Relationship to `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION`:** a
  deliberately **separate** schema family, not a version bump of the
  provenance schema — the orchestration-contract types (work/lease/
  result-commit/acknowledgement/policy/audit) are a distinct schema
  surface from the provenance/identity types B.1 introduced, with their
  own independent evolution cadence, exactly mirroring how this registry
  already keeps `RESULT_SCHEMA_VERSION`, `CACHE_KEY_SCHEMA_VERSION`, and
  `CALIBRATION_SCHEMA_VERSION` as three separately-versioned families
  rather than one shared counter. The two `src/distributed/` schema
  families share the same `CHECKSUM_ALGORITHM_VERSION` (below), the same
  way `RESULT_SCHEMA_VERSION` and `CACHE_KEY_SCHEMA_VERSION` share the
  same sha256-canonical-JSON checksum discipline without sharing one
  schema-version counter.

### `CHECKSUM_ALGORITHM_VERSION` (`src.distributed`) = `sha256-canonical-json-v1`

- **Introduced:** MEGB-03H.2C.3B.1, commit `d79c1d5` (rewritten to
  `b476d8c`, content unchanged); reused, not redefined, by
  MEGB-03H.2C.3B.2A.
- **Trust classification:** manually governed algorithm-version label
  (identifies *how* a checksum is derived — sha256 over
  `json.dumps(payload, sort_keys=True)` — not a checksum value itself).
- **Owning module:** `src/distributed/_checksums.py`; the single
  `sha256_of`/`canonical_json` implementation every self-checksummed
  type in both `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION`- and
  `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`-stamped modules calls.
- **What carries it:** the `checksum_algorithm_version` field present on
  every self-checksummed type in `src/distributed/` (both schema
  families) — same in-memory-only status as the two schema versions
  above.
- **Compatibility/migration:** v1 is the only version that has ever
  existed; nothing to migrate.
- **Relationship to the two schema versions above:** deliberately the one
  checksum-derivation scheme shared across both `src/distributed/` schema
  families — a future change to *how* checksums are computed (a new
  canonicalization scheme, a different hash function) would bump this
  one constant independently of either schema-version constant, the same
  separation of concerns `SYNTHETIC_WORKLOAD_CHECKSUM_ALGORITHM_VERSION`
  already models for G.4's own workload checksum. Distinct from, and
  never to be confused with, `SYNTHETIC_WORKLOAD_CHECKSUM_ALGORITHM_VERSION`
  itself — same *kind* of constant (a checksum-algorithm label), different
  Python identifier, different module, different scope, no shared value.

## MEGB-03H.2C.3B.2B.1 addendum: `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION` v1→v2

This registry's own "Status" note (and the "MEGB-03H.2C.3B addendum" above)
predate this addendum; it is recorded here rather than by rewriting that
prose, per this project's established convention of appending correction
notes instead of silently rewriting an already-accepted historical record.

**Why v2 exists.** The MEGB-03H.2C.3B.2B.1 checkpoint correction's own
authorization required two narrow fixes to already-accepted
MEGB-03H.2C.3B.2A orchestration types, found during that checkpoint's own
re-audit (not the original B.2B.1 atomicity audit, which had already
passed):

1. `PersonalEnvironmentPolicy.spending_ceiling_usd` was a Python `float`,
   letting a binary floating-point value reach the personal-bootstrap
   admission comparison — the authorization requires canonical integer
   currency units (or an explicitly justified exact decimal), never a
   float, on that comparison path.
2. `ArtifactReference.artifact_checksum` bound content bytes only; the
   immutable classification metadata
   (`~src.distributed.artifact_store.ArtifactMetadata`) bound to an
   artifact lived only in the artifact store's own internal dict, keyed
   by that same content-only checksum — so the reference type itself
   never proved which classification was bound to it.

Both are field-shape changes to already-versioned, self-checksummed
orchestration types, not merely additive ones, so this schema family
bumps `v1` (`megb-03h2c3b2a-distributed-orchestration-v1`) to `v2`
(`megb-03h2c3b2b1-distributed-orchestration-v2`) rather than claiming the
correction is additive — the same "shape change requires a version bump"
discipline this table already applies to every prior `v(n)`→`v(n+1)` bump
(e.g. `CALIBRATION_SCHEMA_VERSION` v1→v2 above).

**What v2 changes**, both in `src/distributed/`:

- `personal_policy.py`: `PersonalEnvironmentPolicy.spending_ceiling_usd:
  float` → `spending_ceiling_cents: int`
  (`PERSONAL_BOOTSTRAP_SPENDING_CEILING_USD = 50.0` →
  `PERSONAL_BOOTSTRAP_SPENDING_CEILING_CENTS = 5000`); rejects
  non-`int`, `bool`, and negative values by construction (Python's
  arbitrary-precision `int` makes overflow structurally impossible and
  NaN/infinity unrepresentable). `evaluate_admission`'s own
  `estimated_cost_usd: float` parameter is now `estimated_cost_cents:
  int` — there is no float conversion anywhere on the admission/budget
  comparison path in `src/distributed/` after this correction (the prior
  `budget_store.evaluate_and_reserve`'s one-shot `/ 100` bridge to dollars
  is removed entirely, not merely narrowed).
- `work_contracts.py`: `ArtifactReference.artifact_checksum` renamed to
  `content_checksum` (same meaning: sha256 of raw content bytes only);
  new required field `metadata_checksum` (sha256 of the immutable
  `ArtifactMetadata`'s own canonical payload, computed and self-verified
  by `ArtifactMetadata` in `artifact_store.py`). Both are folded into the
  reference's own pre-existing `reference_checksum` self-checksum, so
  changing only the bound classification (content unchanged) now changes
  the reference's own overall checksum. `artifact_store.py`'s
  `InMemoryArtifactStore` keys its internal storage on the composite
  `(content_checksum, metadata_checksum)` pair rather than content
  checksum alone, so the same content bytes bound to two different
  classifications are two distinct artifact identities, never a
  collision requiring a conflict check and never an idempotent
  equivalent write.

**No other orchestration type's field shape changed.** `WorkDescriptor`,
`QueueWorkMessage`, `CancellationRequest`, `ExecutionAttempt`,
`ResultCommit`, `Acknowledgement`, `TerminalDisposition`,
`WorkerRegistration`, `Lease`, `LeaseRenewal`, and `SafeAuditEvent` are
unchanged by this correction; they are stamped with the same shared
`DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION` constant purely because it is
one schema family with one shared version counter (the same "family, not
per-type, versioning" discipline this table's own `CALIBRATION_SCHEMA_VERSION`
row already documents for its own three co-versioned types).

**No migration performed; stale v1 is rejected, not reinterpreted.** A
repository-wide search confirmed no persisted `src/distributed/`
orchestration artifact of either v1 or v2 exists anywhere (no queue,
store, or coordinator implementation exists yet to persist or transmit
one — MEGB-03H.2C.3B.2B.2's own, separately authorized, scope) — every
v1-stamped payload that exists today is produced live by this
checkpoint's own test fixtures and immediately superseded by this same
correction. `require_orchestration_schema_version` rejects the literal
prior v1 string (`megb-03h2c3b2a-distributed-orchestration-v1`) exactly
as it already rejects any other unrecognized version string; dedicated
regression tests assert this for both `ArtifactReference` and
`PersonalEnvironmentPolicy` (`tests/test_distributed_work_contracts.py`,
`tests/test_distributed_personal_policy.py`).

**A separate, additive, non-versioned change in the same checkpoint:**
`AtomicWorkStoreProtocol` was added to `protocols.py`, and
`AuthoritativeWorkRecord` (in `atomic_work_store.py`, never itself
schema-versioned — see that module's own docstring) gained a new
required `reservation_id` field plus reservation-validation on
`create_if_absent`/`acquire_lease`/`reassign_lease`. Neither of these
touches any `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`-stamped type's
field shape, so neither contributes to, or is covered by, this v1→v2
bump — recorded here only to make clear why *not* every change in this
checkpoint required one.

## MEGB-03H.2C.3B.2B.2 correction addendum: `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION` v2→v3

This registry's own "MEGB-03H.2C.3B.2B.1 addendum" above predates this
addendum; recorded here rather than by rewriting that prose, per this
project's established convention.

**Why v3 exists.** The MEGB-03H.2C.3B.2B.2 checkpoint's own narrow
correction (four semantic issues, authorized after the original B.2B.2
checkpoint report but before its acceptance) found two more field-shape/
legal-value-set changes to already-versioned orchestration types:

1. `TerminalDispositionReason` (`work_contracts.py`) reused
   `RETRY_CEILING_EXCEEDED` for both genuine retry-ceiling exhaustion *and*
   a terminal (non-retryable) executor failure dead-lettered on its very
   first attempt — a semantically false disposition reason for the latter
   case, since no retry ceiling was ever actually exceeded. A new member,
   `NON_RETRYABLE_EXECUTOR_FAILURE`, is added; `RETRY_CEILING_EXCEEDED` is
   now reserved for genuine `retry_count >= retry_limit` exhaustion.
2. `ResultCommit` (`work_contracts.py`) gained a new required field,
   `actual_cost_cents: int` — the exact integer-cent amount to finalize
   against the bound budget reservation, now carried directly on the
   durable, checksum-bound committed-result record itself, so it is
   recoverable from authoritative state after a crash between result
   commit and budget finalization without re-deriving it from a separate,
   independently-mutable budget store (whose own reservation may already
   have moved to `FINALIZED`/`RELEASED` by the time a recovering caller
   looks). `reconcile_result_commit` was correspondingly tightened: two
   commits sharing the same `result_content_checksum` but claiming
   different `actual_cost_cents` now raise `ConflictingResultCommitError`
   rather than reconciling as an idempotent duplicate — a replay must
   never be able to change the amount finalized against an
   already-committed result.

Both are field-shape changes to already-versioned, self-checksummed
orchestration types, so this schema family bumps `v2`
(`megb-03h2c3b2b1-distributed-orchestration-v2`) to `v3`
(`megb-03h2c3b2b2-distributed-orchestration-v3`) rather than claiming
either correction is additive.

**No other orchestration type's field shape changed.** `ArtifactReference`,
`WorkDescriptor`, `QueueWorkMessage`, `CancellationRequest`,
`ExecutionAttempt`, `Acknowledgement`, `TerminalDisposition` (the type
itself — only the closed set of legal `TerminalDispositionReason` values it
may carry grew), `WorkerRegistration`, `Lease`, `LeaseRenewal`,
`PersonalEnvironmentPolicy`, and `SafeAuditEvent` are unchanged by this
correction; they are re-stamped with the same shared
`DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION` constant purely because it is
one schema family with one shared version counter.

**No migration performed; stale v2 is rejected, not reinterpreted.** A
repository-wide search (`grep -rl` across every `.json`/`.jsonl` file for
either literal schema-version string) confirmed no persisted
`src/distributed/` orchestration artifact of v1, v2, or v3 exists anywhere
— no queue, store, or coordinator implementation persists or transmits one
across a process boundary yet (durable persistence remains out of scope
until a separately authorized checkpoint). `require_orchestration_schema_version`
rejects the literal prior v2 string
(`megb-03h2c3b2b1-distributed-orchestration-v2`) exactly as it already
rejects v1 and any other unrecognized version string; a dedicated
regression test (`tests/test_distributed_work_contracts.py`) asserts this
for `ResultCommit`, the type whose shape actually changed, alongside a
companion v3 round-trip test.

**Two additive, non-versioned changes in the same correction, recorded
here only to make clear why they do *not* contribute to this v2→v3 bump:**
(1) `CoordinatorConfig` (`coordinator_config.py`, never itself schema-
versioned) no longer hardcodes the personal-bootstrap 2-worker ceiling —
`max_admitted_workers` is now only required to be a positive int, with the
personal-environment ceiling enforced independently by
`PersonalEnvironmentPolicy`/`evaluate_admission` (unchanged) plus a new
structural cross-check at `Coordinator.__init__` (`config.max_admitted_workers`
must not exceed the injected policy's own ceiling); (2) `InMemoryAuditOutbox`
(`audit_outbox.py`, never itself schema-versioned — in-process outbox
bookkeeping) gained a third entry-lifecycle state, `ABANDONED`, alongside
`PENDING`/`DELIVERED`, for a reconciliation clause made permanently
impossible by a lost CAS/conflicting commit/cancellation/terminal
transition. Neither touches any `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`-
stamped type's field shape.

## Cache key: complete field list

`ReferenceResultCacheKey` (`cache_key.py`, schema `reference-result-cache-key-v2`):
`task_id`, `candidate_sha256`, `reference_case_checksum`, `dataset_version`,
`dataset_checksum`, `partition_version`, `task_manifest_checksum`,
`oracle_version`, `comparison_profile_version`, `evaluator_version`,
`execution_profile_id`, `execution_protocol_version` — 11 identity/checksum
fields plus the self-computed `key_digest`.

## MEGB-03H.2C.3B.3 addendum: calibration/qualification provenance integration

Implements exactly the integration `docs/reference/megb-03h2c3b1-integration-map.md`
named as blocking before MEGB-03H.2C.3D: connecting the standalone,
provider-neutral `src/distributed/` provenance types to the accepted
`src/reference/calibration_schema.py` evidence chain, plus a new typed
qualification-evidence/report model binding them together with measured
peak concurrency. Entirely offline — no GCP, `gcloud`, cloud resource,
Docker, or privileged artifact anywhere. Frozen design:
`docs/reference/megb-03h2c3b3-calibration-provenance-integration-design.md`.

**`CALIBRATION_SCHEMA_VERSION` v2→v3** (this table's own row above):
`CalibrationRunContext` gains `distributed_run_context_checksum`/
`provenance_manifest_checksum` (both sha256 hex, participating in
`context_checksum`); `CalibrationInvocationRecord` gains
`worker_execution_context_checksum` (sha256 hex, participating in
`record_checksum`). **Persisted-artifact search**: repository-wide grep
for `megb-03h-calibration-record-v1`/`-v2` outside this module's own
source and tests, plus this repository's own gitignored local paths,
found nothing — no real persisted v1 or v2 `CalibrationRunContext`/
`CalibrationInvocationRecord`/`CalibrationTaskEvaluationRecord` artifact
exists anywhere, so no migration is performed or required (the same
no-migration determination every prior calibration-schema bump in this
project's history has made). A committed historical **safe** report
(any already-accepted `CalibrationSummaryReport` JSON under
`docs/measurement/`) is explicitly distinct from a resumable **typed
calibration record** — the former is point-in-time evidence already
accepted under its own schema version and is never "migrated"; only the
latter would ever require a migration path, and none exists. Stale-v2
records are rejected outright by the existing
`UnsupportedCalibrationSchemaVersionError` path (regression-tested).
**`CalibrationTaskEvaluationRecord` gains no new field** — audited and
determined explicit: its existing `contributing_invocation_content_checksums`
already binds each contributor's *entire* `record_checksum` at binding
time, and since `worker_execution_context_checksum` is now one of the
fields folded into that same `record_checksum`, any change to which
worker produced a given invocation changes `contributing_invocations_checksum`
on the task evaluation, which `reconcile_task_evaluation` (unchanged)
already rejects as "contributor content changed after binding" —
transitive content binding, not a redundant parallel histogram field
(regression-tested in `tests/test_distributed_calibration_provenance.py`).

**New `DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION`** (this table's
own row above): a fourth, independent `src/distributed/` schema family.
`DistributedProvenanceManifest` composes exclusively already-accepted
`src.distributed` types (`DistributedRunContext`, `WorkerExecutionContext`,
`MixedWorkerProvenanceSummary`, `QualificationIdentity`,
`evaluate_qualification_gate`'s own readiness/missing-dimensions,
`SafeRedactedSummary`) plus two new plain fields (`generation_command`,
`code_revision`) and the manifest's own wrapping/checksum/resolution
logic (`resolve_worker_context`). The **full** manifest is protected
operational/calibration evidence, never committed to a public report
path — only `safe_redacted_summary` and `manifest_checksum` are safe to
reference in any committed report.

**New `CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION`** (this table's own
row above): a fifth, independent `src/distributed/` schema family.
`CalibrationProvenanceReport` binds every fact a calling harness
measures/reconciles (manifest checksum, calibration run-context
checksum, participating worker-context checksums, safe topology
histogram, intended-vs-measured peak concurrency, invocation counts,
invocation-provenance-resolved/task-reconciliation-passed flags, the
manifest's own gate readiness/missing-dimensions) and derives
`readiness`/`blocker_reasons` purely from those facts — never
independently caller-settable. Readiness values:
`CALIBRATION_PROVENANCE_READY_FOR_3C`/`BLOCKED_CALIBRATION_PROVENANCE` —
neither implies GCP readiness or H.2C.3C credential-boundary readiness.
Measured peak concurrency is genuine evidence, never a caller-supplied
label: `measured_peak_concurrency > intended_concurrency`, or (under
`EnvironmentClass.PERSONAL_BOOTSTRAP`) `measured_peak_concurrency >
PERSONAL_BOOTSTRAP_MAX_WORKERS` (2), is rejected as a hard construction-
time error, never merely a blocked readiness.

**New `src/reference/distributed_provenance_reconciliation.py`** — the
only module in `src/reference/` permitted to import `src.distributed`
(no dependency-direction test forbids this direction; only the reverse,
`src/distributed` importing `src.reference`, remains forbidden and
unaffected). `reconcile_calibration_run_context`/
`reconcile_calibration_invocation_worker`/`reconcile_all_invocations`
verify a `CalibrationRunContext`'s/`CalibrationInvocationRecord`'s
distributed-provenance cross-reference checksums resolve against a real
`DistributedProvenanceManifest`.

No modification to `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION`,
`DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`, `RESULT_SCHEMA_VERSION`,
`CACHE_KEY_SCHEMA_VERSION`, or `AUDIT_RECORD_SCHEMA_VERSION` — all
confirmed unchanged. `ReferenceRunContext`, `ReferenceResultCacheKey`,
and `ReferenceAuditRecord` remain untouched, per this checkpoint's own
explicit scope (their distributed-production integration remains a
pre-H.2C.3F requirement, per the integration map's own summary table).

## MEGB-03H.2C.3B.3 correction addendum: `CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION` v1→v2, and the protected-manifest lock

This registry's own "MEGB-03H.2C.3B.3 addendum" above predates this
addendum; recorded here rather than by rewriting that prose, per this
project's established convention. This correction was authorized after
the original B.3 checkpoint report but before its acceptance.

**Why v2 exists (qualification-failure semantics).** The original v1
`CalibrationProvenanceReport.__post_init__` raised
`InvalidCalibrationProvenanceReportError` — a hard construction-time
error — whenever `measured_peak_concurrency` exceeded
`intended_concurrency` or, under `EnvironmentClass.PERSONAL_BOOTSTRAP`,
`PERSONAL_BOOTSTRAP_MAX_WORKERS` (2). This conflated two fundamentally
different things: a genuinely malformed/inconsistent report (wrong
schema version, tampered checksum, an invocation-count partition that
does not sum) versus a **structurally valid measurement that simply
fails a qualification criterion** — real evidence, a failed result, not
malformed data. Hiding a failed criterion behind a raised constructor
error also meant no safe, checksummed record of the failure could ever
be retained as negative evidence.

v2 adds three new closed `CalibrationProvenanceBlockerReason` members —
`MEASURED_CONCURRENCY_EXCEEDS_INTENDED`,
`MEASURED_CONCURRENCY_EXCEEDS_ADMITTED_TOPOLOGY` (measured concurrency
exceeding the admitted worker-topology size, i.e.
`len(participating_worker_context_checksums)` — a new check; v1 checked
only against `intended_concurrency`), and
`PERSONAL_CONCURRENCY_CEILING_EXCEEDED` — and folds all three
concurrency criteria into `_compute_blocker_reasons` alongside the
existing gate/provenance/reconciliation/count-partition checks. Each now
produces a valid, self-checksummed `BLOCKED_CALIBRATION_PROVENANCE`
report with the measured counts preserved, exactly like every other
qualification criterion. The `__post_init__` invariants that remain hard
construction errors are unchanged: unsupported schema version, tampered
`report_checksum`, a malformed/out-of-range count, and an invocation
count partition that does not sum to `admitted_invocation_count`.

**Persisted-artifact search and disposition.** Repository-wide grep for
`megb-03h2c3b3-calibration-provenance-report-v1` found exactly one real
persisted artifact pair:
`docs/measurement/megb-03h2c3b3-calibration-provenance-report.{json,md}`,
committed at `232d0af`. That v1 report is superseded by this
correction's regenerated v2 report at the same path (same underlying
synthetic evidence, re-derived under the v2 schema — the report content
does not otherwise change, since the original synthetic run's measured
concurrency never actually exceeded any bound). The superseded v1
content remains recoverable from git history at `232d0af` and is never
rewritten in place. A stale-v1-schema-version rejection test and a v2
round-trip test proving a `BLOCKED_CALIBRATION_PROVENANCE` report is
safely retained as negative evidence were both added to
`tests/test_calibration_provenance_report.py`.

**Protected-manifest lock (new `MANIFEST_LOCK_SCHEMA_VERSION`).** The
original B.3 checkpoint's own design explicitly stated the full
`DistributedProvenanceManifest` is "never persisted to any file — only
the safe report is written" (`docs/reference/megb-03h2c3b3-calibration-provenance-integration-design.md`).
This meant the committed safe report's `provenance_manifest_checksum`
field could never actually be verified against a real, persisted
artifact — a dangling checksum, contradicting this same design's own
stated principle that "a checksum without a persisted, verifiable
referenced manifest is insufficient." This correction implements the
already-established `src/reference/partition_lock.py` protected-artifact
pattern for the manifest: a new schema family,
`MANIFEST_LOCK_SCHEMA_VERSION` = `megb-03h2c3b3-distributed-provenance-manifest-lock-v1`
(`src/distributed/provenance_manifest_lock.py`) — the full manifest is
written under a gitignored `artifacts/privileged/distributed_provenance/`
path (explicitly labeled synthetic protected evidence, never real
HumanEval/candidate evidence); a small, committed, non-privileged lock
file at `artifacts/reference/distributed_provenance/calibration_provenance_manifest.lock.json`
anchors the protected artifact's identity via checksums, counts, and
generation provenance, without embedding the manifest's own bytes.
`DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION`'s own row above (still
`megb-03h2c3b3-distributed-provenance-manifest-v1`, unchanged — the
manifest's own field shape did not change, only where/how it is
persisted) is updated by this correction to reflect the new lock-backed
persistence path; see that row's own text for the current disposition.

No modification to `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION`,
`DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`, `CALIBRATION_SCHEMA_VERSION`,
`RESULT_SCHEMA_VERSION`, `CACHE_KEY_SCHEMA_VERSION`, or
`AUDIT_RECORD_SCHEMA_VERSION` — all confirmed unchanged by this
correction.
