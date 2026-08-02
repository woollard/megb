"""MEGB-03G.2: the content-addressed cache key for one reference-evaluation
(S*) task-candidate-evaluator work item.

Binds exactly the outcome-affecting fields the "Approved MEGB-03G
Compatibility Amendment" (section 3) and the "Approved MEGB-03G.2-G.5 Scope
Amendment" require: task identity, candidate identity, the reference-case
checksum, and every version/identity field that participates in
``ReferenceRunContext``'s equality (dataset, partition, oracle, comparison
profile, evaluator, execution profile) plus the execution-protocol version
-- now including the v4 content-addressed checksums (``dataset_checksum``,
``task_manifest_checksum``) alongside their pre-existing version labels.

Deliberately excludes run IDs, portfolio-selection IDs, candidate display
IDs, and timestamps -- none of these affect the measured outcome, so none
of them may influence cache identity. They belong in audit/mapping records
instead (see ``src.reference.reference_audit``).

This key is manifest-independent by design (per the scope amendment's
section 1): nothing here ties it to the 164-task
``ReferenceValidationCandidateSetManifest`` or to any specific benchmark
run, so the same key construction serves both the 164-task
reference-validation workflow and MEGB-06H's 163-task experimental reuse.

**Resolved (v2 cache-key schema, post-MEGB-03G.2 cache-provenance audit):**
the original cache key sourced ``protocol_version`` from the live
``EXECUTION_PROTOCOL_VERSION`` module constant rather than from the result
being cached, because no persisted field existed to source it from. The
``result_schema`` v4 correction adds ``execution_protocol_version``
directly to ``ReferenceRunContext``; this module now derives
``execution_protocol_version`` (renamed from ``protocol_version`` to match
that field) exclusively from the persisted, validated result context --
never from a live module constant -- closing the residual gap the v1
cache-key schema left open. The same audit found ``dataset_version``/
``partition_version`` are human-managed version labels, not
content-addressed checksums, so this key now also carries
``dataset_checksum`` and ``task_manifest_checksum`` (the corresponding
content-bound identities already established by
``src.reference.partition_lock``/``src.reference.oracle_lock``) alongside
the pre-existing labels. Because the key's field set changed,
``CACHE_KEY_SCHEMA_VERSION`` moves from ``reference-result-cache-key-v1``
to ``reference-result-cache-key-v2``; no persisted cache artifact has ever
existed (confirmed by a repo-wide search of ``artifacts/privileged/``), so
no migration path is required or provided.
"""

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from src.reference.result_schema import ReferenceTaskResult

CACHE_KEY_SCHEMA_VERSION = "reference-result-cache-key-v2"

_SHA256_FIELD_NAMES = frozenset({"candidate_sha256", "reference_case_checksum"})

# dataset_checksum's authoritative source (DatasetProvenance.evalplus_dataset_hash,
# via evalplus's own get_human_eval_plus_hash) is not a 64-character sha256
# hex digest -- it must not be forced into that format, only required
# nonempty, so it is deliberately excluded from _SHA256_FIELD_NAMES.


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
    dataset_checksum: str,
    partition_version: str,
    task_manifest_checksum: str,
    oracle_version: str,
    comparison_profile_version: str,
    evaluator_version: str,
    execution_profile_id: str,
    execution_protocol_version: str,
) -> str:
    hasher = hashlib.sha256()
    for value in (
        cache_key_schema_version,
        task_id,
        candidate_sha256,
        reference_case_checksum,
        dataset_version,
        dataset_checksum,
        partition_version,
        task_manifest_checksum,
        oracle_version,
        comparison_profile_version,
        evaluator_version,
        execution_profile_id,
        execution_protocol_version,
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
    dataset_checksum: str
    partition_version: str
    task_manifest_checksum: str
    oracle_version: str
    comparison_profile_version: str
    evaluator_version: str
    execution_profile_id: str
    execution_protocol_version: str
    key_digest: str = ""

    def __post_init__(self) -> None:
        _require_nonempty_str(self, "cache_key_schema_version")
        _require_nonempty_str(self, "task_id")
        _require_nonempty_str(self, "dataset_version")
        _require_nonempty_str(self, "dataset_checksum")
        _require_nonempty_str(self, "partition_version")
        _require_nonempty_str(self, "oracle_version")
        _require_nonempty_str(self, "comparison_profile_version")
        _require_nonempty_str(self, "evaluator_version")
        _require_nonempty_str(self, "execution_profile_id")
        _require_nonempty_str(self, "execution_protocol_version")
        for field_name in _SHA256_FIELD_NAMES:
            value = getattr(self, field_name)
            if not isinstance(value, str) or len(value) != 64:
                raise InvalidCacheKeyError(
                    f"{field_name!r} must be a 64-character hex sha256 digest, got {value!r}"
                )
        task_manifest_checksum_ok = (
            isinstance(self.task_manifest_checksum, str) and len(self.task_manifest_checksum) == 64
        )
        if not task_manifest_checksum_ok:
            raise InvalidCacheKeyError(
                f"'task_manifest_checksum' must be a 64-character hex sha256 digest, "
                f"got {self.task_manifest_checksum!r}"
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
            self.dataset_checksum,
            self.partition_version,
            self.task_manifest_checksum,
            self.oracle_version,
            self.comparison_profile_version,
            self.evaluator_version,
            self.execution_profile_id,
            self.execution_protocol_version,
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
    timestamps -- only the outcome-affecting identity/version/checksum
    fields contribute to the returned key. ``execution_protocol_version``
    is read exclusively from ``task_result.context`` -- never from a live
    module constant -- so a serialized-and-reloaded result reproduces
    exactly the same key it was originally cached under.
    """
    context = task_result.context
    return ReferenceResultCacheKey(
        cache_key_schema_version=CACHE_KEY_SCHEMA_VERSION,
        task_id=task_result.task_id,
        candidate_sha256=task_result.candidate_sha256,
        reference_case_checksum=task_result.reference_case_checksum,
        dataset_version=context.dataset_version,
        dataset_checksum=context.dataset_checksum,
        partition_version=context.partition_version,
        task_manifest_checksum=context.task_manifest_checksum,
        oracle_version=task_result.oracle_version,
        comparison_profile_version=context.comparison_profile_version,
        evaluator_version=context.evaluator_version,
        execution_profile_id=context.execution_profile_id,
        execution_protocol_version=context.execution_protocol_version,
    )


def cache_key_to_dict(key: ReferenceResultCacheKey) -> dict[str, str]:
    """Full-fidelity serialization of a :class:`ReferenceResultCacheKey`."""
    return {
        "cache_key_schema_version": key.cache_key_schema_version,
        "task_id": key.task_id,
        "candidate_sha256": key.candidate_sha256,
        "reference_case_checksum": key.reference_case_checksum,
        "dataset_version": key.dataset_version,
        "dataset_checksum": key.dataset_checksum,
        "partition_version": key.partition_version,
        "task_manifest_checksum": key.task_manifest_checksum,
        "oracle_version": key.oracle_version,
        "comparison_profile_version": key.comparison_profile_version,
        "evaluator_version": key.evaluator_version,
        "execution_profile_id": key.execution_profile_id,
        "execution_protocol_version": key.execution_protocol_version,
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
        dataset_checksum=data["dataset_checksum"],
        partition_version=data["partition_version"],
        task_manifest_checksum=data["task_manifest_checksum"],
        oracle_version=data["oracle_version"],
        comparison_profile_version=data["comparison_profile_version"],
        evaluator_version=data["evaluator_version"],
        execution_profile_id=data["execution_profile_id"],
        execution_protocol_version=data["execution_protocol_version"],
        key_digest=data["key_digest"],
    )
