"""Unit tests for the Chapter 10 typed prospective intake boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.causal_analysis import BuildCausalAnalysis
from asymmetric_engine.application.underwriting import BuildOpportunityState
from asymmetric_engine.domain.causal import CausalAnalysis
from asymmetric_engine.interfaces.prospective_intake import (
    AieIntakeServices,
    AieProspectiveIntake,
    BuildCausalAnalysisRequest,
    BuildOpportunityStateRequest,
    IntakeResponse,
)
from tests.causal_factories import make_causal_draft, make_reference_sources
from tests.memory_repository import MemorySourceRepository
from tests.underwriting_factories import make_underwriting_draft, make_underwriting_sources


def _repository() -> MemorySourceRepository:
    causal_documents, causal_contents = make_reference_sources()
    underwriting_documents, underwriting_contents = make_underwriting_sources()
    documents = {
        document.document_id: document for document in (*causal_documents, *underwriting_documents)
    }
    contents = {**causal_contents, **underwriting_contents}
    return MemorySourceRepository(documents=documents, contents=contents)


def _intake(repository: MemorySourceRepository) -> AieProspectiveIntake:
    return AieProspectiveIntake(
        AieIntakeServices(
            causal_analysis=BuildCausalAnalysis(repository),
            opportunity_state=BuildOpportunityState(repository),
        )
    )


def test_causal_intake_equals_direct_canonical_application_result() -> None:
    repository = _repository()
    draft = make_causal_draft()
    direct = BuildCausalAnalysis(repository).execute(draft)

    response = _intake(repository).build_causal_analysis(BuildCausalAnalysisRequest(draft=draft))

    assert response.operation == "build_causal_analysis"
    assert response.result == direct


def test_opportunity_intake_equals_direct_canonical_application_result() -> None:
    repository = _repository()
    causal = BuildCausalAnalysis(repository).execute(make_causal_draft())
    draft = make_underwriting_draft(causal_analysis=causal)
    direct = BuildOpportunityState(repository).execute(draft)

    response = _intake(repository).build_opportunity_state(
        BuildOpportunityStateRequest(draft=draft)
    )

    assert response.operation == "build_opportunity_state"
    assert response.result == direct


def test_intake_requests_and_responses_round_trip_json_exactly() -> None:
    repository = _repository()
    causal_request = BuildCausalAnalysisRequest(draft=make_causal_draft())
    causal_request_round_trip = BuildCausalAnalysisRequest.model_validate(
        causal_request.model_dump(mode="json")
    )
    assert causal_request_round_trip == causal_request

    causal_response = _intake(repository).build_causal_analysis(causal_request)
    causal_response_round_trip = IntakeResponse[CausalAnalysis].model_validate(
        causal_response.model_dump(mode="json")
    )
    assert causal_response_round_trip == causal_response


def test_intake_rejects_client_shadow_fields() -> None:
    payload = BuildCausalAnalysisRequest(draft=make_causal_draft()).model_dump(mode="json")
    payload["client_score"] = 99

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BuildCausalAnalysisRequest.model_validate(payload)
