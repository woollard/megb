"""MEGB-03B build/verify CLI: ``python -m src.reference.partition_cli {build|verify}``.

Kept as its own module (rather than living in ``partition.py`` or
``partition_lock.py``) specifically to avoid a cyclic import: it is the one
place that needs symbols from both the manifest-building module
(``partition.py``) and the privileged-artifact lock module
(``partition_lock.py``), and those two never need to import each other's CLI
glue.
"""

import argparse
import json
import sys

from src.reference.partition import (
    COMMITTED_OUTPUT_DIR,
    LOCK_PATH,
    build_primary_experiment_manifest,
    build_reference_validation_manifest,
    load_real_corpus_inputs,
    redact_primary_experiment_manifest,
    render_validation_report,
    validate_primary_experiment_manifest,
)
from src.reference.partition_lock import (
    FrozenArtifactConflictError,
    ManifestKindMismatchError,
    load_lock_file,
    verify_against_lock,
    write_lock_file,
    write_privileged_artifacts,
)


def _run_build(force: bool) -> None:
    """Build both manifests, write the committed (redacted + report) and
    privileged (full manifests + lock) artifacts."""
    cases_by_task, augmentation_results, provenance = load_real_corpus_inputs()

    validation_manifest = build_reference_validation_manifest(cases_by_task, provenance)
    experiment_manifest = build_primary_experiment_manifest(cases_by_task, provenance)
    checks = validate_primary_experiment_manifest(experiment_manifest)

    # Determinism check: rebuild from scratch, same inputs.
    rebuild_manifest = build_primary_experiment_manifest(cases_by_task, provenance)
    # Seed-sensitivity check: same inputs, different seed.
    reseeded_manifest = build_primary_experiment_manifest(
        cases_by_task, provenance, partition_seed="megb-03b-seed-v1-ALTERNATE"
    )

    COMMITTED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    (COMMITTED_OUTPUT_DIR / "primary_experiment_task_manifest_redacted.json").write_text(
        json.dumps(
            redact_primary_experiment_manifest(experiment_manifest),
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    (COMMITTED_OUTPUT_DIR / "partition_validation_report.md").write_text(
        render_validation_report(
            experiment_manifest,
            validation_manifest,
            checks,
            rebuild_checksum=rebuild_manifest.manifest_checksum,
            reseeded_checksum=reseeded_manifest.manifest_checksum,
        ),
        encoding="utf-8",
    )

    try:
        lock = write_privileged_artifacts(
            experiment_manifest,
            validation_manifest,
            augmentation_results,
            provenance,
            force=force,
        )
    except FrozenArtifactConflictError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    write_lock_file(lock)

    print("checks:", checks)
    print("experiment manifest checksum:", experiment_manifest.manifest_checksum)
    print("validation manifest checksum:", validation_manifest.manifest_checksum)
    print(f"lock file written: {LOCK_PATH}")


def _run_verify() -> None:
    """Regenerate both manifests and verify them against the committed lock file.

    Never prints privileged case contents — only checksums, counts, and
    pass/fail booleans. Exits nonzero on any mismatch.
    """
    if not LOCK_PATH.exists():
        print(f"VERIFY FAILED: lock file not found at {LOCK_PATH}", file=sys.stderr)
        sys.exit(1)

    lock = load_lock_file()
    cases_by_task, augmentation_results, provenance = load_real_corpus_inputs()

    try:
        results = verify_against_lock(lock, cases_by_task, provenance, augmentation_results)
    except ManifestKindMismatchError as exc:
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
            f"augmentation_checksum={result.augmentation_checksum_match})"
        )
        all_passed = all_passed and result.passed

    if not all_passed:
        print("VERIFY FAILED: one or more artifacts did not match the lock.", file=sys.stderr)
        sys.exit(1)
    print("VERIFY PASSED: all privileged artifacts match partition.lock.json.")


def main() -> None:
    """CLI entry point: `build` writes the manifests/lock, `verify` checks reproducibility."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser(
        "build", help="Build both manifests and write committed + privileged artifacts."
    )
    build_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing, differing privileged artifact "
        "(destroys prior frozen evidence).",
    )

    subparsers.add_parser(
        "verify",
        help="Regenerate both manifests and verify them against partition.lock.json.",
    )

    args = parser.parse_args()
    if args.command == "build":
        _run_build(force=args.force)
    elif args.command == "verify":
        _run_verify()


if __name__ == "__main__":
    main()
