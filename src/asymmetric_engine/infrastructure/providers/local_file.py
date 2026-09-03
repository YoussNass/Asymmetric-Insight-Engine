"""Explicit local-file evidence provider for prospective manual source intake."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from asymmetric_engine.application.evidence_ingestion import SourceProviderAccessError
from asymmetric_engine.domain.evidence import (
    AvailabilityBasis,
    SourceDocumentDraft,
    SourceType,
)

LOCAL_MANUAL_PROVIDER = "local-manual"


@dataclass(frozen=True, slots=True)
class LocalFileEvidenceMetadata:
    """Operator-declared immutable metadata for one local source version."""

    provider_record_id: str
    provider_version: str
    subject_id: str
    title: str
    source_uri: str
    source_type: SourceType
    effective_at: datetime
    media_type: str = "application/octet-stream"


class LocalFileSourceProvider:
    """Read exact local bytes while conservatively observing availability at ingestion time."""

    def __init__(self, metadata: LocalFileEvidenceMetadata) -> None:
        self._metadata = metadata

    def fetch(self, reference: str) -> SourceDocumentDraft:
        path = Path(reference).expanduser()
        if not path.is_file():
            raise SourceProviderAccessError(f"local evidence file does not exist: {path}")
        try:
            content = path.read_bytes()
        except OSError as error:
            raise SourceProviderAccessError(f"cannot read local evidence file: {path}") from error
        if not content:
            raise SourceProviderAccessError(f"local evidence file is empty: {path}")
        metadata = self._metadata
        return SourceDocumentDraft(
            provider=LOCAL_MANUAL_PROVIDER,
            provider_record_id=metadata.provider_record_id,
            provider_version=metadata.provider_version,
            subject_id=metadata.subject_id,
            title=metadata.title,
            source_uri=metadata.source_uri,
            source_type=metadata.source_type,
            effective_at=metadata.effective_at,
            availability_basis=AvailabilityBasis.OBSERVED_AT_INGESTION,
            available_at=None,
            media_type=metadata.media_type,
            content=content,
        )


__all__ = [
    "LOCAL_MANUAL_PROVIDER",
    "LocalFileEvidenceMetadata",
    "LocalFileSourceProvider",
]
