# ADR 0014: Establish factual Portfolio State and the T0 capital snapshot

- Status: Proposed
- Date: 2026-08-27

## Context

Chapter 5 can hand an immutable standalone Opportunity State to Portfolio, but AIE still lacks the
factual answer to two prior questions: what the owner held at the decision boundary, and what cash
was actually available for investment. Exposure, fit, and marginal allocation cannot be audited
unless they consume one reproducible Portfolio State rather than rebuilding holdings and capital
from ad hoc inputs.

ADR 0012 authorizes Portfolio State as the first narrow contract inside the Portfolio Decision
bounded context. ADR 0013 separately distinguishes representable holdings, eligible alternatives,
and the benchmark. This slice must implement those decisions without importing Underwriting,
creating an exposure graph, aggregating unlike currencies, or recommending an allocation.

## Complexity Budget

| Gate | Chapter 6A evidence |
| --- | --- |
| Decision value | Every later exposure and capital comparison requires the exact holdings and available cash at T0. |
| Validatability | Deterministic fixtures test point-in-time exclusion, arithmetic identities, canonical replay, and round-trip serialization. |
| Architectural necessity | This is data/state inside the accepted Portfolio Decision context, plus one deterministic builder capability; it is not a new engine or service. |
| Data sufficiency | The contract needs account, instrument, holdings, cash, price, and policy records with explicit timestamps and hashes. Provider integration is not required to validate the boundary. |
| Explainability | Positions, prices, cost basis, cash roles, missing data, assumptions, benchmark, and native-currency subtotals remain inspectable. |
| Maintenance cost | One domain contract, one application builder, shared financial value objects, fixtures, and invariant tests. Persistence and live adapters remain outside the slice. |
| Timing | Portfolio Exposure and Marginal Allocation cannot begin safely without a canonical input state and T0 fingerprint. |

Classification: `Portfolio State` is `CORE NOW` data/state. `BuildPortfolioState` is a `CORE NOW`
deterministic capability. ETF eligibility and cash-role interpretation remain `SIMPLE POLICY`
inside Portfolio; neither receives an engine.

## Decision

### Use one immutable factual snapshot

`PortfolioState` owns:

- one explicit `KnowledgeBoundary` and method version;
- versioned input records for accounts, instruments, holdings, cash, prices, and ETF policy;
- canonical accounts with one basic account-level tax treatment;
- canonical instruments and instrument types;
- one T0 native-currency price per held or eligible instrument;
- aggregate long-only positions per account and instrument;
- aggregate cost basis with reported, estimated, or unavailable status;
- cash balances classified as emergency, strategic, opportunistic, or unallocated;
- the versioned ETF allow-list and declared benchmark identity;
- missing data, conflicts, and assumptions.

All input records must be effective and knowable at the declared boundary. In a live-system replay,
they must also have been recorded by T0. Every input record, account, instrument, and price must
support the resulting state; orphaned or duplicate facts are rejected.

### Keep account facts canonical

Tax treatment and jurisdiction belong to `PortfolioAccount`. Positions and cash reference the
account rather than copying tax metadata on each row. This prevents two holdings in the same
account from silently asserting different account regimes. Tax rates, lots, disposal forecasts,
and optimization remain outside Chapter 6A.

### Separate representation, eligibility, and benchmark role

Portfolio State can represent an existing holding even when it is not eligible for new capital.
Listed equities are inside the accepted V1 universe. An equity ETF is eligible only when it is on
the versioned allow-list and its structural facts identify it as diversified, unleveraged,
non-inverse, not derivative-heavy, and not narrowly thematic. The benchmark must be one of those
eligible ETFs.

Presence in the portfolio never implies eligibility. Eligibility never implies selection or
allocation. Other representable instrument types remain legacy/context holdings only unless a
later ADR expands the investable universe.

### Preserve native currency without implicit FX

Every monetary amount carries an ISO currency. A position value must exactly reproduce as
quantity multiplied by its own T0 price, and cost basis must use the same native currency.
Portfolio State may return subtotals grouped by currency; it exposes no cross-currency total,
base-currency value, or undeclared FX conversion.

### Content-address the complete T0 input

`BuildPortfolioState` canonicalizes semantically unordered collections, hashes the complete
validated draft, and derives stable UUIDv5 identifiers for both the state and its audit envelope.
The envelope preserves the Portfolio State identifier, input fingerprint, knowledge boundary,
benchmark identity, and method version. It intentionally contains no capital decision; later
decision slices may reference it without recursively copying the full state.

### Exclude analytical and execution authority

Chapter 6A contains no Opportunity State, ETF constituent expansion, exposure, portfolio fit,
correlation, concentration score, position sizing, allocation, replacement, market regime,
execution staging, persistence adapter, or live brokerage/provider integration.

## Consequences

### Positive

- Later Portfolio contracts consume one auditable factual state.
- Native-currency arithmetic cannot silently mix EUR, USD, or other currencies.
- Existing ineligible holdings remain visible without becoming eligible by implication.
- Account tax metadata has one owner.
- The benchmark and capital available at T0 survive exact replay.
- The first implementation remains removable from any future provider or persistence choice.

### Negative

- V1 remains long-only and cannot model margin liabilities or short positions.
- Cross-currency portfolio totals require a later explicit point-in-time FX contract.
- Aggregate cost basis is insufficient for tax-lot optimization.
- Fixtures validate the contract, not the completeness or reliability of a live provider.
- The domain rejects incomplete snapshots rather than inventing prices, accounts, or classifications.

## Rejected alternatives

### Reuse the Portfolio Exposure Graph spike as the source of truth

Rejected because holdings and source records are the facts; a graph is a derived view and would
prematurely couple State to Exposure, Fit, risk scoring, and sizing.

### Store positions, cash, and policy as unvalidated dictionaries

Rejected because timestamp, currency, account, price, eligibility, and orphan-reference failures
would become invisible precisely at the boundary every downstream decision trusts.

### Copy tax metadata onto every position and cash balance

Rejected because one account could then carry contradictory tax facts. Account-level ownership is
simpler and canonical.

### Compute one total portfolio value using an implicit base currency

Rejected because no point-in-time FX source or conversion policy is admitted in Chapter 6A.

## Acceptance criteria

This ADR may move to `Accepted` only when the owner reviews the implementation candidate and:

1. all required local checks and the remote Python and container CI jobs pass on the exact head;
2. the state reproduces held value and investable cash by native currency at T0;
3. representation, eligibility, and benchmark remain separate;
4. no analytical or allocation authority enters the slice;
5. the owner explicitly authorizes the Chapter 6A merge.
