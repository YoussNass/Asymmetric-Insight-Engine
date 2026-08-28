# Chapter 6A: Factual Portfolio State

## Outcome

The Chapter 6A reference slice creates an immutable, content-addressed record of what was held and
what capital was available at one decision-time boundary. It is the factual input to future
Portfolio Exposure and Marginal Allocation work; it is not an investment recommendation.

The architectural decision remains proposed in
[`ADR 0014`](adr/0014-factual-portfolio-state-and-t0-snapshot.md) until owner review and merge
authorization.

## Contract map

| Contract | Owns | Explicitly does not own |
| --- | --- | --- |
| `PortfolioInputRecord` | Provider identity/version, source reference, effective/available/recorded times, content hash | Provider retrieval or storage |
| `PortfolioAccount` | Canonical account identity and basic tax treatment | Tax rates, lots, forecasts, optimization |
| `Instrument` | Canonical identity, type, native currency, listing and ETF structural facts | Company underwriting or ETF constituent exposure |
| `InstrumentPrice` | One native-currency unit price backed by a T0 record | FX conversion or price forecasting |
| `Position` | Account, instrument, positive quantity, T0 price, current value, aggregate cost basis | Position sizing or allocation intent |
| `CashBalance` | Account, native-currency amount, and owner-declared cash role | Funding or execution decisions |
| `ETFEligibilityPolicy` | Versioned eligible ETF allow-list and benchmark identity | ETF analysis, ranking, or an ETF engine |
| `PortfolioState` | Validated canonical snapshot, fingerprint, and audit envelope | Exposure, fit, allocation, replacement, or execution |

## Point-in-time lineage

Every material state fact references one immutable input record. The same canonical
`KnowledgeBoundary` used by Causal Alpha and Underwriting applies here:

- `historical_reconstruction` admits records that were publicly available by T0;
- `live_system_replay` also requires the system to have recorded the input by T0;
- `effective_at` must be no later than T0 in both modes.

The state rejects duplicate identifiers, incorrect record kinds, unknown references, unused input
records, unused accounts, unused instruments, and prices that do not match an instrument's native
currency.

## Capital and currency invariants

- Chapter 6A is long-only, consistent with the accepted V1 boundary.
- A position's current value must equal `quantity × T0 unit price` exactly after canonical decimal
  normalization.
- Cost basis is aggregate and explicitly reported, user-estimated, or unavailable. Its reported
  currency is preserved even when different from the instrument currency; this slice computes no
  cross-currency gain or loss.
- Tax treatment is account-level so it cannot diverge between rows in the same account.
- Emergency reserve cash is non-investable. Strategic, opportunistic, and unallocated cash remain
  explicit investment-cash roles.
- Values may be subtotalled only inside their native currency. There is no `total_portfolio_value`
  or base-currency field in this slice.

## ETF boundary

The deterministic reference state demonstrates all three ADR 0013 categories:

1. a listed equity is representable and inside the V1 investable universe;
2. a diversified, unleveraged core equity ETF is allow-listed and designated as benchmark;
3. a narrowly thematic ETF is represented as an existing legacy holding but is ineligible for new
   capital.

The policy answers eligibility only. It does not compare the ETF with a stock or select an
allocation.

## Deterministic reference case

Tests use synthetic source identities and values across two accounts:

- one USD listed-equity position;
- one EUR thematic ETF legacy position;
- one EUR eligible benchmark ETF available as a future alternative;
- EUR emergency and unallocated cash;
- USD opportunistic cash.

The resulting state reports held-value and cash subtotals separately for EUR and USD. Reordering
unordered inputs does not change its fingerprint; changing a quantity, price, cost basis, account,
or eligibility policy does.

The application verifier rebuilds a deserialized state before downstream use. A changed position,
fingerprint, state identifier, benchmark, boundary, or envelope is rejected when it no longer
matches the canonical replay.

The fixture proves the state contract and replay behavior. It is not a real portfolio, a provider
integration, an ETF data-quality claim, or an investment recommendation.

## Exit criterion

Chapter 6A is complete only after ADR 0014 is accepted and the implementation is merged with green
CI. At that point AIE can reproduce owned positions and available capital at T0 without making an
allocation recommendation. Chapter 6B then consumes the immutable state by identifier and
fingerprint to derive descriptive exposure.
