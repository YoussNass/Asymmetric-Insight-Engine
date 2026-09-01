"""Architecture guards for the Chapter 9C operator workspace."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "asymmetric_engine"
APPLICATION_ROOT = SRC_ROOT / "application"
DOMAIN_ROOT = SRC_ROOT / "domain"
WORKSPACE_FILES = (
    SRC_ROOT / "interfaces" / "operator_workspace.py",
    SRC_ROOT / "interfaces" / "workspace_web.py",
)
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


def test_workspace_remains_outside_domain_and_application() -> None:
    for path in WORKSPACE_FILES:
        assert path.is_file()
    violations: list[str] = []
    for root in (DOMAIN_ROOT, APPLICATION_ROOT):
        for path in root.rglob("*.py"):
            for module in _imports(path):
                if module.startswith("asymmetric_engine.interfaces"):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {module}")
    assert not violations, "Inner-layer workspace dependency violations:\n" + "\n".join(violations)


def test_workspace_orchestrator_does_not_depend_on_infrastructure() -> None:
    imports = _imports(WORKSPACE_FILES[0])
    assert not any(module.startswith("asymmetric_engine.infrastructure") for module in imports)


def test_workspace_web_uses_standard_library_server_only() -> None:
    imports = _imports(WORKSPACE_FILES[1])
    assert "wsgiref.simple_server" in imports
    text = PYPROJECT.read_text(encoding="utf-8").lower()
    for package in ("fastapi", "flask", "starlette", "uvicorn", "hypercorn", "streamlit"):
        assert package not in text


def test_workspace_has_no_broker_or_automatic_learning_feedback_dependency() -> None:
    imports = set().union(*(_imports(path) for path in WORKSPACE_FILES))
    forbidden_fragments = ("broker", "optimizer", "retraining", "automatic_feedback")
    assert not any(fragment in module for module in imports for fragment in forbidden_fragments)
