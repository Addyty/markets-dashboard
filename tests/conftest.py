"""Shared test data.

Tests never download from Yahoo Finance. They use small, fixed datasets
whose correct answers are known in advance, so results are repeatable
and the tests run offline.
"""
import numpy as np
import pandas as pd
import pytest


def make_prices(ticker, closes, start="2021-01-04"):
    """Build a raw price table (the shape fetch_prices returns) from a list of closes."""
    dates = pd.bdate_range(start, periods=len(closes))
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": closes * 1.01,
        "low": closes * 0.99,
        "close": closes,
        "volume": 1_000_000,
        "ticker": ticker,
    })


@pytest.fixture
def full_prices():
    """Two ETFs with 1,255 aligned trading days, like the real dataset.

    Prices follow a fixed random walk (seeded), so every run sees the same data.
    """
    rng = np.random.default_rng(42)
    frames = []
    for ticker, drift in [("SPY", 0.0005), ("XLK", 0.0007)]:
        returns = rng.normal(drift, 0.01, 1255)
        closes = 100 * np.cumprod(1 + returns)
        frames.append(make_prices(ticker, closes))
    return pd.concat(frames, ignore_index=True)
