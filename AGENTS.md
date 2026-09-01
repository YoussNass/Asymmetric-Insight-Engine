# Agent Operating Contract

These instructions apply to every automated contributor working in this repository.

## Source of truth

- The repository and its accepted pull requests are the canonical implementation record.
- Read the system constitution and relevant ADRs before changing architecture.
- Never infer that a discussed feature is implemented; verify the code and tests.

## Architecture boundaries

- `domain` must not import from `application`, `infrastructure`, or `interfaces`.
- `application` may depend on `domain`, never the reverse.
- External services, databases, AI models, and data vendors belong behind infrastructure ports.
- User interfaces must call application use cases rather than contain financial logic.
- Shared facts must have one canonical owner; do not duplicate scoring across engines.
- The Temporal shared kernel owns `KnowledgeMode` and decision-time filtering for every context.
- Causal Alpha owns typed change-to-driver-to-actor-to-beneficiary paths and ends at
  `ready_for_underwriting`, never an investment or allocation decision.
- Underwriting owns standalone opportunity state; Portfolio may consume but never recreate or
  mutate it.
- Underwriting consumes one `ready_for_underwriting` causal analysis for the same candidate and
  canonical knowledge boundary; it must not accept portfolio, market-regime, sizing, tax, or
  execution inputs.
- Underwriting reported facts require direct candidate-source provenance; market observations
  require candidate market-data provenance. Analyst-adjusted facts must remain labelled,
  explained, and claim-backed; derived facts must reproduce from explicit inputs under an admitted
  versioned deterministic formula.
- Monetary facts and scenarios declare their native ISO currency. Duration comparisons require a
  matching economic period scope, and no formula may perform or imply an undeclared FX conversion.
- A `ready_for_portfolio_review` state must preserve all eight underwriting dimensions, all six
  categorical gates, bear/base/bull per-share valuation bridges, scenario horizon and observation
  date, current capital-structure anchors, catalysts, risks, assumptions, conflicts, missing data,
  and invalidations. It is never an allocation instruction.
- Do not assign scenario probabilities, forecast distributions, or active decision weights unless
  the producing method is explicitly versioned, empirically calibrated, documented, and approved.
- Keep instrument containment, economic-causal dependency, portfolio fit, marginal allocation,
  execution, and ex-post learning as separate contracts.
- Portfolio State is factual data/state only. It must not import Causal Alpha or Underwriting or
  contain exposure, fit, score, sizing, allocation, market-regime, or execution authority.
- Portfolio accounts own basic tax metadata; positions and cash reference the canonical account
  rather than duplicating account facts.
- Keep representable holdings, instruments eligible for new capital, and the declared benchmark
  as three separate concepts. Presence in a portfolio never grants eligibility.
- Portfolio money remains in native currency. Without an explicit point-in-time FX contract,
  expose currency-grouped subtotals and never a synthetic cross-currency total.
- Emergency reserve cash is non-investable state. Other cash roles remain explicit and cannot be
  silently reclassified by a later analytical contract.
- Content-address every canonical Portfolio State and retain its knowledge boundary, benchmark,
  method version, and input fingerprint in the T0 audit envelope; the envelope is not a capital
  decision.
- Rebuild and verify a deserialized Portfolio State before downstream use; never trust a stored
  fingerprint or generated identifier without canonical replay.
- Portfolio Exposure must verify Portfolio State first and retain only its immutable reference and
  fingerprint; it must never mutate State or recursively redefine positions, cash, or eligibility.
- Initial ETF look-through is one level only. Preserve holdings date, source evidence, coverage,
  and unresolved residual; missing constituent weight is unknown, never diversification.
- Keep ETF containment evidence separate from sector, geography, and economic-driver claims.
  Instrument membership and driver tags are descriptive and must not be represented as causal
  edges.
- Exposure weights, Top-N, and HHI remain inside native-currency books. Without admitted FX, never
  publish a cross-currency concentration metric. Bound HHI when company identity is unresolved.
- Economic-driver tags may overlap and are non-additive. Uncalibrated classification confidence
  cannot gate, rank, score, size, or allocate.
- A hypothetical exposure amount is an explicit external input, not a sizing result or allocation
  instruction. It must reference a canonical policy-eligible instrument and leave Portfolio State
  unchanged.
- Chapter 6C1 must replay Opportunity State, Portfolio State, current Exposure, and each supplied
  hypothetical Exposure before use. All inputs and outputs share one exact knowledge boundary.
- Portfolio Fit is descriptive interaction state only. It may expose native-currency before/after
  value, HHI bounds, and changed exposure components; it must not contain preference, score,
  sizing, allocation, replacement, timing, or execution authority.
- Every marginal new-capital decision must compare exactly the candidate equity, one eligible
  existing listed-equity holding, the policy-selected core ETF, and investment cash using the same
  explicit positive amount and native currency. Funding cash must be known, investable, and
  sufficient; emergency reserve is never eligible.
- The prospective candidate remains outside factual Portfolio State and must bind to the verified
  Opportunity company, market-observed reference-price fact, price date, native currency, and
  valuation-scenario anchors. Portfolio may reference but never rewrite its Underwriting risks.
- All six unordered alternative pairs must preserve standalone case, ordinal permanent loss,
  portfolio effect, uncertainty, rationale, and missing data. Components are never averaged into a
  hidden utility score; permanent-loss direction must agree with the disclosed ordinal classes.
- `ALLOCATE` requires one non-cash alternative to defeat all three competitors. Cash dominance,
  indeterminacy, ties, or cycles return `NO_ALLOCATION` and preserve the exact unit as investment
  cash. The use case never derives or changes the supplied amount.
- `HOLD` is a separate no-new-capital review with no amount, sale, replacement, timing, or order
  authority. `REPLACE` belongs to 6C2; Execution belongs to Chapter 7.
- Chapter 6C2 must consume canonical 6C1 records additively. Owner policy may block an otherwise
  preferred alternative but must never rewrite the 6C1 decision, Fits, comparisons, or fingerprint.
- Owner maximum-capital and concentration/risk constraints are hard gates only. They must not be
  interpreted as target weights and must never automatically resize a caller-supplied capital or
  replacement amount until an explicitly calibrated sizing method is separately admitted.
- `LEGACY_HOLD_ZERO_NEW_CAPITAL` permits an existing factual holding to remain while blocking
  incremental capital; it does not imply a sale, replacement, or failed thesis.
- `RUNNER` may retain recovered proceeds as historical context, but current market value remains
  the opportunity cost of the remaining position. Recovered historical proceeds must never be
  subtracted from current capital-at-risk or replacement arithmetic as “house money.”
- Policy-constrained new-capital decisions must keep investment cash eligible and reuse the
  accepted 6C1 pairwise evidence among remaining alternatives. Policy filtering must not introduce
  rescoring, hidden thresholds, or a second utility model.
- A Chapter 6C2 replacement evaluates one explicit existing source, one explicit target, and one
  caller-supplied positive sale amount. It must not search the portfolio for an optimal sale,
  derive position size, or perform implicit FX.
- Replacement friction keeps tax, fee, and spread as separate explicit T0 estimates and liquidity
  as a separate state. Unknown monetary friction or unknown liquidity must fail safely to `HOLD`;
  aggregate cost basis alone does not justify tax-lot optimization.
- `NEW_CAPITAL_FIRST` must prevent an unnecessary replacement sale when current investable cash in
  the same currency can fund the net target amount. Emergency reserve remains excluded.
- `REPLACE` requires the explicit target to outclass the source before and after visible friction
  and to pass every owner-policy gate. Failure returns `HOLD` with an inspectable decision basis.
- Because Chapter 6B has no canonical hypothetical-sale scenario, any temporary 6C2
  after-replacement constraint observation must remain an explicit fingerprinted input and must
  not be represented as a derived Chapter 6B Exposure state.
- Chapter 7 Execution is downstream of Portfolio Decision. Its domain must not import Portfolio,
  Underwriting, or Causal Alpha; only the application layer may canonically replay Chapter 6 inputs
  and translate an approved instruction into Execution.
- Execution accepts only a verified Chapter 6 `ALLOCATE` or `REPLACE`. `NO_ALLOCATION` and `HOLD`
  are not executable instructions, and Execution must never change the approved target, strategic
  amount, or replacement source-sale amount.
- Execution owns a separate T1 knowledge boundary with `T1 >= T0` and the same `KnowledgeMode` as
  the source capital decision. Every quote and invalidation observation must pass the Temporal
  shared-kernel boundary; future or not-yet-recorded data is rejected.
- Execution may evaluate only the exact upstream `change_conditions`. A triggered condition yields
  `INVALIDATED`; a missing or unknown assessment yields `WAIT`; extra invented invalidation
  conditions are rejected.
- Chapter 7 uses the conservative priority `INVALIDATED > WAIT > STAGED > NOW`. Missing/stale
  quotes, excessive bid/ask spread, or liquidity that is unknown or constrained fail safely to
  `WAIT`; they must not be converted into an inferred timing or liquidity score.
- `STAGED` may arise only from an explicit owner maximum-single-order notional. Tranches may split
  an approved trade leg but their sum must reproduce that approved leg exactly; staging is never a
  strategic resize.
- Chapter 7 creates immutable Execution Plans only. Broker connection, order submission, venue or
  order-type selection, dynamic slippage logic, and Market State/regime scoring remain out of
  scope until separately admitted by an accepted ADR and explicit owner authorization.
- Chapter 8 Learning is downstream of Execution. Its domain must not import Portfolio,
  Underwriting, Execution, or Causal Alpha; only the application layer may replay upstream records
  and freeze immutable T0/T1 references into a Learning case.
- Learning opens active decision-level evaluation only from canonically replayed `NOW` or `STAGED`
  Execution Plans. A plan is not a fill: observed price return must never be labelled realized
  account P&L without a separately admitted broker/fill lifecycle.
- Learning preserves `T2 >= T1 >= T0` with one `KnowledgeMode`. Later price and thesis observations
  must pass the shared Temporal kernel; future, unavailable, or not-yet-recorded observations are
  rejected.
- Learning benchmark and target arithmetic is same-currency only. No implicit FX, total-return
  assumption, dividend reconstruction, or forward fill is permitted in the MVP.
- Learning may re-evaluate only exact upstream `change_conditions`; missing/unknown conditions stay
  unresolved and hindsight-only invalidation rules are rejected.
- Scenario realization is categorical against the preserved T0 bear/base/bull range. It is not a
  probability, score, forecast-calibration claim, or evidence of model skill by itself.
- Learning outputs have no automatic upstream authority: they must not resize capital, rewrite
  Underwriting gates, owner policy, pairwise logic or Execution thresholds, retrain a model, or
  promote a deferred capability without a later accepted ADR and prospective validation.
- Decision Card and future API/frontend adapters are projections over application results. They
  must verify canonical references and contain no financial logic. Chapter 6 Decision Cards report
  Execution as `not_evaluated`; Decision Card schema-version changes must not silently reuse an
  older projection identity, and policy-blocked alternatives cannot be presented as eligible best
  alternatives. Chapter 7 adds a separate read-only Execution Card rather than mutating accepted
  Chapter 6 Decision Card records. Learning remains a separate downstream audit/evaluation record.

## Epistemic and financial safety

- Preserve `effective_at`, `available_at`, `recorded_at`, `as_of`, and `knowledge_mode`
  semantics.
- Never make future data visible to a historical calculation.
- Never treat evidence ingested after `as_of` as present in a live-system replay.
- Never invent missing values or silently forward-fill event data.
- Never describe locally known source versions as universe completeness without an authoritative
  expected-source manifest.
- Keep observed data, statistical results, inferences, hypotheses, and judgements distinct.
- Back every causal node with claims; a real-world-change node requires an observed or statistical
  signal claim, while a causal edge requires inferential or hypothesis support.
- Do not treat a label, correlation, issuer mention, or instrument containment as causal proof;
  every causal edge needs an explicit mechanism and inferential or hypothesis claim support.
- Every material claim needs provenance, confidence, and explicit invalidation conditions.
- Keep confidence calibration status visible; uncalibrated annotations are not gates, ranking
  inputs, or probabilities.
- Do not introduce active default weights, thresholds, scores, or sizing rules without an
  explicit method version, calibration status, component output, and documented evidence.
- Missing correlation or classification evidence is unknown, never zero risk or diversification.
- Never add live brokerage execution without an approved ADR and explicit user authorization.
- Never commit credentials, personal portfolio exports, licensed datasets, or vendor payloads.
- Provider tests and CI use deterministic fixtures; live provider access must be an explicit outer
  interface operation.

## Complexity budget

- Read `docs/complexity-budget.md` and `docs/roadmap.md` before proposing a new analytical
  capability or changing the delivery sequence.
- Classify every new concept as a bounded context, capability, policy, data/state, metric, or
  experimental extension before naming a module or engine.
- Assign `CORE NOW`, `SIMPLE POLICY`, `EXPERIMENTAL`, `DEFER`, or `REJECT` and document the owning
  decision, data requirements, validation method, explanation, maintenance cost, and timing.
- Prefer the simplest version that can be measured. Add sophistication only after a prospective
  failure is recorded and the more complex method has an approved validation and rollback plan.
- Experimental outputs cannot become active gates, rankings, sizes, allocations, or execution
  defaults. Missing inputs remain unknown.
- A named rule does not justify a new engine. Competition for Capital, ETF/cash hurdles,
  replacement, PAC, cash roles, Legacy Holding, and Runner are policies or state inside their
  canonical owner unless an ADR proves otherwise.
- Preserve deferred capabilities and their graduation criteria in the roadmap rather than
  implementing them early or silently deleting them.
- Do not change the Version 1 investable universe implicitly. ETF eligibility requires its own
  accepted ADR and an explicit Constitution decision before implementation.

## Change workflow

- Work on an `agent/*` branch and open a draft pull request.
- Do not push directly to `main` or merge without explicit user approval.
- Keep commits focused and describe the intent, not only the files changed.
- Add or update tests for every behavioral change.
- Update documentation when public contracts or architecture change.

## Required checks

Run before publication:

```bash
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
uv run asymmetric-engine doctor
```

Container changes must also pass:

```bash
docker build --tag asymmetric-insight-engine:check .
docker run --rm asymmetric-insight-engine:check
```

If a local check cannot run, report the exact blocker and rely only on the corresponding green
CI job; do not claim local success.
