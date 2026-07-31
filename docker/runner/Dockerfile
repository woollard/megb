# Minimal, non-root runner image for untrusted MEGB candidate code (MEGB-02).
#
# Build context must be the repository root:
#   docker build -f docker/runner/Dockerfile -t megb-runner:<tag> .
#
# Base image pinned by digest for reproducibility. See
# docs/security/execution-sandbox.md for the update/re-pin procedure.
FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

# Runtime network/filesystem/privilege isolation (no network, read-only
# rootfs, dropped capabilities, no-new-privileges, resource limits) is
# enforced by the trusted controller at `docker run` time
# (src/execution/docker_backend.py), not by this image. This image only
# needs to: not run as root, and carry nothing beyond the runner harness
# itself.
RUN useradd --no-create-home --uid 65532 --shell /usr/sbin/nologin megb-runner

WORKDIR /app
COPY src/__init__.py src/__init__.py
COPY src/execution/ src/execution/

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 65532:65532

ENTRYPOINT ["python", "-m", "src.execution.runner"]
