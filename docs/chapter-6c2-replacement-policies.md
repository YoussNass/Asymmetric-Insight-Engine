# Chapter 6C2: Replacement and capital-flow policies

## Purpose

Chapter 6C2 closes the Portfolio MVP by adding the minimum policies required after the accepted
6C1 new-capital comparison:

- owner-defined risk/concentration gates;
- new-capital-first funding;
- `LEGACY_HOLD_ZERO_NEW_CAPITAL`;
- `RUNNER` state;
- explicit source-to-target `REPLACE` after visible switching friction.

It remains inside the existing Portfolio Decision bounded context. It does not add a replacement
engine, tax engine, portfolio optimizer, sizing engine, or Execution capability.

The design is governed by proposed
[`ADR 0017`](adr/0017-replacement-and-capital-flow-policies.md).

## Inputs and ownership

### Owner Portfolio Policy

`OwnerPortfolioPolicy` is immutable and content-addressed at the same `KnowledgeBoundary` as the
decision it constrains. It may contain:

- `max_capital_unit`;
- `MAX_COMPANY_WEIGHT`;
- `MAX_COMPANY_HHI_UPPER_BOUND`;
- `MAX_ECONOMIC_DRIVER_WEIGHT`;
- per-position lifecycle policy.

The values are maximum admissibility gates. They never become target weights or an objective
function.

### Position lifecycle

A position can be:

- `STANDARD`;
- `LEGACY_HOLD_ZERO_NEW_CAPITAL`;
- `RUNNER`.

Legacy means the position may remain held but cannot receive incremental capital.

Runner may retain explicit historical `recovered_proceeds`, but its capital basis is fixed to
`CURRENT_MARKET_VALUE`. Recovered cost is never subtracted from current value when deciding whether
the position should remain, receive capital, or be replaced.

## Policy-constrained new capital

The 6C2 application first canonically verifies the complete 6C1 package. It does not rebuild the
standalone thesis and does not alter the accepted 6C1 decision.

For each non-cash alternative, owner policy can produce explicit block reasons. Investment cash is
always retained as an eligible fallback.

After filtering, AIE reuses the existing six 6C1 pairwise comparisons. Among the remaining
alternatives, a non-cash allocation still requires complete dominance over every eligible
competitor, including cash.

```text
verified 6C1 comparison
        +
owner policy gates
        |
        v
eligible alternatives + cash
        |
        v
restricted pairwise dominance
        |
        +--> unique non-cash winner -> ALLOCATE exact original unit
        |
        +--> otherwise              -> NO_ALLOCATION -> cash
```

No amount is rounded down to make a policy pass. If USD 100 is evaluated and the owner maximum is
USD 50, the USD 100 alternative is blocked; AIE does not invent a USD 50 position.

## Explicit replacement

`ReplacementDecisionInput` describes exactly one proposal:

```text
source existing position
        -> explicit gross sale amount
        -> explicit target
        -> tax + fee + spread + liquidity
        -> after-friction qualitative conclusion
        -> policy gates
```

Targets admitted in the MVP are:

- prospective candidate equity with verified Opportunity State;
- another eligible held listed equity;
- the declared core ETF.

Source and target use the same currency. No FX conversion is performed.

## Switching-friction arithmetic

The only monetary arithmetic added by 6C2 is deterministic and inspectable:

```text
total_switching_friction = tax + fee + spread
net_redeployable_amount = gross_sale_amount - total_switching_friction
```

Each cost is independently `known`, `not_applicable`, or `unknown`.

An `unknown` cost has no amount and must name the missing data. Unknown tax, fee, or spread makes
the net amount unknown and returns `HOLD / FRICTION_UNKNOWN`.

Liquidity is separate:

- `ADEQUATE`;
- `CONSTRAINED`;
- `UNKNOWN`.

`UNKNOWN` returns `HOLD / LIQUIDITY_UNRESOLVED`. `CONSTRAINED` remains visible but does not become
a hidden threshold; the operator's explicit after-friction comparison must still prefer the target.

## New-capital-first

Before selling the source, AIE totals currently investable cash in the replacement currency.
Emergency reserve cash is excluded by Portfolio State.

If that cash can fund the `net_redeployable_amount`, the result is:

```text
HOLD / NEW_CAPITAL_FIRST
```

The source remains untouched and the target is routed back to the normal new-capital decision.
This prevents unnecessary switching costs without claiming tax optimality.

## Replacement outcome

`REPLACE` requires all gates to clear:

1. valid source and target;
2. common T0 boundary and currency;
3. complete tax/fee/spread estimates;
4. liquidity not unknown;
5. current investable cash insufficient for new-capital-first;
6. target wins the explicit source/target comparison before friction;
7. target remains preferred after friction;
8. owner constraints remain satisfied.

Otherwise the source is retained with a named `HOLD` basis:

- `NEW_CAPITAL_FIRST`;
- `POLICY_BLOCK`;
- `FRICTION_UNKNOWN`;
- `LIQUIDITY_UNRESOLVED`;
- `SOURCE_NOT_OUTCLASSED`.

This means `HOLD` can now arise from two distinct records:

- the 6C1 no-new-capital position review;
- a rejected 6C2 replacement proposal.

The Decision Card preserves the distinction through its source/gross/friction fields and input
fingerprint.

## Replacement concentration boundary

The accepted Exposure contract models current exposure and positive hypothetical additions. It
does not yet support a canonical sell/rebalance scenario.

6C2 therefore does not fake a sale inside `PortfolioExposure`. If owner ratio constraints apply to
a replacement, `ReplacementDecisionInput` must contain one after-replacement observation for every
active constraint, with explicit source reference and content fingerprint.

This boundary is intentionally conservative. A measured need can later justify a canonical
rebalance exposure scenario; 6C2 does not introduce it speculatively.

## Reference-case behavior

The deterministic test portfolio contains USD 200 of investable cash and a USD source position.
For a USD 500 replacement proposal with:

- tax = USD 10;
- fee = USD 1;
- spread = USD 2;

6C2 derives:

```text
total friction       = USD 13
net redeployable      = USD 487
existing investable cash = USD 200
```

If the core ETF wins before and after friction and no owner gate is breached, `REPLACE` is
admissible because USD 200 cannot fund USD 487 without selling the source.

For a USD 100 gross proposal with the same USD 13 friction, net redeployable capital is USD 87.
Because current USD investment cash is USD 200, AIE returns `HOLD / NEW_CAPITAL_FIRST` instead of
selling the position.

A Runner may report USD 900 of recovered historical proceeds in the fixture. The same USD 500
gross sale still produces USD 487 net redeployable capital. The USD 900 history never enters the
calculation.

## Decision Card

The read-only projection supports:

- `ALLOCATE`;
- `NO_ALLOCATION`;
- `HOLD`;
- `REPLACE`.

For replacement it may display:

- source position;
- gross sale amount;
- switching friction;
- net redeployable amount;
- target;
- decision rationale;
- risks/unknowns;
- confidence and calibration;
- change conditions;
- T0 and input fingerprint.

Execution is always `not_evaluated` in Chapter 6.

## Explicit non-goals

6C2 does **not** implement:

- automatic position sizing;
- portfolio-wide sell optimization;
- tax-lot selection;
- jurisdiction tax rules;
- implicit FX;
- covariance/risk-parity optimization;
- market timing;
- order type, venue, staging, or slippage strategy;
- live brokerage execution.

Those boundaries prevent the final Chapter 6 slice from silently absorbing Chapter 7 or deferred
portfolio research.

## Exit criteria

Chapter 6 is complete only after:

1. ADR 0017 is accepted;
2. policy and replacement records replay canonically at one T0 boundary;
3. unit, integration, tamper, architecture, type, format, package, Python 3.12/3.13, and container
   checks are green on the exact PR head;
4. the owner explicitly authorizes the 6C2 merge.

Until then, the implementation remains a review candidate rather than canonical `main` behavior.
