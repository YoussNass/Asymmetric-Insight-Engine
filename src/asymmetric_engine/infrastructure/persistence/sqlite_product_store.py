"""SQLite reference adapter for the Chapter 9B immutable product-record store."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import UUID

from asymmetric_engine.application.product_persistence import (
    PRODUCT_RECORD_ENVELOPE_VERSION,
    ProductAppendResult,
    ProductAppendStatus,
    ProductRecordConflictError,
    ProductRecordEnvelope,
    ProductRecordKind,
    ProductRecordSchemaError,
)

PRODUCT_TABLE = "product_records"
METADATA_TABLE = "product_store_metadata"
DATABASE_SCHEMA_VERSION = "1"


class SQLiteProductRecordRepository:
    """File-backed append-only reference storage for immutable product records."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        initialize_schema: bool = True,
    ) -> None:
        self._database_path = str(database_path)
        if self._database_path == ":memory:":
            raise ValueError("SQLite product store requires a file-backed database")
        if initialize_schema:
            self._initialize_schema()
        else:
            self._require_existing_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {METADATA_TABLE} (
                    metadata_key TEXT PRIMARY KEY,
                    metadata_value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS {PRODUCT_TABLE} (
                    record_id TEXT PRIMARY KEY,
                    envelope_version TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    stored_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE (kind, schema_version, payload_sha256)
                );

                CREATE INDEX IF NOT EXISTS idx_product_records_kind_stored
                ON {PRODUCT_TABLE} (kind, stored_at, record_id);

                CREATE TRIGGER IF NOT EXISTS product_records_no_update
                BEFORE UPDATE ON {PRODUCT_TABLE}
                BEGIN
                    SELECT RAISE(ABORT, 'product record store is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS product_records_no_delete
                BEFORE DELETE ON {PRODUCT_TABLE}
                BEGIN
                    SELECT RAISE(ABORT, 'product record store is append-only');
                END;
                """
            )
            row = connection.execute(
                f"SELECT metadata_value FROM {METADATA_TABLE} WHERE metadata_key = ?",
                ("database_schema_version",),
            ).fetchone()
            if row is None:
                connection.execute(
                    f"INSERT INTO {METADATA_TABLE} (metadata_key, metadata_value) VALUES (?, ?)",
                    ("database_schema_version", DATABASE_SCHEMA_VERSION),
                )
            elif row["metadata_value"] != DATABASE_SCHEMA_VERSION:
                raise ProductRecordSchemaError(
                    "SQLite product store schema requires an explicit migration: "
                    f"found {row['metadata_value']!r}, expected {DATABASE_SCHEMA_VERSION!r}"
                )

    def _require_existing_schema(self) -> None:
        path = Path(self._database_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        with closing(self._connect()) as connection:
            try:
                row = connection.execute(
                    f"SELECT metadata_value FROM {METADATA_TABLE} WHERE metadata_key = ?",
                    ("database_schema_version",),
                ).fetchone()
            except sqlite3.OperationalError as exc:
                raise ProductRecordSchemaError("SQLite product store schema is not initialized") from exc
        if row is None or row["metadata_value"] != DATABASE_SCHEMA_VERSION:
            found = None if row is None else row["metadata_value"]
            raise ProductRecordSchemaError(
                "SQLite product store schema requires an explicit migration: "
                f"found {found!r}, expected {DATABASE_SCHEMA_VERSION!r}"
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ProductRecordEnvelope:
        return ProductRecordEnvelope(
            envelope_version=row["envelope_version"],
            record_id=UUID(row["record_id"]),
            kind=ProductRecordKind(row["kind"]),
            schema_version=row["schema_version"],
            payload_sha256=row["payload_sha256"],
            stored_at=datetime.fromisoformat(row["stored_at"]),
            payload_json=row["payload_json"],
        )

    def append(self, envelope: ProductRecordEnvelope) -> ProductAppendResult:
        """Append one record while preserving the first stored_at on idempotent retries."""

        if envelope.envelope_version != PRODUCT_RECORD_ENVELOPE_VERSION:
            raise ProductRecordSchemaError("unsupported product record envelope version")

        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_row = connection.execute(
                f"SELECT * FROM {PRODUCT_TABLE} WHERE record_id = ?",
                (str(envelope.record_id),),
            ).fetchone()
            if existing_row is not None:
                existing = self._from_row(existing_row)
                if (
                    existing.envelope_version != envelope.envelope_version
                    or existing.kind is not envelope.kind
                    or existing.schema_version != envelope.schema_version
                    or existing.payload_sha256 != envelope.payload_sha256
                    or existing.payload_json != envelope.payload_json
                ):
                    raise ProductRecordConflictError(
                        "immutable product record identity was reused with conflicting content"
                    )
                return ProductAppendResult(ProductAppendStatus.ALREADY_PRESENT, existing)

            duplicate_row = connection.execute(
                f"""
                SELECT * FROM {PRODUCT_TABLE}
                WHERE kind = ? AND schema_version = ? AND payload_sha256 = ?
                """,
                (envelope.kind.value, envelope.schema_version, envelope.payload_sha256),
            ).fetchone()
            if duplicate_row is not None:
                existing = self._from_row(duplicate_row)
                if existing.payload_json != envelope.payload_json:
                    raise ProductRecordConflictError(
                        "product payload hash collision detected for different canonical JSON"
                    )
                if existing.record_id != envelope.record_id:
                    raise ProductRecordConflictError(
                        "identical product payload resolved to a different content-addressed id"
                    )
                return ProductAppendResult(ProductAppendStatus.ALREADY_PRESENT, existing)

            connection.execute(
                f"""
                INSERT INTO {PRODUCT_TABLE} (
                    record_id,
                    envelope_version,
                    kind,
                    schema_version,
                    payload_sha256,
                    stored_at,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(envelope.record_id),
                    envelope.envelope_version,
                    envelope.kind.value,
                    envelope.schema_version,
                    envelope.payload_sha256,
                    envelope.stored_at.isoformat(),
                    envelope.payload_json,
                ),
            )
        return ProductAppendResult(ProductAppendStatus.INSERTED, envelope)

    def get(self, record_id: UUID) -> ProductRecordEnvelope:
        """Return one immutable stored envelope by content-addressed id."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                f"SELECT * FROM {PRODUCT_TABLE} WHERE record_id = ?",
                (str(record_id),),
            ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return self._from_row(row)

    def list_by_kind(self, kind: ProductRecordKind) -> tuple[ProductRecordEnvelope, ...]:
        """Return one record kind in deterministic first-storage order."""

        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM {PRODUCT_TABLE}
                WHERE kind = ?
                ORDER BY stored_at, record_id
                """,
                (kind.value,),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)


__all__ = [
    "DATABASE_SCHEMA_VERSION",
    "SQLiteProductRecordRepository",
]
