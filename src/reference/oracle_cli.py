"""MEGB-03C build/verify CLI: ``python -m src.reference.oracle_cli {build|verify}``.

Kept as its own module — mirroring ``src.reference.partition_cli`` — for the
same reason: it is the one place that needs symbols from the oracle-building
module (``oracle.py``), the oracle lock module (``oracle_lock.py``), and the
MEGB-03B partition/partition-lock modules, and none of those need to import
this CLI glue back.

Before any oracle construction, both ``build`` and ``verify`` first run the
MEGB-03B lock verification (mirroring ``python -m src.reference.partition_cli
verify``, called here as a library function against the same in-memory
corpus reconstruction) and refuse to continue unless both frozen partition
manifests reproduce exactly — the MEGB-03C execution amendment's first
requirement.

Deliberately duplicates some of `partition_cli`'s build/verify scaffolding
rather than sharing a base with it, for the same reason as `oracle_lock.py`:
`partition_cli.py` is already MEGB-03B-accepted code, and consolidating both
CLIs into shared plumbing is flagged as future cleanup, not authorized here.
"""

# pylint: disable=duplicate-code
# See the module docstring above: this intentionally mirrors
# src.reference.partition_cli's build/verify scaffolding rather than
# sharing a base with it.

import argparse
import dataclasses
import json
import sys
from typing import Any

from src.dataset import (
    DatasetProvenance,
    PrivilegedTaskView,
    load_privileged_view,
    load_provenance,
    load_public_view,
)
from src.reference.augmentation import TaskAugmentationResult
from src.reference.oracle import (
    UnresolvedGenerationFailureError,
    build_oracle_artifacts,
    require_release_ready,
)
from src.reference.oracle_lock import (
    COMMITTED_OUTPUT_DIR,
    LOCK_PATH,
    FrozenArtifactConflictError,
    ManifestKindMismatchError,
    load_oracle_lock_file,
    verify_oracle_against_lock,
    write_oracle_lock_file,
    write_privileged_oracle_artifacts,
)
from src.reference.partition import (
    LOCK_PATH as PARTITION_LOCK_PATH,
)
from src.reference.partition import (
    CaseWithProvenance,
    build_primary_experiment_manifest,
    build_reference_validation_manifest,
    gather_eligible_cases_and_args,
)
from src.reference.partition_lock import ManifestKindMismatchError as PartitionKindMismatchError
from src.reference.partition_lock import load_lock_file as load_partition_lock_file
from src.reference.partition_lock import verify_against_lock as verify_partition_against_lock


class PartitionLockVerificationError(RuntimeError):
    """Raised when the MEGB-03B partition lock does not verify cleanly.

    Oracle construction depends on the frozen partition being exactly
    reproducible — building against a partition that has silently drifted
    would produce an oracle keyed to case sets that no longer match the
    committed/privileged partition manifests.
    """


def _load_corpus() -> tuple[
    dict[str, list[CaseWithProvenance]],
    dict[str, TaskAugmentationResult],
    dict[str, dict[str, tuple[Any, ...]]],
    dict[str, PrivilegedTaskView],
    dict[str, str],
    DatasetProvenance,
]:
    """Load the real corpus once; reused for both the partition-lock gate and the oracle build."""
    priv = {t.task_id: t for t in load_privileged_view()}
    pub = {t.task_id: t.prompt for t in load_public_view()}
    provenance = load_provenance()
    cases_by_task, augmentation_results, args_by_task = gather_eligible_cases_and_args(priv, pub)
    return cases_by_task, augmentation_results, args_by_task, priv, pub, provenance


def _require_partition_lock_verified(
    cases_by_task: dict[str, list[CaseWithProvenance]],
    augmentation_results: dict[str, TaskAugmentationResult],
    provenance: DatasetProvenance,
) -> None:
    """MEGB-03C execution amendment, requirement 1: refuse to continue unless
    both MEGB-03B frozen manifests reproduce exactly."""
    if not PARTITION_LOCK_PATH.exists():
        raise PartitionLockVerificationError(
            f"MEGB-03B partition lock not found at {PARTITION_LOCK_PATH} — "
            "cannot construct an oracle without a verified, frozen partition."
        )
    lock = load_partition_lock_file()
    try:
        results = verify_partition_against_lock(
            lock, cases_by_task, provenance, augmentation_results
        )
    except PartitionKindMismatchError as exc:
        raise PartitionLockVerificationError(
            f"MEGB-03B partition lock verification failed: {exc}"
        ) from exc
    if not all(r.passed for r in results):
        raise PartitionLockVerificationError(
            "MEGB-03B partition lock verification failed — refusing to construct "
            f"the oracle against a partition that does not reproduce exactly: {results}"
        )


def _run_build(force: bool) -> None:
    """Verify the MEGB-03B partition lock, then build and freeze the oracle."""
    cases_by_task, augmentation_results, args_by_task, priv, pub, provenance = _load_corpus()
    _require_partition_lock_verified(cases_by_task, augmentation_results, provenance)

    experiment_manifest = build_primary_experiment_manifest(cases_by_task, provenance)
    validation_manifest = build_reference_validation_manifest(cases_by_task, provenance)

    try:
        build_result = build_oracle_artifacts(
            experiment_manifest,
            validation_manifest,
            cases_by_task,
            args_by_task,
            priv,
            pub,
            provenance,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"BUILD FAILED: oracle construction aborted: {exc}", file=sys.stderr)
        sys.exit(1)

    # Diagnostic construction may have completed even with an unresolved
    # original-provenance generation failure recorded explicitly; release
    # (the committed composite manifest, the privileged files, the lock)
    # must refuse to happen at all in that case — checked before writing
    # anything, not only inside write_privileged_oracle_artifacts.
    try:
        require_release_ready(build_result)
    except UnresolvedGenerationFailureError as exc:
        print(f"BUILD FAILED: not release-ready: {exc}", file=sys.stderr)
        sys.exit(1)

    COMMITTED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (COMMITTED_OUTPUT_DIR / "reference_validation_composite_manifest.json").write_text(
        json.dumps(
            dataclasses.asdict(build_result.composite_manifest),
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        lock = write_privileged_oracle_artifacts(
            build_result, augmentation_results, priv, force=force
        )
    except FrozenArtifactConflictError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    write_oracle_lock_file(lock)

    print("development_oracle checksum:", build_result.development_oracle.artifact_checksum)
    print("reference_only_oracle checksum:", build_result.reference_only_oracle.artifact_checksum)
    print(
        "reference_validation_only_oracle checksum:",
        build_result.reference_validation_only_oracle.artifact_checksum,
    )
    print("composite manifest checksum:", build_result.composite_manifest.manifest_checksum)
    print(f"oracle lock file written: {LOCK_PATH}")


def _run_verify() -> None:
    """Verify the MEGB-03B partition lock, then verify the oracle lock."""
    cases_by_task, augmentation_results, args_by_task, priv, pub, provenance = _load_corpus()
    _require_partition_lock_verified(cases_by_task, augmentation_results, provenance)

    if not LOCK_PATH.exists():
        print(f"VERIFY FAILED: oracle lock file not found at {LOCK_PATH}", file=sys.stderr)
        sys.exit(1)

    experiment_manifest = build_primary_experiment_manifest(cases_by_task, provenance)
    validation_manifest = build_reference_validation_manifest(cases_by_task, provenance)

    try:
        build_result = build_oracle_artifacts(
            experiment_manifest,
            validation_manifest,
            cases_by_task,
            args_by_task,
            priv,
            pub,
            provenance,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"VERIFY FAILED: oracle regeneration failed: {exc}", file=sys.stderr)
        sys.exit(1)

    lock = load_oracle_lock_file()
    try:
        results = verify_oracle_against_lock(lock, build_result, augmentation_results, priv)
    except (ManifestKindMismatchError, UnresolvedGenerationFailureError) as exc:
        print(f"VERIFY FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

    all_passed = True
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(
            f"{result.artifact_id}: {status} "
            f"(logical_checksum={result.logical_checksum_match}, "
            f"size={result.size_match}, "
            f"on_disk_present={result.on_disk_present}, "
            f"on_disk_checksum={result.on_disk_checksum_match}, "
            f"on_disk_bytes_match_rebuild={result.on_disk_bytes_match_rebuild}, "
            f"dataset_checksum={result.dataset_checksum_match}, "
            f"augmentation_checksum={result.augmentation_checksum_match}, "
            f"canonical_solution_hashes={result.canonical_solution_hashes_match})"
        )
        all_passed = all_passed and result.passed

    if not all_passed:
        print(
            "VERIFY FAILED: one or more oracle artifacts did not match the lock.",
            file=sys.stderr,
        )
        sys.exit(1)
    print("VERIFY PASSED: all privileged oracle artifacts match oracle.lock.json.")


def main() -> None:
    """CLI entry point: `build` writes the oracle/lock, `verify` checks reproducibility."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser(
        "build", help="Build the oracle artifacts and write committed + privileged output."
    )
    build_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing, differing privileged oracle artifact "
        "(destroys prior frozen evidence).",
    )

    subparsers.add_parser(
        "verify",
        help="Regenerate the oracle and verify it against oracle.lock.json.",
    )

    args = parser.parse_args()
    try:
        if args.command == "build":
            _run_build(force=args.force)
        elif args.command == "verify":
            _run_verify()
    except PartitionLockVerificationError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
