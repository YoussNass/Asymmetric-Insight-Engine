"""Tests for strict SEC submissions-catalog discovery."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256

import pytest

from asymmetric_engine.application.evidence_ingestion import InvalidSourceReferenceError
from asymmetric_engine.infrastructure.providers.sec_edgar_submissions import (
    SecEdgarSubmissionsProvider,
    SecSubmissionCatalogPayloadError,
)


def submissions_payload() -> dict[str, object]:
    return {
        "cik": "320193",
        "name": "Apple Inc.",
        "tickers": ["AAPL"],
        "exchanges": ["Nasdaq"],
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000320193-25-000010",
                    "0000320193-24-000123",
                    "0000320193-25-000079",
                ],
                "filingDate": ["2025-02-01", "2024-11-01", "2025-05-02"],
                "reportDate": ["2024-12-28", "2024-09-28", "2025-03-29"],
                "acceptanceDateTime": [
                    "20250201123456",
                    "20241101120000",
                    "20250502150000",
                ],
                "form": ["8-K", "10-K", "10-Q"],
                "primaryDocument": ["event.htm", "annual.htm", "quarter.htm"],
            },
            "files": [
                {
                    "name": "CIK0000320193-submissions-001.json",
                    "filingCount": 1000,
                    "filingFrom": "1994-01-01",
                    "filingTo": "2023-12-31",
                }
            ],
        },
    }


def encoded(payload: dict[str, object] | None = None) -> bytes:
    return json.dumps(payload or submissions_payload(), separators=(",", ":")).encode()


def test_catalog_discovers_only_admitted_forms_without_claiming_complete_history() -> None:
    requested_urls: list[str] = []
    content = encoded()

    def fetch_bytes(url: str) -> bytes:
        requested_urls.append(url)
        return content

    catalog = SecEdgarSubmissionsProvider(fetch_bytes).fetch("320193")

    assert requested_urls == ["https://data.sec.gov/submissions/CIK0000320193.json"]
    assert catalog.cik == "0000320193"
    assert catalog.subject_id == "company:sec-cik-0000320193"
    assert catalog.company_name == "Apple Inc."
    assert catalog.ticker_exchange_pairs == (("AAPL", "Nasdaq"),)
    assert catalog.total_recent_filings == 3
    assert [entry.form for entry in catalog.entries] == ["10-K", "10-Q"]
    assert [entry.reference for entry in catalog.entries] == [
        "0000320193/0000320193-24-000123",
        "0000320193/0000320193-25-000079",
    ]
    assert catalog.entries[0].acceptance_datetime_text == "20241101120000"
    assert catalog.content_hash == sha256(content).hexdigest()
    assert catalog.content == content
    assert not catalog.history_complete
    assert catalog.warnings == ("additional_sec_history_pages_not_fetched",)
    assert catalog.history_pages[0].filing_count == 1000


def test_catalog_with_no_declared_history_pages_is_complete_for_returned_history_shape() -> None:
    payload = submissions_payload()
    filings = payload["filings"]
    assert isinstance(filings, dict)
    filings["files"] = []

    catalog = SecEdgarSubmissionsProvider(lambda _: encoded(payload)).fetch("0000320193")

    assert catalog.history_complete
    assert catalog.warnings == ()


@pytest.mark.parametrize("reference", ["", "AAPL", "0", "12345678901"])
def test_catalog_rejects_noncanonical_cik_reference(reference: str) -> None:
    with pytest.raises(InvalidSourceReferenceError, match="positive CIK"):
        SecEdgarSubmissionsProvider(lambda _: encoded()).fetch(reference)


def test_catalog_rejects_a_payload_for_another_cik() -> None:
    payload = submissions_payload()
    payload["cik"] = 1

    with pytest.raises(SecSubmissionCatalogPayloadError, match="does not match"):
        SecEdgarSubmissionsProvider(lambda _: encoded(payload)).fetch("320193")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (("recent", "form", ["10-K"]), "inconsistent length"),
        (("recent", "reportDate", ["2024-12-28", "bad", "2025-03-29"]), "ISO date"),
        (
            ("recent", "acceptanceDateTime", ["20250201123456", "bad", "20250502150000"]),
            "acceptanceDateTime",
        ),
        (
            (
                "recent",
                "accessionNumber",
                [
                    "0000320193-25-000010",
                    "0000320193-24-000123",
                    "0000320193-24-000123",
                ],
            ),
            "duplicate",
        ),
        (("root", "exchanges", []), "inconsistent length"),
    ],
)
def test_catalog_fails_closed_on_inconsistent_required_metadata(
    mutation: tuple[str, str, object],
    message: str,
) -> None:
    payload = deepcopy(submissions_payload())
    scope, field, value = mutation
    if scope == "root":
        payload[field] = value
    else:
        filings = payload["filings"]
        assert isinstance(filings, dict)
        recent = filings["recent"]
        assert isinstance(recent, dict)
        recent[field] = value

    with pytest.raises(SecSubmissionCatalogPayloadError, match=message):
        SecEdgarSubmissionsProvider(lambda _: encoded(payload)).fetch("320193")


@pytest.mark.parametrize("content", [b"", b"not-json", b"\xff"])
def test_catalog_rejects_empty_or_invalid_json(content: bytes) -> None:
    with pytest.raises(SecSubmissionCatalogPayloadError, match="payload"):
        SecEdgarSubmissionsProvider(lambda _: content).fetch("320193")


def test_catalog_rejects_duplicate_or_reversed_history_pages() -> None:
    duplicate = submissions_payload()
    filings = duplicate["filings"]
    assert isinstance(filings, dict)
    pages = filings["files"]
    assert isinstance(pages, list)
    pages.append(deepcopy(pages[0]))

    with pytest.raises(SecSubmissionCatalogPayloadError, match="duplicate history"):
        SecEdgarSubmissionsProvider(lambda _: encoded(duplicate)).fetch("320193")

    reversed_dates = submissions_payload()
    reversed_filings = reversed_dates["filings"]
    assert isinstance(reversed_filings, dict)
    reversed_pages = reversed_filings["files"]
    assert isinstance(reversed_pages, list)
    first_page = reversed_pages[0]
    assert isinstance(first_page, dict)
    first_page["filingFrom"] = "2025-01-01"
    first_page["filingTo"] = "2024-01-01"

    with pytest.raises(SecSubmissionCatalogPayloadError, match="reversed"):
        SecEdgarSubmissionsProvider(lambda _: encoded(reversed_dates)).fetch("320193")
