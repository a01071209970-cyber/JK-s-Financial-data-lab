
-- ==================================================
-- JK's Financial Data Lab V1.0
-- Week 3: Multi-Company Ingestion Audit
-- Companies: PLTR, NVDA
-- ==================================================

WITH expected AS (

    SELECT *
    FROM (
        VALUES
            ('PLTR', 1321655, 8134),
            ('NVDA', 1045810, 27281)
    ) AS t(
        ticker,
        expected_cik,
        expected_rows
    )

),

actual AS (

    SELECT
        ticker,

        COUNT(*) AS actual_rows,

        MIN(cik) AS min_cik,
        MAX(cik) AS max_cik,

        COUNT(*) FILTER (
            WHERE taxonomy = 'us-gaap'
        ) AS us_gaap_rows,

        COUNT(*) FILTER (
            WHERE value_num IS NULL
               OR period_end IS NULL
               OR filed IS NULL
        ) AS invalid_rows

    FROM financial_facts_multi

    GROUP BY ticker

),

metadata AS (

    SELECT
        ticker,
        cik,
        source_observations

    FROM companies_multi

),

known_facts AS (

    SELECT
        ticker,
        COUNT(*) AS matched_facts

    FROM financial_facts_multi

    WHERE
        (
            ticker = 'PLTR'
            AND tag =
                'RevenueFromContractWithCustomerExcludingAssessedTax'
            AND period_start = DATE '2026-07-01'
            AND period_end = DATE '2026-09-30'
            AND value_raw = '2313411000'
        )

        OR

        (
            ticker = 'NVDA'
            AND tag = 'Revenues'
            AND period_start = DATE '2026-04-27'
            AND period_end = DATE '2026-07-26'
            AND value_raw = '96221000000'
        )

    GROUP BY ticker

),

legacy_check AS (

    SELECT

        (
            SELECT COUNT(*)
            FROM financial_facts
            WHERE cik = 1321655
        ) AS original_facts,

        (
            SELECT COUNT(*)
            FROM quarterly_metrics
        ) AS original_quarters,

        (
            SELECT revenue_usd
            FROM quarterly_metrics
            WHERE fiscal_year = 2026
              AND fiscal_quarter = 3
        ) AS original_q3_revenue

)

SELECT

    e.ticker,
    e.expected_rows,

    COALESCE(
        a.actual_rows, 0
    ) AS actual_rows,

    COALESCE(
        a.invalid_rows, 0
    ) AS invalid_rows,

    COALESCE(
        a.us_gaap_rows, 0
    ) AS us_gaap_rows,

    COALESCE(
        k.matched_facts, 0
    ) AS known_fact_matches,

    CASE

        WHEN a.actual_rows = e.expected_rows

         AND a.min_cik = e.expected_cik
         AND a.max_cik = e.expected_cik

         AND a.invalid_rows = 0

         AND a.us_gaap_rows > 0

         AND m.cik = e.expected_cik

         AND m.source_observations =
             e.expected_rows

         AND k.matched_facts > 0

         AND l.original_facts = 8134

         AND l.original_quarters = 12

         AND l.original_q3_revenue =
             2313411000

        THEN 'PASS'

        ELSE 'REVIEW'

    END AS validation_result

FROM expected e

LEFT JOIN actual a
    ON e.ticker = a.ticker

LEFT JOIN metadata m
    ON e.ticker = m.ticker

LEFT JOIN known_facts k
    ON e.ticker = k.ticker

CROSS JOIN legacy_check l

ORDER BY e.ticker;