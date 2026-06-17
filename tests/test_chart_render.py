"""#267 chart-vision renderer — pins the data adapter + the None-safety contract (the judge path
treats a None render as 'no chart this row' and falls back to text-only, so None must never throw)
and that a valid series renders to real PNG bytes."""
import datetime as dt

import pytest

from agents.market_intelligence.chart_render import bars_to_df, render_daily_chart_png


def _series(n=60, start=20.0):
    rows = []
    d = dt.date(2025, 1, 1)
    px = start
    for _ in range(n):
        o = px
        c = px * 1.01
        rows.append(dict(date=d, open_price=o, high_price=c * 1.01,
                         low_price=o * 0.99, close_price=c, volume=1_000_000))
        px = c
        d += dt.timedelta(days=1)
    return rows


def test_bars_to_df_builds_sorted_ohlcv():
    pd = pytest.importorskip("pandas")
    rows = list(reversed(_series(5)))  # deliberately out of order
    df = bars_to_df(rows)
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.index.is_monotonic_increasing  # sorted ascending by date
    assert len(df) == 5


def test_bars_to_df_drops_rows_missing_ohlc():
    pytest.importorskip("pandas")
    rows = _series(3)
    rows.append(dict(date=dt.date(2025, 2, 1), open_price=None, high_price=1,
                     low_price=1, close_price=1, volume=1))  # missing open → dropped
    df = bars_to_df(rows)
    assert len(df) == 3


def test_bars_to_df_none_on_empty():
    pytest.importorskip("pandas")
    assert bars_to_df([]) is None


def test_render_none_when_too_few_bars():
    # < 20 bars → None BEFORE importing matplotlib (no MA stack to show). No heavy dep needed.
    pd = pytest.importorskip("pandas")
    df = bars_to_df(_series(10))
    assert render_daily_chart_png(df, "X") is None


def test_render_none_when_df_none():
    assert render_daily_chart_png(None, "X") is None


def test_render_returns_png_bytes():
    pytest.importorskip("pandas")
    pytest.importorskip("mplfinance")
    df = bars_to_df(_series(60))
    png = render_daily_chart_png(df, "TEST", as_of=dt.date(2025, 3, 1))
    assert isinstance(png, bytes) and png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic
