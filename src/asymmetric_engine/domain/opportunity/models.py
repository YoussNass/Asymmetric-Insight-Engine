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

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ThesisSummary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20)]


class OpportunityStatus(StrEnum):
    """Research and capital-readiness state; it is not a buy/sell signal."""

    OBSERVE = "observe"
    INVESTIGATE = "investigate"
    ELIGIBLE = "eligible"
    ALLOCATABLE = "allocatable"
    INVALIDATED = "invalidated"


class OpportunityState(BaseModel):
    """Immutable point-in-time opportunity contract shared with downstream engines."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: UUID = Field(default_factory=uuid4)
    candidate_id: NonEmptyString
    as_of: AwareDatetime
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

        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("duplicate evidence records are not allowed")

        future_evidence = [
            item.evidence_id for item in self.evidence if item.available_at > self.as_of
        ]
        if future_evidence:
            raise ValueError("opportunity contains evidence unavailable at as_of")

        known_ids = set(evidence_ids)
        referenced_ids = {
            evidence_id for claim in self.claims for evidence_id in claim.evidence_ids
        }
        if not referenced_ids.issubset(known_ids):
            raise ValueError("claim references evidence absent from the opportunity")

        if self.status in {OpportunityStatus.ELIGIBLE, OpportunityStatus.ALLOCATABLE}:
            if not self.evidence or not self.claims:
                raise ValueError("capital-ready opportunities require evidence and claims")
            if not self.invalidation_conditions:
                raise ValueError("capital-ready opportunities require invalidation conditions")

        if self.status is OpportunityStatus.INVALIDATED and self.invalidation_reason is None:
            raise ValueError("invalidated opportunities require an invalidation_reason")
        if (
            self.status is not OpportunityStatus.INVALIDATED
            and self.invalidation_reason is not None
        ):
            raise ValueError("only invalidated opportunities may have an invalidation_reason")

        return self
