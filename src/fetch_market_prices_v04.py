
"""
JK's Financial Data Lab — Week 5
Historical Market Price Snapshot V0.4

Fetches historical daily closes for:
    PLTR, NVDA, AMD, MSFT

Uses the as-of date from:
    config/screening_rules_v03.json

Outputs:
    data/raw/market_prices_v04_YYYY-MM-DD.csv
    data/raw/market_prices_v04_YYYY-MM-DD.meta.json

Does NOT modify DuckDB or calculate market cap / EV.
"""

import csv
import hashlib
import json
import math
import os
import tempfile

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

CONFIG = ROOT / "config/screening_rules_v03.json"

OUT_DIR = ROOT / "data/raw"

EXPECTED = (
    "PLTR",
    "NVDA",
    "AMD",
    "MSFT"
)

COLUMNS = (
    "ticker",
    "as_of_date",
    "price_date",
    "close_usd",
    "adjusted_close_usd",
    "volume",
    "currency",
    "provider"
)


def require(condition, message):

    if not condition:
        raise ValueError(message)


def parse_rules():

    rules = json.loads(
        CONFIG.read_text(encoding="utf-8")
    )

    require(
        rules.get("version") == 3,
        "Expected V0.3 policy"
    )

    require(
        set(rules["expected_tickers"])
        == set(EXPECTED),
        "Unexpected tickers"
    )

    as_of = date.fromisoformat(
        rules["as_of_date"]
    )

    require(
        as_of <= datetime.now(timezone.utc).date(),
        "Future as-of date"
    )

    return as_of


def clean_price(value, label):

    require(
        value is not None,
        f"Missing {label}"
    )

    n = float(value)

    require(
        math.isfinite(n) and n > 0,
        f"Invalid {label}: {value}"
    )

    return f"{Decimal(str(n)):.6f}"


def get_quote(yf, ticker, as_of):

    # The yfinance end date is exclusive.
    end = as_of + timedelta(days=1)

    start = as_of - timedelta(days=14)

    instrument = yf.Ticker(ticker)

    prices = instrument.history(
        start=start.isoformat(),
        end=end.isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=True,
        repair=False,
        prepost=False,
        keepna=False
    )

    require(
        prices is not None and not prices.empty,
        f"{ticker}: No historical prices returned"
    )

    metadata = instrument.history_metadata or {}

    currency = metadata.get("currency")

    require(
        currency == "USD",
        (
            f"{ticker}: Unexpected or "
            f"unverified currency: {currency!r}"
        )
    )

    matching = [
        (index.date(), row)
        for index, row in prices.iterrows()
        if index.date() <= as_of
    ]

    require(
        matching,
        f"{ticker}: No trading session by cutoff"
    )

    session, row = max(
        matching,
        key=lambda item: item[0]
    )

    require(
        (as_of - session).days <= 4,
        f"{ticker}: Stale quote for {session}"
    )

    close = clean_price(
        row["Close"],
        f"{ticker} Close"
    )

    adjusted_close = clean_price(
        row["Adj Close"],
        f"{ticker} Adj Close"
    )

    low = float(row["Low"])

    high = float(row["High"])

    require(
        math.isfinite(low)
        and math.isfinite(high)
        and low > 0
        and low <= float(close) <= high,
        f"{ticker}: OHLC consistency failed"
    )

    volume = float(row["Volume"])

    require(
        math.isfinite(volume)
        and volume >= 0
        and volume.is_integer(),
        f"{ticker}: Invalid trading volume"
    )

    return {
        "ticker": ticker,
        "as_of_date": as_of.isoformat(),
        "price_date": session.isoformat(),
        "close_usd": close,
        "adjusted_close_usd": adjusted_close,
        "volume": int(volume),
        "currency": currency,
        "provider": "Yahoo Finance via yfinance"
    }


def main():

    try:
        import yfinance as yf

    except ImportError as exc:

        raise SystemExit(
            "Install dependency: "
            "python -m pip install yfinance"
        ) from exc

    as_of = parse_rules()

    rows = []

    print()
    print("WEEK 5 MARKET PRICE SNAPSHOT")
    print("=" * 65)
    print("As-of:", as_of)

    for ticker in EXPECTED:

        row = get_quote(
            yf,
            ticker,
            as_of
        )

        rows.append(row)

        print(
            f"{ticker}: "
            f"{row['price_date']} "
            f"| ${row['close_usd']} USD "
            f"| volume={row['volume']:,}"
        )

    require(
        len({
            r["ticker"]
            for r in rows
        }) == 4,
        "Duplicate ticker"
    )

    # Compare four companies on the same session.
    require(
        len({
            r["price_date"]
            for r in rows
        }) == 1,
        "Price dates differ across companies"
    )

    OUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    target = (
        OUT_DIR /
        f"market_prices_v04_{as_of.isoformat()}.csv"
    )

    metadata_target = (
        OUT_DIR /
        f"market_prices_v04_{as_of.isoformat()}.meta.json"
    )

    # Preserve immutable price snapshots.
    require(
        not target.exists()
        and not metadata_target.exists(),
        (
            "Snapshot already exists. "
            "Inspect it before replacing."
        )
    )

    retrieved_at = datetime.now(
        timezone.utc
    ).isoformat()

    temp_csv = None
    temp_meta = None

    try:

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=OUT_DIR,
            prefix="market_tmp_",
            suffix=".csv",
            delete=False
        ) as handle:

            temp_csv = Path(handle.name)

            writer = csv.DictWriter(
                handle,
                fieldnames=COLUMNS
            )

            writer.writeheader()
            writer.writerows(rows)

        sha256 = hashlib.sha256(
            temp_csv.read_bytes()
        ).hexdigest()

        metadata = {
            "as_of_date": as_of.isoformat(),
            "price_date": rows[0]["price_date"],
            "retrieved_at_utc": retrieved_at,
            "provider": (
                "Yahoo Finance "
                "(unofficial yfinance access)"
            ),
            "yfinance_version": getattr(
                yf,
                "__version__",
                "unknown"
            ),
            "auto_adjust": False,
            "price_field_for_future_market_cap": "Close",
            "currency": "USD",
            "csv_sha256": sha256,
            "limitations": [
                "Historical Close may be restated for stock splits after the as-of date.",
                "Shares outstanding and corporate actions must be reconciled before market capitalization or EV.",
                "The provider may rate-limit requests or revise historical values.",
                "Verify data reuse and licensing terms before public redistribution."
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=OUT_DIR,
            prefix="market_meta_tmp_",
            suffix=".json",
            delete=False
        ) as handle:

            temp_meta = Path(handle.name)

            json.dump(
                metadata,
                handle,
                indent=2,
                ensure_ascii=False
            )

            handle.write("\n")

        os.replace(
            temp_csv,
            target
        )

        temp_csv = None

        os.replace(
            temp_meta,
            metadata_target
        )

        temp_meta = None

    finally:

        if temp_csv is not None:
            temp_csv.unlink(missing_ok=True)

        if temp_meta is not None:
            temp_meta.unlink(missing_ok=True)

    print()
    print("Snapshot validation: PASS")

    print(
        "CSV:",
        target.relative_to(ROOT)
    )

    print(
        "Metadata:",
        metadata_target.relative_to(ROOT)
    )

    print("SHA-256:", sha256)
    print("DuckDB: UNCHANGED")
    print("Market cap / EV: NOT YET CALCULATED")


if __name__ == "__main__":
    main()