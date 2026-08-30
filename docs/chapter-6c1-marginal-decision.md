# Chapter 6C1: Explicit marginal capital decision

## Outcome

Chapter 6C1 is the first slice allowed to decide where one disclosed unit of new capital belongs.
It compares a prospective stock, one eligible existing holding, the core ETF, and investment cash
without a portfolio score, implicit FX, or automatic sizing.

The architectural decision remains proposed in
[`ADR 0016`](adr/0016-explicit-marginal-capital-decision.md) until exact-head checks and explicit
owner approval authorize the merge.

## Contract map

| Contract | Owns | Explicitly does not own |
| --- | --- | --- |
| `CapitalUnit` | One positive amount, native currency, funding cash IDs, and rationale | Sizing, FX, or execution |
| `CapitalAlternative` | Candidate, incumbent, core ETF, or cash representation using that exact amount | A score or recommendation |
| `PermanentLossAssessment` | Explained ordinal loss class and visible support/missing data | A loss probability |
| `PairwiseCapitalComparison` | Four visible trade-offs and one qualitative conclusion for a complete pair | Weighted utility arithmetic |
| `PortfolioFit` | Content-addressed before/after portfolio interaction for one alternative | Preference, allocation, replacement, or timing |
| `MarginalDecision` | Complete competition and `ALLOCATE`/`NO_ALLOCATION` outcome | Order execution or tax replacement |
| `PositionReview` | Separate no-new-capital `HOLD` record | New capital, disposal, or `REPLACE` |
| `DecisionCard` | Read-only user/API projection of a verified record | Financial logic or decision authority |

## Competition policy

The evaluated set is fixed:

```text
candidate equity | existing holding | core ETF | investment cash
```

Every alternative receives the same amount and currency. All six unordered pairs are required.
Every pair keeps standalone case, permanent loss, portfolio effect, and uncertainty visible.

A non-cash alternative receives `ALLOCATE` only if it defeats all three competitors. Cash winning
all pairs, an indeterminate comparison, a tie, or a preference cycle produces `NO_ALLOCATION`.
Nothing is averaged into a total score.

`HOLD` answers a different question: an existing position remains held without evaluating new
capital. It is a separate record with no amount or execution field.

## Verified hand-offs

The application use case replays every upstream input before derivation:

1. Opportunity State proves the candidate's standalone readiness, company identity, observed
   reference price, scenario anchor, risks, and input fingerprint.
2. Portfolio State proves factual holdings, eligible incumbent, benchmark, funding cash role,
   amount availability, currency, and T0 fingerprint.
3. Current Portfolio Exposure proves the unmodified starting view.
4. Existing-holding and core-ETF Exposure states prove exact supplied-amount before/after views.

All states share one exact knowledge boundary. Downstream records retain references and
fingerprints rather than recursively copying upstream payloads.

## Portfolio Fit behavior

The incumbent and core ETF reuse verified Chapter 6B `hypothetical_after` states. The prospective
candidate remains outside factual State; its Fit adds direct exposure to the candidate company in
the current native-currency book. Evidence-backed sector, geography, and driver classifications
are used when available. Missing classification creates explicit `unknown` deltas instead of
zero exposure.

The cash Fit leaves securities gross value, HHI, and weights unchanged. It still carries the same
evaluated capital amount because cash is a real use of that unit, not absence of an alternative.

Portfolio Fit emits gross before/after values, HHI bounds, and changed weights only. Driver deltas
remain non-additive. It has no score or preference.

## Permanent loss and uncertainty

Permanent loss is an ordinal, uncalibrated judgement: `low`, `moderate`, `high`, or `unknown`.
The candidate must cite actual Underwriting risk IDs. The pairwise permanent-loss direction is
derived consistently from these classes and cannot contradict them.

Decision confidence is qualitative and explicitly uncalibrated. This keeps uncertainty visible
without converting epistemic annotations into allocation weights or probabilities.

## Decision Card

The interface projector exposes:

- `ALLOCATE`, `NO_ALLOCATION`, or the separate `HOLD` action;
- evaluated amount where applicable;
- selected and best rejected alternatives;
- three to five reasons;
- risks and unknowns;
- qualitative confidence and calibration status;
- conditions that would change the decision;
- selected Portfolio Fit effect;
- `not_evaluated` Execution status;
- T0 and input fingerprint.

It verifies the Fit references already owned by the decision and copies them into a stable view.
It cannot rank, size, allocate, stage, or submit an order.

## Deterministic reference case

The synthetic vertical fixture builds one coherent T0 chain from evidence and causal analysis
through Underwriting, State, Exposure, Marginal Decision, and Decision Card. It uses:

- a prospective Micron fixture bound to the verified USD 100 Underwriting price fact;
- one eligible synthetic existing USD equity;
- one policy-selected diversified USD core ETF;
- one explicit USD 100 capital unit funded by opportunistic, not emergency, cash;
- complete one-level ETF look-through and company classifications;
- four loss assessments and all six pairwise comparisons.

The reference comparison makes the candidate the complete pairwise winner so the expected result
is `ALLOCATE USD 100`. Other tests make cash dominant or break dominance and require
`NO_ALLOCATION`. This is contract verification, not a Micron recommendation or proof of alpha.

## Demonstrated properties

Tests cover:

- exact four-alternative and six-pair completeness;
- equal amount/currency and funding eligibility;
- Opportunity price/company/risk binding;
- current and hypothetical Exposure replay;
- native-currency Fit arithmetic and unknown classification;
- ordinal permanent-loss consistency;
- conservative cash fallback under indeterminacy;
- order and pair-orientation invariance;
- serialization, content addressing, canonical replay, and tamper rejection;
- separate `HOLD` semantics;
- read-only Decision Card projection;
- application/domain dependency direction;
- the complete T0 vertical hand-off.

These properties demonstrate deterministic technical correctness against the admitted policy.
They do not demonstrate that the policy generates alpha. That requires prospective records and
Chapter 8 outcome evaluation.

## Deliberate limits

- one discrete caller-supplied amount per decision;
- one incumbent and one core ETF competitor;
- no replacement, tax, spread, fee, or liquidity friction;
- no PAC, Legacy, or Runner policy;
- no automatic sizing, total ordering, optimizer, or portfolio score;
- no implicit FX or cross-currency comparison;
- no market regime, timing, tranche, or order instruction;
- no live provider, persistence adapter, HTTP API, or functional frontend.

## Exit criterion

Chapter 6C1 is complete only after ADR 0016 is accepted and the implementation is merged with
green exact-head CI. At that point AIE can produce its first auditable marginal-capital decision.
Prospective investment validity, replacement friction, Execution, and Learning remain later
stages.
