"""MEGB-03G.2: the content-addressed cache key for one reference-evaluation
(S*) task-candidate-evaluator work item.

Binds exactly the outcome-affecting fields the "Approved MEGB-03G
Compatibility Amendment" (section 3) and the "Approved MEGB-03G.2-G.5 Scope
Amendment" require: task identity, candidate identity, the reference-case
checksum, and every version/identity field that participates in
``ReferenceRunContext``'s equality (dataset, partition, oracle, comparison
profile, evaluator, execution profile) plus the execution-protocol version.

Deliberately excludes run IDs, portfolio-selection IDs, candidate display
IDs, and timestamps -- none of these affect the measured outcome, so none
of them may influence cache identity. They belong in audit/mapping records
instead (see ``src.reference.reference_audit``).

This key is manifest-independent by design (per the scope amendment's
section 1): nothing here ties it to the 164-task
``ReferenceValidationCandidateSetManifest`` or to any specific benchmark
run, so the same key construction serves both the 164-task
reference-validation workflow and MEGB-06H's 163-task experimental reuse.

**Known limitation (reported, not fixed here -- see MEGB-03G.2's checkpoint
report):** the amendment requires "execution-protocol version" as a
cache-key field, but -- exactly like ``comparison_profile_version`` before
the MEGB-03E/F v3 correction -- there is no persisted ``protocol_version``
field on ``ReferenceRunContext`` or ``ReferenceTaskResult``; it exists only
on the trusted-side ``ReferenceTaskEvidence`` input and is verified once by
``evaluate_reference`` against the single module-level
``EXECUTION_PROTOCOL_VERSION`` constant. This module sources
``protocol_version`` from that same constant rather than from the result
being cached. Because both cache writes and cache reads always consult the
same live constant, a future protocol-version bump still correctly
invalidates old entries (they were written under the old constant's digest
contribution and will not match a newly computed key) -- but a cache entry
considered in isolation cannot, by itself, prove which protocol version
produced it. Closing that residual gap would require the same kind of
schema correction ``comparison_profile_version`` received (a new
``ReferenceRunContext`` field, a schema version bump); that change is not
made here without separate authorization.
"""

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from src.reference.reference_evaluator import EXECUTION_PROTOCOL_VERSION
from src.reference.result_schema import ReferenceTaskResult

CACHE_KEY_SCHEMA_VERSION = "reference-result-cache-key-v1"

_SHA256_FIELD_NAMES = frozenset({"candidate_sha256", "reference_case_checksum"})


class InvalidCacheKeyError(ValueError):
    """Raised when a :class:`ReferenceResultCacheKey`'s fields are internally
    inconsistent, or its ``key_digest`` does not match its own recomputed
    contents.

    Construction must fail loudly rather than silently accept a
    self-contradictory or tampered key.
    """


def _require_nonempty_str(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or value == "":
        raise InvalidCacheKeyError(f"{field_name!r} must be a nonempty string, got {value!r}")


def _compute_key_digest(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    cache_key_schema_version: str,
    task_id: str,
    candidate_sha256: str,
    reference_case_checksum: str,
    dataset_version: str,
    partition_version: str,
    oracle_version: str,
    comparison_profile_version: str,
    evaluator_version: str,
    execution_profile_id: str,
    protocol_version: str,
) -> str:
    hasher = hashlib.sha256()
    for value in (
        cache_key_schema_version,
        task_id,
        candidate_sha256,
        reference_case_checksum,
        dataset_version,
        partition_version,
        oracle_version,
        comparison_profile_version,
        evaluator_version,
        execution_profile_id,
        protocol_version,
    ):
        hasher.update(value.encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


@dataclass(frozen=True)
class ReferenceResultCacheKey:
    """Immutable, content-addressed identity for one cacheable reference
    result.

    ``key_digest`` is always recomputed from the key's own canonical
    contents at construction time -- never accepted as an unverified
    caller-provided value, mirroring the same auto-compute-or-reject
    pattern already established by
    :class:`~src.reference.result_schema.ReferenceValidationCandidateSetManifest`.
    Because the digest is computed over ``cache_key_schema_version`` too, a
    future schema bump automatically changes every digest -- an old,
    schema-incompatible entry naturally misses rather than needing a
    separate version-comparison step at lookup time.
    """

    cache_key_schema_version: str
    task_id: str
    candidate_sha256: str
    reference_case_checksum: str
    dataset_version: str
    partition_version: str
    oracle_version: str
    comparison_profile_version: str
    evaluator_version: str
    execution_profile_id: str
    protocol_version: str
    key_digest: str = ""

    def __post_init__(self) -> None:
        _require_nonempty_str(self, "cache_key_schema_version")
        _require_nonempty_str(self, "task_id")
        _require_nonempty_str(self, "dataset_version")
        _require_nonempty_str(self, "partition_version")
        _require_nonempty_str(self, "oracle_version")
        _require_nonempty_str(self, "comparison_profile_version")
        _require_nonempty_str(self, "evaluator_version")
        _require_nonempty_str(self, "execution_profile_id")
        _require_nonempty_str(self, "protocol_version")
        for field_name in _SHA256_FIELD_NAMES:
            value = getattr(self, field_name)
            if not isinstance(value, str) or len(value) != 64:
                raise InvalidCacheKeyError(
                    f"{field_name!r} must be a 64-character hex sha256 digest, got {value!r}"
                )
        if self.cache_key_schema_version != CACHE_KEY_SCHEMA_VERSION:
            raise InvalidCacheKeyError(
                f"cache_key_schema_version {self.cache_key_schema_version!r} does not match "
                f"the version this module implements ({CACHE_KEY_SCHEMA_VERSION!r})"
            )
        expected_digest = _compute_key_digest(
            self.cache_key_schema_version,
            self.task_id,
            self.candidate_sha256,
            self.reference_case_checksum,
            self.dataset_version,
            self.partition_version,
            self.oracle_version,
            self.comparison_profile_version,
            self.evaluator_version,
            self.execution_profile_id,
            self.protocol_version,
        )
        if self.key_digest and self.key_digest != expected_digest:
            raise InvalidCacheKeyError(
                f"key_digest {self.key_digest!r} does not match the recomputed digest "
                f"{expected_digest!r} over its own contents -- tampered or corrupted cache key"
            )
        object.__setattr__(self, "key_digest", expected_digest)


def cache_key_for(task_result: ReferenceTaskResult) -> ReferenceResultCacheKey:
    """Derive the cache key for ``task_result`` from its own fields and its
    embedded :class:`~src.reference.result_schema.ReferenceRunContext`.

    Never accepts run IDs, selection IDs, candidate display IDs, or
    timestamps -- only the outcome-affecting identity/version fields
    contribute to the returned key.
    """
    context = task_result.context
    return ReferenceResultCacheKey(
        cache_key_schema_version=CACHE_KEY_SCHEMA_VERSION,
        task_id=task_result.task_id,
        candidate_sha256=task_result.candidate_sha256,
        reference_case_checksum=task_result.reference_case_checksum,
        dataset_version=context.dataset_version,
        partition_version=context.partition_version,
        oracle_version=task_result.oracle_version,
        comparison_profile_version=context.comparison_profile_version,
        evaluator_version=context.evaluator_version,
        execution_profile_id=context.execution_profile_id,
        protocol_version=EXECUTION_PROTOCOL_VERSION,
    )


def cache_key_to_dict(key: ReferenceResultCacheKey) -> dict[str, str]:
    """Full-fidelity serialization of a :class:`ReferenceResultCacheKey`."""
    return {
        "cache_key_schema_version": key.cache_key_schema_version,
        "task_id": key.task_id,
        "candidate_sha256": key.candidate_sha256,
        "reference_case_checksum": key.reference_case_checksum,
        "dataset_version": key.dataset_version,
        "partition_version": key.partition_version,
        "oracle_version": key.oracle_version,
        "comparison_profile_version": key.comparison_profile_version,
        "evaluator_version": key.evaluator_version,
        "execution_profile_id": key.execution_profile_id,
        "protocol_version": key.protocol_version,
        "key_digest": key.key_digest,
    }


def cache_key_from_dict(data: Mapping[str, Any]) -> ReferenceResultCacheKey:
    """Inverse of :func:`cache_key_to_dict`.

    Reconstructs through :class:`ReferenceResultCacheKey`'s own constructor,
    passing the stored ``key_digest`` through as the "expected" value -- the
    constructor always recomputes it and rejects a mismatch, so tampering is
    caught by the act of deserializing.
    """
    return ReferenceResultCacheKey(
        cache_key_schema_version=data["cache_key_schema_version"],
        task_id=data["task_id"],
        candidate_sha256=data["candidate_sha256"],
        reference_case_checksum=data["reference_case_checksum"],
        dataset_version=data["dataset_version"],
        partition_version=data["partition_version"],
        oracle_version=data["oracle_version"],
        comparison_profile_version=data["comparison_profile_version"],
        evaluator_version=data["evaluator_version"],
        execution_profile_id=data["execution_profile_id"],
        protocol_version=data["protocol_version"],
        key_digest=data["key_digest"],
    )
