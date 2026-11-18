
"""
JK's Financial Data Lab V1.0
Week 4 - Four Company Quarterly Preflight

Read-only preview of 12 quarters per company.

Uses the existing Week 3 quarterly engine.
Does not modify or replace any DuckDB table.

Run:
    python src/preflight_four_company_quarters.py
"""

import json
from collections import Counter
from datetime import date
from pathlib import Path

import duckdb

from check_company_config import load_companies

from build_quarterly_metrics_multi import (
    read_index,
    build_rows
)


ROOT = Path(__file__).resolve().parent.parent

DB = ROOT / "data/processed/financial_data.duckdb"

TAG_CONFIG = ROOT / "config/metric_tags.json"

AS_OF = date(2026, 11, 17)

EXPECTED_FACTS = {
    "AMD": 24244,
    "MSFT": 33058,
    "NVDA": 27281,
    "PLTR": 8134
}

EXPECTED_LATEST = {
    ("AMD", 2026, 3): (
        13377000000,
        2832000000,
        1202000000,
        648000000
    ),
    ("MSFT", 2027, 1): (
        92279000000,
        45915000000,
        58000000000,
        39367000000
    )
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scalar(con, sql):
    result = con.execute(sql).fetchone()

    require(
        result is not None,
        "Expected a scalar result"
    )

    return result[0]


def comparable(value):
    if value is None:
        return None

    return int(value)


def verify_existing_database(con):

    facts = dict(con.execute("""
        SELECT ticker, COUNT(*)
        FROM financial_facts_multi
        GROUP BY ticker
    """).fetchall())

    require(
        facts == EXPECTED_FACTS,
        f"Unexpected raw fact counts: {facts}"
    )

    companies = scalar(
        con,
        "SELECT COUNT(*) FROM companies_multi"
    )

    require(
        companies == 4,
        "Expected four registered companies"
    )

    protected_counts = {
        "financial_facts": 8134,
        "quarterly_metrics": 12,
        "quarterly_metrics_multi": 24,
        "quarterly_metrics_reconciled": 24,
        "company_fcf_reconciliations": 2
    }

    for table, expected in protected_counts.items():

        actual = scalar(
            con,
            f"SELECT COUNT(*) FROM {table}"
        )

        require(
            actual == expected,
            f"{table}: expected {expected}, got {actual}"
        )

    print("SEC observations: 92,717 | PASS")
    print("Existing protected tables: PASS")


def load_existing_baseline(con):

    rows = con.execute("""
        SELECT
            ticker,
            fiscal_year,
            fiscal_quarter,

            revenue_usd,
            operating_income_usd,
            ocf_usd,
            capex_usd,
            fcf_usd,

            validation_status

        FROM quarterly_metrics_multi

        WHERE ticker IN ('PLTR', 'NVDA')
    """).fetchall()

    baseline = {}

    for row in rows:

        key = (
            row[0],
            row[1],
            row[2]
        )

        require(
            key not in baseline,
            f"Duplicate historical key: {key}"
        )

        baseline[key] = (
            tuple(
                comparable(value)
                for value in row[3:8]
            ),
            row[8]
        )

    require(
        len(baseline) == 24,
        "Expected 24 Week 3 baseline quarters"
    )

    return baseline


def validate_new_latest(rows):

    lookup = {
        (r[1], r[2], r[3]): r
        for r in rows
    }

    for key, expected in EXPECTED_LATEST.items():

        require(
            key in lookup,
            f"Missing target quarter: {key}"
        )

        row = lookup[key]

        actual = tuple(
            comparable(value)
            for value in row[6:10]
        )

        require(
            actual == expected,
            (
                f"{key}: quarterly metric mismatch. "
                f"Actual={actual}, expected={expected}"
            )
        )

        require(
            row[22] == "PASS",
            f"{key}: latest quarter is not PASS"
        )

        print(
            f"{key[0]} FY{key[1]} Q{key[2]} "
            "source cross-check: PASS"
        )


def validate_regression(rows, baseline):

    checked = 0

    for row in rows:

        ticker = row[1]

        if ticker not in ("PLTR", "NVDA"):
            continue

        key = (
            ticker,
            row[2],
            row[3]
        )

        require(
            key in baseline,
            f"Missing Week 3 baseline: {key}"
        )

        actual_values = tuple(
            comparable(value)
            for value in row[6:11]
        )

        actual_status = row[22]

        old_values, old_status = baseline[key]

        require(
            actual_values == old_values,
            f"Historical metric changed: {key}"
        )

        require(
            actual_status == old_status,
            f"Historical status changed: {key}"
        )

        checked += 1

    require(
        checked == 24,
        f"Expected 24 regression checks, got {checked}"
    )

    print("PLTR/NVDA 24-quarter regression: PASS")


def main():

    companies = load_companies()

    by_ticker = {
        company["ticker"]: company
        for company in companies
    }

    require(
        len(companies) == 4,
        "Expected four configured companies"
    )

    require(
        set(by_ticker) == set(EXPECTED_FACTS),
        "Unexpected company configuration"
    )

    config = json.loads(
        TAG_CONFIG.read_text(encoding="utf-8")
    )

    require(
        config.get("version") == 1,
        "Invalid metric tag configuration"
    )

    mappings = config["metric_tags"]

    require(
        set(mappings) == set(EXPECTED_FACTS),
        "Company and XBRL mappings do not match"
    )

    con = duckdb.connect(
        str(DB),
        read_only=True
    )

    try:

        print()
        print("FOUR-COMPANY QUARTERLY PREFLIGHT")
        print("=" * 65)

        verify_existing_database(con)

        baseline = load_existing_baseline(con)

        # Reuse the existing Week 3 SEC fact reader.
        index = read_index(
            con,
            mappings,
            AS_OF
        )

        all_rows = []

        for ticker in (
            "PLTR",
            "NVDA",
            "AMD",
            "MSFT"
        ):

            rows = build_rows(
                by_ticker[ticker],
                mappings[ticker],
                index,
                AS_OF
            )

            require(
                len(rows) == 12,
                f"{ticker}: Expected 12 quarters"
            )

            require(
                all(row[1] == ticker for row in rows),
                f"{ticker}: Incorrect ticker in output"
            )

            all_rows.extend(rows)

        require(
            len(all_rows) == 48,
            "Expected 48 generated quarterly records"
        )

        keys = [
            (r[1], r[2], r[3])
            for r in all_rows
        ]

        require(
            len(keys) == len(set(keys)),
            "Duplicate fiscal quarters"
        )

        print()
        print("SOURCE CROSS-CHECKS")
        print("-" * 65)

        validate_new_latest(all_rows)
        validate_regression(all_rows, baseline)

        print()
        print("QUARTER COVERAGE")
        print("-" * 65)

        all_review = []

        for ticker in sorted(by_ticker):

            rows = [
                r for r in all_rows
                if r[1] == ticker
            ]

            rows.sort(
                key=lambda r: (r[2], r[3])
            )

            status_count = Counter(
                r[22] for r in rows
            )

            passed = status_count.get("PASS", 0)
            review = status_count.get("REVIEW", 0)

            first = rows[0]
            latest = rows[-1]

            print()
            print(
                f"{ticker}: 12 quarters "
                f"| PASS={passed} | REVIEW={review}"
            )

            print(
                "Range:",
                f"FY{first[2]} Q{first[3]}",
                "~",
                f"FY{latest[2]} Q{latest[3]}"
            )

            if ticker in ("AMD", "MSFT"):

                print("Quarter details:")

                for row in rows:

                    print(
                        f"  FY{row[2]} Q{row[3]}"
                        f" | {row[5]}"
                        f" | {row[22]}"
                    )

            for row in rows:

                if row[22] != "PASS":
                    all_review.append((
                        ticker,
                        row[2],
                        row[3],
                        row[22]
                    ))

        print()
        print("SUMMARY")
        print("=" * 65)

        total_pass = sum(
            row[22] == "PASS"
            for row in all_rows
        )

        print("Companies:", len(by_ticker))
        print("Generated quarters:", len(all_rows))
        print("PASS:", total_pass)
        print("REVIEW:", len(all_review))

        print("Existing 24-quarter regression: PASS")
        print("Database mode: READ ONLY")

        if all_review:

            print()
            print("QUARTERS REQUIRING REVIEW")
            print("-" * 65)

            for ticker, fy, q, status in all_review:

                print(
                    f"{ticker} FY{fy} Q{q}: {status}"
                )

            print()
            print(
                "Preflight: COMPLETE "
                "(review quarters require reconciliation)"
            )

        else:

            print()
            print("Four-company preflight: PASS")

        print("Original tables: UNCHANGED")

    finally:
        con.close()


if __name__ == "__main__":
    main()