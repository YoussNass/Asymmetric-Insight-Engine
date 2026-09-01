# Chapter 9C: Operator workspace MVP

Chapter 9C is the final Chapter 9 productization slice. It adds a minimal human-facing workspace over the accepted Chapter 9A API contract and proposed Chapter 9B immutable product store. It is governed by proposed ADR 0022.

## What it does

The workspace can browse persisted canonical records, inspect their immutable storage metadata and exact canonical JSON, and render existing Decision/Execution Card projections where available. A configured write composition can invoke the explicit `aie-api-v1` operation registry and persist the exact returned canonical output records.

The shipped CLI composition is intentionally read-only:

```text
asymmetric-engine workspace --database PATH --port 8765
```

It opens an already initialized Chapter 9B SQLite reference store and serves only on `127.0.0.1`. A missing database is an error rather than a side-effecting create operation.

## Boundary

The workspace owns presentation and orchestration only. It does not own financial formulas, eligibility, look-through, ranking, pairwise judgement, sizing, tax, replacement selection, execution timing, thesis evaluation, or Learning feedback.

Storage verification remains distinct from canonical application replay. Seeing a record in the workspace does not make it valid input to a later financial decision unless its canonical application owner replays and verifies it.

## Local write safety

A write-enabled composition is possible only when a real `AieProductApi` and `StoreProductRecord` are injected. Browser writes additionally require a server-generated local token before dispatch. This is a localhost anti-CSRF measure, not authentication. Remote and multi-user deployment are not admitted by Chapter 9C.

Write requests use only the explicit Chapter 9A operation registry. Unknown client-defined operation names are rejected rather than dynamically resolved. Request bodies are bounded, and read-only mode rejects mutation before parsing a purported API request.

## Multi-record persistence

Most successful API responses produce one immutable product record. `MarginalDecisionPackage` is different: it contains multiple `PortfolioFit` records plus the `MarginalDecision`. Chapter 9C appends those exact records one at a time through the Chapter 9B port.

The MVP deliberately does **not** claim cross-record transactional atomicity. If infrastructure fails between appends, a prefix may already exist in the immutable store. Because storage IDs are content-addressed and append is idempotent, retrying the same canonical request can converge without overwriting prior records. A transactional batch/unit-of-work abstraction is deferred until real prospective operation demonstrates that it is needed.

## Explicitly deferred

- production HTTP deployment and authentication;
- React or another rich frontend framework;
- live broker/order/fill lifecycle;
- provider-complete composition;
- cross-record transactional persistence guarantees;
- automatic portfolio mutation from Learning;
- aggregate model-skill statistics;
- production database selection and operations.

The goal is to make AIE inspectable and operable early while preserving the architecture that makes its decisions auditable.
