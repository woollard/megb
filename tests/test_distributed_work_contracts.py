"""MEGB-03H.2C.3B.2A: construction/validation/immutability/round-trip,
identity-separation, reconciliation, and queue-payload-allowlist tests
for :mod:`src.distributed.work_contracts`."""

# pylint: disable=duplicate-code
# ExecutionAttempt's round-trip test intentionally mirrors
# tests/test_distributed_worker_contracts.py's own Lease round-trip test
# (both rebuild an object sharing the same leading field names) -- shared
# boilerplate, not shared logic.

import dataclasses

import pytest

from src.distributed._checksums import (
    DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
    UnsupportedDistributedOrchestrationSchemaVersionError,
)
from src.distributed.work_contracts import (
    Acknowledgement,
    ArtifactKind,
    ArtifactReference,
    CancellationRequest,
    CancellationScope,
    ConflictingResultCommitError,
    ExecutionAttempt,
    QueueWorkMessage,
    ResultCommit,
    ResultCommitReconciliation,
    TerminalDisposition,
    TerminalDispositionKind,
    TerminalDispositionReason,
    WorkDescriptor,
    acknowledgement_to_dict,
    artifact_reference_to_dict,
    cancellation_request_to_dict,
    execution_attempt_to_dict,
    queue_work_message_field_names,
    queue_work_message_to_dict,
    reconcile_result_commit,
    require_commit_before_ack,
    result_commit_to_dict,
    terminal_disposition_to_dict,
    work_descriptor_to_dict,
    work_descriptor_to_queue_message,
)
from tests._distributed_orchestration_fixtures import (
    make_acknowledgement,
    make_candidate_artifact_reference,
    make_cancellation_request,
    make_execution_attempt,
    make_queue_work_message,
    make_result_artifact_reference,
    make_result_commit,
    make_run_context_checksum,
    make_terminal_disposition,
    make_work_descriptor,
)


# ---------------------------------------------------------------------------
# ArtifactReference
# ---------------------------------------------------------------------------


def test_artifact_reference_constructs_and_computes_checksum() -> None:
    """Test artifact reference constructs and computes checksum."""
    reference = make_candidate_artifact_reference()
    assert len(reference.reference_checksum) == 64


def test_artifact_reference_is_immutable() -> None:
    """Test artifact reference is immutable."""
    reference = make_candidate_artifact_reference()
    with pytest.raises(dataclasses.FrozenInstanceError):
        reference.artifact_reference_id = "changed"  # type: ignore[misc]


def test_artifact_reference_round_trips() -> None:
    """Test artifact reference round trips through to_dict/from_dict."""
    reference = make_candidate_artifact_reference()
    data = artifact_reference_to_dict(reference)
    rebuilt = ArtifactReference(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        artifact_kind=ArtifactKind(data["artifact_kind"]),
        artifact_reference_id=data["artifact_reference_id"],
        content_checksum=data["content_checksum"],
        metadata_checksum=data["metadata_checksum"],
        reference_checksum=data["reference_checksum"],
    )
    assert rebuilt == reference


def test_artifact_reference_rejects_checksum_tampering() -> None:
    """Test artifact reference rejects checksum tampering."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_candidate_artifact_reference(reference_checksum="0" * 64)


def test_artifact_reference_rejects_unsupported_schema_version() -> None:
    """Test artifact reference rejects unsupported schema version."""
    with pytest.raises(UnsupportedDistributedOrchestrationSchemaVersionError):
        make_candidate_artifact_reference(
            distributed_orchestration_schema_version="stale-version"
        )


def test_artifact_reference_rejects_non_sha256_checksum() -> None:
    """Test artifact reference rejects non sha256 checksum."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_candidate_artifact_reference(content_checksum="not-a-checksum")


def test_artifact_reference_rejects_empty_reference_id() -> None:
    """Test artifact reference rejects empty reference id."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_candidate_artifact_reference(artifact_reference_id="")


def test_artifact_reference_rejects_the_stale_v1_schema_version_literal() -> None:
    """Test artifact reference rejects the stale
    MEGB-03H.2C.3B.2A v1 schema-version literal -- MEGB-03H.2C.3B.2B.1's
    correction bumped DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION v1->v2
    because ArtifactReference's own field shape changed
    (``artifact_checksum`` split into ``content_checksum``/
    ``metadata_checksum``); a payload still stamped with the exact prior
    v1 string must be rejected, never silently reinterpreted under v2."""
    with pytest.raises(UnsupportedDistributedOrchestrationSchemaVersionError):
        make_candidate_artifact_reference(
            distributed_orchestration_schema_version="megb-03h2c3b2a-distributed-orchestration-v1"
        )


def test_artifact_reference_round_trips_with_current_schema_version() -> None:
    """Test artifact reference round-trips cleanly under the current
    schema version -- the companion positive case to the stale-v1
    rejection test above. ``ArtifactReference``'s own shape has not
    changed since the v1->v2 bump; it is stamped with the current (v3)
    version purely because the shared schema-family constant advanced
    again for MEGB-03H.2C.3B.2B.2's own correction (see
    ``tests.test_result_commit_v3_round_trips_with_current_schema_version``
    for the type whose shape actually changed this round)."""
    reference = make_candidate_artifact_reference()
    assert reference.distributed_orchestration_schema_version == (
        DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION
    )
    assert DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION.endswith("-v3")
    data = artifact_reference_to_dict(reference)
    rebuilt = ArtifactReference(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        artifact_kind=ArtifactKind(data["artifact_kind"]),
        artifact_reference_id=data["artifact_reference_id"],
        content_checksum=data["content_checksum"],
        metadata_checksum=data["metadata_checksum"],
        reference_checksum=data["reference_checksum"],
    )
    assert rebuilt == reference


def test_artifact_reference_kind_changes_checksum() -> None:
    """Test artifact_kind is part of the checksummed identity -- an
    opaque reference cannot be silently reinterpreted as a different
    kind of artifact."""
    candidate = make_candidate_artifact_reference()
    result = make_result_artifact_reference(
        artifact_reference_id=candidate.artifact_reference_id,
        content_checksum=candidate.content_checksum,
        metadata_checksum=candidate.metadata_checksum,
    )
    assert candidate.reference_checksum != result.reference_checksum


# ---------------------------------------------------------------------------
# WorkDescriptor
# ---------------------------------------------------------------------------


def test_work_descriptor_constructs_and_computes_checksum() -> None:
    """Test work descriptor constructs and computes checksum."""
    descriptor = make_work_descriptor()
    assert len(descriptor.work_descriptor_checksum) == 64


def test_work_descriptor_is_immutable() -> None:
    """Test work descriptor is immutable."""
    descriptor = make_work_descriptor()
    with pytest.raises(dataclasses.FrozenInstanceError):
        descriptor.scientific_work_id = "changed"  # type: ignore[misc]


def test_work_descriptor_round_trips() -> None:
    """Test work descriptor round trips."""
    descriptor = make_work_descriptor()
    data = work_descriptor_to_dict(descriptor)
    rebuilt = WorkDescriptor(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        scientific_work_id=data["scientific_work_id"],
        input_ordinal=data["input_ordinal"],
        distributed_run_context_checksum=data["distributed_run_context_checksum"],
        candidate_artifact_reference=ArtifactReference(
            **{**data["candidate_artifact_reference"], "artifact_kind": ArtifactKind(
                data["candidate_artifact_reference"]["artifact_kind"]
            )}
        ),
        work_descriptor_checksum=data["work_descriptor_checksum"],
    )
    assert rebuilt == descriptor


def test_work_descriptor_rejects_negative_input_ordinal() -> None:
    """Test work descriptor rejects negative input ordinal."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_work_descriptor(input_ordinal=-1)


def test_work_descriptor_rejects_non_artifact_reference() -> None:
    """Test work descriptor rejects non artifact reference for its
    candidate reference field."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_work_descriptor(candidate_artifact_reference="not-a-reference")


def test_work_descriptor_input_ordinal_changes_checksum() -> None:
    """Test deterministic ordering: distinct input_ordinal values
    produce distinct work_descriptor_checksum values."""
    first = make_work_descriptor(input_ordinal=0)
    second = make_work_descriptor(input_ordinal=1)
    assert first.work_descriptor_checksum != second.work_descriptor_checksum


def test_work_descriptor_never_carries_candidate_source() -> None:
    """Test WorkDescriptor structurally has no field for candidate
    source/prompt/canonical-solution content -- only an opaque
    ArtifactReference."""
    field_names = {field.name for field in dataclasses.fields(WorkDescriptor)}
    forbidden = {"candidate_source", "prompt", "canonical_solution", "expected_output"}
    assert not field_names & forbidden


# ---------------------------------------------------------------------------
# QueueWorkMessage -- queue-payload allowlist
# ---------------------------------------------------------------------------


def test_queue_work_message_constructs_from_descriptor() -> None:
    """Test queue work message constructs from descriptor."""
    message = make_queue_work_message()
    assert len(message.message_checksum) == 64
    assert message.lease_generation is None
    assert message.attempt_checksum is None


def test_queue_work_message_is_immutable() -> None:
    """Test queue work message is immutable."""
    message = make_queue_work_message()
    with pytest.raises(dataclasses.FrozenInstanceError):
        message.delivery_id = "changed"  # type: ignore[misc]


def test_queue_work_message_round_trips() -> None:
    """Test queue work message round trips."""
    message = make_queue_work_message()
    data = queue_work_message_to_dict(message)
    rebuilt = QueueWorkMessage(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        scientific_work_id=data["scientific_work_id"],
        delivery_id=data["delivery_id"],
        input_ordinal=data["input_ordinal"],
        distributed_run_context_checksum=data["distributed_run_context_checksum"],
        candidate_artifact_reference=ArtifactReference(
            **{
                **data["candidate_artifact_reference"],
                "artifact_kind": ArtifactKind(
                    data["candidate_artifact_reference"]["artifact_kind"]
                ),
            }
        ),
        lease_generation=data["lease_generation"],
        attempt_checksum=data["attempt_checksum"],
        routing_environment_class=data["routing_environment_class"],
        routing_logical_environment_id=data["routing_logical_environment_id"],
        message_checksum=data["message_checksum"],
    )
    assert rebuilt == message


def test_queue_work_message_delivery_id_is_distinct_queue_delivery_identity() -> None:
    """Test that re-delivery (a new delivery_id) does not change
    scientific_work_id -- the queue delivery identity and scientific work
    identity are separate concepts."""
    first_delivery = make_queue_work_message(delivery_id="delivery-0001")
    redelivery = make_queue_work_message(delivery_id="delivery-0002")
    assert first_delivery.scientific_work_id == redelivery.scientific_work_id
    assert first_delivery.delivery_id != redelivery.delivery_id
    assert first_delivery.message_checksum != redelivery.message_checksum


def test_queue_work_message_rejects_zero_lease_generation() -> None:
    """Test queue work message rejects zero lease generation (lease
    generations are always positive, coordinator-issued)."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_queue_work_message(lease_generation=0)


def test_queue_work_message_rejects_non_sha256_attempt_checksum() -> None:
    """Test queue work message rejects non sha256 attempt checksum."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_queue_work_message(attempt_checksum="not-a-checksum")


def test_queue_work_message_field_allowlist_excludes_forbidden_concepts() -> None:
    """Test the queue-visible message type structurally excludes every
    forbidden concept named by the authorization: candidate source,
    prompts, canonical solutions, expected outputs, reference cases,
    privileged diagnostics, credentials, raw infrastructure identifiers,
    unrestricted exception text."""
    field_names = queue_work_message_field_names()
    forbidden_substrings = (
        "candidate_source",
        "prompt",
        "canonical_solution",
        "expected_output",
        "reference_case",
        "privileged",
        "credential",
        "password",
        "secret",
        "token",
        "project_id",
        "hostname",
        "instance_id",
        "container_id",
        "path",
        "exception",
        "stdout",
        "stderr",
        "traceback",
    )
    for name in field_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"field {name!r} matches forbidden {forbidden!r}"


def test_queue_work_message_field_allowlist_is_exactly_expected() -> None:
    """Test the queue message's field set is exactly the allowlisted
    fields this checkpoint's authorization names -- opaque references,
    checksums, schema/version identifiers, input ordinal, run/provenance
    checksums, lease/attempt info, and routing metadata."""
    expected = {
        "distributed_orchestration_schema_version",
        "checksum_algorithm_version",
        "scientific_work_id",
        "delivery_id",
        "input_ordinal",
        "distributed_run_context_checksum",
        "candidate_artifact_reference",
        "lease_generation",
        "attempt_checksum",
        "routing_environment_class",
        "routing_logical_environment_id",
        "message_checksum",
    }
    assert queue_work_message_field_names() == expected


def test_work_descriptor_to_queue_message_is_the_only_projection_path() -> None:
    """Test the sanctioned WorkDescriptor -> QueueWorkMessage projection
    carries the descriptor's own scientific_work_id/input_ordinal/run
    checksum/artifact reference through unchanged."""
    descriptor = make_work_descriptor()
    message = work_descriptor_to_queue_message(
        descriptor,
        delivery_id="delivery-x",
        routing_environment_class="PERSONAL_BOOTSTRAP",
        routing_logical_environment_id="env-x",
    )
    assert message.scientific_work_id == descriptor.scientific_work_id
    assert message.input_ordinal == descriptor.input_ordinal
    assert message.distributed_run_context_checksum == descriptor.distributed_run_context_checksum
    assert message.candidate_artifact_reference == descriptor.candidate_artifact_reference


# ---------------------------------------------------------------------------
# CancellationRequest
# ---------------------------------------------------------------------------


def test_cancellation_request_constructs_and_computes_checksum() -> None:
    """Test cancellation request constructs and computes checksum."""
    request = make_cancellation_request()
    assert len(request.cancellation_checksum) == 64


def test_cancellation_request_round_trips() -> None:
    """Test cancellation request round trips."""
    request = make_cancellation_request()
    data = cancellation_request_to_dict(request)
    rebuilt = CancellationRequest(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        scientific_work_id=data["scientific_work_id"],
        cancellation_scope=CancellationScope(data["cancellation_scope"]),
        requested_at_logical_clock=data["requested_at_logical_clock"],
        cancellation_checksum=data["cancellation_checksum"],
    )
    assert rebuilt == request


def test_cancellation_before_admission_and_after_lease_are_distinguishable() -> None:
    """Test cancellation before admission and after lease are
    distinguishable via cancellation_scope, and each produces a
    different checksum."""
    before = make_cancellation_request(cancellation_scope=CancellationScope.BEFORE_ADMISSION)
    after = make_cancellation_request(cancellation_scope=CancellationScope.AFTER_LEASE)
    assert before.cancellation_scope != after.cancellation_scope
    assert before.cancellation_checksum != after.cancellation_checksum


def test_cancellation_request_rejects_negative_logical_clock() -> None:
    """Test cancellation request rejects negative logical clock."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_cancellation_request(requested_at_logical_clock=-1)


# ---------------------------------------------------------------------------
# ExecutionAttempt -- retry/scientific-identity separation
# ---------------------------------------------------------------------------


def test_execution_attempt_constructs_and_computes_checksum() -> None:
    """Test execution attempt constructs and computes checksum."""
    attempt = make_execution_attempt()
    assert len(attempt.attempt_checksum) == 64


def test_execution_attempt_round_trips() -> None:
    """Test execution attempt round trips."""
    attempt = make_execution_attempt()
    data = execution_attempt_to_dict(attempt)
    rebuilt = ExecutionAttempt(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        scientific_work_id=data["scientific_work_id"],
        worker_participant_id=data["worker_participant_id"],
        lease_generation=data["lease_generation"],
        distributed_run_context_checksum=data["distributed_run_context_checksum"],
        attempt_checksum=data["attempt_checksum"],
    )
    assert rebuilt == attempt


def test_execution_attempt_rejects_non_positive_lease_generation() -> None:
    """Test execution attempt rejects non positive lease generation."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_execution_attempt(lease_generation=0)


def test_retry_produces_distinct_attempt_identity_same_scientific_work_id() -> None:
    """Test retries have distinct attempt identities without changing
    scientific work identity -- a new lease_generation (a retry) changes
    attempt_checksum while scientific_work_id stays fixed."""
    first_attempt = make_execution_attempt(lease_generation=1)
    retry_attempt = make_execution_attempt(lease_generation=2)
    assert first_attempt.scientific_work_id == retry_attempt.scientific_work_id
    assert first_attempt.attempt_checksum != retry_attempt.attempt_checksum


def test_different_worker_same_generation_is_a_different_attempt() -> None:
    """Test a different worker under the same lease_generation number
    (which should not happen operationally, but the type itself must
    still distinguish it) produces a different attempt identity."""
    attempt_a = make_execution_attempt(worker_participant_id="worker-a")
    attempt_b = make_execution_attempt(worker_participant_id="worker-b")
    assert attempt_a.attempt_checksum != attempt_b.attempt_checksum


def test_execution_attempt_rejects_mismatched_run_context() -> None:
    """Test an attempt bound to one run's checksum cannot be silently
    reinterpreted under a different run -- the checksum itself changes."""
    attempt_run_a = make_execution_attempt(
        distributed_run_context_checksum=make_run_context_checksum("run-a")
    )
    attempt_run_b = make_execution_attempt(
        distributed_run_context_checksum=make_run_context_checksum("run-b")
    )
    assert attempt_run_a.attempt_checksum != attempt_run_b.attempt_checksum


# ---------------------------------------------------------------------------
# ResultCommit / reconciliation -- idempotent vs. conflicting duplicates
# ---------------------------------------------------------------------------


def test_result_commit_constructs_and_computes_checksum() -> None:
    """Test result commit constructs and computes checksum."""
    commit = make_result_commit()
    assert len(commit.commit_checksum) == 64


def test_result_commit_round_trips() -> None:
    """Test result commit round trips."""
    commit = make_result_commit()
    data = result_commit_to_dict(commit)
    rebuilt = ResultCommit(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        scientific_work_id=data["scientific_work_id"],
        attempt_checksum=data["attempt_checksum"],
        lease_generation=data["lease_generation"],
        result_content_checksum=data["result_content_checksum"],
        result_artifact_reference=ArtifactReference(
            **{
                **data["result_artifact_reference"],
                "artifact_kind": ArtifactKind(data["result_artifact_reference"]["artifact_kind"]),
            }
        ),
        actual_cost_cents=data["actual_cost_cents"],
        commit_checksum=data["commit_checksum"],
    )
    assert rebuilt == commit


def test_result_commit_rejects_candidate_manifest_entry_as_result_artifact() -> None:
    """Test result commit rejects a CANDIDATE_MANIFEST_ENTRY artifact
    kind for its result_artifact_reference -- a result artifact must
    always be tagged RESULT_ARTIFACT."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_result_commit(result_artifact_reference=make_candidate_artifact_reference())


def test_reconcile_result_commit_accepts_new_when_none_exists() -> None:
    """Test crash-before-commit: no existing commit -> ACCEPTED_NEW."""
    commit = make_result_commit()
    assert reconcile_result_commit(None, commit) == ResultCommitReconciliation.ACCEPTED_NEW


def test_reconcile_result_commit_identical_duplicate_is_idempotent() -> None:
    """Test crash-after-commit-before-ack / duplicate delivery: an
    identical duplicate result commit reconciles idempotently, never as
    a new or conflicting event."""
    attempt = make_execution_attempt()
    first_commit = make_result_commit(attempt)
    duplicate_commit = make_result_commit(attempt)
    assert first_commit.result_content_checksum == duplicate_commit.result_content_checksum
    assert (
        reconcile_result_commit(first_commit, duplicate_commit)
        == ResultCommitReconciliation.IDEMPOTENT_DUPLICATE
    )


def test_reconcile_result_commit_conflicting_duplicate_blocks() -> None:
    """Test conflicting commits block rather than overwrite -- a second
    commit for the same scientific_work_id with a *different*
    result_content_checksum is rejected, never silently accepted."""
    attempt = make_execution_attempt()
    first_commit = make_result_commit(attempt)
    conflicting_commit = make_result_commit(
        attempt,
        result_content_checksum="9" * 64,
        result_artifact_reference=make_result_artifact_reference(content_checksum="9" * 64),
    )
    with pytest.raises(ConflictingResultCommitError):
        reconcile_result_commit(first_commit, conflicting_commit)


def test_reconcile_result_commit_rejects_mismatched_scientific_work_id() -> None:
    """Test reconcile_result_commit rejects mismatched scientific work
    id."""
    commit_a = make_result_commit(scientific_work_id="work-a")
    commit_b = make_result_commit(scientific_work_id="work-b")
    with pytest.raises(InvalidDistributedProvenanceError):
        reconcile_result_commit(commit_a, commit_b)


def test_reconcile_result_commit_conflicting_actual_cost_replay_blocks() -> None:
    """MEGB-03H.2C.3B.2B.2 correction: two commits sharing the same
    result_content_checksum but claiming different actual_cost_cents must
    block, never idempotently accept -- a replay must not be able to
    change the amount finalized against an already-committed result."""
    attempt = make_execution_attempt()
    first_commit = make_result_commit(attempt, actual_cost_cents=100)
    conflicting_cost_commit = make_result_commit(attempt, actual_cost_cents=200)
    assert (
        first_commit.result_content_checksum
        == conflicting_cost_commit.result_content_checksum
    )
    with pytest.raises(ConflictingResultCommitError):
        reconcile_result_commit(first_commit, conflicting_cost_commit)


def test_reconcile_result_commit_identical_actual_cost_duplicate_is_idempotent() -> None:
    """The companion positive case: an identical duplicate (same content
    checksum, same actual_cost_cents) still reconciles idempotently."""
    attempt = make_execution_attempt()
    first_commit = make_result_commit(attempt, actual_cost_cents=100)
    duplicate_commit = make_result_commit(attempt, actual_cost_cents=100)
    assert (
        reconcile_result_commit(first_commit, duplicate_commit)
        == ResultCommitReconciliation.IDEMPOTENT_DUPLICATE
    )


def test_result_commit_rejects_the_stale_v2_schema_version_literal() -> None:
    """MEGB-03H.2C.3B.2B.2 correction: DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION
    bumped v2->v3 because ResultCommit's own field shape changed (gained
    the required actual_cost_cents field); a payload still stamped with
    the exact prior v2 string must be rejected, never silently
    reinterpreted under v3."""
    with pytest.raises(UnsupportedDistributedOrchestrationSchemaVersionError):
        make_result_commit(
            distributed_orchestration_schema_version="megb-03h2c3b2b1-distributed-orchestration-v2"
        )


def test_result_commit_v3_round_trips_with_current_schema_version() -> None:
    """Companion positive case to the stale-v2 rejection test above."""
    commit = make_result_commit()
    assert commit.distributed_orchestration_schema_version == (
        DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION
    )
    assert DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION.endswith("-v3")
    data = result_commit_to_dict(commit)
    rebuilt = ResultCommit(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        scientific_work_id=data["scientific_work_id"],
        attempt_checksum=data["attempt_checksum"],
        lease_generation=data["lease_generation"],
        result_content_checksum=data["result_content_checksum"],
        result_artifact_reference=ArtifactReference(
            **{
                **data["result_artifact_reference"],
                "artifact_kind": ArtifactKind(data["result_artifact_reference"]["artifact_kind"]),
            }
        ),
        actual_cost_cents=data["actual_cost_cents"],
        commit_checksum=data["commit_checksum"],
    )
    assert rebuilt == commit


def test_result_commit_rejects_negative_actual_cost_cents() -> None:
    """actual_cost_cents must be a non-negative int -- never a float,
    never negative."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_result_commit(actual_cost_cents=-1)


def test_terminal_disposition_accepts_non_retryable_executor_failure_reason() -> None:
    """MEGB-03H.2C.3B.2B.2 correction: TerminalDispositionReason gained
    NON_RETRYABLE_EXECUTOR_FAILURE, distinct from RETRY_CEILING_EXCEEDED --
    a terminal disposition may now be constructed with either, and they
    remain distinguishable values."""
    non_retryable = make_terminal_disposition(
        disposition_reason=TerminalDispositionReason.NON_RETRYABLE_EXECUTOR_FAILURE
    )
    ceiling_exceeded = make_terminal_disposition(
        disposition_reason=TerminalDispositionReason.RETRY_CEILING_EXCEEDED
    )
    assert non_retryable.disposition_reason != ceiling_exceeded.disposition_reason
    assert non_retryable.disposition_checksum != ceiling_exceeded.disposition_checksum


# ---------------------------------------------------------------------------
# Acknowledgement -- commit-before-ack ordering
# ---------------------------------------------------------------------------


def test_acknowledgement_constructs_and_computes_checksum() -> None:
    """Test acknowledgement constructs and computes checksum."""
    ack = make_acknowledgement()
    assert len(ack.ack_checksum) == 64


def test_acknowledgement_round_trips() -> None:
    """Test acknowledgement round trips."""
    ack = make_acknowledgement()
    data = acknowledgement_to_dict(ack)
    rebuilt = Acknowledgement(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        scientific_work_id=data["scientific_work_id"],
        attempt_checksum=data["attempt_checksum"],
        result_content_checksum=data["result_content_checksum"],
        ack_checksum=data["ack_checksum"],
    )
    assert rebuilt == ack


def test_require_commit_before_ack_accepts_matching_pair() -> None:
    """Test require commit before ack accepts matching pair."""
    commit = make_result_commit()
    ack = make_acknowledgement(commit)
    require_commit_before_ack(commit, ack)  # must not raise


def test_require_commit_before_ack_rejects_ack_naming_a_different_commit() -> None:
    """Test acknowledgement occurs only after durable, checksum-verified
    result commit -- an ack naming a different result_content_checksum
    than the commit it is checked against is rejected."""
    commit = make_result_commit()
    unrelated_ack = make_acknowledgement(
        commit, result_content_checksum="8" * 64
    )
    with pytest.raises(InvalidDistributedProvenanceError):
        require_commit_before_ack(commit, unrelated_ack)


def test_require_commit_before_ack_rejects_mismatched_attempt() -> None:
    """Test require commit before ack rejects mismatched attempt."""
    commit = make_result_commit()
    mismatched_ack = make_acknowledgement(commit, attempt_checksum="7" * 64)
    with pytest.raises(InvalidDistributedProvenanceError):
        require_commit_before_ack(commit, mismatched_ack)


# ---------------------------------------------------------------------------
# TerminalDisposition
# ---------------------------------------------------------------------------


def test_terminal_disposition_constructs_and_computes_checksum() -> None:
    """Test terminal disposition constructs and computes checksum."""
    disposition = make_terminal_disposition()
    assert len(disposition.disposition_checksum) == 64


def test_terminal_disposition_round_trips() -> None:
    """Test terminal disposition round trips."""
    disposition = make_terminal_disposition()
    data = terminal_disposition_to_dict(disposition)
    rebuilt = TerminalDisposition(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        scientific_work_id=data["scientific_work_id"],
        disposition=TerminalDispositionKind(data["disposition"]),
        disposition_reason=TerminalDispositionReason(data["disposition_reason"]),
        attempt_count=data["attempt_count"],
        disposition_checksum=data["disposition_checksum"],
    )
    assert rebuilt == disposition


def test_terminal_disposition_has_no_free_form_diagnostic_field() -> None:
    """Test terminal disposition is typed and closed, with no free-form
    diagnostic field."""
    field_names = {field.name for field in dataclasses.fields(TerminalDisposition)}
    assert "message" not in field_names
    assert "detail" not in field_names
    assert "diagnostic" not in field_names


def test_terminal_disposition_rejects_negative_attempt_count() -> None:
    """Test terminal disposition rejects negative attempt count."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_terminal_disposition(attempt_count=-1)


def test_distributed_orchestration_schema_version_constant_is_stable() -> None:
    """Test the module-level schema-version constant matches every
    fixture's own declared version (sanity check that fixtures track the
    real constant, not a stale copy)."""
    descriptor = make_work_descriptor()
    assert descriptor.distributed_orchestration_schema_version == (
        DISTRIBUTED_ORCHESTRATION_SCHEMA_VERSION
    )
