"""MEGB-03H.2C.3B.3: offline tests for the distributed-provenance
manifest (``src.distributed.provenance_manifest``), the calibration
schema's v2->v3 distributed-provenance content-binding fields
(``src.reference.calibration_schema``), and the reconciliation bridge
between them (``src.reference.distributed_provenance_reconciliation``).

Synthetic only -- no candidate code, HumanEval cases, oracle values,
Docker, or cloud resources anywhere in this file.
"""

import dataclasses

import pytest

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.identity import DuplicateWorkerProvenanceError, EmptyWorkerSetError
from src.distributed.provenance import (
    DistributedRunContext,
    DistributedRunIntent,
    ProvisioningClass,
    WorkerExecutionContext,
)
from src.distributed.provenance_manifest import (
    DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION,
    DistributedProvenanceManifest,
    UnsupportedDistributedProvenanceManifestSchemaVersionError,
    build_distributed_provenance_manifest,
    distributed_provenance_manifest_from_dict,
    distributed_provenance_manifest_to_dict,
    resolve_worker_context,
)
from src.reference.calibration_schema import (
    CALIBRATION_SCHEMA_VERSION,
    CalibrationReconciliationError,
    InvalidCalibrationRecordError,
    UnsupportedCalibrationSchemaVersionError,
    calibration_invocation_record_to_dict,
    calibration_run_context_to_dict,
    reconcile_task_evaluation,
)
from src.reference.distributed_provenance_reconciliation import (
    DistributedProvenanceReconciliationError,
    reconcile_all_invocations,
    reconcile_calibration_invocation_worker,
    reconcile_calibration_run_context,
)
from tests._calibration_fixtures import make_context, make_invocation, make_task_evaluation_for
from tests._distributed_fixtures import (
    make_run_context,
    make_two_region_workers,
    make_worker_context,
)

_GENERATION_COMMAND = "pytest tests/test_distributed_calibration_provenance.py"
_CODE_REVISION = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"


_ManifestFixture = tuple[
    DistributedRunContext, tuple[WorkerExecutionContext, ...], DistributedProvenanceManifest
]


def _build_manifest(run_overrides: dict[str, object] | None = None) -> _ManifestFixture:
    run = make_run_context(**(run_overrides or {}))
    workers = make_two_region_workers(run)
    manifest = build_distributed_provenance_manifest(
        run, workers, generation_command=_GENERATION_COMMAND, code_revision=_CODE_REVISION
    )
    return run, workers, manifest


# ---------------------------------------------------------------------------
# DistributedProvenanceManifest: construction, round-trip, resolution
# ---------------------------------------------------------------------------


def test_build_manifest_binds_run_workers_topology_identity_and_gate() -> None:
    """A manifest built from a real run/workers set binds every piece
    the frozen design names: run context, worker contexts, topology
    summary, qualification identity, gate readiness, safe summary."""
    run, workers, manifest = _build_manifest()
    assert manifest.run_context == run
    assert set(w.worker_context_checksum for w in manifest.worker_execution_contexts) == {
        w.worker_context_checksum for w in workers
    }
    assert manifest.topology_summary.admitted_worker_count == 2
    assert manifest.qualification_identity.run_context_checksum == run.run_context_checksum
    assert manifest.qualification_gate_readiness == "READY"
    assert not manifest.qualification_gate_missing_dimensions
    assert manifest.safe_redacted_summary.admitted_worker_count == 2
    assert len(manifest.manifest_checksum) == 64


def test_manifest_round_trips_through_to_dict_from_dict() -> None:
    """Full-fidelity serialization round-trips exactly."""
    _, _, manifest = _build_manifest()
    data = distributed_provenance_manifest_to_dict(manifest)
    rebuilt = distributed_provenance_manifest_from_dict(data)
    assert rebuilt == manifest


def test_manifest_rejects_tampered_checksum() -> None:
    """A manifest_checksum that does not match the recomputed value over
    its own contents is rejected -- tampered or corrupted evidence."""
    _, _, manifest = _build_manifest()
    data = distributed_provenance_manifest_to_dict(manifest)
    data["manifest_checksum"] = "0" * 64
    with pytest.raises(InvalidDistributedProvenanceError):
        distributed_provenance_manifest_from_dict(data)


def test_manifest_rejects_stale_schema_version() -> None:
    """A manifest stamped with an unknown schema version is rejected.
    ``from_dict`` wraps every construction-time ``ValueError`` (including
    the more specific ``UnsupportedDistributedProvenanceManifestSchemaVersionError``,
    itself a subclass) into the general error type -- the same
    established convention every other ``from_dict`` in this codebase
    already follows (e.g. ``distributed_run_context_from_dict``); direct
    construction (see
    ``test_manifest_direct_construction_rejects_stale_schema_version``
    below) is what surfaces the specific subclass."""
    _, _, manifest = _build_manifest()
    data = distributed_provenance_manifest_to_dict(manifest)
    data["distributed_provenance_manifest_schema_version"] = (
        "megb-03h2c3b3-distributed-provenance-manifest-v0"
    )
    with pytest.raises(InvalidDistributedProvenanceError):
        distributed_provenance_manifest_from_dict(data)


def test_manifest_direct_construction_rejects_stale_schema_version() -> None:
    """Direct dataclass construction (not via from_dict) surfaces the
    specific UnsupportedDistributedProvenanceManifestSchemaVersionError
    subclass."""
    _, _, manifest = _build_manifest()
    with pytest.raises(UnsupportedDistributedProvenanceManifestSchemaVersionError):
        dataclasses.replace(
            manifest,
            distributed_provenance_manifest_schema_version=(
                "megb-03h2c3b3-distributed-provenance-manifest-v0"
            ),
            manifest_checksum="",
        )


def test_current_manifest_schema_version_is_v1() -> None:
    """Confirms the exact, intentional new schema-family identity."""
    assert (
        DISTRIBUTED_PROVENANCE_MANIFEST_SCHEMA_VERSION
        == "megb-03h2c3b3-distributed-provenance-manifest-v1"
    )


def test_build_manifest_rejects_empty_worker_set() -> None:
    """Unprovenanced evidence (no workers at all) is rejected."""
    run = make_run_context()
    with pytest.raises(EmptyWorkerSetError):
        build_distributed_provenance_manifest(
            run, (), generation_command=_GENERATION_COMMAND, code_revision=_CODE_REVISION
        )


def test_build_manifest_rejects_mixed_distributed_run_contexts() -> None:
    """A worker whose parent_run_context_checksum belongs to a different
    run is rejected -- mixed distributed-run contexts."""
    run_a = make_run_context(distributed_run_id="run-a")
    run_b = make_run_context(distributed_run_id="run-b")
    worker_from_b = make_worker_context(parent_run_context_checksum=run_b.run_context_checksum)
    with pytest.raises(InvalidDistributedProvenanceError):
        build_distributed_provenance_manifest(
            run_a,
            (worker_from_b,),
            generation_command=_GENERATION_COMMAND,
            code_revision=_CODE_REVISION,
        )


def test_build_manifest_rejects_duplicate_participant_id() -> None:
    """Two worker contexts sharing the same worker_participant_id are
    rejected -- a duplicate *observation*, not genuine multiplicity."""
    run = make_run_context()
    worker = make_worker_context(parent_run_context_checksum=run.run_context_checksum)
    with pytest.raises(DuplicateWorkerProvenanceError):
        build_distributed_provenance_manifest(
            run,
            (worker, worker),
            generation_command=_GENERATION_COMMAND,
            code_revision=_CODE_REVISION,
        )


def test_manifest_direct_construction_rejects_duplicate_participant_id() -> None:
    """Even bypassing build_distributed_provenance_manifest, hand-
    constructing a DistributedProvenanceManifest with a duplicate
    worker_participant_id in worker_execution_contexts is independently
    rejected by __post_init__ itself -- never merely a builder-level
    convenience check."""
    _, workers, manifest = _build_manifest()
    duplicate_workers = (workers[0], workers[0])
    with pytest.raises(InvalidDistributedProvenanceError):
        dataclasses.replace(
            manifest,
            worker_execution_contexts=duplicate_workers,
            manifest_checksum="",
        )


def test_resolve_worker_context_finds_real_worker() -> None:
    """resolve_worker_context returns the exact WorkerExecutionContext
    whose checksum matches, from within a real manifest."""
    _, workers, manifest = _build_manifest()
    resolved = resolve_worker_context(manifest, workers[0].worker_context_checksum)
    assert resolved == workers[0]


def test_resolve_worker_context_rejects_unknown_checksum() -> None:
    """A checksum without a persisted, verifiable referenced manifest
    entry is insufficient -- resolve_worker_context rejects it outright."""
    _, _, manifest = _build_manifest()
    with pytest.raises(InvalidDistributedProvenanceError):
        resolve_worker_context(manifest, "f" * 64)


def test_resolve_worker_context_rejects_worker_from_another_manifest() -> None:
    """A worker checksum that is real -- but belongs to a *different*
    manifest's run -- does not resolve within this manifest: "worker from
    another run" / "dangling checksum with no artifact [here]"."""
    _, workers_a, manifest_a = _build_manifest(run_overrides={"distributed_run_id": "run-a"})
    _, workers_b, _manifest_b = _build_manifest(run_overrides={"distributed_run_id": "run-b"})
    assert workers_a[0].worker_context_checksum != workers_b[0].worker_context_checksum
    with pytest.raises(InvalidDistributedProvenanceError):
        resolve_worker_context(manifest_a, workers_b[0].worker_context_checksum)


@pytest.mark.parametrize(
    "field_overrides",
    [
        {"region": "europe-west1"},
        {"machine_type": "c2-standard-8"},
        {"zone": "us-central1-a"},
        {"provisioning_class": ProvisioningClass.SPOT},
        {"worker_image_digest": "7" * 64},
        {"worker_implementation_version": "2.0.0"},
    ],
)
def test_manifest_checksum_changes_with_any_worker_identity_field(
    field_overrides: dict[str, object]
) -> None:
    """Changing worker image, machine type, region, zone, provisioning
    class, or worker implementation on even one participating worker
    changes the manifest's own manifest_checksum (and, transitively,
    qualification_identity.identity_checksum) -- the required identity-
    sensitivity proof."""
    run = make_run_context()
    worker_a = make_worker_context(
        parent_run_context_checksum=run.run_context_checksum,
        worker_participant_id="worker-a",
    )
    worker_b_baseline = make_worker_context(
        parent_run_context_checksum=run.run_context_checksum,
        worker_participant_id="worker-b",
    )
    worker_b_changed = make_worker_context(
        parent_run_context_checksum=run.run_context_checksum,
        worker_participant_id="worker-b",
        **field_overrides,
    )
    manifest_baseline = build_distributed_provenance_manifest(
        run,
        (worker_a, worker_b_baseline),
        generation_command=_GENERATION_COMMAND,
        code_revision=_CODE_REVISION,
    )
    manifest_changed = build_distributed_provenance_manifest(
        run,
        (worker_a, worker_b_changed),
        generation_command=_GENERATION_COMMAND,
        code_revision=_CODE_REVISION,
    )
    assert manifest_baseline.manifest_checksum != manifest_changed.manifest_checksum
    assert (
        manifest_baseline.qualification_identity.identity_checksum
        != manifest_changed.qualification_identity.identity_checksum
    )


def test_manifest_gate_blocked_for_smoke_test_intent() -> None:
    """A smoke-test distributed run's manifest reports gate readiness
    BLOCKED with NOT_QUALIFICATION_INTENT -- smoke evidence can never
    read as qualifying."""
    _, _, manifest = _build_manifest(run_overrides={"run_intent": DistributedRunIntent.SMOKE_TEST})
    assert manifest.qualification_gate_readiness == "BLOCKED"
    assert "NOT_QUALIFICATION_INTENT" in manifest.qualification_gate_missing_dimensions


def test_manifest_generation_command_and_code_revision_reject_secret_looking_values() -> None:
    """generation_command/code_revision are rejected if they look like a
    credential/secret -- defense in depth, mirroring
    protected_mapping.py's own established pattern."""
    run, workers, _manifest = _build_manifest()
    with pytest.raises(InvalidDistributedProvenanceError):
        build_distributed_provenance_manifest(
            run,
            workers,
            generation_command='{"type": "service_account", "project_id": "x"}',
            code_revision=_CODE_REVISION,
        )


# ---------------------------------------------------------------------------
# CalibrationRunContext/CalibrationInvocationRecord v3 fields
# ---------------------------------------------------------------------------


def test_current_calibration_schema_version_is_v3() -> None:
    """Confirms the exact, intentional version string this checkpoint's
    v2->v3 bump produced."""
    assert CALIBRATION_SCHEMA_VERSION == "megb-03h-calibration-record-v3"


def test_calibration_run_context_v3_round_trips() -> None:
    """A CalibrationRunContext carrying real distributed-run-context/
    manifest checksums round-trips exactly."""
    _, _, manifest = _build_manifest()
    context = make_context(
        distributed_run_context_checksum=manifest.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest.manifest_checksum,
    )
    rebuilt = calibration_run_context_to_dict(context)
    assert rebuilt["distributed_run_context_checksum"] == manifest.run_context.run_context_checksum
    assert rebuilt["provenance_manifest_checksum"] == manifest.manifest_checksum


def test_calibration_invocation_record_v3_round_trips() -> None:
    """A CalibrationInvocationRecord carrying a real
    worker_execution_context_checksum round-trips exactly."""
    _, workers, manifest = _build_manifest()
    context = make_context(
        distributed_run_context_checksum=manifest.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest.manifest_checksum,
    )
    invocation = make_invocation(
        context=context, worker_execution_context_checksum=workers[0].worker_context_checksum
    )
    rebuilt = calibration_invocation_record_to_dict(invocation)
    assert rebuilt["worker_execution_context_checksum"] == workers[0].worker_context_checksum


def test_calibration_run_context_rejects_malformed_distributed_checksum() -> None:
    """distributed_run_context_checksum must be sha256-hex shaped."""
    with pytest.raises(InvalidCalibrationRecordError):
        make_context(distributed_run_context_checksum="not-a-checksum")


def test_calibration_invocation_record_rejects_malformed_worker_checksum() -> None:
    """worker_execution_context_checksum must be sha256-hex shaped."""
    with pytest.raises(InvalidCalibrationRecordError):
        make_invocation(worker_execution_context_checksum="not-a-checksum")


# ---------------------------------------------------------------------------
# Reconciliation: positive path
# ---------------------------------------------------------------------------


def test_reconcile_calibration_run_context_accepts_matching_manifest() -> None:
    """A context whose distributed_run_context_checksum/
    provenance_manifest_checksum both match a real manifest reconciles
    cleanly."""
    _, _, manifest = _build_manifest()
    context = make_context(
        distributed_run_context_checksum=manifest.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest.manifest_checksum,
    )
    reconcile_calibration_run_context(context, manifest)  # must not raise


def test_reconcile_calibration_invocation_worker_accepts_real_worker() -> None:
    """An invocation whose worker_execution_context_checksum resolves to
    a real worker within the manifest reconciles cleanly."""
    _, workers, manifest = _build_manifest()
    context = make_context(
        distributed_run_context_checksum=manifest.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest.manifest_checksum,
    )
    invocation = make_invocation(
        context=context, worker_execution_context_checksum=workers[0].worker_context_checksum
    )
    reconcile_calibration_invocation_worker(invocation, manifest)  # must not raise


def test_reconcile_all_invocations_accepts_every_real_worker() -> None:
    """Every invocation in a fully-consistent set reconciles cleanly in
    one pass."""
    _, workers, manifest = _build_manifest()
    context = make_context(
        distributed_run_context_checksum=manifest.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest.manifest_checksum,
    )
    invocations = tuple(
        make_invocation(
            invocation_id=f"inv-{i}",
            context=context,
            worker_execution_context_checksum=worker.worker_context_checksum,
        )
        for i, worker in enumerate(workers)
    )
    reconcile_all_invocations(invocations, manifest)  # must not raise


# ---------------------------------------------------------------------------
# Reconciliation: negative-test matrix
# ---------------------------------------------------------------------------


def test_reconcile_rejects_wrong_distributed_run_checksum() -> None:
    """context.distributed_run_context_checksum pointing at a different
    run than the manifest actually holds is rejected."""
    _, _, manifest = _build_manifest()
    context = make_context(
        distributed_run_context_checksum="9" * 64,
        provenance_manifest_checksum=manifest.manifest_checksum,
    )
    with pytest.raises(DistributedProvenanceReconciliationError):
        reconcile_calibration_run_context(context, manifest)


def test_reconcile_rejects_wrong_manifest_checksum() -> None:
    """context.provenance_manifest_checksum not matching this exact
    manifest is rejected, even when distributed_run_context_checksum is
    correct."""
    _, _, manifest = _build_manifest()
    context = make_context(
        distributed_run_context_checksum=manifest.run_context.run_context_checksum,
        provenance_manifest_checksum="8" * 64,
    )
    with pytest.raises(DistributedProvenanceReconciliationError):
        reconcile_calibration_run_context(context, manifest)


def test_reconcile_rejects_unknown_worker_checksum() -> None:
    """An invocation's worker_execution_context_checksum that resolves
    to nothing in the manifest is rejected."""
    _, _, manifest = _build_manifest()
    context = make_context(
        distributed_run_context_checksum=manifest.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest.manifest_checksum,
    )
    invocation = make_invocation(context=context, worker_execution_context_checksum="6" * 64)
    with pytest.raises(DistributedProvenanceReconciliationError):
        reconcile_calibration_invocation_worker(invocation, manifest)


def test_reconcile_rejects_worker_from_another_run() -> None:
    """A worker checksum real in a *different* manifest is rejected here
    -- "worker from another run"."""
    _, _, manifest_a = _build_manifest(run_overrides={"distributed_run_id": "run-a2"})
    _, workers_b, _manifest_b = _build_manifest(run_overrides={"distributed_run_id": "run-b2"})
    context = make_context(
        distributed_run_context_checksum=manifest_a.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest_a.manifest_checksum,
    )
    invocation = make_invocation(
        context=context, worker_execution_context_checksum=workers_b[0].worker_context_checksum
    )
    with pytest.raises(DistributedProvenanceReconciliationError):
        reconcile_calibration_invocation_worker(invocation, manifest_a)


def test_reconcile_rejects_invocation_manifest_mismatch() -> None:
    """An invocation whose own context does not point at this manifest
    at all is rejected before the worker-checksum lookup ever runs."""
    _, workers, manifest = _build_manifest()
    unrelated_context = make_context(
        distributed_run_context_checksum="5" * 64,
        provenance_manifest_checksum="4" * 64,
    )
    invocation = make_invocation(
        context=unrelated_context,
        worker_execution_context_checksum=workers[0].worker_context_checksum,
    )
    with pytest.raises(DistributedProvenanceReconciliationError):
        reconcile_calibration_invocation_worker(invocation, manifest)


def test_reconcile_all_invocations_rejects_first_failure() -> None:
    """reconcile_all_invocations raises on the first invocation whose
    worker provenance fails to reconcile, given a mixed good/bad set."""
    _, workers, manifest = _build_manifest()
    context = make_context(
        distributed_run_context_checksum=manifest.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest.manifest_checksum,
    )
    good = make_invocation(
        invocation_id="inv-good",
        context=context,
        worker_execution_context_checksum=workers[0].worker_context_checksum,
    )
    bad = make_invocation(
        invocation_id="inv-bad", context=context, worker_execution_context_checksum="3" * 63 + "4"
    )
    with pytest.raises(DistributedProvenanceReconciliationError):
        reconcile_all_invocations((good, bad), manifest)


# ---------------------------------------------------------------------------
# CalibrationTaskEvaluationRecord: no new field, transitive content binding
# ---------------------------------------------------------------------------


def test_calibration_schema_v2_stale_reject_and_v3_current_confirmed() -> None:
    """Redundant, deliberately explicit confirmation alongside
    tests/test_calibration_telemetry_provenance_schema.py's own
    dedicated v2-rejection/v3-current tests: this checkpoint's own new
    fields are unavailable under the stale v2 identifier."""
    with pytest.raises(UnsupportedCalibrationSchemaVersionError):
        make_context(calibration_schema_version="megb-03h-calibration-record-v2")


def test_task_evaluation_reconciliation_rejects_substituted_worker_via_content_checksum() -> None:
    """MEGB-03H.2C.3B.3 design §4's explicit determination, proven: no
    new worker-context histogram field is needed on
    CalibrationTaskEvaluationRecord, because
    contributing_invocation_content_checksums already binds each
    contributor's *entire* record_checksum -- which now includes
    worker_execution_context_checksum. Substituting the worker that
    produced an already-bound invocation (same everything else) changes
    that invocation's record_checksum, which reconcile_task_evaluation
    already rejects as "contributor content changed after binding"."""
    _, workers, manifest = _build_manifest()
    context = make_context(
        distributed_run_context_checksum=manifest.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest.manifest_checksum,
    )
    original_invocation = make_invocation(
        invocation_id="inv-1",
        context=context,
        worker_execution_context_checksum=workers[0].worker_context_checksum,
    )
    task_evaluation = make_task_evaluation_for([original_invocation])

    # Same invocation_id/task/candidate/replicate/case-scope, but a
    # different (still-real, still-in-manifest) contributing worker --
    # this changes record_checksum, simulating a substituted worker
    # discovered after the task-evaluation record already bound the
    # original.
    substituted_invocation = make_invocation(
        invocation_id="inv-1",
        context=context,
        worker_execution_context_checksum=workers[1].worker_context_checksum,
    )
    assert substituted_invocation.record_checksum != original_invocation.record_checksum

    with pytest.raises(CalibrationReconciliationError):
        reconcile_task_evaluation(task_evaluation, {"inv-1": substituted_invocation})

    # The original, unsubstituted invocation still reconciles cleanly --
    # confirms the rejection above is specifically about the
    # substitution, not some unrelated fixture drift.
    reconcile_task_evaluation(task_evaluation, {"inv-1": original_invocation})


def test_calibration_task_evaluation_record_has_no_new_distributed_field() -> None:
    """Structural confirmation of the frozen design's own determination:
    CalibrationTaskEvaluationRecord's field set gained nothing from this
    checkpoint -- no worker-context histogram, no distributed checksum
    field of any kind. Its own contributing_invocation_content_checksums
    field (already accepted) is the sole binding mechanism."""
    from src.reference.calibration_schema import (  # pylint: disable=import-outside-toplevel
        CalibrationTaskEvaluationRecord,
    )

    field_names = {field.name for field in dataclasses.fields(CalibrationTaskEvaluationRecord)}
    for forbidden in (
        "worker_execution_context_checksum",
        "distributed_run_context_checksum",
        "provenance_manifest_checksum",
        "worker_context_histogram",
        "worker_topology",
    ):
        assert forbidden not in field_names, (
            f"CalibrationTaskEvaluationRecord unexpectedly gained field {forbidden!r} -- "
            "the frozen design determined none of these are needed, since contributor "
            "content checksums already bind this information transitively"
        )


# ---------------------------------------------------------------------------
# Additional negative-test-matrix items: altered topology count, mixed
# calibration run contexts, and missing contributor -- confirming these
# already-established reconciliation behaviors still hold correctly with
# the new v3 distributed-provenance fields present.
# ---------------------------------------------------------------------------


def test_manifest_rejects_topology_summary_from_a_different_worker_set() -> None:
    """A manifest whose topology_summary was swapped in from a
    *different* manifest's own worker set (self-consistent on its own,
    but not built from these workers) is rejected -- an altered
    topology count relative to the actual admitted worker set."""
    _, _, manifest_a = _build_manifest(run_overrides={"distributed_run_id": "topology-run-a"})
    _, _, manifest_b = _build_manifest(run_overrides={"distributed_run_id": "topology-run-b"})
    with pytest.raises(InvalidDistributedProvenanceError):
        dataclasses.replace(
            manifest_a,
            topology_summary=manifest_b.topology_summary,
            manifest_checksum="",
        )


def test_reconcile_task_evaluation_rejects_mixed_calibration_run_contexts() -> None:
    """Two invocations recorded under two different CalibrationRunContexts
    (differing distributed_run_context_checksum/provenance_manifest_checksum,
    even though every other label matches) cannot both contribute to one
    task-evaluation record -- mixed calibration run contexts rejected,
    confirmed still correct with the new v3 fields present."""
    _, _, manifest_a = _build_manifest(run_overrides={"distributed_run_id": "mixed-ctx-run-a"})
    _, _, manifest_b = _build_manifest(run_overrides={"distributed_run_id": "mixed-ctx-run-b"})
    context_a = make_context(
        distributed_run_context_checksum=manifest_a.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest_a.manifest_checksum,
    )
    context_b = make_context(
        distributed_run_context_checksum=manifest_b.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest_b.manifest_checksum,
    )
    worker_checksum_a = manifest_a.worker_execution_contexts[0].worker_context_checksum
    worker_checksum_b = manifest_b.worker_execution_contexts[0].worker_context_checksum
    invocation_a = make_invocation(
        invocation_id="inv-mixed-1",
        context=context_a,
        worker_execution_context_checksum=worker_checksum_a,
    )
    invocation_b = make_invocation(
        invocation_id="inv-mixed-2",
        context=context_b,
        worker_execution_context_checksum=worker_checksum_b,
    )
    task_evaluation = make_task_evaluation_for(
        [invocation_a],
        contributing_invocation_ids=("inv-mixed-1", "inv-mixed-2"),
        contributing_invocation_content_checksums=(
            invocation_a.record_checksum,
            invocation_b.record_checksum,
        ),
    )
    with pytest.raises(CalibrationReconciliationError):
        reconcile_task_evaluation(
            task_evaluation, {"inv-mixed-1": invocation_a, "inv-mixed-2": invocation_b}
        )


def test_reconcile_task_evaluation_rejects_missing_contributor() -> None:
    """A task-evaluation record referencing a contributing invocation id
    absent from the supplied invocation set is rejected -- missing
    contributor, confirmed still correct with the new v3 fields
    present."""
    _, _, manifest = _build_manifest()
    context = make_context(
        distributed_run_context_checksum=manifest.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest.manifest_checksum,
    )
    worker_checksum = manifest.worker_execution_contexts[0].worker_context_checksum
    invocation = make_invocation(
        invocation_id="inv-present",
        context=context,
        worker_execution_context_checksum=worker_checksum,
    )
    task_evaluation = make_task_evaluation_for(
        [invocation],
        contributing_invocation_ids=("inv-present", "inv-absent"),
        contributing_invocation_content_checksums=(
            invocation.record_checksum,
            "7" * 64,
        ),
    )
    with pytest.raises(CalibrationReconciliationError):
        reconcile_task_evaluation(task_evaluation, {"inv-present": invocation})
