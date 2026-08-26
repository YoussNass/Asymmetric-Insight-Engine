"""End-to-end Chapter 5 path from causal hand-off to standalone opportunity state."""

from __future__ import annotations

from pathlib import Path

from asymmetric_engine.application.causal_analysis import BuildCausalAnalysis
from asymmetric_engine.application.underwriting import BuildOpportunityState
from asymmetric_engine.domain.opportunity import (
    GateResult,
    OpportunityStatus,
    ScenarioKind,
    UnderwritingDimensionKind,
)
from asymmetric_engine.infrastructure.persistence import SQLiteSourceDocumentRepository
from tests.causal_factories import make_causal_draft, make_reference_sources
from tests.underwriting_factories import make_underwriting_draft, make_underwriting_sources


def test_ledger_causal_handoff_to_portfolio_review_is_reproducible(tmp_path: Path) -> None:
    database_path = tmp_path / "underwriting-evidence.sqlite3"
    repository = SQLiteSourceDocumentRepository(database_path)
    causal_documents, causal_contents = make_reference_sources()
    for document in causal_documents:
        repository.append(document, causal_contents[document.document_id])
    causal_analysis = BuildCausalAnalysis(repository).execute(
        make_causal_draft(documents=causal_documents)
    )

    underwriting_documents, underwriting_contents = make_underwriting_sources()
    for document in underwriting_documents:
        repository.append(document, underwriting_contents[document.document_id])
    draft = make_underwriting_draft(
        causal_analysis=causal_analysis,
        documents=underwriting_documents,
    )
    state = BuildOpportunityState(repository).execute(draft)
    restarted_state = BuildOpportunityState(
        SQLiteSourceDocumentRepository(database_path, initialize_schema=False)
    ).execute(draft)

    assert state == restarted_state
    assert state.status is OpportunityStatus.READY_FOR_PORTFOLIO_REVIEW
    assert state.candidate_id == "company:sec-cik-0000723125"
    assert {dimension.kind for dimension in state.dimensions} == set(UnderwritingDimensionKind)
    assert all(gate.result is GateResult.PASS for gate in state.eligibility_gates)
    assert tuple(scenario.kind for scenario in state.valuation_scenarios) == tuple(ScenarioKind)
    assert state.payoff_profile is not None
    assert state.payoff_profile.upside_to_downside_ratio is not None
    assert state.risks
    assert state.catalysts
    assert state.missing_data
    assert not hasattr(state, "portfolio_id")
    assert not hasattr(state, "position_size")


def test_same_standalone_input_has_no_portfolio_context_to_change_its_result(
    tmp_path: Path,
) -> None:
    repository = SQLiteSourceDocumentRepository(tmp_path / "standalone.sqlite3")
    causal_documents, causal_contents = make_reference_sources()
    underwriting_documents, underwriting_contents = make_underwriting_sources()
    for document in (*causal_documents, *underwriting_documents):
        content = {**causal_contents, **underwriting_contents}[document.document_id]
        repository.append(document, content)
    causal = BuildCausalAnalysis(repository).execute(make_causal_draft(documents=causal_documents))
    draft = make_underwriting_draft(
        causal_analysis=causal,
        documents=underwriting_documents,
    )

    first = BuildOpportunityState(repository).execute(draft)
    second = BuildOpportunityState(repository).execute(draft)

    assert first == second
    assert "portfolio" not in draft.model_dump(mode="json")
