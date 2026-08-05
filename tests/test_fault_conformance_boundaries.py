"""MEGB-03H.2C.3B.2B.3: dependency-direction and leakage boundary checks
for this checkpoint's own new module, ``src/distributed/fault_conformance.py``.
Extends, without modifying, ``tests/test_coordinator_boundaries.py``'s own
established AST-based approach for the B.2B.2 modules."""

# pylint: disable=duplicate-code
# This module's own no-network-import test inherently mirrors
# tests/test_coordinator_boundaries.py's own equivalent test (same check
# shape, different module list) -- shared boilerplate, not shared logic.

import ast
import dataclasses
import pathlib

from src.distributed.fault_conformance import (
    ConformanceEntry,
    FaultConformanceReport,
    ReadinessClassification,
)
from tests.test_distributed_dependency_direction import _distributed_files
from tests.test_execution_dependency_direction import _imported_module_names

_MODULE_STEM = "fault_conformance"

_FORBIDDEN_NETWORK_IMPORT_PREFIXES = (
    "socket",
    "http",
    "http.client",
    "urllib",
    "urllib3",
    "requests",
    "grpc",
    "ssl",
    "asyncio",
)


def _module_path() -> pathlib.Path:
    matches = [path for path in _distributed_files() if path.stem == _MODULE_STEM]
    assert len(matches) == 1, f"expected exactly one {_MODULE_STEM}.py, found {matches!r}"
    return matches[0]


def test_fault_conformance_module_exists_under_src_distributed() -> None:
    """Test fault_conformance.py exists under src/distributed."""
    _module_path()


def test_fault_conformance_module_imports_no_network_transport_library() -> None:
    """Test fault_conformance.py imports no network transport library."""
    imported = _imported_module_names(_module_path().read_text(encoding="utf-8"))
    offending = {
        name
        for name in imported
        if any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in _FORBIDDEN_NETWORK_IMPORT_PREFIXES
        )
    }
    assert not offending, f"fault_conformance.py imports network library {offending!r}"


def test_fault_conformance_module_imports_no_multiprocessing_docker_or_gcp_sdk() -> None:
    """Test fault_conformance.py imports no multiprocessing, subprocess,
    Docker, or GCP SDK -- this report schema is pure, in-memory, and
    provider-neutral."""
    forbidden = ("multiprocessing", "subprocess", "docker", "google", "googleapiclient")
    imported = _imported_module_names(_module_path().read_text(encoding="utf-8"))
    offending = {name for name in imported if name in forbidden}
    assert not offending, f"fault_conformance.py imports {offending!r} -- forbidden"


def test_fault_conformance_module_contains_no_wall_clock_sleep() -> None:
    """Test fault_conformance.py contains no wall-clock sleep."""
    text = _module_path().read_text(encoding="utf-8")
    assert "time.sleep" not in text


def _code_identifiers(source: str) -> set[str]:
    """Every identifier actually used in *code* -- imports, names,
    attribute accesses, function/class definitions -- at the AST level,
    deliberately excluding docstrings, comments, and string literals, so
    this module's own prose *documenting the absence* of a forbidden
    concept can never produce a false positive."""
    tree = ast.parse(source)
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            identifiers.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            identifiers.add(node.module or "")
            for alias in node.names:
                identifiers.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                identifiers.add(alias.asname or alias.name)
    return identifiers


def test_fault_conformance_module_has_no_humaneval_oracle_cache_docker_or_model_logic() -> None:
    """Test fault_conformance.py contains no GCP, Docker, HumanEval,
    oracle, cache, or model-provider logic in actual code."""
    forbidden_substrings = (
        "humaneval",
        "oracle",
        "cache",
        "docker",
        "gcloud",
        "vertex",
        "modelprovider",
    )
    identifiers = _code_identifiers(_module_path().read_text(encoding="utf-8"))
    for identifier in identifiers:
        lowered = identifier.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, (
                f"fault_conformance.py uses identifier {identifier!r} matching forbidden "
                f"substring {forbidden!r}"
            )


def test_fault_conformance_report_has_no_unsafe_field() -> None:
    """Test FaultConformanceReport/ConformanceEntry structurally exclude
    every forbidden concept -- no candidate content, raw exception text,
    participant/worker identifier, or infrastructure identifier field."""
    forbidden_substrings = (
        "candidate",
        "credential",
        "password",
        "secret",
        "hostname",
        "instance_id",
        "container_id",
        "project_id",
        "path",
        "exception",
        "stdout",
        "stderr",
        "traceback",
        "message",
        "participant",
        "worker",
    )
    field_names = {field.name for field in dataclasses.fields(FaultConformanceReport)} | {
        field.name for field in dataclasses.fields(ConformanceEntry)
    }
    for name in field_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"field {name!r} matches forbidden {forbidden!r}"


def test_readiness_classification_is_a_closed_enum_scoped_to_in_process_recovery() -> None:
    """Test ReadinessClassification has exactly the two expected values,
    and neither ever implies a durable-process, cross-host, or
    cloud-recovery claim (both names are scoped explicitly to in-process
    recovery)."""
    values = {member.value for member in ReadinessClassification}
    assert values == {"IN_PROCESS_RECOVERY_READY_FOR_B2C", "BLOCKED_IN_PROCESS_RECOVERY"}
    for value in values:
        assert "IN_PROCESS" in value
        assert "DURABLE" not in value
        assert "CROSS_HOST" not in value
        assert "CLOUD" not in value
