"""End-to-end Chapter 6A factual snapshot and replay boundary."""

from __future__ import annotations

from decimal import Decimal

from asymmetric_engine.application.portfolio_state import BuildPortfolioState
from asymmetric_engine.domain.portfolio import PortfolioState
from tests.portfolio_factories import make_portfolio_draft


def test_portfolio_state_round_trip_reproduces_owned_and_available_capital_at_t0() -> None:
    state = BuildPortfolioState().execute(make_portfolio_draft())
    restored = PortfolioState.model_validate_json(state.model_dump_json())

    assert restored == state
    assert BuildPortfolioState().verify(restored) == state
    assert restored.position_values_by_currency() == {
        "EUR": Decimal("200"),
        "USD": Decimal("1100"),
    }
    assert restored.cash_values_by_currency(investable_only=True) == {
        "EUR": Decimal("1000"),
        "USD": Decimal("200"),
    }
    assert restored.decision_record.portfolio_state_id == restored.portfolio_state_id
    assert not hasattr(restored, "allocation_decision")
    assert not hasattr(restored, "portfolio_score")
