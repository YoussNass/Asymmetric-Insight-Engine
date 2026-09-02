"""Architecture guards for Chapter 10 prospective local product composition."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "asymmetric_engine"
DOMAIN_ROOT = SRC_ROOT / "domain"
APPLICATION_ROOT = SRC_ROOT / "application"
INTERFACES_ROOT = SRC_ROOT / "interfaces"
RUNTIME_FILE = SRC_ROOT / "product_runtime.py"
INTAKE_FILE = INTERFACES_ROOT / "prospective_intake.py"
LOCAL_PROVIDER_FILE = SRC_ROOT / "infrastructure" / "providers" / "local_file.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_inner_layers_do_not_depend_on_product_runtime() -> None:
    violations: list[str] = []
    for root in (DOMAIN_ROOT, APPLICATION_ROOT, INTERFACES_ROOT):
        for path in root.rglob("*.py"):
            for module in _imports(path):
                if module == "asymmetric_engine.product_runtime":
                    violations.append(str(path.relative_to(PROJECT_ROOT)))
    assert not violations, "Inner layers import product runtime: " + ", ".join(violations)


def test_typed_intake_has_no_infrastructure_or_runtime_dependency() -> None:
    imports = _imports(INTAKE_FILE)
    assert not any(module.startswith("asymmetric_engine.infrastructure") for module in imports)
    assert "asymmetric_engine.product_runtime" not in imports


def test_composition_root_is_the_explicit_cross_layer_owner() -> None:
    imports = _imports(RUNTIME_FILE)
    assert any(module.startswith("asymmetric_engine.application") for module in imports)
    assert any(module.startswith("asymmetric_engine.infrastructure") for module in imports)
    assert any(module.startswith("asymmetric_engine.interfaces") for module in imports)


def test_local_manual_provider_cannot_assert_historical_availability() -> None:
    text = LOCAL_PROVIDER_FILE.read_text(encoding="utf-8")
    assert "AvailabilityBasis.OBSERVED_AT_INGESTION" in text
    assert "AvailabilityBasis.PROVIDER_ASSERTED" not in text
    assert "available_at=None" in text
