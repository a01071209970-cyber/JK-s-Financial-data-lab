
"""
JK's Financial Data Lab V1.0
Week 5 - SEC Valuation Note Reconciliation

Source:
    SEC Company Facts
    Official 10-Q note references

Companies:
    PLTR, NVDA, AMD, MSFT

Features:
    Point-in-time filing cutoff
    Exact-quarter balance-sheet matching
    Debt reconciliation
    Conservative liquid-asset classification
    Finance-lease sensitivity scenarios

Read-only.
No database changes.
No market prices or enterprise value.
"""

import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb

from check_company_config import load_companies


ROOT = Path(__file__).resolve().parent.parent

DB = ROOT / "data/processed/financial_data.duckdb"
RAW = ROOT / "data/raw"

POLICY_FILE = (
    ROOT / "config/valuation_input_policy.json"
)

MILLION = Decimal("1000000")
BILLION = Decimal("1000000000")

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

# Manually reviewed official SEC note facts.
# These are NOT inferred from missing XBRL tags.
NOTE_EVIDENCE = {
    "PLTR": {
        "credit_facility_balance_usd": 0,
        "scope": "2014 Credit Facility",
        "url": (
            "https://www.sec.gov/Archives/edgar/"
            "data/1321655/000132165526000048/"
            "pltr-20260930.htm"
        )
    },
    "MSFT": {
        "hedge_adjustment_usd": 4_000_000,
        "exchange_premium_usd": 4_720_000_000,
        "url": (
            "https://www.sec.gov/Archives/edgar/"
            "data/789019/000119312526436133/"
            "msft-20260930.htm"
        )
    }
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    return Decimal(str(value))


def usd_b(value):
    if value is None:
        return "UNVERIFIED"

    return f"${number(value) / BILLION:,.3f}B"


def read_configs():

    policy = json.loads(
        POLICY_FILE.read_text(encoding="utf-8")
    )

    require(
        policy["version"] == 1,
        "Unsupported valuation policy"
    )

    require(
        set(policy["expected_tickers"])
        == EXPECTED_TICKERS,
        "Company universe mismatch"
    )

    require(
        set(policy["companies"])
        == EXPECTED_TICKERS,
        "Company policy mismatch"
    )

    cutoff = date.fromisoformat(
        policy["as_of_date"]
    )

    return policy, cutoff


def get_latest_periods(con, cutoff):

    rows = con.execute("""
        SELECT ticker, period_end
        FROM quarterly_metrics_four_reconciled
        ORDER BY ticker, period_end
    """).fetchall()

    require(
        len(rows) == 48,
        "Expected 48 reconciled quarters"
    )

    counts = Counter(
        ticker for ticker, _ in rows
    )

    require(
        counts == {
            ticker: 12
            for ticker in EXPECTED_TICKERS
        },
        "Incorrect quarter coverage"
    )

    latest = {}

    for ticker, period_end in rows:
        latest[ticker] = period_end

    require(
        all(
            end <= cutoff
            for end in latest.values()
        ),
        "Future reporting period found"
    )

    return latest


def get_fact(
    company_data,
    tag,
    period_end,
    cutoff
):

    require(
        tag is not None,
        "Cannot fetch unspecified tag"
    )

    records = (
        company_data["facts"]
        .get("us-gaap", {})
        .get(tag, {})
        .get("units", {})
        .get("USD", [])
    )

    candidates = []

    for item in records:

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

        measurement = date.fromisoformat(
            item["end"]
        )

        filed = date.fromisoformat(
            item["filed"]
        )

        if measurement != period_end:
            continue

        if filed > cutoff:
            continue

        candidates.append(item)

    require(
        len(candidates) > 0,
        f"No valid quarter-end SEC fact: {tag}"
    )

    candidates.sort(
        key=lambda item: (
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
            item["filed"],
            item.get("accn", "")
        ) == (
            selected["filed"],
            selected.get("accn", "")
        )
    ]

    require(
        len({
            str(item["val"])
            for item in same_source
        }) == 1,
        f"Conflicting values: {tag}"
    )

    return number(
        selected["val"]
    )


def load_company_facts(ticker, company):

    path = (
        RAW /
        f"{ticker.lower()}_companyfacts.json"
    )

    require(
        path.exists(),
        f"Missing SEC data: {path}"
    )

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    require(
        int(data["cik"]) == int(company["cik"]),
        f"{ticker}: CIK mismatch"
    )

    return data


def main():

    policy, cutoff = read_configs()

    require(
        DB.exists(),
        f"Database missing: {DB}"
    )

    companies = {
        item["ticker"]: item
        for item in load_companies()
    }

    require(
        set(companies) == EXPECTED_TICKERS,
        "Company configuration mismatch"
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
            "SEC observation count changed"
        )

        latest = get_latest_periods(
            con,
            cutoff
        )

    finally:
        con.close()

    facts = {
        ticker: load_company_facts(
            ticker,
            companies[ticker]
        )
        for ticker in EXPECTED_TICKERS
    }

    def value(ticker, tag):

        return get_fact(
            facts[ticker],
            tag,
            latest[ticker],
            cutoff
        )

    print()
    print("WEEK 5 SEC VALUATION RECONCILIATION")
    print("=" * 65)
    print("As-of:", cutoff)
    print("SEC observations:", f"{observations:,}")
    print("Database: READ ONLY")

    # -------------------------------------------------
    # PLTR: Cash and securities; debt note evidence
    # -------------------------------------------------

    pltr_cash = value(
        "PLTR",
        "CashAndCashEquivalentsAtCarryingValue"
    )

    pltr_securities = value(
        "PLTR",
        "MarketableSecuritiesCurrent"
    )

    require(
        pltr_cash == 3_619_414_000,
        "PLTR cash baseline mismatch"
    )

    require(
        pltr_securities == 6_942_117_000,
        "PLTR securities baseline mismatch"
    )

    pltr_liquid = (
        pltr_cash + pltr_securities
    )

    require(
        NOTE_EVIDENCE["PLTR"][
            "credit_facility_balance_usd"
        ] == 0,
        "PLTR credit facility note mismatch"
    )

    print()
    print("-" * 65)
    print("PLTR — CASH AND CREDIT FACILITY")
    print("-" * 65)

    print("Cash:", usd_b(pltr_cash))
    print(
        "Marketable securities:",
        usd_b(pltr_securities)
    )
    print(
        "Selected liquid assets:",
        usd_b(pltr_liquid)
    )

    print(
        "Credit facility drawn balance:",
        "$0.000B (OFFICIAL NOTE)"
    )

    print(
        "Total-debt XBRL mapping:",
        "UNVERIFIED"
    )

    print(
        "Note scope:",
        NOTE_EVIDENCE["PLTR"]["scope"]
    )

    print(
        "Source:",
        NOTE_EVIDENCE["PLTR"]["url"]
    )

    # -------------------------------------------------
    # NVDA: Reconcile marketable debt securities
    # -------------------------------------------------

    nvda_cash = value(
        "NVDA",
        "CashAndCashEquivalentsAtCarryingValue"
    )

    nvda_marketable_debt = value(
        "NVDA",
        "DebtSecuritiesCurrent"
    )

    nvda_debt = value(
        "NVDA",
        "LongTermDebt"
    )

    nvda_equity_securities = value(
        "NVDA",
        "EquitySecuritiesFvNi"
    )

    require(
        nvda_cash == 22_443_000_000,
        "NVDA cash mismatch"
    )

    require(
        nvda_marketable_debt == 34_143_000_000,
        "NVDA marketable debt mismatch"
    )

    require(
        nvda_debt == 33_366_000_000,
        "NVDA borrowings mismatch"
    )

    require(
        nvda_equity_securities == 42_783_000_000,
        "NVDA equity securities mismatch"
    )

    nvda_base_liquid = (
        nvda_cash + nvda_marketable_debt
    )

    nvda_base_net = (
        nvda_base_liquid - nvda_debt
    )

    print()
    print("-" * 65)
    print("NVDA — CONSERVATIVE LIQUIDITY")
    print("-" * 65)

    print("Cash:", usd_b(nvda_cash))

    print(
        "Marketable debt securities:",
        usd_b(nvda_marketable_debt)
    )

    print(
        "Conservative liquid assets:",
        usd_b(nvda_base_liquid)
    )

    print(
        "Borrowings:",
        usd_b(nvda_debt)
    )

    print(
        "Conservative liquidity - borrowings:",
        usd_b(nvda_base_net)
    )

    print(
        "Marketable equity securities:",
        usd_b(nvda_equity_securities)
    )

    print(
        "Marketable equity included in base:",
        "NO"
    )

    print(
        "Classification:",
        "CONSERVATIVE / PROVISIONAL"
    )

    # -------------------------------------------------
    # AMD: Existing borrowings calculation
    # -------------------------------------------------

    amd_cash = value(
        "AMD",
        "CashAndCashEquivalentsAtCarryingValue"
    )

    amd_investments = value(
        "AMD",
        "ShortTermInvestments"
    )

    amd_debt = value(
        "AMD",
        "DebtLongtermAndShorttermCombinedAmount"
    )

    amd_current = value(
        "AMD",
        "LongTermDebtCurrent"
    )

    amd_noncurrent = value(
        "AMD",
        "LongTermDebtNoncurrent"
    )

    require(
        amd_debt == amd_current + amd_noncurrent,
        "AMD debt reconciliation failed"
    )

    require(
        amd_cash == 7_404_000_000
        and amd_investments == 8_372_000_000
        and amd_debt == 7_079_000_000,
        "AMD valuation baseline changed"
    )

    amd_base_net = (
        amd_cash + amd_investments - amd_debt
    )

    print()
    print("-" * 65)
    print("AMD — PROVISIONAL NET LIQUIDITY")
    print("-" * 65)

    print(
        "Cash + short-term investments:",
        usd_b(amd_cash + amd_investments)
    )

    print(
        "Borrowings:",
        usd_b(amd_debt)
    )

    print(
        "Base liquidity - borrowings:",
        usd_b(amd_base_net)
    )

    print(
        "Borrowing components reconciliation:",
        "PASS"
    )

    # -------------------------------------------------
    # MSFT: Debt note bridge and lease scenarios
    # -------------------------------------------------

    msft_cash = value(
        "MSFT",
        "CashAndCashEquivalentsAtCarryingValue"
    )

    msft_short_investments = value(
        "MSFT",
        "ShortTermInvestments"
    )

    msft_combined = value(
        "MSFT",
        "CashCashEquivalentsAndShortTermInvestments"
    )

    msft_debt = value(
        "MSFT",
        "LongTermDebt"
    )

    msft_current = value(
        "MSFT",
        "LongTermDebtCurrent"
    )

    msft_noncurrent = value(
        "MSFT",
        "LongTermDebtNoncurrent"
    )

    msft_face = value(
        "MSFT",
        "DebtInstrumentCarryingAmount"
    )

    msft_discount = value(
        "MSFT",
        "DebtInstrumentUnamortizedDiscountPremiumAndDebtIssuanceCostsNet"
    )

    msft_finance_lease = value(
        "MSFT",
        "FinanceLeaseLiability"
    )

    msft_operating_lease = value(
        "MSFT",
        "OperatingLeaseLiability"
    )

    require(
        msft_cash + msft_short_investments
        == msft_combined,
        "MSFT cash reconciliation failed"
    )

    require(
        msft_current + msft_noncurrent
        == msft_debt,
        "MSFT debt components mismatch"
    )

    require(
        msft_face == 41_269_000_000,
        "MSFT face amount changed"
    )

    require(
        msft_discount == 1_064_000_000,
        "MSFT debt discount changed"
    )

    hedge = number(
        NOTE_EVIDENCE["MSFT"][
            "hedge_adjustment_usd"
        ]
    )

    exchange = number(
        NOTE_EVIDENCE["MSFT"][
            "exchange_premium_usd"
        ]
    )

    debt_reconstructed = (
        msft_face
        - msft_discount
        - hedge
        - exchange
    )

    require(
        debt_reconstructed == msft_debt,
        "MSFT SEC debt note bridge failed"
    )

    require(
        msft_debt == 35_481_000_000,
        "MSFT carrying debt changed"
    )

    require(
        msft_finance_lease == 70_973_000_000,
        "MSFT finance lease changed"
    )

    require(
        msft_operating_lease == 27_477_000_000,
        "MSFT operating lease changed"
    )

    msft_base = (
        msft_combined - msft_debt
    )

    msft_finance_adjusted = (
        msft_base - msft_finance_lease
    )

    msft_all_leases_adjusted = (
        msft_finance_adjusted
        - msft_operating_lease
    )

    print()
    print("-" * 65)
    print("MSFT — DEBT RECONCILIATION")
    print("-" * 65)

    print(
        "Debt face value:",
        usd_b(msft_face)
    )

    print(
        "Less discount and issuance costs:",
        usd_b(msft_discount)
    )

    print(
        "Less hedge adjustments:",
        usd_b(hedge)
    )

    print(
        "Less debt exchange premium:",
        usd_b(exchange)
    )

    print(
        "Reconstructed debt carrying amount:",
        usd_b(debt_reconstructed)
    )

    print(
        "Debt note reconciliation:",
        "PASS"
    )

    print()
    print("MSFT — LEASE SENSITIVITY")
    print("-" * 65)

    print(
        "Cash + short-term investments:",
        usd_b(msft_combined)
    )

    print(
        "Scenario A - Borrowings only:",
        usd_b(msft_base)
    )

    print(
        "Scenario B - Including finance leases:",
        usd_b(msft_finance_adjusted)
    )

    print(
        "Scenario C - Including both lease types:",
        usd_b(msft_all_leases_adjusted)
    )

    print(
        "Note source:",
        NOTE_EVIDENCE["MSFT"]["url"]
    )

    print()
    print("=" * 65)

    print("VALUATION RECONCILIATION SUMMARY")

    print("=" * 65)

    print("PLTR credit facility note: RECORDED")
    print("NVDA conservative liquidity: VERIFIED")
    print("AMD debt components: PASS")
    print("MSFT debt note bridge: PASS")
    print("MSFT lease sensitivity: COMPLETED")

    print()
    print("Enterprise value: NOT CALCULATED")
    print("Market prices: NOT LOADED")
    print("Final valuation ranking: NOT APPROVED")
    print("Database: READ ONLY")

    print()
    print("Week 5 note reconciliation: PASS")


if __name__ == "__main__":
    main()