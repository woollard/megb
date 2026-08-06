"""MEGB-03H.2C.3B.3: the offline synthetic integration harness proving
the full calibration-provenance evidence chain end-to-end, in-process:

1. creates a synthetic distributed provenance manifest;
1b. persists it as synthetic protected evidence plus a committed lock;
2. creates a calibration run context bound to it;
3. creates invocation records across (at least) two workers, with a
   real, ``threading.Barrier``-forced concurrent overlap measuring
   genuine peak concurrency;
4. reconciles task-evaluation records against those invocations;
5. constructs the safe qualification-evidence report;
6. writes safe JSON/Markdown output;
7. verifies the artifact chain from the report back to the manifest and
   invocation records;
8. verifies the report -> lock -> protected-manifest chain completes,
   with no dangling manifest checksum.

No candidate code, HumanEval cases, oracle values, Docker, or cloud
resources anywhere in this file. Calibration records are never
persisted to any file. The full ``DistributedProvenanceManifest`` IS
persisted -- as **synthetic protected evidence**, never real
HumanEval/candidate evidence -- to the gitignored
``artifacts/privileged/distributed_provenance/`` path via
``src.distributed.provenance_manifest_lock``, with a small, committed,
non-privileged lock file anchoring its identity; this correction closes
the original B.3 checkpoint's own dangling-checksum gap (the safe
report's ``provenance_manifest_checksum`` previously referenced a
manifest that was never actually written anywhere verifiable). The safe
report itself is written to ``docs/measurement/``, mirroring the
already-accepted B.2C offline-E2E-qualification report's own precedent.
"""

# This file's own _PeakConcurrencyTracker inherently mirrors
# tests/_offline_e2e_qualification_fixtures.py's own already-established
# PeakConcurrencyTrackingExecutor pattern (same measurement shape,
# applied to calibration-record construction rather than candidate
# execution) -- shared boilerplate, not shared logic. Its own healthy-
# report keyword-argument block also mirrors
# tests/test_calibration_provenance_report.py's own equivalent fixture
# defaults. Expected and accepted, not a defect.
# pylint: disable=duplicate-code

import json
import subprocess
import threading
from pathlib import Path

from src.distributed.calibration_provenance_report import (
    CalibrationProvenanceReadiness,
    build_calibration_provenance_report,
    calibration_provenance_report_from_dict,
    calibration_provenance_report_to_dict,
    compute_calibration_evidence_checksum,
    render_markdown,
)
from src.distributed.provenance import WorkerExecutionContext
from src.distributed.provenance_manifest import (
    build_distributed_provenance_manifest,
    resolve_worker_context,
)
from src.distributed.provenance_manifest_lock import (
    DEFAULT_MANIFEST_LOCK_PATH,
    DEFAULT_PROTECTED_MANIFEST_PATH,
    load_lock_file,
    verify_against_lock,
    write_lock_file,
    write_protected_manifest,
)
from src.reference.calibration_schema import CalibrationInvocationRecord, reconcile_all
from src.reference.distributed_provenance_reconciliation import (
    reconcile_all_invocations,
    reconcile_calibration_run_context,
)
from tests._calibration_fixtures import make_context, make_invocation, make_task_evaluation_for
from tests._distributed_fixtures import make_run_context, make_two_region_workers

REPORT_JSON_PATH = Path("docs/measurement/megb-03h2c3b3-calibration-provenance-report.json")
REPORT_MD_PATH = Path("docs/measurement/megb-03h2c3b3-calibration-provenance-report.md")

_GENERATION_COMMAND = "pytest tests/test_calibration_provenance_integration.py"


def _git_head_sha() -> tuple[str, bool]:
    """Return (HEAD commit SHA, whether the working tree has uncommitted
    changes). Best-effort: returns ("unknown", True) if git is
    unavailable, never raises. Mirrors
    ``src.reference.partition_lock``'s own ``_git_head_sha()`` exactly;
    duplicated here (rather than imported) because
    ``src/distributed/provenance_manifest_lock.py`` itself must never
    import ``subprocess``, per this package's own established
    no-subprocess boundary -- git-revision computation is the caller's
    responsibility, and ``tests/`` is unconstrained by that rule."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
        return sha, bool(status.strip())
    except Exception:  # pylint: disable=broad-exception-caught
        return "unknown", True


class _PeakConcurrencyTracker:
    """Tracks the real peak number of simultaneously-active
    ``record()`` calls -- a genuine measurement, never an assumed or
    configured value, mirroring the already-accepted B.2C
    ``PeakConcurrencyTrackingExecutor`` pattern applied here to
    concurrent calibration-record construction rather than candidate
    execution."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0

    def enter(self) -> None:
        """Record the start of one active worker's contribution."""
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)

    def exit(self) -> None:
        """Record the end of one active worker's contribution."""
        with self._lock:
            self._active -= 1


def test_calibration_provenance_integration_end_to_end() -> None:  # pylint: disable=too-many-locals,too-many-statements
    """Build the full evidence chain from a synthetic distributed run
    through a safe, committed calibration-provenance report, verifying
    every link back to the manifest and invocation records."""
    # 1. Synthetic distributed provenance manifest.
    run_context = make_run_context(distributed_run_id="calib-prov-integration-run")
    worker_a, worker_b = make_two_region_workers(run_context)
    manifest = build_distributed_provenance_manifest(
        run_context,
        (worker_a, worker_b),
        generation_command=_GENERATION_COMMAND,
        code_revision="f" * 40,
    )
    assert manifest.qualification_gate_readiness == "READY"

    # 1b. Persist the full manifest as synthetic protected evidence under
    # a gitignored path, plus a small committed lock anchoring its
    # identity -- closes the dangling-checksum gap where the safe
    # report's provenance_manifest_checksum previously referenced a
    # manifest that was never written anywhere verifiable.
    code_revision, code_dirty = _git_head_sha()
    lock_entry = write_protected_manifest(
        manifest,
        generation_command=_GENERATION_COMMAND,
        generating_code_revision=code_revision,
        generating_code_dirty=code_dirty,
        authorized_consumers=("MEGB-03H.2C.3B.3",),
        protected_path=DEFAULT_PROTECTED_MANIFEST_PATH,
    )
    write_lock_file(lock_entry, DEFAULT_MANIFEST_LOCK_PATH)

    # 2. Calibration run context bound to the manifest.
    calibration_context = make_context(
        distributed_run_context_checksum=manifest.run_context.run_context_checksum,
        provenance_manifest_checksum=manifest.manifest_checksum,
    )
    reconcile_calibration_run_context(calibration_context, manifest)

    # 3. Invocation records across two workers, with a real Barrier-
    # forced concurrent overlap measuring genuine peak concurrency.
    barrier = threading.Barrier(2)
    # A second barrier, entered only after tracker.enter(), forces both
    # threads to rendezvous while *both* are already marked active --
    # otherwise, since building a calibration record is near-instantaneous,
    # ordinary thread scheduling could run one thread's whole
    # enter()/build()/exit() sequence before the other ever starts,
    # never producing a genuine simultaneous peak of 2.
    overlap_barrier = threading.Barrier(2)
    tracker = _PeakConcurrencyTracker()
    built_invocations: dict[str, CalibrationInvocationRecord] = {}
    lock = threading.Lock()

    def _build_invocation(
        invocation_id: str, task_id: str, worker: WorkerExecutionContext
    ) -> None:
        barrier.wait()
        tracker.enter()
        overlap_barrier.wait()
        try:
            invocation = make_invocation(
                invocation_id=invocation_id,
                context=calibration_context,
                task_id=task_id,
                worker_execution_context_checksum=worker.worker_context_checksum,
            )
        finally:
            tracker.exit()
        with lock:
            built_invocations[invocation_id] = invocation

    thread_a = threading.Thread(
        target=_build_invocation, args=("inv-task-a-1", "task-a", worker_a)
    )
    thread_b = threading.Thread(
        target=_build_invocation, args=("inv-task-b-1", "task-b", worker_b)
    )
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    assert tracker.peak == 2, "the barrier-forced overlap did not produce a genuine peak of 2"
    invocation_a = built_invocations["inv-task-a-1"]
    invocation_b = built_invocations["inv-task-b-1"]

    # Every invocation's worker checksum resolves within the manifest.
    resolve_worker_context(manifest, invocation_a.worker_execution_context_checksum)
    resolve_worker_context(manifest, invocation_b.worker_execution_context_checksum)
    reconcile_all_invocations((invocation_a, invocation_b), manifest)

    # 4. Task-evaluation records, reconciled against their contributors.
    task_evaluation_a = make_task_evaluation_for([invocation_a])
    task_evaluation_b = make_task_evaluation_for([invocation_b])
    reconcile_all(
        [invocation_a, invocation_b],
        [task_evaluation_a, task_evaluation_b],
    )

    # 5. Safe qualification-evidence report.
    evidence_checksum = compute_calibration_evidence_checksum(
        (invocation_a.record_checksum, invocation_b.record_checksum),
        (task_evaluation_a.record_checksum, task_evaluation_b.record_checksum),
    )
    report = build_calibration_provenance_report(
        provenance_manifest_checksum=manifest.manifest_checksum,
        calibration_run_context_checksum=calibration_context.context_checksum,
        participating_worker_context_checksums=(
            worker_a.worker_context_checksum,
            worker_b.worker_context_checksum,
        ),
        environment_class=run_context.environment_class.value,
        topology_region_counts=manifest.topology_summary.region_counts,
        topology_machine_type_counts=manifest.topology_summary.machine_type_counts,
        topology_provisioning_class_counts=manifest.topology_summary.provisioning_class_counts,
        intended_concurrency=manifest.topology_summary.admitted_worker_count,
        measured_peak_concurrency=tracker.peak,
        admitted_invocation_count=2,
        completed_invocation_count=2,
        invalid_invocation_count=0,
        incomplete_invocation_count=0,
        invocation_provenance_resolved=True,
        task_reconciliation_passed=True,
        qualification_gate_readiness=manifest.qualification_gate_readiness,
        qualification_gate_missing_dimensions=manifest.qualification_gate_missing_dimensions,
        calibration_evidence_checksum=evidence_checksum,
    )
    assert report.readiness == CalibrationProvenanceReadiness.CALIBRATION_PROVENANCE_READY_FOR_3C

    # 6. Safe JSON/Markdown output. The safe report is the only artifact
    # committed to docs/measurement/; the full manifest was already
    # persisted in step 1b as synthetic protected evidence under a
    # gitignored path, anchored by the committed lock -- calibration
    # records themselves are still never written to any file.
    REPORT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON_PATH.write_text(
        json.dumps(calibration_provenance_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    REPORT_MD_PATH.write_text(render_markdown(report), encoding="utf-8")

    # 7. Verify the artifact chain from the report back to the manifest
    # and invocation records: reload the just-written JSON and confirm
    # every checksum still resolves against the real objects above.
    reloaded = calibration_provenance_report_from_dict(
        json.loads(REPORT_JSON_PATH.read_text(encoding="utf-8"))
    )
    assert reloaded == report
    assert reloaded.provenance_manifest_checksum == manifest.manifest_checksum
    assert reloaded.calibration_run_context_checksum == calibration_context.context_checksum
    for worker_checksum in reloaded.participating_worker_context_checksums:
        resolve_worker_context(manifest, worker_checksum)

    # 8. Complete the report -> lock -> protected-manifest chain: the
    # safe report's own provenance_manifest_checksum must never be a
    # dangling reference -- it must match the committed lock's own
    # manifest_checksum, and the lock must itself verify against the
    # actual protected bytes on disk.
    reloaded_lock = load_lock_file(DEFAULT_MANIFEST_LOCK_PATH)
    assert len(reloaded_lock.entries) == 1
    assert reloaded_lock.entries[0].manifest_checksum == reloaded.provenance_manifest_checksum
    manifest_verification_results = verify_against_lock(reloaded_lock)
    assert len(manifest_verification_results) == 1
    assert manifest_verification_results[0].passed
    assert manifest_verification_results[0].on_disk_present
