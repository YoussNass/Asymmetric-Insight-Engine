"""End-to-end Chapter 4 path from SEC-format bytes to underwriting readiness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.causal_analysis import BuildCausalAnalysis
from asymmetric_engine.application.evidence_ingestion import IngestSourceDocument
from asymmetric_engine.domain.causal import CausalReadiness
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode
from asymmetric_engine.infrastructure.persistence import SQLiteSourceDocumentRepository
from asymmetric_engine.infrastructure.providers.sec_edgar import SecEdgarProvider
from tests.causal_factories import (
    ANALYSIS_AS_OF,
    MICRON_CONTENT,
    MICRON_REFERENCE,
    NVIDIA_CONTENT,
    NVIDIA_REFERENCE,
    RECORDED_AT,
    make_causal_draft,
)


@dataclass(frozen=True)
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


def test_sec_ledger_to_causal_beneficiary_handoff_is_reproducible(tmp_path: Path) -> None:
    database_path = tmp_path / "causal-evidence.sqlite3"
    repository = SQLiteSourceDocumentRepository(database_path)

    def fetch_fixture(url: str) -> bytes:
        if "000104581024000029" in url:
            return NVIDIA_CONTENT
        if "000072312524000027" in url:
            return MICRON_CONTENT
        raise AssertionError(f"unexpected SEC fixture URL: {url}")

    ingestion = IngestSourceDocument(
        provider=SecEdgarProvider(fetch_fixture),
        repository=repository,
        clock=FixedClock(RECORDED_AT),
    )
    nvidia = ingestion.execute(NVIDIA_REFERENCE).document
    micron = ingestion.execute(MICRON_REFERENCE).document
    draft = make_causal_draft(documents=(nvidia, micron))

    analysis = BuildCausalAnalysis(repository).execute(draft)
    restarted_analysis = BuildCausalAnalysis(
        SQLiteSourceDocumentRepository(database_path, initialize_schema=False)
    ).execute(draft)

    assert analysis == restarted_analysis
    assert analysis.readiness is CausalReadiness.READY_FOR_UNDERWRITING
    assert {node.subject_id for node in analysis.nodes if node.subject_id is not None} == {
        "company:sec-cik-0000723125"
    }
    assert len(analysis.edges) == 3
    assert len(analysis.claims) == 3
    assert len(analysis.evidence) == 3
    assert {document.provider_version for document in analysis.source_documents} == {
        "0001045810-24-000029",
        "0000723125-24-000027",
    }
    assert repository.read_content(nvidia.document_id) == NVIDIA_CONTENT
    assert repository.read_content(micron.document_id) == MICRON_CONTENT
    assert analysis.missing_data
    assert all(claim.confidence.rationale for claim in analysis.claims)
    assert all(claim.invalidation_condition for claim in analysis.claims)


def test_same_ledger_fails_closed_before_observed_ingestion_time(tmp_path: Path) -> None:
    repository = SQLiteSourceDocumentRepository(tmp_path / "causal-evidence.sqlite3")
    fixture_by_accession = {
        "000104581024000029": NVIDIA_CONTENT,
        "000072312524000027": MICRON_CONTENT,
    }
    ingestion = IngestSourceDocument(
        provider=SecEdgarProvider(
            lambda url: next(
                content for accession, content in fixture_by_accession.items() if accession in url
            )
        ),
        repository=repository,
        clock=FixedClock(RECORDED_AT),
    )
    documents = (
        ingestion.execute(NVIDIA_REFERENCE).document,
        ingestion.execute(MICRON_REFERENCE).document,
    )
    too_early = KnowledgeBoundary(
        as_of=ANALYSIS_AS_OF - timedelta(days=2),
        knowledge_mode=KnowledgeMode.LIVE_SYSTEM_REPLAY,
    )

    with pytest.raises(ValidationError, match="source_not_available"):
        make_causal_draft(documents=documents, boundary=too_early)
