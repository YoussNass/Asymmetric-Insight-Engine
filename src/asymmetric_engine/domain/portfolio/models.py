"""Immutable factual Portfolio State contracts for Chapter 6A."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from asymmetric_engine.domain.evidence.models import ContentHash, NonEmptyString
from asymmetric_engine.domain.evidence.source_documents import SubjectId
from asymmetric_engine.domain.financial import CurrencyCode, MonetaryAmount, canonical_decimal
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode

PortfolioObjectId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[a-z][a-z0-9_.:-]*$",
    ),
]
CountryCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        pattern=r"^[A-Z]{2}$",
    ),
]
ISIN = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$",
    ),
]

PORTFOLIO_STATE_METHOD_VERSION = "portfolio-state-v1"


class PortfolioRecordKind(StrEnum):
    """Factual or policy input represented by one immutable source version."""

    INSTRUMENT_REFERENCE = "instrument_reference"
    ACCOUNT_REFERENCE = "account_reference"
    HOLDINGS_SNAPSHOT = "holdings_snapshot"
    CASH_SNAPSHOT = "cash_snapshot"
    MARKET_PRICE = "market_price"
    ETF_ELIGIBILITY_POLICY = "etf_eligibility_policy"


class InstrumentType(StrEnum):
    """Representable instrument categories; representation is not eligibility."""

    LISTED_EQUITY = "listed_equity"
    EQUITY_ETF = "equity_etf"
    OTHER_ETP = "other_etp"
    FUND = "fund"
    FIXED_INCOME = "fixed_income"
    CRYPTO_ASSET = "crypto_asset"
    OTHER = "other"


class CostBasisStatus(StrEnum):
    """How the aggregate position cost basis was obtained."""

    BROKER_REPORTED = "broker_reported"
    USER_ESTIMATED = "user_estimated"
    UNAVAILABLE = "unavailable"


class TaxTreatment(StrEnum):
    """Basic account-level tax treatment without tax calculation or optimization."""

    TAXABLE = "taxable"
    TAX_DEFERRED = "tax_deferred"
    TAX_EXEMPT = "tax_exempt"
    UNKNOWN = "unknown"


class CashRole(StrEnum):
    """Owner-declared role of cash at the decision boundary."""

    EMERGENCY_RESERVE = "emergency_reserve"
    STRATEGIC = "strategic"
    OPPORTUNISTIC = "opportunistic"
    UNALLOCATED = "unallocated"

    @property
    def is_investable(self) -> bool:
        """Emergency cash is excluded; all investment cash remains explicitly typed."""

        return self is not CashRole.EMERGENCY_RESERVE


class PortfolioInputRecord(BaseModel):
    """Versioned provenance for one factual Portfolio State input."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    record_id: UUID
    kind: PortfolioRecordKind
    provider: NonEmptyString
    provider_record_id: NonEmptyString
    provider_version: NonEmptyString
    source_reference: NonEmptyString
    effective_at: AwareDatetime
    available_at: AwareDatetime
    recorded_at: AwareDatetime
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_ingestion_order(self) -> Self:
        if self.recorded_at < self.available_at:
            raise ValueError("recorded_at must be greater than or equal to available_at")
        return self


class EquityETFProfile(BaseModel):
    """Structural ETF facts used only to enforce the accepted eligibility boundary."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    diversified: bool
    leveraged: bool
    inverse: bool
    derivative_heavy: bool
    narrowly_thematic: bool


class Instrument(BaseModel):
    """Canonical identity for a held or policy-referenced instrument."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    instrument_id: PortfolioObjectId
    symbol: NonEmptyString
    name: NonEmptyString
    instrument_type: InstrumentType
    native_currency: CurrencyCode
    reference_record_id: UUID
    listing_venue: NonEmptyString | None = None
    isin: ISIN | None = None
    company_subject_id: SubjectId | None = None
    etf_profile: EquityETFProfile | None = None

    @model_validator(mode="after")
    def validate_instrument_shape(self) -> Self:
        listed_types = {
            InstrumentType.LISTED_EQUITY,
            InstrumentType.EQUITY_ETF,
            InstrumentType.OTHER_ETP,
        }
        if self.instrument_type in listed_types and self.listing_venue is None:
            raise ValueError("listed instruments require listing_venue")
        if self.instrument_type is InstrumentType.LISTED_EQUITY:
            if self.company_subject_id is None:
                raise ValueError("listed equities require company_subject_id")
        elif self.company_subject_id is not None:
            raise ValueError("only listed equities may declare company_subject_id")
        if self.instrument_type is InstrumentType.EQUITY_ETF:
            if self.etf_profile is None:
                raise ValueError("equity ETFs require etf_profile")
        elif self.etf_profile is not None:
            raise ValueError("only equity ETFs may declare etf_profile")
        return self


class InstrumentPrice(BaseModel):
    """One point-in-time unit price kept separate from instrument identity."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    price_id: PortfolioObjectId
    instrument_id: PortfolioObjectId
    unit_price: MonetaryAmount
    price_record_id: UUID


class PositionCostBasis(BaseModel):
    """Aggregate cost basis only; tax lots and optimization are deliberately absent."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    status: CostBasisStatus
    total_cost: MonetaryAmount | None = None

    @model_validator(mode="after")
    def validate_cost_basis_shape(self) -> Self:
        if self.status is CostBasisStatus.UNAVAILABLE:
            if self.total_cost is not None:
                raise ValueError("unavailable cost basis cannot declare total_cost")
        elif self.total_cost is None:
            raise ValueError("reported or estimated cost basis requires total_cost")
        return self


class TaxMetadata(BaseModel):
    """Minimal tax metadata with no rates, lots, forecasts, or optimization."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    treatment: TaxTreatment
    jurisdiction: CountryCode | None = None

    @model_validator(mode="after")
    def require_known_jurisdiction_for_known_treatment(self) -> Self:
        if self.treatment is not TaxTreatment.UNKNOWN and self.jurisdiction is None:
            raise ValueError("known tax treatment requires jurisdiction")
        return self


class PortfolioAccount(BaseModel):
    """Canonical account identity and its single basic tax treatment."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    account_id: PortfolioObjectId
    label: NonEmptyString
    reference_record_id: UUID
    tax_metadata: TaxMetadata


class Position(BaseModel):
    """One long-only aggregate position at T0."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    position_id: PortfolioObjectId
    account_id: PortfolioObjectId
    instrument_id: PortfolioObjectId
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    price_id: PortfolioObjectId
    current_value: MonetaryAmount
    holdings_record_id: UUID
    cost_basis: PositionCostBasis

    @field_validator("quantity")
    @classmethod
    def normalize_quantity(cls, value: Decimal) -> Decimal:
        return canonical_decimal(value)


class CashBalance(BaseModel):
    """One explicit cash role and amount at T0."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    cash_id: PortfolioObjectId
    account_id: PortfolioObjectId
    role: CashRole
    balance: MonetaryAmount
    snapshot_record_id: UUID

    @property
    def is_investable(self) -> bool:
        return self.role.is_investable


class ETFEligibilityPolicy(BaseModel):
    """Versioned allow-list and benchmark identity accepted by ADR 0013."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    policy_id: PortfolioObjectId
    policy_version: NonEmptyString
    policy_record_id: UUID
    eligible_etf_ids: tuple[PortfolioObjectId, ...] = Field(min_length=1)
    benchmark_instrument_id: PortfolioObjectId
    rationale: NonEmptyString

    @field_validator("eligible_etf_ids")
    @classmethod
    def reject_duplicate_eligible_etfs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate eligible_etf_ids are not allowed")
        return value

    @model_validator(mode="after")
    def require_benchmark_to_be_eligible(self) -> Self:
        if self.benchmark_instrument_id not in self.eligible_etf_ids:
            raise ValueError("benchmark_instrument_id must be an eligible ETF")
        return self


class T0DecisionRecordEnvelope(BaseModel):
    """Stable audit anchor; it intentionally contains no capital decision."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    record_id: UUID
    portfolio_state_id: UUID
    portfolio_input_fingerprint: ContentHash
    knowledge_boundary: KnowledgeBoundary
    benchmark_instrument_id: PortfolioObjectId
    method_version: NonEmptyString


class PortfolioStateDraft(BaseModel):
    """Validated factual input before canonical ordering and content addressing."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    portfolio_id: PortfolioObjectId
    title: NonEmptyString
    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString
    input_records: tuple[PortfolioInputRecord, ...] = Field(min_length=1)
    accounts: tuple[PortfolioAccount, ...] = Field(min_length=1)
    instruments: tuple[Instrument, ...] = Field(min_length=1)
    prices: tuple[InstrumentPrice, ...] = Field(min_length=1)
    positions: tuple[Position, ...] = ()
    cash_balances: tuple[CashBalance, ...] = Field(min_length=1)
    etf_eligibility_policy: ETFEligibilityPolicy
    missing_data: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()

    @field_validator("method_version")
    @classmethod
    def require_admitted_method_version(cls, value: str) -> str:
        if value != PORTFOLIO_STATE_METHOD_VERSION:
            raise ValueError(f"method_version must be {PORTFOLIO_STATE_METHOD_VERSION!r}")
        return value

    @field_validator("missing_data", "conflicts", "assumptions")
    @classmethod
    def reject_duplicate_disclosures(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate disclosure entries are not allowed")
        return value

    @model_validator(mode="after")
    def validate_portfolio_state(self) -> Self:
        records = {record.record_id: record for record in self.input_records}
        accounts = {account.account_id: account for account in self.accounts}
        instruments = {instrument.instrument_id: instrument for instrument in self.instruments}
        prices = {price.price_id: price for price in self.prices}
        positions = {position.position_id: position for position in self.positions}
        cash_balances = {cash.cash_id: cash for cash in self.cash_balances}
        if len(records) != len(self.input_records):
            raise ValueError("duplicate input record_ids are not allowed")
        if len(accounts) != len(self.accounts):
            raise ValueError("duplicate account_ids are not allowed")
        if len(instruments) != len(self.instruments):
            raise ValueError("duplicate instrument_ids are not allowed")
        if len(prices) != len(self.prices):
            raise ValueError("duplicate price_ids are not allowed")
        if len(positions) != len(self.positions):
            raise ValueError("duplicate position_ids are not allowed")
        if len(cash_balances) != len(self.cash_balances):
            raise ValueError("duplicate cash_ids are not allowed")
        if len({price.instrument_id for price in self.prices}) != len(self.prices):
            raise ValueError("only one price per instrument is allowed at T0")
        if len({(item.account_id, item.instrument_id) for item in self.positions}) != len(
            self.positions
        ):
            raise ValueError("positions must be aggregate per account and instrument")
        if len(
            {(item.account_id, item.balance.currency, item.role) for item in self.cash_balances}
        ) != len(self.cash_balances):
            raise ValueError("cash must be aggregate per account, currency, and role")

        for record in self.input_records:
            if record.effective_at > self.knowledge_boundary.as_of:
                raise ValueError(
                    f"input record {record.record_id} is not effective by the knowledge boundary"
                )
            exclusion = self.knowledge_boundary.exclusion_reason(
                available_at=record.available_at,
                recorded_at=record.recorded_at,
            )
            if exclusion is not None:
                raise ValueError(
                    f"input record {record.record_id} is outside the knowledge boundary: "
                    f"{exclusion.value}"
                )

        referenced_records: set[UUID] = set()

        def require_record(
            record_id: UUID,
            expected_kind: PortfolioRecordKind,
            owner: str,
        ) -> None:
            record = records.get(record_id)
            if record is None:
                raise ValueError(f"{owner} references an unknown input record")
            if record.kind is not expected_kind:
                raise ValueError(f"{owner} requires input record kind {expected_kind.value}")
            referenced_records.add(record_id)

        for account in self.accounts:
            require_record(
                account.reference_record_id,
                PortfolioRecordKind.ACCOUNT_REFERENCE,
                f"account {account.account_id}",
            )

        for instrument in self.instruments:
            require_record(
                instrument.reference_record_id,
                PortfolioRecordKind.INSTRUMENT_REFERENCE,
                f"instrument {instrument.instrument_id}",
            )

        prices_by_instrument: dict[str, InstrumentPrice] = {}
        for price in self.prices:
            priced_instrument = instruments.get(price.instrument_id)
            if priced_instrument is None:
                raise ValueError(f"price {price.price_id} references an unknown instrument")
            if price.unit_price.currency != priced_instrument.native_currency:
                raise ValueError(
                    f"price {price.price_id} currency must match instrument native currency"
                )
            require_record(
                price.price_record_id,
                PortfolioRecordKind.MARKET_PRICE,
                f"price {price.price_id}",
            )
            prices_by_instrument[price.instrument_id] = price

        held_instrument_ids: set[str] = set()
        referenced_account_ids: set[str] = set()
        for position in self.positions:
            if position.account_id not in accounts:
                raise ValueError(f"position {position.position_id} references an unknown account")
            held_instrument = instruments.get(position.instrument_id)
            if held_instrument is None:
                raise ValueError(
                    f"position {position.position_id} references an unknown instrument"
                )
            position_price = prices.get(position.price_id)
            if position_price is None or position_price.instrument_id != position.instrument_id:
                raise ValueError(
                    f"position {position.position_id} requires its instrument's T0 price"
                )
            expected_value = canonical_decimal(position.quantity * position_price.unit_price.amount)
            if position.current_value.currency != position_price.unit_price.currency:
                raise ValueError(
                    f"position {position.position_id} value currency must match its price"
                )
            if position.current_value.amount != expected_value:
                raise ValueError(
                    f"position {position.position_id} current_value must equal quantity times price"
                )
            require_record(
                position.holdings_record_id,
                PortfolioRecordKind.HOLDINGS_SNAPSHOT,
                f"position {position.position_id}",
            )
            held_instrument_ids.add(position.instrument_id)
            referenced_account_ids.add(position.account_id)

        for cash in self.cash_balances:
            if cash.account_id not in accounts:
                raise ValueError(f"cash balance {cash.cash_id} references an unknown account")
            require_record(
                cash.snapshot_record_id,
                PortfolioRecordKind.CASH_SNAPSHOT,
                f"cash balance {cash.cash_id}",
            )
            referenced_account_ids.add(cash.account_id)

        policy = self.etf_eligibility_policy
        require_record(
            policy.policy_record_id,
            PortfolioRecordKind.ETF_ELIGIBILITY_POLICY,
            f"ETF policy {policy.policy_id}",
        )
        eligible_etf_ids = set(policy.eligible_etf_ids)
        for instrument_id in eligible_etf_ids:
            eligible_instrument = instruments.get(instrument_id)
            if eligible_instrument is None:
                raise ValueError("ETF policy references an unknown instrument")
            profile = eligible_instrument.etf_profile
            if (
                eligible_instrument.instrument_type is not InstrumentType.EQUITY_ETF
                or profile is None
            ):
                raise ValueError("ETF policy may contain only equity ETFs")
            if (
                not profile.diversified
                or profile.leveraged
                or profile.inverse
                or profile.derivative_heavy
                or profile.narrowly_thematic
            ):
                raise ValueError(
                    "eligible ETFs must be diversified, unleveraged, non-inverse, "
                    "not derivative-heavy, and not narrowly thematic"
                )
            if instrument_id not in prices_by_instrument:
                raise ValueError("every eligible ETF requires a point-in-time price")

        used_instrument_ids = held_instrument_ids | eligible_etf_ids
        if set(instruments) != used_instrument_ids:
            raise ValueError(
                "every instrument must be held or referenced by the ETF eligibility policy"
            )
        if set(prices_by_instrument) != used_instrument_ids:
            raise ValueError("every held or eligible instrument requires exactly one T0 price")
        if set(accounts) != referenced_account_ids:
            raise ValueError("every account must contain a position or cash balance")
        if referenced_records != set(records):
            raise ValueError("every input record must support the Portfolio State")
        return self

    @property
    def as_of(self) -> datetime:
        return self.knowledge_boundary.as_of

    @property
    def knowledge_mode(self) -> KnowledgeMode:
        return self.knowledge_boundary.knowledge_mode

    def is_in_investable_universe(self, instrument_id: str) -> bool:
        """Return instrument-level scope eligibility, never an allocation recommendation."""

        instruments = {instrument.instrument_id: instrument for instrument in self.instruments}
        instrument = instruments.get(instrument_id)
        if instrument is None:
            raise KeyError(instrument_id)
        if instrument.instrument_type is InstrumentType.LISTED_EQUITY:
            return True
        return (
            instrument.instrument_type is InstrumentType.EQUITY_ETF
            and instrument.instrument_id in self.etf_eligibility_policy.eligible_etf_ids
        )

    def position_values_by_currency(self) -> dict[str, Decimal]:
        """Aggregate held value only within each native currency."""

        totals: dict[str, Decimal] = {}
        for position in self.positions:
            currency = position.current_value.currency
            totals[currency] = totals.get(currency, Decimal(0)) + position.current_value.amount
        return {currency: canonical_decimal(totals[currency]) for currency in sorted(totals)}

    def cash_values_by_currency(self, *, investable_only: bool = False) -> dict[str, Decimal]:
        """Aggregate cash by native currency without implying an FX conversion."""

        totals: dict[str, Decimal] = {}
        for cash in self.cash_balances:
            if investable_only and not cash.is_investable:
                continue
            currency = cash.balance.currency
            totals[currency] = totals.get(currency, Decimal(0)) + cash.balance.amount
        return {currency: canonical_decimal(totals[currency]) for currency in sorted(totals)}


class PortfolioState(PortfolioStateDraft):
    """Canonical, content-addressed factual state consumed by later Portfolio slices."""

    portfolio_state_id: UUID
    input_fingerprint: ContentHash
    decision_record: T0DecisionRecordEnvelope

    @model_validator(mode="after")
    def validate_decision_record_envelope(self) -> Self:
        record = self.decision_record
        if record.portfolio_state_id != self.portfolio_state_id:
            raise ValueError("decision record must reference this Portfolio State")
        if record.portfolio_input_fingerprint != self.input_fingerprint:
            raise ValueError("decision record must preserve the Portfolio State fingerprint")
        if record.knowledge_boundary != self.knowledge_boundary:
            raise ValueError("decision record must preserve the canonical knowledge boundary")
        if record.benchmark_instrument_id != self.etf_eligibility_policy.benchmark_instrument_id:
            raise ValueError("decision record must preserve the benchmark identity")
        if record.method_version != self.method_version:
            raise ValueError("decision record must preserve the method version")
        return self
