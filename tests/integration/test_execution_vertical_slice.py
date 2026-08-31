"""Vertical hand-off from canonical Chapter 6 capital decisions into Chapter 7 Execution."""

from asymmetric_engine.domain.execution import ExecutionAction, ExecutionSide
from asymmetric_engine.interfaces.execution_card import ProjectExecutionCard
from tests.execution_factories import (
    make_allocation_execution_input,
    make_execution_context,
    make_execution_policy,
    make_replacement_execution_input,
)


def test_chapter_7_preserves_allocation_and_replacement_lineage_without_resizing() -> None:
    context = make_execution_context()

    allocation_policy = make_execution_policy(
        context,
        max_single_order_notional="30",
    )
    allocation_plan = context.execution_builder.from_policy_allocation(
        portfolio_state=context.decision_context.portfolio_state,
        opportunity_state=context.decision_context.opportunity_state,
        current_exposure=context.decision_context.current_exposure,
        alternative_exposures=context.decision_context.alternative_exposures,
        marginal_result=context.marginal_result,
        owner_policy=context.owner_policy,
        policy_decision=context.policy_decision,
        execution_policy=allocation_policy,
        execution_input=make_allocation_execution_input(context),
    )
    allocation_card = ProjectExecutionCard.from_execution_plan(allocation_plan)

    assert allocation_plan.action is ExecutionAction.STAGED
    assert allocation_plan.source.decision_id == context.policy_decision.policy_decision_id
    assert allocation_plan.source.decision_fingerprint == context.policy_decision.input_fingerprint
    assert allocation_plan.source.target_amount == context.marginal_result.decision.capital_unit.amount
    assert allocation_plan.knowledge_boundary.as_of > (
        allocation_plan.source.decision_boundary.as_of
    )
    assert len(allocation_plan.legs) == 1
    assert allocation_plan.legs[0].side is ExecutionSide.BUY
    assert allocation_plan.legs[0].total_notional == allocation_plan.source.target_amount
    assert allocation_card.execution_plan_id == allocation_plan.plan_id
    assert allocation_card.input_fingerprint == allocation_plan.input_fingerprint

    replacement_policy = make_execution_policy(context)
    replacement_plan = context.execution_builder.from_replacement(
        portfolio_state=context.decision_context.portfolio_state,
        current_exposure=context.decision_context.current_exposure,
        owner_policy=context.owner_policy,
        replacement_decision=context.replacement_decision,
        execution_policy=replacement_policy,
        execution_input=make_replacement_execution_input(context),
    )
    replacement_card = ProjectExecutionCard.from_execution_plan(replacement_plan)

    assert replacement_plan.action is ExecutionAction.NOW
    assert replacement_plan.source.decision_id == context.replacement_decision.replacement_decision_id
    assert replacement_plan.source.target_amount == context.replacement_decision.net_redeployable_amount
    assert replacement_plan.source.source_sale_amount == context.replacement_decision.gross_sale_amount
    assert [item.side for item in replacement_plan.legs] == [
        ExecutionSide.SELL,
        ExecutionSide.BUY,
    ]
    assert replacement_plan.legs[0].total_notional == context.replacement_decision.gross_sale_amount
    assert replacement_plan.legs[1].total_notional == context.replacement_decision.net_redeployable_amount
    assert replacement_card.execution_plan_id == replacement_plan.plan_id
    assert replacement_card.input_fingerprint == replacement_plan.input_fingerprint
