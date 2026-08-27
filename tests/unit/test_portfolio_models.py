"""Domain invariants for factual, point-in-time Portfolio State."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.portfolio import (
    CashRole,
    CostBasisStatus,
    InstrumentType,
    KnowledgeMode,
    PortfolioRecordKind,
    PortfolioStateDraft,
    PositionCostBasis,
    TaxMetadata,
    TaxTreatment,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary
from tests.portfolio_factories import (
    AS_OF,
    make_portfolio_draft,
    rebuild_portfolio_draft,
)


def test_portfolio_state_keeps_representation_eligibility_and_benchmark_distinct() -> None:
    draft = make_portfolio_draft()

    assert draft.is_in_investable_universe("instrument:micron")
    assert draft.is_in_investable_universe("instrument:core-equity-etf")
    assert not draft.is_in_investable_universe("instrument:thematic-etf")
    assert draft.etf_eligibility_policy.benchmark_instrument_id == "instrument:core-equity-etf"
    assert any(position.instrument_id == "instrument:thematic-etf" for position in draft.positions)
    with pytest.raises(KeyError, match="instrument:missing"):
        draft.is_in_investable_universe("instrument:missing")


def test_native_currency_totals_never_imply_an_fx_conversion() -> None:
    draft = make_portfolio_draft()

    assert draft.position_values_by_currency() == {
        "EUR": Decimal("200"),
        "USD": Decimal("1100"),
    }
    assert draft.cash_values_by_currency() == {
        "EUR": Decimal("6000"),
        "USD": Decimal("200"),
    }
    assert draft.cash_values_by_currency(investable_only=True) == {
        "EUR": Decimal("1000"),
        "USD": Decimal("200"),
    }
    emergency = next(
        cash for cash in draft.cash_balances if cash.role is CashRole.EMERGENCY_RESERVE
    )
    assert not emergency.is_investable
    assert not hasattr(draft, "total_portfolio_value")
    assert not hasattr(draft, "base_currency_value")


def test_positions_reproduce_value_from_their_own_t0_price() -> None:
    draft = make_portfolio_draft()
    position = draft.positions[0].model_copy(
        update={"current_value": MonetaryAmount(amount=Decimal("1099"), currency="USD")}
    )

    with pytest.raises(ValidationError, match="current_value must equal quantity times price"):
        rebuild_portfolio_draft(draft, positions=(position, *draft.positions[1:]))

    wrong_price = draft.positions[0].model_copy(update={"price_id": "price:thematic-etf:t0"})
    with pytest.raises(ValidationError, match="requires its instrument's T0 price"):
        rebuild_portfolio_draft(draft, positions=(wrong_price, *draft.positions[1:]))


def test_position_cost_basis_and_account_tax_metadata_remain_basic_and_explicit() -> None:
    unavailable = PositionCostBasis(status=CostBasisStatus.UNAVAILABLE)
    assert unavailable.total_cost is None

    with pytest.raises(ValidationError, match="requires total_cost"):
        PositionCostBasis(status=CostBasisStatus.BROKER_REPORTED)
    with pytest.raises(ValidationError, match="cannot declare total_cost"):
        PositionCostBasis(
            status=CostBasisStatus.UNAVAILABLE,
            total_cost=MonetaryAmount(amount=Decimal("1"), currency="EUR"),
        )
    with pytest.raises(ValidationError, match="known tax treatment requires jurisdiction"):
        TaxMetadata(treatment=TaxTreatment.TAXABLE)
    unknown_treatment = TaxMetadata(treatment=TaxTreatment.UNKNOWN, jurisdiction="IT")
    assert unknown_treatment.jurisdiction == "IT"

    draft = make_portfolio_draft()
    assert all(account.tax_metadata == draft.accounts[0].tax_metadata for account in draft.accounts)
    assert not hasattr(draft.positions[0], "tax_metadata")
    assert not hasattr(draft.cash_balances[0], "tax_metadata")
    account_currency_basis = draft.positions[0].model_copy(
        update={
            "cost_basis": PositionCostBasis(
                status=CostBasisStatus.USER_ESTIMATED,
                total_cost=MonetaryAmount(amount=Decimal("900"), currency="EUR"),
            )
        }
    )
    rebuilt = rebuild_portfolio_draft(
        draft,
        positions=(account_currency_basis, *draft.positions[1:]),
    )
    assert rebuilt.positions[0].cost_basis.total_cost is not None
    assert rebuilt.positions[0].cost_basis.total_cost.currency == "EUR"
    assert not hasattr(rebuilt.positions[0], "unrealized_gain")


def test_etf_policy_rejects_ineligible_structures_and_unknown_benchmarks() -> None:
    draft = make_portfolio_draft()
    thematic_policy = draft.etf_eligibility_policy.model_copy(
        update={
            "eligible_etf_ids": (
                "instrument:core-equity-etf",
                "instrument:thematic-etf",
            )
        }
    )
    with pytest.raises(ValidationError, match="eligible ETFs must be diversified"):
        rebuild_portfolio_draft(draft, etf_eligibility_policy=thematic_policy)

    core_etf_profile = draft.instruments[1].etf_profile
    assert core_etf_profile is not None
    derivative_heavy = draft.instruments[1].model_copy(
        update={"etf_profile": core_etf_profile.model_copy(update={"derivative_heavy": True})}
    )
    with pytest.raises(ValidationError, match="not derivative-heavy"):
        rebuild_portfolio_draft(
            draft,
            instruments=(draft.instruments[0], derivative_heavy, draft.instruments[2]),
        )

    missing_policy = draft.etf_eligibility_policy.model_copy(
        update={
            "eligible_etf_ids": ("instrument:missing",),
            "benchmark_instrument_id": "instrument:missing",
        }
    )
    with pytest.raises(ValidationError, match="unknown instrument"):
        rebuild_portfolio_draft(draft, etf_eligibility_policy=missing_policy)

    equity_policy = draft.etf_eligibility_policy.model_copy(
        update={
            "eligible_etf_ids": ("instrument:micron",),
            "benchmark_instrument_id": "instrument:micron",
        }
    )
    with pytest.raises(ValidationError, match="only equity ETFs"):
        rebuild_portfolio_draft(draft, etf_eligibility_policy=equity_policy)


def test_every_state_fact_requires_the_correct_point_in_time_record() -> None:
    draft = make_portfolio_draft()
    wrong_kind = draft.input_records[0].model_copy(
        update={"kind": PortfolioRecordKind.CASH_SNAPSHOT}
    )
    with pytest.raises(ValidationError, match="requires input record kind account_reference"):
        rebuild_portfolio_draft(
            draft,
            input_records=(wrong_kind, *draft.input_records[1:]),
        )

    future = draft.input_records[0].model_copy(
        update={"effective_at": AS_OF + timedelta(seconds=1)}
    )
    with pytest.raises(ValidationError, match="not effective"):
        rebuild_portfolio_draft(
            draft,
            input_records=(future, *draft.input_records[1:]),
        )

    late = draft.input_records[0].model_copy(
        update={
            "available_at": AS_OF - timedelta(days=1),
            "recorded_at": AS_OF + timedelta(days=1),
        }
    )
    with pytest.raises(ValidationError, match="record_not_ingested"):
        rebuild_portfolio_draft(
            draft,
            input_records=(late, *draft.input_records[1:]),
        )

    reconstructed = rebuild_portfolio_draft(
        draft,
        knowledge_boundary=KnowledgeBoundary(
            as_of=AS_OF,
            knowledge_mode=KnowledgeMode.HISTORICAL_RECONSTRUCTION,
        ),
        input_records=(late, *draft.input_records[1:]),
    )
    assert reconstructed.input_records[0].recorded_at > reconstructed.as_of


def test_snapshot_rejects_duplicate_or_orphaned_state() -> None:
    draft = make_portfolio_draft()
    with pytest.raises(ValidationError, match="duplicate position_ids"):
        rebuild_portfolio_draft(
            draft,
            positions=(*draft.positions, draft.positions[0]),
        )

    unknown_account = draft.positions[0].model_copy(update={"account_id": "account:missing"})
    with pytest.raises(ValidationError, match="references an unknown account"):
        rebuild_portfolio_draft(
            draft,
            positions=(unknown_account, *draft.positions[1:]),
        )

    orphan_account = draft.accounts[0].model_copy(update={"account_id": "account:unused"})
    with pytest.raises(ValidationError, match="every account must contain"):
        rebuild_portfolio_draft(
            draft,
            accounts=(*draft.accounts, orphan_account),
        )

    duplicate_price = draft.prices[0].model_copy(update={"price_id": "price:duplicate"})
    with pytest.raises(ValidationError, match="only one price per instrument"):
        rebuild_portfolio_draft(
            draft,
            prices=(*draft.prices, duplicate_price),
        )

    orphan_record = draft.input_records[0].model_copy(
        update={
            "record_id": "70000000-0000-4000-8000-000000000001",
            "provider_record_id": "unused",
        }
    )
    with pytest.raises(ValidationError, match="every input record must support"):
        rebuild_portfolio_draft(
            draft,
            input_records=(*draft.input_records, orphan_record),
        )

    orphan_instrument = draft.instruments[0].model_copy(
        update={
            "instrument_id": "instrument:unused-equity",
            "symbol": "UNUSED",
            "company_subject_id": "company:unused",
        }
    )
    with pytest.raises(ValidationError, match="every instrument must be held"):
        rebuild_portfolio_draft(
            draft,
            instruments=(*draft.instruments, orphan_instrument),
        )


def test_chapter_6a_has_no_exposure_fit_or_allocation_state() -> None:
    fields = set(PortfolioStateDraft.model_fields)

    assert not fields.intersection(
        {
            "opportunity_state",
            "exposures",
            "portfolio_fit",
            "allocation",
            "position_size",
            "execution",
        }
    )
    assert all(
        instrument.instrument_type in {InstrumentType.LISTED_EQUITY, InstrumentType.EQUITY_ETF}
        for instrument in make_portfolio_draft().instruments
    )
