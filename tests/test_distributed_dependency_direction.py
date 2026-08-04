"""MEGB-03H.2C.3B.1: structural test enforcing that ``src/distributed/``
is provider-neutral -- reuses
``tests/test_execution_dependency_direction.py``'s own
``_imported_module_names`` AST helper (rather than redefining an
identical one) and extends the same pattern to also forbid GCP SDK,
``gcloud`` subprocess invocation, and Docker, not only ``src.reference``.

Parses each ``src/distributed/*.py`` module's own AST (never imports it
as live code beyond what pytest collection already does) and inspects
its ``import``/``from ... import`` statements and any ``subprocess``/
``os.system`` call arguments directly, so this test can never be fooled
by a conditional or lazily-executed import either.
"""

import ast
from pathlib import Path

from tests.test_execution_dependency_direction import _imported_module_names

DISTRIBUTED_DIR = Path(__file__).resolve().parent.parent / "src" / "distributed"

_FORBIDDEN_IMPORT_PREFIXES = (
    "src.reference",
    "google.cloud",
    "google.auth",
    "googleapiclient",
    "docker",  # the docker-py SDK, distinct from this project's own src.execution.docker_backend
)

_FORBIDDEN_LITERAL_SUBSTRINGS = ("gcloud", "docker ")


def _offending_imports(imported: set[str], prefixes: tuple[str, ...]) -> set[str]:
    """Names in ``imported`` equal to, or dotted-submodules of, any of
    ``prefixes`` -- the one shared implementation both forbidden-import
    tests below use, so the two checks never drift into two slightly
    different definitions of "matches a forbidden prefix"."""
    return {
        name
        for name in imported
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)
    }


def _string_literals(source: str) -> list[str]:
    """Every string constant in ``source`` *except* docstrings -- a
    docstring may legitimately discuss "gcloud"/"docker" in prose (e.g.
    "no gcloud is invoked here"); an actual subprocess-call argument or
    other executable string literal never needs to."""
    tree = ast.parse(source)
    docstring_node_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_node_ids.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstring_node_ids
    ]


def _distributed_files() -> list[Path]:
    files = sorted(DISTRIBUTED_DIR.glob("*.py"))
    assert files, "expected to find src/distributed/*.py files"
    return files


def test_no_distributed_module_imports_src_reference() -> None:
    """No src/distributed/*.py module may import src.reference or any of
    its submodules -- this package must remain provider-neutral and
    independent of the reference-execution schema it is designed to
    integrate with only via a later, separately-authorized checkpoint."""
    for path in _distributed_files():
        imported = _imported_module_names(path.read_text(encoding="utf-8"))
        offending = _offending_imports(imported, ("src.reference",))
        assert not offending, f"{path.name} imports {offending!r} -- forbidden"


def test_no_distributed_module_imports_gcp_sdk_or_docker_sdk() -> None:
    """No src/distributed/*.py module may import a GCP SDK (google.cloud/
    google.auth/googleapiclient) or the docker-py SDK -- this checkpoint
    is documentation/schema/test work only, per its own explicit
    execution constraints."""
    for path in _distributed_files():
        imported = _imported_module_names(path.read_text(encoding="utf-8"))
        offending = _offending_imports(imported, _FORBIDDEN_IMPORT_PREFIXES)
        assert not offending, f"{path.name} imports {offending!r} -- forbidden"


def test_no_distributed_module_invokes_gcloud_or_docker_subprocess() -> None:
    """No src/distributed/*.py module contains a string literal naming
    ``gcloud`` or a ``docker`` CLI invocation -- catches a subprocess
    call built from a string constant, not merely an SDK import."""
    for path in _distributed_files():
        literals = _string_literals(path.read_text(encoding="utf-8"))
        for literal in literals:
            lowered = literal.lower()
            for forbidden in _FORBIDDEN_LITERAL_SUBSTRINGS:
                assert forbidden not in lowered, (
                    f"{path.name} contains a string literal {literal!r} matching forbidden "
                    f"substring {forbidden!r}"
                )


def test_no_distributed_module_imports_subprocess_or_os_system() -> None:
    """No src/distributed/*.py module imports ``subprocess`` at all --
    this checkpoint's own execution constraints ("do not run Docker",
    "do not invoke gcloud") are best enforced by this package never
    shelling out to anything, not merely by avoiding specific command
    names."""
    for path in _distributed_files():
        imported = _imported_module_names(path.read_text(encoding="utf-8"))
        assert "subprocess" not in imported, f"{path.name} imports subprocess -- forbidden"


def test_distributed_package_has_no_managed_model_module() -> None:
    """Managed-model/candidate-generation-plane provenance is reserved
    for MEGB-03H.2C.3G -- no module name in this package may be mistaken
    for it."""
    forbidden_substrings = ("model", "vertex", "maas", "generation")
    for path in _distributed_files():
        lowered = path.stem.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"{path.name} name matches forbidden {forbidden!r}"
