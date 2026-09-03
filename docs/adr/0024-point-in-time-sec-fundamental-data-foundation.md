# ADR 0024: Own a point-in-time SEC fundamental-data foundation

- Status: Proposed
- Date: 2026-09-03

## Context

Chapter 10 composes the accepted analytical path into a prospectively usable local product, but it
deliberately leaves source discovery, extraction, and complete filing normalization outside its
scope. Its manual intake is sufficient to prove composition; it is not a sustainable source of
event-driven issuer fundamentals.

The owner has selected SEC EDGAR filings as the canonical first-party source for US issuer
fundamentals and has required a reusable AIE-owned normalization structure. The objective is not to
invent an XBRL standard processor. It is to own source identity, temporal provenance, mapping,
validation, reconciliation, versioning, and canonical fact admission while keeping the underlying
standards processor replaceable.

The existing SEC adapter already preserves exact complete-submission bytes for one caller-supplied
CIK/accession. It does not discover filings, prove expected-source coverage, fetch older submissions
pages, monitor amendments or removals, parse XBRL, or produce financial facts.

## Complexity Budget

| Gate | Chapter 11 evidence |
| --- | --- |
| Decision value | Reliable issuer facts are required by Underwriting and by every later capital decision that depends on it. |
| Validatability | Every catalog entry, source byte, extracted fact, context choice, mapping, and reconciliation can be fixture-tested and replayed. |
| Architectural necessity | Acquisition and parsing are infrastructure capabilities; canonical financial-fact admission remains owned by Underwriting. No new decision engine is required. |
| Data sufficiency | SEC exposes public submissions catalogs, complete filing archives, and structured XBRL. Coverage limits and older history pages remain explicit. |
| Explainability | Every admitted fact must retain accession, document, locator, taxonomy concept, context, unit, period, extraction version, and reconciliation result. |
| Maintenance cost | Start with 10-K/Q and amendments plus a narrow fact set. Use a replaceable standards processor and versioned mappings instead of a universal parser. |
| Timing | Manual filing discovery and typed fact preparation are now an explicit owner-identified operational and point-in-time integrity bottleneck. |

Architectural type: data acquisition and normalization capability inside the Evidence-to-
Underwriting path.

Classification:

- SEC source catalog and exact-byte acquisition: `CORE NOW`;
- XBRL extraction output: `EXPERIMENTAL` until validation;
- individually admitted reconciled fundamental facts: `CORE NOW` after their acceptance gates pass.

## Decision

### Preserve Chapter 10 and introduce Chapter 11 separately

Chapter 11 follows the accepted Chapter 10 implementation merged through PR #31. It must not
retroactively expand ADR 0023, `local-product-runtime-v1`, `aie-intake-v1`, or `aie-api-v1`.

### Separate catalog, source acquisition, extraction, and admission

The pipeline is:

```text
SEC submissions snapshot
-> explicit expected-source manifest
-> exact accession-based complete submission
-> immutable evidence ledger
-> versioned XBRL extraction candidates
-> deterministic mapping and reconciliation
-> canonical Underwriting financial facts
```

Each transition has a distinct contract and failure state. A later stage never repairs or
overwrites an earlier immutable source.

### Treat CIK and accession as canonical provider identity

Ticker and exchange values from SEC submissions are aliases observed in one exact catalog snapshot;
they are not canonical company identity. The zero-padded CIK identifies the subject and the
accession identifies the filing version consumed by the existing SEC provider.

The first catalog slice admits only Form 10-K, 10-K/A, 10-Q, and 10-Q/A. Other forms remain visible
as unsupported source coverage rather than being silently treated as parsed fundamentals.

### Do not turn SEC acceptance text into public availability

SEC submissions metadata may expose an acceptance value, but ADR 0008 establishes that acceptance
is not exact first-public availability. Chapter 11 preserves the raw value as provider metadata and
must not map it to `available_at`.

Live-system replay uses the time AIE actually records the source version. Any future historical
availability claim requires independently admissible dissemination evidence and a separate
decision; it must not be inferred during backfill.

### Make source-universe incompleteness explicit

The current SEC submissions response may point to additional older-history JSON pages. A snapshot
that declares unfetched pages is incomplete and must emit an explicit coverage warning. Whole-
history or whole-universe completeness may be claimed only after all expected pages and filing
versions are reconciled with a content-addressed expected-source manifest.

### Own normalization, not the low-level XBRL standard implementation

AIE owns:

- the canonical financial-fact vocabulary;
- taxonomy and issuer-extension mappings;
- context, unit, currency, duration, instant, and fiscal-period selection;
- amendment and restatement treatment;
- deterministic formula and extractor versions;
- statement and calculation reconciliation;
- ambiguity, conflict, and missing-data behavior;
- source-to-fact-to-decision lineage.

A standards-compliant XBRL processor such as Arelle may be used behind an infrastructure port and
pinned to an exact version. Its parsed output is untrusted input to AIE normalization, not canonical
financial truth by itself.

### Admit facts narrowly and fail closed

The first normalization set targets a small cross-industry core rather than every SEC concept.
Unknown extensions, ambiguous contexts, incompatible units, unreconciled values, and unsupported
dimensions remain explicit missing or conflicting data. They are never filled, forward-filled,
silently reclassified, or selected through an undocumented heuristic.

An extraction-version change creates a new derived result. It does not alter stored source bytes or
silently rewrite a decision that used an older result.

## Initial slices

### 11A — SEC source catalog and acquisition manifest

- strict parsing of one exact SEC submissions JSON response;
- content hash over the exact response bytes;
- canonical CIK and admitted accession references;
- explicit older-history page descriptors;
- no claim of complete history while any page remains unfetched;
- deterministic fixtures with no live SEC access in CI.

### 11B — Versioned XBRL extraction candidates

- extract contexts, concepts, units, periods, dimensions, decimals, and source locators;
- retain taxonomy namespaces and issuer extensions;
- produce shadow candidates with no active Underwriting authority;
- pin and isolate the replaceable standards processor.

### 11C — Canonical fundamental-fact admission

- admit a narrow fact vocabulary one metric family at a time;
- reconcile against filing statements and calculation relationships;
- validate across a heterogeneous golden corpus;
- expose coverage, conflicts, missing facts, and extraction version;
- hand only accepted facts to the existing Underwriting owner.

## Consequences

### Positive

- AIE begins capturing a durable first-party issuer history without a paid fundamentals license.
- Raw evidence remains independently reprocessable when mappings or parser versions improve.
- Point-in-time and restatement semantics remain compatible with ADR 0002, ADR 0007, and ADR 0008.
- The difficult semantic layer is proprietary and auditable while the standards processor remains
  replaceable.

### Negative

- SEC alone does not provide market prices, all news, macro data, or a global issuer universe.
- Historical backfill does not establish exact first-public availability.
- XBRL taxonomy and issuer-extension mappings require a permanent regression corpus and ongoing
  maintenance.
- The narrow first fact set will intentionally return unknown for unsupported sectors or contexts.

## Rejected alternatives

### Add Chapter 11 work to PR 31

Rejected because it would violate Chapter 10's accepted review boundary and make product
composition depend on an unvalidated provider pipeline.

### Treat current Company Facts JSON as historical truth

Rejected because an aggregate response observed today may contain later submissions and
restatements. Every historical fact must remain accession-bound and source-versioned.

### Build an AIE-specific XML/XBRL engine from scratch

Rejected because standards parsing has high maintenance cost and does not create AIE decision
value. AIE differentiates itself through temporal provenance, semantic normalization,
reconciliation, and decision lineage.

### Allow extraction candidates to populate active decisions immediately

Rejected because parser success does not prove economic meaning. Shadow extraction must pass
metric-level validation before canonical admission.

## Acceptance criteria

ADR 0024 may move to `Accepted` only when:

1. Chapter 10 and ADR 0023 are accepted independently;
2. catalog, acquisition, extraction, and fact admission have separate typed contracts;
3. current and older SEC catalog pages cannot be mistaken for complete history;
4. acceptance metadata cannot become `available_at`;
5. exact filing bytes remain the canonical immutable evidence;
6. XBRL outputs retain concept, context, unit, period, dimensions, locator, and method version;
7. extraction candidates have no active decision authority before metric-level validation;
8. amendment and restatement versions remain additive;
9. unknown or ambiguous mappings fail closed;
10. all provider tests use deterministic fixtures and complete repository checks pass;
11. the owner explicitly accepts this ADR; merge authorization remains separate.

## Official references

- SEC EDGAR APIs: <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>
- SEC Developer Resources: <https://www.sec.gov/about/developer-resources>
- EDGAR XBRL Guide: <https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide-2026-01-16.pdf>
- Arelle: <https://github.com/Arelle/Arelle>
