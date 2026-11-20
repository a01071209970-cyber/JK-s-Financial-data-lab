
"""
JK's Financial Data Lab - Week 5
Market-price / SEC-share alignment audit (V0.4).

Inputs:
  config/screening_rules_v03.json
  data/raw/market_prices_v04_YYYY-MM-DD.csv
  data/raw/market_prices_v04_YYYY-MM-DD.meta.json
  data/raw/{ticker}_companyfacts.json
  data/processed/financial_data.duckdb

Output:
  Console audit only.
  No DuckDB or file modification.

Run:
  python src/audit_market_cap_alignment_v04.py

Requires:
  duckdb
  yfinance
"""

import csv
import hashlib
import json

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import yfinance as yf


ROOT = Path(__file__).resolve().parent.parent

RULES = ROOT / "config/screening_rules_v03.json"
RAW = ROOT / "data/raw"
DB = ROOT / "data/processed/financial_data.duckdb"

TICKERS = ("PLTR", "NVDA", "AMD", "MSFT")

VALID_FORMS = {
    "10-Q",
    "10-Q/A",
    "10-K",
    "10-K/A"
}

BILLION = Decimal("1000000000")


def require(condition, message):

    if not condition:
        raise ValueError(message)


def as_date(value):

    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value))


def number(value):

    result = Decimal(str(value))

    require(
        result.is_finite(),
        f"Non-finite numeric value: {value}"
    )

    return result


def load_snapshot():

    rules = json.loads(
        RULES.read_text(encoding="utf-8")
    )

    require(
        rules["version"] == 3,
        "Unexpected screener version"
    )

    require(
        set(rules["expected_tickers"]) == set(TICKERS),
        "Universe mismatch"
    )

    cutoff = as_date(rules["as_of_date"])

    csv_path = (
        RAW / f"market_prices_v04_{cutoff}.csv"
    )

    meta_path = (
        RAW / f"market_prices_v04_{cutoff}.meta.json"
    )

    require(
        csv_path.exists() and meta_path.exists(),
        "Price snapshot missing"
    )

    raw_csv = csv_path.read_bytes()

    meta = json.loads(
        meta_path.read_text(encoding="utf-8")
    )

    actual_hash = hashlib.sha256(
        raw_csv
    ).hexdigest()

    require(
        actual_hash == meta["csv_sha256"],
        "Price CSV checksum mismatch"
    )

    require(
        meta["as_of_date"] == str(cutoff),
        "Metadata cutoff mismatch"
    )

    require(
        meta["price_field_for_future_market_cap"] == "Close",
        "Close policy mismatch"
    )

    with csv_path.open(
        encoding="utf-8",
        newline=""
    ) as file:

        rows = list(
            csv.DictReader(file)
        )

    require(
        len(rows) == 4,
        "Expected four quotes"
    )

    quote_map = {}

    for row in rows:

        ticker = row["ticker"]

        require(
            ticker in TICKERS
            and ticker not in quote_map,
            "Unexpected or duplicate ticker"
        )

        require(
            row["as_of_date"] == str(cutoff),
            f"{ticker}: As-of mismatch"
        )

        require(
            row["currency"] == "USD",
            f"{ticker}: Non-USD quote"
        )

        require(
            row["provider"] == "Yahoo Finance via yfinance",
            f"{ticker}: Provider mismatch"
        )

        price_date = as_date(
            row["price_date"]
        )

        require(
            price_date <= cutoff,
            f"{ticker}: Future quote"
        )

        require(
            (cutoff - price_date).days <= 4,
            f"{ticker}: Stale quote"
        )

        close = number(
            row["close_usd"]
        )

        adjusted_close = number(
            row["adjusted_close_usd"]
        )

        volume = int(
            row["volume"]
        )

        require(
            close > 0
            and adjusted_close > 0
            and volume > 0,
            f"{ticker}: Bad quote"
        )

        quote_map[ticker] = {
            "close": close,
            "date": price_date,
            "adj_close": adjusted_close
        }

    require(
        set(quote_map) == set(TICKERS),
        "Missing quote"
    )

    require(
        len({
            row["date"]
            for row in quote_map.values()
        }) == 1,
        "Different trade dates"
    )

    return (
        cutoff,
        quote_map,
        actual_hash,
        meta
    )


def latest_periods(cutoff):

    require(
        DB.exists(),
        f"Database missing: {DB}"
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
            "SEC fact count regression"
        )

        rows = con.execute("""
            SELECT
                ticker,
                period_end

            FROM quarterly_metrics_four_reconciled

            ORDER BY ticker, period_end
        """).fetchall()

        require(
            len(rows) == 48,
            "Expected 48 quarters"
        )

        latest = {}

        counts = {
            ticker: 0
            for ticker in TICKERS
        }

        for ticker, period_end in rows:

            require(
                ticker in counts,
                "Unexpected ticker in DuckDB"
            )

            counts[ticker] += 1

            latest[ticker] = as_date(
                period_end
            )

        require(
            all(
                value == 12
                for value in counts.values()
            ),
            "Quarter history mismatch"
        )

        require(
            all(
                day <= cutoff
                for day in latest.values()
            ),
            "Future fiscal period"
        )

        return latest

    finally:

        con.close()


def select_share_fact(
    company_facts,
    taxonomy,
    tag,
    quarter_end,
    cutoff
):

    entries = (
        company_facts["facts"]
        .get(taxonomy, {})
        .get(tag, {})
        .get("units", {})
        .get("shares", [])
    )

    candidates = []

    for item in entries:

        if item.get("start") is not None:
            continue

        if item.get("form") not in VALID_FORMS:
            continue

        if not all(
            key in item
            for key in ("end", "filed", "val")
        ):
            continue

        observed = as_date(
            item["end"]
        )

        filed = as_date(
            item["filed"]
        )

        if (
            filed > cutoff
            or observed > cutoff
            or observed > filed
        ):
            continue

        if taxonomy == "dei":

            if observed < quarter_end:
                continue

        else:

            if observed != quarter_end:
                continue

        candidates.append(item)

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            x["end"],
            x["filed"],
            x.get("accn", "")
        ),
        reverse=True
    )

    chosen = candidates[0]

    same_filing = [
        item
        for item in candidates
        if (
            item["end"],
            item["filed"],
            item.get("accn", "")
        ) == (
            chosen["end"],
            chosen["filed"],
            chosen.get("accn", "")
        )
    ]

    values = {
        str(number(item["val"]))
        for item in same_filing
    }

    require(
        len(values) == 1,
        f"Conflicting {taxonomy}:{tag} observations"
    )

    shares = number(
        chosen["val"]
    )

    require(
        shares > 0
        and shares == shares.to_integral_value(),
        "Invalid outstanding shares"
    )

    return {
        "shares": shares,
        "date": as_date(chosen["end"]),
        "filed": as_date(chosen["filed"]),
        "tag": f"{taxonomy}:{tag}"
    }


def read_shares(
    ticker,
    quarter_end,
    cutoff
):

    config = json.loads(
        (
            ROOT / "config/companies.json"
        ).read_text(encoding="utf-8")
    )

    company = next(
        item
        for item in config["companies"]
        if item["ticker"] == ticker
    )

    path = (
        RAW /
        f"{ticker.lower()}_companyfacts.json"
    )

    company_facts = json.loads(
        path.read_text(encoding="utf-8")
    )

    require(
        int(company_facts["cik"])
        == int(company["cik"]),
        f"{ticker}: CIK mismatch"
    )

    dei = select_share_fact(
        company_facts,
        "dei",
        "EntityCommonStockSharesOutstanding",
        quarter_end,
        cutoff
    )

    gaap = select_share_fact(
        company_facts,
        "us-gaap",
        "CommonStockSharesOutstanding",
        quarter_end,
        cutoff
    )

    # Prefer the more recent SEC cover-page
    # count when one is available.
    chosen = dei or gaap

    require(
        chosen is not None,
        f"{ticker}: No usable share count"
    )

    return chosen, dei, gaap


def split_audit(
    ticker,
    measurement_date,
    price_date,
    snap_close
):

    history = yf.Ticker(ticker).history(
        start=(
            measurement_date
            - timedelta(days=7)
        ).isoformat(),
        end=(
            price_date
            + timedelta(days=1)
        ).isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=True,
        repair=False,
        prepost=False,
        keepna=False
    )

    require(
        history is not None
        and not history.empty,
        f"{ticker}: Split history unavailable"
    )

    require(
        "Stock Splits" in history.columns
        and "Close" in history.columns,
        f"{ticker}: Corporate-action field missing"
    )

    events = []

    matched_close = None

    for index, row in history.iterrows():

        session = as_date(
            index.date()
        )

        if session == price_date:

            matched_close = number(
                row["Close"]
            )

        ratio = row["Stock Splits"]

        if (
            ratio is not None
            and ratio == ratio
            and number(ratio) > 0
        ):

            if (
                measurement_date
                < session
                <= price_date
            ):

                events.append((
                    session,
                    number(ratio)
                ))

    require(
        matched_close is not None,
        f"{ticker}: Snapshot session not in history"
    )

    require(
        abs(matched_close - snap_close)
        <= Decimal("0.01"),
        (
            f"{ticker}: Price discrepancy "
            "between snapshot and split audit"
        )
    )

    return events


def main():

    cutoff, quotes, checksum, metadata = (
        load_snapshot()
    )

    quarters = latest_periods(
        cutoff
    )

    print()
    print("WEEK 5 SHARE / PRICE ALIGNMENT AUDIT")
    print("=" * 66)

    print("As-of:", cutoff)

    print(
        "Price CSV SHA-256: VERIFIED",
        checksum
    )

    print(
        "Quote retrieval timestamp:",
        metadata.get("retrieved_at_utc")
    )

    print(
        "Share source:",
        "SEC point-in-time Company Facts"
    )

    print(
        "Split source:",
        "Yahoo Finance corporate actions (re-fetched)"
    )

    print("=" * 66)

    results = []

    for ticker in TICKERS:

        quote = quotes[ticker]

        chosen, dei, gaap = read_shares(
            ticker,
            quarters[ticker],
            cutoff
        )

        age = (
            quote["date"]
            - chosen["date"]
        ).days

        require(
            age >= 0,
            f"{ticker}: Shares measured after quote"
        )

        split_events = split_audit(
            ticker,
            chosen["date"],
            quote["date"],
            quote["close"]
        )

        flags = []

        if split_events:

            flags.append(
                "SPLIT_BETWEEN_SHARE_DATE_AND_PRICE"
            )

        if age > 45:

            flags.append(
                "SHARES_STALE_OVER_45_DAYS"
            )

        if ticker == "PLTR":

            flags.append(
                "SHARE_CLASS_COVERAGE_REVIEW"
            )

        # No split-adjustment assumptions.
        # Block the market-cap estimate if
        # a split occurred after share count.
        cap = (
            None
            if split_events
            else (
                quote["close"]
                * chosen["shares"]
                / BILLION
            )
        )

        print()
        print(
            f"{ticker} "
            f"| trade date {quote['date']} "
            f"| Close ${quote['close']:.2f}"
        )

        print(
            f"  Shares: {chosen['shares']:,.0f}"
            f" | {chosen['date']}"
            f" | {chosen['tag']}"
        )

        print(
            f"  Share-date lag: {age} days"
            f" | filed {chosen['filed']}"
        )

        print(
            "  SEC GAAP quarter-end shares available:",
            "YES" if gaap else "NO"
        )

        print(
            "  SEC DEI cover-page shares available:",
            "YES" if dei else "NO"
        )

        if split_events:

            split_description = ", ".join(
                f"{day} ({ratio}:1)"
                for day, ratio in split_events
            )

        else:

            split_description = "NONE FOUND"

        print(
            "  Stock split events:",
            split_description
        )

        print(
            "  Indicative market cap:",
            (
                "BLOCKED"
                if cap is None
                else f"${cap:,.3f}B"
            )
        )

        print(
            "  Review flags:",
            (
                ", ".join(flags)
                if flags
                else "NONE (STILL INDICATIVE)"
            )
        )

        results.append((
            ticker,
            cap,
            flags
        ))

    print()
    print("AUDIT SUMMARY")
    print("=" * 66)

    print(
        "Companies audited:",
        len(results)
    )

    print(
        "Companies requiring review:",
        sum(
            bool(item[2])
            for item in results
        )
    )

    print(
        "Point-in-time market caps:",
        "NOT CERTIFIED"
    )

    print(
        "Enterprise value / valuation ratios:",
        "NOT CALCULATED"
    )

    print("DuckDB: READ ONLY")

    print(
        "Share / price alignment audit: COMPLETE"
    )


if __name__ == "__main__":
    main()