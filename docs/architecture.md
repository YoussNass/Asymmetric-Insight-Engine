# Architecture

## Style

The project starts as a modular monolith with hexagonal boundaries. This preserves one coherent
domain model and transaction boundary while keeping external providers replaceable.

```text
interfaces -> application -> domain
                    ^
                    |
             infrastructure
```

The domain layer contains pure financial and epistemic invariants. Application services
orchestrate use cases through ports. Infrastructure implements data, persistence, model, and
vendor adapters. Interfaces expose CLI, API, scheduled jobs, and future dashboards.

## Conceptual decision flow

The product should be understandable through five stages:

```text
UNDERSTAND -> UNDERWRITE -> ALLOCATE -> EXECUTE -> LEARN
```

This is a conceptual view, not a deployment topology or a requirement for exactly five bounded
contexts. Evidence and the Temporal shared kernel support every stage. Understand includes
evidence-backed discovery and Causal Alpha; Allocate includes Portfolio State, Exposure, Fit, and
Marginal Allocation without collapsing their ownership contracts.

The detailed delivery sequence is maintained in [`roadmap.md`](roadmap.md).

## Dependency rules

- Domain imports Python standard library and domain-approved validation primitives only.
- Domain never imports infrastructure, application, or interfaces.
- Application depends on domain contracts and declares ports.
- Infrastructure implements application ports.
- Interfaces invoke application services and contain no financial calculations.
- Each fact, transformation, score, and decision has one canonical owner.

## Complexity governance

New sophistication is admitted through the [`Complexity Budget`](complexity-budget.md). A
capability must identify the decision it changes, validation method, required point-in-time data,
explanation, maintenance burden, and reason it is needed now.

Named rules do not automatically become engines. Policies remain inside the context that owns the
decision; metrics remain inspectable components; experimental extensions have no active decision
authority. The required sequence is simple implementation, prospective measurement, observed
failure, narrow complexity addition, and validation against the simpler baseline.

## Temporal model

Evidence distinguishes:

- `effective_at`: when the fact applies in the world;
- `available_at`: when the information became knowable to the system;
- `recorded_at`: when the system ingested it;
- `as_of`: the decision-time boundary.

Every opportunity state must declare one of two knowledge modes:

- `historical_reconstruction`: evidence must satisfy `available_at <= as_of`; a later ingestion
  is permitted only because the calculation reconstructs what was publicly knowable then;
- `live_system_replay`: evidence must satisfy both `available_at <= as_of` and
  `recorded_at <= as_of`, reproducing what this system had actually acquired by that time.

There is no implicit default mode. Restatements and backfills create new records or versions
rather than silently rewriting prior knowledge.

## Underwriting-to-portfolio boundary

Chapter 5 implements the standalone Underwriting bounded context. It consumes one immutable
`ready_for_underwriting` causal analysis for the same candidate and knowledge boundary, then owns:

- normalized financial facts with explicit metric, unit, native currency when monetary, period
  kind and scope, basis, and claim lineage;
- deterministic derived facts with transparent formula and calculation version;
- independent assessments of revenue and margins, cash and earnings quality, ROIC, balance sheet
  and capital needs, dilution and per-share economics, value capture and competition, operating
  execution, and valuation and asymmetry;
- categorical eligibility gates for causal hand-off, survivability, value capture, per-share
  integrity, valuation completeness, and falsifiability;
- bear, base, and bull enterprise-value-to-equity-to-per-share bridges with explicit observation
  date, horizon, current capital-structure anchors, and scenario assumptions;
- catalysts, risks, missing data, conflicts, assumptions, and invalidation conditions.

The application builder independently verifies the causal and underwriting source bytes, rebuilds
the causal identity from its canonical verified content, confirms that each causal source still
matches the immutable version embedded in the hand-off, checks the canonical temporal boundary,
and content-addresses the complete input. Reported financial facts must have direct source
provenance from the candidate company; market observations require candidate market-data
provenance. Derived facts are recalculated from their declared inputs rather than trusted as
submitted values. Monetary formulas require one native currency and never imply an FX conversion.

Underwriting may mark the resulting immutable Opportunity State
`ready_for_portfolio_review`. This means the standalone case is structurally complete enough for
the next bounded context. It is not a recommendation and cannot declare the opportunity
allocatable: Market State, portfolio exposure, portfolio fit, competing uses of capital,
correlation, concentration, liquidity, tax context, sizing, and execution remain downstream.

No portfolio holdings, cash balance, benchmark, risk budget, market-regime input, or execution
parameter is accepted by the Underwriting contract. The same causal analysis, facts, assumptions,
and temporal boundary therefore produce the same Opportunity State regardless of who owns what.

Valuation scenarios carry no probability in this slice because no calibrated distribution model
has been admitted. The displayed upside-to-downside ratio is transparent arithmetic over the
explicit bear and bull returns; it is neither a universal score nor an eligibility, ranking, or
allocation rule.

## Portfolio Decision MVP boundary

ADR 0012 establishes one Portfolio Decision bounded context with four separate immutable
contracts:

- Portfolio State records holdings, instruments, cash roles, and basic cost/tax metadata;
- Portfolio Exposure derives descriptive direct and indirect exposure;
- Portfolio Fit describes how an unchanged standalone Opportunity State interacts with current
  exposure;
- Marginal Allocation compares explicit before/after alternatives and owns the capital decision.

The contracts remain distinct because they have different invariants and cannot overwrite one
another. They do not require separate services, score engines, or chapters. Competition for
Capital, ETF/cash hurdles, replacement, PAC, Legacy Holding, Runner, and concentration preferences
remain policies or state within the appropriate owner.

The minimum exposure path is initially:

```text
holding -> instrument -> underlying company -> sector -> geography -> economic driver
```

Unknown constituent or dependency coverage remains unresolved rather than being normalized away.
Instrument containment and evidence-backed economic-driver classification remain separate
provenance layers; neither ETF membership nor a shared label establishes causality.
Structural correlation, factors, effective independent bets, advanced tax optimization, automated
sizing, and portfolio optimization remain deferred until measured failure and data sufficiency
justify them.

Every derived Exposure, Fit, and Marginal Allocation state retains `as_of`, knowledge mode,
method version, input fingerprint, missing inputs, conflicts, and assumptions as required by ADR
0006.

Marginal Allocation owns the target capital amount. Execution may stage that amount into tranches
but cannot change standalone quality or silently choose a different strategic allocation.

Downstream decision records should retain upstream identifiers and fingerprints and make exact
versions retrievable. They should not recursively duplicate complete upstream payloads when an
auditable immutable reference is sufficient.

ADR 0013 admits only policy-eligible diversified, unleveraged equity ETFs as Portfolio
instruments. Other ETFs and exchange-traded products remain context unless a later decision
explicitly expands the scope. ETF alternatives never enter company Underwriting.

## Chapter 6A Portfolio State boundary

The Chapter 6A implementation candidate establishes the factual contract at the start of the
Portfolio Decision context. It consumes no Causal Alpha or Opportunity State and has no exposure,
fit, sizing, allocation, market-regime, or execution fields.

Portfolio State has one canonical owner for each input:

- versioned input records carry provider version, source reference, effective, available, and
  recorded times, and an exact content hash;
- accounts own basic tax treatment and jurisdiction;
- instruments own identity, type, native currency, and structural ETF facts;
- positions reference accounts, instruments, holdings records, and the instrument's T0 price;
- cash balances reference accounts and retain an explicit cash role;
- the ETF eligibility policy owns the allow-list and benchmark designation.

Representation, eligibility for new capital, and benchmark role are independent. Existing
ineligible instruments remain representable. A diversified unleveraged equity ETF becomes
eligible only through the versioned ADR 0013 policy; being held never grants eligibility.

All money remains in native currency. The factual state validates `current value = quantity × T0
price` and may produce currency-grouped subtotals, but it has no cross-currency total or implicit
FX conversion. The application builder canonicalizes unordered collections and content-addresses
the complete input. Its T0 audit envelope contains the state identifier, fingerprint, knowledge
boundary, benchmark, and method version but no capital decision.

Downstream consumers must verify a deserialized Portfolio State by rebuilding its canonical input
before trusting the identifier and fingerprint. This detects altered state content or generated
identity; verification of future live provider bytes remains an outer adapter responsibility.

The full contract and limitations are documented in
[`chapter-6a-portfolio-state.md`](chapter-6a-portfolio-state.md) and proposed ADR 0014.

## Adjacent applications and experiments

The Market Screener is a separate application that consumes stable engine contracts and must not
duplicate their financial logic. The Quantum Cycle Model is an experimental use-case adapter,
not a dependency or organising principle of the core. The durable decision is recorded in
[ADR 0005](adr/0005-adjacent-applications-and-experimental-models.md).

## Initial persistence direction

Persistence is deferred until the Data and Evidence chapter. The intended split is:

- PostgreSQL for evidence metadata, causal objects, research state, portfolio state, and audit;
- immutable raw snapshots plus Parquet for time-series history;
- DuckDB for local analytical queries and reproducible research.

No domain contract may depend on this storage choice.

Chapter 3 begins with a SQLite reference adapter that atomically stores exact synthetic payloads
and append-only source metadata. It exists to validate provider version identity, idempotency,
restatement handling, and shared knowledge-boundary queries. It is not a production persistence
decision and does not change the PostgreSQL, immutable snapshot, Parquet, and DuckDB direction.

The final Chapter 3 slice adds a controlled CLI around those application ports. Real SEC access is
explicit, sequential, rate-limited, and configured through a declared local user agent. Tests and
CI never contact providers. Integrity verification re-reads exact bytes; knowledge-coverage
reporting describes only versions known to the ledger and cannot assert source-universe
completeness without a separate expected-source manifest.

## Evidence-to-causal boundary

Chapter 4 introduces a narrow Causal Alpha contract before Underwriting:

```text
real-world change -> economic driver -> supply-chain actor -> listed beneficiary
```

Each node has one typed economic role and cites its supporting claims. A real-world-change node
requires an observation or statistical result, which is the explicit input signal. Each forward
edge states a mechanism and requires inferential or hypothesis support; an observation, theme
label, instrument containment relationship, or correlation cannot by itself establish causality.
The beneficiary-mapping edge must resolve to evidence whose immutable source has the target
company's canonical subject identity.

Causal evidence links to one immutable source-document version with a locator and extraction
method. The application builder verifies the source bytes and metadata, applies the canonical
knowledge boundary, and content-addresses the complete input. Collection ordering does not change
the resulting fingerprint; a material claim, mechanism, temporal boundary, or source-version
change does.

Canonical output orders nodes and edges by their economic stage rather than alphabetically. Every
readiness state includes a rationale. Claim confidence exposes whether it is calibrated and which
method produced it when applicable; uncalibrated annotations cannot become gates or ranking inputs.

`ready_for_underwriting` means that a complete, falsifiable path is structurally suitable for the
next bounded context. It conveys no conclusion about company quality, value capture, valuation,
expected return, price, timing, portfolio fit, sizing, or execution.

## AI boundary

AI adapters may extract claims, entities, relations, or candidate hypotheses. Their output is
untrusted until validated against source provenance and domain rules. Deterministic code owns
time filtering, numerical transformations, scoring, constraints, and portfolio calculations.
The Chapter 4 reference slice therefore uses deterministic manual fixture extraction; it does not
grant an AI adapter authority to create a validated causal decision.
