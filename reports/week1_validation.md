
# Week 1 — Data Validation Report

## Project
JK's Financial Data Lab

## Company
Palantir Technologies Inc. (PLTR)

CIK: 1321655

## Data Source
SEC EDGAR Company Facts API

https://data.sec.gov/api/xbrl/companyfacts/CIK0001321655.json

## Environment
- macOS (Intel)
- Python 3.15.2
- DuckDB
- pandas
- requests

## Data Ingestion
- Stored financial observations: 8,134
- Raw source: SEC Company Facts JSON
- Database: financial_data.duckdb
- JSON-to-database record count: PASS

## Financial Validation

### Revenue — FY2026 Q3
Reported quarterly revenue: 2,313,411,000 USD

Calculated quarterly revenue:
5,881,458,000 - 3,568,047,000
= 2,313,411,000 USD

Result: PASS

### Operating Cash Flow — FY2026 Q3
3,319,902,000 - 2,115,332,000
= 1,204,570,000 USD

### Capital Expenditure — FY2026 Q3
29,969,000 - 21,955,000
= 8,014,000 USD

### Free Cash Flow — FY2026 Q3
1,204,570,000 - 8,014,000
= 1,196,556,000 USD

Cash flow data presence and uniqueness test: PASS

## Structural Data Quality
- Missing core fields: 0
- Invalid periods: 0
- Non-numeric values: 0
- Missing starts in selected duration tags: 0
- Exact duplicate rows: 0
- Rows without period start: 3,090
- Rows without frame: 4,428

Audit result: PASS

## Known Limitations
- Optional field omissions have not all been individually classified.
- Restatement reconciliation is not implemented.
- Point-in-time data selection is not implemented.
- Quarterly metrics are not yet materialized.
- Company-reported adjusted FCF is not independently reconciled.
- This audit does not establish full financial accuracy.

## Next Milestone
Week 2: Quarterly financial metric extraction
and point-in-time validation.