
-- Week 2: SEC Filing Version Analysis
-- Company: Palantir Technologies (PLTR)

WITH filing_versions AS (

    SELECT
        tag,
        period_start,
        period_end,

        COUNT(*) AS observation_count,

        COUNT(DISTINCT accn) AS filing_count,

        COUNT(DISTINCT value_raw) AS distinct_values,

        MIN(filed) AS first_filed,
        MAX(filed) AS last_filed

    FROM financial_facts

    WHERE cik = 1321655
      AND taxonomy = 'us-gaap'
      AND unit = 'USD'

      AND form IN (
          '10-Q', '10-K',
          '10-Q/A', '10-K/A'
      )

      AND period_start IS NOT NULL
      AND period_end >= DATE '2025-01-01'

      AND tag IN (
          'RevenueFromContractWithCustomerExcludingAssessedTax',
          'OperatingIncomeLoss',
          'NetCashProvidedByUsedInOperatingActivities',
          'PaymentsToAcquirePropertyPlantAndEquipment'
      )

    GROUP BY
        tag,
        period_start,
        period_end

    HAVING COUNT(DISTINCT accn) > 1
)

SELECT
    *,
    CASE
        WHEN distinct_values > 1
        THEN 'VALUE_CHANGED'
        ELSE 'UNCHANGED'
    END AS version_status

FROM filing_versions

ORDER BY
    CASE WHEN distinct_values > 1 THEN 0 ELSE 1 END,
    period_end DESC,
    filing_count DESC

LIMIT 30;