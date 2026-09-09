"""Pinned Arelle boundary for raw SEC statement and calculation observations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from asymmetric_engine.application.evidence_ingestion import SourceDocumentRepository
from asymmetric_engine.application.sec_fact_admission import SecStatementObservation
from asymmetric_engine.application.sec_xbrl_extraction import (
    SecXbrlCandidate,
    SecXbrlCandidateSet,
    validate_sec_xbrl_candidate_set_integrity,
)
from asymmetric_engine.application.source_verification import load_verified_source_document
from asymmetric_engine.infrastructure.providers.arelle_xbrl import (
    ARELLE_PINNED_VERSION,
    ArelleBridgeError,
    ArelleVersionMismatchError,
)


class PinnedArelleStatementInspectorBridge:
    """Expose raw relationship observations while keeping reconciliation authority in AIE."""

    inspector_name = "Arelle"

    def __init__(
        self,
        *,
        repository: SourceDocumentRepository,
        reported_version: str,
        inspector: Callable[[bytes, str, SecXbrlCandidate], SecStatementObservation],
    ) -> None:
        normalized_version = reported_version.strip()
        if normalized_version != ARELLE_PINNED_VERSION:
            raise ArelleVersionMismatchError(
                f"Arelle {normalized_version!r} does not match pin {ARELLE_PINNED_VERSION!r}"
            )
        self.inspector_version = normalized_version
        self._repository = repository
        self._inspector = inspector

    def inspect(
        self,
        *,
        candidate: SecXbrlCandidate,
        candidate_set: SecXbrlCandidateSet,
    ) -> SecStatementObservation:
        """Inspect the exact verified complete-submission bytes for one candidate."""

        validate_sec_xbrl_candidate_set_integrity(candidate_set)
        if candidate not in candidate_set.candidates:
            raise ArelleBridgeError("candidate is not a member of the supplied extraction set")

        document = load_verified_source_document(
            self._repository,
            candidate_set.source_document_id,
        )
        if document.content_hash != candidate_set.source_content_hash:
            raise ArelleBridgeError(
                "candidate set source hash does not match verified SEC evidence"
            )
        if document.provider_version != candidate_set.accession:
            raise ArelleBridgeError("candidate set accession does not match verified SEC evidence")

        content = self._repository.read_content(document.document_id)
        observation = self._inspector(content, document.source_uri, candidate)
        if not isinstance(observation, SecStatementObservation):
            raise ArelleBridgeError("Arelle statement inspector returned an invalid observation")
        return replace(
            observation,
            inspector_name=self.inspector_name,
            inspector_version=self.inspector_version,
        )
