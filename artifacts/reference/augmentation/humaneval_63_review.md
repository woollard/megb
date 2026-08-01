# MEGB-03A.1 Supplementary-Evidence Review — HumanEval/63

## Task contract

```python
assert isinstance(n, int), "invalid inputs" # $_CONTRACT_$
assert n >= 0, "invalid inputs" # $_CONTRACT_$
```

## Generation rule and justification

Exhaustive enumeration of the integer range [0, 200) (same rule as HumanEval/55 — both share the fib-family unbounded-integer domain).

Domain: n: int, n >= 0 (unbounded above)

Algorithm version: `supplementary-generation-v1` (frozen prior to generation;
see `generation_procedures_v1.md`, checksum
`31705af14ef914a8b495d980c3a9a962b4039b1f6aa574cdad85c706e7289c00`).

## Generated and deduplicated counts

| Quantity | Count |
|---|---:|
| Original (EvalPlus-sourced) unique cases | 65 |
| Raw candidates generated | 200 |
| Duplicates of existing cases (dropped) | 63 |
| Contract-rejected candidates | 0 |
| Infeasible candidates (canonical solution raised) | 0 |
| **Accepted supplementary cases** | **137** |
| **Combined unique cases** | **202** |

Target was >= 100 combined unique cases:
MET.

## Examples and boundary coverage

- n=0 (lower boundary, already covered)
- n=199 (new upper extension well beyond prior max of 102)
- gap-filling values between 0 and 102 not previously present

## Resource-calibration results

Feasibility checks execute the pinned canonical solution directly (trusted-side, not sandboxed — these are corrected reference solutions, not untrusted candidate code). Total wall time for all 137 non-duplicate feasibility checks: 0.0006s; slowest single call: 0.000015s. No resource limit or timeout was approached; this task poses no execution-resource risk.

## Provenance and checksums

- Original-case checksum (`evalplus-original-v1`): `52b4118e408786dc690f92647ee367f6728f5f58be699eb3eee09cbaca0a026a`
- Supplementary-case checksum (`megb-contract-augmentation-v1`): `d5ba0f64cf3dc70f4c35661e8b87bc0ef26698943d9de16d8580514a77659bb7`
- Combined checksum: `bce7ff18a1e6d6ccbca5e945e65925a38840fbd7c523500dfbbc60f49efa6bbd`
- Case ID algorithm: `case-id-v1` (unchanged from MEGB-03A)

## Ambiguities or rejected cases

Contract-rejected candidates:
(none)

Infeasible candidates (canonical solution raised an exception):
(none)

## Design-precedence confirmation

This generation procedure was designed and frozen
(`generation_procedures_v1.md`) using only this task's documented contract
and the general mathematical structure of its input domain. No model
candidate, observed candidate failure, or `S*`/reference-evaluator outcome
was consulted or exists for this task in this repository as of this
review. No expected output was constructed or persisted for any
supplementary case; MEGB-03C remains solely responsible for oracle
construction.

**Requires explicit review acceptance before this evidence is eligible for
MEGB-03B partitioning (Decision 8) — not yet granted.**
