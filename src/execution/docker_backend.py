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


@dataclass(frozen=True)
class _ContainerInspectInfo:
    found: bool
    oom_killed: bool
    exit_code: int | None


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
    inspect_format = "{{.State.OOMKilled}}\t{{.State.ExitCode}}"
    result = subprocess.run(
        ["docker", "inspect", "--format", inspect_format, container_name],
        capture_output=True,
        text=True,
        timeout=_DOCKER_CLI_TIMEOUT_SEC,
        check=False,
    )
    if result.returncode != 0:
        return _ContainerInspectInfo(found=False, oom_killed=False, exit_code=None)
    oom_str, exit_code_str = result.stdout.strip().split("\t")
    return _ContainerInspectInfo(
        found=True,
        oom_killed=oom_str == "true",
        exit_code=int(exit_code_str) if exit_code_str else None,
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
    written failed to parse as a valid response at all). Trims the same
    trailing newline ``parse_response_message`` itself trims, so this
    always matches what was actually parsed (or attempted)."""
    if status in (
        ExecutionStatus.TIMEOUT,
        ExecutionStatus.OUT_OF_MEMORY,
        ExecutionStatus.INFRASTRUCTURE_ERROR,
    ):
        return None
    return len(stdout_bytes.rstrip(b"\n"))


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


class DockerPerInvocationBackend(ExecutionBackend):
    """Launches one fresh, isolated Docker container per candidate invocation."""

    def __init__(
        self,
        runner_image: str = DEFAULT_RUNNER_IMAGE,
        startup_cleanup_grace_sec: float = _DEFAULT_STARTUP_CLEANUP_GRACE_SEC,
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
        """
        self._runner_image = runner_image
        self._startup_cleanup_grace_sec = startup_cleanup_grace_sec

    def execute(  # pylint: disable=too-many-locals
        self, request: CandidateExecutionRequest
    ) -> CandidateExecutionResult:
        """Execute one untrusted candidate invocation in a fresh, isolated container.

        Cleans up the container on every exit path (normal completion,
        timeout, OOM kill, protocol failure, or infrastructure error).
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

            return CandidateExecutionResult(
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
            _docker_remove(container_name)


def execute_candidate(
    request: CandidateExecutionRequest, runner_image: str = DEFAULT_RUNNER_IMAGE
) -> CandidateExecutionResult:
    """Convenience wrapper around ``DockerPerInvocationBackend`` for scripts/tests.

    Evaluator code should depend on ``ExecutionBackend`` and construct a
    concrete backend explicitly, not call this function, so the execution
    strategy stays swappable.
    """
    return DockerPerInvocationBackend(runner_image).execute(request)
