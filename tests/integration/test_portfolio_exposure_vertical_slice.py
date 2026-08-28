"""Integration test for the Chapter 6B Portfolio Exposure hand-off."""

from __future__ import annotations

from decimal import Decimal

from asymmetric_engine.application.portfolio_exposure import BuildPortfolioExposure
from asymmetric_engine.application.portfolio_state import BuildPortfolioState
from asymmetric_engine.domain.portfolio import PortfolioExposure
from tests.exposure_factories import MICRON_COMPANY_ID, make_exposure_input
from tests.portfolio_factories import make_portfolio_draft


def test_verified_portfolio_state_derives_auditable_before_after_exposure() -> None:
    state_builder = BuildPortfolioState()
    portfolio_state = state_builder.execute(make_portfolio_draft())
    exposure_builder = BuildPortfolioExposure(state_builder=state_builder)
    exposure = exposure_builder.execute(portfolio_state, make_exposure_input())
    restored = PortfolioExposure.model_validate_json(exposure.model_dump_json())

    assert exposure_builder.verify(portfolio_state, restored) == exposure
    assert restored.portfolio_state.portfolio_state_id == portfolio_state.portfolio_state_id
    assert restored.portfolio_state.input_fingerprint == portfolio_state.input_fingerprint
    assert not hasattr(restored.portfolio_state, "positions")
    assert restored.before.currency_books[0].unresolved_exposure.weight == Decimal("0.1")
    assert restored.after is not None
    eur_after = restored.after.currency_books[0]
    micron = next(
        item for item in eur_after.company_exposures if item.company_subject_id == MICRON_COMPANY_ID
    )
    assert micron.indirect_instrument_ids == (
        "instrument:core-equity-etf",
        "instrument:thematic-etf",
    )
    assert all(
        claim.confidence.calibration_status.value == "uncalibrated" for claim in restored.claims
    )
