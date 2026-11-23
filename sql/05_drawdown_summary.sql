-- Business question:
--   How deep were each ETF's losses from its peak, and how much of the time
--   was an investor sitting on a loss?
--
-- Drawdown = close ÷ highest close so far − 1 (calculated by the pipeline).
-- The running peak starts on 4 January 2021 (see docs/methodology.md).

WITH worst_day AS (
    SELECT
        ticker,
        date(date) AS max_drawdown_date,
        drawdown,
        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY drawdown ASC) AS rn
    FROM fact_prices
)
SELECT
    p.ticker,
    ROUND(MIN(p.drawdown), 4)                AS max_drawdown,
    w.max_drawdown_date,
    COUNT(*)                                 AS trading_days,
    SUM(p.drawdown < 0)                      AS days_below_peak,
    SUM(p.drawdown <= -0.10)                 AS days_10pct_or_more_below,
    SUM(p.drawdown <= -0.20)                 AS days_20pct_or_more_below,
    ROUND(AVG(p.drawdown < 0), 3)            AS share_of_days_below_peak
FROM fact_prices AS p
JOIN worst_day AS w ON w.ticker = p.ticker AND w.rn = 1
GROUP BY p.ticker, w.max_drawdown_date
ORDER BY p.ticker;
