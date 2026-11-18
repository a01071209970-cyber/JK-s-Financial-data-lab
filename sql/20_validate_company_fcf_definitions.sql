
-- ====================================================
-- JK's Financial Data Lab V1.0
-- Week 4: Company-Specific FCF Definition Audit
--
-- PLTR FY2025 vs NVDA FY2026
-- SEC Company Facts + Official Earnings Releases
--
-- Read-only: no tables are modified
-- ====================================================

WITH reference_values AS (

    -- Officially published values in USD.
    -- PLTR: FY2025 earnings release
    -- NVDA: FY2026 earnings release

    SELECT *
    FROM (
        VALUES

        (
            'PLTR',
            2025,
            DATE '2025-01-01',
            DATE '2025-12-31',

            'PaymentsToAcquirePropertyPlantAndEquipment',

            2134473000::DECIMAL(38,0),
            33882000::DECIMAL(38,0),

            2270436000::DECIMAL(38,0),
            169845000::DECIMAL(38,0),

            'ADJUSTED_FCF'
        ),

        (
            'NVDA',
            2026,
            DATE '2025-01-27',
            DATE '2026-01-25',

            'PaymentsToAcquireProductiveAssets',

            102718000000::DECIMAL(38,0),
            6042000000::DECIMAL(38,0),

            96575000000::DECIMAL(38,0),
            -101000000::DECIMAL(38,0),

            'COMPANY_REPORTED_FCF'
        )

    ) AS t(
        ticker,
        fiscal_year,
        period_start,
        period_end,
        capex_tag,

        expected_ocf,
        expected_capex,

        reported_fcf,
        expected_adjustment,

        fcf_definition
    )
),

-- 1. Retrieve annual financial facts
source_facts AS (

    SELECT
        r.ticker,
        f.tag,
        f.filed,
        f.accn,

        TRY_CAST(
            f.value_raw AS DECIMAL(38,0)
        ) AS amount,

        ROW_NUMBER() OVER (
            PARTITION BY
                r.ticker,
                f.tag

            ORDER BY
                f.filed ASC,
                f.accn ASC
        ) AS rn

    FROM reference_values r

    INNER JOIN financial_facts_multi f

        ON r.ticker = f.ticker
       AND r.period_start = f.period_start
       AND r.period_end = f.period_end

    WHERE f.taxonomy = 'us-gaap'
      AND f.unit = 'USD'

      AND f.form IN ('10-K', '10-K/A')
      AND f.filed <= DATE '2026-11-17'

      AND f.tag IN (
          'NetCashProvidedByUsedInOperatingActivities',
          r.capex_tag
      )
),

-- 2. Select first SEC observations
first_facts AS (

    SELECT *
    FROM source_facts
    WHERE rn = 1
),

-- 3. Aggregate the two core metrics
annual_metrics AS (

    SELECT
        r.ticker,

        MAX(
            CASE
                WHEN f.tag =
                    'NetCashProvidedByUsedInOperatingActivities'
                THEN f.amount
            END
        ) AS sec_ocf,

        MAX(
            CASE
                WHEN f.tag = r.capex_tag
                THEN f.amount
            END
        ) AS sec_capex,

        MAX(
            CASE
                WHEN f.tag =
                    'NetCashProvidedByUsedInOperatingActivities'
                THEN f.filed
            END
        ) AS ocf_filed,

        MAX(
            CASE
                WHEN f.tag = r.capex_tag
                THEN f.filed
            END
        ) AS capex_filed

    FROM reference_values r

    LEFT JOIN first_facts f
      ON r.ticker = f.ticker

    GROUP BY r.ticker
),

-- 4. Recalculate simple FCF
calculated AS (

    SELECT
        r.*,

        a.sec_ocf,
        a.sec_capex,

        a.ocf_filed,
        a.capex_filed,

        a.sec_ocf - a.sec_capex
            AS simple_fcf,

        r.reported_fcf -
            (a.sec_ocf - a.sec_capex)
            AS actual_adjustment

    FROM reference_values r

    LEFT JOIN annual_metrics a
      ON r.ticker = a.ticker
)

-- 5. Compare simple FCF and reported FCF
SELECT
    ticker,
    fiscal_year,

    -- USD millions
    ROUND(
        sec_ocf / 1000000.0, 3
    ) AS ocf_m,

    ROUND(
        sec_capex / 1000000.0, 3
    ) AS capex_m,

    ROUND(
        simple_fcf / 1000000.0, 3
    ) AS simple_fcf_m,

    ROUND(
        reported_fcf / 1000000.0, 3
    ) AS company_reported_fcf_m,

    ROUND(
        actual_adjustment / 1000000.0, 3
    ) AS adjustment_m,

    fcf_definition,

    CASE
        WHEN ticker = 'PLTR'
        THEN 'ADD_EMPLOYER_PAYROLL_TAX_ADJUSTMENT'

        WHEN ticker = 'NVDA'
        THEN 'DEDUCT_ASSET_PRINCIPAL_PAYMENTS'

    END AS adjustment_method,

    ocf_filed,
    capex_filed,

    CASE
        WHEN sec_ocf = expected_ocf
         AND sec_capex = expected_capex

         AND simple_fcf IS NOT NULL

         AND actual_adjustment =
             expected_adjustment

         AND reported_fcf =
             simple_fcf + expected_adjustment

        THEN 'PASS'
        ELSE 'REVIEW'
    END AS validation_result

FROM calculated

ORDER BY ticker;