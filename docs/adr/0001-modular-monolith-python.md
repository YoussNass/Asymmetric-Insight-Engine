# ADR 0001: Modular monolith with a Python core

- Status: Accepted
- Date: 2026-08-17

## Context

The engine combines temporal data engineering, statistical research, causal modelling,
fundamental underwriting, backtesting, and portfolio optimisation. Premature service separation
would duplicate contracts and slow validation.

## Decision

Use a Python 3.12 modular monolith with explicit domain, application, infrastructure, and
interface boundaries. Split deployable services only after measured scaling or isolation needs.

## Consequences

- Scientific, financial, and NLP libraries remain directly accessible.
- One canonical domain model is easier to test and evolve.
- Architecture tests are required to prevent boundary erosion.
- Java or other services may integrate later through stable APIs, not duplicate core logic.
