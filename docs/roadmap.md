# AIE delivery roadmap

## Status and authority

This document is the canonical delivery sequence under accepted ADR 0012. It does not declare a
capability implemented; the code, accepted ADRs, tests, and merged pull requests remain the
implementation record.

At the time of this roadmap:

- Chapters 2 through 10 are complete in `main`;
- factual Portfolio State, Portfolio Exposure, Portfolio Fit, Marginal Allocation, owner policy,
  replacement, capital-flow policy, point-in-time Execution, decision-level Learning, and the
  typed `aie-api-v1` product boundary are canonical;
- Chapter 9A, 9B, and 9C are complete under accepted ADR 0020, ADR 0021, and ADR 0022; their
  integrated implementation reached `main` through PR #30;
- Chapter 10 is complete under accepted ADR 0023 and reached `main` through PR #31;
- Chapter 11 implements the accepted ADR 0024 scope through PRs #32–#34; formal closure
  is gated by the final merge and green main CI;
- Market State remains unimplemented and deferred in the canonical engine;
- the earlier Portfolio Exposure Graph spike is research material only under ADR 0006.

Every roadmap change must pass the [`Complexity Budget`](complexity-budget.md). Deferred items are
preserved with graduation criteria instead of being silently discarded or implemented early.

## Product mental model

Users and developers should be able to understand AIE through five questions:

```text
UNDERSTAND -> UNDERWRITE -> ALLOCATE -> EXECUTE -> LEARN
```

This is a conceptual flow, not a requirement for exactly five bounded contexts. Evidence and the
Temporal shared kernel support every stage.

| Stage | Minimum responsibility |
| --- | --- |
| Understand | Evidence, human-assisted discovery, and falsifiable causal beneficiary mapping |
| Underwrite | Immutable standalone company and opportunity state at the current price |
| Allocate | Portfolio state, exposure, interaction, competing alternatives, and marginal capital decision |
| Execute | Implement an approved amount through explicit staging without rewriting the thesis |
| Learn | Compare the immutable T0/T1 record with later point-in-time decision outcomes without hindsight |

## Mandatory sequencing gate

The prerequisites for Chapter 6 were satisfied on 2026-08-27:

1. Chapter 5 was reviewed, corrected, accepted, and merged;
2. ADR 0012 and ADR 0013 were explicitly accepted;
3. the minimal ETF-scope Constitution amendment was approved;
4. the owner authorized the compressed roadmap and Chapter 6A as the next slice.

Chapter 6 was completed on 2026-08-31 after ADR 0014 through ADR 0017 were accepted and their
implementations merged. Chapter 7 then passed its technical and governance gates under accepted ADR
0018 and PR #24 was merged into `main` on 2026-09-01. Chapter 8 was subsequently implemented and
merged in PR #25; the owner explicitly accepted ADR 0019 on 2026-09-01. PR #26 then added the narrow
same-instrument replacement invariant discovered during the Chapter 8 red-team.

Chapter 9A then established the stable product-facing typed boundary. ADR 0020 was explicitly
accepted and PR #27 was reviewed and merged into `main`. Chapter 9B immutable persistence and
Chapter 9C operator workspace followed under accepted ADR 0021 and ADR 0022; their integrated head
was merged through PR #30 on 2026-09-02. Chapter 10 now composes those accepted capabilities with
the upstream Causal and Underwriting owners over real local evidence and product stores.

Each later slice still requires its own narrow branch, tests, draft pull request, explicit ADR
acceptance, and separate merge authorization. Approval of this roadmap does not authorize merging
an unreviewed future implementation.

## Active minimum-complete roadmap

### Chapter 6A — Portfolio State, instruments, and capital

**Purpose:** establish the factual state consumed by every later portfolio calculation.

**Status:** complete; ADR 0014 accepted and implementation merged with exact-head local and remote
verification.

In scope:

- immutable portfolio snapshot and canonical knowledge boundary;
- positions, quantities, prices, currencies, and current values;
- instrument identity and type;
- investment cash and explicit cash roles;
- basic cost-basis and tax metadata without tax optimization;
- benchmark identity;
- T0 input fingerprint and decision-record envelope.

Out of scope:

- ETF constituent expansion;
- portfolio fit or allocation decisions;
- automatic sizing;
- market regimes or execution timing.

Exit criterion: AIE can reproduce what was owned and what capital was available at T0 without
making an allocation recommendation.

The contract and deterministic reference case are documented in
[`chapter-6a-portfolio-state.md`](chapter-6a-portfolio-state.md). Chapter 6B consumes this state by
immutable identifier and verified fingerprint rather than redefining factual holdings or cash.

### Chapter 6B — Minimal Portfolio Exposure

**Purpose:** expose hidden direct and indirect economic concentration descriptively.

**Status:** complete; ADR 0015 accepted and implementation merged with exact-head local and remote
verification.

In scope:

```text
holding -> instrument -> underlying company -> sector -> geography -> economic driver
```

- direct and indirect exposure;
- one-level ETF constituent snapshots initially;
- point-in-time holdings date, source, coverage, and unresolved residual;
- position weight, Top-N concentration, and HHI;
- evidence-backed economic-driver labels with uncertainty;
- before/after exposure snapshots for a supplied hypothetical position.

Instrument containment and economic-driver classification retain separate provenance. ETF
membership, a shared label, or correlation is not causal evidence.

Out of scope:

- structural-correlation scores;
- factor exposure and factor crowding;
- supplier and catalyst graphs;
- effective independent bets;
- risk-weighted loss aggregation;
- allocation or execution decisions.

Exit criterion: AIE can explain hidden exposure without modifying the Opportunity State or
claiming unknown dependencies are diversification.

The contract and deterministic reference case are documented in
[`chapter-6b-portfolio-exposure.md`](chapter-6b-portfolio-exposure.md). Chapter 6C1 consumes the
verified current and supplied-hypothetical Exposure records without mutating Portfolio State.

### Chapter 6C — Marginal Portfolio Decision

Portfolio Fit is an immutable interaction view inside this chapter, not a separate score engine.
Marginal Allocation owns the decision.

#### Slice 6C1 — New capital and competing alternatives

**Status:** complete; ADR 0016 accepted and implementation merged after exact-head verification and
explicit owner authorization.

Compare explicit before/after states for:

- candidate stock;
- an existing holding;
- the declared core ETF;
- investment cash.

Use standalone underwriting, exposure overlap, basic concentration, ordinal permanent-loss risk,
explicit uncertainty, and disclosed candidate allocation amounts. The minimum decision
vocabulary is:

- `ALLOCATE`;
- `HOLD`;
- `NO_ALLOCATION`.

`ALLOCATE` deploys a named discrete amount to a named alternative. `NO_ALLOCATION` keeps the
evaluated unit as investment cash because no alternative clears the comparison. `HOLD` applies to
an existing-position review when no new unit of capital is being allocated; it is not an alias for
`NO_ALLOCATION`. `REPLACE` enters only in Slice 6C2 after explicit friction.

The core ETF and cash are alternatives, not dedicated engines. The system must preserve the
components and trade-offs rather than emit an uncalibrated portfolio score.

The candidate, one eligible existing holding, the core ETF, and investment cash must use the same
explicit amount and native currency. All six unordered pairs retain standalone case,
permanent-loss class, portfolio effect, and uncertainty. A non-cash alternative receives
`ALLOCATE` only if it defeats all three competitors. Cash dominance, indeterminacy, or a cycle
produces `NO_ALLOCATION`; the caller-supplied amount is never automatically resized.

Every derived Exposure, Fit, and Marginal Allocation state declares `as_of`, knowledge mode,
method version, input fingerprint, missing inputs, conflicts, and assumptions in accordance with
ADR 0006.

The accepted contract and reference case are documented in
[`chapter-6c1-marginal-decision.md`](chapter-6c1-marginal-decision.md). The future API/frontend
boundary is fixed separately in
[`operator-workspace-contract.md`](operator-workspace-contract.md); neither a server nor a
functional frontend enters Chapter 6.

#### Slice 6C2 — Replacement and capital-flow policies

**Status:** complete; ADR 0017 accepted and implementation merged after exact-head verification and
explicit owner authorization.

The accepted slice adds:

- `REPLACE` comparison as one explicit source-to-target proposal rather than a sell optimizer;
- basic tax, spread, fee, liquidity, and switching friction;
- new-capital/PAC-first funding policy;
- `LEGACY_HOLD_ZERO_NEW_CAPITAL`;
- `RUNNER` state without treating recovered cost as free capital;
- owner-defined risk-budget and concentration constraints as hard gates;
- policy-constrained replay of accepted 6C1 decisions without rewriting their fingerprints;
- a Decision Card v2 projection that adds `REPLACE` while keeping Execution `not_evaluated`.

The owner supplies discrete capital and sale amounts. Constraint violations block the proposal;
they never trigger automatic resizing. Unknown friction or liquidity fails safely to `HOLD`.
Runner recovered proceeds remain historical context and never reduce the current market-value
opportunity cost of the retained position.

The accepted contract is documented in
[`chapter-6c2-replacement-policies.md`](chapter-6c2-replacement-policies.md) and
[`ADR 0017`](adr/0017-replacement-and-capital-flow-policies.md).

Exit criterion: AIE can explain the best evaluated use of the next unit of capital, can return no
allocation, and can decide whether one explicit existing position should be replaced after visible
friction and owner policy. It compares discrete, explicit amounts; it does not derive an automatic
Kelly-like size.

Chapter 6 is complete.

### Chapter 7 — Execution MVP

**Purpose:** implement, but never recreate, an approved allocation decision.

**Status:** complete and canonical in `main`; ADR 0018 accepted and PR #24 merged after exact-head
verification and explicit owner authorization.

Minimum outputs:

- `NOW`;
- `STAGED`;
- `WAIT`;
- `INVALIDATED`.

Allocation owns the target capital amount. Execution owns operational validation and deterministic
tranche staging. Market observations, liquidity, spreads, and exact upstream invalidation
conditions may change implementation, not company quality, standalone value, target, or strategic
amount.

Chapter 7 deliberately uses no Market State or timing score. An owner-defined execution policy
supplies quote-age, maximum-spread, and optional maximum-order-notional limits. `STAGED` can only
split the already-approved amount; tranche sums must reproduce that amount exactly. Missing/stale
quotes, excessive spread, unresolved or constrained liquidity, and unknown invalidation evidence
fail safely to `WAIT`. A triggered upstream change condition produces `INVALIDATED`.

The implementation produces an immutable Execution Plan and read-only Execution Card. It does not
connect to a broker or submit orders.

The accepted contract is documented in [`chapter-7-execution-mvp.md`](chapter-7-execution-mvp.md)
and [`ADR 0018`](adr/0018-point-in-time-execution-mvp.md).

Out of scope initially:

- automated order submission;
- a market-timing or regime score;
- venue and order-type selection;
- inferred participation-rate or liquidity scheduling;
- all-in/all-out regime rules;
- automatic changes to the strategic allocation.

Exit criterion: one canonically replayed `ALLOCATE` or `REPLACE` decision can produce a point-in-
time, content-addressed `NOW`, `STAGED`, `WAIT`, or `INVALIDATED` Execution Plan without changing
any upstream capital decision.

### Chapter 8 — Decision-level Learning MVP

**Purpose:** create trustworthy ex-post evidence about an AIE decision before claiming that the
system has learned an investment edge.

**Status:** complete and canonical in `main`; ADR 0019 accepted and PR #25 merged. The owner
explicitly confirmed ADR 0019 acceptance on 2026-09-01.

The first slice opens Learning only from canonically replayed Chapter 7 `NOW` or `STAGED` plans and
preserves three ordered boundaries:

```text
T0 = capital decision
T1 = Execution Plan
T2 = Learning evaluation
T2 >= T1 >= T0
```

Because Chapter 7 has no broker-fill lifecycle, Learning explicitly distinguishes decision-level
observed price return from realized account P&L. It records
`account_pnl_status = not_measured_no_fill_data` and does not call a quote or plan a fill.

Minimum decision-level outputs:

- target price return from the exact T0 reference price;
- same-currency benchmark price return;
- transparent target-minus-benchmark excess return;
- maximum drawdown over the explicitly supplied target-price path, without forward filling;
- for `REPLACE`, source-position price return and target-minus-source counterfactual;
- thesis outcome `intact`, `invalidated`, or `unresolved` using only exact upstream change
  conditions;
- categorical scenario realization against the preserved T0 bear/base/bull range when such a
  range belongs to the selected candidate;
- T0/T1/T2 references, source fingerprints, assumptions, conflicts, and missing data.

The first slice deliberately does **not** claim realized brokerage P&L, total shareholder return,
Sharpe, Sortino, Information Ratio, factor alpha, win rate, or model skill. It also has no automatic
feedback authority: a Learning result cannot resize capital, rewrite owner policy, change
Underwriting gates, alter Execution thresholds, retrain a model, or promote a deferred capability.

The accepted contract is documented in [`chapter-8-learning-mvp.md`](chapter-8-learning-mvp.md)
and [`ADR 0019`](adr/0019-decision-level-learning-mvp.md).

Exit criterion: an executable point-in-time decision can be replayed into a content-addressed T2
Learning record that measures transparent decision-level outcomes without hindsight, implicit FX,
fake fill assumptions, aggregate skill claims, or automatic upstream feedback.

### Chapter 9A — Typed product API boundary

**Purpose:** make the accepted analytical pipeline callable by product adapters without moving
financial logic into transport or UI code.

**Status:** complete and canonical in `main`; ADR 0020 accepted and PR #27 merged after exact-head
review and explicit owner authorization.

The contract is `aie-api-v1`. It provides strict typed request/response models and a
transport-neutral facade in the `interfaces` layer for the accepted Chapter 6 through Chapter 8
product-critical use cases. Application services remain the canonical owners and are injected into
the facade.

Required behavior:

- API invocation and direct application invocation produce exactly equal canonical records;
- immutable upstream records remain subject to their existing canonical replay and tamper checks;
- requests reject unknown client fields rather than accepting shadow calculations;
- request/response records survive JSON-mode round trips;
- interfaces may import application/domain contracts, but application/domain may not import the API;
- no infrastructure provider is created or imported by the product API.

Out of scope:

- FastAPI, Flask, Starlette, ASGI/HTTP routes, or any network server;
- authentication, authorization, CORS, sessions, or rate limiting;
- whole-pipeline persistence and ID-based retrieval;
- frontend/operator workspace implementation;
- live provider composition;
- broker connectivity;
- any new financial metric, score, allocation, sizing, replacement search, timing rule, or Learning
  feedback mechanism.

The accepted contract is documented in [`chapter-9a-api-boundary.md`](chapter-9a-api-boundary.md)
and [`ADR 0020`](adr/0020-typed-transport-neutral-api-boundary.md).

Exit criterion: deterministic Chapter 6/7/8 reference packages pass through `aie-api-v1` with
exactly the same canonical outputs and blocking integrity behavior as direct application calls,
without adding a transport framework or financial logic to the interface layer.

### Chapter 9B — Immutable product persistence

**Purpose:** persist and retrieve immutable product records so prospective use does not depend on
large stateless payloads and Learning case creation can retain creation evidence.

**Status:** complete and canonical in `main`; ADR 0021 accepted and the integrated Chapter 9 head
merged through PR #30 after review and verification.

The slice adds:

- a storage-agnostic application persistence port;
- an explicit registry of 15 admitted canonical product record kinds;
- deterministic canonical JSON, SHA-256 and content-addressed UUIDv5 storage identities;
- a first local timezone-aware `stored_at` timestamp preserved across idempotent re-append;
- verification of envelope, schema, payload hash, storage identity, concrete record type, and
  canonical JSON on load;
- append-only semantics and explicit migration failure;
- a file-backed SQLite reference adapter with update/delete guards and no read-side creation of a
  missing store.

Storage integrity does not replace canonical financial replay. `stored_at` is local operational
audit evidence, not cryptographic notarization of when market information or a human decision first
existed. SQLite is a reference adapter, not the production database decision.

The accepted contract is documented in
[`chapter-9b-immutable-product-persistence.md`](chapter-9b-immutable-product-persistence.md) and
[`ADR 0021`](adr/0021-immutable-product-record-persistence.md).

Exit criterion: admitted immutable product records survive process restarts and can be retrieved by
content-addressed storage ID with corruption and schema drift failing closed, while their canonical
application owners retain all financial verification authority.

### Chapter 9C — Operator workspace MVP

**Purpose:** provide the first functional human-facing workflow over accepted APIs and persisted
records.

**Status:** complete and canonical in `main`; ADR 0022 accepted and the integrated Chapter 9 head
merged through PR #30 after review and verification.

The workspace remains an interface only. The first slice provides:

- a read-only CLI composition over an already initialized Chapter 9B store;
- a local browser navigator for storage-verified records and exact canonical JSON;
- existing Decision/Execution Card projections without recalculation;
- an explicit Chapter 9A operation registry for optional injected write composition;
- persistence of exact canonical `aie-api-v1` outputs through Chapter 9B;
- loopback-only standard-library WSGI serving with bounded request bodies;
- a server-generated local anti-CSRF token checked before browser write dispatch.

Read-only mode rejects mutation before parsing a client API payload. Unknown operation names do not
dynamically dispatch. A multi-record `MarginalDecisionPackage` is appended idempotently record by
record; Chapter 9C does not claim cross-record transactional atomicity. No remote authentication,
rich frontend framework, broker/fill lifecycle, financial scoring/sizing/timing, optimizer,
aggregate Learning statistics, or automatic capital feedback enters the slice.

The accepted contract is documented in
[`chapter-9c-operator-workspace-mvp.md`](chapter-9c-operator-workspace-mvp.md) and
[`ADR 0022`](adr/0022-local-operator-workspace-mvp.md).

Exit criterion: an operator can inspect real persisted AIE records locally and, when a real API/store
composition is explicitly injected, execute only accepted typed operations whose exact canonical
outputs are persisted, without shifting decision ownership into the UI.

Chapter 9 is complete.

### Chapter 10 — Prospective Operation & Product Composition MVP

**Purpose:** operate the accepted analytical and product slices as one explicit local prospective
workflow without creating another financial engine.

**Status:** complete under accepted ADR 0023 and integrated into `main` through PR #31 on
2026-09-03.

The slice adds:

- one `local-product-runtime-v1` outer composition root over accepted application owners;
- a separate strict `aie-intake-v1` boundary for canonical Causal Analysis and Opportunity State;
- exact persistence of successful upstream canonical results through Chapter 9B;
- explicit initialization and fail-closed opening of the local evidence and product stores;
- conservative exact-byte local evidence intake with availability observed only at ingestion;
- a write-enabled Chapter 9C workspace backed by the full accepted `aie-api-v1` service graph.

Chapter 10 adds no source discovery, extraction authority, financial default, score, sizing method,
Market State, automatic Learning feedback, broker lifecycle, remote authentication, or production
database choice.

The accepted contract is documented in
[`chapter-10-prospective-operation-mvp.md`](chapter-10-prospective-operation-mvp.md) and
[`ADR 0023`](adr/0023-prospective-local-product-composition.md).

Exit criterion: a deterministic integration crosses real evidence storage, canonical Causal and
Underwriting intake, immutable product persistence, and configured downstream API/workspace output;
all stores fail closed outside explicit initialization, all repository checks pass on the exact
review head, and the owner explicitly accepts ADR 0023.

Chapter 10 is complete.

### Chapter 11 — Point-in-Time SEC Fundamental Data Foundation

**Purpose:** replace manual SEC filing selection and fundamental-fact transcription with a
replayable, accession-bound source-to-fact path without granting a parser decision authority.

**Status:** implementation complete under accepted ADR 0024 through PRs #32–#34;
CLOSED / CANONICAL / FUNCTIONING upon final merge and green CI on main. See the chapter closure
record for validation evidence and accepted non-blockers.

The chapter is divided into three acceptance slices:

1. **11A — catalog and acquisition manifest:** discover admitted filing references by CIK, retain
   catalog fingerprints and explicit older-history gaps, then acquire exact complete submissions;
2. **11B — shadow XBRL extraction:** retain concept, context, unit, period, dimensions, locator, and
   extraction version without creating canonical financial truth;
3. **11C — canonical fact admission:** map and reconcile a narrow fact vocabulary before the
   existing Underwriting owner may consume it.

The proprietary AIE layer owns point-in-time identity, semantic mapping, reconciliation, versioning,
and source-to-decision lineage. It does not reimplement the XBRL standard processor and does not
silently treat current aggregate Company Facts data as historical truth.

The accepted contract is documented in
[`chapter-11-sec-fundamental-data-foundation.md`](chapter-11-sec-fundamental-data-foundation.md) and
[`ADR 0024`](adr/0024-point-in-time-sec-fundamental-data-foundation.md).

Exit criterion: a declared SEC universe has an immutable expected-source manifest, admitted filing
versions are captured additively, and a narrow reconciled fact set can be regenerated from exact
source bytes with complete point-in-time lineage and fail-closed ambiguity.

### Chapter 12 — Local decision-first product frontend

**Status:** approved on 2026-09-10 under accepted ADR 0025; canonical and functioning
upon merge and green CI on `main`.

Owner-requested interface slice: Home, Analysis, contextual
Evidence, factual Portfolio and marginal Decision with exact linked Fits. This is an
interface capability (`CORE NOW`), not a new financial context or method.
The existing operator workspace remains available. See
[`Chapter 12`](chapter-12-product-frontend.md) and the
[`UX review`](frontend-ux-review.md).

Exit criteria: canonical output/contract tests, explicit failure states, local-only
security, usable evidence-to-decision navigation and prospective usability acceptance.
JSON dossier intake is transitional. Guided authoring, natural-language interpretation,
advanced graphs and additional dashboards remain subsequent UI work; they do not
promote deferred analytical capabilities or supersede the data-foundation priorities.

## Portfolio concepts that remain policies or state

The following do not receive independent engines or chapters:

| Concept | Canonical representation | Owner |
| --- | --- | --- |
| Competition for Capital | Requirement to evaluate explicit alternatives | Marginal Allocation |
| ETF and cash hurdle | Competing alternatives | Marginal Allocation |
| No allocation | Valid decision outcome | Marginal Allocation |
| Replacement | After-friction comparison policy | Marginal Allocation |
| PAC / new capital first | Funding policy | Marginal Allocation |
| Emergency reserve | Non-investable cash role | Portfolio State |
| Strategic/opportunistic/unallocated cash | Cash-role state | Portfolio State |
| Legacy holding | Holding state plus zero-new-capital policy | Portfolio Decision |
| Runner | Holding state and monitoring policy | Portfolio Decision |
| Concentrated compounder profile | Explicit risk-policy configuration | Marginal Allocation |

## Deferred capability register

Deferred capabilities remain visible and may graduate only after the listed trigger is observed.

| Capability | Current class | Prerequisite | Graduation trigger | Future owner |
| --- | --- | --- | --- | --- |
| Automated Insight Discovery | `DEFER` | Expected-source universe and validated extraction | Manual discovery throughput or coverage is a measured bottleneck | Understand |
| Opportunity archetypes | `EXPERIMENTAL` | Sufficient cases with common evidence failures | Archetype metadata demonstrably improves completeness or monitoring | Underwriting configuration |
| Special Situations discovery | `EXPERIMENTAL` | Reliable corporate-action evidence path | Prospective cases show decision value outside causal secular discovery | Understand adapter |
| Multi-level fund look-through | `DEFER` | Real portfolio contains material fund-of-fund exposure | One-level unresolved residual changes a decision materially | Portfolio Exposure |
| Supplier dependencies | `DEFER` | Evidence-backed dependency data | Sector/driver view misses a documented material concentration | Portfolio Exposure |
| Catalyst clustering | `DEFER` | Versioned catalyst data | Common event timing changes a real portfolio decision | Portfolio Exposure |
| Factor exposure/crowding | `DEFER` | Point-in-time factor definitions and histories | Simple exposure views repeatedly miss documented common risk | Portfolio Exposure/Fit |
| Dynamic correlation | `DEFER` | Stable return history and validation baseline | Static/ordinal dependencies produce measured decision errors | Portfolio Fit |
| Effective independent bets | `DEFER` | Admitted correlation/dependency model | Name/driver concentration is demonstrably insufficient | Portfolio Fit metric |
| Tail-risk aggregation | `DEFER` | Calibrated loss inputs | Ordinal permanent-loss classes cannot distinguish material choices | Portfolio Fit |
| Automated sizing | `REJECT` as V1 default | Calibrated distributions and prospective validation | Explicit discrete sizes repeatedly fail against a validated method | Marginal Allocation policy |
| Advanced tax-lot optimization | `DEFER` | Complete tax lots and verified adapter | Basic tax friction causes material avoidable loss | Marginal Allocation policy |
| Market State engine | `DEFER` | Prospective signals and execution baseline | A simple execution policy shows persistent timing failure | Execution input |
| Factor-adjusted alpha | `DEFER` | Adequate decision sample and factor histories | Basic benchmark attribution is statistically insufficient | Learning |
| Aggregate risk-adjusted Learning metrics | `DEFER` | Prospective decision sample and documented minimum-sample policy | Decision-level outcomes are insufficient for model-skill evaluation | Learning |
| Automatic Learning feedback | `REJECT` as V1 default | Prospective calibration, governance, rollback, and causally defensible update rules | Manual review of accumulated Learning records shows a reproducible benefit from a bounded update rule | Learning/application policy |
| Monte Carlo/Bayesian optimizer | `REJECT` as V1 default | Calibrated distributions, covariance, and benchmark | Simpler marginal comparison has a measured, reproducible failure | Experimental allocation adapter |

No deferred capability may become an active default solely because synthetic tests pass.

## Post-Chapter 10 priority order

Priority states sequencing intent only. It does not override a capability's prerequisite,
graduation trigger, classification, or ADR gate.

| Priority | Capabilities | Admission condition |
| --- | --- | --- |
| `P0 — data foundation` | SEC catalog/lifecycle, XBRL normalization, market prices, instrument master, scheduling and coverage monitoring | Required for repeatable point-in-time operation; each provider remains separately admitted |
| `P1 — understand throughput` | Automated Insight Discovery, Special Situations discovery, Opportunity archetypes | Expected-source universe, validated extraction, and enough real cases to measure completeness |
| `P2 — concrete portfolio evidence` | Supplier dependencies, catalyst clustering, multi-level fund look-through, advanced tax-lot optimization | A documented real holding or decision is materially affected by the missing evidence |
| `P3 — contextual risk and timing` | Market State, factor exposure/crowding, dynamic correlation, effective independent bets, tail-risk aggregation | Prospective decisions expose repeatable failures of the simpler execution or exposure baseline |
| `P4 — aggregate learning` | Factor-adjusted alpha, aggregate risk-adjusted Learning metrics | Adequate prospective sample and an approved minimum-sample policy |
| `Not a V1 default` | Automated sizing, automatic Learning feedback, Monte Carlo/Bayesian optimizer | Remain rejected until their stronger calibration, governance, and measured-failure gates are met |

## Standard decision card

Every active capital decision should be renderable as:

```text
DECISION
ALLOCATE amount / HOLD / REPLACE / NO ALLOCATION

WHY
Three to five material drivers

BEST ALTERNATIVE
Core ETF / Cash / Existing Holding

MAIN RISKS AND UNKNOWNS

CONFIDENCE
Including calibration status

WHAT WOULD CHANGE THE DECISION

PORTFOLIO EFFECT
Before/after weight, concentration, driver overlap, tax and cost deltas

EXECUTION
NOW / STAGED / WAIT / INVALIDATED

AS OF AND INPUT FINGERPRINT
```

Chapter 6 Decision Cards remain immutable and show Execution as `not_evaluated`. Chapter 7 adds a
separate read-only Execution Card over a verified Execution Plan rather than mutating the accepted
Chapter 6 projection. Chapter 8 Learning records remain a separate downstream audit/evaluation
surface; none of these projections may hide uncertainty behind a synthetic score.
