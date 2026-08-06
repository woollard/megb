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
from src.distributed.calibration_provenance_report_cli import (
    DEFAULT_JSON,
    build_and_write,
    verify,
)


def test_verify_accepts_the_real_committed_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Test verify() accepts the actual committed report and prints its
    readiness classification and count summary."""
    exit_code = verify(DEFAULT_JSON)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "CALIBRATION_PROVENANCE_READY_FOR_3C" in captured.out
    assert "OK" in captured.out


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
