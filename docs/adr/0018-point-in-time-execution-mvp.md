# ADR 0018: Add a point-in-time Execution MVP without market timing

- Status: Accepted
- Date: 2026-08-31

## Context

Accepted ADR 0017 completes the Chapter 6 Portfolio Decision flow. AIE can now determine an
explicit new-capital allocation or replacement while preserving amount, target, friction, owner
policy, uncertainty, and canonical T0 lineage. The next question is narrower:

> given an already-approved capital decision, should it be implemented now, staged, temporarily
> held back, or invalidated by an upstream condition?

Execution must answer that question without reopening Underwriting, recomputing Portfolio Fit,
changing the strategic amount, searching for a better asset, or introducing an unvalidated market-
timing score. It also must not submit live brokerage orders in this slice.

## Complexity Budget

| Gate | Chapter 7 evidence |
| --- | --- |
| Decision value | Changes only the `WHEN/HOW TO IMPLEMENT` decision after capital allocation is already fixed. |
| Validatability | Deterministic tests cover source replay, temporal filtering, quote freshness, spread/liquidity gates, invalidation, conflict blocking, staging arithmetic, tampering, and architecture boundaries. |
| Architectural necessity | Execution has distinct language, lifecycle, and ownership from Portfolio Decision, so it is a separate bounded context under ADR 0006. |
| Data sufficiency | Uses explicit point-in-time bid/ask observations, liquidity state, owner execution policy, and upstream invalidation conditions. No regime model is required. |
| Explainability | Output exposes source decision, exact amount, quote state, spread, reasons, tranches, missing data, T0/T1 boundaries, and fingerprint. |
| Maintenance cost | One domain package, one application use case, tests, documentation, and a thin projection update. No broker, venue, provider, optimizer, or background service. |
| Timing | Chapter 7 is the next mandatory roadmap slice after Chapter 6 completion and is required before Learning can evaluate implemented decisions. |

Classification: the Execution bounded context is `CORE NOW`. Quote-age, maximum-spread, and
maximum-single-order constraints are explicit owner `SIMPLE POLICY`; they are not calibrated alpha
signals.

## Decision

### Execution consumes, never recreates, a capital decision

Execution accepts only a canonically replayed final Chapter 6 capital decision:

- a policy-constrained new-capital decision whose outcome is `ALLOCATE`; or
- a replacement decision whose outcome is `REPLACE`.

`NO_ALLOCATION` and `HOLD` are not executable instructions. Execution preserves the approved target
instrument and amount exactly. For replacement it also preserves the explicit source sale amount
and source instrument. It may split an approved amount into tranches, but the sum of tranches must
equal the approved amount exactly.

Execution does not alter standalone quality, valuation, Portfolio Fit, owner policy, replacement
friction, tax assumptions, or the selected strategic alternative.

### Separate the allocation boundary from the execution boundary

The upstream capital decision keeps its original knowledge boundary. An Execution Plan has a new
canonical knowledge boundary that may be later in time but must use the same `KnowledgeMode` and
must satisfy:

```text
execution.as_of >= capital_decision.as_of
```

Every market or invalidation observation used by Execution must be included by the execution
knowledge boundary under the shared Temporal kernel. Future or not-yet-recorded data is rejected;
it is never downgraded to a warning.

### Fail closed on unresolved execution-input conflicts

Execution input may retain explicit `conflicts` for audit, but a contradictory input cannot produce
an Execution Plan. Any unresolved conflict is a blocking validation failure before the categorical
execution policy runs. The operator must resolve the contradiction and submit a new immutable
input; Execution must never turn contradictory evidence into `NOW` or `STAGED`.

### Admit four execution outcomes only

The Chapter 7 MVP vocabulary is exactly:

- `NOW`: operational conditions pass and no staging constraint is active;
- `STAGED`: implementation is allowed but an explicit maximum-single-order notional requires the
  unchanged approved amount to be split into deterministic tranches;
- `WAIT`: the capital decision remains valid, but current operational evidence is insufficient or
  outside explicit execution limits;
- `INVALIDATED`: an upstream decision change condition is explicitly observed as triggered.

Priority is conservative after integrity and temporal validation:

```text
INVALIDATED > WAIT > STAGED > NOW
```

No scalar timing score, momentum score, regime score, or expected-return threshold is introduced.

### Keep execution policy explicit and owner-defined

An immutable, content-addressed Execution Policy requires explicit values for:

- maximum quote age in seconds;
- maximum acceptable bid/ask spread in basis points;
- optional maximum notional per order/tranche.

The policy contains no default market-timing thresholds. A maximum order notional is an
implementation constraint only: it may split the approved total but cannot reduce or increase it.

### Use inspectable current market observations

For every instrument that would trade, Execution uses one explicit observation containing:

- bid and ask in native execution currency;
- observation, availability, and recorded timestamps;
- liquidity state: `adequate`, `constrained`, or `unknown`;
- source reference and content fingerprint;
- missing-data disclosure where required.

Spread is transparent arithmetic over bid and ask. A missing or stale quote, spread above the
owner maximum, unknown liquidity, or constrained liquidity returns `WAIT` in the MVP. Constrained
liquidity does not automatically invent a tranche schedule; a richer liquidity model requires a
measured failure and a later ADR.

### Reuse upstream invalidation conditions exactly

Execution may not invent thesis conditions. It receives observations only for the exact
`change_conditions` carried by the approved Chapter 6 source decision.

- any `triggered` condition -> `INVALIDATED`;
- any `unknown` or missing condition assessment -> `WAIT`;
- all conditions explicitly `not_triggered` -> continue to market-condition checks.

Extra unrecognized invalidation conditions are rejected.

The MVP deliberately does not assign one universal age threshold to every invalidation
observation. Different fundamental, regulatory, catalyst, and market conditions can have different
review cadences, and inventing one global TTL would create a new unsupported execution heuristic.
Observation time remains explicit in the immutable input. A condition-specific expiry or freshness
policy may be admitted later only after prospective use demonstrates a measured failure of this
simpler contract.

### Stage only through an explicit maximum order notional

When all other gates pass and `max_single_order_notional` is present, any required trade leg whose
notional exceeds that limit is split deterministically into sequential chunks no larger than the
limit. The final chunk contains the exact remainder.

For a new-capital allocation there is one BUY leg. For replacement there is one SELL leg for the
approved gross sale amount followed by one BUY leg for the approved net redeployable amount. The
MVP records sequence and tranches but does not choose broker, venue, order type, limit price, or
submission time.

### Keep broker execution out of scope

Chapter 7 creates an immutable Execution Plan only. It does not:

- connect to a brokerage account;
- submit, cancel, or amend orders;
- select a venue or order type;
- claim fill probability;
- estimate dynamic slippage;
- run a Market State or regime engine;
- change strategic allocation because of price action.

Live order submission requires a separate accepted ADR and explicit owner authorization.

## Consequences

### Positive

- AIE can distinguish strategic allocation from operational implementation.
- `WAIT` is a valid conservative state rather than an implicit market-timing forecast.
- Upstream thesis invalidation remains canonical instead of being re-authored in Execution.
- Contradictory execution input cannot silently become an executable plan.
- Staging preserves total approved capital exactly and is auditable.
- Point-in-time execution decisions can be replayed later by Learning.

### Negative

- Liquidity `constrained` returns `WAIT` rather than using a sophisticated participation model.
- The MVP has no broker or fill lifecycle.
- Owner execution thresholds are policy inputs, not empirically calibrated defaults.
- Replacement sequencing is deterministic and simple rather than optimized for market impact.
- Invalidation observation freshness has no universal TTL; timestamps remain visible until a
  measured failure justifies a condition-specific expiry policy.

## Rejected alternatives

### Add a Market State score before Execution

Rejected because Market State is explicitly deferred until a simple execution policy demonstrates
persistent timing failure prospectively.

### Let Execution change the approved amount

Rejected because Marginal Allocation owns total strategic capital. Execution may stage but not
resize it.

### Auto-stage constrained liquidity with an inferred schedule

Rejected because that would introduce an unvalidated liquidity heuristic. The MVP fails safely to
`WAIT`.

### Use one default invalidation expiry for every condition

Rejected because heterogeneous thesis conditions do not share one defensible universal review
cadence. Timestamp visibility is retained and a condition-specific policy requires measured need.

### Submit live broker orders

Rejected because Chapter 7 first needs a stable, replayable planning contract and explicit owner
approval before any external side effect is admitted.

## Acceptance criteria

ADR 0018 may move to `Accepted` only when:

1. policy-allocation and replacement sources are canonically replayed before Execution;
2. non-executable Chapter 6 outcomes are rejected;
3. execution never changes the approved target amount or replacement sale amount;
4. execution time cannot precede the source decision and shared `KnowledgeMode` is preserved;
5. every consumed observation passes the Temporal shared-kernel boundary;
6. unresolved execution-input conflicts block plan construction;
7. upstream invalidation conditions are matched exactly and triggered conditions produce
   `INVALIDATED`;
8. missing/unknown invalidation, missing/stale quote, excessive spread, and non-adequate liquidity
   fail safely to `WAIT`;
9. `STAGED` is driven only by explicit maximum-order notional and tranche sums reproduce the exact
   approved leg totals;
10. `NOW` requires all operational gates to pass without staging;
11. no market-timing score, order submission, venue selection, or strategic resizing is added;
12. architecture, unit, integration, replay, tamper, formatting, typing, package, Python 3.12/3.13,
    and container CI checks pass on the exact PR head;
13. the owner explicitly accepts ADR 0018 and authorizes the Chapter 7 merge.