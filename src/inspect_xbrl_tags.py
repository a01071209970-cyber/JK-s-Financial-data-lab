
"""
JK's Financial Data Lab V1.0
Week 3 - XBRL Financial Tag Inspector

Usage:
python src/inspect_xbrl_tags.py --ticker NVDA
python src/inspect_xbrl_tags.py --ticker PLTR
"""

import argparse
import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config/companies.json"
RAW_DIR = ROOT / "data/raw"


# Candidate XBRL tags
CANDIDATES = {
    "REVENUE": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet"
    ],

    "OPERATING_INCOME": [
        "OperatingIncomeLoss"
    ],

    "OPERATING_CASH_FLOW": [
        "NetCashProvidedByUsedInOperatingActivities"
    ],

    "CAPEX": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets"
    ]
}


def load_company(ticker):
    config = json.loads(
        CONFIG_PATH.read_text(encoding="utf-8")
    )

    for company in config["companies"]:
        if company["ticker"] == ticker:
            return company

    raise ValueError(f"Unknown ticker: {ticker}")


def load_facts(company):
    ticker = company["ticker"]

    path = RAW_DIR / (
        f"{ticker.lower()}_companyfacts.json"
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Run fetch_companyfacts.py for {ticker} first"
        )

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    if data.get("cik") != int(company["cik"]):
        raise ValueError("CIK mismatch")

    return data


def duration_days(observation):
    start = observation.get("start")
    end = observation.get("end")

    if not start or not end:
        return None

    return (
        date.fromisoformat(end)
        - date.fromisoformat(start)
    ).days + 1


def inspect_metric(facts, metric, tags, as_of, limit):
    print(f"\n{'=' * 60}")
    print("METRIC:", metric)
    print("=" * 60)

    found = False

    for tag in tags:
        concept = facts.get(tag)

        if concept is None:
            continue

        observations = concept.get(
            "units", {}
        ).get("USD", [])

        valid = [
            row for row in observations
            if row.get("form") in (
                "10-Q", "10-K", "10-Q/A", "10-K/A"
            )
            and row.get("filed", "9999-12-31") <= as_of
            and duration_days(row) is not None
        ]

        if not valid:
            continue

        found = True

        # One first-available filing per exact period
        first_by_period = {}

        for row in sorted(
            valid,
            key=lambda x: (
                x["filed"],
                x.get("accn", "")
            )
        ):
            key = (
                row["start"],
                row["end"]
            )

            if key not in first_by_period:
                first_by_period[key] = row

        selected = list(
            first_by_period.values()
        )

        # Revenue and operating income:
        # show near-quarter durations.
        if metric in ("REVENUE", "OPERATING_INCOME"):
            sample = [
                row for row in selected
                if 75 <= duration_days(row) <= 110
            ]

        # Cash flow:
        # allow Q1, 6M, 9M and annual YTD.
        else:
            sample = [
                row for row in selected
                if 75 <= duration_days(row) <= 380
            ]

        sample.sort(
            key=lambda x: (
                x["end"],
                x["filed"]
            ),
            reverse=True
        )

        print()
        print("Tag:", tag)
        print("Label:", concept.get("label", "N/A"))
        print("USD observations:", len(valid))
        print("Unique periods:", len(selected))

        if valid:
            latest_filing = max(
                row["filed"] for row in valid
            )
            print("Latest filing:", latest_filing)

        print("Recent first-available periods:")

        if not sample:
            print("  No matching duration observations")

        for row in sample[:limit]:
            days = duration_days(row)

            print(
                f"  {row['start']} -> {row['end']} "
                f"({days} days)"
            )

            print(
                f"    Value: {row['val']:,.0f} USD "
                f"| Form: {row['form']}"
            )

            print(
                f"    Filed: {row['filed']} "
                f"| FY: {row.get('fy')} "
                f"| FP: {row.get('fp')}"
            )

            print(
                f"    Accession: {row.get('accn')}"
            )

    if not found:
        print("No usable candidate tags found.")

        keywords = {
            "REVENUE": ("Revenue", "Sales"),
            "OPERATING_INCOME": ("OperatingIncome",),
            "OPERATING_CASH_FLOW": ("CashProvided",),
            "CAPEX": ("PaymentsToAcquire",)
        }

        alternatives = [
            tag for tag in facts
            if any(
                word.lower() in tag.lower()
                for word in keywords[metric]
            )
        ]

        print("Other potentially related tags:")
        for tag in alternatives[:15]:
            print(" -", tag)

    return found


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--ticker",
        required=True
    )

    parser.add_argument(
        "--as-of",
        default="2026-11-17"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=3
    )

    args = parser.parse_args()

    ticker = args.ticker.upper()

    # Validate date input
    date.fromisoformat(args.as_of)

    company = load_company(ticker)
    data = load_facts(company)

    facts = data["facts"].get("us-gaap", {})

    print("\nJK's Financial Data Lab")
    print("XBRL TAG INSPECTION")
    print("-" * 60)

    print("Ticker:", ticker)
    print("CIK:", company["cik"])
    print("SEC company:", data.get("entityName"))
    print("US-GAAP concepts:", len(facts))
    print("As-of filing date:", args.as_of)

    results = {}

    for metric, tags in CANDIDATES.items():
        results[metric] = inspect_metric(
            facts,
            metric,
            tags,
            args.as_of,
            args.limit
        )

    print("\n" + "=" * 60)
    print("FINAL CHECK")
    print("=" * 60)

    for metric, success in results.items():
        print(
            f"{metric}: "
            f"{'FOUND' if success else 'REVIEW REQUIRED'}"
        )

    if all(results.values()):
        print("\nCandidate tag inspection: PASS")
        print("Next: verify fiscal-period mapping.")
    else:
        print("\nCandidate tag inspection: REVIEW")


if __name__ == "__main__":
    main()