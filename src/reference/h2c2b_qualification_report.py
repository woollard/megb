"""MEGB-03H.2C.2B: the safe, committed real-Docker telemetry qualification
report.

Mirrors ``g4_qualification_report.py``'s own self-checksummed, versioned,
explicitly-allowlisted pattern. Every field is a count, boolean, timing/
overhead number, version/identity label, or checksum -- never candidate
source, an individual invocation's input/output, raw stdout/stderr, a
container id/name, a cgroup or filesystem path, a hostname/username, a
Docker socket path, an unrestricted exception message, a per-invocation
log, or any privileged artifact path/content. The raw per-invocation
diagnostic log this report is derived from is gitignored and run-scoped,
never committed.
"""

# This module's error class, nonempty-string validator, and self-checksum
# construction/rejection pattern intentionally mirror
# g4_qualification_report.py's own already-established shape -- both are
# the same safe-report pattern applied to a different measurement.
# Expected and accepted, not a defect.
# pylint: disable=duplicate-code

import dataclasses
import hashlib
import json
from dataclasses import dataclass

H2C2B_QUALIFICATION_REPORT_SCHEMA_VERSION = "megb-03h2c2b-qualification-report-v1"

_KNOWN_READINESS_VALUES = frozenset(
    {
        "TELEMETRY_READY_FOR_MEGB_03H3",
        "BLOCKED_TELEMETRY_OVERHEAD",
        "BLOCKED_NONINTERFERENCE_OR_CLEANUP",
        "BLOCKED_MEASUREMENT_VALIDITY",
        "BLOCKED_EXACT_TELEMETRY_UNAVAILABLE_NATIVE_LINUX_OR_AWS_REQUIRED",
        "BLOCKED_H5_PROJECTION_CEILING",
        "NOT_QUALIFYING_DIAGNOSTIC_PILOT_ONLY",
    }
)


class InvalidQualificationReportError(ValueError):
    """Raised when a :class:`H2C2BQualificationReport`'s fields are
    internally inconsistent, or its self-checksum does not match its own
    recomputed contents."""


def _require_nonempty_str(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or value == "":
        raise InvalidQualificationReportError(
            f"{field_name!r} must be a nonempty string, got {value!r}"
        )


@dataclass(frozen=True)
class ConcurrencyOverheadStat:
    """One concurrency level's paired-overhead aggregate -- never a raw
    per-invocation timing series, only the summary statistics."""

    concurrency: int
    pair_count: int
    mean_overhead_ms: float
    p99_overhead_ms: float

    def __post_init__(self) -> None:
        if self.concurrency < 1:
            raise InvalidQualificationReportError(
                f"concurrency must be >= 1, got {self.concurrency!r}"
            )
        if self.pair_count < 1:
            raise InvalidQualificationReportError(
                f"pair_count must be >= 1, got {self.pair_count!r}"
            )


def _concurrency_overhead_stat_to_dict(stat: ConcurrencyOverheadStat) -> dict[str, object]:
    return dataclasses.asdict(stat)


def _concurrency_overhead_stat_from_dict(data: dict[str, object]) -> ConcurrencyOverheadStat:
    return ConcurrencyOverheadStat(
        concurrency=int(data["concurrency"]),  # type: ignore[call-overload]
        pair_count=int(data["pair_count"]),  # type: ignore[call-overload]
        mean_overhead_ms=float(data["mean_overhead_ms"]),  # type: ignore[arg-type]
        p99_overhead_ms=float(data["p99_overhead_ms"]),  # type: ignore[arg-type]
    )


@dataclass(frozen=True)
class StageProjectionSummary:
    """One (stage, scenario) pair's projected runtime against its own
    frozen hard ceiling -- derived entirely from measured overhead plus
    the already-accepted formula/ceilings, never a raw log."""

    stage: str
    scenario: str
    projected_seconds: float
    hard_ceiling_seconds: float
    within_ceiling: bool

    def __post_init__(self) -> None:
        _require_nonempty_str(self, "stage")
        _require_nonempty_str(self, "scenario")


def _stage_projection_to_dict(projection: StageProjectionSummary) -> dict[str, object]:
    return dataclasses.asdict(projection)


def _stage_projection_from_dict(data: dict[str, object]) -> StageProjectionSummary:
    return StageProjectionSummary(
        stage=str(data["stage"]),
        scenario=str(data["scenario"]),
        projected_seconds=float(data["projected_seconds"]),  # type: ignore[arg-type]
        hard_ceiling_seconds=float(data["hard_ceiling_seconds"]),  # type: ignore[arg-type]
        within_ceiling=bool(data["within_ceiling"]),
    )


@dataclass(frozen=True)
class H2C2BQualificationReport:  # pylint: disable=too-many-instance-attributes
    """The full, typed, versioned, self-checksummed MEGB-03H.2C.2B
    qualification report. ``report_checksum`` is always recomputed from
    every other field at construction time -- the same auto-compute-or-
    reject pattern already established throughout this project."""

    schema_version: str
    generated_at: str
    run_identity: str
    qualifying: bool
    plan_sha256: str
    plan_git_blob_sha1: str
    harness_version: str
    implementation_commit_sha: str
    implementation_dirty: bool
    docker_image_id: str
    docker_image_provenance_checksum: str
    host_os_family: str
    host_architecture: str
    host_kernel_release: str
    host_docker_server_version: str
    host_cgroup_driver: str
    memory_preferred_method: str
    memory_actual_selected_method: str
    memory_selection_disposition: str
    memory_quality: str
    memory_unavailable_reason: str
    process_count_preferred_method: str
    process_count_actual_selected_method: str
    process_count_selection_disposition: str
    process_count_quality: str
    process_count_unavailable_reason: str
    late_peak_quality: str
    late_peak_terminal_coverage: str
    late_peak_value_matches_expected_minimum: bool
    overhead_by_concurrency: tuple[ConcurrencyOverheadStat, ...]
    primary_overhead_gate_ms: float
    primary_overhead_gate_passed: bool
    status_matrix_scenarios_tested: int
    status_matrix_all_statuses_agree: bool
    status_matrix_all_return_values_agree: bool
    leftover_containers_found: bool
    stage_projections: tuple[StageProjectionSummary, ...]
    readiness: str
    blocking_reasons: tuple[str, ...]
    report_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        for field_name in (
            "schema_version",
            "generated_at",
            "run_identity",
            "plan_sha256",
            "plan_git_blob_sha1",
            "harness_version",
            "implementation_commit_sha",
            "docker_image_id",
            "docker_image_provenance_checksum",
            "host_os_family",
            "host_architecture",
            "host_kernel_release",
            "host_docker_server_version",
            "memory_preferred_method",
            "memory_actual_selected_method",
            "memory_selection_disposition",
            "process_count_preferred_method",
            "process_count_actual_selected_method",
            "process_count_selection_disposition",
            "late_peak_terminal_coverage",
            "readiness",
        ):
            _require_nonempty_str(self, field_name)
        if self.schema_version != H2C2B_QUALIFICATION_REPORT_SCHEMA_VERSION:
            raise InvalidQualificationReportError(
                f"schema_version {self.schema_version!r} does not match the version this "
                f"module implements ({H2C2B_QUALIFICATION_REPORT_SCHEMA_VERSION!r})"
            )
        if self.readiness not in _KNOWN_READINESS_VALUES:
            raise InvalidQualificationReportError(
                f"readiness {self.readiness!r} is not a known readiness classification"
            )
        if not self.overhead_by_concurrency:
            raise InvalidQualificationReportError(
                "overhead_by_concurrency must contain at least one entry"
            )
        if not self.stage_projections:
            raise InvalidQualificationReportError(
                "stage_projections must contain at least one entry"
            )
        if self.status_matrix_scenarios_tested < 1:
            raise InvalidQualificationReportError(
                "status_matrix_scenarios_tested must be >= 1"
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
    field.name for field in dataclasses.fields(H2C2BQualificationReport)
)


def _report_payload(report: H2C2BQualificationReport) -> dict[str, object]:
    payload: dict[str, object] = {}
    for name in QUALIFICATION_REPORT_FIELD_NAMES:
        if name == "report_checksum":
            continue
        value = getattr(report, name)
        if name == "overhead_by_concurrency":
            payload[name] = [_concurrency_overhead_stat_to_dict(v) for v in value]
        elif name == "stage_projections":
            payload[name] = [_stage_projection_to_dict(v) for v in value]
        else:
            payload[name] = value
    return payload


def _compute_report_checksum(report: H2C2BQualificationReport) -> str:
    canonical = json.dumps(_report_payload(report), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def qualification_report_to_dict(report: H2C2BQualificationReport) -> dict[str, object]:
    """Serialize a qualification report. Output keys are exactly
    :data:`QUALIFICATION_REPORT_FIELD_NAMES` -- nothing more, nothing
    less."""
    payload = _report_payload(report)
    payload["report_checksum"] = report.report_checksum
    return payload


def qualification_report_from_dict(data: dict[str, object]) -> H2C2BQualificationReport:
    """Inverse of :func:`qualification_report_to_dict`."""
    fields = {name: data[name] for name in QUALIFICATION_REPORT_FIELD_NAMES}
    raw_overhead: list[dict[str, object]] = data[  # type: ignore[assignment]
        "overhead_by_concurrency"
    ]
    raw_stages: list[dict[str, object]] = data["stage_projections"]  # type: ignore[assignment]
    fields["overhead_by_concurrency"] = tuple(
        _concurrency_overhead_stat_from_dict(v) for v in raw_overhead
    )
    fields["stage_projections"] = tuple(_stage_projection_from_dict(v) for v in raw_stages)
    fields["blocking_reasons"] = tuple(fields["blocking_reasons"])  # type: ignore[arg-type]
    return H2C2BQualificationReport(**fields)  # type: ignore[arg-type]


def render_markdown(report: H2C2BQualificationReport) -> str:
    """A concise, human-readable Markdown rendering of the same safe
    fields the JSON report carries -- nothing else."""
    lines = [
        "# MEGB-03H.2C.2B Real-Docker Telemetry Qualification Report",
        "",
        f"- **Readiness:** `{report.readiness}`",
        f"- **Run identity:** `{report.run_identity}` (qualifying: {report.qualifying})",
        f"- **Generated at:** {report.generated_at}",
        f"- **Schema version:** `{report.schema_version}`",
        f"- **Report checksum:** `{report.report_checksum}`",
        "",
        "## Provenance",
        "",
        f"- Frozen plan: sha256 `{report.plan_sha256}`, git blob `{report.plan_git_blob_sha1}`",
        f"- Harness version: `{report.harness_version}`",
        f"- Implementation commit: `{report.implementation_commit_sha}`"
        + (" (dirty working tree)" if report.implementation_dirty else ""),
        (
            f"- Docker image: `{report.docker_image_id}` "
            f"(provenance `{report.docker_image_provenance_checksum}`)"
        ),
        (
            f"- Host: {report.host_os_family}/{report.host_architecture}, "
            f"kernel {report.host_kernel_release}, Docker server "
            f"{report.host_docker_server_version}, cgroup driver "
            f"{report.host_cgroup_driver or '(unresolved)'}"
        ),
        "",
        "## Method / capability / quality",
        "",
        (
            f"- Memory: preferred `{report.memory_preferred_method}` -> selected "
            f"`{report.memory_actual_selected_method}` ({report.memory_selection_disposition}), "
            f"quality `{report.memory_quality}`, unavailable reason "
            f"`{report.memory_unavailable_reason}`"
        ),
        (
            f"- Process count: preferred `{report.process_count_preferred_method}` -> selected "
            f"`{report.process_count_actual_selected_method}` "
            f"({report.process_count_selection_disposition}), quality "
            f"`{report.process_count_quality}`, unavailable reason "
            f"`{report.process_count_unavailable_reason}`"
        ),
        (
            f"- late_peak: quality `{report.late_peak_quality}`, terminal coverage "
            f"`{report.late_peak_terminal_coverage}`, value matches expected minimum: "
            f"{report.late_peak_value_matches_expected_minimum}"
        ),
        "",
        "## Overhead",
        "",
        f"- Primary gate: <= {report.primary_overhead_gate_ms}ms/invocation, "
        f"passed: {report.primary_overhead_gate_passed}",
    ]
    for stat in report.overhead_by_concurrency:
        lines.append(
            f"  - concurrency={stat.concurrency}: n={stat.pair_count} pairs, "
            f"mean={stat.mean_overhead_ms:.3f}ms, p99={stat.p99_overhead_ms:.3f}ms"
        )
    lines += [
        "",
        "## Noninterference and cleanup",
        "",
        f"- Status-matrix scenarios tested: {report.status_matrix_scenarios_tested}",
        f"- All statuses agree: {report.status_matrix_all_statuses_agree}",
        f"- All return values agree: {report.status_matrix_all_return_values_agree}",
        f"- Leftover containers found: {report.leftover_containers_found}",
        "",
        "## Stage projections (H.3-H.6)",
        "",
    ]
    for projection in report.stage_projections:
        lines.append(
            f"- {projection.stage}/{projection.scenario}: "
            f"{projection.projected_seconds:.1f}s / ceiling {projection.hard_ceiling_seconds:.0f}s "
            f"(within ceiling: {projection.within_ceiling})"
        )
    lines += ["", "## Blocking reasons", ""]
    if report.blocking_reasons:
        lines += [f"- {reason}" for reason in report.blocking_reasons]
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "H2C2B_QUALIFICATION_REPORT_SCHEMA_VERSION",
    "InvalidQualificationReportError",
    "ConcurrencyOverheadStat",
    "StageProjectionSummary",
    "H2C2BQualificationReport",
    "QUALIFICATION_REPORT_FIELD_NAMES",
    "qualification_report_to_dict",
    "qualification_report_from_dict",
    "render_markdown",
]
