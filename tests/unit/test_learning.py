"""Unit tests for the Chapter 8 decision-level Learning MVP."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from asymmetric_engine.application.learning import (
    LearningCaseIntegrityError,
    LearningEvaluationIntegrityError,
)
from asymmetric_engine.domain.execution import ExecutionAction
from asymmetric_engine.domain.financial import canonical_decimal
from asymmetric_engine.domain.learning import (
    AccountPnlStatus,
    LearningEvaluationInput,
    LearningReturnBasis,
    LearningSourceKind,
    ScenarioRealizationBand,
    ThesisConditionStatus,
    ThesisOutcome,
)
from tests.execution_factories import make_allocation_execution_input, make_execution_policy
from tests.learning_factories import (
    evaluation_boundary,
    learning_evaluator,
    make_allocation_evaluation_input,
    make_allocation_learning_case,
    make_price_observation,
    make_replacement_evaluation_input,
    make_replacement_learning_case,
    make_thesis_observations,
)


def test_allocation_learning_case_preserves_verified_t0_t1_and_scenarios() -> None:
    context, _, plan, opener, case = make_allocation_learning_case()

    assert opener.verify(case) == case
    assert case.source.source_kind is LearningSourceKind.POLICY_ALLOCATION
    assert case.source.execution_plan_id == plan.plan_id
    assert case.source.decision_id == context.policy_decision.policy_decision_id
    assert case.source.decision_boundary == context.policy_decision.knowledge_boundary
    assert case.knowledge_boundary == plan.knowledge_boundary
    assert case.scenario_range is not None
    assert case.scenario_range.horizon_date == case.evaluation_horizon_date
    assert case.target_reference_price.amount == case.scenario_range.reference_price


def test_allocation_learning_evaluation_is_replayable_and_not_account_pnl() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    evaluator = learning_evaluator()
    evaluation = evaluator.execute(
        case=case,
        evaluation_input=make_allocation_evaluation_input(case),
    )

    assert evaluator.verify(case=case, evaluation=evaluation) == evaluation
    assert evaluation.return_basis is LearningReturnBasis.PRICE_ONLY_FROM_DECISION_REFERENCE
    assert evaluation.account_pnl_status is AccountPnlStatus.NOT_MEASURED_NO_FILL_DATA
    assert evaluation.thesis_outcome is ThesisOutcome.INTACT
    assert evaluation.horizon_reached is True
    assert evaluation.scenario_realization is ScenarioRealizationBand.BASE_TO_BULL
    assert case.scenario_range is not None
    assert evaluation.metrics.observed_target_return == case.scenario_range.base_return
    assert evaluation.metrics.observed_benchmark_return == Decimal("0.1")
    assert evaluation.metrics.observed_excess_return == canonical_decimal(
        evaluation.metrics.observed_target_return - Decimal("0.1")
    )
    expected_drawdown = canonical_decimal(
        min(Decimal("-0.2"), case.scenario_range.base_return, Decimal(0))
    )
    assert evaluation.metrics.target_max_drawdown == expected_drawdown


def test_pre_horizon_evaluation_records_observation_without_claiming_scenario_maturity() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    evaluation = learning_evaluator().execute(
        case=case,
        evaluation_input=make_allocation_evaluation_input(case, after_horizon=False),
    )

    assert evaluation.horizon_reached is False
    assert evaluation.scenario_realization is ScenarioRealizationBand.PRE_HORIZON


def test_unknown_thesis_condition_remains_unresolved() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    evaluation = learning_evaluator().execute(
        case=case,
        evaluation_input=make_allocation_evaluation_input(
            case,
            thesis_status=ThesisConditionStatus.UNKNOWN,
        ),
    )

    assert evaluation.thesis_outcome is ThesisOutcome.UNRESOLVED
    assert evaluation.missing_data


def test_triggered_thesis_condition_invalidates_without_rewriting_decision() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    evaluation = learning_evaluator().execute(
        case=case,
        evaluation_input=make_allocation_evaluation_input(
            case,
            thesis_status=ThesisConditionStatus.TRIGGERED,
        ),
    )

    assert evaluation.thesis_outcome is ThesisOutcome.INVALIDATED
    assert evaluation.case.case_id == case.case_id
    assert evaluation.case.input_fingerprint == case.input_fingerprint


def test_replacement_learning_compares_target_benchmark_and_source_counterfactual() -> None:
    _, _, _, _, case = make_replacement_learning_case()
    evaluation = learning_evaluator().execute(
        case=case,
        evaluation_input=make_replacement_evaluation_input(case),
    )

    assert case.source.source_kind is LearningSourceKind.REPLACEMENT
    assert case.scenario_range is None
    assert evaluation.scenario_realization is ScenarioRealizationBand.NOT_AVAILABLE
    assert evaluation.metrics.observed_target_return == Decimal("0.1")
    assert evaluation.metrics.observed_benchmark_return == Decimal("0.1")
    assert evaluation.metrics.observed_excess_return == Decimal(0)
    assert evaluation.metrics.replacement_source_return == Decimal("-0.1")
    assert evaluation.metrics.replacement_excess_vs_source == Decimal("0.2")


def test_wait_execution_plan_cannot_open_active_learning_case() -> None:
    context, _, _, opener, _ = make_allocation_learning_case()
    policy = make_execution_policy(context, max_quote_age_seconds=30)
    wait_plan = context.execution_builder.from_policy_allocation(
        portfolio_state=context.decision_context.portfolio_state,
        opportunity_state=context.decision_context.opportunity_state,
        current_exposure=context.decision_context.current_exposure,
        alternative_exposures=context.decision_context.alternative_exposures,
        marginal_result=context.marginal_result,
        owner_policy=context.owner_policy,
        policy_decision=context.policy_decision,
        execution_policy=policy,
        execution_input=make_allocation_execution_input(context, age_seconds=120),
    )
    assert wait_plan.action is ExecutionAction.WAIT

    with pytest.raises(ValueError, match="NOW or STAGED"):
        opener.from_policy_allocation(
            portfolio_state=context.decision_context.portfolio_state,
            opportunity_state=context.decision_context.opportunity_state,
            current_exposure=context.decision_context.current_exposure,
            alternative_exposures=context.decision_context.alternative_exposures,
            marginal_result=context.marginal_result,
            owner_policy=context.owner_policy,
            policy_decision=context.policy_decision,
            execution_policy=policy,
            execution_plan=wait_plan,
        )


def test_learning_rejects_future_outcome_observation() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)
    future = base.knowledge_boundary.as_of + timedelta(seconds=1)
    observation = base.price_observations[0]
    altered = observation.model_copy(
        update={"observed_at": future, "available_at": future, "recorded_at": future}
    )
    evaluation_input = base.model_copy(
        update={"price_observations": (altered, *base.price_observations[1:])}
    )

    with pytest.raises(ValueError, match="future"):
        learning_evaluator().execute(case=case, evaluation_input=evaluation_input)


def test_learning_rejects_price_observation_from_before_t0() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)
    before = case.source.decision_boundary.as_of - timedelta(seconds=1)
    observation = base.price_observations[0]
    altered = observation.model_copy(
        update={"observed_at": before, "available_at": before, "recorded_at": before}
    )
    evaluation_input = base.model_copy(
        update={"price_observations": (altered, *base.price_observations[1:])}
    )

    with pytest.raises(ValueError, match="before T0"):
        learning_evaluator().execute(case=case, evaluation_input=evaluation_input)


def test_learning_rejects_unrelated_price_instrument() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)
    end_at = base.knowledge_boundary.as_of - timedelta(minutes=1)
    extra = make_price_observation(
        instrument_id="instrument:unrelated",
        amount=Decimal("100"),
        currency=case.target_reference_price.currency,
        observed_at=end_at,
        sequence=1,
    )
    evaluation_input = base.model_copy(
        update={"price_observations": (*base.price_observations, extra)}
    )

    with pytest.raises(ValueError, match="unrelated instruments"):
        learning_evaluator().execute(case=case, evaluation_input=evaluation_input)


def test_learning_rejects_missing_comparison_leg() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)
    only_target = tuple(
        item
        for item in base.price_observations
        if item.instrument_id == case.target_instrument_id
    )
    evaluation_input = base.model_copy(update={"price_observations": only_target})

    with pytest.raises(ValueError, match="every comparison leg"):
        learning_evaluator().execute(case=case, evaluation_input=evaluation_input)


def test_learning_rejects_retrospective_change_condition() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)
    end_at = base.knowledge_boundary.as_of - timedelta(minutes=1)
    original = make_thesis_observations(case, observed_at=end_at)[0]
    invented = original.model_copy(update={"condition": "A hindsight-only invalidation rule."})
    evaluation_input = base.model_copy(
        update={"thesis_observations": (*base.thesis_observations, invented)}
    )

    with pytest.raises(ValueError, match="retrospective"):
        learning_evaluator().execute(case=case, evaluation_input=evaluation_input)


def test_learning_requires_same_end_observation_date() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)
    benchmark = next(
        item
        for item in base.price_observations
        if item.instrument_id == case.benchmark_instrument_id
    )
    shifted = benchmark.model_copy(
        update={
            "observed_at": benchmark.observed_at - timedelta(days=1),
            "available_at": benchmark.available_at - timedelta(days=1),
            "recorded_at": benchmark.recorded_at - timedelta(days=1),
        }
    )
    observations = tuple(
        shifted if item.instrument_id == case.benchmark_instrument_id else item
        for item in base.price_observations
    )

    with pytest.raises(ValueError, match="same observation date"):
        learning_evaluator().execute(
            case=case,
            evaluation_input=base.model_copy(update={"price_observations": observations}),
        )


def test_learning_conflicts_block_outcome_evaluation() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)
    evaluation_input = base.model_copy(
        update={"conflicts": ("The later market record has an unresolved contradiction.",)}
    )

    with pytest.raises(ValueError, match="conflicts"):
        learning_evaluator().execute(case=case, evaluation_input=evaluation_input)


def test_learning_case_and_evaluation_tampering_are_detected() -> None:
    _, _, _, opener, case = make_allocation_learning_case()
    evaluator = learning_evaluator()
    evaluation = evaluator.execute(
        case=case,
        evaluation_input=make_allocation_evaluation_input(case),
    )

    altered_case = case.model_copy(update={"input_fingerprint": "a" * 64})
    with pytest.raises(LearningCaseIntegrityError, match="canonical replay"):
        opener.verify(altered_case)

    altered_evaluation = evaluation.model_copy(update={"input_fingerprint": "b" * 64})
    with pytest.raises(LearningEvaluationIntegrityError, match="canonical replay"):
        evaluator.verify(case=case, evaluation=altered_evaluation)


def test_learning_rejects_t2_before_t1() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)
    invalid_boundary = base.knowledge_boundary.model_copy(
        update={"as_of": case.knowledge_boundary.as_of - timedelta(seconds=1)}
    )
    evaluation_input = LearningEvaluationInput(
        knowledge_boundary=invalid_boundary,
        price_observations=base.price_observations,
        thesis_observations=base.thesis_observations,
    )

    with pytest.raises(ValueError, match="T2 >= T1"):
        learning_evaluator().execute(case=case, evaluation_input=evaluation_input)


def test_evaluation_boundary_helper_is_after_t1() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    assert evaluation_boundary(case).as_of > case.knowledge_boundary.as_of
