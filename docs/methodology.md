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

## Risk-free rate
Sharpe and Sortino ratios use a fixed **3.2% a year**: the average of the 13-week US Treasury bill yield (`^IRX` on Yahoo Finance) over the same 1,255 trading days, which was 3.21%. The yearly averages were 0.03% (2021), 2.0% (2022), 5.05% (2023), 4.95% (2024) and 4.05% (2025). A single average keeps the ratios simple and reproducible; a day-by-day rate would change them only slightly. The daily rate is 3.2% ÷ 252.

## Risk-adjusted ratios
Daily excess return = daily return − 3.2% ÷ 252.

| Ratio | Definition | Reads as |
|---|---|---|
| Sharpe | mean(excess) ÷ sample std(excess) × √252 | return above cash per unit of total volatility |
| Sortino | mean(excess) ÷ downside deviation × √252, where downside deviation = √(mean of min(excess, 0)²) over all days | return above cash per unit of *downside* volatility only |
| Calmar | CAGR ÷ \|max drawdown\| | yearly growth per unit of the worst loss |

Calmar and Sortino are left blank if there is no drawdown or no below-target day, rather than dividing by zero.

## Rolling metrics
Columns in `fact_prices`, each calculated from the window ending on that day (no look-ahead) and blank until the window is full:

| Column | Window | Definition |
|---|---|---|
| `rolling_vol_21d` | 21 trading days (≈ 1 month) | sample std of daily returns × √252 |
| `rolling_vol_63d` | 63 trading days (≈ 3 months) | sample std of daily returns × √252 |
| `rolling_return_252d` | 252 trading days (≈ 1 year) | close ÷ close 252 trading days earlier − 1 |

## Drawdown episodes and recovery
An **episode** starts on the last day at a running peak, reaches its **trough** (the lowest drawdown in the episode) and ends on the **recovery** day, the first close back at or above that peak. Durations are counted in **trading days**:

- days peak → trough
- days trough → recovery ("time to recover")
- days underwater = peak → recovery. For an episode still open at the end of the sample, this runs to the last day and the recovery date is blank.

`kpi_summary` reports the recovery date and days to recover for the episode holding the maximum drawdown, and the longest time underwater across all episodes.

## Monthly and annual returns
Period return = last close of the period ÷ last close of the previous period that had trading − 1. The first period is measured from the first observed close, the same convention as above. The tables match `sql/02_annual_returns.sql` and `sql/03_monthly_returns.sql`, and compound back to the five-year total return.

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
