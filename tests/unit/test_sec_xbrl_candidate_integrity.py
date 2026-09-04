"""Integrity regression tests for content-addressed SEC XBRL candidate sets."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from hashlib import sha256
from uuid import UUID

import pytest

from asymmetric_engine.application.evidence_ingestion import AppendResult
from asymmetric_engine.application.sec_xbrl_extraction import (
    ExtractSecXbrlCandidates,
    ProcessorXbrlFact,
    SecXbrlCandidateSet,
    SecXbrlExtractionError,
    SecXbrlPeriodKind,
    validate_sec_xbrl_candidate_set_integrity,
)
from asymmetric_engine.domain.evidence import (
    AvailabilityBasis,
    SourceDocument,
    SourceType,
)

CONTENT = b"<SEC-DOCUMENT>candidate integrity fixture</SEC-DOCUMENT>"
DOCUMENT_ID = UUID("44444444-4444-4444-4444-444444444444")


class FakeRepository:
    def __init__(self) -> None:
        observed_at = datetime(2025, 2, 1, 12, 0, tzinfo=UTC)
        self.document = SourceDocument(
            document_id=DOCUMENT_ID,
            provider="sec-edgar",
            provider_record_id="0000320193:10-K:20241228",
            provider_version="0000320193-25-000010",
            subject_id="company:sec-cik-0000320193",
            title="Integrity fixture — 10-K",
            source_uri="https://www.sec.gov/Archives/edgar/data/integrity-fixture.txt",
            source_type=SourceType.FILING,
            effective_at=datetime(2024, 12, 28, tzinfo=UTC),
            availability_basis=AvailabilityBasis.OBSERVED_AT_INGESTION,
            available_at=observed_at,
            recorded_at=observed_at,
            media_type="text/plain",
            content_hash=sha256(CONTENT).hexdigest(),
            content_size_bytes=len(CONTENT),
        )

    def append(self, document: SourceDocument, content: bytes) -> AppendResult:
        raise AssertionError("append is not used")

    def list_by_subject(self, subject_id: str) -> tuple[SourceDocument, ...]:
        return (self.document,) if subject_id == self.document.subject_id else ()

    def get(self, document_id: UUID) -> SourceDocument:
        if document_id != DOCUMENT_ID:
            raise KeyError(document_id)
        return self.document

    def read_content(self, document_id: UUID) -> bytes:
        if document_id != DOCUMENT_ID:
            raise KeyError(document_id)
        return CONTENT


class FakeProcessor:
    processor_name = "fixture-xbrl"
    processor_version = "1.0.0"

    def extract(self, *, content: bytes, source_uri: str) -> tuple[ProcessorXbrlFact, ...]:
        assert content == CONTENT
        assert source_uri
        return (
            ProcessorXbrlFact(
                concept_namespace="http://fasb.org/us-gaap/2024",
                concept_name="Revenues",
                context_id="FY2024",
                period_kind=SecXbrlPeriodKind.DURATION,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
                unit_id="USD",
                unit_numerator=("{http://www.xbrl.org/2003/iso4217}USD",),
                unit_denominator=(),
                dimensions=(),
                decimals="-6",
                precision=None,
                raw_value="1000000000",
                is_numeric=True,
                is_nil=False,
                source_locator="annual.htm#revenue",
            ),
        )


def extracted_set() -> SecXbrlCandidateSet:
    return ExtractSecXbrlCandidates(
        repository=FakeRepository(),
        processor=FakeProcessor(),
    ).execute(DOCUMENT_ID)


def test_extractor_output_revalidates_content_addresses() -> None:
    result = extracted_set()

    validate_sec_xbrl_candidate_set_integrity(result)


def test_candidate_payload_tampering_is_detected_before_admission() -> None:
    result = extracted_set()
    tampered_candidate = replace(result.candidates[0], raw_value="999000000000")
    tampered_set = replace(result, candidates=(tampered_candidate,))

    with pytest.raises(SecXbrlExtractionError, match="content address"):
        validate_sec_xbrl_candidate_set_integrity(tampered_set)


def test_candidate_lineage_drift_is_detected_before_admission() -> None:
    result = extracted_set()
    drifted_candidate = replace(result.candidates[0], accession="0000320193-25-999999")
    drifted_set = replace(result, candidates=(drifted_candidate,))

    with pytest.raises(SecXbrlExtractionError, match="accession drifted"):
        validate_sec_xbrl_candidate_set_integrity(drifted_set)


def test_set_fingerprint_and_extraction_id_tampering_are_detected() -> None:
    result = extracted_set()

    with pytest.raises(SecXbrlExtractionError, match="fingerprint"):
        validate_sec_xbrl_candidate_set_integrity(
            replace(result, input_fingerprint="0" * 64)
        )
    with pytest.raises(SecXbrlExtractionError, match="extraction id"):
        validate_sec_xbrl_candidate_set_integrity(
            replace(result, extraction_id=UUID("55555555-5555-5555-5555-555555555555"))
        )
