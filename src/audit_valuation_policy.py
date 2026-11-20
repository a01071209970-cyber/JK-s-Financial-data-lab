
"""JK's Financial Data Lab - Week 5, valuation policy audit.

Reads SEC Company Facts with a point-in-time cutoff.
No database changes. No market prices. No EV calculation.
"""

import json
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb

from check_company_config import load_companies


ROOT = Path(__file__).resolve().parent.parent

DB = ROOT / "data/processed/financial_data.duckdb"
RAW = ROOT / "data/raw"

POLICY_PATH = ROOT / "config/valuation_input_policy.json"
SCREEN_PATH = ROOT / "config/screening_rules_v03.json"

VALID_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A"}

USD_B = Decimal("1000000000")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def d(value):
    return Decimal(str(value))


def fmt(value):
    return (
        "N/A"
        if value is None
        else f"${d(value) / USD_B:,.3f}B"
    )


def find_instant(
    facts,
    taxonomy,
    tag,
    unit,
    quarter_end,
    cutoff
):

    if tag is None:
        return None

    observations = (
        facts.get(taxonomy, {})
        .get(tag, {})
        .get("units", {})
        .get(unit, [])
    )

    matches = []

    for item in observations:

        if (
            item.get("start") is not None
            or item.get("form") not in VALID_FORMS
        ):
            continue

        if not all(
            k in item
            for k in ("end", "filed", "val")
        ):
            continue

        measurement = date.fromisoformat(
            item["end"]
        )

        filed = date.fromisoformat(
            item["filed"]
        )

        if filed > cutoff or measurement > filed:
            continue

        if taxonomy == "dei":

            if not (
                quarter_end <= measurement
                <= min(
                    cutoff,
                    quarter_end + timedelta(days=60)
                )
            ):
                continue

        elif measurement != quarter_end:
            continue

        matches.append(item)

    if not matches:
        return None

    matches.sort(
        key=lambda x: (
            x["end"],
            x["filed"],
            x.get("accn", "")
        ),
        reverse=True
    )

    chosen = matches[0]

    same_filing = [
        x
        for x in matches
        if (
            x["end"],
            x["filed"],
            x.get("accn", "")
        ) == (
            chosen["end"],
            chosen["filed"],
            chosen.get("accn", "")
        )
    ]

    require(
        len({
            str(x["val"])
            for x in same_filing
        }) == 1,
        f"Conflicting facts: {taxonomy}:{tag}"
    )

    return {
        "value": d(chosen["val"]),
        "measurement": date.fromisoformat(
            chosen["end"]
        ),
        "filed": date.fromisoformat(
            chosen["filed"]
        ),
        "tag": tag
    }


def latest_quarters(con, cutoff, tickers):

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
        "Expected 48 reconciled quarters"
    )

    require(
        Counter(
            r[0] for r in rows
        ) == {
            ticker: 12
            for ticker in tickers
        },
        "Unexpected quarter coverage"
    )

    latest = {}

    for ticker, fy, quarter, end in rows:

        latest[ticker] = (
            fy,
            quarter,
            (
                end
                if isinstance(end, date)
                else date.fromisoformat(str(end))
            )
        )

    require(
        all(
            q[2] <= cutoff
            for q in latest.values()
        ),
        "Future period found"
    )

    return latest


def main():

    policy = json.loads(
        POLICY_PATH.read_text(encoding="utf-8")
    )

    screen = json.loads(
        SCREEN_PATH.read_text(encoding="utf-8")
    )

    require(
        policy["version"] == 1,
        "Unsupported valuation policy version"
    )

    cutoff = date.fromisoformat(
        policy["as_of_date"]
    )

    require(
        cutoff == date.fromisoformat(
            screen["as_of_date"]
        ),
        "As-of mismatch"
    )

    tickers = policy["expected_tickers"]

    require(
        set(tickers) == {
            "PLTR",
            "NVDA",
            "AMD",
            "MSFT"
        },
        "Unexpected universe"
    )

    require(
        set(screen["expected_tickers"])
        == set(tickers),
        "Screen universe mismatch"
    )

    require(
        set(policy["companies"])
        == set(tickers),
        "Missing company policy"
    )

    companies = {
        x["ticker"]: x
        for x in load_companies()
    }

    require(
        set(companies) == set(tickers),
        "Company config mismatch"
    )

    require(
        DB.exists(),
        "DuckDB not found"
    )

    con = duckdb.connect(
        str(DB),
        read_only=True
    )

    try:

        count = con.execute("""
            SELECT COUNT(*)
            FROM financial_facts_multi
        """).fetchone()[0]

        require(
            count == 92717,
            f"Raw facts changed: {count}"
        )

        latest = latest_quarters(
            con,
            cutoff,
            tickers
        )

    finally:
        con.close()

    print()
    print("WEEK 5 VALUATION INPUT POLICY AUDIT")
    print("=" * 66)

    print("As-of:", cutoff)
    print("SEC observations:", f"{count:,}")
    print("Lease liabilities: separately disclosed")
    print("Market prices / EV: NOT CALCULATED")

    for ticker in tickers:

        company = companies[ticker]

        settings = policy["companies"][ticker]

        fy, quarter, end = latest[ticker]

        path = (
            RAW /
            f"{ticker.lower()}_companyfacts.json"
        )

        require(
            path.exists(),
            f"Missing original SEC facts: {path}"
        )

        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        require(
            int(data["cik"]) == int(company["cik"]),
            f"{ticker}: CIK mismatch"
        )

        facts = data["facts"]

        def get(
            key,
            taxonomy="us-gaap",
            unit="USD"
        ):

            tag = settings.get(key)

            result = find_instant(
                facts,
                taxonomy,
                tag,
                unit,
                end,
                cutoff
            )

            if tag is not None:

                require(
                    result is not None,
                    (
                        f"{ticker}: quarter-end "
                        f"tag missing: {tag}"
                    )
                )

            return (
                result["value"]
                if result is not None
                else None
            )

        cash = get("cash_tag")

        investments = get(
            "short_term_investments_tag"
        )

        liquid_total = get(
            "combined_liquidity_tag"
        )

        debt = get("debt_total_tag")

        debt_current = get(
            "debt_current_tag"
        )

        debt_noncurrent = get(
            "debt_noncurrent_tag"
        )

        operating_lease = get(
            "operating_lease_total_tag"
        )

        operating_lease_noncurrent = get(
            "operating_lease_noncurrent_tag"
        )

        finance_lease = get(
            "finance_lease_total_tag"
        )

        equity = get("equity_tag")

        shares = get(
            "shares_tag",
            settings["shares_taxonomy"],
            "shares"
        )

        # Debt carrying amount reconciliation.
        # Never add parent totals to components.

        if (
            debt is not None
            and debt_current is not None
            and debt_noncurrent is not None
        ):

            require(
                debt == debt_current + debt_noncurrent,
                (
                    f"{ticker}: debt components "
                    "do not reconcile"
                )
            )

        # Liquidity from approved, non-overlapping
        # cash and short-term investment categories.

        liquid = (
            cash + investments
            if (
                cash is not None
                and investments is not None
            )
            else None
        )

        if liquid_total is not None:

            require(
                liquid is not None
                and liquid == liquid_total,
                (
                    f"{ticker}: cash/investment "
                    "aggregation does not reconcile"
                )
            )

        # This is a provisional calculation only.
        # Operating and finance leases are excluded.

        if settings[
            "allow_provisional_net_liquidity"
        ]:

            require(
                liquid is not None
                and debt is not None,
                (
                    f"{ticker}: incomplete inputs "
                    "for provisional net liquidity"
                )
            )

            net = liquid - debt

        else:
            net = None

        debt_equity = (
            None
            if debt is None
            or equity in (None, Decimal(0))
            else debt / equity * 100
        )

        print()
        print("-" * 66)

        print(
            f"{ticker} FY{fy} Q{quarter} "
            f"| Period end: {end}"
        )

        print("Cash:", fmt(cash))

        print(
            "Selected short-term investments:",
            fmt(investments)
        )

        print(
            "Selected liquid assets:",
            fmt(liquid),
            (
                "(PARTIAL)"
                if liquid is None
                else "(PROVISIONAL)"
            )
        )

        print(
            "Borrowings, selected definition:",
            fmt(debt)
        )

        print(
            "Borrowings/equity:",
            (
                "N/A"
                if debt_equity is None
                else (
                    f"{debt_equity:.2f}% "
                    "(PROVISIONAL)"
                )
            )
        )

        print(
            "Operating lease liability:",
            fmt(operating_lease)
        )

        print(
            "Operating lease noncurrent (partial):",
            fmt(operating_lease_noncurrent)
        )

        print(
            "Finance lease liability:",
            fmt(finance_lease)
        )

        print(
            "Shares (raw, not market cap):",
            (
                "N/A"
                if shares is None
                else f"{shares:,.0f}"
            )
        )

        print(
            "Provisional liquid assets - borrowings:",
            fmt(net)
        )

        print(
            "Net calculation:",
            (
                "PROVISIONAL"
                if net is not None
                else "BLOCKED"
            )
        )

        print(
            "Review:",
            settings["review_note"]
        )

    print()
    print("VALUATION POLICY AUDIT: PASS")
    print("Database: READ ONLY")
    print(
        "Final net debt / enterprise value: "
        "NOT APPROVED"
    )


if __name__ == "__main__":
    main()