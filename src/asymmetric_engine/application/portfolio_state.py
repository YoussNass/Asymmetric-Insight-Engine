"""Build a deterministic, content-addressed factual Portfolio State."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from asymmetric_engine.domain.portfolio import (
    PortfolioState,
    PortfolioStateDraft,
    T0DecisionRecordEnvelope,
)


class BuildPortfolioState:
    """Canonicalize a T0 snapshot without adding exposure or allocation logic."""

    def execute(self, draft: PortfolioStateDraft) -> PortfolioState:
        """Return the same state and audit envelope for the same semantic input."""

        canonical_draft = self._canonicalize_draft(draft)
        canonical_json = json.dumps(
            canonical_draft.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        fingerprint = sha256(canonical_json).hexdigest()
        portfolio_state_id = uuid5(
            NAMESPACE_URL,
            f"asymmetric-insight-engine:portfolio-state:{fingerprint}",
        )
        decision_record = T0DecisionRecordEnvelope(
            record_id=uuid5(
                NAMESPACE_URL,
                f"asymmetric-insight-engine:portfolio-t0-record:{fingerprint}",
            ),
            portfolio_state_id=portfolio_state_id,
            portfolio_input_fingerprint=fingerprint,
            knowledge_boundary=canonical_draft.knowledge_boundary,
            benchmark_instrument_id=(
                canonical_draft.etf_eligibility_policy.benchmark_instrument_id
            ),
            method_version=canonical_draft.method_version,
        )
        return PortfolioState.model_validate(
            {
                **canonical_draft.model_dump(mode="python"),
                "portfolio_state_id": portfolio_state_id,
                "input_fingerprint": fingerprint,
                "decision_record": decision_record,
            }
        )

    @staticmethod
    def _canonicalize_draft(draft: PortfolioStateDraft) -> PortfolioStateDraft:
        """Sort only semantically unordered collections before fingerprinting."""

        values: dict[str, Any] = draft.model_dump(mode="python")
        values["input_records"] = tuple(
            sorted(draft.input_records, key=lambda item: str(item.record_id))
        )
        values["accounts"] = tuple(sorted(draft.accounts, key=lambda item: item.account_id))
        values["instruments"] = tuple(
            sorted(draft.instruments, key=lambda item: item.instrument_id)
        )
        values["prices"] = tuple(sorted(draft.prices, key=lambda item: item.price_id))
        values["positions"] = tuple(sorted(draft.positions, key=lambda item: item.position_id))
        values["cash_balances"] = tuple(sorted(draft.cash_balances, key=lambda item: item.cash_id))
        values["etf_eligibility_policy"] = draft.etf_eligibility_policy.model_copy(
            update={
                "eligible_etf_ids": tuple(sorted(draft.etf_eligibility_policy.eligible_etf_ids))
            }
        )
        for field in ("missing_data", "conflicts", "assumptions"):
            values[field] = tuple(sorted(getattr(draft, field)))
        return PortfolioStateDraft.model_validate(values)
