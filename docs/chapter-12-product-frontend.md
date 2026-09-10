# Chapter 12 — Product frontend 0.1

Status: implementation for review under **proposed ADR 0025**. Not a chapter closure
or production-readiness declaration. The operator workspace remains available.

## Scope

Italian decision-first Home; saved company analysis with evidence, underwriting and
scenario views; factual native-currency portfolio; marginal decision with linked
Portfolio Fits, four alternatives and six pairwise comparisons. Source drawers show
availability, ingestion time and provenance. Original records remain inspectable.

The Home search searches saved dossiers. It is not a chat or a live ticker search.
New work imports existing structured JSON commands and requires review/confirmation.
Supported operations: `build_opportunity_state`, `build_portfolio_state`,
`build_marginal_decision`. No frontend financial calculations or decision generation.
Other stored decision kinds retain an audit view when no compact projection exists.

## Run locally

From a repository checkout with Python 3.12+ and Node 22.12+ (CI uses Node 24):

```bash
uv sync --locked --all-groups
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
```

For an isolated deterministic demonstration, create a new directory using the helper:

```bash
uv run python -m tests.product_ui_reference ./aie-ui-reference
uv run asymmetric-engine product ui \
  --evidence-database ./aie-ui-reference/evidence.sqlite \
  --product-database ./aie-ui-reference/products.sqlite \
  --frontend-dist ./frontend/dist \
  --reference-data
```

Open `http://127.0.0.1:8765/app/`. The reference banner must stay visible; these are
synthetic test dossiers, not current market facts or investment recommendations.
The helper refuses to overwrite an existing directory. It also writes
`new-capital.json`, which can be imported to exercise explicit review and submission.
Keep these databases and the JSON out of version control.

For real work, use separately initialized existing Chapter 10 stores and omit
`--reference-data`. This flag labels demonstration data; it does not classify sources
automatically. The server never initializes missing production stores. Do not expose
it through a reverse proxy or on a public interface. Stop it with Ctrl+C.

## Boundary and integrity

The adapter lives in `interfaces/product_ui.py`; the CLI composes the existing
`LocalProductRuntime`. No domain or application ownership changes. The adapter's
version is a UI transport version, not a replacement for `aie-api-v1`.

- GET session/records/detail returns no-store, same-origin responses.
- POST prepare is schema-only and does not persist records.
- POST submit invokes canonical application validation and persistence.
- Saved decision links match identifiers, fingerprints and knowledge boundaries.
- Loading verifies storage and exact fit references; it is explicitly not a financial replay.
- Portfolio money is never summed across currencies. Missing values are not zero.
- `NO_ALLOCATION` is a valid result. An execution plan is not created by this UI.
- The UI does not automatically refresh immutable snapshots or retry writes.

`tests.product_ui_contract` generates actual Python responses before frontend tests,
so the TypeScript transport is checked against the canonical runtime rather than a
separately invented mock API. Python tests cover integrity rejection, canonical output
equivalence, local-origin protection, bounded input and explicit submission.

## Acceptance still required

Technical tests are not browser/visual QA. Check keyboard-only use, focus return from
drawers, 200% text enlargement, narrow screens, loading/error states, and these tasks:

1. Locate the reason for a decision and its strongest counterargument.
2. Open the exact evidence behind a material fact and identify its knowledge boundary.
3. Distinguish an analyst assumption from a reported or derived fact.
4. Explain why a company can be attractive standalone without being the chosen allocation.
5. Recognize missing evidence and a valid no-allocation outcome without reading raw JSON.

Record completion, misunderstandings and critical errors before declaring the UI
simple, accessible or ready for routine use. Guided input is the next product-UX gap;
advanced graphs are not a prerequisite for fixing it.
