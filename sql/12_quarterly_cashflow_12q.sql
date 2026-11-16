
-- ====================================================
-- JK's Financial Data Lab V1.0
-- Week 2: Quarterly Cash Flow & FCF
-- Company: PLTR
-- Period: 2023 Q4 - 2026 Q3
-- Method: First-Available YTD Difference
-- Data cutoff: 2026-11-16
-- ====================================================

WITH source AS (

    -- 1. SEC 원본 OCF 및 CAPEX 추출
    SELECT
        tag,
        period_start,
        period_end,
        filed,
        accn,
        form,

        CAST(EXTRACT(YEAR FROM period_end)
            AS INTEGER) AS fiscal_year,

        CAST(EXTRACT(QUARTER FROM period_end)
            AS INTEGER) AS fiscal_quarter,

        TRY_CAST(value_raw AS DECIMAL(38,0))
            AS amount

    FROM financial_facts

    WHERE cik = 1321655
      AND taxonomy = 'us-gaap'
      AND unit = 'USD'

      AND tag IN (
          'NetCashProvidedByUsedInOperatingActivities',
          'PaymentsToAcquirePropertyPlantAndEquipment'
      )

      AND filed <= DATE '2026-11-16'

      AND period_end BETWEEN
          DATE '2023-09-30'
          AND DATE '2026-09-30'

      -- 현금흐름은 연초 누적 데이터만 사용
      AND period_start = make_date(
          CAST(EXTRACT(YEAR FROM period_end)
              AS INTEGER),
          1, 1
      )

      -- 정상적인 분기 종료일 확인
      AND period_end = CAST(
          date_trunc('quarter', period_end)
          + INTERVAL '3 months'
          - INTERVAL '1 day'
          AS DATE
      )

      AND (
          (
              EXTRACT(QUARTER FROM period_end)
                  IN (1, 2, 3)
              AND form IN ('10-Q', '10-Q/A')
          )
          OR
          (
              EXTRACT(QUARTER FROM period_end) = 4
              AND form IN ('10-K', '10-K/A')
          )
      )
),

-- 2. 각 누적기간의 최초 공시 선택
ranked_source AS (

    SELECT
        *,

        ROW_NUMBER() OVER (
            PARTITION BY
                tag, fiscal_year, fiscal_quarter
            ORDER BY
                filed ASC,
                accn ASC
        ) AS rn

    FROM source
),

first_filing AS (

    SELECT *
    FROM ranked_source
    WHERE rn = 1
),

-- 3. 최근 12개 분기 달력 생성
quarters AS (

    SELECT
        CAST(EXTRACT(YEAR FROM quarter_start)
            AS INTEGER) AS fiscal_year,

        CAST(EXTRACT(QUARTER FROM quarter_start)
            AS INTEGER) AS fiscal_quarter

    FROM generate_series(
        DATE '2023-10-01',
        DATE '2026-07-01',
        INTERVAL '3 months'
    ) AS t(quarter_start)
),

-- 4. 계산할 재무 지표
metrics AS (

    SELECT *
    FROM (
        VALUES
        (
            'NetCashProvidedByUsedInOperatingActivities',
            'OCF'
        ),
        (
            'PaymentsToAcquirePropertyPlantAndEquipment',
            'CAPEX'
        )
    ) AS t(tag, metric)
),

-- 5. 누적 현금흐름을 개별 분기로 변환
quarterly_calculations AS (

    SELECT
        q.fiscal_year,
        q.fiscal_quarter,
        m.metric,

        c.amount AS current_ytd,
        p.amount AS previous_ytd,

        CASE
            -- Q1: 3개월 누적 = 개별 분기
            WHEN q.fiscal_quarter = 1
                THEN c.amount

            -- Q2~Q4: 현재 누적 - 직전 누적
            ELSE c.amount - p.amount

        END AS quarterly_amount,

        c.filed AS source_filed,
        c.accn AS source_accn,

        p.filed AS previous_filed,
        p.accn AS previous_accn

    FROM quarters q

    CROSS JOIN metrics m

    LEFT JOIN first_filing c
        ON c.tag = m.tag
       AND c.fiscal_year = q.fiscal_year
       AND c.fiscal_quarter = q.fiscal_quarter

    LEFT JOIN first_filing p
        ON p.tag = m.tag
       AND p.fiscal_year = q.fiscal_year
       AND p.fiscal_quarter = q.fiscal_quarter - 1
),

-- 6. OCF와 CAPEX를 같은 행에 배치
combined AS (

    SELECT
        fiscal_year,
        fiscal_quarter,

        MAX(
            CASE WHEN metric = 'OCF'
            THEN quarterly_amount END
        ) AS ocf_usd,

        MAX(
            CASE WHEN metric = 'CAPEX'
            THEN quarterly_amount END
        ) AS capex_usd,

        MAX(
            CASE WHEN metric = 'OCF'
            THEN source_filed END
        ) AS ocf_filed,

        MAX(
            CASE WHEN metric = 'CAPEX'
            THEN source_filed END
        ) AS capex_filed,

        MAX(
            CASE WHEN metric = 'OCF'
            THEN source_accn END
        ) AS ocf_accn,

        MAX(
            CASE WHEN metric = 'CAPEX'
            THEN source_accn END
        ) AS capex_accn,

        MAX(
            CASE WHEN metric = 'OCF'
            THEN previous_accn END
        ) AS ocf_previous_accn,

        MAX(
            CASE WHEN metric = 'CAPEX'
            THEN previous_accn END
        ) AS capex_previous_accn

    FROM quarterly_calculations

    GROUP BY
        fiscal_year,
        fiscal_quarter
)

-- 7. 최종 분기별 현금흐름 분석
SELECT
    fiscal_year,
    fiscal_quarter,

    ocf_usd,
    capex_usd,

    -- Free Cash Flow
    ocf_usd - capex_usd AS fcf_usd,

    CASE
        WHEN fiscal_quarter = 1
            THEN 'Q1_YTD'
        WHEN fiscal_quarter = 4
            THEN 'FY_MINUS_9M'
        ELSE 'YTD_DIFFERENCE'
    END AS calculation_method,

    GREATEST(
        ocf_filed,
        capex_filed
    ) AS available_date,

    ocf_accn,
    capex_accn,

    ocf_previous_accn,
    capex_previous_accn,

    CASE
        WHEN ocf_usd IS NULL
          OR capex_usd IS NULL
        THEN 'MISSING_SOURCE'
        ELSE 'PASS'
    END AS validation_status,

    COUNT(*) OVER () AS quarters_found

FROM combined

ORDER BY
    fiscal_year DESC,
    fiscal_quarter DESC;