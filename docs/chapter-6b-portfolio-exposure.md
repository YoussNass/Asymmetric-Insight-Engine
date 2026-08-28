# Chapter 6B: Minimal Portfolio Exposure

## Outcome

The Chapter 6B reference slice derives a reproducible view of direct and hidden indirect exposure
from one verified factual Portfolio State. It shows instrument, company, sector, primary economic
geography, and overlapping economic-driver exposure without producing a fit score or capital
decision.

The architectural decision is accepted in
[`ADR 0015`](adr/0015-minimal-point-in-time-portfolio-exposure.md).

## Contract map

| Contract | Owns | Explicitly does not own |
| --- | --- | --- |
| `ETFConstituentSnapshot` | One-level company weights, holdings date, source evidence, coverage, and residual | Recursive funds, causal edges, or ETF ranking |
| `CompanyExposureProfile` | Evidence-backed sector, geography, driver tags, and dimension-level unknowns | Company Underwriting or causal mechanisms |
| `PortfolioExposureInput` | Canonical knowledge boundary, evidence, claims, snapshots, supplied amount, and disclosures | Portfolio State facts or allocation policy |
| `PortfolioStateReference` | Upstream state ID, fingerprint, portfolio ID, and boundary | A recursive copy of holdings or cash |
| `CurrencyExposureBook` | Native-currency instrument weights, direct/indirect companies, classifications, residual, Top-N, and HHI bounds | FX conversion or a universal portfolio score |
| `PortfolioExposure` | Content-addressed before/after descriptive state | Fit, sizing, allocation, replacement, or execution |

## Point-in-time and provenance boundary

Every exposure evidence item must be effective and knowable at the Portfolio State boundary. Live
replay also rejects evidence not recorded by T0. ETF holdings date must match the effective date of
its source evidence.

Containment and classification are distinct:

- ETF snapshots use observation evidence to answer which companies the instrument contains;
- classifications use typed claims to answer how a resolved company is described;
- economic-driver tags require interpretive claims and retain uncalibrated confidence visibly;
- neither layer is a causal edge.

All supplied evidence and claims must support the result; orphan inputs are rejected.

## Native-currency exposure

The deterministic reference portfolio produces separate EUR and USD books:

- the USD listed-equity position is direct company exposure;
- the EUR thematic ETF is indirect company exposure;
- the ETF's ten-percent unresolved residual remains `unknown` in company, sector, geography, and
  driver views;
- no total combines EUR and USD.

The core ETF hypothetical is an explicit EUR 500 input. It changes only the EUR
`hypothetical_after` book and never becomes a recommended amount.

## Concentration metrics

Position weights and Top-N companies are descriptive; `N` is an explicit fingerprinted input,
not a hidden threshold. Company HHI is an interval:

```text
lower = sum(resolved company weights squared)
upper = lower + unresolved weight squared
```

In the deterministic EUR current book, resolved company weights are 60% and 30%, with 10%
unresolved. The HHI interval is therefore `[0.45, 0.46]`. Unknown is not assigned a zero weight and
is not presented as diversification.

Economic-driver exposures are non-additive because a company may legitimately carry multiple
evidence-backed tags. Their weights must not be summed into a portfolio total.

## Deliberate limits

- one ETF level only;
- no provider or persistence adapter;
- no live claim of holdings coverage;
- no implicit FX or cross-currency concentration;
- no supplier, catalyst, factor, or correlation graph;
- no Portfolio Fit or permanent-loss aggregation;
- no sizing, hurdle, replacement, tax, allocation, timing, or execution output;
- the optional hypothetical must reference an already canonical, policy-eligible instrument.

The last constraint prevents Chapter 6B from inventing a candidate-equity representation. Chapter
6C will consume the immutable Underwriting hand-off when it compares a new stock with holdings,
the core ETF, and cash.

## Deterministic reference case

Synthetic fixtures include:

- one direct USD listed equity;
- one held EUR thematic ETF with 90% resolved one-level holdings;
- one eligible EUR core ETF used only for a supplied before/after amount;
- three resolved companies with evidence-backed sector, geography, and driver tags;
- overlapping driver labels and explicit uncalibrated confidence;
- ten-percent unresolved weight in each ETF snapshot.

The fixture proves temporal filtering, containment/classification separation, value
reconciliation, native-currency grouping, HHI bounds, stable canonical ordering, serialization,
and integrity replay. It is not a real portfolio, ETF-provider claim, or investment recommendation.

## Exit criterion

Chapter 6B is complete only after ADR 0015 is accepted and the implementation is merged with green
CI. At that point AIE can explain current and supplied hypothetical exposure without modifying
Portfolio State, Opportunity State, or any capital decision.
