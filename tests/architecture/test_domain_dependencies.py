"""Architecture tests for the innermost domain boundary."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

DOMAIN_ROOT = Path(__file__).parents[2] / "src" / "asymmetric_engine" / "domain"
SRC_ROOT = DOMAIN_ROOT.parents[1]
APPROVED_EXTERNAL_ROOTS = frozenset({"pydantic"})


def imported_modules(path: Path) -> Iterator[str]:
    """Yield absolute module names, resolving imports relative to each domain file."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package_parts = list(path.relative_to(SRC_ROOT).with_suffix("").parts[:-1])
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    yield node.module
                continue

            anchor_length = len(package_parts) - node.level + 1
            if anchor_length < 1:
                yield "<relative-import-outside-package>"
                continue

            resolved_parts = package_parts[:anchor_length]
            if node.module:
                resolved_parts.extend(node.module.split("."))
                yield ".".join(resolved_parts)
            else:
                for alias in node.names:
                    yield ".".join([*resolved_parts, *alias.name.split(".")])


def is_approved(module: str) -> bool:
    root = module.split(".", maxsplit=1)[0]
    if root in sys.stdlib_module_names:
        return True
    if root in APPROVED_EXTERNAL_ROOTS:
        return True
    return module == "asymmetric_engine.domain" or module.startswith("asymmetric_engine.domain.")


def test_domain_root_exists_and_contains_python_sources() -> None:
    assert DOMAIN_ROOT.is_dir(), f"Domain root does not exist: {DOMAIN_ROOT}"
    assert tuple(DOMAIN_ROOT.rglob("*.py")), "Domain root contains no Python sources"


def test_domain_imports_only_approved_dependencies() -> None:
    violations: list[str] = []
    for path in DOMAIN_ROOT.rglob("*.py"):
        for module in imported_modules(path):
            if not is_approved(module):
                violations.append(f"{path.relative_to(DOMAIN_ROOT)} imports {module}")

    assert not violations, "Domain dependency violations:\n" + "\n".join(violations)
