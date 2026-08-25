"""Narrow SEC EDGAR adapter for immutable periodic-filing submissions."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock
from time import monotonic, sleep
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from asymmetric_engine.application.evidence_ingestion import (
    InvalidSourceReferenceError,
    SourceProviderAccessError,
    SourceProviderPayloadError,
    UnsupportedSourceError,
)
from asymmetric_engine.domain.evidence import (
    AvailabilityBasis,
    SourceDocumentDraft,
    SourceType,
)

SEC_ARCHIVE_ROOT = "https://www.sec.gov/Archives/edgar/data"
SUPPORTED_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})
REFERENCE_PATTERN = re.compile(r"^(?P<cik>[0-9]{1,10})/(?P<accession>[0-9]{10}-[0-9]{2}-[0-9]{6})$")
CONTACT_PATTERN = re.compile(r"^[^\s]+\s+[^\s@]+@[^\s@]+\.[^\s@]+$")


class ProviderAccessError(SourceProviderAccessError):
    """Raised when an admitted provider cannot be reached or returns an unusable response."""


class ProviderPayloadError(SourceProviderPayloadError):
    """Raised when provider bytes contradict the requested immutable identity."""


class UnsupportedSecFilingError(UnsupportedSourceError):
    """Raised when a valid EDGAR submission is outside the deliberately narrow scope."""


class SecEdgarHttpFetcher:
    """Policy-enforcing byte fetcher for one exact SEC archive object."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 30.0,
        max_payload_bytes: int = 25_000_000,
        min_interval_seconds: float = 0.2,
        monotonic_clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        normalized_user_agent = user_agent.strip()
        if not CONTACT_PATTERN.fullmatch(normalized_user_agent):
            raise ValueError("user_agent must identify an application and contact email")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_payload_bytes < 1:
            raise ValueError("max_payload_bytes must be positive")
        if min_interval_seconds < 0.1:
            raise ValueError("min_interval_seconds must enforce at most 10 requests per second")
        self._user_agent = normalized_user_agent
        self._timeout_seconds = timeout_seconds
        self._max_payload_bytes = max_payload_bytes
        self._min_interval_seconds = min_interval_seconds
        self._monotonic_clock = monotonic_clock
        self._sleeper = sleeper
        self._last_request_started: float | None = None
        self._rate_lock = Lock()

    def _wait_for_request_slot(self) -> None:
        with self._rate_lock:
            now = self._monotonic_clock()
            if self._last_request_started is not None:
                wait_seconds = self._min_interval_seconds - (now - self._last_request_started)
                if wait_seconds > 0:
                    self._sleeper(wait_seconds)
                    now += wait_seconds
            self._last_request_started = now

    def fetch(self, url: str) -> bytes:
        """Download bounded exact bytes using the SEC-required declared user agent."""

        if not url.startswith(f"{SEC_ARCHIVE_ROOT}/"):
            raise ValueError("SEC fetcher accepts only canonical EDGAR archive URLs")
        self._wait_for_request_slot()
        request = Request(
            url,
            headers={
                "Accept-Encoding": "identity",
                "User-Agent": self._user_agent,
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                final_url = cast(str, response.geturl())
                if not final_url.startswith(f"{SEC_ARCHIVE_ROOT}/"):
                    raise ProviderAccessError("SEC request redirected outside the admitted archive")
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError as error:
                        raise ProviderAccessError(
                            "SEC returned an invalid Content-Length header"
                        ) from error
                    if declared_size < 0:
                        raise ProviderAccessError("SEC returned an invalid Content-Length header")
                    if declared_size > self._max_payload_bytes:
                        raise ProviderAccessError("SEC filing exceeds the configured size limit")
                content = cast(bytes, response.read(self._max_payload_bytes + 1))
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise ProviderAccessError("SEC filing request failed") from error
        if len(content) > self._max_payload_bytes:
            raise ProviderAccessError("SEC filing exceeds the configured size limit")
        if not content:
            raise ProviderAccessError("SEC returned an empty filing")
        return content


class SecEdgarProvider:
    """Map one exact SEC complete submission into the evidence-ledger contract."""

    def __init__(self, fetch_bytes: Callable[[str], bytes]) -> None:
        self._fetch_bytes = fetch_bytes

    @staticmethod
    def _header_value(content: bytes, field: str) -> str:
        pattern = re.compile(
            rb"<" + field.encode("ascii") + rb">[ \t]*([^\r\n<]+)",
            flags=re.IGNORECASE,
        )
        match = pattern.search(content, 0, min(len(content), 1_000_000))
        if match is None:
            raise ProviderPayloadError(f"SEC filing header is missing {field}")
        try:
            return match.group(1).decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError as error:
            raise ProviderPayloadError(f"SEC filing header {field} is not valid UTF-8") from error

    def fetch(self, reference: str) -> SourceDocumentDraft:
        """Fetch ``CIK/accession`` while preserving the complete submission bytes."""

        match = REFERENCE_PATTERN.fullmatch(reference)
        if match is None:
            raise InvalidSourceReferenceError("SEC reference must use CIK/##########-##-######")

        cik_number = int(match.group("cik"))
        if cik_number == 0:
            raise InvalidSourceReferenceError("SEC reference CIK must be positive")
        cik = str(cik_number)
        cik_padded = cik.zfill(10)
        accession = match.group("accession")
        accession_path = accession.replace("-", "")
        source_uri = f"{SEC_ARCHIVE_ROOT}/{cik}/{accession_path}/{accession}.txt"
        content = self._fetch_bytes(source_uri)

        payload_accession = self._header_value(content, "ACCESSION-NUMBER")
        payload_cik = self._header_value(content, "CENTRAL-INDEX-KEY").zfill(10)
        company_name = self._header_value(content, "COMPANY-CONFORMED-NAME")
        form = self._header_value(content, "CONFORMED-SUBMISSION-TYPE").upper()
        report_date = self._header_value(content, "CONFORMED-PERIOD-OF-REPORT")

        if payload_accession != accession:
            raise ProviderPayloadError("SEC payload accession does not match the reference")
        if payload_cik != cik_padded:
            raise ProviderPayloadError("SEC payload CIK does not match the reference")
        if form not in SUPPORTED_FORMS:
            raise UnsupportedSecFilingError(f"SEC form {form!r} is not admitted")
        try:
            effective_at = datetime.strptime(report_date, "%Y%m%d").replace(tzinfo=UTC)
        except ValueError as error:
            raise ProviderPayloadError("SEC period-of-report is not a valid date") from error

        form_family = form.removesuffix("/A")
        return SourceDocumentDraft(
            provider="sec-edgar",
            provider_record_id=f"{cik_padded}:{form_family}:{report_date}",
            provider_version=accession,
            subject_id=f"company:sec-cik-{cik_padded}",
            title=f"{company_name} — {form} for {report_date}",
            source_uri=source_uri,
            source_type=SourceType.FILING,
            effective_at=effective_at,
            availability_basis=AvailabilityBasis.OBSERVED_AT_INGESTION,
            available_at=None,
            media_type="text/plain",
            content=content,
        )
