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

## Dependency rules

- Domain imports Python standard library and domain-approved validation primitives only.
- Domain never imports infrastructure, application, or interfaces.
- Application depends on domain contracts and declares ports.
- Infrastructure implements application ports.
- Interfaces invoke application services and contain no financial calculations.
- Each fact, transformation, score, and decision has one canonical owner.

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

Underwriting may mark an opportunity `ready_for_portfolio_review`. It cannot declare it
allocatable: sizing and allocation require portfolio-level capital, correlation, concentration,
liquidity, risk, and tax context owned by the Portfolio and Capital Allocation module.

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

## AI boundary

AI adapters may extract claims, entities, relations, or candidate hypotheses. Their output is
untrusted until validated against source provenance and domain rules. Deterministic code owns
time filtering, numerical transformations, scoring, constraints, and portfolio calculations.
