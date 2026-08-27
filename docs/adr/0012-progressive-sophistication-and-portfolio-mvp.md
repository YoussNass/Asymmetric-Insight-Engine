# ADR 0012: Apply progressive sophistication to the Portfolio MVP

- Status: Accepted
- Date: 2026-08-27

## Context

ADR 0006 protected the ownership boundaries exposed by the first portfolio-intelligence spike.
The spike also demonstrated a second risk: implementing portfolio state, recursive look-through,
structural correlation, factor and catalyst overlap, risk aggregation, scoring, sizing,
replacement, market overlay, and decision audit together would create a large model before AIE has
real portfolio inputs or prospective evidence that those methods improve capital decisions.

The mission remains sophisticated: given knowable information at T0, the current portfolio,
competing active and passive alternatives, costs, taxes, risk, and uncertainty, explain the best
marginal use of capital. The architecture should reach that decision through the smallest
complete and testable flow rather than through one engine per named concept.

## Decision

### Adopt the Complexity Budget

Every new capability must pass the seven gates in
[`docs/complexity-budget.md`](../complexity-budget.md): decision value, validatability,
architectural necessity, data sufficiency, explainability, maintenance cost, and timing.

Capabilities are classified as `CORE NOW`, `SIMPLE POLICY`, `EXPERIMENTAL`, `DEFER`, or `REJECT`.
The classification is conjunctive and cannot be replaced by a weighted complexity score.

### Use five stages as a product model, not a service topology

The user-facing flow is:

```text
UNDERSTAND -> UNDERWRITE -> ALLOCATE -> EXECUTE -> LEARN
```

Evidence and the Temporal shared kernel remain cross-cutting foundations. The flow does not force
exactly five bounded contexts or deployable services.

The boundaries protected by ADR 0006 remain unchanged:

- standalone Underwriting is upstream and immutable;
- portfolio interaction cannot rewrite it;
- total target allocation is decided before Execution;
- Execution owns staging rather than investment quality;
- downstream states consume the canonical temporal boundary.

### Use one Portfolio Decision bounded context

The first Portfolio implementation has one bounded context with separate immutable contracts:

1. `Portfolio State` records holdings, instruments, cash roles, and basic cost/tax metadata;
2. `Portfolio Exposure` derives direct and indirect exposure descriptively;
3. `Portfolio Fit` describes interaction between an unchanged Opportunity State and current
   exposure;
4. `Marginal Allocation` compares explicit before/after alternatives and owns the decision.

These contracts retain separate ownership and fingerprints, but they do not become independent
engines, services, or universal scores.

Every derived Exposure, Fit, and Marginal Allocation state retains `as_of`, knowledge mode,
method version, input fingerprint, missing inputs, conflicts, and assumptions. Instrument
containment and economic-driver classification keep separate provenance and neither is treated as
causal proof.

Portfolio states should reference immutable upstream identifiers and fingerprints rather than
recursively copying every upstream payload when an auditable reference is sufficient. A decision
record must still make the exact consumed versions retrievable.

### Limit the active Portfolio MVP

The active sequence is:

1. Portfolio State, instrument identity, cash roles, and T0 record envelope;
2. one-level ETF look-through with direct/indirect exposure, sector, geography, economic drivers,
   coverage, position weights, Top-N, and HHI;
3. marginal comparison of a candidate stock, an existing holding, the declared core ETF, and
   investment cash;
4. basic replacement and capital-flow policies only after the new-capital comparison works;
5. minimal Execution and Learning slices.

Position size is initially evaluated through explicit candidate amounts and owner-defined
constraints. No active automated sizing formula is admitted.

### Keep named portfolio rules as policies or state

Competition for Capital, the ETF/cash hurdle, no allocation, replacement, PAC/new-capital first,
Legacy Holding, Runner, cash classification, and concentration preferences remain policies or
state inside their canonical owner. They do not justify separate engines.

### Preserve advanced capabilities behind graduation criteria

Advanced look-through, supplier dependency, catalyst clustering, factor exposure, dynamic
correlation, effective independent bets, tail-risk aggregation, automated sizing, complex tax
optimization, Market State, factor-adjusted alpha, and portfolio optimization remain recorded in
the deferred capability register in [`docs/roadmap.md`](../roadmap.md).

They may graduate only after the simpler version produces a measured failure, the necessary
point-in-time data is available, and a prospective validation plan is approved. Synthetic tests
alone do not satisfy this requirement.

### Keep user output simple

Every active capital decision must be renderable as a Decision Card containing the decision,
evaluated amount, principal reasons, best alternative, risks and unknowns, confidence calibration,
conditions that would change the decision, portfolio before/after effect, execution state, `as_of`,
and input fingerprint.

No universal opportunity or portfolio score is introduced.

## Constitution impact

This decision clarifies delivery and architectural type. It does not change the System
Constitution, the investable universe, or the existing analytical ownership boundaries.

ETF eligibility is the separate product-scope decision accepted in ADR 0013 and accompanied by a
minimal Constitution amendment. This ADR does not broaden that narrow eligibility boundary.

## Consequences

### Positive

- AIE can reach a usable marginal-capital decision earlier.
- Separate Underwriting, Portfolio interaction, and Execution ownership remain protected.
- Policies cannot multiply into engines merely because they have names.
- Deferred sophistication remains visible and can graduate through evidence.
- Data and model risk enter the roadmap explicitly.
- The first Learning sample begins before advanced attribution is attempted.

### Negative

- V1 will not claim covariance-aware optimality, factor-adjusted alpha, or automated sizing.
- Some hidden dependencies will remain qualitative or unknown.
- Owner-defined constraints and discrete candidate sizes require visible human policy inputs.
- A later measured failure may require evolving contracts and migrations.

## Rejected alternatives

### Publish the existing Portfolio spike incrementally without changing its model

Rejected because its active scores, thresholds, correlation fallbacks, sizing, and market overlay
were not calibrated and did not explicitly compare every competing use of capital.

### Collapse all Portfolio states into one score engine

Rejected because it violates ADR 0003 and ADR 0006 and hides trade-offs and missing evidence.

### Remove the extended roadmap permanently

Rejected because advanced capabilities may produce decision value after AIE has sufficient data
and prospective failure evidence. They remain deferred rather than forgotten.

## Acceptance record

The owner accepted this ADR after confirming that:

1. the owner approves the compressed roadmap and deferred capability register;
2. the documentation consistently treats Exposure, Fit, and Marginal Allocation as distinct
   contracts inside one Portfolio Decision context;
3. no active score, sizing formula, or correlation fallback is admitted;
4. the Constitution changes only through the minimal ETF-scope update required by ADR 0013;
5. no Portfolio feature implementation is included with this documentation decision.
