"""Point-in-time evidence and claim contracts."""

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

from asymmetric_engine.domain.temporal import (
    KnowledgeBoundary,
    KnowledgeExclusionReason,
)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ContentHash = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[0-9a-f]{64}$",
    ),
]


class SourceType(StrEnum):
    """High-level provenance category for an evidence record."""

    FILING = "filing"
    TRANSCRIPT = "transcript"
    MARKET_DATA = "market_data"
    GOVERNMENT = "government"
    COMPANY_RELEASE = "company_release"
    NEWS = "news"
    RESEARCH = "research"
    OTHER = "other"


class ClaimType(StrEnum):
    """Epistemic class required by the system constitution."""

    OBSERVATION = "observation"
    STATISTICAL_RESULT = "statistical_result"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    QUALITATIVE_JUDGEMENT = "qualitative_judgement"


class Confidence(BaseModel):
    """A bounded confidence assessment with an explicit rationale."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    score: float = Field(ge=0.0, le=1.0)
    rationale: NonEmptyString


class DataQuality(BaseModel):
    """Independent quality dimensions; absence is never converted into false precision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    coverage: float = Field(ge=0.0, le=1.0)
    source_reliability: float = Field(ge=0.0, le=1.0)
    point_in_time_integrity: float = Field(ge=0.0, le=1.0)
    missing_fields: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()

    @field_validator("missing_fields", "conflicts")
    @classmethod
    def reject_duplicate_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Reject duplicate warnings rather than hiding them during normalization."""

        if len(value) != len(set(value)):
            raise ValueError("duplicate entries are not allowed")
        return value


class EvidenceItem(BaseModel):
    """An immutable fact payload with bitemporal provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: UUID = Field(default_factory=uuid4)
    title: NonEmptyString
    source_uri: NonEmptyString
    source_type: SourceType
    effective_at: AwareDatetime
    available_at: AwareDatetime
    recorded_at: AwareDatetime
    content_hash: ContentHash
    quality: DataQuality

    @model_validator(mode="after")
    def validate_ingestion_order(self) -> Self:
        """Information cannot be recorded before it became available to the system."""

        if self.recorded_at < self.available_at:
            raise ValueError("recorded_at must be greater than or equal to available_at")
        return self

    def knowledge_exclusion_reason(
        self, boundary: KnowledgeBoundary
    ) -> KnowledgeExclusionReason | None:
        """Explain whether this evidence was knowable inside a decision boundary."""

        return boundary.exclusion_reason(
            available_at=self.available_at,
            recorded_at=self.recorded_at,
        )

    def is_knowable_at(self, boundary: KnowledgeBoundary) -> bool:
        """Apply the shared temporal contract rather than context-specific filtering."""

        return self.knowledge_exclusion_reason(boundary) is None


class Claim(BaseModel):
    """A sourced statement kept distinct from the evidence payload itself."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: UUID = Field(default_factory=uuid4)
    text: NonEmptyString
    claim_type: ClaimType
    evidence_ids: tuple[UUID, ...]
    confidence: Confidence
    invalidation_condition: NonEmptyString

    @field_validator("evidence_ids")
    @classmethod
    def require_unique_evidence(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        """Every material claim requires explicit, non-duplicated provenance."""

        if not value:
            raise ValueError("at least one evidence_id is required")
        if len(value) != len(set(value)):
            raise ValueError("duplicate evidence_ids are not allowed")
        return value
