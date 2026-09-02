"""Write-mode presentation coverage without introducing shadow financial logic."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

import pytest

from asymmetric_engine.application.product_persistence import (
    ListProductRecords,
    LoadProductRecord,
    StoreProductRecord,
)
from asymmetric_engine.infrastructure.persistence.sqlite_product_store import (
    SQLiteProductRecordRepository,
)
from asymmetric_engine.interfaces.api import AieProductApi
from asymmetric_engine.interfaces.operator_workspace import OperatorWorkspace
from asymmetric_engine.interfaces.workspace_web import WorkspaceWsgiApp, render_workspace_index


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _write_workspace(tmp_path: Path) -> OperatorWorkspace:
    repository = SQLiteProductRecordRepository(tmp_path / "products.sqlite")
    return OperatorWorkspace(
        loader=LoadProductRecord(repository),
        lister=ListProductRecords(repository),
        api=cast(AieProductApi, object()),
        store=StoreProductRecord(repository=repository, clock=FixedClock()),
    )


def test_write_index_renders_only_explicit_operation_registry(tmp_path: Path) -> None:
    rendered = render_workspace_index(_write_workspace(tmp_path), write_token="local-secret")
    assert "build_portfolio_state" in rendered
    assert "build_learning_evaluation" in rendered
    assert "local-secret" in rendered
    assert "client_defined_operation" not in rendered


def test_form_parser_requires_operation_and_payload() -> None:
    body = urlencode(
        {
            "operation": "build_portfolio_state",
            "payload": "{}",
            "write_token": "t",
        }
    ).encode()
    environ: dict[str, Any] = {
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": BytesIO(body),
    }
    assert WorkspaceWsgiApp._form_submission(environ) == (
        "build_portfolio_state",
        "{}",
        "t",
    )

    empty = urlencode({"operation": "", "payload": "{}"}).encode()
    with pytest.raises(ValueError, match="operation and payload are required"):
        WorkspaceWsgiApp._form_submission(
            {"CONTENT_LENGTH": str(len(empty)), "wsgi.input": BytesIO(empty)}
        )


def test_body_reader_rejects_non_bytes_stream() -> None:
    class TextStream:
        def read(self, length: int) -> str:
            del length
            return "not-bytes"

    with pytest.raises(ValueError, match="must be bytes"):
        WorkspaceWsgiApp._read_body({"CONTENT_LENGTH": "1", "wsgi.input": TextStream()})
