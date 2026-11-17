
-- ==================================================
-- JK's Financial Data Lab V1.0
-- Week 3: Reconciled Quarterly Metrics Audit
-- Companies: PLTR, NVDA
-- ==================================================

WITH coverage AS (

    SELECT
        COUNT(*) AS total_rows,

        COUNT(DISTINCT
            ticker || '-' ||
            CAST(fiscal_year AS VARCHAR) || '-' ||
            CAST(fiscal_quarter AS VARCHAR)
        ) AS unique_quarters,

        COUNT(*) FILTER (
            WHERE ticker = 'PLTR'
        ) AS pltr_quarters,

        COUNT(*) FILTER (
            WHERE ticker = 'NVDA'
        ) AS nvda_quarters,

        COUNT(*) FILTER (
            WHERE validation_status = 'PASS'
        ) AS direct_pass_rows,

        COUNT(*) FILTER (
            WHERE validation_status =
                'RECONCILED_SUPPLEMENTAL'
        ) AS supplemental_rows,

        COUNT(*) FILTER (
            WHERE validation_status = 'REVIEW'
        ) AS review_rows

    FROM quarterly_metrics_reconciled
),

arithmetic_checks AS (

    SELECT
        COUNT(*) FILTER (
            WHERE revenue_usd IS NULL
               OR operating_income_usd IS NULL
               OR ocf_usd IS NULL
               OR capex_usd IS NULL
               OR fcf_usd IS NULL
        ) AS missing_core_errors,

        COUNT(*) FILTER (
            WHERE fcf_usd IS DISTINCT FROM
                (ocf_usd - capex_usd)
        ) AS fcf_errors,

        COUNT(*) FILTER (
            WHERE operating_margin_pct
                IS DISTINCT FROM ROUND(
                    100.0 * operating_income_usd
                    / NULLIF(revenue_usd, 0),
                    2
                )
        ) AS operating_margin_errors,

        COUNT(*) FILTER (
            WHERE fcf_margin_pct
                IS DISTINCT FROM ROUND(
                    100.0 * fcf_usd
                    / NULLIF(revenue_usd, 0),
                    2
                )
        ) AS fcf_margin_errors,

        COUNT(*) FILTER (
            WHERE available_date IS NULL
               OR available_date > as_of_date
        ) AS availability_errors

    FROM quarterly_metrics_reconciled
),

yoy_checks AS (

    SELECT
        COUNT(*) FILTER (
            WHERE p.revenue_usd IS NOT NULL
              AND (
                r.revenue_growth_yoy_pct
                IS DISTINCT FROM ROUND(
                    100.0 *
                    (r.revenue_usd - p.revenue_usd)
                    / NULLIF(p.revenue_usd, 0),
                    2
                )

                OR

                r.operating_margin_yoy_change_pp
                IS DISTINCT FROM ROUND(
                    100.0 * r.operating_income_usd
                    / NULLIF(r.revenue_usd, 0)
                    -
                    100.0 * p.operating_income_usd
                    / NULLIF(p.revenue_usd, 0),
                    2
                )
              )
        ) AS yoy_errors

    FROM quarterly_metrics_reconciled r

    LEFT JOIN quarterly_metrics_reconciled p
      ON r.ticker = p.ticker
     AND r.fiscal_year = p.fiscal_year + 1
     AND r.fiscal_quarter = p.fiscal_quarter
),

preservation_checks AS (

    SELECT
        COUNT(*) AS matching_keys,

        COUNT(*) FILTER (
            WHERE NOT (
                b.ticker = 'NVDA'
                AND b.fiscal_year = 2024
                AND b.fiscal_quarter = 3
            )
            AND (
                r.revenue_usd
                    IS DISTINCT FROM b.revenue_usd
                OR r.operating_income_usd
                    IS DISTINCT FROM b.operating_income_usd
                OR r.ocf_usd
                    IS DISTINCT FROM b.ocf_usd
                OR r.capex_usd
                    IS DISTINCT FROM b.capex_usd
                OR r.fcf_usd
                    IS DISTINCT FROM b.fcf_usd
                OR r.operating_margin_pct
                    IS DISTINCT FROM b.operating_margin_pct
                OR r.fcf_margin_pct
                    IS DISTINCT FROM b.fcf_margin_pct
                OR r.validation_status
                    IS DISTINCT FROM b.validation_status
                OR r.available_date
                    IS DISTINCT FROM b.available_date
            )
        ) AS unexpected_modified_rows

    FROM quarterly_metrics_multi b

    INNER JOIN quarterly_metrics_reconciled r
      USING (
          cik,
          fiscal_year,
          fiscal_quarter
      )
),

supplement_check AS (

    SELECT
        COUNT(*) AS target_rows,

        COUNT(*) FILTER (
            WHERE b.capex_usd IS NULL
              AND b.validation_status = 'REVIEW'

              AND r.capex_usd = 278000000
              AND r.ocf_usd = 7332000000
              AND r.fcf_usd = 7054000000
              AND r.fcf_margin_pct = 38.93

              AND r.available_date =
                  DATE '2023-11-21'

              AND r.validation_status =
                  'RECONCILED_SUPPLEMENTAL'

              AND r.reconciliation_method =
                  '9M_YTD_MINUS_6M_YTD'

              AND r.reconciliation_json IS NOT NULL
        ) AS valid_target_rows

    FROM quarterly_metrics_multi b

    INNER JOIN quarterly_metrics_reconciled r
      USING (
          cik,
          fiscal_year,
          fiscal_quarter
      )

    WHERE b.ticker = 'NVDA'
      AND b.fiscal_year = 2024
      AND b.fiscal_quarter = 3
)

SELECT
    c.total_rows,
    c.unique_quarters,

    c.pltr_quarters,
    c.nvda_quarters,

    c.direct_pass_rows,
    c.supplemental_rows,
    c.review_rows,

    a.missing_core_errors,
    a.fcf_errors,
    a.operating_margin_errors,
    a.fcf_margin_errors,
    a.availability_errors,

    y.yoy_errors,

    p.unexpected_modified_rows,

    CASE
        WHEN c.total_rows = 24
         AND c.unique_quarters = 24

         AND c.pltr_quarters = 12
         AND c.nvda_quarters = 12

         AND c.direct_pass_rows = 23
         AND c.supplemental_rows = 1
         AND c.review_rows = 0

         AND a.missing_core_errors = 0
         AND a.fcf_errors = 0
         AND a.operating_margin_errors = 0
         AND a.fcf_margin_errors = 0
         AND a.availability_errors = 0

         AND y.yoy_errors = 0

         AND p.matching_keys = 24
         AND p.unexpected_modified_rows = 0

         AND s.target_rows = 1
         AND s.valid_target_rows = 1

        THEN 'PASS'
        ELSE 'REVIEW'
    END AS validation_result

FROM coverage c
CROSS JOIN arithmetic_checks a
CROSS JOIN yoy_checks y
CROSS JOIN preservation_checks p
CROSS JOIN supplement_check s;