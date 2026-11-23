# Data dictionary

`python scripts/pull_prices.py` writes six tables. Each is saved three ways: `data/<table>.csv`, a table in `data/markets.db` (SQLite) and a sheet in `data/markets.xlsx`. Join any table to `dim_ticker` on `ticker`. Definitions are in [methodology.md](methodology.md).

## fact_prices
**Grain:** one row per ETF per trading day (2 × 1,255 = 2,510 rows).

| Column | Type | Description |
|---|---|---|
| `date` | date | Trading day |
| `open`, `high`, `low`, `close` | decimal | Adjusted prices (splits and dividends) |
| `volume` | integer | Shares traded |
| `ticker` | text | ETF symbol, joins to `dim_ticker` |
| `daily_return` | decimal | close ÷ previous close − 1; blank on the first day |
| `running_peak` | decimal | Highest close so far in the sample |
| `drawdown` | decimal | close ÷ running_peak − 1; 0 at a new high |
| `indexed` | decimal | Growth of 100 from the first close |
| `rolling_vol_21d` | decimal | Annualised volatility over the last 21 trading days |
| `rolling_vol_63d` | decimal | Annualised volatility over the last 63 trading days |
| `rolling_return_252d` | decimal | Return over the last 252 trading days |

## dim_ticker
**Grain:** one row per ETF.

| Column | Type | Description |
|---|---|---|
| `ticker` | text | ETF symbol (key) |
| `name` | text | Display name |
| `asset_type` | text | "ETF" |
| `sector` | text | "Broad Market" or the sector |
| `country` | text | Market covered |

## kpi_summary
**Grain:** one row per ETF, covering the whole sample.

| Column | Type | Description |
|---|---|---|
| `ticker` | text | ETF symbol |
| `total_return` | decimal | Last close ÷ first close − 1 |
| `cagr` | decimal | Compound annual growth rate |
| `annual_volatility` | decimal | Sample std of daily returns × √252 |
| `max_drawdown` | decimal | Most negative drawdown |
| `max_drawdown_date` | date | Day of the maximum drawdown |
| `latest_close` | decimal | Last adjusted close |
| `sharpe_ratio` | decimal | Excess return per unit of volatility (risk-free 3.2%) |
| `sortino_ratio` | decimal | Excess return per unit of downside volatility |
| `calmar_ratio` | decimal | CAGR ÷ \|max_drawdown\| |
| `max_drawdown_recovery_date` | date | First close back at the pre-crash peak; blank if not recovered |
| `days_to_recover` | integer | Trading days from the max-drawdown trough to recovery |
| `longest_underwater_days` | integer | Longest peak-to-recovery episode, in trading days |

## monthly_returns
**Grain:** one row per ETF per calendar month (2 × 60 rows).

| Column | Type | Description |
|---|---|---|
| `ticker` | text | ETF symbol |
| `year` | integer | Calendar year |
| `month` | integer | Month number, 1–12 |
| `month_label` | text | "YYYY-MM" |
| `monthly_return` | decimal | Month-end close ÷ previous month-end close − 1 |

## annual_returns
**Grain:** one row per ETF per calendar year (2 × 5 rows).

| Column | Type | Description |
|---|---|---|
| `ticker` | text | ETF symbol |
| `year` | integer | Calendar year |
| `annual_return` | decimal | Year-end close ÷ previous year-end close − 1 |

## drawdown_periods
**Grain:** one row per drawdown episode per ETF (peak → trough → recovery).

| Column | Type | Description |
|---|---|---|
| `ticker` | text | ETF symbol |
| `peak_date` | date | Last day at the running peak before the fall |
| `trough_date` | date | Lowest point of the episode |
| `recovery_date` | date | First close back at the peak; blank if still open |
| `depth` | decimal | Drawdown at the trough |
| `days_peak_to_trough` | integer | Trading days from peak to trough |
| `days_trough_to_recovery` | integer | Trading days from trough to recovery; blank if open |
| `days_underwater` | integer | Trading days from peak to recovery (or to the last day if open) |
| `recovered` | boolean | Whether the ETF got back to the peak within the sample |
