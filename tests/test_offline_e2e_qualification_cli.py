"""MEGB-03H.2C.3B.2C: offline tests for the offline E2E qualification
build/verify CLI entry point
(``src/distributed/offline_e2e_qualification_report_cli.py``), mirroring
``tests/test_fault_conformance_cli.py``'s own established shape."""

# This file's own verify/build test shape inherently mirrors
# tests/test_fault_conformance_cli.py's own already-established pattern
# applied to a different CLI. Expected and accepted, not a defect.
# pylint: disable=duplicate-code

import json
import pathlib

import pytest

from src.distributed import offline_e2e_qualification_report_cli
from src.distributed.offline_e2e_qualification_report_cli import (
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
    assert "OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3" in captured.out
    assert "OK" in captured.out


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
    admitted_count has been silently changed -- a deviation from the
    frozen workload's own expectations cannot pass as valid."""
    data = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
    data["admitted_count"] = data["admitted_count"] + 1
    deviated = tmp_path / "deviated.json"
    deviated.write_text(json.dumps(data), encoding="utf-8")
    assert verify(deviated) == 1


def test_build_and_write_short_circuits_on_suite_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test build_and_write() returns the pytest exit code and never
    calls verify() when the underlying suite itself fails."""
    calls: list[str] = []

    def _verify_stub() -> int:
        calls.append("called")
        return 0

    monkeypatch.setattr(offline_e2e_qualification_report_cli, "_run_suite", lambda: 1)
    monkeypatch.setattr(offline_e2e_qualification_report_cli, "verify", _verify_stub)
    assert build_and_write() == 1
    assert not calls


def test_build_and_write_verifies_after_a_successful_suite_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test build_and_write() calls verify() once the suite itself exits
    cleanly."""
    monkeypatch.setattr(offline_e2e_qualification_report_cli, "_run_suite", lambda: 0)
    monkeypatch.setattr(offline_e2e_qualification_report_cli, "verify", lambda: 0)
    assert build_and_write() == 0


def test_main_build_command_dispatches_to_build_and_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main() dispatches the 'build' subcommand to build_and_write()."""
    monkeypatch.setattr("sys.argv", ["offline_e2e_qualification_report_cli", "build"])
    monkeypatch.setattr(offline_e2e_qualification_report_cli, "build_and_write", lambda: 0)
    assert offline_e2e_qualification_report_cli.main() == 0


def test_main_verify_command_dispatches_to_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main() dispatches the 'verify' subcommand to verify()."""
    monkeypatch.setattr("sys.argv", ["offline_e2e_qualification_report_cli", "verify"])
    monkeypatch.setattr(offline_e2e_qualification_report_cli, "verify", lambda: 0)
    assert offline_e2e_qualification_report_cli.main() == 0
