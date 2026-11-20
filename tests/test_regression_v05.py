
"""V0.5 regression suite for JK's Financial Data Lab.

Run from the project root:
    python -m unittest discover -s tests -p 'test_regression_v05.py' -v

Committed artifacts are always tested.
Local-only raw data and DuckDB are tested when present.
No network requests or source-file modifications.
"""

import csv
import hashlib
import json
import unittest

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

try:
    import duckdb
except ImportError:
    duckdb = None


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
CONFIG = ROOT / "config"

AS_OF = "2026-11-17"

TICKERS = {"NVDA", "PLTR", "AMD", "MSFT"}

EXPECTED_FUNDAMENTAL = {
    "NVDA": "PASS",
    "PLTR": "PASS",
    "AMD": "PASS",
    "MSFT": "FAIL",
}

EXPECTED_VALUATION = {
    "NVDA": "BLOCKED_SHARE_COUNT",
    "PLTR": "INDICATIVE_NOTE_BASED",
    "AMD": "INDICATIVE",
    "MSFT": "INDICATIVE",
}

B = Decimal("1000000000")


def load_json(path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def load_csv(path):
    with path.open(
        newline="",
        encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))

    if len(rows) != 4:
        raise AssertionError(
            f"Expected four rows in {path}: got {len(rows)}"
        )

    keyed = {
        row["ticker"]: row
        for row in rows
    }

    if (
        set(keyed) != TICKERS
        or len(keyed) != len(rows)
    ):
        raise AssertionError(
            f"Unexpected or repeated ticker in {path}"
        )

    return keyed


def D(value):
    result = Decimal(str(value))

    if not result.is_finite():
        raise AssertionError(
            f"Nonfinite numeric input: {value}"
        )

    return result


class FinancialDataLabRegressionV05(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rules = load_json(
            CONFIG / "screening_rules_v03.json"
        )

        cls.valuation_policy = load_json(
            CONFIG / "valuation_input_policy.json"
        )

        cls.pit = load_json(
            CONFIG / "pit_evidence_v04.json"
        )

        cls.pltr_note = load_json(
            CONFIG / "pltr_valuation_evidence_v041.json"
        )

        cls.screen = load_csv(
            REPORTS / f"screen_v03_{AS_OF}.csv"
        )

        cls.preview = load_csv(
            REPORTS / f"valuation_preview_v04_{AS_OF}.csv"
        )

        cls.integrated = load_csv(
            REPORTS / f"integrated_screen_v042_{AS_OF}.csv"
        )

    def test_01_config_dates_and_universe(self):
        self.assertEqual(
            self.rules["version"],
            3
        )

        self.assertEqual(
            set(self.rules["expected_tickers"]),
            TICKERS
        )

        configs = (
            self.rules,
            self.valuation_policy,
            self.pit,
            self.pltr_note
        )

        for config in configs:
            self.assertEqual(
                config["as_of_date"],
                AS_OF
            )

        missing_policy = (
            self.valuation_policy["methodology"]
            .get("missing_policy", "")
        )

        self.assertFalse(
            missing_policy.startswith("zero")
        )

    def test_02_fundamental_baseline(self):
        statuses = {
            ticker: self.screen[ticker][
                "fundamental_status"
            ]
            for ticker in TICKERS
        }

        self.assertEqual(
            statuses,
            EXPECTED_FUNDAMENTAL
        )

        observed_order = sorted(
            self.screen,
            key=lambda ticker: D(
                self.screen[ticker][
                    "quarterly_revenue_yoy_pct"
                ]
            ),
            reverse=True
        )

        self.assertEqual(
            observed_order,
            ["NVDA", "PLTR", "AMD", "MSFT"]
        )

        self.assertEqual(
            D(self.screen["NVDA"][
                "quarterly_revenue_yoy_pct"
            ]),
            D("105.85")
        )

        self.assertEqual(
            D(self.screen["MSFT"][
                "quarterly_revenue_yoy_pct"
            ]),
            D("18.80")
        )

    def test_03_original_valuation_decisions(self):
        expected = {
            "NVDA": "BLOCKED",
            "PLTR": "BLOCKED",
            "AMD": "INDICATIVE",
            "MSFT": "INDICATIVE"
        }

        for ticker in TICKERS:
            row = self.preview[ticker]

            self.assertEqual(
                row["valuation_status"],
                expected[ticker]
            )

            if expected[ticker] == "BLOCKED":
                self.assertEqual(
                    row["ev_base_usd_b"],
                    ""
                )

                self.assertEqual(
                    row["ev_sales_base"],
                    ""
                )

    def test_04_integrated_guardrails(self):
        for ticker in TICKERS:
            row = self.integrated[ticker]

            self.assertEqual(
                row["valuation_status"],
                EXPECTED_VALUATION[ticker]
            )

            self.assertEqual(
                row["fundamental_status"],
                EXPECTED_FUNDAMENTAL[ticker]
            )

            self.assertEqual(
                row["quarter_revenue_yoy_pct"],
                self.screen[ticker][
                    "quarterly_revenue_yoy_pct"
                ]
            )

            self.assertEqual(
                row["as_of_date"],
                AS_OF
            )

        nvda = self.integrated["NVDA"]

        self.assertEqual(
            nvda["indicative_ev_usd_b"],
            ""
        )

        self.assertEqual(
            nvda["ev_sales"],
            ""
        )

        self.assertEqual(
            nvda["ev_ebit"],
            ""
        )

        self.assertEqual(
            self.integrated["PLTR"]["ev_sales"],
            "50.34"
        )

        self.assertEqual(
            self.integrated["AMD"]["ev_ebit"],
            "101.48"
        )

        self.assertEqual(
            self.integrated["MSFT"]["ev_ebit"],
            "22.86"
        )

    def test_05_price_provenance_in_committed_reports(self):
        metadata_hash = (
            "8496e2e2405d3802f80de4b9db8d595"
            "f5a56dded60e5785aa96b7d0ef6eee95d"
        )

        for ticker in TICKERS:
            self.assertEqual(
                self.preview[ticker][
                    "source_price_csv_sha256"
                ],
                metadata_hash
            )

        narrative = (
            REPORTS /
            f"integrated_screen_v042_{AS_OF}.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            metadata_hash,
            narrative
        )

        self.assertIn(
            "NVIDIA",
            narrative
        )

        self.assertIn(
            "BLOCKED",
            narrative
        )

    def test_06_pit_evidence_and_pltr_share_math(self):
        classes = self.pit["pltr"][
            "cover_class_shares"
        ]

        self.assertEqual(
            sum(classes.values()),
            2_409_497_474
        )

        price_date = date.fromisoformat(
            AS_OF
        )

        share_date = date.fromisoformat(
            self.pit["pltr"]["cover_share_date"]
        )

        self.assertEqual(
            (price_date - share_date).days,
            22
        )

        cutoff = datetime.fromisoformat(
            self.pit["market_close_et"]
        )

        nvda_accepted = datetime.fromisoformat(
            self.pit["nvda"][
                "filing_accepted_at_et"
            ]
        )

        self.assertIsNotNone(
            cutoff.tzinfo
        )

        self.assertIsNotNone(
            nvda_accepted.tzinfo
        )

        self.assertEqual(
            int(
                (
                    nvda_accepted - cutoff
                ).total_seconds()
            ),
            1251
        )

        self.assertFalse(
            self.pit["nvda"][
                "share_count_review_complete"
            ]
        )

    def test_07_pltr_note_bridge_and_valuation(self):
        note = self.pltr_note

        treasury = D(
            note["us_treasury_securities_usd"]
        )

        equity_security = D(
            note["public_equity_securities_usd"]
        )

        self.assertEqual(
            treasury + equity_security,
            D(
                note["marketable_securities_total_usd"]
            )
        )

        self.assertEqual(
            D(
                note["assumed_financial_borrowings_usd"]
            ),
            0
        )

        cap = D(
            self.integrated["PLTR"][
                "indicative_market_cap_usd_b"
            ]
        )

        ev = cap - (
            D(note["cash_usd"]) + treasury
        ) / B

        self.assertLessEqual(
            abs(
                ev - D(
                    self.integrated["PLTR"][
                        "indicative_ev_usd_b"
                    ]
                )
            ),
            D("0.001")
        )

        self.assertEqual(
            self.integrated["PLTR"][
                "valuation_status"
            ],
            "INDICATIVE_NOTE_BASED"
        )

    def test_08_preview_math_amd_msft(self):
        for ticker in ("AMD", "MSFT"):
            row = self.preview[ticker]

            cap = D(
                row["indicative_market_cap_usd_b"]
            )

            debt = D(
                row["selected_debt_usd_b"]
            )

            cash = D(
                row["cash_usd_b"]
            )

            investments = D(
                row["selected_investments_usd_b"]
            )

            ev = cap + debt - cash - investments

            self.assertLessEqual(
                abs(
                    ev - D(row["ev_base_usd_b"])
                ),
                D("0.001")
            )

            self.assertEqual(
                row["ev_sales_base"],
                self.integrated[ticker][
                    "ev_sales"
                ]
            )

            self.assertEqual(
                row["ev_ebit_base"],
                self.integrated[ticker][
                    "ev_ebit"
                ]
            )

        msft = self.preview["MSFT"]

        base = D(
            msft["ev_base_usd_b"]
        )

        finance = D(
            msft["finance_lease_usd_b"]
        )

        operating = D(
            msft["operating_lease_usd_b"]
        )

        self.assertEqual(
            base + finance,
            D(
                msft["ev_with_finance_lease_usd_b"]
            )
        )

        self.assertEqual(
            base + finance + operating,
            D(
                msft["ev_with_both_leases_usd_b"]
            )
        )

    @unittest.skipUnless(
        (
            DATA / "raw" /
            f"market_prices_v04_{AS_OF}.csv"
        ).exists(),
        "Local-only market price CSV unavailable"
    )
    def test_09_raw_market_price_checksum_and_market_cap(self):
        path = (
            DATA / "raw" /
            f"market_prices_v04_{AS_OF}.csv"
        )

        meta = load_json(
            DATA / "raw" /
            f"market_prices_v04_{AS_OF}.meta.json"
        )

        digest = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

        self.assertEqual(
            digest,
            meta["csv_sha256"]
        )

        quotes = load_csv(path)

        for ticker in TICKERS:
            self.assertEqual(
                quotes[ticker]["price_date"],
                AS_OF
            )

            self.assertEqual(
                quotes[ticker]["currency"],
                "USD"
            )

            shares = D(
                self.preview[ticker][
                    "shares_outstanding"
                ]
            )

            market_cap = (
                D(quotes[ticker]["close_usd"])
                * shares / B
            )

            self.assertLessEqual(
                abs(
                    market_cap - D(
                        self.preview[ticker][
                            "indicative_market_cap_usd_b"
                        ]
                    )
                ),
                D("0.001")
            )

    @unittest.skipUnless(
        (
            duckdb is not None
            and (
                DATA / "processed" /
                "financial_data.duckdb"
            ).exists()
        ),
        "Local-only DuckDB unavailable"
    )
    def test_10_duckdb_counts_and_historical_regression(self):
        path = (
            DATA / "processed" /
            "financial_data.duckdb"
        )

        conn = duckdb.connect(
            str(path),
            read_only=True
        )

        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM financial_facts_multi"
            ).fetchone()[0]

            self.assertEqual(
                count,
                92717
            )

            counts = dict(
                conn.execute("""
                    SELECT ticker, COUNT(*)
                    FROM quarterly_metrics_four_reconciled
                    GROUP BY ticker
                """).fetchall()
            )

            self.assertEqual(
                counts,
                {
                    ticker: 12
                    for ticker in TICKERS
                }
            )

            columns = (
                "ticker, period_end, revenue_usd, "
                "operating_income_usd, ocf_usd, "
                "capex_usd, fcf_usd"
            )

            original = conn.execute(
                f"""
                SELECT {columns}
                FROM quarterly_metrics_reconciled
                ORDER BY ticker, period_end
                """
            ).fetchall()

            expanded = conn.execute(
                f"""
                SELECT {columns}
                FROM quarterly_metrics_four_reconciled
                WHERE ticker IN ('PLTR', 'NVDA')
                ORDER BY ticker, period_end
                """
            ).fetchall()

            self.assertEqual(
                len(original),
                24
            )

            self.assertEqual(
                original,
                expanded
            )

        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()