"""Explicit Portfolio Fit and marginal-capital decision contracts for Chapter 6C1."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from asymmetric_engine.domain.evidence import ConfidenceCalibrationStatus
from asymmetric_engine.domain.evidence.models import ContentHash, NonEmptyString
from asymmetric_engine.domain.evidence.source_documents import SubjectId
from asymmetric_engine.domain.financial import CurrencyCode, MonetaryAmount, canonical_decimal
from asymmetric_engine.domain.portfolio.exposure import (
    ExposureRatio,
    HHIBounds,
    PortfolioStateReference,
)
from asymmetric_engine.domain.portfolio.models import PortfolioObjectId
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode

PORTFOLIO_FIT_METHOD_VERSION = "portfolio-fit-v1"
MARGINAL_DECISION_METHOD_VERSION = "marginal-decision-v1"
POSITION_REVIEW_METHOD_VERSION = "position-review-v1"

CANDIDATE_ALTERNATIVE_ID = "alternative:candidate-equity"
EXISTING_HOLDING_ALTERNATIVE_ID = "alternative:existing-holding"
CORE_ETF_ALTERNATIVE_ID = "alternative:core-etf"
INVESTMENT_CASH_ALTERNATIVE_ID = "alternative:investment-cash"
REQUIRED_ALTERNATIVE_IDS = frozenset(
    {
        CANDIDATE_ALTERNATIVE_ID,
        EXISTING_HOLDING_ALTERNATIVE_ID,
        CORE_ETF_ALTERNATIVE_ID,
        INVESTMENT_CASH_ALTERNATIVE_ID,
    }
)


def _reject_duplicates[T](values: tuple[T, ...], message: str) -> tuple[T, ...]:
    if len(values) != len(set(values)):
        raise ValueError(message)
    return values


def _normalize_ratio(value: Decimal) -> Decimal:
    return canonical_decimal(value)


class CapitalAlternativeKind(StrEnum):
    """The four mandatory uses of one explicit unit of new capital."""

    CANDIDATE_EQUITY = "candidate_equity"
    EXISTING_HOLDING = "existing_holding"
    CORE_ETF = "core_etf"
    INVESTMENT_CASH = "investment_cash"


class MarginalDecisionOutcome(StrEnum):
    """New-capital outcomes; HOLD belongs to a separate no-new-capital review."""

    ALLOCATE = "allocate"
    NO_ALLOCATION = "no_allocation"


class PositionReviewOutcome(StrEnum):
    """The only Chapter 6C1 existing-position outcome before replacement is admitted."""

    HOLD = "hold"


class PermanentLossClass(StrEnum):
    """Ordinal, uncalibrated permanent-loss judgement retained as a visible component."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNKNOWN = "unknown"


class TradeOffDimension(StrEnum):
    """Non-interchangeable comparison components; they are never averaged."""

    STANDALONE_CASE = "standalone_case"
    PERMANENT_LOSS = "permanent_loss"
    PORTFOLIO_EFFECT = "portfolio_effect"
    UNCERTAINTY = "uncertainty"


class ComponentPreference(StrEnum):
    """Direction of one explicit component in a pairwise comparison."""

    FIRST = "first"
    SECOND = "second"
    BALANCED = "balanced"
    UNKNOWN = "unknown"


class PairwiseConclusion(StrEnum):
    """Overall qualitative conclusion; no numerical utility is implied."""

    FIRST = "first"
    SECOND = "second"
    INDETERMINATE = "indeterminate"


class DecisionConfidenceLevel(StrEnum):
    """Qualitative decision support, deliberately not a numerical probability."""

    SUPPORTED = "supported"
    CONDITIONAL = "conditional"
    INSUFFICIENT = "insufficient"


class FitExposureDimension(StrEnum):
    """Inspectable before/after components emitted by Portfolio Fit."""

    INSTRUMENT = "instrument"
    COMPANY = "company"
    SECTOR = "sector"
    GEOGRAPHY = "geography"
    ECONOMIC_DRIVER = "economic_driver"
    UNRESOLVED = "unresolved"


class FitDerivationKind(StrEnum):
    """How an alternative's descriptive exposure effect was obtained."""

    PROSPECTIVE_DIRECT_EQUITY = "prospective_direct_equity"
    VERIFIED_PORTFOLIO_EXPOSURE = "verified_portfolio_exposure"
    UNCHANGED_INVESTMENT_CASH = "unchanged_investment_cash"


class DecisionBasis(StrEnum):
    """The transparent policy that produced the new-capital outcome."""

    UNIQUE_PAIRWISE_DOMINANCE = "unique_pairwise_dominance"
    CONSERVATIVE_CASH_DEFAULT = "conservative_cash_default"


class CapitalUnit(BaseModel):
    """One disclosed amount evaluated identically across every alternative."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    amount: MonetaryAmount
    funding_cash_ids: tuple[PortfolioObjectId, ...] = Field(min_length=1)
    rationale: NonEmptyString

    @field_validator("funding_cash_ids")
    @classmethod
    def reject_duplicate_cash_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate funding cash ids are not allowed")

    @model_validator(mode="after")
    def require_positive_amount(self) -> Self:
        if self.amount.amount == 0:
            raise ValueError("capital unit must be greater than zero")
        return self


class CandidateEquityInstrument(BaseModel):
    """External listed-equity identity tied to the Opportunity State's market fact."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    instrument_id: PortfolioObjectId
    symbol: NonEmptyString
    name: NonEmptyString
    listing_venue: NonEmptyString
    native_currency: CurrencyCode
    company_subject_id: SubjectId
    reference_price: MonetaryAmount
    reference_price_date: date
    reference_price_fact_id: NonEmptyString

    @model_validator(mode="after")
    def require_native_reference_currency(self) -> Self:
        if self.reference_price.currency != self.native_currency:
            raise ValueError("candidate reference price must use the instrument native currency")
        if self.reference_price.amount == 0:
            raise ValueError("candidate reference price must be greater than zero")
        return self


class DecisionConfidence(BaseModel):
    """Visible qualitative confidence that cannot become an allocation weight."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    level: DecisionConfidenceLevel
    rationale: NonEmptyString
    calibration_status: ConfidenceCalibrationStatus = ConfidenceCalibrationStatus.UNCALIBRATED

    @model_validator(mode="after")
    def reject_false_calibration(self) -> Self:
        if self.calibration_status is not ConfidenceCalibrationStatus.UNCALIBRATED:
            raise ValueError("Chapter 6C1 decision confidence must remain uncalibrated")
        return self


class PermanentLossAssessment(BaseModel):
    """One explained ordinal judgement; it is not a probability or automatic gate."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    alternative_id: PortfolioObjectId
    risk_class: PermanentLossClass
    rationale: NonEmptyString
    supporting_risk_ids: tuple[NonEmptyString, ...] = ()
    missing_data: tuple[NonEmptyString, ...] = ()

    @field_validator("supporting_risk_ids", "missing_data")
    @classmethod
    def reject_duplicate_entries(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate permanent-loss entries are not allowed")

    @model_validator(mode="after")
    def require_unknown_disclosure(self) -> Self:
        if self.risk_class is PermanentLossClass.UNKNOWN and not self.missing_data:
            raise ValueError("unknown permanent-loss class requires missing_data")
        return self


class TradeOffComponent(BaseModel):
    """One inspectable component of a pairwise capital comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    dimension: TradeOffDimension
    preference: ComponentPreference
    rationale: NonEmptyString
    missing_data: tuple[NonEmptyString, ...] = ()

    @field_validator("missing_data")
    @classmethod
    def reject_duplicate_missing_data(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate trade-off missing_data is not allowed")

    @model_validator(mode="after")
    def require_unknown_disclosure(self) -> Self:
        if self.preference is ComponentPreference.UNKNOWN and not self.missing_data:
            raise ValueError("unknown trade-off component requires missing_data")
        return self


class PairwiseCapitalComparison(BaseModel):
    """A complete qualitative comparison of two alternatives without weighted scoring."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    first_alternative_id: PortfolioObjectId
    second_alternative_id: PortfolioObjectId
    components: tuple[TradeOffComponent, ...] = Field(min_length=4, max_length=4)
    conclusion: PairwiseConclusion
    rationale: NonEmptyString

    @model_validator(mode="after")
    def validate_comparison(self) -> Self:
        if self.first_alternative_id == self.second_alternative_id:
            raise ValueError("pairwise comparison requires two different alternatives")
        dimensions = tuple(item.dimension for item in self.components)
        _reject_duplicates(dimensions, "duplicate trade-off dimensions are not allowed")
        if set(dimensions) != set(TradeOffDimension):
            raise ValueError("pairwise comparison requires every trade-off dimension")
        preferences = {item.preference for item in self.components}
        if (
            self.conclusion is PairwiseConclusion.FIRST
            and ComponentPreference.FIRST not in preferences
        ):
            raise ValueError("first conclusion requires at least one supporting component")
        if (
            self.conclusion is PairwiseConclusion.SECOND
            and ComponentPreference.SECOND not in preferences
        ):
            raise ValueError("second conclusion requires at least one supporting component")
        if self.conclusion is PairwiseConclusion.INDETERMINATE and preferences in (
            {ComponentPreference.FIRST},
            {ComponentPreference.SECOND},
        ):
            raise ValueError("uniform directional components cannot be declared indeterminate")
        return self


class WeightDelta(BaseModel):
    """One changed weight; overlapping driver deltas remain explicitly non-additive."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    dimension: FitExposureDimension
    component_id: PortfolioObjectId
    before_weight: ExposureRatio
    after_weight: ExposureRatio
    is_non_additive: bool = False

    @field_validator("before_weight", "after_weight")
    @classmethod
    def normalize_weights(cls, value: Decimal) -> Decimal:
        return _normalize_ratio(value)

    @model_validator(mode="after")
    def validate_driver_flag(self) -> Self:
        expected = self.dimension is FitExposureDimension.ECONOMIC_DRIVER
        if self.is_non_additive is not expected:
            raise ValueError("only economic-driver deltas may be non-additive")
        if self.before_weight == self.after_weight:
            raise ValueError("Portfolio Fit emits only changed weights")
        return self


class FitCurrencyEffect(BaseModel):
    """Before/after effect for one unconverted capital currency."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    currency: CurrencyCode
    gross_value_before: MonetaryAmount
    gross_value_after: MonetaryAmount
    company_hhi_before: HHIBounds
    company_hhi_after: HHIBounds
    weight_deltas: tuple[WeightDelta, ...] = ()

    @model_validator(mode="after")
    def validate_effect(self) -> Self:
        if {
            self.gross_value_before.currency,
            self.gross_value_after.currency,
        } != {self.currency}:
            raise ValueError("Portfolio Fit values must match the currency effect")
        identities = tuple((item.dimension, item.component_id) for item in self.weight_deltas)
        _reject_duplicates(identities, "duplicate Portfolio Fit weight deltas are not allowed")
        return self


class OpportunityStateReference(BaseModel):
    """Immutable reference to verified standalone Underwriting; the payload is not copied."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    opportunity_id: UUID
    candidate_id: SubjectId
    input_fingerprint: ContentHash
    knowledge_boundary: KnowledgeBoundary


class PortfolioExposureReference(BaseModel):
    """Immutable reference to a verified descriptive exposure state."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    exposure_id: UUID
    input_fingerprint: ContentHash
    knowledge_boundary: KnowledgeBoundary


class CapitalAlternative(BaseModel):
    """One evaluated use of the exact same capital unit."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    alternative_id: PortfolioObjectId
    kind: CapitalAlternativeKind
    label: NonEmptyString
    amount: MonetaryAmount
    rationale: NonEmptyString
    instrument_id: PortfolioObjectId | None = None
    position_id: PortfolioObjectId | None = None
    opportunity_id: UUID | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if self.amount.amount == 0:
            raise ValueError("capital alternative amount must be greater than zero")
        if self.kind is CapitalAlternativeKind.CANDIDATE_EQUITY:
            if self.instrument_id is None or self.opportunity_id is None or self.position_id:
                raise ValueError("candidate alternative requires instrument and opportunity only")
        elif self.kind is CapitalAlternativeKind.EXISTING_HOLDING:
            if self.instrument_id is None or self.position_id is None or self.opportunity_id:
                raise ValueError("existing holding requires instrument and position only")
        elif self.kind is CapitalAlternativeKind.CORE_ETF:
            if self.instrument_id is None or self.position_id or self.opportunity_id:
                raise ValueError("core ETF alternative requires only an instrument")
        elif any((self.instrument_id, self.position_id, self.opportunity_id)):
            raise ValueError(
                "investment cash cannot reference instrument, position, or opportunity"
            )
        return self


class PortfolioFit(BaseModel):
    """Content-addressed interaction view; it contains no capital preference or score."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    fit_id: UUID
    input_fingerprint: ContentHash
    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString
    derivation_kind: FitDerivationKind
    portfolio_state: PortfolioStateReference
    base_exposure: PortfolioExposureReference
    alternative_exposure: PortfolioExposureReference | None = None
    opportunity_state: OpportunityStateReference | None = None
    alternative: CapitalAlternative
    effect: FitCurrencyEffect
    missing_data: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()

    @field_validator("missing_data", "conflicts", "assumptions")
    @classmethod
    def reject_duplicate_disclosures(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate Portfolio Fit disclosures are not allowed")

    @model_validator(mode="after")
    def validate_fit(self) -> Self:
        if self.method_version != PORTFOLIO_FIT_METHOD_VERSION:
            raise ValueError("Portfolio Fit uses an unrecognized method version")
        boundaries = {
            self.knowledge_boundary,
            self.portfolio_state.knowledge_boundary,
            self.base_exposure.knowledge_boundary,
        }
        if self.alternative_exposure is not None:
            boundaries.add(self.alternative_exposure.knowledge_boundary)
        if self.opportunity_state is not None:
            boundaries.add(self.opportunity_state.knowledge_boundary)
        if len(boundaries) != 1:
            raise ValueError("Portfolio Fit must preserve one canonical knowledge boundary")
        if self.effect.currency != self.alternative.amount.currency:
            raise ValueError("Portfolio Fit effect must use the alternative capital currency")
        if self.derivation_kind is FitDerivationKind.PROSPECTIVE_DIRECT_EQUITY:
            if self.opportunity_state is None or self.alternative_exposure is not None:
                raise ValueError(
                    "prospective equity fit requires Opportunity but no exposure after"
                )
        elif self.derivation_kind is FitDerivationKind.VERIFIED_PORTFOLIO_EXPOSURE:
            if self.alternative_exposure is None or self.opportunity_state is not None:
                raise ValueError("verified exposure fit requires an after exposure only")
        elif self.alternative_exposure is not None or self.opportunity_state is not None:
            raise ValueError("cash fit cannot reference Opportunity or an after exposure")
        return self

    @property
    def as_of(self) -> datetime:
        return self.knowledge_boundary.as_of

    @property
    def knowledge_mode(self) -> KnowledgeMode:
        return self.knowledge_boundary.knowledge_mode


class PortfolioFitReference(BaseModel):
    """Stable reference consumed by Marginal Allocation."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    fit_id: UUID
    alternative_id: PortfolioObjectId
    input_fingerprint: ContentHash


class MarginalDecisionInput(BaseModel):
    """Explicit new-capital policy input before canonical derivation and addressing."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString = MARGINAL_DECISION_METHOD_VERSION
    capital_unit: CapitalUnit
    candidate_instrument: CandidateEquityInstrument
    existing_position_id: PortfolioObjectId
    permanent_loss_assessments: tuple[PermanentLossAssessment, ...] = Field(
        min_length=4, max_length=4
    )
    comparisons: tuple[PairwiseCapitalComparison, ...] = Field(min_length=6, max_length=6)
    best_rejected_alternative_id: PortfolioObjectId | None = None
    decision_rationale: tuple[NonEmptyString, ...] = Field(min_length=3, max_length=5)
    main_risks_and_unknowns: tuple[NonEmptyString, ...] = Field(min_length=1)
    change_conditions: tuple[NonEmptyString, ...] = Field(min_length=1)
    confidence: DecisionConfidence
    missing_data: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()

    @field_validator("method_version")
    @classmethod
    def require_admitted_method(cls, value: str) -> str:
        if value != MARGINAL_DECISION_METHOD_VERSION:
            raise ValueError(f"method_version must be {MARGINAL_DECISION_METHOD_VERSION!r}")
        return value

    @field_validator(
        "decision_rationale",
        "main_risks_and_unknowns",
        "change_conditions",
        "missing_data",
        "conflicts",
        "assumptions",
    )
    @classmethod
    def reject_duplicate_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate decision disclosures are not allowed")

    @model_validator(mode="after")
    def validate_complete_competition(self) -> Self:
        assessments = tuple(item.alternative_id for item in self.permanent_loss_assessments)
        _reject_duplicates(assessments, "duplicate permanent-loss alternatives are not allowed")
        if set(assessments) != REQUIRED_ALTERNATIVE_IDS:
            raise ValueError("permanent-loss assessments must cover all four alternatives")

        pairs: set[frozenset[str]] = set()
        for comparison in self.comparisons:
            pair = frozenset({comparison.first_alternative_id, comparison.second_alternative_id})
            if not pair.issubset(REQUIRED_ALTERNATIVE_IDS):
                raise ValueError("comparison references an unknown capital alternative")
            if pair in pairs:
                raise ValueError("duplicate pairwise capital comparison is not allowed")
            pairs.add(pair)
        expected_pairs = {
            frozenset({first, second})
            for index, first in enumerate(sorted(REQUIRED_ALTERNATIVE_IDS))
            for second in sorted(REQUIRED_ALTERNATIVE_IDS)[index + 1 :]
        }
        if pairs != expected_pairs:
            raise ValueError("comparisons must cover every unordered alternative pair")
        if (
            self.best_rejected_alternative_id is not None
            and self.best_rejected_alternative_id not in REQUIRED_ALTERNATIVE_IDS
        ):
            raise ValueError("best rejected alternative references an unknown alternative")
        return self


class MarginalDecision(MarginalDecisionInput):
    """Content-addressed decision from complete pairwise competition for one capital unit."""

    decision_id: UUID
    input_fingerprint: ContentHash
    portfolio_state: PortfolioStateReference
    opportunity_state: OpportunityStateReference
    alternatives: tuple[CapitalAlternative, ...] = Field(min_length=4, max_length=4)
    portfolio_fits: tuple[PortfolioFitReference, ...] = Field(min_length=4, max_length=4)
    outcome: MarginalDecisionOutcome
    selected_alternative_id: PortfolioObjectId
    dominance_winner_id: PortfolioObjectId | None = None
    decision_basis: DecisionBasis

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        alternative_ids = tuple(item.alternative_id for item in self.alternatives)
        fit_ids = tuple(item.alternative_id for item in self.portfolio_fits)
        _reject_duplicates(alternative_ids, "duplicate capital alternatives are not allowed")
        _reject_duplicates(fit_ids, "duplicate Portfolio Fit alternatives are not allowed")
        if (
            set(alternative_ids) != REQUIRED_ALTERNATIVE_IDS
            or set(fit_ids) != REQUIRED_ALTERNATIVE_IDS
        ):
            raise ValueError("decision must preserve all four alternatives and Portfolio Fits")
        if any(item.amount != self.capital_unit.amount for item in self.alternatives):
            raise ValueError("every alternative must evaluate the exact capital unit")
        if self.portfolio_state.knowledge_boundary != self.knowledge_boundary:
            raise ValueError("decision must preserve the Portfolio State boundary")
        if self.opportunity_state.knowledge_boundary != self.knowledge_boundary:
            raise ValueError("decision must preserve the Opportunity State boundary")
        if self.outcome is MarginalDecisionOutcome.ALLOCATE:
            if self.selected_alternative_id == INVESTMENT_CASH_ALTERNATIVE_ID:
                raise ValueError("ALLOCATE must select a non-cash alternative")
            if self.dominance_winner_id != self.selected_alternative_id:
                raise ValueError("ALLOCATE requires the unique dominance winner")
            if self.decision_basis is not DecisionBasis.UNIQUE_PAIRWISE_DOMINANCE:
                raise ValueError("ALLOCATE requires unique pairwise dominance")
        else:
            if self.selected_alternative_id != INVESTMENT_CASH_ALTERNATIVE_ID:
                raise ValueError("NO_ALLOCATION must preserve the capital unit as cash")
            if self.dominance_winner_id not in (None, INVESTMENT_CASH_ALTERNATIVE_ID):
                raise ValueError("NO_ALLOCATION cannot ignore a dominant non-cash alternative")
            if self.decision_basis is not DecisionBasis.CONSERVATIVE_CASH_DEFAULT:
                raise ValueError("NO_ALLOCATION requires the conservative cash default")
        if self.best_rejected_alternative_id == self.selected_alternative_id:
            raise ValueError("best rejected alternative must differ from the selected outcome")
        return self

    @property
    def as_of(self) -> datetime:
        return self.knowledge_boundary.as_of

    @property
    def knowledge_mode(self) -> KnowledgeMode:
        return self.knowledge_boundary.knowledge_mode


class PositionReviewInput(BaseModel):
    """No-new-capital review input that cannot become replacement or execution."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString = POSITION_REVIEW_METHOD_VERSION
    position_id: PortfolioObjectId
    rationale: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=5)
    main_risks_and_unknowns: tuple[NonEmptyString, ...] = Field(min_length=1)
    change_conditions: tuple[NonEmptyString, ...] = Field(min_length=1)
    confidence: DecisionConfidence
    missing_data: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()

    @field_validator("method_version")
    @classmethod
    def require_admitted_method(cls, value: str) -> str:
        if value != POSITION_REVIEW_METHOD_VERSION:
            raise ValueError(f"method_version must be {POSITION_REVIEW_METHOD_VERSION!r}")
        return value

    @field_validator(
        "rationale",
        "main_risks_and_unknowns",
        "change_conditions",
        "missing_data",
        "conflicts",
        "assumptions",
    )
    @classmethod
    def reject_duplicate_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate position-review disclosures are not allowed")


class PositionReview(PositionReviewInput):
    """Content-addressed HOLD record with no allocation or disposal authority."""

    review_id: UUID
    input_fingerprint: ContentHash
    portfolio_state: PortfolioStateReference
    base_exposure: PortfolioExposureReference
    outcome: PositionReviewOutcome = PositionReviewOutcome.HOLD

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        if self.portfolio_state.knowledge_boundary != self.knowledge_boundary:
            raise ValueError("position review must preserve the Portfolio State boundary")
        if self.base_exposure.knowledge_boundary != self.knowledge_boundary:
            raise ValueError("position review must preserve the Exposure boundary")
        if self.outcome is not PositionReviewOutcome.HOLD:
            raise ValueError("Chapter 6C1 position review may emit HOLD only")
        return self
