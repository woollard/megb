"""MEGB-03H.2C.3B.1: tests for ``src.distributed.safe_summary`` -- the
allowlisted, safe-to-commit projection, and the structural leakage
exclusions it and ``src.distributed.protected_mapping`` must maintain."""

import ast
import dataclasses
from pathlib import Path

import pytest

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.identity import (
    MixedWorkerProvenanceSummary,
    ProductionIdentityProjection,
    QualificationIdentity,
    aggregate_worker_provenance,
    qualification_identity_for,
)
from src.distributed.protected_mapping import ProtectedOperationalMapping
from src.distributed.provenance import (
    DistributedRunContext,
    RetryLeasePolicy,
    WorkerExecutionContext,
)
from src.distributed.qualification_gate import QualificationGateResult
from src.distributed.safe_summary import (
    SafeRedactedSummary,
    build_safe_redacted_summary,
    safe_redacted_summary_from_dict,
    safe_redacted_summary_to_dict,
    safe_summary_field_names,
)
from tests._distributed_fixtures import make_run_and_worker, make_run_context, make_worker_context

_MANAGED_MODEL_FORBIDDEN_SUBSTRINGS = (
    "model",
    "vertex",
    "maas",
    "generation_plane",
    "candidate_generation",
)

# ---------------------------------------------------------------------------
# Construction / determinism
# ---------------------------------------------------------------------------


def test_build_safe_redacted_summary() -> None:
    """Test build safe redacted summary."""
    run_context, worker = make_run_and_worker()
    identity = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (worker,))
    )
    summary = build_safe_redacted_summary(run_context, (worker,), identity)
    assert summary.distinct_worker_count == 1
    assert summary.regions_observed == (worker.region,)


def test_build_safe_redacted_summary_requires_nonempty_workers() -> None:
    """Test build safe redacted summary requires nonempty workers."""
    run_context = make_run_context()
    placeholder_worker = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum
    )
    identity = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (placeholder_worker,))
    )
    with pytest.raises(InvalidDistributedProvenanceError):
        build_safe_redacted_summary(run_context, (), identity)


def test_build_safe_redacted_summary_rejects_mismatched_worker() -> None:
    """Test build safe redacted summary rejects mismatched worker."""
    run_a = make_run_context(distributed_run_id="run-a")
    run_b = make_run_context(distributed_run_id="run-b")
    worker_b = make_worker_context(parent_run_context_checksum=run_b.run_context_checksum)
    identity_b = qualification_identity_for(
        run_b, aggregate_worker_provenance(run_b, (worker_b,))
    )
    with pytest.raises(InvalidDistributedProvenanceError):
        build_safe_redacted_summary(run_a, (worker_b,), identity_b)


def test_aggregates_are_sorted_and_deduplicated() -> None:
    """Test aggregates are sorted and deduplicated."""
    run_context = make_run_context()
    worker_a = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum, region="us-west1"
    )
    worker_b = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        region="us-central1",
        worker_image_digest="9" * 64,
    )
    worker_c = make_worker_context(
        parent_run_context_checksum=run_context.run_context_checksum,
        region="us-central1",  # duplicate region, distinct worker (different image)
        worker_image_digest="8" * 64,
    )
    identity = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (worker_a, worker_b, worker_c))
    )
    summary = build_safe_redacted_summary(run_context, (worker_a, worker_b, worker_c), identity)
    assert summary.regions_observed == tuple(sorted(summary.regions_observed))
    assert summary.regions_observed == ("us-central1", "us-west1")
    assert summary.distinct_worker_count == 3


def test_summary_is_frozen() -> None:
    """Test summary is frozen."""
    run_context, worker = make_run_and_worker()
    identity = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (worker,))
    )
    summary = build_safe_redacted_summary(run_context, (worker,), identity)
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.distinct_worker_count = 99  # type: ignore[misc]


def test_summary_checksum_tampering_detected() -> None:
    """Test summary checksum tampering detected."""
    run_context, worker = make_run_and_worker()
    identity = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (worker,))
    )
    summary = build_safe_redacted_summary(run_context, (worker,), identity)
    payload = safe_redacted_summary_to_dict(summary)
    payload["distinct_worker_count"] = 99
    with pytest.raises(InvalidDistributedProvenanceError, match="summary_checksum"):
        safe_redacted_summary_from_dict(payload)


def test_summary_round_trip() -> None:
    """Test summary round trip."""
    run_context, worker = make_run_and_worker()
    identity = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (worker,))
    )
    summary = build_safe_redacted_summary(run_context, (worker,), identity)
    restored = safe_redacted_summary_from_dict(safe_redacted_summary_to_dict(summary))
    assert restored == summary


# ---------------------------------------------------------------------------
# Structural leakage exclusion
# ---------------------------------------------------------------------------

_PROTECTED_FIELD_NAMES = frozenset(
    field.name for field in dataclasses.fields(ProtectedOperationalMapping)
)

# Derived, not hardcoded: every DistributedRunContext/RetryLeasePolicy
# field whose name marks it as one of the audit-only concepts (Ambiguity
# 2) -- coordinator/fleet/queue/object-store implementation identity, the
# retry/lease policy's own fields, plus per-worker 'zone' (concept #3).
# A name-substring filter over the live dataclass fields, so this list
# tracks the real schema instead of drifting from a separately
# maintained literal copy of it.
_AUDIT_ONLY_NAME_MARKERS = (
    "coordinator",
    "fleet",
    "queue",
    "object_store",
    "lease",
    "retry_ceiling",
    "dead_letter",
    "retry_lease_policy",
)
_EXCLUDED_AUDIT_ONLY_CONCEPT_NAMES = frozenset(
    field.name
    for cls in (DistributedRunContext, RetryLeasePolicy)
    for field in dataclasses.fields(cls)
    if any(marker in field.name for marker in _AUDIT_ONLY_NAME_MARKERS)
) | {"zone"}


def test_safe_summary_field_names_exclude_every_protected_operational_field() -> None:
    """No raw operational identifier field name overlaps a safe-summary
    field name -- the strongest available leakage guarantee, since there
    is structurally no field to accidentally serialize."""
    overlap = safe_summary_field_names() & _PROTECTED_FIELD_NAMES
    # 'logical_environment_id' and the two schema/checksum-version fields
    # are the only intentional, safe overlap -- the join key and version
    # labels, never a raw identifier.
    assert overlap <= {
        "distributed_provenance_schema_version",
        "checksum_algorithm_version",
        "logical_environment_id",
    }


def test_safe_summary_field_names_exclude_audit_only_concepts() -> None:
    """Ambiguity 2: coordinator/fleet/queue/object-store implementation
    version and retry/lease policy fields are excluded from the safe
    summary, per the accepted audit's own conservative "(1),(3)" tagging."""
    overlap = safe_summary_field_names() & _EXCLUDED_AUDIT_ONLY_CONCEPT_NAMES
    assert overlap == set()


def test_safe_summary_field_names_exclude_raw_identifier_shaped_names() -> None:
    """Test safe summary field names exclude raw identifier shaped names."""
    for name in safe_summary_field_names():
        assert "raw_" not in name
        assert "hostname" not in name
        assert "container_id" not in name
        assert "instance_id" not in name
        assert "credential" not in name
        assert "password" not in name
        assert "secret" not in name
        assert "path" not in name


def test_safe_summary_serialization_contains_no_secret_shaped_value() -> None:
    """Even with a maximally-populated fixture, the serialized safe
    summary never contains anything matching a credential/secret shape."""
    run_context, worker = make_run_and_worker()
    identity = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (worker,))
    )
    summary = build_safe_redacted_summary(run_context, (worker,), identity)
    serialized = str(safe_redacted_summary_to_dict(summary))
    for forbidden in ("BEGIN PRIVATE KEY", "service_account", "AKIA", "ya29.", "xoxb-"):
        assert forbidden not in serialized


def test_safe_summary_never_carries_per_worker_zone() -> None:
    """Concept #3: zone is excluded entirely, even in aggregate form, to
    avoid per-record infrastructure-topology fingerprinting."""
    run_context, worker = make_run_and_worker(worker_overrides={"zone": "us-central1-a"})
    identity = qualification_identity_for(
        run_context, aggregate_worker_provenance(run_context, (worker,))
    )
    summary = build_safe_redacted_summary(run_context, (worker,), identity)
    serialized = safe_redacted_summary_to_dict(summary)
    assert "us-central1-a" not in str(serialized)
    assert "zone" not in serialized


def test_protected_mapping_never_imported_by_safe_summary_module() -> None:
    """Structural guarantee: the safe_summary module's own source has no
    import of protected_mapping -- there is no code path from a raw
    identifier into a safe report."""
    source = Path("src/distributed/safe_summary.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
    assert "src.distributed.protected_mapping" not in imported


def test_managed_model_provenance_absent_from_every_distributed_type() -> None:
    """Managed-model/candidate-generation-plane provenance is reserved
    for MEGB-03H.2C.3G -- no field or module name in this package may be
    mistaken for it."""
    for dataclass_type in (
        DistributedRunContext,
        WorkerExecutionContext,
        ProtectedOperationalMapping,
        SafeRedactedSummary,
        MixedWorkerProvenanceSummary,
        QualificationIdentity,
        ProductionIdentityProjection,
        QualificationGateResult,
    ):
        for field in dataclasses.fields(dataclass_type):
            lowered = field.name.lower()
            for forbidden in _MANAGED_MODEL_FORBIDDEN_SUBSTRINGS:
                assert forbidden not in lowered, f"{dataclass_type.__name__}.{field.name}"
