
"""
JK's Financial Data Lab V1.0
Week 4 - Configurable Fundamental Screener V0.2

Uses:
    config/screening_rules.json
    config/screening_metric_policy.json
    sql/23_configurable_fundamental_screen.sql

Run:
    python src/run_configurable_screen.py

Read-only. Does not modify DuckDB.
"""

import json
import math
from datetime import date
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parent.parent

DB_PATH = (
    ROOT / "data/processed/financial_data.duckdb"
)

RULES_PATH = (
    ROOT / "config/screening_rules.json"
)

POLICY_PATH = (
    ROOT / "config/screening_metric_policy.json"
)

SQL_PATH = (
    ROOT / "sql/23_configurable_fundamental_screen.sql"
)

BASELINE_SQL_PATH = (
    ROOT / "sql/22_first_fundamental_screen.sql"
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def read_rows(connection, sql, params=None):
    result = connection.execute(sql, params or [])

    columns = [
        column[0]
        for column in result.description
    ]

    return [
        dict(zip(columns, row))
        for row in result.fetchall()
    ]


def validate_configuration(rules, policy):

    require(
        rules.get("version") == 1,
        "Unsupported screening rules version"
    )

    require(
        policy.get("version") == 1,
        "Unsupported metric policy version"
    )

    cutoff = date.fromisoformat(
        rules["as_of_date"]
    )

    require(
        rules["as_of_date"] == policy["as_of_date"],
        "Rules and metric policy have different cutoff dates"
    )

    tickers = rules["expected_tickers"]

    require(
        isinstance(tickers, list)
        and bool(tickers)
        and len(tickers) == len(set(tickers))
        and all(
            isinstance(ticker, str)
            and ticker.isalnum()
            and ticker == ticker.upper()
            for ticker in tickers
        ),
        "Invalid or duplicate expected tickers"
    )

    require(
        rules["required_history_quarters"] == 8,
        "V0.2 requires exactly 8 fiscal quarters"
    )

    numeric_keys = (
        "min_revenue_yoy_pct",
        "min_operating_margin_pct",
        "min_operating_margin_improvement_pp"
    )

    for key in numeric_keys:
        value = rules[key]

        require(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value),
            f"Invalid numeric rule: {key}"
        )

    max_age = rules["max_filing_age_days"]

    require(
        isinstance(max_age, int)
        and not isinstance(max_age, bool)
        and 0 <= max_age <= 3650,
        "Invalid max_filing_age_days"
    )

    metrics = policy["metrics"]

    for metric in (
        "revenue_growth_yoy_pct",
        "operating_margin_pct"
    ):
        require(
            metrics[metric]["cross_company_ranking"] is True,
            f"Required screening metric blocked: {metric}"
        )

    for metric in (
        "fcf_margin_pct",
        "company_reported_fcf_usd"
    ):
        require(
            metrics[metric]["cross_company_ranking"] is False,
            f"Unsafe FCF ranking enabled: {metric}"
        )

    require(
        rules["fcf_cross_company_ranking"] is False,
        "FCF ranking must remain disabled"
    )

    return cutoff


def baseline_rules(rules):
    return (
        rules["as_of_date"] == "2026-11-17"
        and rules["min_revenue_yoy_pct"] == 20.0
        and rules["min_operating_margin_pct"] == 10.0
        and rules["min_operating_margin_improvement_pp"] == 0.0
        and rules["max_filing_age_days"] == 180
    )


def compare_with_v01(connection, current_rows):

    old_sql = BASELINE_SQL_PATH.read_text(
        encoding="utf-8"
    )

    old_rows = read_rows(
        connection,
        old_sql
    )

    old_by_ticker = {
        row["ticker"]: row
        for row in old_rows
    }

    current_by_ticker = {
        row["ticker"]: row
        for row in current_rows
    }

    require(
        set(old_by_ticker) == set(current_by_ticker),
        "V0.1 and V0.2 ticker coverage mismatch"
    )

    columns_to_compare = (
        "latest_revenue_yoy_pct",
        "latest_operating_margin_pct",
        "latest_margin_change_pp",
        "ltm_revenue_yoy_pct",
        "ltm_operating_margin_pct",
        "data_quality_status",
        "fundamental_screen_status",
        "screening_reason"
    )

    for ticker in current_by_ticker:

        old = old_by_ticker[ticker]
        new = current_by_ticker[ticker]

        for column in columns_to_compare:
            require(
                old[column] == new[column],
                f"V0.1 regression mismatch: {ticker} {column}"
            )

    print("V0.1 regression comparison: PASS")


def main():

    rules = read_json(RULES_PATH)
    policy = read_json(POLICY_PATH)

    cutoff = validate_configuration(
        rules,
        policy
    )

    sql = SQL_PATH.read_text(
        encoding="utf-8"
    )

    # SQL parameters must follow the order of
    # question marks in the PARAMETERS CTE.
    params = [
        cutoff,
        float(rules["min_revenue_yoy_pct"]),
        float(rules["min_operating_margin_pct"]),
        float(rules["min_operating_margin_improvement_pp"]),
        rules["max_filing_age_days"]
    ]

    connection = duckdb.connect(
        str(DB_PATH),
        read_only=True
    )

    try:
        rows = read_rows(
            connection,
            sql,
            params
        )

        actual_tickers = {
            row["ticker"]
            for row in rows
        }

        require(
            actual_tickers == set(rules["expected_tickers"]),
            "Screening universe does not match configuration"
        )

        require(
            len(rows) == len(actual_tickers),
            "Duplicate screening results"
        )

        for row in rows:
            require(
                row["fcf_cross_company_ranking"] == "BLOCKED",
                "FCF ranking restriction failed"
            )

            require(
                row["market_cap_debt_analyst_filters"]
                == "NOT_EVALUATED",
                "Unimplemented filters must remain unverified"
            )

        print()
        print("FUNDAMENTAL SCREENER V0.2")
        print("-" * 70)

        print("Data cutoff:", cutoff)

        print(
            "Revenue YoY threshold:",
            rules["min_revenue_yoy_pct"],
            "%"
        )

        print(
            "Operating margin threshold:",
            rules["min_operating_margin_pct"],
            "%"
        )

        print(
            "Maximum filing age:",
            rules["max_filing_age_days"],
            "days"
        )

        print()

        for row in rows:

            print(
                f"{row['ticker']} "
                f"FY{row['latest_fiscal_year']}"
                f" Q{row['latest_fiscal_quarter']}"
            )

            print(
                "  Revenue YoY:",
                row["latest_revenue_yoy_pct"],
                "%"
            )

            print(
                "  Operating margin:",
                row["latest_operating_margin_pct"],
                "%"
            )

            print(
                "  Margin YoY change:",
                row["latest_margin_change_pp"],
                "pp"
            )

            print(
                "  Data quality:",
                row["data_quality_status"]
            )

            print(
                "  Fundamental screen:",
                row["fundamental_screen_status"]
            )

            print(
                "  Reason:",
                row["screening_reason"]
            )

            print()

        if baseline_rules(rules):
            compare_with_v01(
                connection,
                rows
            )
        else:
            print(
                "V0.1 comparison: SKIPPED "
                "(screening parameters changed)"
            )

        passed = sum(
            row["fundamental_screen_status"] == "PASS"
            for row in rows
        )

        reviewed = sum(
            row["fundamental_screen_status"] == "REVIEW"
            for row in rows
        )

        print()
        print("SCREENING SUMMARY")
        print("-" * 70)

        print("Companies evaluated:", len(rows))
        print("Fundamental PASS:", passed)
        print("Fundamental REVIEW:", reviewed)

        print("FCF ranking: BLOCKED")
        print("Market cap / debt / analysts: NOT EVALUATED")
        print("Database: READ ONLY")

        print()
        print("Configurable screening execution: PASS")

    finally:
        connection.close()


if __name__ == "__main__":
    main()