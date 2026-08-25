# ADR 0008: Admit SEC EDGAR periodic filings conservatively

- Status: Proposed
- Date: 2026-08-25

## Context

The first Temporal Evidence Spine slice proved immutable ingestion with synthetic content. A real
provider can enter the system only if identity, versions, time semantics, access policy, reuse,
and failures are explicit.

The candidates considered for the first adapter were SEC EDGAR, FRED/ALFRED, and the ECB Data
Portal. SEC EDGAR best matches the v1 listed-equity scope, exposes stable accession numbers and
complete submission archives, requires no paid subscription or API credential, and permits reuse
of public filing content. FRED/ALFRED has stronger native vintage semantics but is macro context,
not issuer evidence, and requires an API key. ECB is also macro context and remains a later
candidate.

SEC acceptance time is not the public-availability time. The SEC says filings are often published
one to three minutes later, sometimes later, and that no timestamp records first availability on
sec.gov. Treating acceptance as `available_at` would create false point-in-time precision.

## Provider admission criteria

A provider adapter must document and test:

1. fit with an approved product scope;
2. canonical subject, record, and version identities;
3. `effective_at`, `available_at`, and `recorded_at` derivation;
4. revisions, amendments, removals, and historical-version behaviour;
5. access requirements, rate limits, retry boundaries, and payload limits;
6. retention and reuse rights for exact source bytes;
7. fail-closed behaviour for missing or contradictory metadata;
8. fixture-based tests that make no live network calls in CI.

Failure on a mandatory criterion blocks admission. A known limitation may be admitted only when
the adapter represents it explicitly and chooses the more conservative knowledge boundary.

## Decision

Admit a narrow SEC EDGAR adapter for complete Form 10-K, 10-K/A, 10-Q, and 10-Q/A submissions
addressed by exact `CIK/accession` reference.

- The canonical subject is the zero-padded SEC CIK, not a ticker.
- The record identity is CIK, base form, and period of report.
- The accession number is the immutable provider version. Amendments therefore remain separate
  versions of the same record.
- `effective_at` is the filing header's period of report.
- Exact complete-submission bytes are retained and fingerprinted by the existing ledger.
- Because SEC provides no exact first-publication timestamp, `available_at` is set to the AIE
  ingestion observation and marked `observed_at_ingestion`. Acceptance time is never substituted.
- Automated access must use a declared application/contact user agent, a bounded timeout, bounded
  payload size, canonical SEC archive URLs, and a workload below the SEC maximum. Scheduling and
  retries remain outside this slice.
- Missing fields, identity mismatches, unsupported forms, invalid dates, empty payloads, and access
  failures stop ingestion. They are never repaired with guessed values.
- CI uses synthetic SEC-format fixtures and never contacts sec.gov.

## Consequences

- AIE gains its first real issuer-evidence adapter without credentials or licensed fixtures.
- Live-system replay remains correct: a filing cannot appear before AIE observed it.
- Historical reconstructions are deliberately conservative for filings backfilled after their
  original publication. They do not claim the filing was knowable at the historical acceptance
  time.
- Exact historical public-availability reconstruction remains unresolved. A later slice may use a
  separately archived dissemination feed or another verifiable observation source, but must not
  rewrite already-recorded documents.
- The adapter does not yet discover filings, resolve tickers, parse XBRL facts, schedule polling,
  retry requests, or produce claims.

## Official references

- SEC Developer Resources: <https://www.sec.gov/about/developer-resources>
- Accessing EDGAR Data: <https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data>
- SEC Webmaster FAQ: <https://www.sec.gov/about/webmaster-frequently-asked-questions>
- FRED real-time periods: <https://fred.stlouisfed.org/docs/api/fred/realtime_period.html>
