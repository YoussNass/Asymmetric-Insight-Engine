"""Controlled command-line boundary for diagnostics, evidence, and local product operations."""

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
    SourceProviderError,
)
from asymmetric_engine.application.evidence_operations import (
    IngestSourceDocuments,
    InspectKnowledgeCoverage,
    InvalidBatchInputError,
    VerifySourceDocument,
)
from asymmetric_engine.application.product_persistence import ListProductRecords, LoadProductRecord
from asymmetric_engine.domain.evidence import SourceDocument, SourceType
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode
from asymmetric_engine.infrastructure.clock import SystemClock
from asymmetric_engine.infrastructure.persistence import SQLiteSourceDocumentRepository
from asymmetric_engine.infrastructure.persistence.sqlite_product_store import (
    SQLiteProductRecordRepository,
)
from asymmetric_engine.infrastructure.providers import (
    LocalFileEvidenceMetadata,
    LocalFileSourceProvider,
    SecEdgarHttpFetcher,
    SecEdgarProvider,
)
from asymmetric_engine.interfaces.operator_workspace import OperatorWorkspace
from asymmetric_engine.interfaces.prospective_intake import (
    BuildCausalAnalysisRequest,
    BuildOpportunityStateRequest,
)
from asymmetric_engine.interfaces.workspace_web import serve_local_workspace
from asymmetric_engine.product_runtime import (
    LocalProductPaths,
    ProspectiveIntakeRequest,
    build_local_product_runtime,
    initialize_local_product_stores,
)

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
    ingest_local = evidence_commands.add_parser(
        "ingest-local",
        help="Ingest one explicit local source version with availability observed at ingestion.",
    )
    ingest_local.add_argument("--database", type=Path, required=True)
    ingest_local.add_argument("--file", type=Path, required=True)
    ingest_local.add_argument("--provider-record-id", required=True)
    ingest_local.add_argument("--provider-version", required=True)
    ingest_local.add_argument("--subject", required=True)
    ingest_local.add_argument("--title", required=True)
    ingest_local.add_argument("--source-uri", required=True)
    ingest_local.add_argument(
        "--source-type",
        choices=tuple(item.value for item in SourceType),
        required=True,
    )
    ingest_local.add_argument("--effective-at", type=_aware_datetime, required=True)
    ingest_local.add_argument("--media-type", default="application/octet-stream")
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

    workspace = subparsers.add_parser(
        "workspace",
        help="Open the local read-only operator workspace.",
    )
    workspace.add_argument("--database", type=Path, required=True)
    workspace.add_argument("--port", type=int, default=8765)

    product = subparsers.add_parser(
        "product",
        help="Operate the explicit prospective local product composition.",
    )
    product_commands = product.add_subparsers(dest="product_command", required=True)
    product_init = product_commands.add_parser(
        "init",
        help="Explicitly initialize evidence and immutable product stores.",
    )
    _add_product_store_arguments(product_init)
    product_workspace = product_commands.add_parser(
        "workspace",
        help="Open a write-enabled local workspace over configured canonical services.",
    )
    _add_product_store_arguments(product_workspace)
    product_workspace.add_argument("--port", type=int, default=8765)
    product_intake = product_commands.add_parser(
        "intake",
        help="Build and persist canonical Causal Analysis or Opportunity State from JSON input.",
    )
    _add_product_store_arguments(product_intake)
    product_intake.add_argument(
        "--operation",
        choices=("build_causal_analysis", "build_opportunity_state"),
        required=True,
    )
    product_intake.add_argument("--request", type=Path, required=True)
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


def _add_product_store_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--evidence-database", type=Path, required=True)
    parser.add_argument("--product-database", type=Path, required=True)


def doctor_payload() -> dict[str, str]:
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


def _product_paths(args: argparse.Namespace) -> LocalProductPaths:
    return LocalProductPaths(
        evidence_database=args.evidence_database,
        product_database=args.product_database,
    )


def _required_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise CliUsageError(f"{field} must not be empty")
    return normalized


def _existing_repository(database_path: Path) -> SQLiteSourceDocumentRepository:
    try:
        return SQLiteSourceDocumentRepository(database_path, initialize_schema=False)
    except (FileNotFoundError, sqlite3.Error, ValueError) as error:
        raise CliUsageError(str(error)) from error


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


def _run_ingest_local(args: argparse.Namespace) -> int:
    repository = _existing_repository(args.database)
    metadata = LocalFileEvidenceMetadata(
        provider_record_id=_required_text(args.provider_record_id, "provider-record-id"),
        provider_version=_required_text(args.provider_version, "provider-version"),
        subject_id=_required_text(args.subject, "subject"),
        title=_required_text(args.title, "title"),
        source_uri=_required_text(args.source_uri, "source-uri"),
        source_type=SourceType(args.source_type),
        effective_at=args.effective_at,
        media_type=_required_text(args.media_type, "media-type"),
    )
    result = IngestSourceDocument(
        provider=LocalFileSourceProvider(metadata),
        repository=repository,
        clock=SystemClock(),
    ).execute(str(args.file))
    print(
        json.dumps(
            {
                "command": "evidence.ingest_local",
                "document": _document_payload(result.document),
                "status": result.status.value,
            },
            sort_keys=True,
        )
    )
    return 0


def _run_list_documents(args: argparse.Namespace) -> int:
    boundary = _knowledge_boundary(args)
    subject_id = _required_text(args.subject, "subject")
    documents = ListSourceDocumentsAt(_existing_repository(args.database)).execute(
        subject_id=subject_id,
        boundary=boundary,
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
        subject_id=subject_id,
        boundary=boundary,
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


def _run_workspace(args: argparse.Namespace) -> int:
    try:
        repository = SQLiteProductRecordRepository(
            args.database,
            initialize_schema=False,
        )
    except (FileNotFoundError, sqlite3.Error, ValueError) as error:
        raise CliUsageError(str(error)) from error
    workspace = OperatorWorkspace(
        loader=LoadProductRecord(repository),
        lister=ListProductRecords(repository),
    )
    print(f"AIE read-only workspace: http://127.0.0.1:{args.port}")
    serve_local_workspace(workspace, port=args.port)
    return 0


def _run_product_init(args: argparse.Namespace) -> int:
    paths = _product_paths(args)
    initialize_local_product_stores(paths)
    print(
        json.dumps(
            {
                "command": "product.init",
                "evidence_database": str(paths.evidence_database),
                "product_database": str(paths.product_database),
                "status": "ok",
            },
            sort_keys=True,
        )
    )
    return 0


def _run_product_workspace(args: argparse.Namespace) -> int:
    runtime = build_local_product_runtime(_product_paths(args))
    print(f"AIE prospective workspace: http://127.0.0.1:{args.port}")
    serve_local_workspace(runtime.workspace, port=args.port)
    return 0


def _run_product_intake(args: argparse.Namespace) -> int:
    if not args.request.is_file():
        raise CliUsageError(f"intake request file does not exist: {args.request}")
    payload = args.request.read_text(encoding="utf-8")
    runtime = build_local_product_runtime(_product_paths(args))
    request: ProspectiveIntakeRequest
    if args.operation == "build_causal_analysis":
        request = BuildCausalAnalysisRequest.model_validate_json(payload)
    elif args.operation == "build_opportunity_state":
        request = BuildOpportunityStateRequest.model_validate_json(payload)
    else:  # pragma: no cover - argparse closes the set
        raise AssertionError(f"Unhandled intake operation: {args.operation}")
    if request.operation != args.operation:
        raise CliUsageError("intake request operation does not match --operation")
    submission = runtime.submit_intake(request)
    print(
        json.dumps(
            {
                "command": f"product.intake.{submission.operation}",
                "persisted": {
                    "kind": submission.persisted.envelope.kind.value,
                    "record_id": str(submission.persisted.envelope.record_id),
                    "status": submission.persisted.status.value,
                    "stored_at": submission.persisted.envelope.stored_at.isoformat(),
                },
                "response": submission.response.model_dump(mode="json"),
                "status": "ok",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _print_error(error: Exception) -> None:
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


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "doctor":
        print(json.dumps(doctor_payload(), sort_keys=True))
        return 0
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "workspace":
        try:
            return _run_workspace(args)
        except (CliUsageError, OSError, sqlite3.Error, ValueError) as error:
            _print_error(error)
            return 2
    if args.command == "product":
        try:
            if args.product_command == "init":
                return _run_product_init(args)
            if args.product_command == "workspace":
                return _run_product_workspace(args)
            if args.product_command == "intake":
                return _run_product_intake(args)
        except (CliUsageError, KeyError, OSError, sqlite3.Error, ValueError) as error:
            _print_error(error)
            return 2
    if args.command == "evidence":
        try:
            if args.evidence_command == "ingest-sec":
                return _run_ingest_sec(args)
            if args.evidence_command == "ingest-local":
                return _run_ingest_local(args)
            if args.evidence_command == "list":
                return _run_list_documents(args)
            if args.evidence_command == "coverage":
                return _run_coverage(args)
            if args.evidence_command == "verify":
                return _run_verify(args)
        except (
            CliUsageError,
            KeyError,
            OSError,
            SourceProviderError,
            sqlite3.Error,
            ValueError,
        ) as error:
            _print_error(error)
            return 2
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
