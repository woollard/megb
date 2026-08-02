"""MEGB-03G.4 correction (section 6): the safe, committed qualification report.

Derives a flat, explicitly-allowlisted, self-checksummed report from a
:class:`~src.reference.g4_benchmark.G4BenchmarkReport` plus a small set of
environment/provenance inputs supplied by whoever ran the benchmark. Every
field is either a count, a boolean, a timing/throughput number, a version
label, or a checksum -- never candidate source, an individual synthetic
input/expected output, a real task/case identifier, a privileged path, or
a raw exception/diagnostic payload. Mirrors
``src.reference.reference_audit``'s own explicit-allowlist pattern
(``QUALIFICATION_REPORT_FIELD_NAMES``, tested against
``dataclasses.fields`` the same way ``AUDIT_RECORD_FIELD_NAMES`` is).

Unlike the raw benchmark run log/audit-log directory (gitignored, per
``artifacts/reference/g4_benchmark_audit/`` in ``.gitignore``), this
report's JSON and Markdown renderings are committed: they are the safe,
non-privileged qualification evidence for MEGB-03G.4's readiness
declaration.
"""

import dataclasses
import hashlib
import json
from dataclasses import dataclass

from src.reference.g4_benchmark import G4BenchmarkReport, ReadinessState

G4_QUALIFICATION_REPORT_SCHEMA_VERSION = "megb-03g4-qualification-report-v1"
BENCHMARK_PLAN_VERSION = "megb-03g4-benchmark-plan-v1"


class InvalidQualificationReportError(ValueError):
    """Raised when a :class:`G4QualificationReport`'s fields are internally
    inconsistent, or its self-checksum does not match its own recomputed
    contents."""


def _require_nonempty_str(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or value == "":
        raise InvalidQualificationReportError(
            f"{field_name!r} must be a nonempty string, got {value!r}"
        )


@dataclass(frozen=True)
class G4QualificationReport:  # pylint: disable=too-many-instance-attributes
    """The full, typed, versioned, self-checksummed MEGB-03G.4 qualification
    report. ``report_checksum`` is always recomputed from every other
    field at construction time -- the same auto-compute-or-reject pattern
    ``ReferenceResultCacheKey``/``ReferenceValidationCandidateSetManifest``
    already establish."""

    schema_version: str
    generated_at: str
    benchmark_plan_version: str
    benchmark_plan_checksum: str
    synthetic_workload_version: str
    synthetic_workload_checksum: str
    implementation_commit_sha: str
    implementation_dirty: bool
    docker_image_id: str
    docker_image_provenance_checksum: str
    host_platform_summary: str
    concurrency_levels: tuple[int, ...]
    throughput_sweep_n: int
    cross_tier_n: int
    interruption_n: int
    calibration_sample_count: int
    calibration_mean_seconds: float
    scale_factor: float
    total_wall_seconds: float
    best_speedup: float
    equivalence_all_matched: bool
    equivalence_mismatch_count: int
    ordering_deterministic: bool
    isolation_all_matched: bool
    cache_all_hits_on_warm_run: bool
    resumption_no_gaps: bool
    leftover_containers_found: bool
    readiness: str
    report_checksum: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "schema_version",
            "generated_at",
            "benchmark_plan_version",
            "benchmark_plan_checksum",
            "synthetic_workload_version",
            "synthetic_workload_checksum",
            "implementation_commit_sha",
            "docker_image_id",
            "docker_image_provenance_checksum",
            "host_platform_summary",
            "readiness",
        ):
            _require_nonempty_str(self, field_name)
        if self.schema_version != G4_QUALIFICATION_REPORT_SCHEMA_VERSION:
            raise InvalidQualificationReportError(
                f"schema_version {self.schema_version!r} does not match the version this "
                f"module implements ({G4_QUALIFICATION_REPORT_SCHEMA_VERSION!r})"
            )
        if self.readiness not in {member.value for member in ReadinessState}:
            raise InvalidQualificationReportError(
                f"readiness {self.readiness!r} is not a known ReadinessState value"
            )
        expected_checksum = _compute_report_checksum(self)
        if self.report_checksum and self.report_checksum != expected_checksum:
            raise InvalidQualificationReportError(
                f"report_checksum {self.report_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted qualification report"
            )
        object.__setattr__(self, "report_checksum", expected_checksum)


QUALIFICATION_REPORT_FIELD_NAMES = frozenset(
    field.name for field in dataclasses.fields(G4QualificationReport)
)


def _compute_report_checksum(report: G4QualificationReport) -> str:
    payload = {
        name: getattr(report, name)
        for name in QUALIFICATION_REPORT_FIELD_NAMES
        if name != "report_checksum"
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_qualification_report(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    benchmark_report: G4BenchmarkReport,
    *,
    generated_at: str,
    benchmark_plan_checksum: str,
    synthetic_workload_checksum: str,
    implementation_commit_sha: str,
    implementation_dirty: bool,
    docker_image_id: str,
    docker_image_provenance_checksum: str,
    host_platform_summary: str,
    ordering_deterministic: bool,
    isolation_all_matched: bool,
) -> G4QualificationReport:
    """Derive the safe qualification report from a real
    :class:`G4BenchmarkReport` plus environment/provenance inputs the
    benchmark itself does not know (its own commit SHA, the Docker image
    identity, and the separately-run ordering/isolation Docker tests'
    results)."""
    concurrency_levels = tuple(
        sorted({result.concurrency for result in benchmark_report.throughput_results})
    )
    equivalence_mismatches = sum(
        len(result.mismatched_work_item_ids) for result in benchmark_report.equivalence_results
    )
    return G4QualificationReport(
        schema_version=G4_QUALIFICATION_REPORT_SCHEMA_VERSION,
        generated_at=generated_at,
        benchmark_plan_version=BENCHMARK_PLAN_VERSION,
        benchmark_plan_checksum=benchmark_plan_checksum,
        synthetic_workload_version=benchmark_report.schema_version,
        synthetic_workload_checksum=synthetic_workload_checksum,
        implementation_commit_sha=implementation_commit_sha,
        implementation_dirty=implementation_dirty,
        docker_image_id=docker_image_id,
        docker_image_provenance_checksum=docker_image_provenance_checksum,
        host_platform_summary=host_platform_summary,
        concurrency_levels=concurrency_levels,
        throughput_sweep_n=benchmark_report.scaling.scaled_counts.throughput_sweep_n,
        cross_tier_n=benchmark_report.scaling.scaled_counts.cross_tier_n,
        interruption_n=benchmark_report.scaling.scaled_counts.interruption_n,
        calibration_sample_count=len(benchmark_report.scaling.calibration.sample_seconds),
        calibration_mean_seconds=benchmark_report.scaling.calibration.mean_seconds,
        scale_factor=benchmark_report.scaling.scale_factor,
        total_wall_seconds=benchmark_report.total_wall_seconds,
        best_speedup=benchmark_report.best_speedup,
        equivalence_all_matched=all(
            result.equivalent for result in benchmark_report.equivalence_results
        ),
        equivalence_mismatch_count=equivalence_mismatches,
        ordering_deterministic=ordering_deterministic,
        isolation_all_matched=isolation_all_matched,
        cache_all_hits_on_warm_run=(
            benchmark_report.warm_cache_result.all_cache_hits
            and benchmark_report.warm_cache_result.fresh_execution_keys == 0
        ),
        resumption_no_gaps=benchmark_report.interruption_result.fully_completed_without_gaps,
        leftover_containers_found=bool(benchmark_report.leftover_containers),
        readiness=benchmark_report.readiness.value,
    )


def qualification_report_to_dict(report: G4QualificationReport) -> dict[str, object]:
    """Serialize a qualification report. Output keys are exactly
    :data:`QUALIFICATION_REPORT_FIELD_NAMES` -- nothing more, nothing less."""
    return {name: getattr(report, name) for name in QUALIFICATION_REPORT_FIELD_NAMES}


def qualification_report_from_dict(data: dict[str, object]) -> G4QualificationReport:
    """Inverse of :func:`qualification_report_to_dict`."""
    fields = {name: data[name] for name in QUALIFICATION_REPORT_FIELD_NAMES}
    fields["concurrency_levels"] = tuple(fields["concurrency_levels"])  # type: ignore[arg-type]
    return G4QualificationReport(**fields)  # type: ignore[arg-type]


def render_markdown(report: G4QualificationReport) -> str:
    """A concise, human-readable Markdown rendering of the same safe
    fields the JSON report carries -- nothing else."""
    lines = [
        "# MEGB-03G.4 Qualification Report",
        "",
        f"- **Readiness:** `{report.readiness}`",
        f"- **Generated at:** {report.generated_at}",
        f"- **Schema version:** `{report.schema_version}`",
        f"- **Report checksum:** `{report.report_checksum}`",
        "",
        "## Provenance",
        "",
        (
            f"- Benchmark plan: `{report.benchmark_plan_version}` "
            f"(checksum `{report.benchmark_plan_checksum}`)"
        ),
        (
            f"- Synthetic workload: `{report.synthetic_workload_version}` "
            f"(checksum `{report.synthetic_workload_checksum}`)"
        ),
        f"- Implementation commit: `{report.implementation_commit_sha}`"
        + (" (dirty working tree)" if report.implementation_dirty else ""),
        (
            f"- Docker image: `{report.docker_image_id}` "
            f"(provenance `{report.docker_image_provenance_checksum}`)"
        ),
        f"- Host/platform: {report.host_platform_summary}",
        "",
        "## Configuration",
        "",
        f"- Concurrency levels: {list(report.concurrency_levels)}",
        f"- Throughput-sweep N: {report.throughput_sweep_n}",
        f"- Cross-tier N: {report.cross_tier_n}",
        f"- Interruption N: {report.interruption_n}",
        f"- Calibration samples: {report.calibration_sample_count}",
        f"- Calibration mean: {report.calibration_mean_seconds:.4f}s",
        f"- Scale factor applied: {report.scale_factor:.4f}",
        "",
        "## Results",
        "",
        f"- Total wall-clock: {report.total_wall_seconds:.2f}s",
        f"- Best speedup: {report.best_speedup:.3f}x",
        f"- Equivalence: all matched = {report.equivalence_all_matched} "
        f"(mismatches: {report.equivalence_mismatch_count})",
        f"- Ordering deterministic: {report.ordering_deterministic}",
        f"- Isolation held: {report.isolation_all_matched}",
        f"- Warm-cache all hits: {report.cache_all_hits_on_warm_run}",
        f"- Resumption gap-free: {report.resumption_no_gaps}",
        f"- Leftover containers found: {report.leftover_containers_found}",
        "",
    ]
    return "\n".join(lines)
