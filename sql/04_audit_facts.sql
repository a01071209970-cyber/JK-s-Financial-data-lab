
-- Week 1: PLTR Data Quality Audit

WITH quality AS (
    SELECT
        COUNT(*) AS total_rows,

        COUNT(*) FILTER (
            WHERE taxonomy IS NULL
               OR tag IS NULL
               OR unit IS NULL
               OR period_end IS NULL
               OR filed IS NULL
               OR accn IS NULL
               OR form IS NULL
               OR value_raw IS NULL
        ) AS missing_core_fields,

        COUNT(*) FILTER (
            WHERE period_start > period_end
        ) AS invalid_periods,

        COUNT(*) FILTER (
            WHERE value_num IS NULL
        ) AS non_numeric_values,

        COUNT(*) FILTER (
            WHERE taxonomy = 'us-gaap'
              AND tag IN (
                  'RevenueFromContractWithCustomerExcludingAssessedTax',
                  'OperatingIncomeLoss',
                  'NetCashProvidedByUsedInOperatingActivities',
                  'PaymentsToAcquirePropertyPlantAndEquipment'
              )
              AND period_start IS NULL
        ) AS duration_missing_start,

        COUNT(*) FILTER (
            WHERE period_start IS NULL
        ) AS no_start_rows,

        COUNT(*) FILTER (
            WHERE frame IS NULL
        ) AS no_frame_rows

    FROM financial_facts
    WHERE cik = 1321655
),

duplicate_groups AS (
    SELECT COUNT(*) AS copies
    FROM financial_facts
    WHERE cik = 1321655
    GROUP BY
        cik, taxonomy, tag, label, unit,
        period_start, period_end,
        value_raw, value_num,
        form, filed, accn, fy, fp, frame
    HAVING COUNT(*) > 1
),

duplicates AS (
    SELECT
        COALESCE(SUM(copies - 1), 0)
            AS exact_duplicate_rows
    FROM duplicate_groups
)

SELECT
    q.total_rows,
    q.missing_core_fields,
    q.invalid_periods,
    q.non_numeric_values,
    q.duration_missing_start,
    d.exact_duplicate_rows,
    q.no_start_rows,
    q.no_frame_rows,

    CASE
        WHEN q.total_rows > 0
         AND q.missing_core_fields = 0
         AND q.invalid_periods = 0
         AND q.non_numeric_values = 0
         AND q.duration_missing_start = 0
         AND d.exact_duplicate_rows = 0
        THEN 'PASS'
        ELSE 'REVIEW'
    END AS audit_result

FROM quality q
CROSS JOIN duplicates d;