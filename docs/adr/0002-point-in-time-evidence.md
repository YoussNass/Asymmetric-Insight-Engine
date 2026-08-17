# ADR 0002: Point-in-time evidence is foundational

- Status: Accepted
- Date: 2026-08-17

## Context

An apparent historical insight is invalid when it uses filings, estimates, revisions, constituent
lists, or classifications that were unavailable at the decision time.

## Decision

Every evidence record stores effective, availability, and recording timestamps. Every analytical
output stores an `as_of` timestamp and rejects evidence that was not yet available.

## Consequences

- Temporal semantics are part of domain contracts rather than optional backtest settings.
- Provider adapters must preserve publication and ingestion times.
- Restated data cannot silently overwrite prior knowledge.
- Anti-hindsight tests become possible from the first vertical slice.
