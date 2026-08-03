"""MEGB-03H.2B.2 recovery/path-safety correction: proves the H.5 staging
directory is never derived from the raw, operator-supplied
``calibration_run_id`` -- only from :meth:`H5StagingIdentity.identity_checksum`,
a 64-character lowercase hex digest that can never contain a path
separator, a traversal component, an absolute-path prefix, or a control
character. Synthetic fixtures only, via tests/_h5_fixtures.py -- no real
privileged corpus access, no Docker.
"""

# See _h5_fixtures.py's own note: shared fixtures across the H.2B.2 test
# modules.
# pylint: disable=duplicate-code

from pathlib import Path

import pytest

from src.reference.cache_key import cache_key_for
from src.reference.h5_promotion_manifest import build_initial_manifest, save_promotion_manifest
from src.reference.h5_staging import build_staging_cache, manifest_path_for
from src.reference.reference_cache import CacheDisposition
from tests import _h5_fixtures as fx

_MALICIOUS_RUN_IDS = (
    "../escape",
    "../../../../etc/passwd",
    "/etc/passwd",
    "/absolute/path",
    "a/b/c",
    ".",
    "..",
    "run\x00id",
    "run\nid\r\x1b",
)


@pytest.mark.parametrize("malicious_run_id", _MALICIOUS_RUN_IDS)
def test_staging_dir_stays_contained_despite_a_malicious_run_id(
    tmp_path: Path, malicious_run_id: str
) -> None:
    """No matter what a malicious calibration_run_id contains, staging_dir()
    is always a direct child of the configured root."""
    manifest = fx.candidate_set_manifest()
    identity = fx.staging_identity(manifest, calibration_run_id=malicious_run_id)
    staging_dir = identity.staging_dir(root=tmp_path)
    assert staging_dir.is_relative_to(tmp_path)
    assert staging_dir.parent == tmp_path
    # The checksum-named directory never literally contains the raw run id.
    assert malicious_run_id not in staging_dir.name


@pytest.mark.parametrize("malicious_run_id", _MALICIOUS_RUN_IDS)
def test_staging_cache_and_manifest_path_stay_contained(
    tmp_path: Path, malicious_run_id: str
) -> None:
    """build_staging_cache()'s cache_dir and manifest_path_for()'s path are
    both real descendants of root, regardless of calibration_run_id."""
    manifest = fx.candidate_set_manifest()
    identity = fx.staging_identity(manifest, calibration_run_id=malicious_run_id)

    cache = build_staging_cache(identity, root=tmp_path)
    assert Path(cache.cache_dir).is_relative_to(tmp_path)

    path = manifest_path_for(identity, root=tmp_path)
    assert path.is_relative_to(tmp_path)
    assert path.parent == identity.staging_dir(root=tmp_path)


@pytest.mark.parametrize("malicious_run_id", _MALICIOUS_RUN_IDS)
def test_writes_under_a_malicious_run_id_never_escape_the_root(
    tmp_path: Path, malicious_run_id: str
) -> None:
    """Actually writing a staged result and a promotion manifest under a
    malicious calibration_run_id creates every file strictly inside root --
    proven by walking the real filesystem, not merely inspecting a Path."""
    context = fx.full_run_context()
    results = fx.valid_task_results(context, count=3)
    manifest = fx.candidate_set_manifest()
    identity = fx.staging_identity(manifest, calibration_run_id=malicious_run_id)

    root = tmp_path / "configured_root"
    cache = build_staging_cache(identity, root=root)
    for result in results:
        cache.put(result)

    manifest_path = manifest_path_for(identity, root=root)
    expected_task_ids = tuple(sorted(result.task_id for result in results))
    save_promotion_manifest(manifest_path, build_initial_manifest(identity, expected_task_ids))

    written_paths = [p for p in root.rglob("*") if p.is_file()]
    assert written_paths, "expected at least one file to have been written"
    for written_path in written_paths:
        assert written_path.resolve().is_relative_to(root.resolve())


def test_two_identities_sharing_a_display_run_id_do_not_collide(tmp_path: Path) -> None:
    """Two identities that share the same human-readable calibration_run_id
    but differ in another field get distinct staging directories -- the
    display run id alone never determines the storage location."""
    manifest = fx.candidate_set_manifest()
    shared_run_id = "shared-display-name"
    identity_a = fx.staging_identity(manifest, calibration_run_id=shared_run_id)
    identity_b = fx.staging_identity(
        manifest, calibration_run_id=shared_run_id, execution_profile_id="a-different-profile"
    )

    assert identity_a.calibration_run_id == identity_b.calibration_run_id
    assert identity_a.identity_checksum() != identity_b.identity_checksum()

    dir_a = identity_a.staging_dir(root=tmp_path)
    dir_b = identity_b.staging_dir(root=tmp_path)
    assert dir_a != dir_b

    results = fx.valid_task_results(fx.full_run_context(), count=1)
    cache_a = build_staging_cache(identity_a, root=tmp_path)
    cache_a.put(results[0])

    # identity_b's own (separate) cache never sees identity_a's write.
    cache_b = build_staging_cache(identity_b, root=tmp_path)
    assert cache_b.get(cache_key_for(results[0])).disposition == CacheDisposition.MISS
    assert cache_a.get(cache_key_for(results[0])).disposition == CacheDisposition.VALID_HIT


def test_identity_checksum_is_stable_for_identical_fields() -> None:
    """identity_checksum() is a pure function of the identity's own field
    values -- two independently constructed, value-identical identities
    checksum the same."""
    manifest = fx.candidate_set_manifest()
    identity_1 = fx.staging_identity(manifest)
    identity_2 = fx.staging_identity(manifest)
    assert identity_1 == identity_2
    assert identity_1.identity_checksum() == identity_2.identity_checksum()


def test_identity_checksum_is_a_64_char_hex_digest() -> None:
    """identity_checksum() always returns a 64-character lowercase hex
    digest -- structurally incapable of carrying a path separator,
    traversal component, absolute-path prefix, or control character."""
    manifest = fx.candidate_set_manifest()
    identity = fx.staging_identity(manifest, calibration_run_id="../../escape\x00")
    checksum = identity.identity_checksum()
    assert len(checksum) == 64
    assert all(c in "0123456789abcdef" for c in checksum)
