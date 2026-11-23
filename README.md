
# JK's Financial Data Lab
### US Tech Fundamental Screener | Python · SQL · DuckDB · SEC EDGAR

[![Portable Regression](https://github.com/a01071209970-cyber/JK-s-Financial-data-lab/actions/workflows/portable-regression.yml/badge.svg)](https://github.com/a01071209970-cyber/JK-s-Financial-data-lab/actions/workflows/portable-regression.yml)

**Project status:** V0.5 — Four-company financial screening, guarded valuation and automated regression testing

**Research snapshot:** November 17, 2026 (US regular-session close)

## Overview

JK's Financial Data Lab is a financial data engineering and equity research project built to transform SEC filings into structured, auditable investment research.

The project combines Python, SQL and DuckDB to collect financial facts, reconstruct quarterly statements, validate reported metrics and screen US-listed technology companies.

Rather than treating every reported figure as immediately comparable, the system tracks filing availability, fiscal-period conventions, data reconciliation and valuation evidence.

The current universe consists of Palantir (PLTR), NVIDIA (NVDA), Advanced Micro Devices (AMD) and Microsoft (MSFT).

## Project Highlights

| Metric | Current implementation |
|---|---|
| Companies covered | 4 |
| SEC financial fact observations | 92,717 |
| Reconstructed quarterly records | 48 |
| Quarterly coverage | 12 quarters per company |
| Fundamental screener | V0.3 |
| Guarded valuation engine | V0.4.2 |
| Local regression tests | 10/10 passed |
| GitHub Actions portable tests | 8/8 passed |

The goal is not to produce a stock recommendation from a single ratio, but to develop a research workflow in which financial inputs, calculation decisions and limitations can be inspected.

## Research Snapshot

The table below reflects the November 17, 2026 historical screening snapshot.

| Ticker | Quarterly revenue YoY | Operating margin | Fundamental screen | Indicative EV/Sales | Valuation status |
|---|---:|---:|---|---:|---|
| NVDA | 105.85% | 66.24% | PASS | — | BLOCKED |
| PLTR | 95.87% | 46.89% | PASS | 50.34x | Note-based indicative |
| AMD | 44.68% | 21.17% | PASS | 17.98x | Indicative |
| MSFT | 18.80% | 49.76% | FAIL | 10.77x | Indicative |

The fundamental ranking is based on quarterly revenue growth, not investment attractiveness.

Microsoft fails the current minimum 20% quarterly revenue-growth filter. NVIDIA passes the fundamental screen, but its valuation is blocked because the available outstanding-share evidence is stale and rounded.

**These are historical research outputs, not real-time prices, certified enterprise values or investment recommendations.**

See the [Integrated Screening Report](reports/integrated_screen_v042_2026-11-17.md) for calculation status and methodological restrictions.

## Data Pipeline

```text
SEC EDGAR Company Facts
          |
          v
Raw XBRL Financial Observations
          |
          v
DuckDB Ingestion
          |
          v
Fiscal Calendar & SEC Tag Validation
          |
          v
Quarterly Financial Reconstruction
          |
          v
Financial Reconciliation & PIT Checks
          |
          v
Fundamental Screening
          |
          +-------------------------+
          |                         |
          v                         v
Historical Price Snapshot   Valuation Evidence Review
          |                         |
          +------------+------------+
                       |
                       v
              Guarded Valuation
                       |
                       v
             Integrated Research Report
                       |
                       v
              Regression Validation
```

### 1. SEC Financial Data Ingestion

Company Facts data is collected from SEC EDGAR and stored in DuckDB.

The current database contains 92,717 financial observations across PLTR, NVDA, AMD and MSFT.

The pipeline preserves filing-related information required to examine historical reporting and data availability.

### 2. Quarterly Financial Reconstruction

SEC filings can report cumulative year-to-date values rather than standalone quarterly figures.

The project reconstructs quarterly observations while accounting for fiscal calendars, SEC XBRL tags and differences between directly reported and derived values.

Selected metrics include:

- Revenue and quarterly revenue growth
- Operating income and operating margin
- Operating cash flow
- Capital expenditure
- Free cash flow
- LTM financial aggregates

Company-specific reconciliation policies are used where reported definitions or available observations differ.

### 3. Fundamental Screening

The V0.3 screener evaluates financial performance using configurable rules.

The current policy includes:

- Minimum quarterly revenue growth of 20%
- Operating margin of at least 10%, or qualifying year-over-year improvement
- Minimum historical coverage of eight quarters
- Filing recency checks
- Explicit handling of incomplete financial observations

Free cash flow is not used for a cross-company ranking under the current comparability policy.

Screening rules are stored in [config/screening_rules_v03.json](config/screening_rules_v03.json).

### 4. Guarded Valuation

The valuation layer combines historical closing prices, outstanding-share evidence and selected balance-sheet inputs.

It estimates indicative enterprise values and valuation multiples where the underlying evidence satisfies the project's review rules.

The engine distinguishes:

- `INDICATIVE`: provisional valuation calculation
- `INDICATIVE_NOTE_BASED`: provisional calculation using manually reviewed filing-note evidence
- `BLOCKED_SHARE_COUNT`: valuation withheld because share-count evidence is insufficient

A missing financial value is not automatically interpreted as zero.

Enterprise-value calculations with different financial input policies are not treated as fully comparable investment rankings.

### 5. Point-in-Time Controls

The project applies point-in-time checks to reduce the risk of using information unavailable at the selected valuation date.

Examples include:

- Filing-date eligibility checks
- Share-count measurement-date reviews
- Exclusion of identified post-close filings
- Historical price checksum verification
- Preservation of earlier valuation results
- Separate reporting for blocked and provisional outputs

For NVIDIA, a post-close filing is not allowed to justify the November 17, 2026 regular-session closing valuation.

## Data Quality and Audit Principles

Financial observations are not assumed to be correct or comparable merely because they are present in an API response.

The project follows five principles:

1. **Traceability:** Preserve relevant source dates, filing identifiers and calculation evidence.
2. **Period consistency:** Separate standalone quarterly observations from year-to-date data.
3. **No fabricated inputs:** Missing observations require reconciliation or explicit exclusion.
4. **Point-in-time discipline:** Avoid using information unavailable at the historical research cutoff.
5. **Conservative valuation approval:** Flag or block results when required evidence is incomplete.

The regression suite additionally checks historical output consistency, calculations, data counts and selected audit decisions.

## Repository Structure

```text
JK-s-Financial-data-lab/
|
|-- .github/workflows/
|   `-- portable-regression.yml
|
|-- config/
|   |-- companies.json
|   |-- screening_rules_v03.json
|   |-- valuation_input_policy.json
|   `-- pit_evidence_v04.json
|
|-- src/
|   |-- fetch_companyfacts.py
|   |-- load_multi_company_duckdb.py
|   |-- build_four_company_quarters.py
|   |-- run_four_company_screen.py
|   |-- build_valuation_preview_v04.py
|   `-- build_integrated_screen_v042.py
|
|-- sql/
|   `-- Financial validation and analysis queries
|
|-- reports/
|   |-- screen_v03_2026-11-17.csv
|   |-- valuation_preview_v04_2026-11-17.csv
|   |-- integrated_screen_v042_2026-11-17.csv
|   `-- integrated_screen_v042_2026-11-17.md
|
|-- tests/
|   |-- test_regression_v05.py
|   `-- run_portable_v05.py
|
|-- requirements.txt
`-- README.md
```

The tree highlights the primary components; additional audit scripts, configuration files and reports are available in the respective directories.

## Reproducing the Tests

### Portable regression tests

Clone the repository and execute:

```bash
git clone https://github.com/a01071209970-cyber/JK-s-Financial-data-lab.git
cd JK-s-Financial-data-lab

python3 tests/run_portable_v05.py
```

This test suite uses Python's standard library and checks eight committed-artifact invariants.

It does not require DuckDB, raw SEC data or network access during test execution.

Expected result:

```text
Ran 8 tests

OK

Portable regression: PASS
Tests: 8/8
Skipped: 0
Failed: 0
```

### Full local regression tests

The full suite includes two additional tests that require locally retained historical price data and the processed DuckDB database.

In an environment with the required local files and dependencies:

```bash
python -m unittest discover -s tests -p "test_regression_v05.py" -v
```

The development environment has passed all 10 tests.

**Important:** Raw SEC downloads, historical price source files and the DuckDB database are excluded from Git. A fresh clone does not contain the complete analytical dataset.

Consequently, local-only tests may be skipped on a fresh clone. Such a result must not be represented as full end-to-end validation.

## Continuous Integration

GitHub Actions executes the portable regression suite on:

- Pushes to `main`
- Pull requests targeting `main`
- Manual workflow dispatches

Workflow file: [.github/workflows/portable-regression.yml](.github/workflows/portable-regression.yml)

The portable runner rejects test failures, errors, unexpected skips and unexpected changes to the test inventory.

GitHub Actions currently validates committed artifacts, not the full raw-data ingestion pipeline.

## Selected Research Artifacts

| Artifact | Description |
|---|---|
| [Fundamental Screen V0.3](reports/screen_v03_2026-11-17.csv) | Four-company financial screening results |
| [Valuation Preview V0.4](reports/valuation_preview_v04_2026-11-17.csv) | Historical indicative valuation and blocking decisions |
| [PLTR Valuation Evidence](reports/pltr_valuation_review_v041_2026-11-17.md) | Note-based liquidity and enterprise-value reconciliation |
| [NVDA Share Uncertainty](reports/nvda_share_uncertainty_v041_2026-11-17.md) | Stale share-count evidence and sensitivity analysis |
| [Integrated Screen V0.4.2](reports/integrated_screen_v042_2026-11-17.md) | Combined research results and audit limitations |
| [Week 4 Validation](reports/week4_validation.md) | Four-company financial data validation |

## Data Sources

**Financial filings:** [SEC EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

**Historical market prices:** Yahoo Finance historical closing-price snapshot, retained locally with checksum metadata.

SEC filing notes are used for selected reconciliations. Some evidence is manually documented rather than automatically retrieved and verified.

Historical market-price downloads performed after the valuation date may reflect subsequent vendor adjustments or revisions.

## Current Limitations

- The analyzed universe is limited to four companies.
- The source database and raw price snapshots are not bundled with the public repository.
- NVIDIA's historical valuation remains blocked due to share-count limitations.
- PLTR valuation includes manually documented note-based assumptions.
- Base EV definitions exclude certain lease liabilities and may vary by company.
- Cross-company FCF comparability is not fully standardized.
- Point-in-time controls cover specific audited scenarios; they are not a complete institutional-grade backtesting framework.
- Outputs are historical research illustrations rather than live investment signals.

## Development Roadmap

### Completed

- SEC financial ingestion and DuckDB storage
- Four-company quarterly financial reconstruction
- Configurable fundamental screening
- Historical price and valuation evidence audits
- Integrated fundamental and guarded valuation report
- Ten local regression tests
- Eight portable regression tests in GitHub Actions

### Planned

- Expand coverage from four to ten technology companies
- Standardize additional balance-sheet and risk metrics
- Improve automated filing-note reconciliation
- Strengthen point-in-time data replay and source provenance
- Develop screening dashboards and research-ready visualizations
- Expand integration and data-quality tests

## Disclaimer

This repository is an independent financial data analysis and research-engineering project.

Figures, screening decisions and valuation estimates are provided for educational and research purposes only. They do not constitute investment advice or guaranteed historical point-in-time valuations.