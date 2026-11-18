
-- =====================================================
-- JK's Financial Data Lab V1.0
-- Week 4: Fundamental Screener V0.1
--
-- Screening criteria:
-- 1. Latest quarterly revenue YoY >= 20%
-- 2. Operating margin >= 10%
--    OR operating margin YoY change > 0 pp
--
-- Quality requirements:
-- - 8 consecutive fiscal quarters
-- - Available as of 2026-11-17
-- - Valid reported/reconciled observations
-- - No missing core screening metrics
--
-- EXCLUDED from screening:
-- - FCF (definition not standardized)
-- - Market cap, debt/equity, analyst coverage
--
-- Read-only
-- =====================================================

WITH parameters AS (

    SELECT
        DATE '2026-11-17' AS cutoff_date,

        20.0 AS min_revenue_yoy_pct,

        10.0 AS min_operating_margin_pct,

        180 AS max_filing_age_days
),

ranked AS (

    -- Rank all fiscal quarters first.
    -- Do not hide incomplete recent quarters.

    SELECT
        q.*,

        ROW_NUMBER() OVER (
            PARTITION BY q.ticker
            ORDER BY
                q.period_end DESC,
                q.fiscal_year DESC,
                q.fiscal_quarter DESC
        ) AS recent_rank

    FROM quarterly_metrics_reconciled q

    CROSS JOIN parameters p

    WHERE q.period_end <= p.cutoff_date
),

latest_eight AS (

    -- Current LTM + prior LTM

    SELECT *
    FROM ranked

    WHERE recent_rank <= 8
),

continuity AS (

    SELECT
        *,

        LAG(period_end) OVER (
            PARTITION BY ticker
            ORDER BY period_start
        ) AS previous_end

    FROM latest_eight
),

company_summary AS (

    SELECT
        ticker,

        COUNT(*) AS quarter_count,

        MAX(
            CASE WHEN recent_rank = 1
            THEN fiscal_year END
        ) AS latest_fiscal_year,

        MAX(
            CASE WHEN recent_rank = 1
            THEN fiscal_quarter END
        ) AS latest_fiscal_quarter,

        MAX(
            CASE WHEN recent_rank = 1
            THEN period_end END
        ) AS latest_period_end,

        MAX(
            CASE WHEN recent_rank = 1
            THEN available_date END
        ) AS latest_available_date,

        MAX(
            CASE WHEN recent_rank = 1
            THEN revenue_growth_yoy_pct END
        ) AS latest_revenue_yoy_pct,

        MAX(
            CASE WHEN recent_rank = 1
            THEN operating_margin_pct END
        ) AS latest_operating_margin_pct,

        MAX(
            CASE WHEN recent_rank = 1
            THEN operating_margin_yoy_change_pp END
        ) AS latest_margin_change_pp,

        MAX(
            CASE WHEN recent_rank = 1
            THEN revenue_usd END
        ) AS latest_revenue,

        MAX(
            CASE WHEN recent_rank = 1
            THEN ocf_usd END
        ) AS latest_ocf,

        -- Current four-quarter revenue
        SUM(
            CASE
                WHEN recent_rank <= 4
                THEN revenue_usd
            END
        ) AS ltm_revenue,

        -- Previous four-quarter revenue
        SUM(
            CASE
                WHEN recent_rank BETWEEN 5 AND 8
                THEN revenue_usd
            END
        ) AS prior_ltm_revenue,

        -- Current LTM operating income
        SUM(
            CASE
                WHEN recent_rank <= 4
                THEN operating_income_usd
            END
        ) AS ltm_operating_income,

        -- Data quality: period continuity
        COUNT(*) FILTER (
            WHERE previous_end IS NOT NULL
              AND date_diff(
                  'day',
                  previous_end,
                  period_start
              ) <> 1
        ) AS continuity_errors,

        -- Data quality: incomplete metrics
        COUNT(*) FILTER (
            WHERE revenue_usd IS NULL
               OR operating_income_usd IS NULL
               OR ocf_usd IS NULL
               OR operating_margin_pct IS NULL
        ) AS missing_metric_rows,

        -- Data quality: unverified quarters
        COUNT(*) FILTER (
            WHERE validation_status IS NULL
               OR validation_status NOT IN (
                   'PASS',
                   'RECONCILED_SUPPLEMENTAL'
               )
        ) AS review_rows,

        -- Data quality: filing availability
        COUNT(*) FILTER (
            WHERE available_date IS NULL
               OR available_date > DATE '2026-11-17'
               OR as_of_date
                   IS DISTINCT FROM DATE '2026-11-17'
        ) AS availability_errors

    FROM continuity

    GROUP BY ticker
),

quality_evaluation AS (

    SELECT
        c.*,

        p.cutoff_date,
        p.min_revenue_yoy_pct,
        p.min_operating_margin_pct,

        date_diff(
            'day',
            c.latest_available_date,
            p.cutoff_date
        ) AS filing_age_days,

        ROUND(
            (
                CAST(c.ltm_revenue AS DOUBLE)
                / NULLIF(
                    CAST(c.prior_ltm_revenue AS DOUBLE),
                    0
                ) - 1
            ) * 100,
            2
        ) AS ltm_revenue_yoy_pct,

        ROUND(
            100.0 *
            CAST(c.ltm_operating_income AS DOUBLE)
            / NULLIF(
                CAST(c.ltm_revenue AS DOUBLE),
                0
            ),
            2
        ) AS ltm_operating_margin_pct,

        ROUND(
            100.0 *
            CAST(c.latest_ocf AS DOUBLE)
            / NULLIF(
                CAST(c.latest_revenue AS DOUBLE),
                0
            ),
            2
        ) AS latest_ocf_margin_pct,

        CASE
            WHEN c.quarter_count <> 8
              OR c.continuity_errors <> 0
              OR c.missing_metric_rows <> 0
              OR c.review_rows <> 0
              OR c.availability_errors <> 0

              OR c.latest_revenue_yoy_pct IS NULL
              OR c.latest_operating_margin_pct IS NULL
              OR c.latest_margin_change_pp IS NULL

              OR c.latest_revenue <= 0
              OR c.prior_ltm_revenue <= 0

              OR c.latest_available_date IS NULL

              OR date_diff(
                  'day',
                  c.latest_available_date,
                  p.cutoff_date
              ) > p.max_filing_age_days

            THEN 'REVIEW'

            ELSE 'PASS'

        END AS data_quality_status

    FROM company_summary c

    CROSS JOIN parameters p
),

screened AS (

    SELECT
        *,

        CASE
            WHEN data_quality_status <> 'PASS'
            THEN 'REVIEW'

            WHEN latest_revenue_yoy_pct
                    >= min_revenue_yoy_pct

             AND (
                 latest_operating_margin_pct
                     >= min_operating_margin_pct

                 OR latest_margin_change_pp > 0
             )

            THEN 'PASS'

            ELSE 'FAIL'

        END AS fundamental_screen_status,

        CASE
            WHEN data_quality_status <> 'PASS'
            THEN 'DATA_QUALITY_REVIEW'

            WHEN latest_revenue_yoy_pct
                    < min_revenue_yoy_pct
            THEN 'REVENUE_GROWTH_BELOW_THRESHOLD'

            WHEN latest_operating_margin_pct
                    < min_operating_margin_pct

             AND latest_margin_change_pp <= 0
            THEN 'OPERATING_PROFITABILITY_BELOW_THRESHOLD'

            ELSE 'FILTER_CRITERIA_MET'

        END AS screening_reason

    FROM quality_evaluation
)

SELECT
    ticker,

    latest_fiscal_year,
    latest_fiscal_quarter,

    latest_period_end,
    latest_available_date,

    filing_age_days,

    ROUND(
        CAST(latest_revenue_yoy_pct AS DOUBLE), 2
    ) AS latest_revenue_yoy_pct,

    ROUND(
        CAST(latest_operating_margin_pct AS DOUBLE), 2
    ) AS latest_operating_margin_pct,

    ROUND(
        CAST(latest_margin_change_pp AS DOUBLE), 2
    ) AS latest_margin_change_pp,

    latest_ocf_margin_pct,

    ROUND(
        CAST(ltm_revenue AS DOUBLE) / 1e9, 3
    ) AS ltm_revenue_bn,

    ltm_revenue_yoy_pct,

    ltm_operating_margin_pct,

    data_quality_status,

    fundamental_screen_status,

    screening_reason,

    'BLOCKED' AS fcf_cross_company_ranking,

    'NOT_EVALUATED' AS market_cap_debt_analyst_filters

FROM screened

ORDER BY
    CASE fundamental_screen_status
        WHEN 'PASS' THEN 1
        WHEN 'REVIEW' THEN 2
        ELSE 3
    END,

    latest_revenue_yoy_pct DESC,

    ticker;