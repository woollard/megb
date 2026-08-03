# MEGB-03H.1 — Calibration Design, Metadata Inventory, and Preregistration

## Status

Produced by MEGB-03H.1, under the "Approved MEGB-03H Planning Amendment
(Checkpoint Decomposition H.1–H.7)" (`tickets/megb-03.md`). Specification
and preregistration only: no canonical or candidate code was executed, no
Docker command was run, and no file under `src/`, `tests/`, execution
profiles, schemas, cache behavior, or workflows was modified. All sample
selection and budgets recorded here were frozen from measured aggregate
statistics and existing accepted identities alone — never from any
candidate outcome, since no candidate has been generated or evaluated at
any point in MEGB-01 through MEGB-03.

Assumptions are marked **[ASSUMPTION]** throughout and are kept separate
from **[MEASURED]** facts, per the Planning Amendment's own requirement.

## 1. Inventory: existing versions, locks, profiles, resource limits, safe metadata

**[MEASURED]**, re-confirmed by rereading source this checkpoint (values
unchanged from `docs/reference/version-registry.md`, produced in MEGB-03G.5):

| Identity | Value | Module |
|---|---|---|
| `RESULT_SCHEMA_VERSION` | `reference-result-schema-v4` | `result_schema.py` |
| `CACHE_KEY_SCHEMA_VERSION` | `reference-result-cache-key-v2` | `cache_key.py` |
| `CACHE_ENTRY_SCHEMA_VERSION` | `reference-result-cache-entry-v2` | `reference_cache.py` |
| `AUDIT_RECORD_SCHEMA_VERSION` | `reference-audit-record-v2` | `reference_audit.py` |
| `ORCHESTRATION_MODEL_SCHEMA_VERSION` | `reference-orchestration-v1` | `reference_orchestrator.py` |
| `EXECUTION_PROTOCOL_VERSION` | `reference-evaluator-execution-protocol-v1` | `reference_evaluator.py` |
| `EVALUATOR_VERSION_FULL` | `reference-evaluator-v1` | `reference_evaluator.py` |
| `EXECUTION_PROFILE_ID_FULL` | `docker-megb02-full-v1` | `reference_evaluator.py` |
| `FULL_EXECUTION_PROFILE.limits` | bare `ExecutionLimits()` default: 2.0s wall time, 256MB memory, 1.0 CPU, 32 processes, 64 open files, 65,536-byte stdout/stderr, 1,048,576-byte request/response, 16MB temp storage | `reference_evaluator.py` / `execution/protocol.py` — **never calibrated against the real corpus** |
| `EXECUTION_PROFILE_ID_REDUCED_DEV` / `EVALUATOR_VERSION_REDUCED_DEV` | `docker-megb02-reduced-dev-v1` / `reference-evaluator-reduced-dev-v1`, `wall_time_sec=1.0`, `max_cases_per_task=3` | `reference_evaluator.py` |
| `G4_EVALUATOR_VERSION` | `megb-03g4-benchmark-evaluator-v3` (current, post-conformance-correction) | `g4_benchmark_evaluator.py` |
| `G4_QUALIFICATION_REPORT_SCHEMA_VERSION` | `megb-03g4-qualification-report-v2` | `g4_qualification_report.py` |
| `ExecutionStatus` | `COMPLETED`/`SYNTAX_ERROR`/`CANDIDATE_EXCEPTION`/`TIMEOUT`/`OUT_OF_MEMORY`/`PROCESS_LIMIT`/`OUTPUT_LIMIT`/`PROTOCOL_ERROR`/`INFRASTRUCTURE_ERROR` | `execution/protocol.py` |
| `MeasurementStatus` | `VALID`/`INVALID_ORACLE`/`INVALID_INFRASTRUCTURE`/`INVALID_PROTOCOL`/`INCOMPLETE` | `result_schema.py` |

**Lock verification (read-only, from a clean process, this checkpoint):**

```
python -m src.reference.partition_cli verify
  primary_experiment_task_manifest: PASS
  reference_validation_task_manifest: PASS
  VERIFY PASSED: all privileged artifacts match partition.lock.json.

python -m src.reference.oracle_cli verify
  development_oracle: PASS
  reference_only_oracle: PASS
  reference_validation_only_oracle: PASS
  VERIFY PASSED: all privileged oracle artifacts match oracle.lock.json.
```

Both printed only checksums/booleans, per their own accepted docstrings ("never prints privileged case contents"). **`oracle_cli verify`'s own accepted implementation re-executes EvalPlus canonical solutions in-process (non-Docker) to regenerate a fresh oracle build for comparison against the lock** — this is the existing, already-accepted MEGB-03C verification design (not new code introduced by H.1), explicitly what "verify existing... oracle... locks read-only from a clean process" authorizes; it is not the kind of new, calibration-purpose candidate execution the Planning Amendment's "no canonical execution" prohibition targets for H.3 onward.

**`parity_cli verify` was attempted and deliberately stopped.** Its own implementation does not merely check identity/checksums — it executes the parity corpus's candidates through the real Docker backend (`docker_backend.py`'s `execute()`) to reverify classification agreement. Since H.1 must not run Docker, this command was not completed (it failed immediately on a missing local image tag, before any container ran, with no privileged content in the error). MEGB-03D's own parity corpus was already verified this way and accepted in its own already-completed checkpoint (commits `5d29992`/`dd81002`, per the ticket's MEGB-03D Completion Record: "3 Docker-marked tests... run and passed against the real corpus") — H.1 relies on that prior acceptance rather than re-running it.

## 2. The scoped privileged read

**Exact source read**: `artifacts/privileged/reference/oracle/reference_only_oracle.json`, located via the committed, non-privileged `oracle.lock.json`'s own `privileged_path` entry for `reference_only_oracle` (`load_oracle_lock_file()`, `src/reference/oracle_lock.py` — an existing, already-accepted loader). Read via `json.loads(path.read_text())`, the same raw-JSON operation `verify_oracle_against_lock` already performs internally, wrapped in the existing `unbounded_int_str_digits()` context manager (`src/reference/oracle.py`) to handle the corpus's genuinely large integers without disabling any safety property beyond what that already-accepted utility already does.

**Fields read per record**: `task_id` (public), `status`, and `expected_output`'s own `"type"` tag plus its serialized byte length. **Fields never read, printed, or persisted**: `case_id`, `provenance`, `comparison_profile_kind`, `failure_reason`, or any `expected_output` *value* beyond its type tag and byte length.

**Safe aggregate derived** (committed at `docs/measurement/megb-03h1-reference-evidence-statistics.json`, self-checksummed, schema `megb-03h1-reference-evidence-statistics-v1`, checksum `e42f7e1b638d33a7db056634b5a4c940ac7f18f6cb7357791b014ed9f322d821`):

- **[MEASURED]** 117,961 total records across 163 tasks, all `status="success"` (no unresolved oracle-generation failures in the reference-only pool).
- **[MEASURED]** output-type histogram: `bool`=21,771, `list`=30,057, `str`=21,747, `int`=33,580, `tuple`=5,141, `dict`=620, `none`=158, `float`=4,887.
- **[MEASURED]** overall serialized output-size distribution (bytes): min=27, p50=32, p90=300, p99=977, **max=40,426,656** (~40MB — substantially larger than the ~1MB figure `docs/measurement/privileged-artifact-policy.md`'s prose previously cited for the largest known case, confirming the true tail is more extreme than that earlier description).
- **[MEASURED]** per-task case counts range from 39 (`HumanEval/41`) to 1,060 (`HumanEval/50`); the distribution is skewed toward the high end (p50≈937, p90≈968).
- **[MEASURED]** the single largest output belongs to `HumanEval/130` (75 cases, max 40,426,656 bytes); `HumanEval/15` (95 cases, max 6,889,013 bytes) and `HumanEval/83` (69 cases, max 1,000,028 bytes — the "million-digit" task the existing policy doc already names) are the next largest.

No privileged content beyond these aggregates ever appeared in terminal output, the committed JSON, or this document. Task IDs are public HumanEval identifiers and are not privileged; case-level identity was never read at all in this analysis.

## 3. Frozen decision 1 — diagnostic calibration envelope

A new `ExecutionProfile`, distinct from `FULL_EXECUTION_PROFILE`/`REDUCED_DEV_EXECUTION_PROFILE`: `execution_profile_id="docker-megb03h-diagnostic-v1"`, `evaluator_version="megb-03h-diagnostic-evaluator-v1"`.

| Limit | Frozen value | Basis |
|---|---|---|
| `max_response_bytes` / `max_stdout_bytes` / `max_stderr_bytes` | **64 MB** (67,108,864 bytes) | **[MEASURED]**-grounded: comfortably above the confirmed 40,426,656-byte maximum observed output, avoiding right-censoring for every known case |
| `wall_time_sec` | 20.0s | **[ASSUMPTION]** — an order of magnitude above the current 2.0s default; no Docker-specific real-corpus timing exists yet (MEGB-03C's oracle generation is non-Docker, in-process, so it does not bound this) |
| `memory_mb` | 2048 | **[ASSUMPTION]** — order-of-magnitude headroom above the 256MB default |
| `cpu_count` | 1.0 | Unchanged from current default — no evidence yet suggesting otherwise |
| `max_processes` | 64 | **[ASSUMPTION]** — 2× current default |
| `max_open_files` | 128 | **[ASSUMPTION]** — 2× current default |
| `max_request_bytes` | 4 MB | **[ASSUMPTION]** — request payloads (`args`/`kwargs`) are small for HumanEval+-style calls; generous headroom, not evidence-driven |
| `temp_storage_mb` | 256 | **[ASSUMPTION]** — 16× current default; no evidence yet that HumanEval+ canonical solutions write to `/tmp` at all |

**Hard absolute ceiling** (never silently widened past this without an explicit, dated decision escalated to you, per the already-installed Amendment §3): `wall_time_sec≤120`, `memory_mb≤8192`, `max_response_bytes/max_stdout_bytes/max_stderr_bytes≤256MB`.

## 4. Frozen decision 2 — H.3 pilot

**Selection procedure**: deliberately chosen (not randomly sampled, given the small size) to span the two extremes the aggregate statistics identified as most consequential — minimum case count, maximum output size — plus one median-case-count task, before committing to the larger H.4 run.

**Frozen task set** (4 tasks, **[MEASURED]** case counts / max output sizes from §2's aggregate):

| Task | Case count | Max output (bytes) | Rationale |
|---|---|---|---|
| `HumanEval/41` | 39 | 45 | Minimum case count in the corpus — cheap baseline |
| `HumanEval/83` | 69 | 1,000,028 | The "million-digit" task already named in existing policy docs |
| `HumanEval/37` | 937 | 563 | Representative of the median case-count region (≈p50) |
| `HumanEval/130` | 75 | 40,426,656 | The single most extreme observed output — the diagnostic envelope's own most important early test |

**Invocation projection**: **[MEASURED]** 39+69+937+75 = **1,120 case invocations**, all sequential (concurrency=1 — correctness/feasibility signal first, throughput not yet at issue).

**Runtime ceiling**: **[ASSUMPTION]**, per the Planning Amendment's own formula, using G.4's accepted per-invocation floor (0.42s, evaluator v3, synthetic) as a conservative *lower*-bound placeholder pending H.3's own real measurement, with no marginal-cost term yet available (none has been measured against real cases): $1{,}120 \times 20.0\text{s (diagnostic-envelope worst-case assumption)} \times 3\text{× safety factor} = 67{,}200\text{s} \approx 18.7\text{ hours}$ **as an explicit, deliberately conservative ceiling** — not an expected duration. (Expected duration, using the 0.42s floor with no safety factor, would be ≈470s; the ceiling is set from the worst-case wall-time assumption specifically so a genuinely slow real case does not trigger a false abort.)

**Stop gates**: any invocation classified `TIMEOUT`/`OUT_OF_MEMORY`/`PROCESS_LIMIT`/`OUTPUT_LIMIT` against the diagnostic envelope is a finding requiring investigation before H.4 is authorized (does the diagnostic envelope itself need widening, per §3's escalation rule, or is this a genuine oracle-generation concern for MEGB-03C to review?) — not silently absorbed. Exceeding the runtime ceiling aborts the pilot and requires re-authorization, not a silent extension.

## 5. Frozen decision 3 — H.4 stratified calibration

**Stratification dimensions**: case count (low / median / high) crossed with max observed output size (low / moderate / high / extreme) — the two axes are only loosely correlated (confirmed: `HumanEval/130`, the extreme-output task, has a *low* case count of 75, not a high one), so both must be represented independently rather than assuming one predicts the other.

**Selection procedure and seed**: deterministic, not random — each stratum's representative(s) chosen as the task(s) closest to that stratum's defining statistic (min/median/p90/max), computed once from the frozen `docs/measurement/megb-03h1-reference-evidence-statistics.json` aggregate (itself checksummed) — reproducible by rerunning the selection rule against that one frozen input, no RNG seed needed since the procedure is a deterministic nearest-value selection, not a random sample.

**Frozen task set** (14 tasks, superset of H.3's 4): `HumanEval/41` (39, 45B), `HumanEval/1` (47, 1,143B), `HumanEval/106` (64, 7,210B), `HumanEval/83` (69, 1,000,028B), `HumanEval/37` (937, 563B), `HumanEval/152` (963, 491B), `HumanEval/108` (968, 28B), `HumanEval/50` (1,060, 437B), `HumanEval/38` (1,059, 642B), `HumanEval/130` (75, 40,426,656B), `HumanEval/15` (95, 6,889,013B), `HumanEval/139` (87, 261,864B), `HumanEval/27` (935, 1,149B), `HumanEval/96` (140, 59,024B).

**Invocation projection**: **[MEASURED]** sum of the above case counts = **6,538 case invocations**, run once at concurrency=1 and once at whichever concurrency G.4's own accepted levels (1/2/4) suggest is safe — reusing G.4's already-qualified concurrency ceiling rather than re-deriving one.

**Runtime ceiling**: **[ASSUMPTION]**, per the Amendment's formula, refreshed with H.3's own measured overhead once available (H.3's report freezes this number, per the Amendment's "no stage calculates its own expanded budget after exceeding the previous one" rule) — until then, the same conservative placeholder approach as §4, scaled: $6{,}538 \times 20.0\text{s} \times 3\text{×} \approx 392{,}280\text{s} \approx 4.5\text{ days}$ as a **worst-case, pre-H.3 ceiling only** — H.3's own actual measurement is expected to reduce this dramatically (at the 0.42s floor with a 1.5× factor once real data exists: $6{,}538 \times 0.42\text{s} \times 1.5 \approx 4{,}119\text{s} \approx 69\text{ minutes}$, a plausible expected order of magnitude, **not yet a measured fact**).

**Sample-level gates**: every hard gate in the already-installed Amendment §1 (canonical false rejection = 0, timeout/memory/process/output/temp-storage limits each individually satisfied, infrastructure-error rate below a predeclared ceiling, cleanup/isolation) — applied to **this 14-task sample only**, per the Amendment's explicit H.4-vs-H.5 scoping. Passing here authorizes freezing `EXECUTION_PROFILE_ID_FULL`/`EVALUATOR_VERSION_FULL` (v1→v2) and `FULL_EXECUTION_PROFILE.limits` in H.4 itself — the definitive, all-164 confirmation remains H.5's alone.

## 6. Frozen decision 4 — H.5 full-run design

**Full-run projection**: **[MEASURED]** 117,961 (reference-only pool, 163 tasks) + 12 (`HumanEval/39`'s separate exhaustive validation-only domain) = **117,973 case invocations** across all 164 tasks, one canonical candidate each.

**Staging identity**: a second `ReferenceResultCache` instance (reusing the existing, unmodified class — no new caching code), rooted at `artifacts/privileged/reference/h5_staging_cache/<calibration_run_id>/`, scoped to the full run-identity tuple (`calibration_run_id`, `execution_profile_id`, `evaluator_version`, `execution_protocol_version`, `dataset_version`/checksum, `partition_version`, `oracle_version`, `comparison_profile_version`) — a differently-identified run's staging directory is a sibling, never reused or resumed by this run.

**Complete-run gates**: 164/164 `MeasurementStatus.VALID` with `q_ref_task=1.0` (i.e. `Q_ref`-equivalent = 1.0 across the full run), zero limit-attributable `first_failure_category` (`TIMEOUT`/`RESOURCE_LIMIT`/`OUTPUT_LIMIT`) — cross-checked against the calibration trace's own `first_failure_category` field, not inferred from `MeasurementStatus` alone.

**Promotion-manifest design**: a small, durable JSON record (own schema, own checksum) at `artifacts/privileged/reference/h5_staging_cache/<calibration_run_id>/promotion_manifest.json`, listing the 164 approved target cache keys and, per key, a `promoted: bool` progress flag — updated (with its own atomic temp-file + rename write) immediately after each individual `cache.put()` succeeds during promotion, so an interrupted promotion's exact progress is durably recorded.

**Conflict preflight**: before promoting the first entry, every one of the 164 target keys is checked against the production cache (`cache.get()`, read-only) to confirm none currently resolves to a *different* valid entry; any such conflict halts promotion entirely before any write, per the Amendment's "conflicts stop promotion rather than overwrite data" rule.

**Resumable promotion semantics**: re-invoking promotion reads the manifest, skips every key already marked `promoted: true`, and continues from the first `promoted: false` entry — idempotent by construction, since re-attempting an already-promoted key's `cache.put()` is itself a no-op under the cache's own existing idempotent-identical-write behavior.

## 7. Frozen decision 5 — H.6 task subset and repeat count

**Subset**: derived from H.4's 14-task stratified sample, not identical to it — a smaller, deliberately chosen 6-task subset prioritizing the tasks most likely to reveal apparatus instability (the two output-size extremes, one high-output/low-case-count task, and one median-case-count task), keeping the $N \times \sum c_{\text{task}}$ cost proportionate to a "bounded spot-check" rather than comparable to the full run itself:

| Task | Case count | Max output (bytes) |
|---|---|---|
| `HumanEval/41` | 39 | 45 |
| `HumanEval/83` | 69 | 1,000,028 |
| `HumanEval/130` | 75 | 40,426,656 |
| `HumanEval/15` | 95 | 6,889,013 |
| `HumanEval/106` | 64 | 7,210 |
| `HumanEval/37` | 937 | 563 |

**[MEASURED]** $\sum c_{\text{task}} = 39+69+75+95+64+937 = 1{,}279$.

**Repeat count $N = 20$, frozen now** (per the corrected formula, Addendum I/III): total invocations $= N \times \sum c_{\text{task}} = 20 \times 1{,}279 = \mathbf{25{,}580}$ case-level invocations, and $20 \times 6 = 120$ complete task-evaluation records.

**Why $N=20$ is affordable here, unlike a naive full-stratified-sample repeat**: repeating the *full* 14-task H.4 sample 20 times would cost $20 \times 6{,}538 = 130{,}760$ invocations — more than H.5's entire 164-task/117,973-case run. The 6-task derived subset keeps H.6's cost at ≈22% of H.5's own volume, a proportionate "spot check," while still covering both output-size extremes and a representative median-case-count task — the dimensions requirement 9 actually cares about (task-classification stability under repetition), not exhaustive stratification breadth (H.4's own job).

## 8. Frozen decision 6 — H.6 runtime/compute ceiling and reduction rule

**Ceiling**: **[ASSUMPTION]**, pending H.4's own real marginal-cost measurement (which H.4's report will freeze, per the "no stage authorizes its own expanded budget" rule): pre-H.4, worst-case placeholder $25{,}580 \times 20.0\text{s} \times 1.5\text{×} \approx 767{,}400\text{s} \approx 8.9\text{ days}$; expected order of magnitude once real per-case cost is known (at G.4's 0.42s floor, no safety factor): $25{,}580 \times 0.42\text{s} \approx 10{,}744\text{s} \approx 3.0\text{ hours}$, **not yet a measured fact**.

**Reduction rule**: if H.4's own measurement shows the real ceiling is unaffordable, **H.1's own frozen $N$ and/or subset are revised at that point — by re-opening H.1's own decision, before H.6 executes** — never by observing H.6's own partial determinism results and adjusting afterward (the same integrity rule the Amendment already states for resource limits, applied here to repeat counts). Concretely: if reduction is needed, $N$ is reduced before the subset (repeat count is cheaper to defend reducing scientifically than sample breadth — per Addendum III's own reasoning that case-level breadth, not repeat count, is what tests the right scientific quantity); the subset is only reduced if $N$ alone cannot bring the projection under budget even at $N=5$ (the minimum repeat count still capable of a non-trivial sensitivity claim, per the corrected detection-probability table).

## 9. Frozen decision 7 — calibration-record schemas

**`CalibrationInvocationRecord`** (one case-level backend invocation/attempt): `calibration_schema_version`; `stage`; `calibration_run_id`; `task_id`; `case_ordinal` (an integer position within the task's case list — **not** the true `case_id`, since an ordinal carries no content signal beyond position and is preferred per the Amendment's own default); `task_evaluation_replicate_id`; `attempt_id`; `execution_status`; `measurement_status`; `first_failure_category`; `candidate_wall_time_sec` (`float | None`, quality `EXACT`, `unavailable_reason: TimingUnavailableReason | None` when `None`); `controller_wall_time_sec` (`float`, quality `EXACT`, always available); `observed_response_bytes`/`request_bytes` (`int | None`/`int`, quality `EXACT`, `unavailable_reason` on the former when `None`); `peak_memory_bytes`/`peak_process_count` (`int | None`, quality `EXACT` or `SAMPLED_WITH_KNOWN_ERROR` per H.2's own validation-matrix finding, populated only once H.2 exists); `exit_code`, `terminating_signal`, `backend_id`, `backend_version`, `runner_image_digest`, `invocation_id`, `invoked_at`; `record_checksum` (self-computed, auto-verified on read).

**`CalibrationTaskEvaluationRecord`** (one complete task/candidate/profile/replicate evaluation): `task_id`, `candidate_sha256`, context-identity checksum, `measurement_status`, `q_ref_task`, `first_failure_category`; `reference_case_total`/`reference_case_pass_count`; `work_item_disposition` (reusing `WorkItemDisposition`'s existing taxonomy); `contributing_invocation_ids` (tuple) and `contributing_invocations_checksum` (a single hash over that tuple, sorted, for tamper detection); `superseded: bool` (true for a partial attempt later replaced per the interruption rule); `record_checksum`.

**Identity relationships**: a `CalibrationTaskEvaluationRecord` is uniquely identified by `(stage, calibration_run_id, task_id, candidate_sha256, execution_profile_id, evaluator_version, task_evaluation_replicate_id)`; every `CalibrationInvocationRecord` it references shares that same tuple plus its own `case_ordinal`/`attempt_id`.

**Supersession rule**: an interrupted, incomplete task-replicate's records (both levels) are marked `superseded=true`, never deleted, and excluded from every `CalibrationSummaryReport` aggregation — the full re-execution that completes it is a new, distinct set of records under a fresh `attempt` generation, never merged with the superseded ones.

**Safe-summary projection**: `CalibrationSummaryReport` — per-task (public identifiers) aggregate case counts, resource-stat aggregates, pass/fail/disposition counts, measurement-quality-classification counts; overall aggregate; self-checksummed; excludes `superseded` records; never includes `case_ordinal`-level detail, raw telemetry values beyond aggregates, or any candidate/expected-output content.

## 10. Frozen decision 8 — trace-storage strategy

**Projected record volume** (**[MEASURED]** case-invocation counts from §§4–7, summed across every stage): H.3 (1,120) + H.4 (6,538, run at up to 2 concurrency levels ⇒ up to 13,076) + H.5 (117,973) + H.6 (25,580) ≈ **150,000–160,000 `CalibrationInvocationRecord`s**, plus a few hundred `CalibrationTaskEvaluationRecord`s, across the whole MEGB-03H.3–H.6 sequence.

**Chosen design: (b) append-only JSONL, one file per stage, with `flush()`+`fsync()` after every append, plus startup repair that verifies each record's checksum and truncates the file to the last verified newline before any further append.** Quantified rationale for choosing (b) over (a): at ≈150,000 records, one-immutable-file-per-record (design (a)) would create a comparable number of individual files, directory entries, and rename+fsync pairs — meaningful filesystem/inode overhead and an unwieldy number of tiny files for a human or tool to inspect, with no compensating benefit here (unlike the production cache, calibration-trace records are never looked up individually by a derived key — they are consumed by sequential scan/aggregation). Per-line `fsync()` overhead under design (b), by contrast, is negligible relative to the dominant cost: even a pessimistic 2ms/fsync × 150,000 ≈ 300 seconds of *total* fsync time across the *entire* multi-day calibration sequence, against a floor of tens of hours of actual container-invocation time (§§4–8's own projections) — several orders of magnitude smaller than the activity it accompanies. One file per stage (not one combined file) keeps each stage's own reconciliation trivially scoped without relying solely on in-record field filtering.

**Multi-process/multi-host writers remain out of scope**, per the Amendment — this design assumes single-process orchestration throughout, reusing the orchestrator's already-accepted `_io_lock` to serialize concurrent-execution writes into the single per-stage file.

## 11. Frozen decision 9 — telemetry-quality taxonomy

Exactly four values, as installed in the Amendment: `EXACT`, `SAMPLED_WITH_KNOWN_ERROR`, `BOUNDARY_ONLY`, `UNAVAILABLE_WITHOUT_CONTAMINATION`. Availability is modeled orthogonally: every telemetry field is `T | None`, paired with one quality tag (describing quality *when present*) and, where `None` is possible, a separate typed `unavailable_reason` (e.g. a small `TimingUnavailableReason`/`ResponseUnavailableReason` enum: `NEVER_STARTED` / `KILLED_BEFORE_COMPLETION` / `NO_RESPONSE_PRODUCED`). No fifth quality value exists anywhere in the schema.

## 12. Frozen decision 10 — H.2 feasibility matrix and hard stop criteria

Reused, unchanged in substance, from the already-installed Amendment §5 and the underlying addenda: H.2's own first output is a synthetic-probe validation matrix classifying peak-memory, peak-process-count, temp-storage, and response/request-byte telemetry into exactly one of the four values above, using probes with a known ground truth (not canonical solutions). **Hard stop criterion**: H.2 must produce this matrix and receive its own separate authorization before any canonical solution is executed (H.3) — only `EXACT`/`SAMPLED_WITH_KNOWN_ERROR`-classified metrics may feed the projection formulas in §§4–8 above; `BOUNDARY_ONLY`/`UNAVAILABLE_WITHOUT_CONTAMINATION` metrics are calibrated only via their own boundary characterization, never a formula.

## Unresolved decisions, deviations, and blockers

- **`parity_cli verify` was not completed** (§1) — not a blocker for H.1 itself (MEGB-03D's own prior Docker-based verification is relied on instead), but flagged so it isn't silently assumed re-verified by this checkpoint.
- **The diagnostic envelope's non-response-size limits (§3: `wall_time_sec`, `memory_mb`, `max_processes`, `max_open_files`, `max_request_bytes`, `temp_storage_mb`) are `[ASSUMPTION]`s, not measurements** — no Docker-specific real-corpus timing/resource telemetry exists yet; H.2's own synthetic-probe validation and H.3's own pilot are what will confirm or correct them.
- **All runtime ceilings in §§4, 6, and 8 that reuse G.4's 0.42s synthetic per-invocation floor are explicitly provisional** — they are the best currently-available anchor (an accepted, real measurement, but of synthetic trivial-output cases, not real HumanEval+ cases) and are expected to be superseded by H.3's own real measurement, per the Amendment's own stage-by-stage budget-freezing rule.
- **No blocker prevents H.2 from being authorized next**, on the basis of this checkpoint's own findings.
