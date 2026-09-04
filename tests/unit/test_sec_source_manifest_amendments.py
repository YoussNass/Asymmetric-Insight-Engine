"""Regression test for additive amendment and restatement source identity."""

from datetime import date

from asymmetric_engine.application.sec_source_manifest import (
    BuildSecExpectedSourceManifest,
    SecFilingCatalogEntry,
    SecSubmissionCatalog,
)


def filing(accession: str, form: str) -> SecFilingCatalogEntry:
    return SecFilingCatalogEntry(
        cik="0000320193",
        accession=accession,
        form=form,
        filed_on=date(2025, 2, 1),
        report_period_end=date(2024, 12, 28),
        acceptance_datetime_text="20250201120000",
        primary_document="annual.htm",
    )


def test_original_and_amended_filings_remain_distinct_additive_versions() -> None:
    original = filing("0000320193-25-000010", "10-K")
    amendment = filing("0000320193-25-000011", "10-K/A")
    catalog = SecSubmissionCatalog(
        cik="0000320193",
        company_name="Fixture issuer",
        ticker_exchange_pairs=(("AAPL", "Nasdaq"),),
        entries=(original, amendment),
        history_pages=(),
        source_uri="https://data.sec.gov/submissions/CIK0000320193.json",
        content_hash="a" * 64,
        total_recent_filings=2,
        content=b"current-catalog",
    )

    manifest = BuildSecExpectedSourceManifest().execute(
        current=catalog,
        history_pages=(),
    )

    assert manifest.expected_references == (
        "0000320193/0000320193-25-000010",
        "0000320193/0000320193-25-000011",
    )
    assert tuple(item.form for item in manifest.expected_filings) == ("10-K", "10-K/A")
