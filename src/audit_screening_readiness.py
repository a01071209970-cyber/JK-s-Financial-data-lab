
"""
JK's Financial Data Lab V1.0
Week 4 - Screening Metric Readiness Audit

Read-only audit.

Checks:
- Quarterly coverage
- Eight-quarter continuity for LTM YoY
- Reporting availability
- Financial metric completeness
- CAPEX mapping
- FCF ranking restrictions
- Annual company FCF reconciliation
"""

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parent.parent

DB = ROOT / "data/processed/financial_data.duckdb"

POLICY = ROOT / "config/screening_metric_policy.json"

DEFINITIONS = ROOT / "config/metric_definitions.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def main():
    policy = load_json(POLICY)
    definitions = load_json(DEFINITIONS)

    require(
        policy.get("version") == 1,
        "Unsupported policy version"
    )

    cutoff = date.fromisoformat(
        policy["as_of_date"]
    )

    metric_policy = policy["metrics"]

    # Financial definitions are not fully
    # standardized, so FCF ranking stays blocked.
    restricted = (
        "fcf_margin_pct",
        "company_reported_fcf_usd"
    )

    for metric in restricted:
        require(
            metric in metric_policy,
            f"Missing restricted metric: {metric}"
        )

        require(
            metric_policy[metric][
                "cross_company_ranking"
            ] is False,
            f"Unsafe ranking enabled: {metric}"
        )

    require(
        definitions["metrics"]["fcf_usd"][
            "cross_company_comparable"
        ] is False,
        "Original FCF definition must stay restricted"
    )

    con = duckdb.connect(
        str(DB),
        read_only=True
    )

    try:
        result = con.execute("""
            SELECT
                ticker,
                fiscal_year,
                fiscal_quarter,

                period_start,
                period_end,

                revenue_usd,
                operating_income_usd,
                ocf_usd,
                capex_usd,
                fcf_usd,

                revenue_growth_yoy_pct,
                operating_margin_pct,
                fcf_margin_pct,

                available_date,
                as_of_date,
                validation_status,

                capex_tag

            FROM quarterly_metrics_reconciled

            ORDER BY
                ticker,
                period_end DESC
        """)

        columns = [
            item[0]
            for item in result.description
        ]

        records = [
            dict(zip(columns, row))
            for row in result.fetchall()
        ]

        by_company = defaultdict(list)

        for row in records:
            by_company[row["ticker"]].append(row)

        configured_companies = definitions["companies"]

        require(
            set(by_company) == set(configured_companies),
            "Company configuration mismatch"
        )

        print("SCREENING DATA AUDIT")
        print("-" * 60)

        for ticker, quarters in sorted(
            by_company.items()
        ):
            require(
                len(quarters) == 12,
                f"{ticker}: Expected 12 quarters"
            )

            latest_eight = quarters[:8]

            require(
                len(latest_eight) == 8,
                f"{ticker}: Insufficient LTM history"
            )

            # Verify all eight periods are consecutive.
            chronological = sorted(
                latest_eight,
                key=lambda r: r["period_start"]
            )

            for previous, current in zip(
                chronological,
                chronological[1:]
            ):
                require(
                    previous["period_end"]
                    + timedelta(days=1)
                    == current["period_start"],
                    f"{ticker}: Fiscal period gap"
                )

            for row in latest_eight:
                require(
                    row["validation_status"] in (
                        "PASS",
                        "RECONCILED_SUPPLEMENTAL"
                    ),
                    f"{ticker}: Unresolved quarter"
                )

                require(
                    row["as_of_date"] == cutoff,
                    f"{ticker}: Data cutoff mismatch"
                )

                require(
                    row["available_date"] is not None
                    and row["available_date"] <= cutoff,
                    f"{ticker}: Invalid availability"
                )

                required_columns = (
                    "revenue_usd",
                    "operating_income_usd",
                    "ocf_usd",
                    "capex_usd",
                    "fcf_usd",
                    "revenue_growth_yoy_pct",
                    "operating_margin_pct",
                    "fcf_margin_pct"
                )

                for column in required_columns:
                    require(
                        row[column] is not None,
                        f"{ticker}: Missing {column}"
                    )

                require(
                    row["capex_tag"]
                    == configured_companies[ticker][
                        "capex_tag"
                    ],
                    f"{ticker}: CAPEX tag mismatch"
                )

            latest = latest_eight[0]

            print()
            print(
                f"{ticker}: "
                f"{len(quarters)} quarterly records"
            )

            print(
                "Latest fiscal quarter:",
                f"FY{latest['fiscal_year']}"
                f" Q{latest['fiscal_quarter']}"
            )

            print(
                "Latest period end:",
                latest["period_end"]
            )

            print(
                "Latest filing availability:",
                latest["available_date"]
            )

            print("Latest 8-quarter coverage: PASS")

        # Confirm annual FCF reconciliation records.
        annual = con.execute("""
            SELECT
                ticker,
                COUNT(*) AS total,
                COUNT(*) FILTER (
                    WHERE validation_status = 'PASS'
                ) AS passed
            FROM company_fcf_reconciliations
            GROUP BY ticker
        """).fetchall()

        require(
            {row[0] for row in annual}
            == set(by_company),
            "Annual FCF company coverage mismatch"
        )

        for ticker, total, passed in annual:
            require(
                total == 1 and passed == 1,
                f"{ticker}: Annual FCF audit failed"
            )

        print()
        print("SCREENING METRIC POLICY")
        print("-" * 60)

        for metric, settings in metric_policy.items():
            permitted = settings["cross_company_ranking"]

            status = (
                "CONDITIONAL"
                if permitted
                else "BLOCKED"
            )

            print(
                f"{metric}: {status}"
                f" | {settings['usage']}"
            )

        print()
        print("Screening readiness audit: PASS")
        print("FCF cross-company ranking: BLOCKED")
        print("Company-reported FCF: REFERENCE ONLY")
        print("Existing tables: UNCHANGED")

    finally:
        con.close()


if __name__ == "__main__":
    main()