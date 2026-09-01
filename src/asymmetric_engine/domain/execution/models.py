"""Point-in-time Execution planning contracts for Chapter 7."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from asymmetric_engine.domain.evidence.models import ContentHash, NonEmptyString
from asymmetric_engine.domain.financial import CurrencyCode, MonetaryAmount, canonical_decimal
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode

EXECUTION_POLICY_METHOD_VERSION = "execution-policy-v1"
EXECUTION_PLAN_METHOD_VERSION = "execution-plan-v1"


def _reject_duplicates[T](values: tuple[T, ...], message: str) -> tuple[T, ...]:
    if len(values) != len(set(values)):
        raise ValueError(message)
    return values


class ExecutionSourceKind(StrEnum):
    """The two final Chapter 6 capital instructions admitted into Execution."""

    POLICY_ALLOCATION = "policy_allocation"
    REPLACEMENT = "replacement"


class ExecutionAction(StrEnum):
    """Minimal Chapter 7 implementation vocabulary."""

    NOW = "now"
    STAGED = "staged"
    WAIT = "wait"
    INVALIDATED = "invalidated"


class ExecutionSide(StrEnum):
    """Trade direction retained only as an execution-plan instruction."""

    BUY = "buy"
    SELL = "sell"


class ExecutionLiquidityStatus(StrEnum):
    """Current operational liquidity state; no timing score is implied."""

    ADEQUATE = "adequate"
    CONSTRAINED = "constrained"
    UNKNOWN = "unknown"


class InvalidationStatus(StrEnum):
    """Observed state of one exact upstream change condition."""

    NOT_TRIGGERED = "not_triggered"
    TRIGGERED = "triggered"
    UNKNOWN = "unknown"


class ExecutionReasonCode(StrEnum):
    """Inspectable categorical reason for the execution action."""

    READY_NOW = "ready_now"
    EXPLICIT_STAGING_LIMIT = "explicit_staging_limit"
    INVALIDATION_TRIGGERED = "invalidation_triggered"
    INVALIDATION_UNKNOWN = "invalidation_unknown"
    INVALIDATION_MISSING = "invalidation_missing"
    QUOTE_MISSING = "quote_missing"
    QUOTE_STALE = "quote_stale"
    SPREAD_TOO_WIDE = "spread_too_wide"
    LIQUIDITY_UNKNOWN = "liquidity_unknown"
    LIQUIDITY_CONSTRAINED = "liquidity_constrained"


class ApprovedCapitalInstruction(BaseModel):
    """Execution-facing immutable copy of only the capital facts it is allowed to implement."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    decision_id: UUID
    decision_fingerprint: ContentHash
    decision_boundary: KnowledgeBoundary
    source_kind: ExecutionSourceKind
    target_instrument_id: NonEmptyString
    target_amount: MonetaryAmount
    change_conditions: tuple[NonEmptyString, ...] = Field(min_length=1)
    source_position_id: NonEmptyString | None = None
    source_instrument_id: NonEmptyString | None = None
    source_sale_amount: MonetaryAmount | None = None

    @field_validator("change_conditions")
    @classmethod
    def reject_duplicate_conditions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate execution change conditions are not allowed")

    @model_validator(mode="after")
    def validate_instruction(self) -> Self:
        if self.target_amount.amount == 0:
            raise ValueError("approved execution target amount must be greater than zero")
        replacement_fields = (
            self.source_position_id,
            self.source_instrument_id,
            self.source_sale_amount,
        )
        if self.source_kind is ExecutionSourceKind.POLICY_ALLOCATION:
            if any(item is not None for item in replacement_fields):
                raise ValueError("new-capital execution cannot contain replacement source fields")
        else:
            if any(item is None for item in replacement_fields):
                raise ValueError("replacement execution source fields are required")
            assert self.source_sale_amount is not None
            if self.source_sale_amount.amount == 0:
                raise ValueError("replacement execution source sale amount must be positive")
            if self.source_sale_amount.currency != self.target_amount.currency:
                raise ValueError("replacement execution legs must use one native currency")
        return self


class ExecutionPolicyInput(BaseModel):
    """Explicit owner implementation constraints; there are no hidden defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString = EXECUTION_POLICY_METHOD_VERSION
    max_quote_age_seconds: int = Field(gt=0)
    max_spread_bps: Decimal = Field(ge=0, le=Decimal("10000"), allow_inf_nan=False)
    max_single_order_notional: MonetaryAmount | None = None
    rationale: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=5)
    assumptions: tuple[NonEmptyString, ...] = ()

    @field_validator("method_version")
    @classmethod
    def require_method(cls, value: str) -> str:
        if value != EXECUTION_POLICY_METHOD_VERSION:
            raise ValueError(f"method_version must be {EXECUTION_POLICY_METHOD_VERSION!r}")
        return value

    @field_validator("max_spread_bps")
    @classmethod
    def normalize_spread(cls, value: Decimal) -> Decimal:
        return canonical_decimal(value)

    @field_validator("rationale", "assumptions")
    @classmethod
    def reject_duplicate_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate execution-policy text is not allowed")

    @model_validator(mode="after")
    def require_positive_order_limit(self) -> Self:
        if (
            self.max_single_order_notional is not None
            and self.max_single_order_notional.amount == 0
        ):
            raise ValueError("max_single_order_notional must be greater than zero")
        return self


class ExecutionPolicy(ExecutionPolicyInput):
    """Content-addressed owner execution policy at one execution boundary."""

    policy_id: UUID
    input_fingerprint: ContentHash


class ExecutionPolicyReference(BaseModel):
    """Stable reference retained by the Execution Plan."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    policy_id: UUID
    input_fingerprint: ContentHash
    knowledge_boundary: KnowledgeBoundary


class MarketExecutionObservation(BaseModel):
    """One point-in-time bid/ask and liquidity observation for an instrument that may trade."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    instrument_id: NonEmptyString
    native_currency: CurrencyCode
    bid: MonetaryAmount
    ask: MonetaryAmount
    observed_at: AwareDatetime
    available_at: AwareDatetime
    recorded_at: AwareDatetime
    liquidity: ExecutionLiquidityStatus
    source_reference: NonEmptyString
    source_fingerprint: ContentHash
    missing_data: tuple[NonEmptyString, ...] = ()

    @field_validator("missing_data")
    @classmethod
    def reject_duplicate_missing(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate market-observation missing_data is not allowed")

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if {self.bid.currency, self.ask.currency} != {self.native_currency}:
            raise ValueError("execution bid/ask must use the observation native currency")
        if self.bid.amount == 0 or self.ask.amount == 0:
            raise ValueError("execution bid/ask must be greater than zero")
        if self.ask.amount < self.bid.amount:
            raise ValueError("execution ask cannot be below bid")
        if not (self.observed_at <= self.available_at <= self.recorded_at):
            raise ValueError("execution observation requires observed <= available <= recorded")
        if self.liquidity is ExecutionLiquidityStatus.UNKNOWN and not self.missing_data:
            raise ValueError("unknown execution liquidity requires missing_data")
        return self

    @property
    def spread_bps(self) -> Decimal:
        midpoint = (self.bid.amount + self.ask.amount) / Decimal(2)
        spread = (self.ask.amount - self.bid.amount) / midpoint * Decimal(10000)
        return canonical_decimal(spread)


class ExecutionInvalidationObservation(BaseModel):
    """Point-in-time state of one exact upstream change condition."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    condition: NonEmptyString
    status: InvalidationStatus
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
        return _reject_duplicates(value, "duplicate invalidation missing_data is not allowed")

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if not (self.observed_at <= self.available_at <= self.recorded_at):
            raise ValueError("invalidation observation requires observed <= available <= recorded")
        if self.status is InvalidationStatus.UNKNOWN and not self.missing_data:
            raise ValueError("unknown invalidation state requires missing_data")
        return self


class ExecutionPlanInput(BaseModel):
    """Current operational observations supplied before deterministic execution derivation."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString = EXECUTION_PLAN_METHOD_VERSION
    market_observations: tuple[MarketExecutionObservation, ...] = ()
    invalidation_observations: tuple[ExecutionInvalidationObservation, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()

    @field_validator("method_version")
    @classmethod
    def require_method(cls, value: str) -> str:
        if value != EXECUTION_PLAN_METHOD_VERSION:
            raise ValueError(f"method_version must be {EXECUTION_PLAN_METHOD_VERSION!r}")
        return value

    @field_validator("conflicts", "assumptions")
    @classmethod
    def reject_duplicate_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate Execution Plan disclosures are not allowed")

    @model_validator(mode="after")
    def reject_duplicate_observations(self) -> Self:
        _reject_duplicates(
            tuple(item.instrument_id for item in self.market_observations),
            "duplicate market observations are not allowed",
        )
        _reject_duplicates(
            tuple(item.condition for item in self.invalidation_observations),
            "duplicate invalidation observations are not allowed",
        )
        return self


class ExecutionTranche(BaseModel):
    """One deterministic piece of an already-approved trade-leg notional."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    tranche_index: int = Field(ge=1)
    notional: MonetaryAmount

    @model_validator(mode="after")
    def require_positive_notional(self) -> Self:
        if self.notional.amount == 0:
            raise ValueError("execution tranche notional must be greater than zero")
        return self


class ExecutionLeg(BaseModel):
    """One BUY or SELL instruction split only for implementation, never strategic sizing."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    sequence: int = Field(ge=1)
    side: ExecutionSide
    instrument_id: NonEmptyString
    total_notional: MonetaryAmount
    tranches: tuple[ExecutionTranche, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tranches(self) -> Self:
        if self.total_notional.amount == 0:
            raise ValueError("execution leg total notional must be greater than zero")
        if tuple(item.tranche_index for item in self.tranches) != tuple(
            range(1, len(self.tranches) + 1)
        ):
            raise ValueError("execution tranche indexes must be contiguous from one")
        if any(item.notional.currency != self.total_notional.currency for item in self.tranches):
            raise ValueError("execution tranches must use the leg currency")
        total = canonical_decimal(sum((item.notional.amount for item in self.tranches), Decimal(0)))
        if total != self.total_notional.amount:
            raise ValueError("execution tranche sum must equal the approved leg notional")
        return self


class ExecutionReason(BaseModel):
    """One categorical, inspectable reason for the chosen execution action."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    code: ExecutionReasonCode
    detail: NonEmptyString


class ExecutionPlan(ExecutionPlanInput):
    """Content-addressed implementation decision with no brokerage side effect."""

    plan_id: UUID
    input_fingerprint: ContentHash
    source: ApprovedCapitalInstruction
    policy: ExecutionPolicyReference
    action: ExecutionAction
    reasons: tuple[ExecutionReason, ...] = Field(min_length=1)
    legs: tuple[ExecutionLeg, ...] = ()
    missing_data: tuple[NonEmptyString, ...] = ()

    @field_validator("missing_data")
    @classmethod
    def reject_duplicate_missing(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate Execution Plan missing_data is not allowed")

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if (
            self.source.decision_boundary.knowledge_mode
            is not self.knowledge_boundary.knowledge_mode
        ):
            raise ValueError("Execution must preserve the source decision KnowledgeMode")
        if self.knowledge_boundary.as_of < self.source.decision_boundary.as_of:
            raise ValueError("Execution cannot precede the approved capital decision")
        if self.policy.knowledge_boundary != self.knowledge_boundary:
            raise ValueError("Execution Plan must preserve the execution-policy boundary")
        codes = tuple(item.code for item in self.reasons)
        _reject_duplicates(codes, "duplicate Execution Plan reason codes are not allowed")

        if self.action in {ExecutionAction.WAIT, ExecutionAction.INVALIDATED}:
            if self.legs:
                raise ValueError("WAIT and INVALIDATED cannot contain executable legs")
        else:
            self._validate_executable_legs()
            if self.action is ExecutionAction.NOW:
                if any(len(item.tranches) != 1 for item in self.legs):
                    raise ValueError("NOW requires one tranche per execution leg")
                if ExecutionReasonCode.READY_NOW not in codes:
                    raise ValueError("NOW requires the ready-now reason")
            elif not any(len(item.tranches) > 1 for item in self.legs):
                raise ValueError("STAGED requires at least one multi-tranche leg")

        if self.action is ExecutionAction.INVALIDATED:
            if ExecutionReasonCode.INVALIDATION_TRIGGERED not in codes:
                raise ValueError("INVALIDATED requires a triggered upstream invalidation")
        elif ExecutionReasonCode.INVALIDATION_TRIGGERED in codes:
            raise ValueError("triggered upstream invalidation must produce INVALIDATED")
        return self

    def _validate_executable_legs(self) -> None:
        if self.source.source_kind is ExecutionSourceKind.POLICY_ALLOCATION:
            if len(self.legs) != 1:
                raise ValueError("new-capital execution requires one BUY leg")
            leg = self.legs[0]
            if (
                leg.sequence != 1
                or leg.side is not ExecutionSide.BUY
                or leg.instrument_id != self.source.target_instrument_id
                or leg.total_notional != self.source.target_amount
            ):
                raise ValueError("new-capital execution leg must preserve the approved instruction")
            return

        if len(self.legs) != 2:
            raise ValueError("replacement execution requires SELL then BUY legs")
        sell, buy = self.legs
        if self.source.source_instrument_id is None or self.source.source_sale_amount is None:
            raise ValueError("replacement source fields are missing")
        if (
            sell.sequence != 1
            or sell.side is not ExecutionSide.SELL
            or sell.instrument_id != self.source.source_instrument_id
            or sell.total_notional != self.source.source_sale_amount
        ):
            raise ValueError("replacement SELL leg must preserve the approved source sale")
        if (
            buy.sequence != 2
            or buy.side is not ExecutionSide.BUY
            or buy.instrument_id != self.source.target_instrument_id
            or buy.total_notional != self.source.target_amount
        ):
            raise ValueError("replacement BUY leg must preserve the approved target amount")

    @property
    def as_of(self) -> datetime:
        return self.knowledge_boundary.as_of

    @property
    def knowledge_mode(self) -> KnowledgeMode:
        return self.knowledge_boundary.knowledge_mode
