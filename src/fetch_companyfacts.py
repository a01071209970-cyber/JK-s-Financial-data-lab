
"""
JK's Financial Data Lab V1.0
Week 3 - Multi-Company SEC Collector

Usage:
    python src/fetch_companyfacts.py --ticker NVDA
    python src/fetch_companyfacts.py --ticker PLTR
"""

import argparse
import hashlib
import json
import os
import tempfile

from datetime import datetime, timezone
from pathlib import Path

import requests


# 1. Project paths
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config/companies.json"
RAW_DIR = ROOT / "data/raw"


# 2. Find company configuration
def load_company(ticker):
    config = json.loads(
        CONFIG_PATH.read_text(encoding="utf-8")
    )

    for company in config["companies"]:
        if company["ticker"].upper() == ticker.upper():
            return company

    raise ValueError(
        f"Ticker {ticker} not found in companies.json"
    )


# 3. Validate SEC response
def validate_companyfacts(raw, company):
    data = json.loads(raw)

    expected_cik = int(company["cik"])

    if data.get("cik") != expected_cik:
        raise ValueError(
            "SEC CIK does not match requested company"
        )

    if not isinstance(data.get("entityName"), str):
        raise ValueError("Missing SEC entity name")

    facts = data.get("facts")

    if not isinstance(facts, dict):
        raise ValueError("Missing XBRL facts")

    if not isinstance(facts.get("us-gaap"), dict):
        raise ValueError("Missing US-GAAP data")

    return data


# 4. Save file safely
def atomic_save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=".sec_",
        suffix=".tmp",
        delete=False
    ) as temp:
        temp.write(raw)
        temporary_path = Path(temp.name)

    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


# 5. Download or reuse SEC data
def fetch_company(ticker):
    company = load_company(ticker)

    cik = company["cik"]
    ticker = company["ticker"].upper()

    url = (
        "https://data.sec.gov/api/xbrl/"
        f"companyfacts/CIK{cik}.json"
    )

    output = (
        RAW_DIR /
        f"{ticker.lower()}_companyfacts.json"
    )

    metadata_path = (
        RAW_DIR /
        f"{ticker.lower()}_companyfacts.meta.json"
    )

    if output.exists():
        print("Source: LOCAL CACHE")
        raw = output.read_bytes()

        # Validate the existing cached file
        data = validate_companyfacts(raw, company)

    else:
        user_agent = os.getenv("SEC_USER_AGENT")

        if not user_agent:
            raise SystemExit(
                "Set SEC_USER_AGENT before downloading"
            )

        print("Source: SEC EDGAR API")

        response = requests.get(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json"
            },
            timeout=45
        )

        response.raise_for_status()
        raw = response.content

        # Validate before writing to disk
        data = validate_companyfacts(raw, company)

        downloaded_at = datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds")

        metadata = {
            "ticker": ticker,
            "cik": cik,
            "source_url": url,
            "downloaded_at_utc": downloaded_at,
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(
                raw
            ).hexdigest()
        }

        atomic_save(output, raw)

        atomic_save(
            metadata_path,
            json.dumps(
                metadata,
                indent=2
            ).encode("utf-8")
        )

    # 6. Count reported concepts and observations
    us_gaap = data["facts"]["us-gaap"]

    total_records = sum(
        len(observations)
        for taxonomy in data["facts"].values()
        for concept in taxonomy.values()
        for observations in concept["units"].values()
    )

    # 7. Print validation result
    print()
    print("Ticker:", ticker)
    print("Company:", data["entityName"])
    print("CIK:", data["cik"])
    print("US-GAAP tags:", len(us_gaap))
    print("Total observations:", total_records)
    print("File size:", len(raw), "bytes")
    print("Saved:", output)
    print("SHA256:", hashlib.sha256(raw).hexdigest())
    print("Validation: PASS")


# 8. Command-line entry point
def main():
    parser = argparse.ArgumentParser(
        description="Collect official SEC Company Facts"
    )

    parser.add_argument(
        "--ticker",
        required=True,
        help="Ticker in config/companies.json"
    )

    args = parser.parse_args()

    fetch_company(args.ticker)


if __name__ == "__main__":
    main()