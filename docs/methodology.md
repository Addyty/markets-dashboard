# Methodology

## Data
- **Source:** Yahoo Finance via the `yfinance` Python package.
- **Tickers:** SPY (SPDR S&P 500 ETF Trust, used as the broad-market benchmark) and XLK (Technology Select Sector SPDR Fund).
- **Price basis:** `auto_adjust=True`. Open, high, low and close are adjusted for stock splits and dividends, so the adjusted close reflects total return with dividends reinvested. Both ETFs use the same basis.
- **Why SPY, not the S&P 500 index (`^GSPC`):** the index is a price index and excludes dividends. Comparing it with a dividend-adjusted sector ETF would understate the market's return.

## Sample window
- **Requested:** 1 January 2021 to 31 December 2025 (`START = 2021-01-01`, `END = 2026-01-01`; yfinance excludes the end date).
- **Observed:** first trading day 4 January 2021, last trading day 31 December 2025, 1,255 trading days per ETF.

## Return convention
All period returns are measured **from the first observed adjusted close (4 January 2021)** to the last (31 December 2025). The price move on 4 January 2021 itself is therefore not included. A calendar-year convention would use the 31 December 2020 close as the base; this project does not.

## KPI definitions
| KPI | Definition |
|---|---|
| Daily return | close(t) ÷ close(t−1) − 1. Blank for the first day. |
| Total return | last close ÷ first close − 1 |
| CAGR | (last close ÷ first close)^(1 ÷ years) − 1, where years = calendar days between the first and last date ÷ 365.25 |
| Annual volatility | **sample** standard deviation (n − 1) of daily returns × √252 |
| Running peak | highest close from the first day up to and including day t |
| Drawdown | close ÷ running peak − 1 |
| Max drawdown | the most negative drawdown in the sample, and its date |
| Growth of 100 | close ÷ first close × 100 |

- **Annualisation factor:** 252, the conventional number of US trading days in a year.
- **Drawdown window:** the running peak starts on 4 January 2021. Peaks before the sample are ignored, so drawdowns may understate losses from earlier all-time highs.

## Data-quality checks
Every run validates the raw prices before anything is saved, and stops if any check fails:

1. All requested tickers are present.
2. No duplicate ticker-date rows.
3. No missing open, high, low or close prices.
4. All prices are positive.
5. High ≥ low on every row.
6. All dates fall inside the requested window.
7. Dates are in chronological order for each ticker.
8. Every ticker has exactly the same trading dates.
9. Each ticker has 252 × years trading days, ±2%.

A download that returns no data for any ticker also stops the run.

## Verification
KPIs are calculated in Python (`kpi_summary`) and independently recalculated in Tableau with LOD expressions; the results match.

## Limitations
Yahoo Finance is not an official data source, and its adjusted history can be revised when new dividends are paid. Past performance does not predict future results.
