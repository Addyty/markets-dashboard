-- Business question:
--   How did each ETF perform in each calendar year, and which one won each year?
--
-- Annual return = last close of the year ÷ last close of the previous year − 1.
-- The first year (2021) is measured from the first observed close on 4 January 2021,
-- matching the project's return convention (see docs/methodology.md).
-- Compounding the yearly returns gives back the five-year total return.

WITH year_end AS (
    SELECT
        ticker,
        strftime('%Y', date) AS year,
        close,
        ROW_NUMBER() OVER (PARTITION BY ticker, strftime('%Y', date) ORDER BY date DESC) AS rn
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
annual AS (
    SELECT
        y.ticker,
        y.year,
        y.close / COALESCE(LAG(y.close) OVER (PARTITION BY y.ticker ORDER BY y.year),
                           f.first_close) - 1 AS annual_return
    FROM year_end AS y
    JOIN first_close AS f USING (ticker)
    WHERE y.rn = 1
)
SELECT
    year,
    ticker,
    ROUND(annual_return, 4)                                                    AS annual_return,
    RANK() OVER (PARTITION BY year ORDER BY annual_return DESC)                AS rank_in_year
FROM annual
ORDER BY year, rank_in_year;
