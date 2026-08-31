"""Build point-in-time Chapter 7 Execution Plans from verified capital decisions."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from asymmetric_engine.application.marginal_decision import MarginalDecisionResult
from asymmetric_engine.application.portfolio_policy import (
    ApplyPortfolioPolicy,
    BuildReplacementDecision,
)
from asymmetric_engine.domain.execution import (
    EXECUTION_PLAN_METHOD_VERSION,
    ApprovedCapitalInstruction,
    ExecutionAction,
    ExecutionInvalidationObservation,
    ExecutionLeg,
    ExecutionLiquidityStatus,
    ExecutionPlan,
    ExecutionPlanInput,
    ExecutionPolicy,
    ExecutionPolicyInput,
    ExecutionPolicyReference,
    ExecutionReason,
    ExecutionReasonCode,
    ExecutionSide,
    ExecutionSourceKind,
    ExecutionTranche,
    InvalidationStatus,
    MarketExecutionObservation,
)
from asymmetric_engine.domain.financial import MonetaryAmount, canonical_decimal
from asymmetric_engine.domain.opportunity import OpportunityState
from asymmetric_engine.domain.portfolio import (
    OwnerPortfolioPolicy,
    PolicyConstrainedMarginalDecision,
    PolicyDecisionOutcome,
    PortfolioExposure,
    PortfolioState,
    ReplacementDecision,
    ReplacementOutcome,
)


class ExecutionPolicyIntegrityError(ValueError):
    """An execution policy no longer matches canonical replay."""


class ExecutionPlanIntegrityError(ValueError):
    """An Execution Plan no longer matches canonical replay."""


class BuildExecutionPolicy:
    """Content-address explicit owner execution constraints without hidden defaults."""

    @classmethod
    def execute(cls, policy_input: ExecutionPolicyInput) -> ExecutionPolicy:
        canonical_input = cls._canonicalize_input(policy_input)
        fingerprint = cls._fingerprint(canonical_input.model_dump(mode="json"))
        return ExecutionPolicy.model_validate(
            {
                **canonical_input.model_dump(mode="python"),
                "policy_id": uuid5(
                    NAMESPACE_URL,
                    f"asymmetric-insight-engine:execution-policy:{fingerprint}",
                ),
                "input_fingerprint": fingerprint,
            }
        )

    @classmethod
    def verify(cls, policy: ExecutionPolicy) -> ExecutionPolicy:
        values = {
            field_name: getattr(policy, field_name)
            for field_name in ExecutionPolicyInput.model_fields
        }
        rebuilt = cls.execute(ExecutionPolicyInput.model_validate(values))
        if rebuilt != policy:
            raise ExecutionPolicyIntegrityError("Execution Policy does not match canonical replay")
        return policy

    @staticmethod
    def _canonicalize_input(policy_input: ExecutionPolicyInput) -> ExecutionPolicyInput:
        values: dict[str, Any] = policy_input.model_dump(mode="python")
        values["assumptions"] = tuple(sorted(policy_input.assumptions))
        return ExecutionPolicyInput.model_validate(values)

    @staticmethod
    def _fingerprint(payload: Any) -> str:
        canonical_json = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return sha256(canonical_json).hexdigest()


class BuildExecutionPlan:
    """Implement an approved capital decision without reopening strategic allocation."""

    def __init__(
        self,
        *,
        policy_application: ApplyPortfolioPolicy,
        replacement_builder: BuildReplacementDecision,
        execution_policy_builder: BuildExecutionPolicy | None = None,
    ) -> None:
        self._policy_application = policy_application
        self._replacement_builder = replacement_builder
        self._execution_policy_builder = execution_policy_builder or BuildExecutionPolicy()

    def from_policy_allocation(
        self,
        *,
        portfolio_state: PortfolioState,
        opportunity_state: OpportunityState,
        current_exposure: PortfolioExposure,
        alternative_exposures: tuple[PortfolioExposure, ...],
        marginal_result: MarginalDecisionResult,
        owner_policy: OwnerPortfolioPolicy,
        policy_decision: PolicyConstrainedMarginalDecision,
        execution_policy: ExecutionPolicy,
        execution_input: ExecutionPlanInput,
    ) -> ExecutionPlan:
        verified = self._policy_application.verify(
            portfolio_state=portfolio_state,
            opportunity_state=opportunity_state,
            current_exposure=current_exposure,
            alternative_exposures=alternative_exposures,
            marginal_result=marginal_result,
            policy=owner_policy,
            policy_decision=policy_decision,
        )
        if verified.outcome is not PolicyDecisionOutcome.ALLOCATE:
            raise ValueError("only an ALLOCATE policy decision can enter Execution")
        decision = marginal_result.decision
        selected = next(
            item
            for item in decision.alternatives
            if item.alternative_id == verified.selected_alternative_id
        )
        if selected.instrument_id is None:
            raise ValueError("an executable allocation must target an instrument")
        source = ApprovedCapitalInstruction(
            decision_id=verified.policy_decision_id,
            decision_fingerprint=verified.input_fingerprint,
            decision_boundary=verified.knowledge_boundary,
            source_kind=ExecutionSourceKind.POLICY_ALLOCATION,
            target_instrument_id=selected.instrument_id,
            target_amount=decision.capital_unit.amount,
            change_conditions=decision.change_conditions,
        )
        leg_specs = ((ExecutionSide.BUY, selected.instrument_id, decision.capital_unit.amount),)
        return self._execute(
            source=source,
            execution_policy=execution_policy,
            execution_input=execution_input,
            leg_specs=leg_specs,
        )

    def verify_policy_allocation(
        self,
        *,
        portfolio_state: PortfolioState,
        opportunity_state: OpportunityState,
        current_exposure: PortfolioExposure,
        alternative_exposures: tuple[PortfolioExposure, ...],
        marginal_result: MarginalDecisionResult,
        owner_policy: OwnerPortfolioPolicy,
        policy_decision: PolicyConstrainedMarginalDecision,
        execution_policy: ExecutionPolicy,
        plan: ExecutionPlan,
    ) -> ExecutionPlan:
        execution_input = self._input_from_plan(plan)
        rebuilt = self.from_policy_allocation(
            portfolio_state=portfolio_state,
            opportunity_state=opportunity_state,
            current_exposure=current_exposure,
            alternative_exposures=alternative_exposures,
            marginal_result=marginal_result,
            owner_policy=owner_policy,
            policy_decision=policy_decision,
            execution_policy=execution_policy,
            execution_input=execution_input,
        )
        if rebuilt != plan:
            raise ExecutionPlanIntegrityError("Execution Plan does not match canonical replay")
        return plan

    def from_replacement(
        self,
        *,
        portfolio_state: PortfolioState,
        current_exposure: PortfolioExposure,
        owner_policy: OwnerPortfolioPolicy,
        replacement_decision: ReplacementDecision,
        execution_policy: ExecutionPolicy,
        execution_input: ExecutionPlanInput,
        opportunity_state: OpportunityState | None = None,
    ) -> ExecutionPlan:
        verified = self._replacement_builder.verify(
            portfolio_state=portfolio_state,
            current_exposure=current_exposure,
            policy=owner_policy,
            decision=replacement_decision,
            opportunity_state=opportunity_state,
        )
        if verified.outcome is not ReplacementOutcome.REPLACE:
            raise ValueError("only a REPLACE decision can enter Execution")
        if verified.net_redeployable_amount is None:
            raise ValueError("executable replacement requires a net redeployable amount")
        source_position = next(
            item
            for item in portfolio_state.positions
            if item.position_id == verified.source_position_id
        )
        source = ApprovedCapitalInstruction(
            decision_id=verified.replacement_decision_id,
            decision_fingerprint=verified.input_fingerprint,
            decision_boundary=verified.knowledge_boundary,
            source_kind=ExecutionSourceKind.REPLACEMENT,
            target_instrument_id=verified.target.instrument_id,
            target_amount=verified.net_redeployable_amount,
            source_position_id=verified.source_position_id,
            source_instrument_id=source_position.instrument_id,
            source_sale_amount=verified.gross_sale_amount,
            change_conditions=verified.change_conditions,
        )
        leg_specs = (
            (ExecutionSide.SELL, source_position.instrument_id, verified.gross_sale_amount),
            (ExecutionSide.BUY, verified.target.instrument_id, verified.net_redeployable_amount),
        )
        return self._execute(
            source=source,
            execution_policy=execution_policy,
            execution_input=execution_input,
            leg_specs=leg_specs,
        )

    def verify_replacement(
        self,
        *,
        portfolio_state: PortfolioState,
        current_exposure: PortfolioExposure,
        owner_policy: OwnerPortfolioPolicy,
        replacement_decision: ReplacementDecision,
        execution_policy: ExecutionPolicy,
        plan: ExecutionPlan,
        opportunity_state: OpportunityState | None = None,
    ) -> ExecutionPlan:
        rebuilt = self.from_replacement(
            portfolio_state=portfolio_state,
            current_exposure=current_exposure,
            owner_policy=owner_policy,
            replacement_decision=replacement_decision,
            execution_policy=execution_policy,
            execution_input=self._input_from_plan(plan),
            opportunity_state=opportunity_state,
        )
        if rebuilt != plan:
            raise ExecutionPlanIntegrityError("Execution Plan does not match canonical replay")
        return plan

    def _execute(
        self,
        *,
        source: ApprovedCapitalInstruction,
        execution_policy: ExecutionPolicy,
        execution_input: ExecutionPlanInput,
        leg_specs: tuple[tuple[ExecutionSide, str, MonetaryAmount], ...],
    ) -> ExecutionPlan:
        policy = self._execution_policy_builder.verify(execution_policy)
        current_input = self._canonicalize_input(execution_input)
        self._validate_boundaries(source=source, policy=policy, execution_input=current_input)
        self._validate_policy_currency(policy=policy, leg_specs=leg_specs)
        self._validate_temporal_inputs(current_input)

        expected_conditions = set(source.change_conditions)
        actual_conditions = {item.condition for item in current_input.invalidation_observations}
        extras = actual_conditions - expected_conditions
        if extras:
            raise ValueError("Execution cannot introduce invalidation conditions not owned upstream")
        invalidations = {item.condition: item for item in current_input.invalidation_observations}
        triggered = [
            item for item in invalidations.values() if item.status is InvalidationStatus.TRIGGERED
        ]
        if triggered:
            reasons = (
                ExecutionReason(
                    code=ExecutionReasonCode.INVALIDATION_TRIGGERED,
                    detail="At least one exact upstream change condition is explicitly triggered.",
                ),
            )
            return self._build_plan(
                source=source,
                policy=policy,
                execution_input=current_input,
                action=ExecutionAction.INVALIDATED,
                reasons=reasons,
                legs=(),
                missing_data=(),
            )

        wait_details: dict[ExecutionReasonCode, list[str]] = {}
        missing_data: set[str] = set()
        missing_conditions = expected_conditions - actual_conditions
        if missing_conditions:
            wait_details.setdefault(ExecutionReasonCode.INVALIDATION_MISSING, []).append(
                "Not every upstream change condition has a current execution-time assessment."
            )
            missing_data.update(
                f"Missing invalidation assessment: {condition}" for condition in missing_conditions
            )
        unknown_invalidations = [
            item for item in invalidations.values() if item.status is InvalidationStatus.UNKNOWN
        ]
        if unknown_invalidations:
            wait_details.setdefault(ExecutionReasonCode.INVALIDATION_UNKNOWN, []).append(
                "At least one upstream change condition remains unknown at execution time."
            )
            for item in unknown_invalidations:
                missing_data.update(item.missing_data)

        required_instruments = {instrument_id for _, instrument_id, _ in leg_specs}
        observations = {item.instrument_id: item for item in current_input.market_observations}
        extra_instruments = set(observations) - required_instruments
        if extra_instruments:
            raise ValueError(
                "Execution received market observations for instruments it will not trade"
            )
        missing_instruments = required_instruments - set(observations)
        if missing_instruments:
            wait_details.setdefault(ExecutionReasonCode.QUOTE_MISSING, []).append(
                "A current market observation is missing for at least one required trade instrument."
            )
            missing_data.update(
                f"Missing execution quote: {instrument_id}"
                for instrument_id in missing_instruments
            )

        amount_by_instrument = {instrument_id: amount for _, instrument_id, amount in leg_specs}
        for instrument_id, observation in observations.items():
            expected_amount = amount_by_instrument[instrument_id]
            if observation.native_currency != expected_amount.currency:
                raise ValueError("execution market observation must use the approved leg currency")
            age_seconds = (
                current_input.knowledge_boundary.as_of - observation.observed_at
            ).total_seconds()
            if age_seconds > policy.max_quote_age_seconds:
                wait_details.setdefault(ExecutionReasonCode.QUOTE_STALE, []).append(
                    f"Quote for {instrument_id} exceeds the explicit owner quote-age limit."
                )
            if observation.spread_bps > policy.max_spread_bps:
                wait_details.setdefault(ExecutionReasonCode.SPREAD_TOO_WIDE, []).append(
                    f"Spread for {instrument_id} exceeds the explicit owner maximum."
                )
            if observation.liquidity is ExecutionLiquidityStatus.UNKNOWN:
                wait_details.setdefault(ExecutionReasonCode.LIQUIDITY_UNKNOWN, []).append(
                    f"Liquidity for {instrument_id} is unknown."
                )
                missing_data.update(observation.missing_data)
            elif observation.liquidity is ExecutionLiquidityStatus.CONSTRAINED:
                wait_details.setdefault(ExecutionReasonCode.LIQUIDITY_CONSTRAINED, []).append(
                    f"Liquidity for {instrument_id} is constrained; the MVP does not infer a schedule."
                )

        if wait_details:
            reasons = tuple(
                ExecutionReason(code=code, detail=" ".join(details))
                for code, details in sorted(wait_details.items(), key=lambda item: item[0].value)
            )
            return self._build_plan(
                source=source,
                policy=policy,
                execution_input=current_input,
                action=ExecutionAction.WAIT,
                reasons=reasons,
                legs=(),
                missing_data=tuple(sorted(missing_data)),
            )

        requires_staging = (
            policy.max_single_order_notional is not None
            and any(
                amount.amount > policy.max_single_order_notional.amount
                for _, _, amount in leg_specs
            )
        )
        if requires_staging:
            assert policy.max_single_order_notional is not None
            legs = self._build_legs(
                leg_specs,
                max_single_order_notional=policy.max_single_order_notional,
            )
            reasons = (
                ExecutionReason(
                    code=ExecutionReasonCode.EXPLICIT_STAGING_LIMIT,
                    detail=(
                        "At least one approved trade leg exceeds the explicit maximum order "
                        "notional."
                    ),
                ),
            )
            action = ExecutionAction.STAGED
        else:
            legs = self._build_legs(leg_specs, max_single_order_notional=None)
            reasons = (
                ExecutionReason(
                    code=ExecutionReasonCode.READY_NOW,
                    detail="All explicit execution gates pass without a staging constraint.",
                ),
            )
            action = ExecutionAction.NOW

        return self._build_plan(
            source=source,
            policy=policy,
            execution_input=current_input,
            action=action,
            reasons=reasons,
            legs=legs,
            missing_data=(),
        )

    @staticmethod
    def _validate_boundaries(
        *,
        source: ApprovedCapitalInstruction,
        policy: ExecutionPolicy,
        execution_input: ExecutionPlanInput,
    ) -> None:
        if policy.knowledge_boundary != execution_input.knowledge_boundary:
            raise ValueError("Execution Policy and Plan must share one execution knowledge boundary")
        if (
            source.decision_boundary.knowledge_mode
            is not execution_input.knowledge_boundary.knowledge_mode
        ):
            raise ValueError("Execution must preserve the capital decision KnowledgeMode")
        if execution_input.knowledge_boundary.as_of < source.decision_boundary.as_of:
            raise ValueError("Execution boundary cannot precede the approved capital decision")

    @staticmethod
    def _validate_policy_currency(
        *,
        policy: ExecutionPolicy,
        leg_specs: tuple[tuple[ExecutionSide, str, MonetaryAmount], ...],
    ) -> None:
        if policy.max_single_order_notional is None:
            return
        currencies = {amount.currency for _, _, amount in leg_specs}
        if currencies != {policy.max_single_order_notional.currency}:
            raise ValueError("maximum single-order notional must use the execution-leg currency")

    @staticmethod
    def _validate_temporal_inputs(execution_input: ExecutionPlanInput) -> None:
        boundary = execution_input.knowledge_boundary
        observations: tuple[MarketExecutionObservation | ExecutionInvalidationObservation, ...] = (
            *execution_input.market_observations,
            *execution_input.invalidation_observations,
        )
        for observation in observations:
            if observation.observed_at > boundary.as_of:
                raise ValueError("Execution cannot consume an observation from the future")
            if not boundary.includes(
                available_at=observation.available_at,
                recorded_at=observation.recorded_at,
            ):
                raise ValueError(
                    "Execution observation is outside the canonical knowledge boundary"
                )

    @staticmethod
    def _canonicalize_input(execution_input: ExecutionPlanInput) -> ExecutionPlanInput:
        values: dict[str, Any] = execution_input.model_dump(mode="python")
        values["market_observations"] = tuple(
            sorted(
                (
                    item.model_copy(update={"missing_data": tuple(sorted(item.missing_data))})
                    for item in execution_input.market_observations
                ),
                key=lambda item: item.instrument_id,
            )
        )
        values["invalidation_observations"] = tuple(
            sorted(
                (
                    item.model_copy(update={"missing_data": tuple(sorted(item.missing_data))})
                    for item in execution_input.invalidation_observations
                ),
                key=lambda item: item.condition,
            )
        )
        values["conflicts"] = tuple(sorted(execution_input.conflicts))
        values["assumptions"] = tuple(sorted(execution_input.assumptions))
        return ExecutionPlanInput.model_validate(values)

    @staticmethod
    def _build_legs(
        leg_specs: tuple[tuple[ExecutionSide, str, MonetaryAmount], ...],
        *,
        max_single_order_notional: MonetaryAmount | None,
    ) -> tuple[ExecutionLeg, ...]:
        legs: list[ExecutionLeg] = []
        for sequence, (side, instrument_id, amount) in enumerate(leg_specs, start=1):
            if max_single_order_notional is None:
                tranches = (ExecutionTranche(tranche_index=1, notional=amount),)
            else:
                remaining = amount.amount
                tranche_values: list[ExecutionTranche] = []
                index = 1
                while remaining > 0:
                    current = min(remaining, max_single_order_notional.amount)
                    tranche_values.append(
                        ExecutionTranche(
                            tranche_index=index,
                            notional=MonetaryAmount(
                                amount=canonical_decimal(current),
                                currency=amount.currency,
                            ),
                        )
                    )
                    remaining = canonical_decimal(remaining - current)
                    index += 1
                tranches = tuple(tranche_values)
            legs.append(
                ExecutionLeg(
                    sequence=sequence,
                    side=side,
                    instrument_id=instrument_id,
                    total_notional=amount,
                    tranches=tranches,
                )
            )
        return tuple(legs)

    @staticmethod
    def _policy_reference(policy: ExecutionPolicy) -> ExecutionPolicyReference:
        return ExecutionPolicyReference(
            policy_id=policy.policy_id,
            input_fingerprint=policy.input_fingerprint,
            knowledge_boundary=policy.knowledge_boundary,
        )

    @classmethod
    def _build_plan(
        cls,
        *,
        source: ApprovedCapitalInstruction,
        policy: ExecutionPolicy,
        execution_input: ExecutionPlanInput,
        action: ExecutionAction,
        reasons: tuple[ExecutionReason, ...],
        legs: tuple[ExecutionLeg, ...],
        missing_data: tuple[str, ...],
    ) -> ExecutionPlan:
        policy_reference = cls._policy_reference(policy)
        material = {
            "method_version": EXECUTION_PLAN_METHOD_VERSION,
            "source": source.model_dump(mode="json"),
            "policy": policy_reference.model_dump(mode="json"),
            "execution_input": execution_input.model_dump(mode="json"),
            "action": action.value,
            "reasons": [item.model_dump(mode="json") for item in reasons],
            "legs": [item.model_dump(mode="json") for item in legs],
            "missing_data": missing_data,
        }
        fingerprint = BuildExecutionPolicy._fingerprint(material)
        return ExecutionPlan(
            **execution_input.model_dump(mode="python"),
            plan_id=uuid5(
                NAMESPACE_URL,
                f"asymmetric-insight-engine:execution-plan:{fingerprint}",
            ),
            input_fingerprint=fingerprint,
            source=source,
            policy=policy_reference,
            action=action,
            reasons=reasons,
            legs=legs,
            missing_data=missing_data,
        )

    @staticmethod
    def _input_from_plan(plan: ExecutionPlan) -> ExecutionPlanInput:
        values = {
            field_name: getattr(plan, field_name)
            for field_name in ExecutionPlanInput.model_fields
        }
        return ExecutionPlanInput.model_validate(values)
