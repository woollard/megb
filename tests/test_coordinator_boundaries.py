"""MEGB-03H.2C.3B.2B.2: dependency-direction, protocol-dependency, and
leakage boundary checks for the coordinator/worker engine's own eight new
modules. Extends, without modifying, the existing generic
``tests/test_distributed_dependency_direction.py`` no-network/no-
``src.reference``/no-GCP-Docker-SDK/no-``gcloud``/``docker``-subprocess
scan, and B.2B.1's own equivalent extension pattern in
``tests/test_atomic_stores_boundaries.py``."""

# pylint: disable=duplicate-code
# This module's own no-network-import test inherently mirrors
# tests/test_atomic_stores_boundaries.py's own equivalent test (same
# check shape, different module list) -- shared boilerplate, not shared
# logic.

import ast
import dataclasses
import inspect

from src.distributed import (
    artifact_capabilities,
    audit_outbox,
    cancellation,
    coordinator,
    coordinator_config,
    executor,
    queue_adapter,
    work_outcome,
)
from src.distributed.executor import ExecutorFailureReason
from src.distributed.work_outcome import WorkOutcome
from tests.test_distributed_dependency_direction import _distributed_files
from tests.test_execution_dependency_direction import _imported_module_names

_B2B2_MODULES = (
    "coordinator",
    "coordinator_config",
    "executor",
    "work_outcome",
    "artifact_capabilities",
    "queue_adapter",
    "audit_outbox",
    "cancellation",
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


def test_all_eight_b2b2_modules_exist_under_src_distributed() -> None:
    """Test all eight B.2B.2 modules exist under src/distributed."""
    paths = [path for path in _distributed_files() if path.stem in _B2B2_MODULES]
    assert len(paths) == len(_B2B2_MODULES), (
        f"expected to find all of {_B2B2_MODULES!r} under src/distributed/, found "
        f"{[path.stem for path in paths]!r}"
    )


def test_no_b2b2_module_imports_a_network_transport_library() -> None:
    """Test no B.2B.2 module imports a network transport library."""
    for path in _distributed_files():
        if path.stem not in _B2B2_MODULES:
            continue
        imported = _imported_module_names(path.read_text(encoding="utf-8"))
        offending = {
            name
            for name in imported
            if any(
                name == prefix or name.startswith(prefix + ".")
                for prefix in _FORBIDDEN_NETWORK_IMPORT_PREFIXES
            )
        }
        assert not offending, f"{path.name} imports network library {offending!r} -- forbidden"


def test_no_b2b2_module_imports_multiprocessing_docker_or_gcp_sdk() -> None:
    """Test no B.2B.2 module imports multiprocessing, subprocess,
    Docker, or a GCP SDK -- this engine is provider-neutral and
    in-memory only."""
    forbidden = ("multiprocessing", "subprocess", "docker", "google", "googleapiclient")
    for path in _distributed_files():
        if path.stem not in _B2B2_MODULES:
            continue
        imported = _imported_module_names(path.read_text(encoding="utf-8"))
        offending = {name for name in imported if name in forbidden}
        assert not offending, f"{path.name} imports {offending!r} -- forbidden"


def test_no_b2b2_module_contains_wall_clock_sleep() -> None:
    """Test no B.2B.2 module contains a wall-clock sleep -- every
    timing concept in this engine is the injected logical clock."""
    for path in _distributed_files():
        if path.stem not in _B2B2_MODULES:
            continue
        text = path.read_text(encoding="utf-8")
        assert "time.sleep" not in text, f"{path.name} contains a wall-clock time.sleep"


def _imported_identifier_names(source: str) -> set[str]:
    """Every name actually imported (not merely mentioned in a docstring
    or comment) -- the ``ImportFrom``/``Import`` alias names themselves,
    at the AST level."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _call_names(source: str) -> set[str]:
    """Every bare-name call target in ``source`` at the AST level (e.g.
    ``Foo()`` contributes ``"Foo"``) -- used to prove a class is never
    *instantiated*, independent of whether its name appears in prose."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


def test_coordinator_module_never_imports_the_deprecated_split_protocols() -> None:
    """Test the coordinator module never imports
    LeaseStateStoreProtocol/ResultStoreProtocol -- the deprecated split
    protocols are absent from the authoritative execution path entirely,
    not merely unused. Checked at the AST import-alias level, so this
    module's own docstring prose (which discusses their absence by name)
    cannot produce a false positive."""
    text = (
        [path for path in _distributed_files() if path.stem == "coordinator"][0]
    ).read_text(encoding="utf-8")
    imported = _imported_identifier_names(text)
    assert "LeaseStateStoreProtocol" not in imported
    assert "ResultStoreProtocol" not in imported


def test_coordinator_never_instantiates_the_concrete_atomic_work_store() -> None:
    """Test the coordinator module never instantiates the concrete
    ``AtomicWorkStore`` class -- it depends on ``AtomicWorkStoreProtocol``
    alone for authoritative state, injected by its caller. Checked at the
    AST call level."""
    text = (
        [path for path in _distributed_files() if path.stem == "coordinator"][0]
    ).read_text(encoding="utf-8")
    assert "AtomicWorkStore" not in _call_names(text)


def _code_identifiers(source: str) -> set[str]:
    """Every identifier actually used in *code* -- imports, names,
    attribute accesses, function/class definitions -- at the AST level,
    deliberately excluding docstrings, comments, and string literals, so
    a module's own prose *documenting the absence* of a forbidden concept
    can never produce a false positive."""
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


def test_b2b2_modules_have_no_humaneval_oracle_cache_docker_or_model_logic() -> None:
    """Test none of the eight new modules contain GCP, Docker, HumanEval,
    oracle, cache, or model-provider logic in actual code (imports,
    identifiers, definitions) -- module docstrings are free to discuss
    these concepts by name when documenting their deliberate absence."""
    forbidden_substrings = (
        "humaneval",
        "oracle",
        "cache",
        "docker",
        "gcloud",
        "vertex",
        "modelprovider",
    )
    for path in _distributed_files():
        if path.stem not in _B2B2_MODULES:
            continue
        identifiers = _code_identifiers(path.read_text(encoding="utf-8"))
        for identifier in identifiers:
            lowered = identifier.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in lowered, (
                    f"{path.name} uses identifier {identifier!r} matching forbidden "
                    f"substring {forbidden!r}"
                )


def test_b2b2_modules_define_no_coordinator_alternate_or_worker_loop_class() -> None:
    """Test the new modules define exactly the expected engine classes --
    no second, alternate coordinator/scheduler/executor-loop class."""
    forbidden_substrings = ("scheduler", "workerloop")
    for module in (
        coordinator,
        coordinator_config,
        executor,
        work_outcome,
        artifact_capabilities,
        queue_adapter,
        audit_outbox,
        cancellation,
    ):
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue
            lowered = name.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in lowered, (
                    f"{module.__name__}.{name} matches forbidden {forbidden!r}"
                )


def test_work_outcome_has_no_raw_identifier_or_content_field() -> None:
    """Test WorkOutcome structurally excludes every forbidden concept --
    no candidate content, raw exception text, or infrastructure
    identifier field."""
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
    )
    field_names = {field.name for field in dataclasses.fields(WorkOutcome)}
    for name in field_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"field {name!r} matches forbidden {forbidden!r}"


def test_executor_failure_reason_is_a_closed_enum_never_free_form_text() -> None:
    """Test ExecutorFailureReason is a closed enum with a fixed member
    set -- never free-form diagnostic text."""
    assert {member.value for member in ExecutorFailureReason} == {
        "RETRYABLE_EXECUTION_ERROR",
        "RETRYABLE_RESOURCE_EXHAUSTED",
        "TERMINAL_INVALID_OUTPUT",
        "TERMINAL_EXECUTION_ERROR",
    }
