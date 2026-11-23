"""Tests for the data-quality gate: fetch_prices and validate.

A clean dataset must pass, and every kind of broken dataset must stop
the run (SystemExit) before anything could be saved.
"""
import pandas as pd
import pytest

import pull_prices
from pull_prices import fetch_prices, validate

TICKERS = ["SPY", "XLK"]


# ---------- validate(): good data passes ----------

def test_clean_data_passes(full_prices, capsys):
    validate(full_prices, TICKERS)  # must not raise
    assert "All 9 checks passed" in capsys.readouterr().out


# ---------- validate(): each kind of bad data is stopped ----------
# Each test checks that the run stops AND that the specific check meant to
# catch that problem is the one reporting FAIL. Otherwise a broken check could
# hide behind a different check that happens to fail too.

def assert_stopped_by(df, check_name, capsys):
    with pytest.raises(SystemExit):
        validate(df, TICKERS)
    assert f"[FAIL] {check_name}" in capsys.readouterr().out


def test_missing_ticker_is_stopped(full_prices, capsys):
    spy_only = full_prices[full_prices["ticker"] == "SPY"]
    assert_stopped_by(spy_only, "All requested tickers present", capsys)


def test_duplicate_row_is_stopped(full_prices, capsys):
    # Repeat one day right next to itself, so dates stay in order and only
    # the duplicate check should object.
    dup = pd.concat([full_prices, full_prices.iloc[[5]]]).sort_values(
        ["ticker", "date"], kind="stable"
    )
    assert_stopped_by(dup, "No duplicate ticker-date rows", capsys)


def test_missing_price_is_stopped(full_prices, capsys):
    full_prices.loc[10, "close"] = None
    assert_stopped_by(full_prices, "No missing prices", capsys)


def test_negative_price_is_stopped(full_prices, capsys):
    full_prices.loc[10, "close"] = -5
    assert_stopped_by(full_prices, "All prices positive", capsys)


def test_high_below_low_is_stopped(full_prices, capsys):
    full_prices.loc[10, "high"] = full_prices.loc[10, "low"] - 1
    assert_stopped_by(full_prices, "High >= low on every row", capsys)


def test_date_outside_window_is_stopped(full_prices, capsys):
    full_prices.loc[0, "date"] = pd.Timestamp("2020-12-31")
    assert_stopped_by(full_prices, "Dates inside the requested window", capsys)


def test_dates_out_of_order_are_stopped(full_prices, capsys):
    spy = full_prices[full_prices["ticker"] == "SPY"]
    shuffled = pd.concat([spy.iloc[::-1], full_prices[full_prices["ticker"] == "XLK"]])
    assert_stopped_by(shuffled, "Dates in chronological order", capsys)


def test_misaligned_dates_are_stopped(full_prices, capsys):
    one_xlk_day = full_prices[full_prices["ticker"] == "XLK"].index[100]
    assert_stopped_by(full_prices.drop(one_xlk_day), "Same trading dates for every ticker", capsys)


def test_too_few_trading_days_is_stopped(full_prices, capsys):
    short = full_prices.groupby("ticker").head(500)  # only ~2 years of a 5-year window
    assert_stopped_by(short, "Trading days per ticker between", capsys)


# ---------- fetch_prices(): no Yahoo calls, a fake downloader instead ----------

class FakeTicker:
    """Stands in for yfinance.Ticker. 'BAD' returns nothing, anything else returns 3 days."""

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, **kwargs):
        if self.symbol == "BAD":
            return pd.DataFrame()
        idx = pd.DatetimeIndex(
            ["2021-01-04", "2021-01-05", "2021-01-06"], name="Date"
        ).tz_localize("America/New_York")
        return pd.DataFrame(
            {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1,
             "Dividends": 0.0, "Stock Splits": 0.0},
            index=idx,
        )


def test_fetch_stops_if_any_ticker_has_no_data(monkeypatch):
    monkeypatch.setattr(pull_prices.yf, "Ticker", FakeTicker)
    with pytest.raises(SystemExit, match="BAD"):
        fetch_prices(["SPY", "BAD"])


def test_fetch_returns_one_long_table(monkeypatch):
    monkeypatch.setattr(pull_prices.yf, "Ticker", FakeTicker)
    df = fetch_prices(["SPY", "XLK"])
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume", "ticker"]
    assert len(df) == 6
    assert df["date"].dt.tz is None  # timezone removed for CSV/SQLite
