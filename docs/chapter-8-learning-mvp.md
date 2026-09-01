# Chapter 8 — Decision-level Learning MVP

## Purpose

Chapter 8 closes the minimum AIE decision loop by comparing an immutable T0/T1 decision record with
later T2 outcomes. It is designed to answer:

> what happened after an executable AIE decision, relative to the declared benchmark, the original
> thesis conditions, and any explicit Underwriting scenario range?

It does **not** claim that a planned trade was filled, that observed price return is brokerage P&L,
or that a small sample proves investment skill.

The contract is governed by proposed ADR 0019.

## Ownership

Learning is a downstream bounded context with a different lifecycle from Underwriting, Portfolio
Decision, and Execution.

Upstream owners remain unchanged:

- Underwriting owns the standalone thesis and bear/base/bull scenario range;
- Portfolio Decision owns the selected alternative and capital amount;
- Execution owns `NOW`, `STAGED`, `WAIT`, and `INVALIDATED` operational planning;
- Learning owns only ex-post decision-level evaluation records.

The Learning domain imports none of those upstream contexts. The application layer verifies their
canonical records and copies only immutable references and T0/T1 anchors.

## Admitted sources

The MVP opens an active Learning case only from a canonically replayed Chapter 7 plan whose action
is:

- `NOW`; or
- `STAGED`.

`WAIT` and `INVALIDATED` are not treated as implemented investment outcomes. The first slice also
does not score Chapter 6 `NO_ALLOCATION` or `HOLD` false negatives.

A `NOW` or `STAGED` plan still does not prove a fill. Every Learning evaluation therefore reports:

```text
account_pnl_status = not_measured_no_fill_data
```

## Temporal model

Learning preserves three boundaries:

```text
T0 = capital decision
T1 = Execution Plan
T2 = Learning evaluation

T2 >= T1 >= T0
```

All boundaries use the same `KnowledgeMode`. Every later price or thesis observation must satisfy
the shared Temporal kernel at T2. Future, unavailable, or not-yet-recorded observations are
rejected.

Outcome observations from before T0 are rejected so the evaluation path cannot accidentally
include pre-decision information.

## Evaluation horizon and prospective use

For a selected candidate with verified Underwriting scenarios, the evaluation horizon is inherited
unchanged from that T0 scenario record. A caller cannot substitute a different horizon.

For a target without a standalone Underwriting horizon, the caller supplies one explicit future
`evaluation_horizon_date` when the Learning case is opened. The horizon is content-addressed with
the rest of the case, so later evaluations cannot silently rewrite it.

That integrity guarantee is not the same as prospective-time proof. Until AIE has an accepted
production persistence contract that records case creation at or near T1, replay alone cannot prove
that a non-candidate case was not newly constructed after outcomes were visible with a favorable
horizon. Prospective operation must therefore persist the case before outcome-dependent analysis.
Aggregate or horizon-dependent skill claims remain disabled until that provenance exists.

The MVP also does not invent a trading-calendar or nearest-horizon price-selection rule. It uses
explicit admitted observations and treats scenario maturity categorically at or after the declared
calendar horizon. A richer observation-selection policy requires measured need and separate
validation.

## Decision return versus account P&L

The MVP uses the exact T0 decision reference price and later explicit market-price observations.
Its return basis is:

```text
price_only_from_decision_reference
```

The minimum arithmetic is:

```text
target_return = end_target_price / T0_target_price - 1
benchmark_return = end_benchmark_price / T0_benchmark_price - 1
excess_return = target_return - benchmark_return
```

Target and benchmark must use one native currency. Without an admitted point-in-time FX contract,
Learning refuses cross-currency benchmark excess-return arithmetic.

Price-only return is deliberately not labelled total shareholder return. Dividends, corporate
actions, broker fills, taxes after T1, and realized transaction prices require later provider/fill
contracts.

## Maximum drawdown

Maximum drawdown is calculated over the explicit target-price path supplied to Learning, beginning
with the T0 decision reference price. No missing observation is forward-filled.

The resulting drawdown describes the observed decision-price path. It is not proof that an account
experienced the same path because Chapter 7 has no fill ledger.

## Replacement learning

For a verified `REPLACE` decision, the case retains:

- target T0 price;
- source-position T0 price;
- benchmark T0 price.

At T2 it additionally reports:

```text
source_return = end_source_price / T0_source_price - 1
replacement_excess_vs_source = target_return - source_return
```

This makes the actual replacement question inspectable: did the chosen target outperform the
explicit source counterfactual over the observed period? It is still price-only and not a claim of
realized tax-adjusted account benefit.

## Thesis learning

Learning can evaluate only the exact upstream `change_conditions` frozen into the executable source.

- any `triggered` -> `invalidated`;
- any missing or `unknown` -> `unresolved`;
- all `not_triggered` -> `intact`.

Extra hindsight-only conditions are rejected. Learning cannot rewrite the decision after seeing
what the market did.

## Scenario realization

When the selected target is the candidate equity and verified Underwriting has a common
bear/base/bull reference price and horizon, Learning copies that T0 range unchanged.

Before the horizon the result is `pre_horizon`. At or after the horizon the observed target return
is classified as one of:

- `below_bear`;
- `bear_to_base`;
- `base_to_bull`;
- `above_bull`.

For targets without a standalone Underwriting scenario range, the result is `not_available`.

These are calibration observations only. They are not scenario probabilities, confidence scores,
or evidence that the forecasting method is calibrated.

## What is deliberately absent

The first Learning slice does not calculate or claim:

- realized broker/account P&L;
- total shareholder return;
- CAGR as a model-quality claim;
- volatility, Sharpe, Sortino, or Information Ratio;
- win rate or hit rate as evidence of skill;
- factor-adjusted alpha;
- automatic model retraining;
- automatic owner-policy changes;
- automatic sizing changes;
- automatic Execution-threshold changes.

Those methods require prospective samples and explicit validation policies. Factor-adjusted alpha
remains deferred under the roadmap.

## Replay and audit

A Learning case is content-addressed from its verified T0/T1 anchors. A Learning evaluation stores
its complete T2 input observations as well as the derived metrics and is itself content-addressed.

Canonical replay can therefore detect modification of:

- the source decision or Execution reference;
- T0 target, benchmark, or replacement-source price;
- evaluation horizon or scenario range;
- T2 price/thesis observations;
- return or drawdown arithmetic;
- thesis or scenario classification.

For non-candidate horizons, replay detects alteration after case construction but cannot by itself
attest the real-world creation time of the original case. That requires the future persistence
boundary described above.

## Delivery status

Chapter 7 is canonical in `main` under accepted ADR 0018 and merged PR #24. Chapter 8 is developed
on `agent/chapter-8-learning-mvp`; PR #25 now targets `main` directly and contains only the Chapter
8 delta plus its governance/documentation changes.

Before Chapter 8 can become canonical:

1. exact-head CI and red-team review must pass;
2. ADR 0019 must be explicitly accepted;
3. PR #25 requires explicit merge authorization.
