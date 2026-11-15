
-- PLTR FY2026 Q3 Cash Flow Validation

WITH source AS (
    SELECT
        tag,
        period_end,
        TRY_CAST(value_raw AS DECIMAL(38, 0)) AS amount
    FROM financial_facts
    WHERE cik = 1321655
      AND taxonomy = 'us-gaap'
      AND unit = 'USD'
      AND form = '10-Q'
      AND period_start = DATE '2026-01-01'
      AND tag IN (
          'NetCashProvidedByUsedInOperatingActivities',
          'PaymentsToAcquirePropertyPlantAndEquipment'
      )
      AND (
          (
            period_end = DATE '2026-09-30'
            AND filed = DATE '2026-11-03'
            AND accn = '0001321655-26-000048'
          )
          OR
          (
            period_end = DATE '2026-06-30'
            AND filed = DATE '2026-08-04'
            AND accn = '0001321655-26-000041'
          )
      )
),

summary AS (
    SELECT
        COUNT(*) AS source_rows,

        COUNT(DISTINCT tag || CAST(period_end AS VARCHAR))
            AS unique_rows,

        MAX(amount) FILTER (
            WHERE tag =
              'NetCashProvidedByUsedInOperatingActivities'
              AND period_end = DATE '2026-09-30'
        ) AS ocf_9m,

        MAX(amount) FILTER (
            WHERE tag =
              'NetCashProvidedByUsedInOperatingActivities'
              AND period_end = DATE '2026-06-30'
        ) AS ocf_6m,

        MAX(amount) FILTER (
            WHERE tag =
              'PaymentsToAcquirePropertyPlantAndEquipment'
              AND period_end = DATE '2026-09-30'
        ) AS capex_9m,

        MAX(amount) FILTER (
            WHERE tag =
              'PaymentsToAcquirePropertyPlantAndEquipment'
              AND period_end = DATE '2026-06-30'
        ) AS capex_6m
    FROM source
)

SELECT
    ocf_9m - ocf_6m AS q3_ocf_usd,

    capex_9m - capex_6m AS q3_capex_usd,

    (ocf_9m - ocf_6m)
      - (capex_9m - capex_6m) AS q3_fcf_usd,

    CASE
        WHEN source_rows = 4
         AND unique_rows = 4
         AND ocf_9m IS NOT NULL
         AND ocf_6m IS NOT NULL
         AND capex_9m IS NOT NULL
         AND capex_6m IS NOT NULL
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_result

FROM summary;