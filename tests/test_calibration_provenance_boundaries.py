"""MEGB-03H.2C.3B.3: dependency-direction and leakage boundary checks
for this checkpoint's own new modules
(``src/distributed/provenance_manifest.py``,
``src/distributed/calibration_provenance_report.py``,
``src/reference/distributed_provenance_reconciliation.py``). Extends,
without modifying, ``tests/test_distributed_dependency_direction.py``'s
and ``tests/test_offline_e2e_qualification_boundaries.py``'s own
established AST-based approach."""

# pylint: disable=duplicate-code
# This module's own no-network-import test inherently mirrors
# tests/test_offline_e2e_qualification_boundaries.py's own equivalent
# test (same check shape, different module list) -- shared boilerplate,
# not shared logic.

import ast
import dataclasses
import pathlib

from src.distributed.calibration_provenance_report import CalibrationProvenanceReport
from src.distributed.provenance_manifest import DistributedProvenanceManifest
from tests.test_distributed_dependency_direction import _distributed_files
from tests.test_execution_dependency_direction import _imported_module_names

_DISTRIBUTED_MODULE_STEMS = ("provenance_manifest", "calibration_provenance_report")

_REFERENCE_MODULE_PATH = pathlib.Path(
    "src/reference/distributed_provenance_reconciliation.py"
)

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


def _distributed_module_paths() -> list[pathlib.Path]:
    matches = [path for path in _distributed_files() if path.stem in _DISTRIBUTED_MODULE_STEMS]
    assert len(matches) == len(
        _DISTRIBUTED_MODULE_STEMS
    ), f"expected {_DISTRIBUTED_MODULE_STEMS}, found {matches!r}"
    return matches


def test_new_distributed_modules_exist_under_src_distributed() -> None:
    """Test both new src/distributed modules exist."""
    _distributed_module_paths()


def test_reconciliation_module_exists_under_src_reference() -> None:
    """Test the reconciliation bridge module exists under src/reference."""
    assert _REFERENCE_MODULE_PATH.is_file()


def test_new_distributed_modules_import_no_network_transport_library() -> None:
    """Test neither new src/distributed module imports a network
    transport library."""
    for path in _distributed_module_paths():
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


def test_new_distributed_modules_import_no_multiprocessing_docker_or_gcp_sdk() -> None:
    """Test neither new src/distributed module imports multiprocessing,
    subprocess, Docker, or a GCP SDK -- both are pure, in-memory, and
    provider-neutral."""
    forbidden = ("multiprocessing", "subprocess", "docker", "google", "googleapiclient")
    for path in _distributed_module_paths():
        imported = _imported_module_names(path.read_text(encoding="utf-8"))
        offending = {name for name in imported if name in forbidden}
        assert not offending, f"{path.name} imports {offending!r} -- forbidden"


def test_new_distributed_modules_contain_no_wall_clock_sleep() -> None:
    """Test neither new src/distributed module contains a wall-clock
    sleep."""
    for path in _distributed_module_paths():
        assert "time.sleep" not in path.read_text(encoding="utf-8")


def test_new_distributed_modules_never_import_src_reference() -> None:
    """Test neither new src/distributed module imports src.reference at
    all -- this package must remain provider-neutral and independent of
    the reference-execution schema it is designed to integrate with only
    via the dedicated reconciliation bridge module in src/reference/."""
    for path in _distributed_module_paths():
        imported = _imported_module_names(path.read_text(encoding="utf-8"))
        offending = {
            name
            for name in imported
            if name == "src.reference" or name.startswith("src.reference.")
        }
        assert not offending, f"{path.name} imports {offending!r} -- forbidden"


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


def test_new_distributed_modules_have_no_humaneval_oracle_cache_docker_or_model_logic() -> None:
    """Test neither new src/distributed module contains GCP, Docker,
    HumanEval, oracle, cache, or model-provider logic in actual code."""
    forbidden_substrings = (
        "humaneval",
        "oracle",
        "cache",
        "docker",
        "gcloud",
        "vertex",
        "modelprovider",
    )
    for path in _distributed_module_paths():
        identifiers = _code_identifiers(path.read_text(encoding="utf-8"))
        for identifier in identifiers:
            lowered = identifier.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in lowered, (
                    f"{path.name} uses identifier {identifier!r} matching forbidden "
                    f"substring {forbidden!r}"
                )


def test_calibration_provenance_report_has_no_unsafe_field() -> None:
    """Test CalibrationProvenanceReport structurally excludes every
    forbidden concept -- no candidate content, raw exception text,
    protected identifier, generation command, or code revision (both
    exist only on the protected DistributedProvenanceManifest, never on
    this safe report)."""
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
        "zone",
        "generation_command",
        "code_revision",
    )
    field_names = {field.name for field in dataclasses.fields(CalibrationProvenanceReport)}
    for name in field_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"field {name!r} matches forbidden {forbidden!r}"


def test_distributed_provenance_manifest_has_no_raw_operational_identifier_field() -> None:
    """Test DistributedProvenanceManifest structurally excludes every raw
    operational-identifier concept the authorization names -- project
    IDs, instance IDs, hostnames, paths, service accounts, credentials,
    and infrastructure resource names. (generation_command/code_revision
    are deliberately present here -- this is the *protected*, not safe,
    manifest type -- but must never look like a raw infrastructure
    identifier field themselves.)"""
    forbidden_substrings = (
        "raw_project_id",
        "raw_instance_id",
        "raw_hostname",
        "raw_container_id",
        "raw_filesystem_path",
        "raw_service_account",
        "raw_credential",
        "raw_resource_name",
        "credential",
        "password",
        "secret_value",
    )
    field_names = {field.name for field in dataclasses.fields(DistributedProvenanceManifest)}
    for name in field_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"field {name!r} matches forbidden {forbidden!r}"
