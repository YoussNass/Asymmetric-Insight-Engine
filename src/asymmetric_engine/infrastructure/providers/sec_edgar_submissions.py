"""Strict SEC submissions-catalog parsing for admitted periodic filings."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date
from hashlib import sha256

from asymmetric_engine.application.evidence_ingestion import (
    InvalidSourceReferenceError,
    SourceProviderPayloadError,
)
from asymmetric_engine.application.sec_source_manifest import (
    SecFilingCatalogEntry,
    SecSubmissionCatalog,
    SecSubmissionHistoryPage,
    SecSubmissionHistorySnapshot,
)
from asymmetric_engine.infrastructure.providers.sec_edgar import SUPPORTED_FORMS

SEC_SUBMISSIONS_ROOT = "https://data.sec.gov/submissions"
CIK_PATTERN = re.compile(r"^[0-9]{1,10}$")
ACCESSION_PATTERN = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
ACCEPTANCE_PATTERN = re.compile(r"^[0-9]{14}$")
HISTORY_FILE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.json$")


class SecSubmissionCatalogPayloadError(SourceProviderPayloadError):
    """Raised when SEC submissions JSON cannot support a trustworthy catalog."""


class SecEdgarSubmissionsProvider:
    """Fetch and parse exact SEC submissions pages without claiming public availability."""

    def __init__(self, fetch_bytes: Callable[[str], bytes]) -> None:
        self._fetch_bytes = fetch_bytes

    @staticmethod
    def _cik(value: str) -> str:
        normalized = value.strip()
        if not CIK_PATTERN.fullmatch(normalized) or int(normalized) == 0:
            raise InvalidSourceReferenceError("SEC submissions reference must be a positive CIK")
        return normalized.zfill(10)

    @staticmethod
    def _object(value: object, field: str) -> dict[str, object]:
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise SecSubmissionCatalogPayloadError(
                f"SEC submissions field {field} must be an object"
            )
        return value

    @staticmethod
    def _array(value: object, field: str) -> list[object]:
        if not isinstance(value, list):
            raise SecSubmissionCatalogPayloadError(
                f"SEC submissions field {field} must be an array"
            )
        return value

    @staticmethod
    def _text(value: object, field: str, *, allow_empty: bool = False) -> str:
        if not isinstance(value, str):
            raise SecSubmissionCatalogPayloadError(f"SEC submissions field {field} must be text")
        normalized = value.strip()
        if not normalized and not allow_empty:
            raise SecSubmissionCatalogPayloadError(
                f"SEC submissions field {field} must not be empty"
            )
        return normalized

    @staticmethod
    def _date(value: object, field: str) -> date:
        text = SecEdgarSubmissionsProvider._text(value, field)
        try:
            return date.fromisoformat(text)
        except ValueError as error:
            raise SecSubmissionCatalogPayloadError(
                f"SEC submissions field {field} must be an ISO date"
            ) from error

    @staticmethod
    def _parallel_column(
        recent: dict[str, object],
        field: str,
        expected_length: int,
    ) -> list[object]:
        values = SecEdgarSubmissionsProvider._array(recent.get(field), f"filings.recent.{field}")
        if len(values) != expected_length:
            raise SecSubmissionCatalogPayloadError(
                f"SEC submissions field filings.recent.{field} has inconsistent length"
            )
        return values

    @classmethod
    def _entries(cls, recent: dict[str, object], cik: str) -> tuple[SecFilingCatalogEntry, ...]:
        accessions = cls._array(
            recent.get("accessionNumber"),
            "filings.recent.accessionNumber",
        )
        row_count = len(accessions)
        forms = cls._parallel_column(recent, "form", row_count)
        filing_dates = cls._parallel_column(recent, "filingDate", row_count)
        report_dates = cls._parallel_column(recent, "reportDate", row_count)
        acceptance_values = cls._parallel_column(recent, "acceptanceDateTime", row_count)
        primary_documents = cls._parallel_column(recent, "primaryDocument", row_count)

        entries: list[SecFilingCatalogEntry] = []
        seen_accessions: set[str] = set()
        for index, raw_accession in enumerate(accessions):
            form = cls._text(forms[index], f"filings.recent.form[{index}]").upper()
            if form not in SUPPORTED_FORMS:
                continue
            accession = cls._text(
                raw_accession,
                f"filings.recent.accessionNumber[{index}]",
            )
            if not ACCESSION_PATTERN.fullmatch(accession):
                raise SecSubmissionCatalogPayloadError(
                    f"SEC submissions accession at index {index} is invalid"
                )
            if accession in seen_accessions:
                raise SecSubmissionCatalogPayloadError(
                    "SEC submissions contains duplicate accessions"
                )
            seen_accessions.add(accession)
            acceptance = cls._text(
                acceptance_values[index],
                f"filings.recent.acceptanceDateTime[{index}]",
            )
            if not ACCEPTANCE_PATTERN.fullmatch(acceptance):
                raise SecSubmissionCatalogPayloadError(
                    f"SEC submissions acceptanceDateTime at index {index} is invalid"
                )
            entries.append(
                SecFilingCatalogEntry(
                    cik=cik,
                    accession=accession,
                    form=form,
                    filed_on=cls._date(
                        filing_dates[index],
                        f"filings.recent.filingDate[{index}]",
                    ),
                    report_period_end=cls._date(
                        report_dates[index],
                        f"filings.recent.reportDate[{index}]",
                    ),
                    acceptance_datetime_text=acceptance,
                    primary_document=cls._text(
                        primary_documents[index],
                        f"filings.recent.primaryDocument[{index}]",
                    ),
                )
            )
        return tuple(sorted(entries, key=lambda item: (item.filed_on, item.accession)))

    @classmethod
    def _history_pages(
        cls,
        filings: dict[str, object],
    ) -> tuple[SecSubmissionHistoryPage, ...]:
        raw_pages = cls._array(filings.get("files", []), "filings.files")
        pages: list[SecSubmissionHistoryPage] = []
        seen_names: set[str] = set()
        for index, raw_page in enumerate(raw_pages):
            page = cls._object(raw_page, f"filings.files[{index}]")
            name = cls._text(page.get("name"), f"filings.files[{index}].name")
            if not HISTORY_FILE_PATTERN.fullmatch(name) or ".." in name:
                raise SecSubmissionCatalogPayloadError(
                    f"SEC submissions history filename at index {index} is invalid"
                )
            if name in seen_names:
                raise SecSubmissionCatalogPayloadError(
                    "SEC submissions contains duplicate history filenames"
                )
            seen_names.add(name)
            filing_count = page.get("filingCount")
            if (
                not isinstance(filing_count, int)
                or isinstance(filing_count, bool)
                or filing_count < 1
            ):
                raise SecSubmissionCatalogPayloadError(
                    f"SEC submissions filingCount at index {index} must be positive"
                )
            history_page = SecSubmissionHistoryPage(
                name=name,
                filing_count=filing_count,
                filing_from=cls._date(
                    page.get("filingFrom"),
                    f"filings.files[{index}].filingFrom",
                ),
                filing_to=cls._date(
                    page.get("filingTo"),
                    f"filings.files[{index}].filingTo",
                ),
            )
            if history_page.filing_to < history_page.filing_from:
                raise SecSubmissionCatalogPayloadError(
                    f"SEC submissions history dates at index {index} are reversed"
                )
            pages.append(history_page)
        return tuple(sorted(pages, key=lambda item: (item.filing_from, item.name)))

    @classmethod
    def _decode_json(cls, content: bytes) -> dict[str, object]:
        if not isinstance(content, bytes) or not content:
            raise SecSubmissionCatalogPayloadError("SEC submissions payload must contain bytes")
        try:
            payload: object = json.loads(content.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SecSubmissionCatalogPayloadError(
                "SEC submissions payload is not valid UTF-8 JSON"
            ) from error
        return cls._object(payload, "root")

    def fetch(self, reference: str) -> SecSubmissionCatalog:
        """Fetch one current CIK snapshot while keeping acceptance text non-authoritative."""

        cik = self._cik(reference)
        source_uri = f"{SEC_SUBMISSIONS_ROOT}/CIK{cik}.json"
        content = self._fetch_bytes(source_uri)
        root = self._decode_json(content)
        payload_cik = root.get("cik")
        if isinstance(payload_cik, bool) or not isinstance(payload_cik, (str, int)):
            raise SecSubmissionCatalogPayloadError("SEC submissions field cik is invalid")
        try:
            normalized_payload_cik = self._cik(str(payload_cik))
        except InvalidSourceReferenceError as error:
            raise SecSubmissionCatalogPayloadError(
                "SEC submissions field cik is invalid"
            ) from error
        if normalized_payload_cik != cik:
            raise SecSubmissionCatalogPayloadError(
                "SEC submissions CIK does not match the reference"
            )

        tickers = self._array(root.get("tickers", []), "tickers")
        exchanges = self._array(root.get("exchanges", []), "exchanges")
        if len(tickers) != len(exchanges):
            raise SecSubmissionCatalogPayloadError(
                "SEC ticker and exchange arrays have inconsistent length"
            )
        ticker_exchange_pairs = tuple(
            (
                self._text(ticker, f"tickers[{index}]").upper(),
                self._text(exchanges[index], f"exchanges[{index}]"),
            )
            for index, ticker in enumerate(tickers)
        )
        if len(ticker_exchange_pairs) != len(set(ticker_exchange_pairs)):
            raise SecSubmissionCatalogPayloadError(
                "SEC ticker and exchange aliases contain duplicates"
            )

        filings = self._object(root.get("filings"), "filings")
        recent = self._object(filings.get("recent"), "filings.recent")
        accessions = self._array(
            recent.get("accessionNumber"),
            "filings.recent.accessionNumber",
        )
        return SecSubmissionCatalog(
            cik=cik,
            company_name=self._text(root.get("name"), "name"),
            ticker_exchange_pairs=ticker_exchange_pairs,
            entries=self._entries(recent, cik),
            history_pages=self._history_pages(filings),
            source_uri=source_uri,
            content_hash=sha256(content).hexdigest(),
            total_recent_filings=len(accessions),
            content=content,
        )

    def fetch_history_page(
        self,
        *,
        cik: str,
        page: SecSubmissionHistoryPage,
    ) -> SecSubmissionHistorySnapshot:
        """Fetch one exact older page only when it was declared by a current catalog."""

        normalized_cik = self._cik(cik)
        if not HISTORY_FILE_PATTERN.fullmatch(page.name) or ".." in page.name:
            raise InvalidSourceReferenceError("SEC submissions history page name is invalid")
        source_uri = f"{SEC_SUBMISSIONS_ROOT}/{page.name}"
        content = self._fetch_bytes(source_uri)
        root = self._decode_json(content)
        accessions = self._array(root.get("accessionNumber"), "filings.recent.accessionNumber")
        return SecSubmissionHistorySnapshot(
            cik=normalized_cik,
            page_name=page.name,
            entries=self._entries(root, normalized_cik),
            source_uri=source_uri,
            content_hash=sha256(content).hexdigest(),
            total_filings=len(accessions),
            content=content,
        )
