
# Week 3 — Multi-Company Financial Analysis

## JK's Financial Data Lab V1.0

### Project Status
Week 3: Technical validation completed

### Companies
- Palantir Technologies (PLTR)
- NVIDIA Corporation (NVDA)

### Data Cutoff
2026-11-17

---

## 1. Executive Summary

Week 3 extended the original PLTR financial
data pipeline into a multi-company financial
analysis system.

The project now supports different fiscal
year calendars, company-specific XBRL tags,
quarterly financial reconstruction, and
auditable supplemental data reconciliation.

Both companies passed the LTM internal
validation checks.

## 2. Data Collection

Source: SEC EDGAR Company Facts API

| Metric | PLTR | NVDA |
|---|---:|---:|
| CIK | 1321655 | 1045810 |
| Observations | 8,134 | 27,281 |
| US-GAAP observations | 8,096 | 27,114 |

Total observations: 35,415

Original SEC JSON files are retained locally
and excluded from Git.

## 3. Fiscal Calendar Handling

PLTR:
- Calendar-year fiscal reporting
- Fiscal year ends December 31

NVDA:
- 52/53-week fiscal calendar
- Fiscal year ends on the final Sunday of January
- FY2027 has a 14-week fourth quarter

Fiscal periods are matched using actual
period_start and period_end dates.

SEC fy/fp attributes are not used as the
sole determinants of fiscal-quarter identity.

## 4. XBRL Metric Mapping

PLTR revenue:
RevenueFromContractWithCustomerExcludingAssessedTax

NVDA revenue:
Revenues

Operating income:
OperatingIncomeLoss

Operating cash flow:
NetCashProvidedByUsedInOperatingActivities

PLTR CAPEX:
PaymentsToAcquirePropertyPlantAndEquipment

NVDA CAPEX:
PaymentsToAcquireProductiveAssets

NVDA CAPEX remains a provisional definition
pending broader comparability review.

## 5. Database Architecture

Original Week 2 tables preserved:
- companies
- financial_facts
- quarterly_metrics

Week 3 tables:
- companies_multi
- financial_facts_multi
- quarterly_metrics_multi
- quarterly_metrics_reconciled

Each company is identified by CIK and ticker.

The fiscal year and fiscal quarter identify
the quarterly observation.

## 6. Quarterly Reconstruction

Revenue and operating income:
- Q1-Q3: direct quarterly observations
- Q4: annual amount minus nine-month amount

Operating cash flow and CAPEX:
- Q1: three-month YTD
- Q2: six-month YTD minus three-month YTD
- Q3: nine-month YTD minus six-month YTD
- Q4: full-year YTD minus nine-month YTD

Simple FCF = OCF - selected CAPEX

Metric availability is tracked using
source filing dates.

## 7. Data Reconciliation

One missing observation was identified:
NVDA FY2024 Q3 CAPEX.

The six-month YTD value was available
in NVIDIA's 2023 official results but was
linked to a later filing in the local
SEC Company Facts data.

Reconciliation:
- 6M YTD CAPEX: $537 million
- 9M YTD CAPEX: $815 million
- Q3 CAPEX: $278 million

Reconciled quarterly simple FCF:
$7,054 million

The original quarterly_metrics_multi
record was preserved with REVIEW status.

The separate quarterly_metrics_reconciled
table stores the adjusted calculation
with RECONCILED_SUPPLEMENTAL status
and supporting source information.

## 8. Final Quarterly Validation

File:
sql/18_validate_reconciled_metrics.sql

Results:
- Total quarters: 24
- Unique quarters: 24
- PLTR quarters: 12
- NVDA quarters: 12
- Original PASS observations: 23
- Supplemental reconciliations: 1
- Unresolved REVIEW observations: 0

Arithmetic errors: 0
Missing core metrics: 0
Availability validation errors: 0
Unexpected original-data changes: 0

Validation result: PASS

## 9. LTM Financial Comparison

File:
sql/19_compare_pltr_nvda_ltm.sql

LTM means the latest four reported
fiscal quarters for each company.

| Metric | PLTR | NVDA |
|---|---:|---:|
| LTM end | 2026-09-30 | 2026-07-26 |
| Revenue ($B) | 7.288 | 302.969 |
| Operating income ($B) | 3.326 | 197.579 |
| Revenue YoY (%) | 87.06 | 83.38 |
| Operating margin (%) | 45.64 | 65.21 |
| Simple FCF ($B) | 4.054 | 127.006 |
| Simple FCF margin (%) | 55.62 | 41.92 |

Both companies:
Internal LTM validation = PASS

## 10. Interpretation

PLTR:
- Higher LTM revenue growth rate
- Higher simple FCF margin

NVDA:
- Substantially larger revenue base
- Higher LTM operating margin
- Larger absolute operating cash flow

These observations are historical
financial comparisons, not investment
recommendations or valuations.

## 11. Limitations

1. Companies have different fiscal calendars
   and different LTM end dates.

2. NVDA CAPEX uses a provisional XBRL concept.

3. Simple FCF is not necessarily equal to
   company-reported free cash flow.

4. Some reported quarterly figures can differ
   from values reconstructed from YTD facts.

5. First-available Company Facts observations
   do not necessarily identify the earliest
   public disclosure of every financial amount.

6. Filing dates are used instead of precise
   intraday publication timestamps.

7. Restatements and tag transitions require
   additional historical testing.

8. Historical SEC figures are not independently
   verified against every original filing.

9. The current project does not include
   valuation, market price, or risk metrics.

## 12. Reproducibility

Main configuration files:
- config/companies.json
- config/metric_tags.json
- config/supplemental_facts.json

Core programs:
- src/check_company_config.py
- src/fetch_companyfacts.py
- src/inspect_xbrl_tags.py
- src/validate_fiscal_periods.py
- src/load_multi_company_duckdb.py
- src/build_quarterly_metrics_multi.py
- src/reconcile_quarterly_metrics.py

Validation queries:
- sql/15_validate_multi_company_ingestion.sql
- sql/18_validate_reconciled_metrics.sql
- sql/19_compare_pltr_nvda_ltm.sql

The workflow requires SEC data snapshots,
configuration files, Python dependencies,
and a local DuckDB database.

## 13. Week 4 Priorities

1. Standardize CAPEX and FCF definitions.
2. Improve tag-history mapping.
3. Add more U.S. technology companies.
4. Strengthen point-in-time data selection.
5. Automate multi-company quality checks.
6. Prepare a screening-ready data model.

---

## Conclusion

Week 3 successfully implemented a
multi-company quarterly financial analysis
pipeline using Python, SQL, DuckDB, and
SEC EDGAR financial data.

Internal validation: PASS

Further source reconciliation and FCF
definition standardization remain necessary
before production-grade comparisons.