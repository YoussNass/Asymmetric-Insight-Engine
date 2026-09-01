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
evidence-backed discovery and Causal Alpha; Allocate includes Portfolio State, Exposure, Fit,
Marginal Allocation, and its explicit capital-flow policies without collapsing their ownership
contracts. Execute consumes a final capital decision and owns only operational implementation.
Learn consumes immutable decision/execution lineage and owns only ex-post evaluation evidence.

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

Every derived Exposure, Fit, Marginal Allocation, owner-policy, and replacement state retains
`as_of`, knowledge mode, method version, input fingerprint, missing inputs, conflicts, and
assumptions where applicable, as required by ADR 0006.

Marginal Allocation owns the target capital amount. Execution may stage that amount into tranches
but cannot change standalone quality or silently choose a different strategic allocation.

Downstream decision records should retain upstream identifiers and fingerprints and make exact
versions retrievable. They should not recursively duplicate complete upstream payloads when an
auditable immutable reference is sufficient.

ADR 0013 admits only policy-eligible diversified, unleveraged equity ETFs as Portfolio
instruments. Other ETFs and exchange-traded products remain context unless a later decision
explicitly expands the scope. ETF alternatives never enter company Underwriting.

## Chapter 6A Portfolio State boundary

The Chapter 6A implementation establishes the factual contract at the start of the
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
[`chapter-6a-portfolio-state.md`](chapter-6a-portfolio-state.md) and accepted ADR 0014.

## Chapter 6B Portfolio Exposure boundary

The Chapter 6B implementation derives an immutable analytical view from one verified
Portfolio State. It references the upstream state ID, fingerprint, portfolio ID, and knowledge
boundary instead of recursively copying factual holdings and cash.

Portfolio Exposure admits only:

- direct listed-equity company exposure;
- one-level ETF company containment with holdings date, source evidence, coverage, and unresolved
  residual;
- evidence-backed sector, primary economic geography, and overlapping economic-driver tags;
- native-currency instrument weights, resolved-company Top-N, and company HHI bounds;
- current and supplied-hypothetical snapshots for an explicit positive amount.

Instrument containment evidence is disjoint from classification evidence. Economic-driver tags
require interpretive claims and retain confidence calibration status; they are not causal edges or
ranking inputs. Missing classifications remain explicit unknown buckets.

Every metric is calculated inside an unconverted currency book. When company identity is missing,
HHI is reported as a lower and upper bound rather than converting residual weight into zero risk.
Economic-driver exposures are non-additive and no cross-currency concentration number exists.

The optional hypothetical must reference a canonical instrument already eligible under Portfolio
State policy. The capability does not select its instrument or amount and emits no Fit, score,
sizing, allocation, replacement, timing, or execution state. A new unheld stock candidate remains
outside this slice until Chapter 6C consumes the immutable Underwriting hand-off.

The full contract and limitations are documented in
[`chapter-6b-portfolio-exposure.md`](chapter-6b-portfolio-exposure.md) and accepted ADR 0015.

## Chapter 6C1 Portfolio Fit and Marginal Allocation boundary

The accepted Chapter 6C1 application use case is the first component with capital-decision
authority. It canonically replays one Opportunity State, one Portfolio State, current Exposure,
and exact supplied-amount Exposure views for one eligible incumbent and the core ETF. The
application layer joins these contexts at one knowledge boundary; Portfolio domain records retain
immutable references and fingerprints rather than importing or copying upstream domain payloads.

One caller-supplied capital unit must be known, positive, sufficiently funded by investable cash,
and expressed in a single native currency. It is evaluated unchanged across:

- a prospective listed-equity candidate bound to the Opportunity price fact and scenario anchors;
- one eligible existing listed-equity position;
- the policy-selected diversified core ETF;
- investment cash.

Portfolio Fit remains a descriptive content-addressed interaction view. Incumbent and ETF Fits
consume verified Chapter 6B before/after states. The prospective candidate remains outside factual
State and adds direct company exposure to the current native-currency book. Missing candidate
classification produces explicit unknown sector, geography, and driver deltas. The cash Fit
leaves securities exposure unchanged. No Fit emits preference, score, sizing, or allocation.

Marginal Allocation requires all six unordered pair comparisons. Standalone case, ordinal
permanent loss, portfolio effect, and uncertainty remain separate components and are never
averaged. Permanent-loss pair direction must agree with the disclosed per-alternative ordinal
classes. A non-cash alternative produces `ALLOCATE` only under complete pairwise dominance;
otherwise the conservative policy produces `NO_ALLOCATION` and preserves the unit as investment
cash.

`HOLD` is a separate no-new-capital position-review record. It carries no amount, replacement,
sale, or Execution authority. Timing and staging remain in Chapter 7.

The Decision Card interface is a read-only projection over verified records. It rechecks Fit
identifiers and fingerprints, contains no financial calculation, and fixes Execution to
`not_evaluated`. The accepted contract is documented in
[`chapter-6c1-marginal-decision.md`](chapter-6c1-marginal-decision.md) and accepted
[`ADR 0016`](adr/0016-explicit-marginal-capital-decision.md). The thin product boundary is
documented in [`operator-workspace-contract.md`](operator-workspace-contract.md).

## Chapter 6C2 replacement and capital-flow policy boundary

The accepted Chapter 6C2 slice extends the same Portfolio Decision bounded context. It does not
create a replacement engine, sizing engine, or tax optimizer and does not modify accepted 6C1
records.

An immutable `OwnerPortfolioPolicy` may declare one explicit maximum capital unit, owner-selected
maximum company weight, company-HHI upper bound, and economic-driver weight, plus lifecycle policy
for existing positions. These values are hard eligibility gates. They are not target weights and
are never used to derive a smaller position automatically.

`LEGACY_HOLD_ZERO_NEW_CAPITAL` allows an existing factual position to remain held while preventing
incremental capital. `RUNNER` may retain historical recovered proceeds for explanation, but the
remaining position always has current market value as its opportunity cost. Recovered historical
cost never enters allocation or replacement arithmetic.

Policy-constrained new-capital allocation canonically replays the accepted 6C1 package and removes
policy-ineligible non-cash alternatives with explicit reasons. Investment cash remains eligible.
The remaining alternatives reuse the existing pairwise comparisons; no rescoring occurs. A
non-cash allocation still requires complete dominance among all remaining eligible alternatives,
otherwise the exact unit stays as cash.

Replacement evaluates one explicit source position, one explicit target, and one positive
caller-supplied gross sale amount. The target may be the core ETF, another policy-eligible listed
holding, or a prospective candidate whose standalone Opportunity State is independently replayed.
The source and target must use one native currency; no implicit FX is performed.

Switching friction exposes tax, fee, and spread separately as `known`, `not_applicable`, or
`unknown`, while liquidity is an independent ordinal assessment. Unknown monetary friction or
unknown liquidity fails safely to `HOLD`. When monetary friction is complete:

```text
total_switching_friction = tax + fee + spread
net_redeployable_amount = gross_sale_amount - total_switching_friction
```

`NEW_CAPITAL_FIRST` prevents a sale when already-investable cash in the same currency can fund the
net target amount. Otherwise `REPLACE` requires the target to be explicitly preferred before and
after friction and to pass owner policy. Failure produces `HOLD` with a named basis; no hidden
switching score is admitted.

Because Chapter 6B has no canonical hypothetical-sale scenario, a replacement that uses owner
ratio constraints consumes explicit after-replacement observations carrying a source reference
and fingerprint. They are fingerprinted inputs, not a substitute for a new Exposure owner. A
future sell/rebalance Exposure scenario requires its own measured need and architecture decision.

Decision Card v2 adds `REPLACE` and replacement fields while retaining read-only projection
semantics. Its UUID namespace includes the projection method version so a v2 projection cannot
silently reuse a v1 card identity. Policy-blocked alternatives cannot be surfaced as the card's
best eligible alternative. Execution remains `not_evaluated`.

The accepted contract is documented in
[`chapter-6c2-replacement-policies.md`](chapter-6c2-replacement-policies.md) and accepted
[`ADR 0017`](adr/0017-replacement-and-capital-flow-policies.md).

## Chapter 7 Execution boundary

The accepted Chapter 7 slice introduces Execution as its own bounded context because operational
implementation has different language, inputs, lifecycle, and failure modes from Portfolio
Decision. The Execution domain contains no Portfolio, Underwriting, or Causal Alpha imports. The
application layer alone may replay and join approved Chapter 6 records.

Execution accepts only a canonically replayed final capital decision:

- a policy-constrained new-capital result with outcome `ALLOCATE`; or
- a replacement result with outcome `REPLACE`.

`NO_ALLOCATION` and `HOLD` carry no Execution authority. The resulting
`ApprovedCapitalInstruction` retains only the immutable source decision ID/fingerprint, original
T0 boundary, target instrument, target amount, exact upstream change conditions, and, for a
replacement, the source position/instrument and gross sale amount. Execution may never change
those strategic facts.

Execution has a separate T1 knowledge boundary satisfying:

```text
T1 >= T0
knowledge_mode(T1) == knowledge_mode(T0)
```

Bid/ask and invalidation observations carry observed, available, and recorded timestamps and must
pass the Temporal shared-kernel boundary. A future or not-yet-recorded observation is rejected
rather than treated as a soft warning.

An immutable content-addressed Execution Policy contains explicit owner limits for quote age,
bid/ask spread, and optional maximum single-order notional. These are operational gates, not alpha
signals or market-timing thresholds. No default Market State score exists.

The decision vocabulary is exactly:

- `INVALIDATED`: at least one exact upstream change condition is explicitly triggered;
- `WAIT`: the capital decision remains valid but invalidation evidence, quote freshness, spread,
  or liquidity does not pass current operational policy;
- `STAGED`: every non-staging gate passes but an explicit maximum-order notional requires one or
  more approved trade legs to be split;
- `NOW`: every gate passes and no staging limit requires a split.

The conservative priority is `INVALIDATED > WAIT > STAGED > NOW`. Missing or unknown upstream
invalidation state, missing/stale quotes, excessive spread, and liquidity that is unknown or
constrained all fail safely to `WAIT`. Constrained liquidity does not create an inferred schedule
in the MVP.

Staging never changes strategic capital. Each tranche is a deterministic chunk no larger than the
explicit order limit and tranche sums must exactly reproduce the approved leg. A new-capital
allocation has one BUY leg. A replacement has one SELL source leg followed by one BUY target leg;
the gross source-sale and net target amounts remain the exact Chapter 6 amounts.

The bounded context produces immutable, content-addressed Execution Plans only. Broker connection,
order submission, venue/order-type selection, limit-price logic, fill probability, dynamic
slippage, and Market State/regime scoring remain out of scope. A separate read-only Execution Card
projects the verified plan without mutating accepted Chapter 6 Decision Card identities.

The accepted contract is documented in [`chapter-7-execution-mvp.md`](chapter-7-execution-mvp.md)
and accepted [`ADR 0018`](adr/0018-point-in-time-execution-mvp.md).

## Chapter 8 Learning boundary

The proposed Chapter 8 slice introduces Learning as a separate downstream bounded context because
ex-post evaluation has a different temporal direction, language, and failure mode from
Underwriting, Portfolio Decision, and Execution. The Learning domain imports none of those
investment contexts. The application layer alone may canonically replay upstream records and
freeze immutable references into a Learning case.

The MVP opens an active Learning case only from a verified Chapter 7 Execution Plan with action
`NOW` or `STAGED`. This establishes that the decision reached an implementable planning state; it
does **not** establish that any broker order was submitted or filled.

Learning preserves three ordered knowledge boundaries:

```text
T0 = capital decision
T1 = Execution Plan
T2 = Learning evaluation
T2 >= T1 >= T0
knowledge_mode(T2) == knowledge_mode(T1) == knowledge_mode(T0)
```

Every later price or thesis observation carries observed, available, and recorded timestamps and
must pass the shared Temporal kernel at T2. Future, unavailable, or not-yet-recorded observations
are rejected. Outcome observations from before T0 are rejected.

The Learning case retains the exact T0 target reference price and declared Portfolio benchmark.
Target and benchmark must use one native currency. The MVP computes transparent price-only return:

```text
target_return = end_target_price / T0_target_price - 1
benchmark_return = end_benchmark_price / T0_benchmark_price - 1
excess_return = target_return - benchmark_return
```

For `REPLACE`, the case additionally retains the explicit source instrument and T0 source price so
the target can be compared with the source counterfactual:

```text
replacement_excess_vs_source = target_return - source_return
```

No implicit FX is admitted. Price-only return is not labelled total shareholder return and the
MVP does not invent dividends, corporate-action adjustments, fees after T1, or broker fill data.
Every evaluation therefore states that account P&L is not measured when fill data is absent.

Target maximum drawdown is calculated over the explicit T0 anchor followed by the admitted later
target-price observations. Missing intermediate observations are not forward-filled, and the
metric is an observed-path statistic rather than a claim about realized account experience.

Learning may re-evaluate only the exact upstream `change_conditions` carried by the verified
instruction. A triggered condition yields an invalidated thesis outcome; missing or unknown
assessments remain unresolved; all exact conditions explicitly not triggered yield intact.
Hindsight-only invalidation rules are rejected.

When the selected candidate has a verified Underwriting bear/base/bull range, Learning preserves
that exact T0 range and common horizon. Before the horizon the result remains `pre_horizon`; at or
after the horizon the observed target return is classified only as below bear, bear-to-base,
base-to-bull, or above bull. These are categorical observations, not probabilities or scores.

A single or small number of Learning records cannot emit Sharpe, Sortino, Information Ratio, win
rate, factor-adjusted alpha, or a claim of investment skill. Aggregate methods remain deferred
until prospective sample-size/horizon policy and appropriate data exist.

Learning has no automatic feedback authority. It cannot resize capital, rewrite owner policy,
change Underwriting gates, alter pairwise allocation logic or Execution thresholds, retrain a
model, or promote a deferred capability. Any future active feedback rule requires a separate
accepted ADR, prospective validation, and rollback plan.

The proposed contract is documented in [`chapter-8-learning-mvp.md`](chapter-8-learning-mvp.md)
and proposed [`ADR 0019`](adr/0019-decision-level-learning-mvp.md).

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
