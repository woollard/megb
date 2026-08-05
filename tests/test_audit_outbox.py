"""MEGB-03H.2C.3B.2B.2: construction/behavior tests for
:mod:`src.distributed.audit_outbox` -- reconciliation-aware, idempotent,
bounded, recoverable audit delivery."""

# pylint: disable=duplicate-code
# This file's own `_event` synthetic-event builder inherently mirrors
# tests/test_audit_sink_store.py's own equivalent helper (both build the
# same allowlisted SafeAuditEvent shape) -- shared boilerplate, not
# shared logic, per this project's own established convention.

import pytest

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
)
from src.distributed.atomic_work_store import AtomicWorkStore
from src.distributed.audit_outbox import AuditOutboxFullError, InMemoryAuditOutbox
from src.distributed.audit_sink_store import InMemoryAuditSink
from src.distributed.safe_audit import SafeAuditEvent, SafeAuditEventType, build_safe_audit_event
from src.distributed.state_machine import WorkItemState
from src.distributed.work_contracts import ExecutionAttempt, ResultCommit
from src.distributed.worker_contracts import Lease
from tests._atomic_stores_fixtures import make_result_commit
from tests._distributed_orchestration_fixtures import make_execution_attempt, make_sha256

_RUN_CTX = make_sha256("audit-outbox-test-run-context")


def _event(work_reference: str = "work-1", **overrides: object) -> SafeAuditEvent:
    fields: dict[str, object] = {
        "event_type": SafeAuditEventType.WORK_ADMITTED,
        "work_reference": work_reference,
        "safe_run_identity": "env-logical-0000000000000001",
        "state_after": WorkItemState.PENDING_AVAILABLE,
        "logical_timestamp": 0,
    }
    fields.update(overrides)
    return build_safe_audit_event(**fields)  # type: ignore[arg-type]


def test_enqueue_is_idempotent_by_outbox_key() -> None:
    """Test enqueue is idempotent by outbox key."""
    outbox = InMemoryAuditOutbox(max_pending=5)
    event = _event()
    first = outbox.enqueue("key-1", event)
    second = outbox.enqueue("key-1", event)
    assert first == second
    assert len(outbox.entries()) == 1


def test_enqueue_refuses_beyond_max_pending() -> None:
    """Test enqueue refuses beyond max_pending -- outbox backpressure."""
    outbox = InMemoryAuditOutbox(max_pending=1)
    outbox.enqueue("key-1", _event("work-1"))
    with pytest.raises(AuditOutboxFullError):
        outbox.enqueue("key-2", _event("work-2"))


def test_dispatch_delivers_an_unconditional_entry() -> None:
    """Test dispatch delivers an unconditional entry (no reconciliation
    clause) immediately."""
    outbox = InMemoryAuditOutbox(max_pending=5)
    sink = InMemoryAuditSink()
    work_store = AtomicWorkStore()
    outbox.enqueue("key-1", _event())
    summary = outbox.dispatch_pending(sink, work_store)
    assert summary.delivered_keys == ("key-1",)
    assert len(sink.events()) == 1
    assert outbox.pending_count() == 0


def test_dispatch_leaves_entry_pending_when_sink_fails() -> None:
    """Test dispatch leaves entry pending when sink fails -- audit
    failure is explicit, never a silent false success."""
    outbox = InMemoryAuditOutbox(max_pending=5)
    sink = InMemoryAuditSink(fail_after=0)
    work_store = AtomicWorkStore()
    outbox.enqueue("key-1", _event())
    summary = outbox.dispatch_pending(sink, work_store)
    assert summary.sink_failed_keys == ("key-1",)
    assert outbox.pending_count() == 1


def test_dispatch_retry_succeeds_once_sink_recovers() -> None:
    """Test a retried dispatch succeeds once the sink recovers, without
    re-affecting authoritative state (dispatch never mutates work_store)."""
    outbox = InMemoryAuditOutbox(max_pending=5)
    sink = InMemoryAuditSink()
    work_store = AtomicWorkStore()
    outbox.enqueue("key-1", _event())
    first = outbox.dispatch_pending(sink, work_store)
    assert first.delivered_keys == ("key-1",)
    second = outbox.dispatch_pending(sink, work_store)
    assert not second.delivered_keys  # already delivered -- idempotent, not re-sent
    assert len(sink.events()) == 1


def test_dispatch_withholds_entry_until_reconciliation_matches() -> None:
    """Test dispatch withholds an entry whose reconciliation clause does
    not yet match the authoritative record -- the write-before-CAS
    pattern this module's own module docstring documents."""
    outbox = InMemoryAuditOutbox(max_pending=5)
    sink = InMemoryAuditSink()
    work_store = AtomicWorkStore()
    outbox.enqueue(
        "key-1",
        _event(),
        reconciliation_scientific_work_id="work-1",
        reconciliation_expected_state=WorkItemState.RESULT_COMMITTED,
    )
    summary = outbox.dispatch_pending(sink, work_store)
    assert summary.still_pending_keys == ("key-1",)
    assert not sink.events()

    work_store.create_if_absent("work-1", _RUN_CTX, "res-1", lambda _rid: True)
    summary_still_pending = outbox.dispatch_pending(sink, work_store)
    assert summary_still_pending.still_pending_keys == ("key-1",)  # still PENDING_AVAILABLE

    lease = _make_lease("work-1")
    work_store.acquire_lease("work-1", 0, lease, reservation_validator=lambda _rid: True)
    work_store.transition_to_executing("work-1", 1)
    attempt, commit = _make_attempt_and_commit("work-1")
    work_store.commit_result("work-1", 2, attempt, commit, artifact_resolver=lambda _ref: True)
    delivered = outbox.dispatch_pending(sink, work_store)
    assert delivered.delivered_keys == ("key-1",)


def _make_lease(work_id: str) -> Lease:
    return Lease(
        distributed_orchestration_schema_version=DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
        checksum_algorithm_version=CHECKSUM_ALGORITHM_VERSION,
        scientific_work_id=work_id,
        worker_participant_id="worker-a",
        lease_generation=1,
        lease_issued_at_logical_clock=0,
        lease_duration_logical_ticks=10,
    )


def _make_attempt_and_commit(work_id: str) -> tuple[ExecutionAttempt, ResultCommit]:
    attempt = make_execution_attempt(
        scientific_work_id=work_id,
        worker_participant_id="worker-a",
        lease_generation=1,
        distributed_run_context_checksum=_RUN_CTX,
    )
    content = b"synthetic-outbox-test-content"
    commit = make_result_commit(attempt, content)
    return attempt, commit


def test_dispatch_never_delivers_an_orphaned_intent_for_a_lost_cas() -> None:
    """Test that an outbox intent written before a CAS that ultimately
    loses (a revision conflict) remains permanently pending -- harmless,
    never delivered, exactly mirroring an orphaned unreferenced result
    artifact."""
    outbox = InMemoryAuditOutbox(max_pending=5)
    sink = InMemoryAuditSink()
    work_store = AtomicWorkStore()
    work_store.create_if_absent("work-1", "9" * 64, "res-1", lambda _rid: True)
    outbox.enqueue(
        "key-1",
        _event(),
        reconciliation_scientific_work_id="work-1",
        reconciliation_expected_result_content_checksum="a" * 64,
    )
    summary = outbox.dispatch_pending(sink, work_store)
    assert summary.still_pending_keys == ("key-1",)
    assert not sink.events()
