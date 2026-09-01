# Minimum operator workspace contract

## Purpose

This document fixes the thinnest usable product path around the accepted domain architecture. It
is a contract for future API and frontend work, not an implemented server or UI.

The operator workspace reviews inputs, invokes application use cases, and renders immutable
outputs. It contains no financial formulas, ranking, sizing, temporal filtering, eligibility,
replacement, or execution logic of its own.

## Initial workflow

| Workspace view | Reads | Invokes | May edit before invocation |
| --- | --- | --- | --- |
| Research case | Evidence and claims | Evidence/Causal use cases | Source selection, claim typing, invalidations |
| Causal chain | Causal Analysis draft/state | Causal builder | Nodes, mechanisms, claim support |
| Underwriting | Opportunity draft/state | Underwriting builder | Facts, explicit adjustments, scenarios, risks |
| Portfolio State | Accounts, positions, prices, cash roles, ETF policy | Portfolio State builder | Imported/manual factual records before snapshot |
| Exposure | Current and supplied hypothetical inputs | Exposure builder | Point-in-time ETF snapshots and classifications |
| Marginal Decision | Four alternatives, loss classes, six pairwise comparisons | Marginal Decision builder | Capital unit and explicit qualitative judgements |
| Owner Policy | Verified Portfolio Decision state | Owner Policy builder / policy application | Explicit caps, ratio gates, Legacy/Runner lifecycle policy |
| Replacement | Verified State/Exposure/policy and optional Opportunity | Replacement builder | Source, target, sale amount, friction, liquidity, explicit constraint observations |
| Decision Card | Verified Chapter 6 decision package | Projection only | Nothing |
| Execution | Verified `ALLOCATE`/`REPLACE`, T1 policy and observations | Execution builder | Explicit quote-age/spread/order limits, T1 quote/liquidity and invalidation observations |
| Execution Card | Verified Execution Plan | Projection only | Nothing |

Learning remains disabled until Chapter 8 defines its contract. Chapter 7 defines the Execution
workspace boundary but does not implement a server, frontend, broker adapter, or order-submission
surface.

## Minimum application boundary

A future transport adapter may expose use-case-shaped operations such as:

```text
build_opportunity(draft) -> OpportunityState
build_portfolio_state(draft) -> PortfolioState
build_exposure(state_ref, input) -> PortfolioExposure
build_marginal_decision(verified refs, input) -> Fits + MarginalDecision
record_position_hold(verified refs, input) -> PositionReview
build_owner_portfolio_policy(input) -> OwnerPortfolioPolicy
apply_portfolio_policy(verified 6C1 package, policy) -> PolicyConstrainedMarginalDecision
build_replacement_decision(verified refs, policy, input) -> ReplacementDecision
project_decision_card(verified decision package) -> DecisionCard
build_execution_policy(input) -> ExecutionPolicy
build_execution_plan(verified capital decision, policy, observations) -> ExecutionPlan
project_execution_card(verified execution plan) -> ExecutionCard
```

These names describe application commands, not required HTTP routes. The transport must
deserialize strict contracts, call the canonical use case, and serialize the result. It must not
recalculate HHI, infer preferences, select or resize an amount, calculate tax from incomplete
metadata, change cash roles, choose which position to sell, invent a timing score, alter upstream
change conditions, or trust client-supplied canonical identifiers without server-side replay.

## Marginal Decision screen

The first functional allocation screen should display:

1. one locked T0 boundary and upstream fingerprints;
2. the exact capital amount, currency, and eligible funding cash;
3. candidate, incumbent, core ETF, and cash side by side;
4. before/after gross value, HHI bounds, and changed exposure components;
5. the four permanent-loss assessments;
6. a complete six-pair matrix with four trade-offs per pair;
7. missing data, conflicts, assumptions, and uncalibrated confidence;
8. owner policy blocks, when 6C2 policy is applied, without changing the original 6C1 record;
9. a preview of the immutable Decision Card;
10. an explicit submit action that invokes the application use case;
11. the returned decision ID and input fingerprint.

The interface may improve legibility but may not replace unknown with zero, hide unresolved ETF
weight, collapse currencies, synthesize a score, or silently resize the capital unit to pass a
constraint.

## Replacement screen

A 6C2 replacement screen should make one proposal inspectable rather than search for a sale. It
should display:

1. one verified source position and one explicit target;
2. the caller-supplied gross sale amount and source current market value;
3. target identity and, for a candidate, the verified Opportunity reference;
4. tax, fee, and spread separately, each with known/not-applicable/unknown state;
5. liquidity state and missing data;
6. gross sale amount, total switching friction, and net redeployable amount when friction is
   complete;
7. currently available investable same-currency cash used by `NEW_CAPITAL_FIRST`;
8. explicit owner-policy constraints and any policy block;
9. the source/target pre-friction comparison and the separate after-friction conclusion;
10. `REPLACE` or `HOLD` with the named decision basis;
11. T0, source fingerprints, decision fingerprint, and Decision Card preview.

`RUNNER` recovered proceeds may be shown as historical context only. The screen must not label the
remaining market value as free capital or subtract recovered proceeds from current opportunity
cost.

When replacement ratio constraints use explicit after-replacement observations, the interface must
show their source reference and fingerprint and must not present them as a canonical Chapter 6B
hypothetical-sale calculation.

## Execution screen

A Chapter 7 Execution screen is a point-in-time implementation review over one already-approved
capital decision. It should display:

1. immutable source decision ID/fingerprint and original T0 boundary;
2. locked target instrument and approved target amount;
3. for replacement, locked source instrument and gross sale amount;
4. T1 execution boundary and unchanged KnowledgeMode;
5. explicit owner quote-age, maximum-spread, and optional maximum-order-notional policy;
6. bid/ask, derived spread, observation/availability/recorded timestamps, source reference and
   fingerprint for every instrument that would trade;
7. exact upstream change conditions and their T1 `triggered`/`not_triggered`/`unknown` assessments;
8. liquidity state and missing data for every required trade instrument;
9. `NOW`, `STAGED`, `WAIT`, or `INVALIDATED` with inspectable categorical reasons;
10. for `STAGED`, every trade leg, sequence, tranche notional, and exact tranche-sum reconciliation;
11. Execution Plan ID/fingerprint and read-only Execution Card preview.

The screen must not offer controls to change target, strategic amount, replacement sale amount,
company quality, pairwise preference, or upstream invalidation text. `WAIT` and `INVALIDATED` are
valid non-executable results and therefore show no order legs.

A replacement plan may display SELL then BUY sequencing, but it must not present those legs as
submitted broker orders. Venue, order type, limit price, broker, actual submission time, fill
probability, dynamic slippage, and inferred liquidity schedule remain absent.

## Error and integrity behavior

- Validation errors return field-level explanations without changing the submitted draft.
- Boundary, integrity, and fingerprint failures are blocking and never downgraded to warnings.
- Missing inputs remain visible and must not be silently filled by the client.
- A replayed record is read-only; revisions create a new input and therefore a new fingerprint.
- `NO_ALLOCATION` is rendered as a valid decision, not an error.
- `HOLD` is rendered either as a no-new-capital review or as the valid result of a rejected
  replacement proposal, according to its source record.
- A policy-blocked alternative is not presented as an eligible best alternative.
- `REPLACE` is a capital decision, not an order instruction.
- All Chapter 6 Decision Cards render Execution as `not_evaluated`.
- `NOW` and `STAGED` remain immutable plan outputs, not proof that an order was submitted or filled.
- `WAIT` and `INVALIDATED` carry no executable legs.
- T1 observations outside the shared Temporal boundary are rejected, never shown as warnings.

## Productization sequence

1. Keep accepted Chapter 6 contracts stable while Chapter 7 is reviewed under ADR 0018.
2. Add a thin application-facing API adapter with strict request/response schemas for accepted
   Chapter 6 and, after acceptance, Chapter 7 use cases.
3. Persist immutable drafts, states, Fits, policies, capital decisions, Execution Plans, and source
   payload references.
4. Implement the operator workspace against those real schemas.
5. Start prospective use while retaining manual data entry where providers are absent.
6. Add the Learning screen only after Chapter 8 defines and accepts its contract.
7. Add any live broker adapter only through a separate accepted ADR and explicit owner
   authorization after the replayable planning contract is stable.

This sequence permits early use without designing a terminal, data platform, timing engine,
optimizer, or automated broker before AIE has demonstrated decision value.
