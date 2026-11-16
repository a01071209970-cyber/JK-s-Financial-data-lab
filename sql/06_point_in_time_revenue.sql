
-- Week 2: Point-in-Time Revenue Selection
-- Company: PLTR
-- Target period: FY2025 Q3

WITH checkpoints AS (
    SELECT DATE '2025-10-31' AS as_of_date

    UNION ALL
    SELECT DATE '2025-11-05'

    UNION ALL
    SELECT DATE '2026-11-16'
),

ranked_facts AS (
    SELECT
        c.as_of_date,

        f.period_start,
        f.period_end,
        f.filed,
        f.accn,

        TRY_CAST(f.value_raw AS BIGINT)
            AS revenue_usd,

        ROW_NUMBER() OVER (
            PARTITION BY c.as_of_date
            ORDER BY
                f.filed DESC NULLS LAST,
                f.accn DESC NULLS LAST
        ) AS version_rank

    FROM checkpoints c

    LEFT JOIN financial_facts f
        ON f.cik = 1321655
        AND f.taxonomy = 'us-gaap'
        AND f.tag =
            'RevenueFromContractWithCustomerExcludingAssessedTax'
        AND f.unit = 'USD'
        AND f.form IN (
            '10-Q', '10-K', '10-Q/A', '10-K/A'
        )

        -- 분석 대상 분기
        AND f.period_start = DATE '2025-07-01'
        AND f.period_end = DATE '2025-09-30'

        -- 핵심: 기준일 이후의 공시 제외
        AND f.filed <= c.as_of_date
)

SELECT
    as_of_date,
    filed AS selected_filing_date,
    accn,
    revenue_usd,

    CASE
        WHEN filed IS NULL
        THEN 'NOT_YET_AVAILABLE'
        ELSE 'AVAILABLE'
    END AS data_status

FROM ranked_facts

WHERE version_rank = 1

ORDER BY as_of_date;