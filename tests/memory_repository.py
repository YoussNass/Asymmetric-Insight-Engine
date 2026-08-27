"""Small in-memory implementation of the source-document repository test port."""

from dataclasses import dataclass
from uuid import UUID

from asymmetric_engine.application.evidence_ingestion import AppendResult, AppendStatus
from asymmetric_engine.domain.evidence import SourceDocument


@dataclass
class MemorySourceRepository:
    documents: dict[UUID, SourceDocument]
    contents: dict[UUID, bytes]

    def append(self, document: SourceDocument, content: bytes) -> AppendResult:
        status = (
            AppendStatus.ALREADY_PRESENT
            if document.document_id in self.documents
            else AppendStatus.INSERTED
        )
        self.documents[document.document_id] = document
        self.contents[document.document_id] = content
        return AppendResult(status=status, document=document)

    def list_by_subject(self, subject_id: str) -> tuple[SourceDocument, ...]:
        return tuple(
            document for document in self.documents.values() if document.subject_id == subject_id
        )

    def get(self, document_id: UUID) -> SourceDocument:
        try:
            return self.documents[document_id]
        except KeyError as error:
            raise KeyError(document_id) from error

    def read_content(self, document_id: UUID) -> bytes:
        try:
            return self.contents[document_id]
        except KeyError as error:
            raise KeyError(document_id) from error
