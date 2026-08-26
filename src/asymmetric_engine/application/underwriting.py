"""Build a deterministic standalone opportunity assessment from verified sources."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from asymmetric_engine.application.evidence_ingestion import SourceDocumentRepository
from asymmetric_engine.application.source_verification import (
    SourceDocumentIntegrityError,
    SourceDocumentNotFoundError,
    SourceDocumentVerificationError,
    load_verified_source_document,
)
from asymmetric_engine.domain.opportunity import (
    EligibilityGateKind,
    OpportunityState,
    ScenarioKind,
    UnderwritingDimensionKind,
    UnderwritingDraft,
)

UnderwritingSourceError = SourceDocumentVerificationError
UnderwritingSourceNotFoundError = SourceDocumentNotFoundError
UnderwritingSourceIntegrityError = SourceDocumentIntegrityError


class BuildOpportunityState:
    """Verify exact source bytes and content-address the standalone assessment."""

    def __init__(self, repository: SourceDocumentRepository) -> None:
        self._repository = repository

    def execute(self, draft: UnderwritingDraft) -> OpportunityState:
        """Return the same state identity for the same canonical analytical input."""

        canonical_draft = self._canonicalize_draft(draft)
        causal_documents = {
            document.document_id: document
            for document in canonical_draft.causal_analysis.source_documents
        }
        for document_id in canonical_draft.causal_analysis.source_document_ids:
            current_document = load_verified_source_document(self._repository, document_id)
            if current_document != causal_documents[document_id]:
                raise UnderwritingSourceIntegrityError(
                    f"source document {document_id} no longer matches the immutable version "
                    "embedded in the causal analysis"
                )
        documents = tuple(
            load_verified_source_document(self._repository, document_id)
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
        opportunity_id = uuid5(
            NAMESPACE_URL,
            f"asymmetric-insight-engine:opportunity-state:{fingerprint}",
        )
        return OpportunityState.model_validate(
            {
                **canonical_draft.model_dump(mode="python"),
                "opportunity_id": opportunity_id,
                "input_fingerprint": fingerprint,
                "source_documents": documents,
            }
        )

    @staticmethod
    def _canonicalize_draft(draft: UnderwritingDraft) -> UnderwritingDraft:
        """Sort only semantically unordered collections; preserve formula input order."""

        dimension_order = {kind: index for index, kind in enumerate(UnderwritingDimensionKind)}
        gate_order = {kind: index for index, kind in enumerate(EligibilityGateKind)}
        scenario_order = {kind: index for index, kind in enumerate(ScenarioKind)}
        values: dict[str, Any] = draft.model_dump(mode="python")
        values["source_document_ids"] = tuple(sorted(draft.source_document_ids, key=str))
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
        values["financial_facts"] = tuple(
            sorted(
                (
                    fact.model_copy(update={"claim_ids": tuple(sorted(fact.claim_ids, key=str))})
                    for fact in draft.financial_facts
                ),
                key=lambda item: item.fact_id,
            )
        )
        values["derived_facts"] = tuple(sorted(draft.derived_facts, key=lambda item: item.fact_id))
        values["dimensions"] = tuple(
            sorted(
                (
                    dimension.model_copy(
                        update={
                            "claim_ids": tuple(sorted(dimension.claim_ids, key=str)),
                            "fact_ids": tuple(sorted(dimension.fact_ids)),
                            "missing_data": tuple(sorted(dimension.missing_data)),
                        }
                    )
                    for dimension in draft.dimensions
                ),
                key=lambda item: dimension_order[item.kind],
            )
        )
        values["eligibility_gates"] = tuple(
            sorted(
                (
                    gate.model_copy(
                        update={
                            "claim_ids": tuple(sorted(gate.claim_ids, key=str)),
                            "missing_data": tuple(sorted(gate.missing_data)),
                        }
                    )
                    for gate in draft.eligibility_gates
                ),
                key=lambda item: gate_order[item.kind],
            )
        )
        values["valuation_scenarios"] = tuple(
            sorted(
                (
                    scenario.model_copy(
                        update={
                            "supporting_fact_ids": tuple(sorted(scenario.supporting_fact_ids)),
                            "assumption_claim_ids": tuple(
                                sorted(scenario.assumption_claim_ids, key=str)
                            ),
                            "assumptions": tuple(sorted(scenario.assumptions)),
                            "invalidation_conditions": tuple(
                                sorted(scenario.invalidation_conditions)
                            ),
                        }
                    )
                    for scenario in draft.valuation_scenarios
                ),
                key=lambda item: scenario_order[item.kind],
            )
        )
        values["catalysts"] = tuple(
            sorted(
                (
                    catalyst.model_copy(
                        update={"claim_ids": tuple(sorted(catalyst.claim_ids, key=str))}
                    )
                    for catalyst in draft.catalysts
                ),
                key=lambda item: item.catalyst_id,
            )
        )
        values["risks"] = tuple(
            sorted(
                (
                    risk.model_copy(update={"claim_ids": tuple(sorted(risk.claim_ids, key=str))})
                    for risk in draft.risks
                ),
                key=lambda item: item.risk_id,
            )
        )
        for field in ("invalidation_conditions", "missing_data", "conflicts", "assumptions"):
            values[field] = tuple(sorted(getattr(draft, field)))
        return UnderwritingDraft.model_validate(values)
