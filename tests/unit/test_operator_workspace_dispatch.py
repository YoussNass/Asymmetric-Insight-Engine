"""Focused coverage of Chapter 9C explicit dispatch and persistence guards."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from pydantic import BaseModel

from asymmetric_engine.application.product_persistence import (
    ListProductRecords,
    LoadProductRecord,
    StoreProductRecord,
)
from asymmetric_engine.infrastructure.persistence.sqlite_product_store import (
    SQLiteProductRecordRepository,
)
from asymmetric_engine.interfaces.api import (
    AieProductApi,
    ApiResponse,
    ApplyPortfolioPolicyRequest,
    BuildExecutionFromPolicyAllocationRequest,
    BuildExecutionFromReplacementRequest,
    BuildExecutionPolicyRequest,
    BuildLearningEvaluationRequest,
    BuildMarginalDecisionRequest,
    BuildOwnerPortfolioPolicyRequest,
    BuildPortfolioExposureRequest,
    BuildPortfolioStateRequest,
    BuildReplacementDecisionRequest,
    MarginalDecisionPackage,
    OpenLearningCaseFromPolicyAllocationRequest,
    OpenLearningCaseFromReplacementRequest,
    RecordPositionHoldRequest,
)
from asymmetric_engine.interfaces.operator_workspace import (
    OperatorWorkspace,
    WorkspaceApiRequest,
)
from tests.execution_factories import make_execution_context


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


class Marker(BaseModel):
    method: str


class DispatchRecorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Callable[[object], Marker]:
        def dispatch(_: object) -> Marker:
            self.calls.append(name)
            return Marker(method=name)

        return dispatch


_REQUEST_CASES: tuple[tuple[type[BaseModel], str], ...] = (
    (BuildPortfolioStateRequest, "build_portfolio_state"),
    (BuildPortfolioExposureRequest, "build_portfolio_exposure"),
    (BuildMarginalDecisionRequest, "build_marginal_decision"),
    (RecordPositionHoldRequest, "record_position_hold"),
    (BuildOwnerPortfolioPolicyRequest, "build_owner_portfolio_policy"),
    (ApplyPortfolioPolicyRequest, "apply_portfolio_policy"),
    (BuildReplacementDecisionRequest, "build_replacement_decision"),
    (BuildExecutionPolicyRequest, "build_execution_policy"),
    (
        BuildExecutionFromPolicyAllocationRequest,
        "build_execution_from_policy_allocation",
    ),
    (BuildExecutionFromReplacementRequest, "build_execution_from_replacement"),
    (
        OpenLearningCaseFromPolicyAllocationRequest,
        "open_learning_case_from_policy_allocation",
    ),
    (
        OpenLearningCaseFromReplacementRequest,
        "open_learning_case_from_replacement",
    ),
    (BuildLearningEvaluationRequest, "build_learning_evaluation"),
)


@pytest.mark.parametrize(("request_type", "expected_method"), _REQUEST_CASES)
def test_workspace_dispatch_uses_only_explicit_api_methods(
    request_type: type[BaseModel],
    expected_method: str,
) -> None:
    recorder = DispatchRecorder()
    request = cast(WorkspaceApiRequest, request_type.model_construct())

    result = OperatorWorkspace._dispatch(cast(AieProductApi, recorder), request)

    assert result == Marker(method=expected_method)
    assert recorder.calls == [expected_method]


def test_workspace_dispatch_rejects_unknown_request_type() -> None:
    recorder = DispatchRecorder()
    unsupported = cast(WorkspaceApiRequest, Marker(method="unsupported"))

    with pytest.raises(TypeError, match="unsupported workspace request type"):
        OperatorWorkspace._dispatch(cast(AieProductApi, recorder), unsupported)


def _write_workspace(tmp_path: Path) -> OperatorWorkspace:
    repository = SQLiteProductRecordRepository(tmp_path / "products.sqlite")
    store = StoreProductRecord(repository=repository, clock=FixedClock())
    return OperatorWorkspace(
        loader=LoadProductRecord(repository),
        lister=ListProductRecords(repository),
        api=cast(AieProductApi, object()),
        store=store,
    )


def test_workspace_constructor_requires_api_and_store_together(tmp_path: Path) -> None:
    repository = SQLiteProductRecordRepository(tmp_path / "products.sqlite")

    with pytest.raises(ValueError, match="requires both API and product store"):
        OperatorWorkspace(
            loader=LoadProductRecord(repository),
            lister=ListProductRecords(repository),
            api=cast(AieProductApi, object()),
        )


def test_workspace_persistence_rejects_non_api_and_non_model_results(tmp_path: Path) -> None:
    workspace = _write_workspace(tmp_path)

    with pytest.raises(TypeError, match="non-API response"):
        workspace._persist_response(Marker(method="not-api"))

    with pytest.raises(TypeError, match="not a persistable canonical model"):
        workspace._persist_response(ApiResponse[int](operation="invalid", result=1))


def test_workspace_persists_every_record_from_marginal_decision_package(tmp_path: Path) -> None:
    workspace = _write_workspace(tmp_path)
    context = make_execution_context()
    package = MarginalDecisionPackage.from_application(context.marginal_result)
    response = ApiResponse[MarginalDecisionPackage](
        operation="build_marginal_decision",
        result=package,
    )

    persisted = workspace._persist_response(response)

    assert len(persisted) == len(package.fits) + 1
    assert {item.envelope.kind.value for item in persisted} == {
        "portfolio_fit",
        "marginal_decision",
    }
