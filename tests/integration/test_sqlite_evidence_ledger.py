"""Integration tests for the SQLite append-only evidence ledger."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from asymmetric_engine.application.evidence_ingestion import (
    AppendStatus,
    IngestSourceDocument,
    ListSourceDocumentsAt,
    SourceVersionConflictError,
)
from asymmetric_engine.domain.evidence import (
    AvailabilityBasis,
    SourceDocumentDraft,
    SourceType,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode
from asymmetric_engine.infrastructure.persistence import SQLiteSourceDocumentRepository
from asymmetric_engine.infrastructure.persistence.sqlite_evidence_ledger import TABLE_NAME
from tests.factories import BASE_TIME


@dataclass
class MutableClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass
class MutableProvider:
    draft: SourceDocumentDraft

    def fetch(self, reference: str) -> SourceDocumentDraft:
        assert reference == "testco-q1"
        return self.draft


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


def build_service(
    database_path: Path,
    *,
    draft: SourceDocumentDraft,
    clock: MutableClock,
) -> tuple[IngestSourceDocument, SQLiteSourceDocumentRepository]:
    repository = SQLiteSourceDocumentRepository(database_path)
    return (
        IngestSourceDocument(
            provider=MutableProvider(draft),
            repository=repository,
            clock=clock,
        ),
        repository,
    )


def test_sqlite_round_trip_preserves_exact_content_across_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "evidence-ledger.sqlite3"
    service, repository = build_service(
        database_path,
        draft=make_draft(),
        clock=MutableClock(BASE_TIME),
    )

    inserted = service.execute("testco-q1")
    restarted = SQLiteSourceDocumentRepository(database_path)

    assert inserted.status is AppendStatus.INSERTED
    assert restarted.list_by_subject("company:testco") == (inserted.document,)
    assert restarted.get(inserted.document.document_id) == inserted.document
    assert restarted.read_content(inserted.document.document_id) == make_draft().content
    with pytest.raises(KeyError):
        repository.read_content(inserted.document.document_id.__class__(int=0))
    with pytest.raises(KeyError):
        repository.get(inserted.document.document_id.__class__(int=0))


def test_reingestion_is_idempotent_and_preserves_first_recorded_at(tmp_path: Path) -> None:
    clock = MutableClock(BASE_TIME)
    service, repository = build_service(
        tmp_path / "evidence-ledger.sqlite3",
        draft=make_draft(),
        clock=clock,
    )
    first = service.execute("testco-q1")
    clock.value = BASE_TIME + timedelta(days=3)

    second = service.execute("testco-q1")

    assert first.status is AppendStatus.INSERTED
    assert second.status is AppendStatus.ALREADY_PRESENT
    assert second.document == first.document
    assert repository.list_by_subject("company:testco") == (first.document,)


def test_reused_provider_version_with_different_content_is_a_conflict(tmp_path: Path) -> None:
    clock = MutableClock(BASE_TIME)
    provider = MutableProvider(make_draft())
    repository = SQLiteSourceDocumentRepository(tmp_path / "evidence-ledger.sqlite3")
    service = IngestSourceDocument(provider=provider, repository=repository, clock=clock)
    service.execute("testco-q1")
    provider.draft = make_draft(content=b'{"revenue": 999000000}')

    with pytest.raises(SourceVersionConflictError, match="identity was reused"):
        service.execute("testco-q1")
    provider.draft = make_draft(title="A changed title for the same provider version")
    with pytest.raises(SourceVersionConflictError, match="identity was reused"):
        service.execute("testco-q1")


def test_restatement_is_a_new_version_and_cannot_leak_backwards(tmp_path: Path) -> None:
    clock = MutableClock(BASE_TIME)
    provider = MutableProvider(make_draft())
    repository = SQLiteSourceDocumentRepository(tmp_path / "evidence-ledger.sqlite3")
    service = IngestSourceDocument(provider=provider, repository=repository, clock=clock)
    original = service.execute("testco-q1").document

    restatement_time = BASE_TIME + timedelta(days=30)
    clock.value = restatement_time
    provider.draft = make_draft(
        provider_version="restatement-1",
        available_at=restatement_time,
        content=b'{"revenue": 124000000}',
    )
    restatement = service.execute("testco-q1").document
    query = ListSourceDocumentsAt(repository)

    before_restatement = query.execute(
        subject_id="company:testco",
        boundary=KnowledgeBoundary(
            as_of=BASE_TIME,
            knowledge_mode=KnowledgeMode.HISTORICAL_RECONSTRUCTION,
        ),
    )
    after_restatement = query.execute(
        subject_id="company:testco",
        boundary=KnowledgeBoundary(
            as_of=restatement_time,
            knowledge_mode=KnowledgeMode.LIVE_SYSTEM_REPLAY,
        ),
    )

    assert before_restatement == (original,)
    assert after_restatement == (original, restatement)


def test_sqlite_schema_rejects_updates_and_deletes(tmp_path: Path) -> None:
    database_path = tmp_path / "evidence-ledger.sqlite3"
    service, _ = build_service(
        database_path,
        draft=make_draft(),
        clock=MutableClock(BASE_TIME),
    )
    inserted = service.execute("testco-q1")

    with sqlite3.connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                f"UPDATE {TABLE_NAME} SET title = 'Changed' WHERE document_id = ?",
                (str(inserted.document.document_id),),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                f"DELETE FROM {TABLE_NAME} WHERE document_id = ?",
                (str(inserted.document.document_id),),
            )


def test_repository_defends_content_metadata_and_file_backing(tmp_path: Path) -> None:
    content = make_draft().content
    service, repository = build_service(
        tmp_path / "evidence-ledger.sqlite3",
        draft=make_draft(),
        clock=MutableClock(BASE_TIME),
    )
    document = service.execute("testco-q1").document

    with pytest.raises(ValueError, match="size"):
        repository.append(
            document.model_copy(update={"content_size_bytes": len(content) + 1}),
            content,
        )
    with pytest.raises(ValueError, match="hash"):
        repository.append(
            document.model_copy(update={"content_hash": "f" * 64}),
            content,
        )
    with pytest.raises(ValueError, match="file-backed"):
        SQLiteSourceDocumentRepository(":memory:")


def test_repository_adds_availability_provenance_to_a_first_slice_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "first-slice.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"""
            CREATE TABLE {TABLE_NAME} (
                document_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                provider_record_id TEXT NOT NULL,
                provider_version TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                title TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                source_type TEXT NOT NULL,
                effective_at TEXT NOT NULL,
                available_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                media_type TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                content_size_bytes INTEGER NOT NULL CHECK (content_size_bytes > 0),
                content BLOB NOT NULL,
                UNIQUE (provider, provider_record_id, provider_version)
            )
            """
        )

    SQLiteSourceDocumentRepository(database_path)

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        }
    assert "availability_basis" in columns
