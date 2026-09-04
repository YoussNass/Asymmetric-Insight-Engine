"""Versioned shadow XBRL extraction over verified SEC filing evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from hashlib import sha256
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from asymmetric_engine.application.evidence_ingestion import SourceDocumentRepository
from asymmetric_engine.application.source_verification import load_verified_source_document
from asymmetric_engine.domain.evidence import SourceType


class SecXbrlExtractionError(RuntimeError):
    """Raised when an XBRL processor output cannot support a trustworthy shadow candidate set."""


class SecXbrlPeriodKind(StrEnum):
    """Period shape retained from the XBRL context."""

    INSTANT = "instant"
    DURATION = "duration"


class SecXbrlAuthority(StrEnum):
    """Decision authority of a Chapter 11B extraction result."""

    SHADOW_ONLY = "shadow_only"


@dataclass(frozen=True, slots=True, order=True)
class SecXbrlDimension:
    """One explicit or typed dimension retained without semantic remapping."""

    axis_namespace: str
    axis_name: str
    member_namespace: str | None
    member_name: str
    typed_member: bool = False


@dataclass(frozen=True, slots=True)
class ProcessorXbrlFact:
    """Untrusted normalized output expected from a standards-compliant XBRL processor."""

    concept_namespace: str
    concept_name: str
    context_id: str
    period_kind: SecXbrlPeriodKind
    period_start: date | None
    period_end: date
    unit_id: str | None
    unit_numerator: tuple[str, ...]
    unit_denominator: tuple[str, ...]
    dimensions: tuple[SecXbrlDimension, ...]
    decimals: str | None
    precision: str | None
    raw_value: str
    is_numeric: bool
    is_nil: bool
    source_locator: str


class StandardsXbrlProcessor(Protocol):
    """Replaceable standards processor isolated from AIE semantic normalization."""

    processor_name: str
    processor_version: str

    def extract(self, *, content: bytes, source_uri: str) -> tuple[ProcessorXbrlFact, ...]:
        """Return raw processor facts without assigning AIE financial meaning."""


@dataclass(frozen=True, slots=True)
class SecXbrlCandidate:
    """Immutable shadow candidate with complete source and extraction lineage."""

    candidate_id: str
    source_document_id: UUID
    source_content_hash: str
    accession: str
    concept_namespace: str
    concept_name: str
    context_id: str
    period_kind: SecXbrlPeriodKind
    period_start: date | None
    period_end: date
    unit_id: str | None
    unit_numerator: tuple[str, ...]
    unit_denominator: tuple[str, ...]
    dimensions: tuple[SecXbrlDimension, ...]
    decimals: str | None
    precision: str | None
    raw_value: str
    is_numeric: bool
    is_nil: bool
    source_locator: str
    processor_name: str
    processor_version: str
    extraction_method: str
    extraction_version: str
    authority: SecXbrlAuthority = SecXbrlAuthority.SHADOW_ONLY


@dataclass(frozen=True, slots=True)
class SecXbrlCandidateSet:
    """Content-addressed shadow extraction result for one exact SEC filing version."""

    extraction_id: UUID
    input_fingerprint: str
    source_document_id: UUID
    source_content_hash: str
    accession: str
    processor_name: str
    processor_version: str
    extraction_method: str
    extraction_version: str
    candidates: tuple[SecXbrlCandidate, ...]
    warnings: tuple[str, ...]
    authority: SecXbrlAuthority = SecXbrlAuthority.SHADOW_ONLY


def _fact_payload(fact: ProcessorXbrlFact) -> dict[str, object]:
    return {
        "concept_namespace": fact.concept_namespace,
        "concept_name": fact.concept_name,
        "context_id": fact.context_id,
        "period_kind": fact.period_kind.value,
        "period_start": fact.period_start.isoformat() if fact.period_start else None,
        "period_end": fact.period_end.isoformat(),
        "unit_id": fact.unit_id,
        "unit_numerator": fact.unit_numerator,
        "unit_denominator": fact.unit_denominator,
        "dimensions": [
            {
                "axis_namespace": item.axis_namespace,
                "axis_name": item.axis_name,
                "member_namespace": item.member_namespace,
                "member_name": item.member_name,
                "typed_member": item.typed_member,
            }
            for item in fact.dimensions
        ],
        "decimals": fact.decimals,
        "precision": fact.precision,
        "raw_value": fact.raw_value,
        "is_numeric": fact.is_numeric,
        "is_nil": fact.is_nil,
        "source_locator": fact.source_locator,
    }


def _candidate_as_processor_fact(candidate: SecXbrlCandidate) -> ProcessorXbrlFact:
    return ProcessorXbrlFact(
        concept_namespace=candidate.concept_namespace,
        concept_name=candidate.concept_name,
        context_id=candidate.context_id,
        period_kind=candidate.period_kind,
        period_start=candidate.period_start,
        period_end=candidate.period_end,
        unit_id=candidate.unit_id,
        unit_numerator=candidate.unit_numerator,
        unit_denominator=candidate.unit_denominator,
        dimensions=candidate.dimensions,
        decimals=candidate.decimals,
        precision=candidate.precision,
        raw_value=candidate.raw_value,
        is_numeric=candidate.is_numeric,
        is_nil=candidate.is_nil,
        source_locator=candidate.source_locator,
    )


def _serialize_fact(fact: ProcessorXbrlFact) -> str:
    return json.dumps(
        _fact_payload(fact),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _candidate_id(
    *,
    source_content_hash: str,
    processor_name: str,
    processor_version: str,
    extraction_version: str,
    serialized_fact: str,
) -> str:
    return sha256(
        (
            f"{source_content_hash}|{processor_name}|{processor_version}|"
            f"{extraction_version}|{serialized_fact}"
        ).encode()
    ).hexdigest()


def _candidate_set_fingerprint(candidate_set: SecXbrlCandidateSet) -> str:
    set_payload = {
        "source_document_id": str(candidate_set.source_document_id),
        "source_content_hash": candidate_set.source_content_hash,
        "accession": candidate_set.accession,
        "processor_name": candidate_set.processor_name,
        "processor_version": candidate_set.processor_version,
        "extraction_method": candidate_set.extraction_method,
        "extraction_version": candidate_set.extraction_version,
        "candidate_ids": [item.candidate_id for item in candidate_set.candidates],
    }
    canonical = json.dumps(
        set_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(canonical).hexdigest()


def validate_sec_xbrl_candidate_set_integrity(candidate_set: SecXbrlCandidateSet) -> None:
    """Recompute all content addresses and reject any candidate or set lineage drift."""

    if candidate_set.authority is not SecXbrlAuthority.SHADOW_ONLY:
        raise SecXbrlExtractionError("SEC XBRL candidate set must remain shadow-only")
    if candidate_set.warnings != ("shadow_extraction_not_admitted_for_underwriting",):
        raise SecXbrlExtractionError("SEC XBRL candidate set warning contract drifted")
    for field_name, value in (
        ("source_content_hash", candidate_set.source_content_hash),
        ("accession", candidate_set.accession),
        ("processor_name", candidate_set.processor_name),
        ("processor_version", candidate_set.processor_version),
        ("extraction_method", candidate_set.extraction_method),
        ("extraction_version", candidate_set.extraction_version),
    ):
        if not value.strip():
            raise SecXbrlExtractionError(f"SEC XBRL candidate set {field_name} must not be empty")

    seen_candidate_ids: set[str] = set()
    for candidate in candidate_set.candidates:
        if candidate.authority is not SecXbrlAuthority.SHADOW_ONLY:
            raise SecXbrlExtractionError("SEC XBRL candidate must remain shadow-only")
        if candidate.source_document_id != candidate_set.source_document_id:
            raise SecXbrlExtractionError("SEC XBRL candidate source document drifted from its set")
        if candidate.source_content_hash != candidate_set.source_content_hash:
            raise SecXbrlExtractionError("SEC XBRL candidate source hash drifted from its set")
        if candidate.accession != candidate_set.accession:
            raise SecXbrlExtractionError("SEC XBRL candidate accession drifted from its set")
        if candidate.processor_name != candidate_set.processor_name:
            raise SecXbrlExtractionError("SEC XBRL candidate processor name drifted from its set")
        if candidate.processor_version != candidate_set.processor_version:
            raise SecXbrlExtractionError("SEC XBRL candidate processor version drifted from its set")
        if candidate.extraction_method != candidate_set.extraction_method:
            raise SecXbrlExtractionError("SEC XBRL candidate extraction method drifted from its set")
        if candidate.extraction_version != candidate_set.extraction_version:
            raise SecXbrlExtractionError("SEC XBRL candidate extraction version drifted from its set")
        if candidate.candidate_id in seen_candidate_ids:
            raise SecXbrlExtractionError("SEC XBRL candidate set contains duplicate candidate ids")
        seen_candidate_ids.add(candidate.candidate_id)

        expected_candidate_id = _candidate_id(
            source_content_hash=candidate_set.source_content_hash,
            processor_name=candidate_set.processor_name,
            processor_version=candidate_set.processor_version,
            extraction_version=candidate_set.extraction_version,
            serialized_fact=_serialize_fact(_candidate_as_processor_fact(candidate)),
        )
        if candidate.candidate_id != expected_candidate_id:
            raise SecXbrlExtractionError("SEC XBRL candidate content address does not match payload")

    expected_fingerprint = _candidate_set_fingerprint(candidate_set)
    if candidate_set.input_fingerprint != expected_fingerprint:
        raise SecXbrlExtractionError("SEC XBRL candidate-set fingerprint does not match payload")
    expected_extraction_id = uuid5(
        NAMESPACE_URL,
        f"asymmetric-insight-engine:sec-xbrl-shadow:{expected_fingerprint}",
    )
    if candidate_set.extraction_id != expected_extraction_id:
        raise SecXbrlExtractionError("SEC XBRL extraction id does not match candidate-set fingerprint")


class ExtractSecXbrlCandidates:
    """Verify source bytes, validate processor output, and create shadow-only candidates."""

    _METHOD = "sec-xbrl-shadow-extraction"
    _VERSION = "sec-xbrl-shadow-v1"

    def __init__(
        self,
        *,
        repository: SourceDocumentRepository,
        processor: StandardsXbrlProcessor,
    ) -> None:
        self._repository = repository
        self._processor = processor

    @staticmethod
    def _required_text(value: str, field: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise SecXbrlExtractionError(f"processor fact {field} must not be empty")
        return normalized

    @classmethod
    def _validate_dimension(cls, dimension: SecXbrlDimension) -> SecXbrlDimension:
        axis_namespace = cls._required_text(dimension.axis_namespace, "axis_namespace")
        axis_name = cls._required_text(dimension.axis_name, "axis_name")
        member_name = cls._required_text(dimension.member_name, "member_name")
        member_namespace = dimension.member_namespace
        if dimension.typed_member:
            if member_namespace is not None:
                raise SecXbrlExtractionError(
                    "typed XBRL dimensions must not fabricate a member namespace"
                )
        else:
            if member_namespace is None:
                raise SecXbrlExtractionError("explicit XBRL dimensions require a member namespace")
            member_namespace = cls._required_text(member_namespace, "member_namespace")
        return SecXbrlDimension(
            axis_namespace=axis_namespace,
            axis_name=axis_name,
            member_namespace=member_namespace,
            member_name=member_name,
            typed_member=dimension.typed_member,
        )

    @classmethod
    def _normalize_fact(cls, fact: ProcessorXbrlFact) -> ProcessorXbrlFact:
        concept_namespace = cls._required_text(fact.concept_namespace, "concept_namespace")
        concept_name = cls._required_text(fact.concept_name, "concept_name")
        context_id = cls._required_text(fact.context_id, "context_id")
        locator = cls._required_text(fact.source_locator, "source_locator")
        if fact.period_kind is SecXbrlPeriodKind.INSTANT:
            if fact.period_start is not None:
                raise SecXbrlExtractionError("instant XBRL context must not provide period_start")
        elif fact.period_start is None:
            raise SecXbrlExtractionError("duration XBRL context requires period_start")
        elif fact.period_end < fact.period_start:
            raise SecXbrlExtractionError("duration XBRL context has reversed dates")

        dimensions = tuple(sorted(cls._validate_dimension(item) for item in fact.dimensions))
        axis_keys = {(item.axis_namespace, item.axis_name) for item in dimensions}
        if len(axis_keys) != len(dimensions):
            raise SecXbrlExtractionError("XBRL context contains duplicate dimension axes")

        unit_id = fact.unit_id.strip() if fact.unit_id is not None else None
        if unit_id == "":
            raise SecXbrlExtractionError("processor fact unit_id must not be blank")
        numerator = tuple(
            sorted(cls._required_text(item, "unit_numerator") for item in fact.unit_numerator)
        )
        denominator = tuple(
            sorted(cls._required_text(item, "unit_denominator") for item in fact.unit_denominator)
        )
        if fact.is_numeric and not numerator:
            raise SecXbrlExtractionError("numeric XBRL fact requires a unit numerator")
        if not fact.is_numeric and (numerator or denominator or unit_id is not None):
            raise SecXbrlExtractionError("non-numeric XBRL fact must not carry a numeric unit")
        if fact.is_nil and fact.raw_value.strip():
            raise SecXbrlExtractionError("nil XBRL fact must not carry a non-empty raw value")

        decimals = fact.decimals.strip() if fact.decimals is not None else None
        precision = fact.precision.strip() if fact.precision is not None else None
        if decimals == "" or precision == "":
            raise SecXbrlExtractionError("XBRL decimals and precision metadata must not be blank")

        return ProcessorXbrlFact(
            concept_namespace=concept_namespace,
            concept_name=concept_name,
            context_id=context_id,
            period_kind=fact.period_kind,
            period_start=fact.period_start,
            period_end=fact.period_end,
            unit_id=unit_id,
            unit_numerator=numerator,
            unit_denominator=denominator,
            dimensions=dimensions,
            decimals=decimals,
            precision=precision,
            raw_value=fact.raw_value,
            is_numeric=fact.is_numeric,
            is_nil=fact.is_nil,
            source_locator=locator,
        )

    def execute(self, source_document_id: UUID) -> SecXbrlCandidateSet:
        """Extract one exact filing into shadow candidates with no Underwriting authority."""

        document = load_verified_source_document(self._repository, source_document_id)
        if document.provider != "sec-edgar" or document.source_type is not SourceType.FILING:
            raise SecXbrlExtractionError("Chapter 11B accepts only verified SEC filing evidence")
        accession = document.provider_version.strip()
        if not accession:
            raise SecXbrlExtractionError("SEC filing source is missing its accession version")
        processor_name = self._required_text(self._processor.processor_name, "processor_name")
        processor_version = self._required_text(
            self._processor.processor_version,
            "processor_version",
        )
        content = self._repository.read_content(source_document_id)
        raw_facts = self._processor.extract(content=content, source_uri=document.source_uri)
        normalized_facts = tuple(self._normalize_fact(fact) for fact in raw_facts)

        serialized_payloads = [_serialize_fact(fact) for fact in normalized_facts]
        if len(serialized_payloads) != len(set(serialized_payloads)):
            raise SecXbrlExtractionError("standards processor emitted duplicate XBRL facts")
        ordered_pairs = sorted(zip(serialized_payloads, normalized_facts, strict=True))

        candidates: list[SecXbrlCandidate] = []
        for serialized, fact in ordered_pairs:
            candidate_id = _candidate_id(
                source_content_hash=document.content_hash,
                processor_name=processor_name,
                processor_version=processor_version,
                extraction_version=self._VERSION,
                serialized_fact=serialized,
            )
            candidates.append(
                SecXbrlCandidate(
                    candidate_id=candidate_id,
                    source_document_id=document.document_id,
                    source_content_hash=document.content_hash,
                    accession=accession,
                    concept_namespace=fact.concept_namespace,
                    concept_name=fact.concept_name,
                    context_id=fact.context_id,
                    period_kind=fact.period_kind,
                    period_start=fact.period_start,
                    period_end=fact.period_end,
                    unit_id=fact.unit_id,
                    unit_numerator=fact.unit_numerator,
                    unit_denominator=fact.unit_denominator,
                    dimensions=fact.dimensions,
                    decimals=fact.decimals,
                    precision=fact.precision,
                    raw_value=fact.raw_value,
                    is_numeric=fact.is_numeric,
                    is_nil=fact.is_nil,
                    source_locator=fact.source_locator,
                    processor_name=processor_name,
                    processor_version=processor_version,
                    extraction_method=self._METHOD,
                    extraction_version=self._VERSION,
                )
            )

        provisional = SecXbrlCandidateSet(
            extraction_id=UUID(int=0),
            input_fingerprint="pending",
            source_document_id=document.document_id,
            source_content_hash=document.content_hash,
            accession=accession,
            processor_name=processor_name,
            processor_version=processor_version,
            extraction_method=self._METHOD,
            extraction_version=self._VERSION,
            candidates=tuple(candidates),
            warnings=("shadow_extraction_not_admitted_for_underwriting",),
        )
        fingerprint = _candidate_set_fingerprint(provisional)
        result = SecXbrlCandidateSet(
            extraction_id=uuid5(
                NAMESPACE_URL,
                f"asymmetric-insight-engine:sec-xbrl-shadow:{fingerprint}",
            ),
            input_fingerprint=fingerprint,
            source_document_id=provisional.source_document_id,
            source_content_hash=provisional.source_content_hash,
            accession=provisional.accession,
            processor_name=provisional.processor_name,
            processor_version=provisional.processor_version,
            extraction_method=provisional.extraction_method,
            extraction_version=provisional.extraction_version,
            candidates=provisional.candidates,
            warnings=provisional.warnings,
        )
        validate_sec_xbrl_candidate_set_integrity(result)
        return result
