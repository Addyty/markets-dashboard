"""Download daily prices for SPY and XLK, calculate KPIs, and save files for Tableau.

Run from the project root:
    python scripts/pull_prices.py
"""
import sqlite3
from pathlib import Path

import pandas as pd
import yfinance as yf

# Date range. yfinance excludes the end date, so 2026-01-01 includes all of 2025.
START = "2021-01-01"
END = "2026-01-01"

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
    """Download daily prices for each ticker and stack them into one long table."""
    frames = []
    for t in tickers:
        df = yf.Ticker(t).history(start=START, end=END, auto_adjust=True)
        if df.empty:
            print(f"No data returned for {t}")
            continue
        df = df.reset_index()[["Date", "Open", "High", "Low", "Close", "Volume"]]
        df["ticker"] = t
        frames.append(df)
    if not frames:
        raise SystemExit("No data downloaded. Check your internet connection and try again.")
    out = pd.concat(frames, ignore_index=True)
    # Remove the timezone so dates save cleanly to CSV and SQLite
    out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None)
    return out.rename(columns=str.lower)


def add_metrics(df):
    """Add daily return, running peak, drawdown and growth-of-100 columns."""
    df = df.sort_values(["ticker", "date"]).copy()
    grp = df.groupby("ticker")["close"]
    df["daily_return"] = grp.pct_change()                # today vs yesterday
    df["running_peak"] = grp.cummax()                    # highest close so far
    df["drawdown"] = df["close"] / df["running_peak"] - 1
    df["indexed"] = grp.transform(lambda s: s / s.iloc[0] * 100)
    return df


def summarize(df):
    """One row per ticker with the headline KPIs."""
    rows = []
    for t, g in df.groupby("ticker"):
        first, last = g["close"].iloc[0], g["close"].iloc[-1]
        years = (g["date"].iloc[-1] - g["date"].iloc[0]).days / 365.25
        worst = g.loc[g["drawdown"].idxmin()]
        rows.append({
            "ticker": t,
            "total_return": last / first - 1,
            "cagr": (last / first) ** (1 / years) - 1,
            "annual_volatility": g["daily_return"].std() * (252 ** 0.5),
            "max_drawdown": worst["drawdown"],
            "max_drawdown_date": worst["date"].date(),
            "latest_close": last,
        })
    return pd.DataFrame(rows)


def save(prices, summary):
    """Write CSVs for Tableau and a SQLite database for SQL practice."""
    OUT.mkdir(exist_ok=True)
    dim = pd.DataFrame([{"ticker": t, **meta} for t, meta in TICKERS.items()])

    prices.to_csv(OUT / "fact_prices.csv", index=False)
    dim.to_csv(OUT / "dim_ticker.csv", index=False)
    summary.to_csv(OUT / "kpi_summary.csv", index=False)

    conn = sqlite3.connect(OUT / "markets.db")
    prices.to_sql("fact_prices", conn, if_exists="replace", index=False)
    dim.to_sql("dim_ticker", conn, if_exists="replace", index=False)
    summary.to_sql("kpi_summary", conn, if_exists="replace", index=False)
    conn.close()

    # One Excel file, three sheets: easiest to upload to Tableau Cloud
    with pd.ExcelWriter(OUT / "markets.xlsx") as xl:
        prices.to_excel(xl, sheet_name="fact_prices", index=False)
        dim.to_excel(xl, sheet_name="dim_ticker", index=False)
        summary.to_excel(xl, sheet_name="kpi_summary", index=False)


if __name__ == "__main__":
    prices = fetch_prices(list(TICKERS))
    metrics = add_metrics(prices)
    summary = summarize(metrics)
    save(metrics, summary)
    print(summary.round(4).to_string(index=False))
    print(f"\nSaved {len(metrics):,} price rows to {OUT}")
