"""MEGB-03H.2C.3B.2A: the safe, allowlisted audit-event projection for the
distributed-orchestration contracts.

Mirrors :mod:`~src.distributed.safe_summary`'s own established discipline:
:class:`SafeAuditEvent` is structurally incapable of carrying a raw
exception message, candidate content, privileged evidence, or an
operational resource name -- there is simply no field for any of them.
:func:`build_safe_audit_event` is the one, explicit redaction/construction
boundary a future coordinator (MEGB-03H.2C.3B.2B) must call to emit an
event; because its parameter list matches this type's own allowlisted
fields exactly, there is no way to pass it a free-form string that ends up
on a committed/logged audit trail.

This module deliberately never imports
:mod:`~src.distributed.protected_mapping` -- there is no code path from a
raw operational identifier into a :class:`SafeAuditEvent`, the same
structural-absence guarantee :mod:`~src.distributed.safe_summary` already
establishes.
"""

import dataclasses
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
    require_checksum_algorithm_version as _require_checksum_algorithm_version,
    require_non_negative_int as _require_non_negative_int,
    require_nonempty_str as _require_nonempty_str,
    require_orchestration_schema_version as _require_orchestration_schema_version,
    require_sha256_hex as _require_sha256_hex,
    sha256_of as _sha256_of,
)
from src.distributed.state_machine import WorkItemState


class SafeAuditEventType(str, Enum):
    """Closed set of safe, loggable orchestration event types -- never a
    free-form event name."""

    WORK_ADMITTED = "WORK_ADMITTED"
    WORK_ADMISSION_REFUSED = "WORK_ADMISSION_REFUSED"
    LEASE_ISSUED = "LEASE_ISSUED"
    LEASE_RENEWED = "LEASE_RENEWED"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    RESULT_COMMITTED = "RESULT_COMMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    CANCELLED = "CANCELLED"
    DEAD_LETTERED = "DEAD_LETTERED"


@dataclass(frozen=True)
class SafeAuditEvent:  # pylint: disable=too-many-instance-attributes
    """Allowlisted, safe-to-log projection of one orchestration
    transition. Every field is either a closed-enum value, an opaque
    logical reference, a non-negative counter, a content checksum, or a
    logical (never wall-clock) timestamp -- never a raw exception
    message, candidate content, or operational resource name."""

    distributed_orchestration_schema_version: str
    checksum_algorithm_version: str
    event_type: SafeAuditEventType
    work_reference: str
    safe_run_identity: str
    state_after: WorkItemState
    logical_timestamp: int
    lease_generation: int | None
    content_checksum: str | None
    input_ordinal: int | None
    event_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _require_orchestration_schema_version(self)
        _require_checksum_algorithm_version(self)
        if not isinstance(self.event_type, SafeAuditEventType):
            raise InvalidDistributedProvenanceError(
                f"event_type must be a SafeAuditEventType, got {self.event_type!r}"
            )
        _require_nonempty_str(self, "work_reference")
        _require_nonempty_str(self, "safe_run_identity")
        if not isinstance(self.state_after, WorkItemState):
            raise InvalidDistributedProvenanceError(
                f"state_after must be a WorkItemState, got {self.state_after!r}"
            )
        _require_non_negative_int(self, "logical_timestamp")
        if self.lease_generation is not None:
            if (
                not isinstance(self.lease_generation, int)
                or isinstance(self.lease_generation, bool)
                or self.lease_generation < 0
            ):
                raise InvalidDistributedProvenanceError(
                    f"lease_generation must be a non-negative int or None, got "
                    f"{self.lease_generation!r}"
                )
        if self.content_checksum is not None:
            _require_sha256_hex(self, "content_checksum")
        if self.input_ordinal is not None:
            if (
                not isinstance(self.input_ordinal, int)
                or isinstance(self.input_ordinal, bool)
                or self.input_ordinal < 0
            ):
                raise InvalidDistributedProvenanceError(
                    f"input_ordinal must be a non-negative int or None, got "
                    f"{self.input_ordinal!r}"
                )

        payload = _safe_audit_event_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.event_checksum and self.event_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"event_checksum {self.event_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted safe audit event"
            )
        object.__setattr__(self, "event_checksum", expected_checksum)


def _safe_audit_event_payload(event: SafeAuditEvent) -> dict[str, Any]:
    return {
        "distributed_orchestration_schema_version": (
            event.distributed_orchestration_schema_version
        ),
        "checksum_algorithm_version": event.checksum_algorithm_version,
        "event_type": event.event_type.value,
        "work_reference": event.work_reference,
        "safe_run_identity": event.safe_run_identity,
        "state_after": event.state_after.value,
        "logical_timestamp": event.logical_timestamp,
        "lease_generation": event.lease_generation,
        "content_checksum": event.content_checksum,
        "input_ordinal": event.input_ordinal,
    }


def safe_audit_event_to_dict(event: SafeAuditEvent) -> dict[str, Any]:
    """Full-fidelity serialization of a :class:`SafeAuditEvent`."""
    return {**_safe_audit_event_payload(event), "event_checksum": event.event_checksum}


def build_safe_audit_event(  # pylint: disable=too-many-arguments
    *,
    event_type: SafeAuditEventType,
    work_reference: str,
    safe_run_identity: str,
    state_after: WorkItemState,
    logical_timestamp: int,
    lease_generation: int | None = None,
    content_checksum: str | None = None,
    input_ordinal: int | None = None,
) -> SafeAuditEvent:
    """The one explicit redaction/construction boundary a caller uses to
    emit a :class:`SafeAuditEvent` -- its parameter list is exactly this
    type's own allowlisted fields, so there is no way to pass a free-form
    string (an exception message, candidate content, a raw resource name)
    through it onto a logged audit trail."""
    return SafeAuditEvent(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        event_type=event_type,
        work_reference=work_reference,
        safe_run_identity=safe_run_identity,
        state_after=state_after,
        logical_timestamp=logical_timestamp,
        lease_generation=lease_generation,
        content_checksum=content_checksum,
        input_ordinal=input_ordinal,
    )


def safe_audit_event_field_names() -> frozenset[str]:
    """The exact set of field names :class:`SafeAuditEvent` declares --
    used by leakage tests to structurally assert that no excluded
    concept (raw exception text, candidate content, operational resource
    names) is present, mirroring
    :func:`~src.distributed.safe_summary.safe_summary_field_names`'s own
    established pattern."""
    return frozenset(field.name for field in dataclasses.fields(SafeAuditEvent))


__all__ = [
    "SafeAuditEventType",
    "SafeAuditEvent",
    "safe_audit_event_to_dict",
    "build_safe_audit_event",
    "safe_audit_event_field_names",
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION",
]
