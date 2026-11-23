"""Tests for the calculated columns (add_metrics) and the KPIs (summarize).

Each test uses a tiny price series where the right answer can be worked
out by hand, so a wrong formula is caught immediately.
"""
import math
import statistics

import pandas as pd
import pytest

from conftest import make_prices
from pull_prices import (
    RISK_FREE_RATE, add_metrics, annual_returns, drawdown_periods,
    monthly_returns, summarize,
)


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


# ---------- Release 1.3: rolling metrics ----------

def test_rolling_columns_stay_blank_until_the_window_is_full(full_prices):
    spy = add_metrics(full_prices).query("ticker == 'SPY'")
    # The first daily return is blank, so a 21-day window of returns is first full on day 22
    assert spy["rolling_vol_21d"].isna().sum() == 21
    assert spy["rolling_vol_63d"].isna().sum() == 63
    assert spy["rolling_return_252d"].isna().sum() == 252


def test_rolling_values_match_a_direct_calculation(full_prices):
    spy = add_metrics(full_prices).query("ticker == 'SPY'").reset_index(drop=True)
    last_21 = spy["daily_return"].iloc[-21:].tolist()
    assert spy["rolling_vol_21d"].iloc[-1] == pytest.approx(statistics.stdev(last_21) * math.sqrt(252))
    assert spy["rolling_return_252d"].iloc[-1] == pytest.approx(
        spy["close"].iloc[-1] / spy["close"].iloc[-253] - 1
    )


# ---------- Release 1.3: risk-adjusted ratios ----------

def test_sharpe_and_sortino_match_their_definitions():
    closes = [100, 103, 101, 104, 102, 106, 105, 109]
    kpi = summarize(add_metrics(make_prices("SPY", closes))).iloc[0]
    daily_rf = RISK_FREE_RATE / 252
    excess = [b / a - 1 - daily_rf for a, b in zip(closes, closes[1:])]
    mean = statistics.mean(excess)
    sharpe = mean / statistics.stdev(excess) * math.sqrt(252)
    downside = math.sqrt(sum(min(x, 0) ** 2 for x in excess) / len(excess))
    sortino = mean / downside * math.sqrt(252)
    assert kpi["sharpe_ratio"] == pytest.approx(sharpe)
    assert kpi["sortino_ratio"] == pytest.approx(sortino)


def test_calmar_is_cagr_over_max_drawdown():
    kpi = summarize(add_metrics(make_prices("SPY", [100, 120, 90, 96, 130]))).iloc[0]
    assert kpi["calmar_ratio"] == pytest.approx(kpi["cagr"] / 0.25)


def test_ratios_are_blank_not_errors_when_there_is_no_downside():
    # Prices only rise: no drawdown, so Calmar and Sortino cannot be calculated
    kpi = summarize(add_metrics(make_prices("SPY", [100, 101, 103, 106]))).iloc[0]
    assert math.isnan(kpi["calmar_ratio"])
    assert kpi["longest_underwater_days"] == 0


# ---------- Release 1.3: drawdown episodes and recovery ----------

def test_drawdown_episodes_peak_trough_recovery():
    #             day: 0    1    2   3   4    5    6    7
    df = add_metrics(make_prices("SPY", [100, 120, 90, 96, 125, 110, 100, 105]))
    eps = drawdown_periods(df)
    assert len(eps) == 2

    first = eps.iloc[0]          # peak day 1 (120), trough day 2 (90), back above 120 on day 4
    assert first["peak_date"] == df["date"].iloc[1].date()
    assert first["trough_date"] == df["date"].iloc[2].date()
    assert first["recovery_date"] == df["date"].iloc[4].date()
    assert first["depth"] == pytest.approx(90 / 120 - 1)
    assert first["days_peak_to_trough"] == 1
    assert first["days_trough_to_recovery"] == 2
    assert first["days_underwater"] == 3
    assert bool(first["recovered"])

    second = eps.iloc[1]         # peak day 4 (125), still below it at the end of the data
    assert pd.isna(second["recovery_date"])
    assert not bool(second["recovered"])
    assert second["days_underwater"] == 3      # day 4 to the last day, day 7
    assert second["depth"] == pytest.approx(100 / 125 - 1)


def test_summary_reports_recovery_of_the_deepest_drawdown():
    df = add_metrics(make_prices("SPY", [100, 120, 90, 96, 125, 110, 100, 105]))
    kpi = summarize(df).iloc[0]
    assert kpi["max_drawdown_recovery_date"] == df["date"].iloc[4].date()
    assert kpi["days_to_recover"] == 2
    assert kpi["longest_underwater_days"] == 3


# ---------- Release 1.3: monthly and annual return tables ----------

def test_monthly_and_annual_returns_from_known_prices():
    df = make_prices("SPY", [100, 100, 110, 121])
    df["date"] = pd.to_datetime(["2021-01-04", "2021-01-29", "2021-02-26", "2022-03-31"])
    m = monthly_returns(add_metrics(df))
    jan, feb, mar_2022 = (m.loc[m["month_label"] == x, "monthly_return"].iloc[0]
                          for x in ["2021-01", "2021-02", "2022-03"])
    assert jan == pytest.approx(0.0)        # 100 -> 100 (from the first observed close)
    assert feb == pytest.approx(0.10)       # 100 -> 110
    assert mar_2022 == pytest.approx(0.10)  # 110 (last known close) -> 121
    a = annual_returns(add_metrics(df)).set_index("year")["annual_return"]
    assert a[2021] == pytest.approx(0.10)
    assert a[2022] == pytest.approx(0.10)


def test_monthly_returns_compound_to_total_return(full_prices):
    metrics = add_metrics(full_prices)
    kpi = summarize(metrics).set_index("ticker")
    m = monthly_returns(metrics)
    for ticker, g in m.groupby("ticker"):
        assert (1 + g["monthly_return"]).prod() - 1 == pytest.approx(kpi.loc[ticker, "total_return"])
