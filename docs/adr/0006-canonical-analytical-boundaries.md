# ADR 0006: Canonical temporal and analytical ownership boundaries

- Status: Accepted
- Date: 2026-08-24

## Context

The first portfolio-intelligence spike exposed two architecture failure modes. A cross-domain
knowledge mode was owned by the Opportunity context, forcing unrelated contexts to depend on it.
The spike also recreated standalone opportunity scores inside Portfolio and combined them with
uncalibrated fit weights, thresholds, and sizing defaults. Both patterns violate canonical
ownership and can turn the engine into an opaque 0-100 screener.

## Decision

The Temporal shared kernel owns `KnowledgeMode` and `KnowledgeBoundary`. Evidence, Opportunity,
Market State, Portfolio, Execution, and Learning must apply that same boundary rather than
implement local point-in-time filters.

Analytical ownership is separated as follows:

- Investment Underwriting owns the immutable standalone opportunity assessment;
- Portfolio Exposure owns descriptive look-through and evidence-backed economic dependency state;
- Portfolio Fit compares that standalone assessment with the current portfolio without mutating it;
- Marginal Allocation compares explicit before/after states, constraints, frictions, and competing
  uses of capital;
- Execution owns staging and order planning after an allocation decision.

A contextual scalar may be emitted only by an explicitly versioned and calibrated policy. It
must retain its eligibility gate, component vector, missing inputs, assumptions, and before/after
deltas. Uncalibrated heuristics remain experimental and cannot be active defaults.

## Consequences

- Portfolio code cannot recreate `StandaloneAssessment`, causal quality, valuation, or timing
  scores owned upstream.
- Instrument containment and economic-causal dependency are distinct graph layers with separate
  provenance; shared labels alone are not proof of causality.
- Every derived analytical state declares `as_of`, knowledge mode, method version, input
  fingerprint, missing inputs, conflicts, and assumptions before it can support a decision.
- The existing portfolio spike is research material only and must be rebuilt incrementally under
  these contracts before publication.
