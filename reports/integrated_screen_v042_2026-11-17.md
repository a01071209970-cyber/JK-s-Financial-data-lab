# JK's Financial Data Lab — Integrated Screen V0.4.2

**As-of:** 2026-11-17 (US regular-session close)
**Scope:** PLTR, NVDA, AMD, MSFT
**Purpose:** Combine audited fundamental results with guarded valuation

## Fundamental and valuation overview

| Fundamental rank | Ticker | Revenue YoY | Operating margin | Fundamental | EV/Sales | EV/EBIT | Valuation state |
|---:|---|---:|---:|---|---:|---:|---|
| 1 | NVDA | 105.85% | 66.24% | PASS | BLOCKED | BLOCKED | BLOCKED_SHARE_COUNT |
| 2 | PLTR | 95.87% | 46.89% | PASS | 50.34x | 110.29x | INDICATIVE_NOTE_BASED |
| 3 | AMD | 44.68% | 21.17% | PASS | 17.98x | 101.48x | INDICATIVE |
| 4 | MSFT | 18.80% | 49.76% | FAIL | 10.77x | 22.86x | INDICATIVE |

## Interpretive and audit restrictions

- Fundamental rank is quarterly revenue YoY order, not investment attractiveness.
- Microsoft FAIL reflects the 20% quarterly revenue-growth rule, not a valuation failure.
- PLTR: note-based Treasury adjustment; excludes public-equity securities and lease liabilities.
- AMD/MSFT: selected short-term investments and borrowing debt; lease liabilities excluded from base EV.
- Microsoft lease cases remain separate sensitivities, not a common valuation rank.
- NVIDIA: stale rounded share count; hypothetical EV numbers remain outside the approved comparison.
- No cross-company EV valuation ranking is produced because input definitions and review levels differ.
- Yahoo historical prices were retrieved after the valuation date and may reflect later data revisions.
- SEC note facts for PLTR remain manually transcribed, not verified by this aggregation script.
- The raw market-price source CSV is locally ignored by Git; store provenance separately for reproducibility.
- No FCF cross-company ranking, no real-time valuations, and no trading recommendations.

## Source lineage

- Price CSV SHA-256: `8496e2e2405d3802f80de4b9db8d595f5a56dded60e5785aa96b7d0ef6eee95d`
- `reports/screen_v03_2026-11-17.csv`
- `reports/valuation_preview_v04_2026-11-17.csv`
- `reports/pltr_valuation_review_v041_2026-11-17.md`
- `reports/nvda_share_uncertainty_v041_2026-11-17.md`
- DuckDB: `quarterly_metrics_four_reconciled` (read-only, 48 rows)

**Status:** V0.4.2 INTEGRATION VALIDATED; EV values are NOT certified.
