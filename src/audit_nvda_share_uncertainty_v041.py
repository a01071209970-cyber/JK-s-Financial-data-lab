
"""NVDA V0.4.1: audit pre-close SEC share facts and quantify
hypothetical share-count sensitivity.

Reads existing V0.4 CSVs, SHA-256 metadata, SEC Company
Facts, and manually reviewed PIT evidence.

No network calls or DuckDB writes.
"""

import csv
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw"
REPORTS = ROOT / "reports"
PIT_PATH = ROOT / "config/pit_evidence_v04.json"

BILLION = Decimal("1000000000")
TICKERS = {"PLTR", "NVDA", "AMD", "MSFT"}
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dec(value):
    result = Decimal(str(value))
    require(result.is_finite(), "Non-finite numeric input")
    return result


def read_json(path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def read_rows(path):
    with path.open(
        newline="",
        encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))

    require(
        len(rows) == 4,
        f"Expected four rows: {path.name}"
    )

    lookup = {
        row["ticker"]: row
        for row in rows
    }

    require(
        len(lookup) == 4
        and set(lookup) == TICKERS,
        f"Duplicate or unknown ticker: {path.name}"
    )

    return lookup


def eligible_share_facts(facts, cutoff):
    """
    Exclude same-day filings unless intraday
    acceptance time has been separately verified.

    SEC Company Facts normally supplies filing
    dates rather than exact acceptance times.
    """

    rows = []

    tags = (
        ("dei", "EntityCommonStockSharesOutstanding"),
        ("us-gaap", "CommonStockSharesOutstanding"),
    )

    for taxonomy, tag in tags:

        entries = (
            facts.get(taxonomy, {})
            .get(tag, {})
            .get("units", {})
            .get("shares", [])
        )

        for item in entries:

            if item.get("start") is not None:
                continue

            if item.get("form") not in FORMS:
                continue

            if any(
                item.get(key) is None
                for key in ("end", "filed", "val")
            ):
                continue

            observed = date.fromisoformat(
                item["end"]
            )

            filed = date.fromisoformat(
                item["filed"]
            )

            if not (
                observed <= filed < cutoff
            ):
                continue

            shares = dec(item["val"])

            if (
                shares <= 0
                or shares != shares.to_integral_value()
            ):
                continue

            rows.append({
                "measurement": observed,
                "filed": filed,
                "shares": shares,
                "tag": f"{taxonomy}:{tag}",
                "accn": item.get("accn", ""),
            })

    rows.sort(
        key=lambda row: (
            row["measurement"],
            row["filed"],
            row["tag"].startswith("dei:"),
            row["accn"],
        ),
        reverse=True
    )

    return rows


def main():

    pit = read_json(PIT_PATH)

    require(
        pit["version"] == 1,
        "Unexpected PIT evidence version"
    )

    as_of = date.fromisoformat(
        pit["as_of_date"]
    )

    cutoff = datetime.fromisoformat(
        pit["market_close_et"]
    )

    accepted = datetime.fromisoformat(
        pit["nvda"]["filing_accepted_at_et"]
    )

    require(
        cutoff.tzinfo is not None
        and accepted.tzinfo is not None,
        "Missing filing/cutoff time zone"
    )

    require(
        cutoff.date() == as_of
        and accepted > cutoff,
        "NVDA earnings timing needs review"
    )

    require(
        pit["nvda"]["share_count_review_complete"] is False,
        "Review state unexpectedly changed"
    )

    price_path = (
        RAW / f"market_prices_v04_{as_of}.csv"
    )

    meta = read_json(
        RAW / f"market_prices_v04_{as_of}.meta.json"
    )

    price_hash = hashlib.sha256(
        price_path.read_bytes()
    ).hexdigest()

    require(
        price_hash == meta["csv_sha256"],
        "Price checksum mismatch"
    )

    require(
        meta["price_field_for_future_market_cap"]
        == "Close",
        "Wrong pricing field"
    )

    prices = read_rows(
        price_path
    )

    preview = read_rows(
        REPORTS /
        f"valuation_preview_v04_{as_of}.csv"
    )

    price_row = prices["NVDA"]
    old = preview["NVDA"]

    require(
        price_row["price_date"] == str(as_of)
        and price_row["currency"] == "USD",
        "Unexpected price session or currency"
    )

    require(
        old["valuation_status"] == "BLOCKED"
        and old["source_price_csv_sha256"]
        == price_hash,
        "Historical NVDA preview was modified"
    )

    require(
        old["fiscal_quarter_end"]
        == pit["nvda"][
            "latest_pre_close_quarter_end_in_database"
        ],
        "Financial PIT quarter mismatch"
    )

    source = read_json(
        RAW / "nvda_companyfacts.json"
    )

    require(
        int(source["cik"]) == 1045810,
        "NVDA CIK mismatch"
    )

    share_facts = eligible_share_facts(
        source["facts"],
        as_of
    )

    require(
        share_facts,
        "No eligible pre-close SEC share facts"
    )

    newest = share_facts[0]

    require(
        newest["shares"] == Decimal("24100000000")
        and newest["measurement"] == date(2026, 8, 21),
        "Newer or changed share fact: investigate"
    )

    require(
        newest["filed"] == date(2026, 8, 26),
        "NVDA source filing date changed"
    )

    require(
        newest["tag"]
        == "dei:EntityCommonStockSharesOutstanding",
        "NVDA source share tag changed"
    )

    require(
        dec(old["shares_outstanding"])
        == newest["shares"],
        "Original preview share count mismatch"
    )

    lag = (
        as_of - newest["measurement"]
    ).days

    require(
        lag == 88,
        "Unexpected measurement lag"
    )

    price = dec(
        price_row["close_usd"]
    )

    require(
        price > 0
        and price == dec(old["close_usd"]),
        "Price mismatch"
    )

    cash = dec(old["cash_usd_b"])

    investments = dec(
        old["selected_investments_usd_b"]
    )

    debt = dec(
        old["selected_debt_usd_b"]
    )

    revenue = dec(
        old["ltm_revenue_usd_b"]
    )

    operating = dec(
        old["ltm_operating_income_usd_b"]
    )

    require(
        all(
            value > 0
            for value in (
                cash,
                investments,
                debt,
                revenue,
                operating
            )
        ),
        "Incomplete financial inputs"
    )

    require(
        (cash, investments, debt)
        == (
            Decimal("22.443"),
            Decimal("34.143"),
            Decimal("33.366")
        ),
        "Financial input baseline changed"
    )

    baseline_cap = (
        price * newest["shares"] / BILLION
    )

    require(
        abs(
            baseline_cap
            - dec(
                old["indicative_market_cap_usd_b"]
            )
        ) < Decimal("0.001"),
        "Saved market cap mismatch"
    )

    liquidity_less_debt = (
        cash + investments - debt
    )

    baseline_ev = (
        baseline_cap - liquidity_less_debt
    )

    scenarios = []

    # Hypothetical share-count shocks.
    # These are NOT observed SEC changes.
    for pct in (-2, -1, 0, 1, 2):

        assumed_shares = (
            newest["shares"]
            * (
                Decimal(1)
                + Decimal(pct) / 100
            )
        )

        cap = (
            assumed_shares * price / BILLION
        )

        ev = (
            cap - liquidity_less_debt
        )

        scenarios.append((
            pct,
            cap,
            ev,
            ev / revenue,
            ev / operating
        ))

    rounding_cap_effect = (
        price
        * Decimal("50000000")
        / BILLION
    )

    one_percent_cap_effect = (
        baseline_cap / 100
    )

    report = [
        "# NVDA V0.4.1 — Historical Share-Count Uncertainty",
        "",
        f"**Price as-of:** {as_of} (regular-session close)",
        "**Status:** BLOCKED — sensitivity only",
        "",
        "## Point-in-time evidence",
        "",
        f"- Selected share source: `{newest['tag']}`",
        f"- Measurement date: {newest['measurement']}",
        f"- Filing date: {newest['filed']}",
        f"- Shares disclosed (rounded): {newest['shares']:,.0f}",
        f"- Share-count age: {lag} days",
        "- Same-day Company Facts filings excluded because acceptance times are not supplied.",
        f"- Earnings 8-K acceptance: {accepted.isoformat()} (after regular close)",
        f"- Saved price SHA-256: `{price_hash}`",
        "",
        "## Illustration: valuation sensitivity to outstanding shares",
        "",
        f"- Close: ${price:.6f}",
        f"- Selected liquidity minus borrowings: ${liquidity_less_debt:.3f}B",
        f"- Baseline indicative market cap: ${baseline_cap:.3f}B",
        f"- Baseline *unapproved* EV: ${baseline_ev:.3f}B",
        f"- Hypothetical +/-1% share-count effect on market cap: ${one_percent_cap_effect:.3f}B",
        f"- Hypothetical +/-50 million-share rounding effect: ${rounding_cap_effect:.3f}B",
        "",
        "| Assumed share change | Indicative cap ($B) | Illustrative EV ($B) | EV/Sales | EV/EBIT |",
        "|---:|---:|---:|---:|---:|",
    ]

    for pct, cap, ev, ev_sales, ev_ebit in scenarios:

        report.append(
            f"| {pct:+d}% | {cap:,.3f} | "
            f"{ev:,.3f} | {ev_sales:.2f}x | "
            f"{ev_ebit:.2f}x |"
        )

    report += [
        "",
        "## Restrictions",
        "",
        "- Share scenarios are arbitrary stress tests, not measured repurchases, statistical bounds, or forecasts.",
        "- The cover-page share count is rounded; the exact historical count is not confirmed.",
        "- No newer pre-close share count was established by this offline audit.",
        "- No stock-split history is re-fetched; the prior split audit remains a separate prerequisite.",
        "- No change to the historical V0.4 CSV, rankings, or DuckDB.",
        "- These hypothetical EV ratios must NOT be compared as approved valuation rankings.",
        "",
    ]

    content = "\n".join(report)

    REPORTS.mkdir(
        parents=True,
        exist_ok=True
    )

    target = (
        REPORTS /
        f"nvda_share_uncertainty_v041_{as_of}.md"
    )

    if target.exists():

        require(
            target.read_text(encoding="utf-8")
            == content,
            "Existing NVDA audit differs; refusing overwrite"
        )

        action = "VERIFIED EXISTING"

    else:

        with target.open(
            "x",
            encoding="utf-8"
        ) as handle:
            handle.write(content)

        action = "CREATED"

    print()
    print("NVDA POINT-IN-TIME SHARE AUDIT V0.4.1")
    print("=" * 60)

    print("Price SHA-256: PASS")

    print(
        "Latest eligible share source:",
        newest["tag"]
    )

    print(
        f"Shares: {newest['shares']:,.0f} "
        f"| age: {lag} days"
    )

    print(
        f"Baseline indicative market cap: "
        f"${baseline_cap:,.3f}B"
    )

    print(
        f"Share count +/-1% cap effect: "
        f"${one_percent_cap_effect:,.3f}B"
    )

    print(
        f"Round-to-0.1B hypothetical cap effect: "
        f"+/-${rounding_cap_effect:,.3f}B"
    )

    print("EV and EV multiples: ILLUSTRATIVE ONLY")
    print("NVDA V0.4.1 approval: STILL BLOCKED")
    print("Existing valuation CSV / DuckDB: UNCHANGED")

    print(
        f"Report: {target.relative_to(ROOT)} "
        f"| {action}"
    )

    print("NVDA share uncertainty audit: PASS")


if __name__ == "__main__":
    main()