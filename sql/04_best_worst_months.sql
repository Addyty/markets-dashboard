-- Business question:
--   What were each ETF's best and worst months, and how often did it go up?
--
-- Builds on the monthly returns in 03_monthly_returns.sql (same definition, repeated
-- here so the script runs on its own), then summarises them per ETF.

WITH month_end AS (
    SELECT
        ticker,
        strftime('%Y-%m', date) AS month,
        close,
        ROW_NUMBER() OVER (PARTITION BY ticker, strftime('%Y-%m', date) ORDER BY date DESC) AS rn
    FROM fact_prices
),
first_close AS (
    SELECT ticker, close AS first_close
    FROM (
        SELECT ticker, close, ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date) AS rn
        FROM fact_prices
    )
    WHERE rn = 1
),
monthly AS (
    SELECT
        m.ticker,
        m.month,
        m.close / COALESCE(LAG(m.close) OVER (PARTITION BY m.ticker ORDER BY m.month),
                           f.first_close) - 1 AS monthly_return
    FROM month_end AS m
    JOIN first_close AS f USING (ticker)
    WHERE m.rn = 1
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY monthly_return DESC) AS best_rank,
        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY monthly_return ASC)  AS worst_rank
    FROM monthly
)
SELECT
    ticker,
    MAX(CASE WHEN best_rank = 1 THEN month END)   AS best_month,
    ROUND(MAX(monthly_return), 4)                 AS best_month_return,
    MAX(CASE WHEN worst_rank = 1 THEN month END)  AS worst_month,
    ROUND(MIN(monthly_return), 4)                 AS worst_month_return,
    COUNT(*)                                      AS months,
    SUM(monthly_return > 0)                       AS positive_months,
    ROUND(AVG(monthly_return > 0), 3)             AS positive_month_share
FROM ranked
GROUP BY ticker
ORDER BY ticker;
