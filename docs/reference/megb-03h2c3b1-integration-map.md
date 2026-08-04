# MEGB-03H.2C.3B.1 — Integration Map

**Status: implemented, standalone. No accepted schema modified.** Per
this checkpoint's own explicit integration-boundary instruction:
`src/reference/calibration_schema.py`, `result_schema.py`, `cache_key.py`,
and `reference_audit.py` are untouched, no schema version bumped. This
document is the required deliverable in place of that integration:
exactly which accepted schemas must be extended, and how, before
MEGB-03H.2C.3D qualification evidence is constructed, and before
MEGB-03H.2C.3F production results/cache entries are created.

**H.2C.3D is falsifiable without modifying an existing accepted schema
today.** The new `src/distributed/` package (provenance, identity,
qualification gate, safe summary, protected mapping) is fully
self-contained, fully tested, and does not require any accepted schema
change to exist or to be exercised. Nothing here triggers this
checkpoint's own "stop and report a narrow schema correction" clause —
there is no narrow schema correction to propose. The work below is
integration work for a *later*, separately-authorized checkpoint
(H.2C.3B.2, H.2C.3D, or H.2C.3F itself), not a blocking gap in this one.

## Before MEGB-03H.2C.3D may construct real qualification evidence

H.2C.3D's own qualifying run must produce, per invocation, a
`CalibrationInvocationRecord` (unchanged accepted schema) *and* a
`WorkerExecutionContext` (this checkpoint's new schema), plus one shared
`CalibrationRunContext` (unchanged) *and* one shared
`DistributedRunContext` (this checkpoint's new schema) for the whole run.
Today these are two entirely separate object graphs with no persisted
link between them. Required integration work, **not performed here**:

1. **Add a cross-reference field**, most likely `CalibrationRunContext.distributed_run_context_checksum: str`
   (sha256 hex, nullable/optional during the transition or required from
   the first H.2C.3D-tagged run onward — the exact nullability decision
   belongs to whichever checkpoint performs the bump) and
   `CalibrationInvocationRecord.worker_execution_context_checksum: str`
   (same pattern), each binding to
   `DistributedRunContext.run_context_checksum` /
   `WorkerExecutionContext.worker_context_checksum` respectively. This
   is additive (mirrors every prior H.2C.2A-era addition to this same
   schema) and would require a `CALIBRATION_SCHEMA_VERSION` bump
   (v2→v3), following the same no-migration-needed pattern already
   confirmed multiple times in this project's history (no real
   persisted calibration artifact exists anywhere in the repository
   today).
2. **Reconcile `host_runtime_identity_checksum`/`telemetry_policy_identity_checksum`**
   (on `WorkerExecutionContext`) against the real
   `HostRuntimeContext.host_context_checksum` /
   `TelemetryCollectionPolicy.policy_checksum` values a given invocation's
   `CalibrationRunContext` actually carries — both are already sha256
   hex over canonical JSON (this checkpoint's `CHECKSUM_ALGORITHM_VERSION`
   matches the scheme `calibration_schema.py` already uses, by
   construction), so the reconciliation is a direct equality check, not a
   new checksum scheme. Whichever checkpoint performs this integration
   should add a `reconcile_distributed_provenance(...)` function
   (mirroring `reconcile_task_evaluation`'s own existing shape) that
   rejects a calibration record whose declared
   `host_runtime_identity_checksum` does not match its own embedded
   `HostRuntimeContext`'s checksum.
3. **The H.2C.3D qualification report itself** (not yet designed; H.2C.3D
   is separately authorized) must embed or reference this checkpoint's
   `QualificationIdentity`/`QualificationGateResult`, mirroring
   `H2C2BQualificationReport.qualifying`'s own established precedent, and
   must call `evaluate_qualification_gate` before labeling any result
   qualifying, per the accepted audit's own explicit requirement.

## Before MEGB-03H.2C.3F may create production results/cache entries

Per the accepted audit's revised blocking precondition, the same
identity fields must additionally be integrated into **production**
result/cache identities — not only the calibration schema above — before
H.2C.3F persists any real result:

1. **`ReferenceRunContext`** (`src/reference/result_schema.py`) would gain
   an additive `distributed_run_context_checksum: str` field (nullable
   for non-distributed/local runs), participating in its existing
   dataclass equality check like every other field there. This is a
   breaking schema change under this project's own established
   discipline (`RESULT_SCHEMA_VERSION` v4→v5), since every prior
   `ReferenceRunContext` field addition (v2, v3, v4) has moved the
   version.
2. **`ReferenceResultCacheKey`** (`src/reference/cache_key.py`) would gain
   the fields from `ProductionIdentityProjection` — `environment_class`,
   `logical_environment_id`, `cloud_provider`,
   `network_isolation_policy_checksum`, `machine_type`,
   `provisioning_class`, `worker_image_digest`,
   `worker_implementation_version`, `host_runtime_identity_checksum`,
   `telemetry_policy_identity_checksum` — added to `_compute_key_digest`'s
   own hashed field list, exactly reproducing the "prevent unsafe reuse
   of a cached/audited result across materially different environments"
   requirement the accepted audit names. `CACHE_KEY_SCHEMA_VERSION`
   would move v2→v3. Deliberately **not** added: `distributed_run_id`
   (an identifier, not outcome-affecting, per this checkpoint's own
   `ProductionIdentityProjection` exclusion) and region/zone/CPU
   architecture/coordinator-or-fleet-version/retry-lease-policy (timing-
   only or audit-only, per the field-ownership matrix, and therefore
   correctly excluded from cache identity — including them would cause
   unnecessary cache misses across scientifically-equivalent
   environments, the opposite failure mode).
3. **`ReferenceAuditRecord`** (`src/reference/reference_audit.py`) would
   gain the same fields as (2) above, as safe identity/label values (this
   record already structurally excludes privileged content, and every
   field this checkpoint's `ProductionIdentityProjection` carries is
   already either a closed-enum value or a content-bound checksum — safe
   by the same standard this record already applies to its existing
   fields). `AUDIT_RECORD_SCHEMA_VERSION` would move v3→v4.
4. **A production-scope join** would be required between whichever
   distributed-execution backend eventually implements H.2C.3F's own
   worker fleet and `build_audit_record`/`cache_key_for`'s existing call
   sites, threading a `ProductionIdentityProjection` through
   alongside the `ReferenceTaskResult` those functions already take.

None of this is designed further here — per this checkpoint's own explicit
scope, only the map of *what* must change and *why* is produced, not the
schema correction itself. H.2C.3G's separate managed-model/candidate-
generation-plane schema boundary is unaffected by any of the above; it
remains entirely unreserved by this map, exactly as the field-ownership
matrix's "Managed-model provenance" section states.

## Summary table

| Accepted schema | File | Field(s) to add | Version move | Required before |
|---|---|---|---|---|
| `CalibrationRunContext` | `src/reference/calibration_schema.py` | `distributed_run_context_checksum` | v2→v3 | H.2C.3D |
| `CalibrationInvocationRecord` | `src/reference/calibration_schema.py` | `worker_execution_context_checksum` | v2→v3 (same bump as above) | H.2C.3D |
| `ReferenceRunContext` | `src/reference/result_schema.py` | `distributed_run_context_checksum` | v4→v5 | H.2C.3F |
| `ReferenceResultCacheKey` | `src/reference/cache_key.py` | the 10 `ProductionIdentityProjection` fields | v2→v3 | H.2C.3F |
| `ReferenceAuditRecord` | `src/reference/reference_audit.py` | the same 10 fields, as safe labels | v3→v4 | H.2C.3F |

## Related documents

- `docs/reference/megb-03h2c3b1-provenance-field-matrix.md` — the field-
  ownership matrix this map's field lists are drawn from.
- `docs/reference/megb-03h2c3a-gcp-provenance-audit.md` — the accepted
  audit this checkpoint implements.
- `src/distributed/` — the standalone provenance schema this map
  describes integrating.
