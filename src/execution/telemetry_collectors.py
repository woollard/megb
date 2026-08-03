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
from typing import Callable

from src.execution.telemetry import (
    CollectorFailureStage,
    TelemetryObservation,
    collector_failure_observation,
)


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

    ``cleanup_failed`` is a plain, typed boolean, never a raw exception
    message -- this function never inspects, stores, or forwards the
    cleanup exception's own text or type.
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
                on_cleanup_failure()

    if cleanup_failed:
        return dataclasses.replace(observation, cleanup_failed=True)
    return observation


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
