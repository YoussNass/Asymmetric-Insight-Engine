"""Architecture guards for the Chapter 9B product persistence capability."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "asymmetric_engine"
APPLICATION_FILE = SRC_ROOT / "application" / "product_persistence.py"
SQLITE_FILE = SRC_ROOT / "infrastructure" / "persistence" / "sqlite_product_store.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_product_persistence_port_depends_only_inward() -> None:
    imports = _imports(APPLICATION_FILE)
    assert any(module.startswith("asymmetric_engine.domain") for module in imports)
    assert not any(module.startswith("asymmetric_engine.infrastructure") for module in imports)
    assert not any(module.startswith("asymmetric_engine.interfaces") for module in imports)


def test_sqlite_product_store_is_an_outer_adapter() -> None:
    imports = _imports(SQLITE_FILE)
    assert any(module.startswith("asymmetric_engine.application") for module in imports)
    assert not any(module.startswith("asymmetric_engine.interfaces") for module in imports)


def test_product_persistence_uses_no_orm_or_production_database_client() -> None:
    imports = _imports(SQLITE_FILE) | _imports(APPLICATION_FILE)
    forbidden_roots = {"sqlalchemy", "psycopg", "psycopg2", "asyncpg"}
    assert not {module.split(".", 1)[0] for module in imports} & forbidden_roots
