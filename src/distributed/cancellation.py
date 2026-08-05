"""MEGB-03H.2C.3B.2B.2: a deterministic, synchronous cancellation
controller.

No ``threading.Event``/wait/timeout is used -- cancellation in this
engine is never *awaited*, only *checked* at defined checkpoints in the
admission and worker-execution sequences (before admission, before lease,
after execution but before commit). This keeps cancellation fully
deterministic and testable without any wall-clock wait: a test requests
cancellation, then synchronously drives the coordinator/worker call that
should observe it, and asserts the resulting
:class:`~src.distributed.work_outcome.WorkOutcomeKind`."""

import threading

from src.distributed._checksums import InvalidDistributedProvenanceError


class CancellationController:
    """Synthetic, single-process, lock-protected set of cancelled
    ``scientific_work_id`` values for one coordinator run."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled: set[str] = set()

    def request_cancellation(self, scientific_work_id: str) -> None:
        """Idempotently mark ``scientific_work_id`` cancelled."""
        if not isinstance(scientific_work_id, str) or scientific_work_id == "":
            raise InvalidDistributedProvenanceError(
                f"scientific_work_id must be a nonempty string, got {scientific_work_id!r}"
            )
        with self._lock:
            self._cancelled.add(scientific_work_id)

    def is_cancelled(self, scientific_work_id: str) -> bool:
        """``True`` iff ``scientific_work_id`` has ever had cancellation
        requested."""
        with self._lock:
            return scientific_work_id in self._cancelled

    def token_for(self, scientific_work_id: str) -> "CancellationToken":
        """A :class:`CancellationToken` bound to one ``scientific_work_id``."""
        if not isinstance(scientific_work_id, str) or scientific_work_id == "":
            raise InvalidDistributedProvenanceError(
                f"scientific_work_id must be a nonempty string, got {scientific_work_id!r}"
            )
        return CancellationToken(self, scientific_work_id)


class CancellationToken:
    """A read-only, per-work-item view of a :class:`CancellationController` --
    the one object worker-invocation code actually receives (never the
    full controller, which could cancel unrelated work items)."""

    def __init__(self, controller: CancellationController, scientific_work_id: str) -> None:
        self._controller = controller
        self._scientific_work_id = scientific_work_id

    def is_cancelled(self) -> bool:
        """``True`` iff this token's own ``scientific_work_id`` has had
        cancellation requested."""
        return self._controller.is_cancelled(self._scientific_work_id)


__all__ = [
    "CancellationController",
    "CancellationToken",
]
