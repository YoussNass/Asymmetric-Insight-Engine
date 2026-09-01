"""Unit tests for the Chapter 9C operator workspace."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

import pytest

from asymmetric_engine.application.execution import BuildExecutionPolicy
from asymmetric_engine.application.learning import (
    BuildDecisionLearningEvaluation,
    OpenDecisionLearningCase,
)
from asymmetric_engine.application.marginal_decision import RecordPositionHold
from asymmetric_engine.application.portfolio_policy import BuildOwnerPortfolioPolicy
from asymmetric_engine.application.portfolio_state import BuildPortfolioState
from asymmetric_engine.application.product_persistence import (
    ListProductRecords,
    LoadProductRecord,
    StoreProductRecord,
)
from asymmetric_engine.cli import main
from asymmetric_engine.infrastructure.persistence.sqlite_product_store import (
    SQLiteProductRecordRepository,
)
from asymmetric_engine.interfaces.api import (
    AieApiServices,
    AieProductApi,
    BuildPortfolioStateRequest,
)
from asymmetric_engine.interfaces.operator_workspace import (
    OperatorWorkspace,
    UnknownWorkspaceOperation,
    WorkspaceWriteUnavailable,
)
from asymmetric_engine.interfaces.workspace_web import (
    LOCAL_WORKSPACE_HOST,
    MAX_REQUEST_BYTES,
    WorkspaceWriteTokenError,
    WorkspaceWsgiApp,
    render_workspace_index,
)
from tests.execution_factories import ExecutionContext, make_execution_context
from tests.portfolio_factories import make_portfolio_draft


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _repository_and_store(
    tmp_path: Path,
) -> tuple[SQLiteProductRecordRepository, StoreProductRecord]:
    repository = SQLiteProductRecordRepository(tmp_path / "products.sqlite")
    store = StoreProductRecord(repository=repository, clock=FixedClock())
    return repository, store


def _workspace(tmp_path: Path) -> tuple[OperatorWorkspace, StoreProductRecord]:
    repository, store = _repository_and_store(tmp_path)
    workspace = OperatorWorkspace(
        loader=LoadProductRecord(repository),
        lister=ListProductRecords(repository),
    )
    return workspace, store


def _real_api(context: ExecutionContext) -> AieProductApi:
    decision = context.decision_context
    return AieProductApi(
        AieApiServices(
            portfolio_state=decision.state_builder,
            portfolio_exposure=decision.exposure_builder,
            marginal_decision=decision.decision_builder,
            position_hold=RecordPositionHold(
                state_builder=decision.state_builder,
                exposure_builder=decision.exposure_builder,
            ),
            owner_policy=BuildOwnerPortfolioPolicy(),
            policy_application=context.policy_application,
            replacement=context.replacement_builder,
            execution_policy=BuildExecutionPolicy(),
            execution=context.execution_builder,
            learning_case=OpenDecisionLearningCase(
                execution_builder=context.execution_builder,
            ),
            learning_evaluation=BuildDecisionLearningEvaluation(),
        )
    )


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
        workspace.submit_json("build_portfolio_state", "not-json")


def test_read_only_cli_does_not_create_a_missing_product_store(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "missing-products.sqlite"

    assert main(["workspace", "--database", str(database)]) == 2
    assert not database.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"


def test_workspace_server_is_loopback_only() -> None:
    assert LOCAL_WORKSPACE_HOST == "127.0.0.1"


def test_write_workspace_persists_exact_canonical_api_output(tmp_path: Path) -> None:
    repository, store = _repository_and_store(tmp_path)
    api = _real_api(make_execution_context())
    workspace = OperatorWorkspace(
        loader=LoadProductRecord(repository),
        lister=ListProductRecords(repository),
        api=api,
        store=store,
    )
    request = BuildPortfolioStateRequest(draft=make_portfolio_draft())

    submission = workspace.submit_json(request.operation, request.model_dump_json())
    direct_response = api.build_portfolio_state(request)

    assert submission.response == direct_response
    assert len(submission.persisted) == 1
    envelope = submission.persisted[0].envelope
    expected_json = json.dumps(
        direct_response.result.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert envelope.payload_json == expected_json
    assert workspace.load_record(envelope.record_id).record == direct_response.result


def test_write_workspace_rejects_unknown_operation_without_dynamic_dispatch(
    tmp_path: Path,
) -> None:
    repository, store = _repository_and_store(tmp_path)
    workspace = OperatorWorkspace(
        loader=LoadProductRecord(repository),
        lister=ListProductRecords(repository),
        api=_real_api(make_execution_context()),
        store=store,
    )

    with pytest.raises(UnknownWorkspaceOperation):
        workspace.submit_json("client_defined_operation", "{}")


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


def test_workspace_request_body_limit_is_blocking() -> None:
    environ: dict[str, Any] = {
        "CONTENT_LENGTH": str(MAX_REQUEST_BYTES + 1),
        "wsgi.input": BytesIO(),
    }

    with pytest.raises(ValueError, match="exceeds admitted size"):
        WorkspaceWsgiApp._read_body(environ)
