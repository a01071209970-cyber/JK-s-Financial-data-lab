
"""
JK's Financial Data Lab V1.0
Week 4 - Company FCF Reconciliation

Creates a separate annual reconciliation table.

Does not modify quarterly financial metrics.
"""

import json
from datetime import date
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parent.parent

DB = ROOT / "data/processed/financial_data.duckdb"

CONFIG = (
    ROOT / "config/company_fcf_reconciliations.json"
)

TAGS = ROOT / "config/metric_tags.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def query_one(con, sql, params=None):
    rows = con.execute(
        sql,
        params or []
    ).fetchall()

    require(
        len(rows) == 1,
        f"Expected 1 row, got {len(rows)}"
    )

    return rows[0]


def main():

    config = json.loads(
        CONFIG.read_text(encoding="utf-8")
    )

    tag_config = json.loads(
        TAGS.read_text(encoding="utf-8")
    )["metric_tags"]

    require(
        config.get("version") == 1,
        "Unsupported config version"
    )

    cutoff = date.fromisoformat(
        config["data_cutoff"]
    )

    records = config["records"]

    require(
        len(records) == 2,
        "Expected 2 company records"
    )

    con = duckdb.connect(str(DB))

    try:
        # Keep the original table counts for safety.
        protected_tables = [
            "financial_facts",
            "quarterly_metrics",
            "financial_facts_multi",
            "quarterly_metrics_multi",
            "quarterly_metrics_reconciled"
        ]

        before = {
            table: query_one(
                con,
                f"SELECT COUNT(*) FROM {table}"
            )[0]
            for table in protected_tables
        }

        prepared = []
        seen = set()

        for r in records:

            ticker = r["ticker"]
            fy = int(r["fiscal_year"])

            key = (ticker, fy)

            require(
                key not in seen,
                f"Duplicate company/year: {key}"
            )

            seen.add(key)

            start = date.fromisoformat(
                r["period_start"]
            )

            end = date.fromisoformat(
                r["period_end"]
            )

            published = date.fromisoformat(
                r["official_release_date"]
            )

            require(
                end < published <= cutoff,
                f"{ticker}: Invalid publication date"
            )

            require(
                r["source_url"].startswith("https://"),
                f"{ticker}: Missing official source URL"
            )

            tags = tag_config[ticker]

            # Verify SEC annual facts.
            sec_values = {}

            for metric in ("ocf", "capex"):

                tag = tags[metric]

                fact = query_one(
                    con,
                    """
                    SELECT
                        value_raw,
                        filed

                    FROM financial_facts_multi

                    WHERE ticker = ?
                      AND taxonomy = 'us-gaap'
                      AND tag = ?
                      AND unit = 'USD'
                      AND period_start = ?
                      AND period_end = ?
                      AND filed <= ?
                      AND form IN ('10-K', '10-K/A')

                    ORDER BY
                        filed ASC,
                        accn ASC

                    LIMIT 1
                    """,
                    [
                        ticker,
                        tag,
                        start,
                        end,
                        cutoff
                    ]
                )

                sec_values[metric] = int(fact[0])

            ocf = sec_values["ocf"]
            capex = sec_values["capex"]

            require(
                ocf == int(r["ocf_usd"]),
                f"{ticker}: Annual OCF mismatch"
            )

            require(
                capex == int(r["capex_usd"]),
                f"{ticker}: Annual CAPEX mismatch"
            )

            # Validate the quarterly reconstruction.
            quarterly = query_one(
                con,
                """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT fiscal_quarter),
                    MIN(period_start),
                    MAX(period_end),
                    SUM(ocf_usd),
                    SUM(capex_usd),
                    SUM(fcf_usd),

                    COUNT(*) FILTER (
                        WHERE validation_status NOT IN (
                            'PASS',
                            'RECONCILED_SUPPLEMENTAL'
                        )
                    )

                FROM quarterly_metrics_reconciled

                WHERE ticker = ?
                  AND fiscal_year = ?
                """,
                [ticker, fy]
            )

            (
                count,
                distinct_quarters,
                first_start,
                final_end,
                q_ocf,
                q_capex,
                q_fcf,
                review_count
            ) = quarterly

            require(
                count == 4
                and distinct_quarters == 4
                and first_start == start
                and final_end == end,
                f"{ticker}: Fiscal-quarter coverage mismatch"
            )

            require(
                review_count == 0,
                f"{ticker}: Unresolved quarterly review"
            )

            require(
                int(q_ocf) == ocf
                and int(q_capex) == capex
                and int(q_fcf) == ocf - capex,
                f"{ticker}: Quarterly/annual reconciliation failed"
            )

            simple_fcf = ocf - capex

            adjustment = sum(
                int(item["amount_usd"])
                for item in r["adjustments"]
            )

            reported_fcf = int(
                r["company_reported_fcf_usd"]
            )

            require(
                simple_fcf + adjustment == reported_fcf,
                f"{ticker}: FCF formula mismatch"
            )

            prepared.append((
                ticker,
                fy,
                start,
                end,
                ocf,
                capex,
                simple_fcf,
                adjustment,
                reported_fcf,
                r["metric_type"],
                tags["capex"],
                published,
                cutoff,
                r["source_url"],
                json.dumps(
                    r["adjustments"],
                    ensure_ascii=False
                ),
                "PASS"
            ))

            print(
                f"{ticker} FY{fy}: "
                f"simple FCF={simple_fcf:,}, "
                f"adjustment={adjustment:+,}, "
                f"reported FCF={reported_fcf:,} "
                f"| PASS"
            )

        # Save only after all checks pass.
        con.execute("BEGIN TRANSACTION")

        try:

            con.execute("""
                CREATE OR REPLACE TABLE
                company_fcf_reconciliations (

                    ticker VARCHAR,
                    fiscal_year INTEGER,

                    period_start DATE,
                    period_end DATE,

                    ocf_usd DECIMAL(38,0),
                    capex_usd DECIMAL(38,0),
                    simple_fcf_usd DECIMAL(38,0),
                    adjustment_usd DECIMAL(38,0),
                    company_reported_fcf_usd DECIMAL(38,0),

                    fcf_metric_type VARCHAR,
                    capex_tag VARCHAR,

                    official_release_date DATE,
                    data_cutoff DATE,

                    source_url VARCHAR,
                    adjustments_json VARCHAR,

                    validation_status VARCHAR,

                    PRIMARY KEY (
                        ticker,
                        fiscal_year
                    )
                )
            """)

            placeholders = ",".join(
                "?" for _ in range(16)
            )

            con.executemany(
                "INSERT INTO company_fcf_reconciliations "
                f"VALUES ({placeholders})",
                prepared
            )

            total = query_one(
                con,
                """
                SELECT COUNT(*)
                FROM company_fcf_reconciliations
                """
            )[0]

            require(
                total == len(records),
                "Inserted row count mismatch"
            )

            after = {
                table: query_one(
                    con,
                    f"SELECT COUNT(*) FROM {table}"
                )[0]
                for table in protected_tables
            }

            require(
                before == after,
                "Protected table row count changed"
            )

            con.execute("COMMIT")

        except Exception:
            con.execute("ROLLBACK")
            raise

        print()
        print("COMPANY FCF RECONCILIATION")
        print("-" * 45)
        print(f"Saved annual records: {total}")
        print("Original quarterly tables: PRESERVED")
        print("Validation: PASS")

    finally:
        con.close()


if __name__ == "__main__":
    main()