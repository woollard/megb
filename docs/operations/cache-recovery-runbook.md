# Reference-Result Cache and Audit: Operator Runbook

## Status

Produced by MEGB-03G.5. Operator procedures for
`src.reference.reference_cache.ReferenceResultCache` and
`src.reference.reference_audit.ReferenceAuditLog`, both driven in production
by `src.reference.reference_orchestrator.ReferenceOrchestrator` (MEGB-03G.3,
accepted). See [version-registry.md](../reference/version-registry.md) for
exact schema-version strings and
[privileged-artifact-policy.md](../measurement/privileged-artifact-policy.md#megb-03g-cache-audit-and-g4-benchmark-artifacts)
for the storage/classification table this runbook operationalizes.

**No command in this runbook deletes more than one explicitly-named file.**
There is no broad `rm -rf` over the cache or audit directory here — a
whole-directory wipe is a judgment call for whoever operates the system at
the time, informed by the diagnosis steps below, not a one-liner to run
routinely.

## Cache initialization

`ReferenceResultCache(cache_dir=None)` creates `cache_dir` (default
`artifacts/privileged/reference/cache/`) if it doesn't exist —
`self._cache_dir.mkdir(parents=True, exist_ok=True)` in the constructor. No
separate "init" step exists or is needed: the first `put()` call to a fresh
directory just works. The directory is gitignored
(`artifacts/privileged/` — see `.gitignore`); nothing here is ever committed.

## Interpreting `CacheDisposition` values

Every `get()`/`put()` returns a typed disposition rather than raising, except
for the one genuine caller-contract violation
(`NonCacheableResultError` — attempting to cache a non-`VALID` result).

| Disposition | Meaning | Operator action |
|---|---|---|
| `VALID_HIT` | Entry exists, passed every integrity/schema/self-consistency check, and its content reproduces its own stored cache key. Safe to reuse — no backend re-execution occurs. | None. This is the expected common case. |
| `MISS` | No entry exists for this key (`path.exists()` is `False`). | None — a normal cold-cache or new-key state. The orchestrator will execute and `put()`. |
| `STALE_INCOMPATIBLE` | Entry exists but its `cache_entry_schema_version` or `cache_key_schema_version` doesn't match what this code currently expects (i.e. it was written under an older schema before a breaking bump). | Do not attempt to reinterpret it. Either regenerate the result (the orchestrator will naturally treat this as a cache miss on the *new* key derived from current inputs and re-execute), or, only if a genuine migration is planned, write a dedicated migration script — never hand-edit the on-disk JSON. |
| `CORRUPT` | Entry exists, schema versions match, but something about its content is wrong: malformed JSON, missing `entry_checksum`, checksum mismatch (tamper/truncation), malformed nested payload, a stored key that doesn't match the requested key, a non-`VALID` stored result, or content that doesn't reproduce its own stored key. | See "Corrupt entries" below. |
| `WRITE_ACCEPTED` | `put()` succeeded — either a brand-new entry was written, or an identical entry already existed (idempotent no-op). | None. |
| `CONFLICTING_WRITE` | `put()` found a *different* valid entry already occupying this cache key (or a corrupt entry it refuses to silently overwrite). | See "Conflicting writes" below. Never forced past this without understanding why two different results produced the same key. |
| `STORAGE_INFRASTRUCTURE_FAILURE` | An `OSError` occurred reading or writing the entry (disk full, permissions, I/O error). | See "Storage failures" below. |

## Stale/incompatible entries

A `STALE_INCOMPATIBLE` disposition means the on-disk entry was written under
an older `CACHE_ENTRY_SCHEMA_VERSION` or `CACHE_KEY_SCHEMA_VERSION` than the
code currently running expects. This is expected and safe after any breaking
schema bump (this project's discipline: every schema correction bumps its
version and rejects every older one — see version-registry.md). It is
**never silently reinterpreted** under the new schema's field names.

Recovery: the orchestrator's own cache-first execution loop already treats
this the same as a miss — it re-executes and writes a fresh, current-schema
entry under the (likely also-changed) current cache key. No operator
intervention is required unless you need to reclaim disk space from
known-stale entries, in which case identify them explicitly (read each
entry's `cache_entry_schema_version` field and compare against the constant
currently imported from `reference_cache.py`) before removing any specific
file by name.

## Corrupt entries

A `CORRUPT` disposition means the entry cannot be trusted, for one of several
distinct reasons (see the table in `_check_envelope`/`_reconstruct_and_verify`
in `reference_cache.py`): malformed JSON, missing/mismatched checksum,
malformed nested payload, key/content mismatch, or a non-`VALID` stored
status. In every case, **the corrupt entry is never returned as a hit** — the
caller sees `CORRUPT`, not a silently-degraded result.

Recovery:
1. Read the specific file (`<cache_dir>/<key_digest>.json`) to understand
   which check failed — the `detail` string on the returned
   `CacheLookupResult` names it.
2. If the cause is understood (e.g. a known truncated write from a prior
   crash), remove that **one specific file** by its exact digest name. Do
   not glob-delete.
3. The orchestrator will treat the now-missing entry as a `MISS` and
   re-execute, producing a fresh valid entry.
4. If corruption is widespread (many entries affected), treat it as a
   storage-layer incident — investigate the underlying storage medium
   before assuming the cache logic itself is at fault; this cache uses
   atomic writes (temp file + `os.replace`) specifically to make partial
   writes from a killed process rare, not impossible.

## Conflicting writes

A `CONFLICTING_WRITE` on `put()` means a *different* valid entry already
occupies the requested cache key — the same key derived from what should be
outcome-affecting-identical inputs is now claiming two different results.
This should not happen in ordinary operation (the key binds every
outcome-affecting field — see version-registry.md's cache-key table) and
warrants investigation, not automatic resolution:

- Confirm whether the two candidate results really do differ (e.g. a
  nondeterministic candidate, or a version field that should have been but
  wasn't included in the cache key).
- Never force an overwrite of a `CONFLICTING_WRITE` — the refusal is the
  safety property. If a specific entry is confirmed wrong (e.g. it was
  written by a bug that has since been fixed), remove that one file by name
  and re-run, the same as for a corrupt entry.

## Storage failures

`STORAGE_INFRASTRUCTURE_FAILURE` wraps an `OSError` from the underlying
filesystem (disk full, permission denied, I/O error) on either read or
write. This is not a cache-logic defect — it is the cache faithfully
reporting that its storage medium is unavailable.

Recovery: resolve the underlying storage issue (free disk space, fix
permissions, address the I/O error) and retry. The orchestrator's retry
policy is scoped to `INVALID_INFRASTRUCTURE` measurement failures, not cache
storage failures directly — a storage failure surfaces to whatever called
`get()`/`put()`, which should be handled the same way any other
infrastructure-level retry is handled at the orchestration layer.

## Interruption and resumption

`ReferenceOrchestrator.run()` catches `KeyboardInterrupt` and returns a
typed `OrchestrationRunSummary` with `interrupted=True` rather than
propagating the exception — callers must check `summary.interrupted`
themselves (this is a deliberate, accepted design choice from MEGB-03G.3).
Accepted results up to the interruption point are preserved (already
written to the cache); nothing in flight is duplicated or silently dropped.

To resume: call `run()` again over the same work items. Every already-`put()`
result will be served as a `VALID_HIT`, so only the unstarted/incomplete
items actually execute. `OrchestrationRunSummary` reconciles exactly:
`accepted_work_items + invalid_work_items + unstarted_work_items ==
total_work_items` always holds, across both the interrupted and the resumed
run.

## Audit reconciliation

`ReferenceAuditLog.read_all()` returns every record in append order (empty
tuple if the log doesn't exist yet). To reconcile a run:

1. Read the `OrchestrationRunSummary` returned by `run()` for the expected
   counts (`total_work_items`, `cache_hit_keys`, `fresh_execution_keys`,
   `accepted_work_items`, `invalid_work_items`, `unstarted_work_items`).
2. Read the audit log's records for the same `run_id` (the `caller` field is
   stamped `f"{config.caller}:{run_id}"`) and confirm one record exists per
   invocation attempt, with `cache_disposition` values consistent with the
   summary's own hit/miss counts.
3. Repeated or adaptive querying is visible directly in the log — every
   attempt appends a new record; nothing is ever overwritten or removed, so
   a pattern of repeated invocations for the same task/candidate is
   observable by scanning for duplicate `task_id`/`candidate_id` pairs
   across records, not hidden by the storage layer.

## Safe cache invalidation without silent overwrite

There is no bulk "clear the cache" operation in this runbook, deliberately.
If you need to force re-execution of specific work:

- **One known-wrong entry:** remove that one `<key_digest>.json` file by
  exact name (computed via `cache_key_for(task_result).key_digest` for the
  specific task/candidate/context in question). The next `get()` call sees
  `MISS`, not a stale or wrong hit.
- **A schema-wide correction** (e.g. after a breaking `CACHE_ENTRY_SCHEMA_VERSION`
  bump): no action is needed — every old entry now reads as
  `STALE_INCOMPATIBLE` and is naturally bypassed; a full directory wipe is
  never required for correctness, only optionally for disk-space reclamation,
  and remains an explicit, deliberate operator decision outside this
  runbook's scope (the same posture MEGB-03G.4's own benchmark cache-clearing
  took before each corrected re-run: an explicit, narrowly-scoped
  `rm -rf artifacts/privileged/reference/g4_benchmark_cache` — never applied
  to the production cache directory, and always a conscious step taken by a
  human before a specific, understood re-run, not a scripted default).

## Confirming no candidate code or privileged case content was logged

Both the cache and the audit log are typed, schema-constrained artifacts —
this is a structural guarantee, not merely an operational habit, but it is
worth actively confirming after any change to either schema:

- **Cache entries** are the privileged full-fidelity store — they legitimately
  contain everything `ReferenceTaskResult` carries. The property to confirm
  here is different: that cache entries never leave `artifacts/privileged/`
  (gitignored) and are never exposed through any redacted projection or
  committed artifact. `tests/test_reference_cache.py` and
  `tests/test_result_redaction.py`'s feedback-leakage tests cover this.
- **Audit records** structurally cannot carry candidate code, case inputs,
  case identifiers, expected outputs, canonical solutions,
  `PrivilegedCaseDiagnostic` objects, or exception payloads — none of those
  has a field on `ReferenceAuditRecord` at all (`AUDIT_RECORD_FIELD_NAMES` is
  exhaustive and tested against `dataclasses.fields()` in
  `tests/test_reference_audit.py`). `result_artifact_location` is a cache-key
  digest or path pointer only, itself derived from version/checksum fields,
  never from raw case IDs or inputs. To confirm this holds after any future
  audit-schema change: assert the new field list against the same forbidden-
  fragment check `tests/test_reference_audit.py` already performs, and grep
  any sample audit log for literal candidate source strings as a second,
  independent check before trusting a new field is safe.
