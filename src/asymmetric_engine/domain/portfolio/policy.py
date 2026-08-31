"""Portfolio Decision policies and after-friction replacement contracts for Chapter 6C2."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from asymmetric_engine.domain.evidence.models import ContentHash, NonEmptyString
from asymmetric_engine.domain.financial import CurrencyCode, MonetaryAmount, canonical_decimal
from asymmetric_engine.domain.portfolio.decision import (
    INVESTMENT_CASH_ALTERNATIVE_ID,
    CandidateEquityInstrument,
    DecisionConfidence,
    OpportunityStateReference,
    PairwiseCapitalComparison,
    PortfolioExposureReference,
)
from asymmetric_engine.domain.portfolio.exposure import PortfolioStateReference
from asymmetric_engine.domain.portfolio.models import PortfolioObjectId, TaxTreatment
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode

OWNER_PORTFOLIO_POLICY_METHOD_VERSION = "owner-portfolio-policy-v1"
POLICY_CONSTRAINED_DECISION_METHOD_VERSION = "policy-constrained-decision-v1"
REPLACEMENT_DECISION_METHOD_VERSION = "replacement-decision-v1"


class FundingPriority(StrEnum):
    """Capital-flow policy; replacement is considered only after investable cash."""

    NEW_CAPITAL_FIRST = "new_capital_first"


class PositionCapitalStatus(StrEnum):
    """Owner-declared lifecycle state for an existing position."""

    STANDARD = "standard"
    LEGACY_HOLD_ZERO_NEW_CAPITAL = "legacy_hold_zero_new_capital"
    RUNNER = "runner"


class NewCapitalEligibility(StrEnum):
    """Whether a position may compete for incremental capital."""

    ELIGIBLE = "eligible"
    ZERO_NEW_CAPITAL = "zero_new_capital"


class RunnerCapitalBasis(StrEnum):
    """Runner opportunity cost is current market value, never recovered historical cost."""

    CURRENT_MARKET_VALUE = "current_market_value"


class RatioConstraintKind(StrEnum):
    """Simple owner-defined concentration limits, never optimization targets."""

    MAX_COMPANY_WEIGHT = "max_company_weight"
    MAX_COMPANY_HHI_UPPER_BOUND = "max_company_hhi_upper_bound"
    MAX_ECONOMIC_DRIVER_WEIGHT = "max_economic_driver_weight"


class PolicyDecisionOutcome(StrEnum):
    """Final new-capital outcome after explicit owner policy is applied."""

    ALLOCATE = "allocate"
    NO_ALLOCATION = "no_allocation"


class PolicyDecisionBasis(StrEnum):
    """Transparent policy basis with no hidden weighted score."""

    POLICY_FILTERED_DOMINANCE = "policy_filtered_dominance"
    CONSERVATIVE_CASH_DEFAULT = "conservative_cash_default"


class FrictionCostKind(StrEnum):
    """Basic switching costs admitted in the replacement MVP."""

    TAX = "tax"
    FEE = "fee"
    SPREAD = "spread"


class FrictionEstimateStatus(StrEnum):
    """Whether a friction amount is usable at T0."""

    KNOWN = "known"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class LiquidityStatus(StrEnum):
    """Ordinal liquidity state; it is not a market-timing or execution score."""

    ADEQUATE = "adequate"
    CONSTRAINED = "constrained"
    UNKNOWN = "unknown"


class ReplacementTargetKind(StrEnum):
    """Admitted destination types for one explicit replacement proposal."""

    CANDIDATE_EQUITY = "candidate_equity"
    EXISTING_HOLDING = "existing_holding"
    CORE_ETF = "core_etf"


class ReplacementPreference(StrEnum):
    """Qualitative after-friction conclusion without numerical utility."""

    SOURCE = "source"
    TARGET = "target"
    INDETERMINATE = "indeterminate"


class ReplacementOutcome(StrEnum):
    """Replacement either clears every gate or the source remains held."""

    REPLACE = "replace"
    HOLD = "hold"


class ReplacementDecisionBasis(StrEnum):
    """Reason the replacement policy produced its outcome."""

    AFTER_FRICTION_TARGET_DOMINANCE = "after_friction_target_dominance"
    NEW_CAPITAL_FIRST = "new_capital_first"
    POLICY_BLOCK = "policy_block"
    FRICTION_UNKNOWN = "friction_unknown"
    LIQUIDITY_UNRESOLVED = "liquidity_unresolved"
    SOURCE_NOT_OUTCLASSED = "source_not_outclassed"


def _reject_duplicates[T](values: tuple[T, ...], message: str) -> tuple[T, ...]:
    if len(values) != len(set(values)):
        raise ValueError(message)
    return values


class PositionCapitalPolicy(BaseModel):
    """Lifecycle policy kept separate from factual Portfolio State."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    position_id: PortfolioObjectId
    status: PositionCapitalStatus
    new_capital_eligibility: NewCapitalEligibility
    rationale: NonEmptyString
    change_conditions: tuple[NonEmptyString, ...] = Field(min_length=1)
    recovered_proceeds: MonetaryAmount | None = None
    runner_capital_basis: RunnerCapitalBasis | None = None

    @field_validator("change_conditions")
    @classmethod
    def reject_duplicate_conditions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(
            value, "duplicate position-policy change conditions are not allowed"
        )

    @model_validator(mode="after")
    def validate_position_policy(self) -> Self:
        if self.status is PositionCapitalStatus.STANDARD:
            if self.new_capital_eligibility is not NewCapitalEligibility.ELIGIBLE:
                raise ValueError("standard position policy must remain eligible for new capital")
            if self.recovered_proceeds is not None or self.runner_capital_basis is not None:
                raise ValueError("standard position policy cannot contain Runner fields")
        elif self.status is PositionCapitalStatus.LEGACY_HOLD_ZERO_NEW_CAPITAL:
            if self.new_capital_eligibility is not NewCapitalEligibility.ZERO_NEW_CAPITAL:
                raise ValueError("legacy holding must enforce zero new capital")
            if self.recovered_proceeds is not None or self.runner_capital_basis is not None:
                raise ValueError("legacy holding cannot contain Runner fields")
        else:
            if self.recovered_proceeds is None or self.recovered_proceeds.amount == 0:
                raise ValueError("Runner state requires positive recovered proceeds")
            if self.runner_capital_basis is not RunnerCapitalBasis.CURRENT_MARKET_VALUE:
                raise ValueError("Runner state must use current market value as opportunity cost")
        return self

    @property
    def allows_new_capital(self) -> bool:
        return self.new_capital_eligibility is NewCapitalEligibility.ELIGIBLE


class RatioConstraint(BaseModel):
    """One maximum ratio selected by the owner; it is a gate, not a target weight."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    kind: RatioConstraintKind
    maximum: Decimal = Field(gt=0, le=1, allow_inf_nan=False)
    rationale: NonEmptyString

    @field_validator("maximum")
    @classmethod
    def normalize_ratio(cls, value: Decimal) -> Decimal:
        return canonical_decimal(value)


class OwnerPortfolioPolicyInput(BaseModel):
    """Explicit owner policy used by 6C2 without deriving a position size."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString = OWNER_PORTFOLIO_POLICY_METHOD_VERSION
    funding_priority: FundingPriority = FundingPriority.NEW_CAPITAL_FIRST
    max_capital_unit: MonetaryAmount | None = None
    ratio_constraints: tuple[RatioConstraint, ...] = ()
    position_policies: tuple[PositionCapitalPolicy, ...] = ()
    rationale: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=5)
    assumptions: tuple[NonEmptyString, ...] = ()

    @field_validator("method_version")
    @classmethod
    def require_method(cls, value: str) -> str:
        if value != OWNER_PORTFOLIO_POLICY_METHOD_VERSION:
            raise ValueError(f"method_version must be {OWNER_PORTFOLIO_POLICY_METHOD_VERSION!r}")
        return value

    @field_validator("rationale", "assumptions")
    @classmethod
    def reject_duplicate_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate owner-policy text is not allowed")

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        kinds = tuple(item.kind for item in self.ratio_constraints)
        _reject_duplicates(kinds, "duplicate owner ratio constraints are not allowed")
        positions = tuple(item.position_id for item in self.position_policies)
        _reject_duplicates(positions, "duplicate position policies are not allowed")
        if self.max_capital_unit is not None and self.max_capital_unit.amount == 0:
            raise ValueError("max_capital_unit must be greater than zero")
        return self


class OwnerPortfolioPolicy(OwnerPortfolioPolicyInput):
    """Content-addressed owner policy at one knowledge boundary."""

    policy_id: UUID
    input_fingerprint: ContentHash

    @property
    def as_of(self) -> datetime:
        return self.knowledge_boundary.as_of

    @property
    def knowledge_mode(self) -> KnowledgeMode:
        return self.knowledge_boundary.knowledge_mode


class OwnerPortfolioPolicyReference(BaseModel):
    """Stable reference retained by downstream Portfolio Decision records."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    policy_id: UUID
    input_fingerprint: ContentHash
    knowledge_boundary: KnowledgeBoundary


class AlternativePolicyBlock(BaseModel):
    """Explain why a non-cash alternative cannot receive the evaluated unit."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    alternative_id: PortfolioObjectId
    reasons: tuple[NonEmptyString, ...] = Field(min_length=1)

    @field_validator("reasons")
    @classmethod
    def reject_duplicate_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate policy-block reasons are not allowed")


class PolicyConstrainedMarginalDecision(BaseModel):
    """6C1 competition after owner policy removes inadmissible uses of new capital."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    policy_decision_id: UUID
    input_fingerprint: ContentHash
    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString = POLICY_CONSTRAINED_DECISION_METHOD_VERSION
    source_decision_id: UUID
    source_decision_fingerprint: ContentHash
    policy: OwnerPortfolioPolicyReference
    eligible_alternative_ids: tuple[PortfolioObjectId, ...] = Field(min_length=1)
    blocked_alternatives: tuple[AlternativePolicyBlock, ...] = ()
    outcome: PolicyDecisionOutcome
    selected_alternative_id: PortfolioObjectId
    dominance_winner_id: PortfolioObjectId | None
    decision_basis: PolicyDecisionBasis

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        if self.method_version != POLICY_CONSTRAINED_DECISION_METHOD_VERSION:
            raise ValueError("policy-constrained decision uses an unrecognized method version")
        _reject_duplicates(
            self.eligible_alternative_ids,
            "duplicate eligible alternatives are not allowed",
        )
        blocked_ids = tuple(item.alternative_id for item in self.blocked_alternatives)
        _reject_duplicates(blocked_ids, "duplicate blocked alternatives are not allowed")
        if set(blocked_ids) & set(self.eligible_alternative_ids):
            raise ValueError("an alternative cannot be both eligible and policy-blocked")
        if self.policy.knowledge_boundary != self.knowledge_boundary:
            raise ValueError("policy-constrained decision must preserve the policy boundary")
        if self.outcome is PolicyDecisionOutcome.ALLOCATE:
            if self.selected_alternative_id not in self.eligible_alternative_ids:
                raise ValueError("ALLOCATE must select an eligible alternative")
            if self.dominance_winner_id != self.selected_alternative_id:
                raise ValueError("ALLOCATE requires the policy-filtered dominance winner")
            if self.decision_basis is not PolicyDecisionBasis.POLICY_FILTERED_DOMINANCE:
                raise ValueError("ALLOCATE requires policy-filtered dominance")
        else:
            if self.selected_alternative_id != INVESTMENT_CASH_ALTERNATIVE_ID:
                raise ValueError("NO_ALLOCATION must preserve the capital unit as investment cash")
            if INVESTMENT_CASH_ALTERNATIVE_ID not in self.eligible_alternative_ids:
                raise ValueError("investment cash must remain an eligible fallback")
            if self.dominance_winner_id not in (None, INVESTMENT_CASH_ALTERNATIVE_ID):
                raise ValueError(
                    "NO_ALLOCATION cannot ignore an eligible non-cash dominance winner"
                )
            if self.decision_basis is not PolicyDecisionBasis.CONSERVATIVE_CASH_DEFAULT:
                raise ValueError("NO_ALLOCATION requires conservative cash default")
        return self


class FrictionCostEstimate(BaseModel):
    """One explicit tax, fee, or spread estimate with unknown kept visible."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    kind: FrictionCostKind
    status: FrictionEstimateStatus
    amount: MonetaryAmount | None = None
    rationale: NonEmptyString
    missing_data: tuple[NonEmptyString, ...] = ()

    @field_validator("missing_data")
    @classmethod
    def reject_duplicate_missing(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate friction missing_data is not allowed")

    @model_validator(mode="after")
    def validate_estimate(self) -> Self:
        if self.status is FrictionEstimateStatus.KNOWN:
            if self.amount is None:
                raise ValueError("known friction requires an amount")
        elif self.status is FrictionEstimateStatus.NOT_APPLICABLE:
            if self.amount is not None:
                raise ValueError("not-applicable friction cannot contain an amount")
        else:
            if self.amount is not None:
                raise ValueError("unknown friction cannot contain a guessed amount")
            if not self.missing_data:
                raise ValueError("unknown friction requires missing_data")
        return self


class LiquidityAssessment(BaseModel):
    """Visible liquidity condition used only by replacement policy in Chapter 6C2."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    status: LiquidityStatus
    rationale: NonEmptyString
    missing_data: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def require_unknown_disclosure(self) -> Self:
        if self.status is LiquidityStatus.UNKNOWN and not self.missing_data:
            raise ValueError("unknown liquidity requires missing_data")
        return self


class ReplacementFriction(BaseModel):
    """Basic switching friction kept as separate inspectable components."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    costs: tuple[FrictionCostEstimate, ...] = Field(min_length=3, max_length=3)
    liquidity: LiquidityAssessment

    @model_validator(mode="after")
    def require_all_cost_kinds(self) -> Self:
        kinds = tuple(item.kind for item in self.costs)
        _reject_duplicates(kinds, "duplicate replacement friction kinds are not allowed")
        if set(kinds) != set(FrictionCostKind):
            raise ValueError("replacement friction requires tax, fee, and spread estimates")
        return self

    @property
    def is_complete(self) -> bool:
        return all(item.status is not FrictionEstimateStatus.UNKNOWN for item in self.costs)


class ReplacementTarget(BaseModel):
    """Named destination for one explicit replacement proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    target_id: PortfolioObjectId
    kind: ReplacementTargetKind
    label: NonEmptyString
    instrument_id: PortfolioObjectId
    native_currency: CurrencyCode
    position_id: PortfolioObjectId | None = None
    opportunity_id: UUID | None = None

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if self.kind is ReplacementTargetKind.CANDIDATE_EQUITY:
            if self.opportunity_id is None or self.position_id is not None:
                raise ValueError("candidate replacement target requires Opportunity only")
        elif self.kind is ReplacementTargetKind.EXISTING_HOLDING:
            if self.position_id is None or self.opportunity_id is not None:
                raise ValueError("existing replacement target requires position only")
        elif self.position_id is not None or self.opportunity_id is not None:
            raise ValueError("core ETF replacement target cannot reference position or Opportunity")
        return self


class ReplacementConstraintObservation(BaseModel):
    """Explicit after-replacement observation used to enforce an owner ratio limit."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    kind: RatioConstraintKind
    observed_after: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    source_reference: NonEmptyString
    source_fingerprint: ContentHash
    rationale: NonEmptyString

    @field_validator("observed_after")
    @classmethod
    def normalize_ratio(cls, value: Decimal) -> Decimal:
        return canonical_decimal(value)


class ReplacementDecisionInput(BaseModel):
    """One explicit source-to-target proposal before policy and friction derivation."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString = REPLACEMENT_DECISION_METHOD_VERSION
    source_position_id: PortfolioObjectId
    target: ReplacementTarget
    gross_sale_amount: MonetaryAmount
    candidate_instrument: CandidateEquityInstrument | None = None
    pre_friction_comparison: PairwiseCapitalComparison
    friction: ReplacementFriction
    after_friction_preference: ReplacementPreference
    after_friction_rationale: NonEmptyString
    constraint_observations: tuple[ReplacementConstraintObservation, ...] = ()
    decision_rationale: tuple[NonEmptyString, ...] = Field(min_length=3, max_length=5)
    main_risks_and_unknowns: tuple[NonEmptyString, ...] = Field(min_length=1)
    change_conditions: tuple[NonEmptyString, ...] = Field(min_length=1)
    confidence: DecisionConfidence
    missing_data: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()

    @field_validator("method_version")
    @classmethod
    def require_method(cls, value: str) -> str:
        if value != REPLACEMENT_DECISION_METHOD_VERSION:
            raise ValueError(f"method_version must be {REPLACEMENT_DECISION_METHOD_VERSION!r}")
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
        return _reject_duplicates(value, "duplicate replacement-decision text is not allowed")

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if self.gross_sale_amount.amount == 0:
            raise ValueError("replacement gross_sale_amount must be greater than zero")
        if self.target.kind is ReplacementTargetKind.CANDIDATE_EQUITY:
            if self.candidate_instrument is None:
                raise ValueError("candidate replacement target requires candidate_instrument")
            if self.candidate_instrument.instrument_id != self.target.instrument_id:
                raise ValueError("replacement candidate instrument must match target instrument")
        elif self.candidate_instrument is not None:
            raise ValueError("only candidate replacement target may include candidate_instrument")
        observation_kinds = tuple(item.kind for item in self.constraint_observations)
        _reject_duplicates(
            observation_kinds,
            "duplicate replacement constraint observations are not allowed",
        )
        expected_ids = {self.source_position_id, self.target.target_id}
        actual_ids = {
            self.pre_friction_comparison.first_alternative_id,
            self.pre_friction_comparison.second_alternative_id,
        }
        if actual_ids != expected_ids:
            raise ValueError("pre-friction comparison must cover the source and replacement target")
        return self


class ReplacementDecision(ReplacementDecisionInput):
    """Content-addressed after-friction replacement result with no execution timing."""

    replacement_decision_id: UUID
    input_fingerprint: ContentHash
    portfolio_state: PortfolioStateReference
    base_exposure: PortfolioExposureReference
    policy: OwnerPortfolioPolicyReference
    opportunity_state: OpportunityStateReference | None = None
    source_tax_treatment: TaxTreatment
    total_switching_friction: MonetaryAmount | None
    net_redeployable_amount: MonetaryAmount | None
    available_new_capital: MonetaryAmount
    outcome: ReplacementOutcome
    decision_basis: ReplacementDecisionBasis

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        if self.portfolio_state.knowledge_boundary != self.knowledge_boundary:
            raise ValueError("replacement must preserve the Portfolio State boundary")
        if self.base_exposure.knowledge_boundary != self.knowledge_boundary:
            raise ValueError("replacement must preserve the Exposure boundary")
        if self.policy.knowledge_boundary != self.knowledge_boundary:
            raise ValueError("replacement must preserve the owner-policy boundary")
        if (
            self.opportunity_state is not None
            and self.opportunity_state.knowledge_boundary != self.knowledge_boundary
        ):
            raise ValueError("replacement candidate must preserve the Opportunity boundary")
        if self.target.kind is ReplacementTargetKind.CANDIDATE_EQUITY:
            if (
                self.opportunity_state is None
                or self.target.opportunity_id != self.opportunity_state.opportunity_id
            ):
                raise ValueError(
                    "candidate replacement must retain the verified Opportunity reference"
                )
        elif self.opportunity_state is not None:
            raise ValueError("non-candidate replacement cannot retain an Opportunity reference")
        currency = self.gross_sale_amount.currency
        if self.target.native_currency != currency:
            raise ValueError("replacement target must use the gross-sale currency")
        if self.available_new_capital.currency != currency:
            raise ValueError("available new capital must use replacement currency")
        for amount in (self.total_switching_friction, self.net_redeployable_amount):
            if amount is not None and amount.currency != currency:
                raise ValueError("replacement derived amounts must use the gross-sale currency")
        if self.outcome is ReplacementOutcome.REPLACE:
            if self.decision_basis is not ReplacementDecisionBasis.AFTER_FRICTION_TARGET_DOMINANCE:
                raise ValueError("REPLACE requires after-friction target dominance")
            if self.total_switching_friction is None or self.net_redeployable_amount is None:
                raise ValueError("REPLACE requires complete switching friction")
            if self.after_friction_preference is not ReplacementPreference.TARGET:
                raise ValueError("REPLACE requires target preference after friction")
        return self

    @property
    def as_of(self) -> datetime:
        return self.knowledge_boundary.as_of

    @property
    def knowledge_mode(self) -> KnowledgeMode:
        return self.knowledge_boundary.knowledge_mode
