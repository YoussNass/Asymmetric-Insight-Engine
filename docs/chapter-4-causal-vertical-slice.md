# Chapter 4: Causal vertical slice

## Purpose

Chapter 4 proves that AIE can turn point-in-time source material into one explicit, reviewable,
and falsifiable beneficiary hypothesis without crossing into investment underwriting.

## Minimal contract

The analytical object must preserve this lineage:

| Layer | Required meaning | Forbidden shortcut |
| --- | --- | --- |
| Source document | Exact immutable bytes and provider version | Mutable URL treated as evidence |
| Evidence | Located extraction with temporal provenance | Interpretation presented as fact |
| Claim | Typed statement with confidence rationale | Untyped assertion or unsupported score |
| Causal edge | Directional economic mechanism supported by claims | Theme membership or correlation as causality |
| Beneficiary | Canonical listed-company subject | Ticker string without identity |
| Decision | Readiness for the next analytical stage | Buy, allocate, size, time, or trade |

The graph follows four typed stages:

1. `real_world_change`;
2. `economic_driver`;
3. `supply_chain_actor`;
4. `beneficiary`.

Only the corresponding forward edge type may connect each adjacent pair. A ready analysis must
contain at least one complete path across all four stages. Branches are allowed, but every node,
edge, claim, evidence item, and source document must participate in the analysis rather than
remaining as an unreferenced artefact.

## Temporal and provenance rules

Every analysis carries the canonical `KnowledgeBoundary`:

- historical reconstruction admits documents publicly available by `as_of`;
- live-system replay additionally requires that AIE recorded them by `as_of`.

The builder retrieves each declared source from the ledger, verifies the stored byte length and
SHA-256 hash, and binds it to extracted evidence. Linked evidence must reproduce the source URI,
source type, `effective_at`, `available_at`, `recorded_at`, and content hash of that exact document.
Any mismatch fails closed.

`source_locator` identifies where the evidence came from inside the immutable document;
`extraction_method` identifies how it was produced. The first slice uses deterministic manual
fixtures. Future AI extraction must use the same contract and remains untrusted until validated.

## Readiness semantics

| State | Meaning | Required disclosure |
| --- | --- | --- |
| `investigate` | Coherent work in progress | Invalidation conditions |
| `insufficient_evidence` | No responsible hand-off is possible | Specific missing data |
| `ready_for_underwriting` | Complete causal path suitable for economic evaluation | Complete lineage and invalidations |
| `invalidated` | The causal thesis no longer holds | Explicit invalidation reason |

Readiness is categorical. Claim confidence scores remain local to each claim, require a rationale,
and are never averaged into a case score.

## Reference hypothesis

The integration fixture uses two synthetic SEC-format source payloads with real filing identities:

- NVIDIA fiscal 2024 Form 10-K, used for issuer-reported evidence about AI infrastructure demand;
- Micron fiscal 2024 Form 10-K, used for issuer-reported evidence about AI-server memory demand and
  HBM3E production.

The authoritative filing pages are the
[NVIDIA filing](https://www.sec.gov/Archives/edgar/data/1045810/000104581024000029/nvda-20240128.htm)
and the
[Micron filing](https://www.sec.gov/Archives/edgar/data/723125/000072312524000027/mu-20240829.htm).
The repository stores neither filing: its tests contain short synthetic SEC-format payloads that
are explicitly marked as fixtures.

The resulting hypothesis maps AI data-centre expansion through memory-bandwidth demand and HBM
supply to Micron as a candidate beneficiary. It deliberately records these limitations:

- no independent market-wide HBM supply-and-demand dataset;
- issuer reporting is not independent confirmation;
- no pricing, cost, competitive-share, valuation, or per-share impact analysis.

Those omissions do not disappear when the causal graph is structurally ready. They define the
questions that Underwriting must answer next.

## Out of scope

Chapter 4 does not add:

- automated filing extraction or an LLM decision-maker;
- entity discovery, ticker resolution, or a general knowledge graph;
- statistical proof of causality or market-wide causal discovery;
- company quality, valuation, expected-return, or asymmetric-payoff models;
- ranking, portfolio fit, capital allocation, timing, execution, or brokerage connectivity;
- an aggregate score, default weights, or default thresholds.
