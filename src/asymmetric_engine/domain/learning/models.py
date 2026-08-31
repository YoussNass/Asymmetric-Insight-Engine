"""Pure decision-level Learning contracts for Chapter 8."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from asymmetric_engine.domain.evidence.models import ContentHash, NonEmptyString
from asymmetric_engine.domain.financial import CurrencyCode, MonetaryAmount, canonical_decimal
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode

LEARNING_CASE_METHOD_VERSION = "decision-learning-case-v1"
LEARNING_EVALUATION_METHOD_VERSION = "decision-learning-evaluation-v1"


def _reject_duplicates[T](values: tuple[T, ...], message: str) -> tuple[T, ...]:
    if len(values) != len(set(values)):
        raise ValueError(message)
    return values


class LearningSourceKind(StrEnum):
    """Capital-decision source admitted by the first Learning slice."""

    POLICY_ALLOCATION = "policy_allocation"
    REPLACEMENT = "replacement"


class LearningExecutionAction(StrEnum):
    """Only implementable Chapter 7 plans enter active-decision Learning."""

    NOW = "now"
    STAGED = "staged"


class LearningReturnBasis(StrEnum):
    """The MVP baseline deliberately avoids claiming broker or total-return P&L."""

    PRICE_ONLY_FROM_DECISION_REFERENCE = "price_only_from_decision_reference"


class AccountPnlStatus(StrEnum):
    """Whether account-level realized P&L is measured by this record."""

    NOT_MEASURED_NO_FILL_DATA = "not_measured_no_fill_data"


class ThesisConditionStatus(StrEnum):
    """Later state of one exact upstream change condition."""

    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    UNKNOWN = "unknown"


class ThesisOutcome(StrEnum):
    """Decision-level thesis state at the Learning boundary."""

    INTACT = "intact"
    INVALIDATED = "invalidated"
    UNRESOLVED = "unresolved"


class ScenarioRealizationBand(StrEnum):
    """Categorical observation against the T0 scenario range; no probability is implied."""

    PRE_HORIZON = "pre_horizon"
    BELOW_BEAR = "below_bear"
    BEAR_TO_BASE = "bear_to_base"
    BASE_TO_BULL = "base_to_bull"
    ABOVE_BULL = "above_bull"
    NOT_AVAILABLE = "not_available"


class LearningSourceReference(BaseModel):
    """Immutable references to the capital decision and implementable Execution Plan."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    decision_id: UUID
    decision_fingerprint: ContentHash
    execution_plan_id: UUID
    execution_plan_fingerprint: ContentHash
    decision_boundary: KnowledgeBoundary
    execution_boundary: KnowledgeBoundary
    source_kind: LearningSourceKind
    execution_action: LearningExecutionAction

    @model_validator(mode="after")
    def validate_boundaries(self) -> Self:
        if self.execution_boundary.as_of < self.decision_boundary.as_of:
            raise ValueError("Learning source requires T1 >= T0")
        if self.execution_boundary.knowledge_mode is not self.decision_boundary.knowledge_mode:
            raise ValueError("Learning source must preserve one KnowledgeMode")
        return self


class ScenarioRangeAnchor(BaseModel):
    """Exact T0 bear/base/bull return range copied from verified Underwriting when applicable."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    currency: CurrencyCode
    reference_price: Decimal = Field(gt=0, allow_inf_nan=False)
    horizon_date: date
    bear_return: Decimal = Field(allow_inf_nan=False)
    base_return: Decimal = Field(allow_inf_nan=False)
    bull_return: Decimal = Field(allow_inf_nan=False)

    @field_validator("reference_price", "bear_return", "base_return", "bull_return")
    @classmethod
    def normalize_decimal(cls, value: Decimal) -> Decimal:
        return canonical_decimal(value)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if not self.bear_return <= self.base_return <= self.bull_return:
            raise ValueError("scenario range requires bear <= base <= bull")
        return self


class DecisionLearningCaseInput(BaseModel):
    """Verified T0/T1 anchors retained before any later outcome is observed."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString = LEARNING_CASE_METHOD_VERSION
    source: LearningSourceReference
    target_instrument_id: NonEmptyString
    target_reference_price: MonetaryAmount
    benchmark_instrument_id: NonEmptyString
    benchmark_reference_price: MonetaryAmount
    evaluation_horizon_date: date
    scenario_range: ScenarioRangeAnchor | None = None
    replacement_source_instrument_id: NonEmptyString | None = None
    replacement_source_reference_price: MonetaryAmount | None = None
    change_conditions: tuple[NonEmptyString, ...] = Field(min_length=1)
    rationale: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=5)
    missing_data: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()

    @field_validator("method_version")
    @classmethod
    def require_method(cls, value: str) -> str:
        if value != LEARNING_CASE_METHOD_VERSION:
            raise ValueError(f"method_version must be {LEARNING_CASE_METHOD_VERSION!r}")
        return value

    @field_validator(
        "change_conditions",
        "rationale",
        "missing_data",
        "conflicts",
        "assumptions",
    )
    @classmethod
    def reject_duplicate_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate Learning case disclosures are not allowed")

    @model_validator(mode="after")
    def validate_case(self) -> Self:
        if self.knowledge_boundary != self.source.execution_boundary:
            raise ValueError("Learning case boundary must equal the verified Execution boundary")
        if self.evaluation_horizon_date <= self.source.decision_boundary.as_of.date():
            raise ValueError("Learning evaluation horizon must follow the capital decision")
        currencies = {
            self.target_reference_price.currency,
            self.benchmark_reference_price.currency,
        }
        if len(currencies) != 1:
            raise ValueError("Learning benchmark comparison requires one native currency")
        if self.target_reference_price.amount <= 0 or self.benchmark_reference_price.amount <= 0:
            raise ValueError("Learning reference prices must be greater than zero")

        replacement_fields = (
            self.replacement_source_instrument_id,
            self.replacement_source_reference_price,
        )
        if self.source.source_kind is LearningSourceKind.REPLACEMENT:
            if any(item is None for item in replacement_fields):
                raise ValueError(
                    "replacement Learning case requires source instrument and T0 price"
                )
            assert self.replacement_source_reference_price is not None
            if (
                self.replacement_source_reference_price.currency
                != self.target_reference_price.currency
            ):
                raise ValueError("replacement source and target must use one native currency")
            if self.replacement_source_reference_price.amount <= 0:
                raise ValueError("replacement source T0 price must be greater than zero")
        elif any(item is not None for item in replacement_fields):
            raise ValueError("new-capital Learning case cannot contain replacement source fields")

        if self.scenario_range is not None:
            if self.scenario_range.currency != self.target_reference_price.currency:
                raise ValueError("scenario range currency must match the target reference price")
            if self.scenario_range.reference_price != self.target_reference_price.amount:
                raise ValueError("scenario range must preserve the exact target reference price")
            if self.scenario_range.horizon_date != self.evaluation_horizon_date:
                raise ValueError("scenario range must preserve the Learning evaluation horizon")
        return self

    @property
    def knowledge_mode(self) -> KnowledgeMode:
        return self.knowledge_boundary.knowledge_mode


class DecisionLearningCase(DecisionLearningCaseInput):
    """Content-addressed Learning anchor opened before T2 outcome evaluation."""

    case_id: UUID
    input_fingerprint: ContentHash


class DecisionLearningCaseReference(BaseModel):
    """Stable case reference retained by each later evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    case_id: UUID
    input_fingerprint: ContentHash
    knowledge_boundary: KnowledgeBoundary


class LearningPriceObservation(BaseModel):
    """One explicit later market price used only for decision-level price-return learning."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    instrument_id: NonEmptyString
    price: MonetaryAmount
    observed_at: AwareDatetime
    available_at: AwareDatetime
    recorded_at: AwareDatetime
    source_reference: NonEmptyString
    source_fingerprint: ContentHash

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if self.price.amount <= 0:
            raise ValueError("Learning price observation must be greater than zero")
        if not self.observed_at <= self.available_at <= self.recorded_at:
            raise ValueError("Learning price requires observed <= available <= recorded")
        return self


class LearningThesisObservation(BaseModel):
    """Later assessment of one exact upstream change condition."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    condition: NonEmptyString
    status: ThesisConditionStatus
    rationale: NonEmptyString
    observed_at: AwareDatetime
    available_at: AwareDatetime
    recorded_at: AwareDatetime
    source_reference: NonEmptyString
    source_fingerprint: ContentHash
    missing_data: tuple[NonEmptyString, ...] = ()

    @field_validator("missing_data")
    @classmethod
    def reject_duplicate_missing(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate thesis-observation missing_data is not allowed")

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if not self.observed_at <= self.available_at <= self.recorded_at:
            raise ValueError(
                "Learning thesis observation requires observed <= available <= recorded"
            )
        if self.status is ThesisConditionStatus.UNKNOWN and not self.missing_data:
            raise ValueError("unknown thesis condition requires missing_data")
        return self


class LearningEvaluationInput(BaseModel):
    """T2 evidence supplied for deterministic decision-level evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString = LEARNING_EVALUATION_METHOD_VERSION
    price_observations: tuple[LearningPriceObservation, ...] = Field(min_length=1)
    thesis_observations: tuple[LearningThesisObservation, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()

    @field_validator("method_version")
    @classmethod
    def require_method(cls, value: str) -> str:
        if value != LEARNING_EVALUATION_METHOD_VERSION:
            raise ValueError(f"method_version must be {LEARNING_EVALUATION_METHOD_VERSION!r}")
        return value

    @field_validator("conflicts", "assumptions")
    @classmethod
    def reject_duplicate_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(
            value,
            "duplicate Learning evaluation disclosures are not allowed",
        )

    @model_validator(mode="after")
    def reject_duplicate_observations(self) -> Self:
        price_keys = tuple(
            (item.instrument_id, item.observed_at) for item in self.price_observations
        )
        _reject_duplicates(price_keys, "duplicate Learning price observations are not allowed")
        conditions = tuple(item.condition for item in self.thesis_observations)
        _reject_duplicates(conditions, "duplicate Learning thesis observations are not allowed")
        return self


class LearningMetrics(BaseModel):
    """Transparent price-return and drawdown components; never a composite score."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    observed_target_return: Decimal = Field(allow_inf_nan=False)
    observed_benchmark_return: Decimal = Field(allow_inf_nan=False)
    observed_excess_return: Decimal = Field(allow_inf_nan=False)
    target_max_drawdown: Decimal = Field(le=0, ge=-1, allow_inf_nan=False)
    replacement_source_return: Decimal | None = Field(default=None, allow_inf_nan=False)
    replacement_excess_vs_source: Decimal | None = Field(default=None, allow_inf_nan=False)

    @field_validator(
        "observed_target_return",
        "observed_benchmark_return",
        "observed_excess_return",
        "target_max_drawdown",
        "replacement_source_return",
        "replacement_excess_vs_source",
    )
    @classmethod
    def normalize_values(cls, value: Decimal | None) -> Decimal | None:
        return None if value is None else canonical_decimal(value)

    @model_validator(mode="after")
    def validate_arithmetic(self) -> Self:
        expected_excess = canonical_decimal(
            self.observed_target_return - self.observed_benchmark_return
        )
        if self.observed_excess_return != expected_excess:
            raise ValueError("Learning excess return must equal target minus benchmark return")
        replacement_values = (
            self.replacement_source_return,
            self.replacement_excess_vs_source,
        )
        if any(item is None for item in replacement_values) and any(
            item is not None for item in replacement_values
        ):
            raise ValueError("replacement Learning metrics must be complete or absent")
        if self.replacement_source_return is not None:
            assert self.replacement_excess_vs_source is not None
            expected_replacement = canonical_decimal(
                self.observed_target_return - self.replacement_source_return
            )
            if self.replacement_excess_vs_source != expected_replacement:
                raise ValueError("replacement excess must equal target minus source return")
        return self


class DecisionLearningEvaluation(LearningEvaluationInput):
    """Content-addressed T2 outcome record with observations needed for canonical replay."""

    evaluation_id: UUID
    input_fingerprint: ContentHash
    case: DecisionLearningCaseReference
    return_basis: LearningReturnBasis = LearningReturnBasis.PRICE_ONLY_FROM_DECISION_REFERENCE
    account_pnl_status: AccountPnlStatus = AccountPnlStatus.NOT_MEASURED_NO_FILL_DATA
    metrics: LearningMetrics
    thesis_outcome: ThesisOutcome
    horizon_reached: bool
    scenario_realization: ScenarioRealizationBand
    end_observation_at: AwareDatetime
    missing_data: tuple[NonEmptyString, ...] = ()

    @field_validator("missing_data")
    @classmethod
    def reject_duplicate_output_missing(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate Learning evaluation missing_data")

    @model_validator(mode="after")
    def validate_evaluation(self) -> Self:
        if self.knowledge_boundary.as_of < self.case.knowledge_boundary.as_of:
            raise ValueError("Learning evaluation requires T2 >= T1")
        if (
            self.knowledge_boundary.knowledge_mode
            is not self.case.knowledge_boundary.knowledge_mode
        ):
            raise ValueError("Learning evaluation must preserve one KnowledgeMode")
        if self.end_observation_at > self.knowledge_boundary.as_of:
            raise ValueError("Learning end observation cannot be in the future")
        if not self.horizon_reached and self.scenario_realization not in {
            ScenarioRealizationBand.PRE_HORIZON,
            ScenarioRealizationBand.NOT_AVAILABLE,
        }:
            raise ValueError("pre-horizon Learning cannot claim a matured scenario band")
        return self
