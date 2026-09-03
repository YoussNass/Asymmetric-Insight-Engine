# Asymmetric Insight Engine

An evidence-first, point-in-time-safe system for discovering causal investment opportunities,
underwriting their asymmetric payoff, and allocating capital coherently.

## Mission

The engine is designed to answer:

> Which real-world change is creating economic consequences that expectations and prices have
> not yet incorporated, which listed companies can capture that value per share, and what is the
> best marginal use of available capital?

It is a decision-support system, not an infallible forecasting machine and not an automated
brokerage client.

## Canonical pipeline

```text
Evidence -> Insight -> Causal Alpha -> Underwriting -> Opportunity State
         -> Portfolio Decision -> Execution Plan -> Monitoring -> Learning
```

Market and regime state may later inform opportunity assessment and execution without replacing
the causal thesis or the accepted Portfolio Decision ownership boundaries.

For product communication and incremental delivery, the same mission is summarized as:

```text
UNDERSTAND -> UNDERWRITE -> ALLOCATE -> EXECUTE -> LEARN
```

This is a user-facing decision flow, not a requirement for five services or five bounded
contexts. See the [`AIE delivery roadmap`](docs/roadmap.md).

## Non-negotiable principles

- Every decision declares whether it is a historical reconstruction or a live-system replay and
  is evaluated against the corresponding `as_of` knowledge boundary.
- Observation, statistical result, inference, hypothesis, and qualitative judgement stay distinct.
- Missing or conflicting evidence remains visible.
- Eligibility gates precede ranking; there is no universal magic score.
- Company quality, thesis quality, investment quality, portfolio fit, allocation, execution, and
  ex-post learning remain separate concepts.
- Explicit owner constraints are gates, not automatic sizing formulas.
- AI-assisted extraction may propose claims, but calculations and validations remain deterministic.
- No live order submission is included in version 1.

## Delivery discipline

New capabilities must pass the seven admission gates in the
[`Complexity Budget`](docs/complexity-budget.md). Named concepts become capabilities, policies,
state, or metrics inside an existing owner unless distinct language, invariants, and lifecycle
justify a bounded context.

The accepted roadmap implements the minimum complete decision flow first. Advanced Portfolio,
Market State, attribution, and optimization capabilities remain in a deferred register with
explicit graduation criteria; they are preserved without becoming premature active scope.

## Current status

Chapters 2 through 8 and Chapter 9A are complete in `main`. Chapter 5 provides standalone Investment
Underwriting: normalized reported, market-observed, and analyst-adjusted facts with native
currency and fiscal-period scope; versioned deterministic formulas; eight independent analytical
dimensions; categorical eligibility gates; dated bear/base/bull valuation bridges;
probability-free payoff arithmetic; and a deterministic `ready_for_portfolio_review` hand-off.

The reference case continues the Chapter 4 Micron hypothesis and uses selected reported values
from Micron's fiscal 2025 Form 10-K. It keeps diluted weighted-average shares used for EPS distinct
from fiscal-year-end shares outstanding used as the current per-share valuation anchor. Short
source excerpts and all market-price and valuation assumptions are deterministic test fixtures.
The case proves the contract; it is not an investment recommendation, a complete Micron analysis,
or evidence that the security is attractive. See
[`Chapter 5: Standalone investment underwriting`](docs/chapter-5-investment-underwriting.md).

Chapter 6A adds factual, immutable Portfolio State: canonical accounts and instruments, long-only
positions, native-currency prices and cash roles, basic account tax and aggregate cost-basis
metadata, the versioned ETF allow-list and benchmark, and a deterministic T0 fingerprint and audit
envelope. It deliberately contains no exposure, fit, score, sizing, allocation, timing, or
execution logic. See [`Chapter 6A: Factual Portfolio State`](docs/chapter-6a-portfolio-state.md)
and accepted [`ADR 0014`](docs/adr/0014-factual-portfolio-state-and-t0-snapshot.md).

Chapter 6B derives one-level direct and ETF look-through exposure, keeps currency books separate,
exposes unresolved weight and HHI bounds, and produces descriptive before/after views only for an
amount supplied from outside the capability. See
[`Chapter 6B: Minimal Portfolio Exposure`](docs/chapter-6b-portfolio-exposure.md) and accepted
[`ADR 0015`](docs/adr/0015-minimal-point-in-time-portfolio-exposure.md).

Chapter 6C1 is canonical under accepted
[`ADR 0016`](docs/adr/0016-explicit-marginal-capital-decision.md). It verifies the complete
Underwriting/State/Exposure hand-off, compares the candidate, one eligible incumbent, the core ETF,
and investment cash using the same explicit capital unit, derives descriptive Portfolio Fits, and
emits `ALLOCATE` only under complete pairwise dominance. Cash dominance, indeterminacy, ties, or a
cycle return `NO_ALLOCATION`; a separate `HOLD` record carries no new capital. The Decision Card is
a read-only projection and cannot emit Execution state. See
[`Chapter 6C1: Explicit marginal capital decision`](docs/chapter-6c1-marginal-decision.md).

Chapter 6C2 is canonical under accepted
[`ADR 0017`](docs/adr/0017-replacement-and-capital-flow-policies.md). It adds explicit owner
capital/concentration gates, `LEGACY_HOLD_ZERO_NEW_CAPITAL`, `RUNNER` without house-money
accounting, policy-constrained replay of accepted 6C1 decisions, `NEW_CAPITAL_FIRST`, and one
explicit source-to-target `REPLACE` decision after visible tax, fee, spread, and liquidity
friction. Constraint breaches never resize an amount automatically; missing friction or liquidity
fails safely to `HOLD`; recovered Runner proceeds never reduce the current market-value opportunity
cost. See
[`Chapter 6C2: Replacement and capital-flow policies`](docs/chapter-6c2-replacement-policies.md)
and the [`minimum operator workspace contract`](docs/operator-workspace-contract.md).

Chapter 7 is canonical under accepted
[`ADR 0018`](docs/adr/0018-point-in-time-execution-mvp.md). It introduces a separate Execution
bounded context that consumes only canonically replayed `ALLOCATE` or `REPLACE` decisions,
preserves target and approved amounts exactly, evaluates a later point-in-time execution boundary,
and emits only `NOW`, `STAGED`, `WAIT`, or `INVALIDATED`. Bid/ask spread, quote freshness,
liquidity, upstream invalidation state, and explicit owner staging limits are inspectable inputs;
conflicting execution input is blocking. Staging may split an approved amount but may never resize
the strategic allocation. The slice creates immutable plans and a read-only Execution Card only;
it does not submit broker orders or introduce a market-timing or regime score. See
[`Chapter 7: Point-in-time Execution MVP`](docs/chapter-7-execution-mvp.md).

Chapter 8 is canonical under accepted
[`ADR 0019`](docs/adr/0019-decision-level-learning-mvp.md). It adds a separate downstream Learning
bounded context that opens only from canonically replayed `NOW` or `STAGED` Execution Plans,
preserves ordered T0/T1/T2 knowledge boundaries, and compares explicit later price and thesis
observations with the immutable decision record. The MVP reports price-only decision return,
same-currency benchmark excess return, observed-path drawdown, replacement source counterfactual,
exact upstream thesis-condition outcomes, and categorical scenario realization without claiming
broker P&L, total shareholder return, calibrated probabilities, or investment skill. See
[`Chapter 8: Decision-level Learning MVP`](docs/chapter-8-learning-mvp.md).

Chapter 9A is canonical under accepted
[`ADR 0020`](docs/adr/0020-typed-transport-neutral-api-boundary.md) and merged PR #27. It introduces
`aie-api-v1`, a strict transport-neutral interface over the accepted Chapter 6 through Chapter 8
application use cases. The interface composes canonical records, dependency-injects their
application owners, and returns the same canonical outputs as direct Python invocation. It adds no
financial calculation, score, sizing, timing logic, persistence authority, or broker action. See
[`Chapter 9A: Typed product API boundary`](docs/chapter-9a-api-boundary.md).

Chapter 9B is canonical under accepted
[`ADR 0021`](docs/adr/0021-immutable-product-record-persistence.md). It adds an
append-only, content-addressed persistence port and a file-backed SQLite reference adapter for the
15 admitted product-critical immutable record kinds. Storage verification remains distinct from
canonical financial replay, and the first local `stored_at` is audit evidence rather than
cryptographic notarization. See
[`Chapter 9B: Immutable product persistence`](docs/chapter-9b-immutable-product-persistence.md).

Chapter 9C is canonical under accepted
[`ADR 0022`](docs/adr/0022-local-operator-workspace-mvp.md). It adds a
minimal local operator workspace over `aie-api-v1` and Chapter 9B persistence: read-only CLI
composition, immutable-record navigation, exact canonical JSON rendering, existing Decision and
Execution Card projections, and optional injected write orchestration. Browser writes require a
server-generated localhost anti-CSRF token before dispatch. No financial logic moves into the UI.
See [`Chapter 9C: Operator workspace MVP`](docs/chapter-9c-operator-workspace-mvp.md).

Chapter 9 was integrated into `main` through PR #30. Chapter 10 was integrated into `main` through
PR #31 under accepted
[`ADR 0023`](docs/adr/0023-prospective-local-product-composition.md). It adds an
explicit local composition root, strict Causal/Underwriting intake, conservative local-file
evidence ingestion, and explicit fail-closed store initialization. See
[`Chapter 10: Prospective Operation & Product Composition MVP`](docs/chapter-10-prospective-operation-mvp.md).

Chapter 11 is now an active proposal under
[`ADR 0024`](docs/adr/0024-point-in-time-sec-fundamental-data-foundation.md). Its first slice begins a
strict CIK-based SEC submissions catalog before later accession capture, shadow XBRL extraction,
and metric-by-metric canonical fact admission. It remains a separate review scope built on the
merged Chapter 10 foundation. See
[`Chapter 11: Point-in-Time SEC Fundamental Data Foundation`](docs/chapter-11-sec-fundamental-data-foundation.md).

Live brokerage actions, calibrated automatic sizing, advanced
tax-lot optimization, covariance optimization, Market State, aggregate Learning skill statistics,
factor-adjusted alpha, automatic Learning feedback, production database operations, remote/multi-
user web deployment, automated extraction/discovery, and complete filing normalization remain
outside the implemented product scope.

## Quick start

Requirements: Python 3.12 or 3.13 and `uv`.

```bash
uv sync --locked --all-groups
uv run asymmetric-engine doctor
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
```

### Controlled SEC evidence operations

Declare the SEC-required application identity and a monitored contact in your local environment.
Never commit the real value; the address below is only a placeholder:

```bash
export AIE_SEC_USER_AGENT="AIE-Research your-contact@example.com"
```

Ingest one exact filing reference into a local append-only ledger:

```bash
uv run asymmetric-engine evidence ingest-sec \
  --database ./evidence-ledger.sqlite3 \
  --reference 0000320193/0000320193-24-000123
```

Query what AIE had actually ingested by a decision time:

```bash
uv run asymmetric-engine evidence list \
  --database ./evidence-ledger.sqlite3 \
  --subject company:sec-cik-0000320193 \
  --as-of 2026-08-25T18:00:00+00:00 \
  --knowledge-mode live_system_replay
```

Use `evidence coverage` with the same boundary arguments to inspect known-version exclusions and
temporal-provenance warnings. Verify an exact stored document with:

```bash
uv run asymmetric-engine evidence verify \
  --database ./evidence-ledger.sqlite3 \
  --document-id "$DOCUMENT_ID"
```

All completed evidence operations emit machine-readable JSON. Exit code `0` means success, `2`
means an invalid request, missing record, storage failure, or partial batch failure, and `3` means
integrity verification detected altered bytes.

The coverage command describes only versions already known to the ledger. It does not prove that
the filing universe is complete.

An already initialized Chapter 9B product store can be browsed locally
without enabling writes:

```bash
uv run asymmetric-engine workspace \
  --database ./product-records.sqlite3 \
  --port 8765
```

The command binds only to `127.0.0.1` and refuses to create a missing product database. Write
composition remains explicitly injected and is not enabled by this CLI command.

Or build and diagnose the same runtime boundary used by CI:

```bash
docker build --tag asymmetric-insight-engine:local .
docker run --rm asymmetric-insight-engine:local
```

## Repository map

- `src/asymmetric_engine/domain`: pure evidence, temporal, financial, causal, opportunity,
  Portfolio Decision, Execution, and Learning contracts.
- `src/asymmetric_engine/application`: use cases and orchestration, including the storage-agnostic
  product persistence port.
- `src/asymmetric_engine/infrastructure`: external providers and persistence adapters, including
  reference SQLite stores.
- `src/asymmetric_engine/interfaces`: CLI, read-only Decision/Execution Card projections, the typed
  product API boundary, the Chapter 9C local operator workspace, and Chapter 10 prospective intake.
- `docs`: system constitution, architecture, and Architecture Decision Records.
- `docs/roadmap.md`: canonical delivery order and deferred capability register.
- `docs/complexity-budget.md`: admission and graduation rules for new sophistication.
- `tests`: unit, contract, integration, and architecture tests.

The Market Screener remains a separate consumer of shared contracts. The Quantum Cycle Model is
an experimental adapter, not the engine core. See
[`ADR 0005`](docs/adr/0005-adjacent-applications-and-experimental-models.md).

See `CONTRIBUTING.md` for the development workflow and `AGENTS.md` for agent-specific rules.
Required repository-level protections are recorded in
[`docs/github-governance.md`](docs/github-governance.md).
