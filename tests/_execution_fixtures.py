"""Candidate-code snippets shared between offline and Docker-backed execution tests.

Some adversarial scenarios are deliberately verified at two levels: once
in-process via ``run_invocation`` (fast, no Docker) and once end-to-end
through the real container and controller. Sharing the snippet keeps both
levels testing the exact same input instead of two copies drifting apart.
"""

DUP2_HIJACK_FD1_CANDIDATE_CODE = (
    "import os\n"
    "def f():\n"
    "    fd = os.open('/tmp', os.O_RDONLY)\n"
    "    try:\n"
    "        os.dup2(fd, 1)\n"
    "    finally:\n"
    "        os.close(fd)\n"
    "    return 3\n"
)
