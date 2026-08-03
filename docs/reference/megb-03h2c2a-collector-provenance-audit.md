# MEGB-03H.2C.2A — Collector-Provenance Audit

## Status

Read-only determination, required before any real collector implementation
or real-Docker telemetry run, per the MEGB-03H.2C.2A authorization. No code
was modified as part of this audit; it inspects the already-accepted H.2A
persisted schema (`src/reference/calibration_schema.py`) only.

## Question

Can the accepted `CalibrationInvocationRecord`/`CalibrationRunContext`
schema independently identify every telemetry-method choice that could
change a reported measurement — collector implementation/version, metric
name, collection method, sampling interval, exact-vs-sampled-vs-boundary
semantics, capability/fallback choice, the relevant Docker/cgroup
interface, and host/runtime metadata required to interpret portability?

## What the accepted schema already carries

`CalibrationInvocationRecord` (`src/reference/calibration_schema.py`)
carries, per metric (`candidate_wall_time_sec`, `observed_response_bytes`,
`peak_memory_bytes`, `peak_process_count`):

- the value itself (nullable);
- a `MeasurementQuality` (`EXACT` / `SAMPLED_WITH_KNOWN_ERROR` /
  `BOUNDARY_ONLY` / `UNAVAILABLE_WITHOUT_CONTAMINATION`), populated only
  when the value is present;
- a `TelemetryUnavailableReason`, populated only when the value is absent.

It additionally carries `backend_id`/`backend_version`/
`runner_image_digest` (the execution *backend's* identity — which Docker
CLI/runner image executed the candidate) and, via the embedded
`CalibrationRunContext`, `execution_profile_id` (the accepted resource/
concurrency profile identity, e.g. diagnostic vs. full limits).

**Metric name** is not a gap: each metric has its own dedicated,
statically-named field (`peak_memory_bytes` vs. `peak_process_count`),
so which metric a value belongs to is never ambiguous.

**Exact-vs-sampled-vs-boundary semantics** are *partially* covered:
`MeasurementQuality` tells a reader which of the four accepted tiers a
value belongs to. It does not, by itself, say *which method* produced
that tier.

## The gap

The schema has **no field** for:

1. **Collector implementation/version** — e.g. distinguishing
   `cgroup_peak_file_collector/v1` from `sampled_polling_collector/v1`.
2. **Collection method** — e.g. a native cgroup v2 `memory.peak` read vs.
   a `docker stats --no-stream` polling loop. Two collectors could both
   report `BOUNDARY_ONLY` for the same metric while using entirely
   different sampling strategies with different portability and failure
   characteristics, and a reader of the persisted record could not tell
   them apart.
3. **Sampling interval**, when the method is sampled — needed to
   interpret how coarse a `BOUNDARY_ONLY` lower bound actually is.
4. **Capability/fallback choice** — *why* a particular method was
   selected for this invocation (e.g. "cgroup v2 `memory.peak` was not
   readable on this host, fell back to sampled `docker stats`"). This is
   exactly the kind of decision that determines whether a measurement is
   reproducible on a different host.
5. **The relevant Docker/cgroup interface** — e.g. cgroup v1 vs. v2,
   the systemd vs. cgroupfs cgroup driver, which specific path or CLI
   command was read.
6. **Host/runtime metadata required to interpret portability** — kernel
   release, cgroup driver, Docker server version *at the time telemetry
   was collected*. (`backend_version` records the Docker server version
   used for *execution*, which happens to often be the same daemon, but
   is not scoped or named as telemetry provenance, and does not carry
   kernel release or cgroup driver at all.)

**Determination: the accepted persisted calibration schema cannot bind
the telemetry method/configuration sufficiently to reproduce or
interpret a real measurement.** This is a genuine, confirmed gap, not a
matter of interpretation.

## Disposition (per the H.2C.2A authorization)

Per explicit instruction, this gap is **reported, not silently
worked around**:

- `src/reference/calibration_schema.py` (the accepted H.2A persisted
  schema) is **not modified** by H.2C.2A. `execution_profile_id` and
  every other existing field are left exactly as accepted — none of them
  is repurposed to smuggle in collector-method identity.
- The full provenance model (`CollectorMethod`, `CollectorMethodIdentity`
  — method, version, interface string, sampling interval, host runtime
  metadata as an immutable tuple of key/value pairs) is defined entirely
  at the **execution layer** (`src/execution/telemetry_methods.py`),
  attached to `TelemetryObservation` as a new, additive,
  `method_identity: CollectorMethodIdentity | None = None` field —
  mirroring the exact precedent set by `CollectorFailureStage` and
  `cleanup_failed` in the H.2C.1 conformance-audit corrections: real,
  richly-typed, and completely inert with respect to the persisted
  schema.
- `src/reference/execution_telemetry_adapter.py` (the one-way
  execution→reference adapter) is **not extended** to carry
  `method_identity` into `CalibrationTelemetryFields` — there is no slot
  for it there yet, and adding one is exactly the kind of schema
  question this audit exists to flag, not to decide unilaterally.
  Consequently: **any real measurement collected under H.2C.2A's
  collectors, if it were run today, would have its method/provenance
  detail silently dropped the moment it crossed into a persisted
  calibration record.** This is precisely why H.2C.2A performs no real
  Docker execution — there is nothing yet to persist that would be
  reproducible.

## What this means for H.2C.2B

Before any real-Docker measurement run is trusted as reproducible
evidence, one of the following must happen, under separate
authorization:

1. Extend `CalibrationInvocationRecord` (a persisted-schema change) with
   fields for collector method/version, sampling interval, and relevant
   host/interface metadata, mirroring the H.2C.2A execution-layer model
   — the natural, minimal fix, but out of scope for H.2C.2A itself; **or**
2. Explicitly decide, with the same authorization, that this provenance
   detail does not need to survive into the persisted record for the
   H.3–H.6 stages' own purposes (e.g. because the calibration run itself
   is expected to use one fixed, frozen collector configuration
   throughout, recorded once at the run-context level rather than
   per-record) — a legitimate design choice, but one that must be made
   explicitly, not by omission.

The H.2C.2B measurement plan (below) treats this as an open, tracked
precondition rather than assuming an answer.
