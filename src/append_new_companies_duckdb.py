
"""
JK's Financial Data Lab V1.0
Week 4 - Safe Multi-Company SEC Ingestion

Adds AMD and MSFT SEC facts to existing DuckDB.

Safeguards:
- Preserves PLTR and NVDA observations
- Does not rebuild existing quarterly metrics
- Does not modify FCF reconciliation tables
- Uses staging tables and a transaction
- Rejects duplicate ingestion

Usage:
    python src/append_new_companies_duckdb.py
    python src/append_new_companies_duckdb.py --apply

Default mode: DRY RUN (no database changes).
"""

import argparse
import csv
import hashlib
import json
import math
import tempfile

from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parent.parent

DB = ROOT / "data/processed/financial_data.duckdb"

COMPANY_CONFIG = ROOT / "config/companies.json"

RAW_DIR = ROOT / "data/raw"

EXPECTED_NEW = {
    "AMD": 24244,
    "MSFT": 33058
}

EXPECTED_EXISTING = {
    "PLTR": 8134,
    "NVDA": 27281
}

EXPECTED_TOTAL = (
    sum(EXPECTED_NEW.values())
    + sum(EXPECTED_EXISTING.values())
)

NULL_TOKEN = "__JK_FINANCIAL_DATA_NULL__"

FACT_COLUMNS = [
    "cik",
    "ticker",
    "taxonomy",
    "tag",
    "label",
    "unit",
    "period_start",
    "period_end",
    "value_raw",
    "value_num",
    "form",
    "filed",
    "accn",
    "fy",
    "fp",
    "frame"
]

COMPANY_COLUMNS = [
    "ticker",
    "cik",
    "company_name",
    "calendar_type",
    "fiscal_calendar_json",
    "source_file",
    "source_sha256",
    "source_observations"
]

PROTECTED_TABLES = [
    "financial_facts",
    "quarterly_metrics",
    "quarterly_metrics_multi",
    "quarterly_metrics_reconciled",
    "company_fcf_reconciliations"
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scalar(con, query, params=None):
    row = con.execute(
        query,
        params or []
    ).fetchone()

    require(
        row is not None and len(row) == 1,
        "Expected one scalar result"
    )

    return row[0]


def table_counts(con):
    return {
        name: scalar(
            con,
            f"SELECT COUNT(*) FROM {name}"
        )
        for name in PROTECTED_TABLES
    }


def current_company_counts(con):
    rows = con.execute("""
        SELECT ticker, COUNT(*)
        FROM financial_facts_multi
        GROUP BY ticker
    """).fetchall()

    return {
        ticker: int(count)
        for ticker, count in rows
    }


def load_company_configuration():

    config = json.loads(
        COMPANY_CONFIG.read_text(
            encoding="utf-8"
        )
    )

    require(
        config.get("version") == 1,
        "Unsupported company configuration"
    )

    companies = {
        company["ticker"]: company
        for company in config["companies"]
    }

    expected = (
        set(EXPECTED_NEW)
        | set(EXPECTED_EXISTING)
    )

    require(
        set(companies) == expected,
        "Expected PLTR, NVDA, AMD, MSFT"
    )

    require(
        len(config["companies"]) == 4,
        "Duplicate company configuration"
    )

    return companies


def prepare_company(
    ticker,
    company,
    csv_writer
):

    path = (
        RAW_DIR /
        f"{ticker.lower()}_companyfacts.json"
    )

    require(
        path.exists(),
        f"Missing SEC data: {path}"
    )

    raw = path.read_bytes()
    data = json.loads(raw)

    cik = int(company["cik"])

    require(
        int(data["cik"]) == cik,
        f"{ticker}: SEC CIK mismatch"
    )

    sha256 = hashlib.sha256(
        raw
    ).hexdigest()

    observations = 0

    for taxonomy, taxonomy_facts in (
        data["facts"].items()
    ):

        for tag, fact in taxonomy_facts.items():

            label = fact.get("label")

            for unit, entries in (
                fact["units"].items()
            ):

                for item in entries:

                    value = item.get("val")

                    require(
                        isinstance(
                            value, (int, float)
                        )
                        and not isinstance(value, bool),
                        (
                            f"{ticker}: Invalid numeric "
                            f"value for {tag}"
                        )
                    )

                    require(
                        math.isfinite(float(value)),
                        (
                            f"{ticker}: Non-finite "
                            f"value for {tag}"
                        )
                    )

                    require(
                        item.get("end") is not None
                        and item.get("filed") is not None,
                        (
                            f"{ticker}: Missing dates "
                            f"for {tag}"
                        )
                    )

                    record = [
                        cik,
                        ticker,
                        taxonomy,
                        tag,
                        label,
                        unit,
                        item.get("start"),
                        item.get("end"),
                        str(value),
                        value,
                        item.get("form"),
                        item.get("filed"),
                        item.get("accn"),
                        item.get("fy"),
                        item.get("fp"),
                        item.get("frame")
                    ]

                    csv_writer.writerow([
                        NULL_TOKEN
                        if field is None
                        else field
                        for field in record
                    ])

                    observations += 1

    require(
        observations == EXPECTED_NEW[ticker],
        (
            f"{ticker}: Source count changed. "
            f"Expected {EXPECTED_NEW[ticker]:,}, "
            f"received {observations:,}"
        )
    )

    metadata = (
        ticker,
        cik,
        company["company_name"],
        company["fiscal_calendar"]["type"],
        json.dumps(
            company["fiscal_calendar"],
            sort_keys=True
        ),
        str(path.relative_to(ROOT)),
        sha256,
        observations
    )

    print(
        f"Prepared {ticker}: "
        f"{observations:,} observations"
    )

    print("SHA-256:", sha256)

    return metadata


def inspect_existing_database(con):

    existing = current_company_counts(con)

    require(
        existing == EXPECTED_EXISTING,
        (
            "Existing multi-company facts are not "
            f"the expected Week 3 baseline: {existing}"
        )
    )

    company_rows = con.execute("""
        SELECT ticker, COUNT(*)
        FROM companies_multi
        GROUP BY ticker
    """).fetchall()

    registered = {
        ticker: count
        for ticker, count in company_rows
    }

    require(
        registered == {
            "PLTR": 1,
            "NVDA": 1
        },
        (
            "Unexpected existing company metadata: "
            f"{registered}"
        )
    )

    protected = table_counts(con)

    require(
        protected["financial_facts"] == 8134,
        "Week 2 facts changed"
    )

    require(
        protected["quarterly_metrics"] == 12,
        "Week 2 metrics changed"
    )

    require(
        protected["quarterly_metrics_multi"] == 24,
        "Week 3 raw quarterly table changed"
    )

    require(
        protected["quarterly_metrics_reconciled"] == 24,
        "Week 3 reconciled quarters changed"
    )

    require(
        protected["company_fcf_reconciliations"] == 2,
        "FCF reconciliation records changed"
    )

    return protected


def make_stage_tables(con):

    facts = ", ".join(FACT_COLUMNS)

    companies = ", ".join(COMPANY_COLUMNS)

    con.execute(f"""
        CREATE TEMP TABLE stage_week4_facts AS
        SELECT {facts}
        FROM financial_facts_multi
        WHERE FALSE
    """)

    con.execute(f"""
        CREATE TEMP TABLE stage_week4_companies AS
        SELECT {companies}
        FROM companies_multi
        WHERE FALSE
    """)


def load_staging_csv(con, csv_path):

    # The path is generated locally by tempfile.
    safe_path = str(csv_path).replace(
        "'", "''"
    )

    con.execute(f"""
        COPY stage_week4_facts
        FROM '{safe_path}'
        (
            FORMAT CSV,
            HEADER TRUE,
            DELIMITER ',',
            QUOTE '"',
            ESCAPE '"',
            NULL '{NULL_TOKEN}'
        )
    """)

    staged_rows = con.execute("""
        SELECT ticker, COUNT(*)
        FROM stage_week4_facts
        GROUP BY ticker
    """).fetchall()

    staged = {
        ticker: count
        for ticker, count in staged_rows
    }

    require(
        staged == EXPECTED_NEW,
        f"Staging count mismatch: {staged}"
    )

    bad_rows = scalar(
        con,
        """
        SELECT COUNT(*)
        FROM stage_week4_facts
        WHERE
            cik IS NULL
            OR ticker IS NULL
            OR tag IS NULL
            OR unit IS NULL
            OR period_end IS NULL
            OR filed IS NULL
            OR value_num IS NULL
        """
    )

    require(
        bad_rows == 0,
        f"Invalid staged observations: {bad_rows}"
    )

    print()
    print("Staging validation: PASS")


def apply_new_companies(
    con,
    metadata,
    before_protected
):

    placeholders = ", ".join(
        "?" for _ in COMPANY_COLUMNS
    )

    con.executemany(
        f"""
        INSERT INTO stage_week4_companies
        VALUES ({placeholders})
        """,
        metadata
    )

    company_columns = ", ".join(
        COMPANY_COLUMNS
    )

    fact_columns = ", ".join(
        FACT_COLUMNS
    )

    con.execute("BEGIN TRANSACTION")

    try:
        # Append company metadata.
        con.execute(f"""
            INSERT INTO companies_multi
                ({company_columns})
            SELECT {company_columns}
            FROM stage_week4_companies
        """)

        # Append only AMD and MSFT SEC facts.
        con.execute(f"""
            INSERT INTO financial_facts_multi
                ({fact_columns})
            SELECT {fact_columns}
            FROM stage_week4_facts
        """)

        after_facts = current_company_counts(con)

        expected_facts = {
            **EXPECTED_EXISTING,
            **EXPECTED_NEW
        }

        require(
            after_facts == expected_facts,
            (
                "Post-ingestion company counts "
                f"do not match: {after_facts}"
            )
        )

        total_facts = scalar(
            con,
            """
            SELECT COUNT(*)
            FROM financial_facts_multi
            """
        )

        require(
            total_facts == EXPECTED_TOTAL,
            "Total observation count mismatch"
        )

        registered_companies = scalar(
            con,
            """
            SELECT COUNT(*)
            FROM companies_multi
            """
        )

        require(
            registered_companies == 4,
            "Expected four registered companies"
        )

        # None of the protected tables may change.
        after_protected = table_counts(con)

        require(
            before_protected == after_protected,
            "A protected table count changed"
        )

        # Confirm the original companies survived.
        for ticker, count in EXPECTED_EXISTING.items():
            require(
                after_facts[ticker] == count,
                f"{ticker}: Historical facts changed"
            )

        # Commit only after every check succeeds.
        con.execute("COMMIT")

    except Exception:
        con.execute("ROLLBACK")
        raise

    print()
    print("FOUR-COMPANY INGESTION RESULT")
    print("-" * 55)

    for ticker in sorted(after_facts):
        print(
            f"{ticker}: "
            f"{after_facts[ticker]:,} observations"
        )

    print()
    print(f"Total observations: {total_facts:,}")
    print("Original Week 2 tables: PRESERVED")
    print("Week 3 quarterly tables: PRESERVED")
    print("Company FCF reconciliations: PRESERVED")
    print("New companies: AMD, MSFT")
    print("Four-company ingestion: PASS")


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Append AMD and MSFT to DuckDB"
    )

    args = parser.parse_args()

    companies = load_company_configuration()

    require(
        DB.exists(),
        f"Database not found: {DB}"
    )

    # Prepare the complete new data in a
    # temporary CSV before touching DuckDB.
    with tempfile.TemporaryDirectory(
        prefix="jk_week4_ingest_"
    ) as temporary:

        csv_path = (
            Path(temporary) /
            "new_company_facts.csv"
        )

        metadata = []

        with csv_path.open(
            "w",
            encoding="utf-8",
            newline=""
        ) as file:

            writer = csv.writer(file)

            writer.writerow(
                FACT_COLUMNS
            )

            for ticker in (
                "AMD",
                "MSFT"
            ):
                metadata.append(
                    prepare_company(
                        ticker,
                        companies[ticker],
                        writer
                    )
                )

        # A dry run uses a read-only connection.
        con = duckdb.connect(
            str(DB),
            read_only=not args.apply
        )

        try:
            before_protected = (
                inspect_existing_database(con)
            )

            print()
            print("DATABASE PRECHECK")
            print("-" * 55)

            print(
                "Existing observations:",
                f"{sum(EXPECTED_EXISTING.values()):,}"
            )

            print(
                "New observations:",
                f"{sum(EXPECTED_NEW.values()):,}"
            )

            print(
                "Expected total:",
                f"{EXPECTED_TOTAL:,}"
            )

            print("Protected tables: VERIFIED")

            if not args.apply:

                print()
                print("Mode: DRY RUN")
                print("Database: UNCHANGED")
                print("Pre-ingestion audit: PASS")
                return

            make_stage_tables(con)

            load_staging_csv(
                con,
                csv_path
            )

            apply_new_companies(
                con,
                metadata,
                before_protected
            )

        finally:
            con.close()


if __name__ == "__main__":
    main()