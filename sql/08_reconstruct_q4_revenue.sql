
-- Week 2: Reconstruct Q4 Revenue
-- Company: Palantir (PLTR)
-- Method: Annual revenue - Nine-month YTD
-- Data cutoff: 2026-11-16

WITH annual_candidates AS (

    -- 1. 회계연도 전체 매출 검색
    SELECT
        CAST(EXTRACT(YEAR FROM period_end)
            AS INTEGER) AS fiscal_year,

        period_start,
        period_end,
        filed AS annual_filed,
        accn AS annual_accn,

        TRY_CAST(value_raw AS DECIMAL(38,0))
            AS annual_revenue,

        ROW_NUMBER() OVER (
            PARTITION BY period_start, period_end
            ORDER BY filed ASC, accn ASC
        ) AS annual_rank

    FROM financial_facts

    WHERE cik = 1321655
      AND taxonomy = 'us-gaap'
      AND tag =
          'RevenueFromContractWithCustomerExcludingAssessedTax'
      AND unit = 'USD'
      AND form IN ('10-K', '10-K/A')
      AND filed <= DATE '2026-11-16'

      -- 1월 1일~12월 31일의 연간 매출
      AND period_start = make_date(
          CAST(EXTRACT(YEAR FROM period_end) AS INTEGER),
          1, 1
      )
      AND period_end = make_date(
          CAST(EXTRACT(YEAR FROM period_end) AS INTEGER),
          12, 31
      )

      AND period_end BETWEEN
          DATE '2023-12-31'
          AND DATE '2025-12-31'
),

annual_first AS (

    -- 2. 최초 연간 공시 선택
    SELECT *
    FROM annual_candidates
    WHERE annual_rank = 1
),

nine_month_candidates AS (

    -- 3. 연간 공시 당시 이용 가능했던
    --    9개월 누적 매출 검색
    SELECT
        a.fiscal_year,
        a.annual_revenue,
        a.annual_filed,
        a.annual_accn,

        TRY_CAST(f.value_raw AS DECIMAL(38,0))
            AS revenue_9m,

        f.filed AS ytd_filed,
        f.accn AS ytd_accn,

        ROW_NUMBER() OVER (
            PARTITION BY a.fiscal_year
            ORDER BY
                f.filed DESC NULLS LAST,
                f.accn DESC NULLS LAST
        ) AS ytd_rank

    FROM annual_first a

    LEFT JOIN financial_facts f
        ON f.cik = 1321655
       AND f.taxonomy = 'us-gaap'
       AND f.tag =
           'RevenueFromContractWithCustomerExcludingAssessedTax'
       AND f.unit = 'USD'
       AND f.form IN ('10-Q', '10-Q/A')

       AND f.period_start = a.period_start
       AND f.period_end =
           make_date(a.fiscal_year, 9, 30)

       -- 연간 공시 이후의 자료는 사용하지 않음
       AND f.filed <= a.annual_filed
)

-- 4. Q4 매출 계산 및 검증
SELECT
    fiscal_year,
    annual_revenue,
    revenue_9m,

    annual_revenue - revenue_9m
        AS q4_revenue,

    annual_filed,
    ytd_filed,

    annual_accn,
    ytd_accn,

    CASE
        WHEN annual_revenue IS NULL
          OR revenue_9m IS NULL
        THEN 'MISSING_DATA'

        WHEN annual_revenue < revenue_9m
        THEN 'REVIEW_REQUIRED'

        ELSE 'CALCULATED'
    END AS data_status

FROM nine_month_candidates

WHERE ytd_rank = 1

ORDER BY fiscal_year DESC;