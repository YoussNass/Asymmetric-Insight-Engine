"""Vertical hand-off test for Chapter 6C2 portfolio policy and replacement."""

from decimal import Decimal

from asymmetric_engine.application.portfolio_policy import (
    ApplyPortfolioPolicy,
    BuildOwnerPortfolioPolicy,
    BuildReplacementDecision,
)
from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.portfolio import (
    ComponentPreference,
    DecisionConfidence,
    DecisionConfidenceLevel,
    FrictionCostEstimate,
    FrictionCostKind,
    FrictionEstimateStatus,
    LiquidityAssessment,
    LiquidityStatus,
    OwnerPortfolioPolicyInput,
    PairwiseCapitalComparison,
    PairwiseConclusion,
    PolicyDecisionOutcome,
    ReplacementDecisionInput,
    ReplacementFriction,
    ReplacementOutcome,
    ReplacementPreference,
    ReplacementTarget,
    ReplacementTargetKind,
    TradeOffComponent,
    TradeOffDimension,
)
from asymmetric_engine.interfaces.decision_card import (
    DecisionCardAction,
    DecisionCardExecutionStatus,
    ProjectDecisionCard,
)
from tests.decision_factories import EXISTING_POSITION_ID, make_decision_context

REPLACEMENT_TARGET_ID = "replacement:core-etf"
CORE_ETF_INSTRUMENT_ID = "instrument:core-equity-etf"


def _replacement_comparison() -> PairwiseCapitalComparison:
    return PairwiseCapitalComparison(
        first_alternative_id=EXISTING_POSITION_ID,
        second_alternative_id=REPLACEMENT_TARGET_ID,
        components=(
            TradeOffComponent(
                dimension=TradeOffDimension.STANDALONE_CASE,
                preference=ComponentPreference.SECOND,
                rationale="The explicit core ETF target wins the standalone comparison.",
            ),
            TradeOffComponent(
                dimension=TradeOffDimension.PERMANENT_LOSS,
                preference=ComponentPreference.SECOND,
                rationale="The target has the preferred ordinal permanent-loss profile.",
            ),
            TradeOffComponent(
                dimension=TradeOffDimension.PORTFOLIO_EFFECT,
                preference=ComponentPreference.SECOND,
                rationale="The target is preferred on the explicit portfolio effect.",
            ),
            TradeOffComponent(
                dimension=TradeOffDimension.UNCERTAINTY,
                preference=ComponentPreference.BALANCED,
                rationale="No uncertainty advantage is claimed in the fixture.",
            ),
        ),
        conclusion=PairwiseConclusion.SECOND,
        rationale="The target wins the explicit source-target comparison without a score.",
    )


def _replacement_friction() -> ReplacementFriction:
    return ReplacementFriction(
        costs=(
            FrictionCostEstimate(
                kind=FrictionCostKind.TAX,
                status=FrictionEstimateStatus.KNOWN,
                amount=MonetaryAmount(amount=Decimal("10"), currency="USD"),
                rationale="Explicit T0 tax estimate.",
            ),
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
                rationale="Explicit spread estimate.",
            ),
        ),
        liquidity=LiquidityAssessment(
            status=LiquidityStatus.ADEQUATE,
            rationale="Liquidity is adequate for the explicit proposal.",
        ),
    )


def test_chapter_6c2_preserves_lineage_through_policy_and_replacement_cards() -> None:
    context = make_decision_context()
    marginal_result = context.decision_builder.execute(
        portfolio_state=context.portfolio_state,
        opportunity_state=context.opportunity_state,
        current_exposure=context.current_exposure,
        alternative_exposures=context.alternative_exposures,
        decision_input=context.decision_input,
    )
    policy = BuildOwnerPortfolioPolicy.execute(
        OwnerPortfolioPolicyInput(
            knowledge_boundary=context.portfolio_state.knowledge_boundary,
            rationale=("Use explicit owner gates without automatic sizing.",),
        )
    )
    policy_decision = ApplyPortfolioPolicy(decision_builder=context.decision_builder).execute(
        portfolio_state=context.portfolio_state,
        opportunity_state=context.opportunity_state,
        current_exposure=context.current_exposure,
        alternative_exposures=context.alternative_exposures,
        marginal_result=marginal_result,
        policy=policy,
    )
    policy_card = ProjectDecisionCard.from_policy_constrained_decision(
        policy_decision,
        marginal_result.decision,
        marginal_result.fits,
    )

    replacement_input = ReplacementDecisionInput(
        knowledge_boundary=context.portfolio_state.knowledge_boundary,
        source_position_id=EXISTING_POSITION_ID,
        target=ReplacementTarget(
            target_id=REPLACEMENT_TARGET_ID,
            kind=ReplacementTargetKind.CORE_ETF,
            label="Synthetic diversified equity benchmark",
            instrument_id=CORE_ETF_INSTRUMENT_ID,
            native_currency="USD",
        ),
        gross_sale_amount=MonetaryAmount(amount=Decimal("500"), currency="USD"),
        pre_friction_comparison=_replacement_comparison(),
        friction=_replacement_friction(),
        after_friction_preference=ReplacementPreference.TARGET,
        after_friction_rationale="The target remains preferred after explicit friction.",
        decision_rationale=(
            "The source and target are compared explicitly.",
            "Switching friction is visible before replacement.",
            "Available new capital is insufficient to fund the net target amount.",
        ),
        main_risks_and_unknowns=("The qualitative comparison remains uncalibrated.",),
        change_conditions=("Higher friction or a stronger source case would retain the source.",),
        confidence=DecisionConfidence(
            level=DecisionConfidenceLevel.CONDITIONAL,
            rationale="The decision is explicit but not prospectively calibrated.",
        ),
        assumptions=("Execution timing is outside Chapter 6.",),
    )
    replacement_builder = BuildReplacementDecision(
        state_builder=context.state_builder,
        exposure_builder=context.exposure_builder,
        opportunity_builder=context.opportunity_builder,
    )
    replacement = replacement_builder.execute(
        portfolio_state=context.portfolio_state,
        current_exposure=context.current_exposure,
        policy=policy,
        decision_input=replacement_input,
    )
    verified_replacement = replacement_builder.verify(
        portfolio_state=context.portfolio_state,
        current_exposure=context.current_exposure,
        policy=policy,
        decision=replacement,
    )
    replacement_card = ProjectDecisionCard.from_replacement_decision(verified_replacement)

    assert policy_decision.outcome is PolicyDecisionOutcome.ALLOCATE
    assert policy_decision.source_decision_id == marginal_result.decision.decision_id
    assert policy_decision.knowledge_boundary == context.portfolio_state.knowledge_boundary
    assert policy_card.action is DecisionCardAction.ALLOCATE
    assert policy_card.execution_status is DecisionCardExecutionStatus.NOT_EVALUATED

    assert verified_replacement.outcome is ReplacementOutcome.REPLACE
    assert verified_replacement.portfolio_state.input_fingerprint == (
        context.portfolio_state.input_fingerprint
    )
    assert verified_replacement.base_exposure.input_fingerprint == (
        context.current_exposure.input_fingerprint
    )
    assert verified_replacement.policy.input_fingerprint == policy.input_fingerprint
    assert verified_replacement.total_switching_friction == MonetaryAmount(
        amount=Decimal("13"), currency="USD"
    )
    assert verified_replacement.net_redeployable_amount == MonetaryAmount(
        amount=Decimal("487"), currency="USD"
    )
    assert replacement_card.action is DecisionCardAction.REPLACE
    assert replacement_card.execution_status is DecisionCardExecutionStatus.NOT_EVALUATED
    assert replacement_card.input_fingerprint == verified_replacement.input_fingerprint
