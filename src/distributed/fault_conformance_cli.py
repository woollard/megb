"""MEGB-03H.2C.3B.2B.3 report-integrity correction: a minimal, operator-
usable, offline build/verify entry point for the fault-conformance
report -- previously reachable only by running pytest's own test
collection directly against ``tests/test_fault_conformance.py``.

``python -m src.distributed.fault_conformance_cli build``
    Runs the full in-process fault-injection/recovery conformance suite
    (which writes the committed JSON+Markdown report as its own final
    step, from every scenario it actually recorded), then reads the
    result back and confirms it is complete and internally consistent.

``python -m src.distributed.fault_conformance_cli verify``
    Read-only: reloads the already-committed JSON report and re-validates
    it. Schema version, checksum, and complete/non-duplicate fault-point
    and invariant coverage are all enforced by the report's own
    constructor (:class:`~src.distributed.fault_conformance.FaultConformanceReport`).
    Runs no test and executes no fault scenario.

Neither command runs Docker, touches the network, or accesses any cloud
resource -- ``build`` only runs the already-offline, in-process pytest
suite; ``verify`` only reads an already-committed JSON file."""

import argparse
import json
import sys
from pathlib import Path

import pytest

from src.distributed.fault_conformance import (
    InvalidFaultConformanceReportError,
    fault_conformance_report_from_dict,
)

DEFAULT_JSON = Path("docs/measurement/megb-03h2c3b2b3-fault-conformance-report.json")
_SUITE_PATH = Path("tests/test_fault_conformance.py")


def verify(json_path: Path = DEFAULT_JSON) -> int:
    """Reload and re-validate the committed report. Returns 0 and prints
    a one-line summary if it is valid; returns 1 and prints the specific
    validation failure otherwise."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    try:
        report = fault_conformance_report_from_dict(data)
    except InvalidFaultConformanceReportError as exc:
        print(f"Fault-conformance report INVALID ({json_path}): {exc}", file=sys.stderr)
        return 1
    print(
        f"Fault-conformance report OK: readiness={report.readiness.value}, "
        f"entries={len(report.entries)}, total_attempts={report.total_attempts}, "
        f"checksum={report.report_checksum}"
    )
    return 0


def _run_suite() -> int:
    """Run the full offline fault-conformance suite in-process. A thin,
    directly-monkeypatchable seam so tests can exercise
    :func:`build_and_write`'s own control flow without recursively
    re-running the whole suite from within itself."""
    return int(pytest.main(["-q", str(_SUITE_PATH)]))


def build_and_write() -> int:
    """Run the full offline fault-conformance suite in-process, then
    re-validate what it wrote. The suite's own final test is the only
    place the JSON/Markdown files are written -- this function never
    duplicates that logic, it only triggers and then confirms it."""
    exit_code = _run_suite()
    if exit_code != 0:
        print(f"fault-conformance suite failed (pytest exit code {exit_code})", file=sys.stderr)
        return exit_code
    return verify()


def main() -> int:
    """Parse ``build``/``verify`` from argv and dispatch to the matching
    command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "verify"])
    args = parser.parse_args()
    if args.command == "build":
        return build_and_write()
    return verify()


if __name__ == "__main__":
    sys.exit(main())
