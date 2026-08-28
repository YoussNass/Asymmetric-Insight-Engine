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

Market and regime state informs opportunity assessment, portfolio construction, and execution
without replacing the causal thesis.

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
- Company quality, thesis quality, investment quality, and portfolio fit are separate concepts.
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

Chapters 2 through 6A are complete. Chapter 5 adds the first standalone Investment Underwriting
slice: normalized reported, market-observed, and analyst-adjusted facts with native currency and
fiscal-period scope; versioned deterministic
formulas; eight independent analytical dimensions; categorical eligibility gates; dated
bear/base/bull valuation bridges; probability-free payoff arithmetic; and a deterministic
`ready_for_portfolio_review` hand-off.

The reference case continues the Chapter 4 Micron hypothesis and uses selected reported values
from Micron's fiscal 2025 Form 10-K. It keeps diluted weighted-average shares used for EPS distinct
from fiscal-year-end shares outstanding used as the current per-share valuation anchor. Short
source excerpts and all market-price and valuation assumptions are deterministic test fixtures.
The case proves the contract; it is not an investment recommendation, a complete Micron analysis,
or evidence that the security is attractive. See
[`Chapter 5: Standalone investment underwriting`](docs/chapter-5-investment-underwriting.md).

Chapter 6A adds a factual, immutable Portfolio State:
canonical accounts and instruments, long-only positions, native-currency prices and cash roles,
basic account tax and aggregate cost-basis metadata, the versioned ETF allow-list and benchmark,
and a deterministic T0 fingerprint and audit envelope. It deliberately exposes only
currency-grouped subtotals and contains no exposure, fit, score, sizing, allocation, timing, or
execution logic. See [`Chapter 6A: Factual Portfolio State`](docs/chapter-6a-portfolio-state.md)
and accepted [`ADR 0014`](docs/adr/0014-factual-portfolio-state-and-t0-snapshot.md). Chapter 6B is
the next narrow slice and will derive descriptive exposure without mutating the factual state.

Automated extraction and signal discovery, complete filing normalization, calibrated forecast
distributions, live Portfolio providers and persistence, Market State, portfolio exposure and
fit, capital allocation, order execution, filing discovery, and a complete user interface remain
outside the implemented scope. SQLite remains a local/reference evidence persistence adapter.

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

All completed operations emit machine-readable JSON. Exit code `0` means success, `2` means an
invalid request, missing record, storage failure, or partial batch failure, and `3` means integrity
verification detected altered bytes.

The coverage command describes only versions already known to the ledger. It does not prove that
the filing universe is complete.

Or build and diagnose the same runtime boundary used by CI:

```bash
docker build --tag asymmetric-insight-engine:local .
docker run --rm asymmetric-insight-engine:local
```

## Repository map

- `src/asymmetric_engine/domain`: pure evidence, temporal, financial, causal, opportunity, and
  Portfolio State contracts.
- `src/asymmetric_engine/application`: use cases and orchestration.
- `src/asymmetric_engine/infrastructure`: external providers and persistence adapters.
- `src/asymmetric_engine/interfaces`: CLI, API, and future user interfaces.
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
