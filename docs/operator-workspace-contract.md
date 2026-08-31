# Minimum operator workspace contract

## Purpose

This document fixes the thinnest usable product path around the accepted domain architecture. It
is a contract for future API and frontend work, not an implemented server or UI.

The operator workspace reviews inputs, invokes application use cases, and renders immutable
outputs. It contains no financial formulas, ranking, sizing, temporal filtering, or eligibility
logic.

## Initial workflow

| Workspace view | Reads | Invokes | May edit before invocation |
| --- | --- | --- | --- |
| Research case | Evidence and claims | Evidence/Causal use cases | Source selection, claim typing, invalidations |
| Causal chain | Causal Analysis draft/state | Causal builder | Nodes, mechanisms, claim support |
| Underwriting | Opportunity draft/state | Underwriting builder | Facts, explicit adjustments, scenarios, risks |
| Portfolio State | Accounts, positions, prices, cash roles, ETF policy | Portfolio State builder | Imported/manual factual records before snapshot |
| Exposure | Current and supplied hypothetical inputs | Exposure builder | Point-in-time ETF snapshots and classifications |
| Marginal Decision | Four alternatives, loss classes, six pairwise comparisons | Marginal Decision builder | Capital unit and explicit qualitative judgements |
| Decision Card | Verified decision and Fits | Projection only | Nothing |

Execution and Learning views remain disabled until Chapters 7 and 8 define their contracts.

## Minimum application boundary

A future transport adapter may expose use-case-shaped operations such as:

```text
build_opportunity(draft) -> OpportunityState
build_portfolio_state(draft) -> PortfolioState
build_exposure(state_ref, input) -> PortfolioExposure
build_marginal_decision(verified refs, input) -> Fits + MarginalDecision
record_position_hold(verified refs, input) -> PositionReview
project_decision_card(verified decision package) -> DecisionCard
```

These names describe application commands, not required HTTP routes. The transport must
deserialize strict contracts, call the canonical use case, and serialize the result. It must not
recalculate HHI, infer preferences, select an amount, change cash roles, or trust client-supplied
identifiers without server-side replay.

## Marginal Decision screen

The first functional screen should display:

1. one locked T0 boundary and upstream fingerprints;
2. the exact capital amount, currency, and eligible funding cash;
3. candidate, incumbent, core ETF, and cash side by side;
4. before/after gross value, HHI bounds, and changed exposure components;
5. the four permanent-loss assessments;
6. a complete six-pair matrix with four trade-offs per pair;
7. missing data, conflicts, assumptions, and uncalibrated confidence;
8. a preview of the immutable Decision Card;
9. an explicit submit action that invokes the application use case;
10. the returned decision ID and input fingerprint.

The interface may improve legibility but may not replace unknown with zero, hide unresolved ETF
weight, collapse currencies, or synthesize a score.

## Error and integrity behavior

- Validation errors return field-level explanations without changing the submitted draft.
- Boundary, integrity, and fingerprint failures are blocking and never downgraded to warnings.
- Missing inputs remain visible and must not be silently filled by the client.
- A replayed record is read-only; revisions create a new input and therefore a new fingerprint.
- `NO_ALLOCATION` is rendered as a valid decision, not an error.
- `HOLD` is rendered as a no-new-capital review, not as failed allocation.
- Chapter 6C1 always renders Execution as `not_evaluated`.

## Productization sequence

1. Stabilize and accept the 6C1 contracts.
2. Add a thin application-facing API adapter with strict request/response schemas.
3. Persist immutable drafts, states, Fits, decisions, and source payload references.
4. Implement the operator workspace against those real schemas.
5. Start prospective use while retaining manual data entry where providers are absent.
6. Add 6C2, Execution, and Learning screens only after their contracts are accepted.

This sequence permits early use without designing a terminal, data platform, or automated broker
before AIE has demonstrated decision value.
