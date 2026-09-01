"""Unit tests for the Chapter 9C operator workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

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
from asymmetric_engine.interfaces.api import AieProductApi
from asymmetric_engine.interfaces.operator_workspace import (
    OperatorWorkspace,
    WorkspaceWriteUnavailable,
)
from asymmetric_engine.interfaces.workspace_web import (
    WorkspaceWriteTokenError,
    WorkspaceWsgiApp,
    render_workspace_index,
)
from tests.portfolio_factories import make_portfolio_draft


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _workspace(tmp_path: Path) -> tuple[OperatorWorkspace, StoreProductRecord]:
    repository = SQLiteProductRecordRepository(tmp_path / "products.sqlite")
    store = StoreProductRecord(repository=repository, clock=FixedClock())
    workspace = OperatorWorkspace(
        loader=LoadProductRecord(repository),
        lister=ListProductRecords(repository),
    )
    return workspace, store


def _enable_write_for_web_guard(
    workspace: OperatorWorkspace,
    store: StoreProductRecord,
) -> None:
    object.__setattr__(workspace, "_api", cast(AieProductApi, object()))
    object.__setattr__(workspace, "_store", store)


def test_read_only_workspace_lists_and_loads_verified_records(tmp_path: Path) -> None:
    workspace, store = _workspace(tmp_path)
    state = BuildPortfolioState().execute(make_portfolio_draft())
    appended = store.execute(state)

    summaries = workspace.list_records()
    assert len(summaries) == 1
    assert summaries[0].record_id == appended.envelope.record_id
    assert workspace.load_record(appended.envelope.record_id).record == state
    assert "Persisted canonical records" in render_workspace_index(workspace)


def test_read_only_workspace_rejects_submission_before_payload_parsing(
    tmp_path: Path,
) -> None:
    workspace, _ = _workspace(tmp_path)
    with pytest.raises(WorkspaceWriteUnavailable):
        workspace.submit_json("build_portfolio_state", "{}")


def test_write_enabled_web_app_requires_local_token(tmp_path: Path) -> None:
    workspace, store = _workspace(tmp_path)
    _enable_write_for_web_guard(workspace, store)
    with pytest.raises(WorkspaceWriteTokenError):
        WorkspaceWsgiApp(workspace)


def test_post_without_write_token_is_forbidden_before_dispatch(tmp_path: Path) -> None:
    workspace, store = _workspace(tmp_path)
    _enable_write_for_web_guard(workspace, store)
    app = WorkspaceWsgiApp(workspace, write_token="secret-token")
    body = urlencode({"operation": "build_portfolio_state", "payload": "{}"}).encode()
    environ: dict[str, Any] = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/submit",
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
    assert status == ["403 Forbidden"]
    assert "WorkspaceWriteTokenError" in response
