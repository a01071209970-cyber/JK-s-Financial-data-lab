
-- =====================================================
-- JK's Financial Data Lab V1.0
-- Week 4: Independent Annual FCF Reconciliation Audit
--
-- Checks:
-- 1. Annual SEC facts
-- 2. Sum of four fiscal quarters
-- 3. Simple FCF arithmetic
-- 4. Company-specific FCF adjustments
-- 5. Provenance and data integrity
--
-- Read-only audit
-- =====================================================

WITH expected AS (

    -- Independent reference values for two
    -- previously verified official disclosures

    SELECT *
    FROM (
        VALUES
        (
            'PLTR',
            2025,
            2134473000::DECIMAL(38,0),
            33882000::DECIMAL(38,0),
            169845000::DECIMAL(38,0),
            2270436000::DECIMAL(38,0),
            'ADJUSTED_FREE_CASH_FLOW',
            'EMPLOYER_PAYROLL_TAX_CASH_PAID_ADD_BACK'
        ),
        (
            'NVDA',
            2026,
            102718000000::DECIMAL(38,0),
            6042000000::DECIMAL(38,0),
            -101000000::DECIMAL(38,0),
            96575000000::DECIMAL(38,0),
            'COMPANY_REPORTED_FREE_CASH_FLOW',
            'ASSET_PRINCIPAL_PAYMENTS_DEDUCTION'
        )

    ) AS t(
        ticker,
        fiscal_year,
        expected_ocf,
        expected_capex,
        expected_adjustment,
        expected_reported_fcf,
        expected_fcf_type,
        expected_adjustment_code
    )
),

sec_ranked AS (

    -- Retrieve annual facts independently
    -- from the original multi-company SEC table

    SELECT
        r.ticker,
        r.fiscal_year,
        f.tag,

        TRY_CAST(
            f.value_raw AS DECIMAL(38,0)
        ) AS amount,

        ROW_NUMBER() OVER (
            PARTITION BY
                r.ticker,
                r.fiscal_year,
                f.tag

            ORDER BY
                f.filed ASC,
                f.accn ASC
        ) AS rn

    FROM company_fcf_reconciliations r

    INNER JOIN financial_facts_multi f

      ON f.ticker = r.ticker
     AND f.period_start = r.period_start
     AND f.period_end = r.period_end

     AND f.taxonomy = 'us-gaap'
     AND f.unit = 'USD'

     AND f.form IN ('10-K', '10-K/A')
     AND f.filed <= r.data_cutoff

     AND f.tag IN (
        'NetCashProvidedByUsedInOperatingActivities',
        r.capex_tag
     )
),

sec_annual AS (

    SELECT
        r.ticker,
        r.fiscal_year,

        MAX(
            CASE
                WHEN s.tag =
                'NetCashProvidedByUsedInOperatingActivities'
                THEN s.amount
            END
        ) AS source_ocf,

        MAX(
            CASE
                WHEN s.tag = r.capex_tag
                THEN s.amount
            END
        ) AS source_capex

    FROM company_fcf_reconciliations r

    LEFT JOIN sec_ranked s
      ON s.ticker = r.ticker
     AND s.fiscal_year = r.fiscal_year
     AND s.rn = 1

    GROUP BY
        r.ticker,
        r.fiscal_year
),

quarterly_check AS (

    SELECT
        ticker,
        fiscal_year,

        COUNT(*) AS quarter_count,

        COUNT(DISTINCT fiscal_quarter)
            AS unique_quarter_count,

        MIN(period_start) AS first_start,
        MAX(period_end) AS last_end,

        SUM(ocf_usd) AS quarterly_ocf,
        SUM(capex_usd) AS quarterly_capex,
        SUM(fcf_usd) AS quarterly_fcf,

        COUNT(*) FILTER (
            WHERE validation_status NOT IN (
                'PASS',
                'RECONCILED_SUPPLEMENTAL'
            )
        ) AS unresolved_quarters

    FROM quarterly_metrics_reconciled

    GROUP BY
        ticker,
        fiscal_year
),

adjustment_check AS (

    -- The current source model has exactly
    -- one adjustment item per annual record.

    SELECT
        ticker,
        fiscal_year,

        json_valid(adjustments_json)
            AS valid_json,

        json_array_length(adjustments_json)
            AS adjustment_count,

        json_extract_string(
            adjustments_json,
            '$[0].code'
        ) AS adjustment_code,

        TRY_CAST(
            json_extract_string(
                adjustments_json,
                '$[0].amount_usd'
            )
            AS DECIMAL(38,0)
        ) AS adjustment_from_source

    FROM company_fcf_reconciliations
),

table_integrity AS (

    SELECT
        (
            SELECT COUNT(*)
            FROM company_fcf_reconciliations
        ) AS annual_rows,

        (
            SELECT COUNT(*)
            FROM quarterly_metrics_reconciled
        ) AS reconciled_quarters,

        (
            SELECT COUNT(*)
            FROM quarterly_metrics_multi
        ) AS original_multi_quarters,

        (
            SELECT COUNT(*)
            FROM quarterly_metrics
        ) AS original_week2_quarters
)

SELECT
    e.ticker,
    e.fiscal_year,

    q.quarter_count,

    r.ocf_usd,
    r.capex_usd,

    r.simple_fcf_usd,
    r.adjustment_usd,
    r.company_reported_fcf_usd,

    a.adjustment_count,

    CASE

        WHEN r.ticker IS NOT NULL

         -- Original SEC facts
         AND s.source_ocf = e.expected_ocf
         AND s.source_capex = e.expected_capex

         AND r.ocf_usd = s.source_ocf
         AND r.capex_usd = s.source_capex

         -- All four fiscal quarters
         AND q.quarter_count = 4
         AND q.unique_quarter_count = 4
         AND q.unresolved_quarters = 0

         AND q.first_start = r.period_start
         AND q.last_end = r.period_end

         -- Quarterly to annual reconciliation
         AND q.quarterly_ocf = r.ocf_usd
         AND q.quarterly_capex = r.capex_usd
         AND q.quarterly_fcf = r.simple_fcf_usd

         -- Simple FCF formula
         AND r.simple_fcf_usd =
             r.ocf_usd - r.capex_usd

         -- Company-specific adjustment
         AND r.adjustment_usd =
             e.expected_adjustment

         AND r.company_reported_fcf_usd =
             e.expected_reported_fcf

         AND r.company_reported_fcf_usd =
             r.simple_fcf_usd + r.adjustment_usd

         -- Adjustment JSON traceability
         AND a.valid_json = TRUE
         AND a.adjustment_count = 1

         AND a.adjustment_code =
             e.expected_adjustment_code

         AND a.adjustment_from_source =
             r.adjustment_usd

         -- Definition and source
         AND r.fcf_metric_type =
             e.expected_fcf_type

         AND r.source_url LIKE 'https://%'

         AND r.official_release_date >
             r.period_end

         AND r.official_release_date <=
             r.data_cutoff

         AND r.validation_status = 'PASS'

         -- Existing table counts
         AND t.annual_rows = 2
         AND t.reconciled_quarters = 24
         AND t.original_multi_quarters = 24
         AND t.original_week2_quarters = 12

        THEN 'PASS'

        ELSE 'REVIEW'

    END AS validation_result

FROM expected e

LEFT JOIN company_fcf_reconciliations r
  ON r.ticker = e.ticker
 AND r.fiscal_year = e.fiscal_year

LEFT JOIN sec_annual s
  ON s.ticker = e.ticker
 AND s.fiscal_year = e.fiscal_year

LEFT JOIN quarterly_check q
  ON q.ticker = e.ticker
 AND q.fiscal_year = e.fiscal_year

LEFT JOIN adjustment_check a
  ON a.ticker = e.ticker
 AND a.fiscal_year = e.fiscal_year

CROSS JOIN table_integrity t

ORDER BY e.ticker;