
"""
JK's Financial Data Lab V1.0
Week 4 - AMD / MSFT XBRL Tag Discovery

Read-only inspection of SEC Company Facts.

Target quarters:
    AMD FY2026 Q3
    MSFT FY2027 Q1

Data cutoff:
    2026-11-17
"""

import json
from datetime import date
from pathlib import Path

from check_company_config import (
    load_companies,
    periods
)


ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data/raw"

CUTOFF = date(2026, 11, 17)

TARGETS = {
    "AMD": (2026, 3, 2488),
    "MSFT": (2027, 1, 789019)
}

REVENUE_TAGS = {
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "SalesRevenueServicesNet"
}

OPERATING_INCOME_TAGS = {
    "OperatingIncomeLoss"
}

OCF_TAGS = {
    "NetCashProvidedByUsedInOperatingActivities"
}


def classify_tag(tag, label):

    if tag in REVENUE_TAGS:
        return "REVENUE"

    if tag in OPERATING_INCOME_TAGS:
        return "OPERATING_INCOME"

    if tag in OCF_TAGS:
        return "OCF"

    if tag.startswith("PaymentsToAcquire"):

        capex_terms = (
            "PropertyPlant",
            "ProductiveAssets",
            "IntangibleAssets"
        )

        if any(
            term in tag
            for term in capex_terms
        ):
            return "CAPEX_CANDIDATE"

    # A custom taxonomy or different label may
    # require additional investigation.
    return None


def first_available_observation(
    entries,
    start,
    end
):
    matches = []

    for entry in entries:

        if entry.get("start") != str(start):
            continue

        if entry.get("end") != str(end):
            continue

        if entry.get("form") not in (
            "10-Q", "10-Q/A",
            "10-K", "10-K/A"
        ):
            continue

        filed = entry.get("filed")

        if not filed or filed > str(CUTOFF):
            continue

        matches.append(entry)

    matches.sort(
        key=lambda item: (
            item["filed"],
            item.get("accn", "")
        )
    )

    return matches[0] if matches else None


def describe_observation(entry):

    if entry is None:
        return "NOT_FOUND"

    value = entry["val"]

    amount_m = value / 1_000_000

    return (
        f"${amount_m:,.3f}M "
        f"| filed={entry['filed']} "
        f"| form={entry['form']}"
    )


def main():

    companies = {
        c["ticker"]: c
        for c in load_companies()
    }

    for ticker, (
        fiscal_year,
        quarter,
        expected_cik
    ) in TARGETS.items():

        path = (
            RAW_DIR /
            f"{ticker.lower()}_companyfacts.json"
        )

        if not path.exists():
            raise FileNotFoundError(path)

        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        if int(data["cik"]) != expected_cik:
            raise ValueError(
                f"{ticker}: Incorrect CIK"
            )

        if ticker not in companies:
            raise ValueError(
                f"Missing company configuration: {ticker}"
            )

        fiscal_periods = periods(
            companies[ticker],
            fiscal_year
        )

        current = fiscal_periods[quarter - 1]

        quarter_start = current["start"]
        quarter_end = current["end"]

        ytd_start = fiscal_periods[0]["start"]

        us_gaap = data["facts"].get(
            "us-gaap", {}
        )

        print()
        print("=" * 75)
        print(
            f"{ticker} — FY{fiscal_year} Q{quarter}"
        )
        print("=" * 75)

        print("Company:", data["entityName"])
        print(
            "Quarter:",
            quarter_start,
            "~",
            quarter_end
        )
        print(
            "YTD:",
            ytd_start,
            "~",
            quarter_end
        )
        print("Data cutoff:", CUTOFF)

        categories = {
            "REVENUE": [],
            "OPERATING_INCOME": [],
            "OCF": [],
            "CAPEX_CANDIDATE": []
        }

        for tag, fact in us_gaap.items():

            label = fact.get("label", "")

            category = classify_tag(
                tag, label
            )

            if category is None:
                continue

            usd_entries = fact.get(
                "units", {}
            ).get("USD", [])

            direct = first_available_observation(
                usd_entries,
                quarter_start,
                quarter_end
            )

            ytd = first_available_observation(
                usd_entries,
                ytd_start,
                quarter_end
            )

            # Skip historical tags that have no
            # observation in the target quarter.
            if direct is None and ytd is None:
                continue

            categories[category].append({
                "tag": tag,
                "label": label,
                "direct": direct,
                "ytd": ytd
            })

        for category, rows in categories.items():

            print()
            print("-" * 75)
            print(category)
            print("-" * 75)

            if not rows:
                print(
                    "NO MATCHING TAG — "
                    "manual inspection required"
                )
                continue

            for row in sorted(
                rows,
                key=lambda item: item["tag"]
            ):

                print()
                print("TAG:", row["tag"])
                print("LABEL:", row["label"])

                print(
                    "DIRECT:",
                    describe_observation(
                        row["direct"]
                    )
                )

                print(
                    "YTD:",
                    describe_observation(
                        row["ytd"]
                    )
                )

        print()
        print(f"{ticker} tag discovery: COMPLETED")
        print(
            "Note: candidates require "
            "financial-statement verification."
        )

    print()
    print("=" * 75)
    print("AMD / MSFT XBRL discovery: COMPLETED")
    print("Database: UNCHANGED")
    print("=" * 75)


if __name__ == "__main__":
    main()