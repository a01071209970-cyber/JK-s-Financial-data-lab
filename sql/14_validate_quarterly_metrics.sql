
-- ==================================================
-- JK's Financial Data Lab V1.0
-- Week 2: Quarterly Metrics Quality Audit
-- Company: PLTR
-- Period: 2023 Q4 - 2026 Q3
-- ==================================================

WITH expected_quarters AS (

    -- 1. 정상적으로 존재해야 하는 12개 분기
    SELECT
        CAST(EXTRACT(YEAR FROM quarter_start)
            AS INTEGER) AS fiscal_year,

        CAST(EXTRACT(QUARTER FROM quarter_start)
            AS INTEGER) AS fiscal_quarter

    FROM (
        SELECT
            CAST(
                DATE '2023-10-01'
                + n * INTERVAL '3 months'
                AS DATE
            ) AS quarter_start
        FROM generate_series(0, 11) AS g(n)
    )
),

checked AS (

    -- 2. 저장된 지표를 원본 숫자로 재계산
    SELECT
        m.*,

        CASE
            WHEN m.revenue_usd IS NULL
              OR m.operating_income_usd IS NULL
              OR m.ocf_usd IS NULL
              OR m.capex_usd IS NULL
              OR m.fcf_usd IS NULL
            THEN 1 ELSE 0
        END AS missing_core_error,

        CASE
            WHEN m.fcf_usd IS DISTINCT FROM
                 (m.ocf_usd - m.capex_usd)
            THEN 1 ELSE 0
        END AS fcf_error,

        CASE
            WHEN m.operating_margin_pct
                 IS DISTINCT FROM ROUND(
                    100.0 * m.operating_income_usd
                    / NULLIF(m.revenue_usd, 0), 2
                 )
              OR m.fcf_margin_pct
                 IS DISTINCT FROM ROUND(
                    100.0 * m.fcf_usd
                    / NULLIF(m.revenue_usd, 0), 2
                 )
            THEN 1 ELSE 0
        END AS margin_error,

        CASE
            WHEN p.revenue_usd IS NULL
            THEN
                CASE
                    WHEN m.revenue_growth_yoy_pct IS NULL
                    THEN 0 ELSE 1
                END
            WHEN m.revenue_growth_yoy_pct
                 IS DISTINCT FROM ROUND(
                    (
                        CAST(m.revenue_usd AS DOUBLE)
                        / NULLIF(
                            CAST(p.revenue_usd AS DOUBLE), 0
                        ) - 1
                    ) * 100.0, 2
                 )
            THEN 1
            ELSE 0
        END AS growth_error,

        CASE
            WHEN p.revenue_usd IS NULL
            THEN
                CASE
                    WHEN m.operating_margin_yoy_change_pp
                         IS NULL
                    THEN 0 ELSE 1
                END
            WHEN m.operating_margin_yoy_change_pp
                 IS DISTINCT FROM ROUND(
                    100.0 * m.operating_income_usd
                    / NULLIF(m.revenue_usd, 0)
                    -
                    100.0 * p.operating_income_usd
                    / NULLIF(p.revenue_usd, 0),
                    2
                 )
            THEN 1
            ELSE 0
        END AS yoy_margin_error

    FROM quarterly_metrics m

    LEFT JOIN quarterly_metrics p
      ON p.fiscal_year = m.fiscal_year - 1
     AND p.fiscal_quarter = m.fiscal_quarter
),

summary AS (

    -- 3. 전체 데이터 검증 결과 집계
    SELECT
        COUNT(*) AS total_rows,

        COUNT(DISTINCT
            CAST(fiscal_year AS VARCHAR)
            || '-Q'
            || CAST(fiscal_quarter AS VARCHAR)
        ) AS unique_quarters,

        COALESCE(SUM(missing_core_error), 0)
            AS missing_core_errors,

        COALESCE(SUM(fcf_error), 0)
            AS fcf_errors,

        COALESCE(SUM(margin_error), 0)
            AS margin_errors,

        COALESCE(SUM(growth_error), 0)
            AS growth_errors,

        COALESCE(SUM(yoy_margin_error), 0)
            AS yoy_margin_errors

    FROM checked
),

missing_calendar AS (

    -- 4. 기대한 12개 분기 중 누락된 기간 확인
    SELECT COUNT(*) AS missing_quarters
    FROM expected_quarters e

    LEFT JOIN quarterly_metrics m
      ON e.fiscal_year = m.fiscal_year
     AND e.fiscal_quarter = m.fiscal_quarter

    WHERE m.fiscal_year IS NULL
)

-- 5. 최종 품질 검사 결과
SELECT
    s.*,
    c.missing_quarters,

    CASE
        WHEN s.total_rows = 12
         AND s.unique_quarters = 12
         AND c.missing_quarters = 0
         AND s.missing_core_errors = 0
         AND s.fcf_errors = 0
         AND s.margin_errors = 0
         AND s.growth_errors = 0
         AND s.yoy_margin_errors = 0
        THEN 'PASS'
        ELSE 'REVIEW'
    END AS validation_result

FROM summary s
CROSS JOIN missing_calendar c;