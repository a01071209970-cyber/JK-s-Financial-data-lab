
"""V0.5 candidate SEC Company Facts collector.

Default mode is a no-write dry run.
Use --apply to collect six candidate snapshots.

Existing four-company configuration, DuckDB,
quarterly metrics and valuations are untouched.
"""

import argparse
import hashlib
import json
import os
import re
import time

from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
RAW = ROOT / "data/raw"
REPORTS = ROOT / "reports"

AS_OF = "2026-11-17"

CANDIDATES = (
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "ANET",
    "CRDO",
)

FORMS = {
    "10-Q",
    "10-K",
    "10-Q/A",
    "10-K/A",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_candidates():
    config = read_json(
        CONFIG / "universe_candidates_v05.json"
    )

    require(
        config["version"] == 1,
        "Candidate config version mismatch"
    )

    require(
        config["research_as_of"] == AS_OF,
        "Research cutoff changed"
    )

    baseline = ("PLTR", "NVDA", "AMD", "MSFT")

    require(
        tuple(config["existing_tickers"]) == baseline,
        "Historical universe changed"
    )

    entries = config["candidate_companies"]

    require(
        tuple(x["ticker"] for x in entries)
        == CANDIDATES,
        "Candidate list changed"
    )

    require(
        all(
            x["onboarding_status"] == "PENDING_REVIEW"
            for x in entries
        ),
        "Candidate prematurely approved"
    )

    require(
        all(
            x["calendar_status"] == "UNVERIFIED"
            for x in entries
        ),
        "Calendar status unexpectedly changed"
    )

    existing = read_json(
        CONFIG / "companies.json"
    )["companies"]

    require(
        tuple(x["ticker"] for x in existing)
        == baseline,
        "Protected company configuration changed"
    )

    return entries


def sec_directory():
    rows = read_json(
        RAW / "sec_company_tickers_v05.json"
    )

    require(
        isinstance(rows, dict),
        "SEC company directory invalid"
    )

    mapping = {}

    for record in rows.values():
        if not isinstance(record, dict):
            continue

        ticker = str(
            record.get("ticker", "")
        ).upper()

        cik = record.get("cik_str")

        if (
            ticker
            and isinstance(cik, int)
            and cik > 0
        ):
            require(
                ticker not in mapping,
                f"Duplicate SEC ticker: {ticker}"
            )

            mapping[ticker] = (
                f"{cik:010d}",
                str(record.get("title", ""))
            )

    require(
        len(mapping) >= 1000,
        "SEC directory unexpectedly small"
    )

    return mapping


def validate_payload(raw, ticker, cik):
    item = json.loads(raw)

    require(
        isinstance(item, dict),
        f"{ticker}: Invalid JSON root"
    )

    require(
        int(item.get("cik", -1)) == int(cik),
        f"{ticker}: SEC CIK mismatch"
    )

    require(
        isinstance(item.get("entityName"), str)
        and bool(item["entityName"]),
        f"{ticker}: Entity name missing"
    )

    require(
        isinstance(item.get("facts"), dict)
        and bool(item["facts"]),
        f"{ticker}: Financial facts absent"
    )

    return item


def obtain(ticker, cik, agent):
    raw_path = (
        RAW / f"{ticker.lower()}_companyfacts.json"
    )

    meta_path = (
        RAW / f"{ticker.lower()}_companyfacts.meta.json"
    )

    url = (
        "https://data.sec.gov/api/xbrl/"
        f"companyfacts/CIK{cik}.json"
    )

    if raw_path.exists():
        require(
            meta_path.exists(),
            f"{ticker}: Cached raw has no metadata"
        )

        raw = raw_path.read_bytes()
        meta = read_json(meta_path)
        source = "VERIFIED_CACHE"

    else:
        require(
            not meta_path.exists(),
            f"{ticker}: Orphan metadata file"
        )

        require(
            bool(agent) and "@" in agent,
            "Set SEC_USER_AGENT before downloading"
        )

        response = requests.get(
            url,
            headers={
                "User-Agent": agent,
                "Accept": "application/json",
            },
            timeout=60,
        )

        response.raise_for_status()

        raw = response.content

        require(
            0 < len(raw) < 100_000_000,
            f"{ticker}: Unexpected SEC response size"
        )

        validate_payload(raw, ticker, cik)

        meta = {
            "ticker": ticker,
            "cik": cik,
            "source_url": url,
            "retrieved_at_utc": datetime.now(
                timezone.utc
            ).isoformat(timespec="seconds"),
            "size_bytes": len(raw),
            "sha256": digest(raw),
            "research_as_of": AS_OF,
            "historical_pit_approved": False,
        }

        RAW.mkdir(
            parents=True,
            exist_ok=True
        )

        with raw_path.open("xb") as handle:
            handle.write(raw)

        with meta_path.open(
            "x",
            encoding="utf-8"
        ) as handle:
            json.dump(meta, handle, indent=2)
            handle.write("\n")

        source = "DOWNLOADED"

        time.sleep(0.6)

    data = validate_payload(
        raw, ticker, cik
    )

    require(
        meta.get("ticker") == ticker,
        f"{ticker}: Metadata ticker mismatch"
    )

    require(
        meta.get("cik") == cik,
        f"{ticker}: Metadata CIK mismatch"
    )

    require(
        meta.get("source_url") == url,
        f"{ticker}: Source URL mismatch"
    )

    require(
        meta.get("size_bytes") == len(raw),
        f"{ticker}: Snapshot size mismatch"
    )

    require(
        meta.get("sha256") == digest(raw),
        f"{ticker}: SHA-256 mismatch"
    )

    require(
        meta.get("research_as_of") == AS_OF,
        f"{ticker}: Cutoff mismatch"
    )

    require(
        meta.get("historical_pit_approved") is False,
        f"{ticker}: Unexpected PIT approval"
    )

    return data, meta, source


def inventory(facts):
    eligible = 0
    not_eligible = 0
    missing_filed = 0

    for taxonomy in facts.values():
        for concept in taxonomy.values():
            for observations in concept.get(
                "units", {}
            ).values():
                for item in observations:
                    if item.get("form") not in FORMS:
                        continue

                    filed = item.get("filed", "")

                    if (
                        not isinstance(filed, str)
                        or not re.fullmatch(
                            r"\d{4}-\d{2}-\d{2}",
                            filed
                        )
                    ):
                        missing_filed += 1

                    elif filed < AS_OF:
                        eligible += 1

                    else:
                        not_eligible += 1

    return eligible, not_eligible, missing_filed


def save_immutable(path, content):
    if path.exists():
        require(
            path.read_text(encoding="utf-8")
            == content,
            "Refusing to overwrite existing report"
        )

        return "VERIFIED EXISTING"

    REPORTS.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open(
        "x",
        encoding="utf-8"
    ) as handle:
        handle.write(content)

    return "CREATED"


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Download or verify six SEC snapshots"
    )

    args = parser.parse_args()

    entries = load_candidates()
    directory = sec_directory()

    print()
    print(
        "SEC COMPANY FACTS CANDIDATE ARCHIVE V0.5"
    )
    print("=" * 60)

    print(
        "Mode:",
        "APPLY" if args.apply else "DRY RUN"
    )

    print("Historical cutoff:", AS_OF)

    for entry in entries:
        require(
            entry["ticker"] in directory,
            f"SEC CIK directory missing: "
            f"{entry['ticker']}"
        )

    if not args.apply:
        for entry in entries:
            ticker = entry["ticker"]

            path = (
                RAW /
                f"{ticker.lower()}_companyfacts.json"
            )

            status = (
                "VERIFY LOCAL SNAPSHOT"
                if path.exists()
                else "DOWNLOAD REQUIRED"
            )

            print(f"{ticker}: {status}")

        print(
            "Database: UNCHANGED | Files: UNCHANGED"
        )

        return

    agent = os.getenv(
        "SEC_USER_AGENT", ""
    ).strip()

    results = []

    for entry in entries:
        ticker = entry["ticker"]
        cik, sec_name = directory[ticker]

        data, meta, source = obtain(
            ticker,
            cik,
            agent
        )

        eligible, excluded, missing = inventory(
            data["facts"]
        )

        require(
            eligible > 0,
            f"{ticker}: No eligible pre-cutoff facts"
        )

        results.append((
            ticker,
            cik,
            sec_name,
            data,
            meta,
            source,
            eligible,
            excluded,
            missing,
        ))

        print(
            f"{ticker}: {source} | "
            f"eligible={eligible:,} | "
            f"same-day/later excluded={excluded:,}"
        )

    lines = [
        "# Candidate Company Facts Inventory — V0.5",
        "",
        f"**Research cutoff:** {AS_OF}",
        "**Status:** RAW_ARCHIVED_NOT_ONBOARDED",
        "",
        "| Ticker | CIK | SEC entity | US-GAAP tags | Pre-cutoff facts | Same-day/later excluded | SHA-256 prefix |",
        "|---|---|---|---:|---:|---:|---|",
    ]

    for (
        ticker, cik, sec_name, data,
        meta, source, eligible, excluded, missing
    ) in results:

        name = data["entityName"].replace(
            "|", "/"
        )

        gaap_count = len(
            data["facts"].get("us-gaap", {})
        )

        lines.append(
            f"| {ticker} | `{cik}` | {name} | "
            f"{gaap_count} | {eligible:,} | "
            f"{excluded:,} | "
            f"`{meta['sha256'][:12]}` |"
        )

    lines += [
        "",
        "## Controls and limitations",
        "",
        "- Six company snapshots are stored locally.",
        "- Raw JSON and metadata are excluded from Git.",
        "- Historical eligibility uses SEC filing dates strictly before the cutoff.",
        "- Same-day filings require separate acceptance-time checks.",
        "- Post-cutoff facts remain in the raw archive but must not enter historical screening.",
        "- Retrieval time does not prove historical availability.",
        "- Fiscal calendars and XBRL tag mappings remain unverified.",
        "- No candidate has been approved for valuation.",
        "- Existing DuckDB and four-company reports were not modified.",
        "",
        "## Retrieval provenance",
        "",
    ]

    for (
        ticker, _, _, _, meta,
        _, _, _, _
    ) in results:

        lines.append(
            f"- {ticker}: retrieved "
            f"`{meta['retrieved_at_utc']}`; "
            f"SHA-256 `{meta['sha256']}`"
        )

    lines.append("")

    report = (
        REPORTS /
        f"candidate_companyfacts_inventory_v05_{AS_OF}.md"
    )

    action = save_immutable(
        report,
        "\n".join(lines)
    )

    print()
    print("Companies archived:", len(results))
    print("Prior four-company data: PRESERVED")
    print("Candidate fiscal/PIT approval: PENDING")

    print(
        "Report:",
        report.relative_to(ROOT),
        action
    )

    print("SEC candidate raw archive: PASS")


if __name__ == "__main__":
    main()