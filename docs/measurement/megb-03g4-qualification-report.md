# MEGB-03G.4 Qualification Report

- **Readiness:** `ORCHESTRATION_READY_FOR_MEGB_03H`
- **Generated at:** 2026-08-02T19:22:42.300304+00:00
- **Schema version:** `megb-03g4-qualification-report-v1`
- **Report checksum:** `d3f3bbb31dcd3cb6d774a908f064316deb60d34439249bccf45420214bd9e92b`

## Provenance

- Benchmark plan: `megb-03g4-benchmark-plan-v1` (checksum `16b8634a5700cee173b5f5b916db1d7f8a5023bcd83332c581bb81e8db9b7fd8`)
- Synthetic workload: `megb-03g4-benchmark-evaluator-v2` (checksum `c8e20a97f145c01ae39c56297bffa8e4dae95761095cb9d188eb93260ef92c41`)
- Implementation commit: `ecff45479919be646fb70aa5da0fe814fbba24e0`
- Docker image: `sha256:3ddfd2080085e256d7c7a787e3b470ef9e721abe49cbb3f9b4f4cf6db6abc8ee` (provenance `cdf2fa8490f2a0dd2b8470e8d7218a864afe655d3018e56dd788a47bbe7caa29`)
- Host/platform: macOS-26.5.1-arm64-arm-64bit-Mach-O

## Configuration

- Concurrency levels: [1, 2, 4]
- Throughput-sweep N: 8
- Cross-tier N: 4
- Interruption N: 6
- Calibration samples: 3
- Calibration mean: 0.3866s
- Scale factor applied: 1.0000

## Results

- Total wall-clock: 73.40s
- Best speedup: 1.823x
- Equivalence: all matched = True (mismatches: 0)
- Ordering deterministic: True
- Isolation held: True
- Warm-cache all hits: True
- Resumption gap-free: True
- Leftover containers found: False
