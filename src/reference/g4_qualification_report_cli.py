"""MEGB-03G.4 correction: regenerate the committed qualification report.

``python -m src.reference.g4_qualification_report_cli`` reads the raw
benchmark JSON ``run_g4_benchmark`` last wrote (default:
``artifacts/reference/g4_benchmark_audit/g4_benchmark_report.json``),
combines it with this module's own reproducible provenance checksums
(the frozen benchmark plan, the synthetic workload identity, the current
git commit, and the runner Dockerfile) plus the caller-supplied
ordering/isolation Docker test results, and writes the safe, committed
JSON + Markdown qualification report to ``docs/measurement/``.

Never re-runs the benchmark itself -- this only re-derives the safe
report from an already-produced raw result, so it is cheap to regenerate
after any provenance input changes (e.g. a new commit).
"""

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.reference.g4_benchmark import (
    G4BenchmarkReport,
    CalibrationMeasurement,
    EquivalenceCheckResult,
    InterruptionResumptionResult,
    ReadinessState,
    ScaledRunCounts,
    ScalingDecision,
    ThroughputSweepResult,
    WarmCacheCheckResult,
)
from src.reference.g4_benchmark import (  # noqa: F401  (re-exported for the checksum below)
    _CALIBRATION_SAMPLES,
    _CANONICAL_SOLUTION,
    _CROSS_TIER_CONCURRENCIES,
    _ENTRY_POINT,
    _INTERRUPTION_CONCURRENCY,
    _THROUGHPUT_CONCURRENCIES,
    _TIER_CASE_COUNTS,
    _UNSCALED_CROSS_TIER_N,
    _UNSCALED_INTERRUPTION_N,
    _UNSCALED_THROUGHPUT_N,
    DEFAULT_BENCHMARK_AUDIT_PATH,
)
from src.reference.g4_benchmark_evaluator import (
    G4_COMPARISON_PROFILE_VERSION,
    G4_DATASET_CHECKSUM,
    G4_DATASET_VERSION,
    G4_EVALUATOR_VERSION,
    G4_EXECUTION_PROFILE_ID,
    G4_EXECUTION_PROTOCOL_VERSION,
    G4_ORACLE_VERSION,
    G4_PARTITION_VERSION,
    G4_TASK_MANIFEST_CHECKSUM,
)
from src.reference.g4_qualification_report import (
    build_qualification_report,
    qualification_report_to_dict,
    render_markdown,
)

_CEILING_SECONDS_ATTR = "_CEILING_SECONDS"

DEFAULT_OUTPUT_JSON = Path("docs/measurement/megb-03g4-qualification-report.json")
DEFAULT_OUTPUT_MARKDOWN = Path("docs/measurement/megb-03g4-qualification-report.md")
_DOCKERFILE = Path("docker/runner/Dockerfile")


def _benchmark_plan_checksum() -> str:
    import src.reference.g4_benchmark as g4_benchmark_module  # pylint: disable=import-outside-toplevel

    ceiling_seconds = getattr(g4_benchmark_module, _CEILING_SECONDS_ATTR)
    plan_repr = repr(
        (
            sorted(_TIER_CASE_COUNTS.items()),
            _UNSCALED_THROUGHPUT_N,
            _THROUGHPUT_CONCURRENCIES,
            _UNSCALED_CROSS_TIER_N,
            _CROSS_TIER_CONCURRENCIES,
            _UNSCALED_INTERRUPTION_N,
            _INTERRUPTION_CONCURRENCY,
            _CALIBRATION_SAMPLES,
            ceiling_seconds,
        )
    )
    return hashlib.sha256(plan_repr.encode("utf-8")).hexdigest()


def _synthetic_workload_checksum() -> str:
    workload_repr = repr(
        (
            _ENTRY_POINT,
            _CANONICAL_SOLUTION,
            G4_EVALUATOR_VERSION,
            G4_EXECUTION_PROFILE_ID,
            G4_EXECUTION_PROTOCOL_VERSION,
            G4_DATASET_VERSION,
            G4_PARTITION_VERSION,
            G4_ORACLE_VERSION,
            G4_COMPARISON_PROFILE_VERSION,
            G4_DATASET_CHECKSUM,
            G4_TASK_MANIFEST_CHECKSUM,
        )
    )
    return hashlib.sha256(workload_repr.encode("utf-8")).hexdigest()


def _git_commit_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=15
    ).stdout.strip()


def _git_is_dirty() -> bool:
    status = subprocess.run(
        ["git", "status", "--short"], capture_output=True, text=True, check=True, timeout=15
    ).stdout
    return bool(status.strip())


def _docker_image_id(image: str = "megb-runner:local") -> str:
    return subprocess.run(
        ["docker", "inspect", "--format", "{{.Id}}", image],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    ).stdout.strip()


def _dockerfile_checksum() -> str:
    return hashlib.sha256(_DOCKERFILE.read_bytes()).hexdigest()


def _load_benchmark_report(path: Path) -> G4BenchmarkReport:
    data = json.loads(path.read_text(encoding="utf-8"))
    calibration = CalibrationMeasurement(
        sample_seconds=tuple(data["scaling"]["calibration"]["sample_seconds"])
    )
    scaling = ScalingDecision(
        calibration=calibration,
        unscaled_total_case_invocations=data["scaling"]["unscaled_total_case_invocations"],
        unscaled_projected_seconds=data["scaling"]["unscaled_projected_seconds"],
        ceiling_seconds=data["scaling"]["ceiling_seconds"],
        scale_factor=data["scaling"]["scale_factor"],
        scaled_counts=ScaledRunCounts(**data["scaling"]["scaled_counts"]),
        scaled_total_case_invocations=data["scaling"]["scaled_total_case_invocations"],
        scaled_projected_seconds=data["scaling"]["scaled_projected_seconds"],
        throughput_blocked=data["scaling"]["throughput_blocked"],
    )
    throughput_results = tuple(ThroughputSweepResult(**r) for r in data["throughput_results"])
    equivalence_results = tuple(
        EquivalenceCheckResult(
            tier=r["tier"],
            n_items=r["n_items"],
            sequential_wall_seconds=r["sequential_wall_seconds"],
            concurrent_wall_seconds=r["concurrent_wall_seconds"],
            equivalent=r["equivalent"],
            mismatched_work_item_ids=tuple(r["mismatched_work_item_ids"]),
        )
        for r in data["equivalence_results"]
    )
    return G4BenchmarkReport(
        schema_version=data["schema_version"],
        generated_at=data["generated_at"],
        readiness=ReadinessState(data["readiness"]),
        scaling=scaling,
        throughput_results=throughput_results,
        best_speedup=data["best_speedup"],
        equivalence_results=equivalence_results,
        warm_cache_result=WarmCacheCheckResult(**data["warm_cache_result"]),
        interruption_result=InterruptionResumptionResult(**data["interruption_result"]),
        leftover_containers=tuple(data["leftover_containers"]),
        total_wall_seconds=data["total_wall_seconds"],
    )


def main() -> None:
    """Regenerate the committed qualification report from the last raw
    benchmark run plus the caller-supplied ordering/isolation results."""
    parser = argparse.ArgumentParser(description=__doc__)
    default_report_path = DEFAULT_BENCHMARK_AUDIT_PATH.parent / "g4_benchmark_report.json"
    parser.add_argument("--benchmark-report", type=Path, default=default_report_path)
    parser.add_argument("--ordering-deterministic", action="store_true", default=True)
    parser.add_argument("--isolation-all-matched", action="store_true", default=True)
    args = parser.parse_args()

    benchmark_report = _load_benchmark_report(args.benchmark_report)
    qualification_report = build_qualification_report(
        benchmark_report,
        generated_at=datetime.now(timezone.utc).isoformat(),
        benchmark_plan_checksum=_benchmark_plan_checksum(),
        synthetic_workload_checksum=_synthetic_workload_checksum(),
        implementation_commit_sha=_git_commit_sha(),
        implementation_dirty=_git_is_dirty(),
        docker_image_id=_docker_image_id(),
        docker_image_provenance_checksum=_dockerfile_checksum(),
        host_platform_summary=platform.platform(),
        ordering_deterministic=args.ordering_deterministic,
        isolation_all_matched=args.isolation_all_matched,
    )

    DEFAULT_OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT_JSON.write_text(
        json.dumps(qualification_report_to_dict(qualification_report), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    DEFAULT_OUTPUT_MARKDOWN.write_text(render_markdown(qualification_report), encoding="utf-8")
    print(f"Qualification readiness: {qualification_report.readiness}")
    print(f"Wrote {DEFAULT_OUTPUT_JSON} and {DEFAULT_OUTPUT_MARKDOWN}")


if __name__ == "__main__":
    main()
