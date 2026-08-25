# Chapter 3: Temporal Evidence Spine

## First vertical slice

The first slice proves one narrow chain:

```text
versioned provider payload
-> exact-byte fingerprint
-> immutable ingestion timestamp
-> append-only source ledger
-> historical reconstruction or live replay query
```

It uses synthetic content and a SQLite reference adapter so temporal correctness can be tested
without vendor credentials, licensing assumptions, or production infrastructure.

## Acceptance criteria

1. The same provider record and version is idempotent only when payload and immutable metadata
   match exactly.
2. A reused version identity with different content is rejected.
3. Restatements create new records and never overwrite originals.
4. Historical reconstruction filters by `available_at`.
5. Live-system replay filters by both `available_at` and `recorded_at`.
6. Exact payload bytes can be recovered and verified against their SHA-256 hash.
7. The domain remains independent of SQLite and provider implementations.

## Explicit non-goals

- no real market-data or filing provider;
- no PostgreSQL, object-store, or Parquet deployment;
- no ticker-to-company master-data resolver;
- no claim extraction, fundamental calculation, score, signal, or allocation;
- no licensed or personal dataset in the repository.

The next slice may add one freely accessible provider only after its availability semantics,
historical-version capability, rate limits, license, and failure behaviour are documented.
