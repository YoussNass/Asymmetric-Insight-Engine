"""Shared native-currency value-object invariants."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from asymmetric_engine.domain.financial import MonetaryAmount, canonical_decimal


def test_monetary_amount_normalizes_representation_without_losing_currency() -> None:
    amount = MonetaryAmount(amount=Decimal("100.5000"), currency="EUR")

    assert amount.amount == Decimal("100.5")
    assert amount.currency == "EUR"
    assert canonical_decimal(Decimal("0.000")) == Decimal(0)
    assert canonical_decimal(Decimal("10.000")) == Decimal("10")


def test_monetary_amount_rejects_negative_and_non_finite_values() -> None:
    with pytest.raises(ValidationError):
        MonetaryAmount(amount=Decimal("-0.01"), currency="EUR")
    with pytest.raises(ValueError, match="must be finite"):
        canonical_decimal(Decimal("Infinity"))
