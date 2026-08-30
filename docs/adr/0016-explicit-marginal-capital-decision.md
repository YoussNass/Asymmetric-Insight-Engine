# ADR 0016: Compare one explicit capital unit without a portfolio score

- Status: Proposed
- Date: 2026-08-30

## Context

Accepted ADR 0014 makes factual holdings, eligible instruments, benchmark identity, and cash roles
reproducible at T0. Accepted ADR 0015 derives point-in-time direct and indirect exposure without
making a recommendation. Chapter 6C1 must now answer the first allocative question:

> Of the candidate stock, one eligible existing holding, the declared core ETF, and investment
> cash, which is the best evaluated use of the same next unit of capital?

This is the first point at which AIE may emit an allocation decision. The boundary must preserve
the standalone Opportunity State, expose portfolio interaction, keep every alternative active,
and allow no allocation. It must not reintroduce the rejected universal score, arbitrary weights,
automatic sizing, implicit FX, replacement logic, or Execution authority.

## Complexity Budget

| Gate | Chapter 6C1 evidence |
| --- | --- |
| Decision value | It answers AIE's distinctive marginal-capital question and makes ETF and cash real competitors rather than narrative hurdles. |
| Validatability | Deterministic fixtures falsify incomplete competition, boundary drift, funding misuse, inconsistent ordinal risk, order dependence, tampering, and forced allocation. Prospective investment quality remains unproven until real T0 decisions mature. |
| Architectural necessity | Portfolio Fit is a derived interaction contract and Marginal Allocation owns one decision. Competition for Capital remains policy inside that owner; no new engine or service is created. |
| Data sufficiency | The minimum decision uses accepted Opportunity, State, and Exposure contracts plus explicit qualitative judgements. Missing classification remains unknown and decision confidence remains uncalibrated. |
| Explainability | All four alternatives use the same named amount; every pair exposes standalone case, permanent loss, portfolio effect, uncertainty, rationale, and missing data. |
| Maintenance cost | One deterministic application use case, immutable contracts, a read-only Decision Card projection, and no provider, persistence, HTTP server, optimizer, or frontend framework. |
| Timing | Without 6C1 AIE can describe an idea and a portfolio but cannot decide whether the next unit belongs in the stock, an incumbent, the core ETF, or cash. |

Classification: Portfolio Fit and Marginal Allocation are `CORE NOW` capabilities inside the
accepted Portfolio Decision bounded context. Competition for Capital, ETF/cash hurdles, and the
conservative cash default are `SIMPLE POLICY`. Replacement, friction, PAC, Legacy, and Runner
remain in Slice 6C2.

## Decision

### Join only canonically verified upstream states

`BuildMarginalDecision` must first replay and verify:

- one `ready_for_portfolio_review` Opportunity State;
- one factual Portfolio State;
- one current Portfolio Exposure with no hypothetical position;
- one supplied-hypothetical Exposure for the existing holding;
- one supplied-hypothetical Exposure for the core ETF.

Every input uses exactly one `KnowledgeBoundary`. The application layer joins the bounded
contexts. Portfolio domain contracts retain immutable upstream identifiers, fingerprints, and the
boundary rather than copying complete Causal, Underwriting, State, or Exposure payloads.

### Evaluate one disclosed capital unit

The caller supplies one positive `MonetaryAmount`, a rationale, and the exact investable cash
balance identifiers that could fund it. Emergency reserve cash is rejected. Funding cash must be
known, sufficient, and denominated in the evaluated currency.

The same amount and currency are copied unchanged into all four alternatives. Chapter 6C1 does
not discover, optimize, scale, or round a position size. It performs no currency conversion.

### Require four real alternatives

Every new-capital decision contains exactly:

1. the prospective candidate listed equity;
2. one policy-eligible existing listed-equity holding;
3. the diversified, unleveraged core ETF selected by Portfolio State policy;
4. investment cash.

The candidate is not inserted into factual Portfolio State. Its company identity, native
currency, observed reference price, price date, and price-fact identifier must match the verified
Opportunity State and every valuation-scenario anchor. The candidate permanent-loss assessment
must cite real Underwriting risk identifiers. Other alternatives cannot borrow the candidate's
Underwriting risks.

### Keep Portfolio Fit descriptive

Each alternative receives a content-addressed `PortfolioFit` with native-currency gross value,
company HHI bounds, and changed instrument, company, sector, geography, economic-driver, and
unresolved weights.

- the existing holding and core ETF Fits derive from replayed Chapter 6B before/after states;
- the prospective candidate Fit adds one direct company exposure to the verified current book
  and uses an evidence-backed company profile when available;
- absent candidate classification becomes explicit unknown sector, geography, and driver state;
- the cash Fit leaves securities exposure unchanged.

Economic-driver deltas remain non-additive. A Fit contains no preference, score, hurdle, sizing,
or allocation output.

### Preserve non-interchangeable trade-offs

Each alternative receives an explained ordinal permanent-loss class: `low`, `moderate`, `high`,
or `unknown`. It is not a probability. Candidate support links to Underwriting risks; an unknown
class requires missing-data disclosure.

All six unordered pairs of the four alternatives are mandatory. Each pair reports exactly four
components:

- standalone case;
- permanent-loss risk;
- portfolio effect;
- uncertainty.

A component preference is `first`, `second`, `balanced`, or `unknown`; unknown requires an
explicit missing-data reason. Permanent-loss component direction is checked deterministically
against the disclosed ordinal classes, preventing a second contradictory judgement. The overall
pair conclusion remains an explicit qualitative decision with a rationale. Components are never
averaged and no hidden weights or threshold are applied.

### Allocate only under complete pairwise dominance

A non-cash alternative receives `ALLOCATE` only when it defeats each of the other three
alternatives in the complete pairwise comparison. The selected amount is the original disclosed
capital unit.

If cash defeats all three, or if ties, indeterminate comparisons, or cycles leave no complete
winner, the result is `NO_ALLOCATION` and the capital unit remains investment cash. This is a
conservative policy, not a claim that cash has no risk.

The operator may name the best rejected alternative for the Decision Card. It never overrides the
derived selected outcome.

### Keep `HOLD` outside new-capital allocation

`HOLD` is a separate content-addressed review of an existing position when no new capital unit is
being allocated. It has no amount, replacement, sale, order, or staging field. `HOLD` is therefore
not an alias for `NO_ALLOCATION`, and `REPLACE` remains outside Chapter 6C1.

### Project, but do not decide, at the interface

The interface layer may project a verified Marginal Decision or HOLD review into a compact
Decision Card containing action, amount when relevant, rationale, best rejected alternative,
risks and unknowns, qualitative confidence with calibration status, change conditions, portfolio
effect, T0, and input fingerprint.

The projector rechecks Fit identifiers and fingerprints. Its Execution value is fixed to
`not_evaluated`; it performs no financial calculation and cannot create or alter a decision.

### Content-address and replay every derived record

Portfolio Fits, Marginal Decisions, and HOLD reviews use deterministic canonical ordering,
method versions, complete input fingerprints, and UUIDs derived from those fingerprints.
Deserialized records are trusted only after canonical replay. Input reordering and reversal of a
pair's presentation must not change the resulting record.

## Consequences

### Positive

- AIE can answer its first real capital-allocation question without a universal score.
- ETF and cash remain first-class alternatives and no allocation is operationally possible.
- The exact evaluated amount, currency, source cash, trade-offs, unknowns, and upstream lineage
  remain inspectable.
- Underwriting cannot see or adapt to the portfolio, while Portfolio cannot rewrite the thesis.
- Pairwise cycles and uncertainty fail safely to cash instead of being hidden by arbitrary
  arithmetic.
- The Decision Card is ready for a thin API/frontend without moving financial logic outward.

### Negative

- Complete comparison requires six explicit pair records and disciplined operator judgement.
- Pairwise dominance may decline to allocate even when an operator would accept a weaker total
  ordering.
- Only one supplied amount, one existing holding, and one core ETF are compared per decision.
- Existing alternatives do not yet have symmetrical standalone Underwriting records.
- Qualitative conclusions and loss classes remain uncalibrated and do not prove investment alpha.
- No transaction friction, replacement, execution timing, live data, or persistence is included.

## Rejected alternatives

### Weighted portfolio or fit score

Rejected because weights and thresholds are not calibrated and would hide non-interchangeable
trade-offs behind a number.

### Automatically select a capital amount

Rejected because AIE has no calibrated probability distribution, covariance model, or validated
sizing method. The caller supplies a discrete amount.

### Force the highest-ranked non-cash alternative

Rejected because cycles, ties, and material unknowns are information. The system must be able to
preserve cash.

### Treat the core ETF or cash as a hurdle engine

Rejected because both are ordinary competing alternatives owned by Marginal Allocation, not
separate engines.

### Add the prospective candidate to Portfolio State

Rejected because State records factual holdings and policy, not hypothetical ownership. Fit owns
the interaction view.

### Add replacement, tax, PAC, Runner, or Execution now

Rejected from this slice. They remain preserved in 6C2 and Chapter 7 and may consume the accepted
6C1 decision only after their own contracts are reviewed.

## Acceptance criteria

This ADR may move to `Accepted` only when:

1. all upstream Opportunity, State, and Exposure records are canonically replayed before use;
2. the four alternatives and all six pairwise comparisons are mandatory and use one exact
   capital amount and currency;
3. candidate identity and price bind to the verified Underwriting hand-off;
4. Portfolio Fit remains descriptive and missing classification remains unknown;
5. ordinal permanent-loss comparisons cannot contradict their disclosed assessments;
6. only a complete non-cash pairwise winner produces `ALLOCATE`; all unresolved cases preserve
   cash through `NO_ALLOCATION`;
7. `HOLD` remains a separate no-new-capital record and no `REPLACE` or Execution state enters;
8. Decision Card remains a read-only projection with canonical Fit verification;
9. order-invariance, serialization, integrity replay, anti-tampering, temporal, funding,
   architecture, and vertical-slice tests pass;
10. required local checks and exact-head Python and container CI pass;
11. the owner explicitly authorizes the Chapter 6C1 merge.
