"""Read-only Decision Card projection over verified Portfolio Decision records."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, model_validator

from asymmetric_engine.domain.evidence.models import ContentHash, NonEmptyString
from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.portfolio import (
    CapitalAlternative,
    DecisionConfidence,
    FitCurrencyEffect,
    MarginalDecision,
    MarginalDecisionOutcome,
    PolicyConstrainedMarginalDecision,
    PolicyDecisionOutcome,
    PortfolioFit,
    PositionReview,
    ReplacementDecision,
    ReplacementOutcome,
)

DECISION_CARD_METHOD_VERSION = "decision-card-v2"


class DecisionCardAction(StrEnum):
    """User-facing capital action without execution authority."""

    ALLOCATE = "allocate"
    HOLD = "hold"
    REPLACE = "replace"
    NO_ALLOCATION = "no_allocation"


class DecisionCardExecutionStatus(StrEnum):
    """Chapter 6 cannot decide timing or order staging."""

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
    source_position_id: NonEmptyString | None = None
    gross_sale_amount: MonetaryAmount | None = None
    switching_friction: MonetaryAmount | None = None
    execution_status: DecisionCardExecutionStatus = DecisionCardExecutionStatus.NOT_EVALUATED
    as_of: datetime
    input_fingerprint: ContentHash

    @model_validator(mode="after")
    def validate_projection_shape(self) -> DecisionCard:
        if self.method_version != DECISION_CARD_METHOD_VERSION:
            raise ValueError("Decision Card uses an unrecognized method version")
        if (self.best_alternative_id is None) != (self.best_alternative_label is None):
            raise ValueError("best alternative id and label must be present together")
        replacement_fields = (
            self.source_position_id,
            self.gross_sale_amount,
            self.switching_friction,
        )
        if self.action in {DecisionCardAction.ALLOCATE, DecisionCardAction.NO_ALLOCATION}:
            if self.evaluated_amount is None or self.portfolio_effect is None:
                raise ValueError("new-capital Decision Card requires amount and Portfolio Fit")
            if any(item is not None for item in replacement_fields):
                raise ValueError("new-capital Decision Card cannot contain replacement fields")
        elif self.action is DecisionCardAction.REPLACE:
            if self.evaluated_amount is None:
                raise ValueError("REPLACE requires the net redeployable amount")
            if self.source_position_id is None or self.gross_sale_amount is None:
                raise ValueError("REPLACE requires source position and gross sale amount")
            if self.switching_friction is None:
                raise ValueError("REPLACE requires complete switching friction")
            if self.portfolio_effect is not None:
                raise ValueError("6C2 replacement has no synthetic Portfolio Fit")
        else:
            if self.evaluated_amount is not None or self.portfolio_effect is not None:
                raise ValueError("HOLD cannot contain a deployed amount or Portfolio Fit")
            if self.source_position_id is None:
                if self.gross_sale_amount is not None or self.switching_friction is not None:
                    raise ValueError("ordinary HOLD cannot contain replacement-only fields")
            elif self.gross_sale_amount is None:
                raise ValueError("replacement HOLD requires its explicit gross sale amount")
        if self.execution_status is not DecisionCardExecutionStatus.NOT_EVALUATED:
            raise ValueError("Chapter 6 cannot emit an execution state")
        return self


class ProjectDecisionCard:
    """Copy an already-decided state into a stable UI/API view without financial logic."""

    @staticmethod
    def _verified_fit_maps(
        decision: MarginalDecision,
        fits: tuple[PortfolioFit, ...],
    ) -> tuple[dict[str, PortfolioFit], dict[str, CapitalAlternative]]:
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
        return fit_by_alternative, alternatives

    @staticmethod
    def from_marginal_decision(
        decision: MarginalDecision,
        fits: tuple[PortfolioFit, ...],
    ) -> DecisionCard:
        fit_by_alternative, alternatives = ProjectDecisionCard._verified_fit_maps(decision, fits)
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
    def from_policy_constrained_decision(
        policy_decision: PolicyConstrainedMarginalDecision,
        source_decision: MarginalDecision,
        fits: tuple[PortfolioFit, ...],
    ) -> DecisionCard:
        if (
            policy_decision.source_decision_id != source_decision.decision_id
            or policy_decision.source_decision_fingerprint != source_decision.input_fingerprint
            or policy_decision.knowledge_boundary != source_decision.knowledge_boundary
        ):
            raise ValueError("policy Decision Card received the wrong 6C1 source decision")
        fit_by_alternative, alternatives = ProjectDecisionCard._verified_fit_maps(
            source_decision, fits
        )
        selected = alternatives[policy_decision.selected_alternative_id]
        blocked = tuple(
            reason
            for item in policy_decision.blocked_alternatives
            for reason in item.reasons
        )
        risks = tuple(dict.fromkeys((*source_decision.main_risks_and_unknowns, *blocked)))
        action = (
            DecisionCardAction.ALLOCATE
            if policy_decision.outcome is PolicyDecisionOutcome.ALLOCATE
            else DecisionCardAction.NO_ALLOCATION
        )
        return DecisionCard(
            card_id=uuid5(
                NAMESPACE_URL,
                f"asymmetric-insight-engine:decision-card:{policy_decision.policy_decision_id}",
            ),
            decision_record_id=policy_decision.policy_decision_id,
            action=action,
            evaluated_amount=source_decision.capital_unit.amount,
            selected_alternative_id=selected.alternative_id,
            selected_alternative_label=selected.label,
            why=source_decision.decision_rationale,
            best_alternative_id=source_decision.best_rejected_alternative_id,
            best_alternative_label=(
                alternatives[source_decision.best_rejected_alternative_id].label
                if source_decision.best_rejected_alternative_id is not None
                else None
            ),
            main_risks_and_unknowns=risks,
            confidence=source_decision.confidence,
            what_would_change_the_decision=source_decision.change_conditions,
            portfolio_effect=fit_by_alternative[selected.alternative_id].effect,
            as_of=policy_decision.knowledge_boundary.as_of,
            input_fingerprint=policy_decision.input_fingerprint,
        )

    @staticmethod
    def from_replacement_decision(decision: ReplacementDecision) -> DecisionCard:
        replacing = decision.outcome is ReplacementOutcome.REPLACE
        action = DecisionCardAction.REPLACE if replacing else DecisionCardAction.HOLD
        selected_id = decision.target.target_id if replacing else decision.source_position_id
        selected_label = decision.target.label if replacing else decision.source_position_id
        best_id = decision.source_position_id if replacing else decision.target.target_id
        best_label = decision.source_position_id if replacing else decision.target.label
        return DecisionCard(
            card_id=uuid5(
                NAMESPACE_URL,
                f"asymmetric-insight-engine:decision-card:{decision.replacement_decision_id}",
            ),
            decision_record_id=decision.replacement_decision_id,
            action=action,
            evaluated_amount=decision.net_redeployable_amount if replacing else None,
            selected_alternative_id=selected_id,
            selected_alternative_label=selected_label,
            why=decision.decision_rationale,
            best_alternative_id=best_id,
            best_alternative_label=best_label,
            main_risks_and_unknowns=decision.main_risks_and_unknowns,
            confidence=decision.confidence,
            what_would_change_the_decision=decision.change_conditions,
            portfolio_effect=None,
            source_position_id=decision.source_position_id,
            gross_sale_amount=decision.gross_sale_amount,
            switching_friction=decision.total_switching_friction,
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
