"""MEGB-03H.2C.3B.3: a minimal, operator-usable, offline build/verify
entry point for the calibration-provenance qualification-evidence report
-- mirroring :mod:`~src.distributed.offline_e2e_qualification_report_cli`'s
established shape exactly.

``python -m src.distributed.calibration_provenance_report_cli build``
    Runs the full in-process synthetic integration harness (which writes
    the committed JSON+Markdown report as its own final step, from the
    actual manifest/calibration-provenance chain it built), then reads
    the result back and confirms it is complete and internally
    consistent.

``python -m src.distributed.calibration_provenance_report_cli verify``
    Read-only: reloads the already-committed JSON report and
    re-validates it. Schema version, checksum, peak-concurrency
    invariants, and derived readiness/blocker-reasons are all enforced
    by the report's own constructor. Also completes the
    report -> lock -> protected-manifest artifact-verification chain:
    loads the committed manifest lock, confirms its own
    ``manifest_checksum`` matches the safe report's
    ``provenance_manifest_checksum`` (never a dangling reference), and
    re-verifies the (gitignored, synthetic-protected-evidence) manifest
    bytes on disk against that lock. Runs no test and builds no new
    synthetic manifest/calibration evidence.

Neither command runs Docker, touches the network, or accesses any cloud
resource. Prints only safe report/lock fields -- never manifest or
calibration-record contents."""

# This module's build/verify/main shape intentionally mirrors
# offline_e2e_qualification_report_cli.py's own already-established CLI
# pattern applied to a different report. Expected and accepted, not a
# defect.
# pylint: disable=duplicate-code

import argparse
import json
import sys
from pathlib import Path

import pytest

from src.distributed._checksums import InvalidDistributedProvenanceError
from src.distributed.calibration_provenance_report import (
    InvalidCalibrationProvenanceReportError,
    calibration_provenance_report_from_dict,
)
from src.distributed.provenance_manifest_lock import (
    DEFAULT_MANIFEST_LOCK_PATH,
    load_lock_file,
    verify_against_lock,
)

DEFAULT_JSON = Path("docs/measurement/megb-03h2c3b3-calibration-provenance-report.json")
_SUITE_PATH = Path("tests/test_calibration_provenance_integration.py")


def verify(  # pylint: disable=too-many-return-statements
    json_path: Path = DEFAULT_JSON, lock_path: Path = DEFAULT_MANIFEST_LOCK_PATH
) -> int:
    """Reload and re-validate the committed report, then complete the
    report -> lock -> protected-manifest artifact-verification chain.
    Returns 0 and prints a one-line summary if everything is valid;
    returns 1 and prints the specific validation failure otherwise.
    Never prints protected manifest contents."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    try:
        report = calibration_provenance_report_from_dict(data)
    except InvalidCalibrationProvenanceReportError as exc:
        print(
            f"Calibration-provenance report INVALID ({json_path}): {exc}",
            file=sys.stderr,
        )
        return 1

    lock = load_lock_file(lock_path)
    if not lock.entries:
        print(f"Protected-manifest lock {lock_path} has no entries", file=sys.stderr)
        return 1
    lock_entry = lock.entries[0]
    if lock_entry.manifest_checksum != report.provenance_manifest_checksum:
        print(
            "Protected-manifest lock checksum does not match the safe report's own "
            f"provenance_manifest_checksum ({lock_entry.manifest_checksum!r} != "
            f"{report.provenance_manifest_checksum!r})",
            file=sys.stderr,
        )
        return 1
    try:
        manifest_results = verify_against_lock(lock)
    except InvalidDistributedProvenanceError as exc:
        print(f"Protected manifest INVALID ({lock_path}): {exc}", file=sys.stderr)
        return 1
    if not all(result.passed for result in manifest_results):
        print(f"Protected-manifest verification FAILED: {manifest_results}", file=sys.stderr)
        return 1

    print(
        f"Calibration-provenance report OK: readiness={report.readiness.value}, "
        f"admitted={report.admitted_invocation_count}, "
        f"completed={report.completed_invocation_count}, "
        f"checksum={report.report_checksum}, "
        f"protected_manifest_checksum={lock_entry.manifest_checksum}"
    )
    return 0


def _run_suite() -> int:
    """Run the full synthetic integration harness in-process. A thin,
    directly-monkeypatchable seam so tests can exercise
    :func:`build_and_write`'s own control flow without recursively
    re-running the whole suite from within itself."""
    return int(pytest.main(["-q", str(_SUITE_PATH)]))


def build_and_write() -> int:
    """Run the full synthetic integration harness in-process, then
    re-validate what it wrote. The harness's own final step is the only
    place the JSON/Markdown files are written -- this function never
    duplicates that logic, it only triggers and then confirms it."""
    exit_code = _run_suite()
    if exit_code != 0:
        print(
            f"calibration-provenance integration harness failed (pytest exit code {exit_code})",
            file=sys.stderr,
        )
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
