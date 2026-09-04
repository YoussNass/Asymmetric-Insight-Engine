"""Tests for the pinned raw Arelle statement-inspection boundary."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

import pytest

from asymmetric_engine.application.evidence_ingestion import AppendResult
from asymmetric_engine.application.sec_fact_admission import SecStatementObservation
from asymmetric_engine.application.sec_xbrl_extraction import (
    ExtractSecXbrlCandidates,
    ProcessorXbrlFact,
    SecXbrlCandidate,
    SecXbrlCandidateSet,
    SecXbrlPeriodKind,
)
from asymmetric_engine.domain.evidence import (
    AvailabilityBasis,
    SourceDocument,
    SourceType,
)
from asymmetric_engine.infrastructure.providers.arelle_reconciliation import (
    PinnedArelleStatementInspectorBridge,
)
from asymmetric_engine.infrastructure.providers.arelle_xbrl import (
    ARELLE_PINNED_VERSION,
    ArelleVersionMismatchError,
)

CONTENT = b"<SEC-DOCUMENT>reconciliation bridge fixture</SEC-DOCUMENT>"
DOCUMENT_ID = UUID("66666666-6666-6666-6666-666666666666")


class FakeRepository:
    def __init__(self) -> None:
        observed_at = datetime(2025, 2, 1, 12, 0, tzinfo=UTC)
        self.document = SourceDocument(
            document_id=DOCUMENT_ID,
            provider="sec-edgar",
            provider_record_id="0000320193:10-K:20241228",
            provider_version="0000320193-25-000010",
            subject_id="company:sec-cik-0000320193",
            title="Reconciliation bridge fixture",
            source_uri="https://www.sec.gov/Archives/edgar/data/reconciliation-fixture.txt",
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
    processor_name = "Arelle"
    processor_version = ARELLE_PINNED_VERSION

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


def candidate_set(repository: FakeRepository) -> SecXbrlCandidateSet:
    return ExtractSecXbrlCandidates(
        repository=repository,
        processor=FakeProcessor(),
    ).execute(DOCUMENT_ID)


def observation_for(candidate: SecXbrlCandidate) -> SecStatementObservation:
    return SecStatementObservation(
        candidate_id=candidate.candidate_id,
        statement_present=True,
        statement_role_uri="http://example.com/role/IncomeStatement",
        statement_locator="income-statement#line-1",
        statement_value=Decimal(candidate.raw_value),
        calculation_parent_value=None,
        calculation_components=(),
        calculation_relationship_complete=True,
        inspector_name="untrusted-runtime-name",
        inspector_version="untrusted-runtime-version",
    )


def test_bridge_rejects_unreviewed_arelle_version() -> None:
    with pytest.raises(ArelleVersionMismatchError, match="does not match pin"):
        PinnedArelleStatementInspectorBridge(
            repository=FakeRepository(),
            reported_version="2.44.4",
            inspector=lambda _content, _source_uri, candidate: observation_for(candidate),
        )


def test_bridge_inspects_exact_verified_bytes_and_pins_identity() -> None:
    repository = FakeRepository()
    facts = candidate_set(repository)
    candidate = facts.candidates[0]
    calls: list[tuple[bytes, str, str]] = []

    def inspect(
        content: bytes,
        source_uri: str,
        selected: SecXbrlCandidate,
    ) -> SecStatementObservation:
        calls.append((content, source_uri, selected.candidate_id))
        return observation_for(selected)

    bridge = PinnedArelleStatementInspectorBridge(
        repository=repository,
        reported_version=ARELLE_PINNED_VERSION,
        inspector=inspect,
    )

    observation = bridge.inspect(candidate=candidate, candidate_set=facts)

    assert calls == [(CONTENT, repository.document.source_uri, candidate.candidate_id)]
    assert observation.inspector_name == "Arelle"
    assert observation.inspector_version == ARELLE_PINNED_VERSION
    assert observation.candidate_id == candidate.candidate_id
