# ADR 0023: Add explicit prospective local product composition without changing decision ownership

- Status: Accepted
- Date: 2026-09-02

## Context

Chapters 2 through 8 established the analytical decision loop. Chapter 9A added the typed
`aie-api-v1` boundary, Chapter 9B added immutable product persistence, and Chapter 9C added a local
operator workspace. Those pieces are intentionally decoupled, but AIE still needs an explicit
outer composition that wires real evidence storage, upstream Causal/Underwriting builders,
downstream API services, product persistence, and the workspace into one prospectively usable local
runtime.

ADR 0020 deliberately kept Evidence, Causal Analysis, and Underwriting outside `aie-api-v1` because
source/provider composition is a different responsibility from the accepted Chapter 6 through
Chapter 8 product API. Chapter 10 must close that product gap without expanding the financial model,
weakening point-in-time rules, or turning manual input into trusted canonical output.

## Complexity Budget

| Gate | Chapter 10 evidence |
| --- | --- |
| Decision value | Enables the accepted pipeline to be operated prospectively from evidence intake through Learning rather than only through Python test composition. |
| Validatability | Composition wiring, exact builder equality, persistence identity, fail-closed store opening, and temporal source intake are deterministic. |
| Architectural necessity | Product adapters otherwise need ad-hoc glue that can accidentally bypass canonical builders or instantiate inconsistent dependencies. |
| Data sufficiency | Uses existing accepted contracts and local stores; manual source intake covers provider gaps without claiming source-universe completeness. |
| Explainability | Every operation names its owner, store, request contract, and persisted canonical result. |
| Maintenance cost | One outer composition root, one narrow upstream intake facade, and one conservative local-file source adapter. |
| Timing | Product API, immutable persistence, and local workspace already exist; composition is the smallest next step before accumulating prospective Learning records. |

Architectural type: product composition capability.
Classification: `CORE NOW`.

## Decision

### Add one explicit outer composition root

Chapter 10 introduces `local-product-runtime-v1` at the package outer layer. This is the only
runtime module intentionally allowed to know application services, infrastructure adapters, and
interface adapters at the same time.

Inner domain, application, and interface modules must not depend on the composition root. The
composition root adds no financial calculations and owns no analytical result.

The local runtime wires shared canonical instances for:

- Causal Analysis;
- standalone Underwriting / Opportunity State;
- Portfolio State and Exposure;
- Marginal Decision and HOLD review;
- owner policy and Replacement;
- Execution Policy and Execution Plan;
- Learning case and evaluation;
- `aie-api-v1`;
- Chapter 9B immutable product persistence;
- Chapter 9C operator workspace.

Using shared canonical instances is operational composition only. It does not merge bounded-context
ownership.

### Keep upstream intake separate from `aie-api-v1`

Chapter 10 introduces `aie-intake-v1` as a strict typed interface for only two upstream operations:

1. `CausalAnalysisDraft -> CausalAnalysis` through `BuildCausalAnalysis`;
2. `UnderwritingDraft -> OpportunityState` through `BuildOpportunityState`.

The intake facade delegates exactly to those canonical application owners and returns their exact
results. It must not extract claims, manufacture assumptions, fill missing values, create scores,
or modify the drafts.

`aie-api-v1` remains unchanged and continues to own the accepted Chapter 6 through Chapter 8
product-facing operations. Provider/evidence concerns are not pushed into that contract.

### Persist upstream canonical results exactly

A successful `aie-intake-v1` result is appended unchanged through the accepted Chapter 9B product
store. Persistence remains storage evidence only; it never substitutes for Causal or Underwriting
verification.

The operator can then use the Chapter 9C write-enabled workspace for the existing `aie-api-v1`
downstream path. No generic raw-object import into the immutable product store is introduced.

### Require explicit initialization and fail closed on normal runtime open

The local product runtime uses two explicit durable stores:

- the Chapter 3 source-evidence ledger;
- the Chapter 9B immutable product-record store.

`product init` is the explicit action that creates their schemas. Normal runtime construction opens
both with initialization disabled. A missing or structurally invalid store must fail rather than be
silently created as a side effect of browsing, intake, or workspace startup.

This also tightens read-only opening of the SQLite evidence ledger so it mirrors the already accepted
fail-closed product-store behavior.

### Admit conservative local manual evidence for provider gaps

Chapter 10 adds a local-file evidence adapter only to make prospective operation possible when no
specific automated provider exists yet.

The operator must explicitly declare source identity and descriptive metadata. The adapter reads the
exact local bytes and always uses:

- provider `local-manual`;
- `AvailabilityBasis.OBSERVED_AT_INGESTION`;
- no caller-supplied historical `available_at`.

The ingestion clock therefore becomes the earliest knowledge-availability boundary AIE may claim
for that locally supplied version. An old report imported today is knowable to live-system replay
only from today's ingestion timestamp, unless a future dedicated provider can independently prove
its historical public availability.

Manual intake is evidence transport, not analytical authority. Claims, evidence items, causal
mechanisms, financial facts, scenarios, and decisions still have to satisfy their existing canonical
contracts.

### Keep the first prospective runtime local and operationally narrow

The existing Chapter 9C loopback-only WSGI workspace and anti-CSRF control remain unchanged. Chapter
10 does not add remote binding, user authentication, TLS, multi-user concurrency, deployment
orchestration, live brokerage, or order submission.

It also does not add Market State, automated sizing, source discovery, AI extraction, financial
defaults, automatic Learning feedback, or a production database decision.

## Consequences

### Positive

- AIE can be run as one coherent local product rather than assembled ad hoc in a notebook;
- Causal Analysis and Underwriting gain a typed product intake without destabilizing `aie-api-v1`;
- exact upstream canonical outputs enter the same immutable product history as later decisions;
- manual source gaps can be bridged prospectively without backdating knowledge availability;
- runtime startup cannot silently manufacture missing evidence/product stores;
- the first prospective Learning cases can now be accumulated through a governed operational path.

### Negative

- upstream analytical drafts are still explicit human/application inputs rather than automated
  extraction products;
- local manual evidence cannot reconstruct historical availability and is deliberately conservative;
- two SQLite files remain local reference stores rather than a production data platform;
- the operator still needs to prepare structurally complete typed JSON inputs for complex use cases;
- the local workspace is not remotely deployable or multi-user.

## Rejected alternatives

### Extend `aie-api-v1` with provider and evidence concerns

Rejected because it would mix upstream source composition into the already accepted Chapter 6-8
product contract and enlarge its responsibility without decision value.

### Import arbitrary JSON directly into the product store

Rejected because storage would become a route around canonical application owners and typed schema
validation.

### Let manual evidence declare an old `available_at`

Rejected because it would create a direct hindsight/backdating path. Local manual evidence is
observed only when AIE actually ingests it.

### Auto-create stores whenever runtime code opens a path

Rejected because a typo or wrong path could silently create a new empty source of truth and make a
prospective session appear valid.

### Build automated discovery/extraction before prospective operation

Rejected under the complexity budget. Provider breadth and automated extraction graduate only when
prospective operation measures them as bottlenecks and their outputs can be validated.

### Add broker connectivity or remote product deployment now

Rejected because a working decision-support product does not require order submission or a remote
multi-user threat model. Both need separate future ADRs.

## Acceptance criteria

ADR 0023 may move to `Accepted` only when:

1. one explicit outer composition root wires evidence, accepted application owners, product storage,
   `aie-api-v1`, and the Chapter 9C workspace;
2. domain, application, and interface layers do not depend on that composition root;
3. `aie-intake-v1` contains concrete typed Causal and Underwriting requests and no infrastructure
   dependency;
4. direct canonical application invocation and `aie-intake-v1` produce exactly equal results;
5. successful intake results are persisted unchanged as admitted Chapter 9B records;
6. the existing `aie-api-v1` contract is not expanded or redefined by Chapter 10;
7. normal runtime construction fails closed when either local durable store is missing or invalid;
8. store creation occurs only through an explicit initialization operation in the new product flow;
9. local manual evidence preserves exact bytes, requires explicit identity/provenance metadata, and
   always uses observed-at-ingestion availability with no backdating path;
10. the composed workspace remains loopback-only and retains the accepted write-token control;
11. an integration test crosses real evidence storage -> Causal intake -> Underwriting intake ->
    immutable product storage -> downstream workspace/API composition;
12. no financial formula, score, sizing rule, Market State, automatic Learning feedback, broker,
    remote auth, production database, or source-discovery engine enters the slice;
13. lint, formatting, mypy, pytest, package, Python 3.12/3.13 and container CI pass on the exact PR
    head;
14. the owner explicitly accepts ADR 0023. Merge authorization remains a separate governance gate.

## Acceptance record

The owner accepted this ADR on 2026-09-03 after the Chapter 10 review head satisfied the local
architecture, lint, formatting, type-checking, test, doctor, and package-build gates. Authorization
to merge Draft PR #31 remains a separate governance decision.
