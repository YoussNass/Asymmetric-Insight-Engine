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
| Signal claim | Observed or statistical change with provenance | Causal inference presented as observation |
| Causal node | Typed economic role supported by claims | Unreferenced graph label |
| Causal edge | Directional economic mechanism supported by claims | Theme membership or correlation as causality |
| Beneficiary mapping | Canonical subject plus direct subject evidence | Ticker string or unrelated company document |
| Decision | Explained readiness for the next analytical stage | Buy, allocate, size, time, or trade |

The graph follows four typed stages:

1. `real_world_change`;
2. `economic_driver`;
3. `supply_chain_actor`;
4. `beneficiary`.

Only the corresponding forward edge type may connect each adjacent pair. A ready analysis must
contain at least one complete path across all four stages. Branches are allowed, but every node,
edge, claim, evidence item, and source document must participate in the analysis rather than
remaining as an unreferenced artefact.

Every node cites typed claims. The `real_world_change` node must cite at least one observation or
statistical result: this is the thin slice's explicit signal. Causal edges must instead include an
inference or hypothesis claim. The separation prevents the system from presenting an interpreted
mechanism as an observed fact. Automated signal discovery remains deferred.

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

Every state also includes `readiness_rationale`, so the hand-off itself is explainable. Readiness
is categorical. Claim confidence annotations remain local to each claim, require a rationale,
declare calibration status and method when applicable, and are never averaged into a case score.
The reference annotations are explicitly `uncalibrated`: no decision gate or ranking consumes
their numerical values.

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
- claim confidence annotations are not empirically calibrated;
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
