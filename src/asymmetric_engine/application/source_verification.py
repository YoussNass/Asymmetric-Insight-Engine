"""Shared verification of immutable source-document bytes."""

from hashlib import sha256
from uuid import UUID

from asymmetric_engine.application.evidence_ingestion import SourceDocumentRepository
from asymmetric_engine.domain.evidence import SourceDocument


class SourceDocumentVerificationError(RuntimeError):
    """Base error for source material that cannot be verified."""


class SourceDocumentNotFoundError(SourceDocumentVerificationError):
    """Raised when an immutable source version is absent from the ledger."""


class SourceDocumentIntegrityError(SourceDocumentVerificationError):
    """Raised when stored bytes disagree with immutable source metadata."""


def load_verified_source_document(
    repository: SourceDocumentRepository,
    document_id: UUID,
) -> SourceDocument:
    """Load one source and fail closed on absence, byte-length drift, or hash drift."""

    try:
        document = repository.get(document_id)
        content = repository.read_content(document_id)
    except KeyError as error:
        raise SourceDocumentNotFoundError(
            f"source document {document_id} is missing from the evidence ledger"
        ) from error
    if len(content) != document.content_size_bytes:
        raise SourceDocumentIntegrityError(
            f"source document {document_id} byte length does not match its metadata"
        )
    if sha256(content).hexdigest() != document.content_hash:
        raise SourceDocumentIntegrityError(
            f"source document {document_id} SHA-256 does not match its metadata"
        )
    return document
