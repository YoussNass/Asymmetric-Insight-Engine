# ADR 0009: Complete Chapter 3 with controlled evidence operations

- Status: Proposed
- Date: 2026-08-25

## Context

An immutable ledger and a provider adapter are insufficient if they can be exercised only from
tests. Chapter 3 needs one controlled operational path that can ingest real source references,
explain expected failures, verify stored bytes, and show which known versions cross a decision-time
knowledge boundary. It must do so without prematurely adding discovery, financial extraction,
backtesting, scheduling, or portfolio logic.

Calling a count of locally known versions "complete coverage" would itself be misleading. The
system does not yet own an authoritative expected-filing universe, so it can report knowledge
boundary coverage only for versions already known to the ledger.

## Decision

Chapter 3 ends with the following operational contracts:

- SEC ingestion accepts one or more unique exact `CIK/accession` references and processes them
  sequentially through one rate-limited provider instance.
- The SEC declared identity comes from `AIE_SEC_USER_AGENT`; no personal contact or credential is
  committed to the repository.
- Expected failures are classified as invalid reference, provider access, provider payload,
  unsupported source, or provider-version conflict. A batch continues across those failures and
  exposes every outcome. Unexpected programming errors still fail loudly.
- The CLI emits deterministic JSON for ingestion, point-in-time listing, knowledge-boundary
  coverage, and content-integrity verification.
- Exit code `0` means complete success, `2` means invalid usage, missing data, storage failure, or
  at least one classified batch failure, and `3` means stored-content corruption was detected.
- Integrity verification re-reads stored bytes and recomputes both SHA-256 and byte size.
- Knowledge coverage counts included versions, unavailable source versions, versions not yet
  ingested at replay time, and each availability basis. It emits an explicit warning when public
  historical availability is unverified.
- The report is named `KnowledgeCoverageReport`; it must never be presented as universe or filing
  completeness.
- CI and unit tests use deterministic synthetic SEC-format responses and never contact sec.gov.

The SQLite ledger remains a reference/local adapter. These CLI operations do not change the
production persistence direction recorded in the architecture.

## Chapter 3 definition of done

Chapter 3 is complete only when all of the following are merged and green:

1. immutable, version-aware exact-byte storage;
2. canonical historical-reconstruction and live-replay filtering;
3. one admitted real provider with documented rights and temporal limitations;
4. controlled real-provider invocation with safe configuration;
5. visible expected failures and non-zero failure exit status;
6. deterministic content-integrity verification;
7. honest knowledge-coverage reporting with missing temporal capability warnings;
8. fixture-based tests, strict typing, package diagnostics, Python 3.12/3.13, and container CI;
9. documentation of every deferred capability and the boundary of the next chapter.

## Consequences

- AIE can acquire and audit exact SEC periodic filings without pretending to understand their
  financial contents.
- Operators receive machine-readable partial-batch outcomes and must retain command output until a
  later durable ingestion-run ledger is introduced.
- A zero-document report is visible but cannot prove that no filing should exist.
- Historical SEC backfills remain conservative because first public availability is unresolved.
- Multi-process global rate coordination, retry scheduling, filing discovery, expected-universe
  manifests, provider-removal monitoring, and durable ingestion-run audit are explicitly deferred
  operational capabilities.
- CIK/ticker resolution, XBRL parsing, normalized facts, claims, financial formulas, signals,
  backtesting, portfolio decisions, and execution remain outside Chapter 3.
