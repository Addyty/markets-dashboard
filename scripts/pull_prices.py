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
    validate(prices, list(TICKERS))
    metrics = add_metrics(prices)
    summary = summarize(metrics)
    save(metrics, summary)
    print(summary.round(4).to_string(index=False))
    print(f"\nSaved {len(metrics):,} price rows to {OUT}")
