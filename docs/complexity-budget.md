# Complexity Budget

## Purpose

AIE should be sophisticated in reasoning and simple in decision flow. Complexity is admitted only
when it improves a real capital decision, preserves epistemic safety, or is required for audit and
reproducibility.

The budget is a set of gates, not another weighted score. A capability cannot compensate for
failing one gate by scoring highly on another.

## Admission gates

Every proposed capability, metric, policy, state, or bounded context must answer all seven
questions before active implementation.

| Gate | Required evidence | Failure response |
| --- | --- | --- |
| Decision value | Identify the decision that changes: what to own, how much, when, replacement, invalidation, or learning | Reject if it changes no decision and is not required for provenance, audit, or safety |
| Validatability | State how usefulness or assumptions can be falsified prospectively | Keep experimental or defer |
| Architectural necessity | Explain why an existing owner cannot represent it as a capability, policy, state, or metric | Demote; do not create a new engine or bounded context |
| Data sufficiency | Identify point-in-time data, provenance, coverage, licensing, and realistic acquisition path | Defer or use an explicit simpler proxy |
| Explainability | Show the input, delta, uncertainty, and reason visible in the decision output | Reject from active decisions |
| Maintenance cost | Account for code, tests, data operations, monitoring, calibration, and migration | Simplify, narrow, or defer |
| Timing | Show the measured failure or current user decision that requires the capability now | Defer |

Foundational temporal integrity, provenance, security, and audit controls may support every
decision rather than one decision. They still require a concrete failure mode and the simplest
adequate implementation.

## Required classification

Every roadmap item and pull request must assign one of these classes.

| Class | Meaning | Runtime authority |
| --- | --- | --- |
| `CORE NOW` | All gates pass and the capability is necessary for the current minimum complete decision flow | May support active decisions after normal architecture approval |
| `SIMPLE POLICY` | The rule changes a decision but does not justify a new bounded context or engine | Lives inside the context that owns the decision |
| `EXPERIMENTAL` | Decision value is plausible, but validation or data sufficiency is incomplete | Shadow output only; cannot gate, rank, size, or allocate |
| `DEFER` | Data, validation, maintenance, or timing does not justify implementation now | Documented backlog only |
| `REJECT` | The proposal violates an invariant or has inadequate decision value, explainability, or falsifiability | Must not enter the active architecture |

Classification is versioned. `DEFER` and `EXPERIMENTAL` preserve an idea without pretending it is
ready. `REJECT` applies to the evaluated formulation; a materially different proposal may be
reviewed later with new evidence.

## Architectural type before naming

Classify the thing before giving it an `Engine` or service name.

| Type | Test |
| --- | --- |
| Domain / bounded context | Has distinct language, invariants, ownership, lifecycle, and change reasons |
| Capability | Performs a coherent function inside an existing context |
| Policy | Selects among valid alternatives owned by an existing decision context |
| Data / state | Records facts or an immutable snapshot; it does not decide |
| Metric | Describes one inspectable property; it does not become a recommendation by itself |
| Experimental extension | Tests a hypothesis without active decision authority |

A new bounded context is justified only when ownership and lifecycle would otherwise become
ambiguous or coupled. File size, the number of concepts, or the presence of a named business rule
is not sufficient.

## Progressive sophistication

The mandatory sequence is:

```text
simple implementation
-> prospective measurement
-> observed failure
-> narrow complexity addition
-> validation against the simpler baseline
```

An advanced method must record:

1. the simpler baseline it replaces or augments;
2. the observed failure case;
3. the additional data and maintenance burden;
4. the prospective validation plan;
5. the rollback path;
6. the effect on user-facing explanations.

Without those records, advanced optimization, dynamic correlation, automated sizing, scenario
probabilities, and factor attribution remain deferred.

## Experimental isolation and graduation

Experimental outputs must:

- be clearly labelled with method and calibration status;
- retain missing inputs and assumptions;
- never silently replace `unknown` with zero;
- remain outside active eligibility, ranking, sizing, allocation, and execution defaults;
- be compared prospectively with the current simpler policy;
- be removable without changing canonical decision records.

An experiment graduates only after an ADR or an approved update to its owning ADR identifies the
evidence that satisfied the admission gates. Test coverage proves implementation behavior; it does
not by itself validate investment usefulness.

## Decision-first review

Every capability must map to at least one decision:

- `WHAT TO OWN`;
- `HOW MUCH`;
- `WHEN`;
- `WHAT TO REPLACE`;
- `WHEN THE THESIS FAILED`;
- `WHAT WE LEARNED`.

If the mapping is indirect, the capability must be necessary for point-in-time truth, provenance,
audit, reproducibility, or safety.

## No complexity compression through a magic score

Reducing the number of outputs by averaging them into a universal score is not simplification.
Prefer categorical gates, multidimensional states, dominance, explicit trade-offs, scenario
ranges, uncertainty, and invalidation conditions.

Any contextual scalar remains subject to ADR 0003 and ADR 0006. An uncalibrated scalar is an
experiment and cannot become an active default.

## Pull-request evidence

A pull request that adds an analytical capability must state:

- architectural type and classification;
- owning decision and bounded context;
- simplest considered representation;
- required data and point-in-time coverage;
- validation method and baseline;
- explainable effect on the decision card;
- maintenance burden and rollback path;
- explicitly deferred adjacent capabilities.

The canonical delivery order and deferred capability register are maintained in
[`roadmap.md`](roadmap.md).
