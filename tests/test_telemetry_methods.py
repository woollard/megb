"""MEGB-03H.2C.2A: tests for the execution-layer collector-method/
capability provenance model (src.execution.telemetry_methods). Synthetic
fakes only -- no real host, cgroup filesystem, or Docker CLI.
"""

import pytest

from src.execution.telemetry_methods import (
    CollectorMethod,
    CollectorMethodIdentity,
    FakeHostCapabilityProbe,
    MetricCollectionDisposition,
)


def _identity(**overrides: object) -> CollectorMethodIdentity:
    defaults: dict[str, object] = {
        "method": CollectorMethod.CGROUP_V2_MEMORY_PEAK,
        "method_version": "cgroup_v2_memory_peak/v1",
        "interface": "cgroupfs:memory.peak",
        "sampling_interval_sec": None,
        "selection_disposition": MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
    }
    defaults.update(overrides)
    return CollectorMethodIdentity(**defaults)  # type: ignore[arg-type]


def test_every_collector_method_is_a_closed_typed_set() -> None:
    """Exactly the five methods this checkpoint defines -- no ad hoc
    strings ever substitute for a member."""
    assert {member.value for member in CollectorMethod} == {
        "CGROUP_V2_MEMORY_PEAK",
        "CGROUP_V2_PIDS_PEAK",
        "SAMPLED_DOCKER_STATS_MEMORY",
        "SAMPLED_DOCKER_TOP_PROCESS_COUNT",
        "UNAVAILABLE_WITHOUT_CONTAMINATION",
    }


def test_identity_requires_a_collector_method_enum_member() -> None:
    """method must be a real CollectorMethod, never a raw string."""
    _identity()  # does not raise
    with pytest.raises(ValueError):
        CollectorMethodIdentity(
            method="CGROUP_V2_MEMORY_PEAK",  # type: ignore[arg-type]
            method_version="v1",
            interface="x",
            sampling_interval_sec=None,
            selection_disposition=MetricCollectionDisposition.PRIMARY_METHOD_SELECTED,
        )


def test_identity_requires_nonempty_method_version_and_interface() -> None:
    """Both are load-bearing reproducibility fields -- never empty."""
    with pytest.raises(ValueError):
        _identity(method_version="")
    with pytest.raises(ValueError):
        _identity(interface="")


def test_identity_sampling_interval_must_be_none_or_positive() -> None:
    """None means 'not sampled' (an exact read); a sampled method must
    carry a real positive interval, never zero or negative."""
    _identity(
        method=CollectorMethod.SAMPLED_DOCKER_STATS_MEMORY,
        method_version="sampled_docker_stats_memory/v1",
        interface="docker stats --no-stream",
        sampling_interval_sec=0.5,
    )  # does not raise
    with pytest.raises(ValueError):
        _identity(sampling_interval_sec=0.0)
    with pytest.raises(ValueError):
        _identity(sampling_interval_sec=-1.0)
    with pytest.raises(ValueError):
        _identity(sampling_interval_sec=True)  # bool is not a valid interval


def test_identity_host_runtime_metadata_defaults_to_an_empty_tuple() -> None:
    """No metadata supplied -- an empty, immutable tuple, never None/dict."""
    identity = _identity()
    assert not identity.host_runtime_metadata
    assert isinstance(identity.host_runtime_metadata, tuple)


def test_identity_host_runtime_metadata_must_be_pairs() -> None:
    """Each entry must be a genuine (key, value) pair."""
    _identity(host_runtime_metadata=(("kernel", "6.8.0"), ("cgroup_driver", "systemd")))
    with pytest.raises(ValueError):
        _identity(host_runtime_metadata=[("kernel", "6.8.0")])
    with pytest.raises(ValueError):
        _identity(host_runtime_metadata=(("kernel", "6.8.0", "extra"),))


def test_fake_capability_probe_returns_configured_paths_or_none() -> None:
    """The fake probe never touches a real filesystem -- purely a
    configurable lookup, defaulting to unavailable for unknown ids."""
    probe = FakeHostCapabilityProbe(
        host_metadata=(("kernel", "6.8.0"),),
        memory_peak_paths={"abc123": "/sys/fs/cgroup/.../memory.peak"},
        pids_peak_paths={},
        stats_sampling_available=True,
        top_sampling_available=False,
    )
    assert probe.host_runtime_metadata() == (("kernel", "6.8.0"),)
    assert probe.cgroup_v2_memory_peak_path("abc123") == "/sys/fs/cgroup/.../memory.peak"
    assert probe.cgroup_v2_memory_peak_path("unknown") is None
    assert probe.cgroup_v2_pids_peak_path("abc123") is None
    assert probe.docker_stats_sampling_available() is True
    assert probe.docker_top_sampling_available() is False


def test_fake_capability_probe_defaults_to_no_capability_and_no_metadata() -> None:
    """A bare FakeHostCapabilityProbe() reports no resolvable cgroup
    paths and empty metadata -- capability must be explicitly configured
    to be present, never assumed."""
    probe = FakeHostCapabilityProbe()
    assert not probe.host_runtime_metadata()
    assert probe.cgroup_v2_memory_peak_path("any") is None
    assert probe.cgroup_v2_pids_peak_path("any") is None
    # Sampling fallbacks default to available (a conservative choice
    # documented on the dataclass field itself), unlike cgroup paths
    # which default to unresolved per-container.
    assert probe.docker_stats_sampling_available() is True
    assert probe.docker_top_sampling_available() is True
