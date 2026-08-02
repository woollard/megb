# Version and Provenance Registry (MEGB-03G)

## Status

Produced by MEGB-03G.5. Snapshot of every active accepted identity as of the
MEGB-03G.4 report-schema correction (commit `6e703d1`, qualification report
checksum `9f6e68865f829821ddd6651adf778b83f1cd195239f2a80b9b7ea4dcd1269879`).
This is a point-in-time registry, not a live document — re-derive from source
(`grep -n "_VERSION = " src/reference/*.py`) rather than trusting this file
after any later version bump.

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
| `AUDIT_RECORD_SCHEMA_VERSION` | `reference-audit-record-v2` | `reference_audit.py` | `ReferenceAuditRecord` field shape |
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
| `G4_EVALUATOR_VERSION` | `megb-03g4-benchmark-evaluator-v2` | `g4_benchmark_evaluator.py` | G.4 synthetic benchmark evaluator identity. **v1→v2**: v1's outputs carried incorrect `execution_protocol_version` provenance and must be distinguishable by version alone. |
| `G4_DATASET_VERSION` | `megb-03g4-synthetic-dataset-v1` | `g4_benchmark_evaluator.py` | Synthetic dataset identity — deliberately distinct from `HUMANEVAL_PLUS_VERSION` |
| `G4_PARTITION_VERSION` | `megb-03g4-synthetic-partition-v1` | `g4_benchmark_evaluator.py` | Synthetic partition identity — deliberately distinct from `PARTITION_ALGORITHM_VERSION` |
| `G4_ORACLE_VERSION` | `megb-03g4-synthetic-oracle-v1` | `g4_benchmark_evaluator.py` | Synthetic oracle identity — deliberately distinct from `ORACLE_ALGORITHM_VERSION` |
| `G4_COMPARISON_PROFILE_VERSION` | `megb-03g4-synthetic-comparison-v1` | `g4_benchmark_evaluator.py` | Synthetic comparison-profile identity — deliberately distinct from `COMPARISON_PROFILE_VERSION` |
| `G4_EXECUTION_PROFILE_ID` | `megb-03g4-benchmark-profile-v1` | `g4_benchmark_evaluator.py` | Synthetic execution-profile identity — deliberately distinct from `EXECUTION_PROFILE_ID_FULL` |
| `G4_REPORT_SCHEMA_VERSION` | `megb-03g4-throughput-report-v1` | `g4_benchmark.py` | Raw (non-privileged, gitignored) benchmark-report shape |
| `G4_QUALIFICATION_REPORT_SCHEMA_VERSION` | `megb-03g4-qualification-report-v2` | `g4_qualification_report.py` | Committed qualification-report shape. **v1→v2**: v1 derived `synthetic_workload_version` incorrectly (see below). |
| `BENCHMARK_PLAN_VERSION` | `megb-03g4-benchmark-plan-v1` | `g4_qualification_report.py` | The frozen G.4 benchmark plan's own identity (fixed, module-owned constant, never a caller-supplied parameter) |
| `SYNTHETIC_WORKLOAD_VERSION` | `megb-03g4-synthetic-workload-v1` | `g4_qualification_report.py` | The synthetic workload's own identity — **independent of `G4_EVALUATOR_VERSION`** (a prior version incorrectly set this field to the evaluator's version; fixed to be a separate, fixed, module-owned constant that cannot vary with the evaluator) |
| `SYNTHETIC_WORKLOAD_CHECKSUM_ALGORITHM_VERSION` | `megb-03g4-workload-checksum-algorithm-v1` | `g4_qualification_report.py` | Identifies how the workload content checksum below is canonicalized/hashed — a separate field from the checksum value itself |

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
| `report_checksum` (final, accepted) | `9f6e68865f829821ddd6651adf778b83f1cd195239f2a80b9b7ea4dcd1269879` | Every other qualification-report field, canonical JSON, sha256 — auto-recomputed and verified at construction (`G4QualificationReport.__post_init__`), never a caller-supplied value |
| `G4_DATASET_CHECKSUM` | `ecd5c87a63b86d0ff290f5a8f243668662da5047d0feac3b55625a40334ca4e6` | `sha256(b"megb-03g4-synthetic-dataset-content-v1")` — fixed synthetic constant, never colliding with any real `dataset_checksum` |
| `G4_TASK_MANIFEST_CHECKSUM` | `800231f3a168e18432ca35f64b202274ea0a695e52ccc3b213a650a96a126c4b` | `sha256(b"megb-03g4-synthetic-manifest-content-v1")` — fixed synthetic constant |
| `reference_case_checksum` | (per-case, includes `oracle_record.expected_output`) | `case_serialization.py` — bound into the cache key so a corrected canonical solution with the same case IDs but a different expected output is never invisible to the cache |
| `dataset_checksum` (real) | `DatasetProvenance.evalplus_dataset_hash` (32 chars, natively) | The real HumanEval+ corpus content |
| `manifest_checksum` (candidate-set) | sha256-hex | `ReferenceValidationCandidateSetManifest`'s own content |

**Note on the frozen-plan doc's illustrative pre-images:** the "Approved
MEGB-03G.4 Benchmark Plan (Frozen)" ticket section illustrates
`dataset_checksum`/`task_manifest_checksum` via `sha256("g4-benchmark-synthetic-dataset-v1")`/
`sha256("g4-benchmark-synthetic-manifest-v1")` — pre-images that differ from
what `g4_benchmark_evaluator.py` actually hashes
(`b"megb-03g4-synthetic-dataset-content-v1"`/`b"megb-03g4-synthetic-manifest-content-v1"`).
Found during this registry's compilation. Both are equally fixed, synthetic,
and non-colliding with any real corpus identity — this is a wording
mismatch between the ticket's illustrative prose and the implementation's
actual literal, not a functional, provenance, or security defect (nothing
consumes the pre-image string itself; only the resulting hex digest is ever
tested or compared). The **actual, implemented, currently-in-force** values
are the ones in this table.

## Cache key: complete field list

`ReferenceResultCacheKey` (`cache_key.py`, schema `reference-result-cache-key-v2`):
`task_id`, `candidate_sha256`, `reference_case_checksum`, `dataset_version`,
`dataset_checksum`, `partition_version`, `task_manifest_checksum`,
`oracle_version`, `comparison_profile_version`, `evaluator_version`,
`execution_profile_id`, `execution_protocol_version` — 11 identity/checksum
fields plus the self-computed `key_digest`.
