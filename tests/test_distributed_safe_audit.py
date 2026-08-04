"""MEGB-03H.2C.3B.2A: construction/validation/round-trip and leakage tests
for :mod:`src.distributed.safe_audit`."""

# pylint: disable=duplicate-code
# The field-allowlist-is-exactly-expected test below intentionally
# mirrors tests/test_distributed_work_contracts.py's own equivalent test
# for QueueWorkMessage (same assertion shape, different field sets) --
# shared boilerplate, not shared logic.

import dataclasses
import inspect

import pytest

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
)
from src.distributed.safe_audit import (
    SafeAuditEvent,
    SafeAuditEventType,
    build_safe_audit_event,
    safe_audit_event_field_names,
    safe_audit_event_to_dict,
)
from src.distributed.state_machine import WorkItemState


def _make_event(**overrides: object) -> SafeAuditEvent:
    fields: dict[str, object] = {
        "event_type": SafeAuditEventType.LEASE_ISSUED,
        "work_reference": "work-0000000000000001",
        "safe_run_identity": "env-logical-0000000000000001",
        "state_after": WorkItemState.LEASED,
        "logical_timestamp": 0,
        "lease_generation": 1,
        "content_checksum": None,
        "input_ordinal": 0,
    }
    fields.update(overrides)
    return build_safe_audit_event(**fields)  # type: ignore[arg-type]


def test_safe_audit_event_constructs_and_computes_checksum() -> None:
    """Test safe audit event constructs and computes checksum."""
    event = _make_event()
    assert len(event.event_checksum) == 64


def test_safe_audit_event_is_immutable() -> None:
    """Test safe audit event is immutable."""
    event = _make_event()
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.work_reference = "changed"  # type: ignore[misc]


def test_safe_audit_event_round_trips() -> None:
    """Test safe audit event round trips."""
    event = _make_event()
    data = safe_audit_event_to_dict(event)
    rebuilt = SafeAuditEvent(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        event_type=SafeAuditEventType(data["event_type"]),
        work_reference=data["work_reference"],
        safe_run_identity=data["safe_run_identity"],
        state_after=WorkItemState(data["state_after"]),
        logical_timestamp=data["logical_timestamp"],
        lease_generation=data["lease_generation"],
        content_checksum=data["content_checksum"],
        input_ordinal=data["input_ordinal"],
        event_checksum=data["event_checksum"],
    )
    assert rebuilt == event


def test_safe_audit_event_rejects_checksum_tampering() -> None:
    """Test safe audit event rejects checksum tampering. Constructed
    directly (not via build_safe_audit_event, which has no
    event_checksum parameter by design) to exercise the auto-compute-or-
    reject check itself."""
    with pytest.raises(InvalidDistributedProvenanceError):
        SafeAuditEvent(
            distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
            checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
            event_type=SafeAuditEventType.LEASE_ISSUED,
            work_reference="work-0000000000000001",
            safe_run_identity="env-logical-0000000000000001",
            state_after=WorkItemState.LEASED,
            logical_timestamp=0,
            lease_generation=1,
            content_checksum=None,
            input_ordinal=0,
            event_checksum="0" * 64,
        )


def test_safe_audit_event_allows_none_lease_generation_content_checksum_ordinal() -> None:
    """Test safe audit event allows none for optional fields not
    applicable to every event type (e.g. WORK_ADMITTED has no lease
    generation yet)."""
    event = _make_event(
        event_type=SafeAuditEventType.WORK_ADMITTED,
        state_after=WorkItemState.PENDING_AVAILABLE,
        lease_generation=None,
        content_checksum=None,
        input_ordinal=None,
    )
    assert event.lease_generation is None
    assert event.content_checksum is None
    assert event.input_ordinal is None


def test_safe_audit_event_rejects_negative_lease_generation() -> None:
    """Test safe audit event rejects negative lease generation."""
    with pytest.raises(InvalidDistributedProvenanceError):
        _make_event(lease_generation=-1)


def test_safe_audit_event_rejects_non_sha256_content_checksum() -> None:
    """Test safe audit event rejects non sha256 content checksum."""
    with pytest.raises(InvalidDistributedProvenanceError):
        _make_event(content_checksum="not-a-checksum")


def test_safe_audit_event_rejects_negative_input_ordinal() -> None:
    """Test safe audit event rejects negative input ordinal."""
    with pytest.raises(InvalidDistributedProvenanceError):
        _make_event(input_ordinal=-1)


def test_safe_audit_event_rejects_empty_work_reference() -> None:
    """Test safe audit event rejects empty work reference."""
    with pytest.raises(InvalidDistributedProvenanceError):
        _make_event(work_reference="")


@pytest.mark.parametrize("event_type", list(SafeAuditEventType))
def test_every_event_type_constructs(event_type: SafeAuditEventType) -> None:
    """Test every declared SafeAuditEventType value constructs a valid
    event."""
    event = _make_event(event_type=event_type)
    assert event.event_type == event_type


# ---------------------------------------------------------------------------
# Leakage: structural absence of forbidden concepts
# ---------------------------------------------------------------------------


def test_safe_audit_event_field_allowlist_excludes_forbidden_concepts() -> None:
    """Test safe audit events structurally exclude raw exception text,
    candidate content, and operational resource names -- no field for
    any of them exists at all."""
    field_names = safe_audit_event_field_names()
    forbidden_substrings = (
        "exception",
        "stdout",
        "stderr",
        "traceback",
        "candidate",
        "credential",
        "password",
        "secret",
        "hostname",
        "instance_id",
        "container_id",
        "project_id",
        "path",
    )
    for name in field_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"field {name!r} matches forbidden {forbidden!r}"


def test_safe_audit_event_field_allowlist_is_exactly_expected() -> None:
    """Test safe audit event field allowlist is exactly expected."""
    expected = {
        "distributed_orchestration_schema_version",
        "checksum_algorithm_version",
        "event_type",
        "work_reference",
        "safe_run_identity",
        "state_after",
        "logical_timestamp",
        "lease_generation",
        "content_checksum",
        "input_ordinal",
        "event_checksum",
    }
    assert safe_audit_event_field_names() == expected


def test_build_safe_audit_event_has_no_free_form_string_parameter() -> None:
    """Test build_safe_audit_event's own parameter list matches the
    type's allowlisted fields exactly -- there is no way to pass a
    free-form diagnostic string through it."""
    signature = inspect.signature(build_safe_audit_event)
    param_names = set(signature.parameters.keys())
    assert param_names == {
        "event_type",
        "work_reference",
        "safe_run_identity",
        "state_after",
        "logical_timestamp",
        "lease_generation",
        "content_checksum",
        "input_ordinal",
    }
