"""Build a deterministic causal analysis from verified immutable ledger sources."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from asymmetric_engine.application.evidence_ingestion import SourceDocumentRepository
from asymmetric_engine.domain.causal import CausalAnalysis, CausalAnalysisDraft
from asymmetric_engine.domain.evidence import SourceDocument


class CausalAnalysisSourceError(RuntimeError):
    """Base error for a causal analysis that cannot verify its declared source material."""


class CausalAnalysisSourceNotFoundError(CausalAnalysisSourceError):
    """Raised when a declared immutable source version is missing from the ledger."""


class CausalAnalysisSourceIntegrityError(CausalAnalysisSourceError):
    """Raised when stored bytes no longer match their immutable source metadata."""


class BuildCausalAnalysis:
    """Verify exact source bytes and issue a content-addressed analytical object."""

    def __init__(self, repository: SourceDocumentRepository) -> None:
        self._repository = repository

    def execute(self, draft: CausalAnalysisDraft) -> CausalAnalysis:
        """Build the same identifier for the same semantic input and exact source versions."""

        canonical_draft = self._canonicalize_draft(draft)
        documents = tuple(
            self._load_verified_document(document_id)
            for document_id in canonical_draft.source_document_ids
        )
        payload = {
            "draft": canonical_draft.model_dump(mode="json"),
            "source_documents": [document.model_dump(mode="json") for document in documents],
        }
        canonical_json = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        fingerprint = sha256(canonical_json).hexdigest()
        analysis_id = uuid5(
            NAMESPACE_URL,
            f"asymmetric-insight-engine:causal-analysis:{fingerprint}",
        )
        return CausalAnalysis.model_validate(
            {
                **canonical_draft.model_dump(mode="python"),
                "analysis_id": analysis_id,
                "input_fingerprint": fingerprint,
                "source_documents": documents,
            }
        )

    def _load_verified_document(self, document_id: UUID) -> SourceDocument:
        try:
            document = self._repository.get(document_id)
            content = self._repository.read_content(document_id)
        except KeyError as error:
            raise CausalAnalysisSourceNotFoundError(
                f"source document {document_id} is missing from the evidence ledger"
            ) from error
        if len(content) != document.content_size_bytes:
            raise CausalAnalysisSourceIntegrityError(
                f"source document {document_id} byte length does not match its metadata"
            )
        if sha256(content).hexdigest() != document.content_hash:
            raise CausalAnalysisSourceIntegrityError(
                f"source document {document_id} SHA-256 does not match its metadata"
            )
        return document

    @staticmethod
    def _canonicalize_draft(draft: CausalAnalysisDraft) -> CausalAnalysisDraft:
        values: dict[str, Any] = draft.model_dump(mode="python")
        values["source_document_ids"] = tuple(sorted(draft.source_document_ids, key=str))
        values["nodes"] = tuple(sorted(draft.nodes, key=lambda item: item.node_id))
        values["edges"] = tuple(
            sorted(
                (
                    edge.model_copy(update={"claim_ids": tuple(sorted(edge.claim_ids, key=str))})
                    for edge in draft.edges
                ),
                key=lambda item: item.edge_id,
            )
        )
        values["evidence"] = tuple(sorted(draft.evidence, key=lambda item: str(item.evidence_id)))
        values["claims"] = tuple(
            sorted(
                (
                    claim.model_copy(
                        update={"evidence_ids": tuple(sorted(claim.evidence_ids, key=str))}
                    )
                    for claim in draft.claims
                ),
                key=lambda item: str(item.claim_id),
            )
        )
        for field in (
            "invalidation_conditions",
            "missing_data",
            "conflicts",
            "assumptions",
        ):
            values[field] = tuple(sorted(getattr(draft, field)))
        return CausalAnalysisDraft.model_validate(values)
