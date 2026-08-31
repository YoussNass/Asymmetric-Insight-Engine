"""Unit tests for the Chapter 7 point-in-time Execution MVP."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from asymmetric_engine.application.execution import (
    BuildExecutionPolicy,
    ExecutionPlanIntegrityError,
    ExecutionPolicyIntegrityError,
)
from asymmetric_engine.application.portfolio_policy import BuildOwnerPortfolioPolicy
from asymmetric_engine.domain.execution import (
    ApprovedCapitalInstruction,
    ExecutionAction,
    ExecutionLeg,
    ExecutionLiquidityStatus,
    ExecutionPlan,
    ExecutionPlanInput,
    ExecutionPolicy,
    ExecutionPolicyInput,
    ExecutionReasonCode,
    ExecutionSide,
    ExecutionSourceKind,
    ExecutionTranche,
    InvalidationStatus,
    MarketExecutionObservation,
)
from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.portfolio import OwnerPortfolioPolicyInput
from tests.execution_factories import (
    ExecutionContext,
    make_allocation_execution_input,
    make_execution_context,
    make_execution_policy,
    make_replacement_execution_input,
)


def _allocation_plan(
    *,
    max_order: str | None = None,
) -> tuple[ExecutionContext, ExecutionPolicy, ExecutionPlan]:
    context = make_execution_context()
    policy = make_execution_policy(context, max_single_order_notional=max_order)
    plan = context.execution_builder.from_policy_allocation(
        portfolio_state=context.decision_context.portfolio_state,
        opportunity_state=context.decision_context.opportunity_state,
        current_exposure=context.decision_context.current_exposure,
        alternative_exposures=context.decision_context.alternative_exposures,
        marginal_result=context.marginal_result,
        owner_policy=context.owner_policy,
        policy_decision=context.policy_decision,
        execution_policy=policy,
        execution_input=make_allocation_execution_input(context),
    )
    return context, policy, plan


def test_execution_policy_is_content_addressed_and_replayable() -> None:
    context = make_execution_context()
    policy = make_execution_policy(context, max_single_order_notional="30")

    assert BuildExecutionPolicy.verify(policy) == policy
    altered = policy.model_copy(update={"input_fingerprint": "f" * 64})
    with pytest.raises(ExecutionPolicyIntegrityError, match="canonical replay"):
        BuildExecutionPolicy.verify(altered)


def test_ready_allocation_executes_now_without_resizing() -> None:
    context, policy, plan = _allocation_plan()

    assert plan.action is ExecutionAction.NOW
    assert len(plan.legs) == 1
    leg = plan.legs[0]
    assert leg.side is ExecutionSide.BUY
    assert leg.total_notional == context.marginal_result.decision.capital_unit.amount
    assert len(leg.tranches) == 1
    assert leg.tranches[0].notional == leg.total_notional
    assert {item.code for item in plan.reasons} == {ExecutionReasonCode.READY_NOW}
    assert (
        context.execution_builder.verify_policy_allocation(
            portfolio_state=context.decision_context.portfolio_state,
            opportunity_state=context.decision_context.opportunity_state,
            current_exposure=context.decision_context.current_exposure,
            alternative_exposures=context.decision_context.alternative_exposures,
            marginal_result=context.marginal_result,
            owner_policy=context.owner_policy,
            policy_decision=context.policy_decision,
            execution_policy=policy,
            plan=plan,
        )
        == plan
    )


def test_explicit_order_limit_stages_exact_approved_amount() -> None:
    context, _, plan = _allocation_plan(max_order="30")

    assert plan.action is ExecutionAction.STAGED
    assert [item.notional.amount for item in plan.legs[0].tranches] == [
        Decimal("30"),
        Decimal("30"),
        Decimal("30"),
        Decimal("10"),
    ]
    assert sum(item.notional.amount for item in plan.legs[0].tranches) == (
        context.marginal_result.decision.capital_unit.amount.amount
    )
    assert {item.code for item in plan.reasons} == {ExecutionReasonCode.EXPLICIT_STAGING_LIMIT}


@pytest.mark.parametrize(
    ("execution_input_kwargs", "expected_reason"),
    [
        ({"age_seconds": 120}, ExecutionReasonCode.QUOTE_STALE),
        ({"bid": "99", "ask": "101"}, ExecutionReasonCode.SPREAD_TOO_WIDE),
        (
            {"liquidity": ExecutionLiquidityStatus.CONSTRAINED},
            ExecutionReasonCode.LIQUIDITY_CONSTRAINED,
        ),
        (
            {"liquidity": ExecutionLiquidityStatus.UNKNOWN},
            ExecutionReasonCode.LIQUIDITY_UNKNOWN,
        ),
        ({"include_invalidations": False}, ExecutionReasonCode.INVALIDATION_MISSING),
        (
            {"invalidation_status": InvalidationStatus.UNKNOWN},
            ExecutionReasonCode.INVALIDATION_UNKNOWN,
        ),
    ],
)
def test_operational_uncertainty_fails_safely_to_wait(
    execution_input_kwargs: dict[str, Any],
    expected_reason: ExecutionReasonCode,
) -> None:
    context = make_execution_context()
    policy = make_execution_policy(context)
    execution_input = make_allocation_execution_input(context, **execution_input_kwargs)

    plan = context.execution_builder.from_policy_allocation(
        portfolio_state=context.decision_context.portfolio_state,
        opportunity_state=context.decision_context.opportunity_state,
        current_exposure=context.decision_context.current_exposure,
        alternative_exposures=context.decision_context.alternative_exposures,
        marginal_result=context.marginal_result,
        owner_policy=context.owner_policy,
        policy_decision=context.policy_decision,
        execution_policy=policy,
        execution_input=execution_input,
    )

    assert plan.action is ExecutionAction.WAIT
    assert plan.legs == ()
    assert expected_reason in {item.code for item in plan.reasons}


def test_execution_input_conflicts_block_planning() -> None:
    context = make_execution_context()
    policy = make_execution_policy(context)
    execution_input = make_allocation_execution_input(context).model_copy(
        update={"conflicts": ("Current execution evidence contains an unresolved conflict.",)}
    )

    with pytest.raises(ValueError, match="conflicts"):
        context.execution_builder.from_policy_allocation(
            portfolio_state=context.decision_context.portfolio_state,
            opportunity_state=context.decision_context.opportunity_state,
            current_exposure=context.decision_context.current_exposure,
            alternative_exposures=context.decision_context.alternative_exposures,
            marginal_result=context.marginal_result,
            owner_policy=context.owner_policy,
            policy_decision=context.policy_decision,
            execution_policy=policy,
            execution_input=execution_input,
        )


def test_triggered_upstream_change_condition_invalidates_before_market_staging() -> None:
    context = make_execution_context()
    policy = make_execution_policy(context, max_single_order_notional="30")
    execution_input = make_allocation_execution_input(
        context,
        invalidation_status=InvalidationStatus.TRIGGERED,
    )

    plan = context.execution_builder.from_policy_allocation(
        portfolio_state=context.decision_context.portfolio_state,
        opportunity_state=context.decision_context.opportunity_state,
        current_exposure=context.decision_context.current_exposure,
        alternative_exposures=context.decision_context.alternative_exposures,
        marginal_result=context.marginal_result,
        owner_policy=context.owner_policy,
        policy_decision=context.policy_decision,
        execution_policy=policy,
        execution_input=execution_input,
    )

    assert plan.action is ExecutionAction.INVALIDATED
    assert plan.legs == ()
    assert {item.code for item in plan.reasons} == {ExecutionReasonCode.INVALIDATION_TRIGGERED}


def test_future_market_observation_is_rejected_by_execution_boundary() -> None:
    context = make_execution_context()
    policy = make_execution_policy(context)
    base_input = make_allocation_execution_input(context)
    observation = base_input.market_observations[0]
    future = context.execution_boundary.as_of + timedelta(seconds=1)
    future_observation = observation.model_copy(
        update={"observed_at": future, "available_at": future, "recorded_at": future}
    )
    execution_input = ExecutionPlanInput(
        knowledge_boundary=context.execution_boundary,
        market_observations=(future_observation,),
        invalidation_observations=base_input.invalidation_observations,
    )

    with pytest.raises(ValueError, match="future"):
        context.execution_builder.from_policy_allocation(
            portfolio_state=context.decision_context.portfolio_state,
            opportunity_state=context.decision_context.opportunity_state,
            current_exposure=context.decision_context.current_exposure,
            alternative_exposures=context.decision_context.alternative_exposures,
            marginal_result=context.marginal_result,
            owner_policy=context.owner_policy,
            policy_decision=context.policy_decision,
            execution_policy=policy,
            execution_input=execution_input,
        )


def test_no_allocation_cannot_become_an_execution_instruction() -> None:
    context = make_execution_context()
    blocked_policy = BuildOwnerPortfolioPolicy.execute(
        OwnerPortfolioPolicyInput(
            knowledge_boundary=context.decision_context.portfolio_state.knowledge_boundary,
            max_capital_unit=MonetaryAmount(amount=Decimal("50"), currency="USD"),
            rationale=("Block the evaluated capital unit without resizing it.",),
        )
    )
    blocked_decision = context.policy_application.execute(
        portfolio_state=context.decision_context.portfolio_state,
        opportunity_state=context.decision_context.opportunity_state,
        current_exposure=context.decision_context.current_exposure,
        alternative_exposures=context.decision_context.alternative_exposures,
        marginal_result=context.marginal_result,
        policy=blocked_policy,
    )

    with pytest.raises(ValueError, match="ALLOCATE"):
        context.execution_builder.from_policy_allocation(
            portfolio_state=context.decision_context.portfolio_state,
            opportunity_state=context.decision_context.opportunity_state,
            current_exposure=context.decision_context.current_exposure,
            alternative_exposures=context.decision_context.alternative_exposures,
            marginal_result=context.marginal_result,
            owner_policy=blocked_policy,
            policy_decision=blocked_decision,
            execution_policy=make_execution_policy(context),
            execution_input=make_allocation_execution_input(context),
        )


def test_replacement_staging_preserves_sell_and_buy_amounts_separately() -> None:
    context = make_execution_context()
    policy = make_execution_policy(context, max_single_order_notional="200")
    plan = context.execution_builder.from_replacement(
        portfolio_state=context.decision_context.portfolio_state,
        current_exposure=context.decision_context.current_exposure,
        owner_policy=context.owner_policy,
        replacement_decision=context.replacement_decision,
        execution_policy=policy,
        execution_input=make_replacement_execution_input(context),
    )

    assert plan.action is ExecutionAction.STAGED
    sell, buy = plan.legs
    assert sell.side is ExecutionSide.SELL
    assert sell.total_notional == context.replacement_decision.gross_sale_amount
    assert [item.notional.amount for item in sell.tranches] == [
        Decimal("200"),
        Decimal("200"),
        Decimal("100"),
    ]
    assert buy.side is ExecutionSide.BUY
    assert buy.total_notional == context.replacement_decision.net_redeployable_amount
    assert [item.notional.amount for item in buy.tranches] == [
        Decimal("200"),
        Decimal("200"),
        Decimal("87"),
    ]
    assert (
        context.execution_builder.verify_replacement(
            portfolio_state=context.decision_context.portfolio_state,
            current_exposure=context.decision_context.current_exposure,
            owner_policy=context.owner_policy,
            replacement_decision=context.replacement_decision,
            execution_policy=policy,
            plan=plan,
        )
        == plan
    )


def test_execution_plan_replay_detects_tampering() -> None:
    context, policy, plan = _allocation_plan()
    altered = plan.model_copy(update={"input_fingerprint": "e" * 64})

    with pytest.raises(ExecutionPlanIntegrityError, match="canonical replay"):
        context.execution_builder.verify_policy_allocation(
            portfolio_state=context.decision_context.portfolio_state,
            opportunity_state=context.decision_context.opportunity_state,
            current_exposure=context.decision_context.current_exposure,
            alternative_exposures=context.decision_context.alternative_exposures,
            marginal_result=context.marginal_result,
            owner_policy=context.owner_policy,
            policy_decision=context.policy_decision,
            execution_policy=policy,
            plan=altered,
        )


def test_execution_policy_rejects_zero_order_limit() -> None:
    context = make_execution_context()
    with pytest.raises(ValueError, match="greater than zero"):
        ExecutionPolicyInput(
            knowledge_boundary=context.execution_boundary,
            max_quote_age_seconds=60,
            max_spread_bps=Decimal("50"),
            max_single_order_notional=MonetaryAmount(amount=Decimal("0"), currency="USD"),
            rationale=("Zero cannot be a valid staging limit.",),
        )


def test_market_observation_rejects_crossed_market_and_unknown_without_disclosure() -> None:
    context = make_execution_context()
    observation = make_allocation_execution_input(context).market_observations[0]
    values = observation.model_dump(mode="python")
    values["ask"] = MonetaryAmount(amount=Decimal("99"), currency="USD")
    values["bid"] = MonetaryAmount(amount=Decimal("100"), currency="USD")

    with pytest.raises(ValueError, match="below bid"):
        MarketExecutionObservation.model_validate(values)

    values = observation.model_dump(mode="python")
    values["liquidity"] = ExecutionLiquidityStatus.UNKNOWN
    values["missing_data"] = ()
    with pytest.raises(ValueError, match="requires missing_data"):
        MarketExecutionObservation.model_validate(values)


def test_plan_input_rejects_duplicate_market_observations() -> None:
    context = make_execution_context()
    base_input = make_allocation_execution_input(context)
    observation = base_input.market_observations[0]

    with pytest.raises(ValueError, match="duplicate market observations"):
        ExecutionPlanInput(
            knowledge_boundary=context.execution_boundary,
            market_observations=(observation, observation),
            invalidation_observations=base_input.invalidation_observations,
        )


def test_execution_tranche_and_leg_require_exact_positive_notional() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        ExecutionTranche(
            tranche_index=1,
            notional=MonetaryAmount(amount=Decimal("0"), currency="USD"),
        )

    with pytest.raises(ValueError, match="sum must equal"):
        ExecutionLeg(
            sequence=1,
            side=ExecutionSide.BUY,
            instrument_id="instrument:test",
            total_notional=MonetaryAmount(amount=Decimal("100"), currency="USD"),
            tranches=(
                ExecutionTranche(
                    tranche_index=1,
                    notional=MonetaryAmount(amount=Decimal("90"), currency="USD"),
                ),
            ),
        )


def test_missing_quote_returns_wait_instead_of_inventing_market_data() -> None:
    context = make_execution_context()
    policy = make_execution_policy(context)
    base_input = make_allocation_execution_input(context)
    execution_input = ExecutionPlanInput(
        knowledge_boundary=context.execution_boundary,
        market_observations=(),
        invalidation_observations=base_input.invalidation_observations,
    )

    plan = context.execution_builder.from_policy_allocation(
        portfolio_state=context.decision_context.portfolio_state,
        opportunity_state=context.decision_context.opportunity_state,
        current_exposure=context.decision_context.current_exposure,
        alternative_exposures=context.decision_context.alternative_exposures,
        marginal_result=context.marginal_result,
        owner_policy=context.owner_policy,
        policy_decision=context.policy_decision,
        execution_policy=policy,
        execution_input=execution_input,
    )

    assert plan.action is ExecutionAction.WAIT
    assert ExecutionReasonCode.QUOTE_MISSING in {item.code for item in plan.reasons}
    assert plan.legs == ()


def test_extra_market_or_invalidation_inputs_are_rejected() -> None:
    context = make_execution_context()
    policy = make_execution_policy(context)
    base_input = make_allocation_execution_input(context)
    observation = base_input.market_observations[0]
    extra_market = observation.model_copy(update={"instrument_id": "instrument:unrelated"})
    market_input = ExecutionPlanInput(
        knowledge_boundary=context.execution_boundary,
        market_observations=(observation, extra_market),
        invalidation_observations=base_input.invalidation_observations,
    )

    with pytest.raises(ValueError, match="will not trade"):
        context.execution_builder.from_policy_allocation(
            portfolio_state=context.decision_context.portfolio_state,
            opportunity_state=context.decision_context.opportunity_state,
            current_exposure=context.decision_context.current_exposure,
            alternative_exposures=context.decision_context.alternative_exposures,
            marginal_result=context.marginal_result,
            owner_policy=context.owner_policy,
            policy_decision=context.policy_decision,
            execution_policy=policy,
            execution_input=market_input,
        )

    invalidation = base_input.invalidation_observations[0]
    extra_invalidation = invalidation.model_copy(update={"condition": "Unowned condition"})
    invalidation_input = ExecutionPlanInput(
        knowledge_boundary=context.execution_boundary,
        market_observations=base_input.market_observations,
        invalidation_observations=(*base_input.invalidation_observations, extra_invalidation),
    )
    with pytest.raises(ValueError, match="upstream invalidation"):
        context.execution_builder.from_policy_allocation(
            portfolio_state=context.decision_context.portfolio_state,
            opportunity_state=context.decision_context.opportunity_state,
            current_exposure=context.decision_context.current_exposure,
            alternative_exposures=context.decision_context.alternative_exposures,
            marginal_result=context.marginal_result,
            owner_policy=context.owner_policy,
            policy_decision=context.policy_decision,
            execution_policy=policy,
            execution_input=invalidation_input,
        )


def test_execution_rejects_wrong_currency_and_policy_boundary() -> None:
    context = make_execution_context()
    policy = make_execution_policy(context)
    base_input = make_allocation_execution_input(context)
    observation = base_input.market_observations[0]
    wrong_currency = observation.model_copy(
        update={
            "native_currency": "EUR",
            "bid": MonetaryAmount(amount=observation.bid.amount, currency="EUR"),
            "ask": MonetaryAmount(amount=observation.ask.amount, currency="EUR"),
        }
    )
    wrong_currency_input = ExecutionPlanInput(
        knowledge_boundary=context.execution_boundary,
        market_observations=(wrong_currency,),
        invalidation_observations=base_input.invalidation_observations,
    )
    with pytest.raises(ValueError, match="approved leg currency"):
        context.execution_builder.from_policy_allocation(
            portfolio_state=context.decision_context.portfolio_state,
            opportunity_state=context.decision_context.opportunity_state,
            current_exposure=context.decision_context.current_exposure,
            alternative_exposures=context.decision_context.alternative_exposures,
            marginal_result=context.marginal_result,
            owner_policy=context.owner_policy,
            policy_decision=context.policy_decision,
            execution_policy=policy,
            execution_input=wrong_currency_input,
        )

    later_boundary = context.execution_boundary.model_copy(
        update={"as_of": context.execution_boundary.as_of + timedelta(seconds=1)}
    )
    mismatched_policy = BuildExecutionPolicy.execute(
        ExecutionPolicyInput(
            knowledge_boundary=later_boundary,
            max_quote_age_seconds=60,
            max_spread_bps=Decimal("50"),
            rationale=("Deliberately mismatched test boundary.",),
        )
    )
    with pytest.raises(ValueError, match="share one boundary"):
        context.execution_builder.from_policy_allocation(
            portfolio_state=context.decision_context.portfolio_state,
            opportunity_state=context.decision_context.opportunity_state,
            current_exposure=context.decision_context.current_exposure,
            alternative_exposures=context.decision_context.alternative_exposures,
            marginal_result=context.marginal_result,
            owner_policy=context.owner_policy,
            policy_decision=context.policy_decision,
            execution_policy=mismatched_policy,
            execution_input=base_input,
        )


def test_execution_plan_and_source_models_reject_noncanonical_shapes() -> None:
    _, _, plan = _allocation_plan()
    plan_values = plan.model_dump(mode="python")
    plan_values["action"] = ExecutionAction.WAIT
    with pytest.raises(ValueError, match="cannot contain executable legs"):
        ExecutionPlan.model_validate(plan_values)

    source_values = plan.source.model_dump(mode="python")
    source_values["source_kind"] = ExecutionSourceKind.REPLACEMENT
    with pytest.raises(ValueError, match="source fields are required"):
        ApprovedCapitalInstruction.model_validate(source_values)
