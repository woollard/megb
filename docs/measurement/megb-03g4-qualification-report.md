# MEGB-03G.4 Qualification Report

- **Readiness:** `ORCHESTRATION_READY_FOR_MEGB_03H`
- **Generated at:** 2026-08-02T18:43:39.414891+00:00
- **Schema version:** `megb-03g4-qualification-report-v1`
- **Report checksum:** `975e5b8aafcf1baf79409f9596880be0245ae9173bbc2c53ca24402b1ac7c2d1`

## Provenance

- Benchmark plan: `megb-03g4-benchmark-plan-v1` (checksum `16b8634a5700cee173b5f5b916db1d7f8a5023bcd83332c581bb81e8db9b7fd8`)
- Synthetic workload: `megb-03g4-throughput-report-v1` (checksum `9a8aa118f3d482e445e145639372b8b82b10c58f5e2ea2473e64435f6a55ce90`)
- Implementation commit: `2886ab226606b4e93a04f0f8967dbadb1fd4fa23` (dirty working tree)
- Docker image: `sha256:3ddfd2080085e256d7c7a787e3b470ef9e721abe49cbb3f9b4f4cf6db6abc8ee` (provenance `cdf2fa8490f2a0dd2b8470e8d7218a864afe655d3018e56dd788a47bbe7caa29`)
- Host/platform: macOS-26.5.1-arm64-arm-64bit-Mach-O

## Configuration

- Concurrency levels: [1, 2, 4]
- Throughput-sweep N: 8
- Cross-tier N: 4
- Interruption N: 6
- Calibration samples: 3
- Calibration mean: 0.3830s
- Scale factor applied: 1.0000

## Results

- Total wall-clock: 63.19s
- Best speedup: 2.668x
- Equivalence: all matched = True (mismatches: 0)
- Ordering deterministic: True
- Isolation held: True
- Warm-cache all hits: True
- Resumption gap-free: True
- Leftover containers found: False
