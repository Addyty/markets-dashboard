"""Tests for the SQL scripts in sql/.

Each script runs against a throwaway in-memory SQLite database built from
the fixed test data, in the same table layout the pipeline saves. The key
check: yearly and monthly returns from SQL must compound back to the
five-year total return calculated in Python.
"""
import sqlite3
from pathlib import Path

import pytest

from pull_prices import add_metrics, summarize

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


@pytest.fixture
def db(full_prices):
    metrics = add_metrics(full_prices)
    con = sqlite3.connect(":memory:")
    metrics.to_sql("fact_prices", con, index=False)
    yield con, summarize(metrics).set_index("ticker")
    con.close()


def run(con, name):
    cur = con.execute((SQL_DIR / name).read_text())
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


@pytest.mark.parametrize("name", sorted(p.name for p in SQL_DIR.glob("*.sql")))
def test_every_script_runs_and_returns_rows(db, name):
    con, _ = db
    assert len(run(con, name)) > 0


def test_data_quality_finds_no_problems(db):
    con, _ = db
    for row in run(con, "01_data_quality.sql"):
        assert row["duplicate_dates"] == 0
        assert row["missing_closes"] == 0
        assert row["non_positive_closes"] == 0
        assert row["trading_days"] == 1255


@pytest.mark.parametrize("name, period", [
    ("02_annual_returns.sql", "annual_return"),
    ("03_monthly_returns.sql", "monthly_return"),
])
def test_period_returns_compound_to_total_return(db, name, period):
    con, kpi = db
    rows = run(con, name)
    for ticker in ["SPY", "XLK"]:
        growth = 1.0
        for row in rows:
            if row["ticker"] == ticker:
                growth *= 1 + row[period]
        # SQL rounds each period to 4 decimals, so allow a small tolerance
        assert growth - 1 == pytest.approx(kpi.loc[ticker, "total_return"], abs=2e-3)


def test_drawdown_summary_matches_python(db):
    con, kpi = db
    for row in run(con, "05_drawdown_summary.sql"):
        assert row["max_drawdown"] == pytest.approx(kpi.loc[row["ticker"], "max_drawdown"], abs=1e-4)
        assert row["days_10pct_or_more_below"] <= row["days_below_peak"] <= row["trading_days"]
