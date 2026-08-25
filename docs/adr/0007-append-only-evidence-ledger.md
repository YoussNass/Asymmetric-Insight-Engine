# ADR 0007: Append-only, version-aware evidence source ledger

- Status: Accepted
- Date: 2026-08-25

## Context

Point-in-time filtering is insufficient if a provider revision silently replaces the payload that
was actually available at an earlier date. The first Data and Evidence vertical slice therefore
needs to preserve exact source bytes, provider version identity, publication time, and ingestion
time before financial transformations begin.

## Decision

Every ingested source document has:

- a provider and provider-owned record identity;
- an explicit provider version;
- a canonical internal subject identity rather than an unqualified ticker;
- effective, availability, and recording timestamps;
- a SHA-256 hash and byte size computed from the exact payload;
- an immutable internal document identity derived from the provider version key.

The ledger is append-only. Re-ingesting the same provider record and version with identical bytes
and metadata is idempotent and preserves the original `recorded_at`. Reusing that identity with
different content or immutable metadata is a conflict. A correction or restatement must use a new
provider version and remain alongside the original.

Application queries apply the shared `KnowledgeBoundary`; repositories do not invent alternative
temporal semantics. The initial SQLite adapter is a reference implementation for deterministic
local and integration testing. It does not replace the production direction of PostgreSQL metadata
plus immutable object snapshots.

## Consequences

- Historical reconstruction can select the exact version publicly available by `as_of`.
- Live-system replay can additionally reproduce whether AIE had ingested that version by `as_of`.
- Exact bytes remain available for audit and deterministic reprocessing.
- Provider adapters must expose version identity instead of returning only the latest payload.
- Real provider ingestion remains blocked until licensing, retention, and redistribution rules are
  recorded for that source.
