"""Build conservative, explicit Chapter 6C1 Portfolio Fit and capital decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from asymmetric_engine.application.portfolio_exposure import BuildPortfolioExposure
from asymmetric_engine.application.portfolio_state import BuildPortfolioState
from asymmetric_engine.application.underwriting import BuildOpportunityState
from asymmetric_engine.domain.financial import MonetaryAmount, canonical_decimal
from asymmetric_engine.domain.opportunity import (
    FinancialFactBasis,
    FinancialMetric,
    OpportunityState,
    OpportunityStatus,
)
from asymmetric_engine.domain.portfolio import (
    CANDIDATE_ALTERNATIVE_ID,
    CORE_ETF_ALTERNATIVE_ID,
    EXISTING_HOLDING_ALTERNATIVE_ID,
    INVESTMENT_CASH_ALTERNATIVE_ID,
    PORTFOLIO_FIT_METHOD_VERSION,
    POSITION_REVIEW_METHOD_VERSION,
    CandidateEquityInstrument,
    CapitalAlternative,
    CapitalAlternativeKind,
    ComponentPreference,
    DecisionBasis,
    FitCurrencyEffect,
    FitDerivationKind,
    FitExposureDimension,
    HHIBounds,
    MarginalDecision,
    MarginalDecisionInput,
    MarginalDecisionOutcome,
    OpportunityStateReference,
    PairwiseCapitalComparison,
    PairwiseConclusion,
    PermanentLossClass,
    PortfolioExposure,
    PortfolioExposureReference,
    PortfolioFit,
    PortfolioFitReference,
    PortfolioState,
    PortfolioStateReference,
    PositionReview,
    PositionReviewInput,
    PositionReviewOutcome,
    TradeOffDimension,
    WeightDelta,
)
from asymmetric_engine.domain.portfolio.exposure import (
    CompanyExposureProfile,
    CurrencyExposureBook,
    ExposureSnapshot,
)
from asymmetric_engine.domain.portfolio.models import InstrumentType, Position

_RATIO_QUANTUM = Decimal("0.000000000001")
_UNRESOLVED_COMPONENT_ID = "exposure:unresolved-company"


class MarginalDecisionIntegrityError(ValueError):
    """A decision package no longer matches its verified inputs and canonical derivation."""


class PositionReviewIntegrityError(ValueError):
    """A HOLD review no longer matches its verified factual inputs."""


@dataclass(frozen=True)
class MarginalDecisionResult:
    """Application response retaining distinct Fit states and the decision that consumes them."""

    fits: tuple[PortfolioFit, ...]
    decision: MarginalDecision


class BuildMarginalDecision:
    """Compare four explicit alternatives without scores, thresholds, or automatic sizing."""

    def __init__(
        self,
        *,
        opportunity_builder: BuildOpportunityState,
        state_builder: BuildPortfolioState | None = None,
        exposure_builder: BuildPortfolioExposure | None = None,
    ) -> None:
        self._opportunity_builder = opportunity_builder
        self._state_builder = state_builder or BuildPortfolioState()
        self._exposure_builder = exposure_builder or BuildPortfolioExposure(
            state_builder=self._state_builder
        )

    def execute(
        self,
        *,
        portfolio_state: PortfolioState,
        opportunity_state: OpportunityState,
        current_exposure: PortfolioExposure,
        alternative_exposures: tuple[PortfolioExposure, ...],
        decision_input: MarginalDecisionInput,
    ) -> MarginalDecisionResult:
        """Build four Portfolio Fits and apply unique pairwise-dominance policy."""

        verified_state = self._state_builder.verify(portfolio_state)
        verified_opportunity = self._opportunity_builder.verify(opportunity_state)
        verified_current = self._exposure_builder.verify(verified_state, current_exposure)
        verified_alternatives = tuple(
            self._exposure_builder.verify(verified_state, exposure)
            for exposure in alternative_exposures
        )
        canonical_input = self._canonicalize_input(decision_input)
        self._validate_common_boundary(
            verified_state,
            verified_opportunity,
            verified_current,
            verified_alternatives,
            canonical_input,
        )
        if verified_current.hypothetical_position is not None or verified_current.after is not None:
            raise ValueError("current Portfolio Exposure cannot contain a hypothetical position")

        self._validate_funding(verified_state, canonical_input)
        self._validate_candidate(verified_state, verified_opportunity, canonical_input)
        self._validate_permanent_loss_comparisons(canonical_input)
        existing_position = self._existing_position(verified_state, canonical_input)
        benchmark_id = verified_state.etf_eligibility_policy.benchmark_instrument_id
        benchmark = next(
            instrument
            for instrument in verified_state.instruments
            if instrument.instrument_id == benchmark_id
        )
        capital = canonical_input.capital_unit.amount
        if existing_position.current_value.currency != capital.currency:
            raise ValueError("existing holding must use the evaluated capital currency")
        if benchmark.native_currency != capital.currency:
            raise ValueError("core ETF must use the evaluated capital currency")

        exposure_by_instrument = self._validate_alternative_exposures(
            verified_current,
            verified_alternatives,
            expected_instrument_ids={existing_position.instrument_id, benchmark_id},
            capital=capital,
        )
        state_reference = self._state_reference(verified_state)
        opportunity_reference = self._opportunity_reference(verified_opportunity)
        base_exposure_reference = self._exposure_reference(verified_current)
        alternatives = self._build_alternatives(
            verified_state,
            verified_opportunity,
            canonical_input,
            existing_position,
        )
        alternative_by_id = {item.alternative_id: item for item in alternatives}
        candidate_profile = self._candidate_profile(
            canonical_input.candidate_instrument,
            (verified_current, *verified_alternatives),
        )

        fits = (
            self._build_candidate_fit(
                alternative=alternative_by_id[CANDIDATE_ALTERNATIVE_ID],
                candidate=canonical_input.candidate_instrument,
                profile=candidate_profile,
                portfolio_state=state_reference,
                opportunity_state=opportunity_reference,
                base_exposure=base_exposure_reference,
                current_snapshot=verified_current.before,
                current_exposure=verified_current,
                decision_input=canonical_input,
                opportunity=verified_opportunity,
            ),
            self._build_verified_exposure_fit(
                alternative=alternative_by_id[EXISTING_HOLDING_ALTERNATIVE_ID],
                portfolio_state=state_reference,
                base_exposure=base_exposure_reference,
                current_exposure=verified_current,
                alternative_exposure=exposure_by_instrument[existing_position.instrument_id],
                decision_input=canonical_input,
            ),
            self._build_verified_exposure_fit(
                alternative=alternative_by_id[CORE_ETF_ALTERNATIVE_ID],
                portfolio_state=state_reference,
                base_exposure=base_exposure_reference,
                current_exposure=verified_current,
                alternative_exposure=exposure_by_instrument[benchmark_id],
                decision_input=canonical_input,
            ),
            self._build_cash_fit(
                alternative=alternative_by_id[INVESTMENT_CASH_ALTERNATIVE_ID],
                portfolio_state=state_reference,
                base_exposure=base_exposure_reference,
                current_exposure=verified_current,
                decision_input=canonical_input,
            ),
        )
        fit_references = tuple(
            PortfolioFitReference(
                fit_id=fit.fit_id,
                alternative_id=fit.alternative.alternative_id,
                input_fingerprint=fit.input_fingerprint,
            )
            for fit in fits
        )
        winner = self._dominance_winner(canonical_input.comparisons)
        if winner is not None and winner != INVESTMENT_CASH_ALTERNATIVE_ID:
            outcome = MarginalDecisionOutcome.ALLOCATE
            selected = winner
            basis = DecisionBasis.UNIQUE_PAIRWISE_DOMINANCE
        else:
            outcome = MarginalDecisionOutcome.NO_ALLOCATION
            selected = INVESTMENT_CASH_ALTERNATIVE_ID
            basis = DecisionBasis.CONSERVATIVE_CASH_DEFAULT

        decision_material = {
            "portfolio_state": state_reference.model_dump(mode="json"),
            "opportunity_state": opportunity_reference.model_dump(mode="json"),
            "decision_input": canonical_input.model_dump(mode="json"),
            "portfolio_fits": [item.model_dump(mode="json") for item in fit_references],
        }
        fingerprint = self._fingerprint(decision_material)
        decision = MarginalDecision.model_validate(
            {
                **canonical_input.model_dump(mode="python"),
                "decision_id": uuid5(
                    NAMESPACE_URL,
                    f"asymmetric-insight-engine:marginal-decision:{fingerprint}",
                ),
                "input_fingerprint": fingerprint,
                "portfolio_state": state_reference,
                "opportunity_state": opportunity_reference,
                "alternatives": alternatives,
                "portfolio_fits": fit_references,
                "outcome": outcome,
                "selected_alternative_id": selected,
                "dominance_winner_id": winner,
                "decision_basis": basis,
            }
        )
        return MarginalDecisionResult(fits=fits, decision=decision)

    def verify(
        self,
        *,
        portfolio_state: PortfolioState,
        opportunity_state: OpportunityState,
        current_exposure: PortfolioExposure,
        alternative_exposures: tuple[PortfolioExposure, ...],
        result: MarginalDecisionResult,
    ) -> MarginalDecisionResult:
        """Rebuild the package and reject altered Fit metrics, policy input, or identity."""

        input_values = {
            field_name: getattr(result.decision, field_name)
            for field_name in MarginalDecisionInput.model_fields
        }
        rebuilt = self.execute(
            portfolio_state=portfolio_state,
            opportunity_state=opportunity_state,
            current_exposure=current_exposure,
            alternative_exposures=alternative_exposures,
            decision_input=MarginalDecisionInput.model_validate(input_values),
        )
        if rebuilt != result:
            raise MarginalDecisionIntegrityError(
                "Marginal Decision or Portfolio Fits do not match canonical replay"
            )
        return result

    @staticmethod
    def _canonicalize_input(decision_input: MarginalDecisionInput) -> MarginalDecisionInput:
        values: dict[str, Any] = decision_input.model_dump(mode="python")
        values["capital_unit"] = decision_input.capital_unit.model_copy(
            update={"funding_cash_ids": tuple(sorted(decision_input.capital_unit.funding_cash_ids))}
        )
        values["permanent_loss_assessments"] = tuple(
            sorted(
                (
                    item.model_copy(
                        update={
                            "supporting_risk_ids": tuple(sorted(item.supporting_risk_ids)),
                            "missing_data": tuple(sorted(item.missing_data)),
                        }
                    )
                    for item in decision_input.permanent_loss_assessments
                ),
                key=lambda item: item.alternative_id,
            )
        )
        values["comparisons"] = tuple(
            sorted(
                (
                    BuildMarginalDecision._canonicalize_comparison(item)
                    for item in decision_input.comparisons
                ),
                key=lambda item: (item.first_alternative_id, item.second_alternative_id),
            )
        )
        for field_name in ("missing_data", "conflicts", "assumptions"):
            values[field_name] = tuple(sorted(getattr(decision_input, field_name)))
        return MarginalDecisionInput.model_validate(values)

    @staticmethod
    def _canonicalize_comparison(
        comparison: PairwiseCapitalComparison,
    ) -> PairwiseCapitalComparison:
        first = comparison.first_alternative_id
        second = comparison.second_alternative_id
        reverse = first > second

        def flip_preference(preference: ComponentPreference) -> ComponentPreference:
            if preference is ComponentPreference.FIRST:
                return ComponentPreference.SECOND
            if preference is ComponentPreference.SECOND:
                return ComponentPreference.FIRST
            return preference

        conclusion = comparison.conclusion
        if reverse:
            if conclusion is PairwiseConclusion.FIRST:
                conclusion = PairwiseConclusion.SECOND
            elif conclusion is PairwiseConclusion.SECOND:
                conclusion = PairwiseConclusion.FIRST
        dimension_order = {kind: index for index, kind in enumerate(TradeOffDimension)}
        components = tuple(
            sorted(
                (
                    item.model_copy(
                        update={
                            "preference": flip_preference(item.preference)
                            if reverse
                            else item.preference,
                            "missing_data": tuple(sorted(item.missing_data)),
                        }
                    )
                    for item in comparison.components
                ),
                key=lambda item: dimension_order[item.dimension],
            )
        )
        return PairwiseCapitalComparison(
            first_alternative_id=second if reverse else first,
            second_alternative_id=first if reverse else second,
            components=components,
            conclusion=conclusion,
            rationale=comparison.rationale,
        )

    @staticmethod
    def _validate_common_boundary(
        portfolio_state: PortfolioState,
        opportunity: OpportunityState,
        current_exposure: PortfolioExposure,
        alternatives: tuple[PortfolioExposure, ...],
        decision_input: MarginalDecisionInput,
    ) -> None:
        boundaries = {
            portfolio_state.knowledge_boundary,
            opportunity.knowledge_boundary,
            current_exposure.knowledge_boundary,
            decision_input.knowledge_boundary,
            *(item.knowledge_boundary for item in alternatives),
        }
        if len(boundaries) != 1:
            raise ValueError("Chapter 6C1 requires one canonical knowledge boundary")

    @staticmethod
    def _validate_funding(
        portfolio_state: PortfolioState,
        decision_input: MarginalDecisionInput,
    ) -> None:
        cash_by_id = {item.cash_id: item for item in portfolio_state.cash_balances}
        available = Decimal(0)
        currency = decision_input.capital_unit.amount.currency
        for cash_id in decision_input.capital_unit.funding_cash_ids:
            cash = cash_by_id.get(cash_id)
            if cash is None:
                raise ValueError("capital unit references unknown cash")
            if not cash.is_investable:
                raise ValueError("emergency reserve cannot fund a marginal capital decision")
            if cash.balance.currency != currency:
                raise ValueError("funding cash must use the evaluated capital currency")
            available += cash.balance.amount
        if canonical_decimal(available) < decision_input.capital_unit.amount.amount:
            raise ValueError("funding cash is insufficient for the evaluated capital unit")

    @staticmethod
    def _validate_candidate(
        portfolio_state: PortfolioState,
        opportunity: OpportunityState,
        decision_input: MarginalDecisionInput,
    ) -> None:
        candidate = decision_input.candidate_instrument
        if opportunity.status is not OpportunityStatus.READY_FOR_PORTFOLIO_REVIEW:
            raise ValueError("candidate Opportunity State is not ready for Portfolio review")
        if candidate.company_subject_id != opportunity.candidate_id:
            raise ValueError("candidate instrument must map to the Opportunity State company")
        if candidate.instrument_id in {item.instrument_id for item in portfolio_state.instruments}:
            raise ValueError(
                "Chapter 6C1 candidate instrument must be prospective, not state-owned"
            )
        if candidate.native_currency != decision_input.capital_unit.amount.currency:
            raise ValueError("candidate instrument must use the evaluated capital currency")
        fact = next(
            (
                item
                for item in opportunity.financial_facts
                if item.fact_id == candidate.reference_price_fact_id
            ),
            None,
        )
        if fact is None:
            raise ValueError("candidate reference price fact is absent from Underwriting")
        if (
            fact.metric is not FinancialMetric.REFERENCE_SHARE_PRICE
            or fact.basis is not FinancialFactBasis.MARKET_OBSERVED
        ):
            raise ValueError("candidate price must reference the market-observed share-price fact")
        if (
            fact.value != candidate.reference_price.amount
            or fact.currency != candidate.reference_price.currency
            or fact.period.end_date != candidate.reference_price_date
        ):
            raise ValueError("candidate instrument price must match the Underwriting market fact")
        for scenario in opportunity.valuation_scenarios:
            if (
                scenario.currency != candidate.native_currency
                or scenario.reference_price != candidate.reference_price.amount
                or scenario.reference_price_date != candidate.reference_price_date
            ):
                raise ValueError(
                    "candidate instrument must match every Underwriting scenario anchor"
                )

        risk_ids = {item.risk_id for item in opportunity.risks}
        assessments = {
            item.alternative_id: item for item in decision_input.permanent_loss_assessments
        }
        candidate_assessment = assessments[CANDIDATE_ALTERNATIVE_ID]
        if not candidate_assessment.supporting_risk_ids:
            raise ValueError("candidate permanent-loss judgement requires Underwriting risk ids")
        if not set(candidate_assessment.supporting_risk_ids).issubset(risk_ids):
            raise ValueError("candidate permanent-loss judgement references unknown risks")
        for alternative_id, assessment in assessments.items():
            if alternative_id != CANDIDATE_ALTERNATIVE_ID and assessment.supporting_risk_ids:
                raise ValueError(
                    "only the candidate may reference risks owned by its Opportunity State"
                )

    @staticmethod
    def _existing_position(
        portfolio_state: PortfolioState,
        decision_input: MarginalDecisionInput,
    ) -> Position:
        position = next(
            (
                item
                for item in portfolio_state.positions
                if item.position_id == decision_input.existing_position_id
            ),
            None,
        )
        if position is None:
            raise ValueError("existing-holding alternative references an unknown position")
        instrument = next(
            item
            for item in portfolio_state.instruments
            if item.instrument_id == position.instrument_id
        )
        if instrument.instrument_type is not InstrumentType.LISTED_EQUITY:
            raise ValueError("Chapter 6C1 existing-holding alternative must be a listed equity")
        if not portfolio_state.is_in_investable_universe(instrument.instrument_id):
            raise ValueError("existing holding is not eligible for new capital")
        return position

    @staticmethod
    def _validate_permanent_loss_comparisons(
        decision_input: MarginalDecisionInput,
    ) -> None:
        assessments = {
            item.alternative_id: item.risk_class
            for item in decision_input.permanent_loss_assessments
        }
        rank = {
            PermanentLossClass.LOW: 0,
            PermanentLossClass.MODERATE: 1,
            PermanentLossClass.HIGH: 2,
        }
        for comparison in decision_input.comparisons:
            first = assessments[comparison.first_alternative_id]
            second = assessments[comparison.second_alternative_id]
            if PermanentLossClass.UNKNOWN in {first, second}:
                expected = ComponentPreference.UNKNOWN
            elif first is second:
                expected = ComponentPreference.BALANCED
            elif rank[first] < rank[second]:
                expected = ComponentPreference.FIRST
            else:
                expected = ComponentPreference.SECOND
            component = next(
                item
                for item in comparison.components
                if item.dimension is TradeOffDimension.PERMANENT_LOSS
            )
            if component.preference is not expected:
                raise ValueError(
                    "pairwise permanent-loss component conflicts with ordinal assessments"
                )

    @staticmethod
    def _validate_alternative_exposures(
        current_exposure: PortfolioExposure,
        alternatives: tuple[PortfolioExposure, ...],
        *,
        expected_instrument_ids: set[str],
        capital: MonetaryAmount,
    ) -> dict[str, PortfolioExposure]:
        if len(alternatives) != len(expected_instrument_ids):
            raise ValueError("existing holding and core ETF each require one exposure view")
        by_instrument: dict[str, PortfolioExposure] = {}
        for exposure in alternatives:
            hypothetical = exposure.hypothetical_position
            if hypothetical is None or exposure.after is None:
                raise ValueError("alternative exposure requires a hypothetical after view")
            if hypothetical.instrument_id in by_instrument:
                raise ValueError("duplicate alternative exposure instrument")
            if hypothetical.amount != capital:
                raise ValueError("every alternative exposure must use the exact capital unit")
            if exposure.before != current_exposure.before:
                raise ValueError("alternative exposure must preserve the canonical current view")
            by_instrument[hypothetical.instrument_id] = exposure
        if set(by_instrument) != expected_instrument_ids:
            raise ValueError("alternative exposures must cover existing holding and core ETF")
        return by_instrument

    @staticmethod
    def _build_alternatives(
        portfolio_state: PortfolioState,
        opportunity: OpportunityState,
        decision_input: MarginalDecisionInput,
        existing_position: Position,
    ) -> tuple[CapitalAlternative, ...]:
        amount = decision_input.capital_unit.amount
        instruments = {item.instrument_id: item for item in portfolio_state.instruments}
        existing_instrument = instruments[existing_position.instrument_id]
        benchmark_id = portfolio_state.etf_eligibility_policy.benchmark_instrument_id
        benchmark = instruments[benchmark_id]
        return (
            CapitalAlternative(
                alternative_id=CANDIDATE_ALTERNATIVE_ID,
                kind=CapitalAlternativeKind.CANDIDATE_EQUITY,
                label=decision_input.candidate_instrument.name,
                amount=amount,
                rationale="Evaluate the verified standalone candidate for the disclosed amount.",
                instrument_id=decision_input.candidate_instrument.instrument_id,
                opportunity_id=opportunity.opportunity_id,
            ),
            CapitalAlternative(
                alternative_id=EXISTING_HOLDING_ALTERNATIVE_ID,
                kind=CapitalAlternativeKind.EXISTING_HOLDING,
                label=existing_instrument.name,
                amount=amount,
                rationale="Evaluate adding the same amount to one eligible existing holding.",
                instrument_id=existing_instrument.instrument_id,
                position_id=existing_position.position_id,
            ),
            CapitalAlternative(
                alternative_id=CORE_ETF_ALTERNATIVE_ID,
                kind=CapitalAlternativeKind.CORE_ETF,
                label=benchmark.name,
                amount=amount,
                rationale=(
                    "Evaluate the policy-selected diversified benchmark as active competition."
                ),
                instrument_id=benchmark.instrument_id,
            ),
            CapitalAlternative(
                alternative_id=INVESTMENT_CASH_ALTERNATIVE_ID,
                kind=CapitalAlternativeKind.INVESTMENT_CASH,
                label="Investment cash",
                amount=amount,
                rationale=(
                    "Preserve the unit as explicitly investable cash when no alternative wins."
                ),
            ),
        )

    @staticmethod
    def _candidate_profile(
        candidate: CandidateEquityInstrument,
        exposures: tuple[PortfolioExposure, ...],
    ) -> CompanyExposureProfile | None:
        profiles = {
            profile
            for exposure in exposures
            for profile in exposure.company_profiles
            if profile.company_subject_id == candidate.company_subject_id
        }
        if len(profiles) > 1:
            raise ValueError("candidate company has conflicting exposure profiles")
        return next(iter(profiles), None)

    def _build_candidate_fit(
        self,
        *,
        alternative: CapitalAlternative,
        candidate: CandidateEquityInstrument,
        profile: CompanyExposureProfile | None,
        portfolio_state: PortfolioStateReference,
        opportunity_state: OpportunityStateReference,
        base_exposure: PortfolioExposureReference,
        current_snapshot: ExposureSnapshot,
        current_exposure: PortfolioExposure,
        decision_input: MarginalDecisionInput,
        opportunity: OpportunityState,
    ) -> PortfolioFit:
        currency = alternative.amount.currency
        before_book = self._book(current_snapshot, currency)
        before_values, before_weights = self._book_components(before_book)
        after_values = dict(before_values)
        amount = alternative.amount.amount
        self._increment(
            after_values, FitExposureDimension.INSTRUMENT, candidate.instrument_id, amount
        )
        self._increment(
            after_values,
            FitExposureDimension.COMPANY,
            candidate.company_subject_id,
            amount,
        )
        missing: set[str] = set(current_exposure.missing_data)
        if profile is None:
            sector_id = "sector:unknown"
            geography_id = "geography:unknown"
            driver_ids: tuple[str, ...] = ("driver:unknown",)
            missing.add(
                "Candidate sector, geography, and economic-driver classifications are unknown."
            )
        else:
            sector_id = profile.sector.sector_id if profile.sector is not None else "sector:unknown"
            geography_id = (
                f"geography:{profile.geography.country_code.lower()}"
                if profile.geography is not None
                else "geography:unknown"
            )
            driver_ids = tuple(item.driver_id for item in profile.economic_drivers) or (
                "driver:unknown",
            )
            if profile.missing_reason is not None:
                missing.add(profile.missing_reason)
        self._increment(after_values, FitExposureDimension.SECTOR, sector_id, amount)
        self._increment(after_values, FitExposureDimension.GEOGRAPHY, geography_id, amount)
        for driver_id in driver_ids:
            self._increment(
                after_values,
                FitExposureDimension.ECONOMIC_DRIVER,
                driver_id,
                amount,
            )

        gross_before = self._gross(before_book)
        gross_after = canonical_decimal(gross_before + amount)
        after_weights = self._weights_from_values(after_values, gross_after)
        effect = FitCurrencyEffect(
            currency=currency,
            gross_value_before=MonetaryAmount(amount=gross_before, currency=currency),
            gross_value_after=MonetaryAmount(amount=gross_after, currency=currency),
            company_hhi_before=self._hhi(before_book),
            company_hhi_after=self._hhi_from_values(after_values, gross_after),
            weight_deltas=self._weight_deltas(before_weights, after_weights),
        )
        assumptions = {
            *current_exposure.assumptions,
            *decision_input.assumptions,
            "A prospective listed equity adds direct exposure to its canonical company.",
        }
        return self._make_fit(
            derivation_kind=FitDerivationKind.PROSPECTIVE_DIRECT_EQUITY,
            portfolio_state=portfolio_state,
            base_exposure=base_exposure,
            alternative_exposure=None,
            opportunity_state=opportunity_state,
            alternative=alternative,
            effect=effect,
            missing_data=tuple(
                sorted({*missing, *decision_input.missing_data, *opportunity.missing_data})
            ),
            conflicts=tuple(
                sorted(
                    {
                        *current_exposure.conflicts,
                        *decision_input.conflicts,
                        *opportunity.conflicts,
                    }
                )
            ),
            assumptions=tuple(sorted(assumptions)),
        )

    def _build_verified_exposure_fit(
        self,
        *,
        alternative: CapitalAlternative,
        portfolio_state: PortfolioStateReference,
        base_exposure: PortfolioExposureReference,
        current_exposure: PortfolioExposure,
        alternative_exposure: PortfolioExposure,
        decision_input: MarginalDecisionInput,
    ) -> PortfolioFit:
        currency = alternative.amount.currency
        before_book = self._book(current_exposure.before, currency)
        if alternative_exposure.after is None:
            raise ValueError("verified alternative exposure requires an after view")
        after_book = self._book(alternative_exposure.after, currency)
        gross_before = self._gross(before_book)
        gross_after = self._gross(after_book)
        if canonical_decimal(gross_before + alternative.amount.amount) != gross_after:
            raise ValueError("alternative exposure gross delta must equal the capital unit")
        _, before_weights = self._book_components(before_book)
        _, after_weights = self._book_components(after_book)
        effect = FitCurrencyEffect(
            currency=currency,
            gross_value_before=MonetaryAmount(amount=gross_before, currency=currency),
            gross_value_after=MonetaryAmount(amount=gross_after, currency=currency),
            company_hhi_before=self._hhi(before_book),
            company_hhi_after=self._hhi(after_book),
            weight_deltas=self._weight_deltas(before_weights, after_weights),
        )
        return self._make_fit(
            derivation_kind=FitDerivationKind.VERIFIED_PORTFOLIO_EXPOSURE,
            portfolio_state=portfolio_state,
            base_exposure=base_exposure,
            alternative_exposure=self._exposure_reference(alternative_exposure),
            opportunity_state=None,
            alternative=alternative,
            effect=effect,
            missing_data=tuple(
                sorted(
                    {
                        *current_exposure.missing_data,
                        *alternative_exposure.missing_data,
                        *decision_input.missing_data,
                    }
                )
            ),
            conflicts=tuple(
                sorted(
                    {
                        *current_exposure.conflicts,
                        *alternative_exposure.conflicts,
                        *decision_input.conflicts,
                    }
                )
            ),
            assumptions=tuple(
                sorted(
                    {
                        *current_exposure.assumptions,
                        *alternative_exposure.assumptions,
                        *decision_input.assumptions,
                    }
                )
            ),
        )

    def _build_cash_fit(
        self,
        *,
        alternative: CapitalAlternative,
        portfolio_state: PortfolioStateReference,
        base_exposure: PortfolioExposureReference,
        current_exposure: PortfolioExposure,
        decision_input: MarginalDecisionInput,
    ) -> PortfolioFit:
        currency = alternative.amount.currency
        before_book = self._book(current_exposure.before, currency)
        gross = self._gross(before_book)
        effect = FitCurrencyEffect(
            currency=currency,
            gross_value_before=MonetaryAmount(amount=gross, currency=currency),
            gross_value_after=MonetaryAmount(amount=gross, currency=currency),
            company_hhi_before=self._hhi(before_book),
            company_hhi_after=self._hhi(before_book),
            weight_deltas=(),
        )
        return self._make_fit(
            derivation_kind=FitDerivationKind.UNCHANGED_INVESTMENT_CASH,
            portfolio_state=portfolio_state,
            base_exposure=base_exposure,
            alternative_exposure=None,
            opportunity_state=None,
            alternative=alternative,
            effect=effect,
            missing_data=tuple(
                sorted({*current_exposure.missing_data, *decision_input.missing_data})
            ),
            conflicts=tuple(sorted({*current_exposure.conflicts, *decision_input.conflicts})),
            assumptions=tuple(
                sorted(
                    {
                        *current_exposure.assumptions,
                        *decision_input.assumptions,
                        "NO_ALLOCATION preserves the unit in its declared investment-cash role.",
                    }
                )
            ),
        )

    @classmethod
    def _make_fit(
        cls,
        *,
        derivation_kind: FitDerivationKind,
        portfolio_state: PortfolioStateReference,
        base_exposure: PortfolioExposureReference,
        alternative_exposure: PortfolioExposureReference | None,
        opportunity_state: OpportunityStateReference | None,
        alternative: CapitalAlternative,
        effect: FitCurrencyEffect,
        missing_data: tuple[str, ...],
        conflicts: tuple[str, ...],
        assumptions: tuple[str, ...],
    ) -> PortfolioFit:
        payload = {
            "method_version": PORTFOLIO_FIT_METHOD_VERSION,
            "derivation_kind": derivation_kind.value,
            "portfolio_state": portfolio_state.model_dump(mode="json"),
            "base_exposure": base_exposure.model_dump(mode="json"),
            "alternative_exposure": (
                alternative_exposure.model_dump(mode="json")
                if alternative_exposure is not None
                else None
            ),
            "opportunity_state": (
                opportunity_state.model_dump(mode="json") if opportunity_state is not None else None
            ),
            "alternative": alternative.model_dump(mode="json"),
            "effect": effect.model_dump(mode="json"),
            "missing_data": missing_data,
            "conflicts": conflicts,
            "assumptions": assumptions,
        }
        fingerprint = cls._fingerprint(payload)
        return PortfolioFit(
            fit_id=uuid5(
                NAMESPACE_URL,
                f"asymmetric-insight-engine:portfolio-fit:{fingerprint}",
            ),
            input_fingerprint=fingerprint,
            knowledge_boundary=portfolio_state.knowledge_boundary,
            method_version=PORTFOLIO_FIT_METHOD_VERSION,
            derivation_kind=derivation_kind,
            portfolio_state=portfolio_state,
            base_exposure=base_exposure,
            alternative_exposure=alternative_exposure,
            opportunity_state=opportunity_state,
            alternative=alternative,
            effect=effect,
            missing_data=missing_data,
            conflicts=conflicts,
            assumptions=assumptions,
        )

    @staticmethod
    def _book(snapshot: ExposureSnapshot, currency: str) -> CurrencyExposureBook | None:
        return next((item for item in snapshot.currency_books if item.currency == currency), None)

    @staticmethod
    def _gross(book: CurrencyExposureBook | None) -> Decimal:
        return Decimal(0) if book is None else book.gross_position_value.amount

    @staticmethod
    def _hhi(book: CurrencyExposureBook | None) -> HHIBounds:
        return (
            HHIBounds(lower_bound=Decimal(0), upper_bound=Decimal(0))
            if book is None
            else book.company_hhi
        )

    @classmethod
    def _book_components(
        cls,
        book: CurrencyExposureBook | None,
    ) -> tuple[
        dict[tuple[FitExposureDimension, str], Decimal],
        dict[tuple[FitExposureDimension, str], Decimal],
    ]:
        if book is None:
            return {}, {}
        values: dict[tuple[FitExposureDimension, str], Decimal] = {}
        weights: dict[tuple[FitExposureDimension, str], Decimal] = {}

        def add(
            dimension: FitExposureDimension, item_id: str, value: Decimal, weight: Decimal
        ) -> None:
            values[(dimension, item_id)] = value
            weights[(dimension, item_id)] = weight

        for instrument_exposure in book.instrument_exposures:
            add(
                FitExposureDimension.INSTRUMENT,
                instrument_exposure.instrument_id,
                instrument_exposure.value.amount,
                instrument_exposure.weight,
            )
        for company_exposure in book.company_exposures:
            add(
                FitExposureDimension.COMPANY,
                company_exposure.company_subject_id,
                company_exposure.total_value.amount,
                company_exposure.weight,
            )
        for sector_exposure in book.sector_exposures:
            add(
                FitExposureDimension.SECTOR,
                sector_exposure.category_id,
                sector_exposure.value.amount,
                sector_exposure.weight,
            )
        for geography_exposure in book.geography_exposures:
            add(
                FitExposureDimension.GEOGRAPHY,
                geography_exposure.category_id,
                geography_exposure.value.amount,
                geography_exposure.weight,
            )
        for driver_exposure in book.economic_driver_exposures:
            add(
                FitExposureDimension.ECONOMIC_DRIVER,
                driver_exposure.driver_id,
                driver_exposure.value.amount,
                driver_exposure.weight,
            )
        add(
            FitExposureDimension.UNRESOLVED,
            _UNRESOLVED_COMPONENT_ID,
            book.unresolved_exposure.value.amount,
            book.unresolved_exposure.weight,
        )
        return values, weights

    @staticmethod
    def _increment(
        values: dict[tuple[FitExposureDimension, str], Decimal],
        dimension: FitExposureDimension,
        component_id: str,
        amount: Decimal,
    ) -> None:
        key = (dimension, component_id)
        values[key] = canonical_decimal(values.get(key, Decimal(0)) + amount)

    @classmethod
    def _weights_from_values(
        cls,
        values: dict[tuple[FitExposureDimension, str], Decimal],
        gross: Decimal,
    ) -> dict[tuple[FitExposureDimension, str], Decimal]:
        if gross <= 0:
            return {}
        return {key: cls._ratio(value, gross) for key, value in values.items()}

    @staticmethod
    def _hhi_from_values(
        values: dict[tuple[FitExposureDimension, str], Decimal],
        gross: Decimal,
    ) -> HHIBounds:
        if gross <= 0:
            return HHIBounds(lower_bound=Decimal(0), upper_bound=Decimal(0))
        company_values = (
            value
            for (dimension, _), value in values.items()
            if dimension is FitExposureDimension.COMPANY
        )
        lower = sum(((value / gross) ** 2 for value in company_values), Decimal(0))
        unresolved = values.get(
            (FitExposureDimension.UNRESOLVED, _UNRESOLVED_COMPONENT_ID),
            Decimal(0),
        )
        upper = lower + (unresolved / gross) ** 2
        return HHIBounds(
            lower_bound=BuildMarginalDecision._quantize_ratio(lower),
            upper_bound=BuildMarginalDecision._quantize_ratio(upper),
        )

    @staticmethod
    def _weight_deltas(
        before: dict[tuple[FitExposureDimension, str], Decimal],
        after: dict[tuple[FitExposureDimension, str], Decimal],
    ) -> tuple[WeightDelta, ...]:
        deltas = []
        for dimension, component_id in sorted(
            set(before) | set(after),
            key=lambda item: (item[0].value, item[1]),
        ):
            before_weight = before.get((dimension, component_id), Decimal(0))
            after_weight = after.get((dimension, component_id), Decimal(0))
            if before_weight == after_weight:
                continue
            deltas.append(
                WeightDelta(
                    dimension=dimension,
                    component_id=component_id,
                    before_weight=before_weight,
                    after_weight=after_weight,
                    is_non_additive=dimension is FitExposureDimension.ECONOMIC_DRIVER,
                )
            )
        return tuple(deltas)

    @staticmethod
    def _dominance_winner(
        comparisons: tuple[PairwiseCapitalComparison, ...],
    ) -> str | None:
        wins: dict[str, set[str]] = {
            alternative_id: set()
            for alternative_id in (
                CANDIDATE_ALTERNATIVE_ID,
                EXISTING_HOLDING_ALTERNATIVE_ID,
                CORE_ETF_ALTERNATIVE_ID,
                INVESTMENT_CASH_ALTERNATIVE_ID,
            )
        }
        for comparison in comparisons:
            if comparison.conclusion is PairwiseConclusion.FIRST:
                wins[comparison.first_alternative_id].add(comparison.second_alternative_id)
            elif comparison.conclusion is PairwiseConclusion.SECOND:
                wins[comparison.second_alternative_id].add(comparison.first_alternative_id)
        winners = [alternative_id for alternative_id, beaten in wins.items() if len(beaten) == 3]
        return winners[0] if len(winners) == 1 else None

    @staticmethod
    def _state_reference(state: PortfolioState) -> PortfolioStateReference:
        return PortfolioStateReference(
            portfolio_state_id=state.portfolio_state_id,
            portfolio_id=state.portfolio_id,
            input_fingerprint=state.input_fingerprint,
            knowledge_boundary=state.knowledge_boundary,
        )

    @staticmethod
    def _opportunity_reference(opportunity: OpportunityState) -> OpportunityStateReference:
        return OpportunityStateReference(
            opportunity_id=opportunity.opportunity_id,
            candidate_id=opportunity.candidate_id,
            input_fingerprint=opportunity.input_fingerprint,
            knowledge_boundary=opportunity.knowledge_boundary,
        )

    @staticmethod
    def _exposure_reference(exposure: PortfolioExposure) -> PortfolioExposureReference:
        return PortfolioExposureReference(
            exposure_id=exposure.exposure_id,
            input_fingerprint=exposure.input_fingerprint,
            knowledge_boundary=exposure.knowledge_boundary,
        )

    @staticmethod
    def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
        if denominator <= 0:
            return Decimal(0)
        return BuildMarginalDecision._quantize_ratio(numerator / denominator)

    @staticmethod
    def _quantize_ratio(value: Decimal) -> Decimal:
        return canonical_decimal(value.quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_EVEN))

    @staticmethod
    def _fingerprint(payload: dict[str, Any]) -> str:
        canonical_json = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return sha256(canonical_json).hexdigest()


class RecordPositionHold:
    """Record HOLD without allocating, selling, replacing, or staging a trade."""

    def __init__(
        self,
        *,
        state_builder: BuildPortfolioState | None = None,
        exposure_builder: BuildPortfolioExposure | None = None,
    ) -> None:
        self._state_builder = state_builder or BuildPortfolioState()
        self._exposure_builder = exposure_builder or BuildPortfolioExposure(
            state_builder=self._state_builder
        )

    def execute(
        self,
        *,
        portfolio_state: PortfolioState,
        current_exposure: PortfolioExposure,
        review_input: PositionReviewInput,
    ) -> PositionReview:
        state = self._state_builder.verify(portfolio_state)
        exposure = self._exposure_builder.verify(state, current_exposure)
        if exposure.hypothetical_position is not None or exposure.after is not None:
            raise ValueError("HOLD review requires the current Portfolio Exposure only")
        if review_input.knowledge_boundary != state.knowledge_boundary:
            raise ValueError("HOLD review must preserve the Portfolio State boundary")
        if review_input.method_version != POSITION_REVIEW_METHOD_VERSION:
            raise ValueError("HOLD review uses an unsupported method version")
        if review_input.position_id not in {item.position_id for item in state.positions}:
            raise ValueError("HOLD review references an unknown existing position")
        values = review_input.model_dump(mode="python")
        for field_name in ("missing_data", "conflicts", "assumptions"):
            values[field_name] = tuple(sorted(getattr(review_input, field_name)))
        canonical_input = PositionReviewInput.model_validate(values)
        state_reference = BuildMarginalDecision._state_reference(state)
        exposure_reference = BuildMarginalDecision._exposure_reference(exposure)
        fingerprint = BuildMarginalDecision._fingerprint(
            {
                "portfolio_state": state_reference.model_dump(mode="json"),
                "base_exposure": exposure_reference.model_dump(mode="json"),
                "review_input": canonical_input.model_dump(mode="json"),
            }
        )
        return PositionReview.model_validate(
            {
                **canonical_input.model_dump(mode="python"),
                "review_id": uuid5(
                    NAMESPACE_URL,
                    f"asymmetric-insight-engine:position-review:{fingerprint}",
                ),
                "input_fingerprint": fingerprint,
                "portfolio_state": state_reference,
                "base_exposure": exposure_reference,
                "outcome": PositionReviewOutcome.HOLD,
            }
        )

    def verify(
        self,
        *,
        portfolio_state: PortfolioState,
        current_exposure: PortfolioExposure,
        review: PositionReview,
    ) -> PositionReview:
        input_values = {
            field_name: getattr(review, field_name)
            for field_name in PositionReviewInput.model_fields
        }
        rebuilt = self.execute(
            portfolio_state=portfolio_state,
            current_exposure=current_exposure,
            review_input=PositionReviewInput.model_validate(input_values),
        )
        if rebuilt != review:
            raise PositionReviewIntegrityError(
                "Position HOLD review does not match canonical replay"
            )
        return review
