
-- =====================================================
-- JK's Financial Data Lab V1.0
-- Week 3: PLTR vs NVDA LTM Comparison
--
-- LTM = latest four reported fiscal quarters
-- Previous LTM = four quarters before current LTM
--
-- USD figures displayed in billions.
-- Simple FCF = OCF - selected CAPEX concept.
-- =====================================================

WITH ranked AS (

    -- 1. Rank each company's quarterly history
    SELECT
        ticker,
        fiscal_year,
        fiscal_quarter,
        period_start,
        period_end,
        available_date,
        as_of_date,

        revenue_usd,
        operating_income_usd,
        ocf_usd,
        capex_usd,
        fcf_usd,

        revenue_growth_yoy_pct,
        operating_margin_pct,
        fcf_margin_pct,

        capex_tag,
        validation_status,

        ROW_NUMBER() OVER (
            PARTITION BY ticker
            ORDER BY period_end DESC
        ) AS recent_rank

    FROM quarterly_metrics_reconciled
),

recent_eight AS (

    -- 2. Four current + four prior quarters
    SELECT *
    FROM ranked
    WHERE recent_rank <= 8
),

continuity AS (

    -- 3. Verify consecutive fiscal periods
    SELECT
        *,

        LAG(period_end) OVER (
            PARTITION BY ticker
            ORDER BY period_start
        ) AS previous_end

    FROM recent_eight
),

aggregated AS (

    -- 4. Aggregate 8 quarters by company
    SELECT
        ticker,

        COUNT(*) AS quarters_checked,

        MIN(
            CASE WHEN recent_rank <= 4
            THEN period_start END
        ) AS ltm_start,

        MAX(
            CASE WHEN recent_rank <= 4
            THEN period_end END
        ) AS ltm_end,

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
            THEN available_date END
        ) AS latest_available_date,

        MAX(
            CASE WHEN recent_rank = 1
            THEN as_of_date END
        ) AS data_as_of,

        -- Current LTM
        SUM(
            CASE WHEN recent_rank <= 4
            THEN revenue_usd ELSE 0 END
        ) AS ltm_revenue,

        SUM(
            CASE WHEN recent_rank <= 4
            THEN operating_income_usd ELSE 0 END
        ) AS ltm_operating_income,

        SUM(
            CASE WHEN recent_rank <= 4
            THEN ocf_usd ELSE 0 END
        ) AS ltm_ocf,

        SUM(
            CASE WHEN recent_rank <= 4
            THEN capex_usd ELSE 0 END
        ) AS ltm_capex,

        SUM(
            CASE WHEN recent_rank <= 4
            THEN fcf_usd ELSE 0 END
        ) AS ltm_fcf,

        -- Prior LTM revenue
        SUM(
            CASE WHEN recent_rank BETWEEN 5 AND 8
            THEN revenue_usd ELSE 0 END
        ) AS prior_ltm_revenue,

        -- Latest reported quarter indicators
        MAX(
            CASE WHEN recent_rank = 1
            THEN revenue_growth_yoy_pct END
        ) AS latest_quarter_revenue_yoy_pct,

        MAX(
            CASE WHEN recent_rank = 1
            THEN operating_margin_pct END
        ) AS latest_quarter_operating_margin_pct,

        MAX(
            CASE WHEN recent_rank = 1
            THEN fcf_margin_pct END
        ) AS latest_quarter_fcf_margin_pct,

        MAX(capex_tag) AS capex_tag,

        -- Data-quality checks
        SUM(
            CASE
                WHEN previous_end IS NOT NULL
                 AND date_diff(
                     'day', previous_end, period_start
                 ) <> 1
                THEN 1 ELSE 0
            END
        ) AS continuity_errors,

        SUM(
            CASE
                WHEN revenue_usd IS NULL
                  OR operating_income_usd IS NULL
                  OR ocf_usd IS NULL
                  OR capex_usd IS NULL
                  OR fcf_usd IS NULL
                THEN 1 ELSE 0
            END
        ) AS missing_metric_rows,

        COUNT(*) FILTER (
            WHERE recent_rank <= 4
              AND validation_status =
                  'RECONCILED_SUPPLEMENTAL'
        ) AS supplemental_ltm_quarters,

        COUNT(*) FILTER (
            WHERE validation_status NOT IN (
                'PASS',
                'RECONCILED_SUPPLEMENTAL'
            )
        ) AS review_rows

    FROM continuity

    GROUP BY ticker
)

-- 5. Final comparison table
SELECT
    ticker,

    latest_fiscal_year,
    latest_fiscal_quarter,

    ltm_start,
    ltm_end,
    latest_available_date,
    data_as_of,

    -- USD billions
    ROUND(
        CAST(ltm_revenue AS DOUBLE) / 1e9, 3
    ) AS ltm_revenue_bn,

    ROUND(
        CAST(ltm_operating_income AS DOUBLE)
        / 1e9, 3
    ) AS ltm_operating_income_bn,

    ROUND(
        CAST(ltm_ocf AS DOUBLE) / 1e9, 3
    ) AS ltm_ocf_bn,

    ROUND(
        CAST(ltm_capex AS DOUBLE) / 1e9, 3
    ) AS ltm_capex_bn,

    ROUND(
        CAST(ltm_fcf AS DOUBLE) / 1e9, 3
    ) AS ltm_simple_fcf_bn,

    -- LTM revenue growth YoY
    ROUND(
        (
            CAST(ltm_revenue AS DOUBLE)
            / NULLIF(
                CAST(prior_ltm_revenue AS DOUBLE), 0
            ) - 1
        ) * 100,
        2
    ) AS ltm_revenue_growth_yoy_pct,

    -- LTM operating profitability
    ROUND(
        100.0 * ltm_operating_income
        / NULLIF(ltm_revenue, 0),
        2
    ) AS ltm_operating_margin_pct,

    -- LTM simple FCF margin
    ROUND(
        100.0 * ltm_fcf
        / NULLIF(ltm_revenue, 0),
        2
    ) AS ltm_simple_fcf_margin_pct,

    latest_quarter_revenue_yoy_pct,
    latest_quarter_operating_margin_pct,
    latest_quarter_fcf_margin_pct,

    capex_tag,
    supplemental_ltm_quarters,

    CASE
        WHEN ticker = 'NVDA'
        THEN 'CAPEX_DEFINITION_PROVISIONAL'
        ELSE 'PPE_CAPEX'
    END AS fcf_definition_status,

    CASE
        WHEN quarters_checked = 8
         AND continuity_errors = 0
         AND missing_metric_rows = 0
         AND review_rows = 0
         AND prior_ltm_revenue > 0
         AND ltm_revenue > 0
         AND ltm_fcf = ltm_ocf - ltm_capex
        THEN 'PASS'
        ELSE 'REVIEW'
    END AS internal_validation

FROM aggregated

ORDER BY ticker;