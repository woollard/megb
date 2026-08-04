"""MEGB-03H.2C.3B.1: the protected operational mapping -- the schema
boundary for information that may be necessary operationally but must
never enter a safe committed report.

Joined back to a :class:`~src.distributed.provenance.DistributedRunContext`
only via ``logical_environment_id`` (the safe, pseudonymous label), never
via any field that also appears in a safe/qualification/production
identity -- mirroring this project's own established
``reference_case_checksum`` (safe, committed) vs. the real, privileged
case content it is derived from split.

This type is deliberately never imported by
:mod:`src.distributed.safe_summary` or
:mod:`src.distributed.identity` -- there is no code path from this
module's own fields into any safe-report type, which is the strongest
available guarantee against accidental leakage (structural absence of an
import, not merely a runtime allowlist check).
"""

import re
from dataclasses import dataclass
from typing import Any, Mapping

from src.distributed._checksums import (
    CHECKSUM_ALGORITHM_VERSION,
    DISTRIBUTED_PROVENANCE_SCHEMA_VERSION,
    InvalidDistributedProvenanceError,
    require_checksum_algorithm_version as _require_checksum_algorithm_version,
    require_nonempty_str as _require_nonempty_str,
    require_schema_version as _require_schema_version,
    sha256_of as _sha256_of,
)

# Defense-in-depth only -- not a complete secret-detection guarantee. These
# patterns catch the shapes this project's own validation scripts already
# check for elsewhere (see the MEGB-03H.2C.3A checkpoint reports' own
# secret-pattern scans): PEM/private-key headers, a GCP service-account
# JSON marker, and a small set of well-known cloud-credential prefixes.
# A caller must still never pass a real secret value into this type in the
# first place -- this is a backstop, not the primary control.
_SECRET_LOOKING_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r'"type"\s*:\s*"service_account"'),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    re.compile(r"ya29\.[0-9A-Za-z_\-]+"),
    re.compile(r"xox[baprs]-[0-9A-Za-z\-]+"),
)


def _reject_if_looks_like_secret(value: str, field_name: str) -> None:
    for pattern in _SECRET_LOOKING_PATTERNS:
        if pattern.search(value):
            raise InvalidDistributedProvenanceError(
                f"{field_name!r} contains a value matching a known credential/secret shape -- "
                f"refusing to construct a ProtectedOperationalMapping carrying it. Credentials, "
                f"tokens, private keys, and secret values must never be persisted under any "
                f"circumstance, including here."
            )


def _require_nonempty_str_tuple(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, tuple) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise InvalidDistributedProvenanceError(
            f"{field_name!r} must be a tuple of nonempty strings, got {value!r}"
        )
    for item in value:
        _reject_if_looks_like_secret(item, field_name)


@dataclass(frozen=True)
class ProtectedOperationalMapping:  # pylint: disable=too-many-instance-attributes
    """Raw infrastructure identifiers for one logical environment,
    joined back to a :class:`~src.distributed.provenance.DistributedRunContext`
    only by ``logical_environment_id``.

    Every field here is exactly the raw-identifier category the
    authorization names: cloud project IDs, subscription/account
    identifiers, instance names/IDs, hostnames, container IDs, filesystem
    paths, service-account identities, credential *references* (never
    values), and resource names that reveal infrastructure identity. None
    of these fields exists on any safe or qualification/production
    identity type in this package -- there is no field to accidentally
    reuse.

    This type must never be serialized into, or embedded within, any
    committed report. It exists so an operator can reconstruct which real
    infrastructure a ``logical_environment_id`` refers to, held entirely
    outside any committed, publicly-readable artifact.
    """

    distributed_provenance_schema_version: str
    checksum_algorithm_version: str
    logical_environment_id: str
    raw_cloud_project_id: str
    raw_subscription_or_account_id: str | None
    raw_instance_identifiers: tuple[str, ...]
    raw_hostnames: tuple[str, ...]
    raw_container_ids: tuple[str, ...]
    raw_filesystem_paths: tuple[str, ...]
    raw_service_account_identities: tuple[str, ...]
    raw_credential_references: tuple[str, ...]
    raw_resource_names: tuple[str, ...]
    mapping_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        _require_schema_version(self)
        _require_checksum_algorithm_version(self)
        _require_nonempty_str(self, "logical_environment_id")
        _require_nonempty_str(self, "raw_cloud_project_id")
        _reject_if_looks_like_secret(self.raw_cloud_project_id, "raw_cloud_project_id")
        if self.raw_subscription_or_account_id is not None:
            if (
                not isinstance(self.raw_subscription_or_account_id, str)
                or self.raw_subscription_or_account_id == ""
            ):
                raise InvalidDistributedProvenanceError(
                    "raw_subscription_or_account_id must be a nonempty string or None, got "
                    f"{self.raw_subscription_or_account_id!r}"
                )
            _reject_if_looks_like_secret(
                self.raw_subscription_or_account_id, "raw_subscription_or_account_id"
            )
        for field_name in (
            "raw_instance_identifiers",
            "raw_hostnames",
            "raw_container_ids",
            "raw_filesystem_paths",
            "raw_service_account_identities",
            "raw_credential_references",
            "raw_resource_names",
        ):
            _require_nonempty_str_tuple(self, field_name)

        payload = _protected_operational_mapping_payload(self)
        expected_checksum = _sha256_of(payload)
        if self.mapping_checksum and self.mapping_checksum != expected_checksum:
            raise InvalidDistributedProvenanceError(
                f"mapping_checksum {self.mapping_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted protected operational mapping"
            )
        object.__setattr__(self, "mapping_checksum", expected_checksum)


def _protected_operational_mapping_payload(mapping: ProtectedOperationalMapping) -> dict[str, Any]:
    return {
        "distributed_provenance_schema_version": mapping.distributed_provenance_schema_version,
        "checksum_algorithm_version": mapping.checksum_algorithm_version,
        "logical_environment_id": mapping.logical_environment_id,
        "raw_cloud_project_id": mapping.raw_cloud_project_id,
        "raw_subscription_or_account_id": mapping.raw_subscription_or_account_id,
        "raw_instance_identifiers": list(mapping.raw_instance_identifiers),
        "raw_hostnames": list(mapping.raw_hostnames),
        "raw_container_ids": list(mapping.raw_container_ids),
        "raw_filesystem_paths": list(mapping.raw_filesystem_paths),
        "raw_service_account_identities": list(mapping.raw_service_account_identities),
        "raw_credential_references": list(mapping.raw_credential_references),
        "raw_resource_names": list(mapping.raw_resource_names),
    }


def protected_operational_mapping_to_dict(
    mapping: ProtectedOperationalMapping,
) -> dict[str, Any]:
    """Full-fidelity serialization -- for protected operational storage
    ONLY, never for a committed report. Callers are responsible for never
    routing this output into any safe artifact."""
    return {
        **_protected_operational_mapping_payload(mapping),
        "mapping_checksum": mapping.mapping_checksum,
    }


def protected_operational_mapping_from_dict(
    data: Mapping[str, Any],
) -> ProtectedOperationalMapping:
    """Inverse of :func:`protected_operational_mapping_to_dict`."""
    try:
        return ProtectedOperationalMapping(
            distributed_provenance_schema_version=data["distributed_provenance_schema_version"],
            checksum_algorithm_version=data["checksum_algorithm_version"],
            logical_environment_id=data["logical_environment_id"],
            raw_cloud_project_id=data["raw_cloud_project_id"],
            raw_subscription_or_account_id=data["raw_subscription_or_account_id"],
            raw_instance_identifiers=tuple(data["raw_instance_identifiers"]),
            raw_hostnames=tuple(data["raw_hostnames"]),
            raw_container_ids=tuple(data["raw_container_ids"]),
            raw_filesystem_paths=tuple(data["raw_filesystem_paths"]),
            raw_service_account_identities=tuple(data["raw_service_account_identities"]),
            raw_credential_references=tuple(data["raw_credential_references"]),
            raw_resource_names=tuple(data["raw_resource_names"]),
            mapping_checksum=data["mapping_checksum"],
        )
    except KeyError as exc:
        raise InvalidDistributedProvenanceError(
            f"missing required protected operational mapping field: {exc}"
        ) from exc


__all__ = [
    "ProtectedOperationalMapping",
    "protected_operational_mapping_to_dict",
    "protected_operational_mapping_from_dict",
    "CHECKSUM_ALGORITHM_VERSION",
    "DISTRIBUTED_PROVENANCE_SCHEMA_VERSION",
]
