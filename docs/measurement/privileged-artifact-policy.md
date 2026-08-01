# Privileged-Artifact Policy

## Status

Adopted (MEGB-03B artifact-finalization) and applied (MEGB-03C oracle
construction, MEGB-03D parity/supplementary validation). Default policy for
all subsequent MEGB-03 subtasks that produce privileged/oracle artifacts,
not only MEGB-03B/03C/03D, per explicit authorization.

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

## MEGB-03C: the oracle artifacts

MEGB-03C applies this same policy to the trusted expected-output oracle,
extended with an access-model requirement MEGB-03B didn't need: three
**physically separated** privileged files, each authorized for a different,
disjoint consumer.

| Artifact | Committed / Privileged | Authorized consumer |
|---|---|---|
| `artifacts/reference/oracle/reference_validation_composite_manifest.json` | Committed — index only (case counts + development-pool case IDs; never reference-only or `HumanEval/39` case IDs, never expected-output bytes) | The 164-task validation workflow (MEGB-03D), to know which artifact to open |
| `artifacts/reference/oracle/oracle.lock.json` | Committed — this policy's anchor | Anyone verifying the oracle's identity |
| `artifacts/privileged/reference/oracle/development_oracle.json` | Privileged — 163 tasks × 40 development-pool cases | MEGB-04's trusted side only |
| `artifacts/privileged/reference/oracle/reference_only_oracle.json` | Privileged — 163 tasks × every reference-only case | S\* only |
| `artifacts/privileged/reference/oracle/reference_validation_only_oracle.json` | Privileged — `HumanEval/39`'s complete 12-case domain | MEGB-03D only |

Candidate code and candidate-generation/selection runtimes are authorized
for **none** of the three privileged files — this is enforced by omission
(no runtime is ever listed in any artifact's `trusted_consumers`), not by a
separate denylist. `oracle_lock.py:OracleLockEntry.trusted_consumers` records
each artifact's authorized consumer for exactly this reason (requirement 10
of MEGB-03C's execution amendment); `tests/test_reference_oracle_lock.py`
asserts the three consumer sets are mutually disjoint.

The oracle lock (`oracle-lock-v1`) extends `partition.lock.json`'s fields
with oracle-specific identity: `comparison_profile_version`,
`canonical_solution_hashes` (per task, so a canonical-solution edit is
detectable independent of a dataset-version bump), and `partition_checksum`
(binding the oracle to the exact MEGB-03B manifest it was built from).
Build/verify:

```
python -m src.reference.oracle_cli build [--force]
python -m src.reference.oracle_cli verify
```

Both subcommands first run the MEGB-03B partition-lock verification
in-process and refuse to continue if it fails — an oracle built against a
partition that has silently drifted would be keyed to case sets the
committed/privileged partition manifests no longer describe.

**Resource note:** unlike MEGB-03B's manifests, the two experimental-pool
oracle files are large (development ≈ 460 MB, reference-only ≈ 720 MB on
the real corpus) — legitimate given a handful of HumanEval tasks (e.g.
HumanEval/83, HumanEval/139) have canonical solutions whose output on their
largest `plus_input` cases is an integer with over a million digits. Both
stay fully outside git via the same `artifacts/privileged/` exclusion.

## Backup requirement (MEGB-03C)

Per the same backup requirement as MEGB-03B, all three privileged oracle
artifacts must be copied to separate, access-controlled backup storage
before MEGB-03D+ begins consuming them. No external upload is performed in
MEGB-03C; the backup mechanism itself remains out of scope.

## MEGB-03D: the parity artifact

MEGB-03D applies the same policy to its upstream-vs-MEGB classification
comparison on the frozen parity corpus.

| Artifact | Committed / Privileged | Content |
|---|---|---|
| `artifacts/reference/parity/parity_report_redacted.json` | Committed — redacted | Per candidate: `candidate_id`, `task_id`, `category`, `candidate_source_sha256`, `upstream_outcome`, `megb_outcome`, `agree` (bool), plus `candidate_count`/`agreement_count` aggregates. No free-text mismatch detail, no per-side pass/fail counts. |
| `artifacts/reference/parity/parity.lock.json` | Committed — this policy's anchor | Identity/checksum/provenance only, mirroring `oracle.lock.json`'s shape. |
| `artifacts/privileged/reference/parity/parity_results.json` | Privileged | The full `ParityResult` list (per-side detail strings, e.g. "6/999 mismatched") plus the `EnvironmentRecord` (pinned versions/APIs). |

Unlike MEGB-03B/03C, the actual candidate *source code* here is not a
byte-payload concern — it's OUR OWN hand-authored test corpus, already
fully visible as committed Python source in `src/reference/parity_corpus.py`,
not model/optimizer output or S\* evidence. What the privileged/redacted
split protects instead is the more granular per-side mismatch detail (which
could hint at exact input/output behavior beyond a bare pass/fail label) —
kept privileged per requirement 5's "avoid exposing hidden expected outputs
in public reports."

`EnvironmentRecord` (requirement 11) records the pinned `evalplus`/
`human-eval`/Python/NumPy versions, the specific EvalPlus internal APIs this
module depends on (`evalplus.eval.untrusted_check`, `evalplus.eval.is_floats`,
`evalplus.eval._special_oracle._poly`, `evalplus.gen.util.trusted_exec`,
...), the MEGB-02 backend ID, and the runner image digest actually used —
and, being nested inside the hashed artifact, any drift in these values
changes the artifact checksum, so `parity_cli.py verify` already refuses a
stale environment via the ordinary checksum-mismatch path (no separate
mechanism needed).

Build/verify:

```
python -m src.reference.parity_cli build [--force]
python -m src.reference.parity_cli verify
```

`build` refuses to freeze anything (writes neither the redacted report nor
the privileged artifact nor the lock) if any candidate shows an unresolved
upstream/MEGB classification disagreement — printing only candidate
id/task/category/outcome-label detail, never expected-output content.

**Environment note:** at least one validation host used for this subtask
has `evalplus.eval.reliability_guard`'s memory-limit call
(`resource.setrlimit(RLIMIT_AS, ...)`) fail unconditionally (a macOS +
CPython 3.14 incompatibility, confirmed independent of the requested
limit). `src.reference.parity` works around this the same documented way
EvalPlus itself supports (`EVALPLUS_MAX_MEMORY_BYTES=-1`), scoped to the
call and restored afterward — see that module's docstring. The one
memory-exhausting parity candidate is deliberately sized (~2 GB) to be safe
to run unprotected on an 8 GB+ host rather than relying on this guard being
functional. For the full security analysis of this workaround — which
guard is disabled, why it does not weaken MEGB-02's own container-level
enforcement, and confirmation that the prior process state is always
restored — see
[`docs/security/execution-sandbox.md`](../security/execution-sandbox.md#megb-03d-upstream-comparison-path-a-separate-non-sandboxed-execution-path).

## Backup requirement (MEGB-03D)

Same requirement, same scope note: the one privileged parity artifact must
be copied to separate, access-controlled backup storage before MEGB-03E+
begins consuming it. No external upload performed here.

## Default policy going forward

This is the default handling for **all** MEGB-03 subtasks that produce
privileged or oracle artifacts, not a one-off for MEGB-03B, 03C, or 03D.
Any later subtask producing its own privileged artifacts should follow the
same pattern: bytes live under `artifacts/privileged/...` and stay out of
git; a committed `*.lock.json` anchors their identity; a `build`/`verify`
CLI mode regenerates and checks them without printing privileged content;
any existing frozen artifact is protected from silent overwrite; and, where
different consumers are authorized for different subsets of the data (as
with MEGB-03C's three oracle files), each subset is physically separated
into its own file rather than access-controlled by convention alone.
