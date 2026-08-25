"""Controlled batch, integrity, and coverage operations over source evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Protocol, Self
from uuid import UUID

from asymmetric_engine.application.evidence_ingestion import (
    AppendResult,
    InvalidSourceReferenceError,
    SourceDocumentRepository,
    SourceProviderAccessError,
    SourceProviderPayloadError,
    SourceVersionConflictError,
    UnsupportedSourceError,
)
from asymmetric_engine.domain.evidence import AvailabilityBasis, SourceDocument
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeExclusionReason


class SourceDocumentIngestion(Protocol):
    """Single-reference ingestion boundary used by controlled batch orchestration."""

    def execute(self, reference: str) -> AppendResult:
        """Ingest one exact source reference."""


class BatchFailureKind(StrEnum):
    """Stable, machine-readable categories for expected ingestion failures."""

    INVALID_REFERENCE = "invalid_reference"
    PROVIDER_ACCESS = "provider_access"
    PROVIDER_PAYLOAD = "provider_payload"
    UNSUPPORTED_SOURCE = "unsupported_source"
    VERSION_CONFLICT = "version_conflict"


class InvalidBatchInputError(ValueError):
    """Raised when a controlled batch is empty, ambiguous, or contains duplicates."""


@dataclass(frozen=True, slots=True)
class BatchIngestionOutcome:
    """Result for one exact reference in a sequential controlled batch."""

    reference: str
    append_result: AppendResult | None = None
    failure_kind: BatchFailureKind | None = None
    failure_message: str | None = None

    def __post_init__(self) -> None:
        if not self.reference.strip():
            raise ValueError("outcome reference must not be empty")
        if self.append_result is not None:
            valid = self.failure_kind is None and self.failure_message is None
        else:
            valid = self.failure_kind is not None and self.failure_message is not None
        if not valid:
            raise ValueError("outcome must contain exactly one success or complete failure")

    @classmethod
    def success(cls, *, reference: str, result: AppendResult) -> Self:
        return cls(reference=reference, append_result=result)

    @classmethod
    def failure(
        cls,
        *,
        reference: str,
        kind: BatchFailureKind,
        message: str,
    ) -> Self:
        return cls(reference=reference, failure_kind=kind, failure_message=message)

    @property
    def succeeded(self) -> bool:
        return self.append_result is not None


@dataclass(frozen=True, slots=True)
class BatchIngestionResult:
    """Complete outcome set; expected failures remain visible rather than aborting the batch."""

    outcomes: tuple[BatchIngestionOutcome, ...]

    def __post_init__(self) -> None:
        if not self.outcomes:
            raise ValueError("batch result requires at least one outcome")
        references = tuple(outcome.reference for outcome in self.outcomes)
        if len(references) != len(set(references)):
            raise ValueError("batch result cannot contain duplicate references")

    @property
    def succeeded_count(self) -> int:
        return sum(outcome.succeeded for outcome in self.outcomes)

    @property
    def failed_count(self) -> int:
        return len(self.outcomes) - self.succeeded_count


class IngestSourceDocuments:
    """Ingest unique exact references sequentially and classify expected boundary failures."""

    def __init__(self, ingestion: SourceDocumentIngestion) -> None:
        self._ingestion = ingestion

    @staticmethod
    def _classify_failure(error: Exception) -> BatchFailureKind:
        if isinstance(error, UnsupportedSourceError):
            return BatchFailureKind.UNSUPPORTED_SOURCE
        if isinstance(error, SourceProviderAccessError):
            return BatchFailureKind.PROVIDER_ACCESS
        if isinstance(error, SourceProviderPayloadError):
            return BatchFailureKind.PROVIDER_PAYLOAD
        if isinstance(error, SourceVersionConflictError):
            return BatchFailureKind.VERSION_CONFLICT
        if isinstance(error, InvalidSourceReferenceError):
            return BatchFailureKind.INVALID_REFERENCE
        raise AssertionError(f"unclassified ingestion failure: {type(error).__name__}")

    def execute(self, references: tuple[str, ...]) -> BatchIngestionResult:
        """Continue across expected provider failures without hiding programming defects."""

        normalized = tuple(reference.strip() for reference in references)
        if not normalized or any(not reference for reference in normalized):
            raise InvalidBatchInputError("at least one non-empty reference is required")
        if len(normalized) != len(set(normalized)):
            raise InvalidBatchInputError("duplicate references are not allowed")

        expected_errors = (
            InvalidSourceReferenceError,
            SourceProviderAccessError,
            SourceProviderPayloadError,
            UnsupportedSourceError,
            SourceVersionConflictError,
        )
        outcomes: list[BatchIngestionOutcome] = []
        for reference in normalized:
            try:
                append_result = self._ingestion.execute(reference)
            except expected_errors as error:
                outcomes.append(
                    BatchIngestionOutcome.failure(
                        reference=reference,
                        kind=self._classify_failure(error),
                        message=str(error),
                    )
                )
            else:
                outcomes.append(
                    BatchIngestionOutcome.success(
                        reference=reference,
                        result=append_result,
                    )
                )
        return BatchIngestionResult(tuple(outcomes))


@dataclass(frozen=True, slots=True)
class SourceIntegrityReport:
    """Deterministic verification of stored bytes against immutable metadata."""

    document: SourceDocument
    actual_content_hash: str
    actual_content_size_bytes: int

    @property
    def hash_matches(self) -> bool:
        return self.actual_content_hash == self.document.content_hash

    @property
    def size_matches(self) -> bool:
        return self.actual_content_size_bytes == self.document.content_size_bytes

    @property
    def is_valid(self) -> bool:
        return self.hash_matches and self.size_matches


class VerifySourceDocument:
    """Re-read exact bytes and verify the ledger's immutable fingerprint."""

    def __init__(self, repository: SourceDocumentRepository) -> None:
        self._repository = repository

    def execute(self, document_id: UUID) -> SourceIntegrityReport:
        document = self._repository.get(document_id)
        content = self._repository.read_content(document_id)
        return SourceIntegrityReport(
            document=document,
            actual_content_hash=sha256(content).hexdigest(),
            actual_content_size_bytes=len(content),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeCoverageReport:
    """Visibility report for all known versions at one decision-time boundary."""

    subject_id: str
    boundary: KnowledgeBoundary
    total_versions: int
    included_versions: int
    source_not_available: int
    record_not_ingested: int
    provider_asserted_versions: int
    observed_at_ingestion_versions: int
    warnings: tuple[str, ...]


class InspectKnowledgeCoverage:
    """Count included and excluded known versions without claiming universe completeness."""

    def __init__(self, repository: SourceDocumentRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        subject_id: str,
        boundary: KnowledgeBoundary,
    ) -> KnowledgeCoverageReport:
        normalized_subject_id = subject_id.strip()
        if not normalized_subject_id:
            raise ValueError("subject_id must not be empty")

        documents = self._repository.list_by_subject(normalized_subject_id)
        reasons = tuple(document.knowledge_exclusion_reason(boundary) for document in documents)
        included_versions = sum(reason is None for reason in reasons)
        source_not_available = sum(
            reason is KnowledgeExclusionReason.SOURCE_NOT_AVAILABLE for reason in reasons
        )
        record_not_ingested = sum(
            reason is KnowledgeExclusionReason.RECORD_NOT_INGESTED for reason in reasons
        )
        provider_asserted_versions = sum(
            document.availability_basis is AvailabilityBasis.PROVIDER_ASSERTED
            for document in documents
        )
        observed_at_ingestion_versions = sum(
            document.availability_basis is AvailabilityBasis.OBSERVED_AT_INGESTION
            for document in documents
        )

        warnings: list[str] = []
        if not documents:
            warnings.append("no_source_versions_recorded")
        if observed_at_ingestion_versions:
            warnings.append("historical_publication_time_unverified")
        return KnowledgeCoverageReport(
            subject_id=normalized_subject_id,
            boundary=boundary,
            total_versions=len(documents),
            included_versions=included_versions,
            source_not_available=source_not_available,
            record_not_ingested=record_not_ingested,
            provider_asserted_versions=provider_asserted_versions,
            observed_at_ingestion_versions=observed_at_ingestion_versions,
            warnings=tuple(warnings),
        )
