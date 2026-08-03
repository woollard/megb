"""MEGB-03H.2C.2A: offline integration tests proving
``DockerPerInvocationBackend.execute_with_telemetry()`` correctly
interleaves a real collector's lifecycle around the (faked) container's
own execution -- covering every named backend outcome plus cancellation,
using the same fake Docker-CLI harness as the rest of this suite. No real
Docker, no real container, no real cgroup filesystem.
"""

# This module's response-payload/scenario-matrix construction
# intentionally mirrors test_collector_lifecycle_coverage.py, reusing its
# own _BACKEND_SCENARIOS -- both exercise the same real backend-outcome
# shapes, this one additionally driving execute_with_telemetry() itself
# rather than a standalone run_collector() call. Expected and accepted.
# pylint: disable=duplicate-code

import dataclasses
import subprocess
from pathlib import Path

import pytest

from src.execution import real_telemetry_collectors as rtc
from src.execution.docker_backend import DockerPerInvocationBackend
from src.execution.telemetry import CollectorFailureStage, TelemetryQuality
from src.execution.telemetry_methods import CollectorMethod, FakeHostCapabilityProbe
from tests._docker_backend_fake_fixtures import install_fake_docker
from tests.test_collector_lifecycle_coverage import (
    _BACKEND_SCENARIOS,
    _NO_RESPONSE_SCENARIOS,
    _request,
)

_FAKE_CONTAINER_ID = "f" * 64


def _exact_factory(tmp_path: Path) -> tuple[rtc.TelemetryCollectorFactory, Path, Path]:
    """A factory whose memory/process collectors both resolve to real
    tmp_path files -- exercises the exact (cgroup-peak-file) collector
    path fully offline, with no subprocess.run beyond what the fake
    Docker harness already fakes."""
    memory_peak_file = tmp_path / "memory.peak"
    memory_peak_file.write_text("2048\n")
    pids_peak_file = tmp_path / "pids.peak"
    pids_peak_file.write_text("3\n")
    probe = FakeHostCapabilityProbe(
        memory_peak_paths={_FAKE_CONTAINER_ID: str(memory_peak_file)},
        pids_peak_paths={_FAKE_CONTAINER_ID: str(pids_peak_file)},
    )
    factory = rtc.TelemetryCollectorFactory(probe, rtc.CollectorSelectionConfig())
    return factory, memory_peak_file, pids_peak_file


@pytest.mark.parametrize("scenario_name", sorted(_BACKEND_SCENARIOS))
def test_execute_with_telemetry_covers_every_backend_outcome(
    scenario_name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """For every named backend outcome, execute_with_telemetry() still
    returns the identical status the telemetry-disabled path would, and
    the real (exact) collector still runs its full lifecycle around it,
    fully orthogonal to whatever the backend outcome was."""
    stdout_bytes, raise_timeout_first, inspect_info, expected_status = _BACKEND_SCENARIOS[
        scenario_name
    ]
    harness = install_fake_docker(
        monkeypatch,
        stdout_bytes=stdout_bytes,
        raise_timeout_first=raise_timeout_first,
        inspect_info=inspect_info,
        container_id=_FAKE_CONTAINER_ID,
    )
    factory, _memory_file, _pids_file = _exact_factory(tmp_path)
    backend = DockerPerInvocationBackend(
        telemetry_collector_factory=factory,
        telemetry_container_id_poll_interval_sec=0.001,
        telemetry_container_id_wait_max_sec=0.05,
    )

    result, telemetry = backend.execute_with_telemetry(_request())

    assert result.status == expected_status
    if scenario_name in _NO_RESPONSE_SCENARIOS:
        assert result.observed_response_bytes is None
    else:
        assert result.observed_response_bytes is not None

    # The collector lifecycle ran successfully regardless of the backend
    # outcome -- container-id resolution succeeded (container_id fixed),
    # so both peak files were read. Quality is EXACT everywhere terminal
    # state is independently confirmable (inspect_info.exit_code is
    # not None); "container_never_created" has no real container to
    # confirm exit against, so the read is correctly downgraded to
    # BOUNDARY_ONLY rather than trusting call-site ordering alone (the
    # MEGB-03H.2C.2A provenance/schema correction's own exactness fix).
    expected_quality = (
        TelemetryQuality.BOUNDARY_ONLY
        if scenario_name == "container_never_created"
        else TelemetryQuality.EXACT
    )
    assert telemetry.peak_memory.value == 2048
    assert telemetry.peak_memory.quality == expected_quality
    assert telemetry.peak_memory.method_identity is not None
    assert telemetry.peak_memory.method_identity.method == CollectorMethod.CGROUP_V2_MEMORY_PEAK
    assert telemetry.peak_process_count.value == 3
    assert telemetry.peak_process_count.quality == expected_quality

    # Cleanup/removal happened regardless of outcome.
    assert harness.remove_calls


def test_execute_and_execute_with_telemetry_agree_on_every_classification_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Telemetry-disabled and telemetry-enabled behavior must be
    byte-for-byte/status-for-status compatible: every outcome-
    classification field (everything except the per-call nondeterministic
    invocation_id/started_at/wall_time_sec) matches exactly between the
    two paths for the same fake backend configuration."""
    stdout_bytes, _raise_timeout_first, inspect_info, _expected_status = _BACKEND_SCENARIOS[
        "normal_completion"
    ]
    install_fake_docker(
        monkeypatch, stdout_bytes=stdout_bytes, inspect_info=inspect_info,
        container_id=_FAKE_CONTAINER_ID,
    )
    factory, _memory_file, _pids_file = _exact_factory(tmp_path)
    backend = DockerPerInvocationBackend(
        telemetry_collector_factory=factory,
        telemetry_container_id_poll_interval_sec=0.001,
        telemetry_container_id_wait_max_sec=0.05,
    )

    plain_result = backend.execute(_request())
    telemetry_result, _telemetry = backend.execute_with_telemetry(_request())

    volatile_fields = {"invocation_id", "started_at", "wall_time_sec"}
    for field in dataclasses.fields(plain_result):
        if field.name in volatile_fields:
            continue
        assert getattr(plain_result, field.name) == getattr(telemetry_result, field.name), (
            f"field {field.name!r} differs between execute() and execute_with_telemetry()"
        )


def test_execute_with_telemetry_requires_a_configured_factory() -> None:
    """Telemetry collection must be explicitly enabled -- calling
    execute_with_telemetry() without a factory raises rather than
    silently skipping collection."""
    backend = DockerPerInvocationBackend()
    with pytest.raises(ValueError):
        backend.execute_with_telemetry(_request())


def test_container_id_wait_failure_is_orthogonal_to_the_backend_outcome(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the container's id never becomes resolvable within the bound,
    telemetry collection reports a typed START failure for both metrics
    -- independent of, and never affecting, the backend's own outcome
    classification (which uses its own separate inspect/timeout logic)."""
    stdout_bytes, _raise_timeout_first, inspect_info, expected_status = _BACKEND_SCENARIOS[
        "normal_completion"
    ]
    install_fake_docker(
        monkeypatch,
        stdout_bytes=stdout_bytes,
        inspect_info=inspect_info,
        container_id=None,  # container id never resolves
    )
    factory, _memory_file, _pids_file = _exact_factory(tmp_path)
    backend = DockerPerInvocationBackend(
        telemetry_collector_factory=factory,
        telemetry_container_id_poll_interval_sec=0.001,
        telemetry_container_id_wait_max_sec=0.02,
    )

    result, telemetry = backend.execute_with_telemetry(_request())

    assert result.status == expected_status  # backend outcome unaffected
    assert telemetry.peak_memory.collector_failure == CollectorFailureStage.START
    assert telemetry.peak_process_count.collector_failure == CollectorFailureStage.START


def test_cancellation_during_communicate_still_cleans_up_and_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The final required scenario: a KeyboardInterrupt during the
    candidate's own execution (proc.communicate()) must still result in
    the container being removed and must still propagate unchanged --
    cancellation remains primary even with telemetry collection active."""
    stdout_bytes, _raise_timeout_first, inspect_info, _expected_status = _BACKEND_SCENARIOS[
        "normal_completion"
    ]
    harness = install_fake_docker(
        monkeypatch, stdout_bytes=stdout_bytes, inspect_info=inspect_info,
        container_id=_FAKE_CONTAINER_ID,
    )

    def _raise_keyboard_interrupt(*_args: object, **_kwargs: object) -> tuple[bytes, bytes]:
        raise KeyboardInterrupt("simulated cancellation")

    monkeypatch.setattr(
        "tests._docker_backend_fake_fixtures.FakePopen.communicate", _raise_keyboard_interrupt
    )

    factory, _memory_file, _pids_file = _exact_factory(tmp_path)
    backend = DockerPerInvocationBackend(
        telemetry_collector_factory=factory,
        telemetry_container_id_poll_interval_sec=0.001,
        telemetry_container_id_wait_max_sec=0.05,
    )

    with pytest.raises(KeyboardInterrupt):
        backend.execute_with_telemetry(_request())

    assert harness.remove_calls  # container cleanup still ran


def test_execute_with_telemetry_also_integrates_the_sampled_collector_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One representative scenario proving the SAMPLED (non-exact)
    collector family also integrates correctly through
    execute_with_telemetry() -- not exhaustively re-run across every
    backend outcome (already proven for the exact path above; the
    sampled collector's own lifecycle invariants are proven exhaustively
    at the unit level in test_real_telemetry_collectors.py)."""
    stdout_bytes, _raise_timeout_first, inspect_info, expected_status = _BACKEND_SCENARIOS[
        "normal_completion"
    ]
    harness = install_fake_docker(
        monkeypatch, stdout_bytes=stdout_bytes, inspect_info=inspect_info,
        container_id=_FAKE_CONTAINER_ID,
    )

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "stats"]:
            return subprocess.CompletedProcess(
                args=command, returncode=0, stdout="8MiB / 256MiB\n", stderr=""
            )
        if command[:2] == ["docker", "top"]:
            return subprocess.CompletedProcess(
                args=command, returncode=0, stdout="1\n2\n", stderr=""
            )
        if command[:2] == ["docker", "inspect"]:
            # The sampled collector's own container-existence check
            # reuses docker_backend._docker_inspect, which itself calls
            # subprocess.run -- report "found" immediately.
            return subprocess.CompletedProcess(
                args=command, returncode=0, stdout="false\t0", stderr=""
            )
        raise AssertionError(f"unexpected docker CLI command in sampled-path test: {command}")

    monkeypatch.setattr(subprocess, "run", fake_run)
    probe = FakeHostCapabilityProbe(memory_peak_paths={}, pids_peak_paths={})
    factory = rtc.TelemetryCollectorFactory(
        probe, rtc.CollectorSelectionConfig(memory_sampling_interval_sec=0.01)
    )
    backend = DockerPerInvocationBackend(
        telemetry_collector_factory=factory,
        telemetry_container_id_poll_interval_sec=0.001,
        telemetry_container_id_wait_max_sec=0.05,
    )

    result, telemetry = backend.execute_with_telemetry(_request())

    assert result.status == expected_status
    assert telemetry.peak_memory.method_identity is not None
    expected_method = CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY
    assert telemetry.peak_memory.method_identity.method == expected_method
    assert telemetry.peak_memory.quality in (TelemetryQuality.BOUNDARY_ONLY, None)
    assert harness.remove_calls
