# Chapter 7 — Point-in-time Execution MVP

## Purpose

Chapter 7 implements an already-approved capital decision without recreating investment analysis.
It answers only whether the approved instruction should be implemented `NOW`, `STAGED`, `WAIT`, or
`INVALIDATED` at an explicit execution knowledge boundary.

The contract is governed by proposed ADR 0018.

## Ownership

Execution is a separate bounded context because its language, inputs, lifecycle, and failure modes
are distinct from Portfolio Decision. It consumes immutable upstream decision references and owns
only operational staging.

Portfolio Decision continues to own:

- target alternative/instrument;
- strategic amount;
- replacement source and gross sale amount;
- tax/friction assumptions used to approve replacement;
- investment rationale, uncertainty, and change conditions.

Execution owns:

- current quote and liquidity checks;
- point-in-time operational validity;
- `NOW`, `STAGED`, `WAIT`, `INVALIDATED`;
- deterministic tranche splitting under explicit owner policy;
- immutable execution-plan identity and audit lineage.

## Inputs

### Approved source

The application layer must canonically replay either:

1. a policy-constrained Chapter 6 new-capital decision with outcome `ALLOCATE`; or
2. a Chapter 6 replacement decision with outcome `REPLACE`.

`NO_ALLOCATION` and `HOLD` cannot become Execution Plans.

### Execution policy

The owner supplies explicit policy values at the execution boundary:

- maximum quote age in seconds;
- maximum bid/ask spread in basis points;
- optional maximum notional per order.

There are no hidden or calibrated-default thresholds.

### Market observations

One observation is required for every instrument that would trade. Each observation preserves bid,
ask, timestamps, liquidity state, source reference, source fingerprint, and missing data.

### Invalidation observations

Execution evaluates only exact upstream `change_conditions`. Each condition is `triggered`,
`not_triggered`, or `unknown` and carries point-in-time source lineage.

The MVP does not impose one arbitrary time-to-live on every invalidation condition. Fundamental,
regulatory, catalyst, and market conditions can have different valid review cadences. Their
observation time remains explicit and auditable; a condition-specific expiry/freshness policy may
be admitted later only if prospective use demonstrates that this simpler boundary is unsafe or
insufficient.

### Conflicts

`ExecutionPlanInput.conflicts` is not informational decoration. Any declared unresolved conflict is
a blocking input-integrity condition: the application refuses to construct `NOW`, `STAGED`,
`WAIT`, or `INVALIDATED` until the contradiction is resolved into a new immutable input. This
prevents contradictory evidence from silently reaching an executable plan.

## Temporal semantics

The allocation/replacement decision keeps its original T0 boundary. Execution receives its own T1
boundary, where:

```text
T1 >= T0
knowledge_mode(T1) == knowledge_mode(T0)
```

Every quote and invalidation observation must be included by T1 according to the Temporal shared
kernel. Future or not-yet-recorded records are rejected.

## Decision order

After input integrity and temporal validation pass, Execution applies a conservative priority
order:

```text
1. upstream invalidation triggered -> INVALIDATED
2. missing/unknown invalidation assessment -> WAIT
3. missing/stale quote -> WAIT
4. spread above explicit owner maximum -> WAIT
5. liquidity unknown or constrained -> WAIT
6. explicit max-order notional requires splitting -> STAGED
7. otherwise -> NOW
```

This is a categorical policy, not a market-timing score.

## Staging

For `STAGED`, every trade leg is split into deterministic chunks no larger than the explicit
`max_single_order_notional`. The final chunk carries the exact remainder. Tranche sums must equal
the upstream approved leg amount exactly.

New-capital allocation emits one BUY leg. Replacement emits one SELL source leg followed by one
BUY target leg. The plan does not select venue, order type, limit price, broker, or actual submit
time.

## Fail-safe behavior

- unknown is never converted to a favorable assumption;
- unresolved input conflicts block plan construction;
- invalidation has priority over implementation convenience after input integrity passes;
- `WAIT` carries no executable legs;
- `INVALIDATED` carries no executable legs;
- source identifiers/fingerprints are replayed rather than trusted;
- Execution cannot change capital amount, source sale amount, target, or thesis.

## Out of scope

- live brokerage submission;
- fills and partial-fill lifecycle;
- venue routing;
- limit-price selection;
- participation-rate algorithms;
- dynamic slippage estimation;
- market-regime or technical timing score;
- strategic allocation changes;
- Market State engine;
- one universal invalidation-observation expiry rule without measured need.

## Validation target

The vertical slice must demonstrate:

```text
verified Chapter 6 decision
-> approved execution source
-> explicit T1 policy + observations
-> point-in-time validation
-> NOW/STAGED/WAIT/INVALIDATED
-> immutable Execution Plan + fingerprint
```

Tests must cover both new-capital allocation and replacement, exact tranche preservation,
conservative unknown handling, future-data rejection, blocking conflicts, source tampering, and
architectural separation from Underwriting/Portfolio logic.
