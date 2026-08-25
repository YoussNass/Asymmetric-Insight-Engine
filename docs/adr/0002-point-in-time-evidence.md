# ADR 0002: Point-in-time evidence is foundational

- Status: Accepted
- Date: 2026-08-17

## Context

An apparent historical insight is invalid when it uses filings, estimates, revisions, constituent
lists, or classifications that were unavailable at the decision time.

## Decision

Every evidence record stores effective, availability, and recording timestamps. Every analytical
output stores an `as_of` timestamp and explicitly selects one knowledge mode:

- `historical_reconstruction` requires `available_at <= as_of`;
- `live_system_replay` requires both `available_at <= as_of` and `recorded_at <= as_of`.

No mode is inferred from context or silently defaulted.
Historical reconstruction may use a record ingested later only when its payload faithfully
represents the source version that was available by `as_of`; a current restatement is not a
substitute for the historical snapshot.

## Consequences

- Temporal semantics are part of domain contracts rather than optional backtest settings.
- Provider adapters must preserve publication and ingestion times.
- Historical research and operational replay cannot be mistaken for one another.
- Restated data cannot silently overwrite prior knowledge.
- Anti-hindsight tests become possible from the first vertical slice.
