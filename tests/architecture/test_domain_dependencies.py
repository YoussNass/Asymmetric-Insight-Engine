"""Architecture tests for the innermost domain boundary."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_SEGMENTS = {"application", "infrastructure", "interfaces"}
DOMAIN_ROOT = Path(__file__).parents[2] / "src" / "asymmetric_engine" / "domain"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_domain_does_not_import_outer_layers() -> None:
    violations: list[str] = []
    for path in DOMAIN_ROOT.rglob("*.py"):
        for module in imported_modules(path):
            segments = set(module.split("."))
            if "asymmetric_engine" in segments and segments & FORBIDDEN_SEGMENTS:
                violations.append(f"{path.relative_to(DOMAIN_ROOT)} imports {module}")

    assert not violations, "Domain dependency violations:\n" + "\n".join(violations)
