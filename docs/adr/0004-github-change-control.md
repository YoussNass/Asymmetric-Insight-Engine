# ADR 0004: GitHub branch and pull-request change control

- Status: Accepted
- Date: 2026-08-17

## Context

The project requires autonomous implementation without losing auditability or allowing silent
changes to the canonical branch.

## Decision

Automated contributors may inspect the repository, create `agent/*` branches, implement and test
changes, publish focused commits, open draft pull requests, and repair CI. Merging to `main`,
production deployment, paid services, secrets, destructive actions, and live trading integrations
require explicit approval.

## Consequences

- `main` remains stable and reviewable.
- Every chapter has a durable diff, validation record, and decision trail.
- Autonomy increases without transferring irreversible authority.
