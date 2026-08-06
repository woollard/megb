"""MEGB-03H.2C.3B.3 lock-integrity correction: offline unit tests for
``src/distributed/provenance_manifest_lock.py``'s own self-checksum,
path-containment, and closed-allowlist invariants -- the security
properties added by this correction, independent of the calibration-
provenance report or CLI that consume this module.

Synthetic only -- no candidate code, HumanEval cases, oracle values,
Docker, or cloud resources anywhere in this file.
"""

import json
import os
import pathlib

import pytest

from src.distributed import provenance_manifest_lock as pml
from src.distributed.provenance_manifest import (
    build_distributed_provenance_manifest,
    distributed_provenance_manifest_to_dict,
)
from tests._distributed_fixtures import make_run_context, make_two_region_workers


def _write_manifest(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, *, run_id: str = "lock-unit-test-run"
) -> pml.ManifestLockEntry:
    """Build a real, valid protected manifest + lock entry rooted under
    tmp_path (via ``monkeypatch.chdir``, since ``write_protected_manifest``
    always derives its write location from the fixed, repository-relative
    ``artifacts/privileged/...`` path -- never an arbitrary caller-
    supplied one)."""
    monkeypatch.chdir(tmp_path)
    run_context = make_run_context(distributed_run_id=run_id)
    worker_a, worker_b = make_two_region_workers(run_context)
    manifest = build_distributed_provenance_manifest(
        run_context, (worker_a, worker_b), generation_command="pytest", code_revision="a" * 40
    )
    return pml.write_protected_manifest(
        manifest,
        generation_command="pytest",
        generating_code_revision="a" * 40,
        generating_code_dirty=False,
        authorized_consumers=(pml.AuthorizedManifestConsumer.MEGB_03H_2C_3B_3.value,),
    )


def _mutated(entry: pml.ManifestLockEntry, **overrides: object) -> dict[str, object]:
    """A plain-dict copy of entry's fields with overrides applied and
    lock_checksum cleared, ready to pass to ManifestLockEntry(**fields)
    -- exercising direct (re)construction the way load_lock_file() does."""
    fields = dict(pml.manifest_lock_entry_to_dict(entry))
    fields["lock_checksum"] = ""
    fields.update(overrides)
    return fields


# --- self-checksum -----------------------------------------------------


def test_write_protected_manifest_produces_self_checksummed_entry(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The entry write_protected_manifest() returns always carries a
    valid 64-character lock_checksum, auto-computed over every other
    field."""
    entry = _write_manifest(tmp_path, monkeypatch)
    assert len(entry.lock_checksum) == 64
    assert set(entry.lock_checksum) <= set("0123456789abcdef")


def test_lock_checksum_round_trips_through_write_and_load(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """write_lock_file()/load_lock_file() preserve lock_checksum exactly."""
    entry = _write_manifest(tmp_path, monkeypatch)
    lock_path = tmp_path / "lock.json"
    pml.write_lock_file(entry, lock_path)
    reloaded = pml.load_lock_file(lock_path)
    assert reloaded.entries[0].lock_checksum == entry.lock_checksum
    assert reloaded.entries[0] == entry


def test_load_lock_file_rejects_tampered_lock_checksum(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lock file whose lock_checksum no longer matches its own
    recomputed contents is rejected at load time -- a tampered lock
    fails before any consumer ever sees its fields."""
    entry = _write_manifest(tmp_path, monkeypatch)
    lock_path = tmp_path / "lock.json"
    pml.write_lock_file(entry, lock_path)
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    data["entries"][0]["lock_checksum"] = "0" * 64
    lock_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(pml.InvalidManifestLockEntryError):
        pml.load_lock_file(lock_path)


@pytest.mark.parametrize(
    "field_name,new_value",
    [
        ("artifact_id", "calibration_provenance_manifest"),  # re-set; changes nothing structurally
        ("schema_version", "megb-fake-schema-v9"),
        ("checksum_algorithm_version", "sha256-canonical-json-v9"),
        ("manifest_checksum", "9" * 64),
        ("distributed_run_context_checksum", "8" * 64),
        ("expected_worker_count", 99),
        ("safe_topology_summary_checksum", "7" * 64),
        ("size_bytes", 999999),
        ("generation_command", "some other command"),
        ("generating_code_revision", "f" * 40),
        ("generating_code_dirty", True),
        ("authorized_consumers", (pml.AuthorizedManifestConsumer.MEGB_03H_2C_3B_3.value,)),
    ],
)
def test_mutating_any_security_relevant_field_changes_lock_checksum(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    new_value: object,
) -> None:
    """Every security-relevant lock field (the authorization's own named
    list) participates in lock_checksum: mutating it to a different
    value -- and re-deriving lock_checksum fresh -- produces a different
    checksum than the original, proving the field is actually covered.
    (Re-deriving with the *same* value, as the artifact_id/dirty/
    consumers cases above may do, is the negative control: an unrelated
    field being present must not itself perturb the checksum.)"""
    entry = _write_manifest(tmp_path, monkeypatch)
    fields = _mutated(entry, **{field_name: new_value})
    fields["authorized_consumers"] = tuple(fields["authorized_consumers"])  # type: ignore[arg-type]
    rebuilt = pml.ManifestLockEntry(**fields)  # type: ignore[arg-type]
    if getattr(entry, field_name) == new_value:
        assert rebuilt.lock_checksum == entry.lock_checksum
    else:
        assert rebuilt.lock_checksum != entry.lock_checksum


# --- stale lock schema version -----------------------------------------


def test_load_lock_file_rejects_stale_v1_lock_schema(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lock file stamped with the superseded v1 lock_schema_version --
    which predates the lock_checksum self-check this correction adds --
    is rejected outright, never silently accepted as current."""
    entry = _write_manifest(tmp_path, monkeypatch)
    lock_path = tmp_path / "lock.json"
    pml.write_lock_file(entry, lock_path)
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    data["lock_schema_version"] = "megb-03h2c3b3-distributed-provenance-manifest-lock-v1"
    lock_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(pml.UnsupportedManifestLockSchemaVersionError):
        pml.load_lock_file(lock_path)


def test_manifest_lock_file_direct_construction_rejects_stale_schema() -> None:
    """Direct ManifestLockFile construction (not just load_lock_file())
    validates lock_schema_version -- the invariant holds on every
    construction path, not merely the loader's own."""
    with pytest.raises(pml.UnsupportedManifestLockSchemaVersionError):
        pml.ManifestLockFile(lock_schema_version="stale-version", entries=())


# --- protected_path: absolute / traversal / unexpected shape -----------


def test_manifest_lock_entry_rejects_absolute_protected_path(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A protected_path substituted with an absolute filesystem path
    (e.g. attempting to point at an arbitrary host file) is rejected at
    construction, never trusted as arbitrary input."""
    entry = _write_manifest(tmp_path, monkeypatch)
    fields = _mutated(entry, protected_path="/etc/passwd")
    with pytest.raises(pml.InvalidManifestLockEntryError):
        pml.ManifestLockEntry(**fields)  # type: ignore[arg-type]


def test_manifest_lock_entry_rejects_dotdot_traversal(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A protected_path containing '..' traversal components is
    rejected at construction."""
    entry = _write_manifest(tmp_path, monkeypatch)
    fields = _mutated(
        entry,
        protected_path="artifacts/privileged/distributed_provenance/../../../etc/passwd",
    )
    with pytest.raises(pml.InvalidManifestLockEntryError):
        pml.ManifestLockEntry(**fields)  # type: ignore[arg-type]


def test_manifest_lock_entry_rejects_unexpected_filename_same_artifact_id(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A protected_path pointing at an unexpected filename under the
    otherwise-correct directory -- same artifact_id, wrong leaf -- is
    rejected: protected_path must equal the canonical path exactly."""
    entry = _write_manifest(tmp_path, monkeypatch)
    fields = _mutated(
        entry,
        protected_path="artifacts/privileged/distributed_provenance/some_other_file.json",
    )
    with pytest.raises(pml.InvalidManifestLockEntryError):
        pml.ManifestLockEntry(**fields)  # type: ignore[arg-type]


def test_manifest_lock_entry_rejects_unknown_artifact_id(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An artifact_id outside the closed set of known protected-manifest
    artifact kinds is rejected -- distinctly typed from a merely
    malformed protected_path."""
    entry = _write_manifest(tmp_path, monkeypatch)
    fields = _mutated(entry, artifact_id="something_else")
    with pytest.raises(pml.UnknownManifestArtifactError):
        pml.ManifestLockEntry(**fields)  # type: ignore[arg-type]


def test_manifest_lock_entry_rejects_control_character_in_path(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A protected_path containing a NUL/control character is rejected
    before the canonical-equality check even runs."""
    entry = _write_manifest(tmp_path, monkeypatch)
    fields = _mutated(
        entry,
        protected_path="artifacts/privileged/distributed_provenance/calib\x00ration.json",
    )
    with pytest.raises(pml.InvalidManifestLockEntryError):
        pml.ManifestLockEntry(**fields)  # type: ignore[arg-type]


# --- authorized_consumers: closed allowlist -----------------------------


def test_manifest_lock_entry_rejects_unauthorized_consumer(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """authorized_consumers is a closed, validated allowlist -- an
    entry naming any other value is rejected. Lock tampering can never
    expand access by simply adding a new consumer string."""
    entry = _write_manifest(tmp_path, monkeypatch)
    fields = _mutated(entry, authorized_consumers=("SOME-OTHER-CONSUMER",))
    with pytest.raises(pml.InvalidManifestLockEntryError):
        pml.ManifestLockEntry(**fields)  # type: ignore[arg-type]


def test_manifest_lock_entry_rejects_duplicate_authorized_consumer(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A duplicated (even if individually valid) authorized_consumers
    entry is rejected."""
    entry = _write_manifest(tmp_path, monkeypatch)
    consumer = pml.AuthorizedManifestConsumer.MEGB_03H_2C_3B_3.value
    fields = _mutated(entry, authorized_consumers=(consumer, consumer))
    with pytest.raises(pml.InvalidManifestLockEntryError):
        pml.ManifestLockEntry(**fields)  # type: ignore[arg-type]


# --- path containment at read time (symlink escape) ---------------------


def test_verify_against_lock_rejects_symlink_escape_without_disclosing_target(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A protected_path that is syntactically the canonical string but
    resolves (via a symlink) outside the authorized privileged subtree
    fails containment validation -- raised before any byte of the
    escaped target is read, and the raised error never discloses the
    resolved target path or its contents."""
    entry = _write_manifest(tmp_path, monkeypatch)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret = outside_dir / "secret.json"
    secret.write_text(json.dumps({"leaked": True}), encoding="utf-8")

    protected_path = pathlib.Path(entry.protected_path)
    protected_path.unlink()
    os.symlink(secret.resolve(), protected_path)

    lock = pml.ManifestLockFile(
        lock_schema_version=pml.MANIFEST_LOCK_SCHEMA_VERSION, entries=(entry,)
    )
    with pytest.raises(pml.ManifestPathContainmentError) as exc_info:
        pml.verify_against_lock(lock)
    assert "secret" not in str(exc_info.value)
    assert "leaked" not in str(exc_info.value)
    assert str(outside_dir) not in str(exc_info.value)


# --- verify_against_lock: missing / substituted / size disagreement -----


def test_verify_against_lock_reports_missing_artifact_without_raising(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing protected artifact is reported as on_disk_present=False
    / passed=False, never a raised exception -- the required "missing
    artifact fails verification, caller regenerates then re-verifies"
    CLI behavior."""
    entry = _write_manifest(tmp_path, monkeypatch)
    pathlib.Path(entry.protected_path).unlink()
    lock = pml.ManifestLockFile(
        lock_schema_version=pml.MANIFEST_LOCK_SCHEMA_VERSION, entries=(entry,)
    )
    results = pml.verify_against_lock(lock)
    assert not results[0].on_disk_present
    assert not results[0].passed


def test_verify_against_lock_detects_size_disagreement(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protected-manifest bytes whose on-disk size no longer matches the
    lock's own recorded size_bytes fail verification via size_match,
    even if every other field still happens to parse and match."""
    entry = _write_manifest(tmp_path, monkeypatch)
    protected_path = pathlib.Path(entry.protected_path)
    with open(protected_path, "a", encoding="utf-8") as handle:
        handle.write(" ")
    lock = pml.ManifestLockFile(
        lock_schema_version=pml.MANIFEST_LOCK_SCHEMA_VERSION, entries=(entry,)
    )
    results = pml.verify_against_lock(lock)
    assert results[0].size_match is False
    assert not results[0].passed


def test_verify_against_lock_detects_substituted_wrong_run_manifest(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A protected-manifest file substituted with a different,
    internally-self-consistent manifest from an unrelated distributed
    run fails verification even though the substituted bytes are not
    themselves corrupt."""
    entry = _write_manifest(tmp_path, monkeypatch, run_id="lock-unit-test-run")
    other_run = make_run_context(distributed_run_id="lock-unit-test-other-run")
    other_a, other_b = make_two_region_workers(other_run)
    other_manifest = build_distributed_provenance_manifest(
        other_run, (other_a, other_b), generation_command="pytest", code_revision="b" * 40
    )
    protected_path = pathlib.Path(entry.protected_path)
    protected_path.write_text(
        json.dumps(
            distributed_provenance_manifest_to_dict(other_manifest), indent=2, sort_keys=True
        ),
        encoding="utf-8",
    )
    lock = pml.ManifestLockFile(
        lock_schema_version=pml.MANIFEST_LOCK_SCHEMA_VERSION, entries=(entry,)
    )
    results = pml.verify_against_lock(lock)
    assert not results[0].passed
