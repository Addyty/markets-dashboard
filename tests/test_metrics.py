"""Tests for the calculated columns (add_metrics) and the KPIs (summarize).

Each test uses a tiny price series where the right answer can be worked
out by hand, so a wrong formula is caught immediately.
"""
import math
import statistics

import pandas as pd
import pytest

from conftest import make_prices
from pull_prices import add_metrics, summarize


def test_daily_return():
    df = add_metrics(make_prices("SPY", [100, 110, 99]))
    assert math.isnan(df["daily_return"].iloc[0])          # no previous day
    assert df["daily_return"].iloc[1] == pytest.approx(0.10)  # 100 -> 110
    assert df["daily_return"].iloc[2] == pytest.approx(-0.10)  # 110 -> 99


def test_running_peak_and_drawdown():
    df = add_metrics(make_prices("SPY", [100, 110, 99, 121]))
    assert list(df["running_peak"]) == [100, 110, 110, 121]
    assert df["drawdown"].tolist() == pytest.approx([0, 0, -0.10, 0])


def test_growth_of_100_starts_at_100_whatever_the_price():
    df = add_metrics(make_prices("XLK", [50, 55, 49.5]))
    assert df["indexed"].tolist() == pytest.approx([100, 110, 99])


def test_metrics_are_calculated_separately_per_ticker():
    # If tickers leaked into each other, XLK's first return would be
    # measured against SPY's last price instead of being blank.
    both = pd.concat([make_prices("SPY", [100, 200]), make_prices("XLK", [10, 11])])
    df = add_metrics(both)
    xlk = df[df["ticker"] == "XLK"]
    assert math.isnan(xlk["daily_return"].iloc[0])
    assert xlk["indexed"].tolist() == pytest.approx([100, 110])
    assert xlk["running_peak"].tolist() == [10, 11]


def test_total_return():
    kpi = summarize(add_metrics(make_prices("SPY", [100, 110, 99])))
    assert kpi["total_return"].iloc[0] == pytest.approx(-0.01)


def test_cagr_matches_a_known_two_year_case():
    # 100 grows to 121 over two years: 10% a year (1.1 x 1.1 = 1.21).
    df = make_prices("SPY", [100, 121])
    df["date"] = pd.to_datetime(["2021-01-01", "2023-01-01"])  # 730 days
    kpi = summarize(add_metrics(df))
    assert kpi["cagr"].iloc[0] == pytest.approx(0.10, abs=1e-3)


def test_annual_volatility_uses_sample_std_times_sqrt_252():
    closes = [100, 102, 99, 103, 101, 104]
    df = add_metrics(make_prices("SPY", closes))
    returns = [b / a - 1 for a, b in zip(closes, closes[1:])]
    expected = statistics.stdev(returns) * math.sqrt(252)   # stdev = sample (n - 1)
    kpi = summarize(df)
    assert kpi["annual_volatility"].iloc[0] == pytest.approx(expected)


def test_max_drawdown_value_and_date():
    df = add_metrics(make_prices("SPY", [100, 120, 90, 96, 130]))
    kpi = summarize(df).iloc[0]
    assert kpi["max_drawdown"] == pytest.approx(90 / 120 - 1)  # -25%
    assert str(kpi["max_drawdown_date"]) == str(df["date"].iloc[2].date())


def test_one_kpi_row_per_ticker(full_prices):
    kpi = summarize(add_metrics(full_prices))
    assert sorted(kpi["ticker"]) == ["SPY", "XLK"]
