"""Read-only Chapter 7 projection over a verified Execution Plan."""

from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict

from asymmetric_engine.domain.evidence.models import ContentHash, NonEmptyString
from asymmetric_engine.domain.execution import (
    ExecutionAction,
    ExecutionLeg,
    ExecutionPlan,
    ExecutionReason,
    ExecutionSourceKind,
)
from asymmetric_engine.domain.financial import MonetaryAmount

EXECUTION_CARD_METHOD_VERSION = "execution-card-v1"


class ExecutionCard(BaseModel):
    """Compact operator projection with no execution or capital-decision logic."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    card_id: UUID
    method_version: NonEmptyString = EXECUTION_CARD_METHOD_VERSION
    execution_plan_id: UUID
    source_decision_id: UUID
    source_kind: ExecutionSourceKind
    action: ExecutionAction
    target_instrument_id: NonEmptyString
    approved_target_amount: MonetaryAmount
    source_instrument_id: NonEmptyString | None
    approved_source_sale_amount: MonetaryAmount | None
    reasons: tuple[ExecutionReason, ...]
    legs: tuple[ExecutionLeg, ...]
    missing_data: tuple[NonEmptyString, ...]
    as_of: datetime
    input_fingerprint: ContentHash


class ProjectExecutionCard:
    """Copy a verified Execution Plan into a stable read-only UI/API projection."""

    @staticmethod
    def from_execution_plan(plan: ExecutionPlan) -> ExecutionCard:
        card_id = uuid5(
            NAMESPACE_URL,
            (
                "asymmetric-insight-engine:execution-card:"
                f"{EXECUTION_CARD_METHOD_VERSION}:{plan.plan_id}"
            ),
        )
        return ExecutionCard(
            card_id=card_id,
            execution_plan_id=plan.plan_id,
            source_decision_id=plan.source.decision_id,
            source_kind=plan.source.source_kind,
            action=plan.action,
            target_instrument_id=plan.source.target_instrument_id,
            approved_target_amount=plan.source.target_amount,
            source_instrument_id=plan.source.source_instrument_id,
            approved_source_sale_amount=plan.source.source_sale_amount,
            reasons=plan.reasons,
            legs=plan.legs,
            missing_data=plan.missing_data,
            as_of=plan.as_of,
            input_fingerprint=plan.input_fingerprint,
        )
