# Candidate Company Facts Inventory — V0.5

**Research cutoff:** 2026-11-17
**Status:** RAW_ARCHIVED_NOT_ONBOARDED

| Ticker | CIK | SEC entity | US-GAAP tags | Pre-cutoff facts | Same-day/later excluded | SHA-256 prefix |
|---|---|---|---:|---:|---:|---|
| AMZN | `0001018724` | AMAZON.COM, INC. | 545 | 30,246 | 0 | `acddb7c0a697` |
| META | `0001326801` | Meta Platforms, Inc. | 462 | 18,339 | 0 | `f8e539cea9d3` |
| GOOGL | `0001652044` | Alphabet Inc. | 550 | 20,769 | 0 | `e4b7685f57b8` |
| AVGO | `0001730168` | Broadcom Inc. | 434 | 14,723 | 0 | `3bdb6644c12a` |
| ANET | `0001596532` | Arista Networks, Inc. | 449 | 20,523 | 0 | `3c6e88dae7c6` |
| CRDO | `0001807794` | Credo Technology Group Holding Ltd | 269 | 5,742 | 0 | `427189523614` |

## Controls and limitations

- Six company snapshots are stored locally.
- Raw JSON and metadata are excluded from Git.
- Historical eligibility uses SEC filing dates strictly before the cutoff.
- Same-day filings require separate acceptance-time checks.
- Post-cutoff facts remain in the raw archive but must not enter historical screening.
- Retrieval time does not prove historical availability.
- Fiscal calendars and XBRL tag mappings remain unverified.
- No candidate has been approved for valuation.
- Existing DuckDB and four-company reports were not modified.

## Retrieval provenance

- AMZN: retrieved `2026-11-23T12:40:41+00:00`; SHA-256 `acddb7c0a6973a1fd08372de3b292298a34eae7f42a7eedc4bdebd3ac659c8fd`
- META: retrieved `2026-11-23T12:40:42+00:00`; SHA-256 `f8e539cea9d363752df2f9bb33078c19ae897ff7f34d49fe4d9a732d032b94f7`
- GOOGL: retrieved `2026-11-23T12:40:43+00:00`; SHA-256 `e4b7685f57b8d6fc9be74c23dc891dfd81de5716d0551338914385fa11bf43a6`
- AVGO: retrieved `2026-11-23T12:40:44+00:00`; SHA-256 `3bdb6644c12addf1e63c4dc861008d7804fbf3d3f5aa6eb9b97f72c0e89a7adf`
- ANET: retrieved `2026-11-23T12:40:46+00:00`; SHA-256 `3c6e88dae7c6ee8891f2c4eacdfff23599876320021bb2c568754ace3015a457`
- CRDO: retrieved `2026-11-23T12:40:47+00:00`; SHA-256 `42718952361414c81add8e89adf6803dd1fb6d1f511cc66b62b3e62484045323`
