"""MEGB-03H.2C.1: host-side telemetry-collector lifecycle interface, plus
fake implementations for offline testing.

Covers all three collector roles named in the H.2C.1 authorization --
exact cgroup peak-memory collection, a sampled memory fallback, and
sampled process-count collection -- through one shared lifecycle
(``start``/``sample``/``finalize``/``cleanup``): all three are, at this
interface's level, interchangeable strategies that each produce one
:class:`~src.execution.telemetry.TelemetryObservation` for one metric: the
difference between "exact cgroup read" and "sampled docker-stats read" is
which concrete class implements this interface and what quality it
reports, not a different shape.

Real, host-side implementations (reading ``memory.max_usage_in_bytes``/
``memory.peak``, or streaming ``docker stats``) belong to MEGB-03H.2C.2 --
this checkpoint defines the interface and fakes only, per its own
authorization. Every real implementation must, by this interface's own
contract:

* never execute inside the candidate container (host-side only);
* never require ``docker exec``;
* never mount a host telemetry path into the candidate;
* clean up on every terminal outcome (success, timeout, OOM, protocol
  failure, infrastructure failure, or cancellation) -- guaranteed here by
  :func:`run_collector`'s own ``finally`` block, not left to each
  collector's own discipline;
* distinguish genuinely unavailable telemetry (the collector's own
  ``finalize()`` reports an ``unavailable_reason`` with no exception) from
  a collector failure (``start``/``sample``/``finalize`` raised, wrapped
  by :func:`run_collector` into a ``SAMPLER_FAILURE`` observation tagged
  with the failing stage).
"""

import dataclasses
from abc import ABC, abstractmethod
from typing import Callable, Protocol

from src.execution.telemetry import (
    CollectorFailureStage,
    TelemetryObservation,
    collector_failure_observation,
)
from src.execution.telemetry_methods import CollectorMethodIdentity


class TelemetryCollector(ABC):
    """Lifecycle interface for one host-side telemetry collector observing
    exactly one metric for one invocation."""

    @abstractmethod
    def start(self) -> None:
        """Begin observing. Called once, before the candidate invocation starts."""

    @abstractmethod
    def sample(self) -> None:
        """Record one data point. Safe to call zero or more times -- a
        collector that only reads a final high-watermark value at
        ``finalize()`` may treat this as a no-op."""

    @abstractmethod
    def finalize(self) -> TelemetryObservation:
        """Stop observing and return the final observation. Called once,
        after the candidate invocation has terminated."""

    @abstractmethod
    def cleanup(self) -> None:
        """Release any resources this collector acquired. Must be safe to
        call even if ``start``/``sample``/``finalize`` raised."""


def run_collector(
    collector: TelemetryCollector,
    *,
    sample_count: int = 0,
    on_cleanup_failure: Callable[[], None] | None = None,
) -> TelemetryObservation:
    """Run one collector through its full lifecycle, translating any
    exception from ``start``/``sample``/``finalize`` into a
    ``SAMPLER_FAILURE`` :class:`~src.execution.telemetry.TelemetryObservation`
    (tagged with the failing stage) rather than propagating it, and always
    calling ``cleanup()`` exactly once regardless of outcome -- including
    when a ``BaseException`` (e.g. ``KeyboardInterrupt``, modeling
    cancellation) passes through, since ``finally`` runs unconditionally.

    A failing ``cleanup()`` is never allowed to replace or mask whatever
    the primary lifecycle already determined (MEGB-03H.2C.1 conformance-
    audit correction):

    * if the primary lifecycle produced a real observation (success or a
      ``collector_failure``), the returned observation is the *same* one,
      with only ``cleanup_failed=True`` added on top -- ``value``/
      ``quality``/``unavailable_reason``/``collector_failure`` are
      untouched, so a finalize failure and a cleanup failure are both
      visible, neither overwriting the other;
    * if a ``BaseException`` (real cancellation) is propagating instead,
      there is no return value to amend -- ``on_cleanup_failure`` (if
      supplied) is called as a side effect so the failure is still
      observable, and the original exception continues propagating
      completely unchanged (never replaced by the cleanup failure).

    ``on_cleanup_failure`` itself is called from inside a ``finally``
    block, where *any* exception it raises would otherwise replace
    whatever was already propagating (per Python's own ``finally``
    semantics) -- including a genuine ``KeyboardInterrupt``/cancellation
    from ``start``/``sample``/``finalize``. To prevent a broken callback
    from masking real cancellation, its call is itself guarded and any
    exception it raises is discarded unconditionally (MEGB-03H.2C.1
    cleanup-failure-observability correction, round 2).

    ``cleanup_failed`` is a plain, typed boolean, never a raw exception
    message -- this function never inspects, stores, or forwards the
    cleanup exception's own text or type (nor the callback's, if it
    raises).
    """
    observation: TelemetryObservation
    cleanup_failed = False
    try:
        try:
            collector.start()
        except Exception:  # pylint: disable=broad-exception-caught
            observation = collector_failure_observation(CollectorFailureStage.START)
        else:
            try:
                for _ in range(sample_count):
                    collector.sample()
            except Exception:  # pylint: disable=broad-exception-caught
                observation = collector_failure_observation(CollectorFailureStage.SAMPLE)
            else:
                try:
                    observation = collector.finalize()
                except Exception:  # pylint: disable=broad-exception-caught
                    observation = collector_failure_observation(CollectorFailureStage.FINALIZE)
    finally:
        try:
            collector.cleanup()
        except Exception:  # pylint: disable=broad-exception-caught
            cleanup_failed = True
            if on_cleanup_failure is not None:
                try:
                    on_cleanup_failure()
                except BaseException:  # pylint: disable=broad-exception-caught
                    pass

    if cleanup_failed:
        return dataclasses.replace(observation, cleanup_failed=True)
    return observation


# ---------------------------------------------------------------------------
# Split-phase lifecycle helpers (MEGB-03H.2C.2A)
#
# run_collector() above performs a collector's entire start/sample/
# finalize/cleanup lifecycle back-to-back, in one call -- correct for
# offline collector-only testing, but not for a real invocation, where
# sampling (for a sampled collector) must happen *during* the candidate's
# own container execution, not before it. These three functions expose
# the same failure-classification and cleanup-safety invariants as
# run_collector() split into independently callable phases, so a caller
# like DockerPerInvocationBackend.execute_with_telemetry() can call
# start() right after the container is created, run the candidate's own
# execution in between, then call finalize()/cleanup() right before the
# container is removed. run_collector() itself is intentionally left
# unmodified -- this is new, additive surface area, not a refactor of
# already-accepted code.
# ---------------------------------------------------------------------------


def safe_collector_start(
    collector: TelemetryCollector,
    *,
    method_identity: CollectorMethodIdentity | None = None,
) -> TelemetryObservation | None:
    """Call ``collector.start()``, translating any exception into a
    ``START`` failure observation. Returns ``None`` on success -- the
    caller should proceed to do its own work, then call
    :func:`safe_collector_finalize`. Returns the failure observation
    directly if ``start()`` raised; the caller must not call
    :func:`safe_collector_finalize` in that case, but must still call
    :func:`safe_collector_cleanup` (from a ``finally`` block) with this
    return value. ``method_identity``, when supplied, is attached to the
    failure observation so which method's collector failed remains
    visible even when ``start()`` never got far enough to determine it
    itself."""
    try:
        collector.start()
    except Exception:  # pylint: disable=broad-exception-caught
        return collector_failure_observation(
            CollectorFailureStage.START, method_identity=method_identity
        )
    return None


def safe_collector_finalize(
    collector: TelemetryCollector,
    *,
    method_identity: CollectorMethodIdentity | None = None,
) -> TelemetryObservation:
    """Call ``collector.finalize()``, translating any exception into a
    ``FINALIZE`` failure observation. Only call when
    :func:`safe_collector_start` returned ``None`` (start succeeded).
    ``method_identity``, when supplied, is attached to the failure
    observation on the same basis as :func:`safe_collector_start`."""
    try:
        return collector.finalize()
    except Exception:  # pylint: disable=broad-exception-caught
        return collector_failure_observation(
            CollectorFailureStage.FINALIZE, method_identity=method_identity
        )


def safe_collector_cleanup(
    collector: TelemetryCollector,
    observation: TelemetryObservation,
    *,
    on_cleanup_failure: Callable[[], None] | None = None,
) -> TelemetryObservation:
    """Always call ``collector.cleanup()`` exactly once; amend
    ``cleanup_failed`` onto ``observation`` if it raises, without
    altering any other field -- mirroring ``run_collector()``'s own
    cleanup-safety invariant. Must be called from a ``finally`` block by
    the caller so it always runs, including when a ``BaseException`` is
    propagating; ``on_cleanup_failure`` (if supplied) is itself guarded
    so it can never mask a propagating exception (mirroring
    ``run_collector()``'s own protection)."""
    try:
        collector.cleanup()
    except Exception:  # pylint: disable=broad-exception-caught
        if on_cleanup_failure is not None:
            try:
                on_cleanup_failure()
            except BaseException:  # pylint: disable=broad-exception-caught
                pass
        return dataclasses.replace(observation, cleanup_failed=True)
    return observation


class CollectorFactory(Protocol):
    """Structural interface for building one invocation's memory and
    process-count collectors (MEGB-03H.2C.2A), satisfied by
    :class:`~src.execution.real_telemetry_collectors.TelemetryCollectorFactory`
    without this module -- or ``docker_backend.py``, its only intended
    caller -- ever importing ``real_telemetry_collectors`` directly:
    that module itself imports from ``docker_backend.py``
    (``_docker_inspect``/``_docker_server_version``), so a direct import
    the other way would be circular. A ``Protocol`` lets
    ``docker_backend.py`` accept any conforming factory purely
    structurally."""

    def build_memory_collector(
        self, *, container_id: str, container_name: str
    ) -> tuple[TelemetryCollector, CollectorMethodIdentity]:
        """Select and build this invocation's memory collector."""

    def build_process_count_collector(
        self, *, container_id: str, container_name: str
    ) -> tuple[TelemetryCollector, CollectorMethodIdentity]:
        """Select and build this invocation's process-count collector."""


class FakeTelemetryCollector(TelemetryCollector):
    """A fully synthetic, configurable collector for offline tests --
    stands in for any of the three real collector roles (exact cgroup
    peak-memory, sampled memory fallback, sampled process-count). Never
    touches a real container, cgroup, or ``docker stats`` process.

    Each of ``start``/``sample``/``finalize``/``cleanup`` independently
    raises ``RuntimeError`` when its matching ``*_raises`` flag is set,
    letting a test target exactly one lifecycle stage's failure in
    isolation (including combinations, e.g. ``finalize_raises`` together
    with ``cleanup_raises``). ``cleanup_call_count`` (not just a boolean)
    lets a test assert cleanup ran *exactly* once, never more.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        observation: TelemetryObservation | None = None,
        *,
        start_raises: bool = False,
        sample_raises: bool = False,
        finalize_raises: bool = False,
        cleanup_raises: bool = False,
    ) -> None:
        self._observation = observation
        self._start_raises = start_raises
        self._sample_raises = sample_raises
        self._finalize_raises = finalize_raises
        self._cleanup_raises = cleanup_raises
        self.start_called = False
        self.sample_call_count = 0
        self.finalize_called = False
        self.cleanup_call_count = 0

    @property
    def cleanup_called(self) -> bool:
        """Convenience boolean view over ``cleanup_call_count``."""
        return self.cleanup_call_count > 0

    def start(self) -> None:
        self.start_called = True
        if self._start_raises:
            raise RuntimeError("simulated collector start failure")

    def sample(self) -> None:
        self.sample_call_count += 1
        if self._sample_raises:
            raise RuntimeError("simulated collector sample failure")

    def finalize(self) -> TelemetryObservation:
        self.finalize_called = True
        if self._finalize_raises:
            raise RuntimeError("simulated collector finalize failure")
        assert self._observation is not None, "finalize() called without a configured observation"
        return self._observation

    def cleanup(self) -> None:
        self.cleanup_call_count += 1
        if self._cleanup_raises:
            raise RuntimeError("simulated collector cleanup failure")
