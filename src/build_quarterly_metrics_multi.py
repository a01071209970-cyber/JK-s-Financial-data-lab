
"""
JK's Financial Data Lab V1.0
Week 3 - Multi-Company Quarterly Metrics

Builds quarterly_metrics_multi from SEC facts.
Preserves all original Week 2 tables.

Usage:
python src/build_quarterly_metrics_multi.py
"""

import argparse
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import duckdb

from check_company_config import load_companies, periods


ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data/processed/financial_data.duckdb"
TAG_CONFIG = ROOT / "config/metric_tags.json"

MEASURES = ("revenue", "operating_income", "ocf", "capex")
Q_FORMS = ("10-Q", "10-Q/A")
K_FORMS = ("10-K", "10-K/A")

CENT = Decimal("0.01")


# --------------------------------------------------
# 1. SAFE DATABASE HELPERS
# --------------------------------------------------

def scalar(con, query, params=None):
    rows = con.execute(
        query,
        params or []
    ).fetchall()

    if len(rows) != 1 or len(rows[0]) != 1:
        raise ValueError("Expected one scalar result")

    return rows[0][0]


def ratio(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None

    value = (
        Decimal(numerator) * 100
        / Decimal(denominator)
    )

    return value.quantize(
        CENT,
        rounding=ROUND_HALF_UP
    )


# --------------------------------------------------
# 2. READ FINANCIAL FACTS
# --------------------------------------------------

def read_index(con, tags, as_of):
    unique_tags = sorted({
        tag
        for mapping in tags.values()
        for tag in mapping.values()
    })

    placeholders = ", ".join(
        "?" for _ in unique_tags
    )

    rows = con.execute(
        f"""
        SELECT
            ticker,
            tag,
            period_start,
            period_end,
            filed,
            accn,
            form,
            value_raw

        FROM financial_facts_multi

        WHERE taxonomy = 'us-gaap'
          AND unit = 'USD'
          AND filed <= ?
          AND tag IN ({placeholders})
          AND form IN (
              '10-Q', '10-Q/A',
              '10-K', '10-K/A'
          )
        """,
        [as_of, *unique_tags]
    ).fetchall()

    index = defaultdict(list)

    for ticker, tag, start, end, filed, accn, form, raw in rows:

        if start is None or end is None:
            continue

        amount = Decimal(raw)

        if amount != amount.to_integral_value():
            raise ValueError(
                f"Nonintegral USD fact: "
                f"{ticker} {tag} {raw}"
            )

        key = (
            ticker, tag, start, end, form
        )

        index[key].append({
            "value": int(amount),
            "filed": filed,
            "accn": accn or ""
        })

    return index


# --------------------------------------------------
# 3. FIRST-AVAILABLE FILING
# --------------------------------------------------

def first(
    index,
    ticker,
    tag,
    start,
    end,
    forms,
    latest=None
):
    candidates = []

    for form in forms:
        key = (ticker, tag, start, end, form)
        candidates.extend(index.get(key, []))

    if latest is not None:
        candidates = [
            r for r in candidates
            if r["filed"] <= latest
        ]

    if not candidates:
        return None

    candidates.sort(
        key=lambda r: (
            r["filed"],
            r["accn"]
        )
    )

    earliest = candidates[0]

    duplicates = [
        r for r in candidates
        if (
            r["filed"], r["accn"]
        ) == (
            earliest["filed"], earliest["accn"]
        )
    ]

    if len({r["value"] for r in duplicates}) > 1:
        raise ValueError(
            f"Conflicting first-filed facts: "
            f"{ticker} {tag} {start} {end}"
        )

    return earliest


def result(value, method, observations):
    return {
        "value": value,
        "method": method,
        "available": max(
            r["filed"] for r in observations
        ),
        "sources": [
            {
                "filed": str(r["filed"]),
                "accn": r["accn"]
            }
            for r in observations
        ]
    }


# --------------------------------------------------
# 4. CALCULATE INDIVIDUAL QUARTERS
# --------------------------------------------------

def calculate(index, ticker, tag, ps, quarter, metric):
    current_period = ps[quarter - 1]

    fiscal_start = ps[0]["start"]

    q_start = current_period["start"]
    q_end = current_period["end"]

    # Revenue and operating income:
    # Q1-Q3 use direct quarterly observations.
    if metric in ("revenue", "operating_income") and quarter <= 3:

        direct = first(
            index, ticker, tag,
            q_start, q_end, Q_FORMS
        )

        if direct is None:
            return None

        return result(
            direct["value"],
            "DIRECT",
            [direct]
        )

    # Q4 comes from the annual 10-K.
    forms = K_FORMS if quarter == 4 else Q_FORMS

    current = first(
        index, ticker, tag,
        fiscal_start, q_end, forms
    )

    if current is None:
        return None

    # Q1 cumulative cash flow = Q1 cash flow.
    if quarter == 1:
        return result(
            current["value"],
            "Q1_YTD",
            [current]
        )

    # Q2/Q3/Q4: current YTD minus previous YTD.
    prior_end = ps[quarter - 2]["end"]

    previous = first(
        index,
        ticker,
        tag,
        fiscal_start,
        prior_end,
        Q_FORMS,
        latest=current["filed"]
    )

    if previous is None:
        return None

    method = (
        "FY_MINUS_9M"
        if quarter == 4
        else "YTD_DIFFERENCE"
    )

    return result(
        current["value"] - previous["value"],
        method,
        [current, previous]
    )


# --------------------------------------------------
# 5. BUILD COMPANY QUARTERLY HISTORY
# --------------------------------------------------

def build_rows(company, tags, index, as_of):
    ticker = company["ticker"]

    history = []

    for fy in range(2022, as_of.year + 3):
        fiscal_periods = periods(company, fy)

        for quarter in range(1, 5):
            p = fiscal_periods[quarter - 1]

            if p["end"] > as_of:
                continue

            metrics = {
                metric: calculate(
                    index,
                    ticker,
                    tags[metric],
                    fiscal_periods,
                    quarter,
                    metric
                )
                for metric in MEASURES
            }

            complete = all(
                value is not None
                for value in metrics.values()
            )

            history.append({
                "fy": fy,
                "q": quarter,
                "start": p["start"],
                "end": p["end"],
                "results": metrics,
                "complete": complete
            })

    # Find the most recent fully reported quarter.
    last = next(
        (
            i for i in range(len(history) - 1, -1, -1)
            if history[i]["complete"]
        ),
        None
    )

    if last is None or last < 11:
        raise ValueError(
            f"{ticker}: fewer than 12 historical quarters"
        )

    # Keep the latest 12 consecutive quarters.
    # Missing observations are retained as REVIEW.
    selected = history[last - 11:last + 1]

    by_period = {
        (row["fy"], row["q"]): row
        for row in history
    }

    output = []

    for row in selected:
        fy = row["fy"]
        q = row["q"]

        metrics = row["results"]

        values = {
            metric: (
                metrics[metric]["value"]
                if metrics[metric] else None
            )
            for metric in MEASURES
        }

        revenue = values["revenue"]
        income = values["operating_income"]

        ocf = values["ocf"]
        capex = values["capex"]

        fcf = (
            ocf - capex
            if ocf is not None and capex is not None
            else None
        )

        # Year-over-year comparison
        prior = by_period.get((fy - 1, q))

        old_revenue = None
        old_income = None

        if prior:
            old_metrics = prior["results"]

            if old_metrics["revenue"]:
                old_revenue = old_metrics["revenue"]["value"]

            if old_metrics["operating_income"]:
                old_income = old_metrics["operating_income"]["value"]

        growth = None
        margin_change = None

        if revenue is not None and old_revenue not in (None, 0):

            growth = ratio(
                revenue - old_revenue,
                old_revenue
            )

            if income is not None and old_income is not None and revenue:

                margin_change = (
                    (
                        Decimal(income) / Decimal(revenue)
                        - Decimal(old_income) / Decimal(old_revenue)
                    ) * 100
                ).quantize(
                    CENT,
                    rounding=ROUND_HALF_UP
                )

        available = (
            max(
                metric["available"]
                for metric in metrics.values()
            )
            if row["complete"]
            else None
        )

        status = (
            "PASS"
            if row["complete"] and revenue
            else "REVIEW"
        )

        output.append((
            int(company["cik"]),
            ticker,
            fy,
            q,
            row["start"],
            row["end"],

            revenue,
            income,
            ocf,
            capex,
            fcf,

            growth,
            ratio(income, revenue),
            margin_change,
            ratio(fcf, revenue),

            tags["capex"],

            (
                metrics["revenue"]["method"]
                if metrics["revenue"] else None
            ),
            (
                metrics["operating_income"]["method"]
                if metrics["operating_income"] else None
            ),
            (
                metrics["ocf"]["method"]
                if metrics["ocf"] else None
            ),

            available,
            as_of,

            json.dumps(
                metrics,
                default=str,
                ensure_ascii=False
            ),

            status
        ))

        if status != "PASS":
            missing = [
                metric for metric in MEASURES
                if metrics[metric] is None
            ]

            print(
                f"REVIEW {ticker} FY{fy} Q{q}: "
                f"missing {', '.join(missing)}"
            )

    return output


# --------------------------------------------------
# 6. CHECK AGAINST WEEK 2 RESULTS
# --------------------------------------------------

def check_known(rows, legacy):
    lookup = {
        (r[1], r[2], r[3]): r
        for r in rows
    }

    nvda = lookup.get(("NVDA", 2027, 2))

    expected_nvda = (
        96221000000,
        63734000000,
        24077000000,
        2677000000,
        21400000000
    )

    if (
        nvda is None
        or tuple(nvda[i] for i in (6, 7, 8, 9, 10))
        != expected_nvda
    ):
        raise ValueError(
            "NVDA FY2027 Q2 cross-check failed"
        )

    pltr = [
        row for row in rows
        if row[1] == "PLTR"
    ]

    if len(pltr) != 12:
        raise ValueError(
            "PLTR must have exactly 12 quarters"
        )

    for row in pltr:
        key = (row[2], row[3])
        old = legacy.get(key)

        if old is None:
            raise ValueError(
                f"Missing original PLTR FY{key[0]} Q{key[1]}"
            )

        current_values = tuple(
            int(row[i]) if row[i] is not None else None
            for i in range(6, 11)
        )

        if current_values != old:
            raise ValueError(
                f"PLTR legacy mismatch: "
                f"FY{key[0]} Q{key[1]}"
            )

    print("PLTR Week 2 comparison: PASS")
    print("NVDA FY2027 Q2 cross-check: PASS")


# --------------------------------------------------
# 7. SAVE NEW TABLE SAFELY
# --------------------------------------------------

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--as-of",
        default="2026-11-17"
    )

    args = parser.parse_args()
    as_of = date.fromisoformat(args.as_of)

    companies = load_companies()

    tag_config = json.loads(
        TAG_CONFIG.read_text(encoding="utf-8")
    )

    tags = tag_config["metric_tags"]

    for company in companies:
        ticker = company["ticker"]

        if any(
            metric not in tags[ticker]
            for metric in MEASURES
        ):
            raise ValueError(
                f"Missing tag mapping: {ticker}"
            )

    # Read-only connection:
    # collect inputs and protect legacy data.
    reader = duckdb.connect(
        str(DB),
        read_only=True
    )

    try:
        original_facts = scalar(
            reader,
            """
            SELECT COUNT(*)
            FROM financial_facts
            WHERE cik = 1321655
            """
        )

        if original_facts != 8134:
            raise ValueError(
                "Week 2 financial facts changed"
            )

        original = reader.execute("""
            SELECT
                fiscal_year,
                fiscal_quarter,
                revenue_usd,
                operating_income_usd,
                ocf_usd,
                capex_usd,
                fcf_usd
            FROM quarterly_metrics
        """).fetchall()

        legacy = {
            (fy, q): tuple(
                int(value) for value in metrics
            )
            for fy, q, *metrics in original
        }

        if len(legacy) != 12:
            raise ValueError(
                "Week 2 quarterly metrics changed"
            )

        index = read_index(
            reader,
            tags,
            as_of
        )

    finally:
        reader.close()

    # Calculate all quarters before DB mutation.
    all_rows = []

    for company in companies:
        ticker = company["ticker"]

        company_rows = build_rows(
            company,
            tags[ticker],
            index,
            as_of
        )

        all_rows.extend(company_rows)

        print(
            f"Prepared {ticker}: "
            f"{len(company_rows)} quarters"
        )

    check_known(all_rows, legacy)

    # Write only the new multi-company table.
    con = duckdb.connect(str(DB))

    try:
        con.execute("BEGIN TRANSACTION")

        try:
            con.execute("""
                CREATE OR REPLACE TABLE
                    quarterly_metrics_multi (

                    cik BIGINT,
                    ticker VARCHAR,

                    fiscal_year INTEGER,
                    fiscal_quarter INTEGER,

                    period_start DATE,
                    period_end DATE,

                    revenue_usd DECIMAL(38,0),
                    operating_income_usd DECIMAL(38,0),

                    ocf_usd DECIMAL(38,0),
                    capex_usd DECIMAL(38,0),
                    fcf_usd DECIMAL(38,0),

                    revenue_growth_yoy_pct DECIMAL(12,2),
                    operating_margin_pct DECIMAL(12,2),
                    operating_margin_yoy_change_pp DECIMAL(12,2),
                    fcf_margin_pct DECIMAL(12,2),

                    capex_tag VARCHAR,

                    revenue_method VARCHAR,
                    operating_income_method VARCHAR,
                    cashflow_method VARCHAR,

                    available_date DATE,
                    as_of_date DATE,

                    source_json VARCHAR,
                    validation_status VARCHAR,

                    PRIMARY KEY (
                        cik,
                        fiscal_year,
                        fiscal_quarter
                    )
                )
            """)

            placeholders = ",".join(
                ["?"] * 23
            )

            con.executemany(
                "INSERT INTO quarterly_metrics_multi "
                f"VALUES ({placeholders})",
                all_rows
            )

            inserted = scalar(
                con,
                """
                SELECT COUNT(*)
                FROM quarterly_metrics_multi
                """
            )

            if inserted != len(all_rows):
                raise ValueError(
                    "Inserted row count mismatch"
                )

            if scalar(
                con,
                "SELECT COUNT(*) FROM quarterly_metrics"
            ) != 12:
                raise ValueError(
                    "Original Week 2 table changed"
                )

            con.execute("COMMIT")

        except Exception:
            con.execute("ROLLBACK")
            raise

        print()
        print("QUARTERLY METRICS MULTI")
        print("-" * 72)

        summary = con.execute("""
            SELECT
                ticker,
                COUNT(*) AS quarters,

                SUM(
                    CASE
                        WHEN validation_status = 'PASS'
                        THEN 1
                        ELSE 0
                    END
                ) AS passed,

                MIN(period_end) AS first_end,
                MAX(period_end) AS last_end

            FROM quarterly_metrics_multi

            GROUP BY ticker
            ORDER BY ticker
        """).fetchall()

        for ticker, count, passed, first_end, last_end in summary:
            print(
                f"{ticker}: {count} quarters "
                f"| PASS {passed} "
                f"| {first_end} ~ {last_end}"
            )

        print()
        print("Week 2 tables: PRESERVED")
        print("NVDA CAPEX: PROVISIONAL TAG")
        print("Database:", DB)

    finally:
        con.close()


if __name__ == "__main__":
    main()