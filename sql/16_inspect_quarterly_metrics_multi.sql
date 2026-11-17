
-- JK's Financial Data Lab V1.0
-- Week 3: Inspect multi-company quarterly metrics

SELECT
    ticker,
    fiscal_year,
    fiscal_quarter,

    revenue_usd,
    operating_income_usd,
    ocf_usd,
    capex_usd,
    fcf_usd,

    revenue_growth_yoy_pct,
    operating_margin_pct,
    fcf_margin_pct,

    available_date,
    validation_status

FROM quarterly_metrics_multi

ORDER BY
    ticker,
    fiscal_year DESC,
    fiscal_quarter DESC;