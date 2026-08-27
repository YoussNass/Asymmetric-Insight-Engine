# ADR 0013: Decide ETF eligibility explicitly at the Portfolio boundary

- Status: Accepted
- Date: 2026-08-27

## Context

Before this decision, the Version 1 Constitution defined global listed equities and cash as the
investable universe. ETFs and indexes were context variables. The Portfolio mission, however,
requires every active stock candidate to compete with a core passive alternative and allows the
best marginal use of capital to be the core ETF.

If an ETF can be observed only as context, AIE can conclude that passive capital is superior but
cannot represent allocation to that alternative. Conversely, admitting every ETF would expand the
product into leveraged, inverse, thematic, synthetic, commodity, crypto, and other structures
without evidence that V1 needs them.

Existing holdings also create a separate requirement: Portfolio State must faithfully represent
what the user owns even when an instrument is not eligible for new capital.

## Decision

Admit a versioned allow-list of diversified, unleveraged equity ETFs as eligible Portfolio
instruments.

This decision distinguishes:

- **representable instruments**: every existing holding that Portfolio State must record;
- **eligible alternatives**: instruments allowed to receive new investment capital under a
  versioned policy;
- **benchmark instruments**: eligible ETFs designated as the comparison baseline at T0.

An existing holding may be representable but ineligible for new capital. Eligibility never follows
implicitly from presence in the portfolio.

### Initial eligibility boundary

The first admitted ETF set should be limited to explicit core or alternative diversified equity
benchmarks selected by policy. Leveraged, inverse, volatility, commodity, crypto, derivative-heavy,
and narrowly thematic ETPs remain ineligible unless a later ADR expands the scope.

Admission requires:

- canonical instrument identity and native currency;
- point-in-time price and benchmark role;
- holdings snapshot date, source, coverage, and unresolved residual for look-through;
- explicit fees, spreads, liquidity limitations, and missing data relevant to comparison;
- a versioned eligibility policy and knowledge boundary.

Incomplete look-through remains visible. It cannot be interpreted as zero overlap or automatic
diversification.

### Analytical ownership

An ETF does not enter company Investment Underwriting and does not receive a synthetic company
quality score. Portfolio owns an instrument-alternative state sufficient to represent benchmark
role, exposure, costs, uncertainty, and before/after effects.

Marginal Allocation compares the immutable stock Opportunity State with ETF, cash, and existing
holding alternatives without pretending those objects share the same underwriting model.

## Constitution impact

This accepted ADR changes Version 1 scope through a minimal explicit Constitution amendment that:

- admits policy-eligible diversified equity ETFs as Portfolio instruments;
- keeps other ETFs, indexes, rates, commodities, and crypto as context unless separately admitted;
- preserves long-only decision support and the prohibition on live order submission.

Implementation may admit only the policy-eligible ETF subset defined here. Any broader
exchange-traded-product eligibility requires another explicit ADR and Constitution decision.

## Consequences

### Positive

- Active capital must genuinely earn the right to replace passive capital.
- `CORE ETF` becomes an actionable competing use rather than a rhetorical hurdle.
- Existing ETF holdings can be represented independently of their eligibility for new capital.
- The initial universe remains narrow and auditable.

### Negative

- ETF constituent data creates point-in-time coverage and provider-maintenance obligations.
- Stock and ETF alternatives require different upstream analytical states.
- Eligibility policy and benchmark designation require versioning and governance.

## Alternatives considered

### Keep every ETF as context only

Architecturally simpler, but inconsistent with a decision system that can identify passive capital
as the best marginal use without being able to select it.

### Admit every exchange-traded product

Rejected for Version 1 because the instruments, risks, data, and valuation semantics are too
heterogeneous.

### Represent ETFs only as legacy holdings

Insufficient because it prevents an explicit new-capital comparison with the core benchmark.

## Implementation constraints

The owner explicitly chose this ETF eligibility boundary and approved the minimal Constitution
amendment. Implementation must still begin with deterministic fixtures and point-in-time coverage
disclosure. This ADR does not by itself authorize live provider integration or a broader Portfolio
slice.
