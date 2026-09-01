"""Human-facing Chapter 9C workspace orchestration over accepted API and persistence ports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from asymmetric_engine.application.product_persistence import (
    ListProductRecords,
    LoadProductRecord,
    LoadedProductRecord,
    ProductAppendResult,
    ProductRecordKind,
    StoreProductRecord,
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

WORKSPACE_CONTRACT_VERSION = "operator-workspace-v1"

WorkspaceApiRequest: TypeAlias = (
    BuildPortfolioStateRequest
    | BuildPortfolioExposureRequest
    | BuildMarginalDecisionRequest
    | RecordPositionHoldRequest
    | BuildOwnerPortfolioPolicyRequest
    | ApplyPortfolioPolicyRequest
    | BuildReplacementDecisionRequest
    | BuildExecutionPolicyRequest
    | BuildExecutionFromPolicyAllocationRequest
    | BuildExecutionFromReplacementRequest
    | OpenLearningCaseFromPolicyAllocationRequest
    | OpenLearningCaseFromReplacementRequest
    | BuildLearningEvaluationRequest
)

_REQUEST_TYPES: dict[str, type[WorkspaceApiRequest]] = {
    "build_portfolio_state": BuildPortfolioStateRequest,
    "build_portfolio_exposure": BuildPortfolioExposureRequest,
    "build_marginal_decision": BuildMarginalDecisionRequest,
    "record_position_hold": RecordPositionHoldRequest,
    "build_owner_portfolio_policy": BuildOwnerPortfolioPolicyRequest,
    "apply_portfolio_policy": ApplyPortfolioPolicyRequest,
    "build_replacement_decision": BuildReplacementDecisionRequest,
    "build_execution_policy": BuildExecutionPolicyRequest,
    "build_execution_from_policy_allocation": BuildExecutionFromPolicyAllocationRequest,
    "build_execution_from_replacement": BuildExecutionFromReplacementRequest,
    "open_learning_case_from_policy_allocation": OpenLearningCaseFromPolicyAllocationRequest,
    "open_learning_case_from_replacement": OpenLearningCaseFromReplacementRequest,
    "build_learning_evaluation": BuildLearningEvaluationRequest,
}


class WorkspaceRecordSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    record_id: UUID
    kind: ProductRecordKind
    schema_version: str
    stored_at: str
    payload_sha256: str
    record_type: str


@dataclass(frozen=True, slots=True)
class WorkspaceSubmission:
    operation: str
    response: BaseModel
    persisted: tuple[ProductAppendResult, ...]


class WorkspaceWriteUnavailable(RuntimeError):
    """Raised when a read-only workspace receives a mutation request."""


class UnknownWorkspaceOperation(ValueError):
    """Raised when a client requests an operation outside the accepted API registry."""


class OperatorWorkspace:
    """Thin interface coordinator; it invokes AIE owners and persists their exact outputs."""

    def __init__(self, *, loader: LoadProductRecord, lister: ListProductRecords, api: AieProductApi | None = None, store: StoreProductRecord | None = None) -> None:
        if (api is None) != (store is None):
            raise ValueError("write-enabled workspace requires both API and product store")
        self._loader = loader
        self._lister = lister
        self._api = api
        self._store = store

    @property
    def write_enabled(self) -> bool:
        return self._api is not None and self._store is not None

    def list_records(self, kind: ProductRecordKind | None = None) -> tuple[WorkspaceRecordSummary, ...]:
        kinds = (kind,) if kind is not None else tuple(ProductRecordKind)
        loaded = tuple(item for item_kind in kinds for item in self._lister.execute(item_kind))
        ordered = sorted(loaded, key=lambda item: (item.envelope.stored_at, item.envelope.kind.value, str(item.envelope.record_id)))
        return tuple(self._summary(item) for item in ordered)

    def load_record(self, record_id: UUID, *, expected_kind: ProductRecordKind | None = None) -> LoadedProductRecord:
        return self._loader.execute(record_id, expected_kind=expected_kind)

    def submit_json(self, operation: str, payload_json: str) -> WorkspaceSubmission:
        self._require_write_services()
        request_type = _REQUEST_TYPES.get(operation)
        if request_type is None:
            raise UnknownWorkspaceOperation(operation)
        request = request_type.model_validate_json(payload_json)
        if request.operation != operation:
            raise ValueError("workspace route operation does not match request operation")
        return self.submit(request)

    def submit(self, request: WorkspaceApiRequest) -> WorkspaceSubmission:
        api, _ = self._require_write_services()
        response = self._dispatch(api, request)
        persisted = self._persist_response(response)
        return WorkspaceSubmission(operation=request.operation, response=response, persisted=persisted)

    def _require_write_services(self) -> tuple[AieProductApi, StoreProductRecord]:
        if self._api is None or self._store is None:
            raise WorkspaceWriteUnavailable("workspace is read-only because no configured AIE API/store were injected")
        return self._api, self._store

    def _persist_response(self, response: BaseModel) -> tuple[ProductAppendResult, ...]:
        _, store = self._require_write_services()
        if not isinstance(response, ApiResponse):
            raise TypeError("workspace received a non-API response")
        result = response.result
        if isinstance(result, MarginalDecisionPackage):
            return tuple(store.execute(record) for record in (*result.fits, result.decision))
        if not isinstance(result, BaseModel):
            raise TypeError("API response result is not a persistable canonical model")
        return (store.execute(result),)

    @staticmethod
    def _dispatch(api: AieProductApi, request: WorkspaceApiRequest) -> BaseModel:
        if isinstance(request, BuildPortfolioStateRequest): return api.build_portfolio_state(request)
        if isinstance(request, BuildPortfolioExposureRequest): return api.build_portfolio_exposure(request)
        if isinstance(request, BuildMarginalDecisionRequest): return api.build_marginal_decision(request)
        if isinstance(request, RecordPositionHoldRequest): return api.record_position_hold(request)
        if isinstance(request, BuildOwnerPortfolioPolicyRequest): return api.build_owner_portfolio_policy(request)
        if isinstance(request, ApplyPortfolioPolicyRequest): return api.apply_portfolio_policy(request)
        if isinstance(request, BuildReplacementDecisionRequest): return api.build_replacement_decision(request)
        if isinstance(request, BuildExecutionPolicyRequest): return api.build_execution_policy(request)
        if isinstance(request, BuildExecutionFromPolicyAllocationRequest): return api.build_execution_from_policy_allocation(request)
        if isinstance(request, BuildExecutionFromReplacementRequest): return api.build_execution_from_replacement(request)
        if isinstance(request, OpenLearningCaseFromPolicyAllocationRequest): return api.open_learning_case_from_policy_allocation(request)
        if isinstance(request, OpenLearningCaseFromReplacementRequest): return api.open_learning_case_from_replacement(request)
        if isinstance(request, BuildLearningEvaluationRequest): return api.build_learning_evaluation(request)
        raise TypeError(f"unsupported workspace request type: {type(request).__name__}")

    @staticmethod
    def _summary(item: LoadedProductRecord) -> WorkspaceRecordSummary:
        return WorkspaceRecordSummary(record_id=item.envelope.record_id, kind=item.envelope.kind, schema_version=item.envelope.schema_version, stored_at=item.envelope.stored_at.isoformat(), payload_sha256=item.envelope.payload_sha256, record_type=type(item.record).__name__)


def workspace_submission_json(submission: WorkspaceSubmission) -> str:
    return json.dumps({"contract_version": WORKSPACE_CONTRACT_VERSION, "operation": submission.operation, "persisted": [{"kind": item.envelope.kind.value, "record_id": str(item.envelope.record_id), "status": item.status.value, "stored_at": item.envelope.stored_at.isoformat()} for item in submission.persisted], "response": submission.response.model_dump(mode="json")}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


__all__ = ["WORKSPACE_CONTRACT_VERSION", "OperatorWorkspace", "UnknownWorkspaceOperation", "WorkspaceApiRequest", "WorkspaceRecordSummary", "WorkspaceSubmission", "WorkspaceWriteUnavailable", "workspace_submission_json"]
