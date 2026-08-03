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

**Correction (post-provisional-acceptance review)**: the originally-recorded
18.7-hour (H.3) and 4.5-day (H.4) figures were conservative worst-case
*exposure* estimates, not acceptable hard runtime ceilings, and were at risk
of being read as authorizing a stage to actually run that long. §§4–8 below
now separate expected projection, worst-case exposure, an actual practical
hard ceiling (frozen from G.4's real measurements plus a bounded margin),
per-task ceilings, and circuit-breaker/cleanup rules. §3's diagnostic
envelope is corrected (`max_stdout_bytes`/`max_stderr_bytes` reduced from an
earlier, internally-inconsistent 64MB to 1MB, since they and
`max_response_bytes` all bound the same bundled response message and cannot
each independently claim 64MB without risking exceeding it). §12 adds
trace-persistence feasibility testing and the deferred parity-verification
gate to H.2. No number below reflects a candidate outcome — every figure is
derived from the same frozen `docs/measurement/megb-03h1-reference-evidence-statistics.json`
aggregate and from already-accepted G.4 measurements.

**Correction, round 2 (projection formula and local-ceiling decision)**: the
first correction's expected-runtime figures (39 min/3.8h/2.85 days/14.85h,
using a flat 5×-multiplier-over-the-floor heuristic) are replaced by a
concurrency-aware formula, `stage_time = invocation_count × per_invocation_time
÷ measured_concurrency_speedup`, using the accepted provisional baseline
(`0.418s/invocation`, concurrency=4, speedup≈2.296×), reported as four
scenarios (baseline 1×/moderate 1.5×/conservative 2×/stress 5×; the 5× case
is a stress scenario, not an expected runtime). The retained multi-day/hour
figures from the first correction are renamed **uncapped sequential timeout
exposure** and stated explicitly as neither a prediction nor a permissible
runtime. Practical hard ceilings are now frozen by explicit user decision
rather than derived from a margin multiplier: **H.3=1h, H.4=4h, H.5=12h,
H.6=4h** (≈8h total local budget accepted; AWS/cloud infrastructure not
currently required — H.5 breaching 8h materially, or trending toward 12h,
is an explicit stop-for-infrastructure-decision condition). §12's
trace-persistence overhead gate is also corrected: overhead is now compared
using H.2's own **measured mean** per-record latency against each stage's
own expected runtime and hard ceiling, not `p99 × record_count` against a
single borrowed stage; `p99≤50ms` remains a diagnostic only. This round
does not alter the frozen task sets, H.6's `N=20`/25,580-invocation count,
output-tail coverage, the H.2 parity-verification gate, privileged-read
boundaries, or the circuit-breaker classifications.

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
| `max_response_bytes` | **64 MB** (67,108,864 bytes) | **[MEASURED]**-grounded: `serialize_response` bundles `return_value` together with `stdout`/`stderr`/other fields into *one* wire message (`src/execution/wire.py`), so this must cover their sum, not the return value alone. Required margin, computed explicitly: confirmed max return-value size 40,426,656 bytes + tagged-JSON type-wrapper overhead (a few dozen bytes, negligible) + up to `max_stdout_bytes` (1MB, below) + up to `max_stderr_bytes` (1MB, below) + small envelope overhead for the remaining fields (`status`, `exception_type`/`message`, timing — all short strings/numbers) ≈ 42.4MB worst case, comfortably under the 64MB frozen value (≈1.5× margin over the worst-case sum, not just over the raw return value) |
| `max_stdout_bytes` / `max_stderr_bytes` | **1 MB** each (1,048,576 bytes) | **Corrected** from an earlier, internally-inconsistent 64MB (which would have let `max_response_bytes` be exceeded by a candidate producing both a maximal return value *and* maximal stdout/stderr simultaneously). Canonical solutions are pure computational functions with no expected reason to print; 1MB (16× the current 65,536-byte default) is generous headroom for any legitimate incidental output, and a canonical solution that actually needs more is itself a finding to investigate (`OUTPUT_LIMIT`), not something to silently accommodate at parity with the return-value channel |
| `wall_time_sec` | 20.0s | **[ASSUMPTION]** — an order of magnitude above the current 2.0s default; no Docker-specific real-corpus timing exists yet (MEGB-03C's oracle generation is non-Docker, in-process, so it does not bound this) |
| `memory_mb` | 2048 | **[ASSUMPTION]** — order-of-magnitude headroom above the 256MB default. The 64MB `max_response_bytes` ceiling above is confirmed to fit safely within this envelope with wide margin (2048MB / 64MB ≈ 32×), so no `BLOCKED_RESOURCE_PROFILE` is triggered by the response-size decision itself |
| `cpu_count` | 1.0 | Unchanged from current default — no evidence yet suggesting otherwise |
| `max_processes` | 64 | **[ASSUMPTION]** — 2× current default |
| `max_open_files` | 128 | **[ASSUMPTION]** — 2× current default |
| `max_request_bytes` | 4 MB | **[ASSUMPTION]** — request payloads (`args`/`kwargs`) are small for HumanEval+-style calls; generous headroom, not evidence-driven |
| `temp_storage_mb` | 256 | **[ASSUMPTION]** — 16× current default; no evidence yet that HumanEval+ canonical solutions write to `/tmp` at all |

**Hard absolute ceiling** (never silently widened past this without an explicit, dated decision escalated to you, per the already-installed Amendment §3): `wall_time_sec≤120`, `memory_mb≤8192`, `max_response_bytes≤256MB`, `max_stdout_bytes`/`max_stderr_bytes`≤16MB each.

**Rule if the measured tail cannot safely fit**: if any future measurement (during H.3/H.4) shows a real expected-output size that would not fit safely within `memory_mb`'s envelope even after widening `max_response_bytes` up to its own hard absolute ceiling above, H.2/H.3 must report `BLOCKED_RESOURCE_PROFILE` for that specific case rather than silently excluding it from the measured set or widening the memory envelope past its own hard ceiling without escalation.

**Correction (second round — projection formula, local hard ceilings, trace-overhead comparison)**: the first correction's projection numbers were rejected as written. This round replaces the projection formula and every derived expected/hard-ceiling figure in §§4–8, and corrects §12's trace-overhead comparison. It does **not** touch the frozen task sets, H.6's `N=20`/25,580-invocation count, output-tail coverage, the H.2 parity-verification gate, privileged-read boundaries, or the circuit-breaker classifications (consecutive-retry-exhausted and canonical-limit-attributable-failure thresholds) — all of those are carried forward unchanged from the first correction.

**Corrected projection formula**: $\text{stage\_time} = \text{invocation\_count} \times \text{per\_invocation\_time} \div \text{measured\_concurrency\_speedup}$, using the accepted provisional baseline **`per_invocation_time = 0.418`s/invocation, concurrency = 4, measured speedup ≈ 2.296×`** (G.4's own accepted clean-cache/concurrency benchmark — a real measurement of synthetic, trivial-computation cases, not yet real HumanEval+ cases). Four scenarios are reported by scaling `per_invocation_time` by a multiplier: **baseline (1×, the expected runtime)**, **moderate (1.5×)**, **conservative (2×)**, and **stress (5×)** — the 5× stress case is an explicit stress scenario for capacity planning, **not** an expected runtime.

**Scenario table** (all four stages; sanity-checked against baseline H.3≈3.4min, H.4≈20min, H.5≈6.0h, H.6≈1.3h):

| Stage | Invocations | Baseline (1×) — expected | Moderate (1.5×) | Conservative (2×) | Stress (5×) |
|---|---|---|---|---|---|
| H.3 | 1,120 | 203.9s ≈ **3.4 min** | 305.9s ≈ 5.1 min | 407.9s ≈ 6.8 min | 1,019.7s ≈ 17.0 min |
| H.4 | 6,538 | 1,191.2s ≈ **19.9 min** | 1,786.8s ≈ 29.8 min | 2,382.4s ≈ 39.7 min | 5,956.1s ≈ 1.65 h |
| H.5 | 117,973 | 21,477.6s ≈ **6.0 h** | 32,216.4s ≈ 8.95 h | 42,955.2s ≈ 11.93 h | 107,388.0s ≈ 29.83 h (≈1.24 days) |
| H.6 | 25,580 | 4,657.5s ≈ **1.29 h** | 6,986.3s ≈ 1.94 h | 9,315.0s ≈ 2.59 h | 23,287.5s ≈ 6.47 h |

**Uncapped sequential timeout exposure** (renamed from "conservative worst-case exposure" — the original per-stage multi-day/multi-hour figures computed as $\text{invocation\_count} \times 20.0\text{s (full diagnostic-envelope timeout)} \times 3\text{× safety factor}$, with no concurrency division, i.e. every invocation independently hitting its full timeout with no throughput benefit at all): H.3≈18.7h, H.4≈4.5 days, H.5≈81.9 days, H.6≈17.8 days. **These are neither predictions nor permissible runtimes** — they are a purely theoretical capacity-planning ceiling on the pathological case where every single invocation times out, retained only so infrastructure sizing has an honest upper bound to reason about; no stage is ever permitted to run anywhere near this duration.

**Frozen provisional local hard ceilings** (user-decided, not derived from the formula above): **H.3 = 1 hour, H.4 = 4 hours, H.5 = 12 hours, H.6 = 4 hours.** Per your decision, approximately eight hours of total local runtime is acceptable and AWS/cloud infrastructure is not currently required. **H.2 must replace every projection above with measured synthetic estimates before H.3 is authorized.** If H.2's (or H.3's/H.4's) real measurements cause H.5 to project materially above eight hours, or make a 12-hour outcome likely, that is a stop condition requiring an explicit infrastructure decision before H.5 proceeds — not a silent re-budgeting.

**Called-out risk, worth flagging explicitly**: at the accepted provisional baseline, H.5's own moderate (1.5×) scenario is already **8.95h — materially above the 8h acceptable figure** even though it remains under the 12h hard ceiling, and its conservative (2×) scenario (11.93h) is close enough to the 12h ceiling that a real per-invocation cost only modestly above baseline would trigger the stop-for-infrastructure-decision condition above. H.3's/H.4's own real measurements (not this provisional baseline) are what actually govern whether H.5 can proceed locally — this is exactly why H.2 must replace these projections with measured estimates before H.3, and why H.5 is not authorized merely because its baseline scenario looks comfortable.

**Refinement rule (unchanged in spirit from the first correction)**: earlier stages' real measurements may only *refine* — tighten, or loosen within the bounded margin implied by the moderate/conservative scenarios above — later stages' projections; they never silently relax a later stage's frozen hard ceiling. If a stage's real measured runtime would exceed its frozen hard ceiling, that stage stops and an amendment is requested before continuing or before the next stage is authorized.

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

**Expected runtime projection (baseline scenario, from the scenario table above)**: **[ASSUMPTION]** ≈203.9s ≈ **3.4 minutes**. Moderate/conservative/stress scenarios: ≈5.1 min / ≈6.8 min / ≈17.0 min (all per the corrected formula; see scenario table).

**Uncapped sequential timeout exposure** (capacity-planning only, not a runtime allowance): ≈18.7 hours (unchanged number, renamed per the correction above).

**Frozen local hard stage ceiling**: **1 hour (3,600s)** — user-decided, not derived from the formula above; ≈17.7× the baseline expected runtime, giving substantial margin for H.3 being the first real-corpus measurement while remaining a small fraction of the uncapped exposure figure. Must be replaced by H.2's own measured synthetic estimate before H.3 executes.

**Per-task ceiling** (formula unchanged: $\min(\text{stage ceiling}, \max(300\text{s}, \text{share of stage's total invocations} \times \text{stage ceiling} \times 1.5)) + \text{output-size buffer}$, where the buffer is $+300\text{s}$ if max output $>1\text{MB}$ and a further $+900\text{s}$ (i.e. $+1{,}200\text{s}$ total) if max output $>10\text{MB}$; recomputed here against the corrected 3,600s stage ceiling):

| Task | Share of stage invocations | Per-task ceiling |
|---|---|---|
| `HumanEval/41` | 39/1,120 | ≈300s (floor applies; ~5 min) |
| `HumanEval/83` | 69/1,120 | ≈633s (~10.5 min; includes +300s tail buffer) |
| `HumanEval/37` | 937/1,120 | **3,600s** (capped at the full stage ceiling — this task alone is 84% of H.3's cases, so it may legitimately consume the whole budget) |
| `HumanEval/130` | 75/1,120 | ≈1,562s (~26.0 min; includes +1,200s tail buffer for the 40,426,656B output) |

**Circuit breakers**: (a) 3 consecutive work items each individually reaching `WorkItemDisposition.RETRY_EXHAUSTED` (i.e., each already exhausted `RetryPolicy.max_attempts=3` on its own) aborts the whole stage as a systemic-infrastructure signal; (b) **1** canonical limit-attributable failure (`first_failure_category` ∈ `{TIMEOUT, RESOURCE_LIMIT, OUTPUT_LIMIT}`) stops the stage immediately — H.3's 4-task sample is too small to distinguish a fluke from a real signal, so any occurrence here is escalated rather than absorbed.

**Cooperative cancellation and cleanup**: on any ceiling breach (stage or per-task) or manual interrupt, reusing G.3's already-accepted `KeyboardInterrupt`-handling pattern: no new work item is dispatched; in-flight invocations are allowed to reach their own natural outcome (never hard-killed mid-write, so no trace record is left partially written), subject to their own existing per-invocation `wall_time_sec`/`_docker_kill()` path; the existing leftover-container check-and-cleanup (the same `always()`-scoped pattern from G.3/G.4) runs before exit; every record for work that started — complete or not — is durably persisted, with incomplete task-replicates marked `superseded=true` per §9, never silently discarded; the stage reports `ABORTED_CEILING_EXCEEDED` or `ABORTED_CIRCUIT_BREAKER` (not any variant of success) and requires explicit re-authorization before re-attempting.

**Stop gates**: any invocation classified `TIMEOUT`/`OUT_OF_MEMORY`/`PROCESS_LIMIT`/`OUTPUT_LIMIT` against the diagnostic envelope is a finding requiring investigation before H.4 is authorized (does the diagnostic envelope itself need widening, per §3's escalation rule, or is this a genuine oracle-generation concern for MEGB-03C to review?) — not silently absorbed. Exceeding the runtime ceiling aborts the pilot and requires re-authorization, not a silent extension.

## 5. Frozen decision 3 — H.4 stratified calibration

**Stratification dimensions**: case count (low / median / high) crossed with max observed output size (low / moderate / high / extreme) — the two axes are only loosely correlated (confirmed: `HumanEval/130`, the extreme-output task, has a *low* case count of 75, not a high one), so both must be represented independently rather than assuming one predicts the other.

**Selection procedure and seed**: deterministic, not random — each stratum's representative(s) chosen as the task(s) closest to that stratum's defining statistic (min/median/p90/max), computed once from the frozen `docs/measurement/megb-03h1-reference-evidence-statistics.json` aggregate (itself checksummed) — reproducible by rerunning the selection rule against that one frozen input, no RNG seed needed since the procedure is a deterministic nearest-value selection, not a random sample.

**Frozen task set** (14 tasks, superset of H.3's 4): `HumanEval/41` (39, 45B), `HumanEval/1` (47, 1,143B), `HumanEval/106` (64, 7,210B), `HumanEval/83` (69, 1,000,028B), `HumanEval/37` (937, 563B), `HumanEval/152` (963, 491B), `HumanEval/108` (968, 28B), `HumanEval/50` (1,060, 437B), `HumanEval/38` (1,059, 642B), `HumanEval/130` (75, 40,426,656B), `HumanEval/15` (95, 6,889,013B), `HumanEval/139` (87, 261,864B), `HumanEval/27` (935, 1,149B), `HumanEval/96` (140, 59,024B).

**Invocation projection**: **[MEASURED]** sum of the above case counts = **6,538 case invocations**, run once at concurrency=1 and once at whichever concurrency G.4's own accepted levels (1/2/4) suggest is safe — reusing G.4's already-qualified concurrency ceiling rather than re-deriving one.

**Expected runtime projection (baseline scenario)**: **[ASSUMPTION]**, provisional (superseded by H.3's own real measurement per the refinement rule above): ≈1,191.2s ≈ **19.9 minutes**. Moderate/conservative/stress: ≈29.8 min / ≈39.7 min / ≈1.65 h.

**Uncapped sequential timeout exposure** (capacity-planning only, not a runtime allowance): ≈4.5 days (unchanged number, renamed per the correction above).

**Frozen local hard stage ceiling**: **4 hours (14,400s)** — user-decided; ≈12× the baseline expected runtime. **Must be refined from H.3's actual measured per-invocation cost before H.4 executes.**

**Per-task ceiling** (same formula as §4, recomputed against the corrected `stage ceiling=14,400s`, `total stage invocations=6,538`):

| Task | Per-task ceiling | Task | Per-task ceiling |
|---|---|---|---|
| `HumanEval/41` | ≈300s (floor) | `HumanEval/108` | ≈3,200s |
| `HumanEval/1` | ≈300s (floor) | `HumanEval/130` | ≈1,500s (floor + incl. +1,200s tail buffer) |
| `HumanEval/106` | ≈300s (floor) | `HumanEval/15` | ≈614s (incl. +300s tail buffer) |
| `HumanEval/83` | ≈600s (floor + incl. +300s tail buffer) | `HumanEval/139` | ≈300s (floor) |
| `HumanEval/37` | ≈3,096s | `HumanEval/27` | ≈3,089s |
| `HumanEval/152` | ≈3,183s | `HumanEval/96` | ≈462s |
| `HumanEval/50` | ≈3,502s | `HumanEval/38` | ≈3,499s |

No single task in this 14-task stratified set reaches the stage cap (unlike H.3's `HumanEval/37`), since the largest single share here is ≈16% of the stage's total invocations; several small-case-count tasks now hit the 300s floor rather than a share-proportional value, since the corrected 14,400s stage ceiling is much smaller than the first correction's 57,600s figure.

**Circuit breakers**: (a) 3 consecutive `RETRY_EXHAUSTED` work items aborts the stage (same rule as §4); (b) **2** canonical limit-attributable failures stop the stage — one occurrence here is flagged and may be investigated without halting the larger run, but a second occurrence stops it (H.4 is a larger, more expensive stage than H.3, so a single fluke is given slightly more benefit of the doubt before aborting).

**Cooperative cancellation and cleanup**: identical to §4's rule — no new dispatch, in-flight invocations reach their own natural outcome, existing leftover-container cleanup runs before exit, all started work is durably recorded (with `superseded=true` for incomplete replicates), and the stage reports `ABORTED_CEILING_EXCEEDED`/`ABORTED_CIRCUIT_BREAKER` rather than success.

**Sample-level gates**: every hard gate in the already-installed Amendment §1 (canonical false rejection = 0, timeout/memory/process/output/temp-storage limits each individually satisfied, infrastructure-error rate below a predeclared ceiling, cleanup/isolation) — applied to **this 14-task sample only**, per the Amendment's explicit H.4-vs-H.5 scoping. Passing here authorizes freezing `EXECUTION_PROFILE_ID_FULL`/`EVALUATOR_VERSION_FULL` (v1→v2) and `FULL_EXECUTION_PROFILE.limits` in H.4 itself — the definitive, all-164 confirmation remains H.5's alone.

## 6. Frozen decision 4 — H.5 full-run design

**Full-run projection**: **[MEASURED]** 117,961 (reference-only pool, 163 tasks) + 12 (`HumanEval/39`'s separate exhaustive validation-only domain) = **117,973 case invocations** across all 164 tasks, one canonical candidate each.

**Expected runtime projection (baseline scenario)**: **[ASSUMPTION]**, provisional (superseded by H.3's and H.4's own real measurements per the refinement rule): ≈21,477.6s ≈ **6.0 hours**. Moderate/conservative/stress: ≈8.95 h / ≈11.93 h / ≈29.83 h (≈1.24 days) — see the "called-out risk" note above: the moderate and conservative scenarios are already close to or at the user's 8h/12h decision thresholds, so H.5 must not be authorized on this provisional baseline alone.

**Uncapped sequential timeout exposure** (capacity-planning only, not a runtime allowance): ≈81.9 days (unchanged number, renamed per the correction above; not previously stated under this name in the original submission).

**Frozen local hard stage ceiling**: **12 hours (43,200s)** — user-decided; this is the stage the user's explicit stop condition targets directly. **Must be refined from H.3's and H.4's actual measured costs before H.5 executes; if the refined projection is materially above 8 hours or the refined ceiling estimate makes 12 hours a likely outcome, H.5 stops for an explicit infrastructure decision (e.g., AWS) rather than running locally.**

**Per-task ceiling** (same formula as §§4-5, recomputed against the corrected `stage ceiling=43,200s`, `total stage invocations=117,973`; illustrative examples using the known extremes — the full 164-task table is computed mechanically from the frozen aggregate statistics file, not enumerated here): `HumanEval/130` (75 cases, 40,426,656B) ≈1,500s (floor + incl. +1,200s tail buffer); `HumanEval/15` (95 cases, 6,889,013B) ≈600s (floor + incl. +300s buffer); `HumanEval/83` (69 cases, 1,000,028B) ≈600s (floor + incl. +300s buffer); `HumanEval/50` (1,060 cases, the largest case count, 437B) ≈582s (~9.7 min, no buffer). No single task among 164 approaches the stage cap; several low-case-count tasks now hit the 300s floor before the tail buffer is added.

**Circuit breakers**: (a) 3 consecutive `RETRY_EXHAUSTED` work items aborts the stage (same rule as §§4-5); (b) **1** canonical limit-attributable failure stops the run immediately — H.5 is the definitive, all-164 gate, which already requires zero limit-attributable failures at completion (below); continuing a multi-day run after the very first occurrence would only waste time once that gate is already known to be violated.

**Cooperative cancellation and cleanup**: identical to §§4-5's rule. Staging-cache promotion (below) is unaffected by mid-run ceiling breaches, since promotion never begins until *after* the complete-run gate passes — an aborted run never reaches the promotion phase at all.

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

**Expected runtime projection (baseline scenario)**: **[ASSUMPTION]**, provisional (superseded by H.4's own real marginal-cost measurement, per the refinement rule): ≈4,657.5s ≈ **1.29 hours**. Moderate/conservative/stress: ≈1.94 h / ≈2.59 h / ≈6.47 h.

**Uncapped sequential timeout exposure** (capacity-planning only, not a runtime allowance): ≈17.8 days (unchanged number — computed with the same 3× safety factor used consistently across §§4-6 for like-for-like comparison; the original submission's H.6 figure had used a 1.5× factor, corrected here — renamed per the correction above).

**Frozen local hard stage ceiling**: **4 hours (14,400s)** — user-decided; ≈11× the baseline expected runtime. **Must be refined from H.4's actual measured marginal cost before H.6 executes.** Invocation count (`N=20 × Σc_task=25,580`) and repeat count are unchanged by this correction.

**Per-task ceiling** (same formula as §§4-6, applied to each task's total invocation count across all 20 repeats combined; recomputed against the corrected `stage ceiling=14,400s`, `total stage invocations=25,580`):

| Task | Total across 20 repeats | Per-task ceiling (total) | ≈ per-repeat average |
|---|---|---|---|
| `HumanEval/41` | 780 | ≈659s | ≈33s |
| `HumanEval/83` | 1,380 | ≈1,465s (incl. +300s tail buffer) | ≈73s |
| `HumanEval/130` | 1,500 | ≈2,467s (incl. +1,200s tail buffer) | ≈123s |
| `HumanEval/15` | 1,900 | ≈1,904s (incl. +300s tail buffer) | ≈95s |
| `HumanEval/106` | 1,280 | ≈1,081s | ≈54s |
| `HumanEval/37` | 18,740 | **14,400s** (capped at the full stage ceiling — this task alone is 73% of H.6's cases, so it may legitimately consume the whole budget) | ≈720s |

**Circuit breakers**: (a) 3 consecutive `RETRY_EXHAUSTED` work items aborts the stage (same rule as §§4-6); (b) **2** canonical limit-attributable failures stop the stage — H.6 exists specifically to probe determinism/instability, so a single occurrence is itself a finding worth allowing the run to continue briefly to see whether it recurs, but a second occurrence stops it rather than continuing indefinitely.

**Cooperative cancellation and cleanup**: identical to §§4-6's rule — a stage abort marks the in-progress replicate's records `superseded=true` (per §9) rather than merging a partial repeat with a later complete one.

**Reduction rule**: if H.4's own measurement shows the real ceiling is unaffordable, **H.1's own frozen $N$ and/or subset are revised at that point — by re-opening H.1's own decision, before H.6 executes** — never by observing H.6's own partial determinism results and adjusting afterward (the same integrity rule the Amendment already states for resource limits, applied here to repeat counts). Concretely: if reduction is needed, $N$ is reduced before the subset (repeat count is cheaper to defend reducing scientifically than sample breadth — per Addendum III's own reasoning that case-level breadth, not repeat count, is what tests the right scientific quantity); the subset is only reduced if $N$ alone cannot bring the projection under budget even at $N=5$ (the minimum repeat count still capable of a non-trivial sensitivity claim, per the corrected detection-probability table).

## 9. Frozen decision 7 — calibration-record schemas

**`CalibrationInvocationRecord`** (one case-level backend invocation/attempt): `calibration_schema_version`; `stage`; `calibration_run_id`; `task_id`; `case_ordinal` (an integer position within the task's case list — **not** the true `case_id`, since an ordinal carries no content signal beyond position and is preferred per the Amendment's own default); `task_evaluation_replicate_id`; `attempt_id`; `execution_status`; `measurement_status`; `first_failure_category`; `candidate_wall_time_sec` (`float | None`, quality `EXACT`, `unavailable_reason: TimingUnavailableReason | None` when `None`); `controller_wall_time_sec` (`float`, quality `EXACT`, always available); `observed_response_bytes`/`request_bytes` (`int | None`/`int`, quality `EXACT`, `unavailable_reason` on the former when `None`); `peak_memory_bytes`/`peak_process_count` (`int | None`, quality `EXACT` or `SAMPLED_WITH_KNOWN_ERROR` per H.2's own validation-matrix finding, populated only once H.2 exists); `exit_code`, `terminating_signal`, `backend_id`, `backend_version`, `runner_image_digest`, `invocation_id`, `invoked_at`; `record_checksum` (self-computed, auto-verified on read).

**`CalibrationTaskEvaluationRecord`** (one complete task/candidate/profile/replicate evaluation): `task_id`, `candidate_sha256`, context-identity checksum, `measurement_status`, `q_ref_task`, `first_failure_category`; `reference_case_total`/`reference_case_pass_count`; `work_item_disposition` (reusing `WorkItemDisposition`'s existing taxonomy); `contributing_invocation_ids` (tuple) and `contributing_invocations_checksum` (a single hash over that tuple, sorted, for tamper detection); `superseded: bool` (true for a partial attempt later replaced per the interruption rule); `record_checksum`.

**Identity relationships**: a `CalibrationTaskEvaluationRecord` is uniquely identified by `(stage, calibration_run_id, task_id, candidate_sha256, execution_profile_id, evaluator_version, task_evaluation_replicate_id)`; every `CalibrationInvocationRecord` it references shares that same tuple plus its own `case_ordinal`/`attempt_id`.

**Supersession rule**: an interrupted, incomplete task-replicate's records (both levels) are marked `superseded=true`, never deleted, and excluded from every `CalibrationSummaryReport` aggregation — the full re-execution that completes it is a new, distinct set of records under a fresh `attempt` generation, never merged with the superseded ones.

**Safe-summary projection**: `CalibrationSummaryReport` — per-task (public identifiers) aggregate case counts, resource-stat aggregates, pass/fail/disposition counts, measurement-quality-classification counts; overall aggregate; self-checksummed; excludes `superseded` records; never includes `case_ordinal`-level detail, raw telemetry values beyond aggregates, or any candidate/expected-output content.

## 10. Frozen decision 8 — trace-storage strategy

**Projected record volume** (**[MEASURED]** case-invocation counts from §§4–7, summed across every stage): H.3 (1,120) + H.4 (6,538, run at up to 2 concurrency levels ⇒ up to 13,076) + H.5 (117,973) + H.6 (25,580) ≈ **150,000–160,000 `CalibrationInvocationRecord`s**, plus a few hundred `CalibrationTaskEvaluationRecord`s, across the whole MEGB-03H.3–H.6 sequence.

**Chosen design: (b) append-only JSONL, one file per stage, with `flush()`+`fsync()` after every append, plus startup repair that verifies each record's checksum and truncates the file to the last verified newline before any further append.** Quantified rationale for choosing (b) over (a): at ≈150,000 records, one-immutable-file-per-record (design (a)) would create a comparable number of individual files, directory entries, and rename+fsync pairs — meaningful filesystem/inode overhead and an unwieldy number of tiny files for a human or tool to inspect, with no compensating benefit here (unlike the production cache, calibration-trace records are never looked up individually by a derived key — they are consumed by sequential scan/aggregation). Per-line `fsync()` overhead under design (b), by contrast, is directionally small relative to the corrected expected-runtime figures in §§4–8/the intro scenario table (a pessimistic 2ms/fsync × 150,000 ≈ 300 seconds total, against a combined baseline expected runtime on the order of a day across all four stages) — but this directional estimate is illustrative only; **§12's corrected trace-persistence feasibility gate (measured mean latency ≤9.1ms/record, compared per-stage against that stage's own expected runtime and hard ceiling) is the authoritative acceptance check**, not this paragraph's illustrative 2ms figure. One file per stage (not one combined file) keeps each stage's own reconciliation trivially scoped without relying solely on in-record field filtering.

**Multi-process/multi-host writers remain out of scope**, per the Amendment — this design assumes single-process orchestration throughout, reusing the orchestrator's already-accepted `_io_lock` to serialize concurrent-execution writes into the single per-stage file.

## 11. Frozen decision 9 — telemetry-quality taxonomy

Exactly four values, as installed in the Amendment: `EXACT`, `SAMPLED_WITH_KNOWN_ERROR`, `BOUNDARY_ONLY`, `UNAVAILABLE_WITHOUT_CONTAMINATION`. Availability is modeled orthogonally: every telemetry field is `T | None`, paired with one quality tag (describing quality *when present*) and, where `None` is possible, a separate typed `unavailable_reason` (e.g. a small `TimingUnavailableReason`/`ResponseUnavailableReason` enum: `NEVER_STARTED` / `KILLED_BEFORE_COMPLETION` / `NO_RESPONSE_PRODUCED`). No fifth quality value exists anywhere in the schema.

## 12. Frozen decision 10 — H.2 feasibility matrix and hard stop criteria

Reused, unchanged in substance, from the already-installed Amendment §5 and the underlying addenda: H.2's own first output is a synthetic-probe validation matrix classifying peak-memory, peak-process-count, temp-storage, and response/request-byte telemetry into exactly one of the four values above, using probes with a known ground truth (not canonical solutions). **Hard stop criterion**: H.2 must produce this matrix and receive its own separate authorization before any canonical solution is executed (H.3) — only `EXACT`/`SAMPLED_WITH_KNOWN_ERROR`-classified metrics may feed the projection formulas in §§4–8 above; `BOUNDARY_ONLY`/`UNAVAILABLE_WITHOUT_CONTAMINATION` metrics are calibrated only via their own boundary characterization, never a formula.

**Added by this correction, and corrected in the second round below — trace-persistence feasibility test (new required H.2 output, gating §10's chosen design before it is trusted at scale)**: a synthetic-only test (no canonical execution) that (a) appends a volume of fabricated `CalibrationInvocationRecord`s via the exact production code path (`_io_lock`-serialized JSONL append + `flush()`+`fsync()`) at concurrency=1 and at each concurrency level planned for H.4/H.5, measuring per-record append+fsync latency (mean and p50/p90/p99/max) and the resulting projected total overhead at the full projected volume (≈150,000-160,000 records, per §10); (b) deliberately truncates the trace file mid-record to simulate a crash, then confirms startup repair truncates to the last verified newline, a subsequent checksum-verification pass reports 100% valid on all remaining records, and resumption produces zero duplicate `CalibrationTaskEvaluationRecord`s (checked via the identity tuple in §9).

**Corrected acceptance gate (second round)**: the first round's gate computed total overhead as `p99_latency × record_count`, which mischaracterizes p99 (a tail statistic) as if it were the typical per-record cost — overstating projected overhead by treating a rare-case latency as the average case. **Corrected**: projected overhead per stage is `mean_measured_latency × stage_record_count` (using H.2's own measured **mean** append+fsync latency, not p99), compared against that **same stage's own expected runtime and hard ceiling** — not against a single stage borrowed as a stand-in for all four. `p99 ≤ 50ms` is retained as a separate tail-latency **diagnostic** (a sanity check that no individual append is pathologically slow) and plays no role in the overhead-total computation.

Because expected runtime is linear in record count under the corrected formula above (`expected_runtime / record_count = per_invocation_time / speedup = 0.418s / 2.296 ≈ 0.182s`, a constant identical across H.3–H.6), a proportional gate of "≤5% of expected runtime" reduces to the **same mean-latency threshold for every stage: ≤9.1ms/record**. Checked independently against each stage's hard ceiling (a looser, secondary bound: H.3 ≤160.7ms/record, H.4 ≤110.1ms/record, H.5 ≤18.3ms/record, H.6 ≤28.2ms/record), the binding constraint remains the expected-runtime-based **9.1ms/record**, since it is tighter than all four ceiling-based bounds. **Frozen acceptance gate**: mean per-record append+fsync latency ≤ **9.1ms** (primary, binding — derived from 5% of expected runtime, uniform across stages), **and** p99 per-record latency ≤50ms (diagnostic only). If the mean-latency gate is exceeded, H.2 must stop and report `BLOCKED_TRACE_PERSISTENCE_OVERHEAD` and propose an alternative durable representation (e.g. batched fsync with an explicitly bounded and disclosed at-most-K-records-lost-on-crash tradeoff, or design (a)'s per-record immutable files) before H.3 is authorized — §10's chosen design (b) is provisional until this test passes.

**Added by this correction — response-boundary-probe and output-tail coverage confirmation**: H.2's synthetic response-boundary probes must cover ordinary sizes (matching §2's p50≈32B/p90≈300B/p99≈977B distribution), sizes immediately below and above `max_response_bytes` (64MB) to confirm the boundary is enforced in both directions, and explicitly the measured 40,426,656-byte tail plus its full envelope/serialization margin (the ≈42.4MB worst-case sum computed in §3), confirmed reachable within the 64MB limit. Confirmed already true by the existing frozen task sets (no task-set change required): `HumanEval/130` (the max-output task, 40,426,656B) is in both H.3 (§4) and H.4 (§5); `HumanEval/15` (6,889,013B) and `HumanEval/83` (1,000,028B) are in H.4 as the other representative high-percentile-output tasks; `HumanEval/139` (261,864B) is also in H.4 for moderate-large coverage. §3's `BLOCKED_RESOURCE_PROFILE` fallback rule remains the answer if a real measured tail cannot safely fit even at the hard absolute ceiling.

**Added by this correction — deferred parity verification becomes a required pre-canonical H.2 gate**: `parity_cli verify` (§1's documented H.1 deviation, not run during H.1 since it executes Docker) must be run and must PASS during H.2, before H.3 is authorized — using only the existing public, frozen parity corpus, never canonical-source or `reference_only_oracle` content (a boundary parity's own design already respects, since its own privileged artifact is the separate `parity_results.json`). This supersedes reliance on MEGB-03D's prior acceptance (commits `5d29992`/`dd81002`) as sufficient on its own; that prior result remains valid evidence, but a fresh pass is now required before canonical execution begins. Failure blocks H.3 until resolved.

## Unresolved decisions, deviations, and blockers

- **`parity_cli verify` was not completed during H.1** (§1) — **no longer merely relied-upon via MEGB-03D precedent; per the first correction, it is now a required H.2 gate (§12) that must PASS before H.3 is authorized.** Unchanged by the second (formula/ceiling) correction round.
- **The diagnostic envelope's non-response-size limits (§3: `wall_time_sec`, `memory_mb`, `max_processes`, `max_open_files`, `max_request_bytes`, `temp_storage_mb`) are `[ASSUMPTION]`s, not measurements** — no Docker-specific real-corpus timing/resource telemetry exists yet; H.2's own synthetic-probe validation and H.3's own pilot are what will confirm or correct them.
- **All scenario-table figures and per-task ceilings in §§4-6 and 8 that use G.4's 0.418s/invocation floor and the accepted concurrency-4/≈2.296× speedup baseline are explicitly provisional** — they are the best currently-available anchor (an accepted, real measurement, but of synthetic trivial-output cases, not real HumanEval+ cases). H.2 must replace them with measured synthetic estimates before H.3; H.3's own real measurement then refines H.4/H.5/H.6 in turn, per the refinement rule preceding §4.
- **The frozen local hard ceilings (H.3=1h, H.4=4h, H.5=12h, H.6=4h) are a user decision, not derived from the formula** — they stand independent of whatever the formula projects, but H.5 in particular carries an explicit stop-for-infrastructure-decision condition if real measurements push its projection materially above 8h or make 12h a likely outcome (see the "called-out risk" note preceding §4 and §6's own ceiling entry).
- **§10's chosen trace-storage design (append-only JSONL, fsync-per-line) is provisional until H.2's new trace-persistence feasibility test (§12) passes its corrected, mean-latency-based acceptance gate (≤9.1ms/record, with p99≤50ms retained as a diagnostic only)** — if it does not, H.2 must stop `BLOCKED_TRACE_PERSISTENCE_OVERHEAD` and propose an alternative before H.3.
- **No blocker prevents H.2 from being authorized next**, on the basis of this checkpoint's own findings — H.2 itself now carries three hard gates (telemetry-classification matrix, corrected trace-persistence feasibility, parity re-verification) that must all pass before H.3, plus the standing obligation to replace every provisional projection above with a measured estimate.
