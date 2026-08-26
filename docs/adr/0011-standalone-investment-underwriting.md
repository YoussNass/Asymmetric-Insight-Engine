# ADR 0011: Establish standalone investment underwriting

- Status: Proposed
- Date: 2026-08-26

## Context

The accepted causal slice ends with a falsifiable listed-beneficiary hypothesis. That hand-off
does not establish whether the company can survive, capture the identified value, convert earnings
to cash, earn an adequate return on capital, preserve value per share, execute, or offer an
asymmetric payoff at a stated price.

Those questions must be answered before portfolio context is allowed to influence the case. If
holdings, diversification, available cash, or risk budget enter Underwriting, the same company can
receive a different intrinsic assessment for different owners. If all dimensions are collapsed
into a score, missing evidence and disqualifying conditions can be hidden by unrelated strengths.

## Decision

Chapter 5 introduces a deterministic Investment Underwriting contract. It consumes exactly one
`ready_for_underwriting` causal analysis whose candidate, `as_of`, and knowledge mode match the
underwriting boundary. It produces an immutable standalone Opportunity State.

### Financial fact model

Each reported or analyst-adjusted fact declares:

- a stable fact identifier and typed metric;
- a finite decimal value and explicit unit;
- an instant or duration period that does not extend beyond `as_of`;
- a reported or analyst-adjusted basis;
- one or more supporting claims;
- a normalization note for every analyst adjustment.

Reported facts must trace to immutable source bytes whose canonical subject is the candidate.
Analyst adjustments remain visible and cannot masquerade as reported values.

Derived facts declare their input fact identifiers, transparent formula, output unit, and
calculation version. The domain recalculates revenue growth, margins, free cash flow, net debt,
diluted-share growth, and ROIC from those inputs and rejects submitted results that do not match.
No binary floating-point arithmetic is used for financial calculations.

### Standalone assessment

The complete state preserves exactly eight independent dimensions:

1. revenue and margins;
2. cash and earnings quality;
3. ROIC;
4. balance sheet and capital needs;
5. dilution and per-share economics;
6. value capture and competition;
7. operating execution;
8. valuation and asymmetry.

Each dimension carries a categorical outcome, rationale, claim and fact lineage, missing data,
conflicts, assumptions, and invalidation conditions. No aggregate 0–100 score, weighting formula,
or hidden recommendation is produced.

Exactly six explicit eligibility gates remain separate from the dimensions: causal hand-off,
survivability, economic value capture, per-share integrity, valuation completeness, and
falsifiability. A passing gate proves that its stated contract requirement is supported; it does
not prove that the security is attractive or suitable for a portfolio.

### Valuation and payoff

If valuation is present, the state contains exactly one bear, base, and bull scenario. Every
scenario discloses its method and version, assumptions and inferential claims, supporting facts,
reference price, enterprise value, net debt, equity value, diluted shares, implied price, return,
and invalidation conditions. The domain verifies the bridge:

```text
equity value = enterprise value - net debt
implied price = equity value / diluted shares
scenario return = implied price / reference price - 1
```

The reference price must be exactly supported by a declared fact. Diluted shares and net debt must
be anchored to declared current facts; scenario-specific departures remain visible assumptions
supported by interpretive claims. Scenario ordering must remain `bear < base < bull` for both
implied price and return.

No scenario probability is accepted because Chapter 5 has no admitted calibrated forecast
distribution. A probability-free payoff profile may show explicit bear downside, base return,
bull upside, and the arithmetic ratio of bull upside to absolute bear downside. That ratio is
versioned and transparent, but it is not a score, ranking policy, decision gate, or sizing rule.

### Readiness and determinism

Allowed states are `investigate`, `insufficient_evidence`, `ready_for_portfolio_review`, and
`invalidated`. A ready state requires complete source, evidence, claim, financial-fact, dimension,
gate, scenario, catalyst, risk, and invalidation lineage. Unknown dimensions, failed or unknown
gates, future facts, and unused analytical artefacts prevent readiness.

The builder re-reads and verifies every causal and underwriting source, applies the canonical
knowledge boundary, canonicalizes unordered input collections, and content-addresses the complete
state. The same validated inputs produce the same fingerprint and identifier.

The contract accepts no portfolio holdings, cash, benchmark, risk budget, correlation,
concentration, liquidity, tax, market-regime, sizing, timing, or execution input. Those remain
owned by downstream bounded contexts.

## Reference case

The deterministic fixture continues the Micron beneficiary hypothesis from Chapter 4. Selected
reported figures use Micron's fiscal 2025 Form 10-K identity. The repository stores only short,
explicitly synthetic excerpts, not the filing. A separate synthetic market observation fixes a
round reference price solely to make per-share arithmetic reproducible.

The scenario enterprise values and selected analytical inputs are illustrative, uncalibrated
contract fixtures. They do not constitute a forecast, current market quote, complete fundamental
analysis, recommendation, or claim that Micron is ready for a real portfolio.

## Acceptance criteria

Chapter 5 is complete only when:

1. only a matching `ready_for_underwriting` causal analysis can enter the bounded context;
2. all causal and underwriting source bytes and metadata are independently verified, and each
   causal source still matches the immutable version embedded in the hand-off;
3. reported facts have direct candidate provenance and adjusted facts remain explicit;
4. periods, units, bases, claim links, and the temporal boundary are validated;
5. every derived fact reproduces under its declared versioned formula;
6. the exact eight dimensions and six categorical gates remain complete and non-duplicated;
7. bear/base/bull scenarios reproduce the enterprise-value-to-per-share bridge and strict order;
8. no uncalibrated probability, aggregate score, portfolio input, or allocation instruction enters
   the state;
9. the same material inputs produce a stable fingerprint and identifier, while a material change
   changes both;
10. unit, negative-path, integration, architecture, typing, packaging, Python 3.12/3.13, and
    container checks pass.

## Consequences

- AIE gains an auditable boundary between a causal beneficiary hypothesis and portfolio analysis.
- Financial normalization and valuation arithmetic have canonical, deterministic ownership.
- Strength in one dimension cannot average away a failed gate, unknown dimension, or missing data.
- Portfolio diversification cannot rewrite company quality or standalone investment economics.
- The initial model is intentionally verbose and strict; automated extraction must satisfy the
  same contracts rather than bypass them.
- Complete filing normalization, calibrated forecasts, Market State, Portfolio Exposure,
  Portfolio Fit, Marginal Allocation, timing, sizing, and execution remain deferred.
