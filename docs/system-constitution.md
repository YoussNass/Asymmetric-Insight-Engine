# System Constitution

## Mission

The Asymmetric Insight Engine identifies real-world changes whose second-, third-, or
fourth-order economic consequences are not yet correctly reflected in expectations and prices.
It maps those consequences to listed securities, evaluates value capture per share, and supports
the marginal allocation of capital.

The canonical decision chain is:

```text
Evidence -> Insight -> Causal Alpha -> Investment Underwriting -> Opportunity State
         -> Portfolio Decision -> Execution Plan -> Monitoring -> Learning
```

## Bounded responsibilities

### Evidence Ledger

Stores source provenance and the time at which information became knowable. It is the shared
factual substrate for every engine.

### Insight Discovery

Detects anomalies, contradictions, latent variables, structural changes, and falsifiable
hypotheses. It does not select securities or allocate capital.

### Causal Alpha

Builds temporal causal chains, dependency graphs, bottleneck hypotheses, second-order effects,
and the Reality-Expectations-Price gap.

### Investment Underwriting

Maps the causal thesis to company survival, value capture, dilution, execution, valuation,
per-share economics, scenarios, and return distributions.

### Market State

Measures global, sector, thematic, liquidity, cycle, regime, breadth, divergence, and timing
conditions. It can confirm or challenge readiness without creating the causal thesis.

### Portfolio and Capital Allocation

Determines portfolio eligibility, role, sizing, risk budget, correlation, concentration, cash,
tax context, and marginal capital utility. It consumes upstream outputs rather than recreating
them.

### Execution and Monitoring

Plans staged entries, additions, reductions, exits, and alerts; evaluates thesis invalidations;
and records outcomes for calibration and learning.

## Mandatory distinctions

The system must never collapse these separate concepts:

- company quality;
- causal-thesis quality;
- investment quality at the current price;
- temporal opportunity;
- portfolio compatibility;
- execution quality.

## Epistemic contract

Every material statement is classified as one of:

1. observed data;
2. statistical result;
3. inference;
4. hypothesis;
5. qualitative judgement.

Every decision must expose its evidence, confidence, missing data, conflicting signals, and
invalidation conditions. The system may return `insufficient evidence` or `no allocation`.

Every analytical state must also declare its temporal knowledge mode. Historical reconstruction
uses only source versions publicly knowable by `as_of`; live-system replay additionally uses only
records actually ingested by `as_of`. The two modes must never be silently interchanged.

The Temporal shared kernel is the canonical owner of this boundary. Evidence, Opportunity,
Market State, Portfolio, Execution, and Learning must consume it rather than define local time
filters or import temporal semantics from one another.

## Canonical analytical ownership

The decision chain has five non-interchangeable state boundaries:

1. Investment Underwriting owns the standalone opportunity assessment.
2. Portfolio Exposure owns descriptive instrument look-through and evidence-backed economic
   dependencies.
3. Portfolio Fit measures how an unchanged standalone opportunity interacts with the current
   portfolio.
4. Marginal Allocation compares explicit before/after states, constraints, frictions, and other
   eligible uses of capital.
5. Execution owns staging and implementation after an allocation decision.

No downstream context may recreate, overwrite, or silently rescore an upstream state. Instrument
containment and economic causality are separate graph layers: a shared ticker, fund constituent,
theme, or label is not by itself evidence of a causal dependency.

## Scoring contract

The canonical sequence is:

```text
Eligibility gates -> multidimensional state vector -> calibrated scenarios
                  -> contextual portfolio utility
```

There is no universal score whose increase always means a better investment. Higher momentum,
for example, can represent either healthy expansion or euphoria depending on regime and price.

Any contextual scalar must identify its policy and method version, calibration status, component
vector, eligibility gate, missing inputs, assumptions, and before/after deltas. An uncalibrated
heuristic is an experiment, not an active allocation default.

## Version 1 scope

- global listed equities and cash as the investable universe;
- indexes, ETFs, rates, commodities, and crypto initially as context variables;
- long-only decision support;
- daily market updates and event-driven fundamental evidence;
- Italian tax logic behind a replaceable adapter;
- no live order submission;
- public or freely accessible providers first, with explicit capability and coverage flags.

## Definition of done

The system is operational only when it is reproducible, point-in-time safe, auditable, tested,
resilient to missing data, and able to explain every decision and invalidation. Predictive
infallibility is not an acceptance criterion.
