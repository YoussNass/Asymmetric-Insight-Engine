# ADR 0010: Introduce a causal vertical slice before underwriting

- Status: Accepted
- Date: 2026-08-26

## Context

Chapter 3 can acquire, preserve, verify, and query exact source documents without claiming to
understand them. The next architectural risk is crossing from source material to an investment
conclusion without an explicit causal contract. A label, theme, correlation, or issuer statement
must not silently become proof that a listed company benefits economically.

The first slice must demonstrate one complete analytical path while remaining narrower than
Underwriting, Portfolio, and Execution. It must preserve the point-in-time boundary and the
epistemic distinctions already established by the system constitution.

## Decision

Chapter 4 introduces one deterministic causal-analysis contract with this ordered path:

```text
real-world change -> economic driver -> supply-chain actor -> listed beneficiary
```

The path is represented by typed nodes and typed directional edges. Every node cites one or more
material claims. A `real_world_change` node specifically requires an observation or statistical
result, making the initial signal distinct from the causal interpretation. Every edge:

- states its economic mechanism in plain language;
- cites one or more material claims;
- includes at least one claim classified as an inference or hypothesis;
- ultimately resolves to exact evidence items and immutable source-document versions.

The final beneficiary-mapping edge must cite evidence from the canonical subject it identifies;
merely including an unrelated document about that company elsewhere in the case is insufficient.

An evidence item used by this bounded context must identify its source document, source locator,
and extraction method. Its provenance, timestamps, and content hash must match the immutable
ledger record. Before an analysis is built, the application service re-reads the stored bytes and
verifies both SHA-256 and byte length.

Each analysis declares an `as_of` boundary and either `historical_reconstruction` or
`live_system_replay`. Sources and extracted evidence outside that boundary are rejected rather
than silently omitted. Material missing data, conflicts, assumptions, confidence rationales, and
invalidation conditions remain visible. Every readiness state carries a plain-language rationale.

The allowed readiness states are:

- `investigate`: a valid work in progress;
- `insufficient_evidence`: the missing evidence is explicitly identified;
- `ready_for_underwriting`: the causal path is structurally complete and falsifiable;
- `invalidated`: the reason the thesis failed is explicit.

`ready_for_underwriting` is an epistemic hand-off, not an investment approval. Chapter 4 does not
calculate valuation, expected return, balance-sheet quality, per-share economics, portfolio fit,
position size, timing, or orders.

The same validated input and exact source versions produce the same SHA-256 fingerprint and
analysis identifier. Canonical output retains the economic stage order even when input collections
arrive in a different order. There is no aggregate causal score, weighting formula, or automatic
causal discovery in this slice.

Claim-level confidence declares a calibration status and optional method version. The reference
case labels its confidence annotations `uncalibrated`; they are review aids, not empirical
probabilities, thresholds, ranking inputs, or an eligibility formula.

## Reference case

The acceptance fixture models a deliberately narrow, economically real hypothesis:

1. expansion of AI data-centre deployment;
2. greater memory-bandwidth and memory-content requirements per AI server;
3. transmission of that demand through high-bandwidth-memory suppliers;
4. mapping of Micron as a listed beneficiary candidate;
5. hand-off to Underwriting, where economics and investability would be evaluated later.

Synthetic, deterministic excerpts use real SEC filing identities for NVIDIA and Micron. Tests and
CI never contact SEC systems, and the fixture does not claim to reproduce an entire filing.

## Acceptance criteria

Chapter 4 is complete only when:

1. the full typed path can be built from ledger-backed evidence;
2. every reference between document, evidence, claim, node, and edge is validated;
3. the initial signal is an observed or statistical claim rather than a hidden inference;
4. beneficiary mapping is directly supported by evidence about that canonical subject;
5. future or not-yet-recorded knowledge is rejected under the selected temporal mode;
6. missing, altered, or provenance-mismatched source content fails closed;
7. incomplete, incorrectly ordered, unsupported, duplicated, or invalidated graphs cannot be
   marked ready for Underwriting;
8. readiness includes an explicit rationale and confidence calibration status remains visible;
9. the reference case is reproducible with a stable fingerprint and identifier;
10. unit, integration, architecture, typing, packaging, Python 3.12/3.13, and container checks
    pass.

## Consequences

- AIE gains an auditable bridge from immutable evidence to a falsifiable beneficiary hypothesis.
- Causality remains an explicit, reviewable interpretation rather than a property inferred from a
  theme label or correlation.
- Claim-level confidence and its calibration status remain visible but are not collapsed into a
  magic score.
- The reference case proves the contract, not the general truth or profitability of the thesis.
- Automated extraction, entity resolution, graph databases, causal discovery, normalized
  financial facts, Underwriting, ranking, portfolio construction, and execution remain deferred.
