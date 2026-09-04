"""Point-in-time SEC source-universe contracts for Chapter 11A."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from typing import Protocol

from asymmetric_engine.application.evidence_ingestion import AppendResult


class SecSourceManifestError(ValueError):
    """Raised when SEC catalog pages cannot support a complete expected-source manifest."""


@dataclass(frozen=True, slots=True)
class SecFilingCatalogEntry:
    """One admitted SEC filing identity discovered in a submissions snapshot."""

    cik: str
    accession: str
    form: str
    filed_on: date
    report_period_end: date
    acceptance_datetime_text: str
    primary_document: str

    @property
    def reference(self) -> str:
        """Return the exact reference consumed by the complete-submission provider."""

        return f"{self.cik}/{self.accession}"


@dataclass(frozen=True, slots=True)
class SecSubmissionHistoryPage:
    """One older SEC submissions page declared by the current catalog."""

    name: str
    filing_count: int
    filing_from: date
    filing_to: date


@dataclass(frozen=True, slots=True)
class SecSubmissionCatalog:
    """Content-addressed view of one exact current SEC submissions response."""

    cik: str
    company_name: str
    ticker_exchange_pairs: tuple[tuple[str, str], ...]
    entries: tuple[SecFilingCatalogEntry, ...]
    history_pages: tuple[SecSubmissionHistoryPage, ...]
    source_uri: str
    content_hash: str
    total_recent_filings: int
    content: bytes = field(repr=False)

    @property
    def subject_id(self) -> str:
        return f"company:sec-cik-{self.cik}"

    @property
    def history_complete(self) -> bool:
        """Remain false while the current response declares unfetched older pages."""

        return not self.history_pages

    @property
    def warnings(self) -> tuple[str, ...]:
        if self.history_complete:
            return ()
        return ("additional_sec_history_pages_not_fetched",)


@dataclass(frozen=True, slots=True)
class SecSubmissionHistorySnapshot:
    """One exact older-history page fetched from the SEC submissions service."""

    cik: str
    page_name: str
    entries: tuple[SecFilingCatalogEntry, ...]
    source_uri: str
    content_hash: str
    total_filings: int
    content: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class SecExpectedSourceManifest:
    """Complete content-addressed expected filing universe for one SEC catalog snapshot set."""

    cik: str
    subject_id: str
    catalog_content_hashes: tuple[str, ...]
    catalog_source_uris: tuple[str, ...]
    expected_filings: tuple[SecFilingCatalogEntry, ...]
    history_page_names: tuple[str, ...]
    manifest_hash: str
    manifest_version: str = "sec-expected-source-manifest-v1"

    @property
    def expected_references(self) -> tuple[str, ...]:
        return tuple(entry.reference for entry in self.expected_filings)


class SecSubmissionsCatalogProvider(Protocol):
    """Replaceable provider for exact current and older SEC submissions pages."""

    def fetch(self, reference: str) -> SecSubmissionCatalog:
        """Fetch one exact current submissions snapshot by CIK."""

    def fetch_history_page(
        self,
        *,
        cik: str,
        page: SecSubmissionHistoryPage,
    ) -> SecSubmissionHistorySnapshot:
        """Fetch one exact older page declared by the current snapshot."""


class SecSourceIngestor(Protocol):
    """Narrow ingestion port used to capture one manifest-declared complete submission."""

    def execute(self, reference: str) -> AppendResult:
        """Ingest one exact source reference through the canonical Evidence Ledger path."""


class BuildSecExpectedSourceManifest:
    """Reconcile every declared submissions page before claiming source-universe completeness."""

    _VERSION = "sec-expected-source-manifest-v1"

    @staticmethod
    def _canonical_payload(
        *,
        current: SecSubmissionCatalog,
        pages: tuple[SecSubmissionHistorySnapshot, ...],
        filings: tuple[SecFilingCatalogEntry, ...],
    ) -> bytes:
        payload = {
            "version": BuildSecExpectedSourceManifest._VERSION,
            "cik": current.cik,
            "subject_id": current.subject_id,
            "catalogs": [
                {"source_uri": current.source_uri, "content_hash": current.content_hash},
                *[
                    {"source_uri": page.source_uri, "content_hash": page.content_hash}
                    for page in pages
                ],
            ],
            "expected_filings": [
                {
                    "accession": item.accession,
                    "form": item.form,
                    "filed_on": item.filed_on.isoformat(),
                    "report_period_end": item.report_period_end.isoformat(),
                    "primary_document": item.primary_document,
                }
                for item in filings
            ],
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()

    def execute(
        self,
        *,
        current: SecSubmissionCatalog,
        history_pages: tuple[SecSubmissionHistorySnapshot, ...],
    ) -> SecExpectedSourceManifest:
        """Build a complete manifest only after all current-snapshot history pages reconcile."""

        expected_descriptors = {page.name: page for page in current.history_pages}
        if len(expected_descriptors) != len(current.history_pages):
            raise SecSourceManifestError("current SEC catalog contains duplicate history pages")

        supplied_by_name: dict[str, SecSubmissionHistorySnapshot] = {}
        for snapshot in history_pages:
            if snapshot.page_name in supplied_by_name:
                raise SecSourceManifestError("duplicate fetched SEC history page")
            supplied_by_name[snapshot.page_name] = snapshot

        if set(supplied_by_name) != set(expected_descriptors):
            missing = sorted(set(expected_descriptors) - set(supplied_by_name))
            unexpected = sorted(set(supplied_by_name) - set(expected_descriptors))
            detail = ", ".join(
                part
                for part in (
                    f"missing={missing}" if missing else "",
                    f"unexpected={unexpected}" if unexpected else "",
                )
                if part
            )
            raise SecSourceManifestError(
                f"SEC history pages do not match the current expected-source catalog: {detail}"
            )

        ordered_pages: list[SecSubmissionHistorySnapshot] = []
        descriptors = sorted(
            current.history_pages,
            key=lambda item: (item.filing_from, item.name),
        )
        for descriptor in descriptors:
            snapshot = supplied_by_name[descriptor.name]
            if snapshot.cik != current.cik:
                raise SecSourceManifestError("SEC history page CIK does not match current catalog")
            if snapshot.total_filings != descriptor.filing_count:
                raise SecSourceManifestError(
                    f"SEC history page {descriptor.name} filing count does not match descriptor"
                )
            for entry in snapshot.entries:
                if not descriptor.filing_from <= entry.filed_on <= descriptor.filing_to:
                    raise SecSourceManifestError(
                        f"SEC history page {descriptor.name} contains an out-of-range filing"
                    )
            ordered_pages.append(snapshot)

        all_entries = [*current.entries]
        for snapshot in ordered_pages:
            all_entries.extend(snapshot.entries)
        seen_accessions: set[str] = set()
        for entry in all_entries:
            if entry.cik != current.cik:
                raise SecSourceManifestError("SEC filing CIK does not match manifest subject")
            if entry.accession in seen_accessions:
                raise SecSourceManifestError(
                    "SEC expected-source pages contain a duplicate admitted accession"
                )
            seen_accessions.add(entry.accession)

        filings = tuple(sorted(all_entries, key=lambda item: (item.filed_on, item.accession)))
        pages = tuple(ordered_pages)
        canonical = self._canonical_payload(current=current, pages=pages, filings=filings)
        return SecExpectedSourceManifest(
            cik=current.cik,
            subject_id=current.subject_id,
            catalog_content_hashes=(current.content_hash, *(page.content_hash for page in pages)),
            catalog_source_uris=(current.source_uri, *(page.source_uri for page in pages)),
            expected_filings=filings,
            history_page_names=tuple(page.page_name for page in pages),
            manifest_hash=sha256(canonical).hexdigest(),
        )


class DiscoverSecExpectedSourceManifest:
    """Fetch the current catalog and every declared older page before building the manifest."""

    def __init__(self, provider: SecSubmissionsCatalogProvider) -> None:
        self._provider = provider
        self._builder = BuildSecExpectedSourceManifest()

    def execute(self, cik: str) -> SecExpectedSourceManifest:
        """Discover a complete admitted filing universe for one exact current catalog version."""

        current = self._provider.fetch(cik)
        history_pages = tuple(
            self._provider.fetch_history_page(cik=current.cik, page=page)
            for page in current.history_pages
        )
        return self._builder.execute(current=current, history_pages=history_pages)


class CaptureSecExpectedSources:
    """Ingest every accession declared by a complete immutable expected-source manifest."""

    def __init__(self, ingestor: SecSourceIngestor) -> None:
        self._ingestor = ingestor

    def execute(self, manifest: SecExpectedSourceManifest) -> tuple[AppendResult, ...]:
        """Capture exact complete-submission bytes additively in deterministic manifest order."""

        references = manifest.expected_references
        return tuple(self._ingestor.execute(reference) for reference in references)
