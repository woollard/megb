"""MEGB-03H.2C.2A: real, controller-side telemetry collectors.

Two collection strategies, matching the H.2C.2A authorization's candidate
methods exactly:

* :class:`CgroupPeakFileCollector` -- reads a single already-existing,
  kernel-maintained cgroup v2 peak-tracking file (``memory.peak`` or
  ``pids.peak``) directly, host-side, exactly once, after the candidate's
  container has already run to completion and before it is removed. No
  sampling: the kernel itself continuously maintains the peak for the
  entire lifetime of the container's own cgroup, which is created fresh
  and destroyed with the container (MEGB-02's per-invocation-container
  design) -- so a peak read post-hoc already reflects, and only reflects,
  this one invocation's own resource use. This is what justifies
  :class:`~src.execution.telemetry.TelemetryQuality.EXACT` here: the
  scope (the entire container's process tree, not just the candidate
  function) and reset behavior (fresh cgroup per invocation, so no stale
  carry-over from a prior invocation) are both structurally guaranteed by
  the existing sandbox design, not merely assumed.

* :class:`SampledPollingCollector` -- a background thread that polls a
  host-side, read-only sampling function at a fixed interval, tracking
  the observed maximum, used when no exact kernel-maintained peak is
  available. A polled maximum is a lower bound on the true peak (it can
  miss a spike between samples), not the peak itself, and carries no
  defensible quantitative error bound (the miss probability depends on
  the candidate's own runtime behavior, not a fixed sampler
  characteristic) -- so every real use of this collector reports
  :class:`~src.execution.telemetry.TelemetryQuality.BOUNDARY_ONLY`,
  never ``EXACT`` or ``SAMPLED_WITH_KNOWN_ERROR``.

Neither collector ever uses ``docker exec``, mounts anything into a
candidate container, requests privileged/host-PID-namespace access, or
runs any in-container telemetry agent -- both are purely host-side,
read-only with respect to the candidate's own execution.

``src/execution/`` still never imports ``src/reference/`` from this
module.
"""

import os
import platform
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable

from src.execution import docker_backend
from src.execution.telemetry import (
    TelemetryObservation,
    TelemetryQuality,
    TelemetryUnavailableReason,
)
from src.execution.telemetry_collectors import TelemetryCollector
from src.execution.telemetry_methods import (
    CollectorMethod,
    CollectorMethodIdentity,
    HostCapabilityProbe,
    MetricCollectionDisposition,
    TerminalCoverageState,
)

_DOCKER_CLI_TIMEOUT_SEC = 5.0

CGROUP_PEAK_FILE_COLLECTOR_VERSION = "cgroup_peak_file_collector/v1"
SAMPLED_POLLING_COLLECTOR_VERSION = "sampled_polling_collector/v1"


# ---------------------------------------------------------------------------
# Exact: cgroup v2 peak-file collector
# ---------------------------------------------------------------------------


class CgroupPeakFileCollector(TelemetryCollector):
    """Reads one cgroup v2 peak-tracking file, at ``finalize()``. See the
    module docstring for why this is ``EXACT`` -- but only when
    ``confirm_terminal_state`` proves it (MEGB-03H.2C.2A provenance/
    schema correction, further hardened by the terminal-state-proof
    audit): file existence or a successful read alone are not
    sufficient. ``confirm_terminal_state`` is a required, independent,
    injected check (never assumed from call-site ordering alone) that
    must itself prove -- not merely observe an exit code -- that the
    candidate's container has actually terminated (see
    ``_confirm_container_terminal_state`` for the full predicate) before
    a read taken *after* that confirmation is trusted to cover the
    container's complete resource lifetime.

    Event order enforced here, matching the terminal-state-proof audit:
    1. ``confirm_terminal_state()`` is called first, always, before any
       read this call performs is trusted;
    2. only *then* is the peak file opened and read (never the reverse);
    3. if that post-confirmation read succeeds, the value is ``EXACT``;
    4. if it fails (the file disappeared in a lifecycle race after
       confirmation, or confirmation itself failed), an earlier,
       best-effort intermediate read captured via :meth:`sample` --
       itself never trusted as ``EXACT``, since candidate activity may
       have occurred after it was taken -- is used as a ``BOUNDARY_ONLY``
       lower bound if one exists;
    5. if no reading exists at all, the metric is reported unavailable
       (``HOST_TELEMETRY_UNAVAILABLE``) rather than raising -- a genuine
       runtime race, not a capability absence
       (``UNAVAILABLE_WITHOUT_CONTAMINATION``), which is reserved for the
       case where no method was ever selected at all.

    A confirmed terminal read that later fails is never silently
    retained as ``EXACT``, and a value read before confirmation can never
    become ``EXACT`` merely because confirmation later succeeds
    separately -- only a read taken strictly *after* a successful
    ``confirm_terminal_state()`` call, within this same ``finalize()``
    invocation, is ever reported ``EXACT``.
    """

    def __init__(
        self,
        path: str,
        method_identity: CollectorMethodIdentity,
        *,
        confirm_terminal_state: Callable[[], bool],
    ) -> None:
        self._path = path
        self._method_identity = method_identity
        self._confirm_terminal_state = confirm_terminal_state
        self._last_observed_value: int | None = None

    def start(self) -> None:
        """No-op: the kernel already tracks the peak continuously; there
        is nothing this collector needs to begin."""

    def sample(self) -> None:
        """Best-effort, non-authoritative intermediate read, safe to call
        any number of times (including zero) while the candidate is still
        running. Never raises and never itself trusted as ``EXACT`` --
        candidate activity occurring after this call is invisible to it
        -- but its value is retained as a ``BOUNDARY_ONLY`` fallback in
        case the authoritative post-termination read in :meth:`finalize`
        is not obtainable (e.g. this host tears the cgroup file down
        before the container is removed)."""
        try:
            self._last_observed_value = self._read_peak_value()
        except (OSError, ValueError):
            pass

    def _read_peak_value(self) -> int:
        with open(self._path, "r", encoding="ascii") as peak_file:
            raw = peak_file.read().strip()
        return int(raw)

    def finalize(self) -> TelemetryObservation:
        terminal_state_confirmed = self._confirm_terminal_state()
        try:
            final_value: int | None = self._read_peak_value()
        except (OSError, ValueError):
            final_value = None

        if terminal_state_confirmed and final_value is not None:
            return TelemetryObservation(
                value=final_value,
                quality=TelemetryQuality.EXACT,
                unavailable_reason=None,
                method_identity=self._method_identity,
                terminal_coverage=TerminalCoverageState.TERMINAL_READ_CONFIRMED,
            )

        fallback_value = final_value if final_value is not None else self._last_observed_value
        if fallback_value is not None:
            return TelemetryObservation(
                value=fallback_value,
                quality=TelemetryQuality.BOUNDARY_ONLY,
                unavailable_reason=None,
                method_identity=self._method_identity,
                terminal_coverage=TerminalCoverageState.TERMINAL_READ_MISSED,
            )
        return TelemetryObservation(
            value=None,
            quality=None,
            unavailable_reason=TelemetryUnavailableReason.HOST_TELEMETRY_UNAVAILABLE,
            method_identity=self._method_identity,
            terminal_coverage=TerminalCoverageState.TERMINAL_READ_MISSED,
        )

    def cleanup(self) -> None:
        """No-op: no resources were acquired beyond one or two file reads."""


# ---------------------------------------------------------------------------
# Boundary-only: bounded, non-busy-loop sampled polling collector
# ---------------------------------------------------------------------------


class SampledPollingCollector(TelemetryCollector):  # pylint: disable=too-many-instance-attributes
    """Runs a background thread that waits for the target container to
    exist (bounded, read-only polling), then samples a host-side callable
    at a fixed interval until ``finalize()`` stops it -- always before
    the container is removed by the caller.

    Every wait/sample loop uses ``threading.Event.wait(timeout)``, which
    blocks without busy-looping and returns immediately once the event is
    set, rather than a tight ``while True: ...; sleep(...)`` spin.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        container_exists: Callable[[], bool],
        sample_fn: Callable[[], int | None],
        sampling_interval_sec: float,
        existence_poll_interval_sec: float,
        existence_wait_max_sec: float,
        method_identity: CollectorMethodIdentity,
    ) -> None:
        self._container_exists = container_exists
        self._sample_fn = sample_fn
        self._sampling_interval_sec = sampling_interval_sec
        self._existence_poll_interval_sec = existence_poll_interval_sec
        self._existence_wait_max_sec = existence_wait_max_sec
        self._method_identity = method_identity
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._observed_max: int | None = None
        self._sample_count = 0
        self._container_never_appeared = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def sample(self) -> None:
        """No-op: sampling happens autonomously in the background thread
        started by :meth:`start`, not via externally driven calls to
        this method."""

    def _run(self) -> None:
        if not self._wait_for_container():
            return
        while not self._stop_event.wait(self._sampling_interval_sec):
            self._take_one_sample()
        self._take_one_sample()

    def _wait_for_container(self) -> bool:
        deadline = time.monotonic() + self._existence_wait_max_sec
        while not self._stop_event.is_set():
            if self._safe_container_exists():
                return True
            if time.monotonic() >= deadline:
                self._container_never_appeared = True
                return False
            self._stop_event.wait(self._existence_poll_interval_sec)
        return False

    def _safe_container_exists(self) -> bool:
        """A transient failure in the existence check (e.g. a flaky
        ``docker inspect`` call) must not crash the background thread --
        treated the same as "not yet found", tolerated until the bounded
        deadline, exactly like a failed sample in :meth:`_take_one_sample`."""
        try:
            return self._container_exists()
        except Exception:  # pylint: disable=broad-exception-caught
            return False

    def _take_one_sample(self) -> None:
        try:
            value = self._sample_fn()
        except Exception:  # pylint: disable=broad-exception-caught
            return
        if value is None:
            return
        with self._lock:
            self._sample_count += 1
            if self._observed_max is None or value > self._observed_max:
                self._observed_max = value

    def finalize(self) -> TelemetryObservation:
        self._stop_event.set()
        self._join_thread()
        if self._container_never_appeared:
            raise RuntimeError("target container never appeared within the bounded wait")
        with self._lock:
            value = self._observed_max
            sample_count = self._sample_count
        if value is None:
            # Every sample attempt raised (the callable never returned a
            # usable value even once) -- a genuine sampler failure, not
            # capability absence (capability was already confirmed during
            # method selection).
            return TelemetryObservation(
                value=None,
                quality=None,
                unavailable_reason=TelemetryUnavailableReason.HOST_TELEMETRY_UNAVAILABLE,
                method_identity=self._method_identity,
            )
        return TelemetryObservation(
            value=value,
            quality=TelemetryQuality.BOUNDARY_ONLY,
            unavailable_reason=None,
            method_identity=self._method_identity,
            actual_sample_count=sample_count,
        )

    def cleanup(self) -> None:
        self._stop_event.set()
        self._join_thread()

    def _join_thread(self) -> None:
        if self._thread is None:
            return
        join_timeout = self._existence_wait_max_sec + self._sampling_interval_sec * 4
        self._thread.join(timeout=join_timeout)
        if self._thread.is_alive():
            raise RuntimeError("telemetry sampling thread did not terminate within the bound")


# ---------------------------------------------------------------------------
# UNAVAILABLE_WITHOUT_CONTAMINATION: the explicit, typed no-method-available result
# ---------------------------------------------------------------------------


class _UnavailableCollector(TelemetryCollector):
    """Used when capability probing finds no method -- exact or sampled
    -- available without contaminating or weakening the sandbox. Never
    raises; always reports ``UNAVAILABLE_WITHOUT_CONTAMINATION``
    directly, never ``SAMPLER_FAILURE`` (which would incorrectly imply a
    method was attempted and failed operationally)."""

    def __init__(self, method_identity: CollectorMethodIdentity) -> None:
        self._method_identity = method_identity

    def start(self) -> None:
        """No-op: there is no method to start."""

    def sample(self) -> None:
        """No-op: there is no method to sample."""

    def finalize(self) -> TelemetryObservation:
        return TelemetryObservation(
            value=None,
            quality=None,
            unavailable_reason=TelemetryUnavailableReason.UNAVAILABLE_WITHOUT_CONTAMINATION,
            method_identity=self._method_identity,
        )

    def cleanup(self) -> None:
        """No-op: no resources were ever acquired."""


# ---------------------------------------------------------------------------
# Docker-CLI sampling helpers (read-only; no docker exec, no in-container agent)
# ---------------------------------------------------------------------------

_MEM_UNIT_MULTIPLIERS = {
    "B": 1,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
    "TiB": 1024**4,
}

_MEM_USAGE_PATTERN = re.compile(r"^([0-9]*\.?[0-9]+)\s*([A-Za-z]+)$")


def _parse_docker_mem_usage_bytes(mem_usage_field: str) -> int:
    """Parse ``docker stats --format '{{.MemUsage}}'``'s own
    ``"<used> / <limit>"`` string (e.g. ``"12.34MiB / 512MiB"``) into the
    used-bytes integer. Pure and offline-testable -- no subprocess call."""
    used_part = mem_usage_field.split("/", maxsplit=1)[0].strip()
    match = _MEM_USAGE_PATTERN.match(used_part)
    if match is None:
        raise ValueError(f"unrecognized docker stats MemUsage field: {mem_usage_field!r}")
    number = float(match.group(1))
    unit = match.group(2)
    if unit not in _MEM_UNIT_MULTIPLIERS:
        raise ValueError(f"unrecognized docker stats memory unit: {unit!r}")
    return int(number * _MEM_UNIT_MULTIPLIERS[unit])


def _docker_stats_mem_usage_bytes(container_name: str) -> int:
    result = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container_name],
        capture_output=True,
        text=True,
        check=True,
        timeout=_DOCKER_CLI_TIMEOUT_SEC,
    )
    return _parse_docker_mem_usage_bytes(result.stdout.strip())


def _docker_top_process_count(container_name: str) -> int:
    result = subprocess.run(
        ["docker", "top", container_name, "-q"],
        capture_output=True,
        text=True,
        check=True,
        timeout=_DOCKER_CLI_TIMEOUT_SEC,
    )
    return len([line for line in result.stdout.splitlines() if line.strip()])


def _container_exists(container_name: str) -> bool:
    # Deliberately calls the module attribute rather than a directly
    # imported name, so a test's monkeypatch of docker_backend's own
    # _docker_inspect (already the established fake-Docker-harness
    # pattern) takes effect here too.
    return docker_backend._docker_inspect(container_name).found  # pylint: disable=protected-access


# MEGB-03H.2C.2A terminal-state-proof audit: State.ExitCode alone is not
# evidence of termination -- Docker's own Go template reports its zero
# value (0) for a container that is still RUNNING, exactly as it would
# for a genuinely successful exit, so "exit_code is not None" is true
# almost immediately after a container is merely created and is not a
# terminal-state proof at all. Every one of the following is required.
_TERMINAL_CONTAINER_STATUSES = frozenset({"exited", "dead"})
# Docker's own zero-value RFC3339 timestamp for an unset time.Time field.
_DOCKER_ZERO_TIMESTAMP_PREFIX = "0001-01-01T00:00:00"


def _is_populated_finished_at(finished_at: str) -> bool:
    """``True`` only for a real, non-zero ``State.FinishedAt`` value --
    Docker leaves this at its zero-value timestamp until the container
    has actually finished."""
    return bool(finished_at) and not finished_at.startswith(_DOCKER_ZERO_TIMESTAMP_PREFIX)


def _confirm_container_terminal_state(container_name: str, *, expected_container_id: str) -> bool:
    """Independent confirmation (MEGB-03H.2C.2A provenance/schema
    correction; corrected by the terminal-state-proof audit) that the
    container has actually stopped, via signals separate from mere
    call-site ordering or a bare exit-code value. Read-only; never
    ``docker exec``. Any exception (e.g. a transient inspect failure) is
    treated as unconfirmed, never as confirmed -- the safe default for a
    terminal-coverage proof.

    Every one of the following must hold, matching the audit's minimum
    requirements exactly:

    * the container is still inspectable at all (``found``);
    * its inspected identity (``.Id``) is the *same* container this
      collector's cgroup path was derived from -- ``expected_container_id``
      is the id resolved once, before any candidate execution began, and
      threaded through by the caller; a mismatch means the name was
      reused or now resolves to a different container than the one whose
      cgroup we are about to trust, and must never be treated as this
      invocation's own terminal state;
    * ``State.Running`` is explicitly ``false`` -- not inferred from the
      exit code's mere presence;
    * ``State.Status`` is a real terminal status (``exited``/``dead``),
      not e.g. ``created``/``running``/``restarting``/``paused``;
    * ``State.FinishedAt`` is populated with a real, non-zero timestamp.
    """
    try:
        info = docker_backend._docker_inspect(container_name)  # pylint: disable=protected-access
    except Exception:  # pylint: disable=broad-exception-caught
        return False
    if not info.found:
        return False
    if info.container_full_id != expected_container_id:
        return False
    if info.running:
        return False
    if info.status not in _TERMINAL_CONTAINER_STATUSES:
        return False
    return _is_populated_finished_at(info.finished_at)


# ---------------------------------------------------------------------------
# cgroup v2 path resolution (pure path construction, offline-testable;
# file-existence/readability is checked separately)
# ---------------------------------------------------------------------------


def _candidate_cgroup_v2_paths(
    container_id: str, filename: str, cgroup_driver: str | None
) -> tuple[str, ...]:
    """Every host-side path this container's cgroup v2 peak-tracking
    ``filename`` could live at, for the cgroup drivers Docker actually
    supports. When ``cgroup_driver`` is unknown (probe failed), every
    known driver's path is tried, most common (``systemd``) first."""
    candidates = []
    if cgroup_driver in (None, "systemd"):
        candidates.append(f"/sys/fs/cgroup/system.slice/docker-{container_id}.scope/{filename}")
    if cgroup_driver in (None, "cgroupfs"):
        candidates.append(f"/sys/fs/cgroup/docker/{container_id}/{filename}")
    return tuple(candidates)


def _first_existing_readable_path(paths: tuple[str, ...]) -> str | None:
    for path in paths:
        if os.path.isfile(path) and os.access(path, os.R_OK):
            return path
    return None


def _cgroup_driver() -> str | None:
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.CgroupDriver}}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_DOCKER_CLI_TIMEOUT_SEC,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    driver = result.stdout.strip()
    return driver or None


# ---------------------------------------------------------------------------
# RealHostCapabilityProbe
# ---------------------------------------------------------------------------


class RealHostCapabilityProbe(HostCapabilityProbe):
    """The real, host-side capability probe. Every method here is
    read-only: filesystem existence/readability checks and read-only
    Docker CLI invocations (``docker info``) -- never ``docker exec``,
    never a write, never touches a candidate's own execution."""

    def host_runtime_metadata(self) -> tuple[tuple[str, str], ...]:
        # See _container_exists()'s own comment: calling the module
        # attribute (not a directly-imported name) so monkeypatching
        # docker_backend._docker_server_version takes effect here too.
        server_version = docker_backend._docker_server_version()  # pylint: disable=protected-access
        pairs = [
            ("kernel_release", platform.release()),
            ("docker_server_version", server_version),
        ]
        driver = _cgroup_driver()
        if driver is not None:
            pairs.append(("cgroup_driver", driver))
        return tuple(pairs)

    def cgroup_v2_memory_peak_path(self, container_id: str) -> str | None:
        return _first_existing_readable_path(
            _candidate_cgroup_v2_paths(container_id, "memory.peak", _cgroup_driver())
        )

    def cgroup_v2_pids_peak_path(self, container_id: str) -> str | None:
        return _first_existing_readable_path(
            _candidate_cgroup_v2_paths(container_id, "pids.peak", _cgroup_driver())
        )

    def docker_stats_sampling_available(self) -> bool:
        try:
            subprocess.run(
                ["docker", "stats", "--help"],
                capture_output=True,
                check=True,
                timeout=_DOCKER_CLI_TIMEOUT_SEC,
            )
        except (subprocess.SubprocessError, OSError):
            return False
        return True

    def docker_top_sampling_available(self) -> bool:
        try:
            subprocess.run(
                ["docker", "top", "--help"],
                capture_output=True,
                check=True,
                timeout=_DOCKER_CLI_TIMEOUT_SEC,
            )
        except (subprocess.SubprocessError, OSError):
            return False
        return True


# ---------------------------------------------------------------------------
# Collector selection: frozen precedence, disabled by default
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectorSelectionConfig:
    """Disabled by default (``enabled=False``), per the H.2C.2A
    authorization's explicit requirement -- real collection is never
    silently turned on."""

    enabled: bool = False
    memory_sampling_interval_sec: float = 0.5
    process_count_sampling_interval_sec: float = 0.5
    existence_poll_interval_sec: float = 0.05
    existence_wait_max_sec: float = 5.0


class TelemetryCollectorFactory:
    """Builds one memory and one process-count collector per invocation,
    following a frozen, deterministic selection precedence:

    Memory: ``CGROUP_V2_MEMORY_PEAK`` (exact, if the capability probe
    resolves a readable ``memory.peak`` path) → ``SAMPLED_DOCKER_STATS_MEMORY``
    (boundary-only, if sampling is available) → ``UNAVAILABLE_WITHOUT_CONTAMINATION``.

    Process count: ``CGROUP_V2_PIDS_PEAK`` (exact, if the capability
    probe resolves a readable ``pids.peak`` path) → ``SAMPLED_DOCKER_TOP_PROCESS_COUNT``
    (boundary-only, if sampling is available) → ``UNAVAILABLE_WITHOUT_CONTAMINATION``.

    No automatic fallback ever changes a *value already selected* --
    precedence is evaluated once, per invocation, before any collector
    runs; nothing here re-selects mid-invocation.
    """

    def __init__(
        self, capability_probe: HostCapabilityProbe, config: CollectorSelectionConfig
    ) -> None:
        self._capability_probe = capability_probe
        self._config = config

    def build_memory_collector(
        self, *, container_id: str, container_name: str
    ) -> tuple[TelemetryCollector, CollectorMethodIdentity]:
        """Select and build this invocation's memory collector, per the
        frozen precedence documented on this class."""
        host_metadata = self._capability_probe.host_runtime_metadata()
        peak_path = self._capability_probe.cgroup_v2_memory_peak_path(container_id)
        if peak_path is not None:
            identity = CollectorMethodIdentity(
                method=CollectorMethod.CGROUP_V2_MEMORY_PEAK,
                method_version=CGROUP_PEAK_FILE_COLLECTOR_VERSION,
                interface=f"cgroupfs:{peak_path}",
                sampling_interval_sec=None,
                selection_disposition=MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
                host_runtime_metadata=host_metadata,
            )
            collector: TelemetryCollector = CgroupPeakFileCollector(
                peak_path,
                identity,
                confirm_terminal_state=lambda: _confirm_container_terminal_state(
                    container_name, expected_container_id=container_id
                ),
            )
            return collector, identity
        if self._capability_probe.docker_stats_sampling_available():
            identity = CollectorMethodIdentity(
                method=CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY,
                method_version=SAMPLED_POLLING_COLLECTOR_VERSION,
                interface="docker stats --no-stream --format {{.MemUsage}}",
                sampling_interval_sec=self._config.memory_sampling_interval_sec,
                selection_disposition=MetricCollectionDisposition.FALLBACK_METHOD_SELECTED,
                host_runtime_metadata=host_metadata,
            )
            collector = SampledPollingCollector(
                container_exists=lambda: _container_exists(container_name),
                sample_fn=lambda: _docker_stats_mem_usage_bytes(container_name),
                sampling_interval_sec=self._config.memory_sampling_interval_sec,
                existence_poll_interval_sec=self._config.existence_poll_interval_sec,
                existence_wait_max_sec=self._config.existence_wait_max_sec,
                method_identity=identity,
            )
            return collector, identity
        identity = CollectorMethodIdentity(
            method=CollectorMethod.UNAVAILABLE_WITHOUT_CONTAMINATION,
            method_version="unavailable/v1",
            interface="none",
            sampling_interval_sec=None,
            selection_disposition=MetricCollectionDisposition.NO_METHOD_AVAILABLE,
            host_runtime_metadata=host_metadata,
        )
        return _UnavailableCollector(identity), identity

    def build_process_count_collector(
        self, *, container_id: str, container_name: str
    ) -> tuple[TelemetryCollector, CollectorMethodIdentity]:
        """Select and build this invocation's process-count collector,
        per the frozen precedence documented on this class."""
        host_metadata = self._capability_probe.host_runtime_metadata()
        peak_path = self._capability_probe.cgroup_v2_pids_peak_path(container_id)
        if peak_path is not None:
            identity = CollectorMethodIdentity(
                method=CollectorMethod.CGROUP_V2_PIDS_PEAK,
                method_version=CGROUP_PEAK_FILE_COLLECTOR_VERSION,
                interface=f"cgroupfs:{peak_path}",
                sampling_interval_sec=None,
                selection_disposition=MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
                host_runtime_metadata=host_metadata,
            )
            collector: TelemetryCollector = CgroupPeakFileCollector(
                peak_path,
                identity,
                confirm_terminal_state=lambda: _confirm_container_terminal_state(
                    container_name, expected_container_id=container_id
                ),
            )
            return collector, identity
        if self._capability_probe.docker_top_sampling_available():
            identity = CollectorMethodIdentity(
                method=CollectorMethod.SAMPLED_DOCKER_TOP_PROCESS_COUNT,
                method_version=SAMPLED_POLLING_COLLECTOR_VERSION,
                interface="docker top <container> -q",
                sampling_interval_sec=self._config.process_count_sampling_interval_sec,
                selection_disposition=MetricCollectionDisposition.FALLBACK_METHOD_SELECTED,
                host_runtime_metadata=host_metadata,
            )
            collector = SampledPollingCollector(
                container_exists=lambda: _container_exists(container_name),
                sample_fn=lambda: _docker_top_process_count(container_name),
                sampling_interval_sec=self._config.process_count_sampling_interval_sec,
                existence_poll_interval_sec=self._config.existence_poll_interval_sec,
                existence_wait_max_sec=self._config.existence_wait_max_sec,
                method_identity=identity,
            )
            return collector, identity
        identity = CollectorMethodIdentity(
            method=CollectorMethod.UNAVAILABLE_WITHOUT_CONTAMINATION,
            method_version="unavailable/v1",
            interface="none",
            sampling_interval_sec=None,
            selection_disposition=MetricCollectionDisposition.NO_METHOD_AVAILABLE,
            host_runtime_metadata=host_metadata,
        )
        return _UnavailableCollector(identity), identity


__all__ = [
    "CgroupPeakFileCollector",
    "SampledPollingCollector",
    "RealHostCapabilityProbe",
    "CollectorSelectionConfig",
    "TelemetryCollectorFactory",
    "CollectorMethodIdentity",
    "docker_backend",
]
