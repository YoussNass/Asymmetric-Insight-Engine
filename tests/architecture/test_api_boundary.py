"""Architecture tests for the Chapter 9A transport-neutral API boundary."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "asymmetric_engine"
API_FILE = SRC_ROOT / "interfaces" / "api.py"
APPLICATION_ROOT = SRC_ROOT / "application"
DOMAIN_ROOT = SRC_ROOT / "domain"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_api_boundary_depends_inward_and_never_on_infrastructure() -> None:
    assert API_FILE.is_file()
    imports = _imports(API_FILE)
    assert any(module.startswith("asymmetric_engine.application") for module in imports)
    assert any(module.startswith("asymmetric_engine.domain") for module in imports)
    assert not any(module.startswith("asymmetric_engine.infrastructure") for module in imports)


def test_inner_layers_never_import_the_product_api() -> None:
    violations: list[str] = []
    for root in (DOMAIN_ROOT, APPLICATION_ROOT):
        for path in root.rglob("*.py"):
            for module in _imports(path):
                if module.startswith("asymmetric_engine.interfaces"):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {module}")
    assert not violations, "Inner-layer API dependency violations:\n" + "\n".join(violations)


def test_chapter_9a_adds_no_http_server_runtime_dependency() -> None:
    text = PYPROJECT.read_text(encoding="utf-8").lower()
    for package in ("fastapi", "flask", "starlette", "uvicorn", "hypercorn"):
        assert package not in text
