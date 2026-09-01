"""Typed transport-neutral product API over canonical AIE application services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from asymmetric_engine.application.execution import BuildExecutionPlan, BuildExecutionPolicy
from asymmetric_engine.application.learning import (
    BuildDecisionLearningEvaluation,
    OpenDecisionLearningCase,
)
from asymmetric_engine.application.marginal_decision import (
    BuildMarginalDecision,
    MarginalDecisionResult,
    RecordPositionHold,
)
from asymmetric_engine.application.portfolio_exposure import BuildPortfolioExposure
from asymmetric_engine.application.portfolio_policy import (
    ApplyPortfolioPolicy,
    BuildOwnerPortfolioPolicy,
    BuildReplacementDecision,
)
from asymmetric_engine.application.portfolio_state import BuildPortfolioState
from asymmetric_engine.domain.execution import (
    ExecutionPlan,
    ExecutionPlanInput,
    ExecutionPolicy,
    ExecutionPolicyInput,
)
from asymmetric_engine.domain.learning import (
    DecisionLearningCase,
    DecisionLearningEvaluation,
    LearningEvaluationInput,
)
from asymmetric_engine.domain.opportunity import OpportunityState
from asymmetric_engine.domain.portfolio import (
    MarginalDecision,
    MarginalDecisionInput,
    OwnerPortfolioPolicy,
    OwnerPortfolioPolicyInput,
    PolicyConstrainedMarginalDecision,
    PortfolioExposure,
    PortfolioExposureInput,
    PortfolioFit,
    PortfolioState,
    PortfolioStateDraft,
    PositionReview,
    PositionReviewInput,
    ReplacementDecision,
    ReplacementDecisionInput,
)

API_CONTRACT_VERSION: Literal["aie-api-v1"] = "aie-api-v1"


class _ApiModel(BaseModel):
    """Strict immutable base for product-boundary records."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: Literal["aie-api-v1"] = API_CONTRACT_VERSION


class ApiResponse[T](_ApiModel):
    """Versioned JSON-safe response carrying one canonical application result."""

    operation: str
    result: T


class MarginalDecisionPackage(_ApiModel):
    """Thin Pydantic projection of the application-only MarginalDecisionResult dataclass."""

    fits: tuple[PortfolioFit, ...]
    decision: MarginalDecision

    @classmethod
    def from_application(cls, result: MarginalDecisionResult) -> MarginalDecisionPackage:
        return cls(fits=result.fits, decision=result.decision)

    def to_application(self) -> MarginalDecisionResult:
        return MarginalDecisionResult(fits=self.fits, decision=self.decision)


class BuildPortfolioStateRequest(_ApiModel):
    operation: Literal["build_portfolio_state"] = "build_portfolio_state"
    draft: PortfolioStateDraft


class BuildPortfolioExposureRequest(_ApiModel):
    operation: Literal["build_portfolio_exposure"] = "build_portfolio_exposure"
    portfolio_state: PortfolioState
    exposure_input: PortfolioExposureInput


class BuildMarginalDecisionRequest(_ApiModel):
    operation: Literal["build_marginal_decision"] = "build_marginal_decision"
    portfolio_state: PortfolioState
    opportunity_state: OpportunityState
    current_exposure: PortfolioExposure
    alternative_exposures: tuple[PortfolioExposure, ...]
    decision_input: MarginalDecisionInput


class RecordPositionHoldRequest(_ApiModel):
    operation: Literal["record_position_hold"] = "record_position_hold"
    portfolio_state: PortfolioState
    current_exposure: PortfolioExposure
    review_input: PositionReviewInput


class BuildOwnerPortfolioPolicyRequest(_ApiModel):
    operation: Literal["build_owner_portfolio_policy"] = "build_owner_portfolio_policy"
    policy_input: OwnerPortfolioPolicyInput


class ApplyPortfolioPolicyRequest(_ApiModel):
    operation: Literal["apply_portfolio_policy"] = "apply_portfolio_policy"
    portfolio_state: PortfolioState
    opportunity_state: OpportunityState
    current_exposure: PortfolioExposure
    alternative_exposures: tuple[PortfolioExposure, ...]
    marginal_result: MarginalDecisionPackage
    policy: OwnerPortfolioPolicy


class BuildReplacementDecisionRequest(_ApiModel):
    operation: Literal["build_replacement_decision"] = "build_replacement_decision"
    portfolio_state: PortfolioState
    current_exposure: PortfolioExposure
    policy: OwnerPortfolioPolicy
    decision_input: ReplacementDecisionInput
    opportunity_state: OpportunityState | None = None


class BuildExecutionPolicyRequest(_ApiModel):
    operation: Literal["build_execution_policy"] = "build_execution_policy"
    policy_input: ExecutionPolicyInput


class BuildExecutionFromPolicyAllocationRequest(_ApiModel):
    operation: Literal["build_execution_from_policy_allocation"] = (
        "build_execution_from_policy_allocation"
    )
    portfolio_state: PortfolioState
    opportunity_state: OpportunityState
    current_exposure: PortfolioExposure
    alternative_exposures: tuple[PortfolioExposure, ...]
    marginal_result: MarginalDecisionPackage
    owner_policy: OwnerPortfolioPolicy
    policy_decision: PolicyConstrainedMarginalDecision
    execution_policy: ExecutionPolicy
    execution_input: ExecutionPlanInput


class BuildExecutionFromReplacementRequest(_ApiModel):
    operation: Literal["build_execution_from_replacement"] = "build_execution_from_replacement"
    portfolio_state: PortfolioState
    current_exposure: PortfolioExposure
    owner_policy: OwnerPortfolioPolicy
    replacement_decision: ReplacementDecision
    execution_policy: ExecutionPolicy
    execution_input: ExecutionPlanInput
    opportunity_state: OpportunityState | None = None


class OpenLearningCaseFromPolicyAllocationRequest(_ApiModel):
    operation: Literal["open_learning_case_from_policy_allocation"] = (
        "open_learning_case_from_policy_allocation"
    )
    portfolio_state: PortfolioState
    opportunity_state: OpportunityState
    current_exposure: PortfolioExposure
    alternative_exposures: tuple[PortfolioExposure, ...]
    marginal_result: MarginalDecisionPackage
    owner_policy: OwnerPortfolioPolicy
    policy_decision: PolicyConstrainedMarginalDecision
    execution_policy: ExecutionPolicy
    execution_plan: ExecutionPlan
    evaluation_horizon_date: date | None = None


class OpenLearningCaseFromReplacementRequest(_ApiModel):
    operation: Literal["open_learning_case_from_replacement"] = (
        "open_learning_case_from_replacement"
    )
    portfolio_state: PortfolioState
    current_exposure: PortfolioExposure
    owner_policy: OwnerPortfolioPolicy
    replacement_decision: ReplacementDecision
    execution_policy: ExecutionPolicy
    execution_plan: ExecutionPlan
    evaluation_horizon_date: date | None = None
    opportunity_state: OpportunityState | None = None


class BuildLearningEvaluationRequest(_ApiModel):
    operation: Literal["build_learning_evaluation"] = "build_learning_evaluation"
    case: DecisionLearningCase
    evaluation_input: LearningEvaluationInput


@dataclass(frozen=True)
class AieApiServices:
    """Injected canonical application services used by the transport-neutral API."""

    portfolio_state: BuildPortfolioState
    portfolio_exposure: BuildPortfolioExposure
    marginal_decision: BuildMarginalDecision
    position_hold: RecordPositionHold
    owner_policy: BuildOwnerPortfolioPolicy
    policy_application: ApplyPortfolioPolicy
    replacement: BuildReplacementDecision
    execution_policy: BuildExecutionPolicy
    execution: BuildExecutionPlan
    learning_case: OpenDecisionLearningCase
    learning_evaluation: BuildDecisionLearningEvaluation


class AieProductApi:
    """Delegate typed product requests to canonical application use cases without recalculation."""

    def __init__(self, services: AieApiServices) -> None:
        self._services = services

    def build_portfolio_state(
        self,
        request: BuildPortfolioStateRequest,
    ) -> ApiResponse[PortfolioState]:
        result = self._services.portfolio_state.execute(request.draft)
        return ApiResponse[PortfolioState](operation=request.operation, result=result)

    def build_portfolio_exposure(
        self,
        request: BuildPortfolioExposureRequest,
    ) -> ApiResponse[PortfolioExposure]:
        result = self._services.portfolio_exposure.execute(
            request.portfolio_state,
            request.exposure_input,
        )
        return ApiResponse[PortfolioExposure](operation=request.operation, result=result)

    def build_marginal_decision(
        self,
        request: BuildMarginalDecisionRequest,
    ) -> ApiResponse[MarginalDecisionPackage]:
        result = self._services.marginal_decision.execute(
            portfolio_state=request.portfolio_state,
            opportunity_state=request.opportunity_state,
            current_exposure=request.current_exposure,
            alternative_exposures=request.alternative_exposures,
            decision_input=request.decision_input,
        )
        return ApiResponse[MarginalDecisionPackage](
            operation=request.operation,
            result=MarginalDecisionPackage.from_application(result),
        )

    def record_position_hold(
        self,
        request: RecordPositionHoldRequest,
    ) -> ApiResponse[PositionReview]:
        result = self._services.position_hold.execute(
            portfolio_state=request.portfolio_state,
            current_exposure=request.current_exposure,
            review_input=request.review_input,
        )
        return ApiResponse[PositionReview](operation=request.operation, result=result)

    def build_owner_portfolio_policy(
        self,
        request: BuildOwnerPortfolioPolicyRequest,
    ) -> ApiResponse[OwnerPortfolioPolicy]:
        result = self._services.owner_policy.execute(request.policy_input)
        return ApiResponse[OwnerPortfolioPolicy](operation=request.operation, result=result)

    def apply_portfolio_policy(
        self,
        request: ApplyPortfolioPolicyRequest,
    ) -> ApiResponse[PolicyConstrainedMarginalDecision]:
        result = self._services.policy_application.execute(
            portfolio_state=request.portfolio_state,
            opportunity_state=request.opportunity_state,
            current_exposure=request.current_exposure,
            alternative_exposures=request.alternative_exposures,
            marginal_result=request.marginal_result.to_application(),
            policy=request.policy,
        )
        return ApiResponse[PolicyConstrainedMarginalDecision](
            operation=request.operation,
            result=result,
        )

    def build_replacement_decision(
        self,
        request: BuildReplacementDecisionRequest,
    ) -> ApiResponse[ReplacementDecision]:
        result = self._services.replacement.execute(
            portfolio_state=request.portfolio_state,
            current_exposure=request.current_exposure,
            policy=request.policy,
            decision_input=request.decision_input,
            opportunity_state=request.opportunity_state,
        )
        return ApiResponse[ReplacementDecision](operation=request.operation, result=result)

    def build_execution_policy(
        self,
        request: BuildExecutionPolicyRequest,
    ) -> ApiResponse[ExecutionPolicy]:
        result = self._services.execution_policy.execute(request.policy_input)
        return ApiResponse[ExecutionPolicy](operation=request.operation, result=result)

    def build_execution_from_policy_allocation(
        self,
        request: BuildExecutionFromPolicyAllocationRequest,
    ) -> ApiResponse[ExecutionPlan]:
        result = self._services.execution.from_policy_allocation(
            portfolio_state=request.portfolio_state,
            opportunity_state=request.opportunity_state,
            current_exposure=request.current_exposure,
            alternative_exposures=request.alternative_exposures,
            marginal_result=request.marginal_result.to_application(),
            owner_policy=request.owner_policy,
            policy_decision=request.policy_decision,
            execution_policy=request.execution_policy,
            execution_input=request.execution_input,
        )
        return ApiResponse[ExecutionPlan](operation=request.operation, result=result)

    def build_execution_from_replacement(
        self,
        request: BuildExecutionFromReplacementRequest,
    ) -> ApiResponse[ExecutionPlan]:
        result = self._services.execution.from_replacement(
            portfolio_state=request.portfolio_state,
            current_exposure=request.current_exposure,
            owner_policy=request.owner_policy,
            replacement_decision=request.replacement_decision,
            execution_policy=request.execution_policy,
            execution_input=request.execution_input,
            opportunity_state=request.opportunity_state,
        )
        return ApiResponse[ExecutionPlan](operation=request.operation, result=result)

    def open_learning_case_from_policy_allocation(
        self,
        request: OpenLearningCaseFromPolicyAllocationRequest,
    ) -> ApiResponse[DecisionLearningCase]:
        result = self._services.learning_case.from_policy_allocation(
            portfolio_state=request.portfolio_state,
            opportunity_state=request.opportunity_state,
            current_exposure=request.current_exposure,
            alternative_exposures=request.alternative_exposures,
            marginal_result=request.marginal_result.to_application(),
            owner_policy=request.owner_policy,
            policy_decision=request.policy_decision,
            execution_policy=request.execution_policy,
            execution_plan=request.execution_plan,
            evaluation_horizon_date=request.evaluation_horizon_date,
        )
        return ApiResponse[DecisionLearningCase](operation=request.operation, result=result)

    def open_learning_case_from_replacement(
        self,
        request: OpenLearningCaseFromReplacementRequest,
    ) -> ApiResponse[DecisionLearningCase]:
        result = self._services.learning_case.from_replacement(
            portfolio_state=request.portfolio_state,
            current_exposure=request.current_exposure,
            owner_policy=request.owner_policy,
            replacement_decision=request.replacement_decision,
            execution_policy=request.execution_policy,
            execution_plan=request.execution_plan,
            evaluation_horizon_date=request.evaluation_horizon_date,
            opportunity_state=request.opportunity_state,
        )
        return ApiResponse[DecisionLearningCase](operation=request.operation, result=result)

    def build_learning_evaluation(
        self,
        request: BuildLearningEvaluationRequest,
    ) -> ApiResponse[DecisionLearningEvaluation]:
        result = self._services.learning_evaluation.execute(
            case=request.case,
            evaluation_input=request.evaluation_input,
        )
        return ApiResponse[DecisionLearningEvaluation](operation=request.operation, result=result)


__all__ = [
    "API_CONTRACT_VERSION",
    "AieApiServices",
    "AieProductApi",
    "ApiResponse",
    "ApplyPortfolioPolicyRequest",
    "BuildExecutionFromPolicyAllocationRequest",
    "BuildExecutionFromReplacementRequest",
    "BuildExecutionPolicyRequest",
    "BuildLearningEvaluationRequest",
    "BuildMarginalDecisionRequest",
    "BuildOwnerPortfolioPolicyRequest",
    "BuildPortfolioExposureRequest",
    "BuildPortfolioStateRequest",
    "BuildReplacementDecisionRequest",
    "MarginalDecisionPackage",
    "OpenLearningCaseFromPolicyAllocationRequest",
    "OpenLearningCaseFromReplacementRequest",
    "RecordPositionHoldRequest",
]
