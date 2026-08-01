# MEGB-03B Partition Validation Report

Generated: 2026-08-01T05:30:17.499236+00:00

## Manifests

- `reference_validation_task_manifest`: 164 tasks,
  checksum `832620da24471ffe85946fc1ccac7e7ff8a375ab16a452b0b2d60a1b9d8a59b9`
- `primary_experiment_task_manifest`: 163 tasks,
  checksum `c85ec9d3cd073821e06b875ccb54e9a7d2b958eeb093dd30afda37f2d5ac1b71`
- Partition algorithm: `partition-v1`,
  seed: `megb-03b-seed-v1`
- Development target: 40,
  minimum reference-only: 30

## Required validations

| Check | Result |
|---|---|
| Exactly 163 experimental tasks | 163 — PASS |
| Task IDs unique | PASS |
| Exactly 40 development cases per task | PASS |
| At least 30 reference-only cases per task | min=39 — PASS |
| Exhaustive assignment (dev + ref == total unique) | PASS |
| Zero development/reference overlap | PASS |
| `HumanEval/39` absent from experimental partition | PASS |
| Deterministic byte-stable reconstruction (rebuild, compare checksum) | rebuild=`c85ec9d3cd073821e06b875ccb54e9a7d2b958eeb093dd30afda37f2d5ac1b71` — PASS |
| Changed seed changes manifest identity | reseeded=`17e0c11c524c3401fde60d354007657c6bb98efdd85887c4e67cb3cf18ec7c22` — PASS |

## Provenance counts for augmented tasks

- `HumanEval/55`: development={'megb-contract-augmentation-v1': 33, 'evalplus-original-v1': 7}, reference_only={'megb-contract-augmentation-v1': 124, 'evalplus-original-v1': 38}
- `HumanEval/6`: development={'megb-contract-augmentation-v1': 33, 'evalplus-original-v1': 7}, reference_only={'megb-contract-augmentation-v1': 185, 'evalplus-original-v1': 62}
- `HumanEval/63`: development={'evalplus-original-v1': 15, 'megb-contract-augmentation-v1': 25}, reference_only={'megb-contract-augmentation-v1': 112, 'evalplus-original-v1': 50}

## Scope confirmation

No MEGB-04 observation sets were generated, no expected outputs were
constructed, no candidate code was executed, and MEGB-03C was not begun.
This report covers partition assignment only.
