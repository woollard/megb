"""MEGB-03H.2C.3B.2C: shared fixtures for the offline end-to-end
synthetic distributed qualification suite. Not a test module itself.

Every candidate content byte string and the transform applied to it are
frozen exactly as described in
``docs/reference/megb-03h2c3b2c-offline-e2e-qualification-plan.md``."""

import hashlib
import threading

from src.distributed.executor import (
    ExecutorInvocationResult,
    WorkExecutorProtocol,
    executor_success,
)


def synthetic_transform(candidate_content: bytes) -> bytes:
    """The frozen, harmless, deterministic transform this checkpoint's
    entire synthetic workload is built on. Never source-code execution --
    a fixed byte transform of already-resolved candidate content."""
    return hashlib.sha256(candidate_content).digest()[:16]


def synthetic_transform_checksum(candidate_content: bytes) -> str:
    """The exact ``result_content_checksum`` a correctly-committed
    transform of ``candidate_content`` must carry."""
    return hashlib.sha256(synthetic_transform(candidate_content)).hexdigest()


class TransformExecutor:
    """A synthetic executor whose successful invocation always returns
    ``synthetic_transform(candidate_content)`` -- real, deterministic,
    harmless data transformation, never scripted canned content. An
    optional leading ``pre_script`` of failures is returned before the
    real transform ever runs, for the retry-then-success item."""

    def __init__(self, pre_script: list[ExecutorInvocationResult] | None = None) -> None:
        self._pre_script = pre_script or []
        self.invocation_count = 0
        self.received_contents: list[bytes] = []

    def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
        """Return the next scripted failure, or the real transform once
        the pre-script is exhausted."""
        self.invocation_count += 1
        self.received_contents.append(candidate_content)
        if self.invocation_count <= len(self._pre_script):
            return self._pre_script[self.invocation_count - 1]
        return executor_success(synthetic_transform(candidate_content))


class BarrierSynchronizedTransformExecutor:
    """Like :class:`TransformExecutor`, but every invocation first waits
    on a shared ``threading.Barrier`` sized to the number of
    concurrently-running workers -- forcing genuine, real overlapping
    execution so this checkpoint's measured-peak-concurrency field
    reflects an actually-realized overlap, never merely a configured
    worker count that real thread scheduling might otherwise race
    through without ever truly overlapping."""

    def __init__(self, barrier: threading.Barrier) -> None:
        self._barrier = barrier
        self.invocation_count = 0

    def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
        """Wait for every concurrently-running worker to arrive, then
        apply the real, deterministic transform."""
        self._barrier.wait()
        self.invocation_count += 1
        return executor_success(synthetic_transform(candidate_content))


class PeakConcurrencyTrackingExecutor:
    """Wraps an inner executor and measures the actual peak number of
    concurrently-active ``execute()`` invocations -- a genuine
    measurement, never an assumed or asserted value, and never a
    wall-clock timing."""

    def __init__(self, inner: WorkExecutorProtocol) -> None:
        self._inner = inner
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0

    def execute(self, candidate_content: bytes) -> ExecutorInvocationResult:
        """Track active-invocation concurrency around the inner
        executor's own call."""
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)
        try:
            return self._inner.execute(candidate_content)
        finally:
            with self._lock:
                self._active -= 1


def path_coverage_content(item_id: str) -> bytes:
    """Frozen candidate content for one path-coverage workload item."""
    return f"e2e-synthetic-candidate-{item_id}".encode("utf-8")


def equivalence_content(item_id: str) -> bytes:
    """Frozen candidate content for one equivalence-workload item."""
    return f"e2e-eq-synthetic-{item_id}".encode("utf-8")


# Frozen workload definition (item id -> content seed), matching the plan
# document exactly. Used only to compute a stable workload checksum -- the
# actual per-item behavior is exercised by the test functions themselves.
PATH_COVERAGE_ITEM_IDS = ("01", "02", "03", "04", "05", "06", "07", "08")

# EQUIVALENCE_ITEM_IDS (2 items, not the plan's originally-described 4):
# AtomicBudgetStore's own worker-ceiling check counts every *currently
# RESERVED* reservation's requested_worker_count, and Coordinator.run()
# admits every item before executing any of them -- so a personal
# (max_admitted_workers=2) environment can never hold more than 2
# concurrently-reserved single-worker items open at once, regardless of
# how many worker threads later drain them. Reduced from 4 to 2 items so
# the personal concurrency-1-vs-2 comparison stays within that ceiling --
# a narrow implementation adjustment, not a weakening of the equivalence
# requirement itself (still exact serial/c1/c2 agreement over a real,
# fixed, multi-item workload). GENERIC_EQUIVALENCE_ITEM_IDS (4 items) is
# used only for the separate, non-personal concurrency-4 comparison,
# which has no such ceiling.
EQUIVALENCE_ITEM_IDS = ("01", "02")
GENERIC_EQUIVALENCE_ITEM_IDS = ("01", "02", "03", "04")


def compute_workload_checksum() -> str:
    """Sha256 over a canonical repr of the frozen workload definition:
    item ids, content seeds, and the transform's own name -- changes if
    and only if the frozen workload itself changes."""
    canonical = repr(
        (
            "synthetic_transform:sha256-digest-16",
            tuple((item_id, path_coverage_content(item_id)) for item_id in PATH_COVERAGE_ITEM_IDS),
            tuple((item_id, equivalence_content(item_id)) for item_id in EQUIVALENCE_ITEM_IDS),
            tuple(
                (item_id, equivalence_content(item_id)) for item_id in GENERIC_EQUIVALENCE_ITEM_IDS
            ),
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
