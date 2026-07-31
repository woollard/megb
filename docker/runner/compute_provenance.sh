#!/usr/bin/env bash
# Computes the reproducibility provenance for the MEGB-02 runner image:
# pinned base-image digest, Dockerfile hash, build-context hash, and the
# resulting local image ID. Run from the repository root:
#
#   ./docker/runner/compute_provenance.sh
#
# This exists so these values are always independently recomputable rather
# than relying solely on figures copied into documentation, which can go
# stale. Rerun after any change to the Dockerfile or to src/execution/.
#
# Hashing is delegated to Python (not sha256sum/shasum) so the
# build-context hash is identical across hosts: GNU coreutils and BSD/macOS
# checksum tools format their output differently, which would otherwise
# make a hash-of-hashes computed via shell pipes non-portable.
#
# The build itself passes --provenance=false --sbom=false: BuildKit embeds
# a build-timestamped provenance/SBOM attestation by default, which makes
# the resulting image ID different on every rebuild even with byte-identical
# Dockerfile and build context. Disabling both makes the local image ID a
# pure function of content again (verified: two consecutive builds from an
# unchanged tree produce the same image ID with these flags, and different
# IDs without them).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

DOCKERFILE="docker/runner/Dockerfile"
IMAGE_TAG="megb-runner:local"

echo "== Base image digest (from Dockerfile FROM line) =="
BASE_IMAGE_LINE="$(grep -m1 '^FROM' "$DOCKERFILE")"
echo "$BASE_IMAGE_LINE"

echo
echo "== Dockerfile SHA-256 =="
DOCKERFILE_HASH="$(python3 -c "
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())
" "$DOCKERFILE")"
echo "$DOCKERFILE_HASH"

echo
echo "== Build-context SHA-256 (src/__init__.py + src/execution/*, sorted, content-hashed) =="
BUILD_CONTEXT_HASH="$(python3 -c "
import hashlib
from pathlib import Path

paths = sorted(
    p for p in (list(Path('src/execution').rglob('*')) + [Path('src/__init__.py')])
    if p.is_file()
)
digest = hashlib.sha256()
for path in paths:
    digest.update(str(path.as_posix()).encode('utf-8'))
    digest.update(b'\\0')
    digest.update(path.read_bytes())
print(digest.hexdigest())
")"
echo "$BUILD_CONTEXT_HASH"

echo
echo "== Building $IMAGE_TAG =="
docker build --provenance=false --sbom=false -f "$DOCKERFILE" -t "$IMAGE_TAG" . >/dev/null

echo
echo "== Resulting local image ID =="
IMAGE_ID="$(docker inspect --format='{{.Id}}' "$IMAGE_TAG")"
echo "$IMAGE_ID"

echo
echo "== Summary (copy into docs/ADRs if recording a snapshot) =="
echo "base_image_digest:    ${BASE_IMAGE_LINE#FROM }"
echo "dockerfile_sha256:    $DOCKERFILE_HASH"
echo "build_context_sha256: $BUILD_CONTEXT_HASH"
echo "local_image_id:       $IMAGE_ID"
