"""Tests for the Chapter 10 explicit local-file evidence adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from asymmetric_engine.application.evidence_ingestion import SourceProviderAccessError
from asymmetric_engine.domain.evidence import AvailabilityBasis, SourceType
from asymmetric_engine.infrastructure.providers.local_file import (
    LOCAL_MANUAL_PROVIDER,
    LocalFileEvidenceMetadata,
    LocalFileSourceProvider,
)


def _metadata() -> LocalFileEvidenceMetadata:
    return LocalFileEvidenceMetadata(
        provider_record_id="manual-report-001",
        provider_version="sha-declared-v1",
        subject_id="company:manual-test",
        title="Operator supplied source",
        source_uri="file-origin://research/manual-report-001",
        source_type=SourceType.RESEARCH,
        effective_at=datetime(2026, 9, 2, 7, 0, tzinfo=UTC),
        media_type="text/plain",
    )


def test_local_provider_preserves_exact_bytes_and_declared_metadata(tmp_path: Path) -> None:
    path = tmp_path / "source.txt"
    content = b"exact source bytes\nwith no transformation\n"
    path.write_bytes(content)

    draft = LocalFileSourceProvider(_metadata()).fetch(str(path))

    assert draft.provider == LOCAL_MANUAL_PROVIDER
    assert draft.provider_record_id == "manual-report-001"
    assert draft.provider_version == "sha-declared-v1"
    assert draft.subject_id == "company:manual-test"
    assert draft.source_uri == "file-origin://research/manual-report-001"
    assert draft.source_type is SourceType.RESEARCH
    assert draft.effective_at == datetime(2026, 9, 2, 7, 0, tzinfo=UTC)
    assert draft.media_type == "text/plain"
    assert draft.content == content


def test_local_provider_never_backdates_public_availability(tmp_path: Path) -> None:
    path = tmp_path / "source.txt"
    path.write_text("prospective source", encoding="utf-8")

    draft = LocalFileSourceProvider(_metadata()).fetch(str(path))

    assert draft.availability_basis is AvailabilityBasis.OBSERVED_AT_INGESTION
    assert draft.available_at is None


def test_local_provider_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SourceProviderAccessError, match="does not exist"):
        LocalFileSourceProvider(_metadata()).fetch(str(tmp_path / "missing.txt"))


def test_local_provider_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_bytes(b"")

    with pytest.raises(SourceProviderAccessError, match="is empty"):
        LocalFileSourceProvider(_metadata()).fetch(str(path))
