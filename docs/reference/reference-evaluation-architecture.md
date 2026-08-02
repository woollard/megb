# Trusted Reference-Evaluation Architecture (MEGB-03G)

## Status

Produced by MEGB-03G.5, documenting the complete path MEGB-03G.1–G.4
implemented and MEGB-03G.3/G.4 accepted into production. Architecture only
— see [megb-03g-acceptance-matrix.md](megb-03g-acceptance-matrix.md) for
requirement-by-requirement status and [version-registry.md](version-registry.md)
for exact identity/checksum values.

## The complete trusted path

```
task-candidate work item                  WorkItem (task_id, candidate_id,
                                           candidate_code, candidate_sha256,
                                           input_ordinal) -- reference_orchestrator.py

  -> trusted evidence resolution           EvidenceResolver protocol;
                                            MappingEvidenceResolver (production-
                                            usable, wraps a pre-resolved mapping;
                                            a privileged-corpus-reading resolver
                                            is a later, separately authorized step)

  -> cache lookup                          ReferenceResultCache.get() via a
                                            prospective cache key computed BEFORE
                                            any execution (deduplicates identical
                                            work items without ever invoking the
                                            backend for a valid hit)

  -> bounded orchestration                 ReferenceOrchestrator.run(): sliding
                                            admission window over ThreadPoolExecutor,
                                            configurable max_concurrency, retry
                                            scoped to INVALID_INFRASTRUCTURE only,
                                            cooperative-cancellation resumption

  -> MEGB-02 execution boundary            CandidateExecutionRequest/Result over
                                            src.execution.wire; DockerPerInvocationBackend
                                            (per-invocation container, unchanged by
                                            this orchestration work)

  -> trusted oracle comparison             evaluate_reference() (or, for G.4's
                                            synthetic benchmark only,
                                            evaluate_g4_benchmark_candidate() --
                                            never the same code path, never
                                            contaminating the real one)

  -> typed task result                     ReferenceTaskResult (result_schema.py) --
                                            MeasurementStatus, q_ref_task,
                                            ReferenceRunContext, PrivilegedCaseDiagnostic
                                            tuple (returned, never persisted --
                                            see "PrivilegedCaseDiagnostic" below)

  -> privileged cache                      ReferenceResultCache.put() -- only
                                            VALID results ever stored, under
                                            artifacts/privileged/reference/cache/
                                            (gitignored, never committed)

  -> safe audit                            ReferenceAuditLog.append() -- one
                                            append-only JSONL record per
                                            invocation attempt, whatever its
                                            disposition (cache hit, miss, fresh
                                            execution, retry)

  -> 164-task aggregation                  aggregate_reference_results() --
                                            THE ONLY manifest-restricted entry
                                            point in this whole path
```

Every stage above except the last is manifest-independent: `WorkItem`,
`EvidenceResolver`, `ReferenceResultCache`, `ReferenceOrchestrator`, and
`ReferenceAuditLog` operate on individual task-candidate-evaluator work items
and never import or require `ReferenceValidationCandidateSetManifest`,
`primary_experiment_task_manifest`, or any expected 163/164 count
(`reference_orchestrator.py`'s own module docstring states this explicitly).

## Manifest independence and the MEGB-06H reuse boundary

This is the single most important architectural boundary in MEGB-03G, per
the "Approved MEGB-03G.2–G.5 Scope Amendment" §1:

- **`aggregate_reference_results(task_results, candidate_set_manifest)`**
  ([`aggregation.py:80`](../../src/reference/aggregation.py)) is the *only*
  function in this path restricted to the 164-entry
  `ReferenceValidationCandidateSetManifest`. It requires exactly 164 task
  results, verifies every result's identity against its manifest entry, and
  computes the primary 164-task validation `Q_ref`.
- **Everything upstream of aggregation** — the cache, the orchestrator, the
  evidence-resolver protocol, the audit log — has no manifest parameter
  anywhere in its public API and no hardcoded task count. This is
  deliberate: **MEGB-06H may reuse the cache and orchestration primitive
  unmodified for its own 163-task experimental workload** against
  `primary_experiment_task_manifest`, supplying its own `EvidenceResolver`
  and its own set of `WorkItem`s, without MEGB-03G needing to change at all.
- **MEGB-03G never constructs a 163-task `Q_ref` aggregate, `Q_meas`, or
  gaming delta.** No function in `src/reference/` accepts
  `primary_experiment_task_manifest` or computes anything named `Q_meas` or
  a gaming delta — that is exclusively MEGB-06I's responsibility, built from
  its own dataset builder. `aggregate_reference_results` structurally cannot
  be handed a 163-task manifest: it is typed to
  `ReferenceValidationCandidateSetManifest` (164 tasks) specifically, and
  `_require_exact_count`/`__post_init__` reject any other count.

## Benchmark-only G.4 results cannot enter Q_ref

MEGB-03G.4's synthetic benchmark evaluator (`evaluate_g4_benchmark_candidate`
in [`g4_benchmark_evaluator.py`](../../src/reference/g4_benchmark_evaluator.py))
produces `ReferenceTaskResult` objects carrying six synthetic identities
(`G4_DATASET_VERSION`, `G4_PARTITION_VERSION`, `G4_ORACLE_VERSION`,
`G4_COMPARISON_PROFILE_VERSION`, `G4_EVALUATOR_VERSION`,
`G4_EXECUTION_PROFILE_ID` — see [version-registry.md](version-registry.md)),
each genuinely distinct from every real MEGB-03B/C/E/F constant. Structural
non-contamination guarantees, proven in `tests/test_g4_benchmark_non_contamination.py`:

1. **Rejected by `aggregate_reference_results` on count grounds** — G.4 never
   produces 164 results in the shape `aggregate_reference_results` expects.
2. **Rejected on profile grounds independently** — even padded to 164 items,
   `_require_full_reference_profile` rejects the synthetic
   `execution_profile_id`/`evaluator_version`.
3. **Rejected when mixed** — one G4 result among 163 real-context results
   fails the run-context-equality check every other result must share.
4. **Cache non-collision** — G.4 results live under a dedicated
   `g4_benchmark_cache/` directory, never `artifacts/privileged/reference/cache/`;
   even if they somehow shared a directory, five of the six identity fields
   in `ReferenceResultCacheKey` differ from the real profile's own (the
   sixth, `execution_protocol_version`, is correctly *equal*, since it
   identifies the shared, unchanged MEGB-02 wire transport rather than
   evaluated content — see version-registry.md's provenance-categories note).

The consequence: **no code path exists by which a G.4 benchmark-only result
could contribute to `q_ref`/`Q_ref`.** This is proven structurally (type/count/
profile rejection), not merely asserted.

## Internal commands

MEGB-03G.5 provides only internal build/verify/qualification commands,
following the existing `partition_cli.py`/`oracle_cli.py`/`parity_cli.py`
pattern. It does **not** implement the user-facing `evaluate-reference`
CLI — that belongs exclusively to MEGB-03I.

| Command | Purpose |
|---|---|
| `python -m src.reference.g4_benchmark` | Runs the full frozen G.4 orchestration-qualification benchmark against a real `DockerPerInvocationBackend`; writes `artifacts/reference/g4_benchmark_audit/g4_benchmark_report.json`; exits nonzero if readiness is `ORCHESTRATION_BLOCKED`. Manual/scheduled invocation only (see `.github/workflows/g4-qualification.yml`) — never on ordinary push/PR. |
| `python -m src.reference.g4_qualification_report_cli` | Regenerates the safe, committed qualification report (`docs/measurement/megb-03g4-qualification-report.{json,md}`) from an already-produced raw benchmark JSON. Never re-runs the benchmark itself. |
| `python -m src.reference.partition_cli {build,verify}` | MEGB-03B partition manifest build/verify (pre-existing). |
| `python -m src.reference.oracle_cli {build,verify}` | MEGB-03C oracle build/verify (pre-existing). |
| `python -m src.reference.parity_cli {build,verify}` | MEGB-03D parity build/verify (pre-existing). |

There is deliberately no `reference_cache_cli.py` or `reference_audit_cli.py`:
the Scope Amendment §5 makes these commands optional ("**may** provide
internal build/verify commands for its own cache, audit, or benchmark
artifacts"), and no operational need for a standalone cache/audit CLI has
arisen — the cache and audit log are exercised through
`ReferenceOrchestrator`, not built/verified as standalone frozen artifacts
the way partition/oracle/parity manifests are. This is a deliberate omission,
not a gap; MEGB-03I remains free to add one if a future need arises.
