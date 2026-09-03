# Chapter 11 — Point-in-Time SEC Fundamental Data Foundation

Type: evidence acquisition and normalization capability

Complexity classes: `CORE NOW` acquisition; `EXPERIMENTAL` extraction until fact admission

Governing decision: proposed ADR 0024

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

Status: first implementation started on a branch based on merged Chapter 10.

The first increment adds a strict parser for one exact `data.sec.gov/submissions/CIK##########.json`
response. It:

- accepts a positive CIK rather than a ticker;
- checks that the response CIK matches the request;
- filters only the forms already admitted by ADR 0008;
- produces exact CIK/accession references for the existing complete-submission provider;
- hashes the exact catalog response bytes;
- preserves acceptance metadata as non-authoritative text;
- exposes older-history pages and refuses to call the snapshot complete while they remain unfetched;
- rejects malformed parallel arrays, dates, accessions, duplicates, and inconsistent ticker/exchange
  aliases.

This first increment does not yet perform a live HTTP request, persist the catalog snapshot, fetch
older history pages, or ingest all discovered filing references. Those operations require the
manifest and lifecycle contract to be accepted first.

## Slice 11B — Versioned XBRL extraction

The second slice will place a standards-compliant processor behind a narrow infrastructure port and
produce immutable extraction candidates. A candidate retains:

- source document and accession;
- taxonomy namespace and concept;
- context and source locator;
- instant or duration period;
- unit and native currency;
- dimensions;
- precision/decimals metadata;
- extraction method and version.

Extraction candidates remain shadow data. They cannot satisfy Underwriting reported-fact inputs.

## Slice 11C — Canonical fact admission

The final slice admits a deliberately small first vocabulary after reconciliation. Each metric
family receives fixtures, mapping rules, ambiguity behavior, and a heterogeneous validation corpus.

Initial candidates include revenue, operating income, net income, operating cash flow, capital
expenditure inputs, cash, debt, diluted shares, stock-based compensation, and repurchases. Exact
scope remains subject to ADR review because sector-specific meanings may require separate mappings.

## Explicit limits

Chapter 11 does not provide:

- market prices or trading liquidity;
- non-SEC global issuer coverage;
- complete news or macro evidence;
- AI-generated claims or causal hypotheses;
- Market State;
- automated sizing, optimization, or Learning feedback;
- exact historical first-publication time where SEC does not provide it.

## Exit criterion

Chapter 11 is complete when a declared SEC issuer universe can be reconciled against an immutable
expected-source manifest, all admitted filing versions are retained, a narrow accepted fact set can
be deterministically regenerated and reconciled from exact source bytes, ambiguity fails closed,
and every downstream fact retains complete point-in-time source lineage.
