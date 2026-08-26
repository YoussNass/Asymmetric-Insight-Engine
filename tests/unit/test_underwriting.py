"""Tests for deterministic Chapter 5 opportunity-state construction."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.underwriting import (
    BuildOpportunityState,
    UnderwritingSourceIntegrityError,
    UnderwritingSourceNotFoundError,
)
from asymmetric_engine.domain.opportunity import OpportunityState, UnderwritingDraft
from tests.underwriting_factories import make_underwriting_context


def rebuild(draft: UnderwritingDraft, **overrides: object) -> UnderwritingDraft:
    values = draft.model_dump(mode="python")
    values.update(overrides)
    return UnderwritingDraft.model_validate(values)


def test_builder_produces_deterministic_content_addressed_opportunity_state() -> None:
    repository, draft = make_underwriting_context()
    builder = BuildOpportunityState(repository)

    first = builder.execute(draft)
    second = builder.execute(draft)

    assert first == second
    assert first.opportunity_id.version == 5
    assert len(first.input_fingerprint) == 64
    assert first.as_of == draft.knowledge_boundary.as_of
    assert first.knowledge_mode is draft.knowledge_boundary.knowledge_mode
    assert tuple(document.document_id for document in first.source_documents) == tuple(
        sorted(draft.source_document_ids, key=str)
    )


def test_fingerprint_ignores_only_semantically_unordered_collection_order() -> None:
    repository, draft = make_underwriting_context()
    reordered = rebuild(
        draft,
        source_document_ids=tuple(reversed(draft.source_document_ids)),
        evidence=tuple(reversed(draft.evidence)),
        claims=tuple(
            claim.model_copy(update={"evidence_ids": tuple(reversed(claim.evidence_ids))})
            for claim in reversed(draft.claims)
        ),
        financial_facts=tuple(
            fact.model_copy(update={"claim_ids": tuple(reversed(fact.claim_ids))})
            for fact in reversed(draft.financial_facts)
        ),
        derived_facts=tuple(reversed(draft.derived_facts)),
        dimensions=tuple(
            dimension.model_copy(
                update={
                    "claim_ids": tuple(reversed(dimension.claim_ids)),
                    "fact_ids": tuple(reversed(dimension.fact_ids)),
                    "missing_data": tuple(reversed(dimension.missing_data)),
                    "conflicts": tuple(reversed(dimension.conflicts)),
                    "assumptions": tuple(reversed(dimension.assumptions)),
                    "invalidation_conditions": tuple(reversed(dimension.invalidation_conditions)),
                }
            )
            for dimension in reversed(draft.dimensions)
        ),
        eligibility_gates=tuple(
            gate.model_copy(
                update={
                    "claim_ids": tuple(reversed(gate.claim_ids)),
                    "missing_data": tuple(reversed(gate.missing_data)),
                }
            )
            for gate in reversed(draft.eligibility_gates)
        ),
        valuation_scenarios=tuple(
            scenario.model_copy(
                update={
                    "supporting_fact_ids": tuple(reversed(scenario.supporting_fact_ids)),
                    "assumption_claim_ids": tuple(reversed(scenario.assumption_claim_ids)),
                    "assumptions": tuple(reversed(scenario.assumptions)),
                    "invalidation_conditions": tuple(reversed(scenario.invalidation_conditions)),
                }
            )
            for scenario in reversed(draft.valuation_scenarios)
        ),
        catalysts=tuple(reversed(draft.catalysts)),
        risks=tuple(reversed(draft.risks)),
        invalidation_conditions=tuple(reversed(draft.invalidation_conditions)),
        missing_data=tuple(reversed(draft.missing_data)),
        assumptions=tuple(reversed(draft.assumptions)),
    )
    builder = BuildOpportunityState(repository)

    assert builder.execute(reordered) == builder.execute(draft)


def test_material_underwriting_change_changes_the_fingerprint() -> None:
    repository, draft = make_underwriting_context()
    changed_catalyst = draft.catalysts[0].model_copy(
        update={"description": "A materially different observable catalyst description."}
    )
    changed = rebuild(draft, catalysts=(changed_catalyst,))
    builder = BuildOpportunityState(repository)

    assert builder.execute(changed).input_fingerprint != builder.execute(draft).input_fingerprint


def test_builder_fails_closed_when_source_or_content_is_missing() -> None:
    repository, draft = make_underwriting_context()
    missing_id = draft.source_document_ids[0]
    del repository.documents[missing_id]
    with pytest.raises(UnderwritingSourceNotFoundError, match=str(missing_id)):
        BuildOpportunityState(repository).execute(draft)

    repository, draft = make_underwriting_context()
    del repository.contents[draft.source_document_ids[0]]
    with pytest.raises(UnderwritingSourceNotFoundError, match="missing"):
        BuildOpportunityState(repository).execute(draft)


def test_builder_detects_source_size_and_hash_corruption() -> None:
    repository, draft = make_underwriting_context()
    document_id = draft.source_document_ids[0]
    repository.contents[document_id] += b"altered"
    with pytest.raises(UnderwritingSourceIntegrityError, match="byte length"):
        BuildOpportunityState(repository).execute(draft)

    repository, draft = make_underwriting_context()
    document_id = draft.source_document_ids[0]
    original = repository.contents[document_id]
    repository.contents[document_id] = bytes([original[0] ^ 1]) + original[1:]
    with pytest.raises(UnderwritingSourceIntegrityError, match="SHA-256"):
        BuildOpportunityState(repository).execute(draft)


def test_builder_rejects_causal_source_metadata_drift() -> None:
    repository, draft = make_underwriting_context()
    document_id = draft.causal_analysis.source_document_ids[0]
    repository.documents[document_id] = repository.documents[document_id].model_copy(
        update={"source_uri": "https://example.test/rebound-causal-source"}
    )

    with pytest.raises(UnderwritingSourceIntegrityError, match="embedded in the causal analysis"):
        BuildOpportunityState(repository).execute(draft)


def test_verified_state_rejects_source_provenance_mismatch() -> None:
    repository, draft = make_underwriting_context()
    document_id = draft.source_document_ids[0]
    repository.documents[document_id] = repository.documents[document_id].model_copy(
        update={"source_uri": "https://example.test/different-underwriting-source"}
    )

    with pytest.raises(ValidationError, match="provenance does not match"):
        BuildOpportunityState(repository).execute(draft)


def test_verified_state_requires_exact_unique_document_set() -> None:
    repository, draft = make_underwriting_context()
    state = BuildOpportunityState(repository).execute(draft)
    values = state.model_dump(mode="python")
    values["source_documents"] = (*state.source_documents, state.source_documents[0])
    with pytest.raises(ValidationError, match="duplicate verified source"):
        OpportunityState.model_validate(values)

    values["source_documents"] = state.source_documents[1:]
    with pytest.raises(ValidationError, match="must match underwriting"):
        OpportunityState.model_validate(values)
