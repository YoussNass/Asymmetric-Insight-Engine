"""CLI tests for Chapter 10 prospective local product operation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from asymmetric_engine import cli
from asymmetric_engine.cli import main
from asymmetric_engine.interfaces.operator_workspace import OperatorWorkspace


def _store_args(tmp_path: Path) -> tuple[list[str], Path, Path]:
    evidence = tmp_path / "evidence.sqlite"
    products = tmp_path / "products.sqlite"
    return (
        [
            "--evidence-database",
            str(evidence),
            "--product-database",
            str(products),
        ],
        evidence,
        products,
    )


def test_product_init_explicitly_creates_both_local_stores(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments, evidence, products = _store_args(tmp_path)

    assert main(["product", "init", *arguments]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert evidence.is_file()
    assert products.is_file()


def test_local_evidence_cli_requires_initialized_store_and_records_at_ingestion(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "evidence.sqlite"
    source = tmp_path / "source.txt"
    source.write_text("prospective local evidence", encoding="utf-8")
    command = [
        "evidence",
        "ingest-local",
        "--database",
        str(database),
        "--file",
        str(source),
        "--provider-record-id",
        "manual-001",
        "--provider-version",
        "v1",
        "--subject",
        "company:manual-test",
        "--title",
        "Manual source",
        "--source-uri",
        "file-origin://manual-001",
        "--source-type",
        "research",
        "--effective-at",
        "2026-09-02T06:00:00+00:00",
        "--media-type",
        "text/plain",
    ]

    assert main(command) == 2
    missing_store = json.loads(capsys.readouterr().out)
    assert "does not exist" in missing_store["message"]
    assert not database.exists()

    product_database = tmp_path / "products.sqlite"
    assert (
        main(
            [
                "product",
                "init",
                "--evidence-database",
                str(database),
                "--product-database",
                str(product_database),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(command) == 0
    ingestion = json.loads(capsys.readouterr().out)
    assert ingestion["status"] == "inserted"
    assert ingestion["document"]["provider"] == "local-manual"
    assert ingestion["document"]["availability_basis"] == "observed_at_ingestion"
    assert ingestion["document"]["available_at"] == ingestion["document"]["recorded_at"]


def test_product_workspace_uses_write_enabled_canonical_runtime(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments, _, _ = _store_args(tmp_path)
    assert main(["product", "init", *arguments]) == 0
    capsys.readouterr()
    captured: list[OperatorWorkspace] = []

    def fake_serve(workspace: OperatorWorkspace, *, port: int) -> None:
        assert port == 9876
        captured.append(workspace)

    monkeypatch.setattr(cli, "serve_local_workspace", fake_serve)

    assert main(["product", "workspace", *arguments, "--port", "9876"]) == 0
    assert captured and captured[0].write_enabled is True
    assert "AIE prospective workspace" in capsys.readouterr().out
