"""Explicit local product composition root for prospective AIE operation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from asymmetric_engine.application.causal_analysis import BuildCausalAnalysis
from asymmetric_engine.application.execution import BuildExecutionPlan, BuildExecutionPolicy
from asymmetric_engine.application.learning import (
    BuildDecisionLearningEvaluation,
    OpenDecisionLearningCase,
)
from asymmetric_engine.application.marginal_decision import (
    BuildMarginalDecision,
    RecordPositionHold,
)
from asymmetric_engine.application.portfolio_exposure import BuildPortfolioExposure
from asymmetric_engine.application.portfolio_policy import (
    ApplyPortfolioPolicy,
    BuildOwnerPortfolioPolicy,
    BuildReplacementDecision,
)
from asymmetric_engine.application.portfolio_state import BuildPortfolioState
from asymmetric_engine.application.product_persistence import (
    ListProductRecords,
    LoadProductRecord,
    ProductAppendResult,
    StoreProductRecord,
)
from asymmetric_engine.application.underwriting import BuildOpportunityState
from asymmetric_engine.infrastructure.clock import SystemClock
from asymmetric_engine.infrastructure.persistence import SQLiteSourceDocumentRepository
from asymmetric_engine.infrastructure.persistence.sqlite_product_store import (
    SQLiteProductRecordRepository,
)
from asymmetric_engine.interfaces.api import AieApiServices, AieProductApi
from asymmetric_engine.interfaces.operator_workspace import OperatorWorkspace
from asymmetric_engine.interfaces.prospective_intake import (
    AieIntakeServices,
    AieProspectiveIntake,
    BuildCausalAnalysisRequest,
    BuildOpportunityStateRequest,
    IntakeResponse,
)

LOCAL_PRODUCT_RUNTIME_VERSION = "local-product-runtime-v1"

type ProspectiveIntakeRequest = BuildCausalAnalysisRequest | BuildOpportunityStateRequest


@dataclass(frozen=True, slots=True)
class LocalProductPaths:
    """Explicit local durable stores used by one prospective runtime."""

    evidence_database: Path
    product_database: Path


@dataclass(frozen=True, slots=True)
class ProspectiveIntakeSubmission:
    """One upstream owner result plus its immutable product-store append result."""

    operation: str
    response: IntakeResponse[object]
    persisted: ProductAppendResult


@dataclass(frozen=True, slots=True)
class LocalProductRuntime:
    """Fully wired local AIE runtime; composition only, never a financial decision owner."""

    paths: LocalProductPaths
    evidence_repository: SQLiteSourceDocumentRepository
    product_repository: SQLiteProductRecordRepository
    intake: AieProspectiveIntake
    api: AieProductApi
    workspace: OperatorWorkspace
    product_store: StoreProductRecord

    def submit_intake(self, request: ProspectiveIntakeRequest) -> ProspectiveIntakeSubmission:
        if isinstance(request, BuildCausalAnalysisRequest):
            response = self.intake.build_causal_analysis(request)
        elif isinstance(request, BuildOpportunityStateRequest):
            response = self.intake.build_opportunity_state(request)
        else:  # pragma: no cover - closed union guard
            raise TypeError(f"unsupported prospective intake request: {type(request).__name__}")
        persisted = self.product_store.execute(response.result)
        return ProspectiveIntakeSubmission(
            operation=request.operation,
            response=response,
            persisted=persisted,
        )


def initialize_local_product_stores(paths: LocalProductPaths) -> None:
    """Explicitly initialize both local stores; normal runtime construction never creates them."""

    SQLiteSourceDocumentRepository(paths.evidence_database, initialize_schema=True)
    SQLiteProductRecordRepository(paths.product_database, initialize_schema=True)


def build_local_product_runtime(paths: LocalProductPaths) -> LocalProductRuntime:
    """Wire accepted owners over existing local stores without adding analytical defaults."""

    evidence_repository = SQLiteSourceDocumentRepository(
        paths.evidence_database,
        initialize_schema=False,
    )
    product_repository = SQLiteProductRecordRepository(
        paths.product_database,
        initialize_schema=False,
    )

    portfolio_state = BuildPortfolioState()
    portfolio_exposure = BuildPortfolioExposure(state_builder=portfolio_state)
    opportunity_state = BuildOpportunityState(evidence_repository)
    causal_analysis = BuildCausalAnalysis(evidence_repository)
    marginal_decision = BuildMarginalDecision(
        opportunity_builder=opportunity_state,
        state_builder=portfolio_state,
        exposure_builder=portfolio_exposure,
    )
    position_hold = RecordPositionHold(
        state_builder=portfolio_state,
        exposure_builder=portfolio_exposure,
    )
    owner_policy = BuildOwnerPortfolioPolicy()
    policy_application = ApplyPortfolioPolicy(
        decision_builder=marginal_decision,
        policy_builder=owner_policy,
    )
    replacement = BuildReplacementDecision(
        state_builder=portfolio_state,
        exposure_builder=portfolio_exposure,
        policy_builder=owner_policy,
        opportunity_builder=opportunity_state,
    )
    execution_policy = BuildExecutionPolicy()
    execution = BuildExecutionPlan(
        policy_application=policy_application,
        replacement_builder=replacement,
        execution_policy_builder=execution_policy,
    )
    learning_case = OpenDecisionLearningCase(execution_builder=execution)
    learning_evaluation = BuildDecisionLearningEvaluation()

    api = AieProductApi(
        AieApiServices(
            portfolio_state=portfolio_state,
            portfolio_exposure=portfolio_exposure,
            marginal_decision=marginal_decision,
            position_hold=position_hold,
            owner_policy=owner_policy,
            policy_application=policy_application,
            replacement=replacement,
            execution_policy=execution_policy,
            execution=execution,
            learning_case=learning_case,
            learning_evaluation=learning_evaluation,
        )
    )
    intake = AieProspectiveIntake(
        AieIntakeServices(
            causal_analysis=causal_analysis,
            opportunity_state=opportunity_state,
        )
    )
    product_store = StoreProductRecord(
        repository=product_repository,
        clock=SystemClock(),
    )
    workspace = OperatorWorkspace(
        loader=LoadProductRecord(product_repository),
        lister=ListProductRecords(product_repository),
        api=api,
        store=product_store,
    )
    return LocalProductRuntime(
        paths=paths,
        evidence_repository=evidence_repository,
        product_repository=product_repository,
        intake=intake,
        api=api,
        workspace=workspace,
        product_store=product_store,
    )


__all__ = [
    "LOCAL_PRODUCT_RUNTIME_VERSION",
    "LocalProductPaths",
    "LocalProductRuntime",
    "ProspectiveIntakeRequest",
    "ProspectiveIntakeSubmission",
    "build_local_product_runtime",
    "initialize_local_product_stores",
]
