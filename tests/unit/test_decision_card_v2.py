"""Audit-focused tests for the Chapter 6 Decision Card v2 projection."""

from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from asymmetric_engine.application.portfolio_policy import (
    ApplyPortfolioPolicy,
    BuildOwnerPortfolioPolicy,
)
from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.portfolio import OwnerPortfolioPolicyInput
from asymmetric_engine.interfaces.decision_card import (
    DECISION_CARD_METHOD_VERSION,
    ProjectDecisionCard,
)
from tests.decision_factories import make_decision_context


def _marginal_result():
    context = make_decision_context()
    result = context.decision_builder.execute(
        portfolio_state=context.portfolio_state,
        opportunity_state=context.opportunity_state,
        current_exposure=context.current_exposure,
        alternative_exposures=context.alternative_exposures,
        decision_input=context.decision_input,
    )
    return context, result


def test_v2_card_identity_includes_projection_method_version() -> None:
    context, result = _marginal_result()
    card = ProjectDecisionCard.from_marginal_decision(result.decision, result.fits)

    expected = uuid5(
        NAMESPACE_URL,
        (
            "asymmetric-insight-engine:decision-card:"
            f"{DECISION_CARD_METHOD_VERSION}:{result.decision.decision_id}"
        ),
    )
    legacy_v1_identity = uuid5(
        NAMESPACE_URL,
        f"asymmetric-insight-engine:decision-card:{result.decision.decision_id}",
    )

    assert card.card_id == expected
    assert card.card_id != legacy_v1_identity
    assert card.as_of == context.portfolio_state.knowledge_boundary.as_of


def test_policy_card_never_surfaces_a_blocked_best_alternative() -> None:
    context, result = _marginal_result()
    policy = BuildOwnerPortfolioPolicy.execute(
        OwnerPortfolioPolicyInput(
            knowledge_boundary=context.portfolio_state.knowledge_boundary,
            max_capital_unit=MonetaryAmount(amount=Decimal("50"), currency="USD"),
            rationale=("Block amounts above the explicit owner maximum.",),
        )
    )
    policy_decision = ApplyPortfolioPolicy(decision_builder=context.decision_builder).execute(
        portfolio_state=context.portfolio_state,
        opportunity_state=context.opportunity_state,
        current_exposure=context.current_exposure,
        alternative_exposures=context.alternative_exposures,
        marginal_result=result,
        policy=policy,
    )
    card = ProjectDecisionCard.from_policy_constrained_decision(
        policy_decision,
        result.decision,
        result.fits,
    )

    assert result.decision.best_rejected_alternative_id is not None
    assert result.decision.best_rejected_alternative_id not in (
        policy_decision.eligible_alternative_ids
    )
    assert card.best_alternative_id is None
    assert card.best_alternative_label is None
