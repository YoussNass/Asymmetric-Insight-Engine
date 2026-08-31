# ADR 0017: Add replacement and capital-flow policy without an optimizer

- Status: Proposed
- Date: 2026-08-31

## Context

Accepted ADR 0016 makes one explicit new-capital unit compete across candidate equity, one eligible
incumbent, the core ETF, and investment cash. That solves the first allocation question but does
not answer two practical portfolio questions:

1. what if an otherwise attractive use of new capital violates an explicit owner constraint or a
   position is intentionally classified as no-new-capital;
2. what if the best use of capital requires selling an existing position and paying switching
   friction before the target can be funded.

Chapter 6C2 is the final Portfolio MVP slice before Execution. It must add these decisions without
turning AIE into a tax optimizer, a portfolio optimizer, a market-timing system, or an automatic
position-sizing model.

## Complexity Budget

| Gate | Chapter 6C2 evidence |
| --- | --- |
| Decision value | Makes owner constraints, Legacy/Runner state, new-capital-first funding, and explicit replacement operational in the marginal-capital flow. |
| Validatability | Deterministic tests cover policy replay, zero-new-capital state, discrete amount preservation, friction arithmetic, missing friction, new-capital-first, concentration gates, Runner accounting, tampering, and architecture boundaries. |
| Architectural necessity | All new concepts are contracts or policies inside the accepted Portfolio Decision bounded context; no new engine or service is introduced. |
| Data sufficiency | Uses accepted Portfolio State/Exposure/6C1 records plus explicit owner constraints and externally supplied T0 tax/fee/spread/liquidity observations. Tax-lot optimization is not claimed. |
| Explainability | Every block names the violated policy; replacement exposes gross sale amount, each friction component, net redeployable amount, available investable cash, qualitative comparison, and decision basis. |
| Maintenance cost | One policy module, one application module, read-only Decision Card extension, tests, and documentation. No provider, persistence, optimizer, order adapter, or new framework. |
| Timing | Replacement and capital-flow policy are required to complete the Portfolio MVP before Chapter 7 can stage an already-decided target allocation. |

Classification: owner constraints, new-capital-first, Legacy, Runner, and basic replacement are
`SIMPLE POLICY` inside Portfolio Decision. Complex tax optimization, automated sizing, covariance
optimization, and Execution remain deferred or later-stage capabilities.

## Decision

### Preserve accepted 6C1 records

Chapter 6C2 does not modify or reinterpret the canonical 6C1 `MarginalDecision` fingerprint.
Instead it consumes a canonically replayed 6C1 package and an immutable, content-addressed
`OwnerPortfolioPolicy`.

The policy may declare:

- an optional maximum explicit capital unit in one currency;
- maximum company weight;
- maximum company-HHI upper bound;
- maximum economic-driver weight;
- position lifecycle policy.

These are hard eligibility gates, not target weights and not ingredients of a weighted score.
When the supplied capital unit exceeds the owner maximum, the system rejects that use of capital;
it never silently reduces or optimizes the amount.

### Keep cash eligible after policy filtering

Investment cash can never be removed by owner policy. Non-cash alternatives that breach an
explicit policy are removed from the eligible set with inspectable reasons. The application then
reuses the already-complete 6C1 pairwise comparisons among the remaining alternatives.

A non-cash `ALLOCATE` result still requires complete pairwise dominance over every remaining
eligible alternative, including cash. If no such winner exists, the policy-constrained result is
`NO_ALLOCATION` and the exact capital unit remains investment cash.

This is policy-filtered competition, not rescoring.

### Define Legacy as holdable but zero-new-capital

`LEGACY_HOLD_ZERO_NEW_CAPITAL` is owner-declared state for an existing position that may remain in
the factual portfolio but cannot receive incremental capital. It does not imply sell, replace,
or thesis failure.

Restoring eligibility requires a new owner policy record with explicit change conditions; past
policy records remain immutable.

### Define Runner without house-money accounting

`RUNNER` records that some historical proceeds have been recovered, but recovered proceeds are
historical context only. They never reduce the economic opportunity cost of the remaining
position.

Every Runner decision uses current market value as the capital basis. A Runner can be configured
as eligible or zero-new-capital by explicit owner policy, but it cannot be treated as “free”
capital merely because cost has previously been recovered.

### Admit one explicit replacement proposal

Replacement is not a search optimizer. One record compares:

- one existing source position;
- one explicit target: candidate equity, another eligible listed-equity holding, or the core ETF;
- one caller-supplied gross sale amount in the source/target native currency.

The sale amount must be positive and cannot exceed the source position's current market value.
Chapter 6C2 performs no FX conversion and no automatic sizing.

Candidate replacement targets must reference and canonically replay the standalone Opportunity
State. Portfolio policy cannot rewrite Underwriting.

### Keep switching friction explicit

A replacement proposal must expose exactly three monetary friction categories:

- tax;
- fee;
- spread.

Each is `known`, `not_applicable`, or `unknown`. Unknown friction cannot contain a guessed amount
and must disclose missing data. Liquidity is separately `adequate`, `constrained`, or `unknown`.

When monetary friction is complete:

```text
total_switching_friction = tax + fee + spread
net_redeployable_amount = gross_sale_amount - total_switching_friction
```

Known switching friction must be lower than the gross sale amount. The arithmetic uses only the
explicit proposal. Runner recovered proceeds never enter either formula.

A constrained but known liquidity state remains visible and can be incorporated into the explicit
qualitative after-friction judgement. Unknown liquidity blocks replacement.

### Apply new-capital-first before selling a position

After policy eligibility and friction are known, AIE compares the net redeployable amount with
currently available investment cash in the same currency. Emergency reserve cash is excluded by
Portfolio State semantics.

If existing investable cash can fund the net target amount, the source is not sold. The result is
`HOLD` with decision basis `NEW_CAPITAL_FIRST`; the target must be evaluated through the ordinary
new-capital flow instead.

This policy avoids unnecessary switching friction without claiming tax optimality.

### Require the source to be outclassed before `REPLACE`

`REPLACE` requires all of the following:

1. source and target pass identity, temporal, currency, and owner-policy checks;
2. monetary switching friction is complete;
3. liquidity is not unknown;
4. existing investable cash is insufficient to fund the target under new-capital-first;
5. the target wins the explicit pre-friction source/target comparison;
6. the explicit qualitative after-friction conclusion still prefers the target;
7. owner concentration/risk gates are not breached.

Failure of any required gate returns `HOLD` with a named basis such as `POLICY_BLOCK`,
`FRICTION_UNKNOWN`, `LIQUIDITY_UNRESOLVED`, `NEW_CAPITAL_FIRST`, or
`SOURCE_NOT_OUTCLASSED`.

No numerical utility, expected-return threshold, or hidden switching score is introduced.

### Keep replacement exposure constraints explicit

Chapter 6B supports current exposure and positive hypothetical additions; it does not yet model a
canonical hypothetical sale. Chapter 6C2 therefore does not mutate Exposure to fake a sale.

When owner ratio constraints are active for a replacement, the caller must provide an explicit
T0 after-replacement observation for every configured ratio constraint, including source reference
and fingerprint. Missing or extra observations are rejected. This is a temporary explicit input
boundary, not a new exposure engine.

A later measured need may justify a canonical sell/rebalance exposure scenario; it is not admitted
pre-emptively.

### Extend the Decision Card, not Execution

The read-only Decision Card adds `REPLACE` plus replacement fields for source position, gross sale
amount, switching friction, and net redeployable amount. `HOLD` can also represent a rejected
replacement proposal with its visible reason.

Execution remains fixed to `not_evaluated`. Chapter 6C2 does not select timing, venue, order type,
staging, slippage strategy, or trade sequence.

## Consequences

### Positive

- Chapter 6 can distinguish “attractive but policy-ineligible” from “inferior.”
- Legacy and Runner become explicit, auditable state rather than behavioral exceptions.
- Replacement decisions include the economic cost of switching and can prefer doing nothing.
- New investable cash is used before forcing a taxable/costly sale when it can fund the same
  target amount.
- Accepted 6C1 records remain immutable and replayable.
- No score, optimizer, automatic sizing, or Chapter 7 responsibility leaks into Portfolio Decision.

### Negative

- Replacement compares one explicit source/target proposal at a time; it does not search the
  entire portfolio for the globally optimal sale.
- Tax is an explicit T0 monetary estimate, not tax-lot optimization.
- After-replacement concentration observations are supplied rather than derived from a canonical
  sell scenario.
- Qualitative before/after-friction preference remains uncalibrated.
- Multi-currency replacement requires separate explicit proposals; no implicit FX is performed.

## Rejected alternatives

### Rewrite 6C1 to embed every owner policy

Rejected because accepted 6C1 fingerprints and semantics should remain stable. 6C2 is an additive
policy layer over canonical replay.

### Rank all holdings and automatically choose what to sell

Rejected because this would introduce an unvalidated portfolio optimizer and materially larger
search/model surface.

### Calculate exact tax from aggregate cost basis

Rejected because aggregate cost basis is insufficient for robust lot-level tax optimization and
jurisdiction-specific rules are outside the active data boundary.

### Treat Runner proceeds as free capital

Rejected because recovered historical cost does not remove the current opportunity cost of the
remaining market value.

### Resize the proposal until a constraint passes

Rejected because that would be an automatic sizing algorithm. The caller supplies discrete
amounts; policy returns eligible or blocked.

### Add timing or order staging to replacement

Rejected because target allocation must be decided before Execution. Chapter 7 owns timing and
staging.

## Acceptance criteria

ADR 0017 may move to `Accepted` only when:

1. the 6C1 package and owner policy are canonically replayed before policy-constrained allocation;
2. investment cash remains an eligible fallback and no blocked alternative can receive capital;
3. owner maximum capital and ratio constraints operate only as gates and never resize the amount;
4. Legacy enforces zero new capital without implying a sale;
5. Runner uses current market value as opportunity cost and recovered proceeds never enter
   replacement arithmetic;
6. replacement preserves State/Exposure/Opportunity T0 boundaries and uses no implicit FX;
7. tax, fee, spread, and liquidity are explicit, with unknowns failing safely;
8. new-capital-first prevents a sale when current investable cash can fund the net target amount;
9. `REPLACE` requires target preference both before and after friction plus all policy gates;
10. Decision Card remains read-only and Execution is `not_evaluated`;
11. architecture, unit, integration, replay, tamper, formatting, typing, package, Python 3.12/3.13,
    and container CI checks pass on the exact PR head;
12. the owner explicitly accepts ADR 0017 and authorizes the Chapter 6C2 merge.
