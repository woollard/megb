"""MEGB-03G.2: the persistent, content-addressed reference-result cache.

Stores full-fidelity, privileged :class:`~src.reference.result_schema.ReferenceTaskResult`
objects under ``artifacts/privileged/reference/cache/`` (see
``docs/measurement/privileged-artifact-policy.md``), keyed by
:class:`~src.reference.cache_key.ReferenceResultCacheKey`. Never exposes
cached contents through any committed artifact or redacted projection --
this module has no such export function, by design.

Only ``VALID`` results are cacheable (:class:`NonCacheableResultError` on
any other status): invalid/incomplete measurements are never reused as if
valid, per the accepted amendment, and are simply never stored here --
MEGB-03G.3's resumption/retry policy tracks attempt history through the
audit log instead (see ``src.reference.reference_audit``), not through this
cache.

Every operation returns a typed :class:`CacheDisposition` rather than
raising for ordinary negative outcomes (miss, corrupt entry, conflicting
write, storage failure) -- callers (MEGB-03G.3) need to branch on these
programmatically, not catch exceptions for expected cache-layer states.
Only a genuine caller-contract violation (attempting to cache a non-VALID
result) raises.

Does not implement execution orchestration, bounded concurrency,
resumption, or backend invocation -- those belong to MEGB-03G.3, which
calls this cache's ``get``/``put`` around its own execution loop.
"""

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from src.reference.cache_key import (
    CACHE_KEY_SCHEMA_VERSION,
    ReferenceResultCacheKey,
    cache_key_for,
    cache_key_from_dict,
    cache_key_to_dict,
)
from src.reference.result_redaction import task_result_from_dict, task_result_to_dict
from src.reference.result_schema import (
    InvalidReferenceResultError,
    MeasurementStatus,
    ReferenceTaskResult,
    UnsupportedResultSchemaVersionError,
)

CACHE_ENTRY_SCHEMA_VERSION = "reference-result-cache-entry-v1"

DEFAULT_CACHE_DIR = Path("artifacts/privileged/reference/cache")


class NonCacheableResultError(ValueError):
    """Raised when :meth:`ReferenceResultCache.put` is asked to cache a
    non-``VALID`` :class:`~src.reference.result_schema.ReferenceTaskResult`.

    Invalid or incomplete measurements are never reused as if valid, and
    this cache never stores them at all -- attempting to do so is a caller
    contract violation, not a normal cache-layer outcome.
    """


class CacheDisposition(str, Enum):
    """Typed outcome of a cache ``get``/``put`` operation.

    Sufficient for MEGB-03G.3 to distinguish every outcome its orchestration
    loop needs to branch on, without raising for expected states.
    """

    VALID_HIT = "VALID_HIT"
    MISS = "MISS"
    STALE_INCOMPATIBLE = "STALE_INCOMPATIBLE"
    CORRUPT = "CORRUPT"
    WRITE_ACCEPTED = "WRITE_ACCEPTED"
    CONFLICTING_WRITE = "CONFLICTING_WRITE"
    STORAGE_INFRASTRUCTURE_FAILURE = "STORAGE_INFRASTRUCTURE_FAILURE"


@dataclass(frozen=True)
class CacheLookupResult:
    """Result of :meth:`ReferenceResultCache.get`.

    ``task_result`` is populated only when ``disposition`` is
    :attr:`CacheDisposition.VALID_HIT`; ``None`` for every other
    disposition.
    """

    disposition: CacheDisposition
    task_result: ReferenceTaskResult | None
    detail: str

    def __post_init__(self) -> None:
        if self.disposition == CacheDisposition.VALID_HIT:
            if self.task_result is None:
                raise ValueError("VALID_HIT must carry a task_result")
        elif self.task_result is not None:
            raise ValueError(
                f"{self.disposition.value} must not carry a task_result, got one anyway"
            )


@dataclass(frozen=True)
class CacheWriteResult:
    """Result of :meth:`ReferenceResultCache.put`."""

    disposition: CacheDisposition
    detail: str


def _entry_checksum(payload_without_checksum: dict[str, Any]) -> str:
    canonical = json.dumps(payload_without_checksum, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_entry_payload(
    key: ReferenceResultCacheKey, task_result: ReferenceTaskResult
) -> dict[str, Any]:
    return {
        "cache_entry_schema_version": CACHE_ENTRY_SCHEMA_VERSION,
        "cache_key_schema_version": CACHE_KEY_SCHEMA_VERSION,
        "cache_key": cache_key_to_dict(key),
        "task_result": task_result_to_dict(task_result),
    }


class ReferenceResultCache:
    """Persistent, content-addressed cache of privileged, ``VALID``
    :class:`~src.reference.result_schema.ReferenceTaskResult` objects.

    One file per cache key, named by the key's own ``key_digest``, under
    ``cache_dir`` (default: ``artifacts/privileged/reference/cache/``).
    Writes are atomic (temp file + ``os.replace``); a write that would
    silently overwrite a *different* valid entry under the same key is
    refused (:attr:`CacheDisposition.CONFLICTING_WRITE`) rather than
    clobbering it.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cache_dir(self) -> Path:
        """The directory this cache reads and writes entries under."""
        return self._cache_dir

    def _path_for(self, key: ReferenceResultCacheKey) -> Path:
        return self._cache_dir / f"{key.key_digest}.json"

    def get(self, key: ReferenceResultCacheKey) -> CacheLookupResult:
        """Look up a cached result for ``key``.

        Validates integrity, schema compatibility, and self-consistency
        before ever returning a hit -- a stale, mismatched, malformed,
        truncated, or checksum-invalid entry is never returned as valid.

        Split into small private stages (``_load_payload``,
        ``_check_envelope``, ``_reconstruct_and_verify``) purely to keep
        each stage's own branch count small and independently readable;
        together they perform exactly the single validation pipeline
        described above.
        """
        path = self._path_for(key)
        payload, early_result = self._load_payload(path)
        if early_result is not None:
            return early_result
        assert payload is not None  # narrows type for the stages below

        early_result = self._check_envelope(payload)
        if early_result is not None:
            return early_result

        return self._reconstruct_and_verify(payload, key)

    def _load_payload(self, path: Path) -> tuple[dict[str, Any] | None, CacheLookupResult | None]:
        """Read and JSON-parse the entry at ``path``.

        Returns ``(payload, None)`` on success, or ``(None, <result>)`` for
        a miss, storage failure, or malformed/non-object JSON.
        """
        try:
            if not path.exists():
                return None, CacheLookupResult(
                    CacheDisposition.MISS, None, "no cache entry for this key"
                )
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            return None, CacheLookupResult(
                CacheDisposition.STORAGE_INFRASTRUCTURE_FAILURE,
                None,
                f"error reading cache entry: {exc}",
            )

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return None, CacheLookupResult(CacheDisposition.CORRUPT, None, f"malformed JSON: {exc}")

        if not isinstance(payload, dict):
            return None, CacheLookupResult(
                CacheDisposition.CORRUPT, None, "entry payload is not a JSON object"
            )
        return payload, None

    def _check_envelope(self, payload: dict[str, Any]) -> CacheLookupResult | None:
        """Verify schema versions and the integrity checksum.

        Schema/version-shape checks run before checksum checking: an
        envelope in a shape this module doesn't recognize is
        STALE_INCOMPATIBLE regardless of whether its checksum happens to be
        internally consistent, rather than CORRUPT. Returns ``None`` when
        every check passes.
        """
        if payload.get("cache_entry_schema_version") != CACHE_ENTRY_SCHEMA_VERSION:
            return CacheLookupResult(
                CacheDisposition.STALE_INCOMPATIBLE,
                None,
                f"cache_entry_schema_version {payload.get('cache_entry_schema_version')!r} "
                f"does not match {CACHE_ENTRY_SCHEMA_VERSION!r}",
            )
        if payload.get("cache_key_schema_version") != CACHE_KEY_SCHEMA_VERSION:
            return CacheLookupResult(
                CacheDisposition.STALE_INCOMPATIBLE,
                None,
                f"cache_key_schema_version {payload.get('cache_key_schema_version')!r} "
                f"does not match {CACHE_KEY_SCHEMA_VERSION!r}",
            )

        try:
            stored_checksum = payload["entry_checksum"]
        except KeyError:
            return CacheLookupResult(CacheDisposition.CORRUPT, None, "missing entry_checksum field")

        payload_without_checksum = {k: v for k, v in payload.items() if k != "entry_checksum"}
        expected_checksum = _entry_checksum(payload_without_checksum)
        if stored_checksum != expected_checksum:
            return CacheLookupResult(
                CacheDisposition.CORRUPT,
                None,
                "entry_checksum mismatch -- tampered or truncated cache entry",
            )
        return None

    def _reconstruct_and_verify(
        self, payload: dict[str, Any], key: ReferenceResultCacheKey
    ) -> CacheLookupResult:
        """Reconstruct the stored key/result and verify self-consistency
        against the requested ``key``. Assumes :meth:`_check_envelope`
        already passed."""
        try:
            stored_key = cache_key_from_dict(payload["cache_key"])
            task_result = task_result_from_dict(payload["task_result"])
        except (
            KeyError,
            InvalidReferenceResultError,
            UnsupportedResultSchemaVersionError,
        ) as exc:
            return CacheLookupResult(
                CacheDisposition.CORRUPT, None, f"malformed entry contents: {exc}"
            )

        if stored_key != key:
            return CacheLookupResult(
                CacheDisposition.CORRUPT, None, "stored cache key does not match the requested key"
            )
        if task_result.status != MeasurementStatus.VALID:
            return CacheLookupResult(
                CacheDisposition.CORRUPT, None, "cache entry does not contain a VALID result"
            )
        if cache_key_for(task_result) != key:
            return CacheLookupResult(
                CacheDisposition.CORRUPT,
                None,
                "task_result content does not reproduce its own stored cache key",
            )
        return CacheLookupResult(CacheDisposition.VALID_HIT, task_result, "valid cache hit")

    def put(self, task_result: ReferenceTaskResult) -> CacheWriteResult:
        """Store ``task_result`` under its own derived cache key.

        Raises :class:`NonCacheableResultError` if ``task_result.status``
        is not ``VALID`` -- this cache never stores invalid/incomplete
        results. An identical entry already present under the same key is
        treated as an idempotent no-op write; a *different* entry under the
        same key is refused as :attr:`CacheDisposition.CONFLICTING_WRITE`.
        """
        if task_result.status != MeasurementStatus.VALID:
            raise NonCacheableResultError(
                f"task {task_result.task_id!r}: only VALID results may be cached, "
                f"got status={task_result.status.value!r}"
            )

        key = cache_key_for(task_result)
        path = self._path_for(key)
        payload = _build_entry_payload(key, task_result)
        checksum = _entry_checksum(payload)
        payload_with_checksum = {**payload, "entry_checksum": checksum}
        serialized = json.dumps(payload_with_checksum, indent=2, sort_keys=True)

        try:
            if path.exists():
                try:
                    existing_payload = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    return CacheWriteResult(
                        CacheDisposition.CONFLICTING_WRITE,
                        "an existing (corrupt) entry occupies this cache key; "
                        "refusing to overwrite",
                    )
                if existing_payload.get("task_result") != payload["task_result"]:
                    return CacheWriteResult(
                        CacheDisposition.CONFLICTING_WRITE,
                        "a different valid entry already exists under this cache key",
                    )
                return CacheWriteResult(
                    CacheDisposition.WRITE_ACCEPTED,
                    "identical entry already present (idempotent write)",
                )

            tmp_path = path.with_name(f".tmp-{uuid.uuid4().hex}-{path.name}")
            tmp_path.write_text(serialized, encoding="utf-8")
            os.replace(tmp_path, path)
        except OSError as exc:
            return CacheWriteResult(
                CacheDisposition.STORAGE_INFRASTRUCTURE_FAILURE, f"error writing cache entry: {exc}"
            )

        return CacheWriteResult(CacheDisposition.WRITE_ACCEPTED, "new entry written")
