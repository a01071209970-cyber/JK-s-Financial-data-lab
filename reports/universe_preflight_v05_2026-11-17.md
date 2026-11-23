# Candidate Universe V0.5 — SEC Identity Preflight

**Research cutoff:** 2026-11-17
**State:** IDENTITY_VERIFIED_ONLY — NOT INGESTED

## New candidate companies

| Ticker | SEC registrant | CIK | Research theme | Onboarding |
|---|---|---|---|---|
| AMZN | AMAZON COM INC | `0001018724` | AWS cloud infrastructure and AI investment | PENDING_REVIEW |
| META | Meta Platforms, Inc. | `0001326801` | AI advertising and platform profitability | PENDING_REVIEW |
| GOOGL | Alphabet Inc. | `0001652044` | Search, Google Cloud and AI | PENDING_REVIEW |
| AVGO | Broadcom Inc. | `0001730168` | AI semiconductors and infrastructure software | PENDING_REVIEW |
| ANET | Arista Networks, Inc. | `0001596532` | AI data center Ethernet networking | PENDING_REVIEW |
| CRDO | Credo Technology Group Holding Ltd | `0001807794` | High-speed data connectivity and AI interconnect | PENDING_REVIEW |

## Verification and scope

- SEC ticker directory: https://www.sec.gov/files/company_tickers.json
- Locally retained directory SHA-256: `6b59e0ed15932cceb6917a79be900062751c66b6c038168abd9d4bff64ae0210`
- All four existing CIK mappings were rechecked.
- Candidate CIK identity only; fiscal calendars and US-GAAP metric tags remain unverified.
- This directory represents the retrieval-time mapping, not proof of historical index membership.
- No Company Facts were downloaded for the candidates.
- No facts were admitted into the November 17 historical snapshot.
- Existing DuckDB, quarterly tables, financial screens and valuations were not modified.
- Filing acceptance time and post-close availability must be reviewed before PIT approval.
- Alphabet's multiple share classes require separate market-cap review.

**Next gate:** fiscal calendar + XBRL taxonomy + as-of filing availability checks.
