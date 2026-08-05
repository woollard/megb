"""MEGB-03H.2C.3B.2C: dependency-direction and leakage boundary checks
for this checkpoint's own new modules
(``src/distributed/offline_e2e_qualification_report.py``,
``src/distributed/candidate_manifest.py``). Extends, without modifying,
``tests/test_coordinator_boundaries.py``'s and
``tests/test_fault_conformance_boundaries.py``'s own established
AST-based approach."""

# pylint: disable=duplicate-code
# This module's own no-network-import test inherently mirrors
# tests/test_fault_conformance_boundaries.py's own equivalent test (same
# check shape, different module list) -- shared boilerplate, not shared
# logic.

import ast
import dataclasses
import pathlib

from src.distributed.candidate_manifest import CandidateManifest
from src.distributed.offline_e2e_qualification_report import (
    OfflineE2EQualificationReport,
    ReadinessClassification,
)
from tests.test_distributed_dependency_direction import _distributed_files
from tests.test_execution_dependency_direction import _imported_module_names

_MODULE_STEMS = ("offline_e2e_qualification_report", "candidate_manifest")

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


def _module_paths() -> list[pathlib.Path]:
    matches = [path for path in _distributed_files() if path.stem in _MODULE_STEMS]
    assert len(matches) == len(_MODULE_STEMS), f"expected {_MODULE_STEMS}, found {matches!r}"
    return matches


def test_offline_e2e_modules_exist_under_src_distributed() -> None:
    """Test both new modules exist under src/distributed."""
    _module_paths()


def test_offline_e2e_modules_import_no_network_transport_library() -> None:
    """Test neither new module imports a network transport library."""
    for path in _module_paths():
        imported = _imported_module_names(path.read_text(encoding="utf-8"))
        offending = {
            name
            for name in imported
            if any(
                name == prefix or name.startswith(prefix + ".")
                for prefix in _FORBIDDEN_NETWORK_IMPORT_PREFIXES
            )
        }
        assert not offending, f"{path.name} imports network library {offending!r}"


def test_offline_e2e_modules_import_no_multiprocessing_docker_or_gcp_sdk() -> None:
    """Test neither new module imports multiprocessing, subprocess,
    Docker, or a GCP SDK -- both are pure, in-memory, and
    provider-neutral."""
    forbidden = ("multiprocessing", "subprocess", "docker", "google", "googleapiclient")
    for path in _module_paths():
        imported = _imported_module_names(path.read_text(encoding="utf-8"))
        offending = {name for name in imported if name in forbidden}
        assert not offending, f"{path.name} imports {offending!r} -- forbidden"


def test_offline_e2e_modules_contain_no_wall_clock_sleep() -> None:
    """Test neither new module contains a wall-clock sleep."""
    for path in _module_paths():
        assert "time.sleep" not in path.read_text(encoding="utf-8")


def _code_identifiers(source: str) -> set[str]:
    """Every identifier actually used in *code* -- imports, names,
    attribute accesses, function/class definitions -- at the AST level,
    deliberately excluding docstrings, comments, and string literals, so
    prose *documenting the absence* of a forbidden concept can never
    produce a false positive."""
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


def test_offline_e2e_modules_have_no_humaneval_oracle_cache_docker_or_model_logic() -> None:
    """Test neither new module contains GCP, Docker, HumanEval, oracle,
    cache, or model-provider logic in actual code."""
    forbidden_substrings = (
        "humaneval",
        "oracle",
        "cache",
        "docker",
        "gcloud",
        "vertex",
        "modelprovider",
    )
    for path in _module_paths():
        identifiers = _code_identifiers(path.read_text(encoding="utf-8"))
        for identifier in identifiers:
            lowered = identifier.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in lowered, (
                    f"{path.name} uses identifier {identifier!r} matching forbidden "
                    f"substring {forbidden!r}"
                )


def test_offline_e2e_qualification_report_has_no_unsafe_field() -> None:
    """Test OfflineE2EQualificationReport structurally excludes every
    forbidden concept -- no candidate content, raw exception text,
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
        "worker_id",
        "prompt",
        "source",
    )
    field_names = {field.name for field in dataclasses.fields(OfflineE2EQualificationReport)}
    for name in field_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"field {name!r} matches forbidden {forbidden!r}"


def test_candidate_manifest_has_no_unsafe_field() -> None:
    """Test CandidateManifest structurally excludes every forbidden
    concept."""
    forbidden_substrings = ("candidate_content", "raw_content", "credential", "secret")
    field_names = {field.name for field in dataclasses.fields(CandidateManifest)}
    for name in field_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"field {name!r} matches forbidden {forbidden!r}"


def test_readiness_classification_is_a_closed_enum_scoped_to_offline_distributed_path() -> None:
    """Test ReadinessClassification has exactly the two expected values,
    and neither ever implies H.2C.3D readiness, GCP readiness, durable-
    process recovery, cross-host recovery, or Docker/native-Linux
    equivalence."""
    values = {member.value for member in ReadinessClassification}
    assert values == {
        "OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3",
        "BLOCKED_OFFLINE_DISTRIBUTED_PATH",
    }
    for value in values:
        assert "OFFLINE" in value
        for forbidden in ("H2C3D", "GCP", "DURABLE", "CROSS_HOST", "DOCKER"):
            assert forbidden not in value
