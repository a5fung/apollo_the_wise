"""#592 (2026-09-27) — the stable-anchor carry must outlive a week out of the scan.

A name that leaves the flag scan for more than the old 5-day window came back with no carried
pole top, re-anchored fresh, and skipped `_flag_resolved_by` — so a wick over an unresolved flag
became the top again (7 of the 8 wick-walks measured on prod after the 09-04 fix). These pin the
carry window to the finder's own lookback and show the end-to-end consequence on the finder.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import flag_detector as fd
from tests.conftest import make_mock_pool


def test_carry_window_covers_the_pivot_lookback():
    # 25 sessions is ~35 calendar days; a carried top the finder can still use must be fetchable.
    assert db.FLAG_PIVOT_CARRY_DAYS * 5 / 7 >= fd._PIVOT_LOOKBACK_DAYS


@pytest.mark.asyncio
async def test_carry_query_uses_the_window_and_shapes_rows(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[
        {"ticker": "MRVL", "pivot_high_date": date(2026, 8, 20), "pivot_high_price": 251.73},
    ])
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    out = await db.get_yesterday_flag_pivots(date(2026, 9, 8))

    assert out == {"MRVL": (date(2026, 8, 20), 251.73)}
    args = conn.fetch.await_args.args
    assert args[1] == date(2026, 9, 8)
    assert args[2] == db.FLAG_PIVOT_CARRY_DAYS


def _bars(highs_closes, start=date(2026, 7, 1)):
    rows, d = [], start
    for h, c in highs_closes:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        rows.append({"trade_date": d, "high_price": h, "close": c, "low_price": c * 0.98,
                     "open_price": c, "volume": 1_000_000})
        d += timedelta(days=1)
    return rows


def test_a_carried_top_survives_a_later_wick_that_a_fresh_anchor_would_take():
    # Pole top on bar 10 (high 100), a formed flag under it, then a wick to 103 that closes 97.
    bars = [(80 + i, 79 + i) for i in range(10)] + [(100, 99)]
    bars += [(96, 95)] * 8 + [(103, 97)] + [(97, 96)] * 3
    rows = _bars(bars)
    today = len(rows) - 1
    top_date = rows[10]["trade_date"]

    carried = fd._find_pivot_high(rows, today, top_date, 100.0)
    fresh = fd._find_pivot_high(rows, today)

    assert carried == (10, 100.0)          # the #592 rule holds when the top is carried
    assert fresh[1] == 103.0               # without the carry the wick becomes the top
