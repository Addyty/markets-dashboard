-- Business question:
--   What did each ETF return month by month?
--
-- Monthly return = last close of the month ÷ last close of the previous month − 1.
-- The first month (January 2021) is measured from the first observed close,
-- matching the project's return convention (see docs/methodology.md).
-- Output: one row per ETF per month (60 months per ETF), ready for a heatmap.

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
)
SELECT
    m.ticker,
    m.month,
    ROUND(
        m.close / COALESCE(LAG(m.close) OVER (PARTITION BY m.ticker ORDER BY m.month),
                           f.first_close) - 1,
        4
    ) AS monthly_return
FROM month_end AS m
JOIN first_close AS f USING (ticker)
WHERE m.rn = 1
ORDER BY m.ticker, m.month;
