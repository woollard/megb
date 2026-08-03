"""``DockerPerInvocationBackend``: one fresh container per candidate invocation.

Implements ``ExecutionBackend`` (see ``src/execution/backend.py``) per
MEGB-02: every candidate invocation runs in a fresh, isolated container with
no network access, a read-only root filesystem plus bounded scratch space, a
non-root unprivileged user, all capabilities dropped, and explicit
CPU/memory/process/file-descriptor limits. The controller enforces the
wall-clock timeout itself and always removes the container afterward,
regardless of outcome.

Evaluator code should depend on ``ExecutionBackend``, not on this class or
its per-invocation-container strategy directly — a future batched/pooled
backend may implement the same interface for performance.

See ``docs/security/execution-threat-model.md`` for the full threat model
and known residual risks, and
``docs/decisions/0002-execution-sandbox-design.md`` for the design
rationale behind the status-disambiguation strategy used here.
"""

import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

from src.execution.backend import ExecutionBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionLimits,
    ExecutionStatus,
)
from src.execution.telemetry import (
    CollectorFailureStage,
    ExecutionTelemetry,
    build_execution_telemetry,
    collector_failure_observation,
)
from src.execution.telemetry_collectors import (
    CollectorFactory,
    TelemetryCollector,
    safe_collector_cleanup,
    safe_collector_finalize,
    safe_collector_start,
)
from src.execution.wire import ProtocolError, parse_response_message, serialize_request

DEFAULT_RUNNER_IMAGE = "megb-runner:local"
BACKEND_ID = "docker"

_RUNNER_UID_GID = "65532:65532"
# Default value for DockerPerInvocationBackend's startup_cleanup_grace_sec:
# slack added to a candidate's own wall_time_sec to bound how long the
# controller waits for container start/stop overhead before concluding the
# invocation has failed to complete. This is controller bookkeeping only —
# it is never blended into candidate_wall_time_sec (measured independently
# by the runner itself) and does not extend the container's own
# --cpus/--memory/--pids-limit resource ceilings.
_DEFAULT_STARTUP_CLEANUP_GRACE_SEC = 2.0
_DOCKER_CLI_TIMEOUT_SEC = 15.0
# MEGB-03H.2C.2A: bounds on how long execute_with_telemetry() waits for a
# just-launched container's full id to become resolvable (via `docker
# inspect`) before giving up on telemetry collection for this invocation
# entirely -- bounded, non-busy-loop polling (a plain time.sleep between
# attempts), never affecting the candidate's own execution or the
# eventual CandidateExecutionResult.
_DEFAULT_TELEMETRY_CONTAINER_ID_POLL_INTERVAL_SEC = 0.02
_DEFAULT_TELEMETRY_CONTAINER_ID_WAIT_MAX_SEC = 2.0


@dataclass(frozen=True)
class _ContainerInspectInfo:
    found: bool
    oom_killed: bool
    exit_code: int | None
    # MEGB-03H.2C.2A terminal-state-proof correction: exit_code alone is
    # not evidence of termination -- Docker's Go template reports
    # State.ExitCode's zero value (0) for a still-RUNNING container just
    # as it would for a real successful exit. These three fields let a
    # caller (real_telemetry_collectors._confirm_container_terminal_state)
    # independently prove the container has actually stopped. Defaulted
    # so every pre-existing classification-only call site (which never
    # cared about terminal-state proof, only exit_code/oom_killed) is
    # unaffected.
    container_full_id: str = ""
    running: bool = False
    status: str = ""
    finished_at: str = ""


@lru_cache(maxsize=1)
def _docker_server_version() -> str:
    result = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=_DOCKER_CLI_TIMEOUT_SEC,
    )
    return result.stdout.strip()


@lru_cache(maxsize=8)
def _resolve_image_digest(image: str) -> str:
    """Resolve a content-addressed identifier for the runner image.

    Uses the image's content ID rather than a registry RepoDigest so this
    works identically whether or not the image has ever been pushed.
    """
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.Id}}", image],
        capture_output=True,
        text=True,
        check=True,
        timeout=_DOCKER_CLI_TIMEOUT_SEC,
    )
    return result.stdout.strip()


def _docker_inspect(container_name: str) -> _ContainerInspectInfo:
    inspect_format = (
        "{{.Id}}\t{{.State.OOMKilled}}\t{{.State.ExitCode}}\t"
        "{{.State.Running}}\t{{.State.Status}}\t{{.State.FinishedAt}}"
    )
    result = subprocess.run(
        ["docker", "inspect", "--format", inspect_format, container_name],
        capture_output=True,
        text=True,
        timeout=_DOCKER_CLI_TIMEOUT_SEC,
        check=False,
    )
    if result.returncode != 0:
        return _ContainerInspectInfo(found=False, oom_killed=False, exit_code=None)
    full_id, oom_str, exit_code_str, running_str, status, finished_at = (
        result.stdout.strip().split("\t")
    )
    return _ContainerInspectInfo(
        found=True,
        oom_killed=oom_str == "true",
        exit_code=int(exit_code_str) if exit_code_str else None,
        container_full_id=full_id,
        running=running_str == "true",
        status=status,
        finished_at=finished_at,
    )


def _docker_kill(container_name: str) -> None:
    subprocess.run(
        ["docker", "kill", container_name],
        capture_output=True,
        timeout=_DOCKER_CLI_TIMEOUT_SEC,
        check=False,
    )


def _docker_remove(container_name: str) -> None:
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True,
        timeout=_DOCKER_CLI_TIMEOUT_SEC,
        check=False,
    )


def _derive_terminating_signal(exit_code: int | None) -> int | None:
    if exit_code is not None and exit_code >= 128:
        return exit_code - 128
    return None


@dataclass(frozen=True)
class _ClassifiedOutcome:  # pylint: disable=duplicate-code,too-many-instance-attributes
    """The parts of a ``CandidateExecutionResult`` derived from one run's outcome.

    Structurally echoes several ``RunnerResponse`` field names (see
    ``wire.py``) because it is, in the common case, built directly from
    one — this is a correlated projection of the wire protocol's own
    schema, not independent duplication.
    """

    status: ExecutionStatus
    return_value: object
    exception_type: str | None
    exception_message: str | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    candidate_wall_time_sec: float | None
    infrastructure_error_detail: str | None
    observed_response_bytes: int | None


def observed_response_byte_count(*, status: ExecutionStatus, stdout_bytes: bytes) -> int | None:
    """The exact number of raw bytes the controller received on the
    container's stdout (wire-response) channel — never candidate stdout,
    which the runner captures separately and reports inside the parsed
    response — or ``None`` precisely when no completed response ever
    existed: ``TIMEOUT``/``OUT_OF_MEMORY`` (the container was killed before
    writing one) or ``INFRASTRUCTURE_ERROR`` (never started, or what was
    written failed to parse as a valid response at all).

    Deliberately measures ``stdout_bytes`` exactly as received —
    ``len(stdout_bytes)``, with no newline stripping, UTF-8 decoding, or
    JSON parsing first. ``parse_response_message`` (called separately, by
    ``_classify_outcome`` below) strips exactly one trailing newline
    *before* parsing, for its own, unrelated reason: the runner's own
    ``max_response_bytes`` size check (``wire.serialize_response``) never
    counted the framing newline ``main()`` appends after serialization
    succeeds, so the parser strips it first to keep its size check
    consistent with what the runner itself validated. That parsing-side
    convention must not leak into this telemetry count, which reports the
    real number of bytes this invocation put on the wire, framing byte
    included.
    """
    if status in (
        ExecutionStatus.TIMEOUT,
        ExecutionStatus.OUT_OF_MEMORY,
        ExecutionStatus.INFRASTRUCTURE_ERROR,
    ):
        return None
    return len(stdout_bytes)


def _classify_outcome(
    *,
    timed_out: bool,
    inspect_info: _ContainerInspectInfo,
    stdout_bytes: bytes,
    stderr_bytes: bytes,
    max_response_bytes: int,
) -> _ClassifiedOutcome:
    """Disambiguate TIMEOUT / OUT_OF_MEMORY / runner-reported / INFRASTRUCTURE_ERROR.

    Precedence: a controller-enforced timeout or a kernel OOM kill are only
    observable to the controller (the container never gets to report them
    itself), so they take priority over anything found on stdout.

    A controller timeout is only classified as candidate ``TIMEOUT`` when
    the container actually started (``inspect_info.found``): if ``docker
    run`` never even created a container within the allotted time, the
    candidate never got a chance to run at all, so that failure belongs to
    the execution infrastructure, not the candidate.
    """
    stderr = stderr_bytes.decode("utf-8", errors="replace")

    if timed_out:
        if not inspect_info.found:
            detail = (
                "container never started within the startup/cleanup grace "
                "period; this is an infrastructure failure, not a candidate "
                f"timeout; stderr={stderr[:2000]!r}"
            )
            return _ClassifiedOutcome(
                ExecutionStatus.INFRASTRUCTURE_ERROR, None, None, None, "", stderr, False, False,
                None, detail, None,
            )
        return _ClassifiedOutcome(
            ExecutionStatus.TIMEOUT, None, None, None, "", stderr, False, False, None, None, None
        )
    if inspect_info.oom_killed:
        return _ClassifiedOutcome(
            ExecutionStatus.OUT_OF_MEMORY, None, None, None, "", stderr, False, False, None,
            None, None,
        )

    try:
        runner_response = parse_response_message(stdout_bytes.rstrip(b"\n"), max_response_bytes)
    except ProtocolError as exc:
        detail = (
            f"failed to parse runner response: {exc}; "
            f"exit_code={inspect_info.exit_code}; stderr={stderr[:2000]!r}"
        )
        return _ClassifiedOutcome(
            ExecutionStatus.INFRASTRUCTURE_ERROR, None, None, None, "", stderr, False, False,
            None, detail, None,
        )

    return _ClassifiedOutcome(
        status=runner_response.status,
        return_value=runner_response.return_value,
        exception_type=runner_response.exception_type,
        exception_message=runner_response.exception_message,
        stdout=runner_response.stdout,
        stderr=runner_response.stderr,
        stdout_truncated=runner_response.stdout_truncated,
        stderr_truncated=runner_response.stderr_truncated,
        candidate_wall_time_sec=runner_response.candidate_wall_time_sec,
        infrastructure_error_detail=None,
        observed_response_bytes=observed_response_byte_count(
            status=runner_response.status, stdout_bytes=stdout_bytes
        ),
    )


def _build_docker_run_command(
    container_name: str, image: str, limits: ExecutionLimits
) -> list[str]:
    return [
        "docker",
        "run",
        "--name",
        container_name,
        "-i",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        f"/tmp:size={limits.temp_storage_mb}m,mode=1777",
        "--memory",
        f"{limits.memory_mb}m",
        "--memory-swap",
        f"{limits.memory_mb}m",
        "--cpus",
        str(limits.cpu_count),
        "--pids-limit",
        str(limits.max_processes),
        "--ulimit",
        f"nofile={limits.max_open_files}:{limits.max_open_files}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        _RUNNER_UID_GID,
        image,
    ]


def _resolve_container_id(container_name: str) -> str | None:
    """Read-only: this container's full content-addressed id, or
    ``None`` if it is not (yet) inspectable -- never a write, never
    ``docker exec``."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.Id}}", container_name],
        capture_output=True,
        text=True,
        timeout=_DOCKER_CLI_TIMEOUT_SEC,
        check=False,
    )
    if result.returncode != 0:
        return None
    container_id = result.stdout.strip()
    return container_id or None


def _wait_for_container_id(
    container_name: str, *, poll_interval_sec: float, max_wait_sec: float
) -> str | None:
    """Bounded, non-busy-loop wait (a plain ``time.sleep`` between
    attempts, never a tight spin) for the target container to become
    inspectable. Returns ``None`` if it never appears within the bound --
    a telemetry-collection-only concern, never surfaced to or affecting
    the candidate's own execution or ``CandidateExecutionResult``."""
    deadline = time.monotonic() + max_wait_sec
    while True:
        container_id = _resolve_container_id(container_name)
        if container_id is not None:
            return container_id
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll_interval_sec)


def _best_effort_collector_cleanup(collector: TelemetryCollector) -> None:
    """Used only when a ``BaseException`` interrupts execution before a
    started collector's ``finalize()`` ever ran: there is no observation
    to amend (the caller is exiting via the propagating exception
    regardless), so ``cleanup()`` is attempted and any exception it
    raises is discarded -- matching ``run_collector()``'s own cleanup-
    safety behavior for this same scenario."""
    try:
        collector.cleanup()
    except Exception:  # pylint: disable=broad-exception-caught
        pass


class DockerPerInvocationBackend(ExecutionBackend):
    """Launches one fresh, isolated Docker container per candidate invocation."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        runner_image: str = DEFAULT_RUNNER_IMAGE,
        startup_cleanup_grace_sec: float = _DEFAULT_STARTUP_CLEANUP_GRACE_SEC,
        telemetry_collector_factory: CollectorFactory | None = None,
        telemetry_container_id_poll_interval_sec: float = (
            _DEFAULT_TELEMETRY_CONTAINER_ID_POLL_INTERVAL_SEC
        ),
        telemetry_container_id_wait_max_sec: float = _DEFAULT_TELEMETRY_CONTAINER_ID_WAIT_MAX_SEC,
    ) -> None:
        """Construct a per-invocation Docker backend.

        Args:
            runner_image: The runner image to launch for each invocation.
            startup_cleanup_grace_sec: Slack added on top of a request's own
                ``wall_time_sec`` before the controller gives up waiting on
                a container, to absorb `docker run` start/stop overhead.
                Explicit and named so it is never silently folded into
                candidate-attributed timing (see ``candidate_wall_time_sec``
                on the result, which is measured by the runner itself).
            telemetry_collector_factory: Optional (MEGB-03H.2C.2A),
                ``None`` by default -- real telemetry collection is never
                silently turned on. When supplied, enables
                :meth:`execute_with_telemetry`; :meth:`execute` itself is
                completely unaffected either way.
            telemetry_container_id_poll_interval_sec/
            telemetry_container_id_wait_max_sec: Bounds on
                ``execute_with_telemetry()``'s bounded, non-busy-loop wait
                for the just-launched container to become inspectable
                before giving up on telemetry collection for that one
                invocation (never affecting the candidate's own
                execution). Configurable so offline tests need not wait
                the real-world default bound.
        """
        self._runner_image = runner_image
        self._startup_cleanup_grace_sec = startup_cleanup_grace_sec
        self._telemetry_collector_factory = telemetry_collector_factory
        self._telemetry_container_id_poll_interval_sec = telemetry_container_id_poll_interval_sec
        self._telemetry_container_id_wait_max_sec = telemetry_container_id_wait_max_sec

    def execute(self, request: CandidateExecutionRequest) -> CandidateExecutionResult:
        """Execute one untrusted candidate invocation in a fresh, isolated container.

        Cleans up the container on every exit path (normal completion,
        timeout, OOM kill, protocol failure, or infrastructure error).
        """
        result, _telemetry = self._execute_impl(request, collect_telemetry=False)
        return result

    def execute_with_telemetry(
        self, request: CandidateExecutionRequest
    ) -> tuple[CandidateExecutionResult, ExecutionTelemetry]:
        """Execute one invocation exactly as :meth:`execute` does,
        additionally collecting peak-memory/peak-process-count telemetry
        around it via the configured ``telemetry_collector_factory``
        (MEGB-03H.2C.2A).

        Raises :class:`ValueError` if no factory was configured at
        construction -- telemetry collection must be explicitly enabled,
        never silently skipped in a way that could be mistaken for
        "collected but unavailable".
        """
        if self._telemetry_collector_factory is None:
            raise ValueError(
                "execute_with_telemetry() requires a telemetry_collector_factory to "
                "be configured at construction time"
            )
        result, telemetry = self._execute_impl(request, collect_telemetry=True)
        assert telemetry is not None
        return result, telemetry

    def _execute_impl(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        self, request: CandidateExecutionRequest, *, collect_telemetry: bool
    ) -> tuple[CandidateExecutionResult, ExecutionTelemetry | None]:
        """Shared implementation for :meth:`execute`/
        :meth:`execute_with_telemetry`. When ``collect_telemetry`` is
        ``False``, no collector code path executes at all -- this is
        byte-for-byte and status-for-status identical to H.2C.1's own
        ``execute()``, so telemetry-disabled behavior is provably
        unaffected by this checkpoint's changes.
        """
        invocation_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()
        container_name = f"megb-runner-{invocation_id}"
        image_digest = _resolve_image_digest(self._runner_image)

        request_payload = serialize_request(request)
        command = _build_docker_run_command(container_name, self._runner_image, request.limits)

        timed_out = False
        start = time.monotonic()
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        memory_collector: TelemetryCollector | None = None
        process_collector: TelemetryCollector | None = None
        memory_observation = None
        process_observation = None

        if collect_telemetry:
            factory = self._telemetry_collector_factory
            assert factory is not None
            container_id = _wait_for_container_id(
                container_name,
                poll_interval_sec=self._telemetry_container_id_poll_interval_sec,
                max_wait_sec=self._telemetry_container_id_wait_max_sec,
            )
            if container_id is None:
                memory_observation = collector_failure_observation(CollectorFailureStage.START)
                process_observation = collector_failure_observation(CollectorFailureStage.START)
            else:
                memory_collector, memory_identity = factory.build_memory_collector(
                    container_id=container_id, container_name=container_name
                )
                process_collector, process_identity = factory.build_process_count_collector(
                    container_id=container_id, container_name=container_name
                )
                memory_observation = safe_collector_start(
                    memory_collector, method_identity=memory_identity
                )
                process_observation = safe_collector_start(
                    process_collector, method_identity=process_identity
                )

        try:
            try:
                stdout_bytes, stderr_bytes = proc.communicate(
                    input=request_payload,
                    timeout=request.limits.wall_time_sec + self._startup_cleanup_grace_sec,
                )
            except subprocess.TimeoutExpired:
                timed_out = True
                _docker_kill(container_name)
                stdout_bytes, stderr_bytes = proc.communicate()
            wall_time_sec = time.monotonic() - start
            inspect_info = _docker_inspect(container_name)
            outcome = _classify_outcome(
                timed_out=timed_out,
                inspect_info=inspect_info,
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
                max_response_bytes=request.limits.max_response_bytes,
            )

            if memory_collector is not None and memory_observation is None:
                memory_observation = safe_collector_finalize(memory_collector)
            if process_collector is not None and process_observation is None:
                process_observation = safe_collector_finalize(process_collector)

            result = CandidateExecutionResult(
                invocation_id=invocation_id,
                status=outcome.status,
                return_value=outcome.return_value,
                exception_type=outcome.exception_type,
                exception_message=outcome.exception_message,
                wall_time_sec=wall_time_sec,
                candidate_wall_time_sec=outcome.candidate_wall_time_sec,
                exit_code=inspect_info.exit_code,
                terminating_signal=_derive_terminating_signal(inspect_info.exit_code),
                stdout=outcome.stdout,
                stderr=outcome.stderr,
                stdout_truncated=outcome.stdout_truncated,
                stderr_truncated=outcome.stderr_truncated,
                backend_id=BACKEND_ID,
                backend_version=_docker_server_version(),
                runner_image_digest=image_digest,
                protocol_version=request.protocol_version,
                limits=request.limits,
                started_at=started_at,
                infrastructure_error_detail=outcome.infrastructure_error_detail,
                request_bytes=len(request_payload),
                observed_response_bytes=outcome.observed_response_bytes,
            )
        finally:
            if memory_collector is not None:
                if memory_observation is not None:
                    memory_observation = safe_collector_cleanup(
                        memory_collector, memory_observation
                    )
                else:
                    _best_effort_collector_cleanup(memory_collector)
            if process_collector is not None:
                if process_observation is not None:
                    process_observation = safe_collector_cleanup(
                        process_collector, process_observation
                    )
                else:
                    _best_effort_collector_cleanup(process_collector)
            _docker_remove(container_name)

        if not collect_telemetry:
            return result, None
        assert memory_observation is not None
        assert process_observation is not None
        telemetry = build_execution_telemetry(
            result, peak_memory=memory_observation, peak_process_count=process_observation
        )
        return result, telemetry


def execute_candidate(
    request: CandidateExecutionRequest, runner_image: str = DEFAULT_RUNNER_IMAGE
) -> CandidateExecutionResult:
    """Convenience wrapper around ``DockerPerInvocationBackend`` for scripts/tests.

    Evaluator code should depend on ``ExecutionBackend`` and construct a
    concrete backend explicitly, not call this function, so the execution
    strategy stays swappable.
    """
    return DockerPerInvocationBackend(runner_image).execute(request)
