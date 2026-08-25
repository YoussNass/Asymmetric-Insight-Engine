"""Provider and persistence ports for the first temporal-evidence vertical slice."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from asymmetric_engine.domain.evidence import (
    AvailabilityBasis,
    SourceDocument,
    SourceDocumentDraft,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary


class AppendStatus(StrEnum):
    """Whether an immutable source version was newly recorded or already present."""

    INSERTED = "inserted"
    ALREADY_PRESENT = "already_present"


@dataclass(frozen=True, slots=True)
class AppendResult:
    """Repository result that preserves the canonical first-ingestion record."""

    status: AppendStatus
    document: SourceDocument


class SourceVersionConflictError(RuntimeError):
    """Raised when a provider reuses one version identity for different content or metadata."""


class Clock(Protocol):
    """Injectable ingestion clock."""

    def now(self) -> datetime:
        """Return the current timezone-aware timestamp."""


class SourceDocumentProvider(Protocol):
    """Replaceable provider that returns one exact, versioned source payload."""

    def fetch(self, reference: str) -> SourceDocumentDraft:
        """Fetch a provider record without normalising away its version identity."""


class SourceDocumentRepository(Protocol):
    """Append-only evidence-ledger persistence port."""

    def append(self, document: SourceDocument, content: bytes) -> AppendResult:
        """Atomically insert or identify an idempotent re-ingestion."""

    def list_by_subject(self, subject_id: str) -> tuple[SourceDocument, ...]:
        """Return every stored version for a canonical subject identity."""

    def read_content(self, document_id: UUID) -> bytes:
        """Return the exact immutable payload used to compute the content hash."""


class IngestSourceDocument:
    """Fetch, fingerprint, timestamp, and append one provider source version."""

    def __init__(
        self,
        *,
        provider: SourceDocumentProvider,
        repository: SourceDocumentRepository,
        clock: Clock,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._clock = clock

    def execute(self, reference: str) -> AppendResult:
        """Ingest the referenced source while preserving its exact bytes and identity."""

        normalized_reference = reference.strip()
        if not normalized_reference:
            raise ValueError("reference must not be empty")
        draft = self._provider.fetch(normalized_reference)
        recorded_at = self._clock.now()
        available_at = (
            recorded_at
            if draft.availability_basis is AvailabilityBasis.OBSERVED_AT_INGESTION
            else draft.available_at
        )
        if available_at is None:  # pragma: no cover - guarded by the domain contract
            raise ValueError("source draft does not establish an availability boundary")
        identity = json.dumps(
            (draft.provider, draft.provider_record_id, draft.provider_version),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        document = SourceDocument(
            document_id=uuid5(NAMESPACE_URL, identity),
            provider=draft.provider,
            provider_record_id=draft.provider_record_id,
            provider_version=draft.provider_version,
            subject_id=draft.subject_id,
            title=draft.title,
            source_uri=draft.source_uri,
            source_type=draft.source_type,
            effective_at=draft.effective_at,
            availability_basis=draft.availability_basis,
            available_at=available_at,
            recorded_at=recorded_at,
            media_type=draft.media_type,
            content_hash=sha256(draft.content).hexdigest(),
            content_size_bytes=len(draft.content),
        )
        return self._repository.append(document, draft.content)


class ListSourceDocumentsAt:
    """Query stored source versions through the canonical knowledge boundary."""

    def __init__(self, repository: SourceDocumentRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        subject_id: str,
        boundary: KnowledgeBoundary,
    ) -> tuple[SourceDocument, ...]:
        """Return only source versions knowable under the selected mode and as-of date."""

        normalized_subject_id = subject_id.strip()
        if not normalized_subject_id:
            raise ValueError("subject_id must not be empty")
        included = (
            document
            for document in self._repository.list_by_subject(normalized_subject_id)
            if document.is_knowable_at(boundary)
        )
        return tuple(
            sorted(
                included,
                key=lambda item: (
                    item.available_at,
                    item.recorded_at,
                    item.provider,
                    item.provider_record_id,
                    item.provider_version,
                ),
            )
        )
