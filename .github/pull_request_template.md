## What changed

<!-- Describe the complete behavioral and architectural scope. -->

## Why

<!-- Explain the problem, decision, or requirement this addresses. -->

## Complexity budget

<!-- For a new analytical capability, complete every field. Use N/A with a reason for changes
that do not alter analytical scope. -->

- Architectural type:
- Classification (`CORE NOW`, `SIMPLE POLICY`, `EXPERIMENTAL`, `DEFER`, or `REJECT`):
- Decision supported or safety/audit invariant:
- Simplest baseline and observed failure:
- Point-in-time data and coverage requirements:
- Validation method and rollback path:
- Maintenance burden and explicitly deferred adjacent scope:

- [ ] A named policy or metric has not been promoted into a new engine without an approved ADR.
- [ ] Experimental output has no active gate, rank, size, allocation, or execution authority.
- [ ] Missing data remains unknown rather than zero risk or diversification.

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
