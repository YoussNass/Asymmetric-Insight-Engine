"""Tests for the Chapter 9A transport-neutral product API boundary."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.execution import BuildExecutionPolicy
from asymmetric_engine.application.learning import (
    BuildDecisionLearningEvaluation,
    OpenDecisionLearningCase,
)
from asymmetric_engine.application.marginal_decision import RecordPositionHold
from asymmetric_engine.application.portfolio_policy import BuildOwnerPortfolioPolicy
from asymmetric_engine.application.portfolio_state import PortfolioStateIntegrityError
from asymmetric_engine.domain.execution import ExecutionPolicyInput
from asymmetric_engine.domain.portfolio import (
    DecisionConfidence,
    DecisionConfidenceLevel,
    OwnerPortfolioPolicyInput,
    PortfolioState,
    PositionReviewInput,
)
from asymmetric_engine.interfaces.api import (
    API_CONTRACT_VERSION,
    AieApiServices,
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
    ExecutionContext,
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


def _api(context: ExecutionContext) -> AieProductApi:
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
            learning_case=OpenDecisionLearningCase(execution_builder=context.execution_builder),
            learning_evaluation=BuildDecisionLearningEvaluation(),
        )
    )


def test_portfolio_state_and_exposure_api_match_direct_application_and_round_trip_json() -> None:
    context = make_execution_context()
    api = _api(context)
    draft = make_portfolio_draft()

    request = BuildPortfolioStateRequest(draft=draft)
    request_round_trip = BuildPortfolioStateRequest.model_validate(request.model_dump(mode="json"))
    assert request_round_trip == request
    assert request.contract_version == API_CONTRACT_VERSION

    response = api.build_portfolio_state(request)
    direct_state = context.decision_context.state_builder.execute(draft)
    assert response.result == direct_state
    assert response.operation == "build_portfolio_state"

    response_round_trip = ApiResponse[PortfolioState].model_validate(response.model_dump(mode="json"))
    assert response_round_trip == response

    exposure_input = make_exposure_input()
    exposure_response = api.build_portfolio_exposure(
        BuildPortfolioExposureRequest(
            portfolio_state=response.result,
            exposure_input=exposure_input,
        )
    )
    direct_exposure = context.decision_context.exposure_builder.execute(
        response.result,
        exposure_input,
    )
    assert exposure_response.result == direct_exposure


def test_marginal_policy_hold_replacement_and_execution_api_match_direct_application() -> None:
    context = make_execution_context()
    api = _api(context)
    decision = context.decision_context

    marginal_request = BuildMarginalDecisionRequest(
        portfolio_state=decision.portfolio_state,
        opportunity_state=decision.opportunity_state,
        current_exposure=decision.current_exposure,
        alternative_exposures=decision.alternative_exposures,
        decision_input=decision.decision_input,
    )
    marginal_response = api.build_marginal_decision(marginal_request)
    assert marginal_response.result == MarginalDecisionPackage.from_application(
        context.marginal_result
    )

    hold_input = PositionReviewInput(
        knowledge_boundary=decision.portfolio_state.knowledge_boundary,
        position_id=EXISTING_POSITION_ID,
        rationale=("Retain the existing position without allocating incremental capital.",),
        main_risks_and_unknowns=("The standalone position review remains uncalibrated.",),
        change_conditions=("Re-underwrite the position if the standalone thesis changes.",),
        confidence=DecisionConfidence(
            level=DecisionConfidenceLevel.CONDITIONAL,
            rationale="The HOLD record is explicit but does not create a new-capital instruction.",
        ),
    )
    hold_response = api.record_position_hold(
        RecordPositionHoldRequest(
            portfolio_state=decision.portfolio_state,
            current_exposure=decision.current_exposure,
            review_input=hold_input,
        )
    )
    direct_hold = RecordPositionHold(
        state_builder=decision.state_builder,
        exposure_builder=decision.exposure_builder,
    ).execute(
        portfolio_state=decision.portfolio_state,
        current_exposure=decision.current_exposure,
        review_input=hold_input,
    )
    assert hold_response.result == direct_hold

    owner_policy_input = OwnerPortfolioPolicyInput(
        knowledge_boundary=decision.portfolio_state.knowledge_boundary,
        rationale=("Use explicit owner gates without automatic sizing.",),
    )
    policy_response = api.build_owner_portfolio_policy(
        BuildOwnerPortfolioPolicyRequest(policy_input=owner_policy_input)
    )
    assert policy_response.result == context.owner_policy

    applied_response = api.apply_portfolio_policy(
        ApplyPortfolioPolicyRequest(
            portfolio_state=decision.portfolio_state,
            opportunity_state=decision.opportunity_state,
            current_exposure=decision.current_exposure,
            alternative_exposures=decision.alternative_exposures,
            marginal_result=marginal_response.result,
            policy=policy_response.result,
        )
    )
    assert applied_response.result == context.policy_decision

    replacement_response = api.build_replacement_decision(
        BuildReplacementDecisionRequest(
            portfolio_state=decision.portfolio_state,
            current_exposure=decision.current_exposure,
            policy=policy_response.result,
            decision_input=make_replacement_input(decision),
        )
    )
    assert replacement_response.result == context.replacement_decision

    policy_input = ExecutionPolicyInput(
        knowledge_boundary=context.execution_boundary,
        max_quote_age_seconds=60,
        max_spread_bps=Decimal("50"),
        rationale=("Use explicit operational limits without a market-timing or regime score.",),
    )
    execution_policy_response = api.build_execution_policy(
        BuildExecutionPolicyRequest(policy_input=policy_input)
    )
    assert execution_policy_response.result == make_execution_policy(context)

    allocation_input = make_allocation_execution_input(context)
    allocation_response = api.build_execution_from_policy_allocation(
        BuildExecutionFromPolicyAllocationRequest(
            portfolio_state=decision.portfolio_state,
            opportunity_state=decision.opportunity_state,
            current_exposure=decision.current_exposure,
            alternative_exposures=decision.alternative_exposures,
            marginal_result=marginal_response.result,
            owner_policy=context.owner_policy,
            policy_decision=context.policy_decision,
            execution_policy=execution_policy_response.result,
            execution_input=allocation_input,
        )
    )
    direct_allocation = context.execution_builder.from_policy_allocation(
        portfolio_state=decision.portfolio_state,
        opportunity_state=decision.opportunity_state,
        current_exposure=decision.current_exposure,
        alternative_exposures=decision.alternative_exposures,
        marginal_result=context.marginal_result,
        owner_policy=context.owner_policy,
        policy_decision=context.policy_decision,
        execution_policy=execution_policy_response.result,
        execution_input=allocation_input,
    )
    assert allocation_response.result == direct_allocation

    replacement_input = make_replacement_execution_input(context)
    replacement_execution_response = api.build_execution_from_replacement(
        BuildExecutionFromReplacementRequest(
            portfolio_state=decision.portfolio_state,
            current_exposure=decision.current_exposure,
            owner_policy=context.owner_policy,
            replacement_decision=context.replacement_decision,
            execution_policy=execution_policy_response.result,
            execution_input=replacement_input,
        )
    )
    direct_replacement = context.execution_builder.from_replacement(
        portfolio_state=decision.portfolio_state,
        current_exposure=decision.current_exposure,
        owner_policy=context.owner_policy,
        replacement_decision=context.replacement_decision,
        execution_policy=execution_policy_response.result,
        execution_input=replacement_input,
    )
    assert replacement_execution_response.result == direct_replacement


def test_learning_api_matches_direct_case_and_evaluation_for_allocation_and_replacement() -> None:
    context = make_execution_context()
    api = _api(context)
    decision = context.decision_context
    execution_policy = make_execution_policy(context)

    allocation_plan = context.execution_builder.from_policy_allocation(
        portfolio_state=decision.portfolio_state,
        opportunity_state=decision.opportunity_state,
        current_exposure=decision.current_exposure,
        alternative_exposures=decision.alternative_exposures,
        marginal_result=context.marginal_result,
        owner_policy=context.owner_policy,
        policy_decision=context.policy_decision,
        execution_policy=execution_policy,
        execution_input=make_allocation_execution_input(context),
    )
    marginal_package = MarginalDecisionPackage.from_application(context.marginal_result)
    allocation_case_response = api.open_learning_case_from_policy_allocation(
        OpenLearningCaseFromPolicyAllocationRequest(
            portfolio_state=decision.portfolio_state,
            opportunity_state=decision.opportunity_state,
            current_exposure=decision.current_exposure,
            alternative_exposures=decision.alternative_exposures,
            marginal_result=marginal_package,
            owner_policy=context.owner_policy,
            policy_decision=context.policy_decision,
            execution_policy=execution_policy,
            execution_plan=allocation_plan,
        )
    )
    direct_opener = OpenDecisionLearningCase(execution_builder=context.execution_builder)
    direct_allocation_case = direct_opener.from_policy_allocation(
        portfolio_state=decision.portfolio_state,
        opportunity_state=decision.opportunity_state,
        current_exposure=decision.current_exposure,
        alternative_exposures=decision.alternative_exposures,
        marginal_result=context.marginal_result,
        owner_policy=context.owner_policy,
        policy_decision=context.policy_decision,
        execution_policy=execution_policy,
        execution_plan=allocation_plan,
    )
    assert allocation_case_response.result == direct_allocation_case

    allocation_evaluation_input = make_allocation_evaluation_input(allocation_case_response.result)
    allocation_evaluation_response = api.build_learning_evaluation(
        BuildLearningEvaluationRequest(
            case=allocation_case_response.result,
            evaluation_input=allocation_evaluation_input,
        )
    )
    direct_evaluation = BuildDecisionLearningEvaluation().execute(
        case=direct_allocation_case,
        evaluation_input=allocation_evaluation_input,
    )
    assert allocation_evaluation_response.result == direct_evaluation

    replacement_plan = context.execution_builder.from_replacement(
        portfolio_state=decision.portfolio_state,
        current_exposure=decision.current_exposure,
        owner_policy=context.owner_policy,
        replacement_decision=context.replacement_decision,
        execution_policy=execution_policy,
        execution_input=make_replacement_execution_input(context),
    )
    replacement_horizon = context.execution_boundary.as_of.date() + timedelta(days=365)
    replacement_case_response = api.open_learning_case_from_replacement(
        OpenLearningCaseFromReplacementRequest(
            portfolio_state=decision.portfolio_state,
            current_exposure=decision.current_exposure,
            owner_policy=context.owner_policy,
            replacement_decision=context.replacement_decision,
            execution_policy=execution_policy,
            execution_plan=replacement_plan,
            evaluation_horizon_date=replacement_horizon,
        )
    )
    direct_replacement_case = direct_opener.from_replacement(
        portfolio_state=decision.portfolio_state,
        current_exposure=decision.current_exposure,
        owner_policy=context.owner_policy,
        replacement_decision=context.replacement_decision,
        execution_policy=execution_policy,
        execution_plan=replacement_plan,
        evaluation_horizon_date=replacement_horizon,
    )
    assert replacement_case_response.result == direct_replacement_case

    replacement_evaluation_input = make_replacement_evaluation_input(
        replacement_case_response.result
    )
    replacement_evaluation_response = api.build_learning_evaluation(
        BuildLearningEvaluationRequest(
            case=replacement_case_response.result,
            evaluation_input=replacement_evaluation_input,
        )
    )
    direct_replacement_evaluation = BuildDecisionLearningEvaluation().execute(
        case=direct_replacement_case,
        evaluation_input=replacement_evaluation_input,
    )
    assert replacement_evaluation_response.result == direct_replacement_evaluation


def test_api_does_not_hide_canonical_replay_failure_for_tampered_state() -> None:
    context = make_execution_context()
    api = _api(context)
    state = context.decision_context.portfolio_state.model_copy(
        update={"input_fingerprint": "0" * 64}
    )

    with pytest.raises(PortfolioStateIntegrityError):
        api.build_portfolio_exposure(
            BuildPortfolioExposureRequest(
                portfolio_state=state,
                exposure_input=make_exposure_input(),
            )
        )


def test_api_request_models_reject_unknown_transport_fields() -> None:
    draft = make_portfolio_draft()
    payload = BuildPortfolioStateRequest(draft=draft).model_dump(mode="python")
    payload["client_calculated_score"] = 99

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BuildPortfolioStateRequest.model_validate(payload)
