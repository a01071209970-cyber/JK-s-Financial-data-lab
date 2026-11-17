
"""
JK's Financial Data Lab V1.0
Week 3 - Multi-Company DuckDB Loader

Creates:
    companies_multi
    financial_facts_multi

Preserves Week 2 tables:
    companies
    financial_facts
    quarterly_metrics
"""

import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd


# ==================================================
# 1. PROJECT PATHS
# ==================================================

ROOT = Path(__file__).resolve().parent.parent

DB_PATH = ROOT / "data/processed/financial_data.duckdb"
CONFIG_PATH = ROOT / "config/companies.json"
RAW_DIR = ROOT / "data/raw"

FACT_COLUMNS = [
    "cik",
    "ticker",
    "taxonomy",
    "tag",
    "label",
    "unit",
    "period_start",
    "period_end",
    "value_raw",
    "form",
    "filed",
    "accn",
    "fy",
    "fp",
    "frame",
]


# ==================================================
# 2. LOAD SEC JSON FILES
# ==================================================

def read_sources():

    config = json.loads(
        CONFIG_PATH.read_text(encoding="utf-8")
    )

    companies = config["companies"]

    fact_rows = []
    company_rows = []
    counts = {}

    for company in companies:

        ticker = company["ticker"].upper()
        cik = int(company["cik"])

        path = (
            RAW_DIR /
            f"{ticker.lower()}_companyfacts.json"
        )

        if not path.exists():
            raise FileNotFoundError(path)

        raw = path.read_bytes()
        data = json.loads(raw)

        if data.get("cik") != cik:
            raise ValueError(
                f"{ticker}: SEC CIK mismatch"
            )

        if not data.get("facts", {}).get("us-gaap"):
            raise ValueError(
                f"{ticker}: Missing US-GAAP facts"
            )

        before = len(fact_rows)

        # Preserve every SEC observation
        for taxonomy, concepts in data["facts"].items():

            for tag, concept in concepts.items():

                label = concept.get("label")

                for unit, observations in (
                    concept.get("units", {}).items()
                ):

                    for obs in observations:

                        value = obs.get("val")

                        if (
                            isinstance(value, bool)
                            or not isinstance(
                                value, (int, float)
                            )
                        ):
                            raise ValueError(
                                f"{ticker}: Invalid value in {tag}"
                            )

                        fact_rows.append((
                            cik,
                            ticker,
                            taxonomy,
                            tag,
                            label,
                            unit,
                            obs.get("start"),
                            obs.get("end"),
                            str(value),
                            obs.get("form"),
                            obs.get("filed"),
                            obs.get("accn"),
                            obs.get("fy"),
                            obs.get("fp"),
                            obs.get("frame"),
                        ))

        count = len(fact_rows) - before

        counts[ticker] = count

        company_rows.append({
            "ticker": ticker,
            "cik": cik,
            "company_name": data["entityName"],
            "calendar_type": (
                company["fiscal_calendar"]["type"]
            ),
            "fiscal_calendar_json": json.dumps(
                company["fiscal_calendar"]
            ),
            "source_file": str(
                path.relative_to(ROOT)
            ),
            "source_sha256": hashlib.sha256(
                raw
            ).hexdigest(),
            "source_observations": count,
        })

        print(
            f"Prepared {ticker}: "
            f"{count:,} observations"
        )

    if len(counts) != len(companies):
        raise ValueError(
            "Duplicate ticker in company configuration"
        )

    facts_df = pd.DataFrame(
        fact_rows,
        columns=FACT_COLUMNS
    )

    companies_df = pd.DataFrame(
        company_rows
    )

    return facts_df, companies_df, counts


# ==================================================
# 3. SAFE SQL RESULT READING
# ==================================================

def one_value(con, sql, params=None):

    # Fetch all rows to completely consume the
    # result before any subsequent DuckDB operation.
    rows = con.execute(
        sql,
        params or []
    ).fetchall()

    if len(rows) != 1 or len(rows[0]) != 1:
        raise ValueError(
            "Expected exactly one scalar result"
        )

    return rows[0][0]


# ==================================================
# 4. PROTECT EXISTING WEEK 2 DATA
# ==================================================

def check_week2(con):

    facts = one_value(
        con,
        """
        SELECT COUNT(*)
        FROM financial_facts
        WHERE cik = 1321655
        """
    )

    metrics = one_value(
        con,
        """
        SELECT COUNT(*)
        FROM quarterly_metrics
        """
    )

    revenue = one_value(
        con,
        """
        SELECT revenue_usd
        FROM quarterly_metrics
        WHERE fiscal_year = 2026
          AND fiscal_quarter = 3
        """
    )

    if (
        facts != 8134
        or metrics != 12
        or int(revenue) != 2313411000
    ):
        raise ValueError(
            "Week 2 protection failed: "
            f"facts={facts}, "
            f"metrics={metrics}, "
            f"revenue={revenue}"
        )

    return (
        facts,
        metrics,
        int(revenue)
    )


# ==================================================
# 5. BUILD MULTI-COMPANY DATABASE
# ==================================================

def main():

    if not DB_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )

    facts_df, companies_df, expected = read_sources()

    # Validate original tables using a separate
    # read-only connection.
    reader = duckdb.connect(
        str(DB_PATH),
        read_only=True
    )

    try:
        baseline = check_week2(reader)

    finally:
        reader.close()

    # Open write connection
    con = duckdb.connect(str(DB_PATH))

    try:

        # IMPORTANT:
        # Register DataFrames before executing SQL.
        # This avoids the previous unfinished-result
        # connection error.
        con.register(
            "stage_facts",
            facts_df
        )

        con.register(
            "stage_companies",
            companies_df
        )

        con.execute("BEGIN TRANSACTION")

        try:

            # Check original Week 2 tables
            if check_week2(con) != baseline:
                raise ValueError(
                    "Week 2 baseline changed"
                )

            # --------------------------------------
            # Create multi-company financial facts
            # --------------------------------------

            con.execute("""
                CREATE OR REPLACE TABLE
                    financial_facts_multi AS

                SELECT
                    CAST(cik AS BIGINT) AS cik,
                    CAST(ticker AS VARCHAR) AS ticker,
                    CAST(taxonomy AS VARCHAR) AS taxonomy,
                    CAST(tag AS VARCHAR) AS tag,
                    CAST(label AS VARCHAR) AS label,
                    CAST(unit AS VARCHAR) AS unit,

                    TRY_CAST(
                        period_start AS DATE
                    ) AS period_start,

                    TRY_CAST(
                        period_end AS DATE
                    ) AS period_end,

                    CAST(
                        value_raw AS VARCHAR
                    ) AS value_raw,

                    TRY_CAST(
                        value_raw AS DOUBLE
                    ) AS value_num,

                    CAST(form AS VARCHAR) AS form,

                    TRY_CAST(
                        filed AS DATE
                    ) AS filed,

                    CAST(accn AS VARCHAR) AS accn,
                    TRY_CAST(fy AS INTEGER) AS fy,
                    CAST(fp AS VARCHAR) AS fp,
                    CAST(frame AS VARCHAR) AS frame

                FROM stage_facts
            """)

            # --------------------------------------
            # Create multi-company metadata table
            # --------------------------------------

            con.execute("""
                CREATE OR REPLACE TABLE
                    companies_multi AS

                SELECT
                    CAST(ticker AS VARCHAR) AS ticker,
                    CAST(cik AS BIGINT) AS cik,

                    CAST(
                        company_name AS VARCHAR
                    ) AS company_name,

                    CAST(
                        calendar_type AS VARCHAR
                    ) AS calendar_type,

                    CAST(
                        fiscal_calendar_json AS VARCHAR
                    ) AS fiscal_calendar_json,

                    CAST(
                        source_file AS VARCHAR
                    ) AS source_file,

                    CAST(
                        source_sha256 AS VARCHAR
                    ) AS source_sha256,

                    CAST(
                        source_observations AS BIGINT
                    ) AS source_observations

                FROM stage_companies
            """)

            # --------------------------------------
            # Validate observation counts
            # --------------------------------------

            for ticker, expected_count in expected.items():

                actual = one_value(
                    con,
                    """
                    SELECT COUNT(*)
                    FROM financial_facts_multi
                    WHERE ticker = ?
                    """,
                    [ticker]
                )

                if actual != expected_count:
                    raise ValueError(
                        f"{ticker}: Expected "
                        f"{expected_count}, got {actual}"
                    )

            company_count = one_value(
                con,
                """
                SELECT COUNT(*)
                FROM companies_multi
                """
            )

            if company_count != len(expected):
                raise ValueError(
                    "Company count mismatch"
                )

            # --------------------------------------
            # Validate required data types
            # --------------------------------------

            bad_rows = one_value(
                con,
                """
                SELECT COUNT(*)
                FROM financial_facts_multi
                WHERE value_num IS NULL
                   OR period_end IS NULL
                   OR filed IS NULL
                """
            )

            if bad_rows:
                raise ValueError(
                    f"Invalid converted rows: {bad_rows}"
                )

            # --------------------------------------
            # Validate company relationships
            # --------------------------------------

            orphan_rows = one_value(
                con,
                """
                SELECT COUNT(*)
                FROM financial_facts_multi f

                LEFT JOIN companies_multi c
                  ON f.cik = c.cik
                 AND f.ticker = c.ticker

                WHERE c.cik IS NULL
                """
            )

            if orphan_rows:
                raise ValueError(
                    f"Orphan financial facts: {orphan_rows}"
                )

            # --------------------------------------
            # Cross-check known SEC observations
            # --------------------------------------

            known_values = [
                (
                    "PLTR",
                    "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "2026-07-01",
                    "2026-09-30",
                    "2313411000"
                ),
                (
                    "NVDA",
                    "Revenues",
                    "2026-04-27",
                    "2026-07-26",
                    "96221000000"
                )
            ]

            for ticker, tag, start, end, value in known_values:

                matches = one_value(
                    con,
                    """
                    SELECT COUNT(*)
                    FROM financial_facts_multi

                    WHERE ticker = ?
                      AND tag = ?
                      AND period_start = CAST(? AS DATE)
                      AND period_end = CAST(? AS DATE)
                      AND value_raw = ?
                    """,
                    [ticker, tag, start, end, value]
                )

                if matches == 0:
                    raise ValueError(
                        f"SEC cross-check failed: {ticker}"
                    )

            # --------------------------------------
            # Verify Week 2 data again
            # --------------------------------------

            if check_week2(con) != baseline:
                raise ValueError(
                    "Original Week 2 data changed"
                )

            # All checks passed
            con.execute("COMMIT")

        except Exception:
            con.execute("ROLLBACK")
            raise

        # ------------------------------------------
        # Display final database results
        # ------------------------------------------

        rows = con.execute("""
            SELECT
                ticker,
                COUNT(*) AS observations

            FROM financial_facts_multi

            GROUP BY ticker
            ORDER BY ticker
        """).fetchall()

        print()
        print("MULTI-COMPANY INGESTION RESULT")
        print("-" * 52)

        for ticker, count in rows:
            print(
                f"{ticker}: {count:,} observations"
            )

        print()
        print(
            f"Total observations: "
            f"{sum(expected.values()):,}"
        )

        print("Original Week 2 tables: PRESERVED")
        print("Known SEC cross-check: PASS")
        print("Multi-company ingestion: PASS")
        print("Database:", DB_PATH)

    finally:
        con.close()


if __name__ == "__main__":
    main()
