"""Unit and metamorphic tests for Chapter 6C1 marginal capital decisions."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.marginal_decision import (
    MarginalDecisionIntegrityError,
    MarginalDecisionResult,
    PositionReviewIntegrityError,
    RecordPositionHold,
)
from asymmetric_engine.application.underwriting import OpportunityStateIntegrityError
from asymmetric_engine.domain.evidence import ConfidenceCalibrationStatus
from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.opportunity import OpportunityStatus
from asymmetric_engine.domain.portfolio import (
    CANDIDATE_ALTERNATIVE_ID,
    CORE_ETF_ALTERNATIVE_ID,
    EXISTING_HOLDING_ALTERNATIVE_ID,
    INVESTMENT_CASH_ALTERNATIVE_ID,
    CandidateEquityInstrument,
    CapitalAlternative,
    CapitalAlternativeKind,
    ComponentPreference,
    DecisionBasis,
    DecisionConfidence,
    DecisionConfidenceLevel,
    FitDerivationKind,
    FitExposureDimension,
    HHIBounds,
    MarginalDecision,
    MarginalDecisionInput,
    MarginalDecisionOutcome,
    PairwiseCapitalComparison,
    PairwiseConclusion,
    PermanentLossAssessment,
    PermanentLossClass,
    PortfolioExposureInput,
    PortfolioFit,
    PositionReviewInput,
    PositionReviewOutcome,
    TradeOffComponent,
    TradeOffDimension,
    WeightDelta,
)
from asymmetric_engine.interfaces.decision_card import (
    DecisionCard,
    DecisionCardAction,
    DecisionCardExecutionStatus,
    ProjectDecisionCard,
)
from tests.decision_factories import (
    CAPITAL_AMOUNT,
    EXISTING_POSITION_ID,
    DecisionContext,
    make_decision_context,
    rebuild_decision_input,
)


def _execute(context: DecisionContext) -> MarginalDecisionResult:
    return context.decision_builder.execute(
        portfolio_state=context.portfolio_state,
        opportunity_state=context.opportunity_state,
        current_exposure=context.current_exposure,
        alternative_exposures=context.alternative_exposures,
        decision_input=context.decision_input,
    )


def test_candidate_unique_dominance_builds_allocate_decision_and_read_only_card() -> None:
    context = make_decision_context()
    result = _execute(context)

    assert result.decision.outcome is MarginalDecisionOutcome.ALLOCATE
    assert result.decision.selected_alternative_id == CANDIDATE_ALTERNATIVE_ID
    assert result.decision.dominance_winner_id == CANDIDATE_ALTERNATIVE_ID
    assert result.decision.decision_basis is DecisionBasis.UNIQUE_PAIRWISE_DOMINANCE
    assert {fit.alternative.alternative_id for fit in result.fits} == {
        CANDIDATE_ALTERNATIVE_ID,
        EXISTING_HOLDING_ALTERNATIVE_ID,
        CORE_ETF_ALTERNATIVE_ID,
        INVESTMENT_CASH_ALTERNATIVE_ID,
    }
    assert {item.amount for item in result.decision.alternatives} == {CAPITAL_AMOUNT}

    candidate_fit = result.fits[0]
    assert candidate_fit.derivation_kind is FitDerivationKind.PROSPECTIVE_DIRECT_EQUITY
    assert candidate_fit.opportunity_state == result.decision.opportunity_state
    assert candidate_fit.effect.gross_value_before.amount == Decimal("1100")
    assert candidate_fit.effect.gross_value_after.amount == Decimal("1200")
    assert candidate_fit.effect.company_hhi_before == HHIBounds(
        lower_bound=Decimal("1"), upper_bound=Decimal("1")
    )
    assert candidate_fit.effect.company_hhi_after.lower_bound == Decimal("0.847222222222")
    assert any(
        delta.dimension is FitExposureDimension.COMPANY
        and delta.component_id == context.opportunity_state.candidate_id
        and delta.before_weight == 0
        and delta.after_weight == Decimal("0.083333333333")
        for delta in candidate_fit.effect.weight_deltas
    )

    card = ProjectDecisionCard.from_marginal_decision(result.decision, result.fits)
    assert card.action is DecisionCardAction.ALLOCATE
    assert card.evaluated_amount == CAPITAL_AMOUNT
    assert card.portfolio_effect == candidate_fit.effect
    assert card.execution_status is DecisionCardExecutionStatus.NOT_EVALUATED
    assert not hasattr(card, "order")
    assert not hasattr(result.decision, "score")
    assert not hasattr(result.decision, "position_size")


def test_indeterminate_pair_prevents_forced_allocation_and_preserves_cash() -> None:
    context = make_decision_context()
    comparisons = tuple(
        _make_indeterminate(item)
        if {
            item.first_alternative_id,
            item.second_alternative_id,
        }
        == {CANDIDATE_ALTERNATIVE_ID, INVESTMENT_CASH_ALTERNATIVE_ID}
        else item
        for item in context.decision_input.comparisons
    )
    context = _replace_input(
        context,
        comparisons=comparisons,
        best_rejected_alternative_id=CANDIDATE_ALTERNATIVE_ID,
    )
    result = _execute(context)

    assert result.decision.outcome is MarginalDecisionOutcome.NO_ALLOCATION
    assert result.decision.selected_alternative_id == INVESTMENT_CASH_ALTERNATIVE_ID
    assert result.decision.dominance_winner_id is None
    assert result.decision.decision_basis is DecisionBasis.CONSERVATIVE_CASH_DEFAULT


def test_dominant_cash_is_an_explicit_no_allocation_outcome() -> None:
    context = make_decision_context()
    comparisons = tuple(
        _prefer_cash(item)
        if INVESTMENT_CASH_ALTERNATIVE_ID in {item.first_alternative_id, item.second_alternative_id}
        else item
        for item in context.decision_input.comparisons
    )
    context = _replace_input(
        context,
        comparisons=comparisons,
        best_rejected_alternative_id=CANDIDATE_ALTERNATIVE_ID,
    )
    result = _execute(context)

    assert result.decision.outcome is MarginalDecisionOutcome.NO_ALLOCATION
    assert result.decision.dominance_winner_id == INVESTMENT_CASH_ALTERNATIVE_ID
    assert result.decision.selected_alternative_id == INVESTMENT_CASH_ALTERNATIVE_ID
    cash_fit = next(
        fit
        for fit in result.fits
        if fit.alternative.alternative_id == INVESTMENT_CASH_ALTERNATIVE_ID
    )
    assert cash_fit.derivation_kind is FitDerivationKind.UNCHANGED_INVESTMENT_CASH
    assert cash_fit.effect.gross_value_before == cash_fit.effect.gross_value_after
    assert cash_fit.effect.weight_deltas == ()


def test_order_and_pair_orientation_do_not_change_content_addresses() -> None:
    context = make_decision_context()
    expected = _execute(context)
    reversed_comparisons = tuple(
        _reverse_comparison(item) for item in reversed(context.decision_input.comparisons)
    )
    reordered = _replace_input(
        context,
        comparisons=reversed_comparisons,
        permanent_loss_assessments=tuple(
            reversed(context.decision_input.permanent_loss_assessments)
        ),
        missing_data=tuple(reversed(context.decision_input.missing_data)),
        assumptions=tuple(reversed(context.decision_input.assumptions)),
    )

    assert _execute(reordered) == expected
    assert (
        reordered.decision_builder.execute(
            portfolio_state=reordered.portfolio_state,
            opportunity_state=reordered.opportunity_state,
            current_exposure=reordered.current_exposure,
            alternative_exposures=tuple(reversed(reordered.alternative_exposures)),
            decision_input=reordered.decision_input,
        )
        == expected
    )


def test_round_trip_replay_rejects_tampered_fit_and_decision() -> None:
    context = make_decision_context()
    result = _execute(context)
    restored = MarginalDecisionResult(
        fits=tuple(
            PortfolioFit.model_validate_json(item.model_dump_json()) for item in result.fits
        ),
        decision=MarginalDecision.model_validate_json(result.decision.model_dump_json()),
    )

    assert restored == result
    assert (
        context.decision_builder.verify(
            portfolio_state=context.portfolio_state,
            opportunity_state=context.opportunity_state,
            current_exposure=context.current_exposure,
            alternative_exposures=context.alternative_exposures,
            result=restored,
        )
        is restored
    )

    candidate_fit = restored.fits[0]
    changed_effect = candidate_fit.effect.model_copy(
        update={"company_hhi_after": HHIBounds(lower_bound=Decimal("0"), upper_bound=Decimal("0"))}
    )
    tampered_fits = (
        candidate_fit.model_copy(update={"effect": changed_effect}),
        *restored.fits[1:],
    )
    with pytest.raises(MarginalDecisionIntegrityError, match="canonical replay"):
        context.decision_builder.verify(
            portfolio_state=context.portfolio_state,
            opportunity_state=context.opportunity_state,
            current_exposure=context.current_exposure,
            alternative_exposures=context.alternative_exposures,
            result=MarginalDecisionResult(fits=tampered_fits, decision=restored.decision),
        )

    tampered_decision = restored.decision.model_copy(update={"input_fingerprint": "0" * 64})
    with pytest.raises(MarginalDecisionIntegrityError, match="canonical replay"):
        context.decision_builder.verify(
            portfolio_state=context.portfolio_state,
            opportunity_state=context.opportunity_state,
            current_exposure=context.current_exposure,
            alternative_exposures=context.alternative_exposures,
            result=MarginalDecisionResult(fits=restored.fits, decision=tampered_decision),
        )


@pytest.mark.parametrize(
    ("cash_ids", "amount", "message"),
    [
        (("cash:unknown",), CAPITAL_AMOUNT, "unknown cash"),
        (
            ("cash:bank:emergency-eur",),
            CAPITAL_AMOUNT,
            "emergency reserve",
        ),
        (
            ("cash:broker-a:unallocated-eur",),
            CAPITAL_AMOUNT,
            "evaluated capital currency",
        ),
        (
            ("cash:broker-a:opportunistic-usd",),
            MonetaryAmount(amount=Decimal("500"), currency="USD"),
            "insufficient",
        ),
    ],
)
def test_funding_must_be_known_investable_same_currency_and_sufficient(
    cash_ids: tuple[str, ...],
    amount: MonetaryAmount,
    message: str,
) -> None:
    context = make_decision_context()
    capital = context.decision_input.capital_unit.model_copy(
        update={"funding_cash_ids": cash_ids, "amount": amount}
    )
    context = _replace_input(context, capital_unit=capital)

    with pytest.raises(ValueError, match=message):
        _execute(context)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"company_subject_id": "company:not-micron"}, "Opportunity State company"),
        ({"instrument_id": "instrument:existing-equity"}, "must be prospective"),
        (
            {"reference_price": MonetaryAmount(amount=Decimal("99"), currency="USD")},
            "must match the Underwriting market fact",
        ),
        ({"native_currency": "EUR"}, "reference price must use"),
    ],
)
def test_candidate_must_match_verified_underwriting_and_remain_prospective(
    updates: dict[str, object],
    message: str,
) -> None:
    context = make_decision_context()
    values = context.decision_input.candidate_instrument.model_dump(mode="python")
    values.update(updates)
    if updates.get("native_currency") == "EUR":
        with pytest.raises(ValidationError, match=message):
            CandidateEquityInstrument.model_validate(values)
        return
    candidate = CandidateEquityInstrument.model_validate(values)
    context = _replace_input(context, candidate_instrument=candidate)

    with pytest.raises(ValueError, match=message):
        _execute(context)


def test_candidate_must_be_ready_and_use_the_funded_currency() -> None:
    context = make_decision_context(opportunity_status=OpportunityStatus.INVESTIGATE)
    with pytest.raises(ValueError, match="not ready for Portfolio review"):
        _execute(context)

    context = make_decision_context()
    capital = context.decision_input.capital_unit.model_copy(
        update={
            "amount": MonetaryAmount(amount=Decimal("100"), currency="EUR"),
            "funding_cash_ids": ("cash:broker-a:unallocated-eur",),
        }
    )
    context = _replace_input(context, capital_unit=capital)
    with pytest.raises(ValueError, match="candidate instrument must use"):
        _execute(context)


@pytest.mark.parametrize(
    ("existing_currency", "core_currency", "message"),
    [
        ("EUR", "USD", "existing holding must use"),
        ("USD", "EUR", "core ETF must use"),
    ],
)
def test_competing_securities_cannot_cross_currency_without_an_fx_contract(
    existing_currency: str,
    core_currency: str,
    message: str,
) -> None:
    context = make_decision_context(
        existing_currency=existing_currency,
        core_currency=core_currency,
    )

    with pytest.raises(ValueError, match=message):
        _execute(context)


def test_risk_lineage_is_candidate_only_and_must_resolve_to_underwriting() -> None:
    context = make_decision_context()
    assessments = list(context.decision_input.permanent_loss_assessments)
    candidate = assessments[0]
    assessments[0] = candidate.model_copy(update={"supporting_risk_ids": ()})
    with pytest.raises(ValueError, match="requires Underwriting risk ids"):
        _execute(_replace_input(context, permanent_loss_assessments=tuple(assessments)))

    assessments[0] = candidate.model_copy(update={"supporting_risk_ids": ("risk:unknown",)})
    with pytest.raises(ValueError, match="references unknown risks"):
        _execute(_replace_input(context, permanent_loss_assessments=tuple(assessments)))

    assessments[0] = candidate
    assessments[1] = assessments[1].model_copy(
        update={"supporting_risk_ids": candidate.supporting_risk_ids}
    )
    with pytest.raises(ValueError, match="only the candidate"):
        _execute(_replace_input(context, permanent_loss_assessments=tuple(assessments)))


@pytest.mark.parametrize(
    ("fact_id", "message"),
    [
        ("fact:absent", "absent from Underwriting"),
        ("reported:revenue-2025", "market-observed share-price fact"),
    ],
)
def test_candidate_price_reference_must_resolve_to_the_admitted_market_fact(
    fact_id: str,
    message: str,
) -> None:
    context = make_decision_context()
    candidate = context.decision_input.candidate_instrument.model_copy(
        update={"reference_price_fact_id": fact_id}
    )
    context = _replace_input(context, candidate_instrument=candidate)

    with pytest.raises(ValueError, match=message):
        _execute(context)


@pytest.mark.parametrize(
    ("position_id", "message"),
    [
        ("position:absent", "unknown position"),
        ("position:broker-a:thematic-etf", "must be a listed equity"),
    ],
)
def test_existing_alternative_must_be_a_known_eligible_equity(
    position_id: str,
    message: str,
) -> None:
    context = _replace_input(make_decision_context(), existing_position_id=position_id)

    with pytest.raises(ValueError, match=message):
        _execute(context)


def test_current_and_alternative_exposure_roles_cannot_be_substituted() -> None:
    context = make_decision_context()
    with pytest.raises(ValueError, match="current Portfolio Exposure cannot"):
        context.decision_builder.execute(
            portfolio_state=context.portfolio_state,
            opportunity_state=context.opportunity_state,
            current_exposure=context.core_etf_exposure,
            alternative_exposures=context.alternative_exposures,
            decision_input=context.decision_input,
        )

    with pytest.raises(ValueError, match="requires a hypothetical after view"):
        context.decision_builder.execute(
            portfolio_state=context.portfolio_state,
            opportunity_state=context.opportunity_state,
            current_exposure=context.current_exposure,
            alternative_exposures=(context.current_exposure, context.core_etf_exposure),
            decision_input=context.decision_input,
        )

    input_values = {
        field_name: getattr(context.existing_exposure, field_name)
        for field_name in PortfolioExposureInput.model_fields
    }
    exposure_input = PortfolioExposureInput.model_validate(input_values)
    assert exposure_input.hypothetical_position is not None
    wrong_amount_input = exposure_input.model_copy(
        update={
            "hypothetical_position": exposure_input.hypothetical_position.model_copy(
                update={"amount": MonetaryAmount(amount=Decimal("50"), currency="USD")}
            )
        }
    )
    wrong_amount_exposure = context.exposure_builder.execute(
        context.portfolio_state, wrong_amount_input
    )
    with pytest.raises(ValueError, match="must use the exact capital unit"):
        context.decision_builder.execute(
            portfolio_state=context.portfolio_state,
            opportunity_state=context.opportunity_state,
            current_exposure=context.current_exposure,
            alternative_exposures=(wrong_amount_exposure, context.core_etf_exposure),
            decision_input=context.decision_input,
        )

    different_before_input = exposure_input.model_copy(update={"top_company_count": 1})
    different_before_exposure = context.exposure_builder.execute(
        context.portfolio_state, different_before_input
    )
    with pytest.raises(ValueError, match="preserve the canonical current view"):
        context.decision_builder.execute(
            portfolio_state=context.portfolio_state,
            opportunity_state=context.opportunity_state,
            current_exposure=context.current_exposure,
            alternative_exposures=(different_before_exposure, context.core_etf_exposure),
            decision_input=context.decision_input,
        )


def test_tampered_upstream_states_and_incomplete_alternative_views_are_rejected() -> None:
    context = make_decision_context()
    tampered_opportunity = context.opportunity_state.model_copy(
        update={"thesis_summary": "Tampered but otherwise valid standalone thesis."}
    )
    with pytest.raises(OpportunityStateIntegrityError, match="canonical replay"):
        context.decision_builder.execute(
            portfolio_state=context.portfolio_state,
            opportunity_state=tampered_opportunity,
            current_exposure=context.current_exposure,
            alternative_exposures=context.alternative_exposures,
            decision_input=context.decision_input,
        )

    with pytest.raises(ValueError, match="each require one exposure view"):
        context.decision_builder.execute(
            portfolio_state=context.portfolio_state,
            opportunity_state=context.opportunity_state,
            current_exposure=context.current_exposure,
            alternative_exposures=(context.existing_exposure,),
            decision_input=context.decision_input,
        )
    with pytest.raises(ValueError, match="duplicate alternative exposure"):
        context.decision_builder.execute(
            portfolio_state=context.portfolio_state,
            opportunity_state=context.opportunity_state,
            current_exposure=context.current_exposure,
            alternative_exposures=(context.existing_exposure, context.existing_exposure),
            decision_input=context.decision_input,
        )


def test_missing_candidate_classification_is_unknown_not_false_zero_exposure() -> None:
    context = make_decision_context(include_candidate_profile=False)
    candidate_fit = _execute(context).fits[0]
    deltas = {
        (item.dimension, item.component_id): item for item in candidate_fit.effect.weight_deltas
    }

    assert (FitExposureDimension.SECTOR, "sector:unknown") in deltas
    assert (FitExposureDimension.GEOGRAPHY, "geography:unknown") in deltas
    assert (FitExposureDimension.ECONOMIC_DRIVER, "driver:unknown") in deltas
    assert any("classifications are unknown" in item for item in candidate_fit.missing_data)


def test_hold_is_a_separate_no_new_capital_record_and_has_no_execution_authority() -> None:
    context = make_decision_context()
    recorder = RecordPositionHold(
        state_builder=context.state_builder,
        exposure_builder=context.exposure_builder,
    )
    review_input = PositionReviewInput(
        knowledge_boundary=context.portfolio_state.knowledge_boundary,
        position_id=EXISTING_POSITION_ID,
        rationale=("The incumbent thesis remains intact; no new capital is evaluated.",),
        main_risks_and_unknowns=("No replacement comparison is admitted in Chapter 6C1.",),
        change_conditions=("A thesis invalidation triggers a new review.",),
        confidence=DecisionConfidence(
            level=DecisionConfidenceLevel.CONDITIONAL,
            rationale="The review is explicit but uncalibrated.",
        ),
    )
    review = recorder.execute(
        portfolio_state=context.portfolio_state,
        current_exposure=context.current_exposure,
        review_input=review_input,
    )

    assert review.outcome is PositionReviewOutcome.HOLD
    assert (
        recorder.verify(
            portfolio_state=context.portfolio_state,
            current_exposure=context.current_exposure,
            review=review,
        )
        is review
    )
    assert not hasattr(review, "amount")
    assert not hasattr(review, "replacement")
    assert not hasattr(review, "execution")
    card = ProjectDecisionCard.from_position_review(review)
    assert card.action is DecisionCardAction.HOLD
    assert card.evaluated_amount is None
    assert card.portfolio_effect is None

    tampered = review.model_copy(update={"input_fingerprint": "f" * 64})
    with pytest.raises(PositionReviewIntegrityError, match="canonical replay"):
        recorder.verify(
            portfolio_state=context.portfolio_state,
            current_exposure=context.current_exposure,
            review=tampered,
        )

    with pytest.raises(ValueError, match="current Portfolio Exposure only"):
        recorder.execute(
            portfolio_state=context.portfolio_state,
            current_exposure=context.core_etf_exposure,
            review_input=review_input,
        )
    shifted = review_input.knowledge_boundary.model_copy(
        update={"as_of": review_input.knowledge_boundary.as_of + timedelta(seconds=1)}
    )
    with pytest.raises(ValueError, match="preserve the Portfolio State boundary"):
        recorder.execute(
            portfolio_state=context.portfolio_state,
            current_exposure=context.current_exposure,
            review_input=review_input.model_copy(update={"knowledge_boundary": shifted}),
        )
    with pytest.raises(ValueError, match="unsupported method version"):
        recorder.execute(
            portfolio_state=context.portfolio_state,
            current_exposure=context.current_exposure,
            review_input=review_input.model_copy(update={"method_version": "hold-v999"}),
        )
    with pytest.raises(ValueError, match="unknown existing position"):
        recorder.execute(
            portfolio_state=context.portfolio_state,
            current_exposure=context.current_exposure,
            review_input=review_input.model_copy(update={"position_id": "position:unknown"}),
        )


def test_decision_card_rejects_missing_or_noncanonical_fits() -> None:
    result = _execute(make_decision_context())

    with pytest.raises(ValueError, match="do not match"):
        ProjectDecisionCard.from_marginal_decision(result.decision, result.fits[1:])
    changed = result.fits[0].model_copy(update={"input_fingerprint": "a" * 64})
    with pytest.raises(ValueError, match="non-canonical"):
        ProjectDecisionCard.from_marginal_decision(result.decision, (changed, *result.fits[1:]))
    changed_alternative = result.fits[0].alternative.model_copy(
        update={"label": "Tampered candidate label"}
    )
    changed = result.fits[0].model_copy(update={"alternative": changed_alternative})
    with pytest.raises(ValueError, match="does not match its decision alternative"):
        ProjectDecisionCard.from_marginal_decision(result.decision, (changed, *result.fits[1:]))


def test_contract_rejects_partial_competition_unknowns_without_disclosure_and_scores() -> None:
    context = make_decision_context()
    with pytest.raises(ValidationError, match="at least 6 items"):
        rebuild_decision_input(
            context.decision_input,
            comparisons=context.decision_input.comparisons[:-1],
        )
    with pytest.raises(ValidationError, match="unknown trade-off component requires"):
        TradeOffComponent(
            dimension=TradeOffDimension.UNCERTAINTY,
            preference=ComponentPreference.UNKNOWN,
            rationale="The available evidence cannot distinguish uncertainty.",
        )
    values = context.decision_input.model_dump(mode="python")
    values["score"] = 99
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MarginalDecisionInput.model_validate(values)


def test_pairwise_permanent_loss_must_match_the_disclosed_ordinal_assessments() -> None:
    context = make_decision_context()
    comparison = context.decision_input.comparisons[0]
    components = tuple(
        item.model_copy(update={"preference": ComponentPreference.BALANCED})
        if item.dimension is TradeOffDimension.PERMANENT_LOSS
        else item
        for item in comparison.components
    )
    inconsistent = PairwiseCapitalComparison.model_validate(
        {**comparison.model_dump(mode="python"), "components": components}
    )
    context = _replace_input(
        context,
        comparisons=(inconsistent, *context.decision_input.comparisons[1:]),
    )

    with pytest.raises(ValueError, match="conflicts with ordinal assessments"):
        _execute(context)


def test_unknown_permanent_loss_remains_explicit_without_becoming_a_score() -> None:
    context = make_decision_context()
    assessments = tuple(
        item.model_copy(
            update={
                "risk_class": PermanentLossClass.UNKNOWN,
                "missing_data": ("The loss class is not yet distinguishable.",),
            }
        )
        if item.alternative_id == CANDIDATE_ALTERNATIVE_ID
        else item
        for item in context.decision_input.permanent_loss_assessments
    )
    comparisons = tuple(
        item.model_copy(
            update={
                "components": tuple(
                    component.model_copy(
                        update={
                            "preference": ComponentPreference.UNKNOWN,
                            "missing_data": (
                                "Candidate permanent-loss risk is not yet distinguishable.",
                            ),
                        }
                    )
                    if component.dimension is TradeOffDimension.PERMANENT_LOSS
                    else component
                    for component in item.components
                )
            }
        )
        if CANDIDATE_ALTERNATIVE_ID in {item.first_alternative_id, item.second_alternative_id}
        else item
        for item in context.decision_input.comparisons
    )
    context = _replace_input(
        context,
        permanent_loss_assessments=assessments,
        comparisons=comparisons,
    )

    result = _execute(context)
    assert result.decision.outcome is MarginalDecisionOutcome.ALLOCATE
    assert any(
        component.preference is ComponentPreference.UNKNOWN
        for comparison in result.decision.comparisons
        for component in comparison.components
        if component.dimension is TradeOffDimension.PERMANENT_LOSS
    )


def test_knowledge_boundary_must_be_identical_across_every_state() -> None:
    context = make_decision_context()
    shifted = context.decision_input.knowledge_boundary.model_copy(
        update={"as_of": context.decision_input.knowledge_boundary.as_of + timedelta(seconds=1)}
    )
    context = _replace_input(context, knowledge_boundary=shifted)

    with pytest.raises(ValueError, match="one canonical knowledge boundary"):
        _execute(context)


def test_epistemic_contracts_reject_false_calibration_and_undisclosed_unknowns() -> None:
    with pytest.raises(ValidationError, match="must remain uncalibrated"):
        DecisionConfidence(
            level=DecisionConfidenceLevel.SUPPORTED,
            rationale="This deliberately false calibration must be rejected.",
            calibration_status=ConfidenceCalibrationStatus.CALIBRATED,
        )
    with pytest.raises(ValidationError, match="unknown permanent-loss class requires"):
        PermanentLossAssessment(
            alternative_id=CANDIDATE_ALTERNATIVE_ID,
            risk_class=PermanentLossClass.UNKNOWN,
            rationale="Available evidence does not support an ordinal class.",
        )
    with pytest.raises(ValidationError, match="duplicate permanent-loss entries"):
        PermanentLossAssessment(
            alternative_id=CANDIDATE_ALTERNATIVE_ID,
            risk_class=PermanentLossClass.MODERATE,
            rationale="Duplicate support identifiers are invalid.",
            supporting_risk_ids=("risk:a", "risk:a"),
        )


def test_pairwise_and_weight_contracts_reject_incoherent_shapes() -> None:
    context = make_decision_context()
    comparison = context.decision_input.comparisons[0]
    with pytest.raises(ValidationError, match="two different alternatives"):
        PairwiseCapitalComparison.model_validate(
            {
                **comparison.model_dump(mode="python"),
                "second_alternative_id": comparison.first_alternative_id,
            }
        )
    components = tuple(
        item.model_copy(update={"preference": ComponentPreference.BALANCED})
        for item in comparison.components
    )
    with pytest.raises(ValidationError, match="requires at least one supporting component"):
        PairwiseCapitalComparison.model_validate(
            {**comparison.model_dump(mode="python"), "components": components}
        )
    with pytest.raises(ValidationError, match="only economic-driver deltas"):
        WeightDelta(
            dimension=FitExposureDimension.COMPANY,
            component_id="company:test",
            before_weight=Decimal("0.1"),
            after_weight=Decimal("0.2"),
            is_non_additive=True,
        )
    with pytest.raises(ValidationError, match="only changed weights"):
        WeightDelta(
            dimension=FitExposureDimension.COMPANY,
            component_id="company:test",
            before_weight=Decimal("0.1"),
            after_weight=Decimal("0.1"),
        )


def test_alternative_fit_and_decision_contracts_are_defensive_when_deserialized() -> None:
    result = _execute(make_decision_context())
    candidate = result.decision.alternatives[0]
    with pytest.raises(ValidationError, match="candidate alternative requires"):
        CapitalAlternative.model_validate(
            {**candidate.model_dump(mode="python"), "opportunity_id": None}
        )
    cash = result.decision.alternatives[-1]
    with pytest.raises(ValidationError, match="investment cash cannot reference"):
        CapitalAlternative.model_validate(
            {**cash.model_dump(mode="python"), "instrument_id": "instrument:hidden"}
        )

    candidate_fit = result.fits[0]
    with pytest.raises(ValidationError, match="unrecognized method version"):
        PortfolioFit.model_validate(
            {**candidate_fit.model_dump(mode="python"), "method_version": "fit-v999"}
        )
    with pytest.raises(ValidationError, match="requires Opportunity"):
        PortfolioFit.model_validate(
            {**candidate_fit.model_dump(mode="python"), "opportunity_state": None}
        )

    decision_values = result.decision.model_dump(mode="python")
    with pytest.raises(ValidationError, match="NO_ALLOCATION must preserve"):
        MarginalDecision.model_validate(
            {**decision_values, "outcome": MarginalDecisionOutcome.NO_ALLOCATION}
        )
    with pytest.raises(ValidationError, match="best rejected alternative must differ"):
        MarginalDecision.model_validate(
            {
                **decision_values,
                "best_rejected_alternative_id": CANDIDATE_ALTERNATIVE_ID,
            }
        )


def test_decision_card_contract_cannot_smuggle_new_logic_or_execution() -> None:
    result = _execute(make_decision_context())
    card = ProjectDecisionCard.from_marginal_decision(result.decision, result.fits)
    values = card.model_dump(mode="python")

    with pytest.raises(ValidationError, match="unrecognized method version"):
        DecisionCard.model_validate({**values, "method_version": "decision-card-v999"})
    with pytest.raises(ValidationError, match="present together"):
        DecisionCard.model_validate({**values, "best_alternative_label": None})
    with pytest.raises(ValidationError, match="new-capital Decision Card requires"):
        DecisionCard.model_validate({**values, "evaluated_amount": None})
    with pytest.raises(ValidationError, match="Input should be 'not_evaluated'"):
        DecisionCard.model_validate({**values, "execution_status": "now"})


def test_all_capital_alternative_kinds_have_distinct_reference_shapes() -> None:
    result = _execute(make_decision_context())
    by_kind = {item.kind: item for item in result.decision.alternatives}

    assert by_kind[CapitalAlternativeKind.CANDIDATE_EQUITY].opportunity_id is not None
    assert by_kind[CapitalAlternativeKind.EXISTING_HOLDING].position_id is not None
    assert by_kind[CapitalAlternativeKind.CORE_ETF].instrument_id is not None
    assert by_kind[CapitalAlternativeKind.INVESTMENT_CASH].instrument_id is None


def _replace_input(context: DecisionContext, **overrides: object) -> DecisionContext:
    return context.__class__(
        **{
            **context.__dict__,
            "decision_input": rebuild_decision_input(context.decision_input, **overrides),
        }
    )


def _make_indeterminate(comparison: PairwiseCapitalComparison) -> PairwiseCapitalComparison:
    return PairwiseCapitalComparison.model_validate(
        {
            **comparison.model_dump(mode="python"),
            "conclusion": PairwiseConclusion.INDETERMINATE,
            "rationale": "The disclosed components do not establish an overall preference.",
        }
    )


def _prefer_cash(comparison: PairwiseCapitalComparison) -> PairwiseCapitalComparison:
    cash_is_first = comparison.first_alternative_id == INVESTMENT_CASH_ALTERNATIVE_ID
    preference = ComponentPreference.FIRST if cash_is_first else ComponentPreference.SECOND
    components = tuple(
        item.model_copy(update={"preference": preference})
        if item.dimension is TradeOffDimension.STANDALONE_CASE
        else item
        for item in comparison.components
    )
    return PairwiseCapitalComparison(
        first_alternative_id=comparison.first_alternative_id,
        second_alternative_id=comparison.second_alternative_id,
        components=components,
        conclusion=PairwiseConclusion.FIRST if cash_is_first else PairwiseConclusion.SECOND,
        rationale="Investment cash is explicitly preferred in this test case.",
    )


def _reverse_comparison(comparison: PairwiseCapitalComparison) -> PairwiseCapitalComparison:
    flip_component = {
        ComponentPreference.FIRST: ComponentPreference.SECOND,
        ComponentPreference.SECOND: ComponentPreference.FIRST,
        ComponentPreference.BALANCED: ComponentPreference.BALANCED,
        ComponentPreference.UNKNOWN: ComponentPreference.UNKNOWN,
    }
    flip_conclusion = {
        PairwiseConclusion.FIRST: PairwiseConclusion.SECOND,
        PairwiseConclusion.SECOND: PairwiseConclusion.FIRST,
        PairwiseConclusion.INDETERMINATE: PairwiseConclusion.INDETERMINATE,
    }
    return PairwiseCapitalComparison(
        first_alternative_id=comparison.second_alternative_id,
        second_alternative_id=comparison.first_alternative_id,
        components=tuple(
            item.model_copy(update={"preference": flip_component[item.preference]})
            for item in reversed(comparison.components)
        ),
        conclusion=flip_conclusion[comparison.conclusion],
        rationale=comparison.rationale,
    )
