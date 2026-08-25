"""Tests for the deliberately narrow SEC EDGAR filing adapter."""

from __future__ import annotations

from email.message import Message
from urllib.error import URLError
from urllib.request import Request

import pytest

from asymmetric_engine.application.evidence_ingestion import InvalidSourceReferenceError
from asymmetric_engine.domain.evidence import AvailabilityBasis, SourceType
from asymmetric_engine.infrastructure.providers import sec_edgar
from asymmetric_engine.infrastructure.providers.sec_edgar import (
    ProviderAccessError,
    ProviderPayloadError,
    SecEdgarHttpFetcher,
    SecEdgarProvider,
    UnsupportedSecFilingError,
)

REFERENCE = "0000320193/0000320193-24-000123"


def filing_bytes(
    *,
    accession: str = "0000320193-24-000123",
    cik: str = "0000320193",
    form: str = "10-K",
    report_date: str = "20240928",
) -> bytes:
    return (
        "<SEC-DOCUMENT>"
        f"\n<ACCESSION-NUMBER>{accession}"
        f"\n<CONFORMED-SUBMISSION-TYPE>{form}"
        f"\n<CONFORMED-PERIOD-OF-REPORT>{report_date}"
        "\n<FILER><COMPANY-DATA>"
        "\n<COMPANY-CONFORMED-NAME>Example Corp"
        f"\n<CENTRAL-INDEX-KEY>{cik}"
        "\n</COMPANY-DATA></FILER>"
        "\n<DOCUMENT>exact filing bytes</DOCUMENT>"
    ).encode()


def test_sec_provider_maps_exact_complete_submission_without_inventing_availability() -> None:
    requested_urls: list[str] = []

    def fetch_bytes(url: str) -> bytes:
        requested_urls.append(url)
        return filing_bytes()

    draft = SecEdgarProvider(fetch_bytes).fetch(REFERENCE)

    assert requested_urls == [
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/0000320193-24-000123.txt"
    ]
    assert draft.provider == "sec-edgar"
    assert draft.provider_record_id == "0000320193:10-K:20240928"
    assert draft.provider_version == "0000320193-24-000123"
    assert draft.subject_id == "company:sec-cik-0000320193"
    assert draft.source_type is SourceType.FILING
    assert draft.effective_at.isoformat() == "2024-09-28T00:00:00+00:00"
    assert draft.availability_basis is AvailabilityBasis.OBSERVED_AT_INGESTION
    assert draft.available_at is None
    assert draft.content == filing_bytes()


def test_amendment_keeps_record_identity_but_has_a_distinct_version() -> None:
    amendment_accession = "0000320193-25-000001"
    draft = SecEdgarProvider(
        lambda _: filing_bytes(accession=amendment_accession, form="10-K/A")
    ).fetch(f"320193/{amendment_accession}")

    assert draft.provider_record_id == "0000320193:10-K:20240928"
    assert draft.provider_version == amendment_accession


@pytest.mark.parametrize(
    "reference",
    ["", "AAPL/0000320193-24-000123", "0320193/invalid", "320193", "0/0000320193-24-000123"],
)
def test_sec_provider_rejects_noncanonical_references(reference: str) -> None:
    with pytest.raises(InvalidSourceReferenceError, match="SEC reference"):
        SecEdgarProvider(lambda _: filing_bytes()).fetch(reference)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (filing_bytes(accession="0000320193-24-999999"), "accession"),
        (filing_bytes(cik="0000000001"), "CIK"),
        (filing_bytes(report_date="20241399"), "period-of-report"),
        (b"<SEC-DOCUMENT>\n<ACCESSION-NUMBER>0000320193-24-000123", "CENTRAL-INDEX-KEY"),
        (
            filing_bytes().replace(b"Example Corp", b"Example \xff Corp"),
            "valid UTF-8",
        ),
    ],
)
def test_sec_provider_fails_closed_on_inconsistent_headers(content: bytes, message: str) -> None:
    with pytest.raises(ProviderPayloadError, match=message):
        SecEdgarProvider(lambda _: content).fetch(REFERENCE)


def test_sec_provider_rejects_forms_outside_the_admitted_slice() -> None:
    with pytest.raises(UnsupportedSecFilingError, match="8-K"):
        SecEdgarProvider(lambda _: filing_bytes(form="8-K")).fetch(REFERENCE)


class FakeResponse:
    def __init__(
        self,
        content: bytes,
        content_length: str | None = None,
        final_url: str = "https://www.sec.gov/Archives/edgar/data/1/filing.txt",
    ) -> None:
        self._content = content
        self._final_url = final_url
        self.headers = Message()
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self._content[:limit]

    def geturl(self) -> str:
        return self._final_url


def test_http_fetcher_declares_identity_and_preserves_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"exact bytes"

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        assert request.get_header("User-agent") == "AIE admin@example.com"
        assert request.get_header("Accept-encoding") == "identity"
        assert timeout == 7.0
        return FakeResponse(content, str(len(content)))

    monkeypatch.setattr(sec_edgar, "urlopen", fake_urlopen)
    fetcher = SecEdgarHttpFetcher(
        user_agent="AIE admin@example.com",
        timeout_seconds=7,
        max_payload_bytes=100,
    )

    assert fetcher.fetch("https://www.sec.gov/Archives/edgar/data/1/filing.txt") == content


def test_http_fetcher_enforces_a_conservative_request_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [FakeResponse(b"first"), FakeResponse(b"second")]
    times = iter((10.0, 10.05))
    waits: list[float] = []
    monkeypatch.setattr(sec_edgar, "urlopen", lambda *_args, **_kwargs: responses.pop(0))
    fetcher = SecEdgarHttpFetcher(
        user_agent="AIE admin@example.com",
        min_interval_seconds=0.2,
        monotonic_clock=lambda: next(times),
        sleeper=waits.append,
    )

    fetcher.fetch("https://www.sec.gov/Archives/edgar/data/1/first.txt")
    fetcher.fetch("https://www.sec.gov/Archives/edgar/data/1/second.txt")

    assert waits == pytest.approx([0.15])


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (FakeResponse(b"abc", "invalid"), "Content-Length"),
        (FakeResponse(b"abc", "-1"), "Content-Length"),
        (FakeResponse(b"abc", "101"), "size limit"),
        (FakeResponse(b"x" * 101), "size limit"),
        (FakeResponse(b""), "empty"),
        (FakeResponse(b"abc", final_url="https://example.test/filing.txt"), "redirected"),
    ],
)
def test_http_fetcher_rejects_unusable_responses(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeResponse,
    message: str,
) -> None:
    monkeypatch.setattr(sec_edgar, "urlopen", lambda *_args, **_kwargs: response)
    fetcher = SecEdgarHttpFetcher(
        user_agent="AIE admin@example.com",
        max_payload_bytes=100,
    )

    with pytest.raises(ProviderAccessError, match=message):
        fetcher.fetch("https://www.sec.gov/Archives/edgar/data/1/filing.txt")


def test_http_fetcher_normalizes_transport_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> FakeResponse:
        raise URLError("offline")

    monkeypatch.setattr(sec_edgar, "urlopen", fail)
    fetcher = SecEdgarHttpFetcher(user_agent="AIE admin@example.com")

    with pytest.raises(ProviderAccessError, match="request failed"):
        fetcher.fetch("https://www.sec.gov/Archives/edgar/data/1/filing.txt")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"user_agent": "anonymous"},
        {"user_agent": "AIE admin@example.com", "timeout_seconds": 0},
        {"user_agent": "AIE admin@example.com", "max_payload_bytes": 0},
        {"user_agent": "AIE admin@example.com", "min_interval_seconds": 0.09},
    ],
)
def test_http_fetcher_rejects_unsafe_configuration(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        SecEdgarHttpFetcher(**kwargs)  # type: ignore[arg-type]

    fetcher = SecEdgarHttpFetcher(user_agent="AIE admin@example.com")
    with pytest.raises(ValueError, match="canonical"):
        fetcher.fetch("https://example.test/filing.txt")
