"""Unit tests for Chapter 6C2 replacement and capital-flow policies."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.portfolio_policy import (
    ApplyPortfolioPolicy,
    BuildOwnerPortfolioPolicy,
    BuildReplacementDecision,
    PortfolioPolicyIntegrityError,
)
from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.portfolio import (
    CANDIDATE_ALTERNATIVE_ID,
    EXISTING_HOLDING_ALTERNATIVE_ID,
    INVESTMENT_CASH_ALTERNATIVE_ID,
    ComponentPreference,
    DecisionConfidence,
    DecisionConfidenceLevel,
    FrictionCostEstimate,
    FrictionCostKind,
    FrictionEstimateStatus,
    LiquidityAssessment,
    LiquidityStatus,
    NewCapitalEligibility,
    OwnerPortfolioPolicy,
    OwnerPortfolioPolicyInput,
    PairwiseCapitalComparison,
    PairwiseConclusion,
    PolicyDecisionOutcome,
    PositionCapitalPolicy,
    PositionCapitalStatus,
    RatioConstraint,
    RatioConstraintKind,
    ReplacementConstraintObservation,
    ReplacementDecisionBasis,
    ReplacementDecisionInput,
    ReplacementFriction,
    ReplacementOutcome,
    ReplacementPreference,
    ReplacementTarget,
    ReplacementTargetKind,
    RunnerCapitalBasis,
    TradeOffComponent,
    TradeOffDimension,
)
from asymmetric_engine.interfaces.decision_card import (
    DecisionCardAction,
    DecisionCardExecutionStatus,
    ProjectDecisionCard,
)
from tests.decision_factories import (
    EXISTING_POSITION_ID,
    DecisionContext,
    make_decision_context,
)

CORE_INSTRUMENT_ID = "instrument:core-equity-etf"
REPLACEMENT_TARGET_ID = "replacement:core-etf"


def _marginal_result(context: DecisionContext):
    return context.decision_builder.execute(
        portfolio_state=context.portfolio_state,
        opportunity_state=context.opportunity_state,
        current_exposure=context.current_exposure,
        alternative_exposures=context.alternative_exposures,
        decision_input=context.decision_input,
    )


def _policy(
    context: DecisionContext,
    *,
    max_capital: str | None = None,
    position_policies: tuple[PositionCapitalPolicy, ...] = (),
    ratio_constraints: tuple[RatioConstraint, ...] = (),
) -> OwnerPortfolioPolicy:
    return BuildOwnerPortfolioPolicy.execute(
        OwnerPortfolioPolicyInput(
            knowledge_boundary=context.portfolio_state.knowledge_boundary,
            max_capital_unit=(
                MonetaryAmount(amount=Decimal(max_capital), currency="USD")
                if max_capital is not None
                else None
            ),
            position_policies=position_policies,
            ratio_constraints=ratio_constraints,
            rationale=(
                "Owner constraints are explicit gates and never an automatic sizing formula.",
            ),
            assumptions=("The policy applies only at the declared T0 boundary.",),
        )
    )


def _apply_policy(context: DecisionContext, policy: OwnerPortfolioPolicy):
    result = _marginal_result(context)
    builder = ApplyPortfolioPolicy(decision_builder=context.decision_builder)
    return result, builder.execute(
        portfolio_state=context.portfolio_state,
        opportunity_state=context.opportunity_state,
        current_exposure=context.current_exposure,
        alternative_exposures=context.alternative_exposures,
        marginal_result=result,
        policy=policy,
    )


def _comparison(*, target_wins: bool = True) -> PairwiseCapitalComparison:
    preference = ComponentPreference.SECOND if target_wins else ComponentPreference.FIRST
    conclusion = PairwiseConclusion.SECOND if target_wins else PairwiseConclusion.FIRST
    return PairwiseCapitalComparison(
        first_alternative_id=EXISTING_POSITION_ID,
        second_alternative_id=REPLACEMENT_TARGET_ID,
        components=(
            TradeOffComponent(
                dimension=TradeOffDimension.STANDALONE_CASE,
                preference=preference,
                rationale="The explicit target is preferred on the standalone case.",
            ),
            TradeOffComponent(
                dimension=TradeOffDimension.PERMANENT_LOSS,
                preference=preference,
                rationale="Permanent-loss trade-off is explicitly judged for this proposal.",
            ),
            TradeOffComponent(
                dimension=TradeOffDimension.PORTFOLIO_EFFECT,
                preference=preference,
                rationale=(
                    "Portfolio effect is explicit and remains separate from other dimensions."
                ),
            ),
            TradeOffComponent(
                dimension=TradeOffDimension.UNCERTAINTY,
                preference=ComponentPreference.BALANCED,
                rationale="No uncertainty advantage is claimed in this deterministic fixture.",
            ),
        ),
        conclusion=conclusion,
        rationale="The qualitative pair conclusion is visible and carries no hidden score.",
    )


def _friction(*, unknown_tax: bool = False) -> ReplacementFriction:
    tax = (
        FrictionCostEstimate(
            kind=FrictionCostKind.TAX,
            status=FrictionEstimateStatus.UNKNOWN,
            rationale="Tax cannot yet be estimated from available aggregate metadata.",
            missing_data=("Verified taxable gain for the proposed sale is unavailable.",),
        )
        if unknown_tax
        else FrictionCostEstimate(
            kind=FrictionCostKind.TAX,
            status=FrictionEstimateStatus.KNOWN,
            amount=MonetaryAmount(amount=Decimal("10"), currency="USD"),
            rationale="Explicit externally supplied tax estimate for the proposed sale.",
        )
    )
    return ReplacementFriction(
        costs=(
            tax,
            FrictionCostEstimate(
                kind=FrictionCostKind.FEE,
                status=FrictionEstimateStatus.KNOWN,
                amount=MonetaryAmount(amount=Decimal("1"), currency="USD"),
                rationale="Explicit broker fee estimate.",
            ),
            FrictionCostEstimate(
                kind=FrictionCostKind.SPREAD,
                status=FrictionEstimateStatus.KNOWN,
                amount=MonetaryAmount(amount=Decimal("2"), currency="USD"),
                rationale="Explicit spread-cost estimate.",
            ),
        ),
        liquidity=LiquidityAssessment(
            status=LiquidityStatus.ADEQUATE,
            rationale="The explicit amount is assumed executable without a liquidity block.",
        ),
    )


def _replacement_input(
    context: DecisionContext,
    *,
    gross: str = "500",
    unknown_tax: bool = False,
    target_wins: bool = True,
    observations: tuple[ReplacementConstraintObservation, ...] = (),
) -> ReplacementDecisionInput:
    return ReplacementDecisionInput(
        knowledge_boundary=context.portfolio_state.knowledge_boundary,
        source_position_id=EXISTING_POSITION_ID,
        target=ReplacementTarget(
            target_id=REPLACEMENT_TARGET_ID,
            kind=ReplacementTargetKind.CORE_ETF,
            label="Synthetic diversified equity benchmark",
            instrument_id=CORE_INSTRUMENT_ID,
            native_currency="USD",
        ),
        gross_sale_amount=MonetaryAmount(amount=Decimal(gross), currency="USD"),
        pre_friction_comparison=_comparison(target_wins=target_wins),
        friction=_friction(unknown_tax=unknown_tax),
        after_friction_preference=(
            ReplacementPreference.TARGET
            if target_wins
            else ReplacementPreference.SOURCE
        ),
        after_friction_rationale=(
            "The target remains preferable after explicitly disclosed switching friction."
        ),
        constraint_observations=observations,
        decision_rationale=(
            "The source and target are compared directly rather than through a portfolio score.",
            "Tax, fee, spread, and liquidity remain visible rather than hidden in a threshold.",
            "The replacement uses a caller-supplied sale amount and never derives position size.",
        ),
        main_risks_and_unknowns=(
            "The qualitative source-target comparison is not empirically calibrated.",
        ),
        change_conditions=(
            "A higher switching cost or a stronger source case would keep the source position.",
        ),
        confidence=DecisionConfidence(
            level=DecisionConfidenceLevel.CONDITIONAL,
            rationale="The replacement is explicit but not prospectively calibrated.",
        ),
        assumptions=("No execution timing or order staging is evaluated in Chapter 6.",),
    )


def _replacement_builder(context: DecisionContext) -> BuildReplacementDecision:
    return BuildReplacementDecision(
        state_builder=context.state_builder,
        exposure_builder=context.exposure_builder,
        opportunity_builder=context.opportunity_builder,
    )


def test_owner_policy_is_content_addressed_and_order_invariant() -> None:
    context = make_decision_context()
    legacy = PositionCapitalPolicy(
        position_id=EXISTING_POSITION_ID,
        status=PositionCapitalStatus.LEGACY_HOLD_ZERO_NEW_CAPITAL,
        new_capital_eligibility=NewCapitalEligibility.ZERO_NEW_CAPITAL,
        rationale="The position may be held but cannot receive incremental capital.",
        change_conditions=("Re-underwrite before restoring new-capital eligibility.",),
    )
    constraints = (
        RatioConstraint(
            kind=RatioConstraintKind.MAX_COMPANY_HHI_UPPER_BOUND,
            maximum=Decimal("0.90"),
            rationale="Do not increase unresolved company concentration beyond the owner cap.",
        ),
        RatioConstraint(
            kind=RatioConstraintKind.MAX_COMPANY_WEIGHT,
            maximum=Decimal("0.95"),
            rationale="No company may exceed the owner-declared maximum weight.",
        ),
    )
    first = _policy(
        context,
        position_policies=(legacy,),
        ratio_constraints=constraints,
    )
    second = BuildOwnerPortfolioPolicy.execute(
        OwnerPortfolioPolicyInput(
            knowledge_boundary=context.portfolio_state.knowledge_boundary,
            position_policies=(legacy,),
            ratio_constraints=tuple(reversed(constraints)),
            rationale=(
                "Owner constraints are explicit gates and never an automatic sizing formula.",
            ),
            assumptions=("The policy applies only at the declared T0 boundary.",),
        )
    )
    assert second == first
    assert BuildOwnerPortfolioPolicy.verify(first) == first


def test_policy_constraints_keep_discrete_amount_and_can_force_no_allocation() -> None:
    context = make_decision_context()
    result, policy_decision = _apply_policy(context, _policy(context, max_capital="50"))

    assert result.decision.selected_alternative_id == CANDIDATE_ALTERNATIVE_ID
    assert policy_decision.outcome is PolicyDecisionOutcome.NO_ALLOCATION
    assert policy_decision.selected_alternative_id == INVESTMENT_CASH_ALTERNATIVE_ID
    assert {item.alternative_id for item in policy_decision.blocked_alternatives} == {
        CANDIDATE_ALTERNATIVE_ID,
        EXISTING_HOLDING_ALTERNATIVE_ID,
        "alternative:core-etf",
    }
    assert result.decision.capital_unit.amount.amount == Decimal("100")


def test_legacy_policy_blocks_only_incremental_capital_to_that_position() -> None:
    context = make_decision_context()
    legacy = PositionCapitalPolicy(
        position_id=EXISTING_POSITION_ID,
        status=PositionCapitalStatus.LEGACY_HOLD_ZERO_NEW_CAPITAL,
        new_capital_eligibility=NewCapitalEligibility.ZERO_NEW_CAPITAL,
        rationale="Keep the legacy position but allocate no new money to it.",
        change_conditions=("A fresh standalone review may change the classification.",),
    )
    _, decision = _apply_policy(context, _policy(context, position_policies=(legacy,)))

    assert decision.outcome is PolicyDecisionOutcome.ALLOCATE
    assert decision.selected_alternative_id == CANDIDATE_ALTERNATIVE_ID
    blocked = {item.alternative_id: item.reasons for item in decision.blocked_alternatives}
    assert EXISTING_HOLDING_ALTERNATIVE_ID in blocked


def test_runner_requires_current_market_value_opportunity_cost() -> None:
    with pytest.raises(ValidationError, match="current market value"):
        PositionCapitalPolicy(
            position_id=EXISTING_POSITION_ID,
            status=PositionCapitalStatus.RUNNER,
            new_capital_eligibility=NewCapitalEligibility.ZERO_NEW_CAPITAL,
            rationale="Recovered cost is tracked historically but cannot make the position free.",
            change_conditions=("Re-underwrite if thesis conditions change.",),
            recovered_proceeds=MonetaryAmount(amount=Decimal("900"), currency="USD"),
        )


def test_after_friction_target_can_replace_when_new_cash_is_insufficient() -> None:
    context = make_decision_context()
    policy = _policy(context)
    decision = _replacement_builder(context).execute(
        portfolio_state=context.portfolio_state,
        current_exposure=context.current_exposure,
        policy=policy,
        decision_input=_replacement_input(context),
    )

    assert decision.outcome is ReplacementOutcome.REPLACE
    assert decision.decision_basis is ReplacementDecisionBasis.AFTER_FRICTION_TARGET_DOMINANCE
    assert decision.total_switching_friction == MonetaryAmount(
        amount=Decimal("13"), currency="USD"
    )
    assert decision.net_redeployable_amount == MonetaryAmount(
        amount=Decimal("487"), currency="USD"
    )
    assert decision.available_new_capital == MonetaryAmount(
        amount=Decimal("200"), currency="USD"
    )
    card = ProjectDecisionCard.from_replacement_decision(decision)
    assert card.action is DecisionCardAction.REPLACE
    assert card.evaluated_amount == decision.net_redeployable_amount
    assert card.execution_status is DecisionCardExecutionStatus.NOT_EVALUATED


def test_new_capital_first_prevents_unnecessary_sale() -> None:
    context = make_decision_context()
    decision = _replacement_builder(context).execute(
        portfolio_state=context.portfolio_state,
        current_exposure=context.current_exposure,
        policy=_policy(context),
        decision_input=_replacement_input(context, gross="100"),
    )

    assert decision.outcome is ReplacementOutcome.HOLD
    assert decision.decision_basis is ReplacementDecisionBasis.NEW_CAPITAL_FIRST
    assert decision.net_redeployable_amount == MonetaryAmount(
        amount=Decimal("87"), currency="USD"
    )


def test_unknown_friction_fails_safe_to_hold() -> None:
    context = make_decision_context()
    decision = _replacement_builder(context).execute(
        portfolio_state=context.portfolio_state,
        current_exposure=context.current_exposure,
        policy=_policy(context),
        decision_input=_replacement_input(context, unknown_tax=True),
    )

    assert decision.outcome is ReplacementOutcome.HOLD
    assert decision.decision_basis is ReplacementDecisionBasis.FRICTION_UNKNOWN
    assert decision.total_switching_friction is None
    assert decision.net_redeployable_amount is None


def test_owner_replacement_cap_is_a_gate_not_an_automatic_resize() -> None:
    context = make_decision_context()
    decision = _replacement_builder(context).execute(
        portfolio_state=context.portfolio_state,
        current_exposure=context.current_exposure,
        policy=_policy(context, max_capital="400"),
        decision_input=_replacement_input(context),
    )

    assert decision.outcome is ReplacementOutcome.HOLD
    assert decision.decision_basis is ReplacementDecisionBasis.POLICY_BLOCK
    assert decision.gross_sale_amount.amount == Decimal("500")
    assert decision.net_redeployable_amount is not None
    assert decision.net_redeployable_amount.amount == Decimal("487")


def test_runner_recovered_proceeds_never_enter_replacement_arithmetic() -> None:
    context = make_decision_context()
    runner = PositionCapitalPolicy(
        position_id=EXISTING_POSITION_ID,
        status=PositionCapitalStatus.RUNNER,
        new_capital_eligibility=NewCapitalEligibility.ZERO_NEW_CAPITAL,
        rationale="The runner is evaluated at current market value, not at recovered cost.",
        change_conditions=("Exit if the remaining thesis is invalidated.",),
        recovered_proceeds=MonetaryAmount(amount=Decimal("900"), currency="USD"),
        runner_capital_basis=RunnerCapitalBasis.CURRENT_MARKET_VALUE,
    )
    decision = _replacement_builder(context).execute(
        portfolio_state=context.portfolio_state,
        current_exposure=context.current_exposure,
        policy=_policy(context, position_policies=(runner,)),
        decision_input=_replacement_input(context),
    )

    assert decision.outcome is ReplacementOutcome.REPLACE
    assert decision.gross_sale_amount.amount == Decimal("500")
    assert decision.net_redeployable_amount is not None
    assert decision.net_redeployable_amount.amount == Decimal("487")


def test_replacement_concentration_observation_can_block_target() -> None:
    context = make_decision_context()
    constraint = RatioConstraint(
        kind=RatioConstraintKind.MAX_COMPANY_WEIGHT,
        maximum=Decimal("0.25"),
        rationale="Reject a replacement that breaches the owner company-weight limit.",
    )
    observation = ReplacementConstraintObservation(
        kind=RatioConstraintKind.MAX_COMPANY_WEIGHT,
        observed_after=Decimal("0.30"),
        source_reference="fixture://replacement/after-exposure",
        source_fingerprint="0" * 64,
        rationale="Explicit after-replacement company-weight observation.",
    )
    decision = _replacement_builder(context).execute(
        portfolio_state=context.portfolio_state,
        current_exposure=context.current_exposure,
        policy=_policy(context, ratio_constraints=(constraint,)),
        decision_input=_replacement_input(context, observations=(observation,)),
    )

    assert decision.outcome is ReplacementOutcome.HOLD
    assert decision.decision_basis is ReplacementDecisionBasis.POLICY_BLOCK


def test_policy_decision_replay_detects_tampering() -> None:
    context = make_decision_context()
    policy = _policy(context)
    result, decision = _apply_policy(context, policy)
    altered = decision.model_copy(update={"input_fingerprint": "f" * 64})
    builder = ApplyPortfolioPolicy(decision_builder=context.decision_builder)

    with pytest.raises(PortfolioPolicyIntegrityError, match="canonical replay"):
        builder.verify(
            portfolio_state=context.portfolio_state,
            opportunity_state=context.opportunity_state,
            current_exposure=context.current_exposure,
            alternative_exposures=context.alternative_exposures,
            marginal_result=result,
            policy=policy,
            policy_decision=altered,
        )
