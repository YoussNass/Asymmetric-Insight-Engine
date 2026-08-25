"""Controlled command-line boundary for diagnostics and source-evidence operations."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from asymmetric_engine import __version__
from asymmetric_engine.application.evidence_ingestion import (
    IngestSourceDocument,
    ListSourceDocumentsAt,
)
from asymmetric_engine.application.evidence_operations import (
    IngestSourceDocuments,
    InspectKnowledgeCoverage,
    InvalidBatchInputError,
    VerifySourceDocument,
)
from asymmetric_engine.domain.evidence import SourceDocument
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode
from asymmetric_engine.infrastructure.clock import SystemClock
from asymmetric_engine.infrastructure.persistence import SQLiteSourceDocumentRepository
from asymmetric_engine.infrastructure.providers import SecEdgarHttpFetcher, SecEdgarProvider

SEC_USER_AGENT_ENV = "AIE_SEC_USER_AGENT"


class CliUsageError(RuntimeError):
    """Expected invalid user configuration or command input."""


def _aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an ISO-8601 datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("must include a timezone offset")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="asymmetric-engine")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Validate the local package installation.")
    subparsers.add_parser("version", help="Print the package version.")

    evidence = subparsers.add_parser(
        "evidence",
        help="Operate the local append-only source-evidence ledger.",
    )
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)

    ingest_sec = evidence_commands.add_parser(
        "ingest-sec",
        help="Ingest exact SEC CIK/accession references sequentially.",
    )
    ingest_sec.add_argument("--database", type=Path, required=True)
    ingest_sec.add_argument("--reference", dest="references", action="append", required=True)

    list_documents = evidence_commands.add_parser(
        "list",
        help="List source versions knowable at a decision-time boundary.",
    )
    _add_knowledge_boundary_arguments(list_documents)

    coverage = evidence_commands.add_parser(
        "coverage",
        help="Report inclusion, exclusion, and temporal-provenance counts.",
    )
    _add_knowledge_boundary_arguments(coverage)

    verify = evidence_commands.add_parser(
        "verify",
        help="Recompute one stored source document's hash and byte size.",
    )
    verify.add_argument("--database", type=Path, required=True)
    verify.add_argument("--document-id", type=UUID, required=True)
    return parser


def _add_knowledge_boundary_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--as-of", type=_aware_datetime, required=True)
    parser.add_argument(
        "--knowledge-mode",
        choices=tuple(mode.value for mode in KnowledgeMode),
        required=True,
    )


def doctor_payload() -> dict[str, str]:
    """Return a deterministic, machine-readable installation diagnostic."""

    return {
        "package": "asymmetric-insight-engine",
        "python": platform.python_version(),
        "status": "ok",
        "version": __version__,
    }


def _document_payload(document: SourceDocument) -> dict[str, Any]:
    return {
        "availability_basis": document.availability_basis.value,
        "available_at": document.available_at.isoformat(),
        "content_hash": document.content_hash,
        "content_size_bytes": document.content_size_bytes,
        "document_id": str(document.document_id),
        "effective_at": document.effective_at.isoformat(),
        "media_type": document.media_type,
        "provider": document.provider,
        "provider_record_id": document.provider_record_id,
        "provider_version": document.provider_version,
        "recorded_at": document.recorded_at.isoformat(),
        "source_type": document.source_type.value,
        "source_uri": document.source_uri,
        "subject_id": document.subject_id,
        "title": document.title,
    }


def _knowledge_boundary(args: argparse.Namespace) -> KnowledgeBoundary:
    return KnowledgeBoundary(
        as_of=args.as_of,
        knowledge_mode=KnowledgeMode(args.knowledge_mode),
    )


def _required_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise CliUsageError(f"{field} must not be empty")
    return normalized


def _existing_repository(database_path: Path) -> SQLiteSourceDocumentRepository:
    if not database_path.is_file():
        raise CliUsageError(f"evidence database does not exist: {database_path}")
    return SQLiteSourceDocumentRepository(database_path, initialize_schema=False)


def _run_ingest_sec(args: argparse.Namespace) -> int:
    user_agent = os.environ.get(SEC_USER_AGENT_ENV, "").strip()
    if not user_agent:
        raise CliUsageError(f"{SEC_USER_AGENT_ENV} must identify the application and contact email")
    try:
        fetcher = SecEdgarHttpFetcher(user_agent=user_agent)
    except ValueError as error:
        raise CliUsageError(str(error)) from error
    try:
        references = IngestSourceDocuments.validate_references(tuple(args.references))
    except InvalidBatchInputError as error:
        raise CliUsageError(str(error)) from error
    repository = SQLiteSourceDocumentRepository(args.database)
    result = IngestSourceDocuments(
        IngestSourceDocument(
            provider=SecEdgarProvider(fetcher.fetch),
            repository=repository,
            clock=SystemClock(),
        )
    ).execute(references)

    outcomes: list[dict[str, Any]] = []
    for outcome in result.outcomes:
        if outcome.append_result is not None:
            outcomes.append(
                {
                    "document": _document_payload(outcome.append_result.document),
                    "reference": outcome.reference,
                    "status": outcome.append_result.status.value,
                }
            )
        else:
            outcomes.append(
                {
                    "failure_kind": outcome.failure_kind.value
                    if outcome.failure_kind is not None
                    else None,
                    "failure_message": outcome.failure_message,
                    "reference": outcome.reference,
                    "status": "failed",
                }
            )
    print(
        json.dumps(
            {
                "command": "evidence.ingest_sec",
                "failed": result.failed_count,
                "outcomes": outcomes,
                "succeeded": result.succeeded_count,
            },
            sort_keys=True,
        )
    )
    return 0 if result.failed_count == 0 else 2


def _run_list_documents(args: argparse.Namespace) -> int:
    boundary = _knowledge_boundary(args)
    subject_id = _required_text(args.subject, "subject")
    documents = ListSourceDocumentsAt(_existing_repository(args.database)).execute(
        subject_id=subject_id, boundary=boundary
    )
    print(
        json.dumps(
            {
                "as_of": boundary.as_of.isoformat(),
                "documents": [_document_payload(document) for document in documents],
                "knowledge_mode": boundary.knowledge_mode.value,
                "subject_id": subject_id,
            },
            sort_keys=True,
        )
    )
    return 0


def _run_coverage(args: argparse.Namespace) -> int:
    boundary = _knowledge_boundary(args)
    subject_id = _required_text(args.subject, "subject")
    report = InspectKnowledgeCoverage(_existing_repository(args.database)).execute(
        subject_id=subject_id, boundary=boundary
    )
    print(
        json.dumps(
            {
                "as_of": report.boundary.as_of.isoformat(),
                "included_versions": report.included_versions,
                "knowledge_mode": report.boundary.knowledge_mode.value,
                "observed_at_ingestion_versions": report.observed_at_ingestion_versions,
                "provider_asserted_versions": report.provider_asserted_versions,
                "record_not_ingested": report.record_not_ingested,
                "source_not_available": report.source_not_available,
                "subject_id": report.subject_id,
                "total_versions": report.total_versions,
                "warnings": report.warnings,
            },
            sort_keys=True,
        )
    )
    return 0


def _run_verify(args: argparse.Namespace) -> int:
    report = VerifySourceDocument(_existing_repository(args.database)).execute(args.document_id)
    print(
        json.dumps(
            {
                "actual_content_hash": report.actual_content_hash,
                "actual_content_size_bytes": report.actual_content_size_bytes,
                "document_id": str(report.document.document_id),
                "expected_content_hash": report.document.content_hash,
                "expected_content_size_bytes": report.document.content_size_bytes,
                "hash_matches": report.hash_matches,
                "size_matches": report.size_matches,
                "status": "ok" if report.is_valid else "corrupt",
            },
            sort_keys=True,
        )
    )
    return 0 if report.is_valid else 3


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit code."""

    args = _build_parser().parse_args(argv)
    if args.command == "doctor":
        print(json.dumps(doctor_payload(), sort_keys=True))
        return 0
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "evidence":
        try:
            if args.evidence_command == "ingest-sec":
                return _run_ingest_sec(args)
            if args.evidence_command == "list":
                return _run_list_documents(args)
            if args.evidence_command == "coverage":
                return _run_coverage(args)
            if args.evidence_command == "verify":
                return _run_verify(args)
        except (CliUsageError, KeyError, OSError, sqlite3.Error) as error:
            print(
                json.dumps(
                    {
                        "error": type(error).__name__,
                        "message": str(error),
                        "status": "error",
                    },
                    sort_keys=True,
                )
            )
            return 2
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
