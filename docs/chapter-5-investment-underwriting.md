# Chapter 5: Standalone investment underwriting

## Purpose

Chapter 5 determines whether a causal beneficiary hypothesis is sufficiently complete,
falsifiable, and economically explicit to be reviewed by the future Portfolio bounded context.
It does not decide whether the user should buy, how much capital to allocate, or when to trade.

## Input and output boundary

| Boundary | Required input or output | Explicitly excluded |
| --- | --- | --- |
| Input | One immutable `ready_for_underwriting` causal analysis | Incomplete or different-company causal cases |
| Time | Same `as_of` and `knowledge_mode` as the causal analysis | Later facts, silent backfills, mixed replay modes |
| Sources | Independently verified immutable causal and financial documents | Unverified URLs or altered bytes |
| Output | Immutable standalone Opportunity State | Portfolio recommendation or allocation |

The builder accepts no holdings, cash balance, benchmark, market regime, risk budget, correlation,
tax lot, position-size, timing, or order input. Consequently, identical analytical inputs must
produce identical output for every portfolio and user.

## Financial facts and formulas

Financial facts preserve the distinction between what the candidate reported and what an analyst
adjusted. Every fact states its metric, decimal value, unit, period, basis, and supporting claims.
An adjustment without an explanation is invalid. A duration metric cannot be attached to an
instant date, and a balance-sheet metric cannot be attached to a duration period.

Derived values are not trusted just because they were supplied. The domain recomputes these first
canonical formulas:

| Derived metric | Formula |
| --- | --- |
| Revenue growth | `(current revenue - prior revenue) / prior revenue` |
| Gross margin | `gross profit / revenue` |
| Free cash flow | `operating cash flow - capital expenditures` |
| Net debt | `total debt - cash and investments` |
| Diluted-share growth | `(current diluted shares - prior diluted shares) / prior diluted shares` |
| ROIC | `NOPAT / invested capital` |

Every formula has an explicit calculation version. Units, metric identity, compatible periods,
distinct inputs, non-zero denominators, and submitted outputs are validated with decimal
arithmetic.

## Eight-dimensional state

The Opportunity State preserves exactly these dimensions rather than averaging them:

| Dimension | Question |
| --- | --- |
| Revenue and margins | Is growth economically meaningful, and what is happening to margins? |
| Cash and earnings quality | Do reported earnings convert into cash after capital expenditure? |
| ROIC | Is operating profit adequate relative to invested capital? |
| Balance sheet and capital needs | Can the company fund the thesis and survive adverse outcomes? |
| Dilution and per-share economics | Does value accrue to each diluted share rather than only to the enterprise? |
| Value capture and competition | Can the causal beneficiary retain economics after rivalry and bargaining? |
| Operating execution | Can management and operations deliver the required capacity, product, and timing? |
| Valuation and asymmetry | What explicit per-share outcomes follow under bear, base, and bull assumptions? |

Each dimension independently reports `positive`, `mixed`, `negative`, or `unknown`, together with
its rationale, lineage, missing data, conflicts, assumptions, and invalidations. An unknown
dimension remains unknown; it is never converted into zero or silently offset by a positive one.

## Eligibility gates

Readiness uses six categorical gates:

1. the causal hand-off is valid;
2. the company can plausibly survive the underwriting horizon;
3. economic value capture has explicit support;
4. per-share integrity is visible;
5. valuation is arithmetically and evidentially complete;
6. the case is falsifiable.

A gate may be `pass`, `fail`, or `unknown`. `ready_for_portfolio_review` requires all six to pass,
but that status is structural. It says the case can be reviewed downstream, not that its economics
are good or that capital should be allocated.

## Valuation scenarios

Bear, base, and bull scenarios expose a common per-share bridge:

```text
enterprise value
- net debt
= equity value
/ diluted shares
= implied price per share
/ reference price - 1
= scenario return
```

Each scenario keeps its method version, assumptions, inferential claim support, fact support, and
invalidation conditions. The reference price must match its fact exactly; current diluted shares
and net debt anchor, but do not conceal, scenario-specific assumptions. The three implied prices
and returns must be strictly ordered.

Chapter 5 intentionally assigns no probabilities. The system has not yet admitted a calibrated
forecast distribution, so numeric probabilities would create false precision. The optional
upside-to-downside ratio is only the reproducible quotient of explicit bull upside and absolute
bear downside. No gate, rank, or size is derived from it.

## Reference case and source limits

The reference case continues the Chapter 4 Micron hypothesis. Selected reported values are tied to
the official
[Micron fiscal 2025 Form 10-K](https://www.sec.gov/Archives/edgar/data/723125/000072312525000028/mu-20250828.htm),
including revenue, gross profit, cash flow, capital expenditure, cash and investments, debt,
diluted shares, and stock-based compensation.

Tests store only short synthetic fixture excerpts with the real filing identity. The synthetic
market source uses a round USD 100 reference price, and scenario enterprise values, NOPAT, invested
capital, and some interpretive claims are explicitly illustrative and uncalibrated. These choices
make the contract deterministic; they must not be read as current Micron data or advice.

## Reproducibility and failure behaviour

The application builder:

1. re-verifies every source's byte length and SHA-256 and confirms that causal sources still match
   the immutable versions embedded in the hand-off;
2. validates source metadata and exact evidence provenance;
3. applies the same temporal boundary used by the causal analysis;
4. validates all claim, fact, dimension, gate, scenario, catalyst, and risk references;
5. canonicalizes unordered collections;
6. hashes the complete material state and derives a deterministic identifier.

Missing sources, altered bytes, future facts, reused identifiers, mismatched formulas, unsupported
scenarios, incomplete lineages, duplicate dimensions or gates, and invalid readiness fail closed.

## Deferred work

Chapter 5 does not add:

- automated filing extraction or complete financial-statement normalization;
- consensus forecasts, calibrated scenario probabilities, or a return distribution;
- an aggregate opportunity score, active weights, ranking, or threshold policy;
- Market State, portfolio look-through, portfolio fit, marginal allocation, or tax logic;
- position sizing, timing, execution, live orders, or brokerage connectivity;
- a complete production database or user interface.
