
-- ===================================================
-- JK's Financial Data Lab V1.0
-- Week 2: Quarterly Operating Margin
-- PLTR | 2023 Q4 - 2026 Q3
-- ===================================================

SELECT
    r.fiscal_year,
    r.fiscal_quarter,

    -- 1. Revenue
    CAST(r.revenue_usd AS BIGINT)
        AS revenue_usd,

    -- 2. Operating Income
    CAST(o.operating_income_usd AS BIGINT)
        AS operating_income_usd,

    -- 3. Operating Margin (%)
    ROUND(
        o.operating_income_usd * 100.0
        / NULLIF(r.revenue_usd, 0),
        2
    ) AS operating_margin_pct,

    -- 4. Data provenance
    r.calculation_method AS revenue_method,
    o.calculation_method AS income_method,

    -- 5. Both metrics become available
    GREATEST(
        r.source_filed,
        o.source_filed
    ) AS available_date,

    -- 6. Original SEC filing identifiers
    r.source_accn AS revenue_accn,
    o.source_accn AS income_accn

FROM quarterly_revenue r

INNER JOIN quarterly_operating_income o
    ON r.fiscal_year = o.fiscal_year
   AND r.fiscal_quarter = o.fiscal_quarter

WHERE r.revenue_usd IS NOT NULL
  AND o.operating_income_usd IS NOT NULL

ORDER BY
    r.fiscal_year DESC,
    r.fiscal_quarter DESC;