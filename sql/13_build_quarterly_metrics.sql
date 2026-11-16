
-- JK's Financial Data Lab V1.0
-- Week 2: Integrated Quarterly Metrics
-- PLTR | First-Available | 2026-11-16 cutoff

CREATE OR REPLACE TABLE quarterly_metrics AS

WITH merged AS (
    SELECT
        r.fiscal_year,
        r.fiscal_quarter,

        r.revenue_usd,
        o.operating_income_usd,
        c.ocf_usd,
        c.capex_usd,
        c.fcf_usd,

        r.calculation_method AS revenue_method,
        o.calculation_method AS income_method,
        c.calculation_method AS cashflow_method,

        r.source_filed AS revenue_filed,
        o.source_filed AS income_filed,
        c.available_date AS cashflow_filed,

        GREATEST(
            r.source_filed,
            o.source_filed,
            c.available_date
        ) AS available_date,

        r.source_accn AS revenue_accn,
        r.support_accn AS revenue_support_accn,

        o.source_accn AS income_accn,
        o.support_accn AS income_support_accn,

        c.ocf_accn,
        c.capex_accn,
        c.ocf_previous_accn,
        c.capex_previous_accn

    FROM quarterly_revenue r

    INNER JOIN quarterly_operating_income o
        USING (fiscal_year, fiscal_quarter)

    INNER JOIN quarterly_cashflow c
        USING (fiscal_year, fiscal_quarter)

    WHERE c.validation_status = 'PASS'
),

-- Calculate profitability ratios
ratios AS (
    SELECT
        *,

        100.0 * operating_income_usd
            / NULLIF(revenue_usd, 0)
            AS operating_margin_raw,

        100.0 * fcf_usd
            / NULLIF(revenue_usd, 0)
            AS fcf_margin_raw

    FROM merged
),

-- Compare with the same quarter last year
lagged AS (
    SELECT
        *,

        LAG(revenue_usd, 4) OVER (
            ORDER BY fiscal_year, fiscal_quarter
        ) AS prior_year_revenue,

        LAG(operating_margin_raw, 4) OVER (
            ORDER BY fiscal_year, fiscal_quarter
        ) AS prior_year_operating_margin

    FROM ratios
)

SELECT
    fiscal_year,
    fiscal_quarter,

    revenue_usd,
    operating_income_usd,
    ocf_usd,
    capex_usd,
    fcf_usd,

    ROUND(operating_margin_raw, 2)
        AS operating_margin_pct,

    ROUND(fcf_margin_raw, 2)
        AS fcf_margin_pct,

    ROUND(
        (
            CAST(revenue_usd AS DOUBLE)
            / NULLIF(
                CAST(prior_year_revenue AS DOUBLE), 0
            ) - 1
        ) * 100.0,
        2
    ) AS revenue_growth_yoy_pct,

    ROUND(
        operating_margin_raw
        - prior_year_operating_margin,
        2
    ) AS operating_margin_yoy_change_pp,

    revenue_method,
    income_method,
    cashflow_method,

    available_date,
    revenue_filed,
    income_filed,
    cashflow_filed,

    revenue_accn,
    revenue_support_accn,
    income_accn,
    income_support_accn,
    ocf_accn,
    capex_accn,
    ocf_previous_accn,
    capex_previous_accn

FROM lagged

ORDER BY fiscal_year, fiscal_quarter;