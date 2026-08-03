"""MEGB-03H.2C.2A terminal-state-proof audit: proves that
``CgroupPeakFileCollector``'s ``TERMINAL_READ_CONFIRMED`` state is
logically sufficient and correctly ordered.

Covers, using fakes only (no real Docker, no real cgroup filesystem):

* the corrected ``_confirm_container_terminal_state`` predicate itself,
  directly -- proving a bare ``ExitCode`` value (which Docker reports as
  its zero value, 0, for a still-RUNNING container) is never treated as
  proof of termination, and that a mismatched container identity is
  never accepted;
* the full event-order/decision table for ``CgroupPeakFileCollector``:
  confirmed+read-succeeds -> EXACT; confirmed+read-fails+earlier sample
  -> BOUNDARY_ONLY; confirmed+read-fails+no sample -> typed unavailable;
  unconfirmed (for any reason) -> never EXACT;
* that the same rules apply independently to the memory.peak and
  pids.peak methods, since both are served by the same collector class
  through ``TelemetryCollectorFactory``.
"""

from pathlib import Path

import pytest

from src.execution import real_telemetry_collectors as rtc
from src.execution.docker_backend import _ContainerInspectInfo
from src.execution.telemetry import TelemetryQuality, TelemetryUnavailableReason
from src.execution.telemetry_methods import CollectorMethod, FakeHostCapabilityProbe

_REAL_CONTAINER_ID = "a" * 64
_OTHER_CONTAINER_ID = "b" * 64
_TERMINAL_TIMESTAMP = "2026-01-01T00:00:01Z"
_ZERO_TIMESTAMP = "0001-01-01T00:00:00Z"


def _inspect(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    found: bool = True,
    container_full_id: str = _REAL_CONTAINER_ID,
    running: bool = False,
    status: str = "exited",
    finished_at: str = _TERMINAL_TIMESTAMP,
    exit_code: int | None = 0,
    oom_killed: bool = False,
) -> _ContainerInspectInfo:
    """A fully-populated, by-default genuinely-terminal inspect result --
    every field overridable so each test can break exactly one
    predicate."""
    return _ContainerInspectInfo(
        found=found,
        oom_killed=oom_killed,
        exit_code=exit_code,
        container_full_id=container_full_id,
        running=running,
        status=status,
        finished_at=finished_at,
    )


# ---------------------------------------------------------------------------
# 1. _confirm_container_terminal_state: the predicate itself
# ---------------------------------------------------------------------------


def test_confirm_terminal_state_accepts_a_genuinely_terminal_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every predicate holds -- confirmed."""
    monkeypatch.setattr(rtc.docker_backend, "_docker_inspect", lambda name: _inspect())
    assert (
        rtc._confirm_container_terminal_state(  # pylint: disable=protected-access
            "c", expected_container_id=_REAL_CONTAINER_ID
        )
        is True
    )


def test_confirm_terminal_state_rejects_running_true_even_with_exit_code_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact defect this audit corrects: Docker reports ExitCode's
    zero value (0) for a container that is still running, so
    ``exit_code is not None`` alone is never proof of termination --
    ``State.Running`` must be explicitly false."""
    monkeypatch.setattr(
        rtc.docker_backend,
        "_docker_inspect",
        lambda name: _inspect(running=True, status="running", finished_at=_ZERO_TIMESTAMP),
    )
    assert (
        rtc._confirm_container_terminal_state(  # pylint: disable=protected-access
            "c", expected_container_id=_REAL_CONTAINER_ID
        )
        is False
    )


def test_confirm_terminal_state_rejects_container_never_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A container that was never created (or is no longer inspectable
    at all) can never be confirmed terminal -- there is nothing to prove
    termination of."""
    monkeypatch.setattr(rtc.docker_backend, "_docker_inspect", lambda name: _inspect(found=False))
    assert (
        rtc._confirm_container_terminal_state(  # pylint: disable=protected-access
            "c", expected_container_id=_REAL_CONTAINER_ID
        )
        is False
    )


def test_confirm_terminal_state_rejects_mismatched_container_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the currently-inspected container's own id no longer matches
    the id this collector's cgroup path was derived from -- the name was
    reused, or now resolves to a different container -- confirmation
    must fail even though every other field looks terminal. A stale
    cgroup from a different invocation must never be accepted."""
    monkeypatch.setattr(
        rtc.docker_backend,
        "_docker_inspect",
        lambda name: _inspect(container_full_id=_OTHER_CONTAINER_ID),
    )
    assert (
        rtc._confirm_container_terminal_state(  # pylint: disable=protected-access
            "c", expected_container_id=_REAL_CONTAINER_ID
        )
        is False
    )


@pytest.mark.parametrize("status", ["created", "running", "restarting", "paused", "removing"])
def test_confirm_terminal_state_rejects_every_non_terminal_status(
    status: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only ``exited``/``dead`` count as terminal -- every other status
    Docker defines is rejected, even if ``Running`` happened to read
    false (e.g. ``paused``)."""
    monkeypatch.setattr(
        rtc.docker_backend,
        "_docker_inspect",
        lambda name: _inspect(status=status, finished_at=_ZERO_TIMESTAMP),
    )
    assert (
        rtc._confirm_container_terminal_state(  # pylint: disable=protected-access
            "c", expected_container_id=_REAL_CONTAINER_ID
        )
        is False
    )


def test_confirm_terminal_state_rejects_zero_finished_at_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docker's own zero-value RFC3339 timestamp for FinishedAt means the
    container has never actually finished, regardless of what Running/
    Status otherwise report -- a defensive, independent check."""
    monkeypatch.setattr(
        rtc.docker_backend, "_docker_inspect", lambda name: _inspect(finished_at=_ZERO_TIMESTAMP)
    )
    assert (
        rtc._confirm_container_terminal_state(  # pylint: disable=protected-access
            "c", expected_container_id=_REAL_CONTAINER_ID
        )
        is False
    )


def test_confirm_terminal_state_accepts_oom_killed_nonzero_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exactness is determined by terminal-state coverage, never by
    exit-code success/failure or OOM-kill status -- a killed container
    confirms terminal exactly like a clean exit, once Running/Status/
    FinishedAt/identity all agree."""
    monkeypatch.setattr(
        rtc.docker_backend,
        "_docker_inspect",
        lambda name: _inspect(exit_code=137, oom_killed=True),
    )
    assert (
        rtc._confirm_container_terminal_state(  # pylint: disable=protected-access
            "c", expected_container_id=_REAL_CONTAINER_ID
        )
        is True
    )


def test_confirm_terminal_state_treats_inspect_exception_as_unconfirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient inspect failure is the safe default: unconfirmed,
    never confirmed."""

    def _raise(_name: str) -> _ContainerInspectInfo:
        raise RuntimeError("simulated transient docker inspect failure")

    monkeypatch.setattr(rtc.docker_backend, "_docker_inspect", _raise)
    assert (
        rtc._confirm_container_terminal_state(  # pylint: disable=protected-access
            "c", expected_container_id=_REAL_CONTAINER_ID
        )
        is False
    )


# ---------------------------------------------------------------------------
# 2. CgroupPeakFileCollector: full event-order / decision table, via the
#    real factory (so container-id threading is exercised end to end,
#    not just the predicate in isolation)
# ---------------------------------------------------------------------------


def _memory_collector(tmp_path: Path, *, content: str) -> tuple[rtc.CgroupPeakFileCollector, str]:
    peak_file = tmp_path / "memory.peak"
    peak_file.write_text(content)
    probe = FakeHostCapabilityProbe(memory_peak_paths={_REAL_CONTAINER_ID: str(peak_file)})
    factory = rtc.TelemetryCollectorFactory(probe, rtc.CollectorSelectionConfig())
    collector, identity = factory.build_memory_collector(
        container_id=_REAL_CONTAINER_ID, container_name="c"
    )
    assert identity.method == CollectorMethod.CGROUP_V2_MEMORY_PEAK
    assert isinstance(collector, rtc.CgroupPeakFileCollector)
    return collector, str(peak_file)


def test_confirmed_and_read_succeeds_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Terminal state confirmed, same cgroup peak then successfully read
    -> EXACT."""
    collector, _path = _memory_collector(tmp_path, content="2048\n")
    monkeypatch.setattr(rtc.docker_backend, "_docker_inspect", lambda name: _inspect())
    observation = collector.finalize()
    assert observation.value == 2048
    assert observation.quality == TelemetryQuality.EXACT


def test_unconfirmed_never_reports_exact_even_with_a_readable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running=true and ExitCode=0 (or any other unconfirmed state) ->
    never EXACT, even though the file itself is perfectly readable."""
    collector, _path = _memory_collector(tmp_path, content="2048\n")
    monkeypatch.setattr(
        rtc.docker_backend,
        "_docker_inspect",
        lambda name: _inspect(running=True, status="running", finished_at=_ZERO_TIMESTAMP),
    )
    observation = collector.finalize()
    assert observation.quality != TelemetryQuality.EXACT
    assert observation.quality == TelemetryQuality.BOUNDARY_ONLY


def test_confirmed_but_file_gone_falls_back_to_earlier_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Terminal state confirmed but peak file already gone, with an
    earlier observation -> BOUNDARY_ONLY, not EXACT and not lost."""
    collector, path = _memory_collector(tmp_path, content="1024\n")
    collector.sample()  # succeeds while the file still exists
    Path(path).unlink()
    monkeypatch.setattr(rtc.docker_backend, "_docker_inspect", lambda name: _inspect())
    observation = collector.finalize()
    assert observation.value == 1024
    assert observation.quality == TelemetryQuality.BOUNDARY_ONLY


def test_confirmed_but_file_gone_with_no_earlier_sample_is_typed_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Terminal state confirmed but peak file gone, with no observation
    at all -> a typed unavailable state, never a raised exception and
    never EXACT."""
    collector, path = _memory_collector(tmp_path, content="1024\n")
    Path(path).unlink()  # gone before any sample() or the final read
    monkeypatch.setattr(rtc.docker_backend, "_docker_inspect", lambda name: _inspect())
    observation = collector.finalize()
    assert observation.value is None
    assert observation.quality is None
    assert observation.unavailable_reason == TelemetryUnavailableReason.HOST_TELEMETRY_UNAVAILABLE


def test_container_never_created_scenario_is_never_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the container is not found at all (never created, or already
    gone), confirmation fails and the collector must fall back to
    BOUNDARY_ONLY/unavailable -- never EXACT."""
    collector, _path = _memory_collector(tmp_path, content="2048\n")
    monkeypatch.setattr(rtc.docker_backend, "_docker_inspect", lambda name: _inspect(found=False))
    observation = collector.finalize()
    assert observation.quality != TelemetryQuality.EXACT


def test_cgroup_identity_mismatch_is_never_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A container inspect that reports a *different* container's id
    (name reuse, or a race resolving to the wrong container) must never
    let this invocation's read be trusted as EXACT -- a stale/foreign
    cgroup must never be accepted as this invocation's own."""
    collector, _path = _memory_collector(tmp_path, content="2048\n")
    monkeypatch.setattr(
        rtc.docker_backend,
        "_docker_inspect",
        lambda name: _inspect(container_full_id=_OTHER_CONTAINER_ID),
    )
    observation = collector.finalize()
    assert observation.quality != TelemetryQuality.EXACT
    assert observation.quality == TelemetryQuality.BOUNDARY_ONLY


def test_oom_killed_termination_with_retained_peak_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OOM/SIGKILL termination with a retained, readable post-terminal
    peak -> exactness is determined by terminal-state coverage, not by
    exit-code success (137 here is a real kill exit code, and
    oom_killed=True)."""
    collector, _path = _memory_collector(tmp_path, content="536870912\n")
    monkeypatch.setattr(
        rtc.docker_backend,
        "_docker_inspect",
        lambda name: _inspect(exit_code=137, oom_killed=True),
    )
    observation = collector.finalize()
    assert observation.value == 536870912
    assert observation.quality == TelemetryQuality.EXACT


def test_late_terminal_spike_is_captured_by_the_fresh_read_not_the_stale_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A late resource spike occurring after the last pre-terminal
    sample() must be reflected in the EXACT value -- the pre-terminal
    sample is never substituted for a successful fresh post-confirmation
    read, so a late spike can never be silently missed by trusting a
    stale value."""
    collector, path = _memory_collector(tmp_path, content="1000\n")  # baseline
    collector.sample()  # observes only the baseline -- the spike hasn't happened yet
    # the late spike, now reflected in the kernel-maintained file
    Path(path).write_text("9999\n", encoding="ascii")
    monkeypatch.setattr(rtc.docker_backend, "_docker_inspect", lambda name: _inspect())
    observation = collector.finalize()
    assert observation.value == 9999  # the fresh, post-confirmation read -- not the stale 1000
    assert observation.quality == TelemetryQuality.EXACT


# ---------------------------------------------------------------------------
# 3. The same rules apply independently to pids.peak
# ---------------------------------------------------------------------------


def test_pids_peak_follows_the_identical_decision_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CGROUP_V2_PIDS_PEAK is served by the same CgroupPeakFileCollector
    class -- confirms EXACT under a genuinely terminal state, exactly
    like memory.peak, via the same predicate."""
    peak_file = tmp_path / "pids.peak"
    peak_file.write_text("11\n")
    probe = FakeHostCapabilityProbe(pids_peak_paths={_REAL_CONTAINER_ID: str(peak_file)})
    factory = rtc.TelemetryCollectorFactory(probe, rtc.CollectorSelectionConfig())
    collector, identity = factory.build_process_count_collector(
        container_id=_REAL_CONTAINER_ID, container_name="c"
    )
    assert identity.method == CollectorMethod.CGROUP_V2_PIDS_PEAK
    monkeypatch.setattr(rtc.docker_backend, "_docker_inspect", lambda name: _inspect())
    observation = collector.finalize()
    assert observation.value == 11
    assert observation.quality == TelemetryQuality.EXACT


def test_pids_peak_never_exact_when_running_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Running=true/ExitCode=0 defect is equally corrected for
    pids.peak, not just memory.peak."""
    peak_file = tmp_path / "pids.peak"
    peak_file.write_text("11\n")
    probe = FakeHostCapabilityProbe(pids_peak_paths={_REAL_CONTAINER_ID: str(peak_file)})
    factory = rtc.TelemetryCollectorFactory(probe, rtc.CollectorSelectionConfig())
    collector, _identity = factory.build_process_count_collector(
        container_id=_REAL_CONTAINER_ID, container_name="c"
    )
    monkeypatch.setattr(
        rtc.docker_backend,
        "_docker_inspect",
        lambda name: _inspect(running=True, status="running", finished_at=_ZERO_TIMESTAMP),
    )
    observation = collector.finalize()
    assert observation.quality != TelemetryQuality.EXACT
