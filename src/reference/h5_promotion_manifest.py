"""MEGB-03H.2B.2: the typed, immutable, versioned, self-checksummed H.5
staging/promotion manifest.

Records the frozen run identity, the expected ordered task/key set, staged-
entry identities and content checksums, the complete-run gate result, the
production-cache preflight result, per-entry promotion state, and the
overall promotion state -- everything a later, independent process needs to
resume promotion idempotently without re-running the scientific gate
against a different staged set (see :func:`advance_manifest`'s transition
enforcement and :func:`load_promotion_manifest`'s identity verification).

Every update produces a *new* immutable instance (via :func:`advance_manifest`,
never in-place mutation) with a freshly recomputed ``manifest_checksum`` and
an incremented ``generation`` -- mirroring the auto-compute-or-reject
checksum pattern already established throughout this codebase
(:class:`~src.reference.result_schema.ReferenceValidationCandidateSetManifest`,
:class:`~src.reference.cache_key.ReferenceResultCacheKey`, every calibration
record). Persisted via atomic temp-file + ``os.replace``, with an explicit
``flush()``/``fsync()`` before the rename -- the same durability discipline
:class:`~src.reference.calibration_trace.CalibrationTraceStore` already uses
for the calibration trace itself.
"""

# _identity_from_dict's field-by-field reconstruction intentionally mirrors
# cache_key.py's own cache_key_from_dict shape -- both rebuild the same
# recurring identity vocabulary from a plain dict. Expected and accepted,
# not a defect (see h5_staging.py's own equivalent note).
# pylint: disable=duplicate-code

import dataclasses
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.reference.cache_key import cache_key_for
from src.reference.h5_staging import H5StagingIdentity
from src.reference.result_redaction import task_result_to_dict
from src.reference.result_schema import ReferenceTaskResult

H5_PROMOTION_MANIFEST_SCHEMA_VERSION = "megb-03h5-promotion-manifest-v1"

_SHA256_HEX_LEN = 64


class InvalidPromotionManifestError(ValueError):
    """Raised when a promotion manifest's fields are internally
    inconsistent, or its checksum does not match its own recomputed
    contents (tampered or corrupted manifest)."""


class UnsupportedPromotionManifestSchemaVersionError(InvalidPromotionManifestError):
    """Raised when deserializing a payload stamped with a different
    ``H5_PROMOTION_MANIFEST_SCHEMA_VERSION`` than this module implements."""


class PromotionStateTransitionError(InvalidPromotionManifestError):
    """Raised by :func:`advance_manifest` when the requested new
    ``PromotionState`` is not a legal transition from the manifest's
    current state."""


class PromotionManifestIdentityMismatchError(InvalidPromotionManifestError):
    """Raised when a caller's supplied :class:`~src.reference.h5_staging.H5StagingIdentity`
    does not match an existing, on-disk manifest's own frozen identity --
    staging from one run/profile/manifest identity must never resume or
    satisfy another's."""


class PromotionManifestWriteError(InvalidPromotionManifestError):
    """Raised when a durable manifest write (temp-file + flush + fsync +
    atomic replace) fails."""


class PromotionState(str, Enum):
    """Overall promotion-manifest lifecycle state."""

    PREPARED = "PREPARED"
    GATE_PASSED = "GATE_PASSED"
    PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
    PROMOTING = "PROMOTING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class EntryPromotionState(str, Enum):
    """Per-task-id promotion progress within one manifest."""

    PENDING = "PENDING"
    ALREADY_SATISFIED = "ALREADY_SATISFIED"
    PROMOTED = "PROMOTED"


class PreflightClassification(str, Enum):
    """Read-only production-cache classification for one prospective entry."""

    ABSENT = "ABSENT"
    IDENTICAL_VALID = "IDENTICAL_VALID"
    CONFLICTING = "CONFLICTING"
    CORRUPT_OR_STALE = "CORRUPT_OR_STALE"
    STORAGE_FAILURE = "STORAGE_FAILURE"


_ALLOWED_TRANSITIONS: Mapping[PromotionState, frozenset[PromotionState]] = {
    PromotionState.PREPARED: frozenset({PromotionState.GATE_PASSED, PromotionState.BLOCKED}),
    PromotionState.GATE_PASSED: frozenset(
        {PromotionState.PREFLIGHT_PASSED, PromotionState.BLOCKED}
    ),
    PromotionState.PREFLIGHT_PASSED: frozenset(
        {PromotionState.PROMOTING, PromotionState.BLOCKED}
    ),
    PromotionState.PROMOTING: frozenset({PromotionState.COMPLETED, PromotionState.BLOCKED}),
    PromotionState.COMPLETED: frozenset(),
    PromotionState.BLOCKED: frozenset(),
}


def _require_nonempty_str(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or value == "":
        raise InvalidPromotionManifestError(
            f"{field_name!r} must be a nonempty string, got {value!r}"
        )


def _require_sha256_hex(obj: object, field_name: str) -> None:
    value = getattr(obj, field_name)
    if not isinstance(value, str) or len(value) != _SHA256_HEX_LEN:
        raise InvalidPromotionManifestError(
            f"{field_name!r} must be a {_SHA256_HEX_LEN}-character hex digest, got {value!r}"
        )


@dataclass(frozen=True)
class StagedEntryRecord:
    """One approved task's staged identity: its cache-key digest and a
    content checksum of the staged :class:`~src.reference.result_schema.ReferenceTaskResult`
    -- never the result's own content, only its identity/checksum."""

    task_id: str
    cache_key_digest: str
    content_checksum: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self, "task_id")
        _require_sha256_hex(self, "cache_key_digest")
        _require_sha256_hex(self, "content_checksum")


def content_checksum_for(result: ReferenceTaskResult) -> str:
    """A stable content checksum for one staged
    :class:`~src.reference.result_schema.ReferenceTaskResult` -- never the
    result's own content, only an identity/tamper-evidence checksum over
    its canonical (redaction-schema) serialization."""
    return _checksum_of(task_result_to_dict(result))


def build_staged_entries(
    task_results: Sequence[ReferenceTaskResult],
) -> tuple[StagedEntryRecord, ...]:
    """Build one :class:`StagedEntryRecord` per ``task_results`` entry,
    sorted by ``task_id`` (canonical order)."""
    entries = [
        StagedEntryRecord(
            task_id=result.task_id,
            cache_key_digest=cache_key_for(result).key_digest,
            content_checksum=content_checksum_for(result),
        )
        for result in task_results
    ]
    return tuple(sorted(entries, key=lambda entry: entry.task_id))


@dataclass(frozen=True)
class GateOutcome:
    """The recorded :class:`~src.reference.h5_staging.GateResult` (safe
    projection -- ``passed``/``reason`` only, never the full benchmark
    result)."""

    passed: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.passed, bool):
            raise InvalidPromotionManifestError(f"passed must be a bool, got {self.passed!r}")
        _require_nonempty_str(self, "reason")


@dataclass(frozen=True)
class PreflightEntryResult:
    """One prospective entry's read-only production-cache classification."""

    task_id: str
    classification: PreflightClassification
    detail: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self, "task_id")
        if not isinstance(self.classification, PreflightClassification):
            raise InvalidPromotionManifestError(
                f"classification must be a PreflightClassification, got {self.classification!r}"
            )
        _require_nonempty_str(self, "detail")


@dataclass(frozen=True)
class PreflightOutcome:
    """Aggregate production-cache preflight result across every approved entry."""

    passed: bool
    reason: str
    entries: tuple[PreflightEntryResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.passed, bool):
            raise InvalidPromotionManifestError(f"passed must be a bool, got {self.passed!r}")
        _require_nonempty_str(self, "reason")
        for entry in self.entries:
            if not isinstance(entry, PreflightEntryResult):
                raise InvalidPromotionManifestError(
                    f"entries must contain only PreflightEntryResult, got {entry!r}"
                )


@dataclass(frozen=True)
class H5PromotionManifest:  # pylint: disable=too-many-instance-attributes
    """The complete, immutable H.5 staging/promotion manifest for one frozen
    run identity. Never mutated in place -- use :func:`advance_manifest` to
    produce the next generation."""

    manifest_schema_version: str
    identity: H5StagingIdentity
    expected_task_ids: tuple[str, ...]
    staged_entries: tuple[StagedEntryRecord, ...]
    gate_outcome: GateOutcome | None
    preflight_outcome: PreflightOutcome | None
    entry_states: Mapping[str, EntryPromotionState]
    state: PromotionState
    interrupted: bool = False
    generation: int = 0
    manifest_checksum: str = ""

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        if self.manifest_schema_version != H5_PROMOTION_MANIFEST_SCHEMA_VERSION:
            raise UnsupportedPromotionManifestSchemaVersionError(
                f"manifest_schema_version {self.manifest_schema_version!r} does not match the "
                f"version this module implements ({H5_PROMOTION_MANIFEST_SCHEMA_VERSION!r})"
            )
        if not isinstance(self.identity, H5StagingIdentity):
            raise InvalidPromotionManifestError(
                f"identity must be an H5StagingIdentity, got {type(self.identity).__name__}"
            )
        if len(self.expected_task_ids) != len(set(self.expected_task_ids)):
            raise InvalidPromotionManifestError("expected_task_ids contains duplicates")
        if tuple(sorted(self.expected_task_ids)) != tuple(self.expected_task_ids):
            raise InvalidPromotionManifestError(
                "expected_task_ids must be sorted (canonical order)"
            )
        expected = set(self.expected_task_ids)
        staged_task_ids = {entry.task_id for entry in self.staged_entries}
        if self.state == PromotionState.PREPARED:
            if staged_task_ids:
                raise InvalidPromotionManifestError(
                    "PREPARED must not carry any staged_entries -- staging has not run yet"
                )
        elif staged_task_ids != expected:
            raise InvalidPromotionManifestError(
                f"staged_entries task_id set {sorted(staged_task_ids)!r} does not match "
                f"expected_task_ids {sorted(expected)!r}"
            )
        if set(self.entry_states) != expected:
            raise InvalidPromotionManifestError(
                f"entry_states keys {sorted(self.entry_states)!r} do not match "
                f"expected_task_ids {sorted(expected)!r}"
            )
        for task_id, entry_state in self.entry_states.items():
            if not isinstance(entry_state, EntryPromotionState):
                raise InvalidPromotionManifestError(
                    f"entry_states[{task_id!r}] must be an EntryPromotionState, "
                    f"got {entry_state!r}"
                )
        if not isinstance(self.state, PromotionState):
            raise InvalidPromotionManifestError(
                f"state must be a PromotionState, got {self.state!r}"
            )
        if not isinstance(self.interrupted, bool):
            raise InvalidPromotionManifestError(
                f"interrupted must be a bool, got {self.interrupted!r}"
            )
        generation_ok = (
            isinstance(self.generation, int)
            and not isinstance(self.generation, bool)
            and self.generation >= 0
        )
        if not generation_ok:
            raise InvalidPromotionManifestError(
                f"generation must be a non-negative int, got {self.generation!r}"
            )
        self._validate_state_invariants()

        payload = _manifest_payload(self)
        expected_checksum = _checksum_of(payload)
        if self.manifest_checksum and self.manifest_checksum != expected_checksum:
            raise InvalidPromotionManifestError(
                f"manifest_checksum {self.manifest_checksum!r} does not match the recomputed "
                f"checksum {expected_checksum!r} over its own contents -- tampered or "
                f"corrupted promotion manifest"
            )
        object.__setattr__(self, "manifest_checksum", expected_checksum)

    def _validate_state_invariants(self) -> None:
        if self.state == PromotionState.PREPARED:
            if self.gate_outcome is not None or self.preflight_outcome is not None:
                raise InvalidPromotionManifestError(
                    "PREPARED must not carry a gate_outcome or preflight_outcome"
                )
            if any(value != EntryPromotionState.PENDING for value in self.entry_states.values()):
                raise InvalidPromotionManifestError("PREPARED requires every entry_state PENDING")
            return
        if self.state in (
            PromotionState.GATE_PASSED,
            PromotionState.PREFLIGHT_PASSED,
            PromotionState.PROMOTING,
            PromotionState.COMPLETED,
        ):
            if self.gate_outcome is None or not self.gate_outcome.passed:
                raise InvalidPromotionManifestError(
                    f"{self.state.value} requires a passed gate_outcome"
                )
        if self.state in (
            PromotionState.PREFLIGHT_PASSED,
            PromotionState.PROMOTING,
            PromotionState.COMPLETED,
        ):
            if self.preflight_outcome is None or not self.preflight_outcome.passed:
                raise InvalidPromotionManifestError(
                    f"{self.state.value} requires a passed preflight_outcome"
                )
        if self.state == PromotionState.COMPLETED:
            if any(value == EntryPromotionState.PENDING for value in self.entry_states.values()):
                raise InvalidPromotionManifestError(
                    "COMPLETED requires every entry_state to be PROMOTED or ALREADY_SATISFIED"
                )
        if self.state == PromotionState.BLOCKED:
            gate_failed = self.gate_outcome is not None and not self.gate_outcome.passed
            preflight = self.preflight_outcome
            preflight_failed = preflight is not None and not preflight.passed
            if not (gate_failed or preflight_failed):
                raise InvalidPromotionManifestError(
                    "BLOCKED requires a failed gate_outcome or a failed preflight_outcome"
                )


def advance_manifest(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    manifest: H5PromotionManifest,
    *,
    state: PromotionState | None = None,
    gate_outcome: GateOutcome | None = None,
    preflight_outcome: PreflightOutcome | None = None,
    staged_entries: tuple[StagedEntryRecord, ...] | None = None,
    entry_states: Mapping[str, EntryPromotionState] | None = None,
    interrupted: bool | None = None,
) -> H5PromotionManifest:
    """Produce the next generation of ``manifest`` -- never mutates
    ``manifest`` itself. Raises :class:`PromotionStateTransitionError` if
    ``state`` names an illegal transition from ``manifest.state``.

    ``staged_entries`` is normally supplied exactly once, when transitioning
    ``PREPARED`` -> ``GATE_PASSED`` (the gate's own approved staged-entry
    identities/checksums) -- ``PREPARED`` itself must never carry any.
    """
    new_state = state if state is not None else manifest.state
    if new_state != manifest.state:
        allowed = _ALLOWED_TRANSITIONS.get(manifest.state, frozenset())
        if new_state not in allowed:
            raise PromotionStateTransitionError(
                f"illegal promotion-state transition: {manifest.state.value} -> {new_state.value}"
            )
    return dataclasses.replace(
        manifest,
        state=new_state,
        gate_outcome=gate_outcome if gate_outcome is not None else manifest.gate_outcome,
        preflight_outcome=(
            preflight_outcome if preflight_outcome is not None else manifest.preflight_outcome
        ),
        staged_entries=staged_entries if staged_entries is not None else manifest.staged_entries,
        entry_states=entry_states if entry_states is not None else manifest.entry_states,
        interrupted=interrupted if interrupted is not None else manifest.interrupted,
        generation=manifest.generation + 1,
        manifest_checksum="",
    )


def build_initial_manifest(
    identity: H5StagingIdentity, expected_task_ids: tuple[str, ...]
) -> H5PromotionManifest:
    """Build a fresh, ``PREPARED`` manifest for ``identity`` -- generation 0,
    no staged entries yet, every entry PENDING."""
    sorted_ids = tuple(sorted(expected_task_ids))
    return H5PromotionManifest(
        manifest_schema_version=H5_PROMOTION_MANIFEST_SCHEMA_VERSION,
        identity=identity,
        expected_task_ids=sorted_ids,
        staged_entries=(),
        gate_outcome=None,
        preflight_outcome=None,
        entry_states={task_id: EntryPromotionState.PENDING for task_id in sorted_ids},
        state=PromotionState.PREPARED,
    )


# ---------------------------------------------------------------------------
# Serialization (canonical dict <-> typed object), checksum, durable I/O
# ---------------------------------------------------------------------------


def _checksum_of(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _identity_to_dict(identity: H5StagingIdentity) -> dict[str, Any]:
    return dataclasses.asdict(identity)


def _identity_from_dict(data: Mapping[str, Any]) -> H5StagingIdentity:
    return H5StagingIdentity(
        calibration_run_id=data["calibration_run_id"],
        execution_profile_id=data["execution_profile_id"],
        evaluator_version=data["evaluator_version"],
        execution_protocol_version=data["execution_protocol_version"],
        dataset_version=data["dataset_version"],
        dataset_checksum=data["dataset_checksum"],
        partition_version=data["partition_version"],
        task_manifest_checksum=data["task_manifest_checksum"],
        oracle_version=data["oracle_version"],
        comparison_profile_version=data["comparison_profile_version"],
        candidate_set_manifest_checksum=data["candidate_set_manifest_checksum"],
        expected_task_count=data["expected_task_count"],
    )


def _staged_entry_to_dict(entry: StagedEntryRecord) -> dict[str, Any]:
    return dataclasses.asdict(entry)


def _staged_entry_from_dict(data: Mapping[str, Any]) -> StagedEntryRecord:
    return StagedEntryRecord(
        task_id=data["task_id"],
        cache_key_digest=data["cache_key_digest"],
        content_checksum=data["content_checksum"],
    )


def _gate_outcome_to_dict(outcome: GateOutcome) -> dict[str, Any]:
    return {"passed": outcome.passed, "reason": outcome.reason}


def _gate_outcome_from_dict(data: Mapping[str, Any]) -> GateOutcome:
    return GateOutcome(passed=data["passed"], reason=data["reason"])


def _preflight_entry_to_dict(entry: PreflightEntryResult) -> dict[str, Any]:
    return {
        "task_id": entry.task_id,
        "classification": entry.classification.value,
        "detail": entry.detail,
    }


def _preflight_entry_from_dict(data: Mapping[str, Any]) -> PreflightEntryResult:
    return PreflightEntryResult(
        task_id=data["task_id"],
        classification=PreflightClassification(data["classification"]),
        detail=data["detail"],
    )


def _preflight_outcome_to_dict(outcome: PreflightOutcome) -> dict[str, Any]:
    return {
        "passed": outcome.passed,
        "reason": outcome.reason,
        "entries": [_preflight_entry_to_dict(entry) for entry in outcome.entries],
    }


def _preflight_outcome_from_dict(data: Mapping[str, Any]) -> PreflightOutcome:
    return PreflightOutcome(
        passed=data["passed"],
        reason=data["reason"],
        entries=tuple(_preflight_entry_from_dict(entry) for entry in data["entries"]),
    )


def _manifest_payload(manifest: H5PromotionManifest) -> dict[str, Any]:
    return {
        "manifest_schema_version": manifest.manifest_schema_version,
        "identity": _identity_to_dict(manifest.identity),
        "expected_task_ids": list(manifest.expected_task_ids),
        "staged_entries": [_staged_entry_to_dict(entry) for entry in manifest.staged_entries],
        "gate_outcome": (
            _gate_outcome_to_dict(manifest.gate_outcome) if manifest.gate_outcome else None
        ),
        "preflight_outcome": (
            _preflight_outcome_to_dict(manifest.preflight_outcome)
            if manifest.preflight_outcome
            else None
        ),
        "entry_states": {
            task_id: state.value for task_id, state in manifest.entry_states.items()
        },
        "state": manifest.state.value,
        "interrupted": manifest.interrupted,
        "generation": manifest.generation,
    }


def manifest_to_dict(manifest: H5PromotionManifest) -> dict[str, Any]:
    """Full-fidelity serialization of an :class:`H5PromotionManifest`."""
    return {**_manifest_payload(manifest), "manifest_checksum": manifest.manifest_checksum}


def manifest_from_dict(data: Mapping[str, Any]) -> H5PromotionManifest:
    """Inverse of :func:`manifest_to_dict`. Reconstructs through
    :class:`H5PromotionManifest`'s own constructor, so a tampered or
    corrupted payload is rejected the moment it is deserialized."""
    return H5PromotionManifest(
        manifest_schema_version=data["manifest_schema_version"],
        identity=_identity_from_dict(data["identity"]),
        expected_task_ids=tuple(data["expected_task_ids"]),
        staged_entries=tuple(
            _staged_entry_from_dict(entry) for entry in data["staged_entries"]
        ),
        gate_outcome=(
            _gate_outcome_from_dict(data["gate_outcome"]) if data["gate_outcome"] else None
        ),
        preflight_outcome=(
            _preflight_outcome_from_dict(data["preflight_outcome"])
            if data["preflight_outcome"]
            else None
        ),
        entry_states={
            task_id: EntryPromotionState(value)
            for task_id, value in data["entry_states"].items()
        },
        state=PromotionState(data["state"]),
        interrupted=data["interrupted"],
        generation=data["generation"],
        manifest_checksum=data["manifest_checksum"],
    )


def save_promotion_manifest(path: Path, manifest: H5PromotionManifest) -> None:
    """Durably persist ``manifest`` at ``path``: serialize, write to a
    sibling temp file, ``flush()``+``fsync()`` the temp file's own handle,
    then atomically ``os.replace`` it over ``path``. The previous
    generation (if any) is only ever replaced wholesale, never edited in
    place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(manifest_to_dict(manifest), indent=2, sort_keys=True)
    tmp_path = path.with_name(f".tmp-{uuid.uuid4().hex}-{path.name}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except OSError as exc:
        raise PromotionManifestWriteError(
            f"failed to durably write promotion manifest to {path}: {exc}"
        ) from exc


def load_promotion_manifest(path: Path) -> H5PromotionManifest | None:
    """Load the manifest at ``path``, or ``None`` if it does not exist yet.
    Raises whatever :class:`H5PromotionManifest`'s own constructor raises
    if the payload is malformed, wrong-schema, or checksum-tampered."""
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return manifest_from_dict(data)


def load_or_create_manifest(
    path: Path, identity: H5StagingIdentity, expected_task_ids: tuple[str, ...]
) -> H5PromotionManifest:
    """Load the existing manifest at ``path`` if one exists and its own
    frozen identity matches ``identity`` exactly; otherwise build and
    return a fresh :func:`build_initial_manifest` (not yet persisted -- the
    caller decides when to first :func:`save_promotion_manifest`).

    Raises :class:`PromotionManifestIdentityMismatchError` if a manifest
    already exists at ``path`` under a *different* identity -- staging from
    one run/profile/manifest identity must never resume or satisfy
    another's, regardless of directory naming.
    """
    existing = load_promotion_manifest(path)
    if existing is None:
        return build_initial_manifest(identity, expected_task_ids)
    if existing.identity != identity:
        raise PromotionManifestIdentityMismatchError(
            f"existing promotion manifest at {path} was created under a different staging "
            f"identity ({existing.identity!r}) than the one supplied now ({identity!r}) -- "
            f"refusing to resume across identities"
        )
    return existing
