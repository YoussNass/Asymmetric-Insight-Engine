"""Tests for Chapter 11B shadow-only XBRL extraction."""

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
    SecXbrlAuthority,
    SecXbrlDimension,
    SecXbrlExtractionError,
    SecXbrlPeriodKind,
)
from asymmetric_engine.application.source_verification import SourceDocumentIntegrityError
from asymmetric_engine.domain.evidence import (
    AvailabilityBasis,
    SourceDocument,
    SourceType,
)
from asymmetric_engine.infrastructure.providers.arelle_xbrl import (
    ARELLE_PINNED_VERSION,
    ArelleBridgeError,
    ArelleVersionMismatchError,
    PinnedArelleProcessorBridge,
    SecCompleteSubmissionEntryPointExtractor,
)


CONTENT = b"<SEC-DOCUMENT>verified filing bytes</SEC-DOCUMENT>"
DOCUMENT_ID = UUID("11111111-1111-1111-1111-111111111111")


def source_document(*, provider: str = "sec-edgar") -> SourceDocument:
    observed_at = datetime(2025, 2, 1, 12, 0, tzinfo=UTC)
    return SourceDocument(
        document_id=DOCUMENT_ID,
        provider=provider,
        provider_record_id="0000320193:10-K:20241228",
        provider_version="0000320193-25-000010",
        subject_id="company:sec-cik-0000320193",
        title="Apple Inc. — 10-K for 20241228",
        source_uri=(
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019325000010/0000320193-25-000010.txt"
        ),
        source_type=SourceType.FILING,
        effective_at=datetime(2024, 12, 28, tzinfo=UTC),
        availability_basis=AvailabilityBasis.OBSERVED_AT_INGESTION,
        available_at=observed_at,
        recorded_at=observed_at,
        media_type="text/plain",
        content_hash=sha256(CONTENT).hexdigest(),
        content_size_bytes=len(CONTENT),
    )


class FakeRepository:
    def __init__(self, document: SourceDocument, content: bytes = CONTENT) -> None:
        self.document = document
        self.content = content

    def append(self, document: SourceDocument, content: bytes) -> AppendResult:
        raise AssertionError("append is not used by shadow extraction")

    def list_by_subject(self, subject_id: str) -> tuple[SourceDocument, ...]:
        return (self.document,) if subject_id == self.document.subject_id else ()

    def get(self, document_id: UUID) -> SourceDocument:
        if document_id != self.document.document_id:
            raise KeyError(document_id)
        return self.document

    def read_content(self, document_id: UUID) -> bytes:
        if document_id != self.document.document_id:
            raise KeyError(document_id)
        return self.content


def revenue_fact() -> ProcessorXbrlFact:
    return ProcessorXbrlFact(
        concept_namespace="http://fasb.org/us-gaap/2024",
        concept_name="RevenueFromContractWithCustomerExcludingAssessedTax",
        context_id="FY2024",
        period_kind=SecXbrlPeriodKind.DURATION,
        period_start=date(2023, 10, 1),
        period_end=date(2024, 9, 28),
        unit_id="USD",
        unit_numerator=("{http://www.xbrl.org/2003/iso4217}USD",),
        unit_denominator=(),
        dimensions=(),
        decimals="-6",
        precision=None,
        raw_value="391035000000",
        is_numeric=True,
        is_nil=False,
        source_locator="annual.htm#fact-42",
    )


def cash_fact() -> ProcessorXbrlFact:
    return ProcessorXbrlFact(
        concept_namespace="http://fasb.org/us-gaap/2024",
        concept_name="CashAndCashEquivalentsAtCarryingValue",
        context_id="I2024",
        period_kind=SecXbrlPeriodKind.INSTANT,
        period_start=None,
        period_end=date(2024, 9, 28),
        unit_id="USD",
        unit_numerator=("{http://www.xbrl.org/2003/iso4217}USD",),
        unit_denominator=(),
        dimensions=(
            SecXbrlDimension(
                axis_namespace="http://example.com/entity/2024",
                axis_name="BusinessUnitAxis",
                member_namespace="http://example.com/entity/2024",
                member_name="CorporateMember",
            ),
        ),
        decimals="-6",
        precision=None,
        raw_value="29943000000",
        is_numeric=True,
        is_nil=False,
        source_locator="annual.htm#fact-99",
    )


class FakeProcessor:
    processor_name = "fixture-xbrl"
    processor_version = "1.0.0"

    def __init__(self, facts: tuple[ProcessorXbrlFact, ...]) -> None:
        self.facts = facts
        self.calls: list[tuple[bytes, str]] = []

    def extract(self, *, content: bytes, source_uri: str) -> tuple[ProcessorXbrlFact, ...]:
        self.calls.append((content, source_uri))
        return self.facts


def test_shadow_extraction_is_deterministic_and_order_independent() -> None:
    repository = FakeRepository(source_document())
    first_processor = FakeProcessor((revenue_fact(), cash_fact()))
    second_processor = FakeProcessor((cash_fact(), revenue_fact()))

    first = ExtractSecXbrlCandidates(
        repository=repository,
        processor=first_processor,
    ).execute(DOCUMENT_ID)
    second = ExtractSecXbrlCandidates(
        repository=repository,
        processor=second_processor,
    ).execute(DOCUMENT_ID)

    assert first == second
    assert first.authority is SecXbrlAuthority.SHADOW_ONLY
    assert first.warnings == ("shadow_extraction_not_admitted_for_underwriting",)
    assert first.source_content_hash == sha256(CONTENT).hexdigest()
    assert first.accession == "0000320193-25-000010"
    assert len(first.candidates) == 2
    assert all(item.authority is SecXbrlAuthority.SHADOW_ONLY for item in first.candidates)
    assert all(item.source_document_id == DOCUMENT_ID for item in first.candidates)
    assert first_processor.calls[0][0] == CONTENT


def test_shadow_candidate_preserves_context_unit_dimension_and_versions() -> None:
    processor = FakeProcessor((cash_fact(),))
    result = ExtractSecXbrlCandidates(
        repository=FakeRepository(source_document()),
        processor=processor,
    ).execute(DOCUMENT_ID)

    candidate = result.candidates[0]
    assert candidate.concept_name == "CashAndCashEquivalentsAtCarryingValue"
    assert candidate.period_kind is SecXbrlPeriodKind.INSTANT
    assert candidate.period_start is None
    assert candidate.period_end == date(2024, 9, 28)
    assert candidate.unit_numerator == ("{http://www.xbrl.org/2003/iso4217}USD",)
    assert candidate.dimensions[0].axis_name == "BusinessUnitAxis"
    assert candidate.processor_name == "fixture-xbrl"
    assert candidate.processor_version == "1.0.0"
    assert candidate.extraction_version == "sec-xbrl-shadow-v1"
    assert candidate.source_locator == "annual.htm#fact-99"


def test_shadow_extraction_rejects_duplicate_processor_facts() -> None:
    fact = revenue_fact()
    with pytest.raises(SecXbrlExtractionError, match="duplicate XBRL facts"):
        ExtractSecXbrlCandidates(
            repository=FakeRepository(source_document()),
            processor=FakeProcessor((fact, fact)),
        ).execute(DOCUMENT_ID)


@pytest.mark.parametrize(
    ("fact", "message"),
    [
        (
            replace(revenue_fact(), period_start=None),
            "duration XBRL context requires period_start",
        ),
        (
            replace(
                revenue_fact(),
                period_start=date(2025, 1, 1),
                period_end=date(2024, 1, 1),
            ),
            "reversed dates",
        ),
        (
            replace(cash_fact(), period_start=date(2024, 1, 1)),
            "instant XBRL context",
        ),
        (
            replace(revenue_fact(), unit_numerator=()),
            "numeric XBRL fact requires a unit numerator",
        ),
        (
            replace(revenue_fact(), is_nil=True),
            "nil XBRL fact",
        ),
        (
            replace(
                cash_fact(),
                dimensions=(cash_fact().dimensions[0], cash_fact().dimensions[0]),
            ),
            "duplicate dimension axes",
        ),
        (
            replace(
                cash_fact(),
                dimensions=(
                    replace(cash_fact().dimensions[0], member_namespace=None),
                ),
            ),
            "explicit XBRL dimensions require",
        ),
    ],
)
def test_shadow_extraction_fails_closed_on_invalid_processor_semantics(
    fact: ProcessorXbrlFact,
    message: str,
) -> None:
    with pytest.raises(SecXbrlExtractionError, match=message):
        ExtractSecXbrlCandidates(
            repository=FakeRepository(source_document()),
            processor=FakeProcessor((fact,)),
        ).execute(DOCUMENT_ID)


def test_shadow_extraction_rejects_non_sec_sources() -> None:
    repository = FakeRepository(source_document(provider="local-file"))

    with pytest.raises(SecXbrlExtractionError, match="only verified SEC filing"):
        ExtractSecXbrlCandidates(
            repository=repository,
            processor=FakeProcessor((revenue_fact(),)),
        ).execute(DOCUMENT_ID)


def test_shadow_extraction_reuses_canonical_source_integrity_gate() -> None:
    repository = FakeRepository(source_document(), content=b"tampered")

    with pytest.raises(SourceDocumentIntegrityError, match="byte length"):
        ExtractSecXbrlCandidates(
            repository=repository,
            processor=FakeProcessor((revenue_fact(),)),
        ).execute(DOCUMENT_ID)


def complete_submission(primary_text: bytes = b"<html>ixbrl</html>") -> bytes:
    return b"".join(
        (
            b"<SEC-DOCUMENT>\n",
            b"<DOCUMENT>\n<TYPE>10-K\n<FILENAME>annual.htm\n<TEXT>",
            primary_text,
            b"</TEXT>\n</DOCUMENT>\n",
            b"<DOCUMENT>\n<TYPE>EX-99\n<FILENAME>exhibit.htm\n<TEXT>x</TEXT>\n</DOCUMENT>\n",
            b"</SEC-DOCUMENT>",
        )
    )


def test_entry_point_extractor_selects_only_admitted_primary_document() -> None:
    entry = SecCompleteSubmissionEntryPointExtractor().extract(complete_submission())

    assert entry.form == "10-K"
    assert entry.filename == "annual.htm"
    assert entry.content == b"<html>ixbrl</html>"


def test_pinned_arelle_bridge_rejects_version_drift() -> None:
    with pytest.raises(ArelleVersionMismatchError, match="does not match pin"):
        PinnedArelleProcessorBridge(
            reported_version="2.44.4",
            extractor=lambda _content, _filename: (),
        )


def test_pinned_arelle_bridge_passes_primary_bytes_and_prefixes_locator() -> None:
    calls: list[tuple[bytes, str]] = []

    def extractor(content: bytes, filename: str) -> tuple[ProcessorXbrlFact, ...]:
        calls.append((content, filename))
        return (replace(revenue_fact(), source_locator="line-42"),)

    bridge = PinnedArelleProcessorBridge(
        reported_version=ARELLE_PINNED_VERSION,
        extractor=extractor,
    )

    facts = bridge.extract(
        content=complete_submission(),
        source_uri="https://www.sec.gov/example.txt",
    )

    assert calls == [(b"<html>ixbrl</html>", "annual.htm")]
    assert facts[0].source_locator == "annual.htm:line-42"
    assert bridge.processor_name == "Arelle"
    assert bridge.processor_version == ARELLE_PINNED_VERSION


def test_entry_point_extractor_fails_closed_on_missing_or_multiple_primary_documents() -> None:
    with pytest.raises(ArelleBridgeError, match="no admitted primary"):
        SecCompleteSubmissionEntryPointExtractor().extract(
            b"<SEC-DOCUMENT><DOCUMENT><TYPE>8-K\n<FILENAME>x.htm\n"
            b"<TEXT>x</TEXT></DOCUMENT></SEC-DOCUMENT>"
        )

    doubled = complete_submission() + complete_submission()
    with pytest.raises(ArelleBridgeError, match="multiple admitted primary"):
        SecCompleteSubmissionEntryPointExtractor().extract(doubled)
