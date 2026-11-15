
SELECT
    period_start,
    period_end,
    filed,
    form,
    accn,
    value_num AS revenue_usd
FROM financial_facts
WHERE cik = 1321655
    AND taxonomy = 'us-gaap'
    AND tag = 'RevenueFromContractWithCustomerExcludingAssessedTax'
    AND unit = 'USD'
    AND form IN ('10-Q', '10-K')
ORDER BY
    filed DESC,
    period_end DESC,
    period_start DESC
LIMIT 10;