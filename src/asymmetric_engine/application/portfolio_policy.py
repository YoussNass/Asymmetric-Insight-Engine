"""Apply Chapter 6C2 owner policy and explicit after-friction replacement."""

from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from asymmetric_engine.application.marginal_decision import (
    BuildMarginalDecision,
    MarginalDecisionResult,
)
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
    POLICY_CONSTRAINED_DECISION_METHOD_VERSION,
    AlternativePolicyBlock,
    FitExposureDimension,
    FrictionEstimateStatus,
    FundingPriority,
    LiquidityStatus,
    OwnerPortfolioPolicy,
    OwnerPortfolioPolicyInput,
    OwnerPortfolioPolicyReference,
    PairwiseCapitalComparison,
    PairwiseConclusion,
    PolicyConstrainedMarginalDecision,
    PolicyDecisionBasis,
    PolicyDecisionOutcome,
    PortfolioExposure,
    PortfolioExposureReference,
    PortfolioFit,
    PortfolioState,
    PortfolioStateReference,
    RatioConstraintKind,
    ReplacementDecision,
    ReplacementDecisionBasis,
    ReplacementDecisionInput,
    ReplacementOutcome,
    ReplacementPreference,
    ReplacementTargetKind,
)
from asymmetric_engine.domain.portfolio.models import InstrumentType, Position


class PortfolioPolicyIntegrityError(ValueError):
    """A policy or policy-constrained decision no longer replays canonically."""


class ReplacementDecisionIntegrityError(ValueError):
    """A replacement decision no longer matches its canonical verified inputs."""


class BuildOwnerPortfolioPolicy:
    """Content-address explicit owner constraints without creating a sizing model."""

    @classmethod
    def execute(cls, policy_input: OwnerPortfolioPolicyInput) -> OwnerPortfolioPolicy:
        canonical_input = cls._canonicalize_input(policy_input)
        fingerprint = cls._fingerprint(canonical_input.model_dump(mode="json"))
        return OwnerPortfolioPolicy.model_validate(
            {
                **canonical_input.model_dump(mode="python"),
                "policy_id": uuid5(
                    NAMESPACE_URL,
                    f"asymmetric-insight-engine:owner-portfolio-policy:{fingerprint}",
                ),
                "input_fingerprint": fingerprint,
            }
        )

    @classmethod
    def verify(cls, policy: OwnerPortfolioPolicy) -> OwnerPortfolioPolicy:
        input_values = {
            field_name: getattr(policy, field_name)
            for field_name in OwnerPortfolioPolicyInput.model_fields
        }
        rebuilt = cls.execute(OwnerPortfolioPolicyInput.model_validate(input_values))
        if rebuilt != policy:
            raise PortfolioPolicyIntegrityError(
                "Owner Portfolio Policy does not match canonical replay"
            )
        return policy

    @staticmethod
    def _canonicalize_input(policy_input: OwnerPortfolioPolicyInput) -> OwnerPortfolioPolicyInput:
        values: dict[str, Any] = policy_input.model_dump(mode="python")
        values["ratio_constraints"] = tuple(
            sorted(policy_input.ratio_constraints, key=lambda item: item.kind.value)
        )
        values["position_policies"] = tuple(
            sorted(
                (
                    item.model_copy(
                        update={"change_conditions": tuple(sorted(item.change_conditions))}
                    )
                    for item in policy_input.position_policies
                ),
                key=lambda item: item.position_id,
            )
        )
        values["assumptions"] = tuple(sorted(policy_input.assumptions))
        return OwnerPortfolioPolicyInput.model_validate(values)

    @staticmethod
    def _fingerprint(payload: Any) -> str:
        canonical_json = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return sha256(canonical_json).hexdigest()


class ApplyPortfolioPolicy:
    """Filter a verified 6C1 decision through explicit owner constraints."""

    def __init__(
        self,
        *,
        decision_builder: BuildMarginalDecision,
        policy_builder: BuildOwnerPortfolioPolicy | None = None,
    ) -> None:
        self._decision_builder = decision_builder
        self._policy_builder = policy_builder or BuildOwnerPortfolioPolicy()

    def execute(
        self,
        *,
        portfolio_state: PortfolioState,
        opportunity_state: OpportunityState,
        current_exposure: PortfolioExposure,
        alternative_exposures: tuple[PortfolioExposure, ...],
        marginal_result: MarginalDecisionResult,
        policy: OwnerPortfolioPolicy,
    ) -> PolicyConstrainedMarginalDecision:
        verified_result = self._decision_builder.verify(
            portfolio_state=portfolio_state,
            opportunity_state=opportunity_state,
            current_exposure=current_exposure,
            alternative_exposures=alternative_exposures,
            result=marginal_result,
        )
        verified_policy = self._policy_builder.verify(policy)
        decision = verified_result.decision
        if verified_policy.knowledge_boundary != decision.knowledge_boundary:
            raise ValueError("6C2 owner policy must share the 6C1 knowledge boundary")
        self._validate_position_policies(portfolio_state, verified_policy)

        fit_by_id = {item.alternative.alternative_id: item for item in verified_result.fits}
        alternative_by_id = {item.alternative_id: item for item in decision.alternatives}
        blocks: list[AlternativePolicyBlock] = []
        eligible = {INVESTMENT_CASH_ALTERNATIVE_ID}
        for alternative_id in (
            CANDIDATE_ALTERNATIVE_ID,
            EXISTING_HOLDING_ALTERNATIVE_ID,
            CORE_ETF_ALTERNATIVE_ID,
        ):
            reasons = self._block_reasons(
                alternative_id=alternative_id,
                alternative=alternative_by_id[alternative_id],
                fit=fit_by_id[alternative_id],
                policy=verified_policy,
            )
            if reasons:
                blocks.append(
                    AlternativePolicyBlock(
                        alternative_id=alternative_id,
                        reasons=tuple(sorted(reasons)),
                    )
                )
            else:
                eligible.add(alternative_id)

        winner = self._restricted_dominance_winner(
            decision.comparisons,
            eligible=frozenset(eligible),
        )
        if winner is not None and winner != INVESTMENT_CASH_ALTERNATIVE_ID:
            outcome = PolicyDecisionOutcome.ALLOCATE
            selected = winner
            basis = PolicyDecisionBasis.POLICY_FILTERED_DOMINANCE
        else:
            outcome = PolicyDecisionOutcome.NO_ALLOCATION
            selected = INVESTMENT_CASH_ALTERNATIVE_ID
            basis = PolicyDecisionBasis.CONSERVATIVE_CASH_DEFAULT

        policy_reference = self._policy_reference(verified_policy)
        eligible_ids = tuple(sorted(eligible))
        blocked = tuple(sorted(blocks, key=lambda item: item.alternative_id))
        material = {
            "method_version": POLICY_CONSTRAINED_DECISION_METHOD_VERSION,
            "source_decision_id": str(decision.decision_id),
            "source_decision_fingerprint": decision.input_fingerprint,
            "policy": policy_reference.model_dump(mode="json"),
            "eligible_alternative_ids": eligible_ids,
            "blocked_alternatives": [item.model_dump(mode="json") for item in blocked],
            "outcome": outcome.value,
            "selected_alternative_id": selected,
            "dominance_winner_id": winner,
            "decision_basis": basis.value,
        }
        fingerprint = BuildOwnerPortfolioPolicy._fingerprint(material)
        return PolicyConstrainedMarginalDecision(
            policy_decision_id=uuid5(
                NAMESPACE_URL,
                f"asymmetric-insight-engine:policy-constrained-decision:{fingerprint}",
            ),
            input_fingerprint=fingerprint,
            knowledge_boundary=decision.knowledge_boundary,
            source_decision_id=decision.decision_id,
            source_decision_fingerprint=decision.input_fingerprint,
            policy=policy_reference,
            eligible_alternative_ids=eligible_ids,
            blocked_alternatives=blocked,
            outcome=outcome,
            selected_alternative_id=selected,
            dominance_winner_id=winner,
            decision_basis=basis,
        )

    def verify(
        self,
        *,
        portfolio_state: PortfolioState,
        opportunity_state: OpportunityState,
        current_exposure: PortfolioExposure,
        alternative_exposures: tuple[PortfolioExposure, ...],
        marginal_result: MarginalDecisionResult,
        policy: OwnerPortfolioPolicy,
        policy_decision: PolicyConstrainedMarginalDecision,
    ) -> PolicyConstrainedMarginalDecision:
        rebuilt = self.execute(
            portfolio_state=portfolio_state,
            opportunity_state=opportunity_state,
            current_exposure=current_exposure,
            alternative_exposures=alternative_exposures,
            marginal_result=marginal_result,
            policy=policy,
        )
        if rebuilt != policy_decision:
            raise PortfolioPolicyIntegrityError(
                "Policy-constrained marginal decision does not match canonical replay"
            )
        return policy_decision

    @staticmethod
    def _validate_position_policies(
        state: PortfolioState,
        policy: OwnerPortfolioPolicy,
    ) -> None:
        positions = {item.position_id: item for item in state.positions}
        for position_policy in policy.position_policies:
            position = positions.get(position_policy.position_id)
            if position is None:
                raise ValueError("owner policy references an unknown Portfolio State position")
            if (
                position_policy.recovered_proceeds is not None
                and position_policy.recovered_proceeds.currency != position.current_value.currency
            ):
                raise ValueError("Runner recovered proceeds must use the position native currency")

    @staticmethod
    def _block_reasons(
        *,
        alternative_id: str,
        alternative: Any,
        fit: PortfolioFit,
        policy: OwnerPortfolioPolicy,
    ) -> set[str]:
        reasons: set[str] = set()
        if policy.max_capital_unit is not None:
            if policy.max_capital_unit.currency != alternative.amount.currency:
                raise ValueError("owner max capital unit must use the evaluated capital currency")
            if alternative.amount.amount > policy.max_capital_unit.amount:
                reasons.add(
                    "Evaluated capital unit exceeds the owner maximum; 6C2 does not resize it."
                )
        if alternative_id == EXISTING_HOLDING_ALTERNATIVE_ID:
            position_policy = next(
                (
                    item
                    for item in policy.position_policies
                    if item.position_id == alternative.position_id
                ),
                None,
            )
            if position_policy is not None and not position_policy.allows_new_capital:
                reasons.add("Existing position is explicitly classified as zero-new-capital state.")

        for constraint in policy.ratio_constraints:
            observed = ApplyPortfolioPolicy._fit_observation(fit, constraint.kind)
            if observed is None:
                reasons.add(
                    "Owner constraint "
                    f"{constraint.kind.value} cannot be evaluated from Portfolio Fit."
                )
            elif observed > constraint.maximum:
                reasons.add(
                    f"Owner constraint {constraint.kind.value} would be exceeded after allocation."
                )
        return reasons

    @staticmethod
    def _fit_observation(fit: PortfolioFit, kind: RatioConstraintKind) -> Decimal | None:
        if kind is RatioConstraintKind.MAX_COMPANY_HHI_UPPER_BOUND:
            return fit.effect.company_hhi_after.upper_bound
        dimension = (
            FitExposureDimension.COMPANY
            if kind is RatioConstraintKind.MAX_COMPANY_WEIGHT
            else FitExposureDimension.ECONOMIC_DRIVER
        )
        weights = [
            item.after_weight for item in fit.effect.weight_deltas if item.dimension is dimension
        ]
        return max(weights) if weights else None

    @staticmethod
    def _restricted_dominance_winner(
        comparisons: tuple[PairwiseCapitalComparison, ...],
        *,
        eligible: frozenset[str],
    ) -> str | None:
        wins: dict[str, set[str]] = {alternative_id: set() for alternative_id in eligible}
        for comparison in comparisons:
            pair = {comparison.first_alternative_id, comparison.second_alternative_id}
            if not pair.issubset(eligible):
                continue
            if comparison.conclusion is PairwiseConclusion.FIRST:
                wins[comparison.first_alternative_id].add(comparison.second_alternative_id)
            elif comparison.conclusion is PairwiseConclusion.SECOND:
                wins[comparison.second_alternative_id].add(comparison.first_alternative_id)
        required_wins = len(eligible) - 1
        winners = [
            alternative_id
            for alternative_id, beaten in wins.items()
            if len(beaten) == required_wins
        ]
        return winners[0] if len(winners) == 1 else None

    @staticmethod
    def _policy_reference(policy: OwnerPortfolioPolicy) -> OwnerPortfolioPolicyReference:
        return OwnerPortfolioPolicyReference(
            policy_id=policy.policy_id,
            input_fingerprint=policy.input_fingerprint,
            knowledge_boundary=policy.knowledge_boundary,
        )


class BuildReplacementDecision:
    """Decide one explicit source-to-target replacement after visible switching friction."""

    def __init__(
        self,
        *,
        state_builder: BuildPortfolioState | None = None,
        exposure_builder: BuildPortfolioExposure | None = None,
        policy_builder: BuildOwnerPortfolioPolicy | None = None,
        opportunity_builder: BuildOpportunityState | None = None,
    ) -> None:
        self._state_builder = state_builder or BuildPortfolioState()
        self._exposure_builder = exposure_builder or BuildPortfolioExposure(
            state_builder=self._state_builder
        )
        self._policy_builder = policy_builder or BuildOwnerPortfolioPolicy()
        self._opportunity_builder = opportunity_builder

    def execute(
        self,
        *,
        portfolio_state: PortfolioState,
        current_exposure: PortfolioExposure,
        policy: OwnerPortfolioPolicy,
        decision_input: ReplacementDecisionInput,
        opportunity_state: OpportunityState | None = None,
    ) -> ReplacementDecision:
        state = self._state_builder.verify(portfolio_state)
        exposure = self._exposure_builder.verify(state, current_exposure)
        owner_policy = self._policy_builder.verify(policy)
        if exposure.hypothetical_position is not None or exposure.after is not None:
            raise ValueError("replacement requires the current Portfolio Exposure only")
        if (
            len(
                {
                    state.knowledge_boundary,
                    exposure.knowledge_boundary,
                    owner_policy.knowledge_boundary,
                    decision_input.knowledge_boundary,
                }
            )
            != 1
        ):
            raise ValueError("Chapter 6C2 replacement requires one knowledge boundary")
        if owner_policy.funding_priority is not FundingPriority.NEW_CAPITAL_FIRST:
            raise ValueError("Chapter 6C2 admits new-capital-first funding only")
        ApplyPortfolioPolicy._validate_position_policies(state, owner_policy)
        canonical_input = self._canonicalize_input(decision_input)
        source = self._source_position(state, canonical_input)
        if canonical_input.target.instrument_id == source.instrument_id:
            raise ValueError("replacement target instrument must differ from source instrument")
        currency = source.current_value.currency
        if canonical_input.gross_sale_amount.currency != currency:
            raise ValueError("replacement sale amount must use the source position currency")
        if canonical_input.gross_sale_amount.amount > source.current_value.amount:
            raise ValueError("replacement sale amount cannot exceed source current market value")
        if canonical_input.target.native_currency != currency:
            raise ValueError("replacement target must use the source position currency")

        verified_opportunity = self._validate_target(
            state=state,
            decision_input=canonical_input,
            opportunity_state=opportunity_state,
        )
        self._validate_constraint_observations(owner_policy, canonical_input)
        total_friction, net_amount = self._friction_amounts(canonical_input, currency)
        available_new_capital = self._available_investable_cash(state, currency)
        source_account = next(
            item for item in state.accounts if item.account_id == source.account_id
        )
        target_wins_pre_friction = self._target_wins(
            canonical_input.pre_friction_comparison,
            target_id=canonical_input.target.target_id,
        )
        policy_block = self._replacement_policy_block(
            state=state,
            owner_policy=owner_policy,
            decision_input=canonical_input,
            net_amount=net_amount,
        )

        if total_friction is None or net_amount is None:
            outcome = ReplacementOutcome.HOLD
            basis = ReplacementDecisionBasis.FRICTION_UNKNOWN
        elif policy_block:
            outcome = ReplacementOutcome.HOLD
            basis = ReplacementDecisionBasis.POLICY_BLOCK
        elif available_new_capital.amount >= net_amount.amount:
            outcome = ReplacementOutcome.HOLD
            basis = ReplacementDecisionBasis.NEW_CAPITAL_FIRST
        elif canonical_input.friction.liquidity.status is LiquidityStatus.UNKNOWN:
            outcome = ReplacementOutcome.HOLD
            basis = ReplacementDecisionBasis.LIQUIDITY_UNRESOLVED
        elif (
            not target_wins_pre_friction
            or canonical_input.after_friction_preference is not ReplacementPreference.TARGET
        ):
            outcome = ReplacementOutcome.HOLD
            basis = ReplacementDecisionBasis.SOURCE_NOT_OUTCLASSED
        else:
            outcome = ReplacementOutcome.REPLACE
            basis = ReplacementDecisionBasis.AFTER_FRICTION_TARGET_DOMINANCE

        state_reference = PortfolioStateReference(
            portfolio_state_id=state.portfolio_state_id,
            portfolio_id=state.portfolio_id,
            input_fingerprint=state.input_fingerprint,
            knowledge_boundary=state.knowledge_boundary,
        )
        exposure_reference = PortfolioExposureReference(
            exposure_id=exposure.exposure_id,
            input_fingerprint=exposure.input_fingerprint,
            knowledge_boundary=exposure.knowledge_boundary,
        )
        policy_reference = ApplyPortfolioPolicy._policy_reference(owner_policy)
        opportunity_reference = (
            BuildMarginalDecision._opportunity_reference(verified_opportunity)
            if verified_opportunity is not None
            else None
        )
        material = {
            "portfolio_state": state_reference.model_dump(mode="json"),
            "base_exposure": exposure_reference.model_dump(mode="json"),
            "policy": policy_reference.model_dump(mode="json"),
            "opportunity_state": (
                opportunity_reference.model_dump(mode="json")
                if opportunity_reference is not None
                else None
            ),
            "decision_input": canonical_input.model_dump(mode="json"),
            "source_tax_treatment": source_account.tax_metadata.treatment.value,
            "total_switching_friction": (
                total_friction.model_dump(mode="json") if total_friction is not None else None
            ),
            "net_redeployable_amount": (
                net_amount.model_dump(mode="json") if net_amount is not None else None
            ),
            "available_new_capital": available_new_capital.model_dump(mode="json"),
            "outcome": outcome.value,
            "decision_basis": basis.value,
        }
        fingerprint = BuildOwnerPortfolioPolicy._fingerprint(material)
        return ReplacementDecision.model_validate(
            {
                **canonical_input.model_dump(mode="python"),
                "replacement_decision_id": uuid5(
                    NAMESPACE_URL,
                    f"asymmetric-insight-engine:replacement-decision:{fingerprint}",
                ),
                "input_fingerprint": fingerprint,
                "portfolio_state": state_reference,
                "base_exposure": exposure_reference,
                "policy": policy_reference,
                "opportunity_state": opportunity_reference,
                "source_tax_treatment": source_account.tax_metadata.treatment,
                "total_switching_friction": total_friction,
                "net_redeployable_amount": net_amount,
                "available_new_capital": available_new_capital,
                "outcome": outcome,
                "decision_basis": basis,
            }
        )

    def verify(
        self,
        *,
        portfolio_state: PortfolioState,
        current_exposure: PortfolioExposure,
        policy: OwnerPortfolioPolicy,
        decision: ReplacementDecision,
        opportunity_state: OpportunityState | None = None,
    ) -> ReplacementDecision:
        input_values = {
            field_name: getattr(decision, field_name)
            for field_name in ReplacementDecisionInput.model_fields
        }
        rebuilt = self.execute(
            portfolio_state=portfolio_state,
            current_exposure=current_exposure,
            policy=policy,
            decision_input=ReplacementDecisionInput.model_validate(input_values),
            opportunity_state=opportunity_state,
        )
        if rebuilt != decision:
            raise ReplacementDecisionIntegrityError(
                "Replacement Decision does not match canonical replay"
            )
        return decision

    @staticmethod
    def _canonicalize_input(
        decision_input: ReplacementDecisionInput,
    ) -> ReplacementDecisionInput:
        values: dict[str, Any] = decision_input.model_dump(mode="python")
        values["pre_friction_comparison"] = BuildMarginalDecision._canonicalize_comparison(
            decision_input.pre_friction_comparison
        )
        values["friction"] = decision_input.friction.model_copy(
            update={
                "costs": tuple(
                    sorted(
                        (
                            item.model_copy(
                                update={"missing_data": tuple(sorted(item.missing_data))}
                            )
                            for item in decision_input.friction.costs
                        ),
                        key=lambda item: item.kind.value,
                    )
                ),
                "liquidity": decision_input.friction.liquidity.model_copy(
                    update={
                        "missing_data": tuple(
                            sorted(decision_input.friction.liquidity.missing_data)
                        )
                    }
                ),
            }
        )
        values["constraint_observations"] = tuple(
            sorted(decision_input.constraint_observations, key=lambda item: item.kind.value)
        )
        for field_name in ("missing_data", "conflicts", "assumptions"):
            values[field_name] = tuple(sorted(getattr(decision_input, field_name)))
        return ReplacementDecisionInput.model_validate(values)

    @staticmethod
    def _source_position(
        state: PortfolioState,
        decision_input: ReplacementDecisionInput,
    ) -> Position:
        source = next(
            (
                item
                for item in state.positions
                if item.position_id == decision_input.source_position_id
            ),
            None,
        )
        if source is None:
            raise ValueError("replacement references an unknown source position")
        return source

    def _validate_target(
        self,
        *,
        state: PortfolioState,
        decision_input: ReplacementDecisionInput,
        opportunity_state: OpportunityState | None,
    ) -> OpportunityState | None:
        target = decision_input.target
        instruments = {item.instrument_id: item for item in state.instruments}
        positions = {item.position_id: item for item in state.positions}
        if target.kind is ReplacementTargetKind.CORE_ETF:
            if opportunity_state is not None:
                raise ValueError("core ETF replacement cannot consume Opportunity State")
            if target.instrument_id != state.etf_eligibility_policy.benchmark_instrument_id:
                raise ValueError("core ETF replacement must use the policy benchmark")
            instrument = instruments[target.instrument_id]
            if instrument.native_currency != target.native_currency:
                raise ValueError("replacement target currency must match the core ETF")
            return None
        if target.kind is ReplacementTargetKind.EXISTING_HOLDING:
            if opportunity_state is not None:
                raise ValueError("existing replacement target cannot consume Opportunity State")
            position = positions.get(target.position_id or "")
            if position is None or position.position_id == decision_input.source_position_id:
                raise ValueError("replacement existing target must be a different held position")
            if position.instrument_id != target.instrument_id:
                raise ValueError("replacement target position does not match target instrument")
            instrument = instruments[target.instrument_id]
            if instrument.instrument_type is not InstrumentType.LISTED_EQUITY:
                raise ValueError("existing replacement target must be a listed equity")
            if not state.is_in_investable_universe(instrument.instrument_id):
                raise ValueError("existing replacement target is not eligible for new capital")
            if instrument.native_currency != target.native_currency:
                raise ValueError("replacement target currency must match the held instrument")
            return None

        if opportunity_state is None or self._opportunity_builder is None:
            raise ValueError("candidate replacement requires a verifiable Opportunity State")
        opportunity = self._opportunity_builder.verify(opportunity_state)
        candidate = decision_input.candidate_instrument
        if candidate is None:
            raise ValueError("candidate replacement requires candidate instrument details")
        if opportunity.status is not OpportunityStatus.READY_FOR_PORTFOLIO_REVIEW:
            raise ValueError("candidate replacement Opportunity is not ready for Portfolio review")
        if target.opportunity_id != opportunity.opportunity_id:
            raise ValueError("replacement target must reference the verified Opportunity")
        if candidate.company_subject_id != opportunity.candidate_id:
            raise ValueError("replacement candidate must map to the Opportunity company")
        if candidate.instrument_id != target.instrument_id:
            raise ValueError("replacement candidate must match the target instrument")
        if candidate.native_currency != target.native_currency:
            raise ValueError("replacement candidate currency must match the target")
        if candidate.instrument_id in instruments:
            raise ValueError("prospective replacement candidate cannot already be Portfolio State")
        fact = next(
            (
                item
                for item in opportunity.financial_facts
                if item.fact_id == candidate.reference_price_fact_id
            ),
            None,
        )
        if fact is None:
            raise ValueError("replacement candidate price fact is absent from Underwriting")
        if (
            fact.metric is not FinancialMetric.REFERENCE_SHARE_PRICE
            or fact.basis is not FinancialFactBasis.MARKET_OBSERVED
        ):
            raise ValueError("replacement candidate price must be market observed")
        if (
            fact.value != candidate.reference_price.amount
            or fact.currency != candidate.reference_price.currency
            or fact.period.end_date != candidate.reference_price_date
        ):
            raise ValueError("replacement candidate price must match Underwriting")
        for scenario in opportunity.valuation_scenarios:
            if (
                scenario.currency != candidate.native_currency
                or scenario.reference_price != candidate.reference_price.amount
                or scenario.reference_price_date != candidate.reference_price_date
            ):
                raise ValueError("replacement candidate must match Underwriting scenario anchors")
        return opportunity

    @staticmethod
    def _validate_constraint_observations(
        policy: OwnerPortfolioPolicy,
        decision_input: ReplacementDecisionInput,
    ) -> None:
        expected = {item.kind for item in policy.ratio_constraints}
        observed = {item.kind for item in decision_input.constraint_observations}
        if observed != expected:
            raise ValueError(
                "replacement constraint observations must exactly cover owner ratio constraints"
            )

    @staticmethod
    def _friction_amounts(
        decision_input: ReplacementDecisionInput,
        currency: str,
    ) -> tuple[MonetaryAmount | None, MonetaryAmount | None]:
        if not decision_input.friction.is_complete:
            return None, None
        total = Decimal(0)
        for estimate in decision_input.friction.costs:
            if estimate.status is FrictionEstimateStatus.KNOWN:
                if estimate.amount is None or estimate.amount.currency != currency:
                    raise ValueError("known replacement friction must use replacement currency")
                total += estimate.amount.amount
        total = canonical_decimal(total)
        if total >= decision_input.gross_sale_amount.amount:
            raise ValueError("known switching friction must be lower than gross sale amount")
        net = canonical_decimal(decision_input.gross_sale_amount.amount - total)
        return (
            MonetaryAmount(amount=total, currency=currency),
            MonetaryAmount(amount=net, currency=currency),
        )

    @staticmethod
    def _available_investable_cash(state: PortfolioState, currency: str) -> MonetaryAmount:
        amount = sum(
            (
                item.balance.amount
                for item in state.cash_balances
                if item.is_investable and item.balance.currency == currency
            ),
            Decimal(0),
        )
        return MonetaryAmount(amount=canonical_decimal(amount), currency=currency)

    @staticmethod
    def _target_wins(comparison: PairwiseCapitalComparison, *, target_id: str) -> bool:
        if comparison.first_alternative_id == target_id:
            return comparison.conclusion is PairwiseConclusion.FIRST
        if comparison.second_alternative_id == target_id:
            return comparison.conclusion is PairwiseConclusion.SECOND
        raise ValueError("replacement comparison does not contain target")

    @staticmethod
    def _replacement_policy_block(
        *,
        state: PortfolioState,
        owner_policy: OwnerPortfolioPolicy,
        decision_input: ReplacementDecisionInput,
        net_amount: MonetaryAmount | None,
    ) -> bool:
        if net_amount is not None and owner_policy.max_capital_unit is not None:
            if owner_policy.max_capital_unit.currency != net_amount.currency:
                raise ValueError("owner max capital unit must use replacement target currency")
            if net_amount.amount > owner_policy.max_capital_unit.amount:
                return True
        if decision_input.target.kind is ReplacementTargetKind.EXISTING_HOLDING:
            target_policy = next(
                (
                    item
                    for item in owner_policy.position_policies
                    if item.position_id == decision_input.target.position_id
                ),
                None,
            )
            if target_policy is not None and not target_policy.allows_new_capital:
                return True
        constraints = {item.kind: item for item in owner_policy.ratio_constraints}
        observations = {item.kind: item for item in decision_input.constraint_observations}
        for kind, constraint in constraints.items():
            if observations[kind].observed_after > constraint.maximum:
                return True
        source = next(
            item
            for item in state.positions
            if item.position_id == decision_input.source_position_id
        )
        source_policy = next(
            (
                item
                for item in owner_policy.position_policies
                if item.position_id == source.position_id
            ),
            None,
        )
        if (
            source_policy is not None
            and source_policy.recovered_proceeds is not None
            and source_policy.recovered_proceeds.currency != source.current_value.currency
        ):
            # Runner history is intentionally not used in any replacement arithmetic.
            raise ValueError("Runner recovered proceeds must use source position currency")
        return False