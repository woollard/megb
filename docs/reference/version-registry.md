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

## Cache key: complete field list

`ReferenceResultCacheKey` (`cache_key.py`, schema `reference-result-cache-key-v2`):
`task_id`, `candidate_sha256`, `reference_case_checksum`, `dataset_version`,
`dataset_checksum`, `partition_version`, `task_manifest_checksum`,
`oracle_version`, `comparison_profile_version`, `evaluator_version`,
`execution_profile_id`, `execution_protocol_version` — 11 identity/checksum
fields plus the self-computed `key_digest`.
