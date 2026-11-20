
"""JK's Financial Data Lab - Week 5 valuation preview (V0.4).

Reuses the previously validated market, SEC share, and financial
statement readers. Price/split checks may contact Yahoo Finance.

Writes an indicative CSV in reports. Does not modify DuckDB.
"""

import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb

from audit_market_cap_alignment_v04 import (
    latest_periods,
    load_snapshot,
    read_shares,
    split_audit,
)
from reconcile_valuation_notes import get_fact
from run_four_company_screen import (
    DB_PATH,
    ROOT,
    check_database,
    load_rules,
    read_quarters,
    validate_historical_regression,
    validate_quarter_sequence,
)

TICKERS = ("PLTR", "NVDA", "AMD", "MSFT")
BILLION = Decimal("1000000000")
MAX_SHARE_AGE_DAYS = 45

POLICY = ROOT / "config/valuation_input_policy.json"
COMPANIES = ROOT / "config/companies.json"
RAW = ROOT / "data/raw"
REPORTS = ROOT / "reports"

# Week 5 SEC source-level validation baselines.
# Mismatches stop execution rather than inventing inputs.
BASELINES = {
    "PLTR": (3619414000, 6942117000, None),
    "NVDA": (22443000000, 34143000000, 33366000000),
    "AMD": (7404000000, 8372000000, 7079000000),
    "MSFT": (20281000000, 44228000000, 35481000000),
}

FIELDS = [
    "ticker",
    "as_of_date",
    "fiscal_quarter_end",
    "share_date",
    "share_filed_date",
    "share_source",
    "share_age_days",
    "split_events",
    "close_usd",
    "shares_outstanding",
    "indicative_market_cap_usd_b",
    "cash_usd_b",
    "selected_investments_usd_b",
    "selected_debt_usd_b",
    "operating_lease_usd_b",
    "finance_lease_usd_b",
    "ltm_revenue_usd_b",
    "ltm_operating_income_usd_b",
    "valuation_status",
    "review_flags",
    "ev_base_usd_b",
    "ev_sales_base",
    "ev_ebit_base",
    "ev_with_finance_lease_usd_b",
    "ev_with_both_leases_usd_b",
    "source_price_csv_sha256",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def usd_b(value):
    if value is None:
        return ""
    return f"{value / BILLION:.3f}"


def multiple(value):
    if value is None:
        return ""
    return f"{value:.2f}"


def load_sec(ticker, company_cik):
    path = RAW / f"{ticker.lower()}_companyfacts.json"

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    require(
        int(data["cik"]) == int(company_cik),
        f"{ticker}: CIK mismatch"
    )

    return data


def selected_fact(data, tag, fiscal_end, as_of):
    if tag is None:
        return None

    result = get_fact(
        data,
        tag,
        fiscal_end,
        as_of
    )

    require(
        result.is_finite(),
        f"{tag}: non-finite value"
    )

    return result


def load_financial_inputs(
    ticker,
    data,
    setting,
    fiscal_end,
    as_of
):
    def get(setting_name):
        return selected_fact(
            data,
            setting.get(setting_name),
            fiscal_end,
            as_of
        )

    cash = get("cash_tag")

    # NVDA's current marketable debt securities
    # were separately validated in Week 5.
    if ticker == "NVDA":
        investments = selected_fact(
            data,
            "DebtSecuritiesCurrent",
            fiscal_end,
            as_of
        )
    else:
        investments = get(
            "short_term_investments_tag"
        )

    debt = get("debt_total_tag")
    current = get("debt_current_tag")
    noncurrent = get("debt_noncurrent_tag")

    require(
        cash is not None
        and investments is not None,
        f"{ticker}: Missing liquid-asset components"
    )

    if (
        debt is not None
        and current is not None
        and noncurrent is not None
    ):
        require(
            debt == current + noncurrent,
            f"{ticker}: Debt components do not reconcile"
        )

    combined = get("combined_liquidity_tag")

    if combined is not None:
        require(
            combined == cash + investments,
            f"{ticker}: Combined liquidity mismatch"
        )

    lease_op = get("operating_lease_total_tag")
    lease_fin = get("finance_lease_total_tag")

    expected = BASELINES[ticker]
    expected_cash = expected[0]
    expected_investments = expected[1]
    expected_debt = expected[2]

    require(
        cash == expected_cash
        and investments == expected_investments,
        f"{ticker}: Liquidity baseline changed"
    )

    require(
        debt == expected_debt,
        f"{ticker}: Debt baseline changed"
    )

    if ticker == "MSFT":
        require(
            lease_fin == Decimal(70973000000),
            "MSFT: Finance lease changed"
        )

        require(
            lease_op == Decimal(27477000000),
            "MSFT: Operating lease changed"
        )

    return (
        cash,
        investments,
        debt,
        lease_op,
        lease_fin
    )


def ltm_metrics(rows):
    recent = rows[-4:]

    revenue = sum(
        (
            Decimal(str(row["revenue_usd"]))
            for row in recent
        ),
        Decimal(0)
    )

    operating = sum(
        (
            Decimal(str(row["operating_income_usd"]))
            for row in recent
        ),
        Decimal(0)
    )

    require(
        revenue > 0 and operating > 0,
        "Invalid LTM denominator"
    )

    return revenue, operating


def main():
    as_of, quotes, price_sha, metadata = (
        load_snapshot()
    )

    rules, screen_as_of = load_rules()

    require(
        as_of == screen_as_of,
        "Screen and quote dates differ"
    )

    require(
        set(rules["expected_tickers"]) == set(TICKERS),
        "Ticker mismatch"
    )

    policy = json.loads(
        POLICY.read_text(encoding="utf-8")
    )

    company_config = json.loads(
        COMPANIES.read_text(encoding="utf-8")
    )

    require(
        policy["version"] == 1,
        "Unexpected valuation policy version"
    )

    require(
        date.fromisoformat(policy["as_of_date"]) == as_of,
        "Valuation policy date mismatch"
    )

    require(
        set(policy["companies"]) == set(TICKERS),
        "Valuation company mismatch"
    )

    ciks = {
        company["ticker"]: company["cik"]
        for company in company_config["companies"]
    }

    require(
        set(ciks) == set(TICKERS),
        "SEC company CIK mapping mismatch"
    )

    fiscal_ends = latest_periods(as_of)

    con = duckdb.connect(
        str(DB_PATH),
        read_only=True
    )

    try:
        check_database(con)

        records = read_quarters(con)

        validate_historical_regression(
            con,
            records
        )

    finally:
        con.close()

    by_ticker = {
        ticker: []
        for ticker in TICKERS
    }

    for row in records:
        require(
            row["ticker"] in by_ticker,
            "Unexpected quarterly ticker"
        )

        by_ticker[row["ticker"]].append(row)

    output = []

    print()
    print("WEEK 5 INDICATIVE VALUATION PREVIEW V0.4")
    print("=" * 67)
    print("As-of:", as_of)
    print("Price snapshot SHA-256:", price_sha)

    print(
        "Note: historical Yahoo prices and SEC share "
        "counts are not certified PIT market caps."
    )

    for ticker in TICKERS:
        rows = by_ticker[ticker]

        validate_quarter_sequence(
            ticker,
            rows,
            as_of
        )

        require(
            rows[-1]["period_end"] == fiscal_ends[ticker],
            f"{ticker}: Latest quarter mismatch"
        )

        revenue, operating = ltm_metrics(rows)

        quote = quotes[ticker]

        share, dei, gaap = read_shares(
            ticker,
            fiscal_ends[ticker],
            as_of
        )

        age = (
            quote["date"] - share["date"]
        ).days

        require(
            age >= 0,
            f"{ticker}: Future share measurement"
        )

        splits = split_audit(
            ticker,
            share["date"],
            quote["date"],
            quote["close"]
        )

        flags = []

        if splits:
            flags.append(
                "SPLIT_BETWEEN_SHARE_DATE_AND_PRICE"
            )

        if age > MAX_SHARE_AGE_DAYS:
            flags.append(
                "SHARES_STALE_OVER_45_DAYS"
            )

        if ticker == "PLTR":
            flags.extend([
                "SHARE_CLASS_COVERAGE_REVIEW",
                "BORROWINGS_NOT_FULLY_VERIFIED"
            ])

        company_facts = load_sec(
            ticker,
            ciks[ticker]
        )

        (
            cash,
            investments,
            debt,
            lease_op,
            lease_fin
        ) = load_financial_inputs(
            ticker,
            company_facts,
            policy["companies"][ticker],
            fiscal_ends[ticker],
            as_of
        )

        market_cap = (
            quote["close"] * share["shares"]
        )

        status = (
            "BLOCKED"
            if flags or debt is None
            else "INDICATIVE"
        )

        if status == "BLOCKED":
            ev = None
        else:
            ev = (
                market_cap
                + debt
                - cash
                - investments
            )

        ev_sales = (
            None
            if ev is None
            else ev / revenue
        )

        ev_ebit = (
            None
            if ev is None
            else ev / operating
        )

        ev_fin = (
            ev + lease_fin
            if ev is not None
            and lease_fin is not None
            else None
        )

        ev_both = (
            ev_fin + lease_op
            if ev_fin is not None
            and lease_op is not None
            else None
        )

        expected_status = (
            "INDICATIVE"
            if ticker in ("AMD", "MSFT")
            else "BLOCKED"
        )

        require(
            status == expected_status,
            (
                f"{ticker}: Unexpected review status; "
                "investigate inputs"
            )
        )

        split_label = "; ".join(
            f"{day.isoformat()}:{ratio}"
            for day, ratio in splits
        )

        output.append({
            "ticker": ticker,
            "as_of_date": as_of.isoformat(),
            "fiscal_quarter_end": (
                fiscal_ends[ticker].isoformat()
            ),
            "share_date": share["date"].isoformat(),
            "share_filed_date": (
                share["filed"].isoformat()
            ),
            "share_source": share["tag"],
            "share_age_days": age,
            "split_events": split_label,
            "close_usd": str(quote["close"]),
            "shares_outstanding": str(share["shares"]),
            "indicative_market_cap_usd_b": (
                usd_b(market_cap)
            ),
            "cash_usd_b": usd_b(cash),
            "selected_investments_usd_b": (
                usd_b(investments)
            ),
            "selected_debt_usd_b": usd_b(debt),
            "operating_lease_usd_b": usd_b(lease_op),
            "finance_lease_usd_b": usd_b(lease_fin),
            "ltm_revenue_usd_b": usd_b(revenue),
            "ltm_operating_income_usd_b": (
                usd_b(operating)
            ),
            "valuation_status": status,
            "review_flags": "; ".join(flags),
            "ev_base_usd_b": usd_b(ev),
            "ev_sales_base": multiple(ev_sales),
            "ev_ebit_base": multiple(ev_ebit),
            "ev_with_finance_lease_usd_b": (
                usd_b(ev_fin)
            ),
            "ev_with_both_leases_usd_b": (
                usd_b(ev_both)
            ),
            "source_price_csv_sha256": price_sha,
        })

        print()
        print(
            f"{ticker}: {status} "
            f"| indicative market cap ${usd_b(market_cap)}B"
            f" | shares {age}d old"
        )

        print(
            "  EV/Sales:",
            multiple(ev_sales) or "BLOCKED",
            "| EV/EBIT:",
            multiple(ev_ebit) or "BLOCKED"
        )

        if flags:
            print(
                "  Review flags:",
                "; ".join(flags)
            )

        if ticker == "MSFT":
            print(
                "  Finance-lease-inclusive EV: $"
                + usd_b(ev_fin) + "B"
            )

            print(
                "  Both-leases-inclusive EV: $"
                + usd_b(ev_both) + "B"
            )

    require(
        len(output) == 4,
        "Incomplete valuation output"
    )

    require(
        sum(
            row["valuation_status"] == "INDICATIVE"
            for row in output
        ) == 2,
        "Unexpected number of indicative valuations"
    )

    buffer = io.StringIO(newline="")

    writer = csv.DictWriter(
        buffer,
        fieldnames=FIELDS,
        lineterminator="\n"
    )

    writer.writeheader()
    writer.writerows(output)

    csv_bytes = buffer.getvalue().encode("utf-8")

    REPORTS.mkdir(
        parents=True,
        exist_ok=True
    )

    target = (
        REPORTS /
        f"valuation_preview_v04_{as_of.isoformat()}.csv"
    )

    if target.exists():
        require(
            target.read_bytes() == csv_bytes,
            (
                "Existing report differs; refusing "
                "to overwrite historical output"
            )
        )

        action = "VERIFIED EXISTING"

    else:
        with target.open("xb") as file:
            file.write(csv_bytes)

        action = "CREATED"

    print()
    print("=" * 67)

    print(
        "Report:",
        target.relative_to(ROOT),
        "|",
        action
    )

    print(
        "Report SHA-256:",
        hashlib.sha256(csv_bytes).hexdigest()
    )

    print(
        "Indicative EV cases: 2 "
        "| Blocked EV cases: 2"
    )

    print(
        "MSFT lease cases: SENSITIVITY ONLY, "
        "not peer-comparable"
    )

    print("FCF cross-company ranking: DISABLED")
    print("DuckDB: READ ONLY")
    print("Valuation preview V0.4: PASS")


if __name__ == "__main__":
    main()