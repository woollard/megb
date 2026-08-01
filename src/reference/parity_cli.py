"""MEGB-03D build/verify CLI: ``python -m src.reference.parity_cli {build|verify}``.

Kept as its own module — mirroring ``src.reference.partition_cli`` /
``src.reference.oracle_cli`` — for the same reason: it is the one place
that needs symbols from the parity comparison module (``parity.py``), the
parity lock module (``parity_lock.py``), and MEGB-02's Docker backend, and
none of those need to import this CLI glue back.

Requires a running Docker daemon and the ``megb-runner:local`` image (see
``docs/security/execution-sandbox.md``): ``build`` executes every parity
candidate through it. There is no offline mode.

Deliberately duplicates some of `partition_cli`/`oracle_cli`'s build/verify
scaffolding rather than sharing a base with them, for the same reason
documented in `oracle_lock.py`'s module docstring: those are already-accepted
code, and consolidating all three CLIs into shared plumbing is flagged as
future cleanup, not authorized here.
"""

# pylint: disable=duplicate-code

import argparse
import json
import sys
from importlib.metadata import version as pkg_version

import evalplus
import numpy

from src.dataset import load_privileged_view, load_provenance, load_public_view
from src.execution.docker_backend import (
    DEFAULT_RUNNER_IMAGE,
    BACKEND_ID,
    DockerPerInvocationBackend,
    execute_candidate,
)
from src.execution.protocol import CandidateExecutionRequest, ExecutionLimits
from src.reference.parity import run_parity_corpus
from src.reference.parity_corpus import (
    PARITY_CORPUS,
    PARITY_CORPUS_VERSION,
    check_corpus_covers_required_categories,
)
from src.reference.parity_lock import (
    COMMITTED_OUTPUT_DIR,
    LOCK_PATH,
    EnvironmentRecord,
    FrozenArtifactConflictError,
    finalize_parity_artifact,
    load_parity_lock_file,
    redact_parity_artifact,
    verify_parity_against_lock,
    write_parity_lock_file,
    write_privileged_parity_artifact,
)

_ENVIRONMENT_PROBE_PROTOCOL_VERSION = "1"
_EVALPLUS_INTERNAL_APIS = (
    "evalplus.eval.untrusted_check",
    "evalplus.eval.PASS",
    "evalplus.eval.is_floats",
    "evalplus.eval._special_oracle._poly",
    "evalplus.eval.utils.time_limit",
    "evalplus.gen.util.trusted_exec",
)


def _probe_runner_image_digest() -> str:
    """One trivial invocation through the real backend, purely to record
    which runner image digest this run actually used (requirement 11)."""
    request = CandidateExecutionRequest(
        candidate_code="def _probe():\n    return 1\n",
        entry_point="_probe",
        args=(),
        kwargs={},
        limits=ExecutionLimits(),
        protocol_version=_ENVIRONMENT_PROBE_PROTOCOL_VERSION,
    )
    return execute_candidate(request, runner_image=DEFAULT_RUNNER_IMAGE).runner_image_digest


def _build_environment_record() -> EnvironmentRecord:
    return EnvironmentRecord(
        evalplus_version=evalplus.__version__,
        human_eval_version=pkg_version("human-eval"),
        python_version=sys.version,
        numpy_version=numpy.__version__,
        evalplus_internal_apis=_EVALPLUS_INTERNAL_APIS,
        docker_backend_id=BACKEND_ID,
        runner_image_digest=_probe_runner_image_digest(),
    )


def _run_build(force: bool) -> None:
    """Run the frozen parity corpus through both classification paths and freeze the result."""
    check_corpus_covers_required_categories()

    priv = {t.task_id: t for t in load_privileged_view()}
    pub = {t.task_id: t.prompt for t in load_public_view()}
    provenance = load_provenance()
    backend = DockerPerInvocationBackend()

    results = run_parity_corpus(PARITY_CORPUS, priv, pub, backend)
    environment = _build_environment_record()
    artifact = finalize_parity_artifact(PARITY_CORPUS_VERSION, provenance, results, environment)

    disagreements = [r for r in results if not r.agree]
    if disagreements:
        print(
            f"BUILD FAILED: {len(disagreements)} candidate(s) show an unresolved "
            "upstream/MEGB classification mismatch — refusing to freeze a parity "
            "artifact with unexplained disagreement. See below for task/category "
            "identification (no expected outputs are printed).",
            file=sys.stderr,
        )
        for r in disagreements:
            print(f"  {r.candidate_id} ({r.task_id}, {r.category}): {r.mismatch_detail}",
                  file=sys.stderr)
        sys.exit(1)

    COMMITTED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (COMMITTED_OUTPUT_DIR / "parity_report_redacted.json").write_text(
        json.dumps(redact_parity_artifact(artifact), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    try:
        lock = write_privileged_parity_artifact(artifact, force=force)
    except FrozenArtifactConflictError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    write_parity_lock_file(lock)

    pass_base_fail_plus = [r for r in results if r.megb.outcome == "PASS_BASE_FAIL_PLUS"]
    print(f"candidates: {len(results)}, all agree: {len(disagreements) == 0}")
    print(f"PASS_BASE_FAIL_PLUS candidates: {[r.candidate_id for r in pass_base_fail_plus]}")
    print("artifact checksum:", artifact.artifact_checksum)
    print(f"parity lock file written: {LOCK_PATH}")


def _run_verify() -> None:
    """Regenerate the parity corpus results and verify them against parity.lock.json."""
    if not LOCK_PATH.exists():
        print(f"VERIFY FAILED: parity lock file not found at {LOCK_PATH}", file=sys.stderr)
        sys.exit(1)

    check_corpus_covers_required_categories()
    priv = {t.task_id: t for t in load_privileged_view()}
    pub = {t.task_id: t.prompt for t in load_public_view()}
    provenance = load_provenance()
    backend = DockerPerInvocationBackend()

    results = run_parity_corpus(PARITY_CORPUS, priv, pub, backend)
    environment = _build_environment_record()
    fresh_artifact = finalize_parity_artifact(
        PARITY_CORPUS_VERSION, provenance, results, environment
    )

    lock = load_parity_lock_file()
    verification_results = verify_parity_against_lock(lock, fresh_artifact)

    all_passed = True
    for result in verification_results:
        status = "PASS" if result.passed else "FAIL"
        print(
            f"{result.artifact_id}: {status} "
            f"(logical_checksum={result.logical_checksum_match}, "
            f"size={result.size_match}, "
            f"on_disk_present={result.on_disk_present}, "
            f"on_disk_checksum={result.on_disk_checksum_match}, "
            f"on_disk_bytes_match_rebuild={result.on_disk_bytes_match_rebuild}, "
            f"dataset_checksum={result.dataset_checksum_match})"
        )
        all_passed = all_passed and result.passed

    if not all_passed:
        print("VERIFY FAILED: parity artifact did not match parity.lock.json.", file=sys.stderr)
        sys.exit(1)
    print("VERIFY PASSED: privileged parity artifact matches parity.lock.json.")


def main() -> None:
    """CLI entry point: `build` writes the parity artifacts/lock, `verify` checks it."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser(
        "build", help="Run the parity corpus and write committed + privileged artifacts."
    )
    build_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing, differing privileged parity artifact "
        "(destroys prior frozen evidence).",
    )

    subparsers.add_parser(
        "verify",
        help="Regenerate the parity corpus results and verify them against parity.lock.json.",
    )

    args = parser.parse_args()
    if args.command == "build":
        _run_build(force=args.force)
    elif args.command == "verify":
        _run_verify()


if __name__ == "__main__":
    main()
