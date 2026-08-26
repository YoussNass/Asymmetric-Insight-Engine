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

ADR 0008 admits SEC EDGAR periodic filings as the first real provider. The slice adds:

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

## Final vertical slice: controlled evidence operations

The completion slice makes the spine usable without expanding it into financial analysis:

```text
exact SEC references
-> sequential, rate-limited acquisition
-> immutable append or classified failure
-> deterministic JSON result
-> point-in-time listing
-> knowledge-boundary coverage report
-> exact-byte integrity verification
```

The CLI provides:

- `evidence ingest-sec` for one or more exact references;
- `evidence list` for documents included by `as_of` and `knowledge_mode`;
- `evidence coverage` for known-version inclusion, exclusion, and temporal provenance;
- `evidence verify` for stored byte-size and SHA-256 verification.

Successful commands return exit code `0`; invalid configuration, a missing record, or any failed
batch member returns `2`; detected content corruption returns `3`. Every completed operation emits
JSON on standard output so callers can retain and inspect the exact result.

`KnowledgeCoverageReport` deliberately does not claim filing-universe completeness. Until AIE owns
an authoritative expected-source manifest, it can only explain the versions already known to its
ledger. An empty report means `no_source_versions_recorded`, not `no filing exists`.

## Chapter completion boundary

When ADR 0009 and its implementation are accepted, Chapter 3 is complete at the evidence-source
level. The following remain intentionally deferred:

- SEC filing discovery and ticker/CIK master data;
- expected-filing manifests and durable ingestion-run audit;
- provider correction/removal monitoring;
- exact historical SEC first-publication reconstruction;
- distributed rate limiting, scheduled polling, and retry orchestration;
- XBRL parsing, normalized financial facts, claims, scores, signals, and backtests.

Those capabilities must enter later slices behind the contracts established here; none may alter
already-recorded source bytes or silently relax the temporal boundary.
