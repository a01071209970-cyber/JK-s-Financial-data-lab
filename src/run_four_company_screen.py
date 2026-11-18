
"""
JK's Financial Data Lab V1.0

Week 4
Fundamental Screener V0.3

Universe:
    PLTR, NVDA, AMD, MSFT

Source:
    quarterly_metrics_four_reconciled

Features:
    - Quarterly revenue YoY
    - Operating margin
    - Operating margin YoY improvement
    - LTM revenue and operating margin
    - LTM revenue YoY growth
    - OCF margin (secondary metric)
    - Filing recency filter
    - 8-quarter minimum history
    - Historical regression validation

Financial comparability policy:
    FCF is NOT used for cross-company ranking.

Database access:
    READ ONLY

Usage:
    python src/run_four_company_screen.py
"""

import json
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parent.parent

DB_PATH = (
    ROOT / "data/processed/financial_data.duckdb"
)

CONFIG_PATH = (
    ROOT / "config/screening_rules_v03.json"
)

SOURCE_TABLE = "quarterly_metrics_four_reconciled"

EXPECTED_FACTS = {
    "AMD": 24244,
    "MSFT": 33058,
    "NVDA": 27281,
    "PLTR": 8134
}

VALID_STATUSES = {
    "PASS",
    "RECONCILED_SUPPLEMENTAL"
}

HUNDRED = Decimal("100")


def require(condition, message):

    if not condition:
        raise ValueError(message)


def dec(value):

    require(
        value is not None,
        "Missing numeric value"
    )

    return Decimal(str(value))


def to_date(value):

    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value))


def pct(numerator, denominator):

    denominator = dec(denominator)

    require(
        denominator > 0,
        "Percentage denominator must be positive"
    )

    return (
        dec(numerator)
        / denominator
        * HUNDRED
    )


def growth_pct(current, previous):

    return pct(
        dec(current) - dec(previous),
        previous
    )


def money_b(value):

    return f"${dec(value) / Decimal('1000000000'):,.3f}B"


def fmt_pct(value):

    return f"{value:,.2f}%"


def fmt_pp(value):

    return f"{value:+,.2f}pp"


def load_rules():

    config = json.loads(
        CONFIG_PATH.read_text(encoding="utf-8")
    )

    require(
        config.get("version") == 3,
        "Expected screening rules V0.3"
    )

    required = {
        "PLTR",
        "NVDA",
        "AMD",
        "MSFT"
    }

    tickers = config["expected_tickers"]

    require(
        len(tickers) == 4
        and set(tickers) == required,
        "Incorrect V0.3 screening universe"
    )

    require(
        config["required_history_quarters"] == 8,
        "Expected eight-quarter history requirement"
    )

    require(
        config["fcf_cross_company_ranking"] is False,
        "Cross-company FCF ranking is prohibited"
    )

    as_of = date.fromisoformat(
        config["as_of_date"]
    )

    require(
        config["max_filing_age_days"] >= 0,
        "Maximum filing age cannot be negative"
    )

    return config, as_of


def check_database(con):

    expected_tables = {
        "financial_facts_multi": 92717,
        "quarterly_metrics_multi": 24,
        "quarterly_metrics_reconciled": 24,
        "quarterly_metrics_four": 48,
        "quarterly_metrics_four_reconciled": 48,
        "company_fcf_reconciliations": 2
    }

    for table, expected in expected_tables.items():

        actual = con.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

        require(
            actual == expected,
            (
                f"{table}: expected {expected}, "
                f"found {actual}"
            )
        )

    counts = dict(
        con.execute("""
            SELECT ticker, COUNT(*)
            FROM financial_facts_multi
            GROUP BY ticker
        """).fetchall()
    )

    require(
        counts == EXPECTED_FACTS,
        "Raw SEC observation counts changed"
    )

    statuses = dict(
        con.execute(f"""
            SELECT validation_status, COUNT(*)
            FROM {SOURCE_TABLE}
            GROUP BY validation_status
        """).fetchall()
    )

    require(
        statuses == {
            "PASS": 47,
            "RECONCILED_SUPPLEMENTAL": 1
        },
        f"Unexpected validation statuses: {statuses}"
    )

    print("Database integrity: PASS")
    print("SEC observations: 92,717")
    print("Reconciled quarters: 48")
    print("Existing historical tables: PRESERVED")


def read_quarters(con):

    columns = [
        "ticker",
        "fiscal_year",
        "fiscal_quarter",
        "period_start",
        "period_end",
        "revenue_usd",
        "operating_income_usd",
        "ocf_usd",
        "capex_usd",
        "fcf_usd",
        "available_date",
        "validation_status"
    ]

    rows = con.execute(f"""
        SELECT
            {", ".join(columns)}
        FROM {SOURCE_TABLE}
        ORDER BY
            ticker,
            period_end
    """).fetchall()

    records = [
        dict(zip(columns, row))
        for row in rows
    ]

    require(
        len(records) == 48,
        "Expected 48 quarterly records"
    )

    return records


def validate_quarter_sequence(
    ticker,
    rows,
    as_of
):

    require(
        len(rows) == 12,
        f"{ticker}: Expected 12 quarters"
    )

    keys = set()

    for index, row in enumerate(rows):

        key = (
            row["fiscal_year"],
            row["fiscal_quarter"]
        )

        require(
            key not in keys,
            f"{ticker}: Duplicate fiscal quarter {key}"
        )

        keys.add(key)

        start = to_date(row["period_start"])
        end = to_date(row["period_end"])
        available = to_date(row["available_date"])

        require(
            start <= end,
            f"{ticker}: Invalid quarter dates"
        )

        require(
            end <= as_of,
            f"{ticker}: Future reporting period"
        )

        require(
            end <= available <= as_of,
            (
                f"{ticker}: Invalid data availability "
                f"for {key}"
            )
        )

        require(
            row["validation_status"] in VALID_STATUSES,
            f"{ticker}: Unresolved quarter {key}"
        )

        for metric in (
            "revenue_usd",
            "operating_income_usd",
            "ocf_usd",
            "capex_usd",
            "fcf_usd"
        ):
            require(
                row[metric] is not None,
                f"{ticker}: Missing {metric} for {key}"
            )

        require(
            dec(row["fcf_usd"])
            == dec(row["ocf_usd"])
            - dec(row["capex_usd"]),
            f"{ticker}: FCF mismatch for {key}"
        )

        if index == 0:
            continue

        previous = rows[index - 1]

        previous_end = to_date(
            previous["period_end"]
        )

        require(
            start == previous_end + timedelta(days=1),
            f"{ticker}: Non-contiguous fiscal periods"
        )

        previous_fy = previous["fiscal_year"]
        previous_q = previous["fiscal_quarter"]

        if previous_q == 4:
            expected_key = (previous_fy + 1, 1)
        else:
            expected_key = (previous_fy, previous_q + 1)

        require(
            key == expected_key,
            (
                f"{ticker}: Fiscal quarter sequence "
                f"incorrect: {key}"
            )
        )


def validate_historical_regression(
    con,
    records
):

    existing = con.execute("""
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

        FROM quarterly_metrics_reconciled
    """).fetchall()

    lookup = {
        (
            row["ticker"],
            row["fiscal_year"],
            row["fiscal_quarter"]
        ): row
        for row in records
    }

    require(
        len(existing) == 24,
        "Expected 24 historical reconciled quarters"
    )

    for old in existing:

        key = old[:3]

        require(
            key in lookup,
            f"Historical quarter missing: {key}"
        )

        current = lookup[key]

        fields = [
            "revenue_usd",
            "operating_income_usd",
            "ocf_usd",
            "capex_usd",
            "fcf_usd"
        ]

        for index, field in enumerate(fields, start=3):

            require(
                dec(old[index])
                == dec(current[field]),
                (
                    f"Historical regression mismatch: "
                    f"{key}, {field}"
                )
            )

        require(
            old[8] == current["validation_status"],
            f"Historical status mismatch: {key}"
        )

    print(
        "PLTR/NVDA 24-quarter regression: PASS"
    )


def calculate_company(
    ticker,
    rows,
    rules,
    as_of
):

    required = rules["required_history_quarters"]

    require(
        len(rows) >= required,
        f"{ticker}: Insufficient quarterly history"
    )

    latest = rows[-1]

    prior_year = rows[-5]

    latest_revenue = dec(
        latest["revenue_usd"]
    )

    prior_revenue = dec(
        prior_year["revenue_usd"]
    )

    latest_margin = pct(
        latest["operating_income_usd"],
        latest_revenue
    )

    prior_margin = pct(
        prior_year["operating_income_usd"],
        prior_revenue
    )

    revenue_yoy = growth_pct(
        latest_revenue,
        prior_revenue
    )

    margin_improvement = (
        latest_margin - prior_margin
    )

    ocf_margin = pct(
        latest["ocf_usd"],
        latest_revenue
    )

    latest_four = rows[-4:]
    previous_four = rows[-8:-4]

    ltm_revenue = sum(
        (
            dec(row["revenue_usd"])
            for row in latest_four
        ),
        Decimal("0")
    )

    previous_ltm_revenue = sum(
        (
            dec(row["revenue_usd"])
            for row in previous_four
        ),
        Decimal("0")
    )

    ltm_operating_income = sum(
        (
            dec(row["operating_income_usd"])
            for row in latest_four
        ),
        Decimal("0")
    )

    ltm_revenue_yoy = growth_pct(
        ltm_revenue,
        previous_ltm_revenue
    )

    ltm_operating_margin = pct(
        ltm_operating_income,
        ltm_revenue
    )

    filing_age = (
        as_of - to_date(
            latest["available_date"]
        )
    ).days

    min_growth = dec(
        rules["min_revenue_yoy_pct"]
    )

    min_margin = dec(
        rules["min_operating_margin_pct"]
    )

    min_improvement = dec(
        rules["min_operating_margin_improvement_pp"]
    )

    growth_pass = revenue_yoy >= min_growth

    profitability_pass = (
        latest_margin >= min_margin
        or margin_improvement > min_improvement
    )

    freshness_pass = (
        0 <= filing_age
        <= rules["max_filing_age_days"]
    )

    recent_rows = rows[-required:]

    history_pass = (
        len(recent_rows) == required
        and all(
            row["validation_status"]
            in VALID_STATUSES
            for row in recent_rows
        )
    )

    passed = (
        growth_pass
        and profitability_pass
        and freshness_pass
        and history_pass
    )

    failed_reasons = []

    if not growth_pass:
        failed_reasons.append(
            "Revenue YoY below threshold"
        )

    if not profitability_pass:
        failed_reasons.append(
            "Operating margin criterion failed"
        )

    if not freshness_pass:
        failed_reasons.append(
            "Latest filing too old"
        )

    if not history_pass:
        failed_reasons.append(
            "Insufficient validated history"
        )

    return {
        "ticker": ticker,
        "fiscal_year": latest["fiscal_year"],
        "fiscal_quarter": latest["fiscal_quarter"],
        "period_end": to_date(
            latest["period_end"]
        ),
        "revenue_yoy": revenue_yoy,
        "operating_margin": latest_margin,
        "margin_improvement": margin_improvement,
        "ocf_margin": ocf_margin,
        "ltm_revenue": ltm_revenue,
        "ltm_revenue_yoy": ltm_revenue_yoy,
        "ltm_operating_margin": ltm_operating_margin,
        "filing_age": filing_age,
        "passed": passed,
        "failed_reasons": failed_reasons
    }


def display_results(results, as_of):

    results.sort(
        key=lambda result: (
            result["passed"],
            result["revenue_yoy"],
            result["operating_margin"]
        ),
        reverse=True
    )

    print()
    print("=" * 68)
    print("FUNDAMENTAL SCREENER V0.3")
    print("=" * 68)
    print("As-of:", as_of)
    print("Universe: PLTR / NVDA / AMD / MSFT")
    print("Ranking: Quarterly revenue YoY")
    print("FCF cross-company ranking: BLOCKED")
    print()

    for rank, result in enumerate(
        results,
        start=1
    ):

        ticker = result["ticker"]

        status = (
            "PASS"
            if result["passed"]
            else "FAIL"
        )

        print("-" * 68)
        print(
            f"{rank}. {ticker} | {status}"
        )

        print(
            f"FY{result['fiscal_year']} "
            f"Q{result['fiscal_quarter']} "
            f"| End: {result['period_end']}"
        )

        print(
            "Quarter revenue YoY:",
            fmt_pct(result["revenue_yoy"])
        )

        print(
            "Operating margin:",
            fmt_pct(result["operating_margin"])
        )

        print(
            "Operating margin YoY change:",
            fmt_pp(result["margin_improvement"])
        )

        print(
            "OCF margin (secondary):",
            fmt_pct(result["ocf_margin"])
        )

        print(
            "LTM revenue:",
            money_b(result["ltm_revenue"])
        )

        print(
            "LTM revenue YoY:",
            fmt_pct(result["ltm_revenue_yoy"])
        )

        print(
            "LTM operating margin:",
            fmt_pct(result["ltm_operating_margin"])
        )

        print(
            "Latest filing age:",
            f"{result['filing_age']} days"
        )

        if result["failed_reasons"]:

            print(
                "Failure reasons:",
                "; ".join(result["failed_reasons"])
            )

    statuses = Counter(
        result["passed"]
        for result in results
    )

    print()
    print("=" * 68)
    print("SCREENING SUMMARY")
    print("=" * 68)

    print("Total companies:", len(results))
    print("Fundamental PASS:", statuses[True])
    print("Fundamental FAIL:", statuses[False])

    print()
    print("Market-cap filter: NOT IMPLEMENTED")
    print("Debt filter: NOT IMPLEMENTED")
    print("Analyst coverage: NOT IMPLEMENTED")
    print("Technical signals: NOT IMPLEMENTED")
    print("FCF cross-company ranking: DISABLED")
    print()
    print("Database: READ ONLY")
    print("Four-company screening V0.3: PASS")


def main():

    rules, as_of = load_rules()

    require(
        DB_PATH.exists(),
        f"Database not found: {DB_PATH}"
    )

    con = duckdb.connect(
        str(DB_PATH),
        read_only=True
    )

    try:

        print()
        print("JK's FINANCIAL DATA LAB")
        print("Four-company Fundamental Screen V0.3")
        print("=" * 68)

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

        for row in records:

            ticker = row["ticker"]

            require(
                ticker in grouped,
                f"Unexpected company: {ticker}"
            )

            grouped[ticker].append(row)

        results = []

        for ticker in rules["expected_tickers"]:

            rows = grouped[ticker]

            validate_quarter_sequence(
                ticker,
                rows,
                as_of
            )

            print(
                f"{ticker}: 12-quarter validation PASS"
            )

            result = calculate_company(
                ticker,
                rows,
                rules,
                as_of
            )

            results.append(result)

        require(
            len(results) == 4,
            "Expected four screening results"
        )

        display_results(
            results,
            as_of
        )

    finally:

        con.close()


if __name__ == "__main__":
    main()