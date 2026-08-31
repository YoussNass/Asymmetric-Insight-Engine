"""Integration test for the Chapter 6 -> 7 -> 8 decision-learning flow."""

from __future__ import annotations

from asymmetric_engine.domain.learning import AccountPnlStatus, ThesisOutcome
from tests.learning_factories import (
    learning_evaluator,
    make_allocation_evaluation_input,
    make_allocation_learning_case,
    make_replacement_evaluation_input,
    make_replacement_learning_case,
)


def test_verified_capital_decisions_flow_through_execution_into_learning() -> None:
    allocation_context, _, allocation_plan, _, allocation_case = make_allocation_learning_case()
    evaluator = learning_evaluator()
    allocation_evaluation = evaluator.execute(
        case=allocation_case,
        evaluation_input=make_allocation_evaluation_input(allocation_case),
    )

    assert allocation_case.source.decision_id == allocation_context.policy_decision.policy_decision_id
    assert allocation_case.source.execution_plan_id == allocation_plan.plan_id
    assert allocation_case.source.decision_boundary.as_of <= allocation_case.knowledge_boundary.as_of
    assert allocation_case.knowledge_boundary.as_of <= allocation_evaluation.knowledge_boundary.as_of
    assert allocation_evaluation.thesis_outcome is ThesisOutcome.INTACT
    assert allocation_evaluation.account_pnl_status is AccountPnlStatus.NOT_MEASURED_NO_FILL_DATA
    assert evaluator.verify(case=allocation_case, evaluation=allocation_evaluation) == (
        allocation_evaluation
    )

    replacement_context, _, replacement_plan, _, replacement_case = (
        make_replacement_learning_case()
    )
    replacement_evaluation = evaluator.execute(
        case=replacement_case,
        evaluation_input=make_replacement_evaluation_input(replacement_case),
    )

    assert replacement_case.source.decision_id == (
        replacement_context.replacement_decision.replacement_decision_id
    )
    assert replacement_case.source.execution_plan_id == replacement_plan.plan_id
    assert replacement_evaluation.metrics.replacement_source_return is not None
    assert replacement_evaluation.metrics.replacement_excess_vs_source is not None
    assert replacement_context.replacement_decision.input_fingerprint == (
        replacement_plan.source.decision_fingerprint
    )
