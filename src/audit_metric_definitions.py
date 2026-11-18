
"""
JK's Financial Data Lab V1.0
Week 4 - Metric Definition Audit

Read-only validation of company-specific
CAPEX definitions against DuckDB.
"""

import json
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parent.parent

CONFIG = ROOT / "config/metric_definitions.json"
DB = ROOT / "data/processed/financial_data.duckdb"


def main():
    config = json.loads(
        CONFIG.read_text(encoding="utf-8")
    )

    if config.get("version") != 1:
        raise ValueError("Unsupported config version")

    companies = config["companies"]

    con = duckdb.connect(
        str(DB),
        read_only=True
    )

    try:
        rows = con.execute("""
            SELECT
                ticker,
                capex_tag,
                COUNT(*) AS quarters,
                COUNT(*) FILTER (
                    WHERE validation_status =
                        'RECONCILED_SUPPLEMENTAL'
                ) AS supplemental_quarters
            FROM quarterly_metrics_reconciled
            GROUP BY ticker, capex_tag
            ORDER BY ticker
        """).fetchall()

        if len(rows) != len(companies):
            raise ValueError(
                "Company count mismatch"
            )

        for ticker, tag, quarters, supplemental in rows:

            company = companies.get(ticker)

            if company is None:
                raise ValueError(
                    f"Missing config: {ticker}"
                )

            if tag != company["capex_tag"]:
                raise ValueError(
                    f"{ticker}: CAPEX tag mismatch"
                )

            if quarters != 12:
                raise ValueError(
                    f"{ticker}: Expected 12 quarters"
                )

            expected_supplemental = (
                1 if company.get(
                    "has_supplemental_reconciliation",
                    False
                ) else 0
            )

            if supplemental != expected_supplemental:
                raise ValueError(
                    f"{ticker}: Supplemental count mismatch"
                )

            print(f"\n{ticker}")
            print("CAPEX tag:", tag)
            print("Quarters:", quarters)
            print(
                "Supplemental quarters:",
                supplemental
            )
            print(
                "Definition status:",
                company["capex_definition_status"]
            )

        fcf_definition = config["metrics"]["fcf_usd"]

        if fcf_definition["cross_company_comparable"]:
            raise ValueError(
                "FCF must remain comparison-restricted"
            )

        print()
        print("Metric Definition Audit: PASS")
        print("FCF comparability: NOT YET VERIFIED")

    finally:
        con.close()


if __name__ == "__main__":
    main()