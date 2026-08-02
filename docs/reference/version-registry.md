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

## Cache key: complete field list

`ReferenceResultCacheKey` (`cache_key.py`, schema `reference-result-cache-key-v2`):
`task_id`, `candidate_sha256`, `reference_case_checksum`, `dataset_version`,
`dataset_checksum`, `partition_version`, `task_manifest_checksum`,
`oracle_version`, `comparison_profile_version`, `evaluator_version`,
`execution_profile_id`, `execution_protocol_version` — 11 identity/checksum
fields plus the self-computed `key_digest`.
