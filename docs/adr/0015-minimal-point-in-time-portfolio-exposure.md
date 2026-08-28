# ADR 0015: Derive minimal point-in-time Portfolio Exposure

- Status: Accepted
- Date: 2026-08-28

## Context

Accepted ADR 0014 gives Portfolio one immutable factual state, but ticker-level positions hide
economic concentration inside ETFs and shared company classifications. Chapter 6B must make that
exposure visible before Marginal Allocation can compare alternatives. It must do so without
promoting the rejected Portfolio Exposure Graph spike, mixing currencies, treating missing
constituents as diversification, or introducing Portfolio Fit and allocation authority early.

ADR 0006 assigns descriptive instrument look-through and evidence-backed economic dependency
state to Portfolio Exposure. ADR 0012 limits the first implementation to one-level ETF holdings,
simple concentration metrics, explicit uncertainty, and supplied before/after amounts.

## Complexity Budget

| Gate | Chapter 6B evidence |
| --- | --- |
| Decision value | Reveals direct and hidden indirect company, sector, geography, and driver exposure required by later capital comparisons. |
| Validatability | Deterministic fixtures falsify temporal, containment, currency, reconciliation, residual, ordering, and replay errors. Prospective investment usefulness remains a later measurement. |
| Architectural necessity | `PortfolioExposure` is a derived contract and `BuildPortfolioExposure` is one pure capability inside Portfolio Decision; neither is an engine or service. |
| Data sufficiency | Requires point-in-time ETF holdings and evidence-backed classifications with coverage and residual disclosure. Deterministic fixtures validate the boundary without claiming provider completeness. |
| Explainability | Every company route, source instrument, native-currency amount, classification claim, missing residual, Top-N result, and HHI bound remains inspectable. |
| Maintenance cost | One-level look-through only; no recursive graph, factor model, covariance, optimizer, provider, or persistence adapter. |
| Timing | Marginal comparison cannot explain portfolio interaction until current and supplied hypothetical exposure can be reproduced. |

Classification: Portfolio Exposure is a `CORE NOW` derived capability inside the accepted
Portfolio Decision bounded context. Position weight, Top-N, and HHI bounds are descriptive
`CORE NOW` metrics. Economic-driver labels are evidence-backed state and never an active score.

## Decision

### Consume a verified Portfolio State by reference

`BuildPortfolioExposure` first replays the supplied `PortfolioState` through its canonical
integrity verifier. The derived state retains only the upstream state identifier, portfolio
identifier, input fingerprint, and knowledge boundary; it does not recursively copy accounts,
positions, cash, or policy.

The exposure input must use that exact knowledge boundary. Its evidence, claims, ETF snapshots,
classifications, missing data, conflicts, and assumptions are canonicalized and content-addressed.
The complete derived state can be rebuilt to detect altered inputs, metrics, or identifiers.

### Admit one-level ETF company containment only

An ETF snapshot contains:

- one canonical ETF instrument identifier;
- holdings effective date and evidence identifier;
- resolved underlying company identifiers and weights;
- explicit coverage through `1 - unresolved_weight`;
- a required reason for every positive unresolved residual.

Resolved weights plus the residual must equal one. The contract does not recursively expand a
constituent fund, infer omitted constituents, or equate fund membership with economic causality.
Every held ETF and every ETF used in a supplied hypothetical view requires exactly one snapshot.

### Keep containment and classification provenance separate

ETF membership is backed by snapshot evidence. Sector, primary economic geography, and economic
driver tags are backed by typed claims and their evidence. The two evidence sets must be disjoint.
Economic-driver tags require an inference, hypothesis, or qualitative-judgement claim; an
observation or shared label alone is not admitted as a driver mechanism.

Claim confidence and calibration status remain visible. Uncalibrated confidence never gates,
ranks, scores, sizes, or allocates. Missing sector, geography, or driver classification is an
explicit dimension with a reason, never an invented value.

### Derive native-currency exposure books

Exposure is grouped by the currency of the held instrument:

- listed-equity value becomes direct exposure to its canonical company;
- ETF constituent value becomes indirect exposure in the ETF position's currency;
- unresolved ETF weight and unsupported legacy instruments remain an explicit unknown amount;
- instrument weights, company exposure, sector, geography, and economic-driver tags are reported
  inside each currency book.

No EUR, USD, or other books are aggregated without a separately admitted point-in-time FX
contract. Economic-driver tags may overlap and are explicitly non-additive.

### Bound HHI instead of converting unknown to zero

For each currency book, resolved company weights produce:

```text
HHI lower bound = sum(resolved company weight squared)
HHI upper bound = lower bound + unresolved weight squared
```

The lower bound represents an unresolved residual split across arbitrarily many companies; the
upper bound represents it concentrated in one company. Neither bound is an allocation gate or a
claim of cross-currency portfolio concentration. Top-N uses an explicit, fingerprinted `N`, lists
only resolved companies, and leaves unresolved weight adjacent to the metric.

### Keep hypothetical exposure descriptive

An optional hypothetical position supplies a positive amount, rationale, and canonical
instrument identifier. It must use the instrument's native currency and the instrument must
already be eligible for new capital under Portfolio State policy. The builder returns immutable
`before` and `hypothetical_after` snapshots without mutating Portfolio State.

This Chapter 6B slice does not choose the instrument or amount. Because Portfolio State does not
contain unheld candidate equities, the first reference case uses the eligible core ETF. Chapter
6C will admit the separate Underwriting hand-off needed to compare a new stock candidate; Chapter
6B does not import or recreate Opportunity State.

### Exclude decision authority

Chapter 6B contains no Portfolio Fit score, structural correlation, factor exposure, effective
independent bets, permanent-loss aggregation, sizing, hurdle, replacement, tax comparison,
allocation outcome, market regime, or execution instruction.

## Consequences

### Positive

- Hidden ETF company exposure becomes visible without making the graph a source of truth.
- Missing holdings remain unknown rather than false diversification.
- Direct and indirect routes retain their source instruments.
- Classifications remain evidence-backed and epistemically typed.
- Native-currency books prevent implicit FX.
- Before/after views become available for later marginal comparison without pre-empting it.

### Negative

- One-level look-through leaves fund-of-fund exposure unresolved.
- HHI is a currency-specific interval rather than one convenient portfolio number.
- Economic-driver tags are interpretive, overlapping, and initially uncalibrated.
- A new unheld stock candidate cannot enter the hypothetical view until Chapter 6C supplies the
  accepted Underwriting-to-Portfolio hand-off.
- Deterministic fixtures do not establish live ETF-provider coverage or timeliness.

## Rejected alternatives

### Promote the earlier Portfolio Exposure Graph spike

Rejected because its graph coupled factual state, scoring, fit, risk, sizing, and market overlay.
The graph is at most a derived implementation view, never the factual source of truth.

### Treat missing constituents as zero overlap

Rejected because absence of evidence is unknown, not diversification. Residual weight remains
explicit and widens the HHI interval.

### Compute one portfolio HHI through implicit FX

Rejected because Chapter 6B has no point-in-time FX source or conversion policy.

### Add recursive funds, suppliers, factors, or dynamic correlation now

Rejected from active scope under ADR 0012. Those capabilities remain in the deferred register and
require a measured failure of this simpler view plus an approved validation plan.

## Acceptance criteria

This ADR may move to `Accepted` only when:

1. Portfolio State replay is mandatory before derivation;
2. one-level ETF weights, coverage, provenance, and unresolved residual reconcile at T0;
3. currencies remain separate and HHI exposes lower and upper bounds;
4. containment evidence and classification claims remain separate;
5. no Fit, score, sizing, allocation, execution, or deferred model enters the slice;
6. required local checks and exact-head Python and container CI pass;
7. the owner explicitly authorizes the Chapter 6B merge.
