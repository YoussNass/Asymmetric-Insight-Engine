"""SQLite reference adapter for the append-only evidence-source ledger."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from asymmetric_engine.application.evidence_ingestion import (
    AppendResult,
    AppendStatus,
    SourceVersionConflictError,
)
from asymmetric_engine.domain.evidence import AvailabilityBasis, SourceDocument, SourceType

TABLE_NAME = "evidence_source_documents"


class SQLiteSourceDocumentRepository:
    """Persist exact payloads and immutable metadata atomically for local use and tests."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        initialize_schema: bool = True,
    ) -> None:
        self._database_path = str(database_path)
        if self._database_path == ":memory:":
            raise ValueError("SQLite evidence ledger requires a file-backed database")
        if initialize_schema:
            self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    document_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    provider_record_id TEXT NOT NULL,
                    provider_version TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    effective_at TEXT NOT NULL,
                    availability_basis TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    content_size_bytes INTEGER NOT NULL CHECK (content_size_bytes > 0),
                    content BLOB NOT NULL,
                    UNIQUE (provider, provider_record_id, provider_version)
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_source_subject
                ON {TABLE_NAME} (subject_id, available_at, recorded_at);

                CREATE TRIGGER IF NOT EXISTS evidence_source_no_update
                BEFORE UPDATE ON {TABLE_NAME}
                BEGIN
                    SELECT RAISE(ABORT, 'evidence source ledger is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS evidence_source_no_delete
                BEFORE DELETE ON {TABLE_NAME}
                BEGIN
                    SELECT RAISE(ABORT, 'evidence source ledger is append-only');
                END;
                """
            )
            columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
            }
            if "availability_basis" not in columns:
                connection.execute(
                    f"ALTER TABLE {TABLE_NAME} ADD COLUMN availability_basis TEXT NOT NULL "
                    f"DEFAULT '{AvailabilityBasis.PROVIDER_ASSERTED.value}'"
                )

    @staticmethod
    def _serialize_datetime(value: datetime) -> str:
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _document_from_row(row: sqlite3.Row) -> SourceDocument:
        return SourceDocument(
            document_id=UUID(row["document_id"]),
            provider=row["provider"],
            provider_record_id=row["provider_record_id"],
            provider_version=row["provider_version"],
            subject_id=row["subject_id"],
            title=row["title"],
            source_uri=row["source_uri"],
            source_type=SourceType(row["source_type"]),
            effective_at=datetime.fromisoformat(row["effective_at"]),
            availability_basis=AvailabilityBasis(row["availability_basis"]),
            available_at=datetime.fromisoformat(row["available_at"]),
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
            media_type=row["media_type"],
            content_hash=row["content_hash"],
            content_size_bytes=row["content_size_bytes"],
        )

    def append(self, document: SourceDocument, content: bytes) -> AppendResult:
        """Atomically preserve a new version or return the identical existing version."""

        if len(content) != document.content_size_bytes:
            raise ValueError("content size does not match source-document metadata")
        if sha256(content).hexdigest() != document.content_hash:
            raise ValueError("content hash does not match source-document metadata")

        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_row = connection.execute(
                f"""
                SELECT * FROM {TABLE_NAME}
                WHERE provider = ? AND provider_record_id = ? AND provider_version = ?
                """,
                document.source_key,
            ).fetchone()
            if existing_row is not None:
                existing = self._document_from_row(existing_row)
                existing_content = bytes(existing_row["content"])
                if (
                    existing.immutable_signature != document.immutable_signature
                    or existing_content != content
                ):
                    raise SourceVersionConflictError(
                        "provider source-version identity was reused with different "
                        "content or metadata"
                    )
                return AppendResult(AppendStatus.ALREADY_PRESENT, existing)

            connection.execute(
                f"""
                INSERT INTO {TABLE_NAME} (
                    document_id,
                    provider,
                    provider_record_id,
                    provider_version,
                    subject_id,
                    title,
                    source_uri,
                    source_type,
                    effective_at,
                    availability_basis,
                    available_at,
                    recorded_at,
                    media_type,
                    content_hash,
                    content_size_bytes,
                    content
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(document.document_id),
                    document.provider,
                    document.provider_record_id,
                    document.provider_version,
                    document.subject_id,
                    document.title,
                    document.source_uri,
                    document.source_type.value,
                    self._serialize_datetime(document.effective_at),
                    document.availability_basis.value,
                    self._serialize_datetime(document.available_at),
                    self._serialize_datetime(document.recorded_at),
                    document.media_type,
                    document.content_hash,
                    document.content_size_bytes,
                    content,
                ),
            )
        return AppendResult(AppendStatus.INSERTED, document)

    def list_by_subject(self, subject_id: str) -> tuple[SourceDocument, ...]:
        """Return all immutable source versions for a subject without time filtering."""

        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                f"""
                SELECT * FROM {TABLE_NAME}
                WHERE subject_id = ?
                ORDER BY available_at, recorded_at, provider, provider_record_id, provider_version
                """,
                (subject_id,),
            ).fetchall()
        return tuple(self._document_from_row(row) for row in rows)

    def get(self, document_id: UUID) -> SourceDocument:
        """Return immutable metadata for one exact source document."""

        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                f"SELECT * FROM {TABLE_NAME} WHERE document_id = ?",
                (str(document_id),),
            ).fetchone()
        if row is None:
            raise KeyError(document_id)
        return self._document_from_row(row)

    def read_content(self, document_id: UUID) -> bytes:
        """Return exact source bytes for audit and deterministic reprocessing."""

        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                f"SELECT content FROM {TABLE_NAME} WHERE document_id = ?",
                (str(document_id),),
            ).fetchone()
        if row is None:
            raise KeyError(document_id)
        return bytes(row["content"])
