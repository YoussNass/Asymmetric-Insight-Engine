"""Open and evaluate point-in-time decision-level Learning cases."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from asymmetric_engine.application.execution import BuildExecutionPlan
from asymmetric_engine.application.marginal_decision import MarginalDecisionResult
from asymmetric_engine.domain.execution import ExecutionAction, ExecutionPlan, ExecutionPolicy
from asymmetric_engine.domain.financial import MonetaryAmount, canonical_decimal
from asymmetric_engine.domain.learning import (
    LEARNING_EVALUATION_METHOD_VERSION,
    DecisionLearningCase,
    DecisionLearningCaseInput,
    DecisionLearningCaseReference,
    DecisionLearningEvaluation,
    LearningEvaluationInput,
    LearningExecutionAction,
    LearningMetrics,
    LearningPriceObservation,
    LearningSourceKind,
    LearningSourceReference,
    ScenarioRangeAnchor,
    ScenarioRealizationBand,
    ThesisConditionStatus,
    ThesisOutcome,
)
from asymmetric_engine.domain.opportunity import FinancialMetric, OpportunityState, ScenarioKind
from asymmetric_engine.domain.portfolio import (
    CapitalAlternativeKind,
    OwnerPortfolioPolicy,
    PolicyConstrainedMarginalDecision,
    PortfolioExposure,
    PortfolioState,
    ReplacementDecision,
)


class LearningCaseIntegrityError(ValueError):
    """A Learning case no longer matches its canonical content address."""


class LearningEvaluationIntegrityError(ValueError):
    """A Learning evaluation no longer matches canonical replay."""


class OpenDecisionLearningCase:
    """Verify Chapter 6/7 lineage and freeze the T0/T1 anchors used by Learning."""

    def __init__(self, *, execution_builder: BuildExecutionPlan) -> None:
        self._execution_builder = execution_builder

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
        execution_plan: ExecutionPlan,
        evaluation_horizon_date: date | None = None,
    ) -> DecisionLearningCase:
        plan = self._execution_builder.verify_policy_allocation(
            portfolio_state=portfolio_state,
            opportunity_state=opportunity_state,
            current_exposure=current_exposure,
            alternative_exposures=alternative_exposures,
            marginal_result=marginal_result,
            owner_policy=owner_policy,
            policy_decision=policy_decision,
            execution_policy=execution_policy,
            plan=execution_plan,
        )
        self._require_implementable_plan(plan)
        decision = marginal_result.decision
        selected = next(
            item
            for item in decision.alternatives
            if item.alternative_id == policy_decision.selected_alternative_id
        )
        if selected.instrument_id is None:
            raise ValueError("Learning requires an executable instrument target")

        scenario_range: ScenarioRangeAnchor | None = None
        if selected.kind is CapitalAlternativeKind.CANDIDATE_EQUITY:
            target_price = decision.candidate_instrument.reference_price
            scenario_range = self._scenario_anchor(
                opportunity_state,
                target_price=target_price,
            )
            horizon = scenario_range.horizon_date
            if evaluation_horizon_date is not None and evaluation_horizon_date != horizon:
                raise ValueError("candidate Learning horizon must preserve Underwriting scenarios")
        else:
            target_price = self._state_price(portfolio_state, selected.instrument_id)
            horizon = self._require_explicit_horizon(evaluation_horizon_date)

        benchmark_id = portfolio_state.etf_eligibility_policy.benchmark_instrument_id
        benchmark_price = self._state_price(portfolio_state, benchmark_id)
        return self._build_case(
            source=self._source_reference(plan, LearningSourceKind.POLICY_ALLOCATION),
            target_instrument_id=selected.instrument_id,
            target_reference_price=target_price,
            benchmark_instrument_id=benchmark_id,
            benchmark_reference_price=benchmark_price,
            evaluation_horizon_date=horizon,
            scenario_range=scenario_range,
            change_conditions=plan.source.change_conditions,
        )

    def from_replacement(
        self,
        *,
        portfolio_state: PortfolioState,
        current_exposure: PortfolioExposure,
        owner_policy: OwnerPortfolioPolicy,
        replacement_decision: ReplacementDecision,
        execution_policy: ExecutionPolicy,
        execution_plan: ExecutionPlan,
        evaluation_horizon_date: date | None = None,
        opportunity_state: OpportunityState | None = None,
    ) -> DecisionLearningCase:
        plan = self._execution_builder.verify_replacement(
            portfolio_state=portfolio_state,
            current_exposure=current_exposure,
            owner_policy=owner_policy,
            replacement_decision=replacement_decision,
            execution_policy=execution_policy,
            plan=execution_plan,
            opportunity_state=opportunity_state,
        )
        self._require_implementable_plan(plan)
        target = replacement_decision.target
        scenario_range: ScenarioRangeAnchor | None = None
        if target.opportunity_id is not None:
            if opportunity_state is None:
                raise ValueError("candidate replacement Learning requires Opportunity State")
            target_price = self._opportunity_reference_price(opportunity_state)
            scenario_range = self._scenario_anchor(
                opportunity_state,
                target_price=target_price,
            )
            horizon = scenario_range.horizon_date
            if evaluation_horizon_date is not None and evaluation_horizon_date != horizon:
                raise ValueError("candidate Learning horizon must preserve Underwriting scenarios")
        else:
            target_price = self._state_price(portfolio_state, target.instrument_id)
            horizon = self._require_explicit_horizon(evaluation_horizon_date)

        benchmark_id = portfolio_state.etf_eligibility_policy.benchmark_instrument_id
        benchmark_price = self._state_price(portfolio_state, benchmark_id)
        if plan.source.source_instrument_id is None:
            raise ValueError("replacement Learning requires the verified source instrument")
        source_price = self._state_price(portfolio_state, plan.source.source_instrument_id)
        return self._build_case(
            source=self._source_reference(plan, LearningSourceKind.REPLACEMENT),
            target_instrument_id=target.instrument_id,
            target_reference_price=target_price,
            benchmark_instrument_id=benchmark_id,
            benchmark_reference_price=benchmark_price,
            evaluation_horizon_date=horizon,
            scenario_range=scenario_range,
            replacement_source_instrument_id=plan.source.source_instrument_id,
            replacement_source_reference_price=source_price,
            change_conditions=plan.source.change_conditions,
        )

    @classmethod
    def verify(cls, case: DecisionLearningCase) -> DecisionLearningCase:
        values = {
            field_name: getattr(case, field_name)
            for field_name in DecisionLearningCaseInput.model_fields
        }
        rebuilt = cls._content_address(DecisionLearningCaseInput.model_validate(values))
        if rebuilt != case:
            raise LearningCaseIntegrityError("Learning case does not match canonical replay")
        return case

    @classmethod
    def _build_case(
        cls,
        *,
        source: LearningSourceReference,
        target_instrument_id: str,
        target_reference_price: MonetaryAmount,
        benchmark_instrument_id: str,
        benchmark_reference_price: MonetaryAmount,
        evaluation_horizon_date: date,
        scenario_range: ScenarioRangeAnchor | None,
        change_conditions: tuple[str, ...],
        replacement_source_instrument_id: str | None = None,
        replacement_source_reference_price: MonetaryAmount | None = None,
    ) -> DecisionLearningCase:
        case_input = DecisionLearningCaseInput(
            knowledge_boundary=source.execution_boundary,
            source=source,
            target_instrument_id=target_instrument_id,
            target_reference_price=target_reference_price,
            benchmark_instrument_id=benchmark_instrument_id,
            benchmark_reference_price=benchmark_reference_price,
            evaluation_horizon_date=evaluation_horizon_date,
            scenario_range=scenario_range,
            replacement_source_instrument_id=replacement_source_instrument_id,
            replacement_source_reference_price=replacement_source_reference_price,
            change_conditions=change_conditions,
            rationale=(
                "Preserve verified capital and Execution anchors for later "
                "decision-level learning.",
            ),
            assumptions=(
                "Observed price return is not realized account P&L without broker fill data.",
            ),
        )
        return cls._content_address(case_input)

    @classmethod
    def _content_address(cls, case_input: DecisionLearningCaseInput) -> DecisionLearningCase:
        current = cls._canonicalize_case_input(case_input)
        fingerprint = cls._fingerprint(current.model_dump(mode="json"))
        return DecisionLearningCase.model_validate(
            {
                **current.model_dump(mode="python"),
                "case_id": uuid5(
                    NAMESPACE_URL,
                    f"asymmetric-insight-engine:learning-case:{fingerprint}",
                ),
                "input_fingerprint": fingerprint,
            }
        )

    @staticmethod
    def _canonicalize_case_input(
        case_input: DecisionLearningCaseInput,
    ) -> DecisionLearningCaseInput:
        values: dict[str, Any] = case_input.model_dump(mode="python")
        for field_name in (
            "change_conditions",
            "missing_data",
            "conflicts",
            "assumptions",
        ):
            values[field_name] = tuple(sorted(getattr(case_input, field_name)))
        return DecisionLearningCaseInput.model_validate(values)

    @staticmethod
    def _source_reference(
        plan: ExecutionPlan,
        source_kind: LearningSourceKind,
    ) -> LearningSourceReference:
        action = {
            ExecutionAction.NOW: LearningExecutionAction.NOW,
            ExecutionAction.STAGED: LearningExecutionAction.STAGED,
        }.get(plan.action)
        if action is None:
            raise ValueError("Learning accepts only NOW or STAGED Execution Plans")
        return LearningSourceReference(
            decision_id=plan.source.decision_id,
            decision_fingerprint=plan.source.decision_fingerprint,
            execution_plan_id=plan.plan_id,
            execution_plan_fingerprint=plan.input_fingerprint,
            decision_boundary=plan.source.decision_boundary,
            execution_boundary=plan.knowledge_boundary,
            source_kind=source_kind,
            execution_action=action,
        )

    @staticmethod
    def _require_implementable_plan(plan: ExecutionPlan) -> None:
        if plan.action not in {ExecutionAction.NOW, ExecutionAction.STAGED}:
            raise ValueError("Learning accepts only NOW or STAGED Execution Plans")

    @staticmethod
    def _require_explicit_horizon(value: date | None) -> date:
        if value is None:
            raise ValueError("non-candidate Learning requires an explicit evaluation horizon")
        return value

    @staticmethod
    def _state_price(portfolio_state: PortfolioState, instrument_id: str) -> MonetaryAmount:
        try:
            return next(
                item.unit_price
                for item in portfolio_state.prices
                if item.instrument_id == instrument_id
            )
        except StopIteration as error:
            raise ValueError(
                "Learning requires the instrument T0 price in Portfolio State"
            ) from error

    @staticmethod
    def _opportunity_reference_price(opportunity_state: OpportunityState) -> MonetaryAmount:
        prices = [
            item
            for item in opportunity_state.financial_facts
            if item.metric is FinancialMetric.REFERENCE_SHARE_PRICE
        ]
        if len(prices) != 1 or prices[0].currency is None:
            raise ValueError("Learning requires one verified Opportunity reference-share price")
        return MonetaryAmount(amount=prices[0].value, currency=prices[0].currency)

    @classmethod
    def _scenario_anchor(
        cls,
        opportunity_state: OpportunityState,
        *,
        target_price: MonetaryAmount,
    ) -> ScenarioRangeAnchor:
        scenarios = {item.kind: item for item in opportunity_state.valuation_scenarios}
        if set(scenarios) != {ScenarioKind.BEAR, ScenarioKind.BASE, ScenarioKind.BULL}:
            raise ValueError("candidate Learning requires bear/base/bull Underwriting scenarios")
        bear = scenarios[ScenarioKind.BEAR]
        base = scenarios[ScenarioKind.BASE]
        bull = scenarios[ScenarioKind.BULL]
        horizons = {bear.horizon_date, base.horizon_date, bull.horizon_date}
        references = {bear.reference_price, base.reference_price, bull.reference_price}
        currencies = {bear.currency, base.currency, bull.currency}
        if len(horizons) != 1 or len(references) != 1 or len(currencies) != 1:
            raise ValueError("candidate Learning requires one common T0 scenario anchor")
        if target_price.currency not in currencies or target_price.amount not in references:
            raise ValueError("Learning target price must match the verified scenario reference")
        return ScenarioRangeAnchor(
            currency=target_price.currency,
            reference_price=target_price.amount,
            horizon_date=bear.horizon_date,
            bear_return=bear.return_from_reference,
            base_return=base.return_from_reference,
            bull_return=bull.return_from_reference,
        )

    @staticmethod
    def _fingerprint(payload: Any) -> str:
        canonical_json = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return sha256(canonical_json).hexdigest()


class BuildDecisionLearningEvaluation:
    """Evaluate a verified Learning case at T2 without changing any upstream decision."""

    def execute(
        self,
        *,
        case: DecisionLearningCase,
        evaluation_input: LearningEvaluationInput,
    ) -> DecisionLearningEvaluation:
        current_case = OpenDecisionLearningCase.verify(case)
        current_input = self._canonicalize_input(evaluation_input)
        if current_input.conflicts:
            raise ValueError(
                "Learning evaluation conflicts must be resolved before evaluating outcomes"
            )
        self._validate_boundary(current_case, current_input)
        self._validate_temporal_inputs(current_case, current_input)

        required_instruments = {
            current_case.target_instrument_id,
            current_case.benchmark_instrument_id,
        }
        if current_case.replacement_source_instrument_id is not None:
            required_instruments.add(current_case.replacement_source_instrument_id)
        observed_instruments = {item.instrument_id for item in current_input.price_observations}
        extras = observed_instruments - required_instruments
        if extras:
            raise ValueError("Learning received price observations for unrelated instruments")
        missing = required_instruments - observed_instruments
        if missing:
            raise ValueError("Learning requires at least one later price for every comparison leg")

        grouped: dict[str, tuple[LearningPriceObservation, ...]] = {
            instrument_id: tuple(
                sorted(
                    (
                        item
                        for item in current_input.price_observations
                        if item.instrument_id == instrument_id
                    ),
                    key=lambda item: item.observed_at,
                )
            )
            for instrument_id in required_instruments
        }
        anchors = {
            current_case.target_instrument_id: current_case.target_reference_price,
            current_case.benchmark_instrument_id: current_case.benchmark_reference_price,
        }
        if (
            current_case.replacement_source_instrument_id is not None
            and current_case.replacement_source_reference_price is not None
        ):
            anchors[current_case.replacement_source_instrument_id] = (
                current_case.replacement_source_reference_price
            )
        for instrument_id, observations in grouped.items():
            if any(item.price.currency != anchors[instrument_id].currency for item in observations):
                raise ValueError("Learning later prices must preserve each T0 anchor currency")

        end_dates = {observations[-1].observed_at.date() for observations in grouped.values()}
        if len(end_dates) != 1:
            raise ValueError("Learning comparison legs must end on the same observation date")

        target_observations = grouped[current_case.target_instrument_id]
        benchmark_observations = grouped[current_case.benchmark_instrument_id]
        target_return = self._return(
            current_case.target_reference_price,
            target_observations[-1].price,
        )
        benchmark_return = self._return(
            current_case.benchmark_reference_price,
            benchmark_observations[-1].price,
        )
        source_return: Decimal | None = None
        replacement_excess: Decimal | None = None
        if current_case.replacement_source_instrument_id is not None:
            assert current_case.replacement_source_reference_price is not None
            source_observations = grouped[current_case.replacement_source_instrument_id]
            source_return = self._return(
                current_case.replacement_source_reference_price,
                source_observations[-1].price,
            )
            replacement_excess = canonical_decimal(target_return - source_return)

        metrics = LearningMetrics(
            observed_target_return=target_return,
            observed_benchmark_return=benchmark_return,
            observed_excess_return=canonical_decimal(target_return - benchmark_return),
            target_max_drawdown=self._max_drawdown(
                current_case.target_reference_price,
                target_observations,
            ),
            replacement_source_return=source_return,
            replacement_excess_vs_source=replacement_excess,
        )
        thesis_outcome, missing_data = self._thesis_outcome(current_case, current_input)
        end_observation_at = max(observations[-1].observed_at for observations in grouped.values())
        horizon_reached = end_observation_at.date() >= current_case.evaluation_horizon_date
        scenario_realization = self._scenario_realization(
            current_case,
            target_return=target_return,
            horizon_reached=horizon_reached,
        )
        case_reference = DecisionLearningCaseReference(
            case_id=current_case.case_id,
            input_fingerprint=current_case.input_fingerprint,
            knowledge_boundary=current_case.knowledge_boundary,
        )
        material = {
            "method_version": LEARNING_EVALUATION_METHOD_VERSION,
            "case": case_reference.model_dump(mode="json"),
            "evaluation_input": current_input.model_dump(mode="json"),
            "metrics": metrics.model_dump(mode="json"),
            "thesis_outcome": thesis_outcome.value,
            "horizon_reached": horizon_reached,
            "scenario_realization": scenario_realization.value,
            "end_observation_at": end_observation_at.isoformat(),
            "missing_data": missing_data,
        }
        fingerprint = OpenDecisionLearningCase._fingerprint(material)
        return DecisionLearningEvaluation(
            **current_input.model_dump(mode="python"),
            evaluation_id=uuid5(
                NAMESPACE_URL,
                f"asymmetric-insight-engine:learning-evaluation:{fingerprint}",
            ),
            input_fingerprint=fingerprint,
            case=case_reference,
            metrics=metrics,
            thesis_outcome=thesis_outcome,
            horizon_reached=horizon_reached,
            scenario_realization=scenario_realization,
            end_observation_at=end_observation_at,
            missing_data=missing_data,
        )

    def verify(
        self,
        *,
        case: DecisionLearningCase,
        evaluation: DecisionLearningEvaluation,
    ) -> DecisionLearningEvaluation:
        values = {
            field_name: getattr(evaluation, field_name)
            for field_name in LearningEvaluationInput.model_fields
        }
        rebuilt = self.execute(
            case=case,
            evaluation_input=LearningEvaluationInput.model_validate(values),
        )
        if rebuilt != evaluation:
            raise LearningEvaluationIntegrityError(
                "Learning evaluation does not match canonical replay"
            )
        return evaluation

    @staticmethod
    def _canonicalize_input(
        evaluation_input: LearningEvaluationInput,
    ) -> LearningEvaluationInput:
        values: dict[str, Any] = evaluation_input.model_dump(mode="python")
        values["price_observations"] = tuple(
            sorted(
                evaluation_input.price_observations,
                key=lambda item: (item.instrument_id, item.observed_at),
            )
        )
        values["thesis_observations"] = tuple(
            sorted(evaluation_input.thesis_observations, key=lambda item: item.condition)
        )
        values["conflicts"] = tuple(sorted(evaluation_input.conflicts))
        values["assumptions"] = tuple(sorted(evaluation_input.assumptions))
        return LearningEvaluationInput.model_validate(values)

    @staticmethod
    def _validate_boundary(
        case: DecisionLearningCase,
        evaluation_input: LearningEvaluationInput,
    ) -> None:
        if evaluation_input.knowledge_boundary.as_of < case.knowledge_boundary.as_of:
            raise ValueError("Learning evaluation requires T2 >= T1")
        if evaluation_input.knowledge_boundary.knowledge_mode is not case.knowledge_mode:
            raise ValueError("Learning evaluation must preserve the source KnowledgeMode")

    @staticmethod
    def _validate_temporal_inputs(
        case: DecisionLearningCase,
        evaluation_input: LearningEvaluationInput,
    ) -> None:
        boundary = evaluation_input.knowledge_boundary
        observations = (
            *evaluation_input.price_observations,
            *evaluation_input.thesis_observations,
        )
        for observation in observations:
            if observation.observed_at < case.source.decision_boundary.as_of:
                raise ValueError("Learning cannot use outcome observations from before T0")
            if observation.observed_at > boundary.as_of:
                raise ValueError("Learning cannot consume an observation from the future")
            if not boundary.includes(
                available_at=observation.available_at,
                recorded_at=observation.recorded_at,
            ):
                raise ValueError("Learning observation is outside the canonical T2 boundary")

    @staticmethod
    def _return(start: MonetaryAmount, end: MonetaryAmount) -> Decimal:
        if start.currency != end.currency:
            raise ValueError("Learning return arithmetic cannot perform implicit FX")
        return canonical_decimal(end.amount / start.amount - Decimal(1))

    @staticmethod
    def _max_drawdown(
        start: MonetaryAmount,
        observations: tuple[LearningPriceObservation, ...],
    ) -> Decimal:
        peak = start.amount
        max_drawdown = Decimal(0)
        for observation in observations:
            value = observation.price.amount
            peak = max(peak, value)
            drawdown = canonical_decimal(value / peak - Decimal(1))
            max_drawdown = min(max_drawdown, drawdown)
        return canonical_decimal(max_drawdown)

    @staticmethod
    def _thesis_outcome(
        case: DecisionLearningCase,
        evaluation_input: LearningEvaluationInput,
    ) -> tuple[ThesisOutcome, tuple[str, ...]]:
        expected = set(case.change_conditions)
        by_condition = {item.condition: item for item in evaluation_input.thesis_observations}
        extras = set(by_condition) - expected
        if extras:
            raise ValueError("Learning cannot invent retrospective change conditions")
        missing_conditions = expected - set(by_condition)
        missing_data = {
            f"Missing Learning thesis assessment: {condition}" for condition in missing_conditions
        }
        if any(item.status is ThesisConditionStatus.TRIGGERED for item in by_condition.values()):
            return ThesisOutcome.INVALIDATED, tuple(sorted(missing_data))
        unknown = [
            item for item in by_condition.values() if item.status is ThesisConditionStatus.UNKNOWN
        ]
        for item in unknown:
            missing_data.update(item.missing_data)
        if missing_conditions or unknown:
            return ThesisOutcome.UNRESOLVED, tuple(sorted(missing_data))
        return ThesisOutcome.INTACT, ()

    @staticmethod
    def _scenario_realization(
        case: DecisionLearningCase,
        *,
        target_return: Decimal,
        horizon_reached: bool,
    ) -> ScenarioRealizationBand:
        scenario = case.scenario_range
        if scenario is None:
            return ScenarioRealizationBand.NOT_AVAILABLE
        if not horizon_reached:
            return ScenarioRealizationBand.PRE_HORIZON
        if target_return < scenario.bear_return:
            return ScenarioRealizationBand.BELOW_BEAR
        if target_return < scenario.base_return:
            return ScenarioRealizationBand.BEAR_TO_BASE
        if target_return <= scenario.bull_return:
            return ScenarioRealizationBand.BASE_TO_BULL
        return ScenarioRealizationBand.ABOVE_BULL
