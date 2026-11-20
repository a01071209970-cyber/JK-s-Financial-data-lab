
"""
JK's Financial Data Lab V1.0
Week 5 - Valuation Input Discovery

Audit balance-sheet XBRL facts for:
    PLTR, NVDA, AMD, MSFT

Categories:
    Cash and investments
    Debt
    Stockholders' equity
    Shares outstanding

Important:
    - Point-in-time filing cutoff enforced
    - Duration facts excluded
    - No market prices
    - No debt aggregation yet
    - Read-only DuckDB access

Run:
    python src/audit_valuation_inputs.py
"""

import json
from collections import Counter
from datetime import date
from pathlib import Path

import duckdb

from check_company_config import load_companies


ROOT = Path(__file__).resolve().parent.parent

DB = ROOT / "data/processed/financial_data.duckdb"
RAW = ROOT / "data/raw"

RULES = (
    ROOT / "config/screening_rules_v03.json"
)

EXPECTED_TICKERS = {
    "PLTR",
    "NVDA",
    "AMD",
    "MSFT"
}

TAG_GROUPS = {
    "CASH_AND_INVESTMENTS": {
        "taxonomy": "us-gaap",
        "unit": "USD",
        "tags": [
            "CashAndCashEquivalentsAtCarryingValue",
            "ShortTermInvestments",
            "MarketableSecuritiesCurrent",
            "ShortTermInvestmentsAndMarketableSecurities",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "RestrictedCashAndCashEquivalentsCurrent",
        ],
    },

    "DEBT": {
        "taxonomy": "us-gaap",
        "unit": "USD",
        "tags": [
            "ShortTermBorrowings",
            "ShortTermDebtCurrent",
            "CommercialPaper",
            "LongTermDebtCurrent",
            "LongTermDebtNoncurrent",
            "LongTermDebt",
            "LongTermDebtAndFinanceLeaseObligations",
            "LongTermDebtAndCapitalLeaseObligations",
        ],
    },

    "EQUITY": {
        "taxonomy": "us-gaap",
        "unit": "USD",
        "tags": [
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ],
    },

    "SHARES_OUTSTANDING": {
        "taxonomy": "dei",
        "unit": "shares",
        "tags": [
            "EntityCommonStockSharesOutstanding",
        ],
    },

    "SHARES_US_GAAP": {
        "taxonomy": "us-gaap",
        "unit": "shares",
        "tags": [
            "CommonStockSharesOutstanding",
        ],
    },
}


def require(condition, message):

    if not condition:
        raise ValueError(message)


def parse_date(value):

    return date.fromisoformat(str(value))


def read_as_of():

    config = json.loads(
        RULES.read_text(encoding="utf-8")
    )

    require(
        config["version"] == 3,
        "Expected screening rules version 3"
    )

    require(
        set(config["expected_tickers"])
        == EXPECTED_TICKERS,
        "Unexpected screening universe"
    )

    return parse_date(
        config["as_of_date"]
    )


def latest_quarters(con, as_of):

    rows = con.execute("""
        SELECT
            ticker,
            fiscal_year,
            fiscal_quarter,
            period_end

        FROM quarterly_metrics_four_reconciled

        ORDER BY ticker, period_end
    """).fetchall()

    require(
        len(rows) == 48,
        "Expected 48 quarterly records"
    )

    counts = Counter(
        row[0] for row in rows
    )

    require(
        counts == {
            ticker: 12
            for ticker in EXPECTED_TICKERS
        },
        "Expected 12 quarters per company"
    )

    latest = {}

    for ticker, fy, quarter, end in rows:

        end_date = parse_date(end)

        require(
            end_date <= as_of,
            f"{ticker}: Future quarter"
        )

        latest[ticker] = {
            "fy": fy,
            "quarter": quarter,
            "end": end_date,
        }

    return latest


def select_instant_fact(
    tag_data,
    unit,
    cutoff,
    max_period_end
):
    observations = tag_data.get(
        "units", {}
    ).get(unit, [])

    candidates = []

    for item in observations:

        # An instant balance-sheet value has
        # an end date but no start date.
        if item.get("start") is not None:
            continue

        if item.get("form") not in (
            "10-Q",
            "10-K",
            "10-Q/A",
            "10-K/A",
        ):
            continue

        if (
            item.get("end") is None
            or item.get("filed") is None
            or item.get("val") is None
        ):
            continue

        end = parse_date(
            item["end"]
        )

        filed = parse_date(
            item["filed"]
        )

        if filed > cutoff:
            continue

        if end > max_period_end:
            continue

        candidates.append(item)

    if not candidates:
        return None

    # Prefer the latest measurement date.
    # Within that date, prefer the latest
    # filing known by the cutoff.
    candidates.sort(
        key=lambda item: (
            item["end"],
            item["filed"],
            item.get("accn", ""),
        ),
        reverse=True,
    )

    selected = candidates[0]

    # Check whether one filing contains
    # inconsistent values for the same
    # concept and measurement date.
    peers = [
        item
        for item in candidates
        if (
            item["end"] == selected["end"]
            and item["filed"] == selected["filed"]
            and item.get("accn", "")
                == selected.get("accn", "")
        )
    ]

    conflicting = (
        len({
            str(item["val"])
            for item in peers
        }) > 1
    )

    return {
        "value": selected["val"],
        "end": parse_date(
            selected["end"]
        ),
        "filed": parse_date(
            selected["filed"]
        ),
        "form": selected["form"],
        "conflicting": conflicting,
    }


def format_value(value, unit):

    if unit == "shares":
        return (
            f"{value:,.0f} shares "
            f"({value / 1e9:,.3f}B)"
        )

    return (
        f"${value:,.0f} "
        f"(${value / 1e9:,.3f}B)"
    )


def audit_company(
    ticker,
    company,
    latest,
    as_of
):

    path = (
        RAW /
        f"{ticker.lower()}_companyfacts.json"
    )

    require(
        path.exists(),
        f"Missing source file: {path}"
    )

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    require(
        int(data["cik"])
        == int(company["cik"]),
        f"{ticker}: CIK mismatch"
    )

    target = latest[ticker]

    print()
    print("=" * 75)
    print(
        f"{ticker} — "
        f"FY{target['fy']} Q{target['quarter']}"
    )
    print("=" * 75)

    print(
        "Quarter end:",
        target["end"]
    )

    print(
        "Filing cutoff:",
        as_of
    )

    found = {}

    for group_name, specification in TAG_GROUPS.items():

        taxonomy = specification["taxonomy"]
        unit = specification["unit"]

        print()
        print("-" * 75)
        print(group_name)
        print("-" * 75)

        matched = 0

        for tag in specification["tags"]:

            taxonomy_facts = (
                data["facts"].get(
                    taxonomy, {}
                )
            )

            tag_data = taxonomy_facts.get(
                tag
            )

            if tag_data is None:
                continue

            # For balance-sheet accounts,
            # require data from no later than
            # the latest fiscal-quarter end.
            #
            # DEI shares may have a later
            # measurement date stated in
            # the filing.
            max_period_end = (
                as_of
                if taxonomy == "dei"
                else target["end"]
            )

            observation = select_instant_fact(
                tag_data,
                unit,
                as_of,
                max_period_end
            )

            if observation is None:
                continue

            matched += 1

            measurement_end = (
                observation["end"]
            )

            if measurement_end == target["end"]:
                status = "QUARTER_END"
            elif measurement_end > target["end"]:
                status = "POST_QUARTER"
            else:
                status = "OLDER_DATE"

            found[(group_name, tag)] = {
                **observation,
                "status": status,
            }

            print()
            print("TAG:", tag)

            print(
                "VALUE:",
                format_value(
                    observation["value"],
                    unit
                )
            )

            print(
                "AS-OF:",
                measurement_end
            )

            print(
                "FILED:",
                observation["filed"]
            )

            print(
                "FORM:",
                observation["form"]
            )

            print(
                "STATUS:",
                status
            )

            if observation["conflicting"]:
                print(
                    "WARNING: CONFLICTING "
                    "VALUES IN SAME FILING"
                )

        if matched == 0:
            print(
                "NO MATCHING INSTANT FACTS"
            )

        print(
            "Candidate tags found:",
            matched
        )

    print()
    print(
        f"{ticker} valuation input discovery: COMPLETE"
    )

    return found


def main():

    as_of = read_as_of()

    companies = {
        company["ticker"]: company
        for company in load_companies()
    }

    require(
        set(companies) == EXPECTED_TICKERS,
        "Company configuration mismatch"
    )

    require(
        DB.exists(),
        f"Database not found: {DB}"
    )

    con = duckdb.connect(
        str(DB),
        read_only=True
    )

    try:
        observations = con.execute("""
            SELECT COUNT(*)
            FROM financial_facts_multi
        """).fetchone()[0]

        require(
            observations == 92717,
            "SEC observations changed"
        )

        latest = latest_quarters(
            con,
            as_of
        )

    finally:
        con.close()

    print()
    print("WEEK 5 VALUATION INPUT AUDIT")
    print("=" * 75)

    print("Companies:", len(companies))
    print("SEC observations:", observations)
    print("Filing cutoff:", as_of)

    results = {}

    for ticker in (
        "PLTR",
        "NVDA",
        "AMD",
        "MSFT"
    ):
        results[ticker] = audit_company(
            ticker,
            companies[ticker],
            latest,
            as_of
        )

    print()
    print("=" * 75)
    print("AUDIT SUMMARY")
    print("=" * 75)

    for ticker, items in results.items():
        print(
            f"{ticker}: "
            f"{len(items)} candidate tags"
        )

    print()
    print("Next action: Review debt/cash definitions")
    print("Market prices: NOT LOADED")
    print("Enterprise value: NOT CALCULATED")
    print("Database: READ ONLY")
    print("Week 5 valuation input audit: PASS")


if __name__ == "__main__":
    main()