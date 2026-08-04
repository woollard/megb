"""MEGB-03H.2C.3B.1: shared checksum/validation primitives for every type
in ``src.distributed``.

Kept in its own small module (rather than duplicated privately per file,
or imported across a `_`-prefixed private boundary) so every type in this
package -- :mod:`~src.distributed.provenance`,
:mod:`~src.distributed.protected_mapping`,
:mod:`~src.distributed.safe_summary`, :mod:`~src.distributed.identity`,
:mod:`~src.distributed.qualification_gate` -- shares exactly one
canonicalization/checksum scheme and one schema-version/checksum-
algorithm-version enforcement path. Deliberately independent of
``src.reference.calibration_schema``'s own private helpers of the same
shape (this package must never import ``src.reference`` at all -- see
each module's own docstring).
"""

import hashlib
import json
from typing import Any, Iterable, Mapping

DISTRIBUTED_PROVENANCE_SCHEMA_VERSION = "megb-03h2c3b1-distributed-provenance-v1"
CHECKSUM_ALGORITHM_VERSION = "sha256-canonical-json-v1"


class InvalidDistributedProvenanceError(ValueError):
    """Raised when a distributed-provenance record's fields are internally
    inconsistent, or a stamped checksum does not match its own recomputed
    contents (tampered or corrupted record)."""


class UnsupportedDistributedProvenanceSchemaVersionError(InvalidDistributedProvenanceError):
    """Raised when deserializing a payload stamped with a different
    ``DISTRIBUTED_PROVENANCE_SCHEMA_VERSION`` than this package currently
    implements."""


class UnsupportedChecksumAlgorithmVersionError(InvalidDistributedProvenanceError):
    """Raised when a record declares a ``checksum_algorithm_version`` other
    than :data:`CHECKSUM_ALGORITHM_VERSION` -- an explicit, typed failure
    rather than silently trusting or reinterpreting an unrecognized
    checksum scheme."""


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Deterministic, cross-process-stable JSON encoding used as the input
    to every checksum in this package."""
    return json.dumps(payload, sort_keys=True)


def sha256_of(payload: Mapping[str, Any]) -> str:
    """The one checksum function every self-checksummed type in this
    package uses -- sha256 over :func:`canonical_json`, matching
    :data:`CHECKSUM_ALGORITHM_VERSION`."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def require_nonempty_str(obj: object, field_name: str) -> None:
    """Raise unless ``getattr(obj, field_name)`` is a nonempty ``str``."""
    value = getattr(obj, field_name)
    if not isinstance(value, str) or value == "":
        raise InvalidDistributedProvenanceError(
            f"{field_name!r} must be a nonempty string, got {value!r}"
        )


def require_nonempty_str_fields(obj: object, field_names: Iterable[str]) -> None:
    """:func:`require_nonempty_str` applied to every name in ``field_names``
    -- shared by every type in this package with more than one plain
    string field, so the same validation loop is never duplicated per
    type."""
    for field_name in field_names:
        require_nonempty_str(obj, field_name)


_SHA256_HEX_LENGTH = 64
_SHA256_HEX_ALPHABET = frozenset("0123456789abcdef")


def require_sha256_hex(obj: object, field_name: str) -> None:
    """Raise unless ``getattr(obj, field_name)`` is a 64-character
    lowercase hex sha256 digest."""
    value = getattr(obj, field_name)
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_HEX_LENGTH
        or not set(value) <= _SHA256_HEX_ALPHABET
    ):
        raise InvalidDistributedProvenanceError(
            f"{field_name!r} must be a 64-character lowercase hex sha256 digest, got {value!r}"
        )


def require_non_negative_int(obj: object, field_name: str) -> None:
    """Raise unless ``getattr(obj, field_name)`` is a non-negative ``int``."""
    value = getattr(obj, field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvalidDistributedProvenanceError(
            f"{field_name!r} must be a non-negative int, got {value!r}"
        )


def require_positive_float(obj: object, field_name: str) -> None:
    """Raise unless ``getattr(obj, field_name)`` is a positive number."""
    value = getattr(obj, field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise InvalidDistributedProvenanceError(
            f"{field_name!r} must be a positive number, got {value!r}"
        )


def require_checksum_algorithm_version(obj: object) -> None:
    """Raise unless ``obj.checksum_algorithm_version`` matches
    :data:`CHECKSUM_ALGORITHM_VERSION`."""
    value = getattr(obj, "checksum_algorithm_version")
    if value != CHECKSUM_ALGORITHM_VERSION:
        raise UnsupportedChecksumAlgorithmVersionError(
            f"checksum_algorithm_version {value!r} does not match the version this package "
            f"implements ({CHECKSUM_ALGORITHM_VERSION!r})"
        )


def require_schema_version(obj: object) -> None:
    """Raise unless ``obj.distributed_provenance_schema_version`` matches
    :data:`DISTRIBUTED_PROVENANCE_SCHEMA_VERSION`."""
    value = getattr(obj, "distributed_provenance_schema_version")
    if value != DISTRIBUTED_PROVENANCE_SCHEMA_VERSION:
        raise UnsupportedDistributedProvenanceSchemaVersionError(
            f"distributed_provenance_schema_version {value!r} does not match the version this "
            f"package implements ({DISTRIBUTED_PROVENANCE_SCHEMA_VERSION!r})"
        )
