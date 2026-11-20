
"""
JK's Financial Data Lab V1.0
Week 5 - Valuation Coverage Audit

Search SEC Company Facts for additional
balance-sheet input candidates.

Universe:
    PLTR, NVDA, AMD, MSFT

Policies:
    - As-of filing cutoff enforced
    - Quarter-end balance-sheet dates required
    - Post-quarter DEI shares shown separately
    - Stale balance-sheet values excluded
    - Debt and investments are NOT summed
    - No enterprise value calculation
    - Read-only database access

Run:
    python src/audit_valuation_coverage.py
"""

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import duckdb

from check_company_config import load_companies


ROOT = Path(__file__).resolve().parent.parent

DB = ROOT / "data/processed/financial_data.duckdb"

RAW = ROOT / "data/raw"

RULES = ROOT / "config/screening_rules_v03.json"

EXPECTED_TICKERS = {
    "PLTR",
    "NVDA",
    "AMD",
    "MSFT"
}

FORMS = {
    "10-Q",
    "10-Q/A",
    "10-K",
    "10-K/A"
}

GROUPS = [
    "CASH_AND_INVESTMENT_CANDIDATES",
    "DEBT_CANDIDATES",
    "LEASE_LIABILITIES",
    "EQUITY",
    "SHARES"
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def as_date(value):
    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value))


def read_rules():

    data = json.loads(
        RULES.read_text(encoding="utf-8")
    )

    require(
        data.get("version") == 3,
        "Unsupported screening configuration"
    )

    require(
        set(data["expected_tickers"])
        == EXPECTED_TICKERS,
        "Unexpected company universe"
    )

    return as_date(data["as_of_date"])


def read_latest_quarters(con, cutoff):

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
        "Incorrect quarterly coverage"
    )

    latest = {}

    for ticker, fy, quarter, period_end in rows:

        end = as_date(period_end)

        require(
            end <= cutoff,
            f"{ticker}: Future reporting period"
        )

        latest[ticker] = {
            "fiscal_year": fy,
            "quarter": quarter,
            "end": end
        }

    return latest


def classify(taxonomy, tag):
    """
    Candidate classification only.

    Inclusion in a group does not imply
    suitability for valuation calculation.
    """

    if taxonomy == "dei":

        if tag == "EntityCommonStockSharesOutstanding":
            return "SHARES"

        return None

    if taxonomy != "us-gaap":
        return None

    if tag == "CommonStockSharesOutstanding":
        return "SHARES"

    if tag in (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    ):
        return "EQUITY"

    name = tag.lower()

    # Lease liabilities must not be silently
    # merged into ordinary financial debt.
    if (
        "lease" in name
        and any(
            term in name
            for term in (
                "liability",
                "obligation",
                "payable"
            )
        )
    ):
        return "LEASE_LIABILITIES"

    # Debt securities and investments are
    # asset candidates, not borrowings.
    asset_terms = (
        "cash",
        "investment",
        "securit",
        "deposit",
        "moneymarket",
        "treasurybill",
        "restrictedcash"
    )

    if any(
        term in name
        for term in asset_terms
    ):
        return "CASH_AND_INVESTMENT_CANDIDATES"

    debt_terms = (
        "debt",
        "borrow",
        "commercialpaper",
        "notespayable",
        "lineofcredit",
        "creditfacility",
        "convertiblenote",
        "seniornotes",
        "debenture"
    )

    if any(
        term in name
        for term in debt_terms
    ):
        return "DEBT_CANDIDATES"

    return None


def choose_observation(
    tag_data,
    taxonomy,
    unit,
    quarter_end,
    cutoff
):
    """
    For US-GAAP balance-sheet facts, accept
    only exact quarter-end instant values.

    DEI shares may be measured after the
    quarter-end date in the same filing.
    """

    observations = tag_data.get(
        "units", {}
    ).get(unit, [])

    candidates = []

    for item in observations:

        if item.get("start") is not None:
            continue

        if item.get("form") not in FORMS:
            continue

        if (
            item.get("end") is None
            or item.get("filed") is None
            or item.get("val") is None
        ):
            continue

        end = as_date(item["end"])
        filed = as_date(item["filed"])

        if filed > cutoff:
            continue

        if taxonomy == "dei":

            if not (
                quarter_end
                <= end
                <= min(
                    cutoff,
                    quarter_end + timedelta(days=60)
                )
            ):
                continue

        else:

            if end != quarter_end:
                continue

        candidates.append(item)

    if not candidates:
        return None

    # Prefer the latest available filing
    # for the selected measurement date.
    candidates.sort(
        key=lambda item: (
            item["end"],
            item["filed"],
            item.get("accn", "")
        ),
        reverse=True
    )

    selected = candidates[0]

    same_source = [
        item
        for item in candidates
        if (
            item["end"] == selected["end"]
            and item["filed"] == selected["filed"]
            and item.get("accn", "")
                == selected.get("accn", "")
        )
    ]

    conflict = (
        len({
            str(item["val"])
            for item in same_source
        }) > 1
    )

    return {
        "value": selected["val"],
        "measurement_date": as_date(
            selected["end"]
        ),
        "filed": as_date(
            selected["filed"]
        ),
        "form": selected["form"],
        "accession": selected.get("accn"),
        "conflict": conflict
    }


def inspect_company(
    ticker,
    company,
    target,
    cutoff
):

    path = (
        RAW /
        f"{ticker.lower()}_companyfacts.json"
    )

    require(
        path.exists(),
        f"Missing SEC file: {path}"
    )

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    require(
        int(data["cik"]) == int(company["cik"]),
        f"{ticker}: Incorrect SEC CIK"
    )

    quarter_end = target["end"]

    matches = {
        group: []
        for group in GROUPS
    }

    for taxonomy, facts in data["facts"].items():

        for tag, tag_data in facts.items():

            group = classify(
                taxonomy,
                tag
            )

            if group is None:
                continue

            unit = (
                "shares"
                if group == "SHARES"
                else "USD"
            )

            selected = choose_observation(
                tag_data,
                taxonomy,
                unit,
                quarter_end,
                cutoff
            )

            if selected is None:
                continue

            matches[group].append({
                "taxonomy": taxonomy,
                "tag": tag,
                "label": tag_data.get("label", ""),
                "unit": unit,
                **selected
            })

    print()
    print("=" * 78)

    print(
        f"{ticker} — "
        f"FY{target['fiscal_year']} "
        f"Q{target['quarter']}"
    )

    print("=" * 78)

    print("Quarter end:", quarter_end)
    print("Filing cutoff:", cutoff)

    for group in GROUPS:

        entries = sorted(
            matches[group],
            key=lambda item: (
                item["taxonomy"],
                item["tag"]
            )
        )

        print()
        print("-" * 78)
        print(group)
        print("-" * 78)

        if not entries:
            print(
                "NO CURRENT-PERIOD CANDIDATE FOUND"
            )
            continue

        for item in entries:

            value = item["value"]

            if item["unit"] == "shares":
                readable = (
                    f"{value / 1e9:,.3f}B shares"
                )
            else:
                readable = (
                    f"${value / 1e9:,.3f}B"
                )

            status = (
                "QUARTER_END"
                if item["measurement_date"]
                == quarter_end
                else "POST_QUARTER"
            )

            print()
            print(
                f"{item['taxonomy']}:{item['tag']}"
            )

            print(
                f"  Value: {readable}"
            )

            print(
                "  Measurement:",
                item["measurement_date"]
            )

            print(
                "  Filed:",
                item["filed"],
                "|",
                item["form"]
            )

            print(
                "  Status:",
                status
            )

            if item["conflict"]:
                print(
                    "  WARNING: Conflicting "
                    "same-filing facts"
                )

        print(
            "Current candidates:",
            len(entries)
        )

    print()
    print(
        f"{ticker} coverage discovery: COMPLETE"
    )

    return {
        group: len(matches[group])
        for group in GROUPS
    }


def main():

    cutoff = read_rules()

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
            "SEC observation count mismatch"
        )

        latest = read_latest_quarters(
            con,
            cutoff
        )

    finally:
        con.close()

    print()
    print("WEEK 5 VALUATION COVERAGE AUDIT")
    print("=" * 78)
    print("Companies:", len(companies))
    print("SEC observations:", observations)
    print("Filing cutoff:", cutoff)
    print("Measurement policy: QUARTER-END ONLY")

    results = {}

    for ticker in (
        "PLTR",
        "NVDA",
        "AMD",
        "MSFT"
    ):

        results[ticker] = inspect_company(
            ticker,
            companies[ticker],
            latest[ticker],
            cutoff
        )

    print()
    print("=" * 78)
    print("COVERAGE SUMMARY")
    print("=" * 78)

    for ticker, counts in results.items():

        print()
        print(ticker)

        for group, count in counts.items():
            print(
                f"  {group}: {count}"
            )

    print()
    print("Debt aggregation: NOT PERFORMED")
    print("Market cap: NOT CALCULATED")
    print("Enterprise value: NOT CALCULATED")
    print("Database: READ ONLY")
    print("Week 5 coverage audit: PASS")


if __name__ == "__main__":
    main()