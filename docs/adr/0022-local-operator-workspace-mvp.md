# ADR 0022: Add a local operator workspace without moving decision logic into the UI

- Status: Proposed
- Date: 2026-09-01

## Context

Chapter 9A defines strict transport-neutral application requests and responses. Chapter 9B proposes immutable product persistence. AIE still lacks the human-facing surface needed to inspect persisted records and exercise accepted use cases without writing Python glue for every interaction.

The first workspace must improve usability without becoming a second financial engine, a remote production service, or a browser-owned source of canonical truth.

## Decision

Chapter 9C introduces `operator-workspace-v1` as an interface-layer coordinator plus a dependency-free local browser adapter.

The workspace may list and load storage-verified Chapter 9B records, render exact canonical JSON, render existing Decision/Execution Card projections, and invoke Chapter 9A operations when a fully configured `AieProductApi` and immutable product store are injected.

A successful write invocation persists only the exact canonical output records returned by `aie-api-v1`. The workspace does not repair, infer, resize, rank, score, time, optimize, or reinterpret financial inputs or outputs.

The default CLI composition is deliberately read-only. It opens an existing SQLite reference product store with `initialize_schema=False`; browsing cannot create a missing database as a side effect. Production write composition remains deferred until real provider/application dependencies are deliberately configured.

The browser adapter binds only to IPv4 loopback. A write-enabled composition requires a server-generated local write token, checked with constant-time comparison before request dispatch, to reduce cross-origin request-forgery risk against localhost. This token is a local anti-CSRF control, not user authentication or authorization. Remote/multi-user deployment remains out of scope.

The adapter uses the Python standard-library WSGI server. No FastAPI, Flask, Streamlit, frontend framework, JavaScript build, broker adapter, auth system, or production deployment dependency is admitted.

## Integrity rules

- Storage verification is visibly distinct from canonical financial replay.
- Read-only mode rejects mutation before parsing a purported API payload.
- Unknown operations are rejected rather than dynamically dispatched.
- Request bodies have an explicit maximum size.
- Validation and integrity failures remain blocking.
- Persisted revisions are new immutable records; the workspace exposes no update/delete action.
- Learning output has no automatic capital-feedback action.
- `NOW`/`STAGED` remain plans, not fills or broker submissions.

## Consequences

AIE gains a minimal usable local workspace and a concrete composition path over real persistence. The surface is intentionally plain: it proves product workflow and auditability before investing in a richer frontend.

It is not a production web application. There is no login, TLS termination, remote binding, multi-user concurrency model, live broker, live market-data composition, or automated feedback loop.

## Acceptance criteria

ADR 0022 may move to `Accepted` only when:

1. the workspace coordinator remains in interfaces and inner layers do not depend on it;
2. the coordinator imports no infrastructure adapter;
3. read-only CLI composition opens only an existing Chapter 9B store;
4. persisted records can be listed, loaded, and rendered without financial recalculation;
5. write-enabled orchestration accepts only the explicit Chapter 9A operation registry and persists exact canonical outputs;
6. read-only mode blocks writes before payload parsing;
7. browser writes require a server-generated local anti-CSRF token before dispatch;
8. the server binds only to loopback and request bodies are bounded;
9. no remote auth, broker, optimizer, timing engine, aggregate Learning statistic, or automatic feedback is introduced;
10. architecture, unit, integration, Python 3.12/3.13, package and container CI are green on the exact PR head;
11. the owner explicitly accepts ADR 0022. Merge authorization remains a separate governance gate.
