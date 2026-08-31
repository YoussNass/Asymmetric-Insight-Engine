"""Deterministic Chapter 8 Learning fixtures over canonical Chapter 7 plans."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from asymmetric_engine.application.learning import (
    BuildDecisionLearningEvaluation,
    OpenDecisionLearningCase,
)
from asymmetric_engine.domain.execution import ExecutionPlan, ExecutionPolicy
from asymmetric_engine.domain.financial import MonetaryAmount, canonical_decimal
from asymmetric_engine.domain.learning import (
    DecisionLearningCase,
    LearningEvaluationInput,
    LearningPriceObservation,
    LearningThesisObservation,
    ThesisConditionStatus,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary
from tests.execution_factories import (
    ExecutionContext,
    make_allocation_execution_input,
    make_execution_context,
    make_execution_policy,
    make_replacement_execution_input,
)

PRICE_FINGERPRINT = "3" * 64
THESIS_FINGERPRINT = "4" * 64


def make_allocation_learning_case() -> tuple[
    ExecutionContext,
    ExecutionPolicy,
    ExecutionPlan,
    OpenDecisionLearningCase,
    DecisionLearningCase,
]:
    context = make_execution_context()
    policy = make_execution_policy(context)
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
    opener = OpenDecisionLearningCase(execution_builder=context.execution_builder)
    case = opener.from_policy_allocation(
        portfolio_state=context.decision_context.portfolio_state,
        opportunity_state=context.decision_context.opportunity_state,
        current_exposure=context.decision_context.current_exposure,
        alternative_exposures=context.decision_context.alternative_exposures,
        marginal_result=context.marginal_result,
        owner_policy=context.owner_policy,
        policy_decision=context.policy_decision,
        execution_policy=policy,
        execution_plan=plan,
    )
    return context, policy, plan, opener, case


def make_replacement_learning_case() -> tuple[
    ExecutionContext,
    ExecutionPolicy,
    ExecutionPlan,
    OpenDecisionLearningCase,
    DecisionLearningCase,
]:
    context = make_execution_context()
    policy = make_execution_policy(context)
    plan = context.execution_builder.from_replacement(
        portfolio_state=context.decision_context.portfolio_state,
        current_exposure=context.decision_context.current_exposure,
        owner_policy=context.owner_policy,
        replacement_decision=context.replacement_decision,
        execution_policy=policy,
        execution_input=make_replacement_execution_input(context),
    )
    opener = OpenDecisionLearningCase(execution_builder=context.execution_builder)
    case = opener.from_replacement(
        portfolio_state=context.decision_context.portfolio_state,
        current_exposure=context.decision_context.current_exposure,
        owner_policy=context.owner_policy,
        replacement_decision=context.replacement_decision,
        execution_policy=policy,
        execution_plan=plan,
        evaluation_horizon_date=(
            context.execution_boundary.as_of.date() + timedelta(days=365)
        ),
    )
    return context, policy, plan, opener, case


def evaluation_boundary(
    case: DecisionLearningCase,
    *,
    after_horizon: bool = True,
) -> KnowledgeBoundary:
    source = case.knowledge_boundary.as_of
    if after_horizon:
        horizon = datetime.combine(
            case.evaluation_horizon_date + timedelta(days=1),
            time(hour=16),
            tzinfo=source.tzinfo,
        )
        as_of = max(source + timedelta(days=2), horizon)
    else:
        horizon = datetime.combine(
            case.evaluation_horizon_date,
            time(hour=16),
            tzinfo=source.tzinfo,
        )
        as_of = min(source + timedelta(days=2), horizon - timedelta(days=1))
        if as_of <= source:
            as_of = source + timedelta(hours=1)
    return KnowledgeBoundary(
        as_of=as_of,
        knowledge_mode=case.knowledge_boundary.knowledge_mode,
    )


def make_price_observation(
    *,
    instrument_id: str,
    amount: Decimal,
    currency: str,
    observed_at: datetime,
    sequence: int,
) -> LearningPriceObservation:
    return LearningPriceObservation(
        instrument_id=instrument_id,
        price=MonetaryAmount(amount=canonical_decimal(amount), currency=currency),
        observed_at=observed_at,
        available_at=observed_at,
        recorded_at=observed_at,
        source_reference=f"fixture://learning/price/{instrument_id}/{sequence}",
        source_fingerprint=PRICE_FINGERPRINT,
    )


def make_thesis_observations(
    case: DecisionLearningCase,
    *,
    observed_at: datetime,
    status: ThesisConditionStatus = ThesisConditionStatus.NOT_TRIGGERED,
) -> tuple[LearningThesisObservation, ...]:
    return tuple(
        LearningThesisObservation(
            condition=condition,
            status=status,
            rationale="Evaluate the exact upstream change condition at the Learning boundary.",
            observed_at=observed_at,
            available_at=observed_at,
            recorded_at=observed_at,
            source_reference=f"fixture://learning/thesis/{index}",
            source_fingerprint=THESIS_FINGERPRINT,
            missing_data=(
                ("Current thesis evidence remains incomplete.",)
                if status is ThesisConditionStatus.UNKNOWN
                else ()
            ),
        )
        for index, condition in enumerate(case.change_conditions, start=1)
    )


def make_allocation_evaluation_input(
    case: DecisionLearningCase,
    *,
    after_horizon: bool = True,
    thesis_status: ThesisConditionStatus = ThesisConditionStatus.NOT_TRIGGERED,
) -> LearningEvaluationInput:
    boundary = evaluation_boundary(case, after_horizon=after_horizon)
    end_at = boundary.as_of - timedelta(minutes=1)
    interim_at = end_at - timedelta(days=1)
    target_start = case.target_reference_price.amount
    benchmark_start = case.benchmark_reference_price.amount
    if case.scenario_range is not None and after_horizon:
        target_end = canonical_decimal(
            target_start * (Decimal(1) + case.scenario_range.base_return)
        )
    else:
        target_end = canonical_decimal(target_start * Decimal("1.20"))
    target_interim = canonical_decimal(target_start * Decimal("0.80"))
    benchmark_end = canonical_decimal(benchmark_start * Decimal("1.10"))
    return LearningEvaluationInput(
        knowledge_boundary=boundary,
        price_observations=(
            make_price_observation(
                instrument_id=case.target_instrument_id,
                amount=target_interim,
                currency=case.target_reference_price.currency,
                observed_at=interim_at,
                sequence=1,
            ),
            make_price_observation(
                instrument_id=case.target_instrument_id,
                amount=target_end,
                currency=case.target_reference_price.currency,
                observed_at=end_at,
                sequence=2,
            ),
            make_price_observation(
                instrument_id=case.benchmark_instrument_id,
                amount=benchmark_end,
                currency=case.benchmark_reference_price.currency,
                observed_at=end_at,
                sequence=1,
            ),
        ),
        thesis_observations=make_thesis_observations(
            case,
            observed_at=end_at,
            status=thesis_status,
        ),
        assumptions=("Price-only Learning does not claim realized brokerage P&L.",),
    )


def make_replacement_evaluation_input(case: DecisionLearningCase) -> LearningEvaluationInput:
    boundary = evaluation_boundary(case, after_horizon=True)
    end_at = boundary.as_of - timedelta(minutes=1)
    assert case.replacement_source_instrument_id is not None
    assert case.replacement_source_reference_price is not None
    target_end = canonical_decimal(case.target_reference_price.amount * Decimal("1.10"))
    benchmark_end = canonical_decimal(
        case.benchmark_reference_price.amount * Decimal("1.10")
    )
    source_end = canonical_decimal(
        case.replacement_source_reference_price.amount * Decimal("0.90")
    )
    observations = [
        make_price_observation(
            instrument_id=case.target_instrument_id,
            amount=target_end,
            currency=case.target_reference_price.currency,
            observed_at=end_at,
            sequence=1,
        ),
        make_price_observation(
            instrument_id=case.replacement_source_instrument_id,
            amount=source_end,
            currency=case.replacement_source_reference_price.currency,
            observed_at=end_at,
            sequence=1,
        ),
    ]
    if case.benchmark_instrument_id != case.target_instrument_id:
        observations.append(
            make_price_observation(
                instrument_id=case.benchmark_instrument_id,
                amount=benchmark_end,
                currency=case.benchmark_reference_price.currency,
                observed_at=end_at,
                sequence=1,
            )
        )
    return LearningEvaluationInput(
        knowledge_boundary=boundary,
        price_observations=tuple(observations),
        thesis_observations=make_thesis_observations(case, observed_at=end_at),
    )


def learning_evaluator() -> BuildDecisionLearningEvaluation:
    return BuildDecisionLearningEvaluation()
