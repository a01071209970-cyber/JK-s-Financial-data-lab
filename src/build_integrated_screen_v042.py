
"""JK's Financial Data Lab - Integrated Screen V0.4.2.

Offline aggregation of previously audited V0.3, V0.4 and
V0.4.1 artifacts.

All valuation statuses are preserved. No valuation ranking
is produced across differently scoped EV definitions.

Writes two immutable reports. DuckDB is read-only.
"""

import csv
import hashlib
import io
import json

from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parent.parent

RAW = ROOT / "data/raw"
REPORTS = ROOT / "reports"
CONFIG = ROOT / "config"

DB = ROOT / "data/processed/financial_data.duckdb"

B = Decimal("1000000000")

TICKERS = ("NVDA", "PLTR", "AMD", "MSFT")

COLUMNS = [
    "fundamental_rank",
    "ticker",
    "as_of_date",
    "fundamental_status",
    "quarter_revenue_yoy_pct",
    "operating_margin_pct",
    "ltm_revenue_yoy_pct",
    "valuation_status",
    "share_age_days",
    "indicative_market_cap_usd_b",
    "indicative_ev_usd_b",
    "ev_sales",
    "ev_ebit",
    "valuation_basis",
    "review_flags",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    require(
        path.exists(),
        f"Missing input: {path}"
    )

    return json.loads(
        path.read_text(encoding="utf-8")
    )


def indexed_csv(path):
    require(
        path.exists(),
        f"Missing input: {path}"
    )

    with path.open(
        encoding="utf-8",
        newline=""
    ) as stream:
        records = list(csv.DictReader(stream))

    require(
        len(records) == 4,
        f"Expected four rows: {path.name}"
    )

    keyed = {
        row["ticker"]: row
        for row in records
    }

    require(
        set(keyed) == set(TICKERS),
        f"Universe mismatch: {path.name}"
    )

    return keyed


def decimal(value):
    result = Decimal(str(value))

    require(
        result.is_finite(),
        "Non-finite input"
    )

    return result


def billions(amount):
    return f"{amount / B:.3f}"


def ratio(amount, denominator):
    require(
        denominator > 0,
        "Invalid valuation denominator"
    )

    return f"{amount / denominator:.2f}"


def write_immutable(path, content):
    if path.exists():
        require(
            path.read_bytes() == content,
            (
                "Refusing to replace existing report: "
                f"{path.name}"
            )
        )

        return "VERIFIED EXISTING"

    with path.open("xb") as stream:
        stream.write(content)

    return "CREATED"


def read_ltm(as_of):
    require(
        DB.exists(),
        "DuckDB missing"
    )

    con = duckdb.connect(
        str(DB),
        read_only=True
    )

    try:
        observation_count = con.execute(
            "SELECT COUNT(*) FROM financial_facts_multi"
        ).fetchone()[0]

        require(
            observation_count == 92717,
            "Raw fact count regression"
        )

        rows = con.execute("""
            SELECT
                ticker,
                period_end,
                revenue_usd,
                operating_income_usd
            FROM quarterly_metrics_four_reconciled
            ORDER BY ticker, period_end
        """).fetchall()

    finally:
        con.close()

    require(
        len(rows) == 48,
        "Expected 48 quarters"
    )

    groups = defaultdict(list)

    for ticker, period_end, revenue, operating in rows:
        require(
            ticker in TICKERS,
            f"Unknown ticker {ticker}"
        )

        require(
            period_end <= as_of,
            f"Future financial quarter {ticker}"
        )

        groups[ticker].append((
            period_end,
            decimal(revenue),
            decimal(operating)
        ))

    require(
        set(groups) == set(TICKERS),
        "Quarter universe mismatch"
    )

    result = {}

    for ticker, items in groups.items():
        require(
            len(items) == 12,
            f"Expected 12 quarters for {ticker}"
        )

        last_four = items[-4:]

        result[ticker] = {
            "period_end": items[-1][0],
            "revenue": sum(
                (r[1] for r in last_four),
                Decimal(0)
            ),
            "operating": sum(
                (r[2] for r in last_four),
                Decimal(0)
            )
        }

        require(
            (
                result[ticker]["revenue"] > 0
                and result[ticker]["operating"] > 0
            ),
            f"Invalid LTM financials for {ticker}"
        )

    return result


def main():
    rules = read_json(
        CONFIG / "screening_rules_v03.json"
    )

    as_of = date.fromisoformat(
        rules["as_of_date"]
    )

    require(
        rules["version"] == 3,
        "Unexpected screening rules"
    )

    require(
        set(rules["expected_tickers"]) == set(TICKERS),
        "Rule universe mismatch"
    )

    policy = read_json(
        CONFIG / "valuation_input_policy.json"
    )

    pit = read_json(
        CONFIG / "pit_evidence_v04.json"
    )

    pltr_note = read_json(
        CONFIG / "pltr_valuation_evidence_v041.json"
    )

    require(
        policy["as_of_date"] == str(as_of),
        "Valuation cutoff mismatch"
    )

    require(
        pit["as_of_date"] == str(as_of),
        "PIT cutoff mismatch"
    )

    require(
        pltr_note["as_of_date"] == str(as_of),
        "PLTR note cutoff mismatch"
    )

    screen = indexed_csv(
        REPORTS / f"screen_v03_{as_of}.csv"
    )

    preview = indexed_csv(
        REPORTS / f"valuation_preview_v04_{as_of}.csv"
    )

    quote_path = (
        RAW / f"market_prices_v04_{as_of}.csv"
    )

    quote = indexed_csv(quote_path)

    meta = read_json(
        RAW / f"market_prices_v04_{as_of}.meta.json"
    )

    require(
        hashlib.sha256(
            quote_path.read_bytes()
        ).hexdigest() == meta["csv_sha256"],
        "Market price checksum mismatch"
    )

    require(
        meta["price_field_for_future_market_cap"]
        == "Close",
        "Pricing policy changed"
    )

    require(
        meta["as_of_date"] == str(as_of),
        "Price metadata date mismatch"
    )

    pltr_audit = (
        REPORTS /
        f"pltr_valuation_review_v041_{as_of}.md"
    ).read_text(encoding="utf-8")

    nvda_audit = (
        REPORTS /
        f"nvda_share_uncertainty_v041_{as_of}.md"
    ).read_text(encoding="utf-8")

    require(
        "**Status:** INDICATIVE_NOTE_BASED" in pltr_audit,
        "PLTR audit not approved as indicative"
    )

    require(
        "**Status:** BLOCKED" in nvda_audit,
        "NVDA audit must remain blocked"
    )

    financials = read_ltm(as_of)

    output = []

    lines = [
        "# JK's Financial Data Lab — Integrated Screen V0.4.2",
        "",
        f"**As-of:** {as_of} (US regular-session close)",
        "**Scope:** PLTR, NVDA, AMD, MSFT",
        "**Purpose:** Combine audited fundamental results with guarded valuation",
        "",
        "## Fundamental and valuation overview",
        "",
        "| Fundamental rank | Ticker | Revenue YoY | Operating margin | Fundamental | EV/Sales | EV/EBIT | Valuation state |",
        "|---:|---|---:|---:|---|---:|---:|---|",
    ]

    expected_screen = {
        "PLTR": "PASS",
        "NVDA": "PASS",
        "AMD": "PASS",
        "MSFT": "FAIL"
    }

    expected_preview = {
        "PLTR": "BLOCKED",
        "NVDA": "BLOCKED",
        "AMD": "INDICATIVE",
        "MSFT": "INDICATIVE"
    }

    for rank, ticker in enumerate(TICKERS, 1):
        s = screen[ticker]
        v = preview[ticker]
        q = quote[ticker]

        require(
            s["fundamental_status"]
            == expected_screen[ticker],
            f"{ticker} fundamental status changed"
        )

        require(
            v["valuation_status"]
            == expected_preview[ticker],
            f"{ticker} V0.4 status changed"
        )

        require(
            v["source_price_csv_sha256"]
            == meta["csv_sha256"],
            f"{ticker} checksum provenance mismatch"
        )

        require(
            (
                q["price_date"] == str(as_of)
                and q["currency"] == "USD"
            ),
            f"{ticker} quote date/currency mismatch"
        )

        require(
            decimal(v["close_usd"])
            == decimal(q["close_usd"]),
            f"{ticker} close mismatch"
        )

        require(
            v["fiscal_quarter_end"]
            == str(financials[ticker]["period_end"]),
            f"{ticker} period mismatch"
        )

        for v_field, f_field in (
            ("ltm_revenue_usd_b", "revenue"),
            ("ltm_operating_income_usd_b", "operating")
        ):
            require(
                abs(
                    decimal(v[v_field])
                    - financials[ticker][f_field] / B
                ) <= Decimal("0.0005"),
                (
                    f"{ticker}: LTM mismatch "
                    f"for {v_field}"
                )
            )

        revenue = financials[ticker]["revenue"]
        operating = financials[ticker]["operating"]

        close = decimal(q["close_usd"])

        old_cap = (
            close * decimal(v["shares_outstanding"])
        )

        require(
            abs(
                old_cap / B
                - decimal(
                    v["indicative_market_cap_usd_b"]
                )
            ) <= Decimal("0.0005"),
            f"{ticker}: Market cap changed"
        )

        cap = None
        ev = None
        status = ""
        basis = ""
        share_age = ""
        flags = []

        if ticker == "PLTR":
            classes = pit["pltr"]["cover_class_shares"]

            require(
                set(classes)
                == {"class_a", "class_b", "class_f"},
                "PLTR classes missing"
            )

            total_shares = sum(classes.values())

            require(
                total_shares == 2409497474,
                "PLTR cover shares changed"
            )

            share_date = date.fromisoformat(
                pit["pltr"]["cover_share_date"]
            )

            share_age = (
                as_of - share_date
            ).days

            require(
                share_age == 22,
                "PLTR share lag changed"
            )

            require(
                pltr_note["valuation_status"]
                == "INDICATIVE_NOTE_BASED",
                "PLTR valuation policy changed"
            )

            require(
                pltr_note[
                    "share_classes_economic_rights_reviewed"
                ] is True,
                "PLTR share class review missing"
            )

            cash = decimal(
                pltr_note["cash_usd"]
            )

            treasury = decimal(
                pltr_note["us_treasury_securities_usd"]
            )

            equity = decimal(
                pltr_note["public_equity_securities_usd"]
            )

            require(
                treasury + equity
                == decimal(
                    pltr_note[
                        "marketable_securities_total_usd"
                    ]
                ),
                "PLTR investment bridge mismatch"
            )

            require(
                decimal(v["cash_usd_b"])
                == (cash / B).quantize(
                    Decimal(".001")
                ),
                "PLTR cash mismatch"
            )

            require(
                decimal(
                    pltr_note[
                        "assumed_financial_borrowings_usd"
                    ]
                ) == 0,
                "PLTR borrowings note changed"
            )

            cap = close * total_shares

            ev = cap - cash - treasury

            status = "INDICATIVE_NOTE_BASED"

            basis = (
                "cash_and_us_treasuries; "
                "note_based_zero_borrowings; "
                "leases_excluded"
            )

            flags = [
                "MANUAL_10Q_NOTE_EVIDENCE",
                "SHARES_NOT_CERTIFIED",
                "LEASES_EXCLUDED"
            ]

            require(
                (
                    f"- Base EV/Sales: "
                    f"{ratio(ev, revenue)}x"
                ) in pltr_audit,
                "PLTR EV/Sales audit differs"
            )

            require(
                (
                    f"- Base EV/EBIT: "
                    f"{ratio(ev, operating)}x"
                ) in pltr_audit,
                "PLTR EV/EBIT audit differs"
            )

        elif ticker == "NVDA":
            require(
                (
                    "Shares disclosed (rounded): "
                    "24,100,000,000"
                ) in nvda_audit,
                "NVDA share audit mismatch"
            )

            cap = old_cap

            share_age = int(
                v["share_age_days"]
            )

            require(
                share_age == 88,
                "NVDA share lag changed"
            )

            status = "BLOCKED_SHARE_COUNT"

            basis = (
                "illustrative_sensitivity_only; "
                "EV_not_approved"
            )

            flags = [
                "STALE_SHARES_88_DAYS",
                "ROUNDED_COVER_SHARES",
                "POST_CLOSE_EARNINGS_EXCLUDED"
            ]

        else:
            cap = old_cap

            share_age = int(
                v["share_age_days"]
            )

            require(
                share_age <= 45,
                f"{ticker}: stale shares"
            )

            cash = (
                decimal(v["cash_usd_b"]) * B
            )

            invest = (
                decimal(
                    v["selected_investments_usd_b"]
                ) * B
            )

            debt = (
                decimal(v["selected_debt_usd_b"]) * B
            )

            ev = (
                cap + debt - cash - invest
            )

            require(
                billions(ev) == v["ev_base_usd_b"],
                f"{ticker}: EV mismatch"
            )

            require(
                ratio(ev, revenue)
                == v["ev_sales_base"],
                f"{ticker}: EV/Sales mismatch"
            )

            require(
                ratio(ev, operating)
                == v["ev_ebit_base"],
                f"{ticker}: EV/EBIT mismatch"
            )

            status = "INDICATIVE"

            basis = (
                "cash_plus_selected_short_term_investments; "
                "borrowings; leases_excluded"
            )

            flags = [
                "SHARES_NOT_CERTIFIED",
                "LEASES_EXCLUDED"
            ]

            if ticker == "MSFT":
                finance = (
                    decimal(
                        v["finance_lease_usd_b"]
                    ) * B
                )

                operating_lease = (
                    decimal(
                        v["operating_lease_usd_b"]
                    ) * B
                )

                require(
                    billions(ev + finance)
                    == v[
                        "ev_with_finance_lease_usd_b"
                    ],
                    "MSFT finance-lease sensitivity changed"
                )

                require(
                    billions(
                        ev + finance + operating_lease
                    ) == v[
                        "ev_with_both_leases_usd_b"
                    ],
                    "MSFT lease sensitivity changed"
                )

                flags.append(
                    "FINANCE_LEASE_SENSITIVITY_SEPARATE"
                )

        require(
            cap is not None,
            f"{ticker}: Missing market capitalization"
        )

        cap_value = billions(cap)

        ev_value = (
            billions(ev)
            if ev is not None
            else ""
        )

        sales_value = (
            ratio(ev, revenue)
            if ev is not None
            else ""
        )

        ebit_value = (
            ratio(ev, operating)
            if ev is not None
            else ""
        )

        growth = s["quarterly_revenue_yoy_pct"]
        margin = s["operating_margin_pct"]

        output.append({
            "fundamental_rank": rank,
            "ticker": ticker,
            "as_of_date": as_of.isoformat(),
            "fundamental_status": s["fundamental_status"],
            "quarter_revenue_yoy_pct": growth,
            "operating_margin_pct": margin,
            "ltm_revenue_yoy_pct": s[
                "ltm_revenue_yoy_pct"
            ],
            "valuation_status": status,
            "share_age_days": share_age,
            "indicative_market_cap_usd_b": cap_value,
            "indicative_ev_usd_b": ev_value,
            "ev_sales": sales_value,
            "ev_ebit": ebit_value,
            "valuation_basis": basis,
            "review_flags": "; ".join(flags),
        })

        display_sales = (
            sales_value + "x"
            if sales_value
            else "BLOCKED"
        )

        display_ebit = (
            ebit_value + "x"
            if ebit_value
            else "BLOCKED"
        )

        lines.append(
            f"| {rank} | {ticker} | "
            f"{growth}% | {margin}% | "
            f"{s['fundamental_status']} | "
            f"{display_sales} | "
            f"{display_ebit} | {status} |"
        )

        print(
            f"{ticker}: Fundamental "
            f"{s['fundamental_status']} "
            f"| Valuation {status} "
            f"| EV/Sales {sales_value or 'BLOCKED'}"
        )

    require(
        sum(
            row["valuation_status"]
            != "BLOCKED_SHARE_COUNT"
            for row in output
        ) == 3,
        "Unexpected valuation coverage"
    )

    require(
        sum(
            row["fundamental_status"] == "PASS"
            for row in output
        ) == 3,
        "Fundamental coverage changed"
    )

    lines.extend([
        "",
        "## Interpretive and audit restrictions",
        "",
        "- Fundamental rank is quarterly revenue YoY order, not investment attractiveness.",
        "- Microsoft FAIL reflects the 20% quarterly revenue-growth rule, not a valuation failure.",
        "- PLTR: note-based Treasury adjustment; excludes public-equity securities and lease liabilities.",
        "- AMD/MSFT: selected short-term investments and borrowing debt; lease liabilities excluded from base EV.",
        "- Microsoft lease cases remain separate sensitivities, not a common valuation rank.",
        "- NVIDIA: stale rounded share count; hypothetical EV numbers remain outside the approved comparison.",
        "- No cross-company EV valuation ranking is produced because input definitions and review levels differ.",
        "- Yahoo historical prices were retrieved after the valuation date and may reflect later data revisions.",
        "- SEC note facts for PLTR remain manually transcribed, not verified by this aggregation script.",
        "- The raw market-price source CSV is locally ignored by Git; store provenance separately for reproducibility.",
        "- No FCF cross-company ranking, no real-time valuations, and no trading recommendations.",
        "",
        "## Source lineage",
        "",
        f"- Price CSV SHA-256: `{meta['csv_sha256']}`",
        f"- `reports/screen_v03_{as_of}.csv`",
        f"- `reports/valuation_preview_v04_{as_of}.csv`",
        f"- `reports/pltr_valuation_review_v041_{as_of}.md`",
        f"- `reports/nvda_share_uncertainty_v041_{as_of}.md`",
        "- DuckDB: `quarterly_metrics_four_reconciled` (read-only, 48 rows)",
        "",
        "**Status:** V0.4.2 INTEGRATION VALIDATED; EV values are NOT certified.",
        "",
    ])

    REPORTS.mkdir(
        parents=True,
        exist_ok=True
    )

    csv_buffer = io.StringIO(newline="")

    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=COLUMNS,
        lineterminator="\n"
    )

    writer.writeheader()
    writer.writerows(output)

    csv_bytes = (
        csv_buffer.getvalue().encode("utf-8")
    )

    md_bytes = (
        "\n".join(lines).encode("utf-8")
    )

    csv_path = (
        REPORTS /
        f"integrated_screen_v042_{as_of}.csv"
    )

    md_path = (
        REPORTS /
        f"integrated_screen_v042_{as_of}.md"
    )

    print()
    print("INTEGRATED SCREEN V0.4.2 SUMMARY")
    print("=" * 60)

    print(
        "CSV:",
        csv_path.relative_to(ROOT),
        write_immutable(csv_path, csv_bytes)
    )

    print(
        "Markdown:",
        md_path.relative_to(ROOT),
        write_immutable(md_path, md_bytes)
    )

    print(
        "CSV SHA-256:",
        hashlib.sha256(csv_bytes).hexdigest()
    )

    print("Fundamental: 3 PASS / 1 FAIL")
    print("Valuation: 3 INDICATIVE / 1 BLOCKED")
    print("Valuation attractiveness ranking: NOT PRODUCED")
    print("DuckDB: READ ONLY")
    print("Integrated V0.4.2: PASS")


if __name__ == "__main__":
    main()