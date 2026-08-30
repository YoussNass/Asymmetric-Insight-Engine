"""Read-only Decision Card projection over verified Chapter 6C1 records."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, model_validator

from asymmetric_engine.domain.evidence.models import ContentHash, NonEmptyString
from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.portfolio import (
    DecisionConfidence,
    FitCurrencyEffect,
    MarginalDecision,
    MarginalDecisionOutcome,
    PortfolioFit,
    PositionReview,
)

DECISION_CARD_METHOD_VERSION = "decision-card-v1"


class DecisionCardAction(StrEnum):
    """User-facing action without adding execution authority."""

    ALLOCATE = "allocate"
    HOLD = "hold"
    NO_ALLOCATION = "no_allocation"


class DecisionCardExecutionStatus(StrEnum):
    """Chapter 6C1 cannot decide timing or order staging."""

    NOT_EVALUATED = "not_evaluated"


class DecisionCard(BaseModel):
    """Compact projection; every value remains traceable to a canonical decision record."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    card_id: UUID
    method_version: NonEmptyString = DECISION_CARD_METHOD_VERSION
    decision_record_id: UUID
    action: DecisionCardAction
    evaluated_amount: MonetaryAmount | None
    selected_alternative_id: NonEmptyString
    selected_alternative_label: NonEmptyString
    why: tuple[NonEmptyString, ...]
    best_alternative_id: NonEmptyString | None
    best_alternative_label: NonEmptyString | None
    main_risks_and_unknowns: tuple[NonEmptyString, ...]
    confidence: DecisionConfidence
    what_would_change_the_decision: tuple[NonEmptyString, ...]
    portfolio_effect: FitCurrencyEffect | None
    execution_status: DecisionCardExecutionStatus = DecisionCardExecutionStatus.NOT_EVALUATED
    as_of: datetime
    input_fingerprint: ContentHash

    @model_validator(mode="after")
    def validate_projection_shape(self) -> DecisionCard:
        if self.method_version != DECISION_CARD_METHOD_VERSION:
            raise ValueError("Decision Card uses an unrecognized method version")
        if (self.best_alternative_id is None) != (self.best_alternative_label is None):
            raise ValueError("best alternative id and label must be present together")
        if self.action is DecisionCardAction.HOLD:
            if self.evaluated_amount is not None or self.portfolio_effect is not None:
                raise ValueError("HOLD cannot contain a new-capital amount or effect")
        elif self.evaluated_amount is None or self.portfolio_effect is None:
            raise ValueError("new-capital Decision Card requires amount and Portfolio Fit effect")
        if self.execution_status is not DecisionCardExecutionStatus.NOT_EVALUATED:
            raise ValueError("Chapter 6C1 cannot emit an execution state")
        return self


class ProjectDecisionCard:
    """Copy an already-decided state into a stable UI/API view without financial logic."""

    @staticmethod
    def from_marginal_decision(
        decision: MarginalDecision,
        fits: tuple[PortfolioFit, ...],
    ) -> DecisionCard:
        fit_by_alternative = {item.alternative.alternative_id: item for item in fits}
        if len(fit_by_alternative) != len(fits):
            raise ValueError("Decision Card received duplicate Portfolio Fits")
        if set(fit_by_alternative) != {item.alternative_id for item in decision.portfolio_fits}:
            raise ValueError("Decision Card Portfolio Fits do not match the decision")
        alternatives = {item.alternative_id: item for item in decision.alternatives}
        for reference in decision.portfolio_fits:
            fit = fit_by_alternative[reference.alternative_id]
            if (
                reference.fit_id != fit.fit_id
                or reference.input_fingerprint != fit.input_fingerprint
            ):
                raise ValueError("Decision Card received a non-canonical Portfolio Fit")
            if (
                fit.alternative != alternatives[reference.alternative_id]
                or fit.knowledge_boundary != decision.knowledge_boundary
            ):
                raise ValueError("Decision Card Fit does not match its decision alternative")
        selected = alternatives[decision.selected_alternative_id]
        best_id = decision.best_rejected_alternative_id
        best = alternatives[best_id] if best_id is not None else None
        action = (
            DecisionCardAction.ALLOCATE
            if decision.outcome is MarginalDecisionOutcome.ALLOCATE
            else DecisionCardAction.NO_ALLOCATION
        )
        return DecisionCard(
            card_id=uuid5(
                NAMESPACE_URL,
                f"asymmetric-insight-engine:decision-card:{decision.decision_id}",
            ),
            decision_record_id=decision.decision_id,
            action=action,
            evaluated_amount=decision.capital_unit.amount,
            selected_alternative_id=selected.alternative_id,
            selected_alternative_label=selected.label,
            why=decision.decision_rationale,
            best_alternative_id=best.alternative_id if best is not None else None,
            best_alternative_label=best.label if best is not None else None,
            main_risks_and_unknowns=decision.main_risks_and_unknowns,
            confidence=decision.confidence,
            what_would_change_the_decision=decision.change_conditions,
            portfolio_effect=fit_by_alternative[selected.alternative_id].effect,
            as_of=decision.as_of,
            input_fingerprint=decision.input_fingerprint,
        )

    @staticmethod
    def from_position_review(review: PositionReview) -> DecisionCard:
        return DecisionCard(
            card_id=uuid5(
                NAMESPACE_URL,
                f"asymmetric-insight-engine:decision-card:{review.review_id}",
            ),
            decision_record_id=review.review_id,
            action=DecisionCardAction.HOLD,
            evaluated_amount=None,
            selected_alternative_id=review.position_id,
            selected_alternative_label=review.position_id,
            why=review.rationale,
            best_alternative_id=None,
            best_alternative_label=None,
            main_risks_and_unknowns=review.main_risks_and_unknowns,
            confidence=review.confidence,
            what_would_change_the_decision=review.change_conditions,
            portfolio_effect=None,
            as_of=review.knowledge_boundary.as_of,
            input_fingerprint=review.input_fingerprint,
        )
