# ADR 0005: Adjacent applications and experimental models stay outside the core

- Status: Accepted
- Date: 2026-08-19

## Context

The project includes prior work on a Market Screener and a Quantum Cycle Model. Treating either
as the engine foundation would mix application-specific presentation or a narrow experimental
model with the canonical evidence-to-portfolio decision chain.

## Decision

The Market Screener remains a separate application. It may consume stable shared contracts and
application use cases, but it must not duplicate or own engine domain logic.

The Quantum Cycle Model remains an experimental use-case adapter and reference implementation.
It may evaluate sector regimes, relative strength, divergences, and systemic or idiosyncratic
risk for its defined universe, but it neither predicts prices with certainty nor defines the
core architecture.

## Consequences

- The engine can evolve independently of one interface or sector model.
- Useful experimental logic can graduate behind stable ports after validation.
- Scores or assumptions specific to the Quantum Cycle Model cannot become universal engine
  semantics by accident.
- The Market Screener must integrate through versioned contracts rather than source duplication.
