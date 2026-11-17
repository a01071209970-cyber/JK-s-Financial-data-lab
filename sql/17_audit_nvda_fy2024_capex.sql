
-- ====================================================
-- JK's Financial Data Lab V1.0
-- Week 3: NVDA FY2024 CAPEX Source Audit
-- Read-only: no tables are modified
-- ====================================================

WITH candidate_facts AS (

    SELECT
        taxonomy,
        tag,
        label,
        unit,

        period_start,
        period_end,

        value_raw,
        form,
        filed,
        accn,

        CASE
            WHEN period_start = DATE '2023-01-30'
             AND period_end = DATE '2023-07-30'
                THEN 'Q2_6M_YTD'

            WHEN period_start = DATE '2023-01-30'
             AND period_end = DATE '2023-10-29'
                THEN 'Q3_9M_YTD'

            WHEN period_start = DATE '2023-07-31'
             AND period_end = DATE '2023-10-29'
                THEN 'Q3_DIRECT'

            WHEN period_start = DATE '2023-01-30'
             AND period_end = DATE '2024-01-28'
                THEN 'FY2024_ANNUAL'

            ELSE 'OTHER'
        END AS period_type

    FROM financial_facts_multi

    WHERE ticker = 'NVDA'
      AND unit = 'USD'

      AND filed <= DATE '2026-11-17'

      AND form IN (
          '10-Q', '10-Q/A',
          '10-K', '10-K/A'
      )

      AND period_end IN (
          DATE '2023-07-30',
          DATE '2023-10-29',
          DATE '2024-01-28'
      )

      AND period_start IN (
          DATE '2023-01-30',
          DATE '2023-07-31'
      )

      AND (
          tag ILIKE '%PaymentsToAcquire%'
          OR tag ILIKE '%ProductiveAsset%'
          OR tag ILIKE '%CapitalExpenditure%'
          OR tag ILIKE '%PropertyPlant%'
          OR tag = 'NetCashProvidedByUsedInOperatingActivities'
          OR label ILIKE '%property and equipment%'
          OR label ILIKE '%capital expenditure%'
      )
),

ranked AS (

    SELECT
        *,

        ROW_NUMBER() OVER (
            PARTITION BY
                taxonomy,
                tag,
                period_start,
                period_end
            ORDER BY filed ASC, accn ASC
        ) AS rn

    FROM candidate_facts

)

SELECT
    period_type,
    taxonomy,
    tag,
    label,

    period_start,
    period_end,

    value_raw AS value_usd,

    form,
    filed,
    accn

FROM ranked

WHERE rn = 1

ORDER BY
    period_end,
    period_type,
    tag

LIMIT 100;