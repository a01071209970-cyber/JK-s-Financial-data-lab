
-- PLTR: 12 Quarterly Revenue Observations
-- Method: First-Available
-- Data cutoff: 2026-11-16

WITH base AS (
    SELECT
        period_start,
        period_end,
        filed,
        accn,
        form,
        TRY_CAST(value_raw AS DECIMAL(38,0))
            AS amount
    FROM financial_facts
    WHERE cik = 1321655
      AND taxonomy = 'us-gaap'
      AND tag =
        'RevenueFromContractWithCustomerExcludingAssessedTax'
      AND unit = 'USD'
      AND filed <= DATE '2026-11-16'
),

-- 1. 직접 보고된 Q1~Q3 매출
direct_ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY period_start, period_end
            ORDER BY filed ASC, accn ASC
        ) AS rn
    FROM base
    WHERE form IN ('10-Q', '10-Q/A')
      AND period_end BETWEEN
          DATE '2024-01-01' AND DATE '2026-09-30'
      AND EXTRACT(QUARTER FROM period_end)
          IN (1, 2, 3)
      AND period_start =
          CAST(date_trunc('quarter', period_end) AS DATE)
      AND period_end =
          CAST(
              date_trunc('quarter', period_end)
              + INTERVAL '3 months'
              - INTERVAL '1 day'
              AS DATE
          )
),

direct_q AS (
    SELECT
        CAST(EXTRACT(YEAR FROM period_end)
            AS INTEGER) AS fiscal_year,
        CAST(EXTRACT(QUARTER FROM period_end)
            AS INTEGER) AS fiscal_quarter,
        period_start,
        period_end,
        amount AS revenue_usd,
        'DIRECT' AS calculation_method,
        filed AS source_filed,
        accn AS source_accn,
        CAST(NULL AS DATE) AS support_filed,
        CAST(NULL AS VARCHAR) AS support_accn
    FROM direct_ranked
    WHERE rn = 1
),

-- 2. 각 연도의 최초 연간 공시
annual_ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY period_end
            ORDER BY filed ASC, accn ASC
        ) AS rn
    FROM base
    WHERE form IN ('10-K', '10-K/A')
      AND period_end BETWEEN
          DATE '2023-12-31' AND DATE '2025-12-31'
      AND period_start = make_date(
          CAST(EXTRACT(YEAR FROM period_end) AS INTEGER),
          1, 1
      )
      AND period_end = make_date(
          CAST(EXTRACT(YEAR FROM period_end) AS INTEGER),
          12, 31
      )
),

annual_first AS (
    SELECT
        CAST(EXTRACT(YEAR FROM period_end)
            AS INTEGER) AS fiscal_year,
        period_start,
        period_end,
        filed,
        accn,
        amount
    FROM annual_ranked
    WHERE rn = 1
),

-- 3. 최초 연간 공시 당시의 9M 누적 매출
q4_ranked AS (
    SELECT
        a.fiscal_year,
        a.amount AS annual_revenue,
        y.amount AS revenue_9m,
        a.filed AS annual_filed,
        a.accn AS annual_accn,
        y.filed AS ytd_filed,
        y.accn AS ytd_accn,
        ROW_NUMBER() OVER (
            PARTITION BY a.fiscal_year
            ORDER BY
                y.filed DESC NULLS LAST,
                y.accn DESC NULLS LAST
        ) AS rn
    FROM annual_first a
    LEFT JOIN base y
      ON y.period_start = a.period_start
     AND y.period_end = make_date(a.fiscal_year, 9, 30)
     AND y.form IN ('10-Q', '10-Q/A')
     AND y.filed <= a.filed
),

-- 4. Q4 매출 재구성
derived_q4 AS (
    SELECT
        fiscal_year,
        4 AS fiscal_quarter,
        make_date(fiscal_year, 10, 1) AS period_start,
        make_date(fiscal_year, 12, 31) AS period_end,
        annual_revenue - revenue_9m AS revenue_usd,
        'DERIVED' AS calculation_method,
        annual_filed AS source_filed,
        annual_accn AS source_accn,
        ytd_filed AS support_filed,
        ytd_accn AS support_accn
    FROM q4_ranked
    WHERE rn = 1
),

-- 5. 직접 공시값과 계산값 결합
combined AS (
    SELECT * FROM direct_q
    UNION ALL
    SELECT * FROM derived_q4
)

SELECT
    fiscal_year,
    fiscal_quarter,
    revenue_usd,
    calculation_method,
    source_filed,
    source_accn,
    support_filed,
    support_accn,
    COUNT(*) OVER () AS quarters_found
FROM combined
ORDER BY fiscal_year DESC, fiscal_quarter DESC;