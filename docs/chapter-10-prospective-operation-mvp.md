# Chapter 10 — Prospective Operation & Product Composition MVP

Type: product composition capability  
Complexity class: `CORE NOW`  
Governing decision: proposed ADR 0023  
Runtime contract: `local-product-runtime-v1`  
Upstream intake contract: `aie-intake-v1`

## Purpose

Chapter 10 turns the accepted analytical and product slices into one prospectively usable local
workflow without introducing a new financial engine.

Before this chapter, AIE has canonical analytical owners, a typed Chapter 6-8 API, immutable product
persistence, and a local workspace. The missing piece is a deliberate outer composition that gives
all of those components the same real evidence ledger and product store, while also exposing the
Causal Analysis and Underwriting hand-off that ADR 0020 intentionally kept outside `aie-api-v1`.

Chapter 10 is therefore about **operating the accepted system**, not adding predictive sophistication.

## Product flow

The admitted local workflow is:

```text
EXPLICIT STORE INITIALIZATION
        |
        v
SOURCE EVIDENCE
SEC provider or conservative local-file ingestion
        |
        v
AIE-INTAKE-V1
CausalAnalysisDraft -> canonical CausalAnalysis
UnderwritingDraft   -> canonical OpportunityState
        |
        v
IMMUTABLE PRODUCT STORE
exact Chapter 9B records
        |
        v
AIE-API-V1 + OPERATOR WORKSPACE
Portfolio -> Allocation/Replacement -> Execution -> Learning
        |
        v
IMMUTABLE PROSPECTIVE RECORD HISTORY
```

Every analytical arrow above is still owned by the already accepted application use case. The
runtime only wires those owners together.

## Explicit initialization

The prospective runtime uses separate file-backed reference databases for:

- source evidence;
- immutable product records.

Creation is explicit:

```bash
uv run asymmetric-engine product init \
  --evidence-database ./aie-evidence.sqlite3 \
  --product-database ./aie-products.sqlite3
```

Normal product startup does **not** create either store. A missing or invalid path fails closed.
This makes an accidental new database distinguishable from an intentionally initialized AIE
history.

## Evidence intake

### Existing SEC path

The existing exact SEC accession path remains available for admitted SEC filings. It is not changed
into a generic discovery engine by Chapter 10.

### Local manual source path

When no automated provider exists, the operator may ingest exact local bytes:

```bash
uv run asymmetric-engine evidence ingest-local \
  --database ./aie-evidence.sqlite3 \
  --file ./source.pdf \
  --provider-record-id research-note-2026-09-02 \
  --provider-version v1 \
  --subject company:example \
  --title "Research source" \
  --source-uri file-origin://research-note-2026-09-02 \
  --source-type research \
  --effective-at 2026-09-02T06:00:00+00:00 \
  --media-type application/pdf
```

This adapter is intentionally conservative. It always records availability as
`observed_at_ingestion`. The operator cannot declare that AIE knew the source at some earlier date.
The source may describe an older event, but live-system replay sees it only from the moment AIE
actually ingested it.

This path imports evidence bytes and metadata only. It does not turn the file into claims,
financial facts, or investment conclusions automatically.

## Upstream typed intake

`aie-intake-v1` exposes only:

- `build_causal_analysis`;
- `build_opportunity_state`.

Each JSON request contains the complete existing typed draft. Example invocation:

```bash
uv run asymmetric-engine product intake \
  --evidence-database ./aie-evidence.sqlite3 \
  --product-database ./aie-products.sqlite3 \
  --operation build_causal_analysis \
  --request ./causal-request.json
```

The facade delegates directly to `BuildCausalAnalysis` or `BuildOpportunityState`. Successful
canonical output is immediately appended to the immutable Chapter 9B store. Client-added fields are
rejected and the intake surface performs no extraction or financial computation.

## Downstream operator workspace

Once the upstream records and the other explicit inputs are available, the fully composed local
workspace can be started with:

```bash
uv run asymmetric-engine product workspace \
  --evidence-database ./aie-evidence.sqlite3 \
  --product-database ./aie-products.sqlite3 \
  --port 8765
```

This is the same Chapter 9C workspace, but now supplied with the complete accepted application
service graph and immutable product store. It remains bound to `127.0.0.1`; browser writes retain
the existing local anti-CSRF write token.

The downstream operations remain exactly those in `aie-api-v1`. Chapter 10 does not alter their
request or response schemas.

## What is now possible

With explicit valid inputs, one local AIE installation can now:

1. preserve exact source evidence;
2. build and persist a canonical causal analysis;
3. build and persist standalone underwriting / Opportunity State;
4. create Portfolio State and Exposure;
5. compare marginal capital alternatives;
6. apply owner policy or evaluate an explicit replacement;
7. create an Execution Plan;
8. open a prospective Learning case;
9. later evaluate that case at T2;
10. inspect the complete immutable record history in one operator workspace.

This does not mean AIE can yet discover the whole market autonomously or operate a broker. It means
the accepted logic can finally be exercised prospectively as a coherent product rather than as
separate test fixtures or Python glue.

## Manual-input boundary

Chapter 10 deliberately permits explicit structured operator input where automatic providers or
extractors do not yet exist. This is not a relaxation of the epistemic model:

- source bytes require immutable provenance;
- local source availability cannot be backdated;
- Causal and Underwriting drafts still have to satisfy all evidence/claim/gate/scenario invariants;
- Portfolio inputs remain explicit factual records;
- capital amounts remain caller supplied;
- Execution observations remain T1 inputs;
- Learning observations remain T2 inputs.

The product runtime never supplies a missing financial value, score, probability, target size,
market regime, or decision preference.

## Out of scope

Chapter 10 does not add:

- automated whole-market discovery;
- AI extraction or automatic claim generation;
- a market-data universe provider;
- Market State or market timing;
- calibrated automatic sizing;
- generic raw JSON import into canonical storage;
- automatic Learning feedback;
- broker connectivity, orders, fills, or account synchronization;
- remote binding, user accounts, authentication, TLS, or multi-user concurrency;
- PostgreSQL/ORM/cloud persistence;
- a richer frontend framework.

Those capabilities remain subject to the complexity budget and their existing graduation criteria.

## Exit criterion

Chapter 10 is complete when a deterministic integration path proves:

```text
real append-only evidence store
-> canonical Causal Analysis
-> canonical Opportunity State
-> immutable product persistence
-> configured aie-api-v1/workspace
-> canonical persisted downstream output
```

while missing stores fail closed, local manual evidence cannot backdate availability, direct
application and typed intake results remain exactly equal, and the complete repository CI passes on
the reviewed implementation head.
