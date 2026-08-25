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

## Non-negotiable principles

- Every decision declares whether it is a historical reconstruction or a live-system replay and
  is evaluated against the corresponding `as_of` knowledge boundary.
- Observation, statistical result, inference, hypothesis, and qualitative judgement stay distinct.
- Missing or conflicting evidence remains visible.
- Eligibility gates precede ranking; there is no universal magic score.
- Company quality, thesis quality, investment quality, and portfolio fit are separate concepts.
- AI-assisted extraction may propose claims, but calculations and validations remain deterministic.
- No live order submission is included in version 1.

## Current status

Chapter 2: engineering foundation. The repository currently provides domain contracts,
architecture decisions, a diagnostic CLI, a reproducible container, and automated quality
gates. Financial ingestion, signals, portfolio logic, and user interfaces will be delivered in
later vertical slices.

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

Or build and diagnose the same runtime boundary used by CI:

```bash
docker build --tag asymmetric-insight-engine:local .
docker run --rm asymmetric-insight-engine:local
```

## Repository map

- `src/asymmetric_engine/domain`: pure business contracts and invariants.
- `src/asymmetric_engine/application`: use cases and orchestration.
- `src/asymmetric_engine/infrastructure`: external providers and persistence adapters.
- `src/asymmetric_engine/interfaces`: CLI, API, and future user interfaces.
- `docs`: system constitution, architecture, and Architecture Decision Records.
- `tests`: unit, contract, integration, and architecture tests.

The Market Screener remains a separate consumer of shared contracts. The Quantum Cycle Model is
an experimental adapter, not the engine core. See
[`ADR 0005`](docs/adr/0005-adjacent-applications-and-experimental-models.md).

See `CONTRIBUTING.md` for the development workflow and `AGENTS.md` for agent-specific rules.
Required repository-level protections are recorded in
[`docs/github-governance.md`](docs/github-governance.md).
