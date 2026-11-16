
# Week 2 — Quarterly Financial Metrics Validation

## Project
JK's Financial Data Lab V1.0

## Company
Palantir Technologies Inc. (PLTR)

CIK: 1321655

## Reporting Period
2023 Q4 - 2026 Q3

Data cutoff: 2026-11-16

## 1. Objective

Build a reproducible quarterly financial metrics
engine using SEC EDGAR data, SQL, and DuckDB.

## 2. Source

SEC EDGAR Company Facts API

https://data.sec.gov/api/xbrl/companyfacts/CIK0001321655.json

Original financial observations: 8,134

## 3. Completed Features

- SEC filing version comparison
- Basic point-in-time revenue selection
- First-available filing selection
- Quarterly revenue extraction
- Q4 revenue reconstruction
- Quarterly operating income extraction
- Quarterly operating cash flow calculation
- Quarterly CAPEX calculation
- Free cash flow calculation
- Revenue growth YoY
- Operating margin
- FCF margin
- Operating margin YoY change

## 4. Database

Table: quarterly_metrics

Total quarters: 12

Coverage:
2023 Q4 through 2026 Q3

## 5. FY2026 Q3 Results

Revenue: 2,313,411,000 USD

Operating income: 1,084,845,000 USD

Operating cash flow: 1,204,570,000 USD

Capital expenditure: 8,014,000 USD

Free cash flow: 1,196,556,000 USD

Revenue growth YoY: 95.87%

Operating margin: 46.89%

FCF margin: 51.72%

Operating margin YoY change: +13.60 pp

## 6. Validation Results

Executed SQL:
sql/14_validate_quarterly_metrics.sql

Total rows: 12
Unique quarters: 12

Missing core errors: 0
FCF calculation errors: 0
Margin calculation errors: 0
Growth calculation errors: 0
YoY margin errors: 0
Missing quarters: 0

Final result: PASS

## 7. Methodology

Direct quarterly revenue and operating income
were selected from SEC filings.

Q4 revenue and operating income were derived
using annual figures minus nine-month YTD figures.

Quarterly operating cash flow and CAPEX
were derived from differences between cumulative
cash flow observations.

FCF = Operating Cash Flow - CAPEX

Revenue Growth YoY =
(Current Quarter Revenue / Prior Year Quarter Revenue - 1) * 100

Operating Margin =
Operating Income / Revenue * 100

FCF Margin =
FCF / Revenue * 100

## 8. Known Limitations

- Only PLTR is currently supported.
- The current table does not include a company CIK column.
- Filing selection is based on filing dates,
  not precise filing timestamps.
- First-available values are not equivalent to
  a complete point-in-time historical database.
- Restatements have not been fully reconciled.
- Net profit margin is not yet implemented.
- FY2024 Q4 operating margin requires
  further investigation.
- The current FCF definition excludes company-
  specific adjustments.
- Validation establishes internal consistency,
  not comprehensive external financial accuracy.

## 9. Next Steps

Week 3:

1. Generalize collection and SQL processing by CIK.
2. Ingest NVDA financial data.
3. Handle NVDA's fiscal-year calendar.
4. Compare PLTR and NVDA using identical metrics.
5. Improve point-in-time and restatement handling.
6. Add multi-company validation.

## Status

Week 2: Completed — internal validation PASS