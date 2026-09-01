"""Exhaustive JSON round-trip checks for the public Chapter 9A API contract."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from pydantic import BaseModel

from asymmetric_engine.domain.execution import ExecutionPlan, ExecutionPolicy, ExecutionPolicyInput
from asymmetric_engine.domain.learning import DecisionLearningCase, DecisionLearningEvaluation
from asymmetric_engine.domain.portfolio import (
    DecisionConfidence,
    DecisionConfidenceLevel,
    OwnerPortfolioPolicy,
    OwnerPortfolioPolicyInput,
    PolicyConstrainedMarginalDecision,
    PortfolioExposure,
    PortfolioState,
    PositionReview,
    PositionReviewInput,
    ReplacementDecision,
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
from tests.decision_factories import EXISTING_POSITION_ID
from tests.execution_factories import (
    make_allocation_execution_input,
    make_execution_context,
    make_execution_policy,
    make_replacement_execution_input,
    make_replacement_input,
)
from tests.exposure_factories import make_exposure_input
from tests.learning_factories import (
    make_allocation_evaluation_input,
    make_replacement_evaluation_input,
)
from tests.portfolio_factories import make_portfolio_draft
from tests.unit.test_api import _api


def _assert_round_trip[T: BaseModel](model: T, model_type: type[T] | None = None) -> None:
    validator = model_type or type(model)
    rebuilt = validator.model_validate(model.model_dump(mode="json"))
    assert rebuilt == model


def test_every_public_request_and_response_round_trips_through_json_mode() -> None:
    context = make_execution_context()
    api: AieProductApi = _api(context)
    decision = context.decision_context

    state_request = BuildPortfolioStateRequest(draft=make_portfolio_draft())
    _assert_round_trip(state_request)
    state_response = api.build_portfolio_state(state_request)
    _assert_round_trip(state_response, ApiResponse[PortfolioState])

    exposure_request = BuildPortfolioExposureRequest(
        portfolio_state=state_response.result,
        exposure_input=make_exposure_input(),
    )
    _assert_round_trip(exposure_request)
    exposure_response = api.build_portfolio_exposure(exposure_request)
    _assert_round_trip(exposure_response, ApiResponse[PortfolioExposure])

    marginal_request = BuildMarginalDecisionRequest(
        portfolio_state=decision.portfolio_state,
        opportunity_state=decision.opportunity_state,
        current_exposure=decision.current_exposure,
        alternative_exposures=decision.alternative_exposures,
        decision_input=decision.decision_input,
    )
    _assert_round_trip(marginal_request)
    marginal_response = api.build_marginal_decision(marginal_request)
    _assert_round_trip(marginal_response, ApiResponse[MarginalDecisionPackage])

    hold_input = PositionReviewInput(
        knowledge_boundary=decision.portfolio_state.knowledge_boundary,
        position_id=EXISTING_POSITION_ID,
        rationale=("Retain the position without allocating incremental capital.",),
        main_risks_and_unknowns=("The position review remains uncalibrated.",),
        change_conditions=("Re-underwrite if the standalone thesis changes.",),
        confidence=DecisionConfidence(
            level=DecisionConfidenceLevel.CONDITIONAL,
            rationale="The review has no new-capital authority.",
        ),
    )
    hold_request = RecordPositionHoldRequest(
        portfolio_state=decision.portfolio_state,
        current_exposure=decision.current_exposure,
        review_input=hold_input,
    )
    _assert_round_trip(hold_request)
    hold_response = api.record_position_hold(hold_request)
    _assert_round_trip(hold_response, ApiResponse[PositionReview])

    owner_policy_request = BuildOwnerPortfolioPolicyRequest(
        policy_input=OwnerPortfolioPolicyInput(
            knowledge_boundary=decision.portfolio_state.knowledge_boundary,
            rationale=("Use explicit owner gates without automatic sizing.",),
        )
    )
    _assert_round_trip(owner_policy_request)
    owner_policy_response = api.build_owner_portfolio_policy(owner_policy_request)
    _assert_round_trip(owner_policy_response, ApiResponse[OwnerPortfolioPolicy])

    apply_request = ApplyPortfolioPolicyRequest(
        portfolio_state=decision.portfolio_state,
        opportunity_state=decision.opportunity_state,
        current_exposure=decision.current_exposure,
        alternative_exposures=decision.alternative_exposures,
        marginal_result=marginal_response.result,
        policy=owner_policy_response.result,
    )
    _assert_round_trip(apply_request)
    apply_response = api.apply_portfolio_policy(apply_request)
    _assert_round_trip(apply_response, ApiResponse[PolicyConstrainedMarginalDecision])

    replacement_request = BuildReplacementDecisionRequest(
        portfolio_state=decision.portfolio_state,
        current_exposure=decision.current_exposure,
        policy=owner_policy_response.result,
        decision_input=make_replacement_input(decision),
    )
    _assert_round_trip(replacement_request)
    replacement_response = api.build_replacement_decision(replacement_request)
    _assert_round_trip(replacement_response, ApiResponse[ReplacementDecision])

    execution_policy_request = BuildExecutionPolicyRequest(
        policy_input=ExecutionPolicyInput(
            knowledge_boundary=context.execution_boundary,
            max_quote_age_seconds=60,
            max_spread_bps=Decimal("50"),
            rationale=("Use explicit operational limits without a market-timing or regime score.",),
        )
    )
    _assert_round_trip(execution_policy_request)
    execution_policy_response = api.build_execution_policy(execution_policy_request)
    _assert_round_trip(execution_policy_response, ApiResponse[ExecutionPolicy])
    assert execution_policy_response.result == make_execution_policy(context)

    allocation_execution_request = BuildExecutionFromPolicyAllocationRequest(
        portfolio_state=decision.portfolio_state,
        opportunity_state=decision.opportunity_state,
        current_exposure=decision.current_exposure,
        alternative_exposures=decision.alternative_exposures,
        marginal_result=marginal_response.result,
        owner_policy=owner_policy_response.result,
        policy_decision=apply_response.result,
        execution_policy=execution_policy_response.result,
        execution_input=make_allocation_execution_input(context),
    )
    _assert_round_trip(allocation_execution_request)
    allocation_execution_response = api.build_execution_from_policy_allocation(
        allocation_execution_request
    )
    _assert_round_trip(allocation_execution_response, ApiResponse[ExecutionPlan])

    replacement_execution_request = BuildExecutionFromReplacementRequest(
        portfolio_state=decision.portfolio_state,
        current_exposure=decision.current_exposure,
        owner_policy=owner_policy_response.result,
        replacement_decision=replacement_response.result,
        execution_policy=execution_policy_response.result,
        execution_input=make_replacement_execution_input(context),
    )
    _assert_round_trip(replacement_execution_request)
    replacement_execution_response = api.build_execution_from_replacement(
        replacement_execution_request
    )
    _assert_round_trip(replacement_execution_response, ApiResponse[ExecutionPlan])

    allocation_case_request = OpenLearningCaseFromPolicyAllocationRequest(
        portfolio_state=decision.portfolio_state,
        opportunity_state=decision.opportunity_state,
        current_exposure=decision.current_exposure,
        alternative_exposures=decision.alternative_exposures,
        marginal_result=marginal_response.result,
        owner_policy=owner_policy_response.result,
        policy_decision=apply_response.result,
        execution_policy=execution_policy_response.result,
        execution_plan=allocation_execution_response.result,
    )
    _assert_round_trip(allocation_case_request)
    allocation_case_response = api.open_learning_case_from_policy_allocation(
        allocation_case_request
    )
    _assert_round_trip(allocation_case_response, ApiResponse[DecisionLearningCase])

    replacement_horizon = context.execution_boundary.as_of.date() + timedelta(days=365)
    replacement_case_request = OpenLearningCaseFromReplacementRequest(
        portfolio_state=decision.portfolio_state,
        current_exposure=decision.current_exposure,
        owner_policy=owner_policy_response.result,
        replacement_decision=replacement_response.result,
        execution_policy=execution_policy_response.result,
        execution_plan=replacement_execution_response.result,
        evaluation_horizon_date=replacement_horizon,
    )
    _assert_round_trip(replacement_case_request)
    replacement_case_response = api.open_learning_case_from_replacement(replacement_case_request)
    _assert_round_trip(replacement_case_response, ApiResponse[DecisionLearningCase])

    allocation_evaluation_request = BuildLearningEvaluationRequest(
        case=allocation_case_response.result,
        evaluation_input=make_allocation_evaluation_input(allocation_case_response.result),
    )
    _assert_round_trip(allocation_evaluation_request)
    allocation_evaluation_response = api.build_learning_evaluation(allocation_evaluation_request)
    _assert_round_trip(
        allocation_evaluation_response,
        ApiResponse[DecisionLearningEvaluation],
    )

    replacement_evaluation_request = BuildLearningEvaluationRequest(
        case=replacement_case_response.result,
        evaluation_input=make_replacement_evaluation_input(replacement_case_response.result),
    )
    _assert_round_trip(replacement_evaluation_request)
    replacement_evaluation_response = api.build_learning_evaluation(replacement_evaluation_request)
    _assert_round_trip(
        replacement_evaluation_response,
        ApiResponse[DecisionLearningEvaluation],
    )
