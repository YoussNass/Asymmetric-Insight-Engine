"""Canonical state passed from underwriting to portfolio construction."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from asymmetric_engine.domain.evidence import Claim, EvidenceItem
from asymmetric_engine.domain.temporal import (
    KnowledgeBoundary,
    KnowledgeExclusionReason,
    KnowledgeMode,
)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ThesisSummary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20)]


class OpportunityStatus(StrEnum):
    """Research readiness state; portfolio allocation remains a downstream decision."""

    OBSERVE = "observe"
    INVESTIGATE = "investigate"
    ELIGIBLE = "eligible"
    READY_FOR_PORTFOLIO_REVIEW = "ready_for_portfolio_review"
    INVALIDATED = "invalidated"


class OpportunityState(BaseModel):
    """Immutable point-in-time opportunity contract shared with downstream engines."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: UUID = Field(default_factory=uuid4)
    candidate_id: NonEmptyString
    as_of: AwareDatetime
    knowledge_mode: KnowledgeMode
    status: OpportunityStatus
    thesis_summary: ThesisSummary
    evidence: tuple[EvidenceItem, ...]
    claims: tuple[Claim, ...]
    invalidation_conditions: tuple[NonEmptyString, ...]
    missing_data: tuple[NonEmptyString, ...] = ()
    invalidation_reason: NonEmptyString | None = None

    @field_validator("invalidation_conditions", "missing_data")
    @classmethod
    def reject_duplicate_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Do not let repeated warnings create artificial weight."""

        if len(value) != len(set(value)):
            raise ValueError("duplicate entries are not allowed")
        return value

    @model_validator(mode="after")
    def validate_point_in_time_and_references(self) -> Self:
        """Enforce provenance, temporal availability, and readiness invariants."""

        boundary = KnowledgeBoundary(
            as_of=self.as_of,
            knowledge_mode=self.knowledge_mode,
        )

        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("duplicate evidence records are not allowed")

        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("duplicate claim records are not allowed")

        exclusions = {
            item.evidence_id: item.knowledge_exclusion_reason(boundary) for item in self.evidence
        }
        future_evidence = [
            evidence_id
            for evidence_id, reason in exclusions.items()
            if reason is KnowledgeExclusionReason.SOURCE_NOT_AVAILABLE
        ]
        if future_evidence:
            raise ValueError("opportunity contains evidence unavailable at as_of")

        unrecorded_evidence = [
            evidence_id
            for evidence_id, reason in exclusions.items()
            if reason is KnowledgeExclusionReason.RECORD_NOT_INGESTED
        ]
        if unrecorded_evidence:
            raise ValueError("live replay contains evidence not recorded at as_of")

        known_ids = set(evidence_ids)
        referenced_ids = {
            evidence_id for claim in self.claims for evidence_id in claim.evidence_ids
        }
        if not referenced_ids.issubset(known_ids):
            raise ValueError("claim references evidence absent from the opportunity")

        review_ready_statuses = {
            OpportunityStatus.ELIGIBLE,
            OpportunityStatus.READY_FOR_PORTFOLIO_REVIEW,
        }
        if self.status in review_ready_statuses:
            if not self.evidence or not self.claims:
                raise ValueError("review-ready opportunities require evidence and claims")
            if not self.invalidation_conditions:
                raise ValueError("review-ready opportunities require invalidation conditions")

        if self.status is OpportunityStatus.INVALIDATED and self.invalidation_reason is None:
            raise ValueError("invalidated opportunities require an invalidation_reason")
        if (
            self.status is not OpportunityStatus.INVALIDATED
            and self.invalidation_reason is not None
        ):
            raise ValueError("only invalidated opportunities may have an invalidation_reason")

        return self
