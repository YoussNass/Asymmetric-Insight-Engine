"""Regression test for the Chapter 6C2 same-instrument replacement guard."""

from __future__ import annotations

import pytest

from asymmetric_engine.domain.portfolio import ReplacementTarget, ReplacementTargetKind
from tests.decision_factories import EXISTING_INSTRUMENT_ID, EXISTING_POSITION_ID, make_decision_context
from tests.unit.test_portfolio_policy import (
    REPLACEMENT_TARGET_ID,
    _policy,
    _replacement_builder,
    _replacement_input,
)


def test_replacement_rejects_targeting_the_source_instrument() -> None:
    context = make_decision_context()
    valid_input = _replacement_input(context)
    self_target = ReplacementTarget(
        target_id=REPLACEMENT_TARGET_ID,
        kind=ReplacementTargetKind.EXISTING_HOLDING,
        label="Invalid self-replacement target",
        instrument_id=EXISTING_INSTRUMENT_ID,
        native_currency="USD",
        position_id=EXISTING_POSITION_ID,
    )
    decision_input = valid_input.model_copy(update={"target": self_target})

    with pytest.raises(ValueError, match="target instrument must differ from source instrument"):
        _replacement_builder(context).execute(
            portfolio_state=context.portfolio_state,
            current_exposure=context.current_exposure,
            policy=_policy(context),
            decision_input=decision_input,
        )
