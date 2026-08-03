"""MEGB-03H.2C.2A: tests for the real, controller-side telemetry
collectors (src.execution.real_telemetry_collectors). Fake/monkeypatched
subprocess and filesystem interfaces only -- no real Docker, no real
container, no real cgroup filesystem.
"""

# test_unavailable_collector_reports_unavailable_without_contamination's
# own CollectorMethodIdentity(...) construction intentionally mirrors
# TelemetryCollectorFactory's own "no method available" identity literal
# in real_telemetry_collectors.py -- the test builds the exact object the
# factory would, to exercise _UnavailableCollector directly. Expected and
# accepted, not a defect.
# pylint: disable=duplicate-code

import platform
import subprocess
import time
from pathlib import Path

import pytest

from src.execution import real_telemetry_collectors as rtc
from src.execution.telemetry import TelemetryQuality, TelemetryUnavailableReason
from src.execution.telemetry_methods import (
    CollectorMethod,
    FakeHostCapabilityProbe,
    MetricCollectionDisposition,
    TerminalCoverageState,
)


# ---------------------------------------------------------------------------
# CgroupPeakFileCollector
# ---------------------------------------------------------------------------


def _memory_identity(**overrides: object) -> rtc.CollectorMethodIdentity:
    defaults: dict[str, object] = {
        "method": CollectorMethod.CGROUP_V2_MEMORY_PEAK,
        "method_version": rtc.CGROUP_PEAK_FILE_COLLECTOR_VERSION,
        "interface": "cgroupfs:/fake/memory.peak",
        "sampling_interval_sec": None,
        "selection_disposition": MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
    }
    defaults.update(overrides)
    return rtc.CollectorMethodIdentity(**defaults)  # type: ignore[arg-type]


def test_cgroup_peak_file_collector_reads_the_exact_value(tmp_path: Path) -> None:
    """finalize() reads the file exactly once and reports EXACT when
    terminal state is confirmed."""
    peak_file = tmp_path / "memory.peak"
    peak_file.write_text("104857600\n")
    identity = _memory_identity()
    collector = rtc.CgroupPeakFileCollector(
        str(peak_file), identity, confirm_terminal_state=lambda: True
    )
    collector.start()
    collector.sample()
    observation = collector.finalize()
    collector.cleanup()
    assert observation.value == 104857600
    assert observation.quality == TelemetryQuality.EXACT
    assert observation.unavailable_reason is None
    assert observation.method_identity is identity
    assert observation.terminal_coverage == TerminalCoverageState.TERMINAL_READ_CONFIRMED


def test_cgroup_peak_file_collector_downgrades_to_boundary_only_when_terminal_state_unconfirmed(
    tmp_path: Path,
) -> None:
    """MEGB-03H.2C.2A provenance/schema correction: a read that cannot be
    independently confirmed to have happened after the candidate's
    container fully terminated must never silently retain EXACT -- it is
    downgraded to BOUNDARY_ONLY, with terminal_coverage recording the
    miss."""
    peak_file = tmp_path / "memory.peak"
    peak_file.write_text("104857600\n")
    identity = _memory_identity()
    collector = rtc.CgroupPeakFileCollector(
        str(peak_file), identity, confirm_terminal_state=lambda: False
    )
    collector.start()
    observation = collector.finalize()
    collector.cleanup()
    assert observation.value == 104857600
    assert observation.quality == TelemetryQuality.BOUNDARY_ONLY
    assert observation.terminal_coverage == TerminalCoverageState.TERMINAL_READ_MISSED


def test_cgroup_peak_file_collector_raises_on_missing_file(tmp_path: Path) -> None:
    """A path that doesn't exist raises -- callers (run_collector /
    docker_backend's split-phase helpers) translate this into a typed
    SAMPLER_FAILURE, never a raw exception surfaced to telemetry."""
    identity = _memory_identity()
    collector = rtc.CgroupPeakFileCollector(
        str(tmp_path / "does_not_exist"), identity, confirm_terminal_state=lambda: True
    )
    collector.start()
    with pytest.raises(OSError):
        collector.finalize()


# ---------------------------------------------------------------------------
# SampledPollingCollector
# ---------------------------------------------------------------------------


def _polling_identity(**overrides: object) -> rtc.CollectorMethodIdentity:
    defaults: dict[str, object] = {
        "method": CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY,
        "method_version": rtc.SAMPLED_POLLING_COLLECTOR_VERSION,
        "interface": "docker stats --no-stream --format {{.MemUsage}}",
        "sampling_interval_sec": 0.02,
        "selection_disposition": MetricCollectionDisposition.FALLBACK_METHOD_SELECTED,
    }
    defaults.update(overrides)
    return rtc.CollectorMethodIdentity(**defaults)  # type: ignore[arg-type]


def test_sampled_polling_collector_tracks_the_observed_maximum() -> None:
    """The running maximum across samples is what finalize() reports --
    not the last sample, not the first."""
    values = iter([10, 50, 30, 20])
    collector = rtc.SampledPollingCollector(
        container_exists=lambda: True,
        sample_fn=lambda: next(values, None),
        sampling_interval_sec=0.01,
        existence_poll_interval_sec=0.01,
        existence_wait_max_sec=1.0,
        method_identity=_polling_identity(),
    )
    collector.start()
    time.sleep(0.08)
    observation = collector.finalize()
    collector.cleanup()
    assert observation.value == 50
    assert observation.quality == TelemetryQuality.BOUNDARY_ONLY
    assert observation.unavailable_reason is None


def test_sampled_polling_collector_waits_for_container_existence_before_sampling() -> None:
    """No sample is ever taken before container_exists() first reports
    True -- capability probing (read-only) and sampling start are
    correctly ordered."""
    exists_calls: list[float] = []
    sample_calls: list[float] = []
    became_true_at = time.monotonic() + 0.05

    def container_exists() -> bool:
        exists_calls.append(time.monotonic())
        return time.monotonic() >= became_true_at

    def sample_fn() -> int:
        sample_calls.append(time.monotonic())
        return 1

    collector = rtc.SampledPollingCollector(
        container_exists=container_exists,
        sample_fn=sample_fn,
        sampling_interval_sec=0.01,
        existence_poll_interval_sec=0.01,
        existence_wait_max_sec=1.0,
        method_identity=_polling_identity(),
    )
    collector.start()
    time.sleep(0.15)
    collector.finalize()
    collector.cleanup()
    assert exists_calls, "container existence must actually be checked"
    assert sample_calls, "at least one sample must be taken once the container exists"
    assert min(sample_calls) >= became_true_at


def test_sampled_polling_collector_raises_when_container_never_appears() -> None:
    """A bounded existence wait that never succeeds is a genuine
    operational failure -- finalize() raises rather than silently
    reporting an empty/zero observation."""
    collector = rtc.SampledPollingCollector(
        container_exists=lambda: False,
        sample_fn=lambda: 1,
        sampling_interval_sec=0.01,
        existence_poll_interval_sec=0.01,
        existence_wait_max_sec=0.05,
        method_identity=_polling_identity(),
    )
    collector.start()
    time.sleep(0.1)
    with pytest.raises(RuntimeError):
        collector.finalize()
    collector.cleanup()


def test_sampled_polling_collector_tolerates_individual_sample_failures() -> None:
    """A sample_fn that raises on some calls must not crash the
    background thread or the collector -- failed samples are simply
    skipped, and a later successful sample still contributes."""
    calls = {"n": 0}

    def flaky_sample_fn() -> int:
        calls["n"] += 1
        if calls["n"] % 2 == 0:
            raise RuntimeError("simulated transient sampling failure")
        return 42

    collector = rtc.SampledPollingCollector(
        container_exists=lambda: True,
        sample_fn=flaky_sample_fn,
        sampling_interval_sec=0.01,
        existence_poll_interval_sec=0.01,
        existence_wait_max_sec=1.0,
        method_identity=_polling_identity(),
    )
    collector.start()
    time.sleep(0.08)
    observation = collector.finalize()
    collector.cleanup()
    assert observation.value == 42
    assert calls["n"] > 1


def test_sampled_polling_collector_reports_host_telemetry_unavailable_if_every_sample_fails() -> (
    None
):
    """If the sampler is confirmed available (container existed) but
    every single sample attempt raised, that is a genuine sampler
    failure -- reported via a valid, typed unavailable observation, not
    an invalid None/None/None TelemetryObservation."""
    collector = rtc.SampledPollingCollector(
        container_exists=lambda: True,
        sample_fn=lambda: (_ for _ in ()).throw(RuntimeError("always fails")),
        sampling_interval_sec=0.01,
        existence_poll_interval_sec=0.01,
        existence_wait_max_sec=1.0,
        method_identity=_polling_identity(),
    )
    collector.start()
    time.sleep(0.05)
    observation = collector.finalize()
    collector.cleanup()
    assert observation.value is None
    assert observation.unavailable_reason == TelemetryUnavailableReason.HOST_TELEMETRY_UNAVAILABLE


def test_sampled_polling_collector_thread_terminates_after_finalize() -> None:
    """No sampling thread survives past finalize()+cleanup() -- proven
    directly, not just inferred from a successful return."""
    collector = rtc.SampledPollingCollector(
        container_exists=lambda: True,
        sample_fn=lambda: 1,
        sampling_interval_sec=0.01,
        existence_poll_interval_sec=0.01,
        existence_wait_max_sec=1.0,
        method_identity=_polling_identity(),
    )
    collector.start()
    time.sleep(0.03)
    collector.finalize()
    collector.cleanup()
    assert collector._thread is not None  # pylint: disable=protected-access
    assert not collector._thread.is_alive()  # pylint: disable=protected-access


def test_sampled_polling_collector_cleanup_is_safe_before_finalize_ever_ran() -> None:
    """cleanup() alone (finalize() never called, e.g. an earlier failure
    elsewhere in the caller's own lifecycle) must still stop the thread
    without raising."""
    collector = rtc.SampledPollingCollector(
        container_exists=lambda: False,
        sample_fn=lambda: 1,
        sampling_interval_sec=0.01,
        existence_poll_interval_sec=0.01,
        existence_wait_max_sec=5.0,
        method_identity=_polling_identity(),
    )
    collector.start()
    time.sleep(0.02)
    collector.cleanup()  # does not raise, even mid-existence-wait
    assert collector._thread is not None  # pylint: disable=protected-access
    assert not collector._thread.is_alive()  # pylint: disable=protected-access


def test_sampled_polling_collector_no_busy_loop() -> None:
    """The existence/sampling loops block on Event.wait(timeout) rather
    than spinning -- proven by an upper bound on how many times
    container_exists()/sample_fn() are called over a fixed wall-clock
    window, given a known sampling interval."""
    exists_calls = {"n": 0}
    sample_calls = {"n": 0}

    def container_exists() -> bool:
        exists_calls["n"] += 1
        return True

    def sample_fn() -> int:
        sample_calls["n"] += 1
        return 1

    collector = rtc.SampledPollingCollector(
        container_exists=container_exists,
        sample_fn=sample_fn,
        sampling_interval_sec=0.05,
        existence_poll_interval_sec=0.05,
        existence_wait_max_sec=1.0,
        method_identity=_polling_identity(),
    )
    collector.start()
    time.sleep(0.22)
    collector.finalize()
    collector.cleanup()
    # ~0.22s / 0.05s interval => at most ~5-6 samples; a busy loop would
    # produce many thousands in the same window.
    assert sample_calls["n"] < 20
    assert exists_calls["n"] < 5


# ---------------------------------------------------------------------------
# _UnavailableCollector (accessed via the factory, but exercised directly too)
# ---------------------------------------------------------------------------


def test_unavailable_collector_reports_unavailable_without_contamination() -> None:
    """The explicit no-method-available outcome is a real, typed
    observation, never a raised exception or a SAMPLER_FAILURE."""
    identity = rtc.CollectorMethodIdentity(
        method=CollectorMethod.UNAVAILABLE_WITHOUT_CONTAMINATION,
        method_version="unavailable/v1",
        interface="none",
        sampling_interval_sec=None,
        selection_disposition=MetricCollectionDisposition.NO_METHOD_AVAILABLE,
    )
    collector = rtc._UnavailableCollector(identity)  # pylint: disable=protected-access
    collector.start()
    collector.sample()
    observation = collector.finalize()
    collector.cleanup()
    assert observation.value is None
    assert (
        observation.unavailable_reason
        == TelemetryUnavailableReason.UNAVAILABLE_WITHOUT_CONTAMINATION
    )
    assert observation.collector_failure is None


# ---------------------------------------------------------------------------
# Docker-stats memory-usage parsing (pure, offline)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field_text", "expected_bytes"),
    [
        ("12.34MiB / 512MiB", int(12.34 * 1024**2)),
        ("1GiB / 2GiB", 1024**3),
        ("500B / 1024B", 500),
        ("2.5KiB / 10KiB", int(2.5 * 1024)),
        ("0B / 256MiB", 0),
    ],
)
def test_parse_docker_mem_usage_bytes_converts_every_unit(
    field_text: str, expected_bytes: int
) -> None:
    """Every binary unit docker stats reports (B/KiB/MiB/GiB) converts
    to the correct raw byte count, using only the 'used' half of the
    '<used> / <limit>' field."""
    assert rtc._parse_docker_mem_usage_bytes(field_text) == expected_bytes  # pylint: disable=protected-access


def test_parse_docker_mem_usage_bytes_rejects_malformed_input() -> None:
    """An unrecognized format or unit raises rather than silently
    returning zero or a guessed value."""
    with pytest.raises(ValueError):
        rtc._parse_docker_mem_usage_bytes("garbage")  # pylint: disable=protected-access
    with pytest.raises(ValueError):
        rtc._parse_docker_mem_usage_bytes("12.3XiB / 512MiB")  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# Docker-CLI subprocess helpers (monkeypatched subprocess.run)
# ---------------------------------------------------------------------------


def _fake_completed_process(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_docker_stats_mem_usage_bytes_calls_the_expected_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uses --no-stream (a single snapshot, not a live stream) and the
    exact container name -- never docker exec."""
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return _fake_completed_process("10MiB / 256MiB\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = rtc._docker_stats_mem_usage_bytes("megb-runner-abc")  # pylint: disable=protected-access
    assert result == 10 * 1024**2
    assert calls == [
        ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", "megb-runner-abc"]
    ]


def test_docker_top_process_count_counts_nonempty_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    """One PID per line, quiet mode (-q) -- never docker exec."""

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command == ["docker", "top", "megb-runner-abc", "-q"]
        return _fake_completed_process("101\n102\n103\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert rtc._docker_top_process_count("megb-runner-abc") == 3  # pylint: disable=protected-access


def test_container_exists_delegates_to_docker_inspect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reuses the existing, already-tested _docker_inspect rather than
    duplicating container-existence logic."""

    class _FakeInspectInfo:
        found = True

    monkeypatch.setattr(rtc.docker_backend, "_docker_inspect", lambda name: _FakeInspectInfo())
    assert rtc._container_exists("megb-runner-abc") is True  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# cgroup v2 path resolution (pure)
# ---------------------------------------------------------------------------


def test_candidate_cgroup_v2_paths_for_systemd_driver() -> None:
    """The systemd cgroup driver's own scope-unit naming convention."""
    paths = rtc._candidate_cgroup_v2_paths(  # pylint: disable=protected-access
        "abc123", "memory.peak", "systemd"
    )
    assert paths == ("/sys/fs/cgroup/system.slice/docker-abc123.scope/memory.peak",)


def test_candidate_cgroup_v2_paths_for_cgroupfs_driver() -> None:
    """The cgroupfs driver's own flat per-container directory convention."""
    paths = rtc._candidate_cgroup_v2_paths(  # pylint: disable=protected-access
        "abc123", "pids.peak", "cgroupfs"
    )
    assert paths == ("/sys/fs/cgroup/docker/abc123/pids.peak",)


def test_candidate_cgroup_v2_paths_tries_both_when_driver_unknown() -> None:
    """An unresolvable driver tries every known driver's own path,
    systemd first (the more common default)."""
    paths = rtc._candidate_cgroup_v2_paths(  # pylint: disable=protected-access
        "abc123", "memory.peak", None
    )
    assert paths == (
        "/sys/fs/cgroup/system.slice/docker-abc123.scope/memory.peak",
        "/sys/fs/cgroup/docker/abc123/memory.peak",
    )


def test_first_existing_readable_path_returns_the_first_match(tmp_path: Path) -> None:
    """Read-only: only os.path.isfile/os.access are consulted, no file
    is ever created, modified, or written."""
    missing = tmp_path / "missing" / "memory.peak"
    present = tmp_path / "memory.peak"
    present.write_text("123\n")
    result = rtc._first_existing_readable_path(  # pylint: disable=protected-access
        (str(missing), str(present))
    )
    assert result == str(present)


def test_first_existing_readable_path_returns_none_when_nothing_matches(tmp_path: Path) -> None:
    """No candidate path exists -- returns None, never raises."""
    missing = tmp_path / "missing" / "memory.peak"
    result = rtc._first_existing_readable_path((str(missing),))  # pylint: disable=protected-access
    assert result is None


# ---------------------------------------------------------------------------
# RealHostCapabilityProbe
# ---------------------------------------------------------------------------


def test_real_capability_probe_host_runtime_metadata_includes_cgroup_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kernel release, Docker server version, and cgroup driver are all
    reported together, using only read-only Docker CLI/platform calls."""
    monkeypatch.setattr(rtc.docker_backend, "_docker_server_version", lambda: "27.0.0")
    monkeypatch.setattr(platform, "release", lambda: "6.8.0-fake")

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command == ["docker", "info", "--format", "{{.CgroupDriver}}"]
        return _fake_completed_process("systemd\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    probe = rtc.RealHostCapabilityProbe()
    metadata = dict(probe.host_runtime_metadata())
    assert metadata["kernel_release"] == "6.8.0-fake"
    assert metadata["docker_server_version"] == "27.0.0"
    assert metadata["cgroup_driver"] == "systemd"


def test_real_capability_probe_omits_cgroup_driver_when_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed docker info call omits cgroup_driver entirely rather
    than inventing a placeholder value."""
    monkeypatch.setattr(rtc.docker_backend, "_docker_server_version", lambda: "27.0.0")
    monkeypatch.setattr(platform, "release", lambda: "6.8.0-fake")

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.SubprocessError("docker info unavailable")

    monkeypatch.setattr(subprocess, "run", fake_run)
    probe = rtc.RealHostCapabilityProbe()
    metadata = dict(probe.host_runtime_metadata())
    assert "cgroup_driver" not in metadata


def test_real_capability_probe_resolves_memory_peak_path_when_readable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A readable candidate path is returned as the resolved peak path."""
    peak_file = tmp_path / "memory.peak"
    peak_file.write_text("1\n")
    monkeypatch.setattr(rtc, "_cgroup_driver", lambda: "cgroupfs")
    monkeypatch.setattr(
        rtc,
        "_candidate_cgroup_v2_paths",
        lambda container_id, filename, driver: (str(peak_file),),
    )
    probe = rtc.RealHostCapabilityProbe()
    assert probe.cgroup_v2_memory_peak_path("abc123") == str(peak_file)


def test_real_capability_probe_returns_none_when_no_path_readable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Neither memory.peak nor pids.peak is readable -- both resolve to
    None, never a fabricated path."""
    monkeypatch.setattr(rtc, "_cgroup_driver", lambda: "cgroupfs")
    monkeypatch.setattr(
        rtc,
        "_candidate_cgroup_v2_paths",
        lambda container_id, filename, driver: (str(tmp_path / "nope"),),
    )
    probe = rtc.RealHostCapabilityProbe()
    assert probe.cgroup_v2_memory_peak_path("abc123") is None
    assert probe.cgroup_v2_pids_peak_path("abc123") is None


def test_real_capability_probe_sampling_availability_reflects_docker_cli_reachability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sampling availability tracks whether the Docker CLI itself is
    reachable -- true when it responds, false when it errors."""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed_process(""))
    probe = rtc.RealHostCapabilityProbe()
    assert probe.docker_stats_sampling_available() is True
    assert probe.docker_top_sampling_available() is True

    def fake_run_failing(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("docker CLI not found")

    monkeypatch.setattr(subprocess, "run", fake_run_failing)
    assert probe.docker_stats_sampling_available() is False
    assert probe.docker_top_sampling_available() is False


# ---------------------------------------------------------------------------
# CollectorSelectionConfig
# ---------------------------------------------------------------------------


def test_collector_selection_config_is_disabled_by_default() -> None:
    """Real collection must never be silently turned on."""
    config = rtc.CollectorSelectionConfig()
    assert config.enabled is False


# ---------------------------------------------------------------------------
# TelemetryCollectorFactory: frozen selection precedence
# ---------------------------------------------------------------------------


def test_factory_selects_cgroup_memory_peak_when_path_resolvable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact method is chosen first, whenever it's available, and is
    reported EXACT once terminal state is independently confirmed."""
    peak_file = tmp_path / "memory.peak"
    peak_file.write_text("2048\n")
    probe = FakeHostCapabilityProbe(memory_peak_paths={"abc123": str(peak_file)})
    factory = rtc.TelemetryCollectorFactory(probe, rtc.CollectorSelectionConfig())
    collector, identity = factory.build_memory_collector(
        container_id="abc123", container_name="c"
    )
    assert identity.method == CollectorMethod.CGROUP_V2_MEMORY_PEAK
    assert isinstance(collector, rtc.CgroupPeakFileCollector)

    class _FakeInspectInfo:
        exit_code = 0

    monkeypatch.setattr(rtc.docker_backend, "_docker_inspect", lambda name: _FakeInspectInfo())
    observation = collector.finalize()
    assert observation.value == 2048
    assert observation.quality == TelemetryQuality.EXACT


def test_factory_falls_back_to_sampled_memory_when_no_cgroup_path() -> None:
    """No exact path resolvable, but sampling is available -- the
    sampled fallback is chosen, carrying the configured interval."""
    probe = FakeHostCapabilityProbe(memory_peak_paths={}, stats_sampling_available=True)
    factory = rtc.TelemetryCollectorFactory(probe, rtc.CollectorSelectionConfig())
    collector, identity = factory.build_memory_collector(
        container_id="abc123", container_name="c"
    )
    assert identity.method == CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY
    expected_interval = rtc.CollectorSelectionConfig().memory_sampling_interval_sec
    assert identity.sampling_interval_sec == expected_interval
    assert isinstance(collector, rtc.SampledPollingCollector)


def test_factory_falls_back_to_unavailable_when_neither_memory_method_works() -> None:
    """Neither exact nor sampled collection is available -- the
    explicit, typed UNAVAILABLE_WITHOUT_CONTAMINATION outcome is used."""
    probe = FakeHostCapabilityProbe(memory_peak_paths={}, stats_sampling_available=False)
    factory = rtc.TelemetryCollectorFactory(probe, rtc.CollectorSelectionConfig())
    collector, identity = factory.build_memory_collector(
        container_id="abc123", container_name="c"
    )
    assert identity.method == CollectorMethod.UNAVAILABLE_WITHOUT_CONTAMINATION
    observation = collector.finalize()
    assert (
        observation.unavailable_reason
        == TelemetryUnavailableReason.UNAVAILABLE_WITHOUT_CONTAMINATION
    )


def test_factory_selects_cgroup_pids_peak_when_path_resolvable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact process-count method is chosen first, when available,
    and is reported EXACT once terminal state is independently
    confirmed."""
    peak_file = tmp_path / "pids.peak"
    peak_file.write_text("7\n")
    probe = FakeHostCapabilityProbe(pids_peak_paths={"abc123": str(peak_file)})
    factory = rtc.TelemetryCollectorFactory(probe, rtc.CollectorSelectionConfig())
    collector, identity = factory.build_process_count_collector(
        container_id="abc123", container_name="c"
    )
    assert identity.method == CollectorMethod.CGROUP_V2_PIDS_PEAK

    class _FakeInspectInfo:
        exit_code = 0

    monkeypatch.setattr(rtc.docker_backend, "_docker_inspect", lambda name: _FakeInspectInfo())
    observation = collector.finalize()
    assert observation.value == 7
    assert observation.quality == TelemetryQuality.EXACT


def test_factory_falls_back_to_sampled_process_count_when_no_cgroup_path() -> None:
    """No exact path resolvable, but sampling is available -- the
    sampled fallback is chosen."""
    probe = FakeHostCapabilityProbe(pids_peak_paths={}, top_sampling_available=True)
    factory = rtc.TelemetryCollectorFactory(probe, rtc.CollectorSelectionConfig())
    collector, identity = factory.build_process_count_collector(
        container_id="abc123", container_name="c"
    )
    assert identity.method == CollectorMethod.SAMPLED_DOCKER_TOP_PROCESS_COUNT
    assert isinstance(collector, rtc.SampledPollingCollector)


def test_factory_falls_back_to_unavailable_when_neither_process_count_method_works() -> None:
    """Neither exact nor sampled process-count collection is
    available -- the explicit, typed unavailable outcome is used."""
    probe = FakeHostCapabilityProbe(pids_peak_paths={}, top_sampling_available=False)
    factory = rtc.TelemetryCollectorFactory(probe, rtc.CollectorSelectionConfig())
    _collector, identity = factory.build_process_count_collector(
        container_id="abc123", container_name="c"
    )
    assert identity.method == CollectorMethod.UNAVAILABLE_WITHOUT_CONTAMINATION


def test_factory_propagates_host_runtime_metadata_into_every_identity() -> None:
    """Whichever method is selected, the probe's own host metadata is
    always carried onto the resulting identity."""
    probe = FakeHostCapabilityProbe(
        host_metadata=(("kernel_release", "6.8.0-fake"),), memory_peak_paths={}
    )
    factory = rtc.TelemetryCollectorFactory(probe, rtc.CollectorSelectionConfig())
    _collector, identity = factory.build_memory_collector(container_id="abc123", container_name="c")
    assert identity.host_runtime_metadata == (("kernel_release", "6.8.0-fake"),)


def test_factory_capability_probing_is_read_only(tmp_path: Path) -> None:
    """Building collectors for both metrics must never write to the
    filesystem or mutate the probe's own configured state."""
    peak_file = tmp_path / "memory.peak"
    peak_file.write_text("100\n")
    before = peak_file.read_text()
    probe = FakeHostCapabilityProbe(memory_peak_paths={"abc123": str(peak_file)})
    factory = rtc.TelemetryCollectorFactory(probe, rtc.CollectorSelectionConfig())
    factory.build_memory_collector(container_id="abc123", container_name="c")
    factory.build_process_count_collector(container_id="abc123", container_name="c")
    assert peak_file.read_text() == before
