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

Historical calculations may consume only evidence with `available_at <= as_of`. Restatements and
backfills create new records or versions rather than silently rewriting prior knowledge.

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
