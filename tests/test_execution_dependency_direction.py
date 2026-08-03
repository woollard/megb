"""MEGB-03H.2C.1: structural test enforcing the architectural constraint
that ``src/execution/`` must never import ``src/reference/`` or any
calibration schema. Reference-side code may adapt execution telemetry
into calibration records; the reverse direction is forbidden.

Parses each ``src/execution/*.py`` module's own AST (never imports it as
live code beyond what pytest collection already does) and inspects its
``import``/``from ... import`` statements directly, so this test can never
be fooled by a conditional or lazily-executed import either.
"""

import ast
from pathlib import Path

EXECUTION_DIR = Path(__file__).resolve().parent.parent / "src" / "execution"


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_no_execution_module_imports_src_reference() -> None:
    """No src/execution/*.py module may import src.reference or any of its
    submodules, at the AST level -- never as live code."""
    execution_files = sorted(EXECUTION_DIR.glob("*.py"))
    assert execution_files, "expected to find src/execution/*.py files"
    for path in execution_files:
        imported = _imported_module_names(path.read_text(encoding="utf-8"))
        offending = {
            name
            for name in imported
            if name == "src.reference" or name.startswith("src.reference.")
        }
        assert not offending, (
            f"{path.name} imports {offending!r} -- src/execution/ must never import "
            f"src/reference/"
        )
