"""MEGB-03H.2C.1: tests for the host-side telemetry-collector lifecycle
(src.execution.telemetry_collectors). Fake collectors only -- no real
cgroup/docker-stats collection, no real container, no Docker.
"""

import pytest

from src.execution.telemetry import (
    CollectorFailureStage,
    TelemetryObservation,
    TelemetryQuality,
    TelemetryUnavailableReason,
)
from src.execution.telemetry_collectors import FakeTelemetryCollector, run_collector


def _exact(value: float) -> TelemetryObservation:
    return TelemetryObservation(
        value=value, quality=TelemetryQuality.EXACT, unavailable_reason=None
    )


def _sampled(value: float) -> TelemetryObservation:
    return TelemetryObservation(
        value=value, quality=TelemetryQuality.SAMPLED_WITH_KNOWN_ERROR, unavailable_reason=None
    )


def _boundary_only(value: float) -> TelemetryObservation:
    return TelemetryObservation(
        value=value, quality=TelemetryQuality.BOUNDARY_ONLY, unavailable_reason=None
    )


def _unavailable() -> TelemetryObservation:
    return TelemetryObservation(
        value=None,
        quality=None,
        unavailable_reason=TelemetryUnavailableReason.HOST_TELEMETRY_UNAVAILABLE,
    )


# ---------------------------------------------------------------------------
# Successful lifecycle, every observation kind
# ---------------------------------------------------------------------------


def test_exact_observation_passes_through_and_cleans_up() -> None:
    """An EXACT observation from finalize() passes through unchanged."""
    collector = FakeTelemetryCollector(observation=_exact(1024))
    result = run_collector(collector)
    assert result.value == 1024
    assert result.quality == TelemetryQuality.EXACT
    assert collector.start_called
    assert collector.finalize_called
    assert collector.cleanup_called


def test_sampled_observation_passes_through_and_cleans_up() -> None:
    """A SAMPLED_WITH_KNOWN_ERROR observation passes through unchanged."""
    collector = FakeTelemetryCollector(observation=_sampled(2048))
    result = run_collector(collector, sample_count=3)
    assert result.value == 2048
    assert result.quality == TelemetryQuality.SAMPLED_WITH_KNOWN_ERROR
    assert collector.sample_call_count == 3
    assert collector.cleanup_called


def test_boundary_only_observation_passes_through_and_cleans_up() -> None:
    """A BOUNDARY_ONLY observation passes through unchanged."""
    collector = FakeTelemetryCollector(observation=_boundary_only(4096))
    result = run_collector(collector)
    assert result.value == 4096
    assert result.quality == TelemetryQuality.BOUNDARY_ONLY
    assert collector.cleanup_called


def test_genuinely_unavailable_observation_is_not_a_collector_failure() -> None:
    """Unavailable (no exception, collector itself reports it) is
    distinct from a collector failure -- collector_failure stays None."""
    collector = FakeTelemetryCollector(observation=_unavailable())
    result = run_collector(collector)
    assert result.value is None
    assert result.unavailable_reason == TelemetryUnavailableReason.HOST_TELEMETRY_UNAVAILABLE
    assert result.collector_failure is None
    assert collector.cleanup_called


# ---------------------------------------------------------------------------
# Collector failure at each lifecycle stage, and cleanup afterward
# ---------------------------------------------------------------------------


def test_start_failure_is_reported_as_sampler_failure_and_still_cleans_up() -> None:
    """start() raising is reported as a SAMPLER_FAILURE at the START stage."""
    collector = FakeTelemetryCollector(start_raises=True)
    result = run_collector(collector)
    assert result.value is None
    assert result.unavailable_reason == TelemetryUnavailableReason.SAMPLER_FAILURE
    assert result.collector_failure == CollectorFailureStage.START
    assert collector.cleanup_called
    # sample()/finalize() never ran after start() raised.
    assert collector.sample_call_count == 0
    assert not collector.finalize_called


def test_sample_failure_is_reported_as_sampler_failure_and_still_cleans_up() -> None:
    """sample() raising is reported as a SAMPLER_FAILURE at the SAMPLE stage."""
    collector = FakeTelemetryCollector(sample_raises=True)
    result = run_collector(collector, sample_count=1)
    assert result.value is None
    assert result.collector_failure == CollectorFailureStage.SAMPLE
    assert collector.start_called
    assert collector.cleanup_called
    assert not collector.finalize_called


def test_finalize_failure_is_reported_as_sampler_failure_and_still_cleans_up() -> None:
    """finalize() raising is reported as a SAMPLER_FAILURE at the FINALIZE stage."""
    collector = FakeTelemetryCollector(finalize_raises=True)
    result = run_collector(collector)
    assert result.value is None
    assert result.collector_failure == CollectorFailureStage.FINALIZE
    assert collector.start_called
    assert collector.finalize_called
    assert collector.cleanup_called


def test_cleanup_runs_exactly_once_regardless_of_which_stage_failed() -> None:
    """cleanup() runs EXACTLY once (not merely at least once), no matter
    which lifecycle stage failed."""
    for collector in (
        FakeTelemetryCollector(start_raises=True),
        FakeTelemetryCollector(sample_raises=True),
        FakeTelemetryCollector(finalize_raises=True),
    ):
        run_collector(collector, sample_count=1)
        assert collector.cleanup_call_count == 1


def test_cleanup_runs_exactly_once_on_success_too() -> None:
    """Same guarantee on the happy path, not just failure paths."""
    collector = FakeTelemetryCollector(observation=_exact(1))
    run_collector(collector)
    assert collector.cleanup_call_count == 1


class _RaisingAt(FakeTelemetryCollector):
    """Simulates cooperative cancellation (KeyboardInterrupt) at a chosen
    lifecycle stage -- a BaseException, not caught by run_collector's own
    `except Exception` blocks, but cleanup must still run via `finally`."""

    def __init__(self, *, stage: str, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._stage = stage

    def start(self) -> None:
        self.start_called = True
        if self._stage == "start":
            raise KeyboardInterrupt("simulated cancellation")

    def sample(self) -> None:
        self.sample_call_count += 1
        if self._stage == "sample":
            raise KeyboardInterrupt("simulated cancellation")

    def finalize(self) -> TelemetryObservation:
        self.finalize_called = True
        if self._stage == "finalize":
            raise KeyboardInterrupt("simulated cancellation")
        return _exact(1)


@pytest.mark.parametrize("stage", ["start", "sample", "finalize"])
def test_cancellation_at_any_stage_still_cleans_up_and_propagates(stage: str) -> None:
    """A KeyboardInterrupt at ANY lifecycle stage (not just finalize) is
    never swallowed -- cancellation must actually cancel -- but cleanup()
    still runs before it propagates."""
    collector = _RaisingAt(stage=stage)
    with pytest.raises(KeyboardInterrupt):
        run_collector(collector, sample_count=1)
    assert collector.cleanup_call_count == 1


# ---------------------------------------------------------------------------
# cleanup() failure behavior: must never mask a result or cancellation
# ---------------------------------------------------------------------------


def test_cleanup_failure_after_successful_finalize_does_not_lose_the_observation() -> None:
    """A cleanup() that raises after a successful finalize() must not
    discard or replace the already-computed observation -- it is
    returned unchanged, with cleanup_failed=True added on top (MEGB-03H.2C.1
    conformance-audit correction: cleanup failure is now observable)."""
    collector = FakeTelemetryCollector(observation=_exact(4096), cleanup_raises=True)
    result = run_collector(collector)
    assert result.value == 4096
    assert result.quality == TelemetryQuality.EXACT
    assert result.cleanup_failed is True
    assert collector.cleanup_call_count == 1


def test_cleanup_failure_after_a_lifecycle_failure_does_not_override_the_classification() -> None:
    """A cleanup() that also raises, on top of a start/sample/finalize
    failure, must not override or replace the original SAMPLER_FAILURE
    classification/stage with an unrelated cleanup error -- both failures
    are visible at once via collector_failure (the original stage) and
    cleanup_failed (additive)."""
    for collector, expected_stage in (
        (
            FakeTelemetryCollector(start_raises=True, cleanup_raises=True),
            CollectorFailureStage.START,
        ),
        (
            FakeTelemetryCollector(sample_raises=True, cleanup_raises=True),
            CollectorFailureStage.SAMPLE,
        ),
        (
            FakeTelemetryCollector(finalize_raises=True, cleanup_raises=True),
            CollectorFailureStage.FINALIZE,
        ),
    ):
        result = run_collector(collector, sample_count=1)
        assert result.value is None
        assert result.unavailable_reason == TelemetryUnavailableReason.SAMPLER_FAILURE
        assert result.collector_failure == expected_stage
        assert result.cleanup_failed is True
        assert collector.cleanup_call_count == 1


def test_cleanup_failure_never_replaces_an_in_flight_cancellation() -> None:
    """cleanup() raising a DIFFERENT exception while a KeyboardInterrupt
    is actively propagating must never mask or replace that
    KeyboardInterrupt -- the real cancellation must still be what
    ultimately propagates, not a misleading cleanup-generated error."""
    collector = _RaisingAt(stage="finalize", cleanup_raises=True)
    with pytest.raises(KeyboardInterrupt):
        run_collector(collector)
    assert collector.cleanup_call_count == 1


def test_cleanup_failure_during_cancellation_is_observable_via_the_callback() -> None:
    """The 5th required combination: KeyboardInterrupt + cleanup failure.
    There is no return value to amend in this path (the function exits
    via the propagating exception), so on_cleanup_failure is the only
    channel that can make the cleanup failure observable -- proven here
    to actually fire, while the original KeyboardInterrupt still
    propagates unaltered."""
    calls: list[None] = []
    collector = _RaisingAt(stage="finalize", cleanup_raises=True)
    with pytest.raises(KeyboardInterrupt):
        run_collector(collector, on_cleanup_failure=lambda: calls.append(None))
    assert len(calls) == 1
    assert collector.cleanup_call_count == 1


def test_on_cleanup_failure_is_not_called_when_cleanup_succeeds() -> None:
    """The callback fires only on an actual cleanup() failure."""
    calls: list[None] = []
    collector = FakeTelemetryCollector(observation=_exact(1))
    run_collector(collector, on_cleanup_failure=lambda: calls.append(None))
    assert not calls
