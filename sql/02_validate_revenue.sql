
WITH revenue_data AS (
    SELECT
        MAX(CASE
            WHEN period_start = '2026-07-01'
             AND period_end = '2026-09-30'
             AND filed = '2026-11-03'
            THEN TRY_CAST(value_raw AS DECIMAL(38,0))
        END) AS q3_reported,

        MAX(CASE
            WHEN period_start = '2026-01-01'
             AND period_end = '2026-09-30'
             AND filed = '2026-11-03'
            THEN TRY_CAST(value_raw AS DECIMAL(38,0))
        END) AS nine_month_ytd,

        MAX(CASE
            WHEN period_start = '2026-01-01'
             AND period_end = '2026-06-30'
             AND filed = '2026-08-04'
            THEN TRY_CAST(value_raw AS DECIMAL(38,0))
        END) AS six_month_ytd

    FROM financial_facts
    WHERE cik = 1321655
      AND taxonomy = 'us-gaap'
      AND tag = 'RevenueFromContractWithCustomerExcludingAssessedTax'
      AND unit = 'USD'
      AND form = '10-Q'
)

SELECT
    q3_reported,
    nine_month_ytd - six_month_ytd AS q3_calculated,

    CASE
        WHEN q3_reported IS NOT NULL
         AND nine_month_ytd IS NOT NULL
         AND six_month_ytd IS NOT NULL
         AND q3_reported = nine_month_ytd - six_month_ytd
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_result

FROM revenue_data;