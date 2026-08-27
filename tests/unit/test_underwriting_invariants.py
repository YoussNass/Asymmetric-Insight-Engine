"""Negative-path tests for explicit Chapter 5 financial and epistemic invariants."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from asymmetric_engine.application.underwriting import (
    BuildOpportunityState,
    UnderwritingSourceNotFoundError,
)
from asymmetric_engine.domain.evidence import ClaimType
from asymmetric_engine.domain.opportunity import (
    DerivedMetric,
    DimensionOutcome,
    EligibilityGateKind,
    FinancialFactBasis,
    FinancialFormula,
    FinancialMetric,
    FinancialPeriod,
    FinancialPeriodKind,
    FinancialPeriodScope,
    FinancialUnit,
    OpportunityStatus,
    UnderwritingDimensionKind,
    UnderwritingDraft,
)
from tests.underwriting_factories import make_underwriting_context


def rebuild(draft: UnderwritingDraft, **overrides: object) -> UnderwritingDraft:
    values = draft.model_dump(mode="python")
    values.update(overrides)
    return UnderwritingDraft.model_validate(values)


def revalidate(model: BaseModel, **updates: object) -> BaseModel:
    values = model.model_dump(mode="python")
    values.update(updates)
    return model.__class__.model_validate(values)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (
            {
                "kind": FinancialPeriodKind.INSTANT,
                "start_date": date(2025, 1, 1),
                "end_date": date(2025, 12, 31),
            },
            "instant financial periods",
        ),
        (
            {
                "kind": FinancialPeriodKind.DURATION,
                "start_date": None,
                "end_date": date(2025, 12, 31),
            },
            "duration financial periods",
        ),
        (
            {
                "kind": FinancialPeriodKind.DURATION,
                "start_date": date(2025, 12, 31),
                "end_date": date(2025, 12, 31),
            },
            "must precede",
        ),
    ],
)
def test_financial_period_rejects_invalid_shapes(values: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        FinancialPeriod.model_validate(values)


def test_financial_period_requires_an_explicit_comparable_duration_scope() -> None:
    with pytest.raises(ValidationError, match="require duration_scope"):
        FinancialPeriod(
            kind=FinancialPeriodKind.DURATION,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
        )
    with pytest.raises(ValidationError, match="cannot declare duration_scope"):
        FinancialPeriod(
            kind=FinancialPeriodKind.INSTANT,
            end_date=date(2025, 3, 31),
            duration_scope=FinancialPeriodScope.FISCAL_QUARTER,
        )


def test_financial_fact_rejects_invalid_values_units_periods_and_basis_notes() -> None:
    _, draft = make_underwriting_context()
    revenue = next(fact for fact in draft.financial_facts if fact.metric is FinancialMetric.REVENUE)
    capex = next(
        fact
        for fact in draft.financial_facts
        if fact.metric is FinancialMetric.CAPITAL_EXPENDITURES
    )
    adjusted = next(
        fact for fact in draft.financial_facts if fact.basis is FinancialFactBasis.ANALYST_ADJUSTED
    )
    invalid_cases = (
        (revenue, {"value": Decimal("NaN")}, "finite number"),
        (revenue, {"claim_ids": (revenue.claim_ids[0],) * 2}, "duplicate financial fact"),
        (revenue, {"unit": FinancialUnit.RATIO}, "requires unit"),
        (
            revenue,
            {
                "period": FinancialPeriod(
                    kind=FinancialPeriodKind.INSTANT,
                    end_date=revenue.period.end_date,
                )
            },
            "requires a duration period",
        ),
        (revenue, {"value": Decimal("0")}, "greater than zero"),
        (capex, {"value": Decimal("-1")}, "cannot be negative"),
        (adjusted, {"normalization_note": None}, "require normalization_note"),
        (revenue, {"normalization_note": "Not allowed for a reported fact."}, "cannot declare"),
    )
    for model, updates, message in invalid_cases:
        with pytest.raises(ValidationError, match=message):
            revalidate(model, **updates)


def test_money_requires_currency_and_formulas_reject_hidden_fx_conversion() -> None:
    _, draft = make_underwriting_context()
    revenue = next(fact for fact in draft.financial_facts if fact.metric is FinancialMetric.REVENUE)
    shares = next(
        fact
        for fact in draft.financial_facts
        if fact.metric is FinancialMetric.DILUTED_WEIGHTED_AVERAGE_SHARES
    )
    with pytest.raises(ValidationError, match="requires an ISO currency"):
        revalidate(revenue, currency=None)
    with pytest.raises(ValidationError, match="cannot declare a currency"):
        revalidate(shares, currency="USD")

    prior_revenue = next(
        fact for fact in draft.financial_facts if fact.fact_id == "reported:revenue-2024"
    )
    euro_prior = prior_revenue.model_copy(update={"currency": "EUR"})
    with pytest.raises(ValidationError, match="same-currency inputs"):
        rebuild(
            draft,
            financial_facts=tuple(
                euro_prior if fact.fact_id == prior_revenue.fact_id else fact
                for fact in draft.financial_facts
            ),
        )


def test_market_observed_basis_is_reserved_for_reference_share_price() -> None:
    _, draft = make_underwriting_context()
    revenue = next(fact for fact in draft.financial_facts if fact.metric is FinancialMetric.REVENUE)
    price = next(
        fact
        for fact in draft.financial_facts
        if fact.metric is FinancialMetric.REFERENCE_SHARE_PRICE
    )

    with pytest.raises(ValidationError, match="admitted only for reference_share_price"):
        revalidate(revenue, basis=FinancialFactBasis.MARKET_OBSERVED)
    with pytest.raises(ValidationError, match="requires market_observed basis"):
        revalidate(price, basis=FinancialFactBasis.REPORTED)


def test_derived_fact_rejects_nonfinite_wrong_identity_and_duplicate_inputs() -> None:
    _, draft = make_underwriting_context()
    growth = next(
        fact for fact in draft.derived_facts if fact.metric is DerivedMetric.REVENUE_GROWTH
    )
    invalid_cases = (
        ({"value": Decimal("Infinity")}, "finite number"),
        ({"unit": FinancialUnit.MONEY_MILLIONS, "currency": "USD"}, "requires unit"),
        ({"formula": FinancialFormula.DEBT_MINUS_CASH}, "requires formula"),
        ({"input_fact_ids": (growth.input_fact_ids[0],) * 2}, "two distinct input facts"),
    )
    for updates, message in invalid_cases:
        with pytest.raises(ValidationError, match=message):
            revalidate(growth, **updates)

    free_cash_flow = next(
        fact for fact in draft.derived_facts if fact.metric is DerivedMetric.FREE_CASH_FLOW
    )
    with pytest.raises(ValidationError, match="requires an ISO currency"):
        revalidate(free_cash_flow, currency=None)
    with pytest.raises(ValidationError, match="cannot declare a currency"):
        revalidate(growth, currency="USD")

    wrong_output_currency = free_cash_flow.model_copy(update={"currency": "EUR"})
    with pytest.raises(ValidationError, match="output currency does not match"):
        rebuild(
            draft,
            derived_facts=tuple(
                wrong_output_currency if fact.fact_id == free_cash_flow.fact_id else fact
                for fact in draft.derived_facts
            ),
        )


def test_active_contracts_reject_unknown_method_versions() -> None:
    _, draft = make_underwriting_context()
    growth = draft.derived_facts[0]
    with pytest.raises(ValidationError, match="unsupported financial calculation version"):
        revalidate(growth, calculation_version="unknown-formula-v999")

    survivability = next(
        gate for gate in draft.eligibility_gates if gate.kind is EligibilityGateKind.SURVIVABILITY
    )
    with pytest.raises(ValidationError, match="unsupported eligibility-gate method"):
        revalidate(survivability, method_version="unknown-gates-v999")

    payoff = draft.payoff_profile
    assert payoff is not None
    with pytest.raises(ValidationError, match="unsupported payoff method"):
        revalidate(payoff, method_version="unknown-payoff-v999")

    with pytest.raises(ValidationError, match="unsupported underwriting method"):
        rebuild(draft, method_version="unknown-underwriting-v999")


def test_scenario_and_payoff_reject_nonfinite_duplicate_and_nonpositive_inputs() -> None:
    _, draft = make_underwriting_context()
    scenario = draft.valuation_scenarios[0]
    invalid_scenarios = (
        ({"enterprise_value_millions": Decimal("NaN")}, "finite number"),
        (
            {"supporting_fact_ids": (scenario.supporting_fact_ids[0],) * 2},
            "duplicate valuation-scenario",
        ),
        ({"enterprise_value_millions": Decimal("0")}, "enterprise value"),
        ({"scenario_diluted_shares_millions": Decimal("0")}, "diluted shares"),
        (
            {
                "enterprise_value_millions": Decimal("1"),
                "scenario_net_debt_millions": Decimal("2"),
            },
            "equity value cannot be negative",
        ),
    )
    for updates, message in invalid_scenarios:
        with pytest.raises(ValidationError, match=message):
            revalidate(scenario, **updates)

    payoff = draft.payoff_profile
    assert payoff is not None
    with pytest.raises(ValidationError, match="finite number"):
        revalidate(payoff, bear_return=Decimal("NaN"))


def test_catalyst_window_and_duplicate_component_references_are_rejected() -> None:
    _, draft = make_underwriting_context()
    catalyst = draft.catalysts[0]
    with pytest.raises(ValidationError, match="window_start"):
        revalidate(catalyst, window_start=catalyst.window_end + timedelta(days=1))
    with pytest.raises(ValidationError, match="duplicate catalyst"):
        revalidate(catalyst, claim_ids=(catalyst.claim_ids[0],) * 2)
    with pytest.raises(ValidationError, match="duplicate risk"):
        revalidate(draft.risks[0], claim_ids=(draft.risks[0].claim_ids[0],) * 2)
    with pytest.raises(ValidationError, match="duplicate dimension"):
        revalidate(
            draft.dimensions[0],
            assumptions=("Repeated dimension assumption.",) * 2,
        )


def test_passing_noncausal_gate_requires_explicit_support() -> None:
    _, draft = make_underwriting_context()
    survivability = next(
        gate for gate in draft.eligibility_gates if gate.kind is EligibilityGateKind.SURVIVABILITY
    )
    with pytest.raises(ValidationError, match="requires explicit analytical support"):
        revalidate(survivability, claim_ids=(), fact_ids=())


def test_draft_rejects_duplicate_documents_and_disclosures() -> None:
    _, draft = make_underwriting_context()
    with pytest.raises(ValidationError, match="duplicate source_document_ids"):
        rebuild(
            draft, source_document_ids=(*draft.source_document_ids, draft.source_document_ids[0])
        )
    with pytest.raises(ValidationError, match="duplicate underwriting disclosures"):
        rebuild(draft, assumptions=(draft.assumptions[0],) * 2)


def test_draft_rejects_cross_type_ids_and_broken_evidence_lineage() -> None:
    _, draft = make_underwriting_context()
    colliding_derived = draft.derived_facts[0].model_copy(
        update={"fact_id": draft.financial_facts[0].fact_id}
    )
    with pytest.raises(ValidationError, match="unique across the assessment"):
        rebuild(draft, derived_facts=(colliding_derived, *draft.derived_facts[1:]))

    unbound_evidence = draft.evidence[0].model_copy(
        update={
            "source_document_id": None,
            "source_locator": None,
            "extraction_method": None,
        }
    )
    with pytest.raises(ValidationError, match="must link to a source document"):
        rebuild(draft, evidence=(unbound_evidence, *draft.evidence[1:]))

    unknown_evidence_claim = draft.claims[0].model_copy(update={"evidence_ids": (uuid4(),)})
    with pytest.raises(ValidationError, match="references unknown evidence"):
        rebuild(draft, claims=(unknown_evidence_claim, *draft.claims[1:]))

    unused_evidence = draft.evidence[0].model_copy(update={"evidence_id": uuid4()})
    with pytest.raises(ValidationError, match="every underwriting evidence item"):
        rebuild(draft, evidence=(*draft.evidence, unused_evidence))

    unused_source = draft.causal_analysis.source_document_ids[0]
    with pytest.raises(ValidationError, match="every underwriting source document"):
        rebuild(draft, source_document_ids=(*draft.source_document_ids, unused_source))


def test_draft_rejects_future_facts_unknown_claims_and_unknown_formula_inputs() -> None:
    _, draft = make_underwriting_context()
    price = next(
        fact
        for fact in draft.financial_facts
        if fact.metric is FinancialMetric.REFERENCE_SHARE_PRICE
    )
    future_price = price.model_copy(
        update={
            "period": price.period.model_copy(
                update={"end_date": draft.knowledge_boundary.as_of.date() + timedelta(days=1)}
            )
        }
    )
    with pytest.raises(ValidationError, match="ends after the as_of"):
        rebuild(
            draft,
            financial_facts=tuple(
                future_price if fact.fact_id == price.fact_id else fact
                for fact in draft.financial_facts
            ),
        )

    revenue = draft.financial_facts[0].model_copy(update={"claim_ids": (uuid4(),)})
    with pytest.raises(ValidationError, match="references unknown claims"):
        rebuild(draft, financial_facts=(revenue, *draft.financial_facts[1:]))

    growth = draft.derived_facts[0].model_copy(
        update={"input_fact_ids": ("reported:missing", draft.derived_facts[0].input_fact_ids[1])}
    )
    with pytest.raises(ValidationError, match="unknown input facts"):
        rebuild(draft, derived_facts=(growth, *draft.derived_facts[1:]))


def test_draft_rejects_incompatible_and_temporally_misaligned_formula_inputs() -> None:
    _, draft = make_underwriting_context()
    growth = next(
        fact for fact in draft.derived_facts if fact.metric is DerivedMetric.REVENUE_GROWTH
    )
    incompatible = growth.model_copy(
        update={
            "input_fact_ids": (
                "reported:operating-income-2025",
                "reported:revenue-2025",
            )
        }
    )
    with pytest.raises(ValidationError, match="incompatible input metrics"):
        rebuild(
            draft,
            derived_facts=tuple(
                incompatible if fact.fact_id == growth.fact_id else fact
                for fact in draft.derived_facts
            ),
        )

    free_cash_flow = next(
        fact for fact in draft.derived_facts if fact.metric is DerivedMetric.FREE_CASH_FLOW
    )
    capex = next(
        fact
        for fact in draft.financial_facts
        if fact.fact_id == "reported:capital-expenditures-2025"
    )
    capex_start = capex.period.start_date
    assert capex_start is not None
    shifted_capex = capex.model_copy(
        update={
            "period": capex.period.model_copy(
                update={"start_date": capex_start + timedelta(days=1)}
            )
        }
    )
    with pytest.raises(ValidationError, match="same-period cash flow and capex"):
        rebuild(
            draft,
            financial_facts=tuple(
                shifted_capex if fact.fact_id == capex.fact_id else fact
                for fact in draft.financial_facts
            ),
            derived_facts=tuple(
                free_cash_flow if fact.fact_id == free_cash_flow.fact_id else fact
                for fact in draft.derived_facts
            ),
        )

    gross_margin = next(
        fact for fact in draft.derived_facts if fact.metric is DerivedMetric.GROSS_MARGIN
    )
    gross_profit = next(
        fact for fact in draft.financial_facts if fact.fact_id == "reported:gross-profit-2025"
    )
    gross_profit_start = gross_profit.period.start_date
    assert gross_profit_start is not None
    shifted_gross_profit = gross_profit.model_copy(
        update={
            "period": gross_profit.period.model_copy(
                update={"start_date": gross_profit_start + timedelta(days=1)}
            )
        }
    )
    with pytest.raises(ValidationError, match="same-period revenue and gross profit"):
        rebuild(
            draft,
            financial_facts=tuple(
                shifted_gross_profit if fact.fact_id == gross_profit.fact_id else fact
                for fact in draft.financial_facts
            ),
            derived_facts=tuple(
                gross_margin if fact.fact_id == gross_margin.fact_id else fact
                for fact in draft.derived_facts
            ),
        )

    net_debt = next(fact for fact in draft.derived_facts if fact.metric is DerivedMetric.NET_DEBT)
    cash = next(
        fact
        for fact in draft.financial_facts
        if fact.fact_id == "reported:cash-and-investments-2025"
    )
    shifted_cash = cash.model_copy(
        update={
            "period": cash.period.model_copy(
                update={"end_date": cash.period.end_date - timedelta(days=1)}
            )
        }
    )
    with pytest.raises(ValidationError, match="same-date debt and cash"):
        rebuild(
            draft,
            financial_facts=tuple(
                shifted_cash if fact.fact_id == cash.fact_id else fact
                for fact in draft.financial_facts
            ),
            derived_facts=tuple(
                net_debt if fact.fact_id == net_debt.fact_id else fact
                for fact in draft.derived_facts
            ),
        )

    roic = next(
        fact
        for fact in draft.derived_facts
        if fact.metric is DerivedMetric.RETURN_ON_INVESTED_CAPITAL
    )
    invested_capital = next(
        fact
        for fact in draft.financial_facts
        if fact.fact_id == "adjusted:average-invested-capital-2025"
    )
    invested_capital_start = invested_capital.period.start_date
    assert invested_capital_start is not None
    shifted_invested_capital = invested_capital.model_copy(
        update={
            "period": invested_capital.period.model_copy(
                update={"start_date": invested_capital_start + timedelta(days=1)}
            )
        }
    )
    with pytest.raises(ValidationError, match="same-period NOPAT and invested capital"):
        rebuild(
            draft,
            financial_facts=tuple(
                shifted_invested_capital if fact.fact_id == invested_capital.fact_id else fact
                for fact in draft.financial_facts
            ),
            derived_facts=tuple(
                roic if fact.fact_id == roic.fact_id else fact for fact in draft.derived_facts
            ),
        )

    prior_revenue = next(
        fact for fact in draft.financial_facts if fact.fact_id == "reported:revenue-2024"
    )
    incomparable_prior = prior_revenue.model_copy(
        update={
            "period": prior_revenue.period.model_copy(
                update={"duration_scope": FinancialPeriodScope.FISCAL_QUARTER}
            )
        }
    )
    with pytest.raises(ValidationError, match="comparable period scopes"):
        rebuild(
            draft,
            financial_facts=tuple(
                incomparable_prior if fact.fact_id == prior_revenue.fact_id else fact
                for fact in draft.financial_facts
            ),
        )

    prior_start = prior_revenue.period.start_date
    assert prior_start is not None
    shortened_prior = prior_revenue.model_copy(
        update={
            "period": prior_revenue.period.model_copy(
                update={"start_date": prior_start + timedelta(days=90)}
            )
        }
    )
    with pytest.raises(ValidationError, match="comparable duration lengths"):
        rebuild(
            draft,
            financial_facts=tuple(
                shortened_prior if fact.fact_id == prior_revenue.fact_id else fact
                for fact in draft.financial_facts
            ),
        )


@pytest.mark.parametrize(
    ("component", "field", "message"),
    [
        ("dimension", "claim_ids", "component references unknown claims"),
        ("dimension", "fact_ids", "dimension references unknown financial facts"),
        ("gate", "claim_ids", "component references unknown claims"),
        ("gate", "fact_ids", "eligibility gate references unknown financial facts"),
        ("scenario", "assumption_claim_ids", "unknown assumption claims"),
        ("scenario", "supporting_fact_ids", "unknown financial facts"),
        ("catalyst", "claim_ids", "catalyst or risk references unknown claims"),
        ("risk", "claim_ids", "catalyst or risk references unknown claims"),
    ],
)
def test_analytical_components_reject_unknown_references(
    component: str,
    field: str,
    message: str,
) -> None:
    _, draft = make_underwriting_context()
    overrides: dict[str, object]
    if component == "dimension":
        dimension = draft.dimensions[0]
        dimension_replacement = dimension.model_copy(
            update={field: (uuid4(),) if field == "claim_ids" else ("reported:missing",)}
        )
        overrides = {"dimensions": (dimension_replacement, *draft.dimensions[1:])}
    elif component == "gate":
        gate = draft.eligibility_gates[1]
        gate_replacement = gate.model_copy(
            update={field: (uuid4(),) if field == "claim_ids" else ("reported:missing",)}
        )
        overrides = {
            "eligibility_gates": (
                draft.eligibility_gates[0],
                gate_replacement,
                *draft.eligibility_gates[2:],
            )
        }
    elif component == "scenario":
        scenario = draft.valuation_scenarios[0]
        value: tuple[object, ...] = (
            (uuid4(),) if field == "assumption_claim_ids" else ("reported:missing",)
        )
        scenario_replacement = scenario.model_copy(update={field: value})
        overrides = {
            "valuation_scenarios": (
                scenario_replacement,
                *draft.valuation_scenarios[1:],
            )
        }
    elif component == "catalyst":
        catalyst_replacement = draft.catalysts[0].model_copy(update={field: (uuid4(),)})
        overrides = {"catalysts": (catalyst_replacement,)}
    else:
        risk_replacement = draft.risks[0].model_copy(update={field: (uuid4(),)})
        overrides = {"risks": (risk_replacement, *draft.risks[1:])}
    with pytest.raises(ValidationError, match=message):
        rebuild(draft, **overrides)


def test_scenarios_require_interpretive_claim_and_price_share_debt_support() -> None:
    _, draft = make_underwriting_context()
    assumption_id = draft.valuation_scenarios[0].assumption_claim_ids[0]
    observed_claims = tuple(
        claim.model_copy(update={"claim_type": ClaimType.OBSERVATION})
        if claim.claim_id == assumption_id
        else claim
        for claim in draft.claims
    )
    with pytest.raises(ValidationError, match="assumption claim must be inferential"):
        rebuild(draft, claims=observed_claims)

    scenario = draft.valuation_scenarios[0]
    for omitted, message in (
        ("reported:diluted-shares-outstanding-2025", "outstanding-share fact support"),
        ("derived:net-debt", "net-debt anchor lacks exact"),
    ):
        changed = scenario.model_copy(
            update={
                "supporting_fact_ids": tuple(
                    fact_id for fact_id in scenario.supporting_fact_ids if fact_id != omitted
                )
            }
        )
        with pytest.raises(ValidationError, match=message):
            rebuild(draft, valuation_scenarios=(changed, *draft.valuation_scenarios[1:]))


def test_scenario_requires_exact_market_observation_and_capital_structure_anchors() -> None:
    _, draft = make_underwriting_context()
    scenario = draft.valuation_scenarios[0]

    with pytest.raises(ValidationError, match="horizon_date must follow"):
        revalidate(scenario, horizon_date=scenario.reference_price_date)

    price = next(
        fact
        for fact in draft.financial_facts
        if fact.metric is FinancialMetric.REFERENCE_SHARE_PRICE
    )
    mislabeled_price = price.model_copy(update={"basis": FinancialFactBasis.REPORTED})
    with pytest.raises(ValidationError, match="requires market_observed basis"):
        rebuild(
            draft,
            financial_facts=tuple(
                mislabeled_price if fact.fact_id == price.fact_id else fact
                for fact in draft.financial_facts
            ),
        )

    weighted_average_only = scenario.model_copy(
        update={
            "supporting_fact_ids": tuple(
                "reported:diluted-shares-2025"
                if fact_id == "reported:diluted-shares-outstanding-2025"
                else fact_id
                for fact_id in scenario.supporting_fact_ids
            )
        }
    )
    with pytest.raises(ValidationError, match="outstanding-share fact support"):
        rebuild(
            draft,
            valuation_scenarios=(weighted_average_only, *draft.valuation_scenarios[1:]),
        )

    changed_anchor = scenario.model_copy(
        update={"anchor_net_debt_millions": scenario.anchor_net_debt_millions + Decimal(1)}
    )
    with pytest.raises(ValidationError, match="net-debt anchor lacks exact"):
        rebuild(draft, valuation_scenarios=(changed_anchor, *draft.valuation_scenarios[1:]))

    expired_horizon = tuple(
        scenario.model_copy(update={"horizon_date": draft.knowledge_boundary.as_of.date()})
        for scenario in draft.valuation_scenarios
    )
    with pytest.raises(ValidationError, match="horizon must remain future"):
        rebuild(draft, valuation_scenarios=expired_horizon)

    changed_horizon = draft.valuation_scenarios[-1].model_copy(
        update={"horizon_date": draft.valuation_scenarios[-1].horizon_date + timedelta(days=1)}
    )
    with pytest.raises(ValidationError, match="must share currency, reference observation"):
        rebuild(
            draft,
            valuation_scenarios=(*draft.valuation_scenarios[:-1], changed_horizon),
        )


def test_partial_or_unpaired_scenarios_and_bad_payoff_ratio_are_rejected() -> None:
    _, draft = make_underwriting_context()
    with pytest.raises(ValidationError, match="exactly bear, base, and bull"):
        rebuild(
            draft,
            status=OpportunityStatus.INVESTIGATE,
            valuation_scenarios=(draft.valuation_scenarios[0],),
        )
    with pytest.raises(ValidationError, match="payoff_profile requires valuation scenarios"):
        rebuild(
            draft,
            status=OpportunityStatus.INVESTIGATE,
            valuation_scenarios=(),
        )
    with pytest.raises(ValidationError, match="require payoff_profile"):
        rebuild(draft, status=OpportunityStatus.INVESTIGATE, payoff_profile=None)

    payoff = draft.payoff_profile
    assert payoff is not None
    assert payoff.upside_to_downside_ratio is not None
    wrong_ratio = payoff.model_copy(
        update={"upside_to_downside_ratio": payoff.upside_to_downside_ratio + Decimal("1")}
    )
    with pytest.raises(ValidationError, match="ratio must match"):
        rebuild(draft, payoff_profile=wrong_ratio)

    high_price = Decimal("300")
    price = next(
        fact
        for fact in draft.financial_facts
        if fact.metric is FinancialMetric.REFERENCE_SHARE_PRICE
    )
    repriced_fact = price.model_copy(update={"value": high_price})
    repriced_scenarios = tuple(
        scenario.model_copy(
            update={
                "reference_price": high_price,
                "return_from_reference": scenario.value_per_share / high_price - Decimal(1),
            }
        )
        for scenario in draft.valuation_scenarios
    )
    undefined_ratio_payoff = payoff.model_copy(
        update={
            "bear_return": repriced_scenarios[0].return_from_reference,
            "base_return": repriced_scenarios[1].return_from_reference,
            "bull_return": repriced_scenarios[2].return_from_reference,
            "upside_to_downside_ratio": Decimal("1"),
        }
    )
    valid_no_ratio_payoff = undefined_ratio_payoff.model_copy(
        update={"upside_to_downside_ratio": None}
    )
    no_ratio_draft = rebuild(
        draft,
        financial_facts=tuple(
            repriced_fact if fact.fact_id == price.fact_id else fact
            for fact in draft.financial_facts
        ),
        valuation_scenarios=repriced_scenarios,
        payoff_profile=valid_no_ratio_payoff,
    )
    assert no_ratio_draft.payoff_profile is not None
    assert no_ratio_draft.payoff_profile.upside_to_downside_ratio is None

    with pytest.raises(ValidationError, match="undefined without loss and gain"):
        rebuild(
            draft,
            financial_facts=tuple(
                repriced_fact if fact.fact_id == price.fact_id else fact
                for fact in draft.financial_facts
            ),
            valuation_scenarios=repriced_scenarios,
            payoff_profile=undefined_ratio_payoff,
        )


def test_ready_state_rejects_unknown_dimension_and_incomplete_lineage() -> None:
    _, draft = make_underwriting_context()
    original = next(
        dimension
        for dimension in draft.dimensions
        if dimension.kind is UnderwritingDimensionKind.VALUE_CAPTURE_AND_COMPETITION
    )
    unknown = original.model_copy(
        update={
            "outcome": DimensionOutcome.UNKNOWN,
            "missing_data": ("The entire dimension remains unknown.",),
        }
    )
    with pytest.raises(ValidationError, match="cannot contain unknown dimensions"):
        rebuild(
            draft,
            dimensions=tuple(
                unknown if dimension.kind is original.kind else dimension
                for dimension in draft.dimensions
            ),
        )
    with pytest.raises(ValidationError, match="incomplete analytical lineage"):
        rebuild(draft, catalysts=())
    with pytest.raises(ValidationError, match="requires three valuation scenarios"):
        rebuild(draft, valuation_scenarios=(), payoff_profile=None)
    with pytest.raises(ValidationError, match="allowed only for invalidated"):
        rebuild(draft, invalidation_reason="Not allowed for a ready state.")

    no_dimension_invalidation = draft.dimensions[0].model_copy(
        update={"invalidation_conditions": ()}
    )
    with pytest.raises(ValidationError, match="dimension-level invalidations"):
        rebuild(
            draft,
            dimensions=(no_dimension_invalidation, *draft.dimensions[1:]),
        )

    expired = draft.catalysts[0].model_copy(
        update={"window_start": date(2020, 1, 1), "window_end": date(2020, 12, 31)}
    )
    with pytest.raises(ValidationError, match="expired catalysts"):
        rebuild(draft, catalysts=(expired,))


def test_builder_rechecks_causal_sources_and_direct_candidate_provenance() -> None:
    repository, draft = make_underwriting_context()
    causal_source_id = draft.causal_analysis.source_document_ids[0]
    del repository.documents[causal_source_id]
    with pytest.raises(UnderwritingSourceNotFoundError, match=str(causal_source_id)):
        BuildOpportunityState(repository).execute(draft)

    repository, draft = make_underwriting_context()
    filing_id = next(
        document_id
        for document_id in draft.source_document_ids
        if repository.documents[document_id].source_type.value == "filing"
    )
    repository.documents[filing_id] = repository.documents[filing_id].model_copy(
        update={"subject_id": "company:sec-cik-0001045810"}
    )
    with pytest.raises(ValidationError, match="candidate-subject provenance"):
        BuildOpportunityState(repository).execute(draft)
