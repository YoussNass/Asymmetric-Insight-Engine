# ADR 0025 — Local decision-first product frontend

Status: **Proposed**. Owner acceptance and merge are required; this draft does not
change any accepted financial method or universe.

## Context

The owner requested a product UI alongside the accepted operator workspace.
Chapter 12 must expose the existing decision chain without translating illustrative
ratings, graphs or chat responses into new financial authority.

## Decision proposed

Add an opt-in local React/TypeScript/Vite frontend at `/app/`, served by the existing
Python runtime through a narrow `aie-product-ui-v1` adapter. Keep the operator
workspace at `/`. No remote hosting, authentication system, broker connectivity,
database schema change, or financial engine is introduced.

Four active destinations: Home, Analysis, Portfolio, Decisions. Evidence is
contextual. Use existing canonical dimensions, gates, scenarios, exact references,
Portfolio Fits and Decision Cards. JSON intake supports only the three existing
opportunity, portfolio-state and marginal-decision operations. Preparation validates
syntax/schema only; explicit confirmation invokes the existing canonical use case.
Reading stored records verifies storage integrity, not a new financial replay; the
UI must say so. Missing dependencies block the compact decision projection.

Keep native currencies and explicit temporal boundaries. Do not add total scores,
scenario probabilities, automatic amounts, implicit FX, or synthetic market data.
TanStack Query manages requests, with automatic retries and background refresh off;
Zod validates the transport envelope. Raw domain records remain audit-visible.
Use semantic HTML, native dialogs and themed CSS; defer component/graph libraries
until an actual interaction needs them. Pin dependencies and commit the npm lockfile.

## Complexity admission

Type: interface capability, not a bounded context. Proposed class: `CORE NOW`
for inspection and explicit submission only, after acceptance.

| Gate | Bounded justification |
| --- | --- |
| Decision value | Inspect the exact evidence and trade-offs behind an existing capital decision. |
| Validatability | Cross-language contract tests and canonical output equivalence; separate usability acceptance tasks. |
| Architectural necessity | An interface projection over existing owners; no new analytical service. |
| Data sufficiency | Existing immutable records and explicit input dossiers; no new provider assumptions. |
| Explainability | Sources, missing inputs, contradictory evidence, pairwise conclusions and raw records remain accessible. |
| Maintenance cost | One small web adapter, one frontend, a lockfile and a dedicated CI job; no second persistence layer. |
| Timing | Owner requested a usable frontend; the current operator UI is principally an audit/debug surface. |

## Security and failure behavior

Bind IPv4 loopback only. Reject foreign Host/Origin/fetch-site requests, require a
session token for writes, enforce the existing 2 MB request limit, and serve only
contained build assets. Set restrictive CSP and no-store responses. No external
fonts, scripts, telemetry or credentials are embedded. This is a local trusted-user
tool, not a remotely deployable service. A token is not multi-user authentication.

Do not silently reuse stale results after a request fails. Do not automatically retry
mutations; existing idempotent storage is retained. A partially completed multi-record
submission can leave valid upstream records; failure must not be displayed as success.

## Consequences and rollback

The Python package remains independently installable. Building the optional UI needs
Node and npm; its assets are supplied explicitly to the local CLI. Structured JSON
intake remains a usability limitation, not an implementation of natural-language
analysis. Browser accessibility/visual testing and prospective usability review remain
separate acceptance work; unit coverage cannot establish either or investment skill.

Rollback: stop using `product ui` and return to the unchanged operator/CLI surface.
Canonical records and accepted application use cases require no migration or reversal.

Deferred: guided dossier authoring, natural-language draft interpretation, Discovery,
advanced PEG/causal graphics, aggregate Learning, desktop packaging, remote serving.
Each analytical capability retains its existing ADR and calibration prerequisites.
