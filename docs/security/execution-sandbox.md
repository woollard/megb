# Execution Sandbox (MEGB-02)

This document describes the isolated candidate-execution substrate: what it
protects, how it is built and operated, and its known limitations. It
covers `src/execution/` (`protocol.py`, `wire.py`, `runner.py`,
`docker_backend.py`, `backend.py`) and `docker/runner/`.

For the condensed threat-model summary (protected assets, adversary model,
trust boundary only), see
[`execution-threat-model.md`](execution-threat-model.md). This document is
the canonical, detailed reference; that one is a short pointer here plus
the formal threat framing CLAUDE.md's ADR process expects.

## Statement of scope

**This is a research-grade Docker isolation baseline, not a formally
verified defense against container-runtime or kernel vulnerabilities.**
It relies on Docker's standard namespace/cgroup isolation, configured
correctly (no network, read-only rootfs, dropped capabilities, resource
limits, non-root user). It does not add isolation beyond what those
primitives provide, and does not defend against a kernel or `runc`/`containerd`
0-day that breaks container isolation itself. See "Known limitations"
below for the complete list.

## MEGB-03D upstream-comparison path: a separate, non-sandboxed execution path

MEGB-03D (`src/reference/parity.py`) needs to run the pinned upstream
EvalPlus implementation itself — `evalplus.eval.untrusted_check` — to
compare its classification against MEGB-02's. **This upstream-comparison
path is not part of the sandbox this document describes, is not this
sandbox weakened, and involves no untrusted or adversarial code:**

* **What actually runs there.** `untrusted_check` executes candidates from
  MEGB-03D's own fixed, hand-authored, version-controlled parity corpus
  (`src/reference/parity_corpus.py`) — never optimizer output, never a
  confirmatory experimental candidate, never anything from MEGB-05/06 (see
  that ticket's requirement 7). This corpus is committed source, reviewed
  the same way any other code in this repository is.
* **Which guard is disabled, and how.** EvalPlus's own
  `evalplus.eval.reliability_guard` sets a process memory limit via
  `resource.setrlimit(resource.RLIMIT_AS, ...)`. On at least one validation
  host used for MEGB-03D (macOS + CPython 3.14), that specific call fails
  unconditionally — confirmed by calling `resource.setrlimit(RLIMIT_AS,
  ...)` directly with several different limit values, all raising the same
  `ValueError: current limit exceeds maximum limit` regardless of the
  requested size; this is a platform/interpreter incompatibility, not a
  sizing problem, and without a workaround it crashes every single upstream
  classification before the candidate ever runs. `src.reference.parity`
  works around it using EvalPlus's own documented, supported escape hatch:
  setting the `EVALPLUS_MAX_MEMORY_BYTES` environment variable to `-1`,
  which `evalplus.eval.query_maximum_memory_bytes` treats as "no limit" and
  skips the `setrlimit` call entirely (see that function's own
  `if maximum_memory_bytes == -1: return None` branch — this is EvalPlus's
  own supported configuration path, not a patch to its source).
* **Why this does not weaken MEGB-02's sandbox enforcement.** The disabled
  guard is a process-level `RLIMIT_AS` call inside EvalPlus's own
  `multiprocessing.Process`-isolated comparison utility — a completely
  different code path, process, and enforcement mechanism from MEGB-02's
  Docker container limits. MEGB-02's `memory_mb` limit is a **kernel-enforced
  cgroup limit on the container itself** (`docker run --memory`), applied by
  the Linux/Docker Desktop VM kernel independently of anything any Python
  process does or doesn't call. Disabling EvalPlus's own in-process
  `setrlimit` guard has no effect whatsoever on that cgroup limit: it isn't
  the same mechanism, isn't in the same process, and MEGB-02's own
  `docker_backend.py` never imports or depends on `evalplus.eval.reliability_guard`
  in any way. The two are verified independently to still work as
  intended — MEGB-03D's own resource-exhausting parity candidates
  (`he55-resource-exhausting-memory`, `he55-resource-exhausting-infinite-loop`)
  are confirmed, via real execution, to still be safely OOM-killed /
  timed out inside MEGB-02's Docker containers with this guard disabled on
  the upstream side.
* **Scope of the workaround.** Confined to `src.reference.parity`'s own
  upstream-classification calls via a context manager
  (`_disabled_upstream_memory_guard`), which sets
  `EVALPLUS_MAX_MEMORY_BYTES` immediately before calling `untrusted_check`/
  `trusted_exec` and restores the environment variable to its exact prior
  state (removed if it was previously absent, restored to its previous
  value otherwise) via `try`/`finally` — even if the wrapped call raises.
  It is never set for the duration of any MEGB-02 execution, never touches
  `docker_backend.py`, and never persists past the single upstream call
  that needs it. Proven by dedicated regression tests
  (`tests/test_parity.py`, and the analogous pattern's own tests in
  `tests/test_reference_oracle.py` for the sibling `unbounded_int_str_digits`
  workaround) asserting the environment variable's before/after state is
  identical, including when the wrapped call raises.
* **Given this is genuinely a host/interpreter-specific quirk** (not
  universal to all macOS or all Python 3.14 installs, and not reproduced on
  every host), this workaround is scoped to remain narrowly applicable:
  only the parity module's own upstream-classification calls, only for the
  duration of each call, and only because the corpus it runs is fixed,
  small, and fully trusted.

## Security boundary and threat model

Every candidate invocation is untrusted, potentially adversarial code. The
boundary separates three roles:

```
Trusted evaluation controller (host process)
    |  serialized invocation, over the container's stdin
    v
Isolated candidate worker (fresh container, one per invocation)
    |  serialized result, over the container's stdout
    v
Trusted evaluation controller (host process)
```

The controller (`DockerPerInvocationBackend.execute`, in
`src/execution/docker_backend.py`) never executes candidate code directly —
it only runs `docker` CLI subprocesses and parses JSON. The candidate's
source is compiled and executed exclusively inside the container, by
`src/execution/runner.py` running as `main()`'s entry point.

Expected adversarial behaviors this design defends against: infinite loops,
excessive memory allocation, process/thread spawning, filesystem
inspection/modification, environment-variable inspection, network access,
subprocess execution, oversized stdout/stderr, interpreter termination, and
malformed protocol output. See "Known limitations" for what is out of
scope.

## What is and is not trusted

**Trusted (runs on the host, outside any container):**
- The evaluation controller process (`docker_backend.py`) and everything it
  imports.
- The `docker` CLI / Docker daemon itself (a supply-chain and
  runtime-security dependency of this whole design — see limitations).
- The pinned runner image's *build* (produced from `docker/runner/Dockerfile`,
  reviewed source, no candidate involvement).

**Untrusted (treated as adversarial):**
- `candidate_code` in every `CandidateExecutionRequest` — never `exec`'d or
  `eval`'d outside the container.
- Everything the candidate does at runtime inside the container: its
  stdout/stderr content, its return value, its exceptions, its attempts to
  read/write files, open sockets, spawn processes, or manipulate its own
  file descriptors.

**Deliberately never exposed to the candidate:** canonical solutions,
hidden tests, expected outputs, evaluator source, repository contents, host
environment variables, host filesystem contents. (Enforced by
`src/dataset.py`'s public/privileged view split for the corpus side, and by
this document's isolation controls for the execution side.)

## Container lifecycle and cleanup

One fresh container per invocation (`docker run --name megb-runner-<uuid>
-i ...`), never reused across invocations. Sequence:

1. Controller resolves the runner image's content-addressed ID
   (`_resolve_image_digest`) and serializes the request
   (`wire.serialize_request`, size-bounded by `ExecutionLimits.max_request_bytes`).
2. `docker run` is launched via `subprocess.Popen`, request piped to its
   stdin.
3. Controller waits up to `wall_time_sec + startup_cleanup_grace_sec`
   (default grace: 2.0s, a named, explicit `DockerPerInvocationBackend`
   constructor parameter — never silently folded into candidate-attributed
   timing; see "Controller wall time vs. candidate wall time" below).
4. On timeout: `docker kill` the container, then reap.
5. `docker inspect` reads `State.OOMKilled` and `State.ExitCode`.
6. Outcome is classified (see "Status classification" below).
7. **`docker rm -f` always runs, in a `finally` block, on every exit path** —
   normal completion, timeout, OOM, protocol failure, or infrastructure
   error. Verified by `test_no_containers_remain_after_adversarial_exit_paths`
   (`tests/test_execution_sandbox.py`), which runs normal/exception/timeout/
   OOM/fork-bomb scenarios and asserts zero leftover containers afterward,
   independently re-confirmed via a manual `docker ps -a` sweep.

No writable state carries across invocations: each container gets a fresh
`--tmpfs /tmp`, destroyed with the container. Verified by
`test_writable_state_does_not_carry_across_invocations`.

## Isolation controls

Every `docker run` invocation (`_build_docker_run_command` in
`docker_backend.py`) applies:

| Dimension | Control | Flag(s) | Verifying test |
|---|---|---|---|
| Filesystem | Read-only root; bounded, ephemeral scratch space | `--read-only --tmpfs /tmp:size=<temp_storage_mb>m,mode=1777` | `test_cannot_modify_root_filesystem`, `test_can_write_within_bounded_tmp` |
| Environment | No host env vars inherited (Docker's default — no `-e`/`--env-file` passed) | *(absence of flags)* | `test_cannot_read_host_env_canary` |
| Network | No network namespace access at all | `--network none` | `test_cannot_connect_to_network`, `test_cannot_resolve_dns`, `test_cannot_access_cloud_metadata_endpoint` |
| Privilege | Non-root user, all capabilities dropped, no privilege escalation | `--user 65532:65532 --cap-drop ALL --security-opt no-new-privileges` | `test_runtime_privilege_controls_are_actually_enforced` — checks effective UID != 0, `CapEff` in `/proc/self/status` is all zero, `NoNewPrivs: 1`, and `os.setuid(0)` is denied |
| PID / process count | Bounded process count | `--pids-limit <max_processes>` | `test_process_spawning_is_bounded` |
| Memory | Hard memory ceiling, no swap beyond it | `--memory <memory_mb>m --memory-swap <memory_mb>m` | `test_memory_exhaustion_is_reported_as_out_of_memory` |
| CPU | Bounded CPU quota | `--cpus <cpu_count>` | *(not directly probed; see limitations)* |
| File descriptors | Bounded open-file count | `--ulimit nofile=<max_open_files>:<max_open_files>` | *(not directly probed; see limitations)* |
| Wall-clock timeout | Controller-enforced, independent of the container | `subprocess.Popen.communicate(timeout=...)` + `docker kill` | `test_infinite_loop_times_out` |
| Output size | Bounded stdout/stderr, enforced live | `_BoundedTextBuffer` in `runner.py` (Python-level); raw fd writes discarded (OS-level) | `test_excessive_stdout_is_output_limit`, `test_continuous_raw_fd_write_is_bounded_by_timeout_not_left_running` |
| Filesystem read (host) | No bind mounts of any kind | *(absence of `-v`/`--mount`)* | `test_cannot_read_host_canary_file` |

Filesystem isolation is structural, not merely configured: the container
has no bind mount to any host path, so a candidate cannot read the
repository, dataset files, evaluator source, or arbitrary host paths
regardless of the read-only flag — there is simply nothing there to read.

## Status classification

`ExecutionStatus` (`src/execution/protocol.py`) deliberately excludes
`WRONG_ANSWER`/`PASSED` — those are evaluator-level judgments, out of scope
for this execution layer.

| Condition | Status | Detected by | Notes |
|---|---|---|---|
| Normal return | `COMPLETED` | runner | `return_value` populated |
| Invalid syntax | `SYNTAX_ERROR` | runner, at `compile()` | before any candidate code runs |
| Candidate raises | `CANDIDATE_EXCEPTION` | runner, generic handler | captured, never propagated |
| Recognized OS resource-exhaustion (`BlockingIOError`/`ChildProcessError`/`EAGAIN`/`ENOMEM`/thread-creation failure) | `PROCESS_LIMIT` | runner, heuristic (`_is_process_limit_error`) | best-effort; see limitations |
| `print()`/`sys.stdout`/`sys.stderr` output exceeds its byte budget | `OUTPUT_LIMIT` | runner, `_BoundedTextBuffer` raises on overflow | stops immediately, not on next timeout check |
| Wall-clock exceeded, container was running | `TIMEOUT` | controller, `subprocess.TimeoutExpired` + `docker inspect` shows the container was created | the common case |
| Wall-clock exceeded, container never created | `INFRASTRUCTURE_ERROR` | controller, `subprocess.TimeoutExpired` + container not found | e.g. a stalled image pull — not the candidate's fault |
| Kernel OOM-kill | `OUT_OF_MEMORY` | controller, `docker inspect` `State.OOMKilled` | takes precedence over stdout parsing |
| No parseable response (interpreter killed itself, garbled output, crash) | `INFRASTRUCTURE_ERROR` | controller, wire-protocol parse failure on stdout | includes `os._exit()` |
| Malformed/invalid incoming request | `PROTOCOL_ERROR` | runner, `wire.ProtocolError` on request parse | should not occur in practice — the controller always builds valid requests |

## Controller wall time vs. candidate wall time

`CandidateExecutionResult` carries two distinct timing fields:

- **`wall_time_sec`** — measured by the controller, covers the entire
  `docker run` lifecycle (container start, candidate execution, teardown).
  Always populated.
- **`candidate_wall_time_sec`** — measured by the *runner*, starting
  immediately before `compile()` and ending when a status is determined.
  Covers compilation, module-level code executed by `exec()`, and the
  entry-point call itself — not merely the final function invocation
  (proved by `test_candidate_wall_time_covers_module_level_code_not_just_the_call`,
  whose candidate does its slow work at module level with an instant
  function body). Only populated when the runner got to report it at all:
  `None` for `TIMEOUT`, `OUT_OF_MEMORY`, and `INFRASTRUCTURE_ERROR`, since
  in those cases the runner was killed externally or never started, and
  never measured its own duration.

The `startup_cleanup_grace_sec` added to a request's `wall_time_sec` before
the controller gives up on a container (default 2.0s) is a named,
documented, and tested controller setting — it is never blended into
`candidate_wall_time_sec`, and a container that never starts within it is
reported as `INFRASTRUCTURE_ERROR`, not `TIMEOUT` (see the table above).

## Raw Python output vs. raw-FD output

Two genuinely different channels exist, and they are handled differently
on purpose:

- **Ordinary Python output** (`print()`, `sys.stdout.write()`,
  `sys.stderr.write()`) is captured via `contextlib.redirect_stdout`/
  `redirect_stderr` into `_BoundedTextBuffer` instances. The bound is
  enforced *while* output is produced — `write()` raises
  `_OutputLimitExceeded` the instant the cumulative byte count crosses the
  configured limit, not after accumulating everything and truncating
  afterward. This propagates to `OUTPUT_LIMIT` immediately.
- **Raw file-descriptor output** — a candidate calling `os.write(1, ...)`
  or `os.write(2, ...)` directly bypasses Python's `sys.stdout`/`sys.stderr`
  objects entirely, so `redirect_stdout`/`redirect_stderr` alone cannot stop
  it. This is closed at the OS level instead: `runner._os_stdio_isolated()`
  `dup2`s the real fd 1/2 to `/dev/null` for the duration of the candidate
  call (saving the originals via `os.dup`), then restores them before the
  runner writes its own final result line. **Raw-fd output is therefore
  intentionally discarded, not captured** — it never appears in the
  reported `stdout`/`stderr` fields, and it cannot corrupt the runner's
  JSON result line no matter what the candidate does to fd 1 (confirmed
  even against a candidate that calls `os.close(1)`, replaces
  `sys.stdout` with a fake object, or `os.dup2`s fd 1 to a file it opened
  itself — see `test_candidate_closing_stdio_fds_*`,
  `test_candidate_replacing_sys_stdout_*`, and
  `test_candidate_dup2_hijack_of_fd1_*` in both `test_execution_runner.py`
  and `test_execution_sandbox.py`).
- A candidate that floods fd 1 directly in an infinite loop
  (`test_continuous_raw_fd_write_is_bounded_by_timeout_not_left_running`)
  has no `OUTPUT_LIMIT` backstop available to it (there's nothing to bound
  — the bytes go straight to `/dev/null`), so the wall-clock timeout is the
  only thing that stops it. This is confirmed to work: the test's candidate
  is reliably terminated as `TIMEOUT`, never left hanging and never
  producing a corrupted result.

## Known limitations

- `PROCESS_LIMIT` classification (`_is_process_limit_error` in
  `runner.py`) is a best-effort heuristic matching specific exception types
  and `errno` values (`BlockingIOError`, `ChildProcessError`,
  `EAGAIN`/`ENOMEM`, "can't start new thread"). It is not an exhaustive
  classification of every way an OS can signal resource exhaustion; an
  unrecognized resource error would fall through to `CANDIDATE_EXCEPTION`
  instead.
- Raw-fd output is silently discarded, not captured — by design (see
  above), but worth restating: a candidate that only writes via raw fd
  calls will show empty `stdout`/`stderr` in the result even though it
  produced output.
- The `INFRASTRUCTURE_ERROR`-vs-`TIMEOUT` "container never created" branch
  is verified via a direct unit test of `_classify_outcome`
  (`tests/test_docker_backend_classification.py`), not an end-to-end
  reproduction — triggering it for real requires a stalled image pull or
  similar `docker run` startup failure, which is not reliably reproducible
  in an automated test.
- CPU quota (`--cpus`) and open-file limit (`--ulimit nofile`) are applied
  on every invocation but have no dedicated adversarial test proving they
  are enforced (unlike memory, PID count, network, filesystem, and
  privilege, which all have a test forcing the limit and checking the
  outcome). This is a real test-coverage gap, not a known bypass.
- Docker image ID reproducibility depends on building with
  `--provenance=false --sbom=false` (see "Reproducibility" below) — without
  those flags, BuildKit embeds a build-timestamped attestation that changes
  the image ID on every rebuild even with byte-identical inputs.
- This is Docker's standard namespace/cgroup isolation, correctly
  configured — not a custom or hardened sandbox, and not evaluated against
  container-escape research or kernel-level exploits. A kernel or
  `runc`/`containerd` vulnerability that breaks container isolation itself
  is out of scope, consistent with MEGB-02's own stated non-goals ("does
  not... defend formally against container-runtime or kernel zero-day
  vulnerabilities").
- The fork-bomb adversarial test
  (`test_process_spawning_is_bounded`/`test_no_containers_remain_after_adversarial_exit_paths`)
  accepts either `PROCESS_LIMIT` or `TIMEOUT` as a passing outcome, since
  which one is observed first is a timing race between the `--pids-limit`
  rejection and the wall-clock timeout. Both are safe, contained outcomes.

## Local setup

Requires Docker (Docker Desktop on macOS, or a Docker Engine daemon on
Linux/CI) and this repository's Python virtual environment
(`pip install -r requirements.txt`).

```bash
# Build the runner image (see "Reproducibility" for the exact flags/why):
./docker/runner/compute_provenance.sh

# Offline tests (no Docker needed):
pytest -m "not docker"

# Docker-backed adversarial suite (requires the image above):
pytest -m docker
```

## CI requirements

See the CI workflow (`.github/workflows/ci.yml`) for the authoritative,
versioned definition. Summary: offline tests/mypy/pylint run on every push
and pull request; the Docker-backed adversarial suite runs in a separate
job on the same runner-image definition, and failures there are reported
visibly (never silently skipped) — see that file's comments for exactly
how the job fails loudly if Docker itself is unavailable.

## Reproducibility

Compute the full provenance chain (base-image digest, Dockerfile hash,
build-context hash, resulting image ID) with one command from the
repository root:

```bash
./docker/runner/compute_provenance.sh
```

This is the authoritative way to get current values — the ones below are a
snapshot and will go stale as the Dockerfile or `src/execution/` changes.

**Snapshot as of this writing:**

| Field | Value |
|---|---|
| Base image | `python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b` |
| Dockerfile SHA-256 | `cdf2fa8490f2a0dd2b8470e8d7218a864afe655d3018e56dd788a47bbe7caa29` |
| Build-context SHA-256 (`src/__init__.py` + `src/execution/*`) | `f74b115d682d3870f50799cc69ee1515e2bc07aabf2c1dfa17f56f25042626a6` |
| Resulting local image ID | `sha256:3ddfd2080085e256d7c7a787e3b470ef9e721abe49cbb3f9b4f4cf6db6abc8ee` |

**Why the base image is pinned by digest, not just tag:** `python:3.12-slim-bookworm`
as a tag is mutable — Debian security patches republish the same tag with
different content over time. Pinning by digest (the `@sha256:...` suffix)
means the base layer is byte-identical on every pull, forever, until
someone deliberately re-pins it.

**Why the runner image itself has no registry digest:** it is built
locally and never pushed, so it has no `RepoDigests` entry from a
registry. Its content-addressed local image ID (`docker inspect --format
'{{.Id}}' megb-runner:local`) serves the same purpose — a stable identifier
tied to exact byte content — without requiring a registry push merely to
obtain one. A registry-publishing workflow can be added later if
deployment requires it; it is out of scope here.

**Why `--provenance=false --sbom=false`:** BuildKit's default behavior
embeds a build-timestamped provenance/SBOM attestation into the image
manifest. This was verified empirically to make the resulting image ID
different on every rebuild even with byte-for-byte identical Dockerfile
and build context (three consecutive builds from an unchanged tree
produced three different image IDs). Disabling both flags restores the
property that the image ID is a pure function of content: two consecutive
builds with these flags produced identical IDs. `compute_provenance.sh`
always builds with both flags for this reason.

**Note:** a Software Bill of Materials (SBOM) for the runner image can
still be generated separately and on demand — e.g. `docker sbom
megb-runner:local` or `docker buildx build --sbom=true ...` into a
dedicated output — when one is actually needed (a release/audit process).
Disabling it in the default build path is purely about reproducibility of
the image ID; it is not a statement that SBOMs are unwanted.
