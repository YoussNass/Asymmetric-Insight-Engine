"""Application tests for provider ingestion and point-in-time source queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.evidence_ingestion import (
    AppendResult,
    AppendStatus,
    IngestSourceDocument,
    ListSourceDocumentsAt,
)
from asymmetric_engine.domain.evidence import (
    AvailabilityBasis,
    SourceDocument,
    SourceDocumentDraft,
    SourceType,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode
from tests.factories import BASE_TIME


@dataclass
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass
class StaticProvider:
    draft: SourceDocumentDraft
    requested_reference: str | None = None

    def fetch(self, reference: str) -> SourceDocumentDraft:
        self.requested_reference = reference
        return self.draft


class CapturingRepository:
    def __init__(self, documents: tuple[SourceDocument, ...] = ()) -> None:
        self.documents = documents
        self.appended: tuple[SourceDocument, bytes] | None = None

    def append(self, document: SourceDocument, content: bytes) -> AppendResult:
        self.appended = (document, content)
        return AppendResult(AppendStatus.INSERTED, document)

    def list_by_subject(self, subject_id: str) -> tuple[SourceDocument, ...]:
        return tuple(item for item in self.documents if item.subject_id == subject_id)

    def read_content(self, document_id: UUID) -> bytes:
        raise KeyError(document_id)


def make_draft(**overrides: object) -> SourceDocumentDraft:
    values: dict[str, object] = {
        "provider": "synthetic-filings",
        "provider_record_id": "TESTCO-2025-Q1",
        "provider_version": "original",
        "subject_id": "company:testco",
        "title": "TestCo first-quarter filing",
        "source_uri": "https://example.test/testco/2025-q1",
        "source_type": SourceType.FILING,
        "effective_at": BASE_TIME - timedelta(days=90),
        "availability_basis": AvailabilityBasis.PROVIDER_ASSERTED,
        "available_at": BASE_TIME - timedelta(days=1),
        "media_type": "application/json",
        "content": b'{"revenue": 125000000}',
    }
    values.update(overrides)
    return SourceDocumentDraft.model_validate(values)


def make_document(
    *,
    provider_version: str,
    available_at: datetime,
    recorded_at: datetime,
) -> SourceDocument:
    return SourceDocument(
        document_id=UUID(int=len(provider_version)),
        provider="synthetic-filings",
        provider_record_id="TESTCO-2025-Q1",
        provider_version=provider_version,
        subject_id="company:testco",
        title="TestCo first-quarter filing",
        source_uri=f"https://example.test/{provider_version}",
        source_type=SourceType.FILING,
        effective_at=BASE_TIME - timedelta(days=90),
        availability_basis=AvailabilityBasis.PROVIDER_ASSERTED,
        available_at=available_at,
        recorded_at=recorded_at,
        media_type="application/json",
        content_hash="a" * 64,
        content_size_bytes=24,
    )


def test_ingestion_hashes_exact_bytes_and_uses_the_injected_clock() -> None:
    draft = make_draft()
    provider = StaticProvider(draft)
    repository = CapturingRepository()
    service = IngestSourceDocument(
        provider=provider,
        repository=repository,
        clock=FixedClock(BASE_TIME),
    )

    result = service.execute("  testco-quarterly-filing  ")

    assert result.status is AppendStatus.INSERTED
    assert provider.requested_reference == "testco-quarterly-filing"
    assert repository.appended == (result.document, draft.content)
    assert result.document.recorded_at == BASE_TIME
    assert result.document.content_hash == (
        "776aed88babf55ebe24a840b464c92d9795770ba342665929a2cf8b63a51ac1c"
    )
    assert result.document.content_size_bytes == len(draft.content)


def test_source_identity_produces_a_stable_document_id() -> None:
    draft = make_draft()
    first = IngestSourceDocument(
        provider=StaticProvider(draft),
        repository=CapturingRepository(),
        clock=FixedClock(BASE_TIME),
    ).execute("same-source")
    second = IngestSourceDocument(
        provider=StaticProvider(draft),
        repository=CapturingRepository(),
        clock=FixedClock(BASE_TIME + timedelta(days=1)),
    ).execute("same-source")

    assert first.document.document_id == second.document.document_id


def test_query_applies_reconstruction_and_replay_boundaries() -> None:
    public_but_recorded_later = make_document(
        provider_version="original",
        available_at=BASE_TIME - timedelta(days=1),
        recorded_at=BASE_TIME + timedelta(days=1),
    )
    future_restatement = make_document(
        provider_version="restatement-1",
        available_at=BASE_TIME + timedelta(days=2),
        recorded_at=BASE_TIME + timedelta(days=2),
    )
    repository = CapturingRepository((future_restatement, public_but_recorded_later))
    query = ListSourceDocumentsAt(repository)

    reconstruction = query.execute(
        subject_id="company:testco",
        boundary=KnowledgeBoundary(
            as_of=BASE_TIME,
            knowledge_mode=KnowledgeMode.HISTORICAL_RECONSTRUCTION,
        ),
    )
    replay = query.execute(
        subject_id="company:testco",
        boundary=KnowledgeBoundary(
            as_of=BASE_TIME,
            knowledge_mode=KnowledgeMode.LIVE_SYSTEM_REPLAY,
        ),
    )

    assert reconstruction == (public_but_recorded_later,)
    assert replay == ()


def test_ingestion_and_query_reject_blank_identifiers() -> None:
    service = IngestSourceDocument(
        provider=StaticProvider(make_draft()),
        repository=CapturingRepository(),
        clock=FixedClock(BASE_TIME),
    )

    with pytest.raises(ValueError, match="reference"):
        service.execute("  ")
    with pytest.raises(ValueError, match="subject_id"):
        ListSourceDocumentsAt(CapturingRepository()).execute(
            subject_id=" ",
            boundary=KnowledgeBoundary(
                as_of=BASE_TIME,
                knowledge_mode=KnowledgeMode.HISTORICAL_RECONSTRUCTION,
            ),
        )


def test_source_contracts_reject_empty_content_and_impossible_ingestion_order() -> None:
    with pytest.raises(ValidationError, match="content"):
        make_draft(content=b"")
    with pytest.raises(ValidationError, match="subject_id"):
        make_draft(subject_id="TESTCO")
    with pytest.raises(ValidationError, match="recorded_at"):
        make_document(
            provider_version="impossible",
            available_at=BASE_TIME,
            recorded_at=BASE_TIME - timedelta(seconds=1),
        )


def test_observed_availability_uses_the_ingestion_clock_and_is_explicit() -> None:
    draft = make_draft(
        availability_basis=AvailabilityBasis.OBSERVED_AT_INGESTION,
        available_at=None,
    )
    result = IngestSourceDocument(
        provider=StaticProvider(draft),
        repository=CapturingRepository(),
        clock=FixedClock(BASE_TIME),
    ).execute("observed-source")

    assert result.document.availability_basis is AvailabilityBasis.OBSERVED_AT_INGESTION
    assert result.document.available_at == BASE_TIME
    assert result.document.recorded_at == BASE_TIME

    with pytest.raises(ValidationError, match="must not provide available_at"):
        make_draft(availability_basis=AvailabilityBasis.OBSERVED_AT_INGESTION)
    with pytest.raises(ValidationError, match="requires available_at"):
        make_draft(available_at=None)
