# AIE delivery roadmap

## Status and authority

This document is the canonical delivery sequence under accepted ADR 0012. It does not declare a
capability implemented; the code, accepted ADRs, tests, and merged pull requests remain the
implementation record.

At the time of this roadmap:

- Chapters 2, 3, 4, and 5 are complete in `main`;
- no canonical Portfolio, Market State, Execution, or Learning implementation exists;
- the earlier Portfolio Exposure Graph spike is research material only under ADR 0006.

Every roadmap change must pass the [`Complexity Budget`](complexity-budget.md). Deferred items are
preserved with graduation criteria instead of being silently discarded or implemented early.

## Product mental model

Users and developers should be able to understand AIE through five questions:

```text
UNDERSTAND -> UNDERWRITE -> ALLOCATE -> EXECUTE -> LEARN
```

This is a conceptual flow, not a requirement for exactly five bounded contexts. Evidence and the
Temporal shared kernel support every stage.

| Stage | Minimum responsibility |
| --- | --- |
| Understand | Evidence, human-assisted discovery, and falsifiable causal beneficiary mapping |
| Underwrite | Immutable standalone company and opportunity state at the current price |
| Allocate | Portfolio state, exposure, interaction, competing alternatives, and marginal capital decision |
| Execute | Implement an approved amount through explicit staging without rewriting the thesis |
| Learn | Compare the T0 record with realized outcomes and the declared benchmark |

## Mandatory sequencing gate

The prerequisites for Chapter 6 were satisfied on 2026-08-27:

1. Chapter 5 was reviewed, corrected, accepted, and merged;
2. ADR 0012 and ADR 0013 were explicitly accepted;
3. the minimal ETF-scope Constitution amendment was approved;
4. the owner authorized the compressed roadmap and Chapter 6A as the next slice.

Each later slice still requires its own narrow branch, tests, draft pull request, and explicit
merge authorization. Approval of this roadmap does not authorize merging an unreviewed future
implementation.

## Active minimum-complete roadmap

### Chapter 6A — Portfolio State, instruments, and capital

**Purpose:** establish the factual state consumed by every later portfolio calculation.

**Status:** complete; ADR 0014 accepted and implementation merged with exact-head local and remote
verification.

In scope:

- immutable portfolio snapshot and canonical knowledge boundary;
- positions, quantities, prices, currencies, and current values;
- instrument identity and type;
- investment cash and explicit cash roles;
- basic cost-basis and tax metadata without tax optimization;
- benchmark identity;
- T0 input fingerprint and decision-record envelope.

Out of scope:

- ETF constituent expansion;
- portfolio fit or allocation decisions;
- automatic sizing;
- market regimes or execution timing.

Exit criterion: AIE can reproduce what was owned and what capital was available at T0 without
making an allocation recommendation.

The contract and deterministic reference case are documented in
[`chapter-6a-portfolio-state.md`](chapter-6a-portfolio-state.md). Chapter 6B is the next authorized
implementation slice; it still requires its own branch, tests, draft pull request, review, and
explicit merge authorization.

### Chapter 6B — Minimal Portfolio Exposure

**Purpose:** expose hidden direct and indirect economic concentration descriptively.

In scope:

```text
holding -> instrument -> underlying company -> sector -> geography -> economic driver
```

- direct and indirect exposure;
- one-level ETF constituent snapshots initially;
- point-in-time holdings date, source, coverage, and unresolved residual;
- position weight, Top-N concentration, and HHI;
- evidence-backed economic-driver labels with uncertainty;
- before/after exposure snapshots for a supplied hypothetical position.

Instrument containment and economic-driver classification retain separate provenance. ETF
membership, a shared label, or correlation is not causal evidence.

Out of scope:

- structural-correlation scores;
- factor exposure and factor crowding;
- supplier and catalyst graphs;
- effective independent bets;
- risk-weighted loss aggregation;
- allocation or execution decisions.

Exit criterion: AIE can explain hidden exposure without modifying the Opportunity State or
claiming unknown dependencies are diversification.

### Chapter 6C — Marginal Portfolio Decision

Portfolio Fit is an immutable interaction view inside this chapter, not a separate score engine.
Marginal Allocation owns the decision.

#### Slice 6C1 — New capital and competing alternatives

Compare explicit before/after states for:

- candidate stock;
- an existing holding;
- the declared core ETF;
- investment cash.

Use standalone underwriting, exposure overlap, basic concentration, ordinal permanent-loss risk,
explicit uncertainty, and disclosed candidate allocation amounts. The minimum decision
vocabulary is:

- `ALLOCATE`;
- `HOLD`;
- `NO_ALLOCATION`.

`ALLOCATE` deploys a named discrete amount to a named alternative. `NO_ALLOCATION` keeps the
evaluated unit as investment cash because no alternative clears the comparison. `HOLD` applies to
an existing-position review when no new unit of capital is being allocated; it is not an alias for
`NO_ALLOCATION`. `REPLACE` enters only in Slice 6C2 after explicit friction.

The core ETF and cash are alternatives, not dedicated engines. The system must preserve the
components and trade-offs rather than emit an uncalibrated portfolio score.

Every derived Exposure, Fit, and Marginal Allocation state declares `as_of`, knowledge mode,
method version, input fingerprint, missing inputs, conflicts, and assumptions in accordance with
ADR 0006.

#### Slice 6C2 — Replacement and capital-flow policies

Add only after 6C1 is prospectively usable:

- `REPLACE` comparison;
- basic tax, spread, fee, liquidity, and switching friction;
- new-capital/PAC-first funding policy;
- `LEGACY_HOLD_ZERO_NEW_CAPITAL`;
- `RUNNER` state without treating recovered cost as free capital;
- owner-defined risk-budget and concentration constraints.

Exit criterion: AIE can explain the best evaluated use of the next unit of capital and can return
no allocation. It compares discrete, explicit amounts; it does not derive an automatic Kelly-like
size.

### Chapter 7 — Execution MVP

**Purpose:** implement, but never recreate, an approved allocation decision.

Minimum outputs:

- `NOW`;
- `STAGED`;
- `WAIT`;
- `INVALIDATED`.

Allocation owns the target capital amount. Execution owns tranche and order staging. Market data,
liquidity, spreads, and upstream invalidation conditions may change implementation, not company
quality or standalone value.

Out of scope initially:

- automated order submission;
- a market-timing score;
- all-in/all-out regime rules;
- automatic changes to the strategic allocation.

### Chapter 8 — Learning MVP

**Purpose:** determine whether active AIE decisions deserve additional capital.

Record from the first decision:

- decision timestamp and knowledge boundary;
- benchmark and price at T0;
- expected scenario range and horizon;
- selected alternative and reason;
- realized return and benchmark return;
- excess return and maximum drawdown;
- thesis and invalidation outcomes;
- expected versus realized payoff;
- forecast-calibration observations.

CAGR, volatility, Sharpe, Sortino, and Information Ratio may be shown only when sample size and
horizon make them meaningful. Factor-adjusted alpha remains deferred until the data supports a
defensible model.

## Portfolio concepts that remain policies or state

The following do not receive independent engines or chapters:

| Concept | Canonical representation | Owner |
| --- | --- | --- |
| Competition for Capital | Requirement to evaluate explicit alternatives | Marginal Allocation |
| ETF and cash hurdle | Competing alternatives | Marginal Allocation |
| No allocation | Valid decision outcome | Marginal Allocation |
| Replacement | After-friction comparison policy | Marginal Allocation |
| PAC / new capital first | Funding policy | Marginal Allocation |
| Emergency reserve | Non-investable cash role | Portfolio State |
| Strategic/opportunistic/unallocated cash | Cash-role state | Portfolio State |
| Legacy holding | Holding state plus zero-new-capital policy | Portfolio Decision |
| Runner | Holding state and monitoring policy | Portfolio Decision |
| Concentrated compounder profile | Explicit risk-policy configuration | Marginal Allocation |

## Deferred capability register

Deferred capabilities remain visible and may graduate only after the listed trigger is observed.

| Capability | Current class | Prerequisite | Graduation trigger | Future owner |
| --- | --- | --- | --- | --- |
| Automated Insight Discovery | `DEFER` | Expected-source universe and validated extraction | Manual discovery throughput or coverage is a measured bottleneck | Understand |
| Opportunity archetypes | `EXPERIMENTAL` | Sufficient cases with common evidence failures | Archetype metadata demonstrably improves completeness or monitoring | Underwriting configuration |
| Special Situations discovery | `EXPERIMENTAL` | Reliable corporate-action evidence path | Prospective cases show decision value outside causal secular discovery | Understand adapter |
| Multi-level fund look-through | `DEFER` | Real portfolio contains material fund-of-fund exposure | One-level unresolved residual changes a decision materially | Portfolio Exposure |
| Supplier dependencies | `DEFER` | Evidence-backed dependency data | Sector/driver view misses a documented material concentration | Portfolio Exposure |
| Catalyst clustering | `DEFER` | Versioned catalyst data | Common event timing changes a real portfolio decision | Portfolio Exposure |
| Factor exposure/crowding | `DEFER` | Point-in-time factor definitions and histories | Simple exposure views repeatedly miss documented common risk | Portfolio Exposure/Fit |
| Dynamic correlation | `DEFER` | Stable return history and validation baseline | Static/ordinal dependencies produce measured decision errors | Portfolio Fit |
| Effective independent bets | `DEFER` | Admitted correlation/dependency model | Name/driver concentration is demonstrably insufficient | Portfolio Fit metric |
| Tail-risk aggregation | `DEFER` | Calibrated loss inputs | Ordinal permanent-loss classes cannot distinguish material choices | Portfolio Fit |
| Automated sizing | `REJECT` as V1 default | Calibrated distributions and prospective validation | Explicit discrete sizes repeatedly fail against a validated method | Marginal Allocation policy |
| Advanced tax-lot optimization | `DEFER` | Complete tax lots and verified adapter | Basic tax friction causes material avoidable loss | Marginal Allocation policy |
| Market State engine | `DEFER` | Prospective signals and execution baseline | A simple execution policy shows persistent timing failure | Execution input |
| Factor-adjusted alpha | `DEFER` | Adequate decision sample and factor histories | Basic benchmark attribution is statistically insufficient | Learning |
| Monte Carlo/Bayesian optimizer | `REJECT` as V1 default | Calibrated distributions, covariance, and benchmark | Simpler marginal comparison has a measured, reproducible failure | Experimental allocation adapter |

No deferred capability may become an active default solely because synthetic tests pass.

## Standard decision card

Every active capital decision should be renderable as:

```text
DECISION
ALLOCATE amount / HOLD / REPLACE / NO ALLOCATION

WHY
Three to five material drivers

BEST ALTERNATIVE
Core ETF / Cash / Existing Holding

MAIN RISKS AND UNKNOWNS

CONFIDENCE
Including calibration status

WHAT WOULD CHANGE THE DECISION

PORTFOLIO EFFECT
Before/after weight, concentration, driver overlap, tax and cost deltas

EXECUTION
NOW / STAGED / WAIT / INVALIDATED

AS OF AND INPUT FINGERPRINT
```

The card is a view over inspectable states. It must not hide uncertainty behind a synthetic score.
