
"""
JK's Financial Data Lab V1.0
Week 4 - Export validated Fundamental Screener V0.3 results.

Outputs:
    reports/week4_validation.md
    reports/screen_v03_YYYY-MM-DD.csv

Reads DuckDB in read-only mode.
No database modification and no network access.
"""

import csv
from datetime import date
from decimal import Decimal

import duckdb

from run_four_company_screen import (
    DB_PATH,
    ROOT,
    calculate_company,
    check_database,
    load_rules,
    read_quarters,
    validate_historical_regression,
    validate_quarter_sequence,
)


REPORTS = ROOT / "reports"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rounded(value):
    return f"{value:.2f}"


def order_results(results):
    return sorted(
        results,
        key=lambda r: (
            r["passed"],
            r["revenue_yoy"],
            r["operating_margin"],
        ),
        reverse=True,
    )


def collect_results():

    rules, as_of = load_rules()

    require(
        DB_PATH.exists(),
        f"Missing database: {DB_PATH}"
    )

    con = duckdb.connect(
        str(DB_PATH),
        read_only=True
    )

    try:
        check_database(con)

        records = read_quarters(con)

        validate_historical_regression(
            con,
            records
        )

        grouped = {
            ticker: []
            for ticker in rules["expected_tickers"]
        }

        for record in records:

            ticker = record["ticker"]

            require(
                ticker in grouped,
                f"Unknown company: {ticker}"
            )

            grouped[ticker].append(record)

        results = []

        for ticker, rows in grouped.items():

            validate_quarter_sequence(
                ticker,
                rows,
                as_of
            )

            results.append(
                calculate_company(
                    ticker,
                    rows,
                    rules,
                    as_of
                )
            )

        require(
            len(results) == 4,
            "Expected four companies"
        )

        passed = {
            r["ticker"]
            for r in results
            if r["passed"]
        }

        failed = {
            r["ticker"]
            for r in results
            if not r["passed"]
        }

        require(
            passed == {"PLTR", "NVDA", "AMD"}
            and failed == {"MSFT"},
            (
                "Unexpected screening baseline: "
                f"pass={passed}, fail={failed}"
            )
        )

        return (
            rules,
            as_of,
            order_results(results)
        )

    finally:
        con.close()


def write_csv(path, results):

    fields = [
        "ticker",
        "fiscal_year",
        "fiscal_quarter",
        "period_end",
        "quarterly_revenue_yoy_pct",
        "operating_margin_pct",
        "operating_margin_yoy_change_pp",
        "ocf_margin_pct",
        "ltm_revenue_usd",
        "ltm_revenue_yoy_pct",
        "ltm_operating_margin_pct",
        "filing_age_days",
        "fundamental_status",
        "failure_reasons",
    ]

    with path.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields
        )

        writer.writeheader()

        for r in results:

            writer.writerow({
                "ticker": r["ticker"],
                "fiscal_year": r["fiscal_year"],
                "fiscal_quarter": r["fiscal_quarter"],
                "period_end": (
                    r["period_end"].isoformat()
                ),
                "quarterly_revenue_yoy_pct": (
                    rounded(r["revenue_yoy"])
                ),
                "operating_margin_pct": (
                    rounded(r["operating_margin"])
                ),
                "operating_margin_yoy_change_pp": (
                    rounded(r["margin_improvement"])
                ),
                "ocf_margin_pct": (
                    rounded(r["ocf_margin"])
                ),
                "ltm_revenue_usd": str(
                    r["ltm_revenue"]
                ),
                "ltm_revenue_yoy_pct": (
                    rounded(r["ltm_revenue_yoy"])
                ),
                "ltm_operating_margin_pct": (
                    rounded(r["ltm_operating_margin"])
                ),
                "filing_age_days": r["filing_age"],
                "fundamental_status": (
                    "PASS" if r["passed"] else "FAIL"
                ),
                "failure_reasons": "; ".join(
                    r["failed_reasons"]
                ),
            })


def write_report(
    path,
    rules,
    as_of,
    results
):

    passed = sum(
        r["passed"]
        for r in results
    )

    lines = [
        "# JK's Financial Data Lab — Week 4 Validation Report",
        "",
        f"**As-of:** {as_of.isoformat()}  ",
        "**Model:** Fundamental Screener V0.3  ",
        "**Scope:** PLTR, NVDA, AMD, MSFT  ",
        "**Data source:** Local SEC Company Facts in DuckDB  ",
        "**Database mode during screening:** Read only",
        "",
        "## Data integrity",
        "",
        "| Check | Result |",
        "|---|---|",
        "| Raw SEC observations | 92,717 |",
        "| Companies | 4 |",
        "| Quarters per company | 12 |",
        "| Quarterly metrics | 48 |",
        "| SEC-only validated quarters | 47 |",
        "| NVDA FY2024 Q3 supplemental CAPEX reconciliation | 1 |",
        "| Original PLTR/NVDA 24-quarter regression | PASS |",
        "| Source tables during export | UNCHANGED |",
        "",
        "## Fundamental screen",
        "",
        (
            f"**Result:** {passed} PASS / "
            f"{len(results) - passed} FAIL"
        ),
        "",
        "| Rank | Ticker | Latest fiscal quarter | Quarterly revenue YoY | Operating margin | LTM revenue YoY | Status |",
        "|---:|---|---|---:|---:|---:|---|",
    ]

    for rank, r in enumerate(
        results,
        start=1
    ):

        period = (
            f"FY{r['fiscal_year']} "
            f"Q{r['fiscal_quarter']}"
        )

        status = (
            "PASS"
            if r["passed"]
            else "FAIL"
        )

        lines.append(
            f"| {rank} | {r['ticker']} | {period} | "
            f"{rounded(r['revenue_yoy'])}% | "
            f"{rounded(r['operating_margin'])}% | "
            f"{rounded(r['ltm_revenue_yoy'])}% | "
            f"{status} |"
        )

    lines.extend([
        "",
        "## LTM comparison",
        "",
        "| Ticker | LTM revenue (USD bn) | LTM operating margin | Quarterly OCF margin (secondary) | Filing age (days) |",
        "|---|---:|---:|---:|---:|",
    ])

    for r in results:

        ltm_billions = (
            r["ltm_revenue"]
            / Decimal("1000000000")
        )

        lines.append(
            f"| {r['ticker']} | "
            f"{ltm_billions:,.3f} | "
            f"{rounded(r['ltm_operating_margin'])}% | "
            f"{rounded(r['ocf_margin'])}% | "
            f"{r['filing_age']} |"
        )

    lines.extend([
        "",
        "## Methodology",
        "",
        (
            "- Quarterly revenue growth threshold: "
            f"{rules['min_revenue_yoy_pct']}% YoY."
        ),
        (
            "- Profitability: operating margin at least "
            f"{rules['min_operating_margin_pct']}%, "
            "or YoY margin improvement greater than "
            f"{rules['min_operating_margin_improvement_pp']} "
            "percentage points."
        ),
        (
            "- Required validated history: "
            f"{rules['required_history_quarters']} quarters."
        ),
        (
            "- Latest filing maximum age: "
            f"{rules['max_filing_age_days']} days."
        ),
        "- LTM revenue is the sum of four latest quarters; LTM growth compares the prior four quarters.",
        "- OCF margin is a supplementary metric, not a screening threshold.",
        "- FCF and adjusted/official FCF are excluded from cross-company ranking due to differing definitions.",
        "",
        "## Limits and interpretation",
        "",
        "- MSFT fails only the 20% quarterly revenue-growth requirement; this is not a financial-distress finding.",
        "- This is a fundamental first-stage filter, not an investment recommendation or expected-return ranking.",
        "- Market capitalization, debt ratios, analyst coverage, share prices and technical signals have not been incorporated.",
        "- Data reflects SEC information available by the configured as-of date, not live market conditions.",
        "- NVDA FY2024 Q3 CAPEX was reconciled from a previously validated supplemental record; provenance remains in the database.",
        "",
    ])

    path.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )


def main():

    rules, as_of, results = (
        collect_results()
    )

    REPORTS.mkdir(
        parents=True,
        exist_ok=True
    )

    csv_path = (
        REPORTS /
        f"screen_v03_{as_of.isoformat()}.csv"
    )

    md_path = (
        REPORTS /
        "week4_validation.md"
    )

    write_csv(
        csv_path,
        results
    )

    write_report(
        md_path,
        rules,
        as_of,
        results
    )

    with csv_path.open(
        encoding="utf-8",
        newline=""
    ) as handle:

        output_rows = list(
            csv.DictReader(handle)
        )

    require(
        len(output_rows) == 4,
        "CSV row count mismatch"
    )

    require(
        md_path.exists()
        and md_path.stat().st_size > 0,
        "Report missing"
    )

    print()
    print("WEEK 4 REPORT EXPORT")
    print("-" * 45)

    print(
        "CSV:",
        csv_path.relative_to(ROOT)
    )

    print(
        "Markdown:",
        md_path.relative_to(ROOT)
    )

    print(
        "Companies: 4 | PASS=3 | FAIL=1"
    )

    print("Database: READ ONLY")
    print("Week 4 reporting: PASS")


if __name__ == "__main__":
    main()