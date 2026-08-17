"""Opportunity-state invariant tests."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from asymmetric_engine.domain.evidence import Claim, ClaimType, Confidence
from asymmetric_engine.domain.opportunity import OpportunityState, OpportunityStatus
from tests.factories import BASE_TIME, make_claim, make_evidence


def build_state(**overrides: object) -> OpportunityState:
    evidence = make_evidence()
    values: dict[str, object] = {
        "candidate_id": "TEST",
        "as_of": BASE_TIME,
        "status": OpportunityStatus.ELIGIBLE,
        "thesis_summary": "A sufficiently detailed and falsifiable test investment thesis.",
        "evidence": (evidence,),
        "claims": (make_claim(evidence),),
        "invalidation_conditions": ("Capacity expansion is cancelled.",),
    }
    values.update(overrides)
    return OpportunityState.model_validate(values)


def test_valid_point_in_time_opportunity_is_accepted() -> None:
    state = build_state()

    assert state.status is OpportunityStatus.ELIGIBLE
    assert state.candidate_id == "TEST"


def test_opportunity_rejects_future_evidence() -> None:
    evidence = make_evidence(available_at=BASE_TIME + timedelta(days=1))

    with pytest.raises(ValidationError, match="unavailable at as_of"):
        build_state(evidence=(evidence,), claims=(make_claim(evidence),))


def test_opportunity_rejects_unknown_evidence_reference() -> None:
    evidence = make_evidence()
    claim = Claim(
        text="A claim linked to evidence outside the state.",
        claim_type=ClaimType.INFERENCE,
        evidence_ids=(uuid4(),),
        confidence=Confidence(score=0.4, rationale="Needs source reconciliation."),
        invalidation_condition="The referenced evidence cannot be recovered.",
    )

    with pytest.raises(ValidationError, match="absent from the opportunity"):
        build_state(evidence=(evidence,), claims=(claim,))


def test_capital_ready_state_requires_invalidation_conditions() -> None:
    with pytest.raises(ValidationError, match="require invalidation conditions"):
        build_state(invalidation_conditions=())


def test_invalidated_state_requires_reason() -> None:
    with pytest.raises(ValidationError, match="invalidation_reason"):
        build_state(status=OpportunityStatus.INVALIDATED, invalidation_conditions=())


def test_non_invalidated_state_rejects_invalidation_reason() -> None:
    with pytest.raises(ValidationError, match="only invalidated"):
        build_state(invalidation_reason="This reason is inconsistent with an eligible state.")


def test_invalidated_state_accepts_reason() -> None:
    state = build_state(
        status=OpportunityStatus.INVALIDATED,
        invalidation_conditions=(),
        invalidation_reason="Primary evidence disproved the causal mechanism.",
    )

    assert state.status is OpportunityStatus.INVALIDATED
