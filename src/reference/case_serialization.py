"""Stable, versioned serialization and case identifiers (MEGB-03A).

A "case" is one authorized test invocation for one task: a tuple of
arguments drawn from that task's ``base_input`` or ``plus_input`` (see
``src.dataset.PrivilegedTaskView``). Case identifiers must be stable across
repeated runs and across processes, since MEGB-03B's partition assignment
and later oracle/audit artifacts are keyed by them.

Deliberately reuses ``src.execution.wire.encode_value`` (MEGB-02's tagged
wire encoding) rather than a new ad hoc serializer: it already provides an
explicit, tested, versioned type-safe representation (rejecting
unsupported types, preserving tuple-vs-list) for exactly the value types
HumanEval/HumanEval+ cases use.
"""

import hashlib
import json
from typing import Any

from src.execution.wire import encode_value

CASE_ID_ALGORITHM_VERSION = "case-id-v1"


def canonical_case_representation(task_id: str, args: tuple[Any, ...]) -> str:
    """Deterministic, versioned string representation of one (task_id, args) case.

    Two calls with equal ``task_id`` and equal ``args`` always produce an
    identical string; this is also what collision detection compares
    against a case ID, since a true hash collision means two conceptually
    different canonical representations produced the same ID.
    """
    tagged_args = [encode_value(v) for v in args]
    payload = json.dumps(tagged_args, sort_keys=True, separators=(",", ":"))
    return f"{CASE_ID_ALGORITHM_VERSION}|{task_id}|{payload}"


def stable_case_id(task_id: str, args: tuple[Any, ...]) -> str:
    """Stable, deterministic identifier for one (task_id, args) case.

    Never uses Python's built-in ``hash()`` (randomized per-process for
    strings unless ``PYTHONHASHSEED`` is fixed) — always SHA-256 over the
    versioned canonical representation.
    """
    canonical = canonical_case_representation(task_id, args)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
