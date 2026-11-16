
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parent.parent

DB_PATH = ROOT / "data/processed/financial_data.duckdb"
SQL_DIR = ROOT / "sql"

# Reuse existing financial analysis queries
SQL_SOURCES = {
    "quarterly_revenue":
        "09_quarterly_revenue_12q.sql",

    "quarterly_operating_income":
        "10_quarterly_operating_income_12q.sql",

    "quarterly_cashflow":
        "12_quarterly_cashflow_12q.sql"
}

# Expected consecutive quarters
EXPECTED = (
    [(2023, 4)]
    + [(y, q) for y in (2024, 2025)
       for q in range(1, 5)]
    + [(2026, q) for q in range(1, 4)]
)

con = duckdb.connect(str(DB_PATH))

try:
    # 1. Create temporary views from existing SQL
    for view_name, filename in SQL_SOURCES.items():
        query = (SQL_DIR / filename).read_text(
            encoding="utf-8"
        )

        con.execute(
            f"CREATE OR REPLACE TEMP VIEW "
            f"{view_name} AS\n{query}"
        )

        print(f"Loaded: {filename}")

    # 2. Check completeness and quarter order
    for view_name in SQL_SOURCES:
        rows = con.execute(
            f"""
            SELECT fiscal_year, fiscal_quarter
            FROM {view_name}
            ORDER BY fiscal_year, fiscal_quarter
            """
        ).fetchall()

        if rows != EXPECTED:
            raise ValueError(
                f"{view_name}: Missing or duplicate quarters"
            )

    # 3. Verify original metrics are not missing
    checks = {
        "quarterly_revenue": "revenue_usd",
        "quarterly_operating_income":
            "operating_income_usd",
        "quarterly_cashflow": "fcf_usd"
    }

    for view_name, column in checks.items():
        missing = con.execute(
            f"""
            SELECT COUNT(*)
            FROM {view_name}
            WHERE {column} IS NULL
            """
        ).fetchone()[0]

        if missing:
            raise ValueError(
                f"{view_name}: {missing} missing values"
            )

    # 4. Check cash-flow validation status
    failures = con.execute("""
        SELECT COUNT(*)
        FROM quarterly_cashflow
        WHERE validation_status IS DISTINCT FROM 'PASS'
    """).fetchone()[0]

    if failures:
        raise ValueError("Cash flow validation failed")

    print("Source validation: PASS")

    # 5. Create the permanent table
    con.execute("BEGIN TRANSACTION")

    try:
        build_query = (
            SQL_DIR / "13_build_quarterly_metrics.sql"
        ).read_text(encoding="utf-8")

        con.execute(build_query)

        result = con.execute("""
            SELECT
                fiscal_year,
                fiscal_quarter,
                revenue_usd,
                operating_income_usd,
                ocf_usd,
                capex_usd,
                fcf_usd,
                operating_margin_pct,
                fcf_margin_pct,
                revenue_growth_yoy_pct,
                operating_margin_yoy_change_pp
            FROM quarterly_metrics
            ORDER BY fiscal_year DESC, fiscal_quarter DESC
        """).df()

        if len(result) != 12:
            raise ValueError("Expected exactly 12 quarters")

        # Known SEC cross-check: FY2026 Q3
        q3 = result[
            (result["fiscal_year"] == 2026)
            & (result["fiscal_quarter"] == 3)
        ].iloc[0]

        expected_q3 = {
            "revenue_usd": 2313411000,
            "operating_income_usd": 1084845000,
            "ocf_usd": 1204570000,
            "capex_usd": 8014000,
            "fcf_usd": 1196556000
        }

        for column, expected in expected_q3.items():
            if q3[column] != expected:
                raise ValueError(
                    f"FY2026 Q3 mismatch: {column}"
                )

        con.execute("COMMIT")

    except Exception:
        con.execute("ROLLBACK")
        raise

    # 6. Display results
    print()
    print(result.to_string(index=False))
    print()
    print("Total quarters:", len(result))
    print("FY2026 Q3 cross-check: PASS")
    print("Quarterly Metrics Validation: PASS")
    print("Database:", DB_PATH)

finally:
    con.close()