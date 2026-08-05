"""MEGB-03H.2C.3B.2B.1: no-network-import and leakage boundary checks for
the five new B.2B.1 store modules. The existing
``tests/test_distributed_dependency_direction.py`` already generically
globs every ``src/distributed/*.py`` file for the no-``src.reference``/
no-GCP-or-Docker-SDK/no-``gcloud``-or-``docker``-subprocess/no-
``subprocess``-import/no-forbidden-filename checks (these five new
modules are automatically covered by it, verified by running it after
adding these files). Its own no-network-import check, however, iterates
a B.2A-specific hardcoded module list -- this file extends the same
check to the five new B.2B.1 modules without modifying that
already-accepted test."""

# pylint: disable=duplicate-code
# This module's own no-network-import test inherently mirrors
# tests/test_distributed_orchestration_boundaries.py's own equivalent
# test (same check shape, different module list) -- shared boilerplate,
# not shared logic.

import dataclasses
import inspect

from src.distributed import (
    artifact_store,
    atomic_work_store,
    audit_sink_store,
    budget_store,
    worker_registry_store,
)
from src.distributed.atomic_work_store import AtomicWorkStore, AuthoritativeWorkRecord
from src.distributed.budget_store import BudgetReservation
from src.distributed.protocols import AtomicWorkStoreProtocol
from tests._distributed_orchestration_fixtures import make_sha256
from tests.test_distributed_dependency_direction import _distributed_files
from tests.test_execution_dependency_direction import _imported_module_names

_B2B1_MODULES = (
    "atomic_work_store",
    "artifact_store",
    "budget_store",
    "worker_registry_store",
    "audit_sink_store",
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


def test_all_five_b2b1_modules_exist_under_src_distributed() -> None:
    """Test all five b2b1 modules exist under src distributed."""
    b2b1_paths = [path for path in _distributed_files() if path.stem in _B2B1_MODULES]
    assert len(b2b1_paths) == len(_B2B1_MODULES), (
        f"expected to find all of {_B2B1_MODULES!r} under src/distributed/, found "
        f"{[path.stem for path in b2b1_paths]!r}"
    )


def test_no_b2b1_module_imports_a_network_transport_library() -> None:
    """Test no b2b1 module imports a network transport library."""
    for path in _distributed_files():
        if path.stem not in _B2B1_MODULES:
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


def test_no_b2b1_module_imports_multiprocessing_or_asyncio_event_loop() -> None:
    """Test the synthetic in-memory stores use only ``threading``, never
    ``multiprocessing``/``asyncio`` -- no coordinator/worker loop of any
    kind is authorized in this checkpoint."""
    forbidden = ("multiprocessing", "asyncio")
    for path in _distributed_files():
        if path.stem not in _B2B1_MODULES:
            continue
        imported = _imported_module_names(path.read_text(encoding="utf-8"))
        offending = {name for name in imported if name in forbidden}
        assert not offending, f"{path.name} imports {offending!r} -- forbidden"


def test_authoritative_work_record_has_no_raw_identifier_field() -> None:
    """Test AuthoritativeWorkRecord structurally excludes every forbidden
    concept -- no field name matching a raw candidate/credential/
    infrastructure-identifier/exception-text pattern."""
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
    )
    field_names = {field.name for field in dataclasses.fields(AuthoritativeWorkRecord)}
    for name in field_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"field {name!r} matches forbidden {forbidden!r}"


def test_budget_reservation_has_no_raw_identifier_field() -> None:
    """Test BudgetReservation structurally excludes every forbidden
    concept."""
    forbidden_substrings = ("credential", "password", "secret", "path", "hostname")
    field_names = {field.name for field in dataclasses.fields(BudgetReservation)}
    for name in field_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"field {name!r} matches forbidden {forbidden!r}"


def _always_valid_reservation(_reservation_id: str) -> bool:
    return True


def test_atomic_work_store_structurally_implements_atomic_work_store_protocol() -> None:
    """Test AtomicWorkStore structurally satisfies AtomicWorkStoreProtocol
    (MEGB-03H.2C.3B.2B.1 correction) -- the assignment below is checked
    statically by this repository's own mypy-strict verification step
    (a structural mismatch would be a mypy error), and the calls through
    the protocol-typed variable prove real runtime behavior is reachable
    through the protocol alone, never only through the concrete class."""
    concrete = AtomicWorkStore()
    store: AtomicWorkStoreProtocol = concrete
    reservation_id = "reservation-conformance-0001"
    record = store.create_if_absent(
        "work-conformance-0001",
        make_sha256("conformance-run-context"),
        reservation_id,
        _always_valid_reservation,
    )
    assert record.reservation_id == reservation_id
    read_back = store.read("work-conformance-0001")
    assert read_back == record


def test_b2b1_modules_define_no_coordinator_or_worker_loop_class() -> None:
    """Test none of the five new modules define a coordinator/worker
    execution-loop class -- that is MEGB-03H.2C.3B.2B.2's own,
    separately authorized, scope."""
    forbidden_substrings = ("coordinator", "workerloop", "scheduler", "executor")
    for module in (
        atomic_work_store,
        artifact_store,
        budget_store,
        worker_registry_store,
        audit_sink_store,
    ):
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue
            lowered = name.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in lowered, (
                    f"{module.__name__}.{name} matches forbidden {forbidden!r}"
                )
