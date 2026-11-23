
"""JK's Financial Data Lab V0.5 - candidate-universe preflight.

Uses SEC's public ticker/CIK directory, not SEC financial observations.
Existing four-company configuration, DuckDB and reports remain untouched.
"""

import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
RAW = ROOT / "data/raw"
REPORTS = ROOT / "reports"
UNIVERSE_PATH = CONFIG / "universe_candidates_v05.json"
TICKER_CACHE = RAW / "sec_company_tickers_v05.json"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
BASELINE = ("PLTR", "NVDA", "AMD", "MSFT")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sec_ticker_snapshot():
    if TICKER_CACHE.exists():
        raw = TICKER_CACHE.read_bytes()
        origin = "LOCAL_SEC_CACHE"
    else:
        agent = os.getenv("SEC_USER_AGENT", "").strip()
        require(
            bool(agent) and "@" in agent,
            "Set SEC_USER_AGENT to an identifying name and real contact email",
        )
        response = requests.get(
            SEC_TICKERS_URL,
            headers={"User-Agent": agent, "Accept": "application/json"},
            timeout=45,
        )
        response.raise_for_status()
        raw = response.content
        origin = "SEC_DOWNLOAD"

    content = json.loads(raw)
    require(isinstance(content, dict) and content, "Invalid SEC ticker directory")

    lookup = {}
    for row in content.values():
        if not isinstance(row, dict):
            continue

        ticker = str(row.get("ticker", "")).strip().upper()
        title = str(row.get("title", "")).strip()
        cik = row.get("cik_str")

        if not ticker or not title or not isinstance(cik, int) or cik <= 0:
            continue

        require(ticker not in lookup, f"Duplicate SEC ticker: {ticker}")

        lookup[ticker] = {
            "cik": f"{cik:010d}",
            "name": title
        }

    require(
        len(lookup) >= 1000,
        "SEC ticker directory unexpectedly small"
    )

    if origin == "SEC_DOWNLOAD":
        RAW.mkdir(parents=True, exist_ok=True)
        with TICKER_CACHE.open("xb") as output:
            output.write(raw)

    return lookup, hashlib.sha256(raw).hexdigest(), origin


def write_immutable(path, value):
    if path.exists():
        require(
            path.read_text(encoding="utf-8") == value,
            f"Existing report differs; refusing overwrite: {path.name}"
        )
        return "VERIFIED EXISTING"

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(value)

    return "CREATED"


def main():
    universe = read_json(UNIVERSE_PATH)
    companies = read_json(CONFIG / "companies.json")
    rules = read_json(CONFIG / "screening_rules_v03.json")

    require(
        universe["version"] == 1,
        "Unexpected candidate policy version"
    )

    as_of = date.fromisoformat(universe["research_as_of"])
    require(
        as_of == date(2026, 11, 17),
        "Research cutoff has changed"
    )

    require(
        tuple(universe["existing_tickers"]) == BASELINE,
        "Existing universe order changed"
    )

    require(
        tuple(c["ticker"] for c in companies["companies"]) == BASELINE,
        "Protected company configuration changed"
    )

    require(
        set(rules["expected_tickers"]) == set(BASELINE),
        "Protected screen configuration changed"
    )

    candidates = universe["candidate_companies"]
    require(
        len(candidates) == 6,
        "Exactly six new candidates required"
    )

    tickers = [c["ticker"] for c in candidates]

    require(
        len(set(tickers)) == 6
        and not (set(tickers) & set(BASELINE)),
        "Duplicate or already-covered candidate"
    )

    for company in candidates:
        require(
            re.fullmatch(r"[A-Z]{1,5}", company["ticker"]) is not None,
            f"Invalid ticker: {company['ticker']}"
        )

        require(
            company["onboarding_status"] == "PENDING_REVIEW",
            "Candidate prematurely approved"
        )

        require(
            company["calendar_status"] == "UNVERIFIED",
            "Calendar approval needs separate evidence"
        )

        require(
            bool(company["research_theme"]),
            "Missing research theme"
        )

    directory, digest, origin = sec_ticker_snapshot()

    missing = [
        ticker
        for ticker in (*BASELINE, *tickers)
        if ticker not in directory
    ]

    require(
        not missing,
        f"Ticker(s) absent from SEC directory: {missing}"
    )

    for company in companies["companies"]:
        ticker = company["ticker"]

        require(
            directory[ticker]["cik"] == str(company["cik"]).zfill(10),
            f"Existing CIK identity mismatch: {ticker}"
        )

    lines = [
        "# Candidate Universe V0.5 — SEC Identity Preflight",
        "",
        f"**Research cutoff:** {as_of}",
        "**State:** IDENTITY_VERIFIED_ONLY — NOT INGESTED",
        "",
        "## New candidate companies",
        "",
        "| Ticker | SEC registrant | CIK | Research theme | Onboarding |",
        "|---|---|---|---|---|",
    ]

    for c in candidates:
        found = directory[c["ticker"]]
        name = found["name"].replace("|", "/")
        theme = c["research_theme"].replace("|", "/")

        lines.append(
            f"| {c['ticker']} | {name} | `{found['cik']}` | "
            f"{theme} | PENDING_REVIEW |"
        )

    lines += [
        "",
        "## Verification and scope",
        "",
        f"- SEC ticker directory: {SEC_TICKERS_URL}",
        f"- Locally retained directory SHA-256: `{digest}`",
        "- All four existing CIK mappings were rechecked.",
        "- Candidate CIK identity only; fiscal calendars and US-GAAP metric tags remain unverified.",
        "- This directory represents the retrieval-time mapping, not proof of historical index membership.",
        "- No Company Facts were downloaded for the candidates.",
        "- No facts were admitted into the November 17 historical snapshot.",
        "- Existing DuckDB, quarterly tables, financial screens and valuations were not modified.",
        "- Filing acceptance time and post-close availability must be reviewed before PIT approval.",
        "- Alphabet's multiple share classes require separate market-cap review.",
        "",
        "**Next gate:** fiscal calendar + XBRL taxonomy + as-of filing availability checks.",
        "",
    ]

    report = REPORTS / f"universe_preflight_v05_{as_of}.md"

    result = write_immutable(
        report,
        "\n".join(lines)
    )

    print("JK's FINANCIAL DATA LAB — UNIVERSE PREFLIGHT V0.5")
    print("=" * 58)

    print("Existing companies: 4 | CIK identities: PASS")
    print("Candidate companies: 6 | CIK identities: PASS")
    print("SEC map:", origin)

    for c in candidates:
        item = directory[c["ticker"]]
        print(
            f"{c['ticker']:<6} "
            f"CIK {item['cik']}  {item['name']}"
        )

    print("New candidates: PENDING_REVIEW")
    print("DuckDB: UNCHANGED | Existing reports: PRESERVED")

    print(
        "Report:",
        report.relative_to(ROOT),
        result
    )

    print("Candidate SEC identity preflight: PASS")


if __name__ == "__main__":
    main()