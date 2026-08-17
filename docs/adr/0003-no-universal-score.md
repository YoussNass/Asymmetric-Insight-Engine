# ADR 0003: No universal magic score

- Status: Accepted
- Date: 2026-08-17

## Context

Trend, causal confidence, valuation, downside, liquidity, timing, and portfolio fit are not
interchangeable. Combining every feature into one scalar hides conflicts and double-counts
information.

## Decision

Use hard eligibility gates, a multidimensional state vector, calibrated scenario distributions,
and a portfolio-conditional utility function. Context-specific rankings may be derived from this
state but cannot replace it.

## Consequences

- Conflicting signals remain inspectable.
- Company quality stays distinct from portfolio suitability.
- Weights and transformations require provenance, calibration, and stability testing.
