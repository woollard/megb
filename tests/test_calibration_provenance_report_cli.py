"""MEGB-03H.2C.3B.3: offline tests for the calibration-provenance
report build/verify CLI entry point
(``src/distributed/calibration_provenance_report_cli.py``), mirroring
``tests/test_offline_e2e_qualification_cli.py``'s own established shape."""

# This file's own verify/build test shape inherently mirrors
# tests/test_offline_e2e_qualification_cli.py's own already-established
# pattern applied to a different CLI. Expected and accepted, not a
# defect.
# pylint: disable=duplicate-code

import json
import pathlib

import pytest

from src.distributed import calibration_provenance_report_cli
from src.distributed.calibration_provenance_report import (
    build_calibration_provenance_report,
    calibration_provenance_report_to_dict,
    compute_calibration_evidence_checksum,
)
from src.distributed.calibration_provenance_report_cli import (
    DEFAULT_JSON,
    build_and_write,
    verify,
)
from src.distributed.provenance_manifest import (
    build_distributed_provenance_manifest,
    distributed_provenance_manifest_to_dict,
)
from src.distributed.provenance_manifest_lock import write_lock_file, write_protected_manifest
from tests._distributed_fixtures import make_run_context, make_two_region_workers


def _build_synthetic_chain(
    tmp_path: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """Build a real, valid report -> lock -> protected-manifest chain
    rooted entirely under tmp_path (never touching the real committed
    artifacts), returning (report_json_path, lock_path,
    protected_manifest_path). Used to exercise the CLI's lock-chain
    verification paths without corrupting the real committed evidence."""
    run_context = make_run_context(distributed_run_id="cli-lock-chain-test-run")
    worker_a, worker_b = make_two_region_workers(run_context)
    manifest = build_distributed_provenance_manifest(
        run_context,
        (worker_a, worker_b),
        generation_command="pytest cli-lock-chain-test",
        code_revision="1" * 40,
    )
    protected_path = tmp_path / "protected" / "manifest.json"
    lock_path = tmp_path / "lock" / "manifest.lock.json"
    entry = write_protected_manifest(
        manifest,
        generation_command="pytest cli-lock-chain-test",
        generating_code_revision="1" * 40,
        generating_code_dirty=False,
        authorized_consumers=("MEGB-03H.2C.3B.3-tests",),
        protected_path=protected_path,
    )
    write_lock_file(entry, lock_path)

    report = build_calibration_provenance_report(
        provenance_manifest_checksum=manifest.manifest_checksum,
        calibration_run_context_checksum="c" * 64,
        participating_worker_context_checksums=(
            worker_a.worker_context_checksum,
            worker_b.worker_context_checksum,
        ),
        environment_class=run_context.environment_class.value,
        topology_region_counts=manifest.topology_summary.region_counts,
        topology_machine_type_counts=manifest.topology_summary.machine_type_counts,
        topology_provisioning_class_counts=manifest.topology_summary.provisioning_class_counts,
        intended_concurrency=manifest.topology_summary.admitted_worker_count,
        measured_peak_concurrency=2,
        admitted_invocation_count=2,
        completed_invocation_count=2,
        invalid_invocation_count=0,
        incomplete_invocation_count=0,
        invocation_provenance_resolved=True,
        task_reconciliation_passed=True,
        qualification_gate_readiness=manifest.qualification_gate_readiness,
        qualification_gate_missing_dimensions=manifest.qualification_gate_missing_dimensions,
        calibration_evidence_checksum=compute_calibration_evidence_checksum(
            ("a" * 64,), ("b" * 64,)
        ),
    )
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(calibration_provenance_report_to_dict(report), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report_path, lock_path, protected_path


def test_verify_accepts_the_real_committed_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Test verify() accepts the actual committed report, completes the
    full report -> lock -> protected-manifest chain against the real
    committed lock and gitignored protected manifest, and prints its
    readiness classification, count summary, and protected-manifest
    checksum."""
    exit_code = verify(DEFAULT_JSON)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "CALIBRATION_PROVENANCE_READY_FOR_3C" in captured.out
    assert "OK" in captured.out
    assert "protected_manifest_checksum=" in captured.out


def test_verify_raises_on_missing_report_file(tmp_path: pathlib.Path) -> None:
    """verify() against a path with no committed report at all raises
    (rather than silently succeeding) -- a checksum/report can never be
    verified without a persisted, readable artifact to check it
    against."""
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(OSError):
        verify(missing)


def test_verify_rejects_tampered_checksum(tmp_path: pathlib.Path) -> None:
    """Test verify() rejects a copy of the committed report with a
    tampered checksum, returning 1 rather than raising."""
    data = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
    data["report_checksum"] = "0" * 64
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(data), encoding="utf-8")
    assert verify(tampered) == 1


def test_verify_rejects_report_with_a_deviated_count(tmp_path: pathlib.Path) -> None:
    """Test verify() rejects a copy of the committed report whose
    admitted_invocation_count has been silently changed without
    updating the other counts to match -- an inconsistent count
    partition cannot pass as valid."""
    data = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
    data["admitted_invocation_count"] = data["admitted_invocation_count"] + 1
    deviated = tmp_path / "deviated.json"
    deviated.write_text(json.dumps(data), encoding="utf-8")
    assert verify(deviated) == 1


def test_verify_rejects_report_with_readiness_manually_altered(tmp_path: pathlib.Path) -> None:
    """Test verify() rejects a copy of the committed report whose
    readiness has been silently flipped to BLOCKED despite otherwise-
    healthy counts/flags."""
    data = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
    data["readiness"] = "BLOCKED_CALIBRATION_PROVENANCE"
    data["blocker_reasons"] = ["TASK_RECONCILIATION_FAILED"]
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(data), encoding="utf-8")
    assert verify(altered) == 1


def test_verify_accepts_a_valid_synthetic_lock_chain(tmp_path: pathlib.Path) -> None:
    """Test verify() accepts a freshly-built, self-consistent synthetic
    report -> lock -> protected-manifest chain rooted entirely under
    tmp_path -- proving the chain-verification logic itself, independent
    of the one real committed artifact."""
    report_path, lock_path, _ = _build_synthetic_chain(tmp_path)
    assert verify(report_path, lock_path) == 0


def test_verify_rejects_lock_checksum_mismatch_with_report(tmp_path: pathlib.Path) -> None:
    """Test verify() rejects a lock whose manifest_checksum was silently
    changed to no longer match the safe report's own
    provenance_manifest_checksum -- the report -> lock link must never
    be allowed to dangle."""
    report_path, lock_path, _ = _build_synthetic_chain(tmp_path)
    lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_data["entries"][0]["manifest_checksum"] = "0" * 64
    lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
    assert verify(report_path, lock_path) == 1


def test_verify_rejects_lock_with_no_entries(tmp_path: pathlib.Path) -> None:
    """Test verify() rejects an (otherwise well-formed) lock file with
    zero entries rather than silently treating it as verified."""
    report_path, lock_path, _ = _build_synthetic_chain(tmp_path)
    lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_data["entries"] = []
    lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
    assert verify(report_path, lock_path) == 1


def test_verify_rejects_missing_protected_manifest(tmp_path: pathlib.Path) -> None:
    """Test verify() rejects a lock referencing a protected-manifest
    path that does not (or no longer) exists on disk -- required CLI
    behavior: a missing artifact fails verification (a caller wanting
    'regenerate then verify' must call the deterministic build path
    first)."""
    report_path, lock_path, protected_path = _build_synthetic_chain(tmp_path)
    protected_path.unlink()
    assert verify(report_path, lock_path) == 1


def test_verify_rejects_protected_manifest_with_tampered_self_checksum(
    tmp_path: pathlib.Path,
) -> None:
    """Test verify() rejects protected-manifest bytes whose own
    self-checksum was tampered -- a genuinely corrupt artifact, caught
    by the manifest's own structural validation (raises
    InvalidDistributedProvenanceError internally) and surfaced by
    verify() as exit code 1, never a silent pass."""
    report_path, lock_path, protected_path = _build_synthetic_chain(tmp_path)
    data = json.loads(protected_path.read_text(encoding="utf-8"))
    data["manifest_checksum"] = "0" * 64
    protected_path.write_text(json.dumps(data), encoding="utf-8")
    assert verify(report_path, lock_path) == 1


def test_verify_rejects_substituted_wrong_run_protected_manifest(
    tmp_path: pathlib.Path,
) -> None:
    """Test verify() rejects a protected-manifest file substituted with
    a different, internally-self-consistent manifest from an unrelated
    distributed run -- required CLI behavior: substituted/wrong-run
    content fails verification even though the substituted bytes are
    not themselves corrupt."""
    report_path, lock_path, protected_path = _build_synthetic_chain(tmp_path)
    other_run = make_run_context(distributed_run_id="cli-lock-chain-test-other-run")
    other_a, other_b = make_two_region_workers(other_run)
    other_manifest = build_distributed_provenance_manifest(
        other_run,
        (other_a, other_b),
        generation_command="pytest cli-lock-chain-test",
        code_revision="2" * 40,
    )
    protected_path.write_text(
        json.dumps(
            distributed_provenance_manifest_to_dict(other_manifest), indent=2, sort_keys=True
        ),
        encoding="utf-8",
    )
    assert verify(report_path, lock_path) == 1


def test_build_and_write_short_circuits_on_suite_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test build_and_write() returns the pytest exit code and never
    calls verify() when the underlying harness itself fails."""
    calls: list[str] = []

    def _verify_stub() -> int:
        calls.append("called")
        return 0

    monkeypatch.setattr(calibration_provenance_report_cli, "_run_suite", lambda: 1)
    monkeypatch.setattr(calibration_provenance_report_cli, "verify", _verify_stub)
    assert build_and_write() == 1
    assert not calls


def test_build_and_write_verifies_after_a_successful_suite_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test build_and_write() calls verify() once the harness itself
    exits cleanly."""
    monkeypatch.setattr(calibration_provenance_report_cli, "_run_suite", lambda: 0)
    monkeypatch.setattr(calibration_provenance_report_cli, "verify", lambda: 0)
    assert build_and_write() == 0


def test_main_build_command_dispatches_to_build_and_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main() dispatches the 'build' subcommand to build_and_write()."""
    monkeypatch.setattr("sys.argv", ["calibration_provenance_report_cli", "build"])
    monkeypatch.setattr(calibration_provenance_report_cli, "build_and_write", lambda: 0)
    assert calibration_provenance_report_cli.main() == 0


def test_main_verify_command_dispatches_to_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main() dispatches the 'verify' subcommand to verify()."""
    monkeypatch.setattr("sys.argv", ["calibration_provenance_report_cli", "verify"])
    monkeypatch.setattr(calibration_provenance_report_cli, "verify", lambda: 0)
    assert calibration_provenance_report_cli.main() == 0
