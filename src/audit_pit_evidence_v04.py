
"""
JK's Financial Data Lab - Week 5
Point-in-Time Evidence Audit V0.4

Verifies:
- Existing price snapshot checksum
- PLTR class-share arithmetic
- PLTR quarter-end SEC XBRL share count
- Revised PLTR indicative market capitalization
- NVIDIA post-market-close SEC filing time
- Existing valuation BLOCKED decisions

Creates an immutable Markdown audit report.

SEC note evidence is manually recorded in JSON.
This program does not remotely authenticate that text.
No DuckDB modification and no market-price download.
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

EVIDENCE = ROOT / "config/pit_evidence_v04.json"

BILLION = Decimal("1000000000")


def require(condition, message):

    if not condition:
        raise ValueError(message)


def read_json(path):

    return json.loads(
        path.read_text(encoding="utf-8")
    )


def read_csv(path):

    with path.open(
        encoding="utf-8",
        newline=""
    ) as handle:

        rows = list(
            csv.DictReader(handle)
        )

    require(
        len(rows) == 4,
        f"Expected four rows in {path.name}"
    )

    result = {}

    for row in rows:

        ticker = row["ticker"]

        require(
            ticker not in result,
            f"Duplicate ticker: {ticker}"
        )

        result[ticker] = row

    require(
        set(result) == {
            "PLTR", "NVDA", "AMD", "MSFT"
        },
        "Unexpected ticker universe"
    )

    return result


def as_decimal(value):

    result = Decimal(str(value))

    require(
        result.is_finite(),
        "Non-finite numeric input"
    )

    return result


def class_total(classes):

    require(
        set(classes) == {
            "class_a",
            "class_b",
            "class_f"
        },
        "Incomplete PLTR share classes"
    )

    values = list(classes.values())

    require(
        all(
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
            for value in values
        ),
        "Invalid share-class count"
    )

    return sum(values)


def verify_pltr_xbrl(
    quarter_end,
    cutoff,
    expected
):

    source = RAW / "pltr_companyfacts.json"

    require(
        source.exists(),
        "PLTR SEC Company Facts missing"
    )

    data = read_json(source)

    require(
        int(data["cik"]) == 1321655,
        "PLTR CIK mismatch"
    )

    records = (
        data["facts"]["us-gaap"]
        ["CommonStockSharesOutstanding"]
        ["units"]["shares"]
    )

    candidates = []

    for fact in records:

        if fact.get("start") is not None:
            continue

        if fact.get("form") not in {
            "10-Q", "10-Q/A", "10-K", "10-K/A"
        }:
            continue

        if (
            fact.get("end") == quarter_end.isoformat()
            and fact.get("filed")
            and date.fromisoformat(
                fact["filed"]
            ) <= cutoff
        ):
            candidates.append(fact)

    require(
        candidates,
        "PLTR quarter-end share fact missing"
    )

    candidates.sort(
        key=lambda item: (
            item["filed"],
            item.get("accn", "")
        ),
        reverse=True
    )

    chosen = candidates[0]

    require(
        int(chosen["val"]) == expected,
        "PLTR quarter-end XBRL changed"
    )

    return int(chosen["val"])


def main():

    evidence = read_json(EVIDENCE)

    require(
        evidence["version"] == 1,
        "Unexpected evidence version"
    )

    as_of = date.fromisoformat(
        evidence["as_of_date"]
    )

    cutoff = datetime.fromisoformat(
        evidence["market_close_et"]
    )

    require(
        cutoff.tzinfo is not None
        and cutoff.date() == as_of
        and cutoff.hour == 16
        and cutoff.minute == 0,
        "Invalid market-close cutoff"
    )

    prices_path = (
        RAW /
        f"market_prices_v04_{as_of}.csv"
    )

    meta_path = (
        RAW /
        f"market_prices_v04_{as_of}.meta.json"
    )

    preview_path = (
        REPORTS /
        f"valuation_preview_v04_{as_of}.csv"
    )

    require(
        all(
            path.exists()
            for path in (
                prices_path,
                meta_path,
                preview_path
            )
        ),
        "Existing snapshot/report missing"
    )

    metadata = read_json(meta_path)

    price_hash = hashlib.sha256(
        prices_path.read_bytes()
    ).hexdigest()

    require(
        price_hash == metadata["csv_sha256"],
        "Price snapshot SHA mismatch"
    )

    prices = read_csv(prices_path)

    preview = read_csv(preview_path)

    for ticker in prices:

        require(
            prices[ticker]["as_of_date"]
            == as_of.isoformat(),
            f"{ticker}: Price as-of mismatch"
        )

        require(
            preview[ticker]["as_of_date"]
            == as_of.isoformat(),
            f"{ticker}: Valuation as-of mismatch"
        )

        require(
            preview[ticker]["source_price_csv_sha256"]
            == price_hash,
            f"{ticker}: Source checksum mismatch"
        )

    # --------------------------------------
    # PLTR share-class evidence
    # --------------------------------------

    pltr = evidence["pltr"]

    filing_date = date.fromisoformat(
        pltr["filing_date"]
    )

    quarter_end = date.fromisoformat(
        pltr["quarter_end"]
    )

    cover_date = date.fromisoformat(
        pltr["cover_share_date"]
    )

    require(
        quarter_end < cover_date
        <= filing_date <= as_of,
        "PLTR share/filing dates inconsistent"
    )

    old_total_exact = class_total(
        pltr["quarter_end_class_shares"]
    )

    new_total = class_total(
        pltr["cover_class_shares"]
    )

    require(
        old_total_exact == 2409153214,
        "PLTR quarter-end class total changed"
    )

    require(
        new_total == 2409497474,
        "PLTR cover-page class total changed"
    )

    xbrl_total = verify_pltr_xbrl(
        quarter_end,
        as_of,
        2409153000
    )

    # The existing GAAP total is reported
    # at thousand-share precision.
    require(
        abs(old_total_exact - xbrl_total) <= 500,
        "PLTR share classes do not reconcile"
    )

    pltr_quote = prices["PLTR"]

    pltr_preview = preview["PLTR"]

    require(
        pltr_preview["valuation_status"]
        == "BLOCKED",
        "PLTR previous BLOCKED state changed"
    )

    require(
        pltr["total_borrowings_approved"] is False
        and pltr["economic_rights_review_complete"]
        is False,
        "PLTR risk-approval policy changed"
    )

    trade_date = date.fromisoformat(
        pltr_quote["price_date"]
    )

    require(
        trade_date == as_of,
        "PLTR quote date mismatch"
    )

    old_shares = int(
        pltr_preview["shares_outstanding"]
    )

    require(
        old_shares == xbrl_total,
        "PLTR previous shares mismatch"
    )

    close = as_decimal(
        pltr_quote["close_usd"]
    )

    old_cap = (
        close * old_shares / BILLION
    )

    new_cap = (
        close * new_total / BILLION
    )

    saved_old_cap = as_decimal(
        pltr_preview["indicative_market_cap_usd_b"]
    )

    require(
        abs(old_cap - saved_old_cap)
        < Decimal("0.001"),
        "PLTR saved capitalization mismatch"
    )

    old_lag = (
        trade_date - quarter_end
    ).days

    new_lag = (
        trade_date - cover_date
    ).days

    require(
        old_lag == 48
        and new_lag == 22,
        "PLTR share-date lag mismatch"
    )

    # --------------------------------------
    # NVIDIA post-close filing
    # --------------------------------------

    nvda = evidence["nvda"]

    accepted = datetime.fromisoformat(
        nvda["filing_accepted_at_et"]
    )

    require(
        accepted.tzinfo is not None,
        "NVDA filing timestamp missing offset"
    )

    require(
        accepted > cutoff,
        "NVDA filing unexpectedly pre-close"
    )

    require(
        nvda["filing_type"] == "8-K",
        "Unexpected NVIDIA filing type"
    )

    require(
        nvda["share_count_review_complete"]
        is False,
        "NVIDIA share review state changed"
    )

    require(
        preview["NVDA"]["valuation_status"]
        == "BLOCKED",
        "NVDA previous BLOCKED state changed"
    )

    require(
        preview["NVDA"]["fiscal_quarter_end"]
        == nvda[
            "latest_pre_close_quarter_end_in_database"
        ],
        "NVIDIA historical quarter mismatch"
    )

    delay = int(
        (accepted - cutoff).total_seconds()
    )

    require(
        delay > 0,
        "NVDA filing timing not after close"
    )

    # --------------------------------------
    # Write an immutable audit record
    # --------------------------------------

    report = [
        "# Week 5 — Point-in-Time Evidence Review",
        "",
        f"**Valuation date:** {as_of}",
        "",
        "**Market cutoff:** 16:00 US Eastern",
        "",
        "**Price snapshot SHA-256:** "
        + price_hash,
        "",
        "## PLTR share coverage",
        "",
        f"- Quarter-end class total: {old_total_exact:,}",
        f"- SEC GAAP XBRL total: {xbrl_total:,}",
        "- Quarter-end rounding reconciliation: PASS",
        f"- Cover-page share date: {cover_date}",
        f"- Cover-page class A: "
        f"{pltr['cover_class_shares']['class_a']:,}",
        f"- Cover-page class B: "
        f"{pltr['cover_class_shares']['class_b']:,}",
        f"- Cover-page class F: "
        f"{pltr['cover_class_shares']['class_f']:,}",
        f"- Cover-page class total: {new_total:,}",
        f"- Original share lag: {old_lag} days",
        f"- Revised share lag: {new_lag} days",
        f"- Old indicative market cap: ${old_cap:,.3f}B",
        f"- Updated indicative market cap: ${new_cap:,.3f}B",
        "",
        "**EV status: BLOCKED.** Total borrowing coverage "
        "and share-class economic rights are not yet approved.",
        "",
        f"Source: {pltr['source_url']}",
        "",
        "## NVDA earnings filing cutoff",
        "",
        f"- Regular-session price cutoff: {cutoff.isoformat()}",
        f"- SEC 8-K acceptance: {accepted.isoformat()}",
        f"- Post-close delay: {delay} seconds",
        "- New 8-K data must not be mixed into "
        "the same day's closing-price valuation.",
        "- Existing FY2027 Q2 financial input remains unchanged.",
        "",
        "**EV status: BLOCKED.** Share-count freshness "
        "has not been approved.",
        "",
        f"Source: {nvda['source_url']}",
        "",
        "## Audit limitations",
        "",
        "- SEC URLs and note details are manually reviewed evidence.",
        "- This script validates local XBRL, arithmetic, dates, "
        "and snapshot provenance; it does not fetch filing text.",
        "- The historical price and corporate-action data "
        "remain subject to provider revision.",
        "- No historical report or database table was changed.",
        "- No new enterprise value was approved.",
        "",
    ]

    content = "\n".join(report)

    target = (
        REPORTS /
        f"pit_alignment_review_v04_{as_of}.md"
    )

    if target.exists():

        require(
            target.read_text(encoding="utf-8")
            == content,
            "Existing evidence report differs"
        )

        result = "VERIFIED EXISTING"

    else:

        with target.open(
            "x",
            encoding="utf-8"
        ) as handle:

            handle.write(content)

        result = "CREATED"

    print()
    print("WEEK 5 POINT-IN-TIME EVIDENCE AUDIT")
    print("=" * 65)

    print("Price checksum: PASS")
    print("PLTR quarter-end share reconciliation: PASS")

    print(
        "PLTR latest cover-page shares:",
        f"{new_total:,}"
    )

    print(
        "PLTR share lag:",
        f"{old_lag} -> {new_lag} days"
    )

    print(
        "PLTR revised indicative market cap:",
        f"${new_cap:,.3f}B"
    )

    print("PLTR EV: STILL BLOCKED")

    print(
        "NVDA SEC filing after close:",
        f"{delay // 60}m {delay % 60}s"
    )

    print("NVDA EV: STILL BLOCKED")

    print(
        "Evidence report:",
        target.relative_to(ROOT),
        result
    )

    print("Original V0.4 CSV: PRESERVED")
    print("DuckDB: UNCHANGED")
    print("PIT evidence audit: PASS")


if __name__ == "__main__":
    main()