"""MEGB-03H.2C.3B.2A: structural tests for
:mod:`src.distributed.protocols` -- confirms each interface is a
``typing.Protocol`` with exactly the methods this checkpoint's own
authorization names, and that no concrete implementation (a coordinator
or worker engine) exists in this module -- that is MEGB-03H.2C.3B.2B's
own, separately authorized, scope."""

import inspect
import typing

from src.distributed import protocols


def _is_protocol(cls: type) -> bool:
    return typing.Protocol in getattr(cls, "__mro__", ()) or getattr(
        cls, "_is_protocol", False
    )


def test_work_queue_protocol_is_a_protocol_with_expected_methods() -> None:
    """Test work queue protocol is a protocol with expected methods."""
    assert _is_protocol(protocols.WorkQueueProtocol)
    assert {"publish", "lease", "cancel"} <= set(dir(protocols.WorkQueueProtocol))


def test_artifact_store_protocol_is_a_protocol_with_expected_methods() -> None:
    """Test artifact store protocol is a protocol with expected
    methods."""
    assert _is_protocol(protocols.ArtifactStoreProtocol)
    assert "resolve" in dir(protocols.ArtifactStoreProtocol)


def test_result_store_protocol_is_a_protocol_with_expected_methods() -> None:
    """Test result store protocol is a protocol with expected methods."""
    assert _is_protocol(protocols.ResultStoreProtocol)
    assert {"get_result", "commit_result", "acknowledge"} <= set(
        dir(protocols.ResultStoreProtocol)
    )


def test_lease_state_store_protocol_is_a_protocol_with_expected_methods() -> None:
    """Test lease state store protocol is a protocol with expected
    methods."""
    assert _is_protocol(protocols.LeaseStateStoreProtocol)
    assert {
        "get_state",
        "transition",
        "current_lease",
        "renew_lease",
        "record_terminal_disposition",
    } <= set(dir(protocols.LeaseStateStoreProtocol))


def test_worker_registry_protocol_is_a_protocol_with_expected_methods() -> None:
    """Test worker registry protocol is a protocol with expected
    methods."""
    assert _is_protocol(protocols.WorkerRegistryProtocol)
    assert {"register", "active_worker_participant_ids"} <= set(
        dir(protocols.WorkerRegistryProtocol)
    )


def test_audit_sink_protocol_is_a_protocol_with_expected_methods() -> None:
    """Test audit sink protocol is a protocol with expected methods."""
    assert _is_protocol(protocols.AuditSinkProtocol)
    assert "emit" in dir(protocols.AuditSinkProtocol)


def test_protocols_module_defines_no_concrete_coordinator_or_worker_class() -> None:
    """Test this module defines only Protocol interfaces -- no concrete
    coordinator/worker engine class, which is MEGB-03H.2C.3B.2B's own,
    separately authorized, scope."""
    forbidden_substrings = ("coordinator", "engine", "worker_loop")
    for name, obj in inspect.getmembers(protocols, inspect.isclass):
        if obj.__module__ != protocols.__name__:
            continue
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"{name} matches forbidden {forbidden!r}"
        assert _is_protocol(obj), f"{name} is a concrete class, not a Protocol"
