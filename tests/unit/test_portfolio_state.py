"""Deterministic construction and audit-envelope tests for Portfolio State."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.portfolio_state import BuildPortfolioState
from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.portfolio import PortfolioState
from tests.portfolio_factories import make_portfolio_draft, rebuild_portfolio_draft


def test_builder_produces_a_deterministic_content_addressed_state() -> None:
    draft = make_portfolio_draft()
    builder = BuildPortfolioState()

    first = builder.execute(draft)
    second = builder.execute(draft)

    assert first == second
    assert first.portfolio_state_id.version == 5
    assert first.decision_record.record_id.version == 5
    assert len(first.input_fingerprint) == 64
    assert first.decision_record.portfolio_state_id == first.portfolio_state_id
    assert first.decision_record.portfolio_input_fingerprint == first.input_fingerprint
    assert first.decision_record.knowledge_boundary == first.knowledge_boundary
    assert (
        first.decision_record.benchmark_instrument_id
        == first.etf_eligibility_policy.benchmark_instrument_id
    )


def test_fingerprint_ignores_semantically_irrelevant_collection_order() -> None:
    draft = make_portfolio_draft()
    reordered = rebuild_portfolio_draft(
        draft,
        input_records=tuple(reversed(draft.input_records)),
        accounts=tuple(reversed(draft.accounts)),
        instruments=tuple(reversed(draft.instruments)),
        prices=tuple(reversed(draft.prices)),
        positions=tuple(reversed(draft.positions)),
        cash_balances=tuple(reversed(draft.cash_balances)),
        etf_eligibility_policy=draft.etf_eligibility_policy.model_copy(
            update={
                "eligible_etf_ids": tuple(reversed(draft.etf_eligibility_policy.eligible_etf_ids))
            }
        ),
        missing_data=tuple(reversed(draft.missing_data)),
        assumptions=tuple(reversed(draft.assumptions)),
    )

    assert BuildPortfolioState().execute(reordered) == BuildPortfolioState().execute(draft)


def test_fingerprint_changes_for_quantity_price_cost_and_policy_changes() -> None:
    draft = make_portfolio_draft()
    baseline = BuildPortfolioState().execute(draft)

    changed_quantity = draft.positions[0].model_copy(
        update={
            "quantity": Decimal("11"),
            "current_value": MonetaryAmount(amount=Decimal("1210"), currency="USD"),
        }
    )
    quantity_state = BuildPortfolioState().execute(
        rebuild_portfolio_draft(
            draft,
            positions=(changed_quantity, *draft.positions[1:]),
        )
    )
    changed_price = draft.prices[0].model_copy(
        update={"unit_price": MonetaryAmount(amount=Decimal("111"), currency="USD")}
    )
    repriced_position = draft.positions[0].model_copy(
        update={"current_value": MonetaryAmount(amount=Decimal("1110"), currency="USD")}
    )
    price_state = BuildPortfolioState().execute(
        rebuild_portfolio_draft(
            draft,
            prices=(changed_price, *draft.prices[1:]),
            positions=(repriced_position, *draft.positions[1:]),
        )
    )
    changed_cost = draft.positions[0].model_copy(
        update={
            "cost_basis": draft.positions[0].cost_basis.model_copy(
                update={
                    "total_cost": MonetaryAmount(
                        amount=Decimal("901"),
                        currency="USD",
                    )
                }
            )
        }
    )
    cost_state = BuildPortfolioState().execute(
        rebuild_portfolio_draft(
            draft,
            positions=(changed_cost, *draft.positions[1:]),
        )
    )
    changed_policy = draft.etf_eligibility_policy.model_copy(
        update={"policy_version": "core-equity-etf-allow-list-v2"}
    )
    policy_state = BuildPortfolioState().execute(
        rebuild_portfolio_draft(draft, etf_eligibility_policy=changed_policy)
    )

    assert {
        quantity_state.input_fingerprint,
        price_state.input_fingerprint,
        cost_state.input_fingerprint,
        policy_state.input_fingerprint,
    }.isdisjoint({baseline.input_fingerprint})


def test_verified_state_rejects_a_tampered_decision_record_envelope() -> None:
    state = BuildPortfolioState().execute(make_portfolio_draft())
    values = state.model_dump(mode="python")
    values["decision_record"] = state.decision_record.model_copy(
        update={"portfolio_input_fingerprint": "f" * 64}
    )

    with pytest.raises(ValidationError, match="preserve the Portfolio State fingerprint"):
        PortfolioState.model_validate(values)
