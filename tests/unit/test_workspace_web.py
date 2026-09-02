"""Focused browser-boundary tests for the local Chapter 9C workspace."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from asymmetric_engine.application.portfolio_state import BuildPortfolioState
from asymmetric_engine.application.product_persistence import (
    ListProductRecords,
    LoadProductRecord,
    StoreProductRecord,
)
from asymmetric_engine.infrastructure.persistence.sqlite_product_store import (
    SQLiteProductRecordRepository,
)
from asymmetric_engine.interfaces.operator_workspace import OperatorWorkspace
from asymmetric_engine.interfaces.workspace_web import (
    MAX_REQUEST_BYTES,
    WorkspaceWsgiApp,
    render_record_detail,
    render_submission_result,
)
from tests.portfolio_factories import make_portfolio_draft


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _workspace_with_state(tmp_path: Path) -> tuple[OperatorWorkspace, str]:
    repository = SQLiteProductRecordRepository(tmp_path / "products.sqlite")
    store = StoreProductRecord(repository=repository, clock=FixedClock())
    state = BuildPortfolioState().execute(make_portfolio_draft())
    result = store.execute(state)
    workspace = OperatorWorkspace(
        loader=LoadProductRecord(repository),
        lister=ListProductRecords(repository),
    )
    return workspace, str(result.envelope.record_id)


def _call(
    app: WorkspaceWsgiApp,
    method: str,
    path: str,
    body: bytes = b"",
) -> tuple[str, str]:
    environ: dict[str, Any] = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": BytesIO(body),
    }
    status: list[str] = []

    def start_response(
        value: str,
        headers: list[tuple[str, str]],
        exc_info: object | None = None,
    ) -> None:
        del headers, exc_info
        status.append(value)

    response = b"".join(app(environ, start_response)).decode()
    return status[0], response


def test_browser_lists_and_renders_persisted_record(tmp_path: Path) -> None:
    workspace, record_id = _workspace_with_state(tmp_path)
    app = WorkspaceWsgiApp(workspace)
    status, index = _call(app, "GET", "/")
    assert status == "200 OK"
    assert record_id in index
    status, detail = _call(app, "GET", f"/records/{record_id}")
    assert status == "200 OK"
    assert "Canonical record" in detail
    assert "Downstream use still requires canonical application replay" in detail


def test_record_renderer_handles_non_card_record(tmp_path: Path) -> None:
    workspace, record_id = _workspace_with_state(tmp_path)
    detail = render_record_detail(workspace.load_record(UUID(record_id)))
    assert "Canonical record" in detail


def test_browser_invalid_record_id_is_blocking_conflict(tmp_path: Path) -> None:
    workspace, _ = _workspace_with_state(tmp_path)
    status, response = _call(WorkspaceWsgiApp(workspace), "GET", "/records/not-a-uuid")
    assert status == "409 Conflict"
    assert '"blocking": true' in response


def test_browser_unknown_route_is_404(tmp_path: Path) -> None:
    workspace, _ = _workspace_with_state(tmp_path)
    status, response = _call(WorkspaceWsgiApp(workspace), "GET", "/missing")
    assert status == "404 Not Found"
    assert "workspace route not found" in response


def test_read_only_post_is_forbidden(tmp_path: Path) -> None:
    workspace, _ = _workspace_with_state(tmp_path)
    status, response = _call(
        WorkspaceWsgiApp(workspace),
        "POST",
        "/operations/build_portfolio_state",
        b"{}",
    )
    assert status == "403 Forbidden"
    assert "WorkspaceWriteTokenError" in response


def test_request_body_size_and_length_are_fail_closed(tmp_path: Path) -> None:
    workspace, _ = _workspace_with_state(tmp_path)
    app = WorkspaceWsgiApp(workspace)
    with pytest.raises(ValueError, match="exceeds admitted size"):
        app._read_body({"CONTENT_LENGTH": str(MAX_REQUEST_BYTES + 1), "wsgi.input": BytesIO()})
    with pytest.raises(ValueError, match="invalid Content-Length"):
        app._read_body({"CONTENT_LENGTH": "bad", "wsgi.input": BytesIO()})


def test_submission_result_renders_exact_response() -> None:
    submission = {
        "persisted": [
            {
                "kind": "portfolio_state",
                "record_id": "00000000-0000-0000-0000-000000000001",
                "status": "appended",
            }
        ],
        "response": {"contract_version": "aie-api-v1"},
    }
    rendered = render_submission_result(json.dumps(submission))
    assert "portfolio_state" in rendered
    assert "aie-api-v1" in rendered
