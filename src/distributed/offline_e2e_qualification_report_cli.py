"""MEGB-03H.2C.3B.2C: a minimal, operator-usable, offline build/verify
entry point for the offline end-to-end qualification report --
mirroring :mod:`~src.distributed.fault_conformance_cli`'s established
shape exactly.

``python -m src.distributed.offline_e2e_qualification_report_cli build``
    Runs the full in-process offline E2E qualification suite (which
    writes the committed JSON+Markdown report as its own final step,
    from the actual run it performed), then reads the result back and
    confirms it is complete and internally consistent.

``python -m src.distributed.offline_e2e_qualification_report_cli verify``
    Read-only: reloads the already-committed JSON report and
    re-validates it. Schema version, checksum, and the frozen workload's
    exact expected counts are all enforced by the report's own
    constructor. Runs no test and executes no synthetic workload.

Neither command runs Docker, touches the network, or accesses any cloud
resource."""

# This module's build/verify/main shape intentionally mirrors
# fault_conformance_cli.py's own already-established CLI pattern applied
# to a different report. Expected and accepted, not a defect.
# pylint: disable=duplicate-code

import argparse
import json
import sys
from pathlib import Path

import pytest

from src.distributed.offline_e2e_qualification_report import (
    InvalidOfflineE2EQualificationReportError,
    offline_e2e_qualification_report_from_dict,
)

DEFAULT_JSON = Path("docs/measurement/megb-03h2c3b2c-offline-e2e-qualification-report.json")
_SUITE_PATH = Path("tests/test_offline_e2e_qualification.py")


def verify(json_path: Path = DEFAULT_JSON) -> int:
    """Reload and re-validate the committed report. Returns 0 and prints
    a one-line summary if it is valid; returns 1 and prints the specific
    validation failure otherwise."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    try:
        report = offline_e2e_qualification_report_from_dict(data)
    except InvalidOfflineE2EQualificationReportError as exc:
        print(f"Offline E2E qualification report INVALID ({json_path}): {exc}", file=sys.stderr)
        return 1
    print(
        f"Offline E2E qualification report OK: readiness={report.readiness.value}, "
        f"admitted={report.admitted_count}, completed={report.completed_count}, "
        f"checksum={report.report_checksum}"
    )
    return 0


def _run_suite() -> int:
    """Run the full offline E2E qualification suite in-process. A thin,
    directly-monkeypatchable seam so tests can exercise
    :func:`build_and_write`'s own control flow without recursively
    re-running the whole suite from within itself."""
    return int(pytest.main(["-q", str(_SUITE_PATH)]))


def build_and_write() -> int:
    """Run the full offline E2E qualification suite in-process, then
    re-validate what it wrote. The suite's own final test is the only
    place the JSON/Markdown files are written -- this function never
    duplicates that logic, it only triggers and then confirms it."""
    exit_code = _run_suite()
    if exit_code != 0:
        print(f"offline E2E qualification suite failed (pytest exit code {exit_code})",
              file=sys.stderr)
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
