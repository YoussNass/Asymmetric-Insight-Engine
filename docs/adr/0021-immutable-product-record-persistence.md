# ADR 0021: Persist immutable product records without making storage a decision authority

- Status: Proposed
- Date: 2026-09-01

## Context

Chapter 9A established `aie-api-v1`, but accepted product records still live only in process memory
unless they happen to belong to the separate Chapter 3 evidence ledger. Large stateless payloads are
therefore still required between use cases, and Chapter 8 cannot yet retain durable evidence of
when a Learning case was first preserved by AIE.

Persistence must solve durability and retrieval without becoming a second owner of financial
validation. A database row must never make a modified Portfolio State, capital decision, Execution
Plan, or Learning record trustworthy merely because it was stored successfully.

## Complexity Budget

| Gate | Chapter 9B evidence |
| --- | --- |
| Decision value | Enables durable replay, ID-based retrieval, and prospective Learning-case creation evidence. |
| Validatability | Stored JSON, SHA-256, content-addressed ID, schema version, typed reconstruction, and append-only behavior are deterministic. |
| Architectural necessity | Chapter 9C should consume persisted real records rather than keep complete product state only in browser/client memory. |
| Data sufficiency | Uses accepted Pydantic records and the standard-library SQLite reference adapter; no new market data is required. |
| Explainability | Record kind, schema, first storage time, hash, payload, and migration failure are explicit. |
| Maintenance cost | One application port plus one SQLite reference adapter; no ORM, server, distributed store, or production database dependency. |
| Timing | 9A is canonical; persistence is the required predecessor to the operator workspace. |

Architectural type: persistence capability.
Classification: `CORE NOW`.

## Decision

### Add a storage-agnostic application port

Chapter 9B introduces an application-layer product persistence port with three operations:

- append one admitted immutable record;
- load one record by immutable storage ID;
- list stored records by admitted kind.

The application module may depend on domain models. It must not import infrastructure or
interfaces. Concrete databases remain infrastructure adapters.

### Admit exact canonical record types

The first registry admits the product-critical immutable records required to bridge the accepted
pipeline into the workspace:

- Causal Analysis;
- Opportunity State;
- Portfolio State Draft and canonical Portfolio State;
- Portfolio Exposure and Portfolio Fit;
- Marginal Decision and Position Review;
- Owner Portfolio Policy and policy-constrained decision;
- Replacement Decision;
- Execution Policy and Execution Plan;
- Decision Learning Case and Decision Learning Evaluation.

Registration is by exact model type. An arbitrary caller-defined Pydantic model is not silently
stored as if it were a canonical AIE product record.

Raw evidence bytes remain owned by the Chapter 3 evidence ledger. Chapter 9B does not duplicate
source payload bytes; admitted records retain their existing embedded source references and
fingerprints.

### Use a content-addressed storage identity

Every persisted record is serialized to deterministic canonical JSON and receives:

- record kind;
- record JSON schema version;
- SHA-256 of the exact canonical UTF-8 JSON;
- UUIDv5 storage ID derived from kind, schema version, and payload hash;
- first `stored_at` timestamp;
- envelope version.

The storage ID is a persistence identity, not a replacement for a record's canonical financial ID
or fingerprint.

### Preserve the first AIE storage timestamp

`stored_at` is supplied by an injected timezone-aware clock when AIE first appends a record.
Re-appending byte-identical canonical content is idempotent and returns the original stored
envelope, including the original `stored_at`.

This timestamp proves only when this local AIE store first preserved that exact content. It does
not prove original market availability, original human decision time, or that a historical record
was not backfilled later. For prospective Learning, a case persisted near T1 provides stronger
creation evidence than a case first stored after its outcome horizon.

The timestamp is operational audit evidence, not cryptographic notarization. The first slice assumes
that writes occur through the governed repository and that the underlying database file is protected
by ordinary host access controls. A privileged actor who can rewrite the database file, drop
triggers, and coherently recompute metadata is outside this integrity model. Cryptographic signing,
external timestamping, KMS-backed attestations, and append-only remote logs require a future ADR if
that threat model becomes decision-relevant.

### Storage integrity and canonical replay remain different gates

Loading a record must verify:

1. admitted envelope and record schema versions;
2. exact payload SHA-256;
3. content-addressed storage UUID;
4. validation into the exact registered Pydantic type;
5. byte-for-byte canonical JSON reproduction.

Passing those checks proves storage integrity only. Before a loaded Portfolio, Execution, or
Learning record influences a downstream decision, its canonical application owner must still replay
and verify it according to the existing Chapter 6/7/8 invariants.

### Records are append-only

No persisted product record is updated or deleted in place. A material revision creates new
canonical content and therefore a new storage ID. The reference SQLite adapter enforces no-update
and no-delete triggers.

### Migrations fail closed

The SQLite reference store records an explicit database schema version. A mismatched database or
record JSON schema raises a migration error; Chapter 9B performs no silent in-place migration and
no best-effort reinterpretation of old payloads.

A future migration must be explicit, tested, reversible at the storage-copy level, and must never
rewrite the historical meaning of a canonical record.

### SQLite remains a reference adapter, not the production database decision

Chapter 9B adds a file-backed SQLite adapter because it is deterministic, dependency-free, and
sufficient to validate persistence semantics and the first operator workspace. It does not reverse
the longer-term architecture direction toward replaceable production storage.

No PostgreSQL driver, ORM, object store, distributed lock, cloud deployment, encryption/key
management system, backup scheduler, or retention service is admitted in this slice.

## Consequences

### Positive

- accepted product records can survive process restarts;
- the workspace can retrieve by immutable ID rather than trust client memory;
- first local persistence time becomes inspectable;
- accidental or incoherent row corruption is detected independently of Pydantic shape validation;
- storage can later be replaced without changing domain contracts;
- Chapter 8 can begin collecting stronger prospective evidence without claiming backfilled records
  were prospective.

### Negative

- SQLite is suitable only as a local/reference product store;
- the first registry must be extended explicitly when new canonical product record types are
  admitted;
- records may duplicate nested canonical objects because normalization is deliberately avoided in
  the first append-only slice;
- the local store is not a cryptographic anti-tamper ledger against a privileged database operator;
- no retention, backup, encryption, multi-user concurrency, or production disaster-recovery policy
  exists yet.

## Rejected alternatives

### Treat the database row as canonical verification

Rejected because storage integrity cannot replace Portfolio, Execution, Underwriting, or Learning
replay.

### Mutate one row per logical entity

Rejected because overwriting would destroy historical decision evidence and make prospective audit
ambiguous.

### Adopt PostgreSQL or an ORM immediately

Rejected because backend selection and deployment complexity are unnecessary to prove the
append-only persistence contract and operator workflow.

### Add cryptographic notarization in Chapter 9B

Rejected because the current threat model is local operational auditability, not hostile database
administration. Signing, external timestamps, or an immutable remote log should be admitted only if
that stronger evidence changes a real governance decision.

### Store arbitrary dictionaries or caller-defined models as canonical records

Rejected because it would create an ungoverned shadow schema beside accepted domain/application
owners.

### Automatically migrate old schemas on read

Rejected because silent reinterpretation is incompatible with auditability and point-in-time
replay.

## Acceptance criteria

ADR 0021 may move to `Accepted` only when:

1. the persistence port lives in application and has no infrastructure/interface dependency;
2. admitted product record types are explicit and arbitrary shadow models are rejected;
3. storage IDs are deterministic from exact kind/schema/payload content;
4. the first `stored_at` is generated by an injected timezone-aware clock and survives idempotent re-append;
5. SQLite physically blocks update and delete of product records;
6. exact payload hash, storage ID, schema and typed reconstruction are revalidated on load;
7. accidental/incoherent corruption remains blocking even if database guards are bypassed;
8. the documented trust model does not claim cryptographic protection against privileged coherent database rewriting;
9. database and record-schema mismatches fail closed and require explicit migration;
10. read-only opening of a missing store cannot create it as a side effect;
11. documentation states that loaded decision records still require canonical application replay;
12. no production database, ORM, HTTP server, broker, financial score, sizing, timing, or Learning feedback enters the slice;
13. lint, formatting, mypy, pytest, package, Python 3.12/3.13 and container CI pass on the exact PR head;
14. the owner explicitly accepts ADR 0021. Merge authorization remains a separate governance gate.
