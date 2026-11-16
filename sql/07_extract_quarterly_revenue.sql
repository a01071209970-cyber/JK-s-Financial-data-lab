
-- Week 2: Direct Quarterly Revenue Extraction
-- Company: PLTR
-- As-of date: 2026-11-16

WITH quarterly_candidates AS (

    SELECT
        period_start,
        period_end,
        filed,
        accn,
        form,

        TRY_CAST(value_raw AS DECIMAL(38,0))
            AS revenue_usd,

        -- 동일 분기에 여러 공시가 존재할 경우
        -- 기준일까지의 가장 최근 버전 선택
        ROW_NUMBER() OVER (
            PARTITION BY period_start, period_end
            ORDER BY filed DESC, accn DESC
        ) AS version_rank

    FROM financial_facts

    WHERE cik = 1321655
      AND taxonomy = 'us-gaap'
      AND tag =
          'RevenueFromContractWithCustomerExcludingAssessedTax'
      AND unit = 'USD'

      AND form IN (
          '10-Q', '10-K', '10-Q/A', '10-K/A'
      )

      -- 미래 공시 사용 방지
      AND filed <= DATE '2026-11-16'

      -- 개별 분기 약 3개월 길이만 선택
      AND period_start IS NOT NULL
      AND date_diff(
          'day', period_start, period_end
      ) BETWEEN 75 AND 105
)

SELECT
    EXTRACT(YEAR FROM period_end)
        AS fiscal_year,

    EXTRACT(QUARTER FROM period_end)
        AS fiscal_quarter,

    period_start,
    period_end,
    revenue_usd,
    filed AS source_filed,
    accn AS source_accn

FROM quarterly_candidates

WHERE version_rank = 1
  AND revenue_usd IS NOT NULL

ORDER BY period_end DESC

LIMIT 15;