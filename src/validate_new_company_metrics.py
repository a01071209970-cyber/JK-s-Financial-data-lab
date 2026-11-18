
"""
JK's Financial Data Lab V1.0
Week 4 - New Company Metric Preflight

Validate AMD and MSFT financial metrics using
SEC Company Facts before database ingestion.

Read-only. No DuckDB modifications.
"""

import json
from datetime import date
from pathlib import Path

from check_company_config import load_companies, periods


ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data/raw"
TAGS_FILE = ROOT / "config/metric_tags.json"

AS_OF = date(2026, 11, 17)

TARGETS = {
    "AMD": {
        "fy": 2026,
        "quarter": 3,
        "cik": 2488,
        "expected": {
            "revenue": 13_377_000_000,
            "operating_income": 2_832_000_000,
            "ocf": 1_202_000_000,
            "capex": 648_000_000
        },
        "expected_ytd": {
            "ocf": 6_523_000_000,
            "capex": 1_845_000_000
        }
    },
    "MSFT": {
        "fy": 2027,
        "quarter": 1,
        "cik": 789019,
        "expected": {
            "revenue": 92_279_000_000,
            "operating_income": 45_915_000_000,
            "ocf": 58_000_000_000,
            "capex": 39_367_000_000
        }
    }
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def select_fact(
    facts,
    tag,
    start,
    end,
    latest_date
):
    if tag not in facts:
        return None

    observations = facts[tag].get(
        "units", {}
    ).get("USD", [])

    candidates = []

    for item in observations:

        if item.get("start") != str(start):
            continue

        if item.get("end") != str(end):
            continue

        if item.get("form") not in (
            "10-Q",
            "10-Q/A",
            "10-K",
            "10-K/A"
        ):
            continue

        filed = item.get("filed")

        if not filed:
            continue

        if date.fromisoformat(filed) > latest_date:
            continue

        candidates.append(item)

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            item["filed"],
            item.get("accn", "")
        )
    )

    first = candidates[0]

    same_filing = [
        item for item in candidates
        if item["filed"] == first["filed"]
        and item.get("accn", "")
            == first.get("accn", "")
    ]

    require(
        len({item["val"] for item in same_filing}) == 1,
        f"Conflicting SEC values for {tag}"
    )

    return first


def calculate_metric(
    facts,
    tag,
    fiscal_periods,
    quarter,
    metric
):
    period = fiscal_periods[quarter - 1]

    fiscal_start = fiscal_periods[0]["start"]

    quarter_start = period["start"]
    quarter_end = period["end"]

    # Revenue and operating income:
    # direct three-month facts.
    if metric in ("revenue", "operating_income"):

        observation = select_fact(
            facts,
            tag,
            quarter_start,
            quarter_end,
            AS_OF
        )

        require(
            observation is not None,
            f"Missing direct quarterly {metric}"
        )

        return {
            "value": int(observation["val"]),
            "method": "DIRECT",
            "filed": observation["filed"]
        }

    # OCF and CAPEX:
    # start with current year-to-date values.
    current = select_fact(
        facts,
        tag,
        fiscal_start,
        quarter_end,
        AS_OF
    )

    require(
        current is not None,
        f"Missing current YTD {metric}"
    )

    current_value = int(current["val"])

    if quarter == 1:
        return {
            "value": current_value,
            "ytd": current_value,
            "method": "Q1_YTD",
            "filed": current["filed"]
        }

    previous_end = fiscal_periods[
        quarter - 2
    ]["end"]

    previous = select_fact(
        facts,
        tag,
        fiscal_start,
        previous_end,
        date.fromisoformat(current["filed"])
    )

    require(
        previous is not None,
        f"Missing previous YTD {metric}"
    )

    previous_value = int(previous["val"])

    return {
        "value": current_value - previous_value,
        "ytd": current_value,
        "prior_ytd": previous_value,
        "method": "YTD_DIFFERENCE",
        "filed": current["filed"],
        "prior_filed": previous["filed"]
    }


def main():
    companies = {
        c["ticker"]: c
        for c in load_companies()
    }

    tag_config = json.loads(
        TAGS_FILE.read_text(encoding="utf-8")
    )

    require(
        tag_config.get("version") == 1,
        "Unsupported mapping version"
    )

    mappings = tag_config["metric_tags"]

    require(
        set(companies) == set(mappings),
        "Company and tag configurations do not match"
    )

    for ticker, target in TARGETS.items():

        path = (
            RAW_DIR /
            f"{ticker.lower()}_companyfacts.json"
        )

        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        require(
            int(data["cik"]) == target["cik"],
            f"{ticker}: Incorrect CIK"
        )

        company = companies[ticker]

        fiscal_periods = periods(
            company,
            target["fy"]
        )

        current_period = fiscal_periods[
            target["quarter"] - 1
        ]

        require(
            current_period["end"] <= AS_OF,
            f"{ticker}: Future fiscal period"
        )

        facts = data["facts"]["us-gaap"]

        results = {}

        print()
        print("=" * 60)
        print(
            f"{ticker} FY{target['fy']} "
            f"Q{target['quarter']}"
        )
        print("=" * 60)

        for metric in (
            "revenue",
            "operating_income",
            "ocf",
            "capex"
        ):
            tag = mappings[ticker][metric]

            result = calculate_metric(
                facts,
                tag,
                fiscal_periods,
                target["quarter"],
                metric
            )

            expected = target["expected"][metric]

            require(
                result["value"] == expected,
                (
                    f"{ticker} {metric} mismatch: "
                    f"actual={result['value']:,}, "
                    f"expected={expected:,}"
                )
            )

            if "expected_ytd" in target:
                if metric in target["expected_ytd"]:

                    require(
                        result["ytd"]
                        == target["expected_ytd"][metric],
                        f"{ticker}: YTD {metric} mismatch"
                    )

            results[metric] = result["value"]

            print()
            print(metric.upper())
            print("Tag:", tag)
            print(
                "Quarter USD:",
                f"{result['value']:,}"
            )
            print("Method:", result["method"])
            print("Filed:", result["filed"])
            print("Validation: PASS")

        revenue = results["revenue"]
        operating_income = results["operating_income"]

        ocf = results["ocf"]
        capex = results["capex"]

        simple_fcf = ocf - capex

        operating_margin = (
            operating_income / revenue * 100
        )

        print()
        print("FINANCIAL SUMMARY")
        print("-" * 60)
        print(f"Revenue: ${revenue / 1e9:.3f}B")
        print(
            f"Operating margin: "
            f"{operating_margin:.2f}%"
        )
        print(f"OCF: ${ocf / 1e9:.3f}B")
        print(f"CAPEX: ${capex / 1e9:.3f}B")
        print(
            f"Simple FCF: ${simple_fcf / 1e9:.3f}B"
        )

        print()
        print(f"{ticker} metric mapping: PASS")

    print()
    print("=" * 60)
    print("NEW COMPANY METRIC PREFLIGHT: PASS")
    print("Database: UNCHANGED")
    print("=" * 60)


if __name__ == "__main__":
    main()