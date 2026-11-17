
"""
JK's Financial Data Lab V1.0
Week 3 - Fiscal Period and XBRL Validation

Read-only: does not modify SEC JSON or DuckDB.

Examples:
python src/validate_fiscal_periods.py --ticker NVDA --fy 2026
python src/validate_fiscal_periods.py --ticker NVDA --fy 2027
python src/validate_fiscal_periods.py --ticker PLTR --fy 2026
"""

import argparse
import json
from datetime import date
from pathlib import Path

from check_company_config import load_companies, periods


ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data/raw"
TAG_CONFIG = ROOT / "config/metric_tags.json"

METRICS = (
    "revenue",
    "operating_income",
    "ocf",
    "capex"
)

Q_FORMS = ("10-Q", "10-Q/A")
K_FORMS = ("10-K", "10-K/A")


# 1. Load SEC facts and financial tag mapping
def load_data(ticker):
    companies = load_companies()

    company = next(
        (c for c in companies if c["ticker"] == ticker),
        None
    )

    if company is None:
        raise ValueError(f"Unknown ticker: {ticker}")

    path = RAW_DIR / f"{ticker.lower()}_companyfacts.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Missing SEC file: {path}"
        )

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    if data.get("cik") != int(company["cik"]):
        raise ValueError("SEC CIK mismatch")

    config = json.loads(
        TAG_CONFIG.read_text(encoding="utf-8")
    )

    if config.get("version") != 1:
        raise ValueError("Unsupported metric config version")

    tags = config["metric_tags"][ticker]

    for metric in METRICS:
        if not tags.get(metric):
            raise ValueError(
                f"Missing tag configuration: {metric}"
            )

    facts = data["facts"]["us-gaap"]

    for metric, tag in tags.items():
        if tag not in facts:
            raise ValueError(
                f"{ticker}: tag not found: {tag}"
            )

    return company, facts, tags


# 2. Find the first filing for an exact period
def find_fact(
    facts,
    tag,
    start,
    end,
    forms,
    as_of
):
    observations = (
        facts[tag]
        .get("units", {})
        .get("USD", [])
    )

    matches = []

    for row in observations:
        if row.get("start") != start.isoformat():
            continue

        if row.get("end") != end.isoformat():
            continue

        if row.get("form") not in forms:
            continue

        filed = row.get("filed")

        if not filed or filed > as_of.isoformat():
            continue

        value = row.get("val")

        if isinstance(value, bool):
            continue

        if not isinstance(value, (int, float)):
            continue

        matches.append(row)

    if not matches:
        return None

    # Earliest eligible filing, not the newest restatement
    return min(
        matches,
        key=lambda r: (
            r["filed"],
            r.get("accn", "")
        )
    )


# 3. Build a calculated metric with source history
def make_result(value, method, sources):
    return {
        "value": value,
        "method": method,
        "available_date": max(
            r["filed"] for r in sources
        ),
        "sources": [
            {
                "filed": r["filed"],
                "accn": r.get("accn")
            }
            for r in sources
        ]
    }


# 4. Reconstruct an individual fiscal quarter
def calculate_metric(
    facts,
    tag,
    fiscal_periods,
    quarter_number,
    metric,
    as_of
):
    current = fiscal_periods[quarter_number - 1]

    fiscal_start = fiscal_periods[0]["start"]
    q_start = current["start"]
    q_end = current["end"]

    forms = (
        K_FORMS if quarter_number == 4
        else Q_FORMS
    )

    # Revenue and operating income:
    # Q1-Q3: direct quarterly facts
    # Q4: annual minus 9M cumulative facts
    if metric in ("revenue", "operating_income"):

        if quarter_number < 4:
            direct = find_fact(
                facts, tag, q_start, q_end,
                Q_FORMS, as_of
            )

            if direct is None:
                return None

            return make_result(
                direct["val"],
                "DIRECT",
                [direct]
            )

        annual = find_fact(
            facts, tag,
            fiscal_start, q_end,
            K_FORMS, as_of
        )

        nine_months = find_fact(
            facts, tag,
            fiscal_start,
            fiscal_periods[2]["end"],
            Q_FORMS, as_of
        )

        if annual is None or nine_months is None:
            return None

        return make_result(
            annual["val"] - nine_months["val"],
            "FY_MINUS_9M",
            [annual, nine_months]
        )

    # Operating cash flow and CAPEX:
    # all quarterly values come from YTD records
    current_ytd = find_fact(
        facts, tag,
        fiscal_start, q_end,
        forms, as_of
    )

    if current_ytd is None:
        return None

    if quarter_number == 1:
        return make_result(
            current_ytd["val"],
            "Q1_YTD",
            [current_ytd]
        )

    previous_end = fiscal_periods[
        quarter_number - 2
    ]["end"]

    previous_ytd = find_fact(
        facts, tag,
        fiscal_start, previous_end,
        Q_FORMS, as_of
    )

    if previous_ytd is None:
        return None

    return make_result(
        current_ytd["val"] - previous_ytd["val"],
        "YTD_DIFFERENCE",
        [current_ytd, previous_ytd]
    )


# 5. Run the audit for all four fiscal quarters
def run_audit(ticker, fy, as_of):
    company, facts, tags = load_data(ticker)

    fiscal_periods = periods(company, fy)

    print("=" * 64)
    print(f"{ticker} | Fiscal Year {fy}")
    print(f"CIK: {company['cik']}")
    print(f"As-of filing date: {as_of}")
    print("=" * 64)

    complete_quarters = 0

    for p in fiscal_periods:
        q = p["quarter"]

        print()
        print(
            f"FY{fy} Q{q}: "
            f"{p['start']} -> {p['end']}"
        )

        results = {}

        for metric in METRICS:
            result = calculate_metric(
                facts,
                tags[metric],
                fiscal_periods,
                q,
                metric,
                as_of
            )

            results[metric] = result

            if result is None:
                print(
                    f"  {metric.upper():17} "
                    "NO MATCHING FACT AS OF DATE"
                )
                continue

            print(
                f"  {metric.upper():17} "
                f"{result['value']:>18,} USD "
                f"[{result['method']}]"
            )

            print(
                "    Available: "
                f"{result['available_date']}"
            )

            for source in result["sources"]:
                print(
                    "    SEC: "
                    f"{source['filed']} | "
                    f"{source['accn']}"
                )

        if all(results.values()):
            revenue = results["revenue"]["value"]
            income = results["operating_income"]["value"]
            ocf = results["ocf"]["value"]
            capex = results["capex"]["value"]

            fcf = ocf - capex
            margin = income / revenue * 100 if revenue else None

            print(f"  {'FCF':17} {fcf:>18,} USD")

            if margin is not None:
                print(
                    f"  Operating margin: {margin:.2f}%"
                )

            print("  Fiscal period status: PASS")
            complete_quarters += 1

            # Cross-check against already inspected facts
            if ticker == "NVDA" and fy == 2027 and q == 2:
                expected = {
                    "revenue": 96221000000,
                    "operating_income": 63734000000,
                    "ocf": 24077000000,
                    "capex": 2677000000
                }

                for metric, value in expected.items():
                    if results[metric]["value"] != value:
                        raise ValueError(
                            f"NVDA FY2027 Q2 mismatch: {metric}"
                        )

                print("  Known-facts cross-check: PASS")

        else:
            print(
                "  Fiscal period status: "
                "INCOMPLETE IN LOCAL SNAPSHOT"
            )

    print()
    print("=" * 64)
    print(
        f"Completed quarters: "
        f"{complete_quarters}/4"
    )
    print("Fiscal period audit finished.")
    print("=" * 64)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--ticker",
        required=True
    )

    parser.add_argument(
        "--fy",
        required=True,
        type=int
    )

    parser.add_argument(
        "--as-of",
        default="2026-11-17"
    )

    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of)

    run_audit(
        args.ticker.upper(),
        args.fy,
        as_of
    )


if __name__ == "__main__":
    main()