
import argparse
import calendar
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config/companies.json"


# 1. Load and validate company configuration
def load_companies():
    config = json.loads(
        CONFIG.read_text(encoding="utf-8")
    )

    if config.get("version") != 1:
        raise ValueError(
            "Unsupported configuration version"
        )

    companies = config["companies"]

    tickers = [c["ticker"] for c in companies]
    ciks = [c["cik"] for c in companies]

    if (len(tickers) != len(set(tickers))
            or len(ciks) != len(set(ciks))):
        raise ValueError("Duplicate ticker or CIK")

    for c in companies:
        if (not c["ticker"].isupper()
                or not c["company_name"].strip()):
            raise ValueError(
                "Invalid company name or ticker"
            )

        if (len(c["cik"]) != 10
                or not c["cik"].isdigit()):
            raise ValueError(
                f"Invalid CIK: {c['ticker']}"
            )

        if c["fiscal_calendar"]["type"] not in (
            "calendar_quarters",
            "week_52_53"
        ):
            raise ValueError(
                f"Unsupported calendar: {c['ticker']}"
            )

    return companies


# 2. Move forward a number of calendar months
def add_months(first_day, number):
    month_index = (
        first_day.year * 12
        + first_day.month - 1
        + number
    )

    year, month_zero = divmod(month_index, 12)

    day = min(
        first_day.day,
        calendar.monthrange(
            year, month_zero + 1
        )[1]
    )

    return date(year, month_zero + 1, day)


# 3. Calculate fiscal-year ending date

def fiscal_year_end(rule, fiscal_year):
    """
    Calculate the fiscal year-end date.

    Supports:
    1. Calendar-quarter fiscal years
    2. 52/53-week fiscal years ending on the
       last specified weekday of a month

    Examples:
    - NVDA: last Sunday of January
    - AMD: last Saturday of December
    """

    from datetime import date, timedelta

    calendar_type = rule["type"]

    # Standard calendar-based fiscal year
    if calendar_type == "calendar_quarters":
        return date(
            fiscal_year,
            rule["year_end_month"],
            rule["year_end_day"]
        )

    if calendar_type != "week_52_53":
        raise ValueError(
            f"Unsupported calendar type: {calendar_type}"
        )

    # Currently, only the 'last weekday' rule
    # is implemented.
    if rule["year_end_rule"] != "last":
        raise ValueError(
            "Only the 'last weekday' rule is supported"
        )

    weekday_map = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6
    }

    weekday_name = rule[
        "year_end_weekday"
    ].lower()

    if weekday_name not in weekday_map:
        raise ValueError(
            f"Unsupported weekday: {weekday_name}"
        )

    target_weekday = weekday_map[
        weekday_name
    ]

    year_end_month = rule[
        "year_end_month"
    ]

    # Find the final calendar day of
    # the specified month.
    if year_end_month == 12:
        last_day = date(
            fiscal_year, 12, 31
        )
    else:
        first_day_next_month = date(
            fiscal_year,
            year_end_month + 1,
            1
        )

        last_day = (
            first_day_next_month
            - timedelta(days=1)
        )

    # Move backwards to the last matching
    # weekday in that month.
    days_back = (
        last_day.weekday() - target_weekday
    ) % 7

    return last_day - timedelta(
        days=days_back
    )


# 4. Generate fiscal-quarter start and end dates
def periods(company, fiscal_year):
    rule = company["fiscal_calendar"]

    start = (
        fiscal_year_end(rule, fiscal_year - 1)
        + timedelta(days=1)
    )

    end = fiscal_year_end(rule, fiscal_year)

    result = []
    cursor = start

    for q in range(1, 5):

        if rule["type"] == "calendar_quarters":
            quarter_end = (
                add_months(start, 3 * q)
                - timedelta(days=1)
            )

        else:
            weeks = rule["quarter_weeks"]

            if weeks != [13, 13, 13]:
                raise ValueError(
                    "Expected 13 weeks in Q1-Q3"
                )

            if q < 4:
                quarter_end = (
                    cursor
                    + timedelta(weeks=13)
                    - timedelta(days=1)
                )
            else:
                quarter_end = end

        if quarter_end < cursor or quarter_end > end:
            raise ValueError(
                f"Invalid FY{fiscal_year} Q{q} period"
            )

        result.append({
            "quarter": q,
            "start": cursor,
            "end": quarter_end,
            "days": (
                quarter_end - cursor
            ).days + 1
        })

        cursor = quarter_end + timedelta(days=1)

    # No gaps or overlaps in fiscal year
    if cursor != end + timedelta(days=1):
        raise ValueError(
            "Quarter calendar does not cover fiscal year"
        )

    # A 52/53-week fiscal year has 364/371 days
    if rule["type"] == "week_52_53":
        total_days = sum(
            p["days"] for p in result
        )

        if total_days not in (364, 371):
            raise ValueError(
                "52/53-week calendar expected"
            )

    return result


# 5. Verify fiscal calendars against known dates
def self_test(companies):
    by_ticker = {
        c["ticker"]: c for c in companies
    }

    expected = {
        ("PLTR", 2026): [
            "2026-03-31",
            "2026-06-30",
            "2026-09-30",
            "2026-12-31"
        ],
        ("NVDA", 2026): [
            "2025-04-27",
            "2025-07-27",
            "2025-10-26",
            "2026-01-25"
        ],
        ("NVDA", 2027): [
            "2026-04-26",
            "2026-07-26",
            "2026-10-25",
            "2027-01-31"
        ]
    }

    for (ticker, fy), dates in expected.items():

        actual = [
            str(p["end"])
            for p in periods(
                by_ticker[ticker], fy
            )
        ]

        if actual != dates:
            raise AssertionError(
                f"{ticker} FY{fy}: "
                f"{actual} != {dates}"
            )

    # FY2027 has a 14-week Q4 for NVIDIA
    assert (
        periods(by_ticker["NVDA"], 2027)[3]["days"]
        == 98
    )

    print("Calendar self-test: PASS")


# 6. Main entry point
def main():
    parser = argparse.ArgumentParser(
        description="Inspect SEC company fiscal calendars"
    )

    parser.add_argument(
        "--ticker",
        help="PLTR or NVDA (default: both)"
    )

    parser.add_argument(
        "--fy",
        type=int,
        default=2026,
        help="Fiscal-year label, default: 2026"
    )

    args = parser.parse_args()

    companies = load_companies()
    self_test(companies)

    selected = [
        c for c in companies
        if args.ticker is None
        or c["ticker"] == args.ticker.upper()
    ]

    if not selected:
        parser.error(
            "Ticker not present in config/companies.json"
        )

    for company in selected:
        ticker = company["ticker"]

        print(
            f"\n{ticker} | "
            f"{company['company_name']} | "
            f"CIK {company['cik']}"
        )

        print(
            "SEC: https://data.sec.gov/api/xbrl/"
            f"companyfacts/CIK{company['cik']}.json"
        )

        print(f"Fiscal year FY{args.fy}:")

        for p in periods(company, args.fy):
            print(
                f"  Q{p['quarter']}: "
                f"{p['start']} ~ {p['end']} "
                f"({p['days']} days)"
            )

    print("\nConfig validation: PASS")


if __name__ == "__main__":
    main()