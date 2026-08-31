# ADR 0019: Add a decision-level Learning MVP without pretending broker P&L

- Status: Proposed
- Date: 2026-08-31

## Context

Chapter 7 can produce a point-in-time Execution Plan for an already-approved `ALLOCATE` or
`REPLACE` decision. It deliberately does not connect to a broker and therefore does not prove that
an order was submitted or filled.

Chapter 8 must close the minimum product loop by preserving what AIE believed at T0 and comparing
that record with later outcomes. The central risk is false precision: using later market prices to
claim actual account P&L, calibrated alpha, or strategy skill when the system has no fill ledger,
no total-return provider contract, and only a small decision sample.

The minimum useful question is narrower:

> what happened after an executable AIE decision, relative to its declared benchmark, thesis
> conditions, and any explicit Underwriting scenario range, without changing the original decision
> or pretending that observed market returns are realized brokerage returns?

## Complexity Budget

| Gate | Chapter 8 evidence |
| --- | --- |
| Decision value | Produces auditable feedback on decision quality and falsification without changing capital automatically. |
| Validatability | Deterministic replay can verify T0/T1 anchors, T2 temporal boundaries, return arithmetic, drawdown, benchmark comparison, and scenario bands. |
| Architectural necessity | Learning has a distinct ex-post lifecycle and must not be owned by Underwriting, Portfolio Decision, or Execution. |
| Data sufficiency | Requires explicit later market observations and thesis-condition observations with provenance; no factor model or broker feed is required. |
| Explainability | Every evaluation exposes source decision, execution plan, benchmark, start/end observations, drawdown, thesis outcome, scenario band, missing data, and limitations. |
| Maintenance cost | One bounded context, one application use case, tests, and thin projection/docs. No model training, optimizer, broker adapter, or factor database. |
| Timing | Learning is the final mandatory stage of the accepted minimum-complete roadmap. |

Classification: Learning is `CORE NOW`. Aggregate performance statistics, factor attribution,
automatic policy updates, and model retraining remain deferred.

## Decision

### Learning is a separate downstream bounded context

The Learning domain must not import Portfolio, Underwriting, Execution, or Causal Alpha. The
application layer may verify those upstream records and translate only immutable references and
T0 anchors into Learning.

Learning never mutates a prior Opportunity State, Portfolio Decision, Execution Plan, owner policy,
or portfolio state. A Learning output is evidence for later human/model review, not an automatic
capital instruction.

### Evaluate only executable Chapter 7 plans in the MVP

The first Learning slice opens a case only from an Execution Plan whose action is `NOW` or
`STAGED`. `WAIT` and `INVALIDATED` do not prove that an active capital decision reached an
implementable state and are not scored as investment outcomes in this MVP.

This does not imply a broker fill. The Learning case records explicitly that implementation
evidence is plan-only until a separately approved fill lifecycle exists.

### Preserve three temporal boundaries

Learning retains:

- T0: original capital-decision boundary;
- T1: Execution Plan boundary;
- T2: later Learning evaluation boundary.

The required ordering is:

```text
T2 >= T1 >= T0
```

All three boundaries must use the same `KnowledgeMode`. Later observations must satisfy the shared
Temporal kernel at T2. Observations from the future, not yet available, or not yet recorded in a
live replay are rejected.

### Distinguish observed decision return from realized account P&L

The MVP records the exact T0 decision reference price for the selected target and benchmark. It
computes an **observed price return** from explicit later price observations.

This is not labelled realized account P&L because Chapter 7 contains no fill price, fill timestamp,
quantity lifecycle, dividend ledger, fees after T1, or broker statement. The evaluation therefore
carries an explicit `account_pnl_status = not_measured_no_fill_data`.

Price-only return is an intentional first baseline. Total-return and corporate-action-adjusted
provider contracts may graduate later only with explicit provenance and validation. The MVP must
state this limitation rather than silently treating price return as total shareholder return.

### Keep benchmark comparison same-currency and transparent

The selected target and declared Portfolio benchmark must have the same native currency in this
MVP. Otherwise Learning refuses to compute excess return because doing so would embed an undeclared
FX assumption.

The minimum arithmetic is:

```text
target_return = end_target_price / T0_target_price - 1
benchmark_return = end_benchmark_price / T0_benchmark_price - 1
excess_return = target_return - benchmark_return
```

For `REPLACE`, Learning also retains the T0 source-instrument price and computes the source
counterfactual price return. The replacement comparison is:

```text
replacement_excess_vs_source = target_return - source_return
```

No factor-adjusted alpha is claimed.

### Compute maximum drawdown from the explicit observed path

Maximum drawdown is calculated from the T0 target price followed by the ordered target price
observations admitted by T2. Missing intermediate observations do not get forward-filled.

The metric is a path statistic over the supplied observations, not proof that the account actually
experienced that drawdown.

### Re-evaluate exact upstream change conditions

The Learning input may evaluate only the exact `change_conditions` carried by the approved source
instruction.

- any triggered condition -> thesis outcome `invalidated`;
- any missing or unknown condition -> thesis outcome `unresolved`;
- all conditions explicitly not triggered -> thesis outcome `intact`.

Learning does not invent new retrospective invalidation rules after seeing the outcome.

### Record scenario realization without inventing calibration probabilities

When the selected target is the prospective candidate and its verified Underwriting record contains
the accepted bear/base/bull return range, Learning preserves that exact T0 range and common horizon.

Before the horizon, the scenario result is `pre_horizon`. At or after the horizon, observed target
price return is classified only as:

- below bear;
- bear to base;
- base to bull;
- above bull.

This is a calibration observation, not a probability estimate and not proof that the scenario
method is calibrated. When the selected target has no standalone Underwriting scenario range, the
scenario result is `not_available`.

### Keep aggregate performance statistics deferred

A single decision evaluation must not emit CAGR, volatility, Sharpe, Sortino, Information Ratio,
win rate, hit rate, or factor alpha as evidence of skill. Those statistics require a documented
minimum sample/horizon policy and, where relevant, suitable return histories.

Chapter 8 MVP stores decision-level records so those aggregate methods can later be validated on a
prospective sample.

### No automatic feedback loop

Learning does not automatically:

- increase or reduce position size;
- change owner constraints;
- change Underwriting gates;
- change pairwise decision logic;
- alter Execution thresholds;
- retrain a model;
- promote a deferred capability.

Any future feedback rule that changes active capital decisions requires a separate accepted ADR,
prospective validation, and rollback plan.

## Consequences

### Positive

- AIE gains an auditable ex-post learning record without contaminating T0 decisions with hindsight.
- Decision quality, benchmark-relative outcome, drawdown, thesis falsification, and scenario
  realization remain inspectable components rather than one magic score.
- Replacement decisions can be compared against the explicit source counterfactual.
- The system cannot mistake a planned trade for a broker-confirmed fill.
- The data needed for later calibration accumulates prospectively from the first canonical case.

### Negative

- Price return omits dividends and may not represent total shareholder return.
- No account P&L can be claimed until a fill lifecycle is admitted.
- `WAIT`, `INVALIDATED`, `NO_ALLOCATION`, and `HOLD` false-positive/false-negative attribution are
  not evaluated in the first slice.
- Factor-adjusted alpha and aggregate risk-adjusted statistics remain unavailable.
- Learning cannot automatically improve the model yet; it first creates trustworthy evaluation
  data.

## Rejected alternatives

### Treat the Chapter 7 execution quote as a fill

Rejected because a quote and an Execution Plan are not evidence that a trade occurred.

### Call observed price return realized portfolio return

Rejected because that would ignore fill timing, quantity, dividends, corporate actions, fees, and
broker state.

### Add Sharpe/Sortino immediately

Rejected because one or a few decision cases do not justify risk-adjusted performance claims.

### Let Learning update policy automatically

Rejected because a feedback mechanism with capital authority requires prospective calibration and
separate governance.

### Add factor-adjusted alpha now

Rejected because factor definitions, point-in-time histories, and adequate decision samples are not
yet available. The roadmap already classifies this capability as deferred.

## Acceptance criteria

ADR 0019 may move to `Accepted` only when:

1. Learning is a downstream bounded context with no domain imports from upstream investment contexts;
2. cases open only from canonically replayed `NOW` or `STAGED` Execution Plans;
3. T0, T1, and T2 boundaries remain ordered and use one `KnowledgeMode`;
4. T2 observations pass the Temporal shared kernel and future data is rejected;
5. the target and benchmark use one currency or Learning refuses benchmark excess-return arithmetic;
6. observed price return is explicitly distinguished from realized account P&L;
7. target return, benchmark return, excess return, and max drawdown reproduce deterministically;
8. replacement evaluations preserve and compare the explicit source counterfactual;
9. thesis evaluation uses only exact upstream change conditions and keeps unknown states unresolved;
10. scenario realization is categorical and never converted into a probability or score;
11. no automatic policy, sizing, execution, or model update is introduced;
12. architecture, unit, integration, replay, tamper, formatting, typing, package, Python 3.12/3.13,
    and container CI checks pass on the exact PR head;
13. the owner explicitly accepts ADR 0019 and authorizes the Chapter 8 merge.
