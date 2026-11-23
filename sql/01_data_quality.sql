-- Business question:
--   Is the data complete and consistent before we analyse it?
--
-- One row per ETF. Every ETF should have the same row count and date range,
-- no duplicate dates, and no missing or non-positive closing prices.
-- (The Python pipeline enforces this too; this query lets an analyst re-check it in SQL.)

SELECT
    ticker,
    COUNT(*)                                AS trading_days,
    COUNT(DISTINCT date)                    AS distinct_dates,
    COUNT(*) - COUNT(DISTINCT date)         AS duplicate_dates,
    MIN(date(date))                         AS first_date,
    MAX(date(date))                         AS last_date,
    SUM(close IS NULL)                      AS missing_closes,
    SUM(close <= 0)                         AS non_positive_closes
FROM fact_prices
GROUP BY ticker
ORDER BY ticker;
