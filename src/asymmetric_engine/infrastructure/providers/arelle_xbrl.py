"""Pinned bridge between SEC complete submissions and an external Arelle runtime."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from asymmetric_engine.application.sec_xbrl_extraction import ProcessorXbrlFact
from asymmetric_engine.infrastructure.providers.sec_edgar import SUPPORTED_FORMS

ARELLE_PINNED_VERSION = "2.44.5"
DOCUMENT_PATTERN = re.compile(rb"<DOCUMENT>(.*?)</DOCUMENT>", re.IGNORECASE | re.DOTALL)


class ArelleBridgeError(RuntimeError):
    """Raised when the isolated standards-processor boundary is unusable."""


class ArelleVersionMismatchError(ArelleBridgeError):
    """Raised when the runtime Arelle version differs from the reviewed pin."""


@dataclass(frozen=True, slots=True)
class SecSubmissionEntryPoint:
    """Primary filing document extracted from an already verified complete submission."""

    form: str
    filename: str
    content: bytes


class SecCompleteSubmissionEntryPointExtractor:
    """Extract the single admitted primary filing document without parsing XBRL semantics."""

    @staticmethod
    def _field(block: bytes, name: bytes) -> str:
        pattern = re.compile(rb"<" + name + rb">[ \t]*([^\r\n<]+)", re.IGNORECASE)
        match = pattern.search(block)
        if match is None:
            raise ArelleBridgeError(f"SEC submission document is missing {name.decode('ascii')}")
        try:
            value = match.group(1).decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError as error:
            raise ArelleBridgeError("SEC submission document metadata is not UTF-8") from error
        if not value:
            raise ArelleBridgeError("SEC submission document metadata must not be blank")
        return value

    def extract(self, content: bytes) -> SecSubmissionEntryPoint:
        """Return exactly one 10-K/Q primary document from complete-submission bytes."""

        matches: list[SecSubmissionEntryPoint] = []
        for match in DOCUMENT_PATTERN.finditer(content):
            block = match.group(1)
            form = self._field(block, b"TYPE").upper()
            if form not in SUPPORTED_FORMS:
                continue
            filename = self._field(block, b"FILENAME")
            text_match = re.search(rb"<TEXT>(.*?)</TEXT>", block, re.IGNORECASE | re.DOTALL)
            if text_match is None or not text_match.group(1).strip():
                raise ArelleBridgeError("SEC primary filing document is missing non-empty TEXT")
            matches.append(
                SecSubmissionEntryPoint(
                    form=form,
                    filename=filename,
                    content=text_match.group(1),
                )
            )
        if not matches:
            raise ArelleBridgeError("SEC complete submission contains no admitted primary document")
        if len(matches) != 1:
            raise ArelleBridgeError(
                "SEC complete submission contains multiple admitted primary documents"
            )
        return matches[0]


class PinnedArelleProcessorBridge:
    """Version-pin Arelle and isolate its output behind the Chapter 11B processor port."""

    processor_name = "Arelle"

    def __init__(
        self,
        *,
        reported_version: str,
        extractor: Callable[[bytes, str, str], tuple[ProcessorXbrlFact, ...]],
        entry_point_extractor: SecCompleteSubmissionEntryPointExtractor | None = None,
    ) -> None:
        normalized_version = reported_version.strip()
        if normalized_version != ARELLE_PINNED_VERSION:
            raise ArelleVersionMismatchError(
                f"Arelle {normalized_version!r} does not match pin {ARELLE_PINNED_VERSION!r}"
            )
        self.processor_version = normalized_version
        self._extractor = extractor
        self._entry_point_extractor = (
            entry_point_extractor or SecCompleteSubmissionEntryPointExtractor()
        )

    def extract(self, *, content: bytes, source_uri: str) -> tuple[ProcessorXbrlFact, ...]:
        """Send the primary filing bytes plus SEC base URI to the pinned standards processor."""

        normalized_source_uri = source_uri.strip()
        if not normalized_source_uri:
            raise ArelleBridgeError("source_uri must not be empty")
        entry_point = self._entry_point_extractor.extract(content)
        facts = self._extractor(
            entry_point.content,
            entry_point.filename,
            normalized_source_uri,
        )
        if not isinstance(facts, tuple):
            raise ArelleBridgeError("Arelle extractor must return an immutable tuple")
        return tuple(
            replace(fact, source_locator=f"{entry_point.filename}:{fact.source_locator}")
            for fact in facts
        )
