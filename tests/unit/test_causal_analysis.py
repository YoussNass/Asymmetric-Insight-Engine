"""Tests for deterministic construction from verified source-ledger bytes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.causal_analysis import (
    BuildCausalAnalysis,
    CausalAnalysisSourceIntegrityError,
    CausalAnalysisSourceNotFoundError,
)
from asymmetric_engine.application.evidence_ingestion import AppendResult, AppendStatus
from asymmetric_engine.domain.causal import CausalAnalysis, CausalAnalysisDraft
from asymmetric_engine.domain.evidence import SourceDocument
from tests.causal_factories import RECORDED_AT, make_causal_draft, make_reference_sources


@dataclass
class MemorySourceRepository:
    documents: dict[UUID, SourceDocument]
    contents: dict[UUID, bytes]

    def append(self, document: SourceDocument, content: bytes) -> AppendResult:
        status = (
            AppendStatus.ALREADY_PRESENT
            if document.document_id in self.documents
            else AppendStatus.INSERTED
        )
        self.documents[document.document_id] = document
        self.contents[document.document_id] = content
        return AppendResult(status=status, document=document)

    def list_by_subject(self, subject_id: str) -> tuple[SourceDocument, ...]:
        return tuple(
            document for document in self.documents.values() if document.subject_id == subject_id
        )

    def get(self, document_id: UUID) -> SourceDocument:
        try:
            return self.documents[document_id]
        except KeyError as error:
            raise KeyError(document_id) from error

    def read_content(self, document_id: UUID) -> bytes:
        try:
            return self.contents[document_id]
        except KeyError as error:
            raise KeyError(document_id) from error


def make_repository() -> tuple[MemorySourceRepository, CausalAnalysisDraft]:
    documents, contents = make_reference_sources()
    repository = MemorySourceRepository(
        documents={document.document_id: document for document in documents},
        contents=contents,
    )
    return repository, make_causal_draft(documents=documents)


def rebuild(draft: CausalAnalysisDraft, **overrides: object) -> CausalAnalysisDraft:
    values = draft.model_dump(mode="python")
    values.update(overrides)
    return CausalAnalysisDraft.model_validate(values)


def test_builder_produces_a_deterministic_content_addressed_analysis() -> None:
    repository, draft = make_repository()
    builder = BuildCausalAnalysis(repository)

    first = builder.execute(draft)
    second = builder.execute(draft)

    assert first == second
    assert first.analysis_id.version == 5
    assert len(first.input_fingerprint) == 64
    assert tuple(document.document_id for document in first.source_documents) == tuple(
        sorted(draft.source_document_ids, key=str)
    )


def test_fingerprint_ignores_semantically_irrelevant_collection_order() -> None:
    repository, draft = make_repository()
    reordered = rebuild(
        draft,
        source_document_ids=tuple(reversed(draft.source_document_ids)),
        nodes=tuple(reversed(draft.nodes)),
        edges=tuple(reversed(draft.edges)),
        evidence=tuple(reversed(draft.evidence)),
        claims=tuple(reversed(draft.claims)),
        invalidation_conditions=tuple(reversed(draft.invalidation_conditions)),
        missing_data=tuple(reversed(draft.missing_data)),
        assumptions=tuple(reversed(draft.assumptions)),
    )
    builder = BuildCausalAnalysis(repository)

    assert builder.execute(reordered) == builder.execute(draft)


def test_fingerprint_changes_when_a_material_mechanism_changes() -> None:
    repository, draft = make_repository()
    changed_edge = draft.edges[0].model_copy(
        update={"mechanism": "A materially different causal mechanism."}
    )
    changed = rebuild(draft, edges=(changed_edge, *draft.edges[1:]))
    builder = BuildCausalAnalysis(repository)

    assert builder.execute(changed).input_fingerprint != builder.execute(draft).input_fingerprint


def test_fingerprint_changes_when_an_immutable_source_version_changes() -> None:
    repository, draft = make_repository()
    baseline = BuildCausalAnalysis(repository).execute(draft)
    nvidia = next(
        document
        for document in repository.documents.values()
        if document.subject_id == "company:sec-cik-0001045810"
    )
    replacement = nvidia.model_copy(
        update={
            "document_id": UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
            "provider_version": "0001045810-24-999999",
            "source_uri": "https://www.sec.gov/Archives/edgar/data/1045810/replacement.txt",
        }
    )
    documents = tuple(
        replacement if document.document_id == nvidia.document_id else document
        for document in repository.documents.values()
    )
    replacement_repository = MemorySourceRepository(
        documents={document.document_id: document for document in documents},
        contents={
            replacement.document_id if document_id == nvidia.document_id else document_id: content
            for document_id, content in repository.contents.items()
        },
    )
    changed = make_causal_draft(documents=(documents[0], documents[1]))

    assert (
        BuildCausalAnalysis(replacement_repository).execute(changed).input_fingerprint
        != baseline.input_fingerprint
    )


def test_builder_fails_closed_when_a_source_or_its_content_is_missing() -> None:
    repository, draft = make_repository()
    missing_id = draft.source_document_ids[0]
    del repository.documents[missing_id]

    with pytest.raises(CausalAnalysisSourceNotFoundError, match=str(missing_id)):
        BuildCausalAnalysis(repository).execute(draft)

    repository, draft = make_repository()
    del repository.contents[draft.source_document_ids[0]]
    with pytest.raises(CausalAnalysisSourceNotFoundError, match="missing"):
        BuildCausalAnalysis(repository).execute(draft)


def test_builder_detects_stored_content_size_and_hash_corruption() -> None:
    repository, draft = make_repository()
    document_id = draft.source_document_ids[0]
    repository.contents[document_id] += b"altered"
    with pytest.raises(CausalAnalysisSourceIntegrityError, match="byte length"):
        BuildCausalAnalysis(repository).execute(draft)

    repository, draft = make_repository()
    document_id = draft.source_document_ids[0]
    original = repository.contents[document_id]
    repository.contents[document_id] = bytes([original[0] ^ 1]) + original[1:]
    with pytest.raises(CausalAnalysisSourceIntegrityError, match="SHA-256"):
        BuildCausalAnalysis(repository).execute(draft)


def test_verified_analysis_rejects_evidence_provenance_mismatch() -> None:
    repository, draft = make_repository()
    document_id = draft.source_document_ids[0]
    repository.documents[document_id] = repository.documents[document_id].model_copy(
        update={"source_uri": "https://example.test/different-source"}
    )

    with pytest.raises(ValidationError, match="provenance does not match"):
        BuildCausalAnalysis(repository).execute(draft)


def test_verified_analysis_rejects_duplicate_or_incomplete_document_sets() -> None:
    repository, draft = make_repository()
    analysis = BuildCausalAnalysis(repository).execute(draft)
    values = analysis.model_dump(mode="python")
    values["source_documents"] = (*analysis.source_documents, analysis.source_documents[0])
    with pytest.raises(ValidationError, match="duplicate source documents"):
        CausalAnalysis.model_validate(values)

    values["source_documents"] = analysis.source_documents[1:]
    with pytest.raises(ValidationError, match="must match source_document_ids"):
        CausalAnalysis.model_validate(values)


def test_verified_analysis_rejects_future_sources_and_unbacked_beneficiaries() -> None:
    repository, draft = make_repository()
    analysis = BuildCausalAnalysis(repository).execute(draft)
    values = analysis.model_dump(mode="python")
    future = analysis.source_documents[0].model_copy(
        update={
            "available_at": RECORDED_AT + timedelta(days=3),
            "recorded_at": RECORDED_AT + timedelta(days=3),
        }
    )
    values["source_documents"] = (future, *analysis.source_documents[1:])
    with pytest.raises(ValidationError, match="outside the knowledge boundary"):
        CausalAnalysis.model_validate(values)

    values = analysis.model_dump(mode="python")
    micron = next(
        document
        for document in analysis.source_documents
        if document.subject_id == "company:sec-cik-0000723125"
    )
    replacement_subject = micron.model_copy(update={"subject_id": "company:sec-cik-9999999999"})
    values["source_documents"] = tuple(
        replacement_subject if document.document_id == micron.document_id else document
        for document in analysis.source_documents
    )
    with pytest.raises(ValidationError, match="every beneficiary"):
        CausalAnalysis.model_validate(values)


def test_repository_append_and_subject_listing_preserve_protocol_semantics() -> None:
    repository, draft = make_repository()
    document = repository.get(draft.source_document_ids[0])
    content = repository.read_content(document.document_id)

    assert repository.append(document, content).status is AppendStatus.ALREADY_PRESENT
    assert repository.list_by_subject(document.subject_id) == (document,)

    new_document = document.model_copy(update={"document_id": uuid4()})
    assert repository.append(new_document, content).status is AppendStatus.INSERTED
