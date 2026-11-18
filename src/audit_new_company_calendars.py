
"""
JK's Financial Data Lab V1.0
Week 4 - New Company Fiscal Calendar Audit

Validate AMD and MSFT fiscal periods before
fetching SEC data or rebuilding DuckDB.

Read-only: no database changes.
"""

from datetime import date, timedelta

from check_company_config import (
    load_companies,
    periods
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_period(
    company,
    fiscal_year,
    quarter,
    expected_start,
    expected_end
):
    fiscal_periods = periods(
        company,
        fiscal_year
    )

    require(
        len(fiscal_periods) == 4,
        "Fiscal year must have 4 quarters"
    )

    actual = fiscal_periods[quarter - 1]

    actual_start = actual["start"]
    actual_end = actual["end"]

    require(
        actual_start == date.fromisoformat(
            expected_start
        ),
        (
            f"{company['ticker']} FY{fiscal_year} "
            f"Q{quarter}: start date mismatch: "
            f"{actual_start}"
        )
    )

    require(
        actual_end == date.fromisoformat(
            expected_end
        ),
        (
            f"{company['ticker']} FY{fiscal_year} "
            f"Q{quarter}: end date mismatch: "
            f"{actual_end}"
        )
    )

    print(
        f"FY{fiscal_year} Q{quarter}: "
        f"{actual_start} ~ {actual_end} "
        f"| PASS"
    )


def check_continuity(company, fiscal_year):

    fiscal_periods = periods(
        company,
        fiscal_year
    )

    require(
        len(fiscal_periods) == 4,
        "Expected four fiscal quarters"
    )

    for previous, current in zip(
        fiscal_periods,
        fiscal_periods[1:]
    ):

        require(
            previous["end"] + timedelta(days=1)
            == current["start"],
            (
                f"{company['ticker']}: "
                f"Gap between fiscal quarters"
            )
        )

    for period in fiscal_periods:
        require(
            period["start"] <= period["end"],
            "Invalid fiscal period"
        )

    total_days = sum(
        (p["end"] - p["start"]).days + 1
        for p in fiscal_periods
    )

    require(
        total_days in (364, 365, 366, 371),
        (
            f"{company['ticker']}: "
            f"Unexpected fiscal year length "
            f"{total_days}"
        )
    )

    print(
        f"FY{fiscal_year} continuity: PASS "
        f"({total_days} days)"
    )


def main():

    companies = load_companies()

    by_ticker = {
        company["ticker"]: company
        for company in companies
    }

    expected = {
        "PLTR",
        "NVDA",
        "AMD",
        "MSFT"
    }

    require(
        set(by_ticker) == expected,
        "Expected exactly four configured companies"
    )

    require(
        len(companies) == len(by_ticker),
        "Duplicate ticker configuration"
    )

    print("NEW COMPANY CALENDAR AUDIT")
    print("-" * 55)

    # AMD: 52/53-week fiscal calendar
    amd = by_ticker["AMD"]

    print("\nAMD")
    check_period(
        amd, 2026, 1,
        "2025-12-28", "2026-03-28"
    )
    check_period(
        amd, 2026, 2,
        "2026-03-29", "2026-06-27"
    )
    check_period(
        amd, 2026, 3,
        "2026-06-28", "2026-09-26"
    )
    check_period(
        amd, 2026, 4,
        "2026-09-27", "2026-12-26"
    )
    check_continuity(amd, 2026)

    # Microsoft FY2027 begins July 1, 2026
    msft = by_ticker["MSFT"]

    print("\nMSFT")
    check_period(
        msft, 2027, 1,
        "2026-07-01", "2026-09-30"
    )
    check_period(
        msft, 2027, 2,
        "2026-10-01", "2026-12-31"
    )
    check_period(
        msft, 2027, 3,
        "2027-01-01", "2027-03-31"
    )
    check_period(
        msft, 2027, 4,
        "2027-04-01", "2027-06-30"
    )
    check_continuity(msft, 2027)

    # Existing company regression checks
    print("\nPLTR REGRESSION")
    check_period(
        by_ticker["PLTR"], 2026, 3,
        "2026-07-01", "2026-09-30"
    )

    print("\nNVDA REGRESSION")
    check_period(
        by_ticker["NVDA"], 2027, 2,
        "2026-04-27", "2026-07-26"
    )

    print()
    print("Configured companies:", len(companies))
    print("AMD fiscal calendar: PASS")
    print("MSFT fiscal calendar: PASS")
    print("Existing company regression: PASS")
    print("Company onboarding calendar audit: PASS")


if __name__ == "__main__":
    main()
