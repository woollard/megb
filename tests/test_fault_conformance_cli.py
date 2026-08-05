"""MEGB-03H.2C.3B.2B.3 report-integrity correction: offline tests for the
fault-conformance build/verify CLI entry point
(``src/distributed/fault_conformance_cli.py``).

``verify`` is tested directly against real files (the actual committed
report, and deliberately tampered copies) -- it is read-only and cheap.
``build_and_write``'s control flow (call the suite, then verify what it
wrote) is tested by monkeypatching ``pytest.main`` rather than actually
re-running the full suite recursively from within this suite -- nested
pytest sessions are unnecessary here and avoid any risk of session-state
interference; the suite itself is already exhaustively tested by
``tests/test_fault_conformance.py``."""

import json
import pathlib

import pytest

from src.distributed import fault_conformance_cli
from src.distributed.fault_conformance_cli import DEFAULT_JSON, build_and_write, verify


def test_verify_accepts_the_real_committed_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Test verify() accepts the actual committed report and prints its
    readiness classification and entry/attempt counts."""
    exit_code = verify(DEFAULT_JSON)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "IN_PROCESS_RECOVERY_READY_FOR_B2C" in captured.out
    assert "OK" in captured.out


def test_verify_rejects_tampered_checksum(tmp_path: pathlib.Path) -> None:
    """Test verify() rejects a copy of the committed report with a
    tampered checksum, returning 1 rather than raising."""
    data = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
    data["report_checksum"] = "0" * 64
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(data), encoding="utf-8")
    assert verify(tampered) == 1


def test_verify_rejects_report_missing_a_fault_point(tmp_path: pathlib.Path) -> None:
    """Test verify() rejects a copy of the committed report with one
    fault point's entries removed -- a scenario cannot be silently
    dropped and still read as valid."""
    data = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
    removed_fault_point = data["entries"][0]["fault_point"]
    data["entries"] = [
        entry for entry in data["entries"] if entry["fault_point"] != removed_fault_point
    ]
    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(json.dumps(data), encoding="utf-8")
    assert verify(incomplete) == 1


def test_build_and_write_short_circuits_on_suite_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test build_and_write() returns the pytest exit code and never
    calls verify() when the underlying suite itself fails."""
    calls: list[str] = []

    def _verify_stub() -> int:
        calls.append("called")
        return 0

    monkeypatch.setattr(fault_conformance_cli, "_run_suite", lambda: 1)
    monkeypatch.setattr(fault_conformance_cli, "verify", _verify_stub)
    assert build_and_write() == 1
    assert not calls


def test_build_and_write_verifies_after_a_successful_suite_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test build_and_write() calls verify() (to confirm and summarize
    what the suite wrote) once the suite itself exits cleanly."""
    monkeypatch.setattr(fault_conformance_cli, "_run_suite", lambda: 0)
    monkeypatch.setattr(fault_conformance_cli, "verify", lambda: 0)
    assert build_and_write() == 0


def test_main_build_command_dispatches_to_build_and_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main() dispatches the 'build' subcommand to build_and_write()."""
    monkeypatch.setattr("sys.argv", ["fault_conformance_cli", "build"])
    monkeypatch.setattr(fault_conformance_cli, "build_and_write", lambda: 0)
    assert fault_conformance_cli.main() == 0


def test_main_verify_command_dispatches_to_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main() dispatches the 'verify' subcommand to verify()."""
    monkeypatch.setattr("sys.argv", ["fault_conformance_cli", "verify"])
    monkeypatch.setattr(fault_conformance_cli, "verify", lambda: 0)
    assert fault_conformance_cli.main() == 0
