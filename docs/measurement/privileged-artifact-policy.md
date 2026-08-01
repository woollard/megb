# Privileged-Artifact Policy

## Status

Adopted (MEGB-03B artifact-finalization). Default policy for all subsequent
MEGB-03 subtasks that produce privileged/oracle artifacts (MEGB-03C onward),
not only MEGB-03B, per explicit authorization.

## Rule

Full bytes of a privileged research artifact — anything whose content must
never leak into the optimization-visible measurement path, or that is simply
too large to belong in version control — are never committed to git. What
gets committed instead is a small, structured **lock file** that anchors the
artifact's identity: its checksum, size, generation provenance, and where it
is expected to live on disk. The artifact itself is regenerated deterministically
from the pinned corpus and committed code, or restored from access-controlled
backup storage (see "Backup requirement" below).

**Why:**

* **Repository hygiene.** MEGB-03B's two full partition manifests are
  ~9.5 MB each. Git repositories do not shrink when large blobs are later
  removed — history retains every version ever committed — so keeping them
  out from the start is the only clean option; removing them after the fact
  would require rewriting history.
* **Privilege boundary.** Starting with MEGB-03C, privileged artifacts will
  carry oracle-relevant content (expected outputs, canonical-solution-derived
  evidence). Per CLAUDE.md's non-negotiable rule that S\*'s evidence must
  never reach the optimization process, keeping this content out of the
  version-controlled tree by default is a stronger guarantee than relying on
  every contributor to remember not to commit it — a lock-file-only policy
  makes the safe state the default state.
* **Reproducibility over storage.** This project's rigor requirement is
  deterministic, byte-stable reconstruction (see ADR 0001 and the MEGB-03A/B
  determinism fixes). A lock file that anchors identity via checksums is
  sufficient to *prove* an artifact is correct without storing its bytes —
  the artifact is either rebuilt from the pinned corpus and committed code,
  or restored from backup and then verified against the same lock.

## What is committed vs. privileged

For MEGB-03B specifically:

| Committed (in git) | Privileged (gitignored) |
|---|---|
| `artifacts/reference/partition/primary_experiment_task_manifest_redacted.json` (development case IDs only — never `reference_only_case_ids`) | `artifacts/privileged/reference/partition/primary_experiment_task_manifest.json` (full dev + reference-only split) |
| `artifacts/reference/partition/partition_validation_report.md` | `artifacts/privileged/reference/partition/reference_validation_task_manifest.json` (full 164-task case sets) |
| `artifacts/reference/partition/partition.lock.json` (this policy's anchor) | — |
| Deterministic generation implementation (`src/reference/partition.py`, `src/reference/partition_lock.py`, `src/reference/partition_cli.py`) and its tests | — |

The privileged directory root (`artifacts/privileged/`) is excluded via
`.gitignore` for the whole subtree, not just these two files — any later
MEGB-03 subtask that writes privileged artifacts under that root inherits the
exclusion automatically.

## The lock file

`partition.lock.json` (schema `partition-lock-v1`) is a `LockFile` containing
one `LockEntry` per privileged artifact
(`src/reference/partition_lock.py:LockEntry`). Each entry records:

* `artifact_id` — logical identity (e.g. `primary_experiment_task_manifest`).
* `privileged_path` — expected on-disk location.
* `schema_version`, `algorithm_version` — lock and partition-algorithm versions.
* `dataset_checksum`, `augmentation_checksums` — provenance of the corpus and
  any MEGB-03A.1 supplementary evidence that fed into this artifact.
* `partition_seed` — the deterministic ranking seed.
* `expected_task_count`, `expected_case_summary` — structural expectations.
* `size_bytes`, `logical_sha256` — the artifact's stabilized (wall-clock-free)
  size and content checksum. This is the value that's actually reproducible
  across separate build invocations; see "Determinism note" below.
* `generation_command`, `generating_code_revision`, `generating_code_dirty` —
  how to reproduce it and from what commit (`generating_code_dirty` records
  whether the working tree had uncommitted changes at generation time).
* `trusted_consumers` — which downstream subtasks/tickets are authorized to
  read this artifact (e.g. `MEGB-03C`).

## Build / verify CLI

```
python -m src.reference.partition_cli build [--force]
python -m src.reference.partition_cli verify
```

* `build` regenerates both manifests from the pinned corpus, writes the
  committed redacted view + validation report, writes the two privileged
  manifests, and writes `partition.lock.json`. If a privileged file already
  exists and differs from the freshly built one, `build` refuses to overwrite
  it (`FrozenArtifactConflictError`) unless `--force` is passed — this
  prevents accidentally destroying previously frozen evidence.
* `verify` regenerates both manifests from the pinned corpus and checks them
  against the committed lock: content checksum, size, source dataset/
  augmentation checksums, and (when the privileged file is present) its
  on-disk checksum and byte-for-byte match against the fresh rebuild. It
  never prints privileged case contents — only checksums, counts, and
  pass/fail booleans — and exits nonzero on any mismatch. If the on-disk file
  is missing, `verify` still succeeds as long as deterministic regeneration
  from the corpus matches the lock; the privileged bytes on disk are a
  convenience, not the source of truth.

**Determinism note:** manifest dataclasses carry a `generated_at` timestamp
and a nested `dataset_provenance.loaded_at` timestamp, both stamped fresh on
every build. Left unstripped, the on-disk privileged file would differ on
every rebuild even with byte-identical corpus and code — the same
determinism-bug class already found twice in this project (MEGB-03A's
inventory checksum, MEGB-03B's manifest checksum). The lock's `size_bytes`
and `logical_sha256`, and the privileged file's actual on-disk bytes, are
computed from a stabilized payload with those two fields blanked out, so
`build` and `verify` are reproducible across separate process invocations.

## Backup requirement

Privileged artifacts must be copied to separate, access-controlled backup
storage before they are consumed by experimental generation (i.e., before
MEGB-03D+ begins running candidates against measurement systems built from
these manifests). This backup is the recovery path if the privileged
directory is lost locally — the lock file proves an artifact's identity but
cannot itself reconstruct lost bytes faster than a full corpus rebuild.

This subtask documents the requirement only. No external upload is performed
here; the specific backup mechanism (destination, access control, rotation)
is a decision for whoever operates that storage and is out of scope for
MEGB-03B.

## Default policy going forward

This is the default handling for **all** MEGB-03 subtasks that produce
privileged or oracle artifacts, not a one-off for MEGB-03B. In particular,
MEGB-03C's expected-output/oracle construction must follow the same pattern:
oracle bytes live under `artifacts/privileged/...` and stay out of git; a
committed `*.lock.json` anchors their identity; a `build`/`verify` CLI mode
regenerates and checks them without printing privileged content; and any
existing frozen artifact is protected from silent overwrite.
