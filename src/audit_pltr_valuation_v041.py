
"""JK's Financial Data Lab - PLTR valuation audit V0.4.1.

SEC note-backed, point-in-time indicative valuation.
Does not alter existing V0.4 outputs or DuckDB.

The SEC 10-Q note values are manually documented.
This program verifies their arithmetic and reconciles
available balance-sheet values with SEC Company Facts.

Requires an online corporate-action recheck via yfinance.
"""

import csv
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb

from audit_market_cap_alignment_v04 import split_audit


ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw"
REPORTS = ROOT / "reports"
DB = ROOT / "data/processed/financial_data.duckdb"

EVIDENCE = ROOT / "config/pltr_valuation_evidence_v041.json"
PIT = ROOT / "config/pit_evidence_v04.json"
BILLION = Decimal("1000000000")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decimal(value):
    result = Decimal(str(value))
    require(result.is_finite(), "Non-finite value")
    return result


def read_json(path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def read_csv(path):
    with path.open(
        newline="",
        encoding="utf-8"
    ) as file:
        return list(csv.DictReader(file))


def sec_instant(facts, tag, quarter_end, cutoff):
    observations = (
        facts.get("us-gaap", {})
        .get(tag, {})
        .get("units", {})
        .get("USD", [])
    )

    candidates = []

    for item in observations:
        if item.get("start") is not None:
            continue

        if item.get("form") not in {
            "10-K", "10-Q", "10-K/A", "10-Q/A"
        }:
            continue

        if not all(
            key in item
            for key in ("end", "filed", "val")
        ):
            continue

        if date.fromisoformat(item["end"]) != quarter_end:
            continue

        if date.fromisoformat(item["filed"]) > cutoff:
            continue

        candidates.append(item)

    require(
        candidates,
        f"SEC balance-sheet fact unavailable: {tag}"
    )

    candidates.sort(
        key=lambda item: (
            item["filed"],
            item.get("accn", "")
        ),
        reverse=True
    )

    chosen = candidates[0]

    same_source = [
        item
        for item in candidates
        if (
            item["filed"],
            item.get("accn", "")
        ) == (
            chosen["filed"],
            chosen.get("accn", "")
        )
    ]

    require(
        len({
            str(decimal(item["val"]))
            for item in same_source
        }) == 1,
        f"Conflicting SEC facts: {tag}"
    )

    return decimal(chosen["val"])


def write_immutable(path, content):
    if path.exists():
        require(
            path.read_text(encoding="utf-8") == content,
            f"Historical artifact changed: {path.name}"
        )
        return "VERIFIED EXISTING"

    with path.open("x", encoding="utf-8") as file:
        file.write(content)

    return "CREATED"


def main():
    evidence = read_json(EVIDENCE)
    pit = read_json(PIT)

    require(
        evidence["version"] == 1
        and evidence["ticker"] == "PLTR",
        "Evidence policy mismatch"
    )

    as_of = date.fromisoformat(
        evidence["as_of_date"]
    )

    quarter_end = date.fromisoformat(
        evidence["fiscal_quarter_end"]
    )

    filed = date.fromisoformat(
        evidence["filing_date"]
    )

    require(
        quarter_end < filed <= as_of,
        "Incorrect point-in-time filing dates"
    )

    require(
        pit["as_of_date"] == as_of.isoformat(),
        "Previous PIT date mismatch"
    )

    require(
        pit["pltr"]["source_url"]
        == evidence["source_url"],
        "SEC source mismatch"
    )

    require(
        evidence["share_classes_economic_rights_reviewed"]
        is True,
        "Share rights not reviewed"
    )

    require(
        evidence["valuation_status"]
        == "INDICATIVE_NOTE_BASED",
        "Unexpected valuation approval status"
    )

    price_file = (
        RAW /
        f"market_prices_v04_{as_of}.csv"
    )

    meta_file = (
        RAW /
        f"market_prices_v04_{as_of}.meta.json"
    )

    old_preview_file = (
        REPORTS /
        f"valuation_preview_v04_{as_of}.csv"
    )

    meta = read_json(meta_file)

    price_hash = hashlib.sha256(
        price_file.read_bytes()
    ).hexdigest()

    require(
        meta["csv_sha256"] == price_hash,
        "Original market price checksum changed"
    )

    prices = read_csv(price_file)
    previews = read_csv(old_preview_file)

    require(
        len(prices) == 4
        and len(previews) == 4,
        "Original snapshots incomplete"
    )

    pltr_price = next(
        row for row in prices
        if row["ticker"] == "PLTR"
    )

    pltr_old = next(
        row for row in previews
        if row["ticker"] == "PLTR"
    )

    require(
        pltr_old["valuation_status"] == "BLOCKED",
        "V0.4 historical status changed"
    )

    require(
        pltr_old["source_price_csv_sha256"]
        == price_hash,
        "V0.4 price provenance mismatch"
    )

    require(
        pltr_price["currency"] == "USD",
        "Non-USD market price"
    )

    price_date = date.fromisoformat(
        pltr_price["price_date"]
    )

    require(
        price_date == as_of,
        "Unexpected trading session"
    )

    price = decimal(
        pltr_price["close_usd"]
    )

    require(
        price > 0,
        "Invalid share price"
    )

    share_evidence = pit["pltr"]

    classes = share_evidence["cover_class_shares"]

    require(
        set(classes) == {
            "class_a", "class_b", "class_f"
        },
        "Missing share class"
    )

    shares = sum(classes.values())

    require(
        shares == 2409497474,
        "PLTR cover-page share count changed"
    )

    share_date = date.fromisoformat(
        share_evidence["cover_share_date"]
    )

    require(
        quarter_end < share_date
        <= filed <= as_of,
        "Share evidence chronology failed"
    )

    split_events = split_audit(
        "PLTR",
        share_date,
        price_date,
        price
    )

    require(
        not split_events,
        "Stock split requires share-count restatement"
    )

    raw_companyfacts = read_json(
        RAW / "pltr_companyfacts.json"
    )

    require(
        int(raw_companyfacts["cik"]) == 1321655,
        "Company Facts CIK mismatch"
    )

    facts = raw_companyfacts["facts"]

    cash = sec_instant(
        facts,
        "CashAndCashEquivalentsAtCarryingValue",
        quarter_end,
        as_of
    )

    marketable = sec_instant(
        facts,
        "MarketableSecuritiesCurrent",
        quarter_end,
        as_of
    )

    require(
        cash == decimal(evidence["cash_usd"]),
        "Cash does not match SEC"
    )

    require(
        marketable == decimal(
            evidence["marketable_securities_total_usd"]
        ),
        "Marketable securities do not match SEC"
    )

    treasury = decimal(
        evidence["us_treasury_securities_usd"]
    )

    equity_securities = decimal(
        evidence["public_equity_securities_usd"]
    )

    treasury_short = decimal(
        evidence["us_treasury_due_within_one_year_usd"]
    )

    require(
        treasury + equity_securities == marketable,
        "SEC note investment bridge failed"
    )

    require(
        0 <= treasury_short <= treasury,
        "Treasury maturity allocation invalid"
    )

    debt = decimal(
        evidence["assumed_financial_borrowings_usd"]
    )

    require(
        debt == 0,
        "Unexpected note-based borrowing assumption"
    )

    require(
        len(evidence["debt_evidence_scope"]) > 20,
        "Debt note scope missing"
    )

    con = duckdb.connect(
        str(DB),
        read_only=True
    )

    try:
        total_quarters = con.execute("""
            SELECT COUNT(*)
            FROM quarterly_metrics_four_reconciled
        """).fetchone()[0]

        require(
            total_quarters == 48,
            "Four-company quarters regression"
        )

        quarter_rows = con.execute("""
            SELECT
                period_end,
                revenue_usd,
                operating_income_usd

            FROM quarterly_metrics_four_reconciled

            WHERE ticker = 'PLTR'

            ORDER BY period_end DESC
        """).fetchall()

        require(
            len(quarter_rows) == 12,
            "PLTR quarter coverage changed"
        )

        require(
            quarter_rows[0][0] == quarter_end,
            "Latest quarter mismatch"
        )

        last_four = quarter_rows[:4]

        ltm_sales = sum(
            (
                decimal(row[1])
                for row in last_four
            ),
            Decimal(0)
        )

        ltm_ebit = sum(
            (
                decimal(row[2])
                for row in last_four
            ),
            Decimal(0)
        )

    finally:
        con.close()

    require(
        ltm_sales > 0 and ltm_ebit > 0,
        "Invalid valuation denominators"
    )

    market_cap = price * shares

    liquid_base = cash + treasury
    liquid_short = cash + treasury_short

    ev_base = market_cap + debt - liquid_base
    ev_short = market_cap + debt - liquid_short

    require(
        ev_base > 0
        and ev_short >= ev_base,
        "Invalid EV sensitivity"
    )

    ev_sales = ev_base / ltm_sales
    ev_ebit = ev_base / ltm_ebit

    output = [
        "# PLTR Valuation V0.4.1 — Evidence Review",
        "",
        f"**As-of:** {as_of}",
        "",
        "**Status:** INDICATIVE_NOTE_BASED",
        "",
        f"**SEC 10-Q:** {evidence['source_url']}",
        "",
        "## Validated and note-derived inputs",
        "",
        f"- Cover-page shares: {shares:,}",
        f"- Share measurement date: {share_date}",
        f"- Share-price date: {price_date}",
        f"- Share-date lag: {(price_date - share_date).days} days",
        f"- Close: ${price:.6f}",
        f"- Cash: ${cash / BILLION:.6f}B",
        f"- Marketable securities: ${marketable / BILLION:.6f}B",
        f"- U.S. Treasury securities: ${treasury / BILLION:.6f}B",
        f"- Public equity securities excluded: ${equity_securities / BILLION:.6f}B",
        f"- Financial borrowing assumption: ${debt / BILLION:.6f}B",
        "",
        "## Indicative scenarios",
        "",
        f"- Market cap: ${market_cap / BILLION:.3f}B",
        f"- Base EV (cash + all Treasuries): ${ev_base / BILLION:.3f}B",
        f"- Short-maturity Treasury EV: ${ev_short / BILLION:.3f}B",
        f"- LTM revenue: ${ltm_sales / BILLION:.3f}B",
        f"- LTM operating income: ${ltm_ebit / BILLION:.3f}B",
        f"- Base EV/Sales: {ev_sales:.2f}x",
        f"- Base EV/EBIT: {ev_ebit:.2f}x",
        "",
        "## Limitations",
        "",
        "- SEC note detail is manually recorded evidence.",
        "- No automatic verification of SEC webpage text.",
        "- Borrowing zero reflects a filing-based assumption.",
        "- Operating and finance lease adjustments are excluded.",
        "- Market capitalization remains indicative.",
        "- Historical V0.4 valuation output is preserved.",
        "- NVIDIA remains BLOCKED.",
        ""
    ]

    REPORTS.mkdir(
        parents=True,
        exist_ok=True
    )

    target = (
        REPORTS /
        f"pltr_valuation_review_v041_{as_of}.md"
    )

    status = write_immutable(
        target,
        "\n".join(output)
    )

    print()
    print("PLTR VALUATION EVIDENCE AUDIT V0.4.1")
    print("=" * 65)

    print("Price SHA-256: PASS")
    print("Share-class evidence: PASS")
    print("Split check: PASS")
    print("Cash XBRL: PASS")
    print("Marketable securities XBRL: PASS")
    print("SEC note component reconciliation: PASS")
    print("LTM data: PASS")

    print()
    print(f"Market cap: ${market_cap / BILLION:,.3f}B")
    print(f"Base indicative EV: ${ev_base / BILLION:,.3f}B")
    print(f"Short-maturity EV: ${ev_short / BILLION:,.3f}B")

    print(f"EV/Sales: {ev_sales:.2f}x")
    print(f"EV/EBIT: {ev_ebit:.2f}x")

    print()
    print("PLTR valuation: INDICATIVE_NOTE_BASED")
    print("NVDA valuation: STILL BLOCKED")
    print("Original V0.4 CSV: PRESERVED")
    print("DuckDB: READ ONLY")

    print(
        "Report:",
        target.relative_to(ROOT),
        status
    )

    print("PLTR V0.4.1 audit: PASS")


if __name__ == "__main__":
    main()