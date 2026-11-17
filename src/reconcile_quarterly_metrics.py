
"""
JK's Financial Data Lab V1.0
Week 3 - Auditable Supplemental Reconciliation

Creates:
    quarterly_metrics_reconciled

Preserves:
    quarterly_metrics_multi
    quarterly_metrics
    financial_facts_multi
    financial_facts
"""

import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parent.parent

DB_PATH = ROOT / "data/processed/financial_data.duckdb"

CONFIG_PATH = (
    ROOT / "config/supplemental_facts.json"
)


def get_one(con, sql, params=None):
    rows = con.execute(
        sql,
        params or []
    ).fetchall()

    if len(rows) != 1:
        raise ValueError(
            f"Expected one row, received {len(rows)}"
        )

    return rows[0]


def validate(condition, message):
    if not condition:
        raise ValueError(message)


def main():

    # 1. Load supplemental source
    config = json.loads(
        CONFIG_PATH.read_text(encoding="utf-8")
    )

    validate(
        config.get("version") == 1,
        "Unsupported configuration version"
    )

    supplements = config.get("supplements", [])

    validate(
        len(supplements) == 1,
        "Expected one supplemental record"
    )

    supplement = supplements[0]

    validate(
        (
            supplement["ticker"],
            supplement["fiscal_year"],
            supplement["fiscal_quarter"],
            supplement["metric"]
        ) == ("NVDA", 2024, 3, "capex"),
        "Unexpected supplemental record"
    )

    prior_ytd = int(
        supplement["six_month_ytd_usd"]
    )

    expected_nine_months = int(
        supplement["nine_month_ytd_usd"]
    )

    source_date = date.fromisoformat(
        supplement["published_date"]
    )

    # 2. Read SEC data without changing the DB
    reader = duckdb.connect(
        str(DB_PATH),
        read_only=True
    )

    try:
        # Original multi-company table row
        original = get_one(
            reader,
            """
            SELECT
                revenue_usd,
                ocf_usd,
                capex_usd,
                validation_status,
                period_start,
                period_end

            FROM quarterly_metrics_multi

            WHERE ticker = 'NVDA'
              AND fiscal_year = 2024
              AND fiscal_quarter = 3
            """
        )

        (
            revenue,
            ocf,
            existing_capex,
            status,
            quarter_start,
            quarter_end
        ) = original

        validate(
            existing_capex is None
            and status == "REVIEW",
            "Original NVDA row is not the expected REVIEW"
        )

        validate(
            quarter_start == date(2023, 7, 31)
            and quarter_end == date(2023, 10, 29),
            "Fiscal quarter dates do not match"
        )

        # Original Q3 9M SEC CAPEX observation
        nine_months_row = get_one(
            reader,
            """
            SELECT
                value_raw,
                filed,
                accn

            FROM financial_facts_multi

            WHERE ticker = 'NVDA'
              AND taxonomy = 'us-gaap'
              AND tag = 'PaymentsToAcquireProductiveAssets'
              AND unit = 'USD'
              AND period_start = DATE '2023-01-30'
              AND period_end = DATE '2023-10-29'
              AND form IN ('10-Q', '10-Q/A')

            ORDER BY filed ASC, accn ASC
            LIMIT 1
            """
        )

        nine_month_ytd = int(nine_months_row[0])
        nine_month_filed = nine_months_row[1]
        nine_month_accn = nine_months_row[2]

        validate(
            nine_month_ytd == expected_nine_months,
            "9M CAPEX does not match SEC data"
        )

        validate(
            source_date <= nine_month_filed,
            "Supplemental data was not available in time"
        )

        # Later comparative filing confirms 6M value
        later_comparison = get_one(
            reader,
            """
            SELECT
                value_raw,
                filed,
                accn

            FROM financial_facts_multi

            WHERE ticker = 'NVDA'
              AND taxonomy = 'us-gaap'
              AND tag = 'PaymentsToAcquireProductiveAssets'
              AND unit = 'USD'
              AND period_start = DATE '2023-01-30'
              AND period_end = DATE '2023-07-30'
              AND value_raw = '537000000'

            ORDER BY filed ASC, accn ASC
            LIMIT 1
            """
        )

        validate(
            int(later_comparison[0]) == prior_ytd,
            "Supplement does not match later SEC comparison"
        )

        # Preserve original Week 2 data
        original_week2 = get_one(
            reader,
            """
            SELECT COUNT(*)
            FROM quarterly_metrics
            """
        )[0]

        original_row_count = get_one(
            reader,
            """
            SELECT COUNT(*)
            FROM quarterly_metrics_multi
            """
        )[0]

        validate(
            original_week2 == 12
            and original_row_count == 24,
            "Original tables have unexpected row counts"
        )

    finally:
        reader.close()

    # 3. Calculate the missing quarter
    capex = nine_month_ytd - prior_ytd

    validate(
        capex == int(
            supplement["expected_quarterly_capex_usd"]
        ),
        "Q3 CAPEX reconstruction mismatch"
    )

    fcf = int(ocf) - capex

    fcf_margin = (
        Decimal(fcf)
        / Decimal(int(revenue))
        * 100
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )

    available_date = max(
        source_date,
        nine_month_filed
    )

    # 4. Build a traceable reconciliation record
    provenance = {
        "ticker": "NVDA",
        "fiscal_year": 2024,
        "fiscal_quarter": 3,
        "metric": "capex",
        "method": "9M_YTD_MINUS_6M_YTD",
        "six_month_ytd_usd": prior_ytd,
        "six_month_source": supplement["source_url"],
        "six_month_published": str(source_date),
        "nine_month_ytd_usd": nine_month_ytd,
        "nine_month_sec_filed": str(nine_month_filed),
        "nine_month_sec_accn": nine_month_accn,
        "later_comparative_filed": str(
            later_comparison[1]
        ),
        "later_comparative_accn": later_comparison[2],
        "independent_q3_source": supplement[
            "independent_q3_source_url"
        ],
        "result_capex_usd": capex,
        "status": "RECONCILED_SUPPLEMENTAL"
    }

    # 5. Write to a separate table
    con = duckdb.connect(str(DB_PATH))

    try:
        con.execute("BEGIN TRANSACTION")

        try:
            con.execute("""
                CREATE OR REPLACE TABLE
                    quarterly_metrics_reconciled AS

                SELECT
                    *,
                    CAST(NULL AS VARCHAR)
                        AS reconciliation_method,

                    CAST(NULL AS VARCHAR)
                        AS reconciliation_json

                FROM quarterly_metrics_multi
            """)

            con.execute(
                """
                UPDATE quarterly_metrics_reconciled

                SET
                    capex_usd = ?,
                    fcf_usd = ?,
                    fcf_margin_pct = ?,

                    available_date = ?,

                    validation_status =
                        'RECONCILED_SUPPLEMENTAL',

                    reconciliation_method =
                        '9M_YTD_MINUS_6M_YTD',

                    reconciliation_json = ?

                WHERE ticker = 'NVDA'
                  AND fiscal_year = 2024
                  AND fiscal_quarter = 3
                """,
                [
                    capex,
                    fcf,
                    fcf_margin,
                    available_date,
                    json.dumps(provenance)
                ]
            )

            # Validate that all original rows survive
            total = get_one(
                con,
                """
                SELECT COUNT(*)
                FROM quarterly_metrics_reconciled
                """
            )[0]

            validate(
                total == original_row_count,
                "Reconciled row count mismatch"
            )

            reconciled = get_one(
                con,
                """
                SELECT
                    capex_usd,
                    fcf_usd,
                    fcf_margin_pct,
                    validation_status

                FROM quarterly_metrics_reconciled

                WHERE ticker = 'NVDA'
                  AND fiscal_year = 2024
                  AND fiscal_quarter = 3
                """
            )

            validate(
                int(reconciled[0]) == capex
                and int(reconciled[1]) == fcf
                and reconciled[2] is not None
                and reconciled[3] ==
                    "RECONCILED_SUPPLEMENTAL",
                "Reconciliation validation failed"
            )

            # Original table must remain unchanged
            original_status = get_one(
                con,
                """
                SELECT validation_status
                FROM quarterly_metrics_multi
                WHERE ticker = 'NVDA'
                  AND fiscal_year = 2024
                  AND fiscal_quarter = 3
                """
            )[0]

            validate(
                original_status == "REVIEW",
                "Original source status changed"
            )

            validate(
                get_one(
                    con,
                    """
                    SELECT COUNT(*)
                    FROM quarterly_metrics
                    """
                )[0] == 12,
                "Week 2 data changed"
            )

            con.execute("COMMIT")

        except Exception:
            con.execute("ROLLBACK")
            raise

    finally:
        con.close()

    # 6. Final result
    print()
    print("NVDA FY2024 Q3 RECONCILIATION")
    print("-" * 45)
    print(f"6M CAPEX YTD: {prior_ytd:,} USD")
    print(f"9M CAPEX YTD: {nine_month_ytd:,} USD")
    print(f"Quarter CAPEX: {capex:,} USD")
    print(f"Quarter OCF: {int(ocf):,} USD")
    print(f"Simple FCF: {fcf:,} USD")
    print(f"FCF Margin: {fcf_margin}%")
    print(f"Available date: {available_date}")
    print("Original table: PRESERVED")
    print("Reconciliation: PASS")
    print("Status: RECONCILED_SUPPLEMENTAL")


if __name__ == "__main__":
    main()