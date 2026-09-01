# Chapter 9A: Typed product API boundary

## Purpose

Chapter 9A begins AIE productization after the analytical loop is complete. It creates a stable,
strict, transport-neutral interface over the accepted application use cases without moving any
financial logic into the interface layer.

The product path remains:

```text
UNDERSTAND -> UNDERWRITE -> ALLOCATE -> EXECUTE -> LEARN
```

Chapter 9A does not add a sixth analytical stage. It makes the existing stages callable by future
runtime and UI adapters.

## Architectural classification

- Type: interface capability.
- Complexity class: `CORE NOW`.
- Governing decision: accepted ADR 0020.
- Contract version: `aie-api-v1`.

The capability lives under `interfaces` and depends inward on application/domain contracts only.
No inner layer may import the API adapter.

## Initial operations

The first slice exposes typed request/response paths for the current product-critical Chapter 6 to
Chapter 8 flow:

1. Portfolio State;
2. Portfolio Exposure;
3. Marginal Decision;
4. position HOLD review;
5. Owner Portfolio Policy construction and application;
6. explicit Replacement Decision;
7. Execution Policy;
8. Execution Plan from policy allocation;
9. Execution Plan from replacement;
10. Learning case from policy allocation;
11. Learning case from replacement;
12. Learning evaluation.

Each operation composes the canonical records it needs. A request carrying an upstream record does
not make that record trusted: the called application service must replay and verify it exactly as it
would in a direct Python invocation.

## Non-negotiable equivalence

For one deterministic request package:

```text
direct application output == API facade output
```

Equality includes canonical identifiers, fingerprints, amounts, currencies, temporal boundaries,
missing data, conflicts, assumptions, outcomes, and nested records.

The API cannot create a second derivation path.

## Serialization

Requests and thin responses use strict Pydantic models. Public API models must:

- reject unknown fields;
- be immutable after validation;
- serialize with `model_dump(mode="json")`;
- validate back from that JSON-safe representation;
- preserve Decimal/UUID/date/datetime/enums through the canonical nested models.

A non-Pydantic application result such as the Marginal Decision package may be projected into a
thin Pydantic response containing the exact `fits` tuple and exact canonical `decision` record.
That projection performs no calculation.

## Dependency injection

The product API receives preconfigured application services. This is deliberate:

- source repositories remain outside the interface;
- infrastructure providers remain outside the interface;
- Chapter 9B persistence can later supply retrieval/composition without changing financial logic;
- tests can use deterministic memory-backed builders.

The API does not create SEC clients, SQLite connections, clocks, brokers, or vendor sessions.

## Error behavior

Chapter 9A preserves fail-closed application behavior. Validation, boundary, and canonical replay
errors remain blocking exceptions at this transport-neutral layer. A future HTTP adapter may map
those exceptions to stable transport error envelopes, but it must not reinterpret a failure as a
warning or successful partial decision.

## Explicitly out of scope

- FastAPI/Flask/Starlette or any network server;
- HTTP routes and OpenAPI generation;
- authentication/authorization;
- CORS/session/rate-limit policy;
- persistence or ID-based record retrieval;
- migration/schema-store policy;
- frontend implementation;
- live provider composition;
- broker connectivity or order submission;
- new financial calculations;
- new allocation, timing, scoring, sizing, or Learning rules.

## Validation target

Chapter 9A is complete when:

- deterministic reference cases pass through the API with exact equality to direct application
  invocation;
- at least one tampered upstream package is rejected by canonical replay through the API;
- API request/response models round-trip through JSON mode;
- architecture tests prove no infrastructure import and no inner-layer reverse dependency;
- `pyproject.toml` gains no API server dependency;
- complete CI remains green on Python 3.12/3.13 and container runtime.

Only after the contract is stable should Chapter 9B introduce immutable record persistence and
retrieval. The operator workspace should then consume those real persisted contracts rather than a
parallel client-side model.
