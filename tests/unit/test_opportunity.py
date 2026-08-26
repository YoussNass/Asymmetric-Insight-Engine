"""Unit tests for the Chapter 5 standalone-underwriting contract."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from asymmetric_engine.domain.causal import CausalReadiness
from asymmetric_engine.domain.evidence import ClaimType
from asymmetric_engine.domain.opportunity import (
    DerivedMetric,
    DimensionOutcome,
    EligibilityGateKind,
    FinancialFactBasis,
    GateResult,
    OpportunityStatus,
    ScenarioKind,
    UnderwritingDimensionKind,
    UnderwritingDraft,
    ValuationScenario,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary
from tests.underwriting_factories import make_underwriting_context


def rebuild(draft: UnderwritingDraft, **overrides: object) -> UnderwritingDraft:
    values = draft.model_dump(mode="python")
    values.update(overrides)
    return UnderwritingDraft.model_validate(values)


def test_reference_underwriting_is_multidimensional_and_portfolio_independent() -> None:
    _, draft = make_underwriting_context()

    assert draft.status is OpportunityStatus.READY_FOR_PORTFOLIO_REVIEW
    assert {dimension.kind for dimension in draft.dimensions} == set(UnderwritingDimensionKind)
    assert {gate.kind for gate in draft.eligibility_gates} == set(EligibilityGateKind)
    assert {scenario.kind for scenario in draft.valuation_scenarios} == set(ScenarioKind)
    assert all(gate.result is GateResult.PASS for gate in draft.eligibility_gates)
    assert "portfolio" not in UnderwritingDraft.model_fields
    assert "score" not in UnderwritingDraft.model_fields
    assert "allocatable" not in {status.value for status in OpportunityStatus}


def test_underwriting_requires_ready_causal_handoff_and_matching_beneficiary() -> None:
    _, draft = make_underwriting_context()
    incomplete = draft.causal_analysis.model_copy(
        update={
            "readiness": CausalReadiness.INVESTIGATE,
            "readiness_rationale": "The causal case remains under investigation.",
        }
    )

    with pytest.raises(ValidationError, match="ready_for_underwriting"):
        rebuild(draft, causal_analysis=incomplete)

    with pytest.raises(ValidationError, match="causal beneficiary"):
        rebuild(draft, candidate_id="company:sec-cik-9999999999")


def test_underwriting_requires_the_canonical_causal_knowledge_boundary() -> None:
    _, draft = make_underwriting_context()
    changed_boundary = KnowledgeBoundary(
        as_of=draft.knowledge_boundary.as_of + timedelta(seconds=1),
        knowledge_mode=draft.knowledge_boundary.knowledge_mode,
    )

    with pytest.raises(ValidationError, match="share the knowledge boundary"):
        rebuild(draft, knowledge_boundary=changed_boundary)


def test_underwriting_rejects_future_or_unrecorded_evidence() -> None:
    _, draft = make_underwriting_context()
    first = draft.evidence[0]
    future = first.model_copy(
        update={
            "available_at": draft.knowledge_boundary.as_of + timedelta(days=1),
            "recorded_at": draft.knowledge_boundary.as_of + timedelta(days=1),
        }
    )

    with pytest.raises(ValidationError, match="source_not_available"):
        rebuild(draft, evidence=(future, *draft.evidence[1:]))


def test_reported_and_adjusted_facts_require_compatible_claim_types() -> None:
    _, draft = make_underwriting_context()
    income_claim_id = draft.financial_facts[0].claim_ids[0]
    changed_claims = tuple(
        claim.model_copy(update={"claim_type": ClaimType.HYPOTHESIS})
        if claim.claim_id == income_claim_id
        else claim
        for claim in draft.claims
    )
    with pytest.raises(ValidationError, match="reported financial fact"):
        rebuild(draft, claims=changed_claims)

    adjusted = next(
        fact for fact in draft.financial_facts if fact.basis is FinancialFactBasis.ANALYST_ADJUSTED
    )
    adjusted_claim_id = adjusted.claim_ids[0]
    changed_claims = tuple(
        claim.model_copy(update={"claim_type": ClaimType.OBSERVATION})
        if claim.claim_id == adjusted_claim_id
        else claim
        for claim in draft.claims
    )
    with pytest.raises(ValidationError, match="analyst_adjusted financial fact"):
        rebuild(draft, claims=changed_claims)


def test_derived_facts_verify_formula_value_metrics_periods_and_order() -> None:
    _, draft = make_underwriting_context()
    growth = next(
        fact for fact in draft.derived_facts if fact.metric is DerivedMetric.REVENUE_GROWTH
    )
    wrong_value = growth.model_copy(update={"value": growth.value + Decimal("0.1")})
    with pytest.raises(ValidationError, match="does not match its declared formula"):
        rebuild(
            draft,
            derived_facts=tuple(
                wrong_value if fact.fact_id == growth.fact_id else fact
                for fact in draft.derived_facts
            ),
        )

    reversed_inputs = growth.model_copy(
        update={"input_fact_ids": tuple(reversed(growth.input_fact_ids))}
    )
    with pytest.raises(ValidationError, match="requires prior then current"):
        rebuild(
            draft,
            derived_facts=tuple(
                reversed_inputs if fact.fact_id == growth.fact_id else fact
                for fact in draft.derived_facts
            ),
        )


def test_scenario_rejects_inconsistent_equity_per_share_and_return_arithmetic() -> None:
    _, draft = make_underwriting_context()
    scenario = draft.valuation_scenarios[0]
    for field, value, message in (
        ("equity_value_usd_millions", Decimal("1"), "enterprise value minus net debt"),
        ("value_per_share_usd", Decimal("1"), "equity value divided by diluted shares"),
        ("return_from_reference", Decimal("1"), "calculated from value per share"),
    ):
        values = scenario.model_dump(mode="python")
        values[field] = value
        with pytest.raises(ValidationError, match=message):
            ValuationScenario.model_validate(values)


def test_scenario_set_requires_supported_price_strict_order_and_matching_payoff() -> None:
    _, draft = make_underwriting_context()
    bear, base, bull = draft.valuation_scenarios
    changed_price = Decimal("101")
    changed_base = base.model_copy(
        update={
            "reference_price_usd": changed_price,
            "return_from_reference": base.value_per_share_usd / changed_price - Decimal(1),
        }
    )
    with pytest.raises(ValidationError, match="reference price lacks exact fact support"):
        rebuild(draft, valuation_scenarios=(bear, changed_base, bull))

    changed_base = base.model_copy(
        update={
            "enterprise_value_usd_millions": bear.enterprise_value_usd_millions,
            "net_debt_usd_millions": bear.net_debt_usd_millions,
            "equity_value_usd_millions": bear.equity_value_usd_millions,
            "diluted_shares_millions": bear.diluted_shares_millions,
            "value_per_share_usd": bear.value_per_share_usd,
            "return_from_reference": bear.return_from_reference,
        }
    )
    with pytest.raises(ValidationError, match="strictly ordered"):
        rebuild(draft, valuation_scenarios=(bear, changed_base, bull))

    payoff = draft.payoff_profile
    assert payoff is not None
    wrong_payoff = payoff.model_copy(update={"bull_return": payoff.bull_return + Decimal("0.1")})
    with pytest.raises(ValidationError, match="must match valuation scenarios"):
        rebuild(draft, payoff_profile=wrong_payoff)


def test_scenario_probabilities_are_deliberately_absent() -> None:
    assert "probability" not in ValuationScenario.model_fields


def test_unknown_dimension_and_gate_require_missing_data() -> None:
    _, draft = make_underwriting_context()
    dimension = draft.dimensions[0].model_copy(
        update={"outcome": DimensionOutcome.UNKNOWN, "missing_data": ()}
    )
    with pytest.raises(ValidationError, match="unknown dimensions"):
        dimension.__class__.model_validate(dimension.model_dump(mode="python"))

    gate = draft.eligibility_gates[0].model_copy(
        update={"result": GateResult.UNKNOWN, "missing_data": ()}
    )
    with pytest.raises(ValidationError, match="unknown eligibility gates"):
        gate.__class__.model_validate(gate.model_dump(mode="python"))


def test_portfolio_ready_state_requires_all_dimensions_gates_and_passing_results() -> None:
    _, draft = make_underwriting_context()
    incomplete_dimensions = tuple(
        dimension
        for dimension in draft.dimensions
        if dimension.kind is not UnderwritingDimensionKind.VALUE_CAPTURE_AND_COMPETITION
    )
    with pytest.raises(ValidationError, match="requires all dimensions"):
        rebuild(draft, dimensions=incomplete_dimensions)
    with pytest.raises(ValidationError, match="requires all eligibility gates"):
        rebuild(draft, eligibility_gates=draft.eligibility_gates[1:])

    failed = draft.eligibility_gates[0].model_copy(update={"result": GateResult.FAIL})
    with pytest.raises(ValidationError, match="every eligibility gate to pass"):
        rebuild(draft, eligibility_gates=(failed, *draft.eligibility_gates[1:]))


def test_duplicate_and_dangling_records_are_rejected() -> None:
    _, draft = make_underwriting_context()
    with pytest.raises(ValidationError, match="duplicate financial fact"):
        rebuild(draft, financial_facts=(*draft.financial_facts, draft.financial_facts[0]))
    with pytest.raises(ValidationError, match="duplicate underwriting dimension"):
        rebuild(draft, dimensions=(*draft.dimensions, draft.dimensions[0]))

    unused_fact = draft.financial_facts[0].model_copy(update={"fact_id": "reported:unused"})
    with pytest.raises(ValidationError, match="every financial fact"):
        rebuild(draft, financial_facts=(*draft.financial_facts, unused_fact))


def test_insufficient_and_invalidated_states_require_explanations() -> None:
    _, draft = make_underwriting_context()
    with pytest.raises(ValidationError, match="insufficient_evidence"):
        rebuild(draft, status=OpportunityStatus.INSUFFICIENT_EVIDENCE, missing_data=())
    with pytest.raises(ValidationError, match="invalidated underwriting"):
        rebuild(draft, status=OpportunityStatus.INVALIDATED)

    invalidated = rebuild(
        draft,
        status=OpportunityStatus.INVALIDATED,
        invalidation_reason="The beneficiary can no longer qualify the relevant HBM product.",
    )
    assert invalidated.status is OpportunityStatus.INVALIDATED


def test_claims_evidence_sources_and_facts_cannot_dangle() -> None:
    _, draft = make_underwriting_context()
    unused_claim = draft.claims[0].model_copy(update={"claim_id": uuid4()})
    with pytest.raises(ValidationError, match="every underwriting claim"):
        rebuild(draft, claims=(*draft.claims, unused_claim))

    with pytest.raises(ValidationError, match="undeclared source"):
        rebuild(draft, source_document_ids=draft.source_document_ids[:1])
