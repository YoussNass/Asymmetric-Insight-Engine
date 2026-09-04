"""Tests for Chapter 11A expected-source reconciliation and capture."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from typing import cast

import pytest

from asymmetric_engine.application.evidence_ingestion import AppendResult
from asymmetric_engine.application.sec_source_manifest import (
    BuildSecExpectedSourceManifest,
    CaptureSecExpectedSources,
    DiscoverSecExpectedSourceManifest,
    SecExpectedSourceManifest,
    SecFilingCatalogEntry,
    SecSourceManifestError,
    SecSubmissionCatalog,
    SecSubmissionHistoryPage,
    SecSubmissionHistorySnapshot,
)
from asymmetric_engine.infrastructure.providers.sec_edgar_submissions import (
    SecEdgarSubmissionsProvider,
)


def entry(
    accession: str,
    *,
    filed_on: date,
    form: str = "10-K",
) -> SecFilingCatalogEntry:
    return SecFilingCatalogEntry(
        cik="0000320193",
        accession=accession,
        form=form,
        filed_on=filed_on,
        report_period_end=filed_on,
        acceptance_datetime_text="20250101120000",
        primary_document="filing.htm",
    )


def current_catalog() -> SecSubmissionCatalog:
    return SecSubmissionCatalog(
        cik="0000320193",
        company_name="Apple Inc.",
        ticker_exchange_pairs=(("AAPL", "Nasdaq"),),
        entries=(entry("0000320193-25-000001", filed_on=date(2025, 1, 2)),),
        history_pages=(
            SecSubmissionHistoryPage(
                name="CIK0000320193-submissions-001.json",
                filing_count=2,
                filing_from=date(2023, 1, 1),
                filing_to=date(2024, 12, 31),
            ),
        ),
        source_uri="https://data.sec.gov/submissions/CIK0000320193.json",
        content_hash="a" * 64,
        total_recent_filings=1,
        content=b"current",
    )


def history_snapshot() -> SecSubmissionHistorySnapshot:
    return SecSubmissionHistorySnapshot(
        cik="0000320193",
        page_name="CIK0000320193-submissions-001.json",
        entries=(
            entry("0000320193-23-000001", filed_on=date(2023, 3, 1)),
            entry("0000320193-24-000001", filed_on=date(2024, 3, 1), form="10-Q"),
        ),
        source_uri="https://data.sec.gov/submissions/CIK0000320193-submissions-001.json",
        content_hash="b" * 64,
        total_filings=2,
        content=b"history",
    )


def test_manifest_requires_every_declared_history_page_and_is_deterministic() -> None:
    builder = BuildSecExpectedSourceManifest()
    current = current_catalog()
    history = history_snapshot()

    first = builder.execute(current=current, history_pages=(history,))
    second = builder.execute(current=current, history_pages=(history,))

    assert first == second
    assert first.manifest_version == "sec-expected-source-manifest-v1"
    assert first.subject_id == "company:sec-cik-0000320193"
    assert first.history_page_names == ("CIK0000320193-submissions-001.json",)
    assert first.catalog_content_hashes == ("a" * 64, "b" * 64)
    assert first.expected_references == (
        "0000320193/0000320193-23-000001",
        "0000320193/0000320193-24-000001",
        "0000320193/0000320193-25-000001",
    )
    assert len(first.manifest_hash) == 64


def test_manifest_without_declared_history_pages_is_valid_and_complete() -> None:
    current = replace(current_catalog(), history_pages=())

    manifest = BuildSecExpectedSourceManifest().execute(current=current, history_pages=())

    assert manifest.history_page_names == ()
    assert manifest.expected_references == ("0000320193/0000320193-25-000001",)


@pytest.mark.parametrize(
    ("history_pages", "message"),
    [
        ((), "missing"),
        ((history_snapshot(), history_snapshot()), "duplicate fetched"),
        (
            (
                replace(
                    history_snapshot(),
                    page_name="unexpected.json",
                ),
            ),
            "missing=.*unexpected",
        ),
        (
            (
                replace(
                    history_snapshot(),
                    cik="0000000001",
                ),
            ),
            "CIK does not match",
        ),
        (
            (
                replace(
                    history_snapshot(),
                    total_filings=1,
                ),
            ),
            "filing count",
        ),
        (
            (
                replace(
                    history_snapshot(),
                    entries=(
                        entry(
                            "0000320193-24-000001",
                            filed_on=date(2025, 1, 1),
                        ),
                    ),
                ),
            ),
            "out-of-range",
        ),
    ],
)
def test_manifest_fails_closed_on_history_reconciliation_errors(
    history_pages: tuple[SecSubmissionHistorySnapshot, ...],
    message: str,
) -> None:
    with pytest.raises(SecSourceManifestError, match=message):
        BuildSecExpectedSourceManifest().execute(
            current=current_catalog(),
            history_pages=history_pages,
        )


def test_manifest_rejects_duplicate_accession_across_current_and_history() -> None:
    duplicate = replace(
        history_snapshot(),
        entries=(
            entry("0000320193-25-000001", filed_on=date(2024, 1, 1)),
            entry("0000320193-24-000001", filed_on=date(2024, 3, 1)),
        ),
    )

    with pytest.raises(SecSourceManifestError, match="duplicate admitted accession"):
        BuildSecExpectedSourceManifest().execute(
            current=current_catalog(),
            history_pages=(duplicate,),
        )


def test_manifest_rejects_cross_subject_filing() -> None:
    foreign_entry = replace(
        entry("0000320193-24-000001", filed_on=date(2024, 1, 1)),
        cik="0000000001",
    )
    foreign = replace(
        history_snapshot(),
        entries=(
            foreign_entry,
            entry("0000320193-24-000002", filed_on=date(2024, 2, 1)),
        ),
    )

    with pytest.raises(SecSourceManifestError, match="filing CIK"):
        BuildSecExpectedSourceManifest().execute(
            current=current_catalog(),
            history_pages=(foreign,),
        )


def history_payload() -> bytes:
    return json.dumps(
        {
            "accessionNumber": ["0000320193-23-000001", "0000320193-23-000099"],
            "filingDate": ["2023-03-01", "2023-04-01"],
            "reportDate": ["2022-12-31", "2023-03-31"],
            "acceptanceDateTime": ["20230301120000", "20230401120000"],
            "form": ["10-K", "8-K"],
            "primaryDocument": ["annual.htm", "event.htm"],
        },
        separators=(",", ":"),
    ).encode()


def test_provider_fetches_declared_history_page_and_filters_unsupported_forms() -> None:
    requested_urls: list[str] = []
    payload = history_payload()

    def fetch_bytes(url: str) -> bytes:
        requested_urls.append(url)
        return payload

    page = SecSubmissionHistoryPage(
        name="CIK0000320193-submissions-001.json",
        filing_count=2,
        filing_from=date(2023, 1, 1),
        filing_to=date(2023, 12, 31),
    )
    snapshot = SecEdgarSubmissionsProvider(fetch_bytes).fetch_history_page(
        cik="320193",
        page=page,
    )

    assert requested_urls == [
        "https://data.sec.gov/submissions/CIK0000320193-submissions-001.json"
    ]
    assert snapshot.cik == "0000320193"
    assert snapshot.page_name == page.name
    assert snapshot.total_filings == 2
    assert [item.form for item in snapshot.entries] == ["10-K"]
    assert snapshot.content == payload


class FakeCatalogProvider:
    def __init__(self) -> None:
        self.pages: list[str] = []

    def fetch(self, reference: str) -> SecSubmissionCatalog:
        assert reference == "320193"
        return current_catalog()

    def fetch_history_page(
        self,
        *,
        cik: str,
        page: SecSubmissionHistoryPage,
    ) -> SecSubmissionHistorySnapshot:
        assert cik == "0000320193"
        self.pages.append(page.name)
        return history_snapshot()


def test_discovery_fetches_all_declared_pages_before_building_manifest() -> None:
    provider = FakeCatalogProvider()

    manifest = DiscoverSecExpectedSourceManifest(provider).execute("320193")

    assert provider.pages == ["CIK0000320193-submissions-001.json"]
    assert len(manifest.expected_filings) == 3


class FakeIngestor:
    def __init__(self) -> None:
        self.references: list[str] = []

    def execute(self, reference: str) -> AppendResult:
        self.references.append(reference)
        return cast(AppendResult, object())


def test_capture_ingests_exact_manifest_references_in_order() -> None:
    ingestor = FakeIngestor()
    manifest = BuildSecExpectedSourceManifest().execute(
        current=current_catalog(),
        history_pages=(history_snapshot(),),
    )

    results = CaptureSecExpectedSources(ingestor).execute(manifest)

    assert len(results) == 3
    assert ingestor.references == list(manifest.expected_references)


def test_manifest_hash_changes_when_source_version_changes() -> None:
    builder = BuildSecExpectedSourceManifest()
    original = builder.execute(
        current=current_catalog(),
        history_pages=(history_snapshot(),),
    )
    changed_history = replace(history_snapshot(), content_hash="c" * 64)
    changed = builder.execute(
        current=current_catalog(),
        history_pages=(changed_history,),
    )

    assert changed.manifest_hash != original.manifest_hash


def test_manifest_model_keeps_acceptance_text_as_metadata_only() -> None:
    manifest: SecExpectedSourceManifest = BuildSecExpectedSourceManifest().execute(
        current=current_catalog(),
        history_pages=(history_snapshot(),),
    )

    assert manifest.expected_filings[0].acceptance_datetime_text == "20250101120000"
    assert not hasattr(manifest.expected_filings[0], "available_at")
