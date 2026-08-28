"""Cross-domain financial value objects with explicit native currency."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

CurrencyCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        pattern=r"^[A-Z]{3}$",
    ),
]


def canonical_decimal(value: Decimal) -> Decimal:
    """Remove representation-only zeroes after finiteness validation."""

    if not value.is_finite():
        raise ValueError("monetary amounts must be finite")
    if value.is_zero():
        return Decimal(0)
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return normalized.quantize(Decimal(1))
    return normalized


class MonetaryAmount(BaseModel):
    """A non-negative amount that can never lose its native currency."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    amount: Decimal = Field(ge=0, allow_inf_nan=False)
    currency: CurrencyCode

    @field_validator("amount")
    @classmethod
    def normalize_amount(cls, value: Decimal) -> Decimal:
        return canonical_decimal(value)
