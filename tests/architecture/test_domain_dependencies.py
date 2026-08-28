"""Architecture tests for the innermost domain boundary."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

DOMAIN_ROOT = Path(__file__).parents[2] / "src" / "asymmetric_engine" / "domain"
APPLICATION_ROOT = DOMAIN_ROOT.parent / "application"
PORTFOLIO_ROOT = DOMAIN_ROOT / "portfolio"
PORTFOLIO_STATE_FILES = (PORTFOLIO_ROOT / "models.py",)
PORTFOLIO_EXPOSURE_FILES = (PORTFOLIO_ROOT / "exposure.py",)
SRC_ROOT = DOMAIN_ROOT.parents[1]
APPROVED_EXTERNAL_ROOTS = frozenset({"pydantic"})
FORBIDDEN_APPLICATION_PREFIXES = (
    "asymmetric_engine.infrastructure",
    "asymmetric_engine.interfaces",
)


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


def test_application_does_not_import_outer_layers() -> None:
    assert APPLICATION_ROOT.is_dir(), f"Application root does not exist: {APPLICATION_ROOT}"
    violations: list[str] = []
    for path in APPLICATION_ROOT.rglob("*.py"):
        for module in imported_modules(path):
            if module.startswith(FORBIDDEN_APPLICATION_PREFIXES):
                violations.append(f"{path.relative_to(APPLICATION_ROOT)} imports {module}")

    assert not violations, "Application dependency violations:\n" + "\n".join(violations)


def test_chapter_6a_portfolio_state_does_not_depend_on_analytical_neighbors() -> None:
    """The factual slice must not pull Underwriting, Exposure, or allocation into its model."""

    assert PORTFOLIO_ROOT.is_dir(), f"Portfolio root does not exist: {PORTFOLIO_ROOT}"
    assert all(path.is_file() for path in PORTFOLIO_STATE_FILES)
    forbidden_prefixes = (
        "asymmetric_engine.domain.causal",
        "asymmetric_engine.domain.opportunity",
    )
    violations: list[str] = []
    for path in PORTFOLIO_STATE_FILES:
        for module in imported_modules(path):
            if module.startswith(forbidden_prefixes):
                violations.append(f"{path.relative_to(PORTFOLIO_ROOT)} imports {module}")

    assert not violations, "Chapter 6A boundary violations:\n" + "\n".join(violations)


def test_chapter_6b_exposure_does_not_import_causal_or_underwriting_contexts() -> None:
    """Descriptive look-through cannot recreate causal or standalone opportunity state."""

    assert all(path.is_file() for path in PORTFOLIO_EXPOSURE_FILES)
    forbidden_prefixes = (
        "asymmetric_engine.domain.causal",
        "asymmetric_engine.domain.opportunity",
    )
    violations: list[str] = []
    for path in PORTFOLIO_EXPOSURE_FILES:
        for module in imported_modules(path):
            if module.startswith(forbidden_prefixes):
                violations.append(f"{path.relative_to(PORTFOLIO_ROOT)} imports {module}")

    assert not violations, "Chapter 6B boundary violations:\n" + "\n".join(violations)
