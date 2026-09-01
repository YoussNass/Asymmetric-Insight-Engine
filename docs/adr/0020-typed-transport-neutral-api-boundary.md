# ADR 0020: Add a typed transport-neutral API boundary before HTTP and frontend

- Status: Proposed
- Date: 2026-09-01

## Context

Chapters 2 through 8 now provide the minimum complete analytical decision flow:

```text
UNDERSTAND -> UNDERWRITE -> ALLOCATE -> EXECUTE -> LEARN
```

The canonical application services are usable from Python, but there is not yet a stable product
boundary that a future HTTP server, desktop client, or operator workspace can call without knowing
internal builder details.

The next productization step must not copy financial logic into an interface, create a second set of
financial models, trust caller-supplied canonical identities without replay, or prematurely select
an HTTP framework before the request/response contract itself is proven stable.

The minimum useful question is:

> can an outer transport submit strict, versioned requests to the accepted application use cases
> and receive JSON-safe canonical outputs while preserving exactly the same validation, replay,
> fingerprints, amounts, temporal boundaries, and fail-closed behavior as direct Python use?

## Complexity Budget

| Gate | Chapter 9A evidence |
| --- | --- |
| Decision value | Makes the accepted decision pipeline callable by a product interface without duplicating decision logic. |
| Validatability | Direct-call and API-boundary outputs can be compared for exact equality; JSON round trips and tamper failures are deterministic. |
| Architectural necessity | Interfaces are the canonical outer adapter layer and must not force a future UI to import application internals directly. |
| Data sufficiency | Uses only existing accepted Pydantic/domain records and application services; no new market/provider data is required. |
| Explainability | Operation, contract version, request model, output model, and validation failure remain explicit. |
| Maintenance cost | One transport-neutral facade and strict schemas; no web server, auth, OpenAPI framework, persistence, or frontend dependency. |
| Timing | Chapter 8 completed the analytical loop; a stable callable boundary is now required before persistence and UI work. |

Architectural type: interface capability.
Classification: `CORE NOW`.

## Decision

### Introduce one versioned product API contract in `interfaces`

Chapter 9A adds a transport-neutral API capability under `src/asymmetric_engine/interfaces`.
It may import application services and domain contracts. It must not be imported by `domain` or
`application`, and it must not import infrastructure adapters.

The initial contract version is:

```text
aie-api-v1
```

Changing the semantic request/response contract requires a new version rather than silently
reinterpreting an existing payload.

### Reuse canonical models instead of creating financial DTO copies

Operation-specific request models may compose the accepted domain inputs and immutable upstream
records directly. The API boundary must not redefine holdings, money, Portfolio Exposure,
Opportunity State, capital decisions, Execution Plans, or Learning records in parallel DTOs that
could drift from their canonical owners.

For application responses that are not themselves Pydantic records, the interface may provide a
thin response projection containing the exact canonical records. It may not recalculate them.

### The adapter delegates; it never decides

The API facade performs only:

1. strict request-model validation;
2. delegation to the injected canonical application service;
3. thin response projection when necessary;
4. JSON-safe serialization through the existing Pydantic contracts.

It must not:

- calculate financial metrics;
- change or infer a capital amount;
- select an alternative;
- recompute HHI or exposure;
- infer replacement targets;
- alter friction or liquidity;
- invent execution timing;
- rewrite invalidation conditions;
- calculate Learning metrics independently;
- catch an integrity failure and downgrade it to a warning.

### Upstream records are replayed by their canonical application owner

A request may carry complete immutable upstream records needed by a use case, but the API facade
does not trust their identifiers or fingerprints. It passes them to the canonical application
builder, whose existing verification path must rebuild and verify them before use.

The API boundary must therefore produce the same result or the same blocking integrity failure that
a direct application invocation would produce.

### Cover the accepted Chapter 6 through Chapter 8 product path

The first contract exposes typed methods for:

- building Portfolio State;
- building Portfolio Exposure;
- building a Marginal Decision package;
- recording a position `HOLD` review;
- building and applying Owner Portfolio Policy;
- building one explicit Replacement Decision;
- building Execution Policy;
- building Execution Plan from policy allocation or replacement;
- opening a Learning case from policy allocation or replacement;
- building a Learning evaluation.

Evidence ingestion, Causal construction, and Underwriting remain callable through their existing
application paths but are not forced into the first product API slice. Their provider/source-byte
requirements need a separately wired product composition root rather than an interface shortcut.
This does not change their canonical status or ownership.

### Keep HTTP, authentication, persistence, and deployment out of 9A

Chapter 9A intentionally does not add FastAPI, Flask, Starlette, an ASGI server, routes, sockets,
authentication, CORS, sessions, database persistence, or cloud deployment.

Those are outer transport/runtime choices. A later HTTP adapter should consume `aie-api-v1` rather
than define a second contract.

The project therefore adds no runtime dependency solely for Chapter 9A.

### Use dependency injection for application services

The facade receives its canonical application services through construction. It does not instantiate
infrastructure providers or repositories internally. This keeps source repositories, persistence,
clock, and future vendor adapters outside the interface contract and makes deterministic tests
possible.

### JSON round trip is part of the contract

Every public request and response model introduced by 9A must serialize in Pydantic JSON mode and
validate back into an equivalent object. Decimal, UUID, date/time, enums, money, and knowledge
boundaries must retain their existing semantics.

JSON-safe does not mean that the interface may coerce invalid values, replace unknown with zero, or
remove missing/conflict disclosures.

## Consequences

### Positive

- A future UI can call one stable product boundary rather than internal builders.
- Financial logic remains in application/domain owners.
- Direct Python and product-interface execution are testable against the same canonical outputs.
- No premature HTTP framework or deployment dependency enters the core package.
- Persistence can be designed around stable versioned records in Chapter 9B.

### Negative

- 9A is not yet a network service and cannot be called from a browser directly.
- Requests can be large because the stateless facade may carry immutable upstream records before
  Chapter 9B persistence provides ID-based retrieval.
- Evidence/Causal/Underwriting product composition remains outside the first slice because source
  verification requires explicit repository/provider wiring.
- Authentication, authorization, rate limits, and transport error mapping remain future concerns.

## Rejected alternatives

### Add FastAPI immediately

Rejected because route design, server lifecycle, authentication, deployment, and OpenAPI would be
additional decisions before the underlying product contract has been stabilized.

### Let the frontend call domain models directly

Rejected because it would bypass canonical application replay and encourage financial logic in the
client.

### Duplicate all domain models into API DTOs

Rejected because two financial schemas would drift and create ambiguous ownership.

### Use one untyped `dict[str, Any]` dispatch payload

Rejected because operation-specific validation and static typing are part of the product safety
boundary.

### Add persistence in the same slice

Rejected because storage lifecycle, append/replace semantics, migration, retrieval by immutable ID,
and creation-time attestation have distinct invariants and belong to Chapter 9B.

## Acceptance criteria

ADR 0020 may move to `Accepted` only when:

1. `aie-api-v1` is defined in the interface layer with no domain/application reverse dependency;
2. no new HTTP/runtime framework dependency is introduced;
3. public operations use concrete typed request models rather than an untyped generic payload;
4. accepted Chapter 6/7/8 product operations delegate to canonical application services;
5. direct application invocation and API invocation produce exactly equal canonical outputs on the deterministic reference cases;
6. tampered upstream records remain blocking through canonical replay;
7. request and response models survive JSON-mode round trip validation;
8. the API performs no financial calculation, sizing, scoring, replacement search, timing inference, or Learning recomputation;
9. architecture tests enforce that the API adapter cannot import infrastructure and that inner layers cannot import it;
10. lint, formatting, mypy, pytest, package, Python 3.12/3.13, and container CI pass on the exact PR head;
11. documentation clearly keeps HTTP, persistence, authentication, frontend, and broker actions out of scope;
12. the owner explicitly accepts ADR 0020 and authorizes the Chapter 9A merge.
