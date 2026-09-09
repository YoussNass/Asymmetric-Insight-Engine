# Chapter 11 — Point-in-Time SEC Fundamental Data Foundation

Type: evidence acquisition and normalization capability

Complexity classes: `CORE NOW` acquisition; `EXPERIMENTAL` extraction until fact admission

Governing decision: accepted ADR 0024

Dependency: Chapter 10 / ADR 0023

## Purpose

Chapter 11 replaces repeated manual SEC filing selection and fundamental-fact transcription with a
replayable source-to-fact pipeline. It adds no investment score, ranking, allocation preference, or
automated insight authority.

The proprietary AIE layer owns temporal identity, source coverage, economic mappings,
reconciliation, and lineage. A replaceable standards processor may handle low-level XBRL syntax.

## Chapter flow

```text
11A CATALOG AND CAPTURE
SEC submissions -> expected references -> immutable complete filings

11B SHADOW EXTRACTION
immutable filing -> versioned XBRL fact candidates

11C FACT ADMISSION
candidate -> mapping + reconciliation -> canonical Underwriting fact
```

## Slice 11A — SEC source catalog and acquisition manifest

Status: implementation complete in PR #32, integrated before PRs #33 and #34.
Owner acceptance and separate merge authorization were recorded on 2026-09-09.

The slice provides a strict, deterministic source-universe path for one SEC CIK. It:

- accepts a positive CIK rather than a ticker and verifies the response CIK;
- filters only Form 10-K, 10-K/A, 10-Q, and 10-Q/A;
- preserves ticker/exchange values only as aliases from the exact catalog snapshot;
- hashes the exact current submissions response bytes;
- preserves acceptance metadata as non-authoritative text and never maps it to `available_at`;
- parses every older-history page descriptor declared by the current response;
- fetches every declared older page through an injected provider boundary;
- reconciles page identity, filing counts, date ranges, CIK, and duplicate accessions;
- refuses an expected-source manifest when a declared page is missing, duplicated, unexpected, or
  inconsistent;
- content-addresses the resulting expected filing universe;
- emits exact CIK/accession references in deterministic order;
- captures every manifest-declared complete submission through the existing append-only Evidence
  Ledger ingestion path;
- keeps provider tests deterministic and free of live SEC access in CI.

The provider still receives its byte-fetch operation from the outer runtime. Chapter 11A does not
add a scheduler or hide live network access inside tests. A catalog hash identifies the exact
snapshot used to build the manifest, while the complete-submission bytes remain the canonical
filing evidence consumed downstream.

## Slice 11B — Versioned XBRL extraction

The second slice places a standards-compliant processor behind a narrow replaceable port and
produces immutable extraction candidates. A candidate retains:

- source document and accession;
- source content hash;
- taxonomy namespace and concept;
- context and source locator;
- instant or duration period;
- unit and native currency when represented by the filing;
- dimensions;
- precision/decimals metadata;
- raw value;
- standards-processor identity and version;
- AIE extraction method and version.

The Arelle bridges require reviewed version 2.44.5. The actual processor and statement inspector
are external injected callables, not a bundled Arelle runtime or a hidden core dependency. The
extraction bridge selects one admitted primary document from verified complete-submission bytes.
Candidate sets are content-addressed and integrity-checked before downstream use.

Extraction candidates are shadow data. They cannot satisfy Underwriting reported-fact inputs and
cannot gate, rank, size, allocate, or execute capital.

## Slice 11C — Canonical fact admission

The final slice admits a deliberately small first vocabulary only after deterministic mapping and
reconciliation. Each metric family receives fixtures, explicit mappings, ambiguity behavior, and a
heterogeneous validation corpus.

The eight admitted v1 metric families are revenue, gross profit, operating income, net income,
operating cash flow, capital expenditures, diluted weighted-average shares, and share-based
compensation. Only admitted standard-taxonomy, dimensionless, exact-period candidates qualify;
native money and shares are normalized to the existing million-unit contracts without FX.

`cash_and_investments`, `total_debt`, and `diluted_shares_outstanding` remain unsupported in v1.
They require separately reviewed semantic composition and reconciliation rules. Unknown issuer
extensions, competing concepts, incompatible units, and ambiguous contexts fail closed.

AIE owns `DeterministicSecFactReconciler`: the injected inspector supplies untrusted statement and
calculation observations, while AIE checks exact statement equality and weighted calculation sums.
Incomplete or inconsistent relationships fail closed; `not_applicable` is explicit when no
calculation relationship is declared. Exact equality deliberately rejects some rounded filings;
there is no implicit rounding tolerance.

Every admitted fact must retain complete source-to-candidate-to-mapping lineage and be handed to the
existing Underwriting owner rather than creating a second fundamental-analysis engine.

## Explicit limits

Chapter 11 does not provide:

- market prices or trading liquidity;
- non-SEC global issuer coverage;
- complete news or macro evidence;
- AI-generated claims or causal hypotheses;
- Market State;
- automated sizing, optimization, or Learning feedback;
- exact historical first-publication time where SEC does not establish it;
- silent filling, forward filling, or heuristic concept selection.

## Exit criterion

Chapter 11 is complete when a declared SEC issuer universe can be reconciled against a
content-addressed expected-source manifest, all admitted filing versions are retained, a narrow
accepted fact set can be deterministically regenerated and reconciled from exact source bytes,
ambiguity fails closed, and every downstream fact retains complete point-in-time source lineage.

## Formal closure record

Owner acceptance of ADR 0024 and separate authorization for all three merges were recorded on
2026-09-09. Delivery order is PR #32 (11A), PR #33 (11B), then PR #34 (11C), each reaching main
through a merge commit after required checks pass. No new capability is part of this closure.

Status: **CLOSED / CANONICAL / FUNCTIONING** once PR #34 is merged and its resulting main commit
passes all three required CI jobs. The PR merge records and the CI run on that exact main commit
are the authoritative completion evidence; before those gates pass this record is pending closure.

Validation covers deterministic catalog/capture fixtures, shadow integrity and pinned processor
boundaries, all eight metric families, and fail-closed reconciliation/lineage cases. It does not
claim a bundled live Arelle deployment or exhaustive real-world issuer coverage. Local validation
was unavailable because `uv` was not installed; only green corresponding CI jobs attest the
required checks, including lint, formatting, typing, tests, doctor, package and container builds.

Accepted non-blockers remain: externally injected Arelle runtime, exact reconciliation without
rounding tolerance, no acceptance-to-`available_at` inference, and the three unsupported metrics
listed above. Amendments and restatements remain additive. Deferred capabilities stay deferred.
