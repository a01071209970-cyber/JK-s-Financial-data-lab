
"""
JK's Financial Data Lab V1.0
Week 4 - Four-Company Quarterly Metrics

Creates:
    quarterly_metrics_four
    quarterly_metrics_four_reconciled

Preserves Week 1-4 source and historical quarterly tables.

Usage:
    python src/build_four_company_quarters.py
    python src/build_four_company_quarters.py --apply

Default: read-only dry run.
"""

import argparse
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb

from check_company_config import load_companies
from build_quarterly_metrics_multi import read_index, build_rows


ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data/processed/financial_data.duckdb"
TAGS = ROOT / "config/metric_tags.json"
AS_OF = date(2026, 11, 17)

EXPECTED_FACTS = {
    "AMD": 24244,
    "MSFT": 33058,
    "NVDA": 27281,
    "PLTR": 8134,
}

PROTECTED = {
    "financial_facts": 8134,
    "quarterly_metrics": 12,
    "financial_facts_multi": 92717,
    "quarterly_metrics_multi": 24,
    "quarterly_metrics_reconciled": 24,
    "company_fcf_reconciliations": 2,
}

NEW_RAW_TABLE = "quarterly_metrics_four"

NEW_RECONCILED_TABLE = (
    "quarterly_metrics_four_reconciled"
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scalar(con, sql):
    row = con.execute(sql).fetchone()

    require(
        row is not None and len(row) == 1,
        "Expected one scalar result"
    )

    return row[0]


def protected_snapshot(con):
    counts = {}

    for table, expected in PROTECTED.items():

        count = scalar(
            con,
            f"SELECT COUNT(*) FROM {table}"
        )

        require(
            count == expected,
            f"{table}: expected {expected}, got {count}"
        )

        counts[table] = count

    facts = dict(
        con.execute("""
            SELECT ticker, COUNT(*)
            FROM financial_facts_multi
            GROUP BY ticker
        """).fetchall()
    )

    require(
        facts == EXPECTED_FACTS,
        f"SEC company counts changed: {facts}"
    )

    registered = dict(
        con.execute("""
            SELECT ticker, COUNT(*)
            FROM companies_multi
            GROUP BY ticker
        """).fetchall()
    )

    require(
        registered == {
            ticker: 1
            for ticker in EXPECTED_FACTS
        },
        f"Company registration mismatch: {registered}"
    )

    return counts


def get_existing_baseline(con):

    rows = con.execute("""
        SELECT *
        FROM quarterly_metrics_multi
    """).fetchall()

    baseline = {}

    for row in rows:

        key = (
            row[1],
            row[2],
            row[3]
        )

        require(
            key not in baseline,
            f"Duplicate baseline quarter: {key}"
        )

        baseline[key] = row

    require(
        len(baseline) == 24,
        "Expected 24 existing quarterly records"
    )

    return baseline


def compare_week3(rows, baseline):

    checked = 0

    for row in rows:

        key = (
            row[1],
            row[2],
            row[3]
        )

        if key not in baseline:
            continue

        previous = baseline[key]

        require(
            tuple(row[:21]) == tuple(previous[:21]),
            f"Week 3 financial regression: {key}"
        )

        require(
            row[22] == previous[22],
            f"Week 3 status regression: {key}"
        )

        require(
            json.loads(row[21])
            == json.loads(previous[21]),
            f"Week 3 provenance regression: {key}"
        )

        checked += 1

    require(
        checked == 24,
        f"Expected 24 regression checks, got {checked}"
    )

    print(
        "PLTR/NVDA regression: PASS (24 quarters)"
    )


def build_preview(con):

    companies = load_companies()

    by_ticker = {
        item["ticker"]: item
        for item in companies
    }

    require(
        len(companies) == 4,
        "Expected four company configurations"
    )

    require(
        set(by_ticker) == set(EXPECTED_FACTS),
        "Company mismatch"
    )

    config = json.loads(
        TAGS.read_text(encoding="utf-8")
    )

    require(
        config.get("version") == 1,
        "Unsupported tag configuration"
    )

    mappings = config["metric_tags"]

    require(
        set(mappings) == set(EXPECTED_FACTS),
        "Metric mapping mismatch"
    )

    baseline = get_existing_baseline(con)

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
            all(
                row[1] == ticker
                and row[20] == AS_OF
                for row in rows
            ),
            f"{ticker}: Invalid ticker or cutoff"
        )

        all_rows.extend(rows)

    require(
        len(all_rows) == 48,
        "Expected 48 quarters"
    )

    keys = [
        (row[1], row[2], row[3])
        for row in all_rows
    ]

    require(
        len(keys) == len(set(keys)),
        "Duplicate fiscal quarters"
    )

    statuses = Counter(
        row[22] for row in all_rows
    )

    require(
        statuses == {
            "PASS": 47,
            "REVIEW": 1
        },
        f"Unexpected raw statuses: {statuses}"
    )

    reviews = [
        (row[1], row[2], row[3])
        for row in all_rows
        if row[22] == "REVIEW"
    ]

    require(
        reviews == [("NVDA", 2024, 3)],
        f"Unexpected REVIEW quarters: {reviews}"
    )

    compare_week3(
        all_rows,
        baseline
    )

    return all_rows


def get_verified_supplement(con):
    """
    Reuse the existing source-verified
    NVIDIA FY2024 Q3 reconciliation.

    Validate the FCF margin against the
    actual FCF / revenue calculation.
    """

    row = con.execute("""
        SELECT
            capex_usd,
            fcf_usd,
            fcf_margin_pct,
            available_date,
            validation_status,
            reconciliation_method,
            reconciliation_json,
            revenue_usd,
            ocf_usd

        FROM quarterly_metrics_reconciled

        WHERE ticker = 'NVDA'
          AND fiscal_year = 2024
          AND fiscal_quarter = 3
    """).fetchone()

    require(
        row is not None,
        "Existing NVDA reconciliation missing"
    )

    require(
        row[0] is not None
        and int(row[0]) == 278_000_000,
        "NVDA supplemental CAPEX changed"
    )

    require(
        row[1] is not None
        and int(row[1]) == 7_054_000_000,
        "NVDA supplemental FCF changed"
    )

    require(
        row[8] is not None
        and int(row[8]) - int(row[0]) == int(row[1]),
        "NVDA OCF - CAPEX does not match supplemental FCF"
    )

    require(
        row[2] is not None
        and row[7] is not None,
        "NVDA FCF margin or revenue missing"
    )

    require(
        Decimal(str(row[7])) > 0,
        "NVDA revenue must be positive"
    )

    reported_margin = Decimal(
        str(row[2])
    )

    calculated_margin = (
        Decimal(str(row[1]))
        * Decimal("100")
        / Decimal(str(row[7]))
    )

    require(
        abs(
            reported_margin - calculated_margin
        ) <= Decimal("0.02"),
        (
            "NVDA supplemental margin inconsistent "
            "with FCF/revenue: "
            f"stored={reported_margin}, "
            f"calculated={calculated_margin:.4f}"
        )
    )

    require(
        isinstance(row[3], date)
        and row[3] <= AS_OF,
        "NVDA supplemental availability invalid"
    )

    require(
        row[4] == "RECONCILED_SUPPLEMENTAL",
        "NVDA reconciliation status changed"
    )

    require(
        bool(row[5]),
        "NVDA reconciliation method missing"
    )

    require(
        row[6] is not None,
        "NVDA provenance missing"
    )

    require(
        isinstance(
            json.loads(row[6]),
            (dict, list)
        ),
        "NVDA provenance is not structured JSON"
    )

    print(
        "NVDA FY2024 Q3 supplemental margin: "
        f"{reported_margin}% "
        "| ratio consistency: PASS"
    )

    # Return the seven columns required
    # by the reconciliation UPDATE.

    return row[:7]


def verify_new_tables(con):

    raw_count = scalar(
        con,
        f"SELECT COUNT(*) FROM {NEW_RAW_TABLE}"
    )

    reconciled_count = scalar(
        con,
        f"SELECT COUNT(*) FROM {NEW_RECONCILED_TABLE}"
    )

    require(
        raw_count == 48
        and reconciled_count == 48,
        "Four-company table counts incorrect"
    )

    raw_statuses = dict(
        con.execute(f"""
            SELECT validation_status, COUNT(*)
            FROM {NEW_RAW_TABLE}
            GROUP BY validation_status
        """).fetchall()
    )

    require(
        raw_statuses == {
            "PASS": 47,
            "REVIEW": 1
        },
        f"Incorrect raw status totals: {raw_statuses}"
    )

    reconciled_statuses = dict(
        con.execute(f"""
            SELECT validation_status, COUNT(*)
            FROM {NEW_RECONCILED_TABLE}
            GROUP BY validation_status
        """).fetchall()
    )

    require(
        reconciled_statuses == {
            "PASS": 47,
            "RECONCILED_SUPPLEMENTAL": 1
        },
        (
            "Incorrect reconciled statuses: "
            f"{reconciled_statuses}"
        )
    )

    incomplete = scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM {NEW_RECONCILED_TABLE}

        WHERE revenue_usd IS NULL
           OR operating_income_usd IS NULL
           OR ocf_usd IS NULL
           OR capex_usd IS NULL
           OR fcf_usd IS NULL
        """
    )

    require(
        incomplete == 0,
        f"Incomplete reconciled quarters: {incomplete}"
    )

    fcf_errors = scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM {NEW_RECONCILED_TABLE}

        WHERE fcf_usd IS DISTINCT FROM
              (ocf_usd - capex_usd)
        """
    )

    require(
        fcf_errors == 0,
        f"FCF calculation errors: {fcf_errors}"
    )

    company_rows = dict(
        con.execute(f"""
            SELECT ticker, COUNT(*)
            FROM {NEW_RECONCILED_TABLE}
            GROUP BY ticker
        """).fetchall()
    )

    require(
        company_rows == {
            ticker: 12
            for ticker in EXPECTED_FACTS
        },
        f"Quarter coverage incorrect: {company_rows}"
    )

    old_rows = con.execute("""
        SELECT *
        FROM quarterly_metrics_reconciled

        ORDER BY
            ticker,
            fiscal_year,
            fiscal_quarter
    """).fetchall()

    new_rows = con.execute(f"""
        SELECT *
        FROM {NEW_RECONCILED_TABLE}

        WHERE ticker IN ('PLTR', 'NVDA')

        ORDER BY
            ticker,
            fiscal_year,
            fiscal_quarter
    """).fetchall()

    require(
        old_rows == new_rows,
        "Existing reconciled quarters changed"
    )

    print(
        "48-quarter table validation: PASS"
    )

    print(
        "Existing reconciled regression: PASS"
    )


def apply_tables(
    con,
    rows,
    supplement,
    before
):

    con.execute("BEGIN TRANSACTION")

    try:

        # Create a separate raw quarterly table.
        # Existing Week 3 tables are not replaced.

        con.execute(f"""
            CREATE OR REPLACE TABLE
                {NEW_RAW_TABLE}
            AS

            SELECT *
            FROM quarterly_metrics_multi
            WHERE FALSE
        """)

        column_count = len(
            con.execute(
                f"""
                SELECT *
                FROM {NEW_RAW_TABLE}
                LIMIT 0
                """
            ).description
        )

        require(
            column_count == 23,
            (
                "Expected 23 columns, "
                f"got {column_count}"
            )
        )

        placeholders = ", ".join(
            "?"
            for _ in range(column_count)
        )

        con.executemany(
            f"""
            INSERT INTO {NEW_RAW_TABLE}
            VALUES ({placeholders})
            """,
            rows
        )

        # Create a separate reconciled table
        # containing the same 48 quarters.

        con.execute(f"""
            CREATE OR REPLACE TABLE
                {NEW_RECONCILED_TABLE}
            AS

            SELECT
                *,
                CAST(NULL AS VARCHAR)
                    AS reconciliation_method,
                CAST(NULL AS VARCHAR)
                    AS reconciliation_json

            FROM {NEW_RAW_TABLE}
        """)

        # Apply the original verified
        # NVIDIA reconciliation record.

        con.execute(
            f"""
            UPDATE {NEW_RECONCILED_TABLE}

            SET
                capex_usd = ?,
                fcf_usd = ?,
                fcf_margin_pct = ?,
                available_date = ?,
                validation_status = ?,
                reconciliation_method = ?,
                reconciliation_json = ?

            WHERE ticker = 'NVDA'
              AND fiscal_year = 2024
              AND fiscal_quarter = 3
            """,
            list(supplement)
        )

        # Validate all resulting financial
        # metrics before committing.

        verify_new_tables(con)

        # Confirm protected source tables
        # remain unchanged in row count.

        require(
            before == protected_snapshot(con),
            "Protected source-table counts changed"
        )

        con.execute("COMMIT")

    except Exception:

        con.execute("ROLLBACK")
        raise

    print()
    print("FOUR-COMPANY QUARTERLY BUILD")
    print("=" * 60)

    print("Companies: 4")
    print("Raw calculated quarters: 48")
    print("SEC-only PASS: 47")
    print("Original REVIEW: 1")
    print("Supplemental reconciliation: 1")
    print("Reconciled complete quarters: 48")

    print()
    print("Week 2 tables: PRESERVED")
    print("Week 3 tables: PRESERVED")
    print("Annual FCF reconciliations: PRESERVED")
    print("Four-company quarterly build: PASS")


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Save two new 48-quarter tables"
    )

    args = parser.parse_args()

    require(
        DB.exists(),
        f"Database not found: {DB}"
    )

    reader = duckdb.connect(
        str(DB),
        read_only=True
    )

    try:

        print()
        print("FOUR-COMPANY QUARTERLY BUILD")
        print("=" * 60)

        before = protected_snapshot(reader)

        rows = build_preview(reader)

        supplement = get_verified_supplement(
            reader
        )

    finally:

        reader.close()

    print()
    print("Pre-build validation: PASS")
    print("Prepared quarters:", len(rows))
    print("NVDA reconciliation: VERIFIED")

    if not args.apply:

        print()
        print("Mode: DRY RUN")
        print("Database: UNCHANGED")

        return

    writer = duckdb.connect(
        str(DB)
    )

    try:

        require(
            protected_snapshot(writer) == before,
            "Database changed since preflight"
        )

        apply_tables(
            writer,
            rows,
            supplement,
            before
        )

    finally:

        writer.close()


if __name__ == "__main__":
    main()