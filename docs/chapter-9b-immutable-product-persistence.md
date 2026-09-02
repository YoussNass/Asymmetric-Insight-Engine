# Chapter 9B: Immutable product persistence

## Purpose

Chapter 9B makes accepted product records durable without moving financial authority into storage.
It is the persistence bridge between the canonical Chapter 9A API boundary and the Chapter 9C
operator workspace.

## Architectural classification

- Type: persistence capability.
- Complexity class: `CORE NOW`.
- Governing decision: proposed ADR 0021.
- Storage envelope: `product-record-envelope-v1`.
- Reference adapter: file-backed SQLite only.

## Core contract

One exact admitted Pydantic record is serialized to deterministic canonical JSON and stored in an
append-only envelope containing:

- admitted record kind;
- record JSON schema version;
- SHA-256 of the exact JSON bytes;
- UUIDv5 storage ID derived from kind, schema and hash;
- first AIE `stored_at` timestamp;
- immutable canonical JSON payload.

The storage identity is not a financial decision identity. Existing canonical IDs and fingerprints
remain inside the record and retain their original owners.

## Admitted first-slice records

The registry covers the product-critical path from Causal/Underwriting output through Learning:

1. Causal Analysis;
2. Opportunity State;
3. Portfolio State Draft;
4. Portfolio State;
5. Portfolio Exposure;
6. Portfolio Fit;
7. Marginal Decision;
8. Position Review;
9. Owner Portfolio Policy;
10. policy-constrained Marginal Decision;
11. Replacement Decision;
12. Execution Policy;
13. Execution Plan;
14. Decision Learning Case;
15. Decision Learning Evaluation.

Raw evidence payloads remain in the Chapter 3 evidence ledger and are not copied into the product
store.

## Persistence semantics

`StoreProductRecord` performs no financial calculation. It:

1. rejects unregistered record classes;
2. canonicalizes the record through Pydantic JSON mode;
3. hashes the exact canonical UTF-8 JSON;
4. derives the deterministic storage ID;
5. asks the injected clock for a timezone-aware first-storage timestamp;
6. appends through the persistence port.

A byte-identical re-append is idempotent and returns the first stored envelope, including its
original timestamp.

A material revision produces different canonical JSON and therefore a new storage ID. No row is
replaced.

## Load semantics

`LoadProductRecord` verifies before returning a stored object:

- envelope version;
- current admitted record schema version;
- payload SHA-256;
- content-addressed storage ID;
- concrete Pydantic model validation;
- exact canonical JSON reproduction.

This is **storage verification**, not downstream decision verification. A loaded Portfolio State,
Portfolio Decision, Execution Plan, Opportunity State, or Learning record must still pass the
canonical replay path owned by its application use case before it influences a later decision.

## Prospective evidence and trust model

The first `stored_at` timestamp is useful because Chapter 8 previously had no durable proof of when
a Learning case was created. In prospective operation, preserving the case near T1 provides an
auditable local creation record before later T2 outcomes exist.

The timestamp is deliberately narrow evidence. A historical case first persisted after T2 remains a
backfilled case; storage does not retroactively make it prospective. The store rejects a naive
storage clock and requires an explicit timezone-aware instant.

The append-only SQLite controls and integrity checks protect the normal governed application path
and detect accidental or incoherent corruption. They are **not cryptographic notarization**. A
privileged actor who can rewrite the database file, drop triggers and coherently recompute metadata
is outside the first-slice threat model. Signing, external timestamping or an immutable remote audit
log would require a separately admitted capability if that stronger evidence becomes necessary.

## SQLite reference adapter

The Chapter 9B reference adapter:

- requires a file-backed database;
- stores an explicit database schema version;
- uses `BEGIN IMMEDIATE` for append decisions;
- blocks row update and deletion with SQLite triggers;
- supports immutable-ID lookup and deterministic listing by record kind;
- refuses read-mode creation of a missing database;
- performs no automatic migration.

SQLite is not declared the final production backend.

## Explicitly out of scope

- PostgreSQL/ORM/cloud database selection;
- normalized relational decomposition of financial records;
- mutable CRUD entity state;
- cryptographic signing or external timestamp attestation;
- retention, backup, encryption or multi-user policy;
- HTTP routes;
- authentication/authorization;
- frontend implementation;
- live providers or brokers;
- financial scoring, sizing, timing or optimization;
- aggregate Learning statistics or automatic feedback.

## Validation target

Chapter 9B is ready for governance review when:

- every admitted record kind round-trips through the real SQLite adapter;
- duplicate append preserves the first storage timestamp;
- a naive storage clock is rejected before persistence;
- update/delete are physically rejected;
- corrupted stored JSON and a tampered content-addressed ID are detected on load;
- mismatched database schemas fail closed;
- a missing store is not created by read mode;
- arbitrary shadow Pydantic models are rejected;
- architecture checks preserve inward dependency direction;
- the documented trust model does not overclaim protection from privileged coherent DB rewriting;
- full CI remains green on Python 3.12, Python 3.13 and the container runtime.

The reviewed implementation reached 366 passing tests with 90.38% repository coverage and strict
mypy across 94 source files before the final documentation-only close-out.

Chapter 9C may then build a human-facing workspace over the accepted API and these persisted
records without reimplementing the financial engine.
