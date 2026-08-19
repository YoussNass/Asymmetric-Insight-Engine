## What changed

<!-- Describe the complete behavioral and architectural scope. -->

## Why

<!-- Explain the problem, decision, or requirement this addresses. -->

## Validation

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy src tests`
- [ ] `uv run pytest`
- [ ] `uv run asymmetric-engine doctor`
- [ ] `docker build --tag asymmetric-insight-engine:check .`
- [ ] `docker run --rm asymmetric-insight-engine:check`

## Point-in-time and data review

- [ ] No future information can leak into historical calculations.
- [ ] The knowledge mode distinguishes reconstruction from live-system replay.
- [ ] Missing and conflicting evidence remains explicit.
- [ ] No credential, personal portfolio export, or restricted dataset is included.

## Limitations and follow-ups

<!-- State known limitations; do not hide incomplete work. -->
