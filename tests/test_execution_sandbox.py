"""Adversarial sandbox integration tests for the Docker-backed execution worker.

Requires a running Docker daemon and the ``megb-runner:local`` image (see
``docker/runner/Dockerfile`` and ``docs/security/execution-sandbox.md`` for
the build command). These tests spin up real containers and are
substantially slower than the rest of the suite; run with
``pytest -m docker``.
"""

import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest

from src.execution.docker_backend import execute_candidate
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionLimits,
    ExecutionStatus,
)
from tests._execution_fixtures import DUP2_HIJACK_FD1_CANDIDATE_CODE

pytestmark = pytest.mark.docker


def _run(
    candidate_code: str,
    entry_point: str = "f",
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    limits: ExecutionLimits | None = None,
) -> CandidateExecutionResult:
    request = CandidateExecutionRequest(
        candidate_code=candidate_code,
        entry_point=entry_point,
        args=args,
        kwargs=kwargs or {},
        limits=limits or ExecutionLimits(),
        protocol_version="1",
    )
    return execute_candidate(request)


# --- 1: normal return value ---------------------------------------------


def test_normal_return_value_completes() -> None:
    """A well-behaved candidate returns its value with COMPLETED status."""
    result = _run("def f(x, y):\n    return x + y\n", args=(2, 3))

    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value == 5
    assert result.exit_code == 0


# --- 2: raises a Python exception ----------------------------------------


def test_candidate_exception_is_captured() -> None:
    """A candidate that raises is reported as CANDIDATE_EXCEPTION, not a crash."""
    result = _run("def f():\n    raise ValueError('boom')\n")

    assert result.status == ExecutionStatus.CANDIDATE_EXCEPTION
    assert result.exception_type == "ValueError"


# --- 3: invalid syntax ----------------------------------------------------


def test_invalid_syntax_is_classified_distinctly() -> None:
    """Invalid candidate source is SYNTAX_ERROR."""
    result = _run("def f(:\n    pass\n")

    assert result.status == ExecutionStatus.SYNTAX_ERROR


# --- 4: infinite loop -> TIMEOUT ------------------------------------------


def test_infinite_loop_times_out() -> None:
    """A candidate that never returns is killed and reported as TIMEOUT."""
    result = _run(
        "def f():\n    while True:\n        pass\n",
        limits=ExecutionLimits(wall_time_sec=1.0),
    )

    assert result.status == ExecutionStatus.TIMEOUT
    assert result.wall_time_sec < 10.0


# --- 5: memory exhaustion -> OUT_OF_MEMORY ---------------------------------


def test_memory_exhaustion_is_reported_as_out_of_memory() -> None:
    """A candidate that exceeds its memory limit is OOM-killed and reported as such."""
    result = _run(
        (
            "def f():\n"
            "    data = []\n"
            "    while True:\n"
            "        data.append(bytearray(10 * 1024 * 1024))\n"
        ),
        limits=ExecutionLimits(wall_time_sec=10.0, memory_mb=64),
    )

    assert result.status == ExecutionStatus.OUT_OF_MEMORY


# --- 6: process spawning is bounded ----------------------------------------


def test_process_spawning_is_bounded() -> None:
    """A candidate that forks until blocked is contained, not left to destabilize the host."""
    result = _run(
        (
            "import os\n"
            "def f():\n"
            "    forked = 0\n"
            "    for _ in range(10000):\n"
            "        pid = os.fork()\n"
            "        if pid == 0:\n"
            "            while True:\n"
            "                pass\n"
            "        forked += 1\n"
            "    return forked\n"
        ),
        limits=ExecutionLimits(wall_time_sec=5.0, max_processes=16),
    )

    # Contained one way or another: either the runner itself observes the
    # OS resource error (PROCESS_LIMIT) or the container is killed by our
    # own wall-clock timeout before it can destabilize anything. What must
    # never happen is COMPLETED (unbounded forking succeeding) or the test
    # process/host being affected.
    assert result.status in (ExecutionStatus.PROCESS_LIMIT, ExecutionStatus.TIMEOUT)


# --- 7: excessive stdout -> OUTPUT_LIMIT ------------------------------------


def test_excessive_stdout_is_output_limit() -> None:
    """A candidate that floods stdout is stopped and reported as OUTPUT_LIMIT."""
    result = _run(
        "def f():\n    while True:\n        print('x' * 4096)\n",
        limits=ExecutionLimits(wall_time_sec=5.0),
    )

    assert result.status == ExecutionStatus.OUTPUT_LIMIT
    assert result.stdout_truncated is True


# --- 8: cannot read a host-side canary file ---------------------------------


def test_cannot_read_host_canary_file(tmp_path: Path) -> None:
    """A candidate cannot read a file that exists on the host but is not mounted."""
    canary_path = tmp_path / "canary_secret.txt"
    canary_secret = f"secret-{uuid.uuid4()}"
    canary_path.write_text(canary_secret)

    result = _run(
        (
            "def f(path):\n"
            "    try:\n"
            "        with open(path) as fh:\n"
            "            return fh.read()\n"
            "    except OSError as exc:\n"
            "        return type(exc).__name__\n"
        ),
        args=(str(canary_path),),
    )

    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value != canary_secret
    assert result.return_value in ("FileNotFoundError", "NotADirectoryError")


# --- 9: cannot read a host environment-variable canary -----------------------


def test_cannot_read_host_env_canary(monkeypatch: pytest.MonkeyPatch) -> None:
    """A candidate cannot see an environment variable set in the controller's process."""
    canary_secret = f"secret-{uuid.uuid4()}"
    monkeypatch.setenv("MEGB_TEST_CANARY_SECRET", canary_secret)

    result = _run(
        "import os\ndef f():\n    return os.environ.get('MEGB_TEST_CANARY_SECRET')\n"
    )

    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value is None


# --- 10: cannot modify the root filesystem ----------------------------------


def test_cannot_modify_root_filesystem() -> None:
    """A candidate cannot write anywhere outside the bounded /tmp scratch space."""
    result = _run(
        (
            "def f():\n"
            "    try:\n"
            "        with open('/etc/megb-writetest', 'w') as fh:\n"
            "            fh.write('pwned')\n"
            "        return 'wrote'\n"
            "    except OSError as exc:\n"
            "        return type(exc).__name__\n"
        )
    )

    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value in ("OSError", "PermissionError", "ReadOnlyFileSystemError")


# --- 11: can write within the bounded temp directory ------------------------


def test_can_write_within_bounded_tmp() -> None:
    """Writable scratch space under /tmp works normally."""
    result = _run(
        (
            "def f():\n"
            "    with open('/tmp/scratch.txt', 'w') as fh:\n"
            "        fh.write('ok')\n"
            "    with open('/tmp/scratch.txt') as fh:\n"
            "        return fh.read()\n"
        )
    )

    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value == "ok"


# --- 12: cannot connect to an external network address ----------------------


def test_cannot_connect_to_network() -> None:
    """A candidate cannot open an outbound TCP connection."""
    result = _run(
        (
            "import socket\n"
            "def f():\n"
            "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    s.settimeout(3)\n"
            "    try:\n"
            "        s.connect(('8.8.8.8', 53))\n"
            "        return 'connected'\n"
            "    except OSError as exc:\n"
            "        return type(exc).__name__\n"
        ),
        limits=ExecutionLimits(wall_time_sec=8.0),
    )

    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value != "connected"


# --- 13: cannot resolve a DNS hostname ---------------------------------------


def test_cannot_resolve_dns() -> None:
    """A candidate cannot resolve an external hostname."""
    result = _run(
        (
            "import socket\n"
            "def f():\n"
            "    try:\n"
            "        return socket.gethostbyname('example.com')\n"
            "    except OSError as exc:\n"
            "        return type(exc).__name__\n"
        ),
        limits=ExecutionLimits(wall_time_sec=8.0),
    )

    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value == "gaierror"


# --- 14: cannot access a cloud metadata endpoint -----------------------------


def test_cannot_access_cloud_metadata_endpoint() -> None:
    """A candidate cannot reach the common cloud-instance metadata address."""
    result = _run(
        (
            "import socket\n"
            "def f():\n"
            "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    s.settimeout(3)\n"
            "    try:\n"
            "        s.connect(('169.254.169.254', 80))\n"
            "        return 'connected'\n"
            "    except OSError as exc:\n"
            "        return type(exc).__name__\n"
        ),
        limits=ExecutionLimits(wall_time_sec=8.0),
    )

    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value != "connected"


# --- 15: interpreter termination ---------------------------------------------


def test_interpreter_termination_is_infrastructure_error() -> None:
    """A candidate that kills the interpreter outright cannot fake a result."""
    result = _run("import os\ndef f():\n    os._exit(1)\n")

    assert result.status == ExecutionStatus.INFRASTRUCTURE_ERROR
    assert result.infrastructure_error_detail is not None


# --- 16: malformed protocol output --------------------------------------------


def test_raw_fd_write_cannot_corrupt_the_protocol_channel() -> None:
    """Writing directly to fd 1 (bypassing sys.stdout) cannot corrupt the result line."""
    result = _run(
        (
            "import os\n"
            "def f():\n"
            "    os.write(1, b'NOT JSON, DEFINITELY NOT A VALID RESPONSE\\n')\n"
            "    return 42\n"
        )
    )

    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value == 42


def test_continuous_raw_fd_write_is_bounded_by_timeout_not_left_running() -> None:
    """A candidate that floods fd 1 directly (bypassing Python's own bound) is still contained.

    Raw os.write(1, ...) is discarded to /dev/null (see runner._os_stdio_isolated),
    so it never reaches the size-bounded Python buffer at all and cannot be
    stopped by OUTPUT_LIMIT. The only backstop left is the wall-clock
    timeout — this proves that backstop actually catches it, terminates the
    container, and still produces a clean, uncorrupted structured result
    (TIMEOUT), never a hang or a garbled response.
    """
    result = _run(
        (
            "import os\n"
            "def f():\n"
            "    while True:\n"
            "        os.write(1, b'x' * 65536)\n"
        ),
        limits=ExecutionLimits(wall_time_sec=1.0),
    )

    assert result.status == ExecutionStatus.TIMEOUT
    assert result.wall_time_sec < 10.0


def test_candidate_closing_stdio_fds_still_yields_a_clean_result() -> None:
    """A candidate that closes fd 1/2 outright still produces a valid structured result."""
    result = _run(
        "import os\ndef f():\n    os.close(1)\n    os.close(2)\n    return 5\n"
    )

    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value == 5


def test_candidate_dup2_hijack_of_fd1_does_not_corrupt_the_result() -> None:
    """A candidate that permanently re-points fd 1 elsewhere cannot corrupt the result channel.

    Same scenario as test_execution_runner.py's offline version of this
    test, verified here end-to-end through the real container and
    controller (not just run_invocation in-process).
    """
    result = _run(DUP2_HIJACK_FD1_CANDIDATE_CODE)

    assert result.status == ExecutionStatus.COMPLETED
    assert result.return_value == 3


# --- Isolation regression -----------------------------------------------------


def test_writable_state_does_not_carry_across_invocations() -> None:
    """A secret written by one invocation is not visible to the next."""
    secret = f"secret-{uuid.uuid4()}"

    first = _run(
        "def f(secret):\n    with open('/tmp/leftover.txt', 'w') as fh:\n        fh.write(secret)\n"
        "    return 'written'\n",
        args=(secret,),
    )
    assert first.status == ExecutionStatus.COMPLETED

    second = _run(
        (
            "def f():\n"
            "    try:\n"
            "        with open('/tmp/leftover.txt') as fh:\n"
            "            return fh.read()\n"
            "    except OSError:\n"
            "        return None\n"
        )
    )

    assert second.status == ExecutionStatus.COMPLETED
    assert second.return_value is None
    assert second.return_value != secret


# --- Cleanup -------------------------------------------------------------------


def _list_megb_runner_containers() -> list[str]:
    proc = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=megb-runner-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return [name for name in proc.stdout.splitlines() if name]


def test_no_containers_remain_after_adversarial_exit_paths() -> None:
    """No megb-runner-* containers are left behind after any tested exit path.

    Covers: normal completion, exception, timeout, OOM, and a process-limit
    (fork) attack — the full set of termination paths that could plausibly
    leave a container or its descendant processes behind.
    """
    _run("def f():\n    return 1\n")
    _run("def f():\n    raise ValueError('x')\n")
    _run("def f():\n    while True:\n        pass\n", limits=ExecutionLimits(wall_time_sec=1.0))
    _run(
        (
            "def f():\n"
            "    data = []\n"
            "    while True:\n"
            "        data.append(bytearray(10 * 1024 * 1024))\n"
        ),
        limits=ExecutionLimits(wall_time_sec=10.0, memory_mb=64),
    )
    _run(
        (
            "import os\n"
            "def f():\n"
            "    forked = 0\n"
            "    for _ in range(10000):\n"
            "        pid = os.fork()\n"
            "        if pid == 0:\n"
            "            while True:\n"
            "                pass\n"
            "        forked += 1\n"
            "    return forked\n"
        ),
        limits=ExecutionLimits(wall_time_sec=5.0, max_processes=16),
    )

    leftover = _list_megb_runner_containers()
    assert leftover == []
