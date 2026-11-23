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


def test_python_period_tables_match_the_sql_scripts(db, full_prices):
    from pull_prices import annual_returns, monthly_returns
    con, _ = db
    metrics = add_metrics(full_prices)
    py_m = monthly_returns(metrics)
    sql_m = run(con, "03_monthly_returns.sql")
    assert len(py_m) == len(sql_m)
    for py_row, sql_row in zip(py_m.itertuples(), sql_m):
        assert (py_row.ticker, py_row.month_label) == (sql_row["ticker"], sql_row["month"])
        assert round(py_row.monthly_return, 4) == pytest.approx(sql_row["monthly_return"])

    py_a = annual_returns(metrics).set_index(["ticker", "year"])["annual_return"]
    for row in run(con, "02_annual_returns.sql"):
        assert round(py_a[(row["ticker"], int(row["year"]))], 4) == pytest.approx(row["annual_return"])


def test_save_writes_every_table_in_every_format(tmp_path, monkeypatch, full_prices):
    import pandas as pd
    import pull_prices
    monkeypatch.setattr(pull_prices, "OUT", tmp_path)
    metrics = add_metrics(full_prices)
    tables = {
        "fact_prices": metrics,
        "kpi_summary": summarize(metrics),
        "drawdown_periods": pull_prices.drawdown_periods(metrics),
    }
    pull_prices.save(tables)
    with sqlite3.connect(tmp_path / "markets.db") as con:
        names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    sheets = set(pd.ExcelFile(tmp_path / "markets.xlsx").sheet_names)
    for name, table in tables.items():
        assert len(pd.read_csv(tmp_path / f"{name}.csv")) == len(table)
        assert name in names and name in sheets
