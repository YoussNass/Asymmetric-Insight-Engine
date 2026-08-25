"""Immutable source-document contracts for the point-in-time evidence ledger."""

from __future__ import annotations

from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from asymmetric_engine.domain.evidence.models import ContentHash, NonEmptyString, SourceType
from asymmetric_engine.domain.temporal import (
    KnowledgeBoundary,
    KnowledgeExclusionReason,
)

SubjectId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^[a-z][a-z0-9_-]*:[^\s]+$",
    ),
]


class SourceDocumentDraft(BaseModel):
    """Exact provider payload and immutable source-version metadata before ingestion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: NonEmptyString
    provider_record_id: NonEmptyString
    provider_version: NonEmptyString
    subject_id: SubjectId
    title: NonEmptyString
    source_uri: NonEmptyString
    source_type: SourceType
    effective_at: AwareDatetime
    available_at: AwareDatetime
    media_type: NonEmptyString = "application/octet-stream"
    content: bytes = Field(min_length=1, repr=False)


class SourceDocument(BaseModel):
    """Append-only metadata for one exact provider source version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: UUID
    provider: NonEmptyString
    provider_record_id: NonEmptyString
    provider_version: NonEmptyString
    subject_id: SubjectId
    title: NonEmptyString
    source_uri: NonEmptyString
    source_type: SourceType
    effective_at: AwareDatetime
    available_at: AwareDatetime
    recorded_at: AwareDatetime
    media_type: NonEmptyString
    content_hash: ContentHash
    content_size_bytes: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_ingestion_order(self) -> Self:
        """A source cannot be ingested before the provider made it available."""

        if self.recorded_at < self.available_at:
            raise ValueError("recorded_at must be greater than or equal to available_at")
        return self

    @property
    def source_key(self) -> tuple[str, str, str]:
        """Return the provider-owned identity of this exact source version."""

        return (self.provider, self.provider_record_id, self.provider_version)

    @property
    def immutable_signature(self) -> tuple[object, ...]:
        """Return fields that cannot change when the same version is ingested again."""

        return (
            self.document_id,
            *self.source_key,
            self.subject_id,
            self.title,
            self.source_uri,
            self.source_type,
            self.effective_at,
            self.available_at,
            self.media_type,
            self.content_hash,
            self.content_size_bytes,
        )

    def knowledge_exclusion_reason(
        self, boundary: KnowledgeBoundary
    ) -> KnowledgeExclusionReason | None:
        """Explain whether this source version belongs to a decision boundary."""

        return boundary.exclusion_reason(
            available_at=self.available_at,
            recorded_at=self.recorded_at,
        )

    def is_knowable_at(self, boundary: KnowledgeBoundary) -> bool:
        """Apply the canonical cross-domain temporal contract."""

        return self.knowledge_exclusion_reason(boundary) is None
