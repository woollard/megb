# MEGB-03H.2C.3B.3 — Calibration and Qualification Provenance Integration Design

Frozen before any implementation code for this checkpoint was written or
modified. Committed standalone, git blob SHA-1/sha256 referenced (not
embedded) by this checkpoint's later-generated safe qualification
evidence report, mirroring the established
`megb-03h2c3b2c-offline-e2e-qualification-plan.md`/
`megb-03h2c3b2b3-fault-injection-plan.md` pattern. Not modified after
implementation begins.

## Scope and explicit non-claims

This checkpoint implements exactly the integration the accepted
`docs/reference/megb-03h2c3b1-integration-map.md` names as blocking
before MEGB-03H.2C.3D: connecting `src/distributed/`'s standalone,
provider-neutral provenance types to the accepted
`src/reference/calibration_schema.py` evidence chain, and building the
typed qualification-evidence/report model that binds them together with
measured peak concurrency.

This checkpoint is **entirely offline**. It explicitly does **not** and
**may not**: begin MEGB-03H.2C.3C; authenticate to GCP; invoke `gcloud`;
access any cloud resource; run Docker; access real privileged artifacts,
HumanEval evidence, or real candidate content; modify
`ReferenceRunContext`, `ReferenceResultCacheKey`, `ReferenceAuditRecord`,
or any production cache/result schema (those remain a pre-H.2C.3F
requirement, per the integration map's own summary table); or claim
GCP readiness, H.2C.3D readiness, or real scientific-result validity.
Readiness this checkpoint may report is exactly one of:

- `CALIBRATION_PROVENANCE_READY_FOR_3C`
- `BLOCKED_CALIBRATION_PROVENANCE`

Neither implies H.2C.3C credential-boundary readiness (H.2C.3C is a
separate, first-credential-boundary checkpoint requiring its own
authorization) — this checkpoint proves only that the offline evidence
chain from a synthetic distributed run through calibration records to a
release-readiness verdict is content-bound and falsifiable end-to-end,
in-process, with no real infrastructure anywhere.

## 1. Exact calibration-schema changes

`src/reference/calibration_schema.py`, additive field changes only (no
existing field removed or renamed):

- `CalibrationRunContext` gains two new required fields:
  - `distributed_run_context_checksum: str` (sha256 hex) — must equal
    the `DistributedRunContext.run_context_checksum` of the run this
    calibration context was produced under.
  - `provenance_manifest_checksum: str` (sha256 hex) — must equal the
    `DistributedProvenanceManifest.manifest_checksum` (see §2) that
    packages that run context together with its worker contexts,
    topology, qualification identity, and gate result. Both fields
    participate in `context_checksum` (already-established embedding
    convention: every field on `CalibrationRunContext` contributes to
    its own checksum), so a context claiming one run/manifest binding
    while another already exists under the same other labels is a
    different context entirely — never silently reinterpreted.
- `CalibrationInvocationRecord` gains one new required field:
  - `worker_execution_context_checksum: str` (sha256 hex) — must equal
    the `WorkerExecutionContext.worker_context_checksum` of the worker
    that actually produced this invocation. Participates in
    `record_checksum` (already-established embedding convention).
- `CalibrationTaskEvaluationRecord` gains **no new field**. See §4 for
  the explicit transitivity determination and its required test.
- A new function, `reconcile_distributed_provenance(...)`, added in a
  new sibling module (not inside the already-oversized
  `calibration_schema.py`, mirroring the existing
  `calibration_summary.py`/`calibration_trace.py` module-size
  precedent): `src/reference/distributed_provenance_reconciliation.py`.
  This is the only new module in `src/reference/` this checkpoint adds,
  and it is the **only** module in that package permitted to import
  `src.distributed` (no dependency-direction test forbids this
  direction — only the reverse, `src/distributed` importing
  `src.reference`, is forbidden and remains untouched by this
  checkpoint). It:
  - Given a `CalibrationRunContext` and a `DistributedProvenanceManifest`,
    verifies `context.distributed_run_context_checksum ==
    manifest.run_context.run_context_checksum` and
    `context.provenance_manifest_checksum == manifest.manifest_checksum`,
    raising a new `DistributedProvenanceReconciliationError` (subclass of
    `InvalidCalibrationRecordError`) on any mismatch.
  - Given a `CalibrationInvocationRecord` and the same manifest, verifies
    `invocation.worker_execution_context_checksum` resolves to one of
    the manifest's own `WorkerExecutionContext.worker_context_checksum`
    values (via `resolve_worker_context`, §2), raising the same error
    class if it does not (covers: unknown worker checksum, worker from
    another run, substituted worker context, invocation/manifest
    mismatch).
  - Verifies `invocation.context.host_runtime_identity_checksum`-style
    cross-references are not introduced here — the integration map's
    item 2 (`host_runtime_identity_checksum`/
    `telemetry_policy_identity_checksum` reconciliation against
    `HostRuntimeContext`/`TelemetryCollectionPolicy`) was already fully
    specified and remains a `WorkerExecutionContext`-level concern
    unrelated to this checkpoint's own distributed-run binding; it is
    unaffected and not touched here (`WorkerExecutionContext`'s own two
    checksum fields already exist unchanged since MEGB-03H.2C.3B.1).

## 2. Provenance-manifest schema

New module `src/distributed/provenance_manifest.py` (pure
`src.distributed`, no `src.reference` import, per the package's own
layering rule). `DistributedProvenanceManifest`, a typed, immutable,
versioned, self-checksummed dataclass:

| Field | Type | Source |
|---|---|---|
| `distributed_provenance_manifest_schema_version` | `str` | new own version, §8 |
| `checksum_algorithm_version` | `str` | reused `CHECKSUM_ALGORITHM_VERSION` |
| `run_context` | `DistributedRunContext` | embedded in full |
| `worker_execution_contexts` | `tuple[WorkerExecutionContext, ...]` | embedded in full, sorted by `worker_context_checksum` |
| `topology_summary` | `MixedWorkerProvenanceSummary` | via `aggregate_worker_provenance` |
| `qualification_identity` | `QualificationIdentity` | via `qualification_identity_for` |
| `qualification_gate_readiness` | `str` (`ProvenanceGateReadiness` value) | via `evaluate_qualification_gate` |
| `qualification_gate_missing_dimensions` | `tuple[str, ...]` (`ProvenanceGateFailureReason` values) | via `evaluate_qualification_gate` |
| `generation_command` | `str` | caller-supplied, nonempty |
| `code_revision` | `str` | caller-supplied, nonempty (e.g. git commit SHA; not forced to sha256 hex shape, since revision-identifier schemes are not this package's concern) |
| `safe_redacted_summary` | `SafeRedactedSummary` | via the already-accepted `build_safe_redacted_summary` (reused, not reimplemented) |
| `manifest_checksum` | `str` | self-computed, §8 |

Construction (`build_distributed_provenance_manifest(run_context,
workers, *, generation_command, code_revision)`) is the only supported
path: it calls `aggregate_worker_provenance` (rejecting empty/mixed/
duplicate-participant worker sets — satisfies "duplicate participant IDs
or context conflicts are rejected" and "mixed distributed-run contexts
are rejected" structurally, before the manifest dataclass is ever
constructed), `qualification_identity_for`, `evaluate_qualification_gate`,
and `build_safe_redacted_summary`, then constructs the dataclass. The
dataclass's own `__post_init__` independently re-verifies every worker's
`parent_run_context_checksum` and participant-id uniqueness (so a
hand-constructed instance bypassing the builder is equally rejected —
never merely a builder-level convenience check), and recomputes
`manifest_checksum` over a canonical payload embedding every context, the
topology summary's own counts, the qualification identity, the gate
readiness/missing-dimensions, `generation_command`/`code_revision`, and
the safe summary — "manifest checksum binds every context and topology
count."

`resolve_worker_context(manifest, worker_context_checksum) ->
WorkerExecutionContext`: raises `InvalidDistributedProvenanceError` if no
worker in the manifest carries that checksum — "worker-context checksums
must resolve to records in the manifest," and "a checksum without a
persisted, verifiable referenced manifest is insufficient" (a bare
checksum string proves nothing on its own; only resolution against a
real, constructed manifest object does).

Structurally excludes (no field exists for any of them, mirroring
`SafeRedactedSummary`'s own "no field exists" guarantee one layer up):
raw project IDs, instance IDs, hostnames, filesystem paths, service
account identifiers, credentials, or infrastructure resource names — the
full manifest embeds only already-safe-by-construction
`src.distributed` types (every field on `DistributedRunContext`/
`WorkerExecutionContext` is already, by MEGB-03H.2C.3B.1's own design,
free of raw operational identifiers) plus two new plain strings
(`generation_command`, `code_revision`) which this checkpoint's own
negative tests (§ full report's negative-test matrix) confirm are
rejected if they match a known secret-shape pattern, reusing
`protected_mapping.py`'s existing `_reject_if_looks_like_secret`-style
check.

**Protected vs. safe, at the manifest level**: the **full manifest**
(embedding complete `WorkerExecutionContext` records, generation command,
and code revision) is treated as **protected operational/calibration
evidence** — never committed to a public report path, only ever held in
a caller-managed temporary/synthetic path (§10). Only
`manifest.safe_redacted_summary` (already-accepted `SafeRedactedSummary`)
and `manifest.manifest_checksum` itself (an opaque content-bound
identifier, not raw content) are safe to embed in any committed report.

## 3. Artifact/lock relationships

Three artifacts in this checkpoint's own synthetic integration harness,
each a distinct persisted JSON file under a caller-supplied
temporary/synthetic directory (never a fixed repo path — see §10):

1. **Provenance manifest** (`DistributedProvenanceManifest`) — protected,
   full-fidelity. Referenced by checksum from (2) and (3), never
   embedded wholesale in either.
2. **Calibration records** (`CalibrationRunContext` +
   `CalibrationInvocationRecord` + `CalibrationTaskEvaluationRecord`,
   accepted schema, this checkpoint's additive fields) — protected,
   full-fidelity (unchanged: calibration records have always been
   protected/privileged evidence, never a safe report).
3. **Calibration-provenance qualification-evidence report**
   (`CalibrationProvenanceReport`, §5) — safe, committed-report-suitable.
   References (1) and (2) by checksum only.

No new `.lock.json` file is introduced: unlike the partition/oracle/
parity artifacts (which gate real, privileged corpus content a
build/verify CLI must not silently overwrite), this checkpoint's
artifacts are synthetic and offline, and the existing "refuse silent
overwrite of a differing frozen artifact" discipline (§10) is enforced
directly by the build/verify CLI comparing new-vs-existing file content
before writing, exactly mirroring
`offline_e2e_qualification_report_cli.py`'s and
`fault_conformance_cli.py`'s own already-accepted `build`/`verify` shape
— introducing a fourth lock-file convention for one synthetic offline
checkpoint would add ceremony with no additional safety this file-level
check does not already provide.

## 4. Run-level versus invocation-level ownership

- **Run-level** (one `DistributedRunContext`, one manifest, one
  `CalibrationRunContext` per calibration run): environment class, run
  intent, cloud provider, coordinator/queue/object-store implementation
  identity, retry/lease policy, deployment topology policy,
  `distributed_run_context_checksum`, `provenance_manifest_checksum`.
- **Invocation-level** (one `WorkerExecutionContext` per worker, one
  `worker_execution_context_checksum` per `CalibrationInvocationRecord`):
  which specific worker (region, zone, machine type, provisioning class,
  image digest, implementation version) actually produced this one
  invocation. Two invocations sharing a run may bind to two entirely
  different worker contexts.
- **Task-evaluation-level determination (audited, not assumed)**:
  `CalibrationTaskEvaluationRecord` requires **no new explicit
  worker-context histogram field**. Its existing
  `contributing_invocation_content_checksums` binds each contributor's
  *entire* `record_checksum` at binding time — and because
  `worker_execution_context_checksum` is now (per §1) one of the fields
  folded into that same `record_checksum`, any change to which worker
  produced a given invocation changes that invocation's `record_checksum`,
  which changes `contributing_invocations_checksum` on the task
  evaluation, which `reconcile_task_evaluation` (unchanged) already
  rejects as "contributor content changed after binding." The binding is
  **transitive through content, not through a redundant parallel field**.
  This checkpoint adds a dedicated regression test proving exactly this:
  construct a task evaluation bound to one invocation, then rebuild an
  invocation identical in every field except
  `worker_execution_context_checksum`, and confirm
  `reconcile_task_evaluation` rejects it. No new histogram field is
  added — adding one would duplicate information already exactly and
  more strongly bound by content checksum, violating this project's own
  "do not add redundant fields without justification" discipline.

## 5. Qualification-gate behavior

`evaluate_qualification_gate` (accepted, MEGB-03H.2C.3B.1, unchanged)
remains the sole gate function for distributed-provenance completeness:
`run_intent != QUALIFICATION_CANDIDATE` always blocks
(`NOT_QUALIFICATION_INTENT`), regardless of `environment_class` (both
`PERSONAL_BOOTSTRAP` and `COMPANY_PLAYGROUND` may be
`QUALIFICATION_CANDIDATE`). This checkpoint's new
`CalibrationProvenanceReport` (§6) embeds this gate's own
`readiness`/`missing_dimensions` (via the manifest's
`qualification_gate_readiness`/`qualification_gate_missing_dimensions`
fields) and additionally requires, before its own
`CALIBRATION_PROVENANCE_READY_FOR_3C` readiness may be derived: the
manifest's gate readiness itself is `READY`; every invocation's worker
provenance reconciles against that same manifest (§1); calibration
task-evaluation reconciliation passes (unchanged `reconcile_all`); and
peak concurrency evidence (§6) satisfies its own bounds. Smoke-test
distributed provenance (`run_intent == SMOKE_TEST`) can never produce
`CALIBRATION_PROVENANCE_READY_FOR_3C` — the gate's own
`NOT_QUALIFICATION_INTENT` blocks it structurally, mirroring the B.2C
checkpoint's own smoke-vs-qualification discipline one layer up.

## 6. Peak-concurrency evidence

`CalibrationProvenanceReport` (new module
`src/distributed/calibration_provenance_report.py`, pure
`src.distributed`) carries:

- `intended_concurrency: int` — the topology's own admitted worker count
  (`manifest.topology_summary.admitted_worker_count`), a provenance fact.
- `measured_peak_concurrency: int` — **actual, measured evidence**,
  never a caller-supplied provenance label, computed the same way the
  accepted B.2C checkpoint's own `measured_peak_concurrency_personal`/
  `_generic` fields are: a `threading.Barrier`-forced concurrent
  execution and a `PeakConcurrencyTrackingExecutor`-style wrapper that
  records genuine simultaneous-invocation overlap, reused from
  `tests/_offline_e2e_qualification_fixtures.py`'s already-established
  pattern (imported by the harness's own tests, not duplicated into
  production code — the tracking wrapper is test-only instrumentation,
  exactly as it already is for B.2C).
- Required invariant, enforced in `__post_init__`:
  `measured_peak_concurrency <= intended_concurrency` and
  `measured_peak_concurrency <= PERSONAL_BOOTSTRAP_MAX_WORKERS` (2) when
  `manifest.run_context.environment_class == PERSONAL_BOOTSTRAP` — "actual
  concurrency ≤ admitted topology and policy ceiling; personal
  qualification ≤ two." A report violating either is rejected outright
  (`InvalidDistributedProvenanceError`), never silently accepted with a
  blocked readiness — an impossible measurement is a construction error,
  not a business-rule failure.

## 7. Protected versus safe fields

Mirroring the already-established three-tier split this project uses
throughout (`ProtectedOperationalMapping` / full calibration record /
`SafeRedactedSummary`):

| Tier | Contents | Committed? |
|---|---|---|
| Protected | Full `DistributedProvenanceManifest` (complete worker contexts, generation command, code revision); full `CalibrationRunContext`/`CalibrationInvocationRecord`/`CalibrationTaskEvaluationRecord` | Never — synthetic/temp path only |
| Safe | `CalibrationProvenanceReport` — checksums, closed-enum values, counts, coarse topology histograms (region/machine-type/provisioning-class/image-digest, no zone), readiness, typed blocker reasons | Yes — this checkpoint's own committed artifact |

`CalibrationProvenanceReport`'s own field set is exhaustively checked by
a leakage test (mirroring
`test_offline_e2e_qualification_boundaries.py::test_offline_e2e_qualification_report_has_no_unsafe_field`)
against the same forbidden-substring list (`candidate`, `credential`,
`password`, `secret`, `hostname`, `instance_id`, `container_id`,
`project_id`, `path`, `exception`, `stdout`, `stderr`, `traceback`,
`message`, `participant`, `worker_id`, `prompt`, `source`) plus
`zone`/`generation_command`/`code_revision` (the three additional fields
that exist on the protected manifest but must never appear on the safe
report).

## 8. Schema-version transitions

- **`CALIBRATION_SCHEMA_VERSION` v2→v3**: `calibration_schema.py`'s
  three additive fields from §1. Persisted-artifact search performed at
  implementation time (repository-wide `grep` for
  `megb-03h-calibration-record-v2` outside this module's own source and
  tests, plus a check of any gitignored local trace-store path this
  repository's own `.gitignore` names): if no resumable, typed
  `CalibrationRunContext`/`CalibrationInvocationRecord`/
  `CalibrationTaskEvaluationRecord` artifact is found (matching every
  prior calibration-schema bump's own "no real persisted v1/v2 artifact
  exists" precedent), this is documented as the determination and no
  migration is performed. A committed historical **safe** report (e.g.
  any already-accepted `CalibrationSummaryReport` JSON under
  `docs/measurement/`) is explicitly distinguished from a resumable
  **typed calibration record** — the former is point-in-time evidence
  already accepted under its own schema version and is never
  "migrated"; only the latter would ever require a migration path, and
  only if one existed. Stale-v2 records (a payload stamped
  `calibration_schema_version="megb-03h-calibration-record-v2"`) are
  explicitly rejected by the existing `UnsupportedCalibrationSchemaVersionError`
  path — a dedicated regression test constructs a v2-stamped payload and
  confirms rejection by the v3-only module.
- **New `DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION`**: a fourth,
  independent schema family for `src/distributed/` (alongside
  `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION`,
  `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`, and the B.2C-introduced
  `OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION`), value
  `megb-03h2c3b3-distributed-provenance-manifest-v1`.
- **New `CALIBRATION_PROVENANCE_REPORT_SCHEMA_VERSION`**: a fifth,
  independent schema family, value
  `megb-03h2c3b3-calibration-provenance-report-v1`.
- **No change** to `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION`,
  `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`,
  `OFFLINE_E2E_QUALIFICATION_REPORT_SCHEMA_VERSION`,
  `FAULT_CONFORMANCE_REPORT_SCHEMA_VERSION`, `RESULT_SCHEMA_VERSION`,
  `CACHE_KEY_SCHEMA_VERSION`, or `AUDIT_RECORD_SCHEMA_VERSION` — all
  confirmed unchanged at verification time (§11).

## 9. Release-readiness rules

`CalibrationProvenanceReport.readiness` (an enum with exactly two
values, `CALIBRATION_PROVENANCE_READY_FOR_3C` /
`BLOCKED_CALIBRATION_PROVENANCE`) is **always derived in
`__post_init__`, never independently caller-settable** — the same
auto-compute-or-reject pattern used by every prior safe report in this
project. `READY_FOR_3C` requires **all** of:

1. `manifest.qualification_gate_readiness == "READY"` (distributed
   provenance itself is complete and `run_intent ==
   QUALIFICATION_CANDIDATE`).
2. Every bound `CalibrationInvocationRecord`'s
   `worker_execution_context_checksum` resolves in the manifest (§1) —
   missing/mismatched invocation provenance blocks readiness.
3. Calibration task-evaluation reconciliation (`reconcile_all`) raises
   nothing over the full bound set — incomplete calibration evidence
   (a task evaluation referencing a contributor absent from the bound
   invocation set, or any reconciliation mismatch) blocks readiness.
4. `admitted_completed_count == admitted_invocation_count` and
   `invalid_count == 0` (typed counts on the report itself; an
   incomplete or partially-invalid invocation set blocks readiness).
5. `measured_peak_concurrency` invariants (§6) hold (checked at
   construction time as a hard error, not merely a readiness input —
   see §6).

Any single failure yields `BLOCKED_CALIBRATION_PROVENANCE` with a
nonempty tuple of typed, safe blocker reasons (`ProvenanceGateFailureReason`
values plus a small new closed enum,
`CalibrationProvenanceBlockerReason`, for the calibration-specific
failure modes: `INVOCATION_PROVENANCE_UNRESOLVED`,
`TASK_RECONCILIATION_FAILED`, `INCOMPLETE_INVOCATION_EVIDENCE`) — never
free-form failure text, never a protected identifier.

## 10. Build/verify commands

New offline CLI, `src/distributed/calibration_provenance_report_cli.py`,
mirroring `offline_e2e_qualification_report_cli.py`'s and
`fault_conformance_cli.py`'s established shape exactly:

- `python -m src.distributed.calibration_provenance_report_cli build
  --output-dir <path>` — builds the synthetic manifest, calibration
  records, and report fresh, writing all three JSON files under
  `<path>` (a caller-supplied, temporary/synthetic directory — **never**
  a fixed repository path for the protected manifest/calibration
  artifacts; only the safe report may optionally also be persisted at a
  fixed `docs/measurement/` path, exactly as B.2C's own report is).
  Refuses to silently overwrite an existing, **differing** frozen
  artifact at the same path (byte-compares before writing; identical
  content is a deterministic-regeneration no-op, not an error).
- `python -m src.distributed.calibration_provenance_report_cli verify
  --output-dir <path>` — reads all three files back, re-validates every
  checksum (manifest, calibration records, report), re-runs
  `reconcile_distributed_provenance`/`reconcile_all`, and re-derives
  readiness, failing loudly (nonzero exit) on any mismatch, corrupt
  JSON, or missing file. Prints only safe fields (report contents) —
  never manifest or calibration-record contents — to stdout, mirroring
  the accepted CLIs' own "print no protected contents" discipline.
- Both commands require no network, Docker, cloud SDK, or credential of
  any kind — enforced structurally by the same dependency-direction
  test pattern already covering every other `src/distributed/` module
  (extended, not modified, to include the two new modules by filename).

## 11. Acceptance criteria

- `CALIBRATION_SCHEMA_VERSION` v3 implemented exactly as §1/§8 describe;
  stale-v2 rejection and v3 round-trip tests pass.
- `DistributedProvenanceManifest` implemented exactly as §2 describes;
  every negative-test category this authorization's own "Required
  negative tests" section names passes, including the worker-image/
  machine-type/region/zone/provisioning-class/implementation identity-
  change proof.
- `CalibrationTaskEvaluationRecord`'s no-new-field determination (§4) is
  explicit and tested.
- `CalibrationProvenanceReport` implemented exactly as §6/§9 describe;
  readiness is always derived; peak-concurrency invariant is a
  construction-time hard error, not a readiness input alone.
- Synthetic integration harness (offline, no candidate code/HumanEval/
  oracle/Docker/cloud) produces a full manifest→calibration→report
  chain, verified end-to-end by the harness's own tests and by the
  `verify` CLI command.
- No modification to `ReferenceRunContext`, `ReferenceResultCacheKey`,
  `ReferenceAuditRecord`, or any production cache/result schema.
- No modification to `DISTRIBUTED_PROVENANCE_SCHEMA_VERSION` or
  `DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION`.
- Full offline suite, strict mypy, pylint (exit code recorded), repeated
  concurrency tests, deterministic cross-process regeneration,
  fault-conformance CLI verification, offline B.2C report verification,
  version-registry validation, and dependency-direction/leakage scans
  all pass, per this authorization's own "Verification" section.
- No GCP, `gcloud`, cloud resource, Docker, or privileged-artifact access
  anywhere. H.2C.3C is not begun.

These criteria are frozen at this commit and are not changed after
implementation begins, per this authorization's own explicit
instruction. If implementation reveals an additional accepted-schema gap
beyond what §1 already scopes, the authorization's own instruction
applies: stop and report it rather than silently expanding scope.
