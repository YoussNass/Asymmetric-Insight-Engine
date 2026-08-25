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

Chapter 2 is complete. Chapter 3 establishes an append-only, version-aware source-document ledger,
canonical point-in-time queries, a narrowly admitted SEC EDGAR periodic-filing adapter, and
controlled evidence operations. SQLite remains a local/reference persistence adapter.

Financial extraction, signals, portfolio logic, order execution, filing discovery, and a complete
user interface remain outside Chapter 3.

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
  --document-id <UUID>
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
