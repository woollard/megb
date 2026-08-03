# MEGB-03H.2C.2B Real-Docker Telemetry Qualification Report

- **Readiness:** `BLOCKED_TELEMETRY_OVERHEAD`
- **Run identity:** `h2c2b-diagnostic-20260803T211615Z` (qualifying: False)
- **Generated at:** 2026-08-03T21:35:00Z
- **Schema version:** `megb-03h2c2b-qualification-report-v1`
- **Report checksum:** `c1a6854122326928f34af70c0595cf2820efb90614011a53d89a1edd3a2bd7e3`

## Provenance

- Frozen plan: sha256 `9014bbbca776af9ad9075190dc5b43bf95af6e138e89d21960d5f2889a387c75`, git blob `f8a422c457ad1b7a7ecfa33901fe986ff476a20f`
- Harness version: `megb-03h2c2b-measurement-harness-v1`
- Implementation commit: `df53187d7fd1f86d046b00d44e8bbfc0725cda68`
- Docker image: `sha256:e8e1d4d128de4536f1da5f7ec7eddae4838a05ad7719ca81c0d862353ee90679` (provenance `cdf2fa8490f2a0dd2b8470e8d7218a864afe655d3018e56dd788a47bbe7caa29`)
- Host: Darwin/arm64, kernel 25.5.0, Docker server 29.1.3, cgroup driver cgroupfs

## Method / capability / quality

- Memory: preferred `CGROUP_V2_MEMORY_PEAK` -> selected `SAMPLED_DOCKER_STATS_MEMORY` (FALLBACK_METHOD_SELECTED), quality `BOUNDARY_ONLY`, unavailable reason `NONE`
- Process count: preferred `CGROUP_V2_PIDS_PEAK` -> selected `SAMPLED_DOCKER_TOP_PROCESS_COUNT` (FALLBACK_METHOD_SELECTED), quality `NONE`, unavailable reason `HOST_TELEMETRY_UNAVAILABLE`
- late_peak: quality `BOUNDARY_ONLY`, terminal coverage `TERMINAL_READ_NOT_APPLICABLE`, value matches expected minimum: True

## Overhead

- Primary gate: <= 20.9ms/invocation, passed: False
  - concurrency=1: n=24 pairs, mean=1478.326ms, p99=2674.813ms
  - concurrency=2: n=24 pairs, mean=1612.220ms, p99=2684.389ms
  - concurrency=4: n=24 pairs, mean=2670.162ms, p99=3910.040ms

## Noninterference and cleanup

- Status-matrix scenarios tested: 9
- All statuses agree: True
- All return values agree: True
- Leftover containers found: False

## Stage projections (H.3-H.6)

- H3/baseline: 1140.6s / ceiling 3600s (within ceiling: True)
- H3/moderate: 1710.9s / ceiling 3600s (within ceiling: True)
- H3/conservative: 2281.2s / ceiling 3600s (within ceiling: True)
- H3/stress: 5703.0s / ceiling 3600s (within ceiling: False)
- H4/baseline: 6658.3s / ceiling 14400s (within ceiling: True)
- H4/moderate: 9987.4s / ceiling 14400s (within ceiling: True)
- H4/conservative: 13316.5s / ceiling 14400s (within ceiling: True)
- H4/stress: 33291.3s / ceiling 14400s (within ceiling: False)
- H5/baseline: 120143.2s / ceiling 43200s (within ceiling: False)
- H5/moderate: 180214.8s / ceiling 43200s (within ceiling: False)
- H5/conservative: 240286.3s / ceiling 43200s (within ceiling: False)
- H5/stress: 600715.8s / ceiling 43200s (within ceiling: False)
- H6/baseline: 26050.6s / ceiling 14400s (within ceiling: False)
- H6/moderate: 39075.8s / ceiling 14400s (within ceiling: False)
- H6/conservative: 52101.1s / ceiling 14400s (within ceiling: False)
- H6/stress: 130252.8s / ceiling 14400s (within ceiling: False)

## Blocking reasons

- Primary overhead gate breached: measured mean overhead ranged 1478-2670ms/invocation across concurrency levels 1/2/4, vs the frozen 20.9ms gate -- driven by the sampled-fallback collectors' own docker-stats/docker-top subprocess polling cost, not by the (unreachable) cgroup-exact path.
- EXACT peak-memory telemetry unavailable on this host: no host-visible cgroup v2 filesystem exists under Docker Desktop for macOS (containers run inside a Linux VM the host cannot read /sys/fs/cgroup from), so CGROUP_V2_MEMORY_PEAK/CGROUP_V2_PIDS_PEAK can never be selected here -- native Linux or an AWS Linux instance is required to exercise or qualify the EXACT tier.
- Sampled process-count telemetry (SAMPLED_DOCKER_TOP_PROCESS_COUNT) obtained zero successful samples in every one of 8 attempts on this host -- an operational sampler reliability finding distinct from capability absence, requiring investigation before process-count telemetry can be relied on even at BOUNDARY_ONLY quality.
- H.5 baseline-scenario projected runtime (120143s) with measured telemetry overhead included exceeds the frozen 12h local hard ceiling (43200s).
