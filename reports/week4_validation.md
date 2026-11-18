# JK's Financial Data Lab — Week 4 Validation Report

**As-of:** 2026-11-17  
**Model:** Fundamental Screener V0.3  
**Scope:** PLTR, NVDA, AMD, MSFT  
**Data source:** Local SEC Company Facts in DuckDB  
**Database mode during screening:** Read only

## Data integrity

| Check | Result |
|---|---|
| Raw SEC observations | 92,717 |
| Companies | 4 |
| Quarters per company | 12 |
| Quarterly metrics | 48 |
| SEC-only validated quarters | 47 |
| NVDA FY2024 Q3 supplemental CAPEX reconciliation | 1 |
| Original PLTR/NVDA 24-quarter regression | PASS |
| Source tables during export | UNCHANGED |

## Fundamental screen

**Result:** 3 PASS / 1 FAIL

| Rank | Ticker | Latest fiscal quarter | Quarterly revenue YoY | Operating margin | LTM revenue YoY | Status |
|---:|---|---|---:|---:|---:|---|
| 1 | NVDA | FY2027 Q2 | 105.85% | 66.24% | 83.38% | PASS |
| 2 | PLTR | FY2026 Q3 | 95.87% | 46.89% | 87.06% | PASS |
| 3 | AMD | FY2026 Q3 | 44.68% | 21.17% | 41.87% | PASS |
| 4 | MSFT | FY2027 Q1 | 18.80% | 49.76% | 17.91% | FAIL |

## LTM comparison

| Ticker | LTM revenue (USD bn) | LTM operating margin | Quarterly OCF margin (secondary) | Filing age (days) |
|---|---:|---:|---:|---:|
| NVDA | 302.969 | 65.21% | 25.02% | 83 |
| PLTR | 7.288 | 45.64% | 52.07% | 14 |
| AMD | 45.436 | 17.72% | 8.99% | 13 |
| MSFT | 346.445 | 47.10% | 62.85% | 20 |

## Methodology

- Quarterly revenue growth threshold: 20.0% YoY.
- Profitability: operating margin at least 10.0%, or YoY margin improvement greater than 0.0 percentage points.
- Required validated history: 8 quarters.
- Latest filing maximum age: 180 days.
- LTM revenue is the sum of four latest quarters; LTM growth compares the prior four quarters.
- OCF margin is a supplementary metric, not a screening threshold.
- FCF and adjusted/official FCF are excluded from cross-company ranking due to differing definitions.

## Limits and interpretation

- MSFT fails only the 20% quarterly revenue-growth requirement; this is not a financial-distress finding.
- This is a fundamental first-stage filter, not an investment recommendation or expected-return ranking.
- Market capitalization, debt ratios, analyst coverage, share prices and technical signals have not been incorporated.
- Data reflects SEC information available by the configured as-of date, not live market conditions.
- NVDA FY2024 Q3 CAPEX was reconciled from a previously validated supplemental record; provenance remains in the database.
