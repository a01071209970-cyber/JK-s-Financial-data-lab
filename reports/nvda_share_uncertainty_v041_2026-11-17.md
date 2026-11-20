# NVDA V0.4.1 — Historical Share-Count Uncertainty

**Price as-of:** 2026-11-17 (regular-session close)
**Status:** BLOCKED — sensitivity only

## Point-in-time evidence

- Selected share source: `dei:EntityCommonStockSharesOutstanding`
- Measurement date: 2026-08-21
- Filing date: 2026-08-26
- Shares disclosed (rounded): 24,100,000,000
- Share-count age: 88 days
- Same-day Company Facts filings excluded because acceptance times are not supplied.
- Earnings 8-K acceptance: 2026-11-17T16:20:51-05:00 (after regular close)
- Saved price SHA-256: `8496e2e2405d3802f80de4b9db8d595f5a56dded60e5785aa96b7d0ef6eee95d`

## Illustration: valuation sensitivity to outstanding shares

- Close: $155.460007
- Selected liquidity minus borrowings: $23.220B
- Baseline indicative market cap: $3746.586B
- Baseline *unapproved* EV: $3723.366B
- Hypothetical +/-1% share-count effect on market cap: $37.466B
- Hypothetical +/-50 million-share rounding effect: $7.773B

| Assumed share change | Indicative cap ($B) | Illustrative EV ($B) | EV/Sales | EV/EBIT |
|---:|---:|---:|---:|---:|
| -2% | 3,671.654 | 3,648.434 | 12.04x | 18.47x |
| -1% | 3,709.120 | 3,685.900 | 12.17x | 18.66x |
| +0% | 3,746.586 | 3,723.366 | 12.29x | 18.84x |
| +1% | 3,784.052 | 3,760.832 | 12.41x | 19.03x |
| +2% | 3,821.518 | 3,798.298 | 12.54x | 19.22x |

## Restrictions

- Share scenarios are arbitrary stress tests, not measured repurchases, statistical bounds, or forecasts.
- The cover-page share count is rounded; the exact historical count is not confirmed.
- No newer pre-close share count was established by this offline audit.
- No stock-split history is re-fetched; the prior split audit remains a separate prerequisite.
- No change to the historical V0.4 CSV, rankings, or DuckDB.
- These hypothetical EV ratios must NOT be compared as approved valuation rankings.
