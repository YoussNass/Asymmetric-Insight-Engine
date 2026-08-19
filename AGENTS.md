# Agent Operating Contract

These instructions apply to every automated contributor working in this repository.

## Source of truth

- The repository and its accepted pull requests are the canonical implementation record.
- Read the system constitution and relevant ADRs before changing architecture.
- Never infer that a discussed feature is implemented; verify the code and tests.

## Architecture boundaries

- `domain` must not import from `application`, `infrastructure`, or `interfaces`.
- `application` may depend on `domain`, never the reverse.
- External services, databases, AI models, and data vendors belong behind infrastructure ports.
- User interfaces must call application use cases rather than contain financial logic.
- Shared facts must have one canonical owner; do not duplicate scoring across engines.

## Epistemic and financial safety

- Preserve `effective_at`, `available_at`, `recorded_at`, `as_of`, and `knowledge_mode`
  semantics.
- Never make future data visible to a historical calculation.
- Never treat evidence ingested after `as_of` as present in a live-system replay.
- Never invent missing values or silently forward-fill event data.
- Keep observed data, statistical results, inferences, hypotheses, and judgements distinct.
- Every material claim needs provenance, confidence, and explicit invalidation conditions.
- Never add live brokerage execution without an approved ADR and explicit user authorization.
- Never commit credentials, personal portfolio exports, licensed datasets, or vendor payloads.

## Change workflow

- Work on an `agent/*` branch and open a draft pull request.
- Do not push directly to `main` or merge without explicit user approval.
- Keep commits focused and describe the intent, not only the files changed.
- Add or update tests for every behavioral change.
- Update documentation when public contracts or architecture change.

## Required checks

Run before publication:

```bash
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
uv run asymmetric-engine doctor
```

Container changes must also pass:

```bash
docker build --tag asymmetric-insight-engine:check .
docker run --rm asymmetric-insight-engine:check
```

If a local check cannot run, report the exact blocker and rely only on the corresponding green
CI job; do not claim local success.
