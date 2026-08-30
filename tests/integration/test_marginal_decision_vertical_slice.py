"""Vertical hand-off test for Chapter 6C1 competition for marginal capital."""

from __future__ import annotations

from asymmetric_engine.application.marginal_decision import MarginalDecisionResult
from asymmetric_engine.domain.portfolio import (
    CANDIDATE_ALTERNATIVE_ID,
    MarginalDecision,
    MarginalDecisionOutcome,
    PortfolioFit,
)
from asymmetric_engine.interfaces.decision_card import (
    DecisionCardAction,
    ProjectDecisionCard,
)
from tests.decision_factories import make_decision_context


def test_evidence_to_decision_card_preserves_t0_lineage_and_explicit_competition() -> None:
    context = make_decision_context()
    result = context.decision_builder.execute(
        portfolio_state=context.portfolio_state,
        opportunity_state=context.opportunity_state,
        current_exposure=context.current_exposure,
        alternative_exposures=context.alternative_exposures,
        decision_input=context.decision_input,
    )
    restored = MarginalDecisionResult(
        fits=tuple(
            PortfolioFit.model_validate_json(item.model_dump_json()) for item in result.fits
        ),
        decision=MarginalDecision.model_validate_json(result.decision.model_dump_json()),
    )
    verified = context.decision_builder.verify(
        portfolio_state=context.portfolio_state,
        opportunity_state=context.opportunity_state,
        current_exposure=context.current_exposure,
        alternative_exposures=context.alternative_exposures,
        result=restored,
    )
    card = ProjectDecisionCard.from_marginal_decision(verified.decision, verified.fits)

    assert verified.decision.outcome is MarginalDecisionOutcome.ALLOCATE
    assert verified.decision.selected_alternative_id == CANDIDATE_ALTERNATIVE_ID
    assert verified.decision.portfolio_state.input_fingerprint == (
        context.portfolio_state.input_fingerprint
    )
    assert verified.decision.opportunity_state.input_fingerprint == (
        context.opportunity_state.input_fingerprint
    )
    assert verified.decision.knowledge_boundary == context.portfolio_state.knowledge_boundary
    assert all(
        fit.knowledge_boundary == context.portfolio_state.knowledge_boundary
        for fit in verified.fits
    )
    assert card.action is DecisionCardAction.ALLOCATE
    assert card.decision_record_id == verified.decision.decision_id
    assert card.input_fingerprint == verified.decision.input_fingerprint
