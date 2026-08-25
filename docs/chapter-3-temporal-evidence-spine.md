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

## Second vertical slice: first real provider

ADR 0008 proposes SEC EDGAR periodic filings as the first real provider. The slice adds:

- a reusable provider-admission checklist;
- exact `CIK/accession` references for complete submissions;
- explicit record/version mapping for 10-K and 10-Q filings and amendments;
- a declared-user-agent, timeout-bounded, payload-bounded HTTP fetcher;
- fail-closed SEC header validation;
- an explicit `availability_basis` contract.

SEC does not expose a timestamp for first public availability. This adapter therefore records
`available_at == recorded_at` with `availability_basis == observed_at_ingestion`. That policy is
safe for live replay and conservative for historical backfills. It must not be silently replaced
with the EDGAR acceptance timestamp.

This slice does not add filing discovery, ticker resolution, XBRL extraction, scheduled polling,
network calls in CI, or claims derived from filings.
