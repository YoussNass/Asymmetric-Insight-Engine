"""Opportunity-state invariant tests."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from asymmetric_engine.domain.evidence import Claim, ClaimType, Confidence
from asymmetric_engine.domain.opportunity import (
    KnowledgeMode,
    OpportunityState,
    OpportunityStatus,
)
from asymmetric_engine.domain.temporal import KnowledgeMode as CanonicalKnowledgeMode
from tests.factories import BASE_TIME, make_claim, make_evidence


def build_state(**overrides: object) -> OpportunityState:
    evidence = make_evidence()
    values: dict[str, object] = {
        "candidate_id": "TEST",
        "as_of": BASE_TIME,
        "knowledge_mode": KnowledgeMode.LIVE_SYSTEM_REPLAY,
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


def test_opportunity_requires_explicit_knowledge_mode() -> None:
    payload = build_state().model_dump()
    del payload["knowledge_mode"]

    with pytest.raises(ValidationError, match="knowledge_mode"):
        OpportunityState.model_validate(payload)


def test_opportunity_reexports_the_canonical_knowledge_mode() -> None:
    assert KnowledgeMode is CanonicalKnowledgeMode


def test_opportunity_rejects_future_evidence() -> None:
    evidence = make_evidence(available_at=BASE_TIME + timedelta(days=1))

    with pytest.raises(ValidationError, match="unavailable at as_of"):
        build_state(evidence=(evidence,), claims=(make_claim(evidence),))


def test_historical_reconstruction_accepts_evidence_ingested_later() -> None:
    evidence = make_evidence(
        available_at=BASE_TIME - timedelta(days=1),
        recorded_at=BASE_TIME + timedelta(days=1),
    )

    state = build_state(
        knowledge_mode=KnowledgeMode.HISTORICAL_RECONSTRUCTION,
        evidence=(evidence,),
        claims=(make_claim(evidence),),
    )

    assert state.knowledge_mode is KnowledgeMode.HISTORICAL_RECONSTRUCTION


def test_live_replay_rejects_evidence_ingested_later() -> None:
    evidence = make_evidence(
        available_at=BASE_TIME - timedelta(days=1),
        recorded_at=BASE_TIME + timedelta(days=1),
    )

    with pytest.raises(ValidationError, match="not recorded at as_of"):
        build_state(evidence=(evidence,), claims=(make_claim(evidence),))


def test_opportunity_rejects_duplicate_evidence_records() -> None:
    evidence = make_evidence()

    with pytest.raises(ValidationError, match="duplicate evidence"):
        build_state(evidence=(evidence, evidence), claims=(make_claim(evidence),))


def test_opportunity_rejects_duplicate_claim_records() -> None:
    evidence = make_evidence()
    claim = make_claim(evidence)
    duplicate = claim.model_copy(update={"text": "A second payload with the same identity."})

    with pytest.raises(ValidationError, match="duplicate claim"):
        build_state(evidence=(evidence,), claims=(claim, duplicate))


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


def test_review_ready_state_requires_evidence_and_claims() -> None:
    with pytest.raises(ValidationError, match="require evidence and claims"):
        build_state(evidence=(), claims=())


def test_review_ready_state_requires_invalidation_conditions() -> None:
    with pytest.raises(ValidationError, match="require invalidation conditions"):
        build_state(invalidation_conditions=())


def test_portfolio_review_readiness_does_not_claim_allocatability() -> None:
    state = build_state(status=OpportunityStatus.READY_FOR_PORTFOLIO_REVIEW)

    assert state.status.value == "ready_for_portfolio_review"
    assert "allocatable" not in {status.value for status in OpportunityStatus}


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
