"""Deterministic Chapter 7 Execution fixtures over canonical Chapter 6 decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from asymmetric_engine.application.execution import BuildExecutionPlan, BuildExecutionPolicy
from asymmetric_engine.application.marginal_decision import MarginalDecisionResult
from asymmetric_engine.application.portfolio_policy import (
    ApplyPortfolioPolicy,
    BuildOwnerPortfolioPolicy,
    BuildReplacementDecision,
)
from asymmetric_engine.domain.execution import (
    ExecutionInvalidationObservation,
    ExecutionLiquidityStatus,
    ExecutionPlanInput,
    ExecutionPolicy,
    ExecutionPolicyInput,
    InvalidationStatus,
    MarketExecutionObservation,
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
    OwnerPortfolioPolicy,
    OwnerPortfolioPolicyInput,
    PairwiseCapitalComparison,
    PairwiseConclusion,
    PolicyConstrainedMarginalDecision,
    ReplacementDecision,
    ReplacementDecisionInput,
    ReplacementFriction,
    ReplacementPreference,
    ReplacementTarget,
    ReplacementTargetKind,
    TradeOffComponent,
    TradeOffDimension,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary
from tests.decision_factories import (
    EXISTING_INSTRUMENT_ID,
    EXISTING_POSITION_ID,
    DecisionContext,
    make_decision_context,
)

CORE_INSTRUMENT_ID = "instrument:core-equity-etf"
REPLACEMENT_TARGET_ID = "replacement:core-etf"
SOURCE_FINGERPRINT = "1" * 64
INVALIDATION_FINGERPRINT = "2" * 64


@dataclass(frozen=True)
class ExecutionContext:
    """Canonical Chapter 6 decisions plus Chapter 7 builders and T1 boundary."""

    decision_context: DecisionContext
    marginal_result: MarginalDecisionResult
    owner_policy: OwnerPortfolioPolicy
    policy_decision: PolicyConstrainedMarginalDecision
    replacement_decision: ReplacementDecision
    policy_application: ApplyPortfolioPolicy
    replacement_builder: BuildReplacementDecision
    execution_builder: BuildExecutionPlan
    execution_boundary: KnowledgeBoundary


def make_execution_context() -> ExecutionContext:
    """Build one allocation and one replacement that are both executable in Chapter 7."""

    context = make_decision_context()
    marginal_result = context.decision_builder.execute(
        portfolio_state=context.portfolio_state,
        opportunity_state=context.opportunity_state,
        current_exposure=context.current_exposure,
        alternative_exposures=context.alternative_exposures,
        decision_input=context.decision_input,
    )
    owner_policy = BuildOwnerPortfolioPolicy.execute(
        OwnerPortfolioPolicyInput(
            knowledge_boundary=context.portfolio_state.knowledge_boundary,
            rationale=("Use explicit owner gates without automatic sizing.",),
        )
    )
    policy_application = ApplyPortfolioPolicy(decision_builder=context.decision_builder)
    policy_decision = policy_application.execute(
        portfolio_state=context.portfolio_state,
        opportunity_state=context.opportunity_state,
        current_exposure=context.current_exposure,
        alternative_exposures=context.alternative_exposures,
        marginal_result=marginal_result,
        policy=owner_policy,
    )
    replacement_builder = BuildReplacementDecision(
        state_builder=context.state_builder,
        exposure_builder=context.exposure_builder,
        opportunity_builder=context.opportunity_builder,
    )
    replacement_decision = replacement_builder.execute(
        portfolio_state=context.portfolio_state,
        current_exposure=context.current_exposure,
        policy=owner_policy,
        decision_input=make_replacement_input(context),
    )
    execution_builder = BuildExecutionPlan(
        policy_application=policy_application,
        replacement_builder=replacement_builder,
    )
    source_boundary = context.portfolio_state.knowledge_boundary
    execution_boundary = KnowledgeBoundary(
        as_of=source_boundary.as_of + timedelta(minutes=1),
        knowledge_mode=source_boundary.knowledge_mode,
    )
    return ExecutionContext(
        decision_context=context,
        marginal_result=marginal_result,
        owner_policy=owner_policy,
        policy_decision=policy_decision,
        replacement_decision=replacement_decision,
        policy_application=policy_application,
        replacement_builder=replacement_builder,
        execution_builder=execution_builder,
        execution_boundary=execution_boundary,
    )


def make_execution_policy(
    context: ExecutionContext,
    *,
    max_quote_age_seconds: int = 60,
    max_spread_bps: str = "50",
    max_single_order_notional: str | None = None,
) -> ExecutionPolicy:
    return BuildExecutionPolicy.execute(
        ExecutionPolicyInput(
            knowledge_boundary=context.execution_boundary,
            max_quote_age_seconds=max_quote_age_seconds,
            max_spread_bps=Decimal(max_spread_bps),
            max_single_order_notional=(
                MonetaryAmount(
                    amount=Decimal(max_single_order_notional),
                    currency="USD",
                )
                if max_single_order_notional is not None
                else None
            ),
            rationale=("Use explicit operational limits without a market-timing or regime score.",),
        )
    )


def make_market_observation(
    context: ExecutionContext,
    *,
    instrument_id: str,
    bid: str,
    ask: str,
    age_seconds: int = 10,
    liquidity: ExecutionLiquidityStatus = ExecutionLiquidityStatus.ADEQUATE,
) -> MarketExecutionObservation:
    observed_at = context.execution_boundary.as_of - timedelta(seconds=age_seconds)
    missing_data = (
        ("Current executable liquidity classification is unavailable.",)
        if liquidity is ExecutionLiquidityStatus.UNKNOWN
        else ()
    )
    return MarketExecutionObservation(
        instrument_id=instrument_id,
        native_currency="USD",
        bid=MonetaryAmount(amount=Decimal(bid), currency="USD"),
        ask=MonetaryAmount(amount=Decimal(ask), currency="USD"),
        observed_at=observed_at,
        available_at=observed_at,
        recorded_at=observed_at,
        liquidity=liquidity,
        source_reference=f"fixture://execution/quote/{instrument_id}",
        source_fingerprint=SOURCE_FINGERPRINT,
        missing_data=missing_data,
    )


def make_invalidation_observations(
    context: ExecutionContext,
    *,
    conditions: tuple[str, ...],
    status: InvalidationStatus = InvalidationStatus.NOT_TRIGGERED,
) -> tuple[ExecutionInvalidationObservation, ...]:
    observed_at = context.execution_boundary.as_of - timedelta(seconds=5)
    return tuple(
        ExecutionInvalidationObservation(
            condition=condition,
            status=status,
            rationale="The exact upstream change condition is evaluated at the execution boundary.",
            observed_at=observed_at,
            available_at=observed_at,
            recorded_at=observed_at,
            source_reference=f"fixture://execution/invalidation/{index}",
            source_fingerprint=INVALIDATION_FINGERPRINT,
            missing_data=(
                ("Current invalidation evidence is incomplete.",)
                if status is InvalidationStatus.UNKNOWN
                else ()
            ),
        )
        for index, condition in enumerate(conditions, start=1)
    )


def make_allocation_execution_input(
    context: ExecutionContext,
    *,
    age_seconds: int = 10,
    bid: str = "99.90",
    ask: str = "100.10",
    liquidity: ExecutionLiquidityStatus = ExecutionLiquidityStatus.ADEQUATE,
    invalidation_status: InvalidationStatus = InvalidationStatus.NOT_TRIGGERED,
    include_invalidations: bool = True,
) -> ExecutionPlanInput:
    condition_values = context.marginal_result.decision.change_conditions
    invalidations = (
        make_invalidation_observations(
            context,
            conditions=condition_values,
            status=invalidation_status,
        )
        if include_invalidations
        else ()
    )
    return ExecutionPlanInput(
        knowledge_boundary=context.execution_boundary,
        market_observations=(
            make_market_observation(
                context,
                instrument_id=context.marginal_result.decision.candidate_instrument.instrument_id,
                bid=bid,
                ask=ask,
                age_seconds=age_seconds,
                liquidity=liquidity,
            ),
        ),
        invalidation_observations=invalidations,
        assumptions=("No broker side effect is admitted in the Execution MVP.",),
    )


def make_replacement_execution_input(
    context: ExecutionContext,
    *,
    liquidity: ExecutionLiquidityStatus = ExecutionLiquidityStatus.ADEQUATE,
) -> ExecutionPlanInput:
    return ExecutionPlanInput(
        knowledge_boundary=context.execution_boundary,
        market_observations=(
            make_market_observation(
                context,
                instrument_id=EXISTING_INSTRUMENT_ID,
                bid="109.90",
                ask="110.10",
                liquidity=liquidity,
            ),
            make_market_observation(
                context,
                instrument_id=CORE_INSTRUMENT_ID,
                bid="99.90",
                ask="100.10",
                liquidity=liquidity,
            ),
        ),
        invalidation_observations=make_invalidation_observations(
            context,
            conditions=context.replacement_decision.change_conditions,
        ),
    )


def make_replacement_input(context: DecisionContext) -> ReplacementDecisionInput:
    """Return the accepted Chapter 6C2 core-ETF replacement reference case."""

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
        gross_sale_amount=MonetaryAmount(amount=Decimal("500"), currency="USD"),
        pre_friction_comparison=_replacement_comparison(),
        friction=_replacement_friction(),
        after_friction_preference=ReplacementPreference.TARGET,
        after_friction_rationale="The target remains preferred after explicit switching friction.",
        decision_rationale=(
            "The source and target are compared explicitly.",
            "Switching friction remains visible before replacement.",
            "Available new capital cannot fund the net replacement target.",
        ),
        main_risks_and_unknowns=("The qualitative comparison remains uncalibrated.",),
        change_conditions=("Higher friction or a stronger source case would retain the source.",),
        confidence=DecisionConfidence(
            level=DecisionConfidenceLevel.CONDITIONAL,
            rationale="The replacement is explicit but not prospectively calibrated.",
        ),
        assumptions=("Execution remains downstream of this capital decision.",),
    )


def _replacement_comparison() -> PairwiseCapitalComparison:
    return PairwiseCapitalComparison(
        first_alternative_id=EXISTING_POSITION_ID,
        second_alternative_id=REPLACEMENT_TARGET_ID,
        components=(
            TradeOffComponent(
                dimension=TradeOffDimension.STANDALONE_CASE,
                preference=ComponentPreference.SECOND,
                rationale="The target wins the standalone comparison.",
            ),
            TradeOffComponent(
                dimension=TradeOffDimension.PERMANENT_LOSS,
                preference=ComponentPreference.SECOND,
                rationale="The target has the preferred ordinal permanent-loss profile.",
            ),
            TradeOffComponent(
                dimension=TradeOffDimension.PORTFOLIO_EFFECT,
                preference=ComponentPreference.SECOND,
                rationale="The target has the preferred explicit portfolio effect.",
            ),
            TradeOffComponent(
                dimension=TradeOffDimension.UNCERTAINTY,
                preference=ComponentPreference.BALANCED,
                rationale="No uncertainty advantage is claimed.",
            ),
        ),
        conclusion=PairwiseConclusion.SECOND,
        rationale="The target wins the source-target comparison without a score.",
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
                rationale="Explicit spread-cost estimate.",
            ),
        ),
        liquidity=LiquidityAssessment(
            status=LiquidityStatus.ADEQUATE,
            rationale="Liquidity is adequate for the explicit Chapter 6 replacement proposal.",
        ),
    )
