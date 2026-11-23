
"""V0.5 SEC Company Facts candidate audit (read-only).

Checks six downloaded JSON snapshots against immutable metadata and
an official cached SEC ticker directory. Finds financial tag candidates
filed strictly before 2026-11-17. Does not approve or ingest data.
"""

import hashlib
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
CONFIG = ROOT / "config"
REPORTS = ROOT / "reports"
CUTOFF = date(2026, 11, 17)

TICKERS = ("AMZN", "META", "GOOGL", "AVGO", "ANET", "CRDO")
EXISTING = ("PLTR", "NVDA", "AMD", "MSFT")
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A"}

TAG_GROUPS = {
    "Revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
    ),
    "Operating income": (
        "OperatingIncomeLoss",
    ),
    "Operating cash flow": (
        "NetCashProvidedByUsedInOperatingActivities",
    ),
    "CAPEX candidate": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
        "PaymentsToAcquireIntangibleAssets",
    ),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def normalize_cik(value, label):
    """Normalize numeric and string SEC CIK values to 10 digits."""

    require(
        not isinstance(value, bool),
        f"{label}: Invalid boolean CIK"
    )

    digits = str(value).strip()

    require(
        re.fullmatch(r"[0-9]{1,10}", digits) is not None,
        f"{label}: Invalid CIK: {value!r}"
    )

    number = int(digits)

    require(
        number > 0,
        f"{label}: Zero CIK is invalid"
    )

    return f"{number:010d}"


def get_sec_directory():
    rows = read_json(
        RAW / "sec_company_tickers_v05.json"
    )

    require(
        isinstance(rows, dict) and rows,
        "Missing SEC ticker directory"
    )

    mapping = {}
    expected = set(EXISTING) | set(TICKERS)

    for item in rows.values():
        if not isinstance(item, dict):
            continue

        symbol = str(
            item.get("ticker", "")
        ).upper().strip()

        if symbol in expected:
            require(
                symbol not in mapping,
                f"Repeated ticker: {symbol}"
            )

            mapping[symbol] = normalize_cik(
                item.get("cik_str"),
                symbol
            )

    require(
        set(mapping) == expected,
        "Not all 10 tickers appear in cached SEC identity list"
    )

    return mapping


def admissible(item):
    """Validate historical filing date and financial duration."""

    if item.get("form") not in FORMS:
        return None

    value = item.get("val")

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        return None

    try:
        start = date.fromisoformat(item["start"])
        end = date.fromisoformat(item["end"])
        filed = date.fromisoformat(item["filed"])

    except (KeyError, TypeError, ValueError):
        return None

    if not (start <= end <= filed < CUTOFF):
        return None

    duration = (end - start).days + 1

    if not (70 <= duration <= 400):
        return None

    return end, filed, duration


def summarize(gaap, tags):
    entries = []

    for tag in tags:
        concept = gaap.get(tag)

        if not isinstance(concept, dict):
            continue

        observations = (
            concept.get("units", {})
            .get("USD", [])
        )

        for observation in observations:
            period = admissible(observation)

            if period is not None:
                entries.append((*period, tag))

    if not entries:
        return {
            "tags": (),
            "latest": "—",
            "filing": "—",
            "direct_ends": 0,
        }

    latest = max(
        entries,
        key=lambda item: (item[0], item[1])
    )

    return {
        "tags": sorted({
            item[3] for item in entries
        }),
        "latest": latest[0].isoformat(),
        "filing": latest[1].isoformat(),
        "direct_ends": len({
            item[0]
            for item in entries
            if 70 <= item[2] <= 110
        }),
    }


def load_policy():
    policy = read_json(
        CONFIG / "universe_candidates_v05.json"
    )

    baseline = read_json(
        CONFIG / "companies.json"
    )

    screen = read_json(
        CONFIG / "screening_rules_v03.json"
    )

    require(
        policy["version"] == 1,
        "Candidate config version changed"
    )

    require(
        policy["research_as_of"] == CUTOFF.isoformat(),
        "Cutoff changed"
    )

    require(
        tuple(policy["existing_tickers"]) == EXISTING,
        "Historical universe changed"
    )

    require(
        tuple(
            company["ticker"]
            for company in baseline["companies"]
        ) == EXISTING,
        "Protected company config changed"
    )

    require(
        set(screen["expected_tickers"]) == set(EXISTING),
        "Screen policy changed"
    )

    candidates = policy["candidate_companies"]

    require(
        tuple(
            company["ticker"]
            for company in candidates
        ) == TICKERS,
        "Candidate list changed"
    )

    for company in candidates:
        require(
            company["onboarding_status"] == "PENDING_REVIEW",
            "Candidate approved too soon"
        )

        require(
            company["calendar_status"] == "UNVERIFIED",
            "Calendar not audited"
        )

    return candidates


def main():
    candidates = load_policy()
    sec_ciks = get_sec_directory()

    report = [
        "# V0.5 — Candidate SEC Financial Tag Preflight",
        "",
        f"**Historical cutoff:** {CUTOFF} (filings strictly earlier)",
        "**State:** FINANCIAL_TAG_CANDIDATES_ONLY — NOT ONBOARDED",
        "",
        "| Ticker | Revenue | Operating income | OCF | CAPEX | Latest revenue period | Direct revenue period ends |",
        "|---|---|---|---|---|---|---:|",
    ]

    details = []
    total_missing = 0

    print("CANDIDATE FINANCIAL TAG PREFLIGHT V0.5")
    print("=" * 62)

    for company in candidates:
        ticker = company["ticker"]

        raw_file = (
            RAW / f"{ticker.lower()}_companyfacts.json"
        )

        meta_file = (
            RAW / f"{ticker.lower()}_companyfacts.meta.json"
        )

        require(
            raw_file.exists() and meta_file.exists(),
            f"Missing SEC snapshot: {ticker}"
        )

        raw = raw_file.read_bytes()
        meta = read_json(meta_file)
        document = json.loads(raw)

        checksum = hashlib.sha256(raw).hexdigest()

        require(
            meta.get("sha256") == checksum,
            f"{ticker}: SHA-256 mismatch"
        )

        require(
            meta.get("size_bytes") == len(raw),
            f"{ticker}: Size mismatch"
        )

        require(
            meta.get("ticker") == ticker,
            f"{ticker}: Metadata ticker mismatch"
        )

        expected_cik = sec_ciks[ticker]

        meta_cik = normalize_cik(
            meta.get("cik"),
            f"{ticker}: Metadata"
        )

        facts_cik = normalize_cik(
            document.get("cik"),
            f"{ticker}: Company Facts"
        )

        require(
            meta_cik == facts_cik == expected_cik,
            (
                f"{ticker}: CIK identity mismatch "
                f"(meta={meta_cik}, "
                f"companyfacts={facts_cik}, "
                f"SEC={expected_cik})"
            )
        )

        expected_url = (
            "https://data.sec.gov/api/xbrl/"
            f"companyfacts/CIK{expected_cik}.json"
        )

        require(
            meta.get("source_url") == expected_url,
            f"{ticker}: Source URL mismatch"
        )

        require(
            meta.get("research_as_of") == CUTOFF.isoformat(),
            f"{ticker}: Cutoff mismatch"
        )

        require(
            meta.get("historical_pit_approved") is False,
            f"{ticker}: Unexpected PIT approval"
        )

        gaap = (
            document.get("facts", {})
            .get("us-gaap", {})
        )

        require(
            isinstance(gaap, dict) and bool(gaap),
            f"{ticker}: Missing US-GAAP"
        )

        groups = {
            name: summarize(gaap, tags)
            for name, tags in TAG_GROUPS.items()
        }

        missing = [
            name
            for name, detail in groups.items()
            if not detail["tags"]
        ]

        total_missing += len(missing)

        labels = [
            "CANDIDATE" if groups[name]["tags"] else "REVIEW"
            for name in TAG_GROUPS
        ]

        revenue = groups["Revenue"]

        report.append(
            f"| {ticker} | {' | '.join(labels)} | "
            f"{revenue['latest']} | "
            f"{revenue['direct_ends']} |"
        )

        details.extend([
            f"### {ticker}",
            "",
            f"- Verified CIK: `{expected_cik}`",
            f"- Raw SHA-256: `{checksum}`",
            (
                "- Missing candidate groups: "
                + (
                    ", ".join(missing)
                    if missing else "None"
                )
            ),
        ])

        for name, result in groups.items():
            tags = (
                ", ".join(result["tags"])
                if result["tags"] else "NONE"
            )

            details.append(
                f"- {name}: tags={tags}; "
                f"latest period end={result['latest']}; "
                f"latest eligible filing={result['filing']}; "
                f"direct-length period ends={result['direct_ends']}"
            )

        details.append("")

        print(
            f"{ticker}: CIK={expected_cik} "
            f"| groups={4 - len(missing)}/4 "
            f"| latest revenue={revenue['latest']} "
            f"| missing={','.join(missing) or 'none'}"
        )

    report.extend([
        "",
        "## Candidate concepts and provenance",
        "",
        *details,
        "## Interpretation",
        "",
        "- A CANDIDATE tag is present, but its financial-statement definition is not approved.",
        "- Direct-length periods are 70–110 days, not 12 validated fiscal quarters.",
        "- Alternative taxonomy tags may represent different accounting definitions.",
        "- OCF and CAPEX may be year-to-date; standalone quarters have not been reconstructed.",
        "- Same-day filings are excluded pending acceptance-time verification.",
        "- A filed date alone does not establish complete point-in-time availability.",
        "- Existing four-company DuckDB tables and reports were not accessed or modified.",
        "- Fiscal calendars, full 12-quarter coverage, FCF and valuation remain PENDING_REVIEW.",
        "",
        "**Decision: DISCOVERY_ONLY — NO NEW COMPANY ADMITTED.**",
        "",
    ])

    REPORTS.mkdir(
        parents=True,
        exist_ok=True
    )

    output = (
        REPORTS /
        f"candidate_tag_preflight_v05_{CUTOFF}.md"
    )

    content = "\n".join(report)

    if output.exists():
        require(
            output.read_text(encoding="utf-8") == content,
            "Existing report differs; refusing overwrite"
        )

        action = "VERIFIED EXISTING"

    else:
        with output.open(
            "x",
            encoding="utf-8"
        ) as handle:
            handle.write(content)

        action = "CREATED"

    print("Candidate groups missing:", total_missing)

    print(
        "DuckDB: NOT ACCESSED | "
        "Existing outputs: PRESERVED"
    )

    print(
        "Report:",
        output.relative_to(ROOT),
        action
    )

    print(
        "Candidate tag preflight: "
        "PASS (discovery only)"
    )


if __name__ == "__main__":
    main()