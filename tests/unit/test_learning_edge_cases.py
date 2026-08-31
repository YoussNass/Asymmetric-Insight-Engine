"""Fail-safe edge cases for the Chapter 8 decision-level Learning MVP."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.learning import BuildDecisionLearningEvaluation
from asymmetric_engine.domain.financial import MonetaryAmount, canonical_decimal
from asymmetric_engine.domain.learning import (
    DecisionLearningCase,
    DecisionLearningCaseInput,
    LearningEvaluationInput,
    LearningMetrics,
    LearningPriceObservation,
    LearningThesisObservation,
    ScenarioRangeAnchor,
    ScenarioRealizationBand,
    ThesisConditionStatus,
    ThesisOutcome,
)
from asymmetric_engine.domain.temporal import KnowledgeMode
from tests.learning_factories import (
    PRICE_FINGERPRINT,
    THESIS_FINGERPRINT,
    learning_evaluator,
    make_allocation_evaluation_input,
    make_allocation_learning_case,
    make_replacement_learning_case,
)


def _case_input_values(case: DecisionLearningCase) -> dict[str, object]:
    return {
        field_name: getattr(case, field_name)
        for field_name in DecisionLearningCaseInput.model_fields
    }


def _evaluation_with_target_return(
    case: DecisionLearningCase,
    target_return: Decimal,
) -> LearningEvaluationInput:
    base = make_allocation_evaluation_input(case)
    target_observations = [
        item for item in base.price_observations if item.instrument_id == case.target_instrument_id
    ]
    final_target = max(target_observations, key=lambda item: item.observed_at)
    replacement = final_target.model_copy(
        update={
            "price": MonetaryAmount(
                amount=canonical_decimal(
                    case.target_reference_price.amount * (Decimal(1) + target_return)
                ),
                currency=case.target_reference_price.currency,
            )
        }
    )
    observations = tuple(
        replacement if item == final_target else item for item in base.price_observations
    )
    return LearningEvaluationInput(
        knowledge_boundary=base.knowledge_boundary,
        price_observations=observations,
        thesis_observations=base.thesis_observations,
        assumptions=base.assumptions,
    )


def test_candidate_learning_rejects_horizon_that_rewrites_underwriting() -> None:
    context, policy, plan, opener, case = make_allocation_learning_case()

    with pytest.raises(ValueError, match="preserve Underwriting scenarios"):
        opener.from_policy_allocation(
            portfolio_state=context.decision_context.portfolio_state,
            opportunity_state=context.decision_context.opportunity_state,
            current_exposure=context.decision_context.current_exposure,
            alternative_exposures=context.decision_context.alternative_exposures,
            marginal_result=context.marginal_result,
            owner_policy=context.owner_policy,
            policy_decision=context.policy_decision,
            execution_policy=policy,
            execution_plan=plan,
            evaluation_horizon_date=case.evaluation_horizon_date + timedelta(days=1),
        )


def test_non_candidate_learning_requires_explicit_horizon() -> None:
    context, policy, plan, opener, _ = make_replacement_learning_case()

    with pytest.raises(ValueError, match="explicit evaluation horizon"):
        opener.from_replacement(
            portfolio_state=context.decision_context.portfolio_state,
            current_exposure=context.decision_context.current_exposure,
            owner_policy=context.owner_policy,
            replacement_decision=context.replacement_decision,
            execution_policy=policy,
            execution_plan=plan,
        )


def test_learning_case_rejects_cross_currency_benchmark_anchor() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    values = _case_input_values(case)
    values["benchmark_reference_price"] = MonetaryAmount(
        amount=case.benchmark_reference_price.amount,
        currency="EUR",
    )

    with pytest.raises(ValidationError, match="one native currency"):
        DecisionLearningCaseInput.model_validate(values)


def test_learning_case_horizon_must_follow_t0() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    values = _case_input_values(case)
    values["evaluation_horizon_date"] = case.source.decision_boundary.as_of.date()
    values["scenario_range"] = None

    with pytest.raises(ValidationError, match="must follow the capital decision"):
        DecisionLearningCaseInput.model_validate(values)


def test_scenario_range_rejects_non_monotonic_bear_base_bull() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    assert case.scenario_range is not None

    with pytest.raises(ValidationError, match="bear <= base <= bull"):
        ScenarioRangeAnchor(
            currency=case.scenario_range.currency,
            reference_price=case.scenario_range.reference_price,
            horizon_date=case.scenario_range.horizon_date,
            bear_return=Decimal("0.20"),
            base_return=Decimal("0.10"),
            bull_return=Decimal("0.30"),
        )


def test_learning_price_observation_rejects_zero_and_bad_timestamp_order() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    when = case.knowledge_boundary.as_of + timedelta(hours=1)

    with pytest.raises(ValidationError, match="greater than zero"):
        LearningPriceObservation(
            instrument_id=case.target_instrument_id,
            price=MonetaryAmount(amount=Decimal(0), currency=case.target_reference_price.currency),
            observed_at=when,
            available_at=when,
            recorded_at=when,
            source_reference="fixture://learning/zero-price",
            source_fingerprint=PRICE_FINGERPRINT,
        )

    with pytest.raises(ValidationError, match="observed <= available <= recorded"):
        LearningPriceObservation(
            instrument_id=case.target_instrument_id,
            price=case.target_reference_price,
            observed_at=when,
            available_at=when - timedelta(seconds=1),
            recorded_at=when,
            source_reference="fixture://learning/bad-time",
            source_fingerprint=PRICE_FINGERPRINT,
        )


def test_unknown_thesis_observation_requires_missing_data() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    when = case.knowledge_boundary.as_of + timedelta(hours=1)

    with pytest.raises(ValidationError, match="requires missing_data"):
        LearningThesisObservation(
            condition=case.change_conditions[0],
            status=ThesisConditionStatus.UNKNOWN,
            rationale="Evidence is incomplete.",
            observed_at=when,
            available_at=when,
            recorded_at=when,
            source_reference="fixture://learning/unknown-thesis",
            source_fingerprint=THESIS_FINGERPRINT,
        )


def test_learning_input_rejects_duplicate_price_and_thesis_observations() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)

    with pytest.raises(ValidationError, match="duplicate Learning price observations"):
        LearningEvaluationInput(
            knowledge_boundary=base.knowledge_boundary,
            price_observations=(base.price_observations[0], base.price_observations[0]),
            thesis_observations=base.thesis_observations,
        )

    with pytest.raises(ValidationError, match="duplicate Learning thesis observations"):
        LearningEvaluationInput(
            knowledge_boundary=base.knowledge_boundary,
            price_observations=base.price_observations,
            thesis_observations=(base.thesis_observations[0], base.thesis_observations[0]),
        )


def test_learning_metrics_reject_inconsistent_arithmetic() -> None:
    with pytest.raises(ValidationError, match="target minus benchmark"):
        LearningMetrics(
            observed_target_return=Decimal("0.20"),
            observed_benchmark_return=Decimal("0.10"),
            observed_excess_return=Decimal("0.50"),
            target_max_drawdown=Decimal("-0.10"),
        )

    with pytest.raises(ValidationError, match="complete or absent"):
        LearningMetrics(
            observed_target_return=Decimal("0.20"),
            observed_benchmark_return=Decimal("0.10"),
            observed_excess_return=Decimal("0.10"),
            target_max_drawdown=Decimal("-0.10"),
            replacement_source_return=Decimal("0.05"),
        )

    with pytest.raises(ValidationError, match="target minus source"):
        LearningMetrics(
            observed_target_return=Decimal("0.20"),
            observed_benchmark_return=Decimal("0.10"),
            observed_excess_return=Decimal("0.10"),
            target_max_drawdown=Decimal("-0.10"),
            replacement_source_return=Decimal("0.05"),
            replacement_excess_vs_source=Decimal("0.50"),
        )


def test_learning_rejects_wrong_knowledge_mode_at_t2() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)
    other_mode = (
        KnowledgeMode.LIVE_SYSTEM_REPLAY
        if base.knowledge_boundary.knowledge_mode is KnowledgeMode.HISTORICAL_RECONSTRUCTION
        else KnowledgeMode.HISTORICAL_RECONSTRUCTION
    )
    boundary = base.knowledge_boundary.model_copy(update={"knowledge_mode": other_mode})

    with pytest.raises(ValueError, match="preserve the source KnowledgeMode"):
        learning_evaluator().execute(
            case=case,
            evaluation_input=base.model_copy(update={"knowledge_boundary": boundary}),
        )


def test_learning_rejects_observation_not_available_by_t2() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)
    observation = base.price_observations[0]
    later = base.knowledge_boundary.as_of + timedelta(seconds=1)
    altered = observation.model_copy(update={"available_at": later, "recorded_at": later})

    with pytest.raises(ValueError, match="outside the canonical T2 boundary"):
        learning_evaluator().execute(
            case=case,
            evaluation_input=base.model_copy(
                update={"price_observations": (altered, *base.price_observations[1:])}
            ),
        )


def test_learning_rejects_later_price_currency_drift() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)
    observation = base.price_observations[0]
    altered = observation.model_copy(
        update={
            "price": MonetaryAmount(amount=observation.price.amount, currency="EUR")
        }
    )

    with pytest.raises(ValueError, match="preserve each T0 anchor currency"):
        learning_evaluator().execute(
            case=case,
            evaluation_input=base.model_copy(
                update={"price_observations": (altered, *base.price_observations[1:])}
            ),
        )


def test_missing_thesis_assessment_stays_unresolved_instead_of_assuming_intact() -> None:
    _, _, _, _, case = make_allocation_learning_case()
    base = make_allocation_evaluation_input(case)
    evaluation = learning_evaluator().execute(
        case=case,
        evaluation_input=LearningEvaluationInput(
            knowledge_boundary=base.knowledge_boundary,
            price_observations=base.price_observations,
        ),
    )

    assert evaluation.thesis_outcome is ThesisOutcome.UNRESOLVED
    assert evaluation.missing_data


@pytest.mark.parametrize(
    ("relative_to_band", "expected"),
    [
        ("below_bear", ScenarioRealizationBand.BELOW_BEAR),
        ("bear_to_base", ScenarioRealizationBand.BEAR_TO_BASE),
        ("above_bull", ScenarioRealizationBand.ABOVE_BULL),
    ],
)
def test_matured_scenario_extreme_bands_are_categorical_not_scores(
    relative_to_band: str,
    expected: ScenarioRealizationBand,
) -> None:
    _, _, _, _, case = make_allocation_learning_case()
    assert case.scenario_range is not None
    scenario = case.scenario_range
    if relative_to_band == "below_bear":
        target_return = scenario.bear_return - Decimal("0.01")
    elif relative_to_band == "bear_to_base":
        target_return = canonical_decimal(
            (scenario.bear_return + scenario.base_return) / Decimal(2)
        )
    else:
        target_return = scenario.bull_return + Decimal("0.01")

    evaluation = BuildDecisionLearningEvaluation().execute(
        case=case,
        evaluation_input=_evaluation_with_target_return(case, target_return),
    )

    assert evaluation.scenario_realization is expected
