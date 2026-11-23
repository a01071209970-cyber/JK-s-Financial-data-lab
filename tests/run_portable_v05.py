
"""JK's Financial Data Lab V0.5 - Portable regression runner.

Run:
    python tests/run_portable_v05.py

Executes exactly 8 committed-artifact tests.
Does not require raw SEC data, DuckDB, or network access.

Local-only tests 09 and 10 must be run separately.
"""

import sys
import unittest

from test_regression_v05 import FinancialDataLabRegressionV05


PORTABLE_TESTS = (
    "test_01_config_dates_and_universe",
    "test_02_fundamental_baseline",
    "test_03_original_valuation_decisions",
    "test_04_integrated_guardrails",
    "test_05_price_provenance_in_committed_reports",
    "test_06_pit_evidence_and_pltr_share_math",
    "test_07_pltr_note_bridge_and_valuation",
    "test_08_preview_math_amd_msft",
)

LOCAL_ONLY_TESTS = (
    "test_09_raw_market_price_checksum_and_market_cap",
    "test_10_duckdb_counts_and_historical_regression",
)


def main():
    expected = set(PORTABLE_TESTS) | set(LOCAL_ONLY_TESTS)

    discovered = {
        name
        for name in dir(FinancialDataLabRegressionV05)
        if name.startswith("test_")
    }

    if discovered != expected:
        print(
            "FAIL: Regression test inventory changed.",
            file=sys.stderr,
        )

        print(
            "Missing:",
            sorted(expected - discovered),
            file=sys.stderr,
        )

        print(
            "Unexpected:",
            sorted(discovered - expected),
            file=sys.stderr,
        )

        return 1

    suite = unittest.TestSuite(
        FinancialDataLabRegressionV05(method)
        for method in PORTABLE_TESTS
    )

    print()
    print("JK's FINANCIAL DATA LAB")
    print("V0.5 PORTABLE REGRESSION")
    print("=" * 55)

    print("Expected portable tests:", len(PORTABLE_TESTS))
    print("Local-only tests excluded:", len(LOCAL_ONLY_TESTS))
    print("Network access: NOT REQUIRED")
    print("DuckDB: NOT REQUIRED")
    print()

    result = unittest.TextTestRunner(
        verbosity=2,
        stream=sys.stdout,
    ).run(suite)

    success = (
        result.wasSuccessful()
        and result.testsRun == len(PORTABLE_TESTS)
        and len(result.skipped) == 0
    )

    print()
    print("=" * 55)

    if success:
        print("Portable regression: PASS")
        print("Tests: 8/8")
        print("Skipped: 0")
        print("Failed: 0")
        return 0

    print("Portable regression: FAIL")
    print("Executed:", result.testsRun)
    print("Skipped:", len(result.skipped))
    print("Failures:", len(result.failures))
    print("Errors:", len(result.errors))

    return 1


if __name__ == "__main__":
    sys.exit(main())