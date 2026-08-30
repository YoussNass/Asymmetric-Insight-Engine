"""Deterministic Chapter 6C1 fixtures across Underwriting, State, and Exposure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from asymmetric_engine.application.causal_analysis import BuildCausalAnalysis
from asymmetric_engine.application.marginal_decision import BuildMarginalDecision
from asymmetric_engine.application.portfolio_exposure import BuildPortfolioExposure
from asymmetric_engine.application.portfolio_state import BuildPortfolioState
from asymmetric_engine.application.underwriting import BuildOpportunityState
from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.opportunity import OpportunityState, OpportunityStatus
from asymmetric_engine.domain.portfolio import (
    CANDIDATE_ALTERNATIVE_ID,
    CORE_ETF_ALTERNATIVE_ID,
    EXISTING_HOLDING_ALTERNATIVE_ID,
    INVESTMENT_CASH_ALTERNATIVE_ID,
    CandidateEquityInstrument,
    CapitalUnit,
    ComponentPreference,
    DecisionConfidence,
    DecisionConfidenceLevel,
    ETFConstituent,
    HypotheticalPosition,
    MarginalDecisionInput,
    PairwiseCapitalComparison,
    PairwiseConclusion,
    PermanentLossAssessment,
    PermanentLossClass,
    PortfolioExposure,
    PortfolioExposureInput,
    PortfolioState,
    PortfolioStateDraft,
    TradeOffComponent,
    TradeOffDimension,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary
from tests.causal_factories import make_causal_draft, make_reference_sources
from tests.exposure_factories import (
    CONSUMER_COMPANY_ID,
    CORE_SNAPSHOT_EVIDENCE_ID,
    INDUSTRIAL_COMPANY_ID,
    MICRON_COMPANY_ID,
    THEMATIC_SNAPSHOT_EVIDENCE_ID,
    make_exposure_input,
    rebuild_exposure_input,
)
from tests.memory_repository import MemorySourceRepository
from tests.portfolio_factories import make_portfolio_draft, rebuild_portfolio_draft
from tests.underwriting_factories import make_underwriting_draft, make_underwriting_sources

CAPITAL_AMOUNT = MonetaryAmount(amount=Decimal("100"), currency="USD")
CANDIDATE_INSTRUMENT_ID = "instrument:prospective-micron"
EXISTING_INSTRUMENT_ID = "instrument:existing-equity"
EXISTING_POSITION_ID = "position:broker-a:existing-equity"
REFERENCE_PRICE_FACT_ID = "reported:reference-price"
PERMANENT_LOSS_CLASS_BY_ALTERNATIVE = {
    CANDIDATE_ALTERNATIVE_ID: PermanentLossClass.MODERATE,
    EXISTING_HOLDING_ALTERNATIVE_ID: PermanentLossClass.MODERATE,
    CORE_ETF_ALTERNATIVE_ID: PermanentLossClass.LOW,
    INVESTMENT_CASH_ALTERNATIVE_ID: PermanentLossClass.LOW,
}


@dataclass(frozen=True)
class DecisionContext:
    """Verified T0 inputs and builders needed to replay one marginal decision."""

    opportunity_builder: BuildOpportunityState
    state_builder: BuildPortfolioState
    exposure_builder: BuildPortfolioExposure
    decision_builder: BuildMarginalDecision
    opportunity_state: OpportunityState
    portfolio_state: PortfolioState
    current_exposure: PortfolioExposure
    existing_exposure: PortfolioExposure
    core_etf_exposure: PortfolioExposure
    decision_input: MarginalDecisionInput

    @property
    def alternative_exposures(self) -> tuple[PortfolioExposure, ...]:
        return (self.existing_exposure, self.core_etf_exposure)


def make_decision_context(
    *,
    include_candidate_profile: bool = True,
    opportunity_status: OpportunityStatus = OpportunityStatus.READY_FOR_PORTFOLIO_REVIEW,
    existing_currency: str = "USD",
    core_currency: str = "USD",
) -> DecisionContext:
    """Build one coherent, single-currency Chapter 6C1 decision fixture."""

    portfolio_draft = _make_decision_portfolio_draft(
        existing_currency=existing_currency,
        core_currency=core_currency,
    )
    boundary = portfolio_draft.knowledge_boundary
    repository, opportunity = _make_opportunity(boundary=boundary, status=opportunity_status)

    state_builder = BuildPortfolioState()
    state = state_builder.execute(portfolio_draft)
    exposure_builder = BuildPortfolioExposure(state_builder=state_builder)
    current_input, existing_input, core_input = _make_exposure_inputs(
        include_candidate_profile=include_candidate_profile,
        existing_currency=existing_currency,
        core_currency=core_currency,
    )
    current_exposure = exposure_builder.execute(state, current_input)
    existing_exposure = exposure_builder.execute(state, existing_input)
    core_exposure = exposure_builder.execute(state, core_input)

    opportunity_builder = BuildOpportunityState(repository)
    decision_builder = BuildMarginalDecision(
        opportunity_builder=opportunity_builder,
        state_builder=state_builder,
        exposure_builder=exposure_builder,
    )
    decision_input = make_decision_input(opportunity)
    return DecisionContext(
        opportunity_builder=opportunity_builder,
        state_builder=state_builder,
        exposure_builder=exposure_builder,
        decision_builder=decision_builder,
        opportunity_state=opportunity,
        portfolio_state=state,
        current_exposure=current_exposure,
        existing_exposure=existing_exposure,
        core_etf_exposure=core_exposure,
        decision_input=decision_input,
    )


def make_decision_input(opportunity: OpportunityState) -> MarginalDecisionInput:
    """Return a complete input where the candidate uniquely beats all alternatives."""

    risk_id = opportunity.risks[0].risk_id
    assessments = (
        PermanentLossAssessment(
            alternative_id=CANDIDATE_ALTERNATIVE_ID,
            risk_class=PERMANENT_LOSS_CLASS_BY_ALTERNATIVE[CANDIDATE_ALTERNATIVE_ID],
            rationale="The verified case has material but explicitly bounded business risks.",
            supporting_risk_ids=(risk_id,),
        ),
        PermanentLossAssessment(
            alternative_id=EXISTING_HOLDING_ALTERNATIVE_ID,
            risk_class=PERMANENT_LOSS_CLASS_BY_ALTERNATIVE[EXISTING_HOLDING_ALTERNATIVE_ID],
            rationale="The incumbent remains exposed to an ordinary listed-equity loss path.",
        ),
        PermanentLossAssessment(
            alternative_id=CORE_ETF_ALTERNATIVE_ID,
            risk_class=PERMANENT_LOSS_CLASS_BY_ALTERNATIVE[CORE_ETF_ALTERNATIVE_ID],
            rationale="Diversification reduces issuer-specific permanent-loss exposure.",
        ),
        PermanentLossAssessment(
            alternative_id=INVESTMENT_CASH_ALTERNATIVE_ID,
            risk_class=PERMANENT_LOSS_CLASS_BY_ALTERNATIVE[INVESTMENT_CASH_ALTERNATIVE_ID],
            rationale="Nominal capital is preserved while purchasing power remains at risk.",
        ),
    )
    comparisons = (
        _comparison(CANDIDATE_ALTERNATIVE_ID, CORE_ETF_ALTERNATIVE_ID, first_wins=True),
        _comparison(
            CANDIDATE_ALTERNATIVE_ID,
            EXISTING_HOLDING_ALTERNATIVE_ID,
            first_wins=True,
        ),
        _comparison(
            CANDIDATE_ALTERNATIVE_ID,
            INVESTMENT_CASH_ALTERNATIVE_ID,
            first_wins=True,
        ),
        _comparison(CORE_ETF_ALTERNATIVE_ID, EXISTING_HOLDING_ALTERNATIVE_ID),
        _comparison(CORE_ETF_ALTERNATIVE_ID, INVESTMENT_CASH_ALTERNATIVE_ID),
        _comparison(EXISTING_HOLDING_ALTERNATIVE_ID, INVESTMENT_CASH_ALTERNATIVE_ID),
    )
    return MarginalDecisionInput(
        knowledge_boundary=opportunity.knowledge_boundary,
        capital_unit=CapitalUnit(
            amount=CAPITAL_AMOUNT,
            funding_cash_ids=("cash:broker-a:opportunistic-usd",),
            rationale="Evaluate one explicit USD 100 unit without automatic sizing.",
        ),
        candidate_instrument=CandidateEquityInstrument(
            instrument_id=CANDIDATE_INSTRUMENT_ID,
            symbol="MU",
            name="Synthetic prospective Micron equity",
            listing_venue="NASDAQ",
            native_currency="USD",
            company_subject_id=MICRON_COMPANY_ID,
            reference_price=CAPITAL_AMOUNT,
            reference_price_date=date(2026, 8, 25),
            reference_price_fact_id=REFERENCE_PRICE_FACT_ID,
        ),
        existing_position_id=EXISTING_POSITION_ID,
        permanent_loss_assessments=assessments,
        comparisons=comparisons,
        best_rejected_alternative_id=CORE_ETF_ALTERNATIVE_ID,
        decision_rationale=(
            "The candidate has a verified standalone Opportunity State.",
            "Its direct portfolio effect is visible before capital is committed.",
            "It wins every explicit pairwise capital comparison in this fixture.",
        ),
        main_risks_and_unknowns=(
            "Underwriting probabilities and qualitative conclusions remain uncalibrated.",
        ),
        change_conditions=(
            "A thesis invalidation or a superior pairwise alternative changes the decision.",
        ),
        confidence=DecisionConfidence(
            level=DecisionConfidenceLevel.CONDITIONAL,
            rationale="Support is explicit but has not been prospectively calibrated.",
        ),
        missing_data=("No execution timing or tax-replacement analysis is admitted in 6C1.",),
        assumptions=("All four alternatives evaluate the same unconverted USD amount.",),
    )


def rebuild_decision_input(
    decision_input: MarginalDecisionInput,
    **overrides: object,
) -> MarginalDecisionInput:
    values = decision_input.model_dump(mode="python")
    values.update(overrides)
    return MarginalDecisionInput.model_validate(values)


def _make_decision_portfolio_draft(
    *,
    existing_currency: str,
    core_currency: str,
) -> PortfolioStateDraft:
    draft = make_portfolio_draft()
    existing = draft.instruments[0].model_copy(
        update={
            "instrument_id": EXISTING_INSTRUMENT_ID,
            "symbol": "EXIST",
            "name": "Synthetic eligible existing equity",
            "company_subject_id": INDUSTRIAL_COMPANY_ID,
            "native_currency": existing_currency,
        }
    )
    core = draft.instruments[1].model_copy(update={"native_currency": core_currency})
    instruments = (existing, core, draft.instruments[2])

    existing_price = draft.prices[0].model_copy(
        update={
            "price_id": "price:existing-equity:t0",
            "instrument_id": EXISTING_INSTRUMENT_ID,
            "unit_price": MonetaryAmount(amount=Decimal("110"), currency=existing_currency),
        }
    )
    core_price = draft.prices[1].model_copy(
        update={"unit_price": MonetaryAmount(amount=Decimal("100"), currency=core_currency)}
    )
    prices = (existing_price, core_price, draft.prices[2])

    existing_position = draft.positions[0].model_copy(
        update={
            "position_id": EXISTING_POSITION_ID,
            "instrument_id": EXISTING_INSTRUMENT_ID,
            "price_id": existing_price.price_id,
            "current_value": MonetaryAmount(amount=Decimal("1100"), currency=existing_currency),
            "cost_basis": draft.positions[0].cost_basis.model_copy(
                update={
                    "total_cost": MonetaryAmount(amount=Decimal("900"), currency=existing_currency)
                }
            ),
        }
    )
    positions = (existing_position, draft.positions[1])
    return rebuild_portfolio_draft(
        draft,
        title="Deterministic Chapter 6C1 portfolio fixture",
        instruments=instruments,
        prices=prices,
        positions=positions,
    )


def _make_opportunity(
    *,
    boundary: KnowledgeBoundary,
    status: OpportunityStatus,
) -> tuple[MemorySourceRepository, OpportunityState]:
    causal_documents, causal_contents = make_reference_sources()
    repository = MemorySourceRepository(
        documents={document.document_id: document for document in causal_documents},
        contents=dict(causal_contents),
    )
    causal_analysis = BuildCausalAnalysis(repository).execute(
        make_causal_draft(documents=causal_documents, boundary=boundary)
    )
    underwriting_documents, underwriting_contents = make_underwriting_sources()
    for document in underwriting_documents:
        repository.append(document, underwriting_contents[document.document_id])
    opportunity = BuildOpportunityState(repository).execute(
        make_underwriting_draft(
            causal_analysis=causal_analysis,
            documents=underwriting_documents,
            status=status,
        )
    )
    return repository, opportunity


def _make_exposure_inputs(
    *,
    include_candidate_profile: bool,
    existing_currency: str,
    core_currency: str,
) -> tuple[
    PortfolioExposureInput,
    PortfolioExposureInput,
    PortfolioExposureInput,
]:
    full = make_exposure_input()
    if not include_candidate_profile:
        full = _without_company_profile(full, MICRON_COMPANY_ID)
    current = _current_exposure_input(full)
    existing = rebuild_exposure_input(
        current,
        hypothetical_position=HypotheticalPosition(
            hypothetical_id=(f"hypothetical:existing-equity:{existing_currency.lower()}-100"),
            instrument_id=EXISTING_INSTRUMENT_ID,
            amount=MonetaryAmount(amount=Decimal("100"), currency=existing_currency),
            rationale="Describe adding the explicit capital unit to the incumbent.",
        ),
    )
    core = rebuild_exposure_input(
        full,
        hypothetical_position=HypotheticalPosition(
            hypothetical_id=f"hypothetical:core-etf:{core_currency.lower()}-100",
            instrument_id="instrument:core-equity-etf",
            amount=MonetaryAmount(amount=Decimal("100"), currency=core_currency),
            rationale="Describe adding the explicit capital unit to the core ETF.",
        ),
    )
    return current, existing, core


def _current_exposure_input(full: PortfolioExposureInput) -> PortfolioExposureInput:
    thematic_snapshot = next(
        item for item in full.etf_snapshots if item.evidence_id == THEMATIC_SNAPSHOT_EVIDENCE_ID
    )
    required_company_ids = {
        INDUSTRIAL_COMPANY_ID,
        *(item.company_subject_id for item in thematic_snapshot.constituents),
    }
    retained_profiles = tuple(
        item for item in full.company_profiles if item.company_subject_id in required_company_ids
    )
    retained_claim_ids = {
        claim_id
        for profile in retained_profiles
        for claim_id in (
            *(profile.sector.claim_ids if profile.sector is not None else ()),
            *(profile.geography.claim_ids if profile.geography is not None else ()),
            *(claim_id for driver in profile.economic_drivers for claim_id in driver.claim_ids),
        )
    }
    retained_claims = tuple(item for item in full.claims if item.claim_id in retained_claim_ids)
    retained_evidence_ids = {
        THEMATIC_SNAPSHOT_EVIDENCE_ID,
        *(evidence_id for claim in retained_claims for evidence_id in claim.evidence_ids),
    }
    return rebuild_exposure_input(
        full,
        evidence_items=tuple(
            item for item in full.evidence_items if item.evidence_id in retained_evidence_ids
        ),
        claims=retained_claims,
        etf_snapshots=tuple(
            item for item in full.etf_snapshots if item.evidence_id != CORE_SNAPSHOT_EVIDENCE_ID
        ),
        company_profiles=retained_profiles,
        hypothetical_position=None,
    )


def _without_company_profile(
    exposure_input: PortfolioExposureInput,
    company_subject_id: str,
) -> PortfolioExposureInput:
    rewritten_snapshots = tuple(
        snapshot.model_copy(
            update={
                "constituents": _replace_constituent_company(
                    snapshot.constituents,
                    source_company_id=company_subject_id,
                    replacement_company_id=CONSUMER_COMPANY_ID,
                )
            }
        )
        for snapshot in exposure_input.etf_snapshots
    )
    retained_profiles = tuple(
        item
        for item in exposure_input.company_profiles
        if item.company_subject_id != company_subject_id
    )
    retained_claim_ids = {
        claim_id
        for profile in retained_profiles
        for claim_id in (
            *(profile.sector.claim_ids if profile.sector is not None else ()),
            *(profile.geography.claim_ids if profile.geography is not None else ()),
            *(claim_id for driver in profile.economic_drivers for claim_id in driver.claim_ids),
        )
    }
    retained_claims = tuple(
        item for item in exposure_input.claims if item.claim_id in retained_claim_ids
    )
    snapshot_evidence_ids = {snapshot.evidence_id for snapshot in rewritten_snapshots}
    retained_evidence_ids = {
        *snapshot_evidence_ids,
        *(evidence_id for claim in retained_claims for evidence_id in claim.evidence_ids),
    }
    return rebuild_exposure_input(
        exposure_input,
        evidence_items=tuple(
            item
            for item in exposure_input.evidence_items
            if item.evidence_id in retained_evidence_ids
        ),
        claims=retained_claims,
        etf_snapshots=rewritten_snapshots,
        company_profiles=retained_profiles,
    )


def _replace_constituent_company(
    constituents: tuple[ETFConstituent, ...],
    *,
    source_company_id: str,
    replacement_company_id: str,
) -> tuple[ETFConstituent, ...]:
    weights: dict[str, Decimal] = {}
    for constituent in constituents:
        company_id = (
            replacement_company_id
            if constituent.company_subject_id == source_company_id
            else constituent.company_subject_id
        )
        weights[company_id] = weights.get(company_id, Decimal(0)) + constituent.weight
    return tuple(
        ETFConstituent(company_subject_id=company_id, weight=weight)
        for company_id, weight in sorted(weights.items())
    )


def _comparison(
    first: str,
    second: str,
    *,
    first_wins: bool = True,
) -> PairwiseCapitalComparison:
    preferred = ComponentPreference.FIRST if first_wins else ComponentPreference.SECOND
    conclusion = PairwiseConclusion.FIRST if first_wins else PairwiseConclusion.SECOND
    first_loss_class = PERMANENT_LOSS_CLASS_BY_ALTERNATIVE[first]
    second_loss_class = PERMANENT_LOSS_CLASS_BY_ALTERNATIVE[second]
    loss_rank = {
        PermanentLossClass.LOW: 0,
        PermanentLossClass.MODERATE: 1,
        PermanentLossClass.HIGH: 2,
        PermanentLossClass.UNKNOWN: 3,
    }
    if PermanentLossClass.UNKNOWN in {first_loss_class, second_loss_class}:
        permanent_loss_preference = ComponentPreference.UNKNOWN
    elif first_loss_class is second_loss_class:
        permanent_loss_preference = ComponentPreference.BALANCED
    elif loss_rank[first_loss_class] < loss_rank[second_loss_class]:
        permanent_loss_preference = ComponentPreference.FIRST
    else:
        permanent_loss_preference = ComponentPreference.SECOND
    return PairwiseCapitalComparison(
        first_alternative_id=first,
        second_alternative_id=second,
        components=(
            TradeOffComponent(
                dimension=TradeOffDimension.STANDALONE_CASE,
                preference=preferred,
                rationale="The preferred alternative has stronger disclosed standalone support.",
            ),
            TradeOffComponent(
                dimension=TradeOffDimension.PERMANENT_LOSS,
                preference=permanent_loss_preference,
                rationale="The ordinal loss classes are compared directly and never averaged.",
                missing_data=(
                    ("One or both permanent-loss classes are unknown.",)
                    if permanent_loss_preference is ComponentPreference.UNKNOWN
                    else ()
                ),
            ),
            TradeOffComponent(
                dimension=TradeOffDimension.PORTFOLIO_EFFECT,
                preference=ComponentPreference.BALANCED,
                rationale="Portfolio effects are reviewed as a separate descriptive component.",
            ),
            TradeOffComponent(
                dimension=TradeOffDimension.UNCERTAINTY,
                preference=ComponentPreference.BALANCED,
                rationale="Uncertainty remains explicitly uncalibrated for both alternatives.",
            ),
        ),
        conclusion=conclusion,
        rationale="The conclusion follows the disclosed components without a weighted score.",
    )
