# MEGB-03A.1 Supplementary-Evidence Review — HumanEval/55

## Task contract

```python
assert n >= 0, "invalid inputs" # $_CONTRACT_$
assert isinstance(n, int), "invalid inputs" # $_CONTRACT_$
```

## Generation rule and justification

Exhaustive enumeration of the integer range [0, 200).

Domain: n: int, n >= 0 (unbounded above)

Algorithm version: `supplementary-generation-v1` (frozen prior to generation;
see `generation_procedures_v1.md`, checksum
`31705af14ef914a8b495d980c3a9a962b4039b1f6aa574cdad85c706e7289c00`).

## Generated and deduplicated counts

| Quantity | Count |
|---|---:|
| Original (EvalPlus-sourced) unique cases | 45 |
| Raw candidates generated | 200 |
| Duplicates of existing cases (dropped) | 43 |
| Contract-rejected candidates | 0 |
| Infeasible candidates (canonical solution raised) | 0 |
| **Accepted supplementary cases** | **157** |
| **Combined unique cases** | **202** |

Target was >= 100 combined unique cases:
MET.

## Examples and boundary coverage

- n=0 (lower boundary, already covered)
- n=199 (new upper extension well beyond prior max of 86)
- n=9, n=19-26 (previously-missing gaps in the original evidence, now filled)

## Resource-calibration results

Feasibility checks execute the pinned canonical solution directly (trusted-side, not sandboxed — these are corrected reference solutions, not untrusted candidate code). Total wall time for all 157 non-duplicate feasibility checks: 0.0003s; slowest single call: 0.000004s. No resource limit or timeout was approached; this task poses no execution-resource risk.

## Provenance and checksums

- Original-case checksum (`evalplus-original-v1`): `0a184009e3e49e46c973def9068d6bfa992248cee883ef3635097276655b4cda`
- Supplementary-case checksum (`megb-contract-augmentation-v1`): `dfa41b80da6102d4573ec6343f73f2660a4e931ce57efe644717f1fee3143ba7`
- Combined checksum: `860e422d519590be2d8670523f421f85be2f1c7dd51046f00a9c7fd7add96761`
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
