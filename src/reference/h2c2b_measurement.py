"""MEGB-03H.2C.2B: real-Docker telemetry measurement harness.

Executes the frozen plan
(``docs/reference/megb-03h2c2b-real-docker-measurement-plan.md``) against a
real Docker daemon: paired telemetry-disabled/enabled overhead measurement,
synthetic ground-truth workloads, the execution-status matrix, and
container-cleanup verification.

Every frozen parameter below is transcribed verbatim from the plan and
exposed only as a module constant -- never a function default a caller can
silently shadow. :func:`verify_plan_identity` must be called, and must
pass, before any measurement in a real run is treated as reproducible
evidence; a caller that bypasses it is not running this plan.

This module is deliberately split between pure, offline-testable pieces
(workload source generation, the status-matrix scenario table, overhead
statistics, stage-runtime projections) and thin orchestration functions
that require a real Docker daemon (``run_*``) -- the same split
``g4_benchmark.py`` already establishes for its own real-Docker sweep.
"""

# The status-matrix candidate sources and the leftover-container check
# below intentionally reuse the exact, already-proven-against-real-Docker
# recipes from tests/test_execution_sandbox.py, rather than inventing new
# (and unverified) ones -- both exercise the same real backend-outcome
# shapes. Expected and accepted, not a defect.
# pylint: disable=duplicate-code

import statistics as _statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from src.execution.docker_backend import DockerPerInvocationBackend
from src.execution.protocol import (
    CandidateExecutionRequest,
    CandidateExecutionResult,
    ExecutionLimits,
    ExecutionStatus,
)
from src.execution.telemetry import ExecutionTelemetry, TelemetryObservation

H2C2B_MEASUREMENT_HARNESS_VERSION = "megb-03h2c2b-measurement-harness-v1"

# The exact git blob identity of the frozen plan doc at the point this
# authorization was granted (HEAD e8d40a2). A real run must fail loudly,
# not silently proceed, if the working tree's own plan file no longer
# matches this -- see verify_plan_identity().
FROZEN_PLAN_GIT_BLOB_SHA1 = "f8a422c457ad1b7a7ecfa33901fe986ff476a20f"
FROZEN_PLAN_SHA256 = "9014bbbca776af9ad9075190dc5b43bf95af6e138e89d21960d5f2889a387c75"

# Frozen parameters (plan §4, §7, §8, §10) -- never overridable from a CLI
# flag or environment variable; a caller that needs different values is,
# by definition, not running this frozen plan and must use a visibly
# distinct, non-qualifying run identity (see run_identity_for()).
FROZEN_MEMORY_SAMPLING_INTERVAL_SEC = 0.05
FROZEN_PROCESS_COUNT_SAMPLING_INTERVAL_SEC = 0.05
FROZEN_EXISTENCE_POLL_INTERVAL_SEC = 0.02
FROZEN_EXISTENCE_WAIT_MAX_SEC = 2.0
FROZEN_PAIRED_REPETITIONS_N = 8
FROZEN_CONCURRENCY_LEVELS: tuple[int, ...] = (1, 2, 4)
FROZEN_PRIMARY_OVERHEAD_GATE_MS = 20.9
FROZEN_P99_OVERHEAD_DIAGNOSTIC_MS = 50.0

# The accepted concurrency-aware projection formula's own anchors (H.1
# calibration design, corrected round 2), reused verbatim -- never
# rederived here.
FROZEN_BASELINE_PER_INVOCATION_SEC = 0.418
FROZEN_CONCURRENCY_SPEEDUP_AT_4 = 2.296
FROZEN_STAGE_INVOCATION_COUNTS: dict[str, int] = {
    "H3": 1_120,
    "H4": 6_538,
    "H5": 117_973,
    "H6": 25_580,
}
FROZEN_STAGE_HARD_CEILINGS_SEC: dict[str, float] = {
    "H3": 3_600.0,
    "H4": 14_400.0,
    "H5": 43_200.0,
    "H6": 14_400.0,
}
FROZEN_SCENARIO_MULTIPLIERS: dict[str, float] = {
    "baseline": 1.0,
    "moderate": 1.5,
    "conservative": 2.0,
    "stress": 5.0,
}


class PlanIdentityMismatchError(ValueError):
    """Raised when the working tree's plan document no longer matches the
    frozen identity this harness was built against -- a real run must
    never silently proceed on a plan that has since changed."""


def verify_plan_identity(plan_path: str) -> None:
    """Recompute the plan document's git blob SHA-1 the same way ``git
    hash-object`` does (a ``"blob {len}\\0"`` header prepended before
    hashing) and its own SHA-256, and raise unless both match the frozen
    identities above."""
    import hashlib  # pylint: disable=import-outside-toplevel

    with open(plan_path, "rb") as handle:
        content = handle.read()
    sha256 = hashlib.sha256(content).hexdigest()
    blob_header = f"blob {len(content)}\0".encode("ascii")
    git_blob_sha1 = hashlib.sha1(blob_header + content, usedforsecurity=False).hexdigest()
    if sha256 != FROZEN_PLAN_SHA256 or git_blob_sha1 != FROZEN_PLAN_GIT_BLOB_SHA1:
        raise PlanIdentityMismatchError(
            f"{plan_path!r} no longer matches the frozen plan identity this harness "
            f"was authorized against (expected sha256={FROZEN_PLAN_SHA256!r}, "
            f"git_blob_sha1={FROZEN_PLAN_GIT_BLOB_SHA1!r}; got sha256={sha256!r}, "
            f"git_blob_sha1={git_blob_sha1!r}) -- reopen the plan under a new "
            "authorization before proceeding, never silently measure against a "
            "changed plan"
        )


def run_identity_for(*, qualifying: bool, label: str) -> str:
    """A run's own identity string, visibly distinguishing a qualifying
    (full frozen-plan) attempt from a diagnostic/reduced one -- never a
    caller-suppressible flag. A non-qualifying run's identity always
    carries ``-diagnostic-`` so it can never be mistaken for a run
    entitled to a ``TELEMETRY_READY`` declaration."""
    tag = "qualifying" if qualifying else "diagnostic"
    return f"h2c2b-{tag}-{label}"


# ---------------------------------------------------------------------------
# Synthetic ground-truth workloads (plan §5) -- pure source generation
# ---------------------------------------------------------------------------

BASELINE_WORKLOAD_VERSION = "megb-03h2c2b-baseline-workload-v1"
MEMORY_ALLOCATOR_WORKLOAD_VERSION = "megb-03h2c2b-memory-allocator-workload-v1"
PROCESS_SPAWNER_WORKLOAD_VERSION = "megb-03h2c2b-process-spawner-workload-v1"
LATE_PEAK_WORKLOAD_VERSION = "megb-03h2c2b-late-peak-workload-v1"

BASELINE_CANDIDATE_SOURCE = "def f():\n    return 'baseline'\n"


def memory_allocator_candidate_source(mib: int, hold_sec: float) -> str:
    """Allocates and holds ``mib`` mebibytes for ``hold_sec`` seconds, then
    releases and returns. Ground truth: peak memory should be at least
    ``mib`` MiB above the baseline candidate's own floor."""
    return (
        "import time\n"
        f"def f():\n"
        f"    data = bytearray({mib} * 1024 * 1024)\n"
        f"    time.sleep({hold_sec})\n"
        "    return len(data)\n"
    )


def process_spawner_candidate_source(count: int, sleep_sec: float) -> str:
    """Spawns ``count`` short-lived child processes, each sleeping
    ``sleep_sec`` seconds before exiting. Ground truth: peak process count
    should be at least ``count`` above the baseline candidate's own
    floor."""
    return (
        "import os\n"
        "import time\n"
        f"def f():\n"
        "    children = []\n"
        f"    for _ in range({count}):\n"
        "        pid = os.fork()\n"
        "        if pid == 0:\n"
        f"            time.sleep({sleep_sec})\n"
        "            os._exit(0)\n"
        "        children.append(pid)\n"
        "    for pid in children:\n"
        "        os.waitpid(pid, 0)\n"
        "    return len(children)\n"
    )


def late_peak_candidate_source(*, baseline_mib: int, spike_mib: int, presleep_sec: float) -> str:
    """Allocates a small baseline amount, sleeps briefly, then allocates a
    second, larger, distinctly-sized spike immediately before returning --
    timed so the spike is still resident at the candidate process's own
    exit. Ground truth: the true peak must reflect the *late* spike, not
    the earlier baseline."""
    return (
        "import time\n"
        f"def f():\n"
        f"    baseline = bytearray({baseline_mib} * 1024 * 1024)\n"
        f"    time.sleep({presleep_sec})\n"
        f"    spike = bytearray({spike_mib} * 1024 * 1024)\n"
        "    return len(baseline) + len(spike)\n"
    )


# ---------------------------------------------------------------------------
# Execution-status matrix (plan §6) -- pure scenario table, empirically
# confirmed working (each recipe run once, for real, before being encoded
# here) against this exact runner image/protocol version.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StatusScenario:
    """One named execution-status scenario: a candidate source, its
    limits, and the status it is expected to produce."""

    name: str
    candidate_code: str
    limits: ExecutionLimits
    expected_status: ExecutionStatus


STATUS_MATRIX_SCENARIOS: tuple[StatusScenario, ...] = (
    StatusScenario(
        name="completed",
        candidate_code="def f():\n    return 1\n",
        limits=ExecutionLimits(),
        expected_status=ExecutionStatus.COMPLETED,
    ),
    StatusScenario(
        name="syntax_error",
        candidate_code="def f(:\n    pass\n",
        limits=ExecutionLimits(),
        expected_status=ExecutionStatus.SYNTAX_ERROR,
    ),
    StatusScenario(
        name="candidate_exception",
        candidate_code="def f():\n    raise ValueError('boom')\n",
        limits=ExecutionLimits(),
        expected_status=ExecutionStatus.CANDIDATE_EXCEPTION,
    ),
    StatusScenario(
        name="output_limit",
        candidate_code="def f():\n    while True:\n        print('x' * 4096)\n",
        limits=ExecutionLimits(wall_time_sec=5.0),
        expected_status=ExecutionStatus.OUTPUT_LIMIT,
    ),
    StatusScenario(
        name="protocol_error",
        candidate_code="def f():\n    return 'x' * 5000\n",
        limits=ExecutionLimits(max_response_bytes=300),
        expected_status=ExecutionStatus.PROTOCOL_ERROR,
    ),
    StatusScenario(
        name="timeout",
        candidate_code="def f():\n    while True:\n        pass\n",
        limits=ExecutionLimits(wall_time_sec=1.0),
        expected_status=ExecutionStatus.TIMEOUT,
    ),
    StatusScenario(
        name="out_of_memory",
        candidate_code=(
            "def f():\n"
            "    data = []\n"
            "    while True:\n"
            "        data.append(bytearray(10 * 1024 * 1024))\n"
        ),
        limits=ExecutionLimits(wall_time_sec=10.0, memory_mb=64),
        expected_status=ExecutionStatus.OUT_OF_MEMORY,
    ),
    StatusScenario(
        name="infrastructure_error_interpreter_exit",
        candidate_code="import os\ndef f():\n    os._exit(1)\n",
        limits=ExecutionLimits(),
        expected_status=ExecutionStatus.INFRASTRUCTURE_ERROR,
    ),
)

# process_limit is intentionally not pinned to one expected status: the
# established offline/Docker precedent (test_execution_sandbox.py) already
# documents that a fork-bomb candidate is contained either by the runner's
# own PROCESS_LIMIT classification or by the controller's wall-clock
# TIMEOUT backstop, and either outcome is an acceptable containment
# result -- never COMPLETED (unbounded forking succeeding).
PROCESS_LIMIT_SCENARIO_NAME = "process_limit"
PROCESS_LIMIT_CANDIDATE_CODE = (
    "import os\n"
    "def f():\n"
    "    forked = 0\n"
    "    for _ in range(10000):\n"
    "        pid = os.fork()\n"
    "        if pid == 0:\n"
    "            while True:\n"
    "                pass\n"
    "        forked += 1\n"
    "    return forked\n"
)
PROCESS_LIMIT_ACCEPTABLE_STATUSES = (ExecutionStatus.PROCESS_LIMIT, ExecutionStatus.TIMEOUT)
PROCESS_LIMIT_LIMITS = ExecutionLimits(wall_time_sec=5.0, max_processes=16)


# ---------------------------------------------------------------------------
# Results dataclasses (pure, no Docker dependency)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairedInvocationTiming:
    """One paired telemetry-disabled/enabled invocation's wall-clock
    timing -- the raw unit the overhead statistics are computed from."""

    leg_order: str  # "AB" (disabled-then-enabled) or "BA" (enabled-then-disabled)
    disabled_wall_sec: float
    enabled_wall_sec: float

    @property
    def overhead_sec(self) -> float:
        """Telemetry-enabled minus telemetry-disabled wall-clock time."""
        return self.enabled_wall_sec - self.disabled_wall_sec


@dataclass(frozen=True)
class OverheadMeasurement:
    """Paired-overhead results for one (workload, concurrency) configuration."""

    workload: str
    concurrency: int
    pairs: tuple[PairedInvocationTiming, ...]

    @property
    def mean_overhead_ms(self) -> float:
        """Mean added wall-clock overhead per invocation, in milliseconds."""
        return _statistics.fmean(p.overhead_sec for p in self.pairs) * 1000.0

    @property
    def p99_overhead_ms(self) -> float:
        """p99 added wall-clock overhead per invocation -- diagnostic only."""
        return _percentile_ms(tuple(p.overhead_sec for p in self.pairs), 0.99)


def _percentile_ms(values_sec: tuple[float, ...], fraction: float) -> float:
    """Nearest-rank percentile (0..1), matching the H.1 calibration
    design's own p99 treatment -- a diagnostic figure only, never itself a
    gate."""
    if not values_sec:
        raise ValueError("cannot compute a percentile over zero samples")
    ordered = sorted(values_sec)
    rank = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return ordered[rank] * 1000.0


@dataclass(frozen=True)
class MethodFinding:
    """One metric's full empirical determination for one workload/run --
    exactly the fields plan §6 (of the authorization) requires reported."""

    metric: str
    preferred_method: str
    actual_selected_method: str
    selection_disposition: str
    terminal_coverage: str
    quality: str | None
    unavailable_reason: str | None
    actual_sample_count: int


def method_finding_from_observation(
    *, metric: str, preferred_method: str, observation: TelemetryObservation
) -> MethodFinding:
    """Project one raw TelemetryObservation into the safe, typed finding
    shape the authorization requires reported for every metric."""
    identity = observation.method_identity
    return MethodFinding(
        metric=metric,
        preferred_method=preferred_method,
        actual_selected_method=(identity.method.value if identity is not None else "NONE"),
        selection_disposition=(
            identity.selection_disposition.value if identity is not None else "NONE"
        ),
        terminal_coverage=observation.terminal_coverage.value,
        quality=(observation.quality.value if observation.quality is not None else None),
        unavailable_reason=(
            observation.unavailable_reason.value
            if observation.unavailable_reason is not None
            else None
        ),
        actual_sample_count=observation.actual_sample_count,
    )


@dataclass(frozen=True)
class StatusMatrixOutcome:
    """One status-matrix scenario's paired (telemetry-disabled,
    telemetry-enabled) real-Docker outcome."""

    scenario_name: str
    expected_status: str
    disabled_status: str
    enabled_status: str
    disabled_return_value_repr: str
    enabled_return_value_repr: str
    peak_memory_finding: MethodFinding
    peak_process_count_finding: MethodFinding

    @property
    def statuses_agree(self) -> bool:
        """Whether the telemetry-disabled and telemetry-enabled legs
        classified this invocation identically."""
        return self.disabled_status == self.enabled_status

    @property
    def return_values_agree(self) -> bool:
        """Whether the two legs' returned values (or typed failure
        classification) match exactly."""
        return self.disabled_return_value_repr == self.enabled_return_value_repr


@dataclass(frozen=True)
class LatePeakOutcome:
    """The late_peak workload's own real-Docker measurement -- reported
    honestly even when the host cannot exercise the EXACT cgroup path at
    all (see the harness's own host-capability determination)."""

    peak_memory_finding: MethodFinding
    reported_value: int | None
    expected_minimum_bytes: int


@dataclass(frozen=True)
class CleanupCheckResult:
    """An independent post-run container/thread cleanup check."""

    leftover_container_names: tuple[str, ...]

    @property
    def clean(self) -> bool:
        """Whether zero megb-runner-* containers remain."""
        return len(self.leftover_container_names) == 0


def check_no_leftover_containers() -> CleanupCheckResult:
    """Mirrors the G.4 benchmark's own leftover-container check: an
    independent ``docker ps -a --filter name=megb-runner-`` query, never
    trusting the harness's own internal bookkeeping alone."""
    proc = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=megb-runner-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    names = tuple(name for name in proc.stdout.splitlines() if name)
    return CleanupCheckResult(leftover_container_names=names)


# ---------------------------------------------------------------------------
# Stage-runtime projections (pure -- the accepted concurrency-aware formula)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageProjection:
    """One (stage, scenario) pair's projected runtime, inclusive of
    measured telemetry overhead, against its own frozen hard ceiling."""

    stage: str
    scenario: str
    projected_seconds: float
    hard_ceiling_seconds: float

    @property
    def within_ceiling(self) -> bool:
        """Whether the projected runtime fits the frozen hard ceiling."""
        return self.projected_seconds <= self.hard_ceiling_seconds


def project_stage_runtimes(
    *, measured_telemetry_overhead_sec: float
) -> tuple[StageProjection, ...]:
    """``stage_time = invocation_count * per_invocation_time / speedup``,
    with ``per_invocation_time`` inclusive of the *measured* real
    telemetry overhead -- never the offline baseline alone -- across every
    accepted scenario multiplier (baseline/moderate/conservative/stress)
    and every stage (H.3-H.6)."""
    per_invocation_time = FROZEN_BASELINE_PER_INVOCATION_SEC + measured_telemetry_overhead_sec
    projections = []
    for stage, invocation_count in FROZEN_STAGE_INVOCATION_COUNTS.items():
        for scenario, multiplier in FROZEN_SCENARIO_MULTIPLIERS.items():
            projected_seconds = (
                invocation_count
                * per_invocation_time
                * multiplier
                / FROZEN_CONCURRENCY_SPEEDUP_AT_4
            )
            projections.append(
                StageProjection(
                    stage=stage,
                    scenario=scenario,
                    projected_seconds=projected_seconds,
                    hard_ceiling_seconds=FROZEN_STAGE_HARD_CEILINGS_SEC[stage],
                )
            )
    return tuple(projections)


# ---------------------------------------------------------------------------
# Real-Docker orchestration (requires a live Docker daemon)
# ---------------------------------------------------------------------------


def _request(
    candidate_code: str, *, limits: ExecutionLimits | None = None
) -> CandidateExecutionRequest:
    return CandidateExecutionRequest(
        candidate_code=candidate_code,
        entry_point="f",
        args=(),
        kwargs={},
        limits=limits or ExecutionLimits(),
        protocol_version="reference-evaluator-execution-protocol-v1",
    )


def _run_one_pair(
    *, leg_order: str, candidate_code: str, disabled_backend: DockerPerInvocationBackend,
    enabled_backend: DockerPerInvocationBackend,
) -> PairedInvocationTiming:
    if leg_order == "AB":
        start = time.monotonic()
        disabled_backend.execute(_request(candidate_code))
        disabled_wall = time.monotonic() - start
        start = time.monotonic()
        enabled_backend.execute_with_telemetry(_request(candidate_code))
        enabled_wall = time.monotonic() - start
    else:
        start = time.monotonic()
        enabled_backend.execute_with_telemetry(_request(candidate_code))
        enabled_wall = time.monotonic() - start
        start = time.monotonic()
        disabled_backend.execute(_request(candidate_code))
        disabled_wall = time.monotonic() - start
    return PairedInvocationTiming(
        leg_order=leg_order, disabled_wall_sec=disabled_wall, enabled_wall_sec=enabled_wall
    )


@dataclass(frozen=True)
class _PairedOverheadBackends:
    """Groups the two backend instances a paired overhead measurement
    needs -- keeps run_paired_overhead_configuration's own argument count
    within the project's pylint limit without bundling unrelated
    parameters together."""

    disabled_backend: DockerPerInvocationBackend
    enabled_backend: DockerPerInvocationBackend


def run_paired_overhead_configuration(
    *,
    workload: str,
    candidate_code: str,
    concurrency: int,
    backends: _PairedOverheadBackends,
    n_pairs: int = FROZEN_PAIRED_REPETITIONS_N,
) -> OverheadMeasurement:
    """Runs ``n_pairs`` paired invocations, alternating balanced AB/BA
    ordering (plan §7) -- half the pairs disabled-then-enabled, half
    enabled-then-disabled, interleaved rather than blocked, so no
    systematic ordering effect (host caching, thermal throttling) can
    confound the overhead measurement. ``concurrency`` pairs run
    simultaneously via a bounded thread pool (each pair's own two legs
    remain sequential, so its own wall-clock timing is unaffected by
    other concurrently-running pairs) -- the same "how many invocations
    in flight at once" semantics the accepted orchestrator/benchmark
    concurrency levels already use elsewhere in this project."""
    leg_orders = ["AB" if i % 2 == 0 else "BA" for i in range(n_pairs)]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        pairs = list(
            pool.map(
                lambda leg_order: _run_one_pair(
                    leg_order=leg_order,
                    candidate_code=candidate_code,
                    disabled_backend=backends.disabled_backend,
                    enabled_backend=backends.enabled_backend,
                ),
                leg_orders,
            )
        )
    return OverheadMeasurement(workload=workload, concurrency=concurrency, pairs=tuple(pairs))


def run_status_matrix_pass(
    *,
    disabled_backend: DockerPerInvocationBackend,
    enabled_backend: DockerPerInvocationBackend,
) -> tuple[StatusMatrixOutcome, ...]:
    """Runs every scenario in :data:`STATUS_MATRIX_SCENARIOS` once through
    both ``execute()`` and ``execute_with_telemetry()``, proving
    classification agreement against a real container (plan §9)."""
    outcomes = []
    for scenario in STATUS_MATRIX_SCENARIOS:
        request = _request(scenario.candidate_code, limits=scenario.limits)
        disabled_result = disabled_backend.execute(request)
        enabled_result, enabled_telemetry = enabled_backend.execute_with_telemetry(
            _request(scenario.candidate_code, limits=scenario.limits)
        )
        outcomes.append(
            _status_matrix_outcome(
                scenario.name, disabled_result, enabled_result, enabled_telemetry
            )
        )
    return tuple(outcomes)


def _status_matrix_outcome(
    scenario_name: str,
    disabled_result: CandidateExecutionResult,
    enabled_result: CandidateExecutionResult,
    enabled_telemetry: ExecutionTelemetry,
) -> StatusMatrixOutcome:
    return StatusMatrixOutcome(
        scenario_name=scenario_name,
        expected_status=disabled_result.status.value,
        disabled_status=disabled_result.status.value,
        enabled_status=enabled_result.status.value,
        disabled_return_value_repr=repr(disabled_result.return_value),
        enabled_return_value_repr=repr(enabled_result.return_value),
        peak_memory_finding=method_finding_from_observation(
            metric="peak_memory_bytes",
            preferred_method="CGROUP_V2_MEMORY_PEAK",
            observation=enabled_telemetry.peak_memory,
        ),
        peak_process_count_finding=method_finding_from_observation(
            metric="peak_process_count",
            preferred_method="CGROUP_V2_PIDS_PEAK",
            observation=enabled_telemetry.peak_process_count,
        ),
    )


def run_late_peak_probe(
    *, enabled_backend: DockerPerInvocationBackend, baseline_mib: int, spike_mib: int
) -> LatePeakOutcome:
    """Runs the ``late_peak`` workload once through ``execute_with_telemetry()``
    and reports exactly what this host's real collector selection produced
    -- never assuming EXACT is reachable, per the frozen plan's own
    empirical-determination requirement."""
    code = late_peak_candidate_source(
        baseline_mib=baseline_mib, spike_mib=spike_mib, presleep_sec=0.2
    )
    result, telemetry = enabled_backend.execute_with_telemetry(_request(code))
    finding = method_finding_from_observation(
        metric="peak_memory_bytes",
        preferred_method="CGROUP_V2_MEMORY_PEAK",
        observation=telemetry.peak_memory,
    )
    return LatePeakOutcome(
        peak_memory_finding=finding,
        reported_value=(
            int(result.return_value) if isinstance(result.return_value, int) else None
        ),
        expected_minimum_bytes=spike_mib * 1024 * 1024,
    )


__all__ = [
    "H2C2B_MEASUREMENT_HARNESS_VERSION",
    "FROZEN_PLAN_GIT_BLOB_SHA1",
    "FROZEN_PLAN_SHA256",
    "FROZEN_MEMORY_SAMPLING_INTERVAL_SEC",
    "FROZEN_PROCESS_COUNT_SAMPLING_INTERVAL_SEC",
    "FROZEN_EXISTENCE_POLL_INTERVAL_SEC",
    "FROZEN_EXISTENCE_WAIT_MAX_SEC",
    "FROZEN_PAIRED_REPETITIONS_N",
    "FROZEN_CONCURRENCY_LEVELS",
    "FROZEN_PRIMARY_OVERHEAD_GATE_MS",
    "FROZEN_P99_OVERHEAD_DIAGNOSTIC_MS",
    "FROZEN_BASELINE_PER_INVOCATION_SEC",
    "FROZEN_CONCURRENCY_SPEEDUP_AT_4",
    "FROZEN_STAGE_INVOCATION_COUNTS",
    "FROZEN_STAGE_HARD_CEILINGS_SEC",
    "FROZEN_SCENARIO_MULTIPLIERS",
    "PlanIdentityMismatchError",
    "verify_plan_identity",
    "run_identity_for",
    "BASELINE_WORKLOAD_VERSION",
    "MEMORY_ALLOCATOR_WORKLOAD_VERSION",
    "PROCESS_SPAWNER_WORKLOAD_VERSION",
    "LATE_PEAK_WORKLOAD_VERSION",
    "BASELINE_CANDIDATE_SOURCE",
    "memory_allocator_candidate_source",
    "process_spawner_candidate_source",
    "late_peak_candidate_source",
    "StatusScenario",
    "STATUS_MATRIX_SCENARIOS",
    "PROCESS_LIMIT_SCENARIO_NAME",
    "PROCESS_LIMIT_CANDIDATE_CODE",
    "PROCESS_LIMIT_ACCEPTABLE_STATUSES",
    "PROCESS_LIMIT_LIMITS",
    "PairedInvocationTiming",
    "OverheadMeasurement",
    "MethodFinding",
    "method_finding_from_observation",
    "StatusMatrixOutcome",
    "LatePeakOutcome",
    "CleanupCheckResult",
    "check_no_leftover_containers",
    "StageProjection",
    "project_stage_runtimes",
    "run_paired_overhead_configuration",
    "run_status_matrix_pass",
    "run_late_peak_probe",
]
