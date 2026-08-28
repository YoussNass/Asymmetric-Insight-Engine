"""Deterministic Chapter 6A Portfolio State fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.portfolio import (
    PORTFOLIO_STATE_METHOD_VERSION,
    CashBalance,
    CashRole,
    CostBasisStatus,
    EquityETFProfile,
    ETFEligibilityPolicy,
    Instrument,
    InstrumentPrice,
    InstrumentType,
    KnowledgeMode,
    PortfolioAccount,
    PortfolioInputRecord,
    PortfolioRecordKind,
    PortfolioStateDraft,
    Position,
    PositionCostBasis,
    TaxMetadata,
    TaxTreatment,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary

AS_OF = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)

INSTRUMENT_RECORD_IDS = (
    UUID("10000000-0000-4000-8000-000000000001"),
    UUID("10000000-0000-4000-8000-000000000002"),
    UUID("10000000-0000-4000-8000-000000000003"),
)
PRICE_RECORD_IDS = (
    UUID("20000000-0000-4000-8000-000000000001"),
    UUID("20000000-0000-4000-8000-000000000002"),
    UUID("20000000-0000-4000-8000-000000000003"),
)
HOLDINGS_RECORD_ID = UUID("30000000-0000-4000-8000-000000000001")
CASH_RECORD_ID = UUID("40000000-0000-4000-8000-000000000001")
POLICY_RECORD_ID = UUID("50000000-0000-4000-8000-000000000001")
ACCOUNT_RECORD_IDS = (
    UUID("60000000-0000-4000-8000-000000000001"),
    UUID("60000000-0000-4000-8000-000000000002"),
)


def make_record(
    *,
    record_id: UUID,
    kind: PortfolioRecordKind,
    offset_days: int,
) -> PortfolioInputRecord:
    effective_at = AS_OF - timedelta(days=offset_days)
    return PortfolioInputRecord(
        record_id=record_id,
        kind=kind,
        provider="deterministic-fixture",
        provider_record_id=f"{kind.value}:{record_id}",
        provider_version="v1",
        source_reference=f"fixture://portfolio/{record_id}",
        effective_at=effective_at,
        available_at=effective_at,
        recorded_at=effective_at,
        content_hash=sha256(str(record_id).encode()).hexdigest(),
    )


def make_portfolio_draft(
    *,
    boundary: KnowledgeBoundary | None = None,
) -> PortfolioStateDraft:
    records = (
        *(
            make_record(
                record_id=record_id,
                kind=PortfolioRecordKind.ACCOUNT_REFERENCE,
                offset_days=30,
            )
            for record_id in ACCOUNT_RECORD_IDS
        ),
        *(
            make_record(
                record_id=record_id,
                kind=PortfolioRecordKind.INSTRUMENT_REFERENCE,
                offset_days=30,
            )
            for record_id in INSTRUMENT_RECORD_IDS
        ),
        *(
            make_record(
                record_id=record_id,
                kind=PortfolioRecordKind.MARKET_PRICE,
                offset_days=0,
            )
            for record_id in PRICE_RECORD_IDS
        ),
        make_record(
            record_id=HOLDINGS_RECORD_ID,
            kind=PortfolioRecordKind.HOLDINGS_SNAPSHOT,
            offset_days=0,
        ),
        make_record(
            record_id=CASH_RECORD_ID,
            kind=PortfolioRecordKind.CASH_SNAPSHOT,
            offset_days=0,
        ),
        make_record(
            record_id=POLICY_RECORD_ID,
            kind=PortfolioRecordKind.ETF_ELIGIBILITY_POLICY,
            offset_days=7,
        ),
    )
    instruments = (
        Instrument(
            instrument_id="instrument:micron",
            symbol="MU",
            name="Synthetic Micron reference",
            instrument_type=InstrumentType.LISTED_EQUITY,
            native_currency="USD",
            reference_record_id=INSTRUMENT_RECORD_IDS[0],
            listing_venue="NASDAQ",
            isin="US5951121038",
            company_subject_id="company:sec-cik-0000723125",
        ),
        Instrument(
            instrument_id="instrument:core-equity-etf",
            symbol="CORE",
            name="Synthetic diversified equity benchmark",
            instrument_type=InstrumentType.EQUITY_ETF,
            native_currency="EUR",
            reference_record_id=INSTRUMENT_RECORD_IDS[1],
            listing_venue="XETRA",
            isin="IE0000000001",
            etf_profile=EquityETFProfile(
                diversified=True,
                leveraged=False,
                inverse=False,
                derivative_heavy=False,
                narrowly_thematic=False,
            ),
        ),
        Instrument(
            instrument_id="instrument:thematic-etf",
            symbol="THEME",
            name="Synthetic narrowly thematic legacy holding",
            instrument_type=InstrumentType.EQUITY_ETF,
            native_currency="EUR",
            reference_record_id=INSTRUMENT_RECORD_IDS[2],
            listing_venue="BIT",
            isin="IE0000000002",
            etf_profile=EquityETFProfile(
                diversified=False,
                leveraged=False,
                inverse=False,
                derivative_heavy=False,
                narrowly_thematic=True,
            ),
        ),
    )
    prices = (
        InstrumentPrice(
            price_id="price:micron:t0",
            instrument_id="instrument:micron",
            unit_price=MonetaryAmount(amount=Decimal("110"), currency="USD"),
            price_record_id=PRICE_RECORD_IDS[0],
        ),
        InstrumentPrice(
            price_id="price:core-equity-etf:t0",
            instrument_id="instrument:core-equity-etf",
            unit_price=MonetaryAmount(amount=Decimal("100"), currency="EUR"),
            price_record_id=PRICE_RECORD_IDS[1],
        ),
        InstrumentPrice(
            price_id="price:thematic-etf:t0",
            instrument_id="instrument:thematic-etf",
            unit_price=MonetaryAmount(amount=Decimal("50"), currency="EUR"),
            price_record_id=PRICE_RECORD_IDS[2],
        ),
    )
    taxable_italy = TaxMetadata(
        treatment=TaxTreatment.TAXABLE,
        jurisdiction="IT",
    )
    accounts = (
        PortfolioAccount(
            account_id="account:broker-a",
            label="Synthetic taxable brokerage account",
            reference_record_id=ACCOUNT_RECORD_IDS[0],
            tax_metadata=taxable_italy,
        ),
        PortfolioAccount(
            account_id="account:bank",
            label="Synthetic taxable bank account",
            reference_record_id=ACCOUNT_RECORD_IDS[1],
            tax_metadata=taxable_italy,
        ),
    )
    positions = (
        Position(
            position_id="position:broker-a:micron",
            account_id="account:broker-a",
            instrument_id="instrument:micron",
            quantity=Decimal("10"),
            price_id="price:micron:t0",
            current_value=MonetaryAmount(amount=Decimal("1100"), currency="USD"),
            holdings_record_id=HOLDINGS_RECORD_ID,
            cost_basis=PositionCostBasis(
                status=CostBasisStatus.BROKER_REPORTED,
                total_cost=MonetaryAmount(amount=Decimal("900"), currency="USD"),
            ),
        ),
        Position(
            position_id="position:broker-a:thematic-etf",
            account_id="account:broker-a",
            instrument_id="instrument:thematic-etf",
            quantity=Decimal("4"),
            price_id="price:thematic-etf:t0",
            current_value=MonetaryAmount(amount=Decimal("200"), currency="EUR"),
            holdings_record_id=HOLDINGS_RECORD_ID,
            cost_basis=PositionCostBasis(
                status=CostBasisStatus.USER_ESTIMATED,
                total_cost=MonetaryAmount(amount=Decimal("150"), currency="EUR"),
            ),
        ),
    )
    cash_balances = (
        CashBalance(
            cash_id="cash:bank:emergency-eur",
            account_id="account:bank",
            role=CashRole.EMERGENCY_RESERVE,
            balance=MonetaryAmount(amount=Decimal("5000"), currency="EUR"),
            snapshot_record_id=CASH_RECORD_ID,
        ),
        CashBalance(
            cash_id="cash:broker-a:unallocated-eur",
            account_id="account:broker-a",
            role=CashRole.UNALLOCATED,
            balance=MonetaryAmount(amount=Decimal("1000"), currency="EUR"),
            snapshot_record_id=CASH_RECORD_ID,
        ),
        CashBalance(
            cash_id="cash:broker-a:opportunistic-usd",
            account_id="account:broker-a",
            role=CashRole.OPPORTUNISTIC,
            balance=MonetaryAmount(amount=Decimal("200"), currency="USD"),
            snapshot_record_id=CASH_RECORD_ID,
        ),
    )
    return PortfolioStateDraft(
        portfolio_id="portfolio:reference",
        title="Deterministic multi-currency Portfolio State fixture",
        knowledge_boundary=boundary
        or KnowledgeBoundary(
            as_of=AS_OF,
            knowledge_mode=KnowledgeMode.LIVE_SYSTEM_REPLAY,
        ),
        method_version=PORTFOLIO_STATE_METHOD_VERSION,
        input_records=records,
        accounts=accounts,
        instruments=instruments,
        prices=prices,
        positions=positions,
        cash_balances=cash_balances,
        etf_eligibility_policy=ETFEligibilityPolicy(
            policy_id="policy:core-etf-v1",
            policy_version="core-equity-etf-allow-list-v1",
            policy_record_id=POLICY_RECORD_ID,
            eligible_etf_ids=("instrument:core-equity-etf",),
            benchmark_instrument_id="instrument:core-equity-etf",
            rationale="Use one diversified unleveraged equity benchmark in Chapter 6A.",
        ),
        missing_data=("Tax-lot detail is intentionally outside Chapter 6A.",),
        assumptions=("Provider identifiers were canonicalized before domain validation.",),
    )


def rebuild_portfolio_draft(
    draft: PortfolioStateDraft,
    **overrides: object,
) -> PortfolioStateDraft:
    values = draft.model_dump(mode="python")
    values.update(overrides)
    return PortfolioStateDraft.model_validate(values)
