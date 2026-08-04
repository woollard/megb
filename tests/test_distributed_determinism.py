"""MEGB-03H.2C.3B.1: deterministic-checksum-across-processes tests.

``json.dumps(..., sort_keys=True)`` + sha256 is platform/process-
independent by construction (no dict-ordering, hash-randomization, or
floating-point-repr dependency for the field types this package uses),
but the authorization explicitly requires this be *proven*, not merely
asserted -- so this test actually spawns a fresh subprocess and confirms
its independently-recomputed checksum matches the parent process's.
"""

import subprocess
import sys
from pathlib import Path

from src.distributed._checksums import sha256_of
from tests._distributed_fixtures import make_run_and_worker

_REPO_ROOT = Path(__file__).resolve().parent.parent

_CHILD_SCRIPT = """
import sys
sys.path.insert(0, {repo_root!r})
from src.distributed._checksums import sha256_of
from tests._distributed_fixtures import make_run_and_worker

run_context, worker = make_run_and_worker()
print(run_context.run_context_checksum)
print(worker.worker_context_checksum)
print(sha256_of({{"a": 1, "b": [1, 2, 3], "c": "unicode-\\u00e9"}}))
"""


def test_checksum_is_deterministic_across_processes() -> None:
    """Test checksum is deterministic across processes."""
    run_context, worker = make_run_and_worker()
    child = subprocess.run(
        [sys.executable, "-c", _CHILD_SCRIPT.format(repo_root=str(_REPO_ROOT))],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    lines = child.stdout.strip().splitlines()
    assert len(lines) == 3, child.stdout + child.stderr
    child_run_checksum, child_worker_checksum, child_payload_checksum = lines

    assert child_run_checksum == run_context.run_context_checksum
    assert child_worker_checksum == worker.worker_context_checksum
    assert child_payload_checksum == sha256_of({"a": 1, "b": [1, 2, 3], "c": "unicode-é"})


def test_checksum_is_deterministic_across_two_independent_subprocesses() -> None:
    """Two separate fresh interpreters, neither the pytest process,
    produce byte-identical checksums for the same synthetic content --
    rules out any dependency on a single process's hash-seed or
    dict-insertion history."""
    outputs = []
    for _ in range(2):
        child = subprocess.run(
            [sys.executable, "-c", _CHILD_SCRIPT.format(repo_root=str(_REPO_ROOT))],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        outputs.append(child.stdout.strip().splitlines())
    assert outputs[0] == outputs[1]
