"""MEGB-03H.2C.1 conformance audit: a fake subprocess/Docker-CLI harness
letting DockerPerInvocationBackend.execute() run fully offline --
monkeypatches subprocess.Popen and the small Docker-CLI helper functions
docker_backend.py itself calls (server version, image digest, inspect,
kill, remove). No real Docker, no real container.
"""

import subprocess
from dataclasses import dataclass, field
from typing import Any

import pytest

from src.execution import docker_backend
from src.execution.docker_backend import _ContainerInspectInfo


@dataclass
class FakePopen:
    """Records every communicate() call's `input` kwarg and returns
    preconfigured (stdout, stderr) bytes -- or raises TimeoutExpired on
    the first call only, if configured, simulating a controller timeout
    (the real backend re-calls communicate() with no arguments afterward
    to drain the pipe, exactly as it does against a real container)."""

    stdout_bytes: bytes
    stderr_bytes: bytes = b""
    raise_timeout_first: bool = False
    command: list[str] = field(default_factory=list)
    communicate_calls: list[dict[str, Any]] = field(default_factory=list)
    _timeout_already_raised: bool = False

    def communicate(  # pylint: disable=redefined-builtin
        self, input: bytes | None = None, timeout: float | None = None
    ) -> tuple[bytes, bytes]:
        """Match subprocess.Popen.communicate()'s own signature exactly
        (including its ``input`` parameter name, shadowing the builtin, so
        callers using ``communicate(input=...)`` as a keyword argument
        work unchanged)."""
        self.communicate_calls.append({"input": input, "timeout": timeout})
        if self.raise_timeout_first and not self._timeout_already_raised:
            self._timeout_already_raised = True
            raise subprocess.TimeoutExpired(cmd=self.command, timeout=timeout or 0.0)
        return self.stdout_bytes, self.stderr_bytes


@dataclass
class FakeDockerHarness:
    """Everything a test needs to assert on after calling execute()
    against the fake Docker CLI."""

    popens: list[FakePopen]
    remove_calls: list[str]
    inspect_calls: list[str]
    kill_calls: list[str]


def install_fake_docker(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdout_bytes: bytes,
    stderr_bytes: bytes = b"",
    raise_timeout_first: bool = False,
    inspect_info: _ContainerInspectInfo | None = None,
) -> FakeDockerHarness:
    """Monkeypatch docker_backend's subprocess/Docker-CLI calls with fakes
    for the duration of one test. Returns a harness recording every
    Popen/communicate/inspect/kill/remove call made during that test."""
    popens: list[FakePopen] = []
    remove_calls: list[str] = []
    inspect_calls: list[str] = []
    kill_calls: list[str] = []
    resolved_inspect_info = (
        inspect_info
        if inspect_info is not None
        else _ContainerInspectInfo(found=True, oom_killed=False, exit_code=0)
    )

    def fake_popen_factory(
        command: list[str], *, stdin: Any = None, stdout: Any = None, stderr: Any = None
    ) -> FakePopen:
        del stdin, stdout, stderr
        popen = FakePopen(
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            raise_timeout_first=raise_timeout_first,
            command=command,
        )
        popens.append(popen)
        return popen

    def fake_inspect(container_name: str) -> _ContainerInspectInfo:
        inspect_calls.append(container_name)
        return resolved_inspect_info

    def fake_kill(container_name: str) -> None:
        kill_calls.append(container_name)

    def fake_remove(container_name: str) -> None:
        remove_calls.append(container_name)

    monkeypatch.setattr(subprocess, "Popen", fake_popen_factory)
    monkeypatch.setattr(docker_backend, "_docker_server_version", lambda: "fake-server-version")
    monkeypatch.setattr(
        docker_backend, "_resolve_image_digest", lambda image: "sha256:" + "a" * 64
    )
    monkeypatch.setattr(docker_backend, "_docker_inspect", fake_inspect)
    monkeypatch.setattr(docker_backend, "_docker_kill", fake_kill)
    monkeypatch.setattr(docker_backend, "_docker_remove", fake_remove)
    return FakeDockerHarness(
        popens=popens, remove_calls=remove_calls, inspect_calls=inspect_calls, kill_calls=kill_calls
    )
