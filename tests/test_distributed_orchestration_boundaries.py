"""MEGB-03H.2C.3B.2A: two structural boundary checks the required test
list names explicitly and the generic dependency-direction test does not
already cover:

1. No B.2A module imports any network-transport library -- this
   checkpoint is offline contract/schema design only, with no queue
   polling, no cloud adapter, and no network call of any kind (B.2B's
   own, separately authorized, scope).
2. The reference-execution plane's own contracts have no way to request
   candidate generation -- :class:`~src.distributed.work_contracts.ArtifactKind`
   has no generation-authoring member, and neither
   :class:`~src.distributed.protocols.WorkQueueProtocol` nor
   :class:`~src.distributed.protocols.ArtifactStoreProtocol` has a
   method that could create or request one.
"""

from tests.test_distributed_dependency_direction import _distributed_files
from tests.test_execution_dependency_direction import _imported_module_names
from src.distributed.protocols import ArtifactStoreProtocol, WorkQueueProtocol
from src.distributed.work_contracts import ArtifactKind

_B2A_MODULES = (
    "clock",
    "state_machine",
    "personal_policy",
    "safe_audit",
    "work_contracts",
    "worker_contracts",
    "protocols",
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


def test_no_b2a_module_imports_a_network_transport_library() -> None:
    """Test no b2a module imports a network transport library."""
    b2a_paths = [path for path in _distributed_files() if path.stem in _B2A_MODULES]
    assert len(b2a_paths) == len(_B2A_MODULES), (
        f"expected to find all of {_B2A_MODULES!r} under src/distributed/, found "
        f"{[path.stem for path in b2a_paths]!r}"
    )
    for path in b2a_paths:
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


def test_artifact_kind_has_no_candidate_generation_authoring_member() -> None:
    """Test ArtifactKind's closed enum has only the two reference-
    execution-plane kinds this checkpoint authorizes -- no member that
    could represent authoring or requesting a new candidate."""
    assert {member.value for member in ArtifactKind} == {
        "CANDIDATE_MANIFEST_ENTRY",
        "RESULT_ARTIFACT",
    }


def test_work_queue_protocol_has_no_candidate_generation_method() -> None:
    """Test the execution-plane's own work-queue interface has no method
    that could request or trigger candidate generation -- it only
    publishes/leases/cancels already-existing work referencing an
    already-immutable candidate manifest entry."""
    forbidden_substrings = ("generate", "vertex", "model", "invoke")
    for name in dir(WorkQueueProtocol):
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"{name!r} matches forbidden {forbidden!r}"


def test_artifact_store_protocol_has_no_write_or_generation_method() -> None:
    """Test the execution-plane's own artifact-store interface can only
    resolve (check existence of) an artifact reference -- it cannot
    write, create, or generate one; candidate manifests are produced
    exclusively by the (unimplemented, out-of-scope) generation plane."""
    forbidden_substrings = ("write", "create", "generate", "publish_artifact")
    for name in dir(ArtifactStoreProtocol):
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"{name!r} matches forbidden {forbidden!r}"
