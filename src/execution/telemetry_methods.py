"""MEGB-03H.2C.2A: collector-method/capability provenance model.

Execution-layer only, never persisted -- see the H.2C.2A calibration-
provenance audit (``docs/reference/megb-03h2c2a-collector-provenance-
audit.md``): the accepted H.2A ``CalibrationInvocationRecord``/
``CalibrationRunContext`` schema (``src/reference/calibration_schema.py``)
has no field capable of binding a real telemetry measurement to the exact
collector implementation/version, collection method, sampling interval,
capability/fallback choice, cgroup/Docker interface, or host/runtime
metadata that produced it -- only a value/quality/reason triple per
metric. Rather than silently encoding any of that into
``execution_profile_id`` or another unrelated persisted field (explicitly
forbidden by the H.2C.2A authorization), this module defines that
provenance entirely at the execution layer, exactly mirroring the
established precedent of ``CollectorFailureStage``/``cleanup_failed``
(MEGB-03H.2C.1): real, richly-typed, and completely inert with respect to
the accepted persisted schema until a separately authorized schema change
(H.2C.2B or later) decides how -- or whether -- to carry it forward.

``src/execution/`` still never imports ``src/reference/`` from this
module, preserving the one-way dependency direction the architecture
requires.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class CollectorMethod(str, Enum):
    """Every real or explicit-fallback telemetry-collection method this
    checkpoint defines, exhaustive over what
    :class:`~src.execution.real_telemetry_collectors.TelemetryCollectorFactory`
    may ever select. New methods require a new member here (never an
    ad hoc string), so every observation's provenance stays one of a
    closed, typed set.

    ``CGROUP_V2_MEMORY_PEAK``/``CGROUP_V2_PIDS_PEAK`` read a single
    kernel-maintained peak-tracking file directly, host-side, for a
    container's own cgroup -- no ``docker exec``, no in-container agent.
    ``SAMPLED_DOCKER_STATS_MEMORY``/``SAMPLED_DOCKER_TOP_PROCESS_COUNT``
    poll a read-only Docker CLI command at a fixed interval, tracking the
    observed maximum -- a lower bound on the true peak, not the peak
    itself. ``UNAVAILABLE_WITHOUT_CONTAMINATION`` is the explicit,
    typed outcome when capability probing finds neither exact nor sampled
    collection possible without weakening the sandbox or touching the
    candidate's own execution.
    """

    CGROUP_V2_MEMORY_PEAK = "CGROUP_V2_MEMORY_PEAK"
    CGROUP_V2_PIDS_PEAK = "CGROUP_V2_PIDS_PEAK"
    SAMPLED_DOCKER_STATS_MEMORY = "SAMPLED_DOCKER_STATS_MEMORY"
    SAMPLED_DOCKER_TOP_PROCESS_COUNT = "SAMPLED_DOCKER_TOP_PROCESS_COUNT"
    UNAVAILABLE_WITHOUT_CONTAMINATION = "UNAVAILABLE_WITHOUT_CONTAMINATION"


SAMPLED_METHODS = frozenset(
    {CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY, CollectorMethod.SAMPLED_DOCKER_TOP_PROCESS_COUNT}
)


class MetricCollectionDisposition(str, Enum):
    """Typed selection/fallback disposition for one metric's actual
    method (MEGB-03H.2C.2A provenance/schema correction) -- *why* this
    invocation's collector ended up using the method it did, distinct
    from the method itself: two invocations using the identical method
    can have gotten there differently (one via its primary path, one via
    fallback after a capability probe failed), and that difference
    matters for interpreting a real measurement's portability."""

    PRIMARY_METHOD_SELECTED = "PRIMARY_METHOD_SELECTED"
    FALLBACK_METHOD_SELECTED = "FALLBACK_METHOD_SELECTED"
    NO_METHOD_AVAILABLE = "NO_METHOD_AVAILABLE"


class TerminalCoverageState(str, Enum):
    """Whether a collector's own terminal (final) read was confirmed to
    have happened while the underlying resource (cgroup, container) was
    still valid and after all candidate resource activity had already
    ended -- the exactness correction this checkpoint adds. File
    existence or a successful *mid-execution* read is not sufficient
    proof; only an explicit, independently-confirmed terminal-state check
    justifies ``EXACT``.

    ``TERMINAL_READ_NOT_APPLICABLE`` is the correct value for any method
    with no single terminal-read concept at all (every sampled method,
    and the explicit unavailable outcome) -- it is not a weaker claim of
    coverage, it is a statement that this axis does not apply.
    """

    TERMINAL_READ_CONFIRMED = "TERMINAL_READ_CONFIRMED"
    TERMINAL_READ_NOT_APPLICABLE = "TERMINAL_READ_NOT_APPLICABLE"
    TERMINAL_READ_MISSED = "TERMINAL_READ_MISSED"


@dataclass(frozen=True)
class CollectorMethodIdentity:
    """Everything needed to reproduce or interpret one observation's
    provenance -- distinct from, and never a substitute for, its
    :class:`~src.execution.telemetry.TelemetryQuality`. Two observations
    can share the same quality tier (e.g. both ``BOUNDARY_ONLY``) while
    having been produced by different methods with different portability
    characteristics; this identity is what lets that difference still be
    told apart, entirely at the execution layer.

    ``host_runtime_metadata`` is a tuple of ``(key, value)`` pairs, not a
    ``dict``, for true immutability on a frozen dataclass (matching this
    codebase's own convention, e.g.
    :class:`~src.reference.calibration_schema.CalibrationTaskEvaluationRecord`'s
    ``contributing_invocation_ids: tuple[str, ...]`` rather than a mutable
    sequence).
    """

    method: CollectorMethod
    method_version: str
    interface: str
    sampling_interval_sec: float | None
    selection_disposition: MetricCollectionDisposition
    host_runtime_metadata: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.method, CollectorMethod):
            raise ValueError(f"method must be a CollectorMethod, got {self.method!r}")
        if not isinstance(self.method_version, str) or self.method_version == "":
            raise ValueError(
                f"method_version must be a nonempty string, got {self.method_version!r}"
            )
        if not isinstance(self.interface, str) or self.interface == "":
            raise ValueError(f"interface must be a nonempty string, got {self.interface!r}")
        if self.sampling_interval_sec is not None and (
            isinstance(self.sampling_interval_sec, bool) or self.sampling_interval_sec <= 0
        ):
            raise ValueError(
                f"sampling_interval_sec must be a positive number or None, got "
                f"{self.sampling_interval_sec!r}"
            )
        if not isinstance(self.selection_disposition, MetricCollectionDisposition):
            raise ValueError(
                f"selection_disposition must be a MetricCollectionDisposition, got "
                f"{self.selection_disposition!r}"
            )
        if (self.method == CollectorMethod.UNAVAILABLE_WITHOUT_CONTAMINATION) != (
            self.selection_disposition == MetricCollectionDisposition.NO_METHOD_AVAILABLE
        ):
            raise ValueError(
                "selection_disposition must be NO_METHOD_AVAILABLE if and only if method is "
                f"UNAVAILABLE_WITHOUT_CONTAMINATION, got method={self.method!r}, "
                f"selection_disposition={self.selection_disposition!r}"
            )
        if not isinstance(self.host_runtime_metadata, tuple):
            raise ValueError(
                f"host_runtime_metadata must be a tuple, got "
                f"{type(self.host_runtime_metadata).__name__}"
            )
        for pair in self.host_runtime_metadata:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError(
                    f"host_runtime_metadata entries must be (key, value) pairs, got {pair!r}"
                )


class HostCapabilityProbe(ABC):
    """Read-only host-capability probing, independent of any candidate
    invocation. Every method here must be safe to call before a container
    exists, must never mutate host or container state, and must never run
    ``docker exec``, mount anything into a candidate container, or touch
    a candidate's own execution."""

    @abstractmethod
    def host_runtime_metadata(self) -> tuple[tuple[str, str], ...]:
        """Static, portability-relevant host/runtime facts -- e.g. kernel
        release, cgroup driver, Docker server version -- collected once,
        read-only, independent of any specific container."""

    @abstractmethod
    def cgroup_v2_memory_peak_path(self, container_id: str) -> str | None:
        """The host-readable path to ``container_id``'s cgroup v2
        ``memory.peak`` file, or ``None`` if not resolvable/readable on
        this host (cgroup v1, an unrecognized cgroup driver, or the file
        does not exist/is not readable)."""

    @abstractmethod
    def cgroup_v2_pids_peak_path(self, container_id: str) -> str | None:
        """The host-readable path to ``container_id``'s cgroup v2
        ``pids.peak`` file, or ``None`` (``pids.peak`` is a newer kernel
        addition than ``memory.peak`` and may be absent even when cgroup
        v2 memory accounting is otherwise available)."""

    @abstractmethod
    def docker_stats_sampling_available(self) -> bool:
        """Whether the read-only ``docker stats --no-stream`` sampling
        fallback is usable on this host at all (e.g. the Docker CLI
        itself is reachable)."""

    @abstractmethod
    def docker_top_sampling_available(self) -> bool:
        """Whether the read-only ``docker top`` sampling fallback is
        usable on this host at all."""


@dataclass
class FakeHostCapabilityProbe(HostCapabilityProbe):
    """A fully synthetic, configurable capability probe for offline tests
    -- never touches a real host, cgroup filesystem, or Docker CLI."""

    host_metadata: tuple[tuple[str, str], ...] = ()
    memory_peak_paths: dict[str, str | None] = field(default_factory=dict)
    pids_peak_paths: dict[str, str | None] = field(default_factory=dict)
    stats_sampling_available: bool = True
    top_sampling_available: bool = True

    def host_runtime_metadata(self) -> tuple[tuple[str, str], ...]:
        return self.host_metadata

    def cgroup_v2_memory_peak_path(self, container_id: str) -> str | None:
        return self.memory_peak_paths.get(container_id)

    def cgroup_v2_pids_peak_path(self, container_id: str) -> str | None:
        return self.pids_peak_paths.get(container_id)

    def docker_stats_sampling_available(self) -> bool:
        return self.stats_sampling_available

    def docker_top_sampling_available(self) -> bool:
        return self.top_sampling_available


__all__ = [
    "CollectorMethod",
    "CollectorMethodIdentity",
    "HostCapabilityProbe",
    "FakeHostCapabilityProbe",
    "MetricCollectionDisposition",
    "TerminalCoverageState",
    "SAMPLED_METHODS",
]
