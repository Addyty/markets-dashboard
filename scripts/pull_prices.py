"""Download daily prices for SPY and XLK, calculate KPIs, and save files for Tableau.

Run from the project root:
    python scripts/pull_prices.py
"""
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
import yfinance as yf

# Date range. yfinance excludes the end date, so 2026-01-01 includes all of 2025.
START = "2021-01-01"
END = "2026-01-01"

# US trading days in a year, used to annualise daily figures
TRADING_DAYS = 252

# Annual risk-free rate for the Sharpe and Sortino ratios. The 13-week US Treasury
# bill yield (^IRX) averaged 3.21% over 2021-2025, rounded to 3.2%.
# See docs/methodology.md.
RISK_FREE_RATE = 0.032

# Output folder, resolved from this file so the script works from any directory
OUT = Path(__file__).resolve().parent.parent / "data"

# The tickers we track, with descriptive fields for the dim_ticker table.
# SPY (not ^GSPC) is the benchmark because its adjusted prices include
# reinvested dividends, the same as the sector ETFs.
TICKERS = {
    "SPY": {"name": "S&P 500 (SPY)", "asset_type": "ETF", "sector": "Broad Market", "country": "United States"},
    "XLK": {"name": "Technology Select Sector SPDR", "asset_type": "ETF", "sector": "Technology", "country": "United States"},
}


def fetch_prices(tickers):
    """Download daily prices for each ticker and stack them into one long table.

    Stops the run if any ticker returns no data, so a partial dataset
    can never be saved and mistaken for a complete one.
    """
    frames, missing = [], []
    for t in tickers:
        df = yf.Ticker(t).history(start=START, end=END, auto_adjust=True)
        if df.empty:
            missing.append(t)
            continue
        df = df.reset_index()[["Date", "Open", "High", "Low", "Close", "Volume"]]
        df["ticker"] = t
        frames.append(df)
    if missing:
        raise SystemExit(
            f"No data returned for: {', '.join(missing)}. "
            "Stopping so that no incomplete files are saved."
        )
    out = pd.concat(frames, ignore_index=True)
    # Remove the timezone so dates save cleanly to CSV and SQLite
    out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None)
    return out.rename(columns=str.lower)


def validate(df, tickers):
    """Run data-quality checks on the raw prices.

    Prints a PASS/FAIL report and stops the run if any check fails,
    before anything is written to disk.
    """
    checks = []

    def check(name, passed, detail=""):
        checks.append((name, bool(passed), detail))

    price_cols = ["open", "high", "low", "close"]

    # 1. Coverage: every requested ticker came back
    found = sorted(df["ticker"].unique())
    check("All requested tickers present", set(found) == set(tickers), f"found {found}")

    # 2. Uniqueness: one row per ticker per day
    dupes = int(df.duplicated(["ticker", "date"]).sum())
    check("No duplicate ticker-date rows", dupes == 0, f"{dupes} duplicates")

    # 3. Completeness: no blank prices
    nulls = int(df[price_cols].isna().sum().sum())
    check("No missing prices", nulls == 0, f"{nulls} missing values")

    # 4. Plausibility: prices must be positive, and high must be >= low
    bad = int((df[price_cols] <= 0).sum().sum())
    check("All prices positive", bad == 0, f"{bad} zero or negative values")
    inverted = int((df["high"] < df["low"]).sum())
    check("High >= low on every row", inverted == 0, f"{inverted} rows")

    # 5. Window: no dates outside START..END
    first, last = df["date"].min(), df["date"].max()
    in_window = first >= pd.Timestamp(START) and last < pd.Timestamp(END)
    check("Dates inside the requested window", in_window, f"{first.date()} to {last.date()}")

    # 6. Order: dates run forwards for each ticker
    ordered = all(g["date"].is_monotonic_increasing for _, g in df.groupby("ticker"))
    check("Dates in chronological order", ordered)

    # 7. Alignment: every ticker has exactly the same trading dates
    date_sets = df.groupby("ticker")["date"].apply(frozenset)
    check("Same trading dates for every ticker", len(set(date_sets)) == 1)

    # 8. Volume of data: about 252 trading days a year (allow +/- 2%)
    counts = df.groupby("ticker")["date"].count()
    years = (pd.Timestamp(END) - pd.Timestamp(START)).days / 365.25
    expected = 252 * years
    low, high = round(expected * 0.98), round(expected * 1.02)
    check(f"Trading days per ticker between {low} and {high}",
          counts.between(low, high).all(), counts.to_dict())

    # Report
    print("Data validation")
    for name, passed, detail in checks:
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {name}" + (f"  ({detail})" if detail != "" else ""))
    failed = [c for c in checks if not c[1]]
    if failed:
        raise SystemExit(f"\n{len(failed)} check(s) failed. No files were saved.")
    print(f"  All {len(checks)} checks passed.\n")


def add_metrics(df):
    """Add daily return, running peak, drawdown, growth-of-100 and rolling columns."""
    df = df.sort_values(["ticker", "date"]).copy()
    grp = df.groupby("ticker")["close"]
    df["daily_return"] = grp.pct_change()                # today vs yesterday
    df["running_peak"] = grp.cummax()                    # highest close so far
    df["drawdown"] = df["close"] / df["running_peak"] - 1
    df["indexed"] = grp.transform(lambda s: s / s.iloc[0] * 100)

    # Rolling windows, in trading days: 21 is about one month, 63 about three months.
    # Each value uses only the window ending on that day, and stays blank until
    # the window is full.
    ret = df.groupby("ticker")["daily_return"]
    df["rolling_vol_21d"] = ret.transform(lambda s: s.rolling(21).std() * TRADING_DAYS ** 0.5)
    df["rolling_vol_63d"] = ret.transform(lambda s: s.rolling(63).std() * TRADING_DAYS ** 0.5)
    df["rolling_return_252d"] = grp.transform(lambda s: s / s.shift(TRADING_DAYS) - 1)
    return df


def drawdown_periods(df):
    """One row per drawdown episode: from a peak, down to the trough, back to the peak.

    An episode starts on the last day at a running peak and ends on the first
    day the close gets back to that peak. Durations are counted in trading days.
    An episode still open at the end of the sample has no recovery date, and
    its time underwater runs to the last day.
    """
    rows = []
    for t, g in df.groupby("ticker"):
        g = g.reset_index(drop=True)
        underwater = g["drawdown"] < 0
        # A new episode begins on each day that goes from at-peak to below-peak
        episode = (underwater & ~underwater.shift(fill_value=False)).cumsum()
        for _, e in g[underwater].groupby(episode[underwater]):
            peak_i = e.index[0] - 1             # last day at the peak
            trough_i = e["drawdown"].idxmin()
            end_i = e.index[-1] + 1             # first day back at the peak
            recovered = end_i < len(g)
            rows.append({
                "ticker": t,
                "peak_date": g.loc[peak_i, "date"].date(),
                "trough_date": g.loc[trough_i, "date"].date(),
                "recovery_date": g.loc[end_i, "date"].date() if recovered else None,
                "depth": g.loc[trough_i, "drawdown"],
                "days_peak_to_trough": trough_i - peak_i,
                "days_trough_to_recovery": end_i - trough_i if recovered else None,
                "days_underwater": (end_i if recovered else len(g) - 1) - peak_i,
                "recovered": recovered,
            })
    out = pd.DataFrame(rows, columns=[
        "ticker", "peak_date", "trough_date", "recovery_date", "depth",
        "days_peak_to_trough", "days_trough_to_recovery", "days_underwater", "recovered",
    ])
    return out.astype({"days_trough_to_recovery": "Int64"})


def summarize(df):
    """One row per ticker with the headline KPIs."""
    rows = []
    for t, g in df.groupby("ticker"):
        first, last = g["close"].iloc[0], g["close"].iloc[-1]
        years = (g["date"].iloc[-1] - g["date"].iloc[0]).days / 365.25
        worst = g.loc[g["drawdown"].idxmin()]
        cagr = (last / first) ** (1 / years) - 1

        # Risk-adjusted returns use daily returns in excess of the risk-free rate
        excess = g["daily_return"].dropna() - RISK_FREE_RATE / TRADING_DAYS
        downside = ((excess.clip(upper=0) ** 2).mean()) ** 0.5   # only below-target days count
        sharpe = excess.mean() / excess.std() * TRADING_DAYS ** 0.5
        sortino = excess.mean() / downside * TRADING_DAYS ** 0.5 if downside > 0 else float("nan")
        calmar = cagr / abs(worst["drawdown"]) if worst["drawdown"] < 0 else float("nan")

        # Recovery: from the episode that holds the maximum drawdown
        episodes = drawdown_periods(g)
        if episodes.empty:
            recovery_date, days_to_recover, longest_underwater = None, None, 0
        else:
            deepest = episodes.loc[episodes["depth"].idxmin()]
            recovery_date = deepest["recovery_date"]
            days_to_recover = deepest["days_trough_to_recovery"]
            longest_underwater = int(episodes["days_underwater"].max())

        rows.append({
            "ticker": t,
            "total_return": last / first - 1,
            "cagr": cagr,
            "annual_volatility": g["daily_return"].std() * TRADING_DAYS ** 0.5,
            "max_drawdown": worst["drawdown"],
            "max_drawdown_date": worst["date"].date(),
            "latest_close": last,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "max_drawdown_recovery_date": recovery_date,
            "days_to_recover": None if pd.isna(days_to_recover) else int(days_to_recover),
            "longest_underwater_days": longest_underwater,
        })
    return pd.DataFrame(rows).astype({"days_to_recover": "Int64"})


def period_returns(df, freq):
    """Return per ETF per calendar period: period-end close ÷ previous period-end close − 1.

    freq is "ME" for months or "YE" for years. The first period is measured from
    the first observed close, the same convention as the SQL scripts.
    """
    frames = []
    for t, g in df.groupby("ticker"):
        close = g.set_index("date")["close"]
        # Drop empty periods, so each period compares with the last one that had trading
        ends = close.resample(freq).last().dropna()
        returns = ends / ends.shift(1).fillna(close.iloc[0]) - 1
        frames.append(pd.DataFrame({"ticker": t, "period_end": ends.index, "return": returns.values}))
    return pd.concat(frames, ignore_index=True)


def monthly_returns(df):
    """One row per ETF per month, with year and month number for a heatmap."""
    m = period_returns(df, "ME")
    return pd.DataFrame({
        "ticker": m["ticker"],
        "year": m["period_end"].dt.year,
        "month": m["period_end"].dt.month,
        "month_label": m["period_end"].dt.strftime("%Y-%m"),
        "monthly_return": m["return"],
    })


def annual_returns(df):
    """One row per ETF per calendar year."""
    a = period_returns(df, "YE")
    return pd.DataFrame({"ticker": a["ticker"], "year": a["period_end"].dt.year,
                         "annual_return": a["return"]})


def dim_ticker():
    """The descriptive table: one row per ETF."""
    return pd.DataFrame([{"ticker": t, **meta} for t, meta in TICKERS.items()])


def save(tables):
    """Write every table as a CSV, a SQLite table and an Excel sheet."""
    OUT.mkdir(exist_ok=True)
    with closing(sqlite3.connect(OUT / "markets.db")) as conn, \
            pd.ExcelWriter(OUT / "markets.xlsx") as xl:
        for name, table in tables.items():
            table.to_csv(OUT / f"{name}.csv", index=False)
            table.to_sql(name, conn, if_exists="replace", index=False)
            table.to_excel(xl, sheet_name=name, index=False)


if __name__ == "__main__":
    prices = fetch_prices(list(TICKERS))
    validate(prices, list(TICKERS))
    metrics = add_metrics(prices)
    summary = summarize(metrics)
    tables = {
        "fact_prices": metrics,
        "dim_ticker": dim_ticker(),
        "kpi_summary": summary,
        "monthly_returns": monthly_returns(metrics),
        "annual_returns": annual_returns(metrics),
        "drawdown_periods": drawdown_periods(metrics),
    }
    save(tables)
    print(summary.set_index("ticker").T.to_string())
    print(f"\nSaved {len(tables)} tables to {OUT}: {', '.join(tables)}")
