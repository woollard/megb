"""Isolated candidate-execution substrate (MEGB-02).

This package executes untrusted, model-generated candidate code without
exposing the host repository, credentials, evaluator implementation,
canonical solutions, or privileged test evidence. It determines nothing
about candidate correctness — see ``docs/security/execution-threat-model.md``
for the full threat model and ``src/evaluators/`` for measurement systems
that consume this substrate.
"""
