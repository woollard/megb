# MEGB-03H.2C.2B — Real-Docker Telemetry Measurement Plan (Frozen Draft)

## Status

**Drafted and frozen by MEGB-03H.2C.2A. Not executed.** Execution of this
plan requires its own, separate authorization (MEGB-03H.2C.2B). No real
Docker execution, canonical/candidate experiment execution, or
execution-profile freeze occurs anywhere in H.2C.2A, including in the
production of this document.

This plan is preregistered — every threshold and READY/BLOCKED criterion
below is fixed *before* any real-Docker measurement is taken, per the
same integrity discipline already established for the G.4 benchmark plan
and the H.1 calibration design (`docs/reference/megb-03h1-calibration-design.md`).
If H.2C.2B's own real measurements make any of these thresholds
untenable, the correct response is to reopen this plan under a new,
explicit authorization before proceeding — never to relax a criterion
after seeing results that would otherwise fail it.

## 1. Open precondition carried in from the H.2C.2A provenance audit

`docs/reference/megb-03h2c2a-collector-provenance-audit.md` found that
the accepted H.2A persisted calibration schema cannot yet bind collector
method/version, sampling interval, or host/interface metadata to a
measurement. **H.2C.2B must resolve this precondition — either by an
explicitly authorized schema extension, or an explicit decision that
per-invocation provenance need not persist — before any measurement
taken under this plan is treated as reproducible calibration evidence.**
This plan's own committed report (§9) will record execution-layer
telemetry (including `method_identity`) regardless, so the evidence
exists; whether it is additionally persisted into
`CalibrationInvocationRecord` is what remains open.

## 2. Host and Docker-runtime metadata to record

Collected once per measurement run (not per invocation, since it is
expected constant within one run), via
`RealHostCapabilityProbe.host_runtime_metadata()` plus:

- kernel release (`platform.release()`);
- Docker server version;
- cgroup driver (`systemd`/`cgroupfs`), when resolvable;
- cgroup version in effect (v2 assumed; v1 hosts are expected to report
  `UNAVAILABLE_WITHOUT_CONTAMINATION` for both exact methods and fall
  through to the sampled methods — a specific finding to confirm, not
  assume);
- host OS/architecture summary (matching the level of detail already
  committed in `docs/measurement/megb-03g4-qualification-report.md`'s
  own host/platform summary field — never anything more granular).

Never recorded: full `docker info`/`docker version` JSON dumps, environment
variables, filesystem paths beyond the resolved cgroup peak-file paths
themselves (which are host configuration facts, not privileged content).

## 3. Collector methods and version identifiers under test

Exactly the methods H.2C.2A implemented, exercised in frozen precedence
order (`TelemetryCollectorFactory`):

| Metric | Method (in precedence order) | Version |
|---|---|---|
| Memory | `CGROUP_V2_MEMORY_PEAK` → `SAMPLED_DOCKER_STATS_MEMORY` → `UNAVAILABLE_WITHOUT_CONTAMINATION` | `cgroup_peak_file_collector/v1` / `sampled_polling_collector/v1` |
| Process count | `CGROUP_V2_PIDS_PEAK` → `SAMPLED_DOCKER_TOP_PROCESS_COUNT` → `UNAVAILABLE_WITHOUT_CONTAMINATION` | `cgroup_peak_file_collector/v1` / `sampled_polling_collector/v1` |

Whichever method the real host resolves to is what the run measures —
this plan does not force a particular method; it records and reports
whichever the frozen precedence actually selects, and treats a
capability-probe outcome as a finding, not a parameter to tune.

## 4. Sampling intervals

For any invocation where a sampled method is selected:
`memory_sampling_interval_sec = 0.05`, `process_count_sampling_interval_sec = 0.05`
(50ms) — an order of magnitude finer than the shortest diagnostic-envelope
`wall_time_sec` (2.0s default) so at least ~40 samples are taken per
invocation even at the shortest observed durations. Existence-wait bounds:
`existence_poll_interval_sec = 0.02`, `existence_wait_max_sec = 2.0`
(container creation is expected to resolve in well under 100ms locally;
2s gives ample margin without risking a materially-delayed sample start).

## 5. Synthetic candidate workloads

Reusing the established G.4 principle (synthetic, non-canonical,
benchmark-only workloads with their own distinct identity constants,
structurally non-contaminating per the same proof pattern as
`g4_benchmark_evaluator.py`) — but purpose-built here to have a **known
ground truth** for telemetry accuracy, which G.4's throughput workload
did not need:

- **`memory_allocator` candidate**: allocates and holds a fixed,
  parameterized number of bytes (e.g. 32MiB, 128MiB) for the duration of
  a controlled sleep, then releases and returns. Ground truth: peak
  memory usage should be at least the allocated amount plus interpreter/
  runner overhead (measured separately via a zero-allocation baseline
  candidate).
- **`process_spawner` candidate**: spawns a fixed, parameterized number
  of short-lived child processes (e.g. 1, 4, 16), each sleeping briefly
  and exiting. Ground truth: peak process count should be at least the
  spawned count plus the runner's own baseline process count.
- **`baseline` candidate**: returns immediately, no extra allocation or
  processes — establishes the runner's own fixed memory/process-count
  floor, subtracted from the above two before comparing to ground truth.
- **`late_peak` candidate** (added by the H.2C.2A provenance/schema
  correction, targeting the exactness/terminal-coverage gap that
  correction fixed): allocates a small baseline amount, sleeps briefly,
  then — as close as controllable to the candidate process's own exit —
  allocates a second, larger, distinctly-sized spike immediately before
  returning. Ground truth: the true peak must reflect the *late* spike,
  not the earlier baseline. This is the synthetic workload specifically
  designed to probe the teardown race `CgroupPeakFileCollector`'s
  `confirm_terminal_state` check now guards against: run once with the
  real confirmation wired in (expect `EXACT`, value including the late
  spike) and once with a deliberately-broken/always-false confirmation
  callable substituted (expect a forced `BOUNDARY_ONLY` downgrade per
  the schema correction's own hard invariant) — both legs must still
  report the *same* underlying value; only the quality/terminal-coverage
  classification may differ.

None of these candidates touch canonical HumanEval+ content; all four
get their own distinct, synthetic identity constants (mirroring
`G4_EVALUATOR_VERSION` etc.), never colliding with any real profile/
evaluator/dataset identity, verified the same way G.4's own synthetic
identities were (`assert_g4_identities_are_synthetic`-style check).

## 6. Execution statuses exercised

The full matrix already proven offline in H.2C.2A
(`test_docker_backend_telemetry_integration.py`,
`test_collector_lifecycle_coverage.py`), now re-run against real Docker:
`COMPLETED`, `SYNTAX_ERROR`, `CANDIDATE_EXCEPTION`, `OUTPUT_LIMIT`,
`PROCESS_LIMIT`, `PROTOCOL_ERROR`, `TIMEOUT`, `OUT_OF_MEMORY`,
`INFRASTRUCTURE_ERROR` (container-never-created and malformed-response
sub-cases), plus a cooperative-cancellation (`KeyboardInterrupt`) run.

## 7. Paired telemetry-disabled/enabled ordering (balanced AB/BA)

For each (workload, status-scenario, concurrency-level) configuration,
run **N=8** paired invocations: 4 pairs run telemetry-disabled-then-enabled
(AB) and 4 pairs run telemetry-enabled-then-disabled (BA), interleaved,
not blocked — cancels any systematic ordering effect (e.g. host caching,
thermal throttling) from confounding the overhead measurement, the same
concern the G.4 benchmark's own calibration-then-sweep design already
guards against.

## 8. Repetition counts and concurrency levels

- Repetition: N=8 paired runs per configuration (§7), matching the
  already-accepted G.4 per-configuration N.
- Concurrency levels: **1, 2, 4** — identical to the already-accepted
  G.3/G.4/H concurrency levels; no new level introduced.
- Total configurations: 3 candidates × ~4 status-relevant scenarios ×
  3 concurrency levels ≈ 36 configurations × 8 paired runs × 2 legs =
  576 case invocations (unscaled) — small enough to complete well within
  a diagnostic pilot budget, deliberately far below H.3's own 1,120-
  invocation floor.

## 9. Exact noninterference tests (re-verified against real Docker)

Re-run, against real Docker rather than the fake harness, exactly the
categories H.2C.1 already proved offline:

- collector/cleanup failure never changes `CandidateExecutionResult.status`
  or `.return_value`;
- a failure on one metric's collector never corrupts the sibling metric's
  telemetry fields;
- `execute()` (telemetry-disabled) and `execute_with_telemetry()` agree on
  every classification field (already proven offline in
  `test_execute_and_execute_with_telemetry_agree_on_every_classification_field`;
  re-confirmed here is that this agreement holds against a *real*
  container, not only the fake harness).

## 10. Overhead statistics and thresholds (proposed before seeing results)

**Methodology, matching §12 of the H.1 calibration design's own
trace-persistence gate rather than an arbitrary percentage:** the
accepted concurrency-aware projection formula is
`stage_time = invocation_count × per_invocation_time ÷ measured_concurrency_speedup`,
with accepted baseline `per_invocation_time = 0.418s`, concurrency=4,
speedup≈2.296×. The trace-persistence gate already established the
precedent of bounding a *different* per-invocation overhead source
(JSONL append+fsync) at **5% of expected runtime**, reducing to a
uniform ≤9.1ms/record threshold. Telemetry-collection overhead is a
second, independent overhead source competing for the same per-invocation
budget, so this plan applies the *same* 5% figure to it rather than
inventing a new one:

- **Primary, binding gate**: mean added wall-clock overhead per
  invocation (telemetry-enabled minus telemetry-disabled, from the
  paired AB/BA runs) ≤ **5% of 0.418s ≈ 20.9ms**, uniform across every
  stage for the same reason the trace-persistence gate's bound is
  uniform (the projection formula is linear and stage-independent in
  per-invocation cost).
- **Secondary, looser, diagnostic-only bound**, checked against each
  stage's own hard ceiling directly: H.3 ≤ 160.7ms/invocation, H.4 ≤
  110.1ms/invocation, H.5 ≤ 18.3ms/invocation, H.6 ≤ 28.2ms/invocation
  (identical figures to the trace-persistence gate's own per-stage
  bounds, since both are derived from the same 5%-of-ceiling
  calculation over the same accepted baseline).
- **Combined-overhead flag (diagnostic only, not itself a gate)**: since
  trace-persistence and telemetry-collection overhead are independent
  and additive, their sum is reported alongside the individual figures;
  a combined overhead approaching 10% of `per_invocation_time` is noted
  as a risk to the H.5 stop-for-infrastructure-decision condition even
  if both individual gates pass.
- p99 per-invocation overhead ≤ 50ms, retained as a diagnostic only —
  mirroring the trace-persistence gate's own p99 treatment.

If the primary gate is exceeded, H.2C.2B must stop and report
`BLOCKED_TELEMETRY_OVERHEAD`, proposing an alternative (e.g. a coarser
sampling interval, or restricting real collection to a subset of stages)
before any stage authorized on this plan proceeds.

## 11. Container-cleanup checks

Every configuration's run is followed by an independent
`docker ps -a --filter name=megb-runner-` check (mirroring the G.4
benchmark's own leftover-container check) — zero leftover containers is
a hard requirement, not a diagnostic.

## 12. Stopping rules

- 3 consecutive work items each reaching `RETRY_EXHAUSTED` aborts the
  pilot (same systemic-infrastructure-signal rule as H.3–H.6).
- Any single occurrence of unexpected sandbox weakening (a capability,
  mount, or privilege the accepted MEGB-02 threat model forbids) aborts
  immediately and is never absorbed.
- A primary overhead-gate breach (§10) aborts further configurations in
  that stage's tier and reports `BLOCKED_TELEMETRY_OVERHEAD`.

## 13. READY/BLOCKED classification

**`TELEMETRY_READY_FOR_MEGB_03H3`** requires all of:

- 100% agreement in candidate status and return value between
  telemetry-disabled and telemetry-enabled paired runs, across every
  configuration;
- zero sandbox weakening (no capability, mount, privilege, or
  host-PID-namespace change versus the accepted MEGB-02 design);
- zero leftover containers or telemetry worker threads after every run
  (verified both by this plan's own check and an independent `docker
  ps -a`/process check);
- no privileged or candidate content in any committed output;
- an explicit quality classification (`EXACT`/`SAMPLED_WITH_KNOWN_ERROR`/
  `BOUNDARY_ONLY`/`UNAVAILABLE_WITHOUT_CONTAMINATION`) reported for every
  requested metric, on every real host tested — never silently omitted;
- the primary overhead gate (§10) passing;
- a projected H.3–H.6 runtime, recomputed using the *measured* telemetry
  overhead added on top of the already-accepted `0.418s`/invocation
  baseline, still fitting within the frozen local hard ceilings
  (H.3=1h, H.4=4h, H.5=12h, H.6=4h) — using the same concurrency-aware
  formula as the H.1 calibration design.

**`BLOCKED`**, with the specific reason, if:

- any metric required for a stage is `UNAVAILABLE_WITHOUT_CONTAMINATION`
  on the target host with no non-contaminating alternative;
- the recomputed projected H.5 runtime exceeds the frozen 12-hour local
  ceiling, or materially trends toward it (mirroring the H.1 calibration
  design's own explicit stop-for-infrastructure-decision condition,
  applied here to telemetry-inclusive projections rather than the
  execution-only baseline);
- the H.2C.2A provenance precondition (§1) has not been resolved by the
  time a `TELEMETRY_READY` declaration would otherwise be made.

This plan does not itself authorize H.2C.2B's execution, H.2D, an
execution-profile freeze, or any canonical/candidate content access —
those each require their own separate authorization, exactly as stated
in the H.2C.2A authorization this plan was drafted under.
