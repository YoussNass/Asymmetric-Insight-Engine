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
| Decision Card | Verified decision package | Projection only | Nothing |

Execution and Learning views remain disabled until Chapters 7 and 8 define their contracts.

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
```

These names describe application commands, not required HTTP routes. The transport must
deserialize strict contracts, call the canonical use case, and serialize the result. It must not
recalculate HHI, infer preferences, select or resize an amount, calculate tax from incomplete
metadata, change cash roles, choose which position to sell, or trust client-supplied canonical
identifiers without server-side replay.

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

## Productization sequence

1. Keep the accepted 6C1 contracts stable and accept 6C2 only after its exact-head review.
2. Add a thin application-facing API adapter with strict request/response schemas for the accepted
   Chapter 6 use cases.
3. Persist immutable drafts, states, Fits, policies, decisions, and source payload references.
4. Implement the operator workspace against those real schemas.
5. Start prospective use while retaining manual data entry where providers are absent.
6. Add Execution and Learning screens only after Chapters 7 and 8 define and accept their own
   contracts.

This sequence permits early use without designing a terminal, data platform, optimizer, or
automated broker before AIE has demonstrated decision value.
