
# JK's Financial Data Lab

## US Tech Fundamental Screener

Financial data engineering and fundamental analysis project using Python, SQL, DuckDB, and SEC EDGAR.

## Objective

Build a reproducible financial screening system for US-listed technology companies using official SEC filings.

## Initial Coverage

- PLTR
- NVDA

Planned expansion:
AMD, MSFT, AMZN, META, CRDO, ANET

## Tech Stack

- Python
- requests
- pandas
- DuckDB
- SQL
- SEC EDGAR API

## Financial Metrics

1. Revenue growth (YoY)
2. Operating margin
3. Net profit margin
4. Operating cash flow
5. Capital expenditure
6. Free cash flow
7. Free cash flow margin
8. Operating margin change (YoY)

## Data Source

SEC EDGAR Company Facts API

https://www.sec.gov/search-filings/edgar-application-programming-interfaces

## Project Status

### Week 1 — Completed
- Python and DuckDB environment
- SEC Company Facts collection
- 8,134 PLTR financial observations
- Data ingestion and structural validation

### Week 2 — Completed
- SEC filing version analysis
- Basic point-in-time selection
- 12 quarterly revenue observations
- 12 quarterly operating income observations
- Quarterly OCF, CAPEX, and FCF
- Quarterly metrics table
- Revenue growth and profitability analysis
- Internal data quality validation: PASS

### Week 3 — Next
- NVDA data integration
- Fiscal calendar generalization
- Multi-company financial analysis


## Data Quality Principles

- Preserve filing dates and accession numbers
- Distinguish quarterly and year-to-date values
- Handle restatements and missing data
- Avoid look-ahead bias
- Do not substitute fabricated financial data