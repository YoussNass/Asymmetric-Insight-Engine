"""Architecture tests for the innermost domain boundary."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

DOMAIN_ROOT = Path(__file__).parents[2] / "src" / "asymmetric_engine" / "domain"
APPLICATION_ROOT = DOMAIN_ROOT.parent / "application"
PORTFOLIO_ROOT = DOMAIN_ROOT / "portfolio"
EXECUTION_ROOT = DOMAIN_ROOT / "execution"
PORTFOLIO_STATE_FILES = (PORTFOLIO_ROOT / "models.py",)
PORTFOLIO_EXPOSURE_FILES = (PORTFOLIO_ROOT / "exposure.py",)
PORTFOLIO_DECISION_FILES = (
    PORTFOLIO_ROOT / "decision.py",
    PORTFOLIO_ROOT / "policy.py",
)
EXECUTION_DOMAIN_FILES = (EXECUTION_ROOT / "models.py",)
MARGINAL_DECISION_APPLICATION_FILE = APPLICATION_ROOT / "marginal_decision.py"
PORTFOLIO_POLICY_APPLICATION_FILE = APPLICATION_ROOT / "portfolio_policy.py"
EXECUTION_APPLICATION_FILE = APPLICATION_ROOT / "execution.py"
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


def test_chapter_6c_portfolio_domain_references_underwriting_without_importing_it() -> None:
    """Portfolio Decision stores immutable refs; the application layer joins contexts."""

    assert all(path.is_file() for path in PORTFOLIO_DECISION_FILES)
    decision_imports = {
        module for path in PORTFOLIO_DECISION_FILES for module in imported_modules(path)
    }
    forbidden_prefixes = (
        "asymmetric_engine.application",
        "asymmetric_engine.domain.causal",
        "asymmetric_engine.domain.opportunity",
        "asymmetric_engine.infrastructure",
        "asymmetric_engine.interfaces",
    )
    violations = [module for module in decision_imports if module.startswith(forbidden_prefixes)]
    assert not violations, "Chapter 6C decision boundary violations:\n" + "\n".join(violations)

    for application_file in (
        MARGINAL_DECISION_APPLICATION_FILE,
        PORTFOLIO_POLICY_APPLICATION_FILE,
    ):
        assert application_file.is_file()
        application_imports = set(imported_modules(application_file))
        assert any(
            module.startswith("asymmetric_engine.domain.opportunity")
            for module in application_imports
        )

    upstream_imports = {
        module
        for path in (*PORTFOLIO_STATE_FILES, *PORTFOLIO_EXPOSURE_FILES)
        for module in imported_modules(path)
    }
    assert not any(
        module.startswith("asymmetric_engine.domain.portfolio.decision")
        or module.startswith("asymmetric_engine.domain.portfolio.policy")
        for module in upstream_imports
    )


def test_chapter_6c2_does_not_import_execution_or_outer_adapters() -> None:
    """Replacement decides target allocation before Chapter 7 timing and staging."""

    imports = set(imported_modules(PORTFOLIO_POLICY_APPLICATION_FILE))
    forbidden = (
        "asymmetric_engine.interfaces",
        "asymmetric_engine.infrastructure",
        "asymmetric_engine.application.execution",
        "asymmetric_engine.domain.execution",
    )
    assert not any(module.startswith(forbidden) for module in imports)


def test_chapter_7_execution_domain_does_not_recreate_upstream_contexts() -> None:
    """Execution stores an approved instruction and cannot import investment contexts."""

    assert EXECUTION_ROOT.is_dir(), f"Execution root does not exist: {EXECUTION_ROOT}"
    assert all(path.is_file() for path in EXECUTION_DOMAIN_FILES)
    imports = {
        module for path in EXECUTION_DOMAIN_FILES for module in imported_modules(path)
    }
    forbidden = (
        "asymmetric_engine.application",
        "asymmetric_engine.domain.causal",
        "asymmetric_engine.domain.opportunity",
        "asymmetric_engine.domain.portfolio",
        "asymmetric_engine.infrastructure",
        "asymmetric_engine.interfaces",
    )
    violations = [module for module in imports if module.startswith(forbidden)]
    assert not violations, "Chapter 7 Execution boundary violations:\n" + "\n".join(violations)


def test_chapter_7_application_joins_upstream_without_outer_adapter_dependencies() -> None:
    """Only the application layer may replay Portfolio decisions into Execution."""

    assert EXECUTION_APPLICATION_FILE.is_file()
    imports = set(imported_modules(EXECUTION_APPLICATION_FILE))
    assert any(module.startswith("asymmetric_engine.domain.execution") for module in imports)
    assert any(module.startswith("asymmetric_engine.domain.portfolio") for module in imports)
    assert any(
        module.startswith("asymmetric_engine.application.portfolio_policy") for module in imports
    )
    assert not any(
        module.startswith(("asymmetric_engine.infrastructure", "asymmetric_engine.interfaces"))
        for module in imports
    )


def test_chapter_6_application_does_not_depend_on_execution() -> None:
    """Execution is downstream and cannot become an input to capital allocation."""

    for path in (MARGINAL_DECISION_APPLICATION_FILE, PORTFOLIO_POLICY_APPLICATION_FILE):
        imports = set(imported_modules(path))
        assert not any(module.startswith("asymmetric_engine.domain.execution") for module in imports)
        assert not any(
            module.startswith("asymmetric_engine.application.execution") for module in imports
        )
