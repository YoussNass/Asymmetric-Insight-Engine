# AIE delivery roadmap

## Status and authority

This document is the canonical delivery sequence under accepted ADR 0012. It does not declare a
capability implemented; the code, accepted ADRs, tests, and merged pull requests remain the
implementation record.

At the time of this roadmap:

- Chapters 2 through 7 are complete in `main`;
- factual Portfolio State, Portfolio Exposure, Portfolio Fit, Marginal Allocation, owner policy,
  replacement, capital-flow policy, and point-in-time Execution are canonical;
- Chapter 8 is the active implementation candidate under proposed ADR 0019 and PR #25, now
  retargeted directly to `main` after the Chapter 7 merge;
- Market State remains unimplemented and deferred in the canonical engine;
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
| Learn | Compare the immutable T0/T1 record with later point-in-time decision outcomes without hindsight |

## Mandatory sequencing gate

The prerequisites for Chapter 6 were satisfied on 2026-08-27:

1. Chapter 5 was reviewed, corrected, accepted, and merged;
2. ADR 0012 and ADR 0013 were explicitly accepted;
3. the minimal ETF-scope Constitution amendment was approved;
4. the owner authorized the compressed roadmap and Chapter 6A as the next slice.

Chapter 6 was completed on 2026-08-31 after ADR 0014 through ADR 0017 were accepted and their
implementations merged. Chapter 7 then passed its technical and governance gates under accepted ADR
0018 and PR #24 was merged into `main` on 2026-09-01. Chapter 8 is therefore the active
minimum-complete slice and PR #25 now targets `main` directly.

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
[`chapter-6a-portfolio-state.md`](chapter-6a-portfolio-state.md). Chapter 6B consumes this state by
immutable identifier and verified fingerprint rather than redefining factual holdings or cash.

### Chapter 6B — Minimal Portfolio Exposure

**Purpose:** expose hidden direct and indirect economic concentration descriptively.

**Status:** complete; ADR 0015 accepted and implementation merged with exact-head local and remote
verification.

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

The contract and deterministic reference case are documented in
[`chapter-6b-portfolio-exposure.md`](chapter-6b-portfolio-exposure.md). Chapter 6C1 consumes the
verified current and supplied-hypothetical Exposure records without mutating Portfolio State.

### Chapter 6C — Marginal Portfolio Decision

Portfolio Fit is an immutable interaction view inside this chapter, not a separate score engine.
Marginal Allocation owns the decision.

#### Slice 6C1 — New capital and competing alternatives

**Status:** complete; ADR 0016 accepted and implementation merged after exact-head verification and
explicit owner authorization.

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

The candidate, one eligible existing holding, the core ETF, and investment cash must use the same
explicit amount and native currency. All six unordered pairs retain standalone case,
permanent-loss class, portfolio effect, and uncertainty. A non-cash alternative receives
`ALLOCATE` only if it defeats all three competitors. Cash dominance, indeterminacy, or a cycle
produces `NO_ALLOCATION`; the caller-supplied amount is never automatically resized.

Every derived Exposure, Fit, and Marginal Allocation state declares `as_of`, knowledge mode,
method version, input fingerprint, missing inputs, conflicts, and assumptions in accordance with
ADR 0006.

The accepted contract and reference case are documented in
[`chapter-6c1-marginal-decision.md`](chapter-6c1-marginal-decision.md). The future API/frontend
boundary is fixed separately in
[`operator-workspace-contract.md`](operator-workspace-contract.md); neither a server nor a
functional frontend enters Chapter 6.

#### Slice 6C2 — Replacement and capital-flow policies

**Status:** complete; ADR 0017 accepted and implementation merged after exact-head verification and
explicit owner authorization.

The accepted slice adds:

- `REPLACE` comparison as one explicit source-to-target proposal rather than a sell optimizer;
- basic tax, spread, fee, liquidity, and switching friction;
- new-capital/PAC-first funding policy;
- `LEGACY_HOLD_ZERO_NEW_CAPITAL`;
- `RUNNER` state without treating recovered cost as free capital;
- owner-defined risk-budget and concentration constraints as hard gates;
- policy-constrained replay of accepted 6C1 decisions without rewriting their fingerprints;
- a Decision Card v2 projection that adds `REPLACE` while keeping Execution `not_evaluated`.

The owner supplies discrete capital and sale amounts. Constraint violations block the proposal;
they never trigger automatic resizing. Unknown friction or liquidity fails safely to `HOLD`.
Runner recovered proceeds remain historical context and never reduce the current market-value
opportunity cost of the retained position.

The accepted contract is documented in
[`chapter-6c2-replacement-policies.md`](chapter-6c2-replacement-policies.md) and
[`ADR 0017`](adr/0017-replacement-and-capital-flow-policies.md).

Exit criterion: AIE can explain the best evaluated use of the next unit of capital, can return no
allocation, and can decide whether one explicit existing position should be replaced after visible
friction and owner policy. It compares discrete, explicit amounts; it does not derive an automatic
Kelly-like size.

Chapter 6 is complete.

### Chapter 7 — Execution MVP

**Purpose:** implement, but never recreate, an approved allocation decision.

**Status:** complete and canonical in `main`; ADR 0018 accepted and PR #24 merged after exact-head
verification and explicit owner authorization.

Minimum outputs:

- `NOW`;
- `STAGED`;
- `WAIT`;
- `INVALIDATED`.

Allocation owns the target capital amount. Execution owns operational validation and deterministic
tranche staging. Market observations, liquidity, spreads, and exact upstream invalidation
conditions may change implementation, not company quality, standalone value, target, or strategic
amount.

Chapter 7 deliberately uses no Market State or timing score. An owner-defined execution policy
supplies quote-age, maximum-spread, and optional maximum-order-notional limits. `STAGED` can only
split the already-approved amount; tranche sums must reproduce that amount exactly. Missing/stale
quotes, excessive spread, unresolved or constrained liquidity, and unknown invalidation evidence
fail safely to `WAIT`. A triggered upstream change condition produces `INVALIDATED`.

The implementation produces an immutable Execution Plan and read-only Execution Card. It does not
connect to a broker or submit orders.

The accepted contract is documented in [`chapter-7-execution-mvp.md`](chapter-7-execution-mvp.md)
and [`ADR 0018`](adr/0018-point-in-time-execution-mvp.md).

Out of scope initially:

- automated order submission;
- a market-timing or regime score;
- venue and order-type selection;
- inferred participation-rate or liquidity scheduling;
- all-in/all-out regime rules;
- automatic changes to the strategic allocation.

Exit criterion: one canonically replayed `ALLOCATE` or `REPLACE` decision can produce a point-in-
time, content-addressed `NOW`, `STAGED`, `WAIT`, or `INVALIDATED` Execution Plan without changing
any upstream capital decision.

### Chapter 8 — Decision-level Learning MVP

**Purpose:** create trustworthy ex-post evidence about an AIE decision before claiming that the
system has learned an investment edge.

**Status:** active implementation candidate under proposed ADR 0019 and PR #25, targeting `main`.
The pre-documentation implementation head passed Python 3.12/3.13, mypy, pytest, package, doctor,
and container checks with 344 tests and 90.23% repository coverage. Final exact-head verification
is still required after governance/documentation alignment, followed by explicit ADR acceptance and
merge authorization.

The first slice opens Learning only from canonically replayed Chapter 7 `NOW` or `STAGED` plans and
preserves three ordered boundaries:

```text
T0 = capital decision
T1 = Execution Plan
T2 = Learning evaluation
T2 >= T1 >= T0
```

Because Chapter 7 has no broker-fill lifecycle, Learning explicitly distinguishes decision-level
observed price return from realized account P&L. It records
`account_pnl_status = not_measured_no_fill_data` and does not call a quote or plan a fill.

Minimum decision-level outputs:

- target price return from the exact T0 reference price;
- same-currency benchmark price return;
- transparent target-minus-benchmark excess return;
- maximum drawdown over the explicitly supplied target-price path, without forward filling;
- for `REPLACE`, source-position price return and target-minus-source counterfactual;
- thesis outcome `intact`, `invalidated`, or `unresolved` using only exact upstream change
  conditions;
- categorical scenario realization against the preserved T0 bear/base/bull range when such a
  range belongs to the selected candidate;
- T0/T1/T2 references, source fingerprints, assumptions, conflicts, and missing data.

The first slice deliberately does **not** claim realized brokerage P&L, total shareholder return,
Sharpe, Sortino, Information Ratio, factor alpha, win rate, or model skill. It also has no automatic
feedback authority: a Learning result cannot resize capital, rewrite owner policy, change
Underwriting gates, alter Execution thresholds, retrain a model, or promote a deferred capability.

The proposed contract is documented in [`chapter-8-learning-mvp.md`](chapter-8-learning-mvp.md)
and [`ADR 0019`](adr/0019-decision-level-learning-mvp.md).

Exit criterion: an executable point-in-time decision can be replayed into a content-addressed T2
Learning record that measures transparent decision-level outcomes without hindsight, implicit FX,
fake fill assumptions, aggregate skill claims, or automatic upstream feedback.

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
| Aggregate risk-adjusted Learning metrics | `DEFER` | Prospective decision sample and documented minimum-sample policy | Decision-level outcomes are insufficient for model-skill evaluation | Learning |
| Automatic Learning feedback | `REJECT` as V1 default | Prospective calibration, governance, rollback, and causally defensible update rules | Manual review of accumulated Learning records shows a reproducible benefit from a bounded update rule | Learning/application policy |
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

Chapter 6 Decision Cards remain immutable and show Execution as `not_evaluated`. Chapter 7 adds a
separate read-only Execution Card over a verified Execution Plan rather than mutating the accepted
Chapter 6 projection. Chapter 8 Learning records remain a separate downstream audit/evaluation
surface; none of these projections may hide uncertainty behind a synthetic score.
